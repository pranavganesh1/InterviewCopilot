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
from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.sqlalchemy import SessionFactory
from app.models.feedback import FeedbackReport
from app.models.interview import InterviewSession
from app.services import events
from app.services.feedback_service import process_session_feedback

log = get_logger(__name__)


async def process_event(data: bytes) -> None:
    event = json.loads(data)
    session_id = event["session_id"]
    async with SessionFactory() as db:
        result = await process_session_feedback(db, session_id)
        log.info("feedback_processed", session_id=session_id, result=str(result)[:120])


async def run_worker() -> None:
    settings = get_settings()
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
                max_deliver=3,
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
            except Exception as exc:
                log.error("feedback_job_failed", error=str(exc))
                await msg.nak(delay=10)


async def run_catch_up() -> None:
    """Process every completed session that has no feedback report yet."""
    async with SessionFactory() as db:
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
        log.info("catch_up_scanning", pending=len(sessions))
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
