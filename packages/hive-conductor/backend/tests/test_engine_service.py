"""Boy Scout coverage: services/engine.py (was 27%).

Covers:
- TaskRecord property views (id, name, description, mission_status,
  progress with/without subtasks, current_step, created_at, started_at,
  completed_at, error)
- _STATUS_MAP coverage via mission_status property
- EngineService singleton lifecycle (get/start/stop/get-when-not-started)
- EngineService.start with no router_api_key → StubAgentPort
- EngineService.stop with no runner is safe
- submit_task: no queue → RuntimeError
- submit_task: gated capability without confirmed program_context →
  ValueError (work-item-draft guard)
- submit_task: non-gated capability submits and returns TaskRecord
- get_task / list_tasks / delete_task / clear_tasks no-queue branches
- clear_tasks with status filter (failed / completed)
- iter_task_events: yields update for non-terminal, returns on terminal
"""

from __future__ import annotations

import pathlib
import sys
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


@pytest.fixture(autouse=True)
def _reset_singleton():
    import services.engine as e

    prev = e._singleton
    e._singleton = None
    yield
    e._singleton = prev


# --- TaskRecord properties ----------------------------------------------


def _fake_task(**overrides: Any) -> Any:
    defaults = {
        "task_id": "t-1",
        "description": "ship the feature",
        "status": "queued",
        "progress": SimpleNamespace(subtasks=4, completed=2, current="planning"),
        "phase": "",
        "created_at": datetime(2026, 5, 22, tzinfo=UTC),
        "started_at": datetime(2026, 5, 22, 1, tzinfo=UTC),
        "completed_at": None,
        "result": None,
    }
    defaults.update(overrides)
    t = SimpleNamespace(**defaults)
    return t


def test_task_record_basic_properties() -> None:
    from services.engine import TaskRecord

    rec = TaskRecord(_fake_task())
    assert rec.id == "t-1"
    assert rec.name == "ship the feature"
    assert rec.description == "ship the feature"
    assert rec.mission_status == "pending"  # queued → pending
    assert rec.progress == 0.5  # 2/4
    assert rec.current_step == "planning"
    assert rec.started_at is not None
    assert rec.completed_at is None
    assert rec.error is None


def test_task_record_status_mapping() -> None:
    """Each status string maps to the right mission_status."""
    from services.engine import TaskRecord

    mapping = {
        "queued": "pending",
        "planning": "running",
        "coding": "running",
        "reviewing": "running",
        "testing": "running",
        "completed": "completed",
        "failed": "failed",
        "cancelled": "failed",
    }
    for src, expected in mapping.items():
        rec = TaskRecord(_fake_task(status=src))
        assert rec.mission_status == expected


def test_task_record_unknown_status_falls_back_to_pending() -> None:
    from services.engine import TaskRecord

    rec = TaskRecord(_fake_task(status="weird"))
    assert rec.mission_status == "pending"


def test_task_record_progress_no_subtasks_falls_back() -> None:
    from services.engine import TaskRecord

    # No subtasks; not completed → 0.0
    rec = TaskRecord(
        _fake_task(
            progress=SimpleNamespace(subtasks=0, completed=0, current=""),
            status="queued",
        )
    )
    assert rec.progress == 0.0

    # No subtasks; completed → 1.0
    rec = TaskRecord(
        _fake_task(
            progress=SimpleNamespace(subtasks=0, completed=0, current=""),
            status="completed",
        )
    )
    assert rec.progress == 1.0


def test_task_record_current_step_falls_back_to_phase() -> None:
    from services.engine import TaskRecord

    rec = TaskRecord(
        _fake_task(
            progress=SimpleNamespace(subtasks=0, completed=0, current=""),
            phase="phase-x",
        )
    )
    assert rec.current_step == "phase-x"


def test_task_record_error_when_result_set() -> None:
    from services.engine import TaskRecord

    rec = TaskRecord(_fake_task(result=SimpleNamespace(error="boom")))
    assert rec.error == "boom"


def test_task_record_short_name_takes_first_60_chars() -> None:
    from services.engine import TaskRecord

    long = "x" * 200
    rec = TaskRecord(_fake_task(description=long))
    assert rec.name == "x" * 60


# --- EngineService singleton ---------------------------------------------


def test_get_engine_raises_when_not_started() -> None:
    from services.engine import get_engine

    with pytest.raises(RuntimeError, match="EngineService not started"):
        get_engine()


async def test_start_with_no_router_key_uses_stub_agent_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.engine import EngineService

    class _Settings:
        maistro_router_api_key = ""

    # Stub out TaskQueue/TaskRunner so .start doesn't try to spawn real ones
    class _Q:
        pass

    class _R:
        def __init__(self, q: Any, executor: Any) -> None:
            pass

        async def start(self) -> None:
            pass

    import types

    queue_mod = types.ModuleType("maistro.tasks.queue")
    queue_mod.TaskQueue = _Q  # type: ignore[attr-defined]
    runner_mod = types.ModuleType("maistro.tasks.runner")
    runner_mod.TaskRunner = _R  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "maistro.tasks.queue", queue_mod)
    monkeypatch.setitem(sys.modules, "maistro.tasks.runner", runner_mod)
    conductor_mod = types.ModuleType("maistro.agents.conductor")

    async def _stub_run_task(*a: Any, **kw: Any) -> Any:
        return None

    conductor_mod.run_task = _stub_run_task  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "maistro.agents.conductor", conductor_mod)

    svc = EngineService()
    await svc.start(_Settings())  # type: ignore[arg-type]
    assert svc._agent_port is not None
    # type name reflects stub fallback
    assert type(svc._agent_port).__name__ == "StubAgentPort"


async def test_stop_with_no_runner_is_safe() -> None:
    from services.engine import EngineService

    svc = EngineService()
    # _runner is None — stop should be a no-op
    await svc.stop()


async def test_stop_with_failing_runner_is_swallowed() -> None:
    """The runner's stop() might raise; contextlib.suppress lets it pass."""
    from services.engine import EngineService

    class _Runner:
        async def stop(self) -> None:
            raise RuntimeError("synthetic")

    svc = EngineService()
    svc._runner = _Runner()
    await svc.stop()  # no raise


# --- submit_task ---------------------------------------------------------


async def test_submit_task_no_queue_raises_runtime() -> None:
    from services.engine import EngineService

    svc = EngineService()
    with pytest.raises(RuntimeError, match="TaskQueue not available"):
        await svc.submit_task("n", "d")


async def test_submit_task_gated_capability_without_confirmed_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A gated capability must come with `program_context.confirmed=True`."""
    from services.engine import EngineService

    import maistro.agents.pm_capabilities as caps

    monkeypatch.setattr(caps, "is_gated", lambda c: True)
    monkeypatch.setattr(caps, "normalize_capability", lambda c: c)

    svc = EngineService()
    svc._queue = SimpleNamespace()  # truthy
    with pytest.raises(ValueError, match="work-item draft flow"):
        await svc.submit_task(
            "n",
            "d",
            capability="any.gated_cap",
            program_context=None,  # not confirmed
        )


async def test_submit_task_success_returns_task_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.engine import EngineService

    import maistro.agents.pm_capabilities as caps

    monkeypatch.setattr(caps, "is_gated", lambda c: False)
    monkeypatch.setattr(caps, "normalize_capability", lambda c: c)

    class _Queue:
        async def submit(self, body: Any, *, user_id: str = "") -> Any:
            return _fake_task(task_id="new-task", description=body.description)

    svc = EngineService()
    svc._queue = _Queue()
    rec = await svc.submit_task(
        "n",
        "ship hello",
        task_type="intake",
        agent_id="intake",
        capability="route_to_pm_agent",
    )
    assert rec.id == "new-task"
    assert rec.description == "ship hello"


# --- get_task / list_tasks / delete_task / clear_tasks ------------------


def test_get_task_no_queue_returns_none() -> None:
    from services.engine import EngineService

    svc = EngineService()
    assert svc.get_task("any") is None


def test_get_task_with_queue_returns_record() -> None:
    from services.engine import EngineService

    class _Q:
        def get(self, tid: str, *, user_id: Any) -> Any:
            return _fake_task(task_id=tid)

    svc = EngineService()
    svc._queue = _Q()
    rec = svc.get_task("t-1")
    assert rec is not None
    assert rec.id == "t-1"


def test_get_task_missing_returns_none() -> None:
    from services.engine import EngineService

    class _Q:
        def get(self, tid: str, *, user_id: Any) -> Any:
            return None

    svc = EngineService()
    svc._queue = _Q()
    assert svc.get_task("missing") is None


def test_list_tasks_empty_queue_returns_empty() -> None:
    from services.engine import EngineService

    svc = EngineService()
    assert svc.list_tasks() == []


def test_list_tasks_returns_reversed_records() -> None:
    from services.engine import EngineService

    class _Q:
        def list_tasks(self, *, limit: int, user_id: Any) -> tuple[list[Any], int]:
            return ([_fake_task(task_id="a"), _fake_task(task_id="b")], 2)

    svc = EngineService()
    svc._queue = _Q()
    out = svc.list_tasks()
    # Reversed
    assert [r.id for r in out] == ["b", "a"]


def test_delete_task_no_queue_returns_false() -> None:
    from services.engine import EngineService

    svc = EngineService()
    assert svc.delete_task("any") is False


def test_delete_task_with_queue_passes_through() -> None:
    from services.engine import EngineService

    class _Q:
        def remove(self, tid: str) -> bool:
            return tid == "exists"

    svc = EngineService()
    svc._queue = _Q()
    assert svc.delete_task("exists") is True
    assert svc.delete_task("nope") is False


def test_clear_tasks_no_queue_returns_zero() -> None:
    from services.engine import EngineService

    svc = EngineService()
    assert svc.clear_tasks() == 0


def test_clear_tasks_filters_by_status(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.engine import EngineService

    captured: list[Any] = []

    class _Q:
        def remove_where(self, *, status: Any) -> int:
            captured.append(status)
            return 3

    svc = EngineService()
    svc._queue = _Q()
    from maistro.tasks.models import TaskStatus

    # No filter → status=None
    assert svc.clear_tasks() == 3
    assert captured[-1] is None
    # status="failed" → TaskStatus.FAILED
    svc.clear_tasks(status="failed")
    assert captured[-1] is TaskStatus.FAILED
    # status="completed" → TaskStatus.COMPLETED
    svc.clear_tasks(status="completed")
    assert captured[-1] is TaskStatus.COMPLETED


# --- iter_task_events --------------------------------------------------


async def test_iter_task_events_no_queue_returns_immediately() -> None:
    from services.engine import EngineService

    svc = EngineService()
    events = [ev async for ev in svc.iter_task_events("t-1")]
    assert events == []


async def test_iter_task_events_yields_then_terminates() -> None:
    from services.engine import EngineService

    states = [
        _fake_task(task_id="t-1", status="planning"),
        _fake_task(
            task_id="t-1",
            status="completed",
            progress=SimpleNamespace(subtasks=1, completed=1, current="done"),
        ),
    ]
    idx = [0]

    class _Q:
        def get(self, tid: str, *, user_id: Any = None) -> Any:
            i = min(idx[0], len(states) - 1)
            return states[i]

        async def wait_for_update(self, tid: str) -> None:
            idx[0] += 1

    svc = EngineService()
    svc._queue = _Q()
    events = [ev async for ev in svc.iter_task_events("t-1")]
    statuses = [e["status"] for e in events]
    assert statuses == ["running", "completed"]


async def test_iter_task_events_returns_when_task_disappears() -> None:
    from services.engine import EngineService

    class _Q:
        def get(self, tid: str, *, user_id: Any = None) -> Any:
            return None

    svc = EngineService()
    svc._queue = _Q()
    events = [ev async for ev in svc.iter_task_events("missing")]
    assert events == []
