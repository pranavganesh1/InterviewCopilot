import jwt
import pytest

from app.core.security import create_access_token, create_refresh_token, decode_token


def test_access_token_roundtrip():
    token = create_access_token("user-123")
    assert decode_token(token, "access") == "user-123"


def test_refresh_token_roundtrip():
    token = create_refresh_token("user-123")
    assert decode_token(token, "refresh") == "user-123"


def test_wrong_type_rejected():
    token = create_refresh_token("user-123")
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(token, "access")


def test_expired_token_rejected():
    token = create_access_token("user-123", ttl_seconds=-10)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(token, "access")
