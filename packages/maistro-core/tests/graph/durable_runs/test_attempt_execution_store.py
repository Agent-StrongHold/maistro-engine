from __future__ import annotations

from typing import Any

import pytest

from maistro.graph import Graph, GraphExecutionState, Node
from maistro.graph.durable_runs import (
    DurableAttemptExecutionStore,
    DurableRunRecord,
    InMemoryDurableRunStore,
)
from maistro.runs import (
    AttemptExecutionService,
    AttemptStatus,
    GraphSnapshot,
    NodeRun,
    Run,
    RunStatus,
)
from maistro.runs.execution_store import AttemptExecutionStore
from maistro.runtime import PythonExecutionRuntime


async def _durable_execution() -> tuple[
    InMemoryDurableRunStore,
    DurableAttemptExecutionStore,
    NodeRun,
]:
    graph = Graph(
        workspace_id="ws-1",
        project_id="project-1",
        name="Durable attempt bridge",
        nodes=[Node(node_id="node-1", node_type="agent")],
    )
    run = Run(
        run_id="run-1",
        workspace_id=graph.workspace_id,
        project_id=graph.project_id,
        graph=GraphSnapshot.from_graph(graph),
        status=RunStatus.RUNNING,
    )
    node_run = NodeRun(
        node_run_id="node-run-1",
        run_id=run.run_id,
        node_id="node-1",
        ordinal=1,
        status=RunStatus.RUNNING,
    )
    record = DurableRunRecord(
        run=run,
        graph_state=GraphExecutionState(run_id=run.run_id, active_node_ids=("node-1",)),
        node_runs=(node_run,),
        version=1,
    )
    durable = InMemoryDurableRunStore()
    await durable.create(record)
    adapter = DurableAttemptExecutionStore(durable, run_id=run.run_id)
    return durable, adapter, node_run


def test_durable_adapter_satisfies_minimal_attempt_execution_contract() -> None:
    assert isinstance(
        DurableAttemptExecutionStore(InMemoryDurableRunStore(), run_id="run-1"),
        AttemptExecutionStore,
    )


@pytest.mark.asyncio
async def test_canonical_attempt_service_persists_physical_history_in_durable_envelope() -> None:
    durable, adapter, node_run = await _durable_execution()
    service = AttemptExecutionService(store=adapter, runtime=PythonExecutionRuntime())

    async def executor(work_item: Any, _context: Any) -> dict[str, Any]:
        return {"value": work_item}

    terminal = await service.execute(
        node_run.node_run_id,
        7,
        None,
        executor=executor,
        executor_id="graph-node",
    )

    record = await durable.get("run-1")
    assert record is not None
    assert len(record.attempts) == 1
    assert record.attempts[0].attempt_id == terminal.attempt_id
    assert record.attempts[0].status is AttemptStatus.COMPLETED
    assert record.attempts[0].execution_lease is not None
    assert record.node_runs[0].status is RunStatus.COMPLETED
    assert record.node_runs[0].accepted_outcome is not None
    assert record.node_runs[0].accepted_outcome.attempt_result.attempt_id == terminal.attempt_id
    assert record.node_runs[0].result == {"value": 7}


@pytest.mark.asyncio
async def test_durable_attempt_retry_history_remains_ordered_per_logical_visit() -> None:
    durable, adapter, node_run = await _durable_execution()
    service = AttemptExecutionService(store=adapter, runtime=PythonExecutionRuntime())

    async def fail(_work_item: Any, _context: Any) -> None:
        raise RuntimeError("transient")

    with pytest.raises(RuntimeError, match="transient"):
        await service.execute(node_run.node_run_id, None, None, executor=fail)

    async def succeed(_work_item: Any, _context: Any) -> str:
        return "accepted"

    successful = await service.execute(node_run.node_run_id, None, None, executor=succeed)
    record = await durable.get("run-1")
    assert record is not None
    assert [attempt.ordinal for attempt in record.attempts] == [1, 2]
    assert [attempt.status for attempt in record.attempts] == [
        AttemptStatus.FAILED,
        AttemptStatus.COMPLETED,
    ]
    assert record.node_runs[0].accepted_outcome is not None
    assert record.node_runs[0].accepted_outcome.attempt_result.attempt_id == successful.attempt_id
