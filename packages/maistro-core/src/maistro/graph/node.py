from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import structlog

from maistro.agents.circuit_breaker import CircuitBreaker
from maistro.graph.events import (
    node_completed,
    node_failed,
    node_retrying,
    node_started,
)
from maistro.graph.phases import NodePhase
from maistro.graph.strategy import NodeStrategy, get_strategy
from maistro.graph.types import (
    DEFAULT_SYSTEM_PROMPTS,
    JSON_OUTPUT_SCHEMAS,
    AgentRole,
    GraphBlackboard,
    GraphNodeResult,
    NodeConfig,
)
from maistro.resilience.backoff import BackoffConfig, compute_backoff, jittered_backoff
from maistro.resilience.classifier import ClassifiedError, classify_error

logger = structlog.get_logger()


def _strip_json_block(text: str) -> str:
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    return m.group(1).strip() if m else text.strip()


def _build_system_prompt(role: AgentRole, node_config: NodeConfig | None = None) -> str:
    base = (
        (node_config.system_prompt if node_config and node_config.system_prompt else None)
        or DEFAULT_SYSTEM_PROMPTS.get(role, "")
    )
    schema_suffix = JSON_OUTPUT_SCHEMAS.get(role, "")
    return base + schema_suffix


def _blackboard_prefix(role: AgentRole, bb: GraphBlackboard | None) -> str:
    if bb is None:
        return ""
    lines: list[str] = [f"## Pipeline Objective\n{bb.task_objective}\n"]

    if bb.scout_context:
        sc = bb.scout_context
        if sc.relevant_files:
            lines.append("## Workspace Briefing (from SCOUT)")
            lines.append(f"Relevant files: {', '.join(sc.relevant_files[:10])}")
        if sc.patterns:
            lines.append(f"Patterns to follow: {sc.patterns}")
        if sc.similar_implementations:
            lines.append(
                f"Similar existing implementations: {', '.join(sc.similar_implementations[:5])}"
            )
        if sc.raw_findings:
            lines.append(f"Scout summary: {sc.raw_findings}")

    if bb.tool_evaluation and role == AgentRole.REVIEWER:
        te = bb.tool_evaluation
        lines.append(
            f"## Sandbox Results\n"
            f"Tests: {te.tests_passed} passed / {te.tests_failed} failed "
            f"(pass rate {te.pass_rate:.0%})\n"
            f"Lint errors: {len(te.lint_errors)}, Type errors: {len(te.type_errors)}\n"
            f"{te.test_output[:400]}\n"
        )

    annotation = bb.node_annotations.get(role.value)
    if annotation:
        lines.append(f"## Hyperagent Note for {role.upper()}\n{annotation}\n")

    if bb.iteration > 0:
        lines.append(f"## Optimization Context\nIteration {bb.iteration}.")

    return "\n".join(lines) + "\n---\n" if len(lines) > 1 else ""


@dataclass
class BeamCandidate:
    index: int
    raw_response: str
    parsed_output: Any | None = None
    parse_error: str | None = None
    score: float = 0.0
    tokens_used: int = 0
    duration_s: float = 0.0
    error: Exception | None = None


class IterationBudget:
    def __init__(self, max_iterations: int) -> None:
        self._max = max_iterations
        self._consumed = 0

    def consume(self, count: int = 1) -> bool:
        if self._consumed + count > self._max:
            return False
        self._consumed += count
        return True

    @property
    def remaining(self) -> int:
        return max(0, self._max - self._consumed)

    @property
    def exhausted(self) -> bool:
        return self._consumed >= self._max

    @property
    def max_iterations(self) -> int:
        return self._max

    @property
    def consumed(self) -> int:
        return self._consumed


@dataclass
class NodeRun:
    run_id: str
    node_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    role: AgentRole = AgentRole.PLANNER
    strategy: NodeStrategy | None = None
    beam_width: int = 1

    model: str = "default"
    temperature: float | None = None
    system_prompt: str = ""
    user_prompt: str = ""
    blackboard_snapshot: GraphBlackboard | None = None
    node_config: NodeConfig | None = None

    phase: NodePhase = NodePhase.PENDING
    phase_log: list[tuple[NodePhase, float]] = field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 3

    started_at: float | None = None
    completed_at: float | None = None
    duration_s: float | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    error_classifications: list[ClassifiedError] = field(default_factory=list)

    beam_candidates: list[BeamCandidate] = field(default_factory=list)
    beam_selected: int = -1

    raw_response: str | None = None
    parsed_output: Any | None = None
    parse_error: str | None = None
    score: float = 0.0
    classified_error: ClassifiedError | None = None

    circuit: CircuitBreaker = field(default_factory=lambda: CircuitBreaker(name="node"))
    _cancel_requested: bool = field(default=False, repr=False)

    _emit_event: Any = field(default=None, repr=False)

    def _transition(self, new_phase: NodePhase) -> None:
        now = time.monotonic()
        self.phase_log.append((self.phase, now))
        old = self.phase
        self.phase = new_phase
        logger.debug(
            "node_phase_transition",
            node_id=self.node_id,
            role=self.role.value,
            old=old.value,
            new=new_phase.value,
        )

    def cancel(self) -> None:
        self._cancel_requested = True

    async def execute(
        self,
        llm_call: Callable[..., Awaitable[str]],
        timeout: float = 120.0,
        backoff_config: BackoffConfig | None = None,
        iteration_budget: IterationBudget | None = None,
    ) -> None:
        if self.phase not in (NodePhase.PENDING,):
            return

        if self.strategy is None:
            self.strategy = get_strategy(self.role)

        backoff_config = backoff_config or BackoffConfig()
        self._transition(NodePhase.RUNNING)
        self.started_at = time.monotonic()

        if self._emit_event:
            await self._emit_event(node_started(
                self.run_id, self.node_id, self.role.value,
            ))

        try:
            if self.beam_width > 1:
                await self._execute_beam(llm_call, timeout, backoff_config, iteration_budget)
            else:
                await self._execute_single(llm_call, timeout, backoff_config, iteration_budget)
        except asyncio.CancelledError:
            self._transition(NodePhase.CANCELLED)
            self.completed_at = time.monotonic()
            self.duration_s = self.completed_at - (self.started_at or self.completed_at)
            if self._emit_event:
                await self._emit_event(node_failed(
                    self.run_id, self.node_id, self.role.value, reason="cancelled",
                ))
            return
        except Exception as exc:
            self._finish_failure(exc)
            return

        self.completed_at = time.monotonic()
        self.duration_s = self.completed_at - (self.started_at or self.completed_at)

    async def _execute_single(
        self,
        llm_call: Callable[..., Awaitable[str]],
        timeout: float,
        backoff_config: BackoffConfig,
        iteration_budget: IterationBudget | None,
    ) -> None:
        assert self.strategy is not None
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": self.user_prompt},
        ]
        last_exc: Exception | None = None

        for attempt in range(self.max_retries):
            if self._cancel_requested:
                self._transition(NodePhase.CANCELLED)
                return

            if not self.circuit.allow_request():
                self._finish_failure(LLMProviderError("Circuit breaker open for node"))
                return

            if iteration_budget is not None and not iteration_budget.consume():
                self._finish_failure(LLMProviderError("Iteration budget exhausted"))
                return

            try:
                schema = self.strategy.output_type.model_json_schema() if self.strategy and hasattr(self.strategy, 'output_type') else None
                raw = await asyncio.wait_for(
                    llm_call(messages, model=self.model, temperature=self.temperature, response_schema=schema),
                    timeout=timeout,
                )
                self.circuit.record_success()
                self.raw_response = raw

                parsed = self._parse_output(raw)
                if parsed is None:
                    self.circuit.record_failure()
                    last_exc = LLMProviderError(f"Failed to parse output for {self.role.value}")
                    if attempt < self.max_retries - 1:
                        self._transition(NodePhase.RETRYING)
                        self.retry_count += 1
                        delay = jittered_backoff(attempt, base_delay=0.1, max_delay=1.0)
                        await asyncio.sleep(delay)
                        self._transition(NodePhase.RUNNING)
                    continue

                self.parsed_output = parsed
                self.score = self.strategy.score_output(parsed)
                self._transition(NodePhase.SUCCEEDED)

                if self._emit_event:
                    await self._emit_event(node_completed(
                        self.run_id, self.node_id, self.role.value,
                        score=self.score,
                    ))
                return

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                classified = classify_error(
                    exc, provider=self.model, model=self.model,
                )
                self.error_classifications.append(classified)
                last_exc = exc
                self.circuit.record_failure()

                if classified.retryable and attempt < self.max_retries - 1:
                    self._transition(NodePhase.RETRYING)
                    self.retry_count += 1
                    delay = compute_backoff(attempt + 1, backoff_config, retry_after=classified.retry_after_seconds)
                    if delay < 0:
                        self._finish_failure(exc, classified)
                        return
                    logger.warning(
                        "node_retry",
                        node_id=self.node_id,
                        role=self.role.value,
                        attempt=attempt + 1,
                        category=classified.category.value,
                        delay=delay,
                    )
                    if self._emit_event:
                        await self._emit_event(node_retrying(
                            self.run_id, self.node_id, self.role.value,
                            attempt=attempt + 1,
                            category=classified.category.value,
                        ))
                    await asyncio.sleep(delay)
                    self._transition(NodePhase.RUNNING)
                else:
                    self._finish_failure(exc, classified)
                    return

        if last_exc is not None:
            self._finish_failure(last_exc)

    async def _execute_beam(
        self,
        llm_call: Callable[..., Awaitable[str]],
        timeout: float,
        backoff_config: BackoffConfig,
        iteration_budget: IterationBudget | None,
    ) -> None:
        assert self.strategy is not None
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": self.user_prompt},
        ]

        results = await asyncio.gather(
            *[
                self._beam_attempt(i, messages, llm_call, timeout, backoff_config, iteration_budget)
                for i in range(self.beam_width)
            ],
            return_exceptions=True,
        )

        candidates: list[BeamCandidate] = []
        for i, result in enumerate(results):
            if isinstance(result, BeamCandidate):
                candidates.append(result)
            elif isinstance(result, (Exception, BaseException)):
                candidates.append(BeamCandidate(
                    index=i, raw_response="", error=Exception(str(result)),
                ))

        self.beam_candidates = candidates

        scored = [c for c in candidates if c.parsed_output is not None and c.error is None]
        if not scored:
            first_error = next((c.error for c in candidates if c.error), None)
            if first_error:
                self._finish_failure(first_error)
            return

        best = max(scored, key=lambda c: c.score)
        self.beam_selected = best.index
        self.raw_response = best.raw_response
        self.parsed_output = best.parsed_output
        self.score = best.score
        self.tokens_in = sum(c.tokens_used for c in candidates)
        self._transition(NodePhase.SUCCEEDED)

        if self._emit_event:
            await self._emit_event(node_completed(
                self.run_id, self.node_id, self.role.value,
                score=self.score,
                beam_width=self.beam_width,
                beam_succeeded=len(scored),
            ))

    async def _beam_attempt(
        self,
        index: int,
        messages: list[dict[str, str]],
        llm_call: Callable[..., Awaitable[str]],
        timeout: float,
        backoff_config: BackoffConfig,
        iteration_budget: IterationBudget | None,
    ) -> BeamCandidate:
        assert self.strategy is not None
        start = time.monotonic()
        if iteration_budget is not None and not iteration_budget.consume():
            raise LLMProviderError("Iteration budget exhausted")

        raw = await asyncio.wait_for(
            llm_call(messages, model=self.model, temperature=self.temperature),
            timeout=timeout,
        )
        elapsed = time.monotonic() - start

        parsed = self._parse_output_raw(raw)
        if parsed is None:
            return BeamCandidate(
                index=index, raw_response=raw, parse_error="failed to parse",
                duration_s=elapsed,
            )

        score = self.strategy.score_output(parsed)
        return BeamCandidate(
            index=index, raw_response=raw, parsed_output=parsed,
            score=score, duration_s=elapsed,
        )

    def _parse_output(self, raw: str) -> Any | None:
        result = self._parse_output_raw(raw)
        if result is None:
            self.parse_error = "failed to parse LLM output"
        return result

    def _parse_output_raw(self, raw: str) -> Any | None:
        if self.strategy is None:
            return None
        try:
            cleaned = _strip_json_block(raw)
            data = json.loads(cleaned)
            return self.strategy.output_type.model_validate(data)
        except (json.JSONDecodeError, Exception) as exc:
            logger.debug("node_parse_error", node_id=self.node_id, error=str(exc))
            return None

    def _finish_failure(
        self,
        exc: Exception,
        classified: ClassifiedError | None = None,
    ) -> None:
        if classified is None:
            classified = classify_error(exc, provider=self.model, model=self.model)
        self.classified_error = classified
        self._transition(NodePhase.FAILED)
        if self.completed_at is None:
            self.completed_at = time.monotonic()
            self.duration_s = self.completed_at - (self.started_at or self.completed_at)

        if self._emit_event:
            try:
                coro = self._emit_event(node_failed(
                    self.run_id, self.node_id, self.role.value,
                    category=classified.category.value,
                    error=str(exc)[:200],
                ))
                import asyncio as _aio
                loop = _aio.get_running_loop()
                loop.create_task(coro)
            except Exception as _exc:
                _log_b110 = __import__('structlog').get_logger('maistro.graph.node')
                _log_b110.warning('error_swallowed', error=str(_exc), file='packages/maistro-core/src/maistro/graph/node.py', line=456)
                pass

    def to_result(self) -> GraphNodeResult:
        success = self.phase == NodePhase.SUCCEEDED
        output_str = ""
        if success and self.parsed_output is not None:
            output_str = str(self.parsed_output)[:500]
        elif self.classified_error is not None:
            output_str = f"error: {self.classified_error.category.value} — {self.classified_error.message[:200]}"
        elif self.parse_error:
            output_str = f"parse_error: {self.parse_error}"
        else:
            output_str = f"error: phase={self.phase.value}"

        candidates_str: list[str] = []
        selected = 0
        if self.beam_candidates:
            candidates_str = [c.raw_response[:500] for c in self.beam_candidates]
            selected = self.beam_selected if self.beam_selected >= 0 else 0

        return GraphNodeResult(
            role=self.role,
            success=success,
            output=output_str,
            tokens_used=self.tokens_in + self.tokens_out,
            next_nodes=[],
            candidates=candidates_str,
            selected_candidate=selected,
        )


class LLMProviderError(Exception):
    pass
