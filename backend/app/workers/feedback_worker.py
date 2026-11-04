"""Feedback worker: consumes feedback.jobs from NATS JetStream.

Run: cd backend && uv run python -m app.workers.feedback_worker
Catch-up mode (no NATS): uv run python -m app.workers.feedback_worker --catch-up
"""

import asyncio
import json
import sys
from contextlib import suppress

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


class PermanentFeedbackError(Exception):
    """Job cannot succeed on retry (e.g. session permanently missing)."""


async def process_event(data: bytes) -> dict:
    event = json.loads(data)
    session_id = event.get("session_id")
    job_id = event.get("job_id")
    publisher_db = event.get("database")
    if not session_id:
        raise PermanentFeedbackError("feedback job missing session_id")

    settings = get_settings()
    worker_db = settings.database_url.rsplit("/", 1)[-1]
    log.info(
        "feedback_job_received",
        session_id=str(session_id),
        job_id=job_id,
        publisher_database=publisher_db,
        worker_database=worker_db,
    )

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
                raise PermanentFeedbackError(
                    f"session_not_found session_id={session_id} job_id={job_id} "
                    f"worker_database={live_db} publisher_database={publisher_db}"
                ) from exc
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
    # nats-py 2.x: the field is `durable_name` (NOT `durable`) — passing
    # `durable=` raises TypeError, which used to be silently suppressed and
    # then pull_subscribe auto-created the consumer with DEFAULT limits
    # (max_deliver=-1 → infinite redelivery on poison messages).
    with suppress(Exception):
        await js.add_consumer(
            events.FEEDBACK_STREAM,
            config=ConsumerConfig(
                durable_name="feedback-worker",
                deliver_policy=DeliverPolicy.ALL,
                max_deliver=5,
                ack_wait=300,
            ),
        )

    sub = await js.pull_subscribe(events.FEEDBACK_SUBJECT, durable="feedback-worker")
    log.info("feedback_worker_listening", subject=events.FEEDBACK_SUBJECT)

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
            try:
                await process_event(msg.data)
                await msg.ack()
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


async def run_catch_up() -> None:
    """Process every completed session that has no feedback report yet."""
    async with SessionFactory() as db:
        live_db = (await db.execute(text("SELECT current_database()"))).scalar()
        sessions = (
            (
                await db.execute(
                    select(InterviewSession)
                    .where(InterviewSession.status == "completed")
                    .outerjoin(FeedbackReport, FeedbackReport.session_id == InterviewSession.id)
                    .where(FeedbackReport.id.is_(None))
                )
            )
            .scalars()
            .all()
        )
        log.info("catch_up_scanning", pending=len(sessions), database=live_db)
        for s in sessions:
            try:
                await process_session_feedback(db, s.id)
                log.info("catch_up_processed", session_id=str(s.id))
            except Exception as exc:
                log.error("catch_up_failed", session_id=str(s.id), error=str(exc))


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
