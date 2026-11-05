"""Build a consolidated feedback report from persisted per-turn evaluations.

Used as the reliable base for final reports (and as a fallback when the LLM
feedback agent is unavailable). Only submitted answers are assessed.
"""

from __future__ import annotations

from app.agents.feedback_agent import (
    AssessedCompetency,
    FeedbackReportContent,
    QuestionEvidence,
)
from app.models.interview import InterviewSession, SessionTurn

_COVERAGE_RANK = {"none": 0, "partial": 1, "good": 2, "excellent": 3}
_COVERAGE_SCORE = {"none": 0, "partial": 50, "good": 75, "excellent": 100}
_LEVEL_FROM_COVERAGE = {
    "none": "weak",
    "partial": "developing",
    "good": "solid",
    "excellent": "strong",
}


def performance_level_from_score(score: int | None) -> str:
    if score is None:
        return "Not assessed"
    if score >= 85:
        return "Excellent"
    if score >= 70:
        return "Strong"
    if score >= 50:
        return "Developing"
    return "Needs improvement"


def enrich_assessments_with_turns(content: dict, answered_turns: list[SessionTurn]) -> dict:
    """Merge real Q&A + saved eval fields onto question_assessments (by turn_index)."""
    by_index = {t.turn_index: t for t in answered_turns}
    items = list(content.get("question_assessments") or [])
    enriched = []
    for item in items:
        row = dict(item) if isinstance(item, dict) else {}
        t = by_index.get(int(row.get("turn_index") or 0))
        if t is not None:
            detail = t.evaluation_detail if isinstance(t.evaluation_detail, dict) else {}
            coverage = (row.get("coverage") or t.evaluation_coverage or "none").lower()
            row.setdefault("question", t.question or "")
            row.setdefault("answer", t.answer or "")
            if not row.get("strengths"):
                row["strengths"] = list(t.evaluation_strengths or [])
            if not row.get("gaps"):
                row["gaps"] = list(t.evaluation_gaps or [])
            if not row.get("expected_answer_explanation"):
                row["expected_answer_explanation"] = str(
                    detail.get("expected_answer_explanation") or ""
                )
            if not row.get("corrected_code"):
                row["corrected_code"] = str(detail.get("corrected_code") or "")
            if not row.get("time_complexity"):
                row["time_complexity"] = str(detail.get("time_complexity") or "")
            if not row.get("space_complexity"):
                row["space_complexity"] = str(detail.get("space_complexity") or "")
            if row.get("score") is None:
                row["score"] = _COVERAGE_SCORE.get(coverage)
            if not row.get("evidence_excerpt"):
                row["evidence_excerpt"] = (t.answer or "").strip().replace("\n", " ")[:240]
        enriched.append(row)

    # Ensure every answered turn appears even if the agent omitted it.
    present = {int(r.get("turn_index") or 0) for r in enriched}
    for t in answered_turns:
        if t.turn_index in present:
            continue
        coverage = (t.evaluation_coverage or "none").lower()
        detail = t.evaluation_detail if isinstance(t.evaluation_detail, dict) else {}
        enriched.append(
            {
                "turn_index": t.turn_index,
                "coverage": coverage if coverage in _COVERAGE_SCORE else "none",
                "observation": "Submitted answer recorded.",
                "evidence_excerpt": (t.answer or "").strip().replace("\n", " ")[:240],
                "question": t.question or "",
                "answer": t.answer or "",
                "strengths": list(t.evaluation_strengths or []),
                "gaps": list(t.evaluation_gaps or []),
                "expected_answer_explanation": str(detail.get("expected_answer_explanation") or ""),
                "corrected_code": str(detail.get("corrected_code") or ""),
                "time_complexity": str(detail.get("time_complexity") or ""),
                "space_complexity": str(detail.get("space_complexity") or ""),
                "score": _COVERAGE_SCORE.get(coverage, 0),
            }
        )
    enriched.sort(key=lambda r: int(r.get("turn_index") or 0))
    content = {**content, "question_assessments": enriched}
    return content


def build_report_from_saved_evaluations(
    *,
    session: InterviewSession,
    answered_turns: list[SessionTurn],
    brief_content: dict | None,
    max_turns: int,
) -> FeedbackReportContent:
    brief = brief_content or {}
    competencies = brief.get("competencies") or []
    question_areas = [
        qa.get("topic") for qa in (brief.get("question_areas") or []) if qa.get("topic")
    ]

    assessments: list[QuestionEvidence] = []
    strengths: list[str] = []
    gaps: list[str] = []

    for t in answered_turns:
        coverage = (t.evaluation_coverage or "none").lower()
        if coverage not in _COVERAGE_RANK:
            coverage = "none"
        detail = t.evaluation_detail if isinstance(t.evaluation_detail, dict) else {}
        explanation = str(detail.get("expected_answer_explanation") or "").strip()
        strength_bits = [str(s) for s in (t.evaluation_strengths or []) if s]
        gap_bits = [str(g) for g in (t.evaluation_gaps or []) if g]
        strengths.extend(strength_bits)
        gaps.extend(gap_bits)
        observation = (
            "; ".join(strength_bits[:2])
            if strength_bits
            else ("; ".join(gap_bits[:2]) if gap_bits else "Submitted answer recorded.")
        )
        if explanation and len(observation) < 40:
            observation = f"{observation} {explanation}"[:280]
        excerpt = (t.answer or "").strip().replace("\n", " ")
        assessments.append(
            QuestionEvidence(
                turn_index=t.turn_index,
                coverage=coverage,  # type: ignore[arg-type]
                observation=observation[:400],
                evidence_excerpt=excerpt[:240],
                question=t.question or "",
                answer=t.answer or "",
                strengths=strength_bits,
                gaps=gap_bits,
                expected_answer_explanation=explanation,
                corrected_code=str(detail.get("corrected_code") or ""),
                time_complexity=str(detail.get("time_complexity") or ""),
                space_complexity=str(detail.get("space_complexity") or ""),
                score=_COVERAGE_SCORE.get(coverage, 0),
            )
        )

    answered_areas = {t.question_area for t in answered_turns}
    unassessed = [a for a in question_areas if a not in answered_areas]

    if not assessments:
        coverage_status = "MINIMAL"
        summary = (
            "This interview ended before any answers were submitted. "
            "No question-level evidence was available to assess."
        )
    else:
        avg = sum(_COVERAGE_RANK[a.coverage] for a in assessments) / len(assessments)
        if len(assessments) >= max_turns and avg >= 2:
            coverage_status = "COMPLETE"
        elif avg >= 1:
            coverage_status = "PARTIAL"
        else:
            coverage_status = "MINIMAL"
        summary = (
            f"Evaluated {len(assessments)} of {max_turns} questions "
            f"({session.mode} mode). Coverage is {coverage_status.lower()} "
            "based on saved answer evaluations."
        )

    # Deduplicate while preserving order.
    def _uniq(items: list[str], limit: int = 8) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in items:
            key = item.strip()
            if not key or key.lower() in seen:
                continue
            seen.add(key.lower())
            out.append(key)
            if len(out) >= limit:
                break
        return out

    strengths_u = _uniq(strengths)
    gaps_u = _uniq(gaps)
    if not strengths_u and assessments:
        strengths_u = ["Submitted answers for review"]
    if not gaps_u and unassessed:
        gaps_u = [f"Not covered in this session: {', '.join(unassessed[:3])}"]

    competency_rows: list[AssessedCompetency] = []
    for comp in competencies:
        name = comp.get("name") if isinstance(comp, dict) else None
        if not name:
            continue
        related = [
            a
            for a, t in zip(assessments, answered_turns, strict=False)
            if (
                (t.question_area and name.lower() in t.question_area.lower())
                or name.lower() in (t.question or "").lower()
            )
        ]
        # Fallback: if area names don't match competency names, use overall avg.
        if not related and assessments:
            related = assessments
            status = "PARTIALLY_ASSESSED"
        elif related:
            status = "ASSESSED"
        else:
            competency_rows.append(
                AssessedCompetency(
                    competency_name=name,
                    assessment_status="NOT_ASSESSED",
                    level=None,
                    observation="Not probed in the submitted answers.",
                    confidence="LOW",
                )
            )
            continue
        avg_cov = max(related, key=lambda a: _COVERAGE_RANK[a.coverage]).coverage
        competency_rows.append(
            AssessedCompetency(
                competency_name=name,
                assessment_status=status,  # type: ignore[arg-type]
                level=_LEVEL_FROM_COVERAGE.get(avg_cov),  # type: ignore[arg-type]
                observation=related[0].observation,
                confidence="MEDIUM" if status == "ASSESSED" else "LOW",
            )
        )

    recommendations = [f"Review gaps: {g}" for g in gaps_u[:3]] or [
        "Continue practicing with another Strict interview on this track."
    ]
    if unassessed:
        recommendations.append(f"Next session: cover {', '.join(unassessed[:3])}.")

    return FeedbackReportContent(
        session_mode=session.mode if session.mode in ("strict", "guided") else "strict",
        summary_overview=summary,
        coverage_status=coverage_status,  # type: ignore[arg-type]
        question_assessments=assessments,
        competency_assessments=competency_rows,
        strengths=strengths_u,
        improvement_areas=gaps_u,
        unassessed_topics=unassessed,
        recommendations=_uniq(recommendations, limit=5),
    )
