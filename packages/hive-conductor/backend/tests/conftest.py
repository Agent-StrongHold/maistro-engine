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


def _seed_test_user() -> None:
    import bcrypt
    import stores

    if len(stores.users) > 0:
        return

    from datetime import UTC, datetime

    now_ts = datetime.now(UTC)
    pw_hash = bcrypt.hashpw(b"testpass", bcrypt.gensalt()).decode()
    stores.users["user"] = stores.users._model_class(
        id="user",
        username="testuser",
        password_hash=pw_hash,
        role="user",
        is_active=True,
        permissions=[],
        created_at=now_ts,
    )
    pw_hash_admin = bcrypt.hashpw(b"adminpass", bcrypt.gensalt()).decode()
    stores.users["admin"] = stores.users._model_class(
        id="admin",
        username="testadmin",
        password_hash=pw_hash_admin,
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
