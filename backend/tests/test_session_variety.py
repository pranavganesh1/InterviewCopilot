"""Per-session question pools, serve-time cleaning, and the open-session lookup."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.agents.interviewer import TurnDecision, apply_local_policy, decision_violation
from app.agents.question_dedupe import concept_fingerprint
from app.agents.question_plan import deterministic_question_plan, opening_areas_to_avoid
from app.agents.question_quality import prepare_served_question
from app.agents.session_pool import least_recent_text, needs_pool_topup, pick_pool_question
from app.core.security import create_access_token
from app.db.sqlalchemy import SessionFactory
from app.main import create_app
from app.models.interview import InterviewSession, SessionTurn
from app.models.track import InterviewBrief, Track
from app.models.user import User

AREAS = ("Kestrels", "Ledgers", "Glaciers")


_WORDS = (
    "kestrel",
    "ledger",
    "glacier",
    "sonnet",
    "harbour",
    "cobalt",
    "fiddle",
    "orchid",
    "quartz",
    "velvet",
    "cinder",
    "marigold",
    "anvil",
    "badger",
    "canyon",
    "dolphin",
    "ember",
    "falcon",
    "granite",
    "harp",
    "ivory",
    "jasper",
    "kelp",
    "linen",
    "marble",
    "nectar",
    "onyx",
    "pebble",
    "quill",
    "raven",
)


def _question(n: int) -> str:
    word = _WORDS[n]
    return f"{word} {word} {word}?"


def _entry(n: int, difficulty: str, fmt: str, area: str) -> dict:
    return {
        "area": area,
        "difficulty": difficulty,
        "type": fmt,
        "question": _question(n),
    }


def _slot(i: int) -> dict:
    if i < 5:
        difficulty = "foundational"
    elif i < 10:
        difficulty = "intermediate"
    else:
        difficulty = "advanced"
    return {
        "topic": AREAS[i % 3],
        "difficulty": difficulty,
        "format": "mcq" if i % 5 == 4 else "conceptual",
        "objective": f"slot {i}",
    }


def _pool() -> list[dict]:
    rows = []
    n = 0
    for copy in range(2):
        for i in range(15):
            slot = _slot(i)
            rows.append(_entry(n, slot["difficulty"], slot["format"], AREAS[(i + copy) % 3]))
            n += 1
    return rows


def _sequence(seed: str, history: list[str]) -> list[str]:
    asked: list[str] = []
    covered: list[str] = []
    areas: list[str] = []
    for i in range(15):
        slot = _slot(i)
        picked = pick_pool_question(
            _pool(),
            seed=seed,
            slot=slot,
            asked=asked,
            history=history,
            covered_areas=covered,
            mode="strict",
        )
        assert picked is not None
        assert picked["difficulty"] == slot["difficulty"]
        assert picked["type"] == slot["format"]
        asked.append(picked["question"])
        areas.append(picked["area"])
        if picked["area"] not in covered:
            covered.append(picked["area"])
    if not history:
        assert set(areas[:3]) == set(AREAS)
    return asked


def _decision(text: str) -> TurnDecision:
    return TurnDecision(
        evaluation={"coverage": "none", "strengths": [], "gaps": []},
        decision="next_area",
        next_question=text,
        question_area="Kestrels",
    )


def test_two_sessions_differ_and_a_session_is_stable():
    first = _sequence("session-a", [])
    again = _sequence("session-a", [])
    second = _sequence("session-b", first)
    assert first == again
    assert set(first).isdisjoint(second)
    assert len(set(first)) == 15
    assert _sequence("session-a", [])[0] == first[0]


def test_fallback_plan_changes_with_the_seed_and_a_single_area_still_works():
    brief = {
        "summary": "Field notes",
        "question_areas": [{"topic": name, "guidance": "notes"} for name in AREAS],
        "competencies": [],
        "avoid_areas": ["Kestrels"],
    }
    seeded = deterministic_question_plan(brief, 6, seed="alpha")
    other = deterministic_question_plan(brief, 6, seed="bravo")
    assert seeded[0]["topic"] != "Kestrels"
    assert other[0]["topic"] != "Kestrels"
    assert [slot["topic"] for slot in seeded] != [slot["topic"] for slot in other]
    assert [slot["difficulty"] for slot in seeded] == [slot["difficulty"] for slot in other]
    single = deterministic_question_plan(
        {"question_areas": [{"topic": "Kestrels"}], "avoid_areas": ["Kestrels"]},
        3,
        seed="alpha",
    )
    assert [slot["topic"] for slot in single] == ["Kestrels"] * 3
    assert opening_areas_to_avoid(["Kestrels"], ["Kestrels"]) == []


def test_plan_seed_rotates_areas_inside_the_same_arc():
    brief = {
        "summary": "Field notes",
        "question_areas": [{"topic": name, "guidance": "notes"} for name in AREAS],
        "competencies": [],
    }
    plain = deterministic_question_plan(brief, 15)
    seeded = deterministic_question_plan(brief, 15, seed="alpha")
    other = deterministic_question_plan(brief, 15, seed="bravo")
    assert plain[0]["topic"] == "Kestrels"
    assert [slot["difficulty"] for slot in seeded] == [slot["difficulty"] for slot in plain]
    assert [slot["topic"] for slot in seeded] != [slot["topic"] for slot in other]


def test_exhausted_pool_reuses_the_oldest_question_only():
    bank = _pool()[:3]
    history = [bank[1]["question"], bank[0]["question"], bank[2]["question"]]
    unseen = pick_pool_question(
        bank,
        seed="s",
        slot=_slot(0),
        asked=[],
        history=history[:2],
        mode="strict",
    )
    assert unseen is not None
    assert unseen["question"] == bank[2]["question"]
    oldest = pick_pool_question(
        bank,
        seed="s",
        slot=_slot(0),
        asked=[],
        history=history,
        mode="strict",
    )
    assert oldest is not None
    assert oldest["question"] == history[0]
    live = apply_local_policy(
        _decision("What is zephyr77 known for?"),
        {
            "mode": "strict",
            "brief": {"pool": {"target": 45}},
            "question_bank": [],
            "asked_questions": [],
            "questions_remaining": 15,
            "meta": {"session_id": "s"},
        },
    )
    assert live.next_question == "What is zephyr77 known for?"
    repeat = _decision(history[0])
    assert decision_violation(
        repeat,
        {
            "asked_questions": [],
            "prior_track_questions": history,
            "questions_remaining": 15,
        },
    )


def test_fresh_generation_wins_until_only_an_old_question_remains():
    bank = _pool()[:3]
    history = [row["question"] for row in bank]
    payload = {
        "mode": "strict",
        "brief": {"pool": {"target": 45}},
        "question_bank": bank,
        "asked_questions": [],
        "prior_track_questions": history,
        "questions_remaining": 15,
        "meta": {"session_id": "s"},
        "question_plan_slot": _slot(0),
    }
    live = apply_local_policy(_decision("What is zephyr77 known for?"), payload)
    assert live.next_question == "What is zephyr77 known for?"
    assert least_recent_text(history, []) == history[0]


def test_fingerprint_skips_a_bank_question_already_used_on_the_track():
    seen = "Why does contiguous array memory make index access a constant time operation?"
    other = _entry(5, "foundational", "conceptual", "Ledgers")
    fingerprint = tuple(sorted(concept_fingerprint(seen)))
    assert len(fingerprint) >= 4
    picked = pick_pool_question(
        [
            {
                "area": "Kestrels",
                "difficulty": "foundational",
                "type": "conceptual",
                "question": seen,
            },
            other,
        ],
        seed="s",
        slot=_slot(0),
        asked=[],
        history=[],
        fingerprints=[fingerprint],
        mode="strict",
    )
    assert picked is not None
    assert picked["question"] == other["question"]


def test_strict_strips_openers_from_bank_and_generated_questions():
    for text in (
        "Let's start with the basics. Why does a hash table use chaining?",
        "Good start. Why does a hash table use chaining?",
        "I see. Let's explore a bit further. Why does a hash table use chaining?",
    ):
        cleaned = prepare_served_question(text, mode="strict")
        assert cleaned == "Why does a hash table use chaining?"


def test_strict_strips_bank_openers_and_repairs_a_stacked_question():
    opener = (
        "I see. Let's explore a bit further. Why does a hash table use chaining?"
    )
    stacked = "How do you slice a list and what happens if the index is too large?"
    payload = {
        "mode": "strict",
        "question_bank": [
            {
                "area": "Hashmaps",
                "question": opener,
                "type": "conceptual",
                "difficulty": "foundational",
            },
            {
                "area": "Lists",
                "question": stacked,
                "type": "conceptual",
                "difficulty": "foundational",
            },
        ],
        "asked_questions": [],
        "questions_remaining": 15,
        "brief": {},
    }
    first = apply_local_policy(_decision("Improvised question about graphs?"), payload)
    assert first.next_question == "Why does a hash table use chaining?"
    payload["asked_questions"] = [first.next_question]
    payload["question_bank"] = payload["question_bank"][1:]
    second = apply_local_policy(_decision("Improvised question about graphs?"), payload)
    assert "and what happens" not in second.next_question.lower()
    assert second.next_question.count("?") == 1


def test_guided_keeps_encouragement_and_a_long_right_question_stays():
    encouraged = "Great. Why does a hash table use chaining?"
    guided = apply_local_policy(
        _decision(encouraged),
        {"mode": "guided", "question_bank": [], "questions_remaining": 15, "brief": {}},
    )
    assert guided.next_question == encouraged
    kept = prepare_served_question(
        "Right shift in C is an arithmetic operation on the bits?", mode="strict"
    )
    assert kept is not None
    assert kept.startswith("Right shift")


def test_old_brief_without_pool_keeps_bank_order():
    bank = [
        {"area": "Kestrels", "question": _question(1), "type": "conceptual"},
        {"area": "Ledgers", "question": _question(2), "type": "conceptual"},
    ]
    payload = {
        "mode": "strict",
        "brief": {},
        "question_bank": bank,
        "asked_questions": [],
        "questions_remaining": 15,
        "meta": {"session_id": "one"},
    }
    first = apply_local_policy(_decision("Sketch one unusual habitat?"), payload)
    assert first.next_question == _question(1)
    payload["meta"] = {"session_id": "two"}
    payload["asked_questions"] = [_question(1)]
    second = apply_local_policy(_decision("Sketch one unusual habitat?"), payload)
    assert second.next_question == _question(2)


def test_topup_is_needed_only_when_the_unseen_pool_is_low():
    assert needs_pool_topup(2, 15)
    assert not needs_pool_topup(30, 15)


@pytest.mark.asyncio
async def test_extend_pool_failure_returns_nothing(monkeypatch):
    from app.agents import track_creator

    async def boom(**_kwargs):
        raise RuntimeError("llm down")

    monkeypatch.setattr(track_creator, "run_bank_builder_turn", boom)
    monkeypatch.setattr(track_creator, "BANK_CALL_SPACING_S", 0)
    rows = await track_creator.extend_question_pool(
        brief={"question_bank": [], "pool": {"target": 45}},
        objective={"subject": "Kestrels"},
    )
    assert rows == []


@pytest.mark.asyncio
async def test_history_covers_every_status_and_a_failed_topup_still_starts(
    monkeypatch, clean_users_table
):
    from app.services import interview_service as svc

    async def fake_turn(**_kwargs):
        return TurnDecision(
            evaluation={"coverage": "none", "strengths": [], "gaps": []},
            decision="next_area",
            next_question="What is zephyr99 known for?",
            question_area="Kestrels",
        )

    calls = {"n": 0}

    async def boom(**_kwargs):
        calls["n"] += 1
        raise RuntimeError("topup down")

    monkeypatch.setattr(svc, "run_interviewer_turn", fake_turn)
    monkeypatch.setattr(svc, "extend_question_pool", boom)

    async with SessionFactory() as db:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=f"pool-{uuid.uuid4()}@example.com")
        db.add(user)
        await db.commit()
        await db.refresh(user)
        track = Track(user_id=user.id, track_type="topic", subject="Kestrels")
        db.add(track)
        await db.commit()
        await db.refresh(track)
        db.add(
            InterviewBrief(
                track_id=track.id,
                version=1,
                content={
                    "summary": "Field notes",
                    "question_areas": [{"topic": "Kestrels", "guidance": "flight"}],
                    "question_bank": [_entry(1, "foundational", "conceptual", "Kestrels")],
                    "pool": {"target": 45},
                },
            )
        )
        base = datetime(2026, 1, 1, tzinfo=UTC)
        for offset, status, text in (
            (0, "completed", "What is zephyr01 known for?"),
            (1, "cancelled", "What is zephyr02 known for?"),
            (2, "abandoned", "What is zephyr03 known for?"),
        ):
            old = InterviewSession(
                track_id=track.id,
                user_id=user.id,
                mode="strict",
                status=status,
            )
            db.add(old)
            await db.commit()
            await db.refresh(old)
            db.add(
                SessionTurn(
                    session_id=old.id,
                    turn_index=1,
                    question_area="Kestrels",
                    question=text,
                    asked_at=base + timedelta(minutes=offset),
                )
            )
        await db.commit()
        history = await svc._track_history(db, user.id, track.id)
        user_id = user.id
        track_id = track.id
    assert [row["question"] for row in history] == [
        "What is zephyr01 known for?",
        "What is zephyr02 known for?",
        "What is zephyr03 known for?",
    ]

    token = create_access_token(str(user_id))
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        opened = await client.get(
            f"/api/v1/tracks/{track_id}/open-session", cookies={"ic_access": token}
        )
        assert opened.status_code == 200
        assert opened.json()["session"] is None
        started = await client.post(
            f"/api/v1/tracks/{track_id}/sessions", cookies={"ic_access": token}
        )
        assert started.status_code == 201
        sid = started.json()["session"]["id"]
        for _ in range(20):
            if calls["n"]:
                break
            await asyncio.sleep(0.05)
        again = await client.get(
            f"/api/v1/tracks/{track_id}/open-session", cookies={"ic_access": token}
        )
    assert calls["n"] == 1
    body = again.json()["session"]
    assert body["id"] == sid
    assert body["question_index"] == 1
    assert body["mode"] == "strict"


@pytest.mark.asyncio
async def test_three_sessions_open_on_different_areas_and_a_refresh_is_stable(
    monkeypatch, clean_users_table
):
    from app.agents import interviewer
    from app.services import interview_service as svc

    async def fake_structured(*_args, **_kwargs):
        return TurnDecision(
            evaluation={"coverage": "none", "strengths": [], "gaps": []},
            decision="next_area",
            next_question="What is zephyr77 known for?",
            question_area="Array Basics and Memory Layout",
        )

    async def no_topup(**_kwargs):
        return []

    monkeypatch.setattr(interviewer, "structured_completion", fake_structured)
    monkeypatch.setattr(svc, "extend_question_pool", no_topup)

    bank = []
    for area_index, area in enumerate(AREAS):
        for copy in range(2):
            bank.append(
                _entry(area_index * 2 + copy, "foundational", "conceptual", area)
            )

    async with SessionFactory() as db:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=f"variety-{uuid.uuid4()}@example.com")
        db.add(user)
        await db.commit()
        await db.refresh(user)
        track = Track(user_id=user.id, track_type="topic", subject="Field notes")
        db.add(track)
        await db.commit()
        await db.refresh(track)
        db.add(
            InterviewBrief(
                track_id=track.id,
                version=1,
                content={
                    "summary": "Field notes",
                    "question_areas": [{"topic": area, "guidance": "notes"} for area in AREAS],
                    "question_bank": bank,
                    "pool": {"target": 45},
                },
            )
        )
        await db.commit()
        user_id = user.id
        track_id = track.id

    token = create_access_token(str(user_id))
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    openings: list[tuple[str, str]] = []
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(3):
            started = await client.post(
                f"/api/v1/tracks/{track_id}/sessions", cookies={"ic_access": token}
            )
            assert started.status_code == 201
            turn = started.json()["turn"]
            sid = started.json()["session"]["id"]
            refreshed = await client.get(
                f"/api/v1/sessions/{sid}", cookies={"ic_access": token}
            )
            assert refreshed.status_code == 200
            assert refreshed.json()["turns"][0]["question"] == turn["question"]
            assert refreshed.json()["turns"][0]["question_area"] == turn["question_area"]
            openings.append((turn["question_area"], turn["question"]))
    assert len({area for area, _ in openings}) == 3
    assert len({question for _, question in openings}) == 3
    assert "What is zephyr77 known for?" not in {question for _, question in openings}
