from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any

from maistro.graph.types import (
    AgentRole,
    CodeOutput,
    DEFAULT_SYSTEM_PROMPTS,
    GraphBlackboard,
    GraphConfig,
    GraphNodeResult,
    GraphTask,
    HyperagentOutput,
    JSON_OUTPUT_SCHEMAS,
    LLMProviderError,
    OUTPUT_TYPES,
    NodeConfig,
    PlanOutput,
    ReviewOutput,
)

logger = logging.getLogger(__name__)

_MISSING = object()

_NodeOutput = PlanOutput | CodeOutput | ReviewOutput

_RETRYABLE_MESSAGES = {"rate limit", "timeout", "502", "503", "504", "connection"}


class _CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._state = "closed"

    def allow_request(self) -> bool:
        if self._state == "closed":
            return True
        if self._state == "open":
            if time.monotonic() - self._last_failure_time > self._recovery_timeout:
                self._state = "half_open"
                return True
            return False
        return True

    def record_success(self) -> None:
        self._failure_count = 0
        self._state = "closed"

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self._failure_threshold:
            self._state = "open"


_circuit = _CircuitBreaker()


def _is_retryable(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(k in msg for k in _RETRYABLE_MESSAGES) or isinstance(
        exc, (TimeoutError, asyncio.TimeoutError, ConnectionError)
    )


def _strip_json_block(text: str) -> str:
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    return m.group(1).strip() if m else text.strip()


def _parse_json_output(role: AgentRole, raw: str) -> _NodeOutput:
    cleaned = _strip_json_block(raw)
    data = json.loads(cleaned)
    output_type = OUTPUT_TYPES.get(role, PlanOutput)
    return output_type.model_validate(data)  # type: ignore[return-value]


def _get_system_prompt(role: AgentRole, node_config: NodeConfig | None = None) -> str:
    base = (
        (node_config.system_prompt if node_config and node_config.system_prompt else None)
        or DEFAULT_SYSTEM_PROMPTS.get(role, "")
    )
    schema_suffix = JSON_OUTPUT_SCHEMAS.get(role, "")
    return base + schema_suffix


def _get_temperature(
    role: AgentRole,
    node_config: NodeConfig | None = None,
    default: float | None = None,
) -> float | None:
    if node_config and node_config.temperature is not None:
        return node_config.temperature
    return default


def _constraints_text(constraints: list[str]) -> str:
    return "\n".join(f"- {c}" for c in constraints) if constraints else "None"


def _planner_prompt(task: GraphTask) -> str:
    return (
        f"Task: {task.description}\n\n"
        f"Workspace: {task.workspace}\n"
        f"Constraints:\n{_constraints_text(task.constraints)}"
    )


def _coder_prompt(task: GraphTask, plan: PlanOutput) -> str:
    subtasks = "\n".join(
        f"{i + 1}. {s.title}: {s.description}" for i, s in enumerate(plan.subtasks)
    )
    return (
        f"Task: {task.description}\n\n"
        f"Workspace: {task.workspace}\n\n"
        f"Plan: {plan.summary}\n\n"
        f"Subtasks:\n{subtasks}"
    )


def _reviewer_prompt(task: GraphTask, plan: PlanOutput | None, code: CodeOutput) -> str:
    plan_summary = plan.summary if plan else "N/A"
    files = ", ".join(code.files_changed) or "none"
    return (
        f"Task: {task.description}\n\n"
        f"Plan summary: {plan_summary}\n"
        f"Files changed: {files}\n"
        f"Description: {code.description}\n"
        f"Tests added: {code.tests_added}"
    )


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


def _build_node_prompt(
    task: GraphTask,
    role: AgentRole,
    plan: PlanOutput | None,
    code: CodeOutput | None,
    review: ReviewOutput | None,
    blackboard: GraphBlackboard | None = None,
) -> str:
    prefix = _blackboard_prefix(role, blackboard)

    if role == AgentRole.PLANNER:
        return prefix + _planner_prompt(task)
    if role == AgentRole.CODER:
        return prefix + (_coder_prompt(task, plan) if plan else _planner_prompt(task))
    if role == AgentRole.REVIEWER:
        if code is None:
            return prefix + f"Task: {task.description}\n\nNo code output available to review."
        return prefix + _reviewer_prompt(task, plan, code)
    return prefix + f"Task: {task.description}\nWorkspace: {task.workspace}"


def _score_output(role: AgentRole, output: _NodeOutput) -> float:
    if isinstance(output, ReviewOutput):
        return output.score
    if isinstance(output, PlanOutput):
        return float(len(output.subtasks))
    if isinstance(output, CodeOutput):
        return float(len(output.files_changed)) + (2.0 if output.tests_added else 0.0)
    return 0.0


_OPERATORS = [" is not ", " is ", " >= ", " <= ", " != ", " == ", " > ", " < "]


def _resolve_path(
    path: str,
    plan: PlanOutput | None,
    code: CodeOutput | None,
    review: ReviewOutput | None,
) -> object:
    parts = path.split(".", 1)
    if len(parts) != 2:
        return _MISSING
    namespace, field = parts
    obj: object = {"plan": plan, "code": code, "review": review}.get(namespace)
    if obj is None:
        return _MISSING
    return getattr(obj, field, _MISSING)


def _parse_rhs(s: str) -> object:
    if s == "True":
        return True
    if s == "False":
        return False
    if s == "None":
        return None
    try:
        return float(s) if "." in s else int(s)
    except ValueError:
        return s.strip("\"'")


def _compare(lhs: object, op: str, rhs: object) -> bool:
    stripped = op.strip()
    if stripped in ("is", "=="):
        return lhs == rhs
    if stripped in ("is not", "!="):
        return lhs != rhs
    try:
        if stripped == "<":
            return bool(lhs < rhs)  # type: ignore[operator]
        if stripped == ">":
            return bool(lhs > rhs)  # type: ignore[operator]
        if stripped == "<=":
            return bool(lhs <= rhs)  # type: ignore[operator]
        if stripped == ">=":
            return bool(lhs >= rhs)  # type: ignore[operator]
    except TypeError:
        return False
    return False


def evaluate_condition(
    condition: str,
    plan: PlanOutput | None,
    code: CodeOutput | None,
    review: ReviewOutput | None,
) -> bool:
    for op in _OPERATORS:
        if op in condition:
            lhs_str, rhs_str = condition.split(op, 1)
            lhs = _resolve_path(lhs_str.strip(), plan, code, review)
            if lhs is _MISSING:
                return False
            return _compare(lhs, op, _parse_rhs(rhs_str.strip()))
    return False


def _next_nodes(
    config: GraphConfig,
    current: AgentRole,
    plan: PlanOutput | None,
    code: CodeOutput | None,
    review: ReviewOutput | None,
) -> list[AgentRole]:
    sequential: AgentRole | None = None
    parallel: list[AgentRole] = []

    for edge in config.edges:
        if edge.from_role != current:
            continue
        if edge.to_role is None:
            continue
        cond_met = edge.condition is None or evaluate_condition(
            edge.condition, plan, code, review
        )
        if not cond_met:
            continue
        if edge.parallel:
            parallel.append(edge.to_role)
        elif sequential is None:
            sequential = edge.to_role

    result = [] if sequential is None else [sequential]
    result.extend(parallel)
    return result


async def _dispatch_node_single(
    role: AgentRole,
    system_prompt: str,
    user_prompt: str,
    llm_call: Callable[..., Awaitable[str]],
    model: str,
    temperature: float | None = None,
    max_retries: int = 3,
    timeout: float = 120.0,
    initial_backoff: float = 1.0,
) -> tuple[_NodeOutput, int]:
    if not _circuit.allow_request():
        raise LLMProviderError("Circuit breaker is open")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    last_exc: Exception | None = None

    for attempt in range(max_retries):
        try:
            raw = await asyncio.wait_for(
                llm_call(messages, model=model, temperature=temperature),
                timeout=timeout,
            )
            _circuit.record_success()
            typed = _parse_json_output(role, raw)
            return typed, 0

        except Exception as exc:
            if _is_retryable(exc):
                last_exc = exc
                _circuit.record_failure()
                logger.warning(
                    "graph_node_transient_error",
                    extra={"role": role.value, "attempt": attempt + 1, "error": str(exc)},
                )
                if attempt < max_retries - 1:
                    delay = initial_backoff * (2**attempt) + random.uniform(0, 1)
                    await asyncio.sleep(delay)
            else:
                _circuit.record_failure()
                raise

    raise LLMProviderError(
        f"Node {role} failed after {max_retries} retries: {last_exc}"
    )


async def _dispatch_node_beam(
    role: AgentRole,
    system_prompt: str,
    user_prompt: str,
    llm_call: Callable[..., Awaitable[str]],
    model: str,
    temperature: float | None = None,
    max_retries: int = 3,
    timeout: float = 120.0,
    initial_backoff: float = 1.0,
    parallel_generations: int = 1,
) -> tuple[_NodeOutput, int, list[str], int]:
    if parallel_generations == 1:
        output, tokens = await _dispatch_node_single(
            role,
            system_prompt,
            user_prompt,
            llm_call,
            model,
            temperature,
            max_retries,
            timeout,
            initial_backoff,
        )
        return output, tokens, [str(output)[:500]], 0

    raw = await asyncio.gather(
        *[
            _dispatch_node_single(
                role,
                system_prompt,
                user_prompt,
                llm_call,
                model,
                temperature,
                max_retries,
                timeout,
                initial_backoff,
            )
            for _ in range(parallel_generations)
        ],
        return_exceptions=True,
    )

    successes: list[tuple[_NodeOutput, int]] = [
        item for item in raw if not isinstance(item, BaseException)
    ]

    if not successes:
        for item in raw:
            if isinstance(item, BaseException):
                raise item

    scored = sorted(
        range(len(successes)),
        key=lambda i: _score_output(role, successes[i][0]),
        reverse=True,
    )
    best_idx = scored[0]
    best_output, _ = successes[best_idx]
    total_tokens = sum(t for _, t in successes)
    candidates_str = [str(o)[:500] for o, _ in successes]

    logger.info(
        "graph_beam_selected",
        extra={
            "role": role.value,
            "n_beams": parallel_generations,
            "n_succeeded": len(successes),
            "selected": best_idx,
        },
    )

    return best_output, total_tokens, candidates_str, best_idx


def _update_state(
    active: list[AgentRole],
    batch: list[Any],
    plan: PlanOutput | None,
    code: CodeOutput | None,
    review: ReviewOutput | None,
) -> tuple[PlanOutput | None, CodeOutput | None, ReviewOutput | None]:
    for role, result in zip(active, batch, strict=True):
        if isinstance(result, BaseException):
            continue
        typed_output, _tokens, _candidates, _selected = result
        if role == AgentRole.PLANNER and isinstance(typed_output, PlanOutput):
            plan = typed_output
        elif role == AgentRole.CODER and isinstance(typed_output, CodeOutput):
            code = typed_output
        elif role == AgentRole.REVIEWER and isinstance(typed_output, ReviewOutput):
            review = typed_output
    return plan, code, review


async def _route_and_record(
    active: list[AgentRole],
    batch: list[Any],
    plan: PlanOutput | None,
    code: CodeOutput | None,
    review: ReviewOutput | None,
    config: GraphConfig,
    cycle: int,
    parallel_group: int | None,
) -> tuple[list[AgentRole], list[GraphNodeResult]]:
    seen_next: set[AgentRole] = set()
    next_active: list[AgentRole] = []
    new_results: list[GraphNodeResult] = []

    for role, result in zip(active, batch, strict=True):
        node_success = not isinstance(result, BaseException)

        total_tokens: int = 0
        selected: int = 0
        candidates: list[str] = []
        role_next: list[AgentRole] = []

        if node_success:
            _typed_output, total_tokens, candidates, selected = result
            role_next = _next_nodes(config, role, plan, code, review)
            for nxt in role_next:
                if nxt not in seen_next:
                    next_active.append(nxt)
                    seen_next.add(nxt)
        else:
            logger.error(
                "graph_node_failed",
                extra={"role": role.value, "cycle": cycle, "error": str(result)},
            )

        new_results.append(
            GraphNodeResult(
                role=role,
                success=node_success,
                output=candidates[selected] if candidates else f"error: {result}",
                tokens_used=total_tokens,
                next_nodes=role_next,
                candidates=candidates,
                selected_candidate=selected,
                parallel_group=parallel_group,
            )
        )

    return next_active, new_results


def _build_final_answer(review: ReviewOutput | None, plan: PlanOutput | None) -> str:
    if review and review.approved:
        return f"Task completed. Review score: {review.score}/10."
    if review:
        issues = "; ".join(review.issues[:2]) if review.issues else "unspecified issues"
        return f"Review not approved (score: {review.score}/10): {issues}"
    if plan:
        return plan.summary
    return ""


async def run_graph(
    task: GraphTask,
    llm_call: Callable[..., Awaitable[str]],
    *,
    model: str = "default",
    max_retries: int = 3,
    timeout: float = 120.0,
    initial_backoff: float = 1.0,
    parallel_generations: int = 1,
    temperature: float | None = None,
    run_id: str | None = None,
) -> HyperagentOutput:
    config = task.graph_config or GraphConfig(
        nodes=[AgentRole.PLANNER, AgentRole.CODER, AgentRole.REVIEWER]
    )

    logger.info(
        "graph_start",
        extra={
            "hyperagent": config.hyperagent.value,
            "nodes": [n.value for n in config.nodes],
            "entry": config.entry.value,
            "max_cycles": config.max_cycles,
            "model": model,
        },
    )

    blackboard = GraphBlackboard(
        task_objective=task.description,
        workspace=task.workspace,
    )

    if config.run_scout:
        from maistro.graph.scout import run_scout

        blackboard = await run_scout(
            task,
            blackboard,
            llm_call,
            model=model,
            temperature=temperature,
            timeout=timeout,
            max_retries=max_retries,
        )

    node_results: list[GraphNodeResult] = []
    plan: PlanOutput | None = None
    code: CodeOutput | None = None
    review: ReviewOutput | None = None

    active: list[AgentRole] = [config.entry]
    cycle = 0

    while active and cycle < config.max_cycles:
        logger.info(
            "graph_cycle_start",
            extra={"cycle": cycle, "active_nodes": [a.value for a in active]},
        )

        batch: list[Any] = await asyncio.gather(
            *[
                _dispatch_node_beam(
                    role,
                    _get_system_prompt(role, config.node_configs.get(role)),
                    _build_node_prompt(task, role, plan, code, review, blackboard),
                    llm_call,
                    model,
                    _get_temperature(role, config.node_configs.get(role), temperature),
                    max_retries,
                    timeout,
                    initial_backoff,
                    parallel_generations,
                )
                for role in active
            ],
            return_exceptions=True,
        )

        parallel_group = cycle if len(active) > 1 else None
        plan, code, review = _update_state(active, batch, plan, code, review)
        active, new_results = await _route_and_record(
            active, batch, plan, code, review, config, cycle, parallel_group
        )
        node_results.extend(new_results)
        cycle += 1

    success = bool(node_results) and all(r.success for r in node_results)
    final_answer = _build_final_answer(review, plan)

    result = HyperagentOutput(
        plan=plan,
        code=code,
        review=review,
        final_answer=final_answer,
        success=success,
        graph_config=config,
        node_results=node_results,
        total_cycles=cycle,
        blackboard=blackboard,
    )

    logger.info(
        "graph_complete",
        extra={
            "success": success,
            "total_cycles": cycle,
            "review_score": review.score if review else None,
        },
    )

    return result
