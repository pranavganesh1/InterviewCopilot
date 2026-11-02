from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import get_settings

IC_ACCESS_COOKIE = "ic_access"
IC_REFRESH_COOKIE = "ic_refresh"


def _create_token(subject: str, token_type: str, ttl_seconds: int) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: str, ttl_seconds: int | None = None) -> str:
    settings = get_settings()
    ttl = ttl_seconds or settings.access_token_ttl_minutes * 60
    return _create_token(user_id, "access", ttl)


def create_refresh_token(user_id: str, ttl_seconds: int | None = None) -> str:
    settings = get_settings()
    ttl = ttl_seconds or settings.refresh_token_ttl_days * 24 * 3600
    return _create_token(user_id, "refresh", ttl)


def decode_token(token: str, expected_type: str) -> str:
    """Return the token subject if valid and of expected_type; raise jwt.PyJWTError otherwise."""
    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"expected {expected_type} token")
    return str(payload["sub"])
