"""One-shot live smoke of goals → track → session → feedback against host API."""

from __future__ import annotations

import asyncio
import sys
import time
import uuid

import httpx
from sqlalchemy import delete, select

from app.core.security import create_access_token
from app.db.sqlalchemy import SessionFactory
from app.models.feedback import FeedbackReport, ProgressionState
from app.models.interview import InterviewSession, SessionTurn
from app.models.track import InterviewBrief, Track
from app.models.user import User
from app.models.vault import VaultItem

BASE = "http://127.0.0.1:8000"
SMOKE_EMAIL = "pipeline-smoke@interviewcopilot.local"


async def seed_user() -> tuple[uuid.UUID, str]:
    async with SessionFactory() as session:
        existing = (
            await session.execute(select(User).where(User.email == SMOKE_EMAIL))
        ).scalar_one_or_none()
        if existing:
            uid = existing.id
            track_ids = select(Track.id).where(Track.user_id == uid)
            await session.execute(delete(FeedbackReport).where(FeedbackReport.user_id == uid))
            await session.execute(
                delete(ProgressionState).where(ProgressionState.track_id.in_(track_ids))
            )
            await session.execute(
                delete(SessionTurn).where(
                    SessionTurn.session_id.in_(
                        select(InterviewSession.id).where(InterviewSession.user_id == uid)
                    )
                )
            )
            await session.execute(
                delete(InterviewSession).where(InterviewSession.user_id == uid)
            )
            await session.execute(
                delete(InterviewBrief).where(InterviewBrief.track_id.in_(track_ids))
            )
            await session.execute(delete(Track).where(Track.user_id == uid))
            await session.execute(delete(VaultItem).where(VaultItem.user_id == uid))
            await session.execute(delete(User).where(User.id == uid))
            await session.commit()

        user = User(
            google_sub=f"smoke-{uuid.uuid4().hex[:16]}",
            email=SMOKE_EMAIL,
            name="Pipeline Smoke",
        )
        session.add(user)
        await session.flush()
        for category, title in (
            ("project", "Line-following robot"),
            ("skill", "Python"),
            ("education", "B.Tech CSE"),
        ):
            session.add(
                VaultItem(
                    user_id=user.id,
                    category=category,
                    title=title,
                    details={"summary": title},
                    source="manual",
                )
            )
        await session.commit()
        return user.id, create_access_token(str(user.id))


async def cleanup(user_id: uuid.UUID) -> None:
    async with SessionFactory() as session:
        track_ids = select(Track.id).where(Track.user_id == user_id)
        await session.execute(delete(FeedbackReport).where(FeedbackReport.user_id == user_id))
        await session.execute(
            delete(ProgressionState).where(ProgressionState.track_id.in_(track_ids))
        )
        await session.execute(
            delete(SessionTurn).where(
                SessionTurn.session_id.in_(
                    select(InterviewSession.id).where(InterviewSession.user_id == user_id)
                )
            )
        )
        await session.execute(
            delete(InterviewSession).where(InterviewSession.user_id == user_id)
        )
        await session.execute(
            delete(InterviewBrief).where(InterviewBrief.track_id.in_(track_ids))
        )
        await session.execute(delete(Track).where(Track.user_id == user_id))
        await session.execute(delete(VaultItem).where(VaultItem.user_id == user_id))
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()


def ok(label: str, resp: httpx.Response) -> dict | list | str:
    print(f"[{resp.status_code}] {label}")
    if resp.status_code >= 400:
        print(resp.text[:500])
        raise SystemExit(f"FAIL: {label}")
    if not resp.content:
        return {}
    try:
        return resp.json()
    except Exception:
        return resp.text


async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    label: str,
    retries: int = 8,
    **kwargs,
) -> dict | list | str:
    last: httpx.Response | None = None
    for attempt in range(retries):
        last = await client.request(method, url, **kwargs)
        if last.status_code != 503:
            return ok(label, last)
        wait = min(20 * (attempt + 1), 90)
        print(f"[503] {label} — retry in {wait}s ({attempt + 1}/{retries})")
        await asyncio.sleep(wait)
    assert last is not None
    return ok(label, last)


async def main() -> None:
    user_id, token = await seed_user()
    cookies = {"ic_access": token}
    results: dict[str, str] = {}
    try:
        async with httpx.AsyncClient(base_url=BASE, cookies=cookies, timeout=180.0) as client:
            me = ok("auth/me", await client.get("/api/v1/auth/me"))
            assert me.get("email") == SMOKE_EMAIL
            results["auth"] = "ok"

            state = ok("onboarding/state", await client.get("/api/v1/onboarding/state"))
            results["onboarding_state"] = f"phase={state.get('phase')}"

            goals = ok(
                "onboarding/goals",
                await client.post(
                    "/api/v1/onboarding/goals",
                    json={"interests": ["technical"]},
                ),
            )
            results["goals"] = f"reply_len={len(goals.get('reply') or '')}"

            track = ok(
                "tracks create",
                await client.post(
                    "/api/v1/tracks",
                    json={"track_type": "topic", "subject": "Data Structures & Algorithms"},
                ),
            )
            track_payload = track.get("track") if isinstance(track.get("track"), dict) else track
            track_id = track_payload["id"]
            results["track_create"] = f"status={track_payload.get('brief_status')}"

            brief_ready = False
            for i in range(60):
                detail = ok(
                    f"tracks get #{i}",
                    await client.get(f"/api/v1/tracks/{track_id}"),
                )
                detail_track = (
                    detail.get("track") if isinstance(detail.get("track"), dict) else detail
                )
                status = detail_track.get("brief_status")
                if status == "ready":
                    brief_ready = True
                    break
                if status == "failed":
                    raise SystemExit(f"FAIL: brief authoring failed: {detail}")
                await asyncio.sleep(3)
            if not brief_ready:
                raise SystemExit("FAIL: brief not ready within timeout")
            results["brief"] = "ready"

            session = await request_with_retry(
                client,
                "POST",
                f"/api/v1/tracks/{track_id}/sessions",
                label="start session",
                json={"mode": "strict", "duration_minutes": 30},
            )
            assert isinstance(session, dict)
            session_id = session["session"]["id"] if "session" in session else session["id"]
            results["session_start"] = "ok"

            turn = await request_with_retry(
                client,
                "POST",
                f"/api/v1/sessions/{session_id}/turns",
                label="submit turn",
                json={
                    "answer": (
                        "An array stores contiguous elements with O(1) index access. "
                        "A linked list uses nodes and pointers for O(1) insert at head."
                    )
                },
            )
            assert isinstance(turn, dict)
            results["turn"] = f"completed={turn.get('completed')}"

            if not turn.get("completed"):
                done = ok(
                    "complete session",
                    await client.post(f"/api/v1/sessions/{session_id}/complete"),
                )
                results["complete"] = str(done.get("status") or done)
            else:
                results["complete"] = "already_completed"

            report_ok = False
            for _ in range(60):
                report = await client.get(f"/api/v1/sessions/{session_id}/report")
                if report.status_code == 200:
                    body = report.json()
                    print(f"[200] feedback report keys={list(body)[:8]}")
                    report_ok = True
                    break
                if report.status_code not in (404, 202):
                    print(report.text[:500])
                    raise SystemExit(f"FAIL: report status {report.status_code}")
                await asyncio.sleep(3)
            if not report_ok:
                raise SystemExit("FAIL: feedback report not ready within timeout")
            results["feedback"] = "ok"

        print("\nSMOKE PASS")
        for k, v in results.items():
            print(f"  {k}: {v}")
    finally:
        await cleanup(user_id)
        print("cleaned smoke user")


if __name__ == "__main__":
    started = time.monotonic()
    try:
        asyncio.run(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise
    finally:
        print(f"elapsed_s={int(time.monotonic() - started)}")
