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
AUTHORING_STREAM = "AUTHORING"
AUTHORING_SUBJECT = "track-authoring.jobs"

# Fail fast when NATS is down (Docker not started) instead of hanging.
_NATS_CONNECT_TIMEOUT_S = 5
_NATS_MAX_RECONNECT = 10
_NATS_RECONNECT_WAIT_S = 1


async def _open_nats():
    settings = get_settings()
    return await nats.connect(
        servers=[settings.nats_url],
        connect_timeout=_NATS_CONNECT_TIMEOUT_S,
        max_reconnect_attempts=_NATS_MAX_RECONNECT,
        reconnect_time_wait=_NATS_RECONNECT_WAIT_S,
    )


async def publish_track_authoring_job(track_id, user_id) -> None:
    """Queue async brief authoring for a freshly created track (M11)."""
    settings = get_settings()
    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": "track.brief.authoring_requested",
        "event_version": 1,
        "job_id": str(uuid.uuid4()),
        "track_id": str(track_id),
        "user_id": str(user_id),
        "occurred_at": datetime.now(UTC).isoformat(),
    }
    nc = None
    try:
        nc = await _open_nats()
        js = nc.jetstream()
        with suppress(Exception):
            await js.add_stream(StreamConfig(name=AUTHORING_STREAM, subjects=[AUTHORING_SUBJECT]))
        await js.publish(AUTHORING_SUBJECT, json.dumps(event).encode())
        log.info("track_authoring_published", track_id=event["track_id"])
    except Exception as exc:
        log.error("track_authoring_publish_failed", track_id=event["track_id"], error=str(exc))
    finally:
        if nc is not None:
            with suppress(Exception):
                await nc.drain()


async def connect_nats(*, required: bool = False):
    """Connect for app-lifetime reuse (main lifespan). Returns None on failure
    unless required=True, in which case the exception is re-raised."""
    settings = get_settings()
    try:
        nc = await _open_nats()
        log.info("nats_connected", nats_url=settings.nats_url)
        return nc
    except Exception as exc:
        log.warning("nats_connect_failed", nats_url=settings.nats_url, error=str(exc))
        if required:
            raise
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
            nc = await _open_nats()
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
