"""Pick a fresh bank question for one session.

The shuffle is seeded with the session id, so a refresh selects the same
question. History from other sessions is excluded until the pool runs out.
"""

from __future__ import annotations

import random

from app.agents.question_dedupe import is_duplicate_question
from app.agents.question_quality import prepare_served_question

POOL_BUFFER = 5


def needs_pool_topup(unseen: int, session_questions: int, buffer: int = POOL_BUFFER) -> bool:
    return unseen < int(session_questions) + int(buffer)


def _matches(entry: dict, questions: list[str]) -> bool:
    text = (entry.get("question") or "").strip()
    return bool(text) and is_duplicate_question(text, questions)


def pick_pool_question(
    entries: list[dict],
    *,
    seed: str,
    slot: dict | None,
    asked: list[str],
    history: list[str],
    covered_areas: list[str] | None = None,
    mode: str = "strict",
) -> dict | None:
    """Return a bank row with a cleaned question, or None when nothing can be served.

    history is oldest first. The least recently asked row is used only when every
    pool question has already been seen on this track.
    """
    slot = slot or {}
    covered = set(covered_areas or [])
    usable = [entry for entry in entries if not _matches(entry, asked)]
    fresh = [entry for entry in usable if not _matches(entry, history)]
    chosen = _best(fresh, seed, slot, covered) if fresh else None
    if chosen is None:
        chosen = _least_recent(usable, history)
    if chosen is None:
        return None
    cleaned = prepare_served_question(chosen.get("question") or "", mode=mode)
    if not cleaned:
        rest = [entry for entry in usable if entry is not chosen]
        return pick_pool_question(
            rest,
            seed=seed,
            slot=slot,
            asked=asked,
            history=history,
            covered_areas=list(covered),
            mode=mode,
        )
    return {**chosen, "question": cleaned}


def _best(entries: list[dict], seed: str, slot: dict, covered: set[str]) -> dict | None:
    if not entries:
        return None
    difficulty = slot.get("difficulty")
    fmt = slot.get("format")
    tier = [entry for entry in entries if not difficulty or entry.get("difficulty") == difficulty]
    typed = [entry for entry in tier if not fmt or entry.get("type") == fmt]
    pool = typed or tier or entries
    uncovered = [entry for entry in pool if (entry.get("area") or "") not in covered]
    choices = list(uncovered or pool)
    random.Random(seed).shuffle(choices)
    return choices[0]


def _least_recent(entries: list[dict], history: list[str]) -> dict | None:
    for old in history:
        for entry in entries:
            if (entry.get("question") or "").strip() == old.strip():
                return entry
    for old in history:
        for entry in entries:
            if _matches(entry, [old]):
                return entry
    return entries[0] if entries else None
