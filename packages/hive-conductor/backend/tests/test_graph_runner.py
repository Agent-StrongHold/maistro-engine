"""Boy Scout coverage: services/graph_runner.py (was 10% line/branch).

Covers:
- execute_dag with stub maistro.graph: builds GraphConfig + invokes run_graph
- execute_dag entry_node fallback: when not set, uses first node's id
- genome_to_dag: maps PipelineGenome → DAG dict with all node + edge fields
- execute_champion: 4 branches (no svc / no population / no champion / success)
- _build_llm_call: no base URL → stub; with base URL → real httpx fn
- _build_llm_call inner _httpx_llm: posts, parses content
- _build_llm_call with SecretStr-like api key (get_secret_value path)
- execute_dag_streaming: yields started + per-node + completed
- execute_dag_streaming: catches inner exception and yields failed
"""

from __future__ import annotations

import pathlib
import sys
from typing import Any, ClassVar

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# --- _build_llm_call ----------------------------------------------------


def test_build_llm_call_returns_stub_when_base_url_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No base URL → an async stub returning a marker string."""
    import services.graph_runner as _gr
    from services.graph_runner import _build_llm_call

    class _S:
        maistro_llm_base_url = ""
        litellm_api_base = ""
        maistro_llm_api_key = ""
        litellm_api_key = ""
        chat_default_model = "m"

    monkeypatch.setattr(_gr, "get_settings", lambda: _S())
    fn = _build_llm_call()
    import asyncio

    out = asyncio.run(fn([{"role": "user", "content": "hi"}]))
    assert "no LLM configured" in out


async def test_build_llm_call_real_httpx_posts_and_extracts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx
    import services.graph_runner as _gr
    from services.graph_runner import _build_llm_call

    class _S:
        maistro_llm_base_url = "http://stub.example"
        litellm_api_base = ""
        maistro_llm_api_key = "k"
        litellm_api_key = ""
        chat_default_model = "default-model"

    monkeypatch.setattr(_gr, "get_settings", lambda: _S())

    captured: dict[str, Any] = {}

    class _Resp:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> Any:
            return {"choices": [{"message": {"content": "out"}}]}

    class _Client:
        def __init__(self, *a: Any, **kw: Any) -> None: ...
        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *a: Any) -> None: ...
        async def post(self, url: str, *, json: Any, headers: Any) -> _Resp:
            captured["url"] = url
            captured["headers"] = headers
            captured["model"] = json["model"]
            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    fn = _build_llm_call()
    out = await fn([{"role": "user", "content": "hi"}], model="picked-model")
    assert out == "out"
    assert captured["url"] == "http://stub.example/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer k"
    assert captured["model"] == "picked-model"


async def test_build_llm_call_uses_default_model_when_kwarg_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without model kwarg, falls back to settings.chat_default_model."""
    import httpx
    import services.graph_runner as _gr
    from services.graph_runner import _build_llm_call

    class _S:
        maistro_llm_base_url = "http://x"
        litellm_api_base = ""
        maistro_llm_api_key = "k"
        litellm_api_key = ""
        chat_default_model = "the-default"

    monkeypatch.setattr(_gr, "get_settings", lambda: _S())

    captured: dict[str, Any] = {}

    class _Resp:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> Any:
            return {"choices": [{"message": {"content": "ok"}}]}

    class _Client:
        def __init__(self, *a: Any, **kw: Any) -> None: ...
        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *a: Any) -> None: ...
        async def post(self, url: str, *, json: Any, headers: Any) -> _Resp:
            captured["model"] = json["model"]
            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    fn = _build_llm_call()
    await fn([{"role": "user", "content": "hi"}])
    assert captured["model"] == "the-default"


async def test_build_llm_call_secret_str_api_key_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If api key has get_secret_value(), use it (SecretStr branch)."""
    import httpx
    import services.graph_runner as _gr
    from services.graph_runner import _build_llm_call

    class _Secret:
        def get_secret_value(self) -> str:
            return "from-secret"

    class _S:
        maistro_llm_base_url = "http://x"
        litellm_api_base = ""
        maistro_llm_api_key = _Secret()
        litellm_api_key = ""
        chat_default_model = "m"

    monkeypatch.setattr(_gr, "get_settings", lambda: _S())

    captured: dict[str, Any] = {}

    class _Resp:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> Any:
            return {"choices": [{"message": {"content": "ok"}}]}

    class _Client:
        def __init__(self, *a: Any, **kw: Any) -> None: ...
        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *a: Any) -> None: ...
        async def post(self, url: str, *, json: Any, headers: Any) -> _Resp:
            captured["auth"] = headers.get("Authorization")
            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    fn = _build_llm_call()
    await fn([{"role": "user", "content": "x"}])
    assert captured["auth"] == "Bearer from-secret"


async def test_build_llm_call_no_api_key_no_auth_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If raw_key resolves to empty string, no Authorization header set."""
    import httpx
    import services.graph_runner as _gr
    from services.graph_runner import _build_llm_call

    class _S:
        maistro_llm_base_url = "http://x"
        litellm_api_base = ""
        maistro_llm_api_key = ""
        litellm_api_key = ""
        chat_default_model = "m"

    monkeypatch.setattr(_gr, "get_settings", lambda: _S())

    captured: dict[str, Any] = {}

    class _Resp:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> Any:
            return {"choices": [{"message": {"content": "ok"}}]}

    class _Client:
        def __init__(self, *a: Any, **kw: Any) -> None: ...
        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *a: Any) -> None: ...
        async def post(self, url: str, *, json: Any, headers: Any) -> _Resp:
            captured["headers"] = dict(headers)
            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    fn = _build_llm_call()
    await fn([{"role": "user", "content": "x"}])
    assert "Authorization" not in captured["headers"]


# --- execute_dag --------------------------------------------------------


async def test_execute_dag_builds_config_and_returns_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stub maistro.graph.executor.run_graph and verify shape."""
    import services.graph_runner as gr

    captured: dict[str, Any] = {}

    class _NR:
        def __init__(self, node_id: str) -> None:
            self.node_id = node_id
            self.role = "worker"
            self.selected_candidate = "ok"
            self.success = True

    class _Result:
        total_cycles = 1
        node_results: ClassVar = [_NR("n1"), _NR("n2")]

    async def _run_graph(**kw: Any) -> Any:
        captured.update(kw)
        return _Result()

    import maistro.graph.executor as exec_mod

    monkeypatch.setattr(exec_mod, "run_graph", _run_graph)
    # Also stub _build_llm_call so we don't reach settings
    monkeypatch.setattr(gr, "_build_llm_call", lambda: None)

    out = await gr.execute_dag(
        {
            "name": "test",
            "description": "test dag",
            "nodes": [
                {"id": "n1", "role": "worker", "name": "Worker"},
                {"id": "n2", "role": "scout", "name": "Scout"},
            ],
            "edges": [{"from_node": "n1", "to_node": "n2"}],
            "entry_node": "n1",
        }
    )
    assert out["status"] == "completed"
    assert out["cycles"] == 1
    assert set(out["node_results"]) == {"n1", "n2"}
    assert out["node_results"]["n1"]["role"] == "worker"


async def test_execute_dag_entry_node_fallback_to_first_node(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If entry_node is missing, use the first node id."""
    import services.graph_runner as gr

    captured: dict[str, Any] = {}

    class _Result:
        total_cycles = 0
        node_results: ClassVar[list[Any]] = []

    async def _run_graph(**kw: Any) -> Any:
        captured["entry"] = kw["config"].entry
        return _Result()

    import maistro.graph.executor as exec_mod

    monkeypatch.setattr(exec_mod, "run_graph", _run_graph)
    monkeypatch.setattr(gr, "_build_llm_call", lambda: None)

    await gr.execute_dag(
        {
            "name": "x",
            "nodes": [{"id": "first-id", "role": "worker", "name": "F"}],
            "edges": [],
            # entry_node missing
        }
    )
    assert captured["entry"] == "first-id"


# --- genome_to_dag ----------------------------------------------------


def test_genome_to_dag_maps_nodes_and_edges() -> None:
    from services.graph_runner import genome_to_dag

    class _Node:
        def __init__(self, **kw: Any) -> None:
            for k, v in kw.items():
                setattr(self, k, v)

    class _Edge:
        def __init__(self, **kw: Any) -> None:
            for k, v in kw.items():
                setattr(self, k, v)

    class _Topo:
        nodes: ClassVar = [
            _Node(
                id="abc123def",
                role="planner",
                model="m",
                system_prompt="p",
                strategy="react",
                temperature=0.5,
                max_tokens=512,
                max_tool_rounds=3,
            ),
        ]
        edges: ClassVar = [
            _Edge(id="e1", from_node="abc123def", to_node=None, condition=None),
        ]
        entry_node = "abc123def"
        max_cycles = 5
        use_scout = True

    class _Genome:
        topology = _Topo()
        name = "evolved"
        generation = 3
        fitness_score = 0.87
        id = "g-1"

    out = genome_to_dag(_Genome())
    assert out["name"] == "evolved"
    assert out["evolved"] is True
    assert out["genome_id"] == "g-1"
    assert out["nodes"][0]["id"] == "abc123def"
    assert out["nodes"][0]["name"] == "planner-abc123"  # first 6 chars
    assert out["edges"][0]["id"] == "e1"
    assert out["max_cycles"] == 5
    assert out["run_scout"] is True


# --- execute_champion ------------------------------------------------


async def test_execute_champion_returns_error_when_no_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.evolution as evo
    import services.graph_runner as gr

    evo._service = None
    out = await gr.execute_champion()
    assert out["status"] == "error"
    assert "not started" in out["error"]


async def test_execute_champion_no_population(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.evolution as evo
    import services.graph_runner as gr

    class _Svc:
        population = None

    evo._service = _Svc()
    try:
        out = await gr.execute_champion()
        assert out["status"] == "error"
        assert "population not initialized" in out["error"]
    finally:
        evo._service = None


async def test_execute_champion_no_champion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.evolution as evo
    import services.graph_runner as gr

    class _Pop:
        def get_champion(self) -> Any:
            return None

    class _Svc:
        population = _Pop()

    evo._service = _Svc()
    try:
        out = await gr.execute_champion()
        assert out["status"] == "error"
        assert "no champion" in out["error"]
    finally:
        evo._service = None


async def test_execute_champion_success_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.evolution as evo
    import services.graph_runner as gr

    class _Topo:
        nodes: ClassVar[list[Any]] = []
        edges: ClassVar[list[Any]] = []
        entry_node = ""
        max_cycles = 1
        use_scout = False

    class _Genome:
        id = "g-1"
        name = "champ"
        generation = 5
        fitness_score = 0.99
        topology = _Topo()

    class _Pop:
        def get_champion(self) -> Any:
            return _Genome()

    class _Svc:
        population = _Pop()

    evo._service = _Svc()

    async def _stub_execute(d: dict) -> dict[str, Any]:
        return {"status": "completed", "cycles": 0, "node_results": {}}

    monkeypatch.setattr(gr, "execute_dag", _stub_execute)
    try:
        out = await gr.execute_champion()
        assert out["status"] == "completed"
        assert out["genome_id"] == "g-1"
        assert out["fitness"] == 0.99
        assert out["generation"] == 5
    finally:
        evo._service = None


# --- execute_dag_streaming -------------------------------------------


async def test_execute_dag_streaming_yields_full_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.graph_runner as gr

    class _NR:
        node_id = "n1"
        role = "worker"
        selected_candidate = "out"
        success = True

    class _Result:
        total_cycles = 1
        node_results: ClassVar = [_NR()]

    async def _run_graph(**kw: Any) -> Any:
        return _Result()

    import maistro.graph.executor as exec_mod

    monkeypatch.setattr(exec_mod, "run_graph", _run_graph)
    monkeypatch.setattr(gr, "_build_llm_call", lambda: None)

    events = []
    async for ev in gr.execute_dag_streaming(
        {
            "name": "x",
            "nodes": [{"id": "n1", "role": "worker", "name": "W"}],
            "edges": [],
            "entry_node": "n1",
        }
    ):
        events.append(ev)
    statuses = [e["status"] for e in events]
    assert statuses == ["started", "node_complete", "completed"]


async def test_execute_dag_streaming_yields_failed_on_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.graph_runner as gr

    async def _boom(**kw: Any) -> Any:
        raise RuntimeError("synthetic")

    import maistro.graph.executor as exec_mod

    monkeypatch.setattr(exec_mod, "run_graph", _boom)
    monkeypatch.setattr(gr, "_build_llm_call", lambda: None)

    events = []
    async for ev in gr.execute_dag_streaming(
        {
            "name": "x",
            "nodes": [{"id": "n1", "role": "worker", "name": "W"}],
            "edges": [],
            "entry_node": "n1",
        }
    ):
        events.append(ev)
    assert events[0]["status"] == "started"
    assert events[-1]["status"] == "failed"
    assert "synthetic" in events[-1]["error"]
