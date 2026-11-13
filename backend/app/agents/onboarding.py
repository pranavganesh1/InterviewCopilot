import re
import time
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.gateway.structured import structured_completion
from app.services.preparation_goals import (
    EMPTY_PREFERENCES,
    GOAL_INTEREST_LABELS,
    build_resume_goal_options,
    infer_candidate_background,
    merge_preferences,
    next_goal_followup,
    normalize_preferences,
    preferences_ready,
)

log = get_logger(__name__)

# Optional profile sections — never hard blockers for goals/completion.
SUGGESTED_CATEGORIES = ("project", "skill", "education")

ITEM_CATEGORIES = Literal["project", "internship", "skill", "achievement", "education", "other"]

ITEM_CATEGORIES_SET = {
    "project",
    "internship",
    "skill",
    "achievement",
    "education",
    "other",
}

SYSTEM_PROMPT = """You are the InterviewCopilot onboarding coach (profile phase) —
a thoughtful human career mentor / interviewer for ANY background (Commerce, Physics,
Arts, CS, Engineering, self-taught, fresher, career switcher, or undecided). Never
assume everyone is a Computer Science student.

Your job each turn: understand the candidate's latest answer in context, respond like
a real mentor, then ask exactly ONE clear next question (or gently move topics when
the current one is explored enough).

Conversation shape (almost every turn):
1) React — briefly evaluate what they said (strength, clarity, or a specific detail).
2) Reflect — echo 1 concrete detail from THEIR words (tool, concept, outcome, choice).
3) Advance — ONE open question (What / How / Which), OR a smooth bridge to the next
   planned topic if the current topic is already well covered.

Tone:
- Warm, attentive, encouraging. 2–5 short sentences is fine when they gave a rich answer.
- Vary openings. Ban stock loops: "Got it", "Got it — thanks", "Thanks for sharing",
  "Thanks for the details", "I've noted that", "I've added … to your profile/entry",
  "Nice —", "That gives me a clearer picture", "That gives me a clear picture".
- Never narrate database/vault bookkeeping ("I've added the purpose, technologies…").
  Silently put facts in extracted_items only; the reply must sound human, not like a form.
- Never invent education, skills, projects, jobs, or achievements.
- Resume / vault facts are unconfirmed until the candidate affirms them.
- Never use judgmental labels (unqualified, weak, incomplete dropout, etc.).
- If they say they don't know / aren't sure / have no experience: support them, do not
  dig for why, and move to a lighter related angle or the next suggested topic.

You receive:
- candidate_background, coach_context (current_topic, focus_locked, focus_kind,
  last_assistant_question, last_question_intent, asked_questions, answers_received,
  confirmed_facts, skipped_categories, pending_followup)
- known_vault_summary, suggested_next_topics, possible_duplicates, profile_gaps
- conversation_mode, conversation_so_far, new_user_message

Hard rules:
1. ONE question only. Never re-ask something already answered in asked_questions,
   conversation_so_far, answers_received, or known_vault_summary (including rephrasing).
   Prefer What / How / Which. Never ask yes/no when you need details. If they only say
   yes/no to a detail ask, rephrase with a short example — do not repeat the same ask.
2. Incomplete / ambiguous answers: ask ONE specific clarification on the SAME topic.
   Do not ignore gaps and jump ahead, and do not stack multiple clarifications.
3. Rich / complete answers: reflect one concrete detail from THEIR words, then either
   one deeper aspect OR a smooth bridge to suggested_next_topics — never a redundant
   follow-up on the same fact they just covered.
4. Short replies ("yes", "okay", "sure", "continue", "next", "skip", "not sure")
   resolve against last_assistant_question + last_question_intent + current_topic.
   Never treat them as a new topic pick. If they already affirmed a topic offer
   (focus_locked / current_topic set), do NOT ask them to confirm that topic again —
   advance with a real explore question.
5. Topic lock: if focus_locked and current_topic are set, stay there until the user
   asks to switch, skips, or the topic is sufficiently explored (several solid details
   already in conversation / vault for that item). Then bridge naturally, e.g.
   "You've covered a lot on X — shall we look at your Y next?" using
   suggested_next_topics when helpful. Never silently replace the topic.
6. Adapt to background (Commerce → business/analytics; Physics → research/analytical;
   CS → projects/skills only if the resume supports it). Do not force DSA/programming
   on non-tech backgrounds unless they ask.
7. Education, projects, internships, achievements are OPTIONAL — never demand them.
8. possible_duplicates: ask same vs distinct; never silently merge.
9. When ready for goals (vault signal / they skip ahead), set phase="goals",
   show_goal_menu=true so the UI can show chips.
10. extracted_items: only facts the user just stated (short detail keys). Do not claim
    in the reply that anything was saved or added.
11. preparation_update empty unless they volunteer goals/role.
12. conversation_mode:
   - ai_interview: warm-up from THEIR vault; one question at a time.
   - explore_projects / test_skills: only real vault items; never invent tech.
   - career_goal: discover prep goals; fill preparation_update when stated.
"""

GOALS_SYSTEM_PROMPT = """You are the InterviewCopilot preparation coach (goals phase) —
a thoughtful mentor for ANY field. Do not assume software engineering.

Each turn: react to what they just said, reflect one concrete detail, then ONE clear
next question (prefer next_goal_followup). Sound human — not like a form or vault logger.

Tone examples (adapt to THEIR field; don't copy blindly):
- Commerce → "Business analyst is a solid path. Excel, SQL, or a case study first?"
- Physics → "Research or technical roles both fit analytical training — which appeals more?"
- CS with Python → "Nice — Python is a strong anchor. A project story or core language
  drills first?"
- Undecided → "No rush — skill practice, role exploration, or interview conversational
  prep?"

Avoid repeating "Got it" / "Thanks for sharing" / "Nice —" /
"That gives me a clearer picture" / "I've added…". Never claim profile saves in
the reply text. Never re-confirm a topic the candidate already chose.

You receive:
- candidate_background, coach_context, known_vault_summary, resume_highlights,
  suggested_next_topics
- available_skills, available_projects, suggested_roles, suggested_technical_areas,
  suggested_prep_topics
- project_options, project_aspect_options
- current_preparation_preferences, next_goal_followup, conversation_so_far, new_user_message

Interest ids: technical, skill, project, placement, behavioral.

Rules:
1. ONE follow-up at a time. Prefer next_goal_followup. Never repeat asked_questions.
2. Do not re-collect resume facts unless confirming ambiguity.
3. Offer suggested_roles / suggested_prep_topics for THEIR field; allow any direction.
4. Mention at most 1–2 resume items. Never invent facts or claim verification/saves.
5. If no projects: skip project deep-dive pressure; offer skills/goals/behavioral instead.
6. technical interest for non-CS → domain/analytical prep, not forced DSA, unless asked.
7. When follow-ups covered (next_goal_followup null), confirm prefs, phase="ready", summary.
8. show_goal_menu=true only when interests empty.
9. Warm, concise reply. Support changing focus / "I'm not sure yet" anytime.
"""

FINISHED_SYSTEM_PROMPT = """You are the InterviewCopilot profile coach. This student has
already finished onboarding. They are revisiting to edit or enrich their vault or goals.

Rules:
- Do NOT restart the intake questionnaire.
- Respond like a mentor: brief natural acknowledgment + at most one clarifying question.
- Never say "I've added…" / "saved to your profile" in the reply; use extracted_items
  silently when they state new facts.
- Interpret short yes/no/skip answers from conversation context.
- Goal changes go in preparation_update.
- Always set phase="ready" and onboarding_complete=true.
"""


class ExtractedItem(BaseModel):
    category: ITEM_CATEGORIES
    title: str = Field(max_length=255)
    details: dict[str, str] = {}


class PreparationUpdate(BaseModel):
    interests: list[str] | None = None
    target_role: str | None = None
    technical_areas: list[str] | None = None
    focus_skills: list[str] | None = None
    focus_projects: list[str] | None = None
    project_aspects: list[str] | None = None
    placement_target: str | None = None
    experience_level: str | None = None
    behavioral_goals: str | None = None
    confirmed: bool | None = None


class OnboardingTurn(BaseModel):
    reply: str
    extracted_items: list[ExtractedItem] = []
    onboarding_complete: bool = False
    phase: Literal["profile", "goals", "ready"] = "profile"
    show_goal_menu: bool = False
    preparation_update: PreparationUpdate | None = None


class OnboardingState(TypedDict, total=False):
    message: str
    history: list[dict]
    vault_summary: list[dict]
    possible_duplicates: list[dict]
    profile_gaps: dict
    preparation_preferences: dict
    available_skills: list[str]
    available_projects: list[str]
    resume_goal_options: dict
    candidate_background: dict
    coach_context: dict
    conversation_mode: str
    already_finished: bool
    phase: str
    meta: dict
    turn: dict


def compute_profile_gaps(
    vault_summary: list[dict],
    coach_context: dict | None = None,
) -> dict:
    """Optional gaps only — missing sections are suggestions, not failures."""
    cats = {str(i.get("category") or "") for i in vault_summary}
    ctx = coach_context or {}
    skipped = {str(c) for c in (ctx.get("skipped_categories") or [])}
    na = {str(c) for c in (ctx.get("not_applicable_categories") or [])}
    missing_categories = [
        c for c in SUGGESTED_CATEGORIES if c not in cats and c not in skipped and c not in na
    ]
    incomplete_projects = [
        {
            "title": i.get("title"),
            "missing_details": i.get("missing_details") or [],
        }
        for i in vault_summary
        if i.get("category") == "project" and (i.get("missing_details") or [])
    ]
    category_status = {}
    for c in SUGGESTED_CATEGORIES:
        if c in cats:
            category_status[c] = "present"
        elif c in na:
            category_status[c] = "not_applicable"
        elif c in skipped:
            category_status[c] = "skipped"
        else:
            category_status[c] = "not_provided"
    return {
        "missing_categories": missing_categories,
        "incomplete_projects": incomplete_projects,
        "category_status": category_status,
        "optional": True,
    }


def vault_is_ready(
    vault_summary: list[dict],
    coach_context: dict | None = None,
) -> bool:
    """Unlock goals with any vault signal, or when the candidate chooses to proceed."""
    ctx = coach_context or {}
    if ctx.get("proceed_to_goals"):
        return True
    if vault_summary:
        return True
    skipped = {str(c) for c in (ctx.get("skipped_categories") or [])}
    return "vault" in skipped or set(SUGGESTED_CATEGORIES) <= skipped


def derive_phase(
    *,
    vault_summary: list[dict],
    preferences: dict | None,
    already_finished: bool,
    coach_context: dict | None = None,
) -> str:
    if already_finished or preferences_ready(preferences):
        return "ready"
    if vault_is_ready(vault_summary, coach_context):
        return "goals"
    return "profile"


def _question_fingerprint(text: str) -> str:
    cleaned = " ".join((text or "").lower().split())
    return cleaned[:180]


def _norm_msg(text: str) -> str:
    return " ".join((text or "").lower().split())


def last_assistant_content(history: list[dict] | None) -> str:
    for msg in reversed(history or []):
        if msg.get("role") == "assistant":
            return str(msg.get("content") or "")
    return ""


def assistant_asked_about_duplicates(text: str) -> bool:
    t = _norm_msg(text)
    return ("same item" in t and "keep both" in t) or (
        "keep both" in t and ("same" in t or "duplicate" in t or "similar" in t)
    )


def recent_duplicate_prompt(history: list[dict] | None, *, lookback: int = 8) -> bool:
    """True if a recent assistant turn asked same-vs-both (not only the latest message)."""
    seen = 0
    for msg in reversed(history or []):
        if msg.get("role") != "assistant":
            continue
        seen += 1
        if assistant_asked_about_duplicates(str(msg.get("content") or "")):
            return True
        if seen >= lookback:
            break
    return False


def classify_duplicate_answer(message: str) -> str | None:
    """Return 'keep_both', 'merge', or None if unclear."""
    t = _norm_msg(message)
    if not t:
        return None
    merge_exact = {
        "same",
        "same item",
        "merge",
        "combine",
        "one",
        "they're the same",
        "they are the same",
        "its the same",
        "it's the same",
        "yes same",
        "same one",
    }
    keep_exact = {
        "both",
        "keep both",
        "give both",
        "keep them",
        "separate",
        "different",
        "two",
        "keep separate",
        "they're different",
        "they are different",
    }
    if t in keep_exact or t.startswith("keep both") or "give both" in t:
        return "keep_both"
    if t in merge_exact or t.startswith("merge") or t.startswith("same item"):
        return "merge"
    if "both" in t and "not" not in t:
        return "keep_both"
    if t in {"yes", "y"} and "both" not in t:
        # Ambiguous yes — treat as merge only when prior prompt offered same-first.
        return None
    if t in {"no", "n"}:
        return "keep_both"
    return None


def is_ack_only(message: str) -> bool:
    t = _norm_msg(message)
    if not t or len(t) > 40:
        return False
    acks = {
        "ok",
        "okay",
        "k",
        "yes",
        "yep",
        "yeah",
        "sure",
        "fine",
        "alright",
        "all right",
        "lets start",
        "let's start",
        "lets us start",
        "let us start",
        "start",
        "go ahead",
        "continue",
        "next",
        "ready",
        "thanks",
        "thank you",
        "cool",
        "great",
        "good",
        "done",
    }
    return t in acks


_PERSISTENCE_CLAIM_RE = re.compile(
    r"(?i)(?:i(?:'ve| have)\s+(?:added|saved|updated|noted|recorded|stored)\b"
    r"[^.?!\n]{0,160}(?:profile|vault|entry|project|skills?|details?)[^.?!\n]{0,80}[.!]?\s*)"
)


def sanitize_coach_reply(reply: str) -> str:
    """Strip vault-bookkeeping phrases the model sometimes invents."""
    text = (reply or "").strip()
    if not text:
        return text
    cleaned = _PERSISTENCE_CLAIM_RE.sub("", text)
    # Drop leading stock acks / filler bridges when more substance follows.
    cleaned = re.sub(
        r"(?i)^(?:(?:got it|thanks for(?: the)?(?: sharing|details)?|"
        r"nice|that gives me a clear(?:er)? picture(?: of [^.?!,—\-]*)?)\b"
        r"[.!,—\-\s]*)+",
        "",
        cleaned,
    )
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,—-")
    return cleaned or text


def is_affirmative(message: str) -> bool:
    t = _norm_msg(message)
    return t in {
        "yes",
        "y",
        "yep",
        "yeah",
        "sure",
        "ok",
        "okay",
        "k",
        "alright",
        "all right",
        "go ahead",
        "continue",
        "next",
        "lets start",
        "let's start",
        "let us start",
        "lets us start",
        "start",
        "ready",
    }


def is_negative_or_skip(message: str) -> bool:
    t = _norm_msg(message)
    return t in {
        "no",
        "n",
        "nope",
        "nah",
        "skip",
        "pass",
        "not sure",
        "idk",
        "i don't know",
        "i dont know",
        "none",
        "nothing",
        "later",
    }


def wants_topic_switch(message: str) -> bool:
    """True when the user asks to leave the current focus for something else."""
    low = (message or "").strip().lower()
    if not low:
        return False
    cues = (
        "another topic",
        "different topic",
        "different project",
        "another project",
        "different skill",
        "another skill",
        "switch to",
        "change topic",
        "talk about something else",
        "something else",
        "move on",
        "next topic",
        "instead",
    )
    return any(c in low for c in cues)


def ensure_nonempty_reply(
    reply: str,
    *,
    vault_summary: list[dict] | None = None,
    duplicates_resolved: str | None = None,
    coach_context: dict | None = None,
) -> str:
    text = sanitize_coach_reply(reply or "")
    if text:
        return text
    if duplicates_resolved == "keep_both":
        return (
            "Kept both entries. Which project or skill should we dig into next?"
        )
    if duplicates_resolved == "merge":
        return (
            "Merged those into one entry. What was the goal of that item, "
            "and which tools did you use?"
        )
    focused = continue_topic_reply(coach_context, vault_summary)
    if focused:
        return focused
    projects = [
        str(i.get("title") or "")
        for i in (vault_summary or [])
        if i.get("category") == "project" and i.get("title")
    ]
    skills = [
        str(i.get("title") or "")
        for i in (vault_summary or [])
        if i.get("category") == "skill" and i.get("title")
    ]
    if projects:
        return (
            f"What was the goal of your “{projects[0]}” project, "
            "and which tools did you use?"
        )
    if skills:
        return f"How have you used {skills[0]} in a real task or project?"
    return (
        "What would you like to prepare for first — a project story, "
        "a skill, or a target role?"
    )


def ack_followup_question(
    vault_summary: list[dict] | None = None,
    coach_context: dict | None = None,
) -> str:
    return ensure_nonempty_reply(
        "", vault_summary=vault_summary, coach_context=coach_context
    )


_PRACTISE_RE = re.compile(
    r"(?i)\b(?:i(?:'d| would)?\s+like\s+to\s+|let'?s\s+|want\s+to\s+|wanna\s+)?"
    r"(?:practi[sc]e|be\s+interviewed(?:\s+on)?|interview\s+me(?:\s+on)?|"
    r"mock\s+interview(?:\s+on)?|quiz\s+me(?:\s+on)?)\s+"
    r"(?:on\s+|with\s+|about\s+|in\s+)?(?P<subject>.+)$"
)


def classify_practise_intent(
    message: str, vault_summary: list[dict] | None = None
) -> dict | None:
    """Return {subject, track_type} when the user asks to practise / be interviewed."""
    text = (message or "").strip()
    if not text or len(text) > 160:
        return None
    m = _PRACTISE_RE.search(text)
    if not m:
        low = text.lower()
        if not any(
            k in low
            for k in (
                "practise",
                "practice",
                "interview me",
                "mock interview",
                "quiz me",
            )
        ):
            return None
        subject = text
    else:
        subject = (m.group("subject") or "").strip(" .!?\"'")
    subject = re.sub(r"\s+", " ", subject).strip()
    if not subject or len(subject) > 80:
        return None
    # Prefer an exact vault skill/project title when the user named one.
    titles = [
        str(i.get("title") or "").strip()
        for i in (vault_summary or [])
        if i.get("category") in ("skill", "project") and i.get("title")
    ]
    low_sub = subject.lower()
    for title in titles:
        if title.lower() == low_sub or title.lower() in low_sub or low_sub in title.lower():
            cat = next(
                (
                    str(i.get("category"))
                    for i in (vault_summary or [])
                    if str(i.get("title") or "").strip() == title
                ),
                "skill",
            )
            return {
                "subject": title,
                "track_type": "topic" if cat == "project" else "topic",
            }
    # Strip leading "my " for cleaner track subjects.
    if low_sub.startswith("my "):
        subject = subject[3:].strip()
    return {"subject": subject[:80], "track_type": "topic"}


def practise_followup_reply(subject: str) -> str:
    return (
        f"Great — we can run a focused interview on {subject}. "
        "Want to start now?"
    )


# Cross-domain resume abbreviations → related tokens for vault matching.
# Not domain-specific routing — expands both user text and vault text equally.
_TOPIC_SYNONYM_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"dbms", "database", "databases", "sql", "rdbms"}),
    frozenset({"ml", "machine", "learning", "machinelearning"}),
    frozenset({"ai", "artificial", "intelligence"}),
    frozenset({"nlp", "natural", "language", "processing"}),
    frozenset({"cv", "computer", "vision"}),
    frozenset({"ui", "ux", "frontend", "front", "end"}),
    frozenset({"backend", "server", "api"}),
    frozenset({"dsa", "algorithms", "datastructures", "structures"}),
    frozenset({"oop", "object", "oriented"}),
    frozenset({"hr", "human", "resources", "behavioral"}),
    frozenset({"finance", "accounting", "commerce", "excel"}),
    frozenset({"internship", "intern", "placement"}),
)

_TOPIC_FOCUS_CUES = (
    "project",
    "skill",
    "internship",
    "education",
    "degree",
    "course",
    "subject",
    "want",
    "explore",
    "discuss",
    "talk about",
    "let's",
    "lets",
    "focus",
    "about my",
    "dive into",
    "go with",
    "prepare",
    "prep",
    "my ",
)

_FOCUSABLE_CATEGORIES = frozenset(
    {"project", "skill", "internship", "education", "achievement"}
)

_STOP_TOKENS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "want",
        "like",
        "into",
        "about",
        "please",
        "would",
        "could",
        "have",
        "been",
        "your",
        "mine",
        "just",
        "some",
        "more",
        "next",
        "talk",
        "discuss",
        "explore",
        "focus",
        "prep",
        "prepare",
        "preparation",
    }
)


def _tokens(text: str) -> set[str]:
    return {
        t
        for t in re.findall(r"[a-z0-9]+", (text or "").lower())
        if len(t) >= 2 and t not in _STOP_TOKENS
    }


def _expand_tokens(tokens: set[str]) -> set[str]:
    out = set(tokens)
    for group in _TOPIC_SYNONYM_GROUPS:
        if tokens & group:
            out |= set(group)
    return out


def _vault_item_blob(item: dict) -> str:
    details = item.get("details") if isinstance(item.get("details"), dict) else {}
    parts = [str(item.get("title") or "")]
    for v in details.values():
        if v is not None and str(v).strip():
            parts.append(str(v))
    return " ".join(parts)


def _topic_match_score(message_low: str, item: dict) -> int:
    title = str(item.get("title") or "").strip()
    title_low = title.lower()
    if not title_low:
        return 0
    if title_low in message_low or message_low.strip() == title_low:
        return 100
    msg_toks = _expand_tokens(_tokens(message_low))
    item_toks = _expand_tokens(_tokens(_vault_item_blob(item)))
    if not msg_toks or not item_toks:
        return 0
    overlap = msg_toks & item_toks
    score = 0
    for tok in overlap:
        score += 18 if len(tok) >= 4 else 10
    # Prefer matching the category the user named.
    cat = (item.get("category") or "").lower()
    if cat and cat in message_low:
        score += 8
    # Title-token hits are stronger than detail-only hits.
    title_toks = _expand_tokens(_tokens(title_low))
    score += 6 * len(msg_toks & title_toks)
    return score


def _compact_details(details: dict | None) -> dict[str, str]:
    if not isinstance(details, dict):
        return {}
    return {
        str(k)[:40]: str(v)[:160]
        for k, v in list(details.items())[:6]
        if v is not None and str(v).strip()
    }


def find_vault_item_by_title(
    title: str | None, vault_summary: list[dict] | None = None
) -> dict | None:
    want = (title or "").strip().lower()
    if not want:
        return None
    for item in vault_summary or []:
        if not isinstance(item, dict):
            continue
        t = str(item.get("title") or "").strip()
        if t.lower() == want:
            return item
    for item in vault_summary or []:
        if not isinstance(item, dict):
            continue
        t = str(item.get("title") or "").strip().lower()
        if t and (want in t or t in want):
            return item
    return None


def classify_topic_focus(
    message: str,
    vault_summary: list[dict] | None = None,
    *,
    coach_context: dict | None = None,
) -> dict | None:
    """Match any vault project/skill/education item the user just selected — no LLM."""
    text = (message or "").strip()
    if not text or len(text) > 200:
        return None
    # Short acks are continuations / confirmations — never new topic picks.
    if is_ack_only(text) or is_negative_or_skip(text):
        return None
    low = text.lower()
    if any(
        k in low
        for k in ("practise", "practice", "interview me", "mock interview", "quiz me")
    ):
        return None
    # Require an explicit selection cue unless the message is basically a vault title.
    titles = [
        str(i.get("title") or "").strip().lower()
        for i in (vault_summary or [])
        if isinstance(i, dict) and i.get("title")
    ]
    looks_like_title = any(
        t and (t == low or t in low or low in t) for t in titles if len(t) >= 3
    )
    if not looks_like_title and not any(cue in low for cue in _TOPIC_FOCUS_CUES):
        return None
    if not wants_topic_switch(text):
        ctx = coach_context or {}
        locked = bool(ctx.get("focus_locked")) and ctx.get("current_topic")
        # If already locked on a topic and the message does not name a different
        # vault item clearly, keep going via continue path (not a re-select).
        if locked and not looks_like_title:
            # Still allow selecting a different item when match score is strong.
            pass

    candidates = [
        i
        for i in (vault_summary or [])
        if isinstance(i, dict)
        and (i.get("category") or "").lower() in _FOCUSABLE_CATEGORIES
        and (i.get("title") or "").strip()
    ]
    if not candidates:
        return None
    best: dict | None = None
    best_score = 0
    for item in candidates:
        score = _topic_match_score(low, item)
        if score > best_score:
            best_score = score
            best = item
    if not best or best_score < 12:
        return None
    # Don't "re-select" the same locked topic as a brand-new focus event when the
    # user is clearly answering (long message without selection cues) — callers
    # still may use this for explicit re-mentions.
    cat = (best.get("category") or "project").lower()
    return {
        "title": str(best.get("title") or "").strip()[:80],
        "category": cat,
        "kind": cat,
        "details": _compact_details(
            best.get("details") if isinstance(best.get("details"), dict) else {}
        ),
        "score": best_score,
    }


def classify_project_focus(
    message: str, vault_summary: list[dict] | None = None
) -> dict | None:
    """Backward-compatible alias — prefers projects when several categories match."""
    focused = classify_topic_focus(message, vault_summary)
    return focused


def resolve_topic_confirmation(
    message: str,
    vault_summary: list[dict] | None = None,
    coach_context: dict | None = None,
    history: list[dict] | None = None,
) -> dict | None:
    """Map yes/ok to a pending offered topic — not a random vault entry.

    Returns None when the candidate is already locked on that topic so the
    continuation path can ask a real next question instead of re-confirming.
    """
    if not is_affirmative(message):
        return None
    ctx = coach_context or {}
    if (ctx.get("last_question_intent") or "") != "confirm_topic":
        return None
    pending = (ctx.get("pending_followup") or "").strip()
    if not pending:
        # Fall back to a title quoted in the last assistant message.
        last = (ctx.get("last_assistant_question") or "").strip()
        if not last and history:
            for msg in reversed(history):
                if msg.get("role") == "assistant" and msg.get("content"):
                    last = str(msg["content"])
                    break
        m = re.search(r"[“\"]([^”\"]+)[”\"]", last or "")
        if m:
            pending = m.group(1).strip()
    if not pending:
        return None
    current = (ctx.get("current_topic") or "").strip()
    if (
        ctx.get("focus_locked")
        and current
        and current.lower() == pending.lower()
    ):
        # Already exploring this topic — do not restart the opening question.
        return None
    item = find_vault_item_by_title(pending, vault_summary)
    if not item:
        return {
            "title": pending[:80],
            "category": "subject",
            "kind": "subject",
            "details": {},
            "score": 50,
        }
    cat = (item.get("category") or "project").lower()
    return {
        "title": str(item.get("title") or "").strip()[:80],
        "category": cat,
        "kind": cat,
        "details": _compact_details(
            item.get("details") if isinstance(item.get("details"), dict) else {}
        ),
        "score": 90,
    }


def topic_focus_reply(item: dict) -> str:
    """Concrete next question from vault facts — never invent details."""
    title = (item.get("title") or "this topic").strip()
    kind = (item.get("kind") or item.get("category") or "topic").lower()
    details = item.get("details") if isinstance(item.get("details"), dict) else {}
    purpose = str(
        details.get("purpose")
        or details.get("description")
        or details.get("overview")
        or details.get("summary")
        or ""
    ).strip()
    tech = str(
        details.get("technologies")
        or details.get("tools")
        or details.get("stack")
        or details.get("database")
        or details.get("skills")
        or ""
    ).strip()
    if kind == "skill":
        lead = f"Let's dig into your {title} experience."
        return (
            f"{lead} How have you used it in a real task or project, "
            "and what was the outcome?"
        )
    if kind == "education":
        lead = f"I'd like to understand your path through {title}."
        return (
            f"{lead} What did you focus on most, "
            "and which course or topic felt strongest?"
        )
    if kind == "internship":
        lead = f"Your {title} internship sounds worth unpacking."
        return (
            f"{lead} What was your main responsibility, "
            "and what did you deliver?"
        )
    lead = f"I'd love to explore your “{title}” project with you."
    if purpose:
        lead = f"{lead} From what I see, it was about {purpose[:120]}."
    if tech:
        first = tech.split(",")[0].strip() or tech
        return (
            f"{lead} What was the main purpose of the system, "
            f"and how did you use {first}?"
        )
    return (
        f"{lead} What was the main purpose, "
        "and which tools or methods did you use?"
    )


def project_focus_reply(project: dict) -> str:
    """Backward-compatible alias for topic_focus_reply."""
    return topic_focus_reply(project)


def _probe_already_asked(probe: str, asked: list[str], last_q: str) -> bool:
    fp = _question_fingerprint(probe)
    hay = [_question_fingerprint(a) for a in asked if a]
    if last_q:
        hay.append(_question_fingerprint(last_q))
    if not fp:
        return False
    return any(fp[:48] in h or h[:48] in fp for h in hay if h)


def _pick_probe(probes: list[str], *, asked: list[str], last_q: str, offset: int) -> str:
    unused = [p for p in probes if not _probe_already_asked(p, asked, last_q)]
    pool = unused or probes
    return pool[offset % len(pool)]


_PROJECT_PROBES = (
    "What problem were you solving, and who was it for?",
    "Walk me through one design or implementation choice you made and why.",
    "What broke or surprised you while building it, and how did you handle that?",
    "If an interviewer asked for the strongest result, what would you point to?",
)
_SKILL_PROBES = (
    "Walk me through one concrete example where you applied it — situation and result?",
    "What part of it still feels hardest to explain clearly in an interview?",
    "How would you teach the core idea to someone new in two minutes?",
)
_EDU_PROBES = (
    "Which concept from it would you explain confidently in an interview, and why?",
    "What assignment or lab forced you to apply it for real?",
    "How does it connect to the role or field you want next?",
)
_INTERN_PROBES = (
    "What was your main responsibility, and what did you deliver?",
    "What feedback or result are you most proud of?",
    "Which skill from that experience transfers most to your next role?",
)
_GENERIC_PROBES = (
    "What else should an interviewer really understand about it?",
    "Which part would you highlight first in a short interview story?",
    "What would you do differently if you revisited it now?",
)


def continue_topic_reply(
    coach_context: dict | None = None,
    vault_summary: list[dict] | None = None,
) -> str | None:
    """Follow up on the locked/current topic instead of jumping to vault[0]."""
    ctx = coach_context or {}
    topic = (ctx.get("current_topic") or "").strip()
    if not topic:
        return None
    item = find_vault_item_by_title(topic, vault_summary)
    kind = (ctx.get("focus_kind") or (item or {}).get("category") or "topic").lower()
    details = _compact_details((item or {}).get("details") if item else {})
    answers_n = len(ctx.get("answers_received") or [])
    asked = [str(a) for a in (ctx.get("asked_questions") or []) if a]
    last_q = str(ctx.get("last_assistant_question") or "")
    tech = str(
        details.get("technologies")
        or details.get("tools")
        or details.get("stack")
        or ""
    ).strip()
    first_tech = (tech.split(",")[0].strip() if tech else "") or ""

    # Enough depth → natural bridge (no stock "clearer picture" filler).
    if answers_n >= 3:
        nxt_list = suggested_next_topics(vault_summary, topic)
        if nxt_list:
            nxt = nxt_list[0]
            if nxt["kind"] == "skill":
                return (
                    f"You've covered a lot on “{topic}”. "
                    f"Next, I'd like to understand your {nxt['title']} — "
                    "what have you used it for?"
                )
            return (
                f"You've covered a lot on “{topic}”. "
                f"Shall we look at your “{nxt['title']}” {nxt['kind']} next — "
                "what was the main goal?"
            )

    if kind == "project":
        probes = list(_PROJECT_PROBES)
        if first_tech:
            probes.insert(
                1,
                f"How did you decide to use {first_tech}, "
                "and what challenge did that choice create?",
            )
        probe = _pick_probe(probes, asked=asked, last_q=last_q, offset=answers_n)
        return f"Staying with “{topic}” — {probe}"
    if kind == "skill":
        probe = _pick_probe(
            list(_SKILL_PROBES), asked=asked, last_q=last_q, offset=answers_n
        )
        return f"On {topic}: {probe}"
    if kind == "education":
        probe = _pick_probe(
            list(_EDU_PROBES), asked=asked, last_q=last_q, offset=answers_n
        )
        return f"About {topic} — {probe}"
    if kind == "internship":
        probe = _pick_probe(
            list(_INTERN_PROBES), asked=asked, last_q=last_q, offset=answers_n
        )
        return f"About your {topic} experience — {probe}"
    probe = _pick_probe(
        list(_GENERIC_PROBES), asked=asked, last_q=last_q, offset=answers_n
    )
    return f"Continuing with “{topic}” — {probe}"


def suggested_next_topics(
    vault_summary: list[dict] | None,
    current_topic: str | None,
    *,
    limit: int = 4,
) -> list[dict]:
    """Other vault items the coach can bridge to after the current focus."""
    current = (current_topic or "").strip().lower()
    out: list[dict] = []
    for item in vault_summary or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        cat = (item.get("category") or "").lower()
        if not title or cat not in _FOCUSABLE_CATEGORIES:
            continue
        if title.lower() == current:
            continue
        out.append({"title": title[:80], "kind": cat})
        if len(out) >= limit:
            break
    return out


def infer_question_intent(reply: str) -> str:
    """Classify the coach's last ask so short replies resolve correctly.

    Explore/detail beats confirm when the reply already asks What/How/Which —
    bare phrases like "focus on" must not force another confirmation loop.
    """
    text = reply or ""
    low = text.lower()
    has_q = "?" in text
    open_ask = any(
        p in low
        for p in (
            "what was",
            "what did",
            "what have",
            "how did",
            "how have",
            "how would",
            "which ",
            "tell me",
            "walk me",
        )
    )
    if has_q and open_ask:
        return "explore"
    invite = any(
        p in low
        for p in (
            "would you like",
            "want to discuss",
            "shall we look",
            "shall we dig",
            "shall we explore",
            "should we explore",
            "want me to focus",
            "ready to talk about",
        )
    )
    if invite and not open_ask:
        return "confirm_topic"
    if has_q:
        return "detail"
    return "other"


def extract_pending_topic(reply: str) -> str | None:
    m = re.search(r"[“\"]([^”\"]+)[”\"]", reply or "")
    if m:
        return m.group(1).strip()[:120]
    m = re.search(
        r"(?i)(?:your|the)\s+[“\"]?([A-Za-z0-9][^?”\"]{1,80}?)[”\"]?\s+"
        r"(?:project|skill|internship|course|topic)",
        reply or "",
    )
    if m:
        return m.group(1).strip()[:120]
    return None


def _approx_chars(messages: list[dict]) -> int:
    return sum(len(str(m.get("content") or "")) for m in messages)


def compact_vault_for_llm(
    vault_summary: list[dict] | None, *, limit: int = 20
) -> list[dict]:
    """Send titles + short detail snippets — not full resume blobs every turn."""
    out: list[dict] = []
    for item in (vault_summary or [])[:limit]:
        if not isinstance(item, dict):
            continue
        details = item.get("details") if isinstance(item.get("details"), dict) else {}
        slim: dict[str, str] = {}
        for key, value in list(details.items())[:4]:
            text = " ".join(str(value or "").split())
            if text:
                slim[str(key)[:32]] = text[:120]
        out.append(
            {
                "category": str(item.get("category") or "")[:40],
                "title": str(item.get("title") or "")[:80],
                "details": slim,
            }
        )
    return out


def trim_history_for_llm(
    history: list[dict] | None, *, max_chars: int = 3500
) -> list[dict]:
    """Keep recent turns under a char budget; summarise older ones without LLM."""
    msgs = [
        {"role": str(m.get("role") or "user"), "content": str(m.get("content") or "")}
        for m in (history or [])
        if m.get("content")
    ]
    if _approx_chars(msgs) <= max_chars:
        return msgs[-12:]
    kept: list[dict] = []
    used = 0
    for msg in reversed(msgs):
        size = len(msg["content"]) + 8
        if kept and used + size > max_chars:
            break
        kept.append(msg)
        used += size
    kept.reverse()
    older = msgs[: max(0, len(msgs) - len(kept))]
    if older:
        bits = []
        for m in older[-6:]:
            role = "You" if m["role"] == "user" else "Coach"
            bits.append(f"{role}: {m['content'][:80]}")
        summary = {
            "role": "assistant",
            "content": "Earlier in this chat (summary): " + " | ".join(bits),
        }
        return [summary, *kept]
    return kept


async def run_onboarding_turn(
    *,
    message: str,
    history: list[dict],
    vault_summary: list[dict],
    already_finished: bool = False,
    possible_duplicates: list[dict] | None = None,
    profile_gaps: dict | None = None,
    preparation_preferences: dict | None = None,
    available_skills: list[str] | None = None,
    available_projects: list[str] | None = None,
    resume_goal_options: dict | None = None,
    candidate_background: dict | None = None,
    coach_context: dict | None = None,
    conversation_mode: str | None = None,
    phase: str | None = None,
    meta: dict | None = None,
) -> OnboardingTurn:
    """One LLM decision for onboarding (profile intake or goal discovery)."""
    prior = list(history or [])
    if prior and prior[-1].get("role") == "user" and prior[-1].get("content") == message:
        prior = prior[:-1]

    prefs = normalize_preferences(preparation_preferences)
    ctx = coach_context or {}
    bg = candidate_background or infer_candidate_background(vault_summary)
    mode = (conversation_mode or "").strip() or None
    current_phase = phase or derive_phase(
        vault_summary=vault_summary,
        preferences=prefs,
        already_finished=already_finished,
        coach_context=ctx,
    )
    # Starters choose the coach: career goals vs exploratory warm-up.
    if not already_finished:
        if mode == "career_goal":
            current_phase = "goals"
        elif mode in ("ai_interview", "explore_projects", "test_skills"):
            # Keep the profile/exploration coach even when the vault is already ready.
            current_phase = "profile"

    options = resume_goal_options or build_resume_goal_options(vault_summary)
    skills = available_skills if available_skills is not None else options.get(
        "suggested_skills", []
    )
    projects = available_projects if available_projects is not None else options.get(
        "suggested_projects", []
    )

    payload = {
        "known_vault_summary": compact_vault_for_llm(vault_summary),
        "candidate_background": bg,
        "coach_context": {
            "confirmed_facts": (ctx.get("confirmed_facts") or [])[-12:],
            "asked_questions": (ctx.get("asked_questions") or [])[-12:],
            "skipped_categories": ctx.get("skipped_categories") or [],
            "not_applicable_categories": ctx.get("not_applicable_categories") or [],
            "current_topic": ctx.get("current_topic"),
            "focus_kind": ctx.get("focus_kind"),
            "focus_locked": bool(ctx.get("focus_locked")),
            "last_assistant_question": (ctx.get("last_assistant_question") or "")[:320],
            "last_question_intent": ctx.get("last_question_intent"),
            "pending_followup": ctx.get("pending_followup"),
            "answers_received": (ctx.get("answers_received") or [])[-8:],
            "proceed_to_goals": bool(ctx.get("proceed_to_goals")),
        },
        "suggested_next_topics": suggested_next_topics(
            vault_summary, ctx.get("current_topic")
        ),
        "possible_duplicates": (possible_duplicates or [])[:6],
        "profile_gaps": profile_gaps
        or compute_profile_gaps(vault_summary, coach_context=ctx),
        "current_preparation_preferences": prefs,
        "next_goal_followup": next_goal_followup(prefs),
        "available_skills": (skills or [])[:16],
        "available_projects": (projects or [])[:12],
        "suggested_roles": (options.get("suggested_roles") or [])[:8],
        "suggested_technical_areas": (options.get("suggested_technical_areas") or [])[:8],
        "suggested_prep_topics": (
            options.get("suggested_prep_topics") or bg.get("suggested_prep_topics") or []
        )[:8],
        "project_options": (options.get("project_options") or [])[:8],
        "project_aspect_options": (options.get("project_aspect_options") or [])[:8],
        "resume_highlights": options.get("resume_highlights") or {},
        "goal_interest_labels": GOAL_INTEREST_LABELS,
        "conversation_mode": mode,
        "conversation_so_far": trim_history_for_llm(prior),
        "new_user_message": message,
        "already_finished": already_finished,
        "phase": current_phase,
        "reply_style": (
            "Mentor voice: react + reflect one detail from new_user_message, "
            "then exactly one new question. Never claim vault saves. Never re-ask "
            "or re-confirm something already in answers_received / asked_questions / "
            "current_topic. Short yes/ok means continue — not a new questionnaire."
        ),
    }

    if already_finished:
        system = FINISHED_SYSTEM_PROMPT
    elif current_phase in ("goals", "ready"):
        system = GOALS_SYSTEM_PROMPT
    else:
        system = SYSTEM_PROMPT

    # One structured call: reply + extraction together. Fail over fast on 429
    # (max_attempts=1). Shared HTTP client avoids per-turn connection setup.
    llm_started = time.monotonic()
    turn = await structured_completion(
        system=system,
        user_payload=payload,
        schema=OnboardingTurn,
        meta=meta,
        max_attempts=1,
        max_tokens=550,
        timeout_s=18.0,
        repair_attempts=1,
    )
    log.info(
        "onboarding_llm_timing",
        stage="structured_turn",
        elapsed_ms=int((time.monotonic() - llm_started) * 1000),
    )

    # Deterministic phase / completion after the model replies.
    merged_prefs = prefs
    if turn.preparation_update is not None:
        merged_prefs = merge_preferences(
            prefs, turn.preparation_update.model_dump(exclude_none=True)
        )

    # Synthetic vault after this turn's extractions items (for readiness only).
    enriched = list(vault_summary or [])
    for item in turn.extracted_items:
        enriched.append({"category": item.category, "title": item.title, "details": item.details})
    vault_ready = vault_is_ready(enriched, ctx)

    if already_finished or preferences_ready(merged_prefs):
        turn.phase = "ready"
        turn.onboarding_complete = True
        turn.show_goal_menu = False
    elif mode in ("ai_interview", "explore_projects", "test_skills"):
        # Exploration starters stay in conversational profile mode; goals UI waits.
        turn.phase = "profile"
        turn.onboarding_complete = False
        turn.show_goal_menu = False
    elif vault_ready or mode == "career_goal":
        turn.phase = "goals"
        turn.onboarding_complete = False
        if not merged_prefs["interests"]:
            turn.show_goal_menu = True
    else:
        turn.phase = "profile"
        turn.onboarding_complete = False
        turn.show_goal_menu = False

    turn.reply = ensure_nonempty_reply(
        turn.reply, vault_summary=vault_summary, coach_context=ctx
    )
    return turn


def build_onboarding_graph(turn_runner=run_onboarding_turn):
    """Compile the intake graph. turn_runner is injectable for tests."""

    async def intake(state: OnboardingState) -> dict:
        turn = await turn_runner(
            message=state["message"],
            history=state.get("history", []),
            vault_summary=state.get("vault_summary", []),
            already_finished=bool(state.get("already_finished")),
            possible_duplicates=state.get("possible_duplicates"),
            profile_gaps=state.get("profile_gaps"),
            preparation_preferences=state.get("preparation_preferences") or EMPTY_PREFERENCES,
            available_skills=state.get("available_skills"),
            available_projects=state.get("available_projects"),
            resume_goal_options=state.get("resume_goal_options"),
            candidate_background=state.get("candidate_background"),
            coach_context=state.get("coach_context"),
            conversation_mode=state.get("conversation_mode"),
            phase=state.get("phase"),
            meta=state.get("meta"),
        )
        payload = turn.model_dump()
        payload["_question_fingerprint"] = _question_fingerprint(turn.reply)
        return {"turn": payload}

    graph = StateGraph(OnboardingState)
    graph.add_node("intake", intake)
    graph.add_edge(START, "intake")
    graph.add_edge("intake", END)
    return graph.compile()
