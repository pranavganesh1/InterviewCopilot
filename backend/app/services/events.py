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


async def publish_feedback_job(session_id, track_id, user_id) -> None:
    """Publish a feedback job event. Never raises: a failed dispatch must not
    fail the interview — the worker's catch-up scan heals any gap."""
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
    }
    try:
        nc = await nats.connect(servers=[settings.nats_url])
        try:
            js = nc.jetstream()
            with suppress(Exception):
                await js.add_stream(StreamConfig(name=FEEDBACK_STREAM, subjects=[FEEDBACK_SUBJECT]))
            await js.publish(FEEDBACK_SUBJECT, json.dumps(event).encode())
        finally:
            await nc.drain()
        log.info("feedback_job_published", session_id=event["session_id"])
    except Exception as exc:
        log.error("feedback_job_publish_failed", session_id=event["session_id"], error=str(exc))
