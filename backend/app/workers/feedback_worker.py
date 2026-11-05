"""Feedback worker: consumes feedback.jobs from NATS JetStream.

Run: cd backend && uv run python -m app.workers.feedback_worker
Catch-up mode (no NATS): uv run python -m app.workers.feedback_worker --catch-up
"""

import asyncio
import json
import sys
from contextlib import suppress
from datetime import UTC, datetime, timedelta

import nats
from nats.js.api import ConsumerConfig, DeliverPolicy, StreamConfig
from sqlalchemy import select, text

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.sqlalchemy import SessionFactory
from app.models.feedback import FeedbackReport
from app.models.interview import InterviewSession
from app.services import events
from app.services.feedback_service import process_session_feedback

log = get_logger(__name__)

_SESSION_NOT_FOUND_MAX_DELIVERIES = 3
_SESSION_NOT_FOUND_NAK_DELAY_S = 5
# Fixed key so concurrent worker processes serialize catch-up passes.
_CATCH_UP_ADVISORY_LOCK_KEY = 0x1C_FEED_BAC1
_CATCH_UP_MAX_FAILURES = 3
# In-memory fail counts for this process only (session_id -> count).
_catch_up_failures: dict[str, int] = {}


class PermanentFeedbackError(Exception):
    """Job cannot succeed on retry (e.g. session permanently missing)."""


class RetryableFeedbackError(Exception):
    """Transient failure — nak and redeliver shortly."""

    def __init__(self, message: str, *, delay: int = _SESSION_NOT_FOUND_NAK_DELAY_S):
        super().__init__(message)
        self.delay = delay


def _worker_database_name() -> str:
    return get_settings().database_url.rsplit("/", 1)[-1]


def reset_catch_up_failures() -> None:
    """Test helper: clear the in-process failure memory."""
    _catch_up_failures.clear()


async def process_event(data: bytes, *, num_delivered: int = 1) -> dict:
    event = json.loads(data)
    session_id = event.get("session_id")
    job_id = event.get("job_id")
    publisher_db = event.get("database")
    if not session_id:
        raise PermanentFeedbackError("feedback job missing session_id")

    worker_db = _worker_database_name()
    log.info(
        "feedback_job_received",
        session_id=str(session_id),
        job_id=job_id,
        publisher_database=publisher_db,
        worker_database=worker_db,
    )

    # Jobs published by another environment (e.g. pytest → interviewcopilot_test)
    # must not be processed against this worker's database.
    if publisher_db and publisher_db != worker_db:
        log.warning(
            "feedback_job_foreign_database",
            session_id=str(session_id),
            job_id=job_id,
            publisher_database=publisher_db,
            worker_database=worker_db,
        )
        return {"skipped": True, "reason": "foreign_database"}

    async with SessionFactory() as db:
        # Confirm which DB this connection actually hit.
        try:
            live_db = (await db.execute(text("SELECT current_database()"))).scalar()
        except Exception:
            live_db = worker_db
        log.info(
            "feedback_job_db_check",
            session_id=str(session_id),
            job_id=job_id,
            current_database=live_db,
        )
        try:
            result = await process_session_feedback(db, session_id)
        except LookupError as exc:
            if str(exc) == "session_not_found":
                detail = (
                    f"session_not_found session_id={session_id} job_id={job_id} "
                    f"worker_database={live_db} publisher_database={publisher_db}"
                )
                if num_delivered <= _SESSION_NOT_FOUND_MAX_DELIVERIES:
                    raise RetryableFeedbackError(detail) from exc
                raise PermanentFeedbackError(detail) from exc
            raise
        except (ValueError, TypeError) as exc:
            raise PermanentFeedbackError(
                f"invalid_session_id session_id={session_id} job_id={job_id} error={exc}"
            ) from exc
        log.info(
            "feedback_processed",
            session_id=str(session_id),
            job_id=job_id,
            result=str(result)[:120],
        )
        return result if isinstance(result, dict) else {"ok": True}


async def catch_up_once(min_age_seconds: int = 0, limit: int = 20) -> int:
    """Process completed sessions that still lack a FeedbackReport.

    Only sessions whose completed_at is at least min_age_seconds old are
    considered. At most `limit` sessions are attempted per pass. Returns the
    number successfully processed. Uses a Postgres advisory lock so concurrent
    worker processes do not run catch-up at the same time.
    """
    processed = 0
    skipped = 0
    pending = 0

    async with SessionFactory() as db:
        locked = (
            await db.execute(
                text("SELECT pg_try_advisory_lock(:k)"),
                {"k": _CATCH_UP_ADVISORY_LOCK_KEY},
            )
        ).scalar()
        if not locked:
            log.info("catch_up_pass", pending=0, processed=0, skipped=0)
            return 0

        try:
            live_db = (await db.execute(text("SELECT current_database()"))).scalar()
            cutoff = datetime.now(UTC) - timedelta(seconds=max(0, min_age_seconds))
            sessions = (
                (
                    await db.execute(
                        select(InterviewSession)
                        .where(InterviewSession.status == "completed")
                        .where(InterviewSession.completed_at.is_not(None))
                        .where(InterviewSession.completed_at <= cutoff)
                        .outerjoin(
                            FeedbackReport, FeedbackReport.session_id == InterviewSession.id
                        )
                        .where(FeedbackReport.id.is_(None))
                        .order_by(InterviewSession.completed_at.asc())
                    )
                )
                .scalars()
                .all()
            )
            pending = len(sessions)
            log.info("catch_up_scanning", pending=pending, database=live_db)

            attempted = 0
            for s in sessions:
                if attempted >= limit:
                    break
                sid = str(s.id)
                fails = _catch_up_failures.get(sid, 0)
                if fails >= _CATCH_UP_MAX_FAILURES:
                    skipped += 1
                    continue
                attempted += 1
                try:
                    await process_session_feedback(db, s.id)
                    log.info("catch_up_processed", session_id=sid)
                    _catch_up_failures.pop(sid, None)
                    processed += 1
                except Exception as exc:
                    _catch_up_failures[sid] = fails + 1
                    log.error("catch_up_failed", session_id=sid, error=str(exc))
                    if _catch_up_failures[sid] >= _CATCH_UP_MAX_FAILURES:
                        skipped += 1
                        log.error("catch_up_giving_up", session_id=sid)
        finally:
            await db.execute(
                text("SELECT pg_advisory_unlock(:k)"),
                {"k": _CATCH_UP_ADVISORY_LOCK_KEY},
            )

    log.info("catch_up_pass", pending=pending, processed=processed, skipped=skipped)
    return processed


async def run_catch_up() -> None:
    """CLI one-shot: process every eligible completed session (min_age 0)."""
    await catch_up_once(min_age_seconds=0, limit=10_000)


async def _periodic_catch_up(interval_seconds: int) -> None:
    """Background loop: heal lost NATS jobs without racing fresh completions."""
    while True:
        try:
            await catch_up_once(min_age_seconds=120)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("catch_up_loop_error", error=str(exc))
        await asyncio.sleep(interval_seconds)


def maybe_start_catch_up_task() -> asyncio.Task | None:
    """Start the periodic catch-up task, or None when interval is 0 (disabled)."""
    interval = get_settings().feedback_catch_up_interval_seconds
    if interval <= 0:
        return None
    return asyncio.create_task(_periodic_catch_up(interval))


async def run_worker() -> None:
    settings = get_settings()
    log.info(
        "feedback_worker_db",
        database=settings.database_url.rsplit("/", 1)[-1],
        database_url_host=settings.database_url.split("@")[-1],
    )
    nc = await nats.connect(servers=[settings.nats_url])
    js = nc.jetstream()
    with suppress(Exception):
        await js.add_stream(
            StreamConfig(name=events.FEEDBACK_STREAM, subjects=[events.FEEDBACK_SUBJECT])
        )
    with suppress(Exception):
        await js.add_consumer(
            events.FEEDBACK_STREAM,
            config=ConsumerConfig(
                durable="feedback-worker",
                deliver_policy=DeliverPolicy.ALL,
                max_deliver=5,
                ack_wait=300,
            ),
        )

    sub = await js.pull_subscribe(events.FEEDBACK_SUBJECT, durable="feedback-worker")
    log.info("feedback_worker_listening", subject=events.FEEDBACK_SUBJECT)

    catch_up_task = maybe_start_catch_up_task()
    try:
        while True:
            try:
                msgs = await sub.fetch(batch=1, timeout=5)
            except TimeoutError:
                continue
            except Exception as exc:
                log.warning("fetch_error", error=str(exc))
                await asyncio.sleep(1)
                continue
            for msg in msgs:
                num_delivered = 1
                with suppress(Exception):
                    num_delivered = int(msg.metadata.num_delivered)
                try:
                    await process_event(msg.data, num_delivered=num_delivered)
                    await msg.ack()
                except RetryableFeedbackError as exc:
                    log.warning(
                        "feedback_job_retryable",
                        error=str(exc),
                        num_delivered=num_delivered,
                        delay=exc.delay,
                    )
                    await msg.nak(delay=exc.delay)
                except PermanentFeedbackError as exc:
                    # Poison / stale session IDs: terminate so they never redeliver.
                    log.error("feedback_job_permanent_failure", error=str(exc))
                    try:
                        await msg.term()
                    except Exception:
                        await msg.ack()
                except Exception as exc:
                    log.error(
                        "feedback_job_failed",
                        error=str(exc),
                        raw=msg.data.decode("utf-8", errors="replace")[:300],
                    )
                    await msg.nak(delay=10)
    finally:
        if catch_up_task is not None:
            catch_up_task.cancel()
            with suppress(asyncio.CancelledError):
                await catch_up_task


def main() -> None:
    settings = get_settings()
    configure_logging(log_level=settings.log_level, json_logs=settings.app_env != "local")
    if "--catch-up" in sys.argv:
        asyncio.run(run_catch_up())
    else:
        with suppress(KeyboardInterrupt):
            asyncio.run(run_worker())


if __name__ == "__main__":
    main()
