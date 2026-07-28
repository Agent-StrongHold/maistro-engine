"""WebSocket handshake authentication (review finding C2).

`routes/ws.py` had no test file at all and no auth: `AuthMiddleware` subclasses
Starlette's `BaseHTTPMiddleware`, which only runs for `scope["type"] == "http"`,
so both sockets were reachable by anyone who could open a TCP connection —
including `/dags/{id}/run`, which *executes* the graph.

Every rejection test here fails without the fix: before it, `websocket_connect`
succeeded for an anonymous or cross-origin client instead of raising. The one
acceptance test (`test_task_stream_accepts_authenticated_user`) passed before the
fix too — deliberately. It is the control that proves the new checks did not
simply close every socket, which is the cheap way to make the other four green.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


@pytest.fixture
def anon_client() -> TestClient:
    from main import app

    return TestClient(app)


@pytest.mark.contract("behavioral")
@pytest.mark.scope("integration")
def test_task_stream_rejects_anonymous(anon_client: TestClient) -> None:
    with (
        pytest.raises(WebSocketDisconnect),
        anon_client.websocket_connect("/v1/ws/tasks/any-task") as ws,
    ):
        ws.receive_json()


@pytest.mark.contract("behavioral")
@pytest.mark.scope("integration")
def test_dag_run_stream_rejects_anonymous(anon_client: TestClient) -> None:
    """The higher-stakes of the two: this socket runs the DAG."""
    with (
        pytest.raises(WebSocketDisconnect),
        anon_client.websocket_connect("/v1/ws/dags/whatever/run") as ws,
    ):
        ws.receive_json()


@pytest.mark.contract("behavioral")
@pytest.mark.scope("integration")
def test_dag_run_stream_rejects_authenticated_user_without_permission(
    authed_client: TestClient,
) -> None:
    """Authentication alone is not enough.

    `POST /v1/dags` requires `dags.write` in `_PROTECTED_OPS`; the seeded
    `testuser` has `permissions=[]`. If the socket only checked identity, this
    plain user could run a graph over WebSocket that the HTTP route denies —
    an elevation bypass by protocol choice.
    """
    with (
        pytest.raises(WebSocketDisconnect),
        authed_client.websocket_connect("/v1/ws/dags/whatever/run") as ws,
    ):
        ws.receive_json()


@pytest.mark.contract("behavioral")
@pytest.mark.scope("integration")
def test_task_stream_accepts_authenticated_user(authed_client: TestClient) -> None:
    """The socket must still work for a legitimate caller.

    An unknown task id yields no events, so the server closes cleanly after
    accepting — reaching the close without a handshake rejection is the proof
    that authentication passed rather than that everything is now denied.
    """
    with (
        authed_client.websocket_connect("/v1/ws/tasks/unknown-task") as ws,
        pytest.raises(WebSocketDisconnect),
    ):
        ws.receive_json()


@pytest.mark.contract("behavioral")
@pytest.mark.scope("integration")
def test_cross_site_origin_is_rejected(authed_client: TestClient) -> None:
    """Cross-site WebSocket hijacking.

    CORS does not apply to a WebSocket handshake: a page on any origin can open
    one and the browser attaches the session cookie. The Origin check is the
    only thing standing between a visited page and an authenticated socket.
    """
    with (
        pytest.raises(WebSocketDisconnect),
        authed_client.websocket_connect(
            "/v1/ws/tasks/unknown-task",
            headers={"Origin": "https://evil.example"},
        ) as ws,
    ):
        ws.receive_json()
