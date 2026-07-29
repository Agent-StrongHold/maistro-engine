"""Kills for the viable surviving mutants in `durable_runs/executor.py`.

The mutation gate runs per changed file, so this module had never been mutated
until a PR touched it, and it arrived carrying its whole history of untested
behaviour: 139 survivors out of 506 mutants. `scripts/mutation_viability.py`
splits those into 66 that no test can kill -- operator swaps inside type
annotations, which `from __future__ import annotations` never evaluates -- and
73 that are real coverage gaps. This file targets the 73.

Each test names the mutant it kills and, where the choice of a literal matters,
why that literal and not a rounder one. That detail is the whole game here: a
test asserting `attempts == 1` after starting from 0 looks like it pins the
increment, but `0 | 1`, `0 ^ 1` and `0 + 1` all equal 1, so nine of the
thirteen mutants on that line survive it. Starting from 3 separates them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar

from pydantic import BaseModel

from maistro.graph.durable_runs import (
    DurableNodeRecord,
    DurableRunRecord,
    InMemoryDurableRunStore,
    RunStatus,
    run_durable_dag,
)
from maistro.graph.durable_runs.executor import (
    _actually_spawned,
    _build_ctx,
    _checkpoint_success,
    _lift_blackboard,
    _maybe_increment_synth_depth,
    _walk,
)
from maistro.graph.durable_runs.types import NodePhase
from maistro.graph.nodes import BaseNode, NodeContext, get_node, register_node
from maistro.graph.nodes.base import NodeResult


class _In(BaseModel):
    text: str = "x"


class _Out(BaseModel):
    text: str


class _SynthOut(BaseModel):
    """Shaped like `SynthDagOut` for `_actually_spawned`'s two flags."""

    success: bool = False
    dispatched: bool = False


class _MutantEchoNode(BaseNode):
    kind: ClassVar[str] = "test.executor_mutants.echo"
    kind_category: ClassVar = "sync.transform"
    input_schema: ClassVar[type[BaseModel]] = _In
    output_schema: ClassVar[type[BaseModel]] = _Out

    async def _execute(self, inputs: _In, ctx: NodeContext) -> _Out:
        return _Out(text=inputs.text)


class _CountingNode(BaseNode):
    """Counts executions so a step budget can be asserted exactly."""

    kind: ClassVar[str] = "test.executor_mutants.counting"
    kind_category: ClassVar = "sync.transform"
    input_schema: ClassVar[type[BaseModel]] = _In
    output_schema: ClassVar[type[BaseModel]] = _Out
    runs: ClassVar[int] = 0

    async def _execute(self, inputs: _In, ctx: NodeContext) -> _Out:
        type(self).runs += 1
        return _Out(text=inputs.text)


register_node(_MutantEchoNode)
register_node(_CountingNode)


def _resolver(node_id: str, dag: dict[str, Any]) -> Any:
    for n in dag.get("nodes", []):
        if str(n.get("id")) == node_id:
            return get_node(n["kind"])()
    raise KeyError(node_id)


def _record_for(run_id: str, **overrides: Any) -> DurableRunRecord:
    now = datetime.now(UTC)
    base: dict[str, Any] = {
        "run_id": run_id,
        "dag_id": "d1",
        "dag_snapshot": {"nodes": [], "edges": []},
        "started_at": now,
        "last_step_at": now,
        "version": 1,
    }
    base.update(overrides)
    return DurableRunRecord(**base)


def _one_node_dag(kind: str = "test.executor_mutants.echo") -> dict[str, Any]:
    return {
        "id": "one",
        "nodes": [{"id": "n1", "kind": kind, "inputs": {"text": "hi"}}],
        "edges": [],
        "entry_node": "n1",
    }


def _cycle_dag(kind: str = "test.executor_mutants.counting") -> dict[str, Any]:
    return {
        "id": "cycle",
        "nodes": [
            {"id": "n1", "kind": kind, "inputs": {"text": "a"}},
            {"id": "n2", "kind": kind, "inputs": {"text": "b"}},
        ],
        "edges": [
            {"from_node": "n1", "to_node": "n2"},
            {"from_node": "n2", "to_node": "n1"},
        ],
        "entry_node": "n1",
    }


class TestAttemptCounter:
    """`"attempts": node_record.attempts + 1` -- 13 mutants, the largest cluster."""

    async def test_retrying_a_node_increments_attempts_by_exactly_one(self) -> None:
        """Kills all 13 mutants on the attempts line.

        The starting value is 3 on purpose. From 0 the arithmetic mutants
        collapse together -- `0+1`, `0|1` and `0^1` are all 1 -- so nine of
        them survive an assertion of `attempts == 1`. From 3 every mutant
        lands somewhere else: `3-1=2`, `3*1=3`, `3|1=3`, `3^1=2`, `3&1=1`,
        `3<<1=6`, `3>>1=1`, `3//1=3`, `3%1=0`, `3**1=3`, and the literal
        swaps give 5 and 3. Only `3+1` gives 4.

        The attempt counter is what a retry policy reads, so an off-by-one
        here is a run that retries forever or gives up early.
        """
        store = InMemoryDurableRunStore()
        prior = DurableNodeRecord(node_id="n1", kind="test.executor_mutants.echo", attempts=3)
        record = _record_for(
            "r-attempts",
            dag_snapshot=_one_node_dag(),
            current_node_id="n1",
            node_records=[prior],
        )
        await store.create(record)

        result = await _walk(record, store=store, node_resolver=_resolver)

        (nr,) = [n for n in result.node_records if n.node_id == "n1"]
        assert nr.attempts == 4, (
            f"expected 3 -> 4 on retry, got {nr.attempts}; the attempts line is not a plain +1"
        )

    async def test_a_fresh_node_records_its_first_attempt(self) -> None:
        """Control: the increment must also apply to a brand-new record."""
        store = InMemoryDurableRunStore()
        result = await run_durable_dag(_one_node_dag(), store=store, node_resolver=_resolver)

        (nr,) = result.node_records
        assert nr.attempts == 1


class TestStepBudget:
    """`steps = 0`, `steps += 1`, and `steps < max_steps`."""

    async def test_budget_runs_exactly_max_steps_nodes(self) -> None:
        """Kills `steps = 0` -> 1/-1, `steps += 1` -> +=2, and `<` -> `<=`.

        Asserting only that the run FAILED is not enough -- every one of those
        mutants still fails the run, just after the wrong number of steps.
        Counting executions is what separates them: `<=` runs 4, a start of 1
        runs 2, a stride of 2 runs 2, and only the correct code runs 3.
        """
        _CountingNode.runs = 0
        store = InMemoryDurableRunStore()
        record = _record_for("r-budget", dag_snapshot=_cycle_dag(), current_node_id="n1")
        await store.create(record)

        result = await _walk(record, store=store, node_resolver=_resolver, max_steps=3)

        assert result.status == RunStatus.FAILED
        assert _CountingNode.runs == 3, (
            f"expected exactly 3 node executions under max_steps=3, got {_CountingNode.runs}"
        )

    async def test_the_default_step_budget_is_256(self) -> None:
        """Kills `max_steps: int = 256` -> 257 / 255.

        The default is only observable through the failure message, and it is
        a real contract: it bounds how long a cycling DAG burns before the
        executor gives up.
        """
        _CountingNode.runs = 0
        store = InMemoryDurableRunStore()
        record = _record_for("r-default", dag_snapshot=_cycle_dag(), current_node_id="n1")
        await store.create(record)

        result = await _walk(record, store=store, node_resolver=_resolver)

        assert result.status == RunStatus.FAILED
        assert "max_steps=256" in (result.error_message or "")
        assert _CountingNode.runs == 256


class TestVersionArithmetic:
    """`record.version + 1` in the walk advance and the success checkpoint."""

    async def test_version_advances_by_one_from_an_even_base(self) -> None:
        """Kills `+ 1` -> `| 1`, `^ 1`, `<< 1` on the version lines.

        Version 2, not 1. The existing suite pins a one-node run starting at
        version 1, where `1 << 1 == 2 == 1 + 1`, so the shift mutant survives
        it. Starting at 2 the checkpoint computes 3 (`2 << 1` gives 4), and
        the advance then computes 4 from an odd base where `3 | 1 == 3` and
        `3 ^ 1 == 2` both diverge.

        The version is the optimistic-concurrency token, so a skipped or
        repeated number is a lost-update detector that has stopped detecting.
        """
        store = InMemoryDurableRunStore()
        dag = _one_node_dag()
        result = await run_durable_dag(dag, store=store, node_resolver=_resolver, run_id="r-ver2")
        # run_durable_dag starts at version 1; walk it again from 2 instead.
        record = _record_for("r-ver-even", dag_snapshot=dag, current_node_id="n1", version=2)
        store2 = InMemoryDurableRunStore()
        await store2.create(record)

        walked = await _walk(record, store=store2, node_resolver=_resolver)

        # 2 -> checkpoint 3 -> advance 4 -> completion 5.
        assert walked.version == 5, (
            f"expected 2 -> 5 across checkpoint, advance and completion, got {walked.version}"
        )
        assert result.status == RunStatus.COMPLETED

    async def test_checkpoint_success_bumps_version_from_an_even_base(self) -> None:
        """Isolates the `_checkpoint_success` bump from the walk's advance."""
        store = InMemoryDurableRunStore()
        record = _record_for("r-ckpt", current_node_id="n1", version=2)
        await store.create(record)
        nr = DurableNodeRecord(node_id="n1", kind="k")

        updated = await _checkpoint_success(
            record, "n1", nr, NodeResult(success=True, output=_Out(text="a")), store=store
        )

        assert updated.version == 3


class TestSynthDepthArithmetic:
    def test_synth_depth_increments_by_exactly_one_from_an_odd_base(self) -> None:
        """Kills `+ 1` -> `| 1` / `^ 1` on the synth_depth line.

        Base 3 for the same reason as the attempts counter: `3 | 1` is 3 and
        `3 ^ 1` is 2, while `3 + 1` is 4. This counter is the recursion budget
        that stops a self-spawning graph, so a bump that silently does nothing
        removes the cap.
        """
        record = _record_for("r-depth", blackboard_snapshot={"metadata": {"synth_depth": 3}})
        spec = {"kind": "agent.synth_dag"}

        out = _maybe_increment_synth_depth(record, spec, NodeResult(success=True, output=None))

        assert out.blackboard_snapshot["metadata"]["synth_depth"] == 4

    def test_missing_synth_depth_reads_as_zero(self) -> None:
        """Kills `.get("synth_depth", 0)` -> 1 / -1 in `_build_ctx`.

        The existing suite covers the malformed-metadata `except` branch; this
        is the ordinary path where metadata exists but carries no depth yet.
        """
        record = _record_for("r-nodepth", blackboard_snapshot={"metadata": {"other": 1}})

        ctx = _build_ctx(record, "n1")

        assert ctx.metadata["synth_depth"] == 0


class TestRunIdGeneration:
    async def test_generated_run_id_is_exactly_twelve_hex_chars(self) -> None:
        """Kills `uuid4().hex[:12]` -> `[:13]` / `[:11]`.

        The width is a storage contract; a silent change to it is how a key
        column starts colliding or overflowing.
        """
        store = InMemoryDurableRunStore()

        result = await run_durable_dag(_one_node_dag(), store=store, node_resolver=_resolver)

        assert len(result.run_id) == 12


class TestActuallySpawned:
    """`_actually_spawned` -- the `or` chain and both boolean literals."""

    def test_a_refused_synth_does_not_count_as_a_spawn(self) -> None:
        """Kills `getattr(output, "dispatched", False)` -> default True.

        A depth-cap or security refusal reports success=False and never called
        `run_graph`. Counting it would burn a recursion level for a spawn that
        never happened, so an alternate synth after a blocked one would hit the
        cap early.
        """
        result = NodeResult(success=True, output=_SynthOut(success=False, dispatched=False))

        assert _actually_spawned("agent.synth_dag", result) is False

    def test_a_dispatched_but_failed_subgraph_does_count(self) -> None:
        """The other half of the same discrimination.

        Synthesis was approved and `run_graph` ran; only the child failed. That
        is a real spawn attempt and must burn a level, or a chained retry after
        a failed child bypasses the recursion budget.
        """
        result = NodeResult(success=True, output=_SynthOut(success=False, dispatched=True))

        assert _actually_spawned("agent.synth_dag", result) is True

    def test_an_output_without_the_flags_defaults_to_spawned(self) -> None:
        """Kills `getattr(output, "success", True)` -> default False."""
        result = NodeResult(success=True, output=_Out(text='x'))

        assert _actually_spawned("agent.synth_dag", result) is True

    def test_a_non_synth_kind_always_counts(self) -> None:
        """Kills the trailing `return True` -> `return False`.

        `agent.spawn_harness` only reaches this check on a resumed, already
        completed external invocation, so it counts unconditionally.
        """
        result = NodeResult(success=True, output=_SynthOut(success=False, dispatched=False))

        assert _actually_spawned("agent.spawn_harness", result) is True


class _Blackboard:
    def __init__(self, metadata: dict[str, Any], annotations: Any) -> None:
        self.metadata = metadata
        self.node_annotations = annotations


class _NoMetadataBlackboard:
    """A blackboard-shaped object that never got a metadata attribute."""


class TestBlackboardLift:
    def test_annotations_are_lifted_when_present(self) -> None:
        """Kills `if annotations is not None` -> `is None` / `not (...)`,
        and `dict(annotations or {})` -> `and {}`."""
        record = _record_for("r-lift", blackboard_snapshot={"metadata": {}})
        ctx = _build_ctx(record, "n1")
        ctx.blackboard = _Blackboard({"k": "v"}, {"n1": "hi"})

        out = _lift_blackboard(record, ctx)

        assert out.blackboard_snapshot["node_annotations"] == {"n1": "hi"}
        assert out.blackboard_snapshot["metadata"] == {"k": "v"}

    def test_absent_annotations_leave_the_snapshot_key_alone(self) -> None:
        """Control for the branch above: None must not overwrite."""
        record = _record_for(
            "r-lift-none",
            blackboard_snapshot={"metadata": {}, "node_annotations": {"keep": 1}},
        )
        ctx = _build_ctx(record, "n1")
        ctx.blackboard = _Blackboard({"k": "v"}, None)

        out = _lift_blackboard(record, ctx)

        assert out.blackboard_snapshot["node_annotations"] == {"keep": 1}

    def test_a_blackboard_without_metadata_is_ignored(self) -> None:
        """Kills `bb is None or not hasattr(...)` -> `and`.

        With `and`, an object that is not None but has no `metadata` attribute
        falls through to `getattr(bb, "metadata")` handling instead of
        returning early -- the guard stops guarding the case it names.
        """
        record = _record_for("r-nometa", blackboard_snapshot={"metadata": {"keep": 1}})
        ctx = _build_ctx(record, "n1")
        ctx.blackboard = _NoMetadataBlackboard()

        out = _lift_blackboard(record, ctx)

        assert out.blackboard_snapshot["metadata"] == {"keep": 1}

    def test_existing_metadata_survives_a_lift(self) -> None:
        """Kills `dict(record.blackboard_snapshot or {})` -> `and {}`.

        With `and`, a populated snapshot yields `{}` and every key outside
        metadata -- task_objective included -- is dropped on the next step.
        """
        record = _record_for(
            "r-keep",
            blackboard_snapshot={"task_objective": "build it", "metadata": {"a": 1}},
        )
        ctx = _build_ctx(record, "n1")
        ctx.blackboard = _Blackboard({"a": 1, "b": 2}, None)

        out = _lift_blackboard(record, ctx)

        assert out.blackboard_snapshot["task_objective"] == "build it"


class TestBuildCtxFallbacks:
    def test_blackboard_fields_are_carried_from_the_snapshot(self) -> None:
        """Kills the `or` -> `and` swaps on task_objective, workspace and
        node_annotations in `_build_ctx`.

        With `and`, a populated value collapses to the empty fallback, so a
        resumed run silently loses the objective it was given.
        """
        record = _record_for(
            "r-ctx",
            blackboard_snapshot={
                "task_objective": "ship it",
                "workspace": "/tmp/ws",
                "node_annotations": {"n1": "seen"},
                "metadata": {},
            },
        )

        ctx = _build_ctx(record, "n1")

        assert ctx.blackboard is not None
        assert ctx.blackboard.task_objective == "ship it"
        assert ctx.blackboard.workspace == "/tmp/ws"
        assert ctx.blackboard.node_annotations == {"n1": "seen"}

    def test_synth_depth_metadata_is_carried(self) -> None:
        """Kills `dict(snapshot.get("metadata") or {})` -> `and {}`."""
        record = _record_for("r-ctx2", blackboard_snapshot={"metadata": {"synth_depth": 2}})

        ctx = _build_ctx(record, "n1")

        assert ctx.metadata["synth_depth"] == 2


class TestDagIdentityFallbacks:
    async def test_dag_id_prefers_id_over_name(self) -> None:
        """Kills `dag.get("id") or dag.get("name") or "anonymous"` -> `and`.

        With `and`, a DAG carrying an id but no name resolves to `None` and is
        persisted as the string "None" -- every such run collapses into one
        bogus dag_id.
        """
        store = InMemoryDurableRunStore()
        dag = _one_node_dag()
        dag.pop("name", None)

        result = await run_durable_dag(dag, store=store, node_resolver=_resolver)

        assert result.dag_id == "one"

    async def test_dag_id_falls_back_to_anonymous(self) -> None:
        """The tail of the same chain, with neither id nor name."""
        store = InMemoryDurableRunStore()
        dag = _one_node_dag()
        dag.pop("id")

        result = await run_durable_dag(dag, store=store, node_resolver=_resolver)

        assert result.dag_id == "anonymous"

    async def test_task_objective_defaults_to_empty_string(self) -> None:
        """Kills `str(dag.get("name") or "")` -> `and`, which yields "None"."""
        store = InMemoryDurableRunStore()
        dag = _one_node_dag()

        result = await run_durable_dag(dag, store=store, node_resolver=_resolver)

        assert result.blackboard_snapshot["task_objective"] == ""


class TestCheckpointOutput:
    async def test_a_plain_dict_output_is_stored_as_given(self) -> None:
        """Kills `(output or None)` -> `(output and None)`.

        With `and`, every non-model output becomes None and the node's result
        is lost from the record -- which is also what the next node reads as
        its inputs.
        """
        store = InMemoryDurableRunStore()
        record = _record_for("r-out", current_node_id="n1", version=1)
        await store.create(record)
        nr = DurableNodeRecord(node_id="n1", kind="k")

        # `model_construct`, not `NodeResult(...)`, and the reason is a real
        # hazard rather than test convenience. `output` is typed
        # `BaseModel | dict[str, Any] | None`, and pydantic validates a plain
        # dict against the *bare* `BaseModel` arm first -- it succeeds, so the
        # dict is silently replaced by a bare BaseModel instance. Then
        # `isinstance(output, BaseModel)` is True and `output.model_dump()`
        # raises PydanticUserError. Validating here would therefore never
        # reach the `else` branch this test exists to pin.
        result = NodeResult.model_construct(success=True, output={"answer": 42})
        updated = await _checkpoint_success(record, "n1", nr, result, store=store)

        (stored,) = updated.node_records
        assert stored.output == {"answer": 42}
        assert stored.phase == NodePhase.COMPLETED
