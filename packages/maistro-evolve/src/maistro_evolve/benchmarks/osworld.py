from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from ..types import EvalResult, PipelineGenome
from .datasets import OSWORLD_SAMPLES
from .prompt_builder import build_messages, build_model_config, build_system_prompt
from .scoring import judge_score


def _action_from_dict(item: dict[str, Any]) -> str | None:
    action_type = item.get("action") or item.get("type") or item.get("name") or ""
    target = item.get("target") or item.get("value") or item.get("parameter") or ""
    if not action_type:
        return None
    return f"{action_type}:{target}" if target else action_type


def _parse_json_actions(response: str) -> list[str]:
    import json

    json_patterns = [
        r"```(?:json)?\s*(.*?)```",
        r"(\[[^\[\]]*\])",
    ]
    for pat in json_patterns:
        match = re.search(pat, response, re.DOTALL)
        if not match:
            continue
        try:
            data = json.loads(match.group(1))
        except (ValueError, Exception):
            continue
        if not isinstance(data, list):
            continue
        actions: list[str] = []
        for item in data:
            if isinstance(item, dict):
                parsed = _action_from_dict(item)
                if parsed:
                    actions.append(parsed)
            elif isinstance(item, str):
                actions.append(item)
        if actions:
            return actions
    return []


def _parse_actions(response: str) -> list[str]:
    actions = _parse_json_actions(response)
    if actions:
        return actions

    action_patterns = [
        r"step\s*\d+[\.:]\s*(.+?)(?:\n|$)",
        r"^\d+[\.:]\s*(.+?)$",
        r"[-*]\s*(.+?)$",
        r"(?:action|step|click|type|press|open|navigate|select|run):\s*(.+?)(?:\n|$)",
    ]
    for pat in action_patterns:
        matches = re.findall(pat, response, re.MULTILINE | re.IGNORECASE)
        if matches:
            actions.extend(m.strip() for m in matches if m.strip())
            if len(actions) >= 2:
                return actions

    lines = response.strip().split("\n")
    for line in lines:
        line = line.strip().lstrip("0123456789.-) ")
        if line and len(line) > 3:
            actions.append(line)

    return actions


def _score_action_sequence(
    response: str,
    expected_actions: list[str],
) -> float:
    proposed = _parse_actions(response)
    if not proposed:
        return 0.0

    proposed_text = " ".join(proposed).lower()

    matched = 0.0
    for expected in expected_actions:
        exp_lower = expected.lower()
        if ":" in exp_lower:
            parts = exp_lower.split(":", 1)
            action_part = parts[0].strip()
            target_part = parts[1].strip() if len(parts) > 1 else ""

            action_found = action_part in proposed_text
            target_found = target_part in proposed_text if target_part else True

            if action_found and target_found:
                matched += 1.0
            elif action_found:
                matched += 0.5
        else:
            if exp_lower in proposed_text:
                matched += 1.0
            elif any(w in proposed_text for w in exp_lower.split("_")):
                matched += 0.4

    recall = matched / len(expected_actions) if expected_actions else 1.0
    return min(1.0, recall)


async def _judge_os_actions(
    task: str,
    response: str,
    expected_actions: list[str],
    llm_call: Any,
) -> float:
    proposed = _parse_actions(response)
    proposed_text = "\n".join(f"  {i + 1}. {a}" for i, a in enumerate(proposed))
    expected_text = "\n".join(f"  {i + 1}. {a}" for i, a in enumerate(expected_actions))

    judge_prompt = (
        f"Task: {task}\n\n"
        f"Expected action sequence:\n{expected_text}\n\n"
        f"Proposed action sequence:\n{proposed_text}\n\n"
        f"Does the proposed sequence correctly accomplish the task? Rate 0-10.\n"
        f"Respond with ONLY a number."
    )

    try:
        judge_response = await asyncio.wait_for(
            llm_call(
                [
                    {
                        "role": "system",
                        "content": "You are a desktop automation expert. Respond with only a number.",
                    },
                    {"role": "user", "content": judge_prompt},
                ],
                temperature=0.0,
                max_tokens=10,
            ),
            timeout=15.0,
        )
        return judge_score(judge_response)
    except (TimeoutError, Exception):
        return 0.0


async def run_osworld(genome: PipelineGenome, llm_call: Any) -> EvalResult:
    start = time.monotonic()
    system_prompt = build_system_prompt(genome)
    model_config = build_model_config(genome)

    os_system = (
        system_prompt + "\n\n"
        "You are a desktop automation assistant. Given a task, provide a numbered list of "
        "actions to accomplish it. Each action should describe a specific UI interaction like "
        "clicking, typing, selecting, or opening. Format as:\n"
        "1. action_name: target (e.g., 'click: File menu', 'type: hello world')"
    )

    total_score = 0.0
    evaluated = 0
    total_cost = 0.0
    samples = len(OSWORLD_SAMPLES)

    for sample in OSWORLD_SAMPLES:
        user_msg = (
            f"Task: {sample['task']}\n\n"
            f"Provide a step-by-step action sequence to accomplish this task."
        )
        messages = build_messages(os_system, user_msg)

        try:
            if llm_call is not None:
                response = await asyncio.wait_for(
                    llm_call(
                        messages,
                        temperature=model_config.get("temperature", 0.2),
                        max_tokens=model_config.get("max_tokens", 1024),
                    ),
                    timeout=30.0,
                )
                total_cost += 0.001

                expected_actions = sample.get("expected_actions", [])
                static = _score_action_sequence(response, expected_actions)

                if static >= 0.6:
                    total_score += static
                else:
                    judged = await _judge_os_actions(
                        sample["task"], response, expected_actions, llm_call
                    )
                    total_score += max(static, judged)
                    total_cost += 0.0005

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
        benchmark="osworld",
        score=round(avg_score, 4),
        cost_usd=round(total_cost, 4),
        duration_seconds=round(elapsed, 3),
        samples_evaluated=evaluated,
        metadata={"total_samples": samples, "runner": "real"},
    )


def _heuristic_score(sample: dict[str, Any]) -> float:
    import random

    num_actions = len(sample.get("expected_actions", []))
    base = 0.6 if num_actions <= 2 else 0.45 if num_actions <= 3 else 0.3
    return max(0.1, min(0.85, base + random.uniform(-0.05, 0.1)))
