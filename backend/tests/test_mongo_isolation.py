"""Offline guards: pytest must never resolve the application Mongo DB name."""

import pytest

from app.core.config import get_settings
from app.db.mongo import (
    APP_MONGO_DB,
    TEST_MONGO_DB,
    assert_mongo_db_safe_for_tests,
    get_mongo_db,
)


def test_conftest_forces_dedicated_mongo_db_name():
    assert get_settings().mongo_db == TEST_MONGO_DB
    assert get_settings().mongo_db != APP_MONGO_DB


def test_assert_mongo_db_safe_for_tests_blocks_app_name():
    # PYTEST_CURRENT_TEST is set by pytest for this function.
    with pytest.raises(RuntimeError, match="Refusing Mongo DB"):
        assert_mongo_db_safe_for_tests(APP_MONGO_DB)


def test_assert_mongo_db_safe_for_tests_allows_test_name():
    assert assert_mongo_db_safe_for_tests(TEST_MONGO_DB) == TEST_MONGO_DB


def test_get_mongo_db_refuses_app_database_without_connecting(monkeypatch):
    """Guard must raise before opening a client when settings name is unsafe."""
    get_settings.cache_clear()
    monkeypatch.setenv("MONGO_DB", APP_MONGO_DB)
    get_settings.cache_clear()

    calls: list[object] = []

    def boom(*_a, **_k):
        calls.append(True)
        raise AssertionError("get_mongo_client must not be called for app DB")

    monkeypatch.setattr("app.db.mongo.get_mongo_client", boom)
    with pytest.raises(RuntimeError, match="Refusing Mongo DB"):
        get_mongo_db()
    assert calls == []
    # Restore test DB name for later tests in this process.
    monkeypatch.setenv("MONGO_DB", TEST_MONGO_DB)
    get_settings.cache_clear()
