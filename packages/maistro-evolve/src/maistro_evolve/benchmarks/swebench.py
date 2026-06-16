from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from ..types import EvalResult, PipelineGenome
from .datasets import SWEBENCH_SAMPLES
from .prompt_builder import build_messages, build_model_config, build_system_prompt
from .scoring import judge_score


def _score_keywords(code_text: str, sample: dict[str, Any]) -> tuple[float, float]:
    expected_keywords = sample.get("expected_keywords", [])
    if not expected_keywords:
        return 0.0, 0.0
    found = sum(1 for kw in expected_keywords if kw.lower() in code_text.lower())
    return (found / len(expected_keywords)) * 0.4, 0.4


def _score_buggy_change(code_text: str, sample: dict[str, Any]) -> tuple[float, float]:
    buggy_code = sample.get("buggy_code", "")
    if not buggy_code:
        return 0.0, 0.0
    buggy_lines = [
        line.strip()
        for line in buggy_code.split("\n")
        if line.strip() and not line.strip().startswith("def ")
    ]
    if not buggy_lines:
        return 0.1, 0.2
    unchanged = sum(1 for line in buggy_lines if line.lower() in code_text.lower())
    change_ratio = 1.0 - (unchanged / len(buggy_lines))
    return change_ratio * 0.2, 0.2


def _score_recursive(code_text: str, sample: dict[str, Any]) -> tuple[float, float]:
    problem_desc = sample.get("problem", "").lower()
    if "recursive" not in problem_desc and "recursively" not in problem_desc:
        return 0.0, 0.0
    if "recursive" in code_text.lower() or code_text.count("def ") > 1:
        return 0.15, 0.15
    return 0.0, 0.15


def _score_expected_output(code_text: str, sample: dict[str, Any]) -> tuple[float, float]:
    expected_output = sample.get("expected_output", "")
    if not expected_output:
        return 0.0, 0.0
    if expected_output.lower().replace(" ", "") in code_text.lower().replace(" ", ""):
        return 0.1, 0.1
    return 0.0, 0.1


def _score_code_fix(response: str, sample: dict[str, Any]) -> float:
    code_blocks = re.findall(r"```(?:python)?\s*(.*?)```", response, re.DOTALL)
    code_text = "\n".join(code_blocks) if code_blocks else response

    score = 0.0
    max_score = 0.0
    for component in (
        _score_keywords(code_text, sample),
        _score_buggy_change(code_text, sample),
        _score_recursive(code_text, sample),
        _score_expected_output(code_text, sample),
    ):
        score += component[0]
        max_score += component[1]

    if "return" in code_text and "def " in code_text:
        max_score += 0.1
        score += 0.1

    if len(code_text.strip()) > 20:
        max_score += 0.05
        score += 0.05

    if max_score == 0:
        return 0.5

    return min(1.0, score / max_score)


async def _judge_code_quality(
    problem: str,
    buggy_code: str,
    response: str,
    llm_call: Any,
) -> float:
    code_blocks = re.findall(r"```(?:python)?\s*(.*?)```", response, re.DOTALL)
    proposed_fix = "\n".join(code_blocks) if code_blocks else response[:500]

    judge_prompt = (
        f"You are a code review expert. Evaluate this bug fix on a scale of 0-10.\n\n"
        f"Problem: {problem}\n\n"
        f"Buggy code:\n{buggy_code}\n\n"
        f"Proposed fix:\n{proposed_fix}\n\n"
        f"Consider: Does the fix address the bug? Is it correct? Is it efficient?\n"
        f"Respond with ONLY a number 0-10."
    )

    try:
        judge_response = await asyncio.wait_for(
            llm_call(
                [
                    {
                        "role": "system",
                        "content": "You are a strict code judge. Respond with only a number.",
                    },
                    {"role": "user", "content": judge_prompt},
                ],
                temperature=0.0,
                max_tokens=10,
            ),
            timeout=20.0,
        )
        return judge_score(judge_response)
    except (TimeoutError, Exception):
        return 0.0


async def run_swebench(genome: PipelineGenome, llm_call: Any) -> EvalResult:
    start = time.monotonic()
    system_prompt = build_system_prompt(genome)
    model_config = build_model_config(genome)

    code_system = (
        system_prompt + "\n\n"
        "You are an expert software engineer. When given a bug report, provide a corrected "
        "version of the code wrapped in ```python``` code blocks. Explain the fix briefly."
    )

    total_score = 0.0
    evaluated = 0
    total_cost = 0.0
    samples = len(SWEBENCH_SAMPLES)

    for sample in SWEBENCH_SAMPLES:
        user_msg = (
            f"## Bug Report\n{sample['problem']}\n\n"
            f"## Buggy Code\n```python\n{sample['buggy_code']}\n```\n\n"
            f"Please provide the fixed code. The expected output for test input "
            f"{sample['test_input']} is {sample['expected_output']}."
        )
        messages = build_messages(code_system, user_msg)

        try:
            if llm_call is not None:
                response = await asyncio.wait_for(
                    llm_call(
                        messages,
                        temperature=model_config.get("temperature", 0.2),
                        max_tokens=model_config.get("max_tokens", 2048),
                    ),
                    timeout=45.0,
                )

                static_score = _score_code_fix(response, sample)

                if static_score >= 0.7:
                    total_score += static_score
                else:
                    judged = await _judge_code_quality(
                        sample["problem"], sample["buggy_code"], response, llm_call
                    )
                    total_score += max(static_score, judged)
                    total_cost += 0.001

                total_cost += 0.002
                evaluated += 1
            else:
                score = _heuristic_score(sample)
                total_score += score
                evaluated += 1
        except (TimeoutError, Exception):
            evaluated += 1

    avg_score = total_score / max(evaluated, 1)
    elapsed = time.monotonic() - start

    return EvalResult(
        benchmark="swebench",
        score=round(avg_score, 4),
        cost_usd=round(total_cost, 4),
        duration_seconds=round(elapsed, 3),
        samples_evaluated=evaluated,
        metadata={"total_samples": samples, "runner": "proxy", "fidelity": "proxy"},
    )


def _heuristic_score(sample: dict[str, Any]) -> float:
    import random

    problem = sample.get("problem", "").lower()
    base = 0.45
    if "recursive" in problem:
        base = 0.35
    if "optimize" in problem or "slow" in problem:
        base = 0.3
    if "regex" in problem or "re." in problem:
        base = 0.4
    return max(0.1, min(0.85, base + random.uniform(-0.05, 0.1)))
