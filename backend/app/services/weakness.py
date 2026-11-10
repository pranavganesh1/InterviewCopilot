"""Cross-session weakness tracking derived from turn evaluations (no new tables)."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

_COVERAGE_ORDER = {"none": 0, "partial": 1, "good": 2, "excellent": 3}
_MAX_CONCEPTS = 40
_MAX_EVIDENCE = 5


def normalize_concept(raw: str | None) -> str:
    text = re.sub(r"\s+", " ", (raw or "").strip().lower())
    text = re.sub(r"[^a-z0-9 +\-_/]", "", text)
    return text[:80]


def _coverage(turn: Any) -> str | None:
    cov = (getattr(turn, "evaluation_coverage", None) or "").strip().lower()
    return cov if cov in _COVERAGE_ORDER else None


def _gaps(turn: Any) -> list[str]:
    gaps = getattr(turn, "evaluation_gaps", None) or []
    if not isinstance(gaps, list):
        return []
    out = []
    for gap in gaps:
        text = re.sub(r"\s+", " ", str(gap or "")).strip()
        if text:
            out.append(text[:120])
    return out[:6]


def _concept_keys(turn: Any) -> list[str]:
    keys: list[str] = []
    area = normalize_concept(getattr(turn, "question_area", None))
    if area:
        keys.append(area)
    detail = getattr(turn, "evaluation_detail", None) or {}
    if isinstance(detail, dict):
        meta = detail.get("question_meta") if isinstance(detail.get("question_meta"), dict) else {}
        for gap in _gaps(turn):
            key = normalize_concept(gap)
            if key and key not in keys:
                keys.append(key)
        missing = meta.get("missing_concepts") if isinstance(meta, dict) else None
        if isinstance(missing, list):
            for item in missing:
                key = normalize_concept(str(item))
                if key and key not in keys:
                    keys.append(key)
    return keys[:4]


def status_from_labels(labels: list[str]) -> str:
    """Deterministic status from coverage labels (oldest → newest)."""
    usable = [label for label in labels if label in _COVERAGE_ORDER]
    if len(usable) < 1:
        return "not_enough_data"
    recent = usable[-3:]
    if len(usable) >= 2 and all(label in ("good", "excellent") for label in usable[-2:]):
        return "mastered"
    last = recent[-1]
    if last in ("none", "partial"):
        if len(recent) >= 2 and _COVERAGE_ORDER[recent[-1]] > _COVERAGE_ORDER[recent[-2]]:
            return "improving"
        return "weak"
    if len(recent) >= 2 and _COVERAGE_ORDER[recent[-1]] > _COVERAGE_ORDER[recent[0]]:
        return "improving"
    if last in ("good", "excellent"):
        return "improving" if len(usable) == 1 else "mastered"
    return "not_enough_data"


def aggregate_turns(turns: list[Any], *, session_order: list[Any] | None = None) -> dict:
    """Build concept stats from answered turns only.

    `session_order` is optional list of session ids oldest→newest for history charts.
    """
    by_concept: dict[str, dict] = {}
    session_area_scores: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))

    # Preserve encounter order for determinism.
    ordered = list(turns)
    for turn in ordered:
        answer = getattr(turn, "answer", None)
        if answer is None or not str(answer).strip():
            continue
        cov = _coverage(turn)
        if cov is None:
            continue
        session_id = str(getattr(turn, "session_id", "") or "")
        turn_index = int(getattr(turn, "turn_index", 0) or 0)
        points = {"none": 0, "partial": 50, "good": 75, "excellent": 100}[cov]
        for key in _concept_keys(turn):
            row = by_concept.get(key)
            if row is None:
                if len(by_concept) >= _MAX_CONCEPTS:
                    continue
                row = {
                    "concept": key,
                    "times_asked": 0,
                    "labels": [],
                    "evidence": [],
                    "gaps": [],
                }
                by_concept[key] = row
            row["times_asked"] += 1
            row["labels"].append(cov)
            if len(row["evidence"]) < _MAX_EVIDENCE:
                row["evidence"].append(
                    {"session_id": session_id, "turn_index": turn_index, "coverage": cov}
                )
            for gap in _gaps(turn):
                if gap not in row["gaps"] and len(row["gaps"]) < 8:
                    row["gaps"].append(gap)
            if session_id:
                session_area_scores[session_id][key].append(points)

    concepts = []
    for _key, row in by_concept.items():
        labels = row["labels"]
        concepts.append(
            {
                "concept": row["concept"],
                "times_asked": row["times_asked"],
                "last_coverage": labels[-1] if labels else None,
                "trend": labels[-3:],
                "status": status_from_labels(labels),
                "evidence": row["evidence"],
                "missing_concepts": row["gaps"][:5],
            }
        )

    concepts.sort(key=lambda c: (c["status"] != "weak", c["status"] != "improving", c["concept"]))

    history = []
    order = session_order or list(session_area_scores.keys())
    for sid in order[-6:]:
        areas = session_area_scores.get(str(sid)) or {}
        area_scores = {
            area: int(round(sum(vals) / len(vals)))
            for area, vals in areas.items()
            if vals
        }
        if area_scores:
            history.append({"session_id": str(sid), "areas": area_scores})

    weak = [c for c in concepts if c["status"] == "weak"]
    improving = [c for c in concepts if c["status"] == "improving"]
    mastered = [c for c in concepts if c["status"] == "mastered"]

    return {
        "concepts": concepts,
        "weak": weak,
        "improving": improving,
        "mastered": mastered,
        "history": history,
        "has_data": bool(concepts),
    }


def recommended_practice(concepts: list[dict]) -> list[dict]:
    out = []
    for row in concepts:
        if row.get("status") not in ("weak", "improving"):
            continue
        topics = list(row.get("missing_concepts") or [])
        if not topics:
            topics = [f"Review core ideas in {row['concept']}"]
        out.append(
            {
                "concept": row["concept"],
                "status": row["status"],
                "study_topics": topics[:4],
                "practice_themes": [
                    f"Explain {row['concept']} with a worked example",
                    f"Compare two approaches involving {row['concept']}",
                ],
            }
        )
        if len(out) >= 8:
            break
    return out


def build_diagnostics(summary: dict) -> dict:
    """Additive report block. Safe when summary is empty."""
    weak = summary.get("weak") or []
    improving = summary.get("improving") or []
    mastered = summary.get("mastered") or []
    strengths = [
        {"concept": c["concept"], "last_coverage": c.get("last_coverage"), "trend": c.get("trend")}
        for c in mastered[:5]
    ]
    if not strengths:
        strengths = [
            {
                "concept": c["concept"],
                "last_coverage": c.get("last_coverage"),
                "trend": c.get("trend"),
            }
            for c in improving[:3]
        ]
    return {
        "identified_weaknesses": [
            {
                "concept": c["concept"],
                "status": c["status"],
                "evidence": c.get("evidence") or [],
                "missing_concepts": c.get("missing_concepts") or [],
            }
            for c in (weak + improving)[:8]
        ],
        "strengths": strengths,
        "area_score_history": summary.get("history") or [],
        "recommended_practice": recommended_practice(weak + improving),
    }


def weak_concept_names(summary: dict, *, focus: bool) -> list[str]:
    weak = [c["concept"] for c in (summary.get("weak") or [])]
    improving = [c["concept"] for c in (summary.get("improving") or [])]
    if focus:
        return weak + improving
    return weak[:2]
