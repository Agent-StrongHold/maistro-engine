import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


@pytest.fixture(autouse=True, scope="session")
def _init_engine() -> None:
    import services.engine as engine_mod
    from adapters.maistro_core import StubAgentPort

    if engine_mod._singleton is None:
        svc = engine_mod.EngineService()
        svc._agent_port = StubAgentPort()
        engine_mod._singleton = svc

    import services.foundation as foundation_mod

    if foundation_mod._singleton is None:
        f = foundation_mod.Foundation()
        foundation_mod._singleton = f

    import stores

    stores.initialize_stores()

    _seed_test_user()

    import tempfile
    from services import user_credentials as cred_svc

    cred_svc.init_credential_store(tempfile.mkdtemp(prefix="hive-cred-test-"))


def _seed_test_user() -> None:
    import stores

    if len(stores.users) > 0:
        return

    from datetime import UTC, datetime

    now_ts = datetime.now(UTC)
    # Precomputed bcrypt hashes (legacy); login auto-upgrades to Argon2id on success.
    stores.users["user"] = stores.users._model_class(
        id="user",
        username="testuser",
        password_hash="$2b$12$hmpbR.C6bkLEJ4d9PYzoqOthlZNKk.WOSjXnLxHpC0Y3S6sgdYfPq",
        role="user",
        is_active=True,
        permissions=[],
        created_at=now_ts,
    )
    stores.users["admin"] = stores.users._model_class(
        id="admin",
        username="testadmin",
        password_hash="$2b$12$QByl/bXdX8r5UJOGZvS1uelzetMHaGLsRG0hu97dSDIerv2FFdbH.",
        role="admin",
        is_active=True,
        permissions=[],
        created_at=now_ts,
    )


@pytest.fixture(scope="session")
def authed_client():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    r = client.post("/v1/auth/login", json={"username": "testuser", "password": "testpass"})
    assert r.status_code == 200
    return client


@pytest.fixture(scope="session")
def admin_client():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    r = client.post("/v1/auth/login", json={"username": "testadmin", "password": "adminpass"})
    assert r.status_code == 200
    return client
