"""Pick a fresh bank question for one session.

The shuffle is seeded with the session id, so a refresh selects the same
question. History from other sessions is excluded until the pool runs out.
"""

from __future__ import annotations

import random

from app.agents.question_dedupe import fingerprint_tuple, is_duplicate_question
from app.agents.question_quality import prepare_served_question

POOL_BUFFER = 5


def needs_pool_topup(unseen: int, session_questions: int, buffer: int = POOL_BUFFER) -> bool:
    return unseen < int(session_questions) + int(buffer)


def _matches(entry: dict, questions: list[str], fingerprints: set[tuple[str, ...]]) -> bool:
    text = (entry.get("question") or "").strip()
    if not text:
        return False
    if is_duplicate_question(text, questions):
        return True
    fingerprint = fingerprint_tuple(text)
    return len(fingerprint) >= 4 and fingerprint in fingerprints


def least_recent_text(history: list[str], asked: list[str] | None = None) -> str | None:
    """Oldest history question that this session has not already asked."""
    blocked = [q for q in (asked or []) if q]
    for old in history:
        text = (old or "").strip()
        if text and not is_duplicate_question(text, blocked):
            return text
    return None


def pick_pool_question(
    entries: list[dict],
    *,
    seed: str,
    slot: dict | None,
    asked: list[str],
    history: list[str],
    covered_areas: list[str] | None = None,
    mode: str = "strict",
    fingerprints: list[tuple[str, ...]] | None = None,
    avoid_areas: list[str] | None = None,
    reuse: bool = True,
) -> dict | None:
    """Return a bank row with a cleaned question, or None when nothing fresh can be served.

    history is oldest first. Least-recent reuse runs only when reuse is true and every
    pool question has already been seen on this track. The live interviewer leaves
    reuse off so a new question is generated before any old one is repeated.
    """
    slot = slot or {}
    covered = set(covered_areas or [])
    known = {fp for fp in (fingerprints or []) if len(fp) >= 4}
    usable = [entry for entry in entries if not _matches(entry, asked, known)]
    fresh = [entry for entry in usable if not _matches(entry, history, known)]
    avoided = {(area or "").strip() for area in (avoid_areas or []) if (area or "").strip()}
    if avoided:
        steered = [entry for entry in fresh if (entry.get("area") or "") not in avoided]
        if steered:
            fresh = steered
    chosen = _best(fresh, seed, slot, covered) if fresh else None
    if chosen is None and reuse:
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
            fingerprints=list(known),
            avoid_areas=list(avoided),
            reuse=reuse,
        )
    return {**chosen, "question": cleaned}


def _best(entries: list[dict], seed: str, slot: dict, covered: set[str]) -> dict | None:
    if not entries:
        return None
    difficulty = slot.get("difficulty")
    fmt = slot.get("format")
    planned = (slot.get("topic") or "").strip().lower()
    tier = [entry for entry in entries if not difficulty or entry.get("difficulty") == difficulty]
    typed = [entry for entry in tier if not fmt or entry.get("type") == fmt]
    pool = typed or tier or entries
    if planned:
        on_topic = [
            entry
            for entry in pool
            if (entry.get("area") or "").strip().lower() == planned
        ]
        if on_topic:
            pool = on_topic
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
