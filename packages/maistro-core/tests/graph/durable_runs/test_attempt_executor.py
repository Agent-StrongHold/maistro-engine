from __future__ import annotations

import asyncio
from typing import Any, ClassVar

import pytest
from pydantic import BaseModel

from maistro.graph import Edge, Graph, Node
from maistro.graph.durable_runs import InMemoryDurableRunStore, RunStatus, run_durable_graph
from maistro.graph.nodes import BaseNode, NodeContext
from maistro.runs import AttemptStatus
from maistro.runtime import PythonExecutionRuntime


class _Empty(BaseModel):
    pass


class _Seed(BaseModel):
    seed: str


class _BranchOut(BaseModel):
    branch: str


class _Start(BaseNode[_Empty, _Seed]):
    kind: ClassVar[str] = "test.attempt.start"
    kind_category: ClassVar = "sync.transform"
    input_schema: ClassVar[type[BaseModel]] = _Empty
    output_schema: ClassVar[type[BaseModel]] = _Seed

    async def _execute(self, inputs: _Empty, ctx: NodeContext) -> _Seed:
        return _Seed(seed="go")


class _Barrier:
    started: ClassVar[int] = 0
    ready: ClassVar[asyncio.Event | None] = None

    @classmethod
    def reset(cls) -> None:
        cls.started = 0
        cls.ready = asyncio.Event()

    @classmethod
    async def arrive(cls) -> None:
        assert cls.ready is not None
        cls.started += 1
        if cls.started == 2:
            cls.ready.set()
        await asyncio.wait_for(cls.ready.wait(), timeout=1.0)


class _Left(BaseNode[_Empty, _BranchOut]):
    kind: ClassVar[str] = "test.attempt.left"
    kind_category: ClassVar = "sync.transform"
    input_schema: ClassVar[type[BaseModel]] = _Empty
    output_schema: ClassVar[type[BaseModel]] = _BranchOut

    async def _execute(self, inputs: _Empty, ctx: NodeContext) -> _BranchOut:
        await _Barrier.arrive()
        return _BranchOut(branch="left")


class _Right(BaseNode[_Empty, _BranchOut]):
    kind: ClassVar[str] = "test.attempt.right"
    kind_category: ClassVar = "sync.transform"
    input_schema: ClassVar[type[BaseModel]] = _Empty
    output_schema: ClassVar[type[BaseModel]] = _BranchOut

    async def _execute(self, inputs: _Empty, ctx: NodeContext) -> _BranchOut:
        await _Barrier.arrive()
        return _BranchOut(branch="right")


class _RecordingRuntime(PythonExecutionRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.execution_ids: list[str] = []

    async def execute(
        self,
        work_item: Any,
        execution_context: Any,
        *,
        execution_id: str,
        executor: Any,
        timeout_s: float | None = None,
    ) -> Any:
        self.execution_ids.append(execution_id)
        return await super().execute(
            work_item,
            execution_context,
            execution_id=execution_id,
            executor=executor,
            timeout_s=timeout_s,
        )


def _graph() -> Graph:
    return Graph(
        workspace_id="ws-1",
        project_id="project-1",
        name="Attempt frontier",
        nodes=[
            Node(node_id="start", node_type=_Start.kind),
            Node(node_id="left", node_type=_Left.kind),
            Node(node_id="right", node_type=_Right.kind),
        ],
        edges=[
            Edge(edge_id="start-left", from_node="start", to_node="left"),
            Edge(
                edge_id="start-right",
                from_node="start",
                to_node="right",
                metadata={"parallel": True},
            ),
        ],
        metadata={"entry_node": "start"},
    )


def _resolver(node_id: str, graph: Graph) -> BaseNode[Any, Any]:
    del graph
    return {"start": _Start, "left": _Left, "right": _Right}[node_id]()


@pytest.mark.asyncio
async def test_public_durable_executor_routes_each_node_run_through_attempt_runtime() -> None:
    _Barrier.reset()
    store = InMemoryDurableRunStore()
    runtime = _RecordingRuntime()

    record = await run_durable_graph(
        _graph(),
        store=store,
        node_resolver=_resolver,
        runtime=runtime,
    )

    assert record.status is RunStatus.COMPLETED
    assert _Barrier.started == 2
    assert [node_run.node_id for node_run in record.node_runs] == ["start", "left", "right"]
    assert len(record.attempts) == 3
    assert [attempt.ordinal for attempt in record.attempts] == [1, 1, 1]
    assert all(attempt.status is AttemptStatus.COMPLETED for attempt in record.attempts)
    assert [attempt.node_run_id for attempt in record.attempts] == [
        node_run.node_run_id for node_run in record.node_runs
    ]
    assert set(runtime.execution_ids) == {attempt.attempt_id for attempt in record.attempts}
