"""Test fixtures for the Turing backend.

Mirrors hive-conductor's conftest shape: put backend/ first on sys.path, reset
the state singleton per test, and provide authed_client / admin_client (auto
login) plus a turing_service_client (service-key headers).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) in sys.path:
    sys.path.remove(str(_BACKEND))
sys.path.insert(0, str(_BACKEND))

# The dev-stub login accounts (routes/auth.py) are gated off by default so a
# real deployment has no universal known admin login; tests opt in explicitly.
os.environ["TURING_ALLOW_DEV_AUTH"] = "1"


@pytest.fixture(autouse=True)
def _reset_state():
    from state import reset_state

    reset_state()
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from main import app

    return TestClient(app)


@pytest.fixture
def authed_client():
    from fastapi.testclient import TestClient
    from main import app

    c = TestClient(app)
    r = c.post("/v1/auth/login", json={"username": "testuser", "password": "testpass"})
    assert r.status_code == 200
    return c


@pytest.fixture
def admin_client():
    from fastapi.testclient import TestClient
    from main import app

    c = TestClient(app)
    r = c.post("/v1/auth/login", json={"username": "testadmin", "password": "adminpass"})
    assert r.status_code == 200
    return c


@pytest.fixture
def turing_service_client():
    """Client that sends the Turing-internal service key header."""
    from config import turing_service_key
    from fastapi.testclient import TestClient
    from main import app

    c = TestClient(app, headers={"X-Service-Key": turing_service_key()})
    return c
