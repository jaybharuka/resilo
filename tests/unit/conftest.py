"""
tests/unit/conftest.py

Overrides the session-scoped _setup_database fixture from tests/conftest.py
so that pure-unit tests run without a live PostgreSQL connection.

The root conftest creates the asyncpg engine at module import time and then
tries to CREATE ALL tables in the autouse _setup_database fixture.  That
fixture is session-scoped, so it runs once before any test in the session.
By redefining it here with the same name and scope, pytest uses this
(closer-scope) fixture for tests collected under tests/unit/.
"""
from __future__ import annotations

import pytest
import pytest_asyncio


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _setup_database():
    """No-op override: unit tests use mocked DB sessions — no live DB needed."""
    yield


@pytest_asyncio.fixture(autouse=True)
async def _wipe_sessions():
    """No-op override: no sessions to wipe in unit tests."""
    yield
