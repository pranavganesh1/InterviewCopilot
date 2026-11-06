"""Cheap checks for one-focus questions and neutral Strict wording.

Used by the bank builder (before the LLM judge) and by the live interviewer
repair loop. No network, no extra dependencies.
"""

from __future__ import annotations

import re

# One module constant, pasted into the bank prompt and both interviewer prompts.
SINGLE_FOCUS_RULE = """Each turn asks exactly one focused question: at most two short
sentences, plus an optional code snippet or a set of options. No stacked
sub-questions and no "and also".
BAD: "How do you access, slice and handle out-of-bounds errors in Python versus Java?"
GOOD: "In Python, what happens if you slice a list beyond its length, and why?"
"""

QuestionType = str

_CODE_FENCE = re.compile(r"```[\s\S]*?```")
_INLINE_CODE = re.compile(r"`[^`]+`")
_STACK = re.compile(
    r"\band also\b|\bas well as\b|"
    r"compare\s+\S+\s+and\s+\S+\s+and\s+\S+|"
    r",\s+\w+\s+and\s+\w+",
    re.IGNORECASE,
)
_PRAISE = re.compile(
    r"^(nice|good start|great|well done|excellent|correct|incorrect|wrong|"
    r"that's right|thats right|that is right|not quite|"
    r"let's dive deeper|lets dive deeper)\b",
    re.IGNORECASE,
)
_TRANSITION = re.compile(
    r"^(thanks|thank you|understood|moving on|next topic|"
    r"let's continue|lets continue)\b",
    re.IGNORECASE,
)
_PROGRAMMING = re.compile(
    r"\b(python|java|javascript|typescript|coding|programming|dsa|algorithm|"
    r"data structure|sql|backend|frontend|leetcode|arrays?|hash\w*|trees?|graphs?|"
    r"linked list|recursion|complexity|system design|database)\b",
    re.IGNORECASE,
)
_ALLOWED_TYPES = {"coding", "conceptual", "behavioral", "mcq", "code_read"}
_CODE_TYPES = {"coding", "code_read"}

# 8 conceptual, 3 mcq, 2 code_read, 2 coding = 15. Repeats if the plan is longer.
_PROGRAMMING_MIX = (
    ["conceptual"] * 8 + ["mcq"] * 3 + ["code_read"] * 2 + ["coding"] * 2
)


def is_programming_text(*parts: str) -> bool:
    blob = " ".join(p for p in parts if p)
    return bool(_PROGRAMMING.search(blob))


def is_programming_brief(brief: dict | None, subject: str = "") -> bool:
    brief = brief or {}
    topics = " ".join(
        (qa.get("topic") or "")
        for qa in (brief.get("question_areas") or [])
        if isinstance(qa, dict)
    )
    return is_programming_text(subject, brief.get("summary") or "", topics)


def format_for_slot(index: int, *, programming: bool) -> str:
    if not programming:
        return "mcq" if index % 5 == 4 else "conceptual"
    return _PROGRAMMING_MIX[index % len(_PROGRAMMING_MIX)]


def prose_without_code(text: str) -> str:
    cleaned = _CODE_FENCE.sub(" ", text or "")
    cleaned = _INLINE_CODE.sub(" ", cleaned)
    return " ".join(cleaned.split())


def question_focus_violation(text: str) -> str | None:
    """Reject stacked, over-long, or multi-question prompts. None means ok."""
    prose = prose_without_code(text)
    if not prose:
        return "question is empty"
    if prose.count("?") > 1:
        return "question asks more than one thing"
    if len(prose) > 280:
        return "question prose is longer than 280 characters"
    if _STACK.search(prose):
        return "question stacks multiple asks"
    return None


def repair_single_focus(text: str) -> str:
    """Keep the first ask. Caller drops the question if it is still invalid."""
    raw = (text or "").strip()
    raw = re.split(r"\band also\b|\bas well as\b", raw, maxsplit=1, flags=re.IGNORECASE)[0]
    raw = raw.strip(" ,;:")
    if raw.count("?") > 1:
        raw = raw.split("?", 1)[0].strip() + "?"
    if not raw.endswith("?") and "?" not in raw:
        raw = raw.rstrip(".") + "?"
    return raw.strip()


def _drop_leading(text: str, pattern: re.Pattern[str]) -> str:
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    kept: list[str] = []
    dropping = True
    for part in parts:
        if dropping and pattern.search(part.strip()):
            continue
        dropping = False
        kept.append(part)
    cleaned = " ".join(kept).strip()
    return cleaned


def strip_strict_praise(text: str) -> str:
    """Remove evaluative or transitional openers. The stored text is the question."""
    without_praise = _drop_leading(text, _PRAISE)
    without_transition = _drop_leading(without_praise or text, _TRANSITION)
    return (without_transition or without_praise or text).strip()


def strict_praise_violation(text: str) -> str | None:
    first = re.split(r"(?<=[.!?])\s+", (text or "").strip(), maxsplit=1)[0]
    if first and _PRAISE.search(first.strip()):
        return "strict question opens with an evaluation"
    return None


def mcq_violation(options: list | None, correct_index) -> str | None:
    opts = [str(o).strip() for o in (options or [])]
    if len(opts) != 4:
        return "mcq needs exactly 4 options"
    if any(not o for o in opts):
        return "mcq option is empty"
    if len({o.lower() for o in opts}) != 4:
        return "mcq options must be distinct"
    lengths = [len(o) for o in opts]
    if min(lengths) and max(lengths) / min(lengths) > 2.5:
        return "mcq options differ too much in length"
    if not isinstance(correct_index, int) or isinstance(correct_index, bool):
        return "mcq needs exactly one correct index"
    if not 0 <= correct_index <= 3:
        return "mcq correct index is out of range"
    return None


def score_mcq(answer: str, correct_index) -> tuple[str, list[str], list[str]]:
    """Deterministic coverage. Returns coverage, strengths, gaps."""
    try:
        chosen = int(str(answer).strip())
    except (TypeError, ValueError):
        chosen = -1
    correct = isinstance(correct_index, int) and not isinstance(correct_index, bool)
    if correct and chosen == correct_index:
        return "excellent", ["Selected the correct option."], []
    return "none", [], ["Selected a different option."]


def prepare_bank_question(raw: dict, *, programming: bool) -> dict | None:
    """Repair or drop a bank row. Never returns a question that fails the cheap checks."""
    if not isinstance(raw, dict):
        return None
    question = repair_single_focus(str(raw.get("question") or ""))
    if question_focus_violation(question):
        return None
    qtype = str(raw.get("type") or "conceptual")
    if qtype not in _ALLOWED_TYPES:
        qtype = "conceptual"
    if not programming and qtype in _CODE_TYPES:
        qtype = "conceptual"
    options = raw.get("options") or []
    correct = raw.get("correct_index")
    snippet = str(raw.get("code_snippet") or "").strip()
    if qtype == "mcq":
        if mcq_violation(options, correct):
            return None
    elif qtype == "code_read":
        if not snippet:
            return None
        options, correct = [], None
    else:
        options, correct, snippet = [], None, ""
    area = str(raw.get("area") or "General").strip() or "General"
    objective = str(raw.get("objective") or "").strip() or area
    return {
        **raw,
        "area": area,
        "question": question,
        "type": qtype,
        "objective": objective,
        "options": [str(o).strip() for o in options] if qtype == "mcq" else [],
        "correct_index": correct if qtype == "mcq" else None,
        "explanation": str(raw.get("explanation") or raw.get("expected_answer_sketch") or ""),
        "code_snippet": snippet if qtype == "code_read" else "",
    }


def public_question_meta(detail: dict | None, *, reveal: bool) -> dict:
    """Fields safe to show on the session API. The key stays server-side until reveal."""
    meta = {}
    if isinstance(detail, dict):
        stored = detail.get("question_meta")
        if isinstance(stored, dict):
            meta = stored
    out: dict = {}
    options = meta.get("options") or []
    if options:
        out["options"] = list(options)
    snippet = meta.get("code_snippet") or ""
    if snippet:
        out["code_snippet"] = snippet
    if meta.get("objective"):
        out["objective"] = meta["objective"]
    if reveal:
        if isinstance(meta.get("correct_index"), int):
            out["correct_index"] = meta["correct_index"]
        if meta.get("explanation"):
            out["explanation"] = meta["explanation"]
    return out
