"""Close stale empty unfinished interviews (never deletes rows).

Dry-run by default. With --apply, aborts eligible sessions through the same
status=aborted path used elsewhere (no feedback job, no deletes).

Usage:
  cd backend
  uv run python scripts/close_empty_sessions.py
  uv run python scripts/close_empty_sessions.py --apply
  uv run python scripts/close_empty_sessions.py --minutes 10 --apply
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.sqlalchemy import SessionFactory
from app.services import interview_service


async def _run(*, apply: bool, minutes: int) -> None:
    async with SessionFactory() as db:
        eligible = await interview_service.find_empty_sessions_for_cleanup(
            db, older_than_minutes=minutes
        )
        print(f"eligible_count: {len(eligible)}")
        print(f"older_than_minutes: {minutes}")
        print(f"apply: {apply}")
        for session in eligible:
            print(
                f"  session_id={session.id} track_id={session.track_id} "
                f"created_at={session.created_at} mode={session.mode}"
            )
        if not apply:
            print("dry-run: no changes (pass --apply to abort eligible sessions)")
            return
        closed = await interview_service.abort_sessions_by_ids(
            db, [session.id for session in eligible]
        )
        print(f"closed_count: {closed}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Abort open interviews with 0 answered turns (no deletes)."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually abort eligible sessions (default is dry-run).",
    )
    parser.add_argument(
        "--minutes",
        type=int,
        default=10,
        help="Only sessions older than this many minutes (default 10).",
    )
    args = parser.parse_args()
    asyncio.run(_run(apply=bool(args.apply), minutes=max(1, int(args.minutes))))


if __name__ == "__main__":
    main()
