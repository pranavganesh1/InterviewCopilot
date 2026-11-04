import json
import uuid
from contextlib import suppress
from datetime import UTC, datetime

import nats
from nats.js.api import StreamConfig

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

FEEDBACK_STREAM = "FEEDBACK"
FEEDBACK_SUBJECT = "feedback.jobs"


async def connect_nats():
    """Connect for app-lifetime reuse (main lifespan). Returns None on failure."""
    try:
        return await nats.connect(servers=[get_settings().nats_url])
    except Exception as exc:
        log.warning("nats_connect_failed", error=str(exc))
        return None


async def publish_feedback_job(session_id, track_id, user_id, nc=None) -> None:
    """Publish a feedback job event. Never raises: a failed dispatch must not
    fail the interview — the worker's catch-up scan heals any gap.

    nc: an existing connection to reuse (e.g. app.state.nats); when omitted,
    a one-off connection is made and drained here.

    Only interview session IDs (UUID strings) are published — never onboarding
    conversation IDs.
    """
    settings = get_settings()
    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": "session.feedback.requested",
        "event_version": 1,
        "job_id": str(uuid.uuid4()),
        "session_id": str(session_id),
        "track_id": str(track_id),
        "user_id": str(user_id),
        "occurred_at": datetime.now(UTC).isoformat(),
        "database": settings.database_url.rsplit("/", 1)[-1],
    }
    # Refuse to publish malformed IDs (guards against accidental non-session values).
    try:
        uuid.UUID(str(session_id))
    except (ValueError, TypeError):
        log.error(
            "feedback_job_refused_invalid_session_id",
            session_id=str(session_id),
            job_id=event["job_id"],
        )
        return

    owned = nc is None
    try:
        if nc is None:
            nc = await nats.connect(servers=[settings.nats_url])
        js = nc.jetstream()
        with suppress(Exception):
            await js.add_stream(StreamConfig(name=FEEDBACK_STREAM, subjects=[FEEDBACK_SUBJECT]))
        await js.publish(FEEDBACK_SUBJECT, json.dumps(event).encode())
        log.info(
            "feedback_job_published",
            session_id=event["session_id"],
            job_id=event["job_id"],
            track_id=event["track_id"],
            user_id=event["user_id"],
            database=event["database"],
        )
    except Exception as exc:
        log.error(
            "feedback_job_publish_failed",
            session_id=event["session_id"],
            job_id=event["job_id"],
            error=str(exc),
        )
    finally:
        if owned and nc is not None:
            with suppress(Exception):
                await nc.drain()
