from __future__ import annotations

import time
from typing import Any

from ..types import EvalResult, PipelineGenome
from .executable_terminal import (
    HOLDOUT_TASKS,
    TRAINING_TASKS,
    build_executable_terminal_prompt,
    evaluate_executable_terminal_response,
)
from .prompt_builder import build_messages, build_model_config, build_system_prompt

_TASKS = TRAINING_TASKS + HOLDOUT_TASKS


async def run_terminalbench(genome: PipelineGenome, llm_call: Any) -> EvalResult:
    """Score terminal-task responses by actually verifying end filesystem state.

    Proxy-tier (SPEC-202): a small handcrafted task set, not the official
    Terminal-Bench corpus. But the check is genuine — each task defines
    initial files and an exact expected end state (including "no unexpected
    files"), verified in a scratch tempdir
    (``executable_terminal.evaluate_executable_terminal_response``), not
    scored by matching keywords against a proposed shell command. This
    replaces the previous ``TERMINALBENCH_SAMPLES`` keyword-matcher, whose
    samples had no verifiable state at all and included tasks (kill a live
    process, curl a URL, `docker ps`) that cannot run in this harness's
    network-disabled, container-free execution model anyway.
    """
    if llm_call is None:
        raise ValueError(
            "run_terminalbench requires an llm_call — there is no stub/heuristic "
            "fallback (SPEC-202: never produce a fabricated score)"
        )

    start = time.monotonic()
    system_prompt = build_system_prompt(genome)
    model_config = build_model_config(genome)

    total_score = 0.0
    evaluated = 0
    total_cost = 0.0
    failures: list[dict[str, Any]] = []

    for task in _TASKS:
        messages = build_messages(system_prompt, build_executable_terminal_prompt(task))
        try:
            response = await llm_call(
                messages,
                temperature=model_config.get("temperature", 0.1),
                max_tokens=model_config.get("max_tokens", 1024),
            )
            total_cost += 0.001
            result = evaluate_executable_terminal_response(task, response)
            total_score += result.score
            evaluated += 1
            if not result.passed and len(failures) < 5:
                failures.append(
                    {
                        "id": task.id,
                        "error": result.error,
                        "mismatches": list(result.mismatches),
                    }
                )
        except (TimeoutError, Exception) as exc:
            evaluated += 1
            if len(failures) < 5:
                failures.append({"id": task.id, "error": f"error: {exc}"})

    avg_score = total_score / max(evaluated, 1)
    elapsed = time.monotonic() - start

    return EvalResult(
        benchmark="terminalbench",
        score=round(avg_score, 4),
        cost_usd=round(total_cost, 4),
        duration_seconds=round(elapsed, 3),
        samples_evaluated=evaluated,
        metadata={
            "total_samples": len(_TASKS),
            "fidelity": "proxy",
            "check": "verified_filesystem_state",
            "failures": failures,
        },
    )
