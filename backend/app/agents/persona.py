"""Selectable interviewer personalities (no new agent, no migration).

Persona affects tone, preferred probe angles, and a mild plan-slot ordering.
It never changes scoring, question count, rubric, or dedupe rules.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_PERSONA_ID = "balanced"


@dataclass(frozen=True)
class Persona:
    id: str
    name: str
    description: str
    focus_tags: tuple[str, ...]
    probe_style: str
    tone_instruction: str
    preferred_formats: tuple[str, ...]
    preferred_topic_keywords: tuple[str, ...]


PERSONAS: dict[str, Persona] = {
    "balanced": Persona(
        id="balanced",
        name="Balanced",
        description=(
            "Even coverage of concepts, practice, and judgment — today's default interviewer."
        ),
        focus_tags=("Coverage", "Clarity", "Progression"),
        probe_style="balanced",
        tone_instruction="",
        preferred_formats=(),
        preferred_topic_keywords=(),
    ),
    "architect": Persona(
        id="architect",
        name="The Strict Architect",
        description="Presses on structure, reliability, failure modes, and trade-offs.",
        focus_tags=("Trade-offs", "Reliability", "Failure modes"),
        probe_style="architect",
        tone_instruction=(
            "Interviewer lens: Strict Architect. Prefer questions about structure, "
            "reliability, failure modes, scale, and trade-offs. Sound precise and "
            "exacting in the question wording itself. Domain-neutral: apply the same "
            "lens to any subject (engineering, medicine, history, electronics, …)."
        ),
        preferred_formats=("case_study", "conceptual", "code_read"),
        preferred_topic_keywords=(
            "design",
            "system",
            "architect",
            "reliability",
            "scale",
            "trade",
            "failure",
            "structure",
            "protocol",
            "pipeline",
        ),
    ),
    "hiring_manager": Persona(
        id="hiring_manager",
        name="The Hiring Manager",
        description="Focuses on ownership, teamwork, delivery, and measurable impact.",
        focus_tags=("Ownership", "Delivery", "Impact"),
        probe_style="hiring_manager",
        tone_instruction=(
            "Interviewer lens: Hiring Manager. Prefer questions about ownership, "
            "decisions, collaboration, delivery, and impact. Sound practical and "
            "outcome-oriented in the question wording. Domain-neutral: apply to any "
            "subject where judgment and responsibility matter."
        ),
        preferred_formats=("behavioral", "case_study", "conceptual"),
        preferred_topic_keywords=(
            "owner",
            "team",
            "deliver",
            "impact",
            "stakeholder",
            "priority",
            "decision",
            "lead",
            "collaborat",
            "outcome",
        ),
    ),
    "academic": Persona(
        id="academic",
        name="The Academic Deep-Diver",
        description="Digs into fundamentals, complexity, and why a method works.",
        focus_tags=("Fundamentals", "Complexity", "Why it works"),
        probe_style="academic",
        tone_instruction=(
            "Interviewer lens: Academic Deep-Diver. Prefer questions about definitions, "
            "underlying mechanisms, complexity, proofs-of-intuition, and why a method "
            "works. Sound curious and precise in the question wording. Domain-neutral: "
            "apply to any subject with first principles."
        ),
        preferred_formats=("conceptual", "numeric", "mcq"),
        preferred_topic_keywords=(
            "fundament",
            "complex",
            "defin",
            "proof",
            "why",
            "principle",
            "theory",
            "algorithm",
            "mechanis",
            "model",
        ),
    ),
}


def normalize_persona_id(raw: str | None) -> str:
    """Return a valid persona id or raise ValueError('invalid_persona')."""
    if raw is None or str(raw).strip() == "":
        return DEFAULT_PERSONA_ID
    key = str(raw).strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "the_strict_architect": "architect",
        "strict_architect": "architect",
        "the_hiring_manager": "hiring_manager",
        "the_academic_deep_diver": "academic",
        "academic_deep_diver": "academic",
        "deep_diver": "academic",
    }
    key = aliases.get(key, key)
    if key not in PERSONAS:
        raise ValueError("invalid_persona")
    return key


def get_persona(persona_id: str | None) -> Persona:
    try:
        return PERSONAS[normalize_persona_id(persona_id)]
    except ValueError:
        return PERSONAS[DEFAULT_PERSONA_ID]


def persona_prompt_block(persona_id: str | None, *, mode: str = "strict") -> str:
    """Small constant block for the interviewer system prompt. Empty for Balanced."""
    persona = get_persona(persona_id)
    if not persona.tone_instruction:
        return ""
    lines = [
        "Active interviewer persona (fixed for this session; not user-authored):",
        f"- Name: {persona.name}",
        f"- {persona.tone_instruction}",
        "- Ask exactly ONE focused question. Do not change scoring or invent facts.",
    ]
    if mode == "strict":
        lines.append(
            "- Strict mode: keep the question firm or curious, but never praise, "
            "never evaluate the previous answer, and never hint at correctness."
        )
    else:
        lines.append(
            "- Guided mode: you may use a slightly warmer tone that matches this persona."
        )
    return "\n".join(lines)


def bias_plan_for_persona(plan: list[dict], persona_id: str | None) -> list[dict]:
    """Mild early-slot preference for persona-aligned topics/formats. Same length."""
    persona = get_persona(persona_id)
    if not plan or persona.id == DEFAULT_PERSONA_ID:
        return plan
    if not persona.preferred_formats and not persona.preferred_topic_keywords:
        return plan

    scored: list[tuple[int, int, dict]] = []
    for i, slot in enumerate(plan):
        if not isinstance(slot, dict):
            scored.append((0, i, slot))
            continue
        score = 0
        topic = str(slot.get("topic") or "").lower()
        objective = str(slot.get("objective") or "").lower()
        fmt = str(slot.get("format") or "").lower()
        blob = f"{topic} {objective}"
        for kw in persona.preferred_topic_keywords:
            if kw in blob:
                score += 2
        if fmt and fmt in persona.preferred_formats:
            score += 3
        scored.append((score, i, dict(slot)))

    # Keep relative order among equal scores; lift higher scores toward the front
    # but only swap within the first half so required late areas still appear.
    head_n = max(1, len(scored) // 2)
    head = scored[:head_n]
    tail = scored[head_n:]
    head_sorted = sorted(head, key=lambda row: (-row[0], row[1]))
    return [row[2] for row in head_sorted + tail]


def public_persona(persona_id: str | None) -> dict:
    persona = get_persona(persona_id)
    return {
        "persona_id": persona.id,
        "persona_name": persona.name,
        "description": persona.description,
        "focus_tags": list(persona.focus_tags),
    }


def list_public_personas() -> list[dict]:
    return [public_persona(pid) for pid in PERSONAS]
