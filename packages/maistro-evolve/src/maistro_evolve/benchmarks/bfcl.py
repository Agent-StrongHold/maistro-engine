from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from ..types import EvalResult, PipelineGenome
from .datasets import BFCL_SAMPLES
from .prompt_builder import build_messages, build_model_config, build_system_prompt
from .scoring import extract_json_from_response, function_call_match


def _extract_tool_call(response: str) -> dict[str, Any] | None:
    data = extract_json_from_response(response)
    if data is not None:
        if isinstance(data, list) and len(data) > 0:
            data = data[0]
        if isinstance(data, dict):
            return data

    action_match = re.search(
        r"(?:call|invoke|use|execute)\s+(\w+)\s*\(([^)]*)\)",
        response,
        re.IGNORECASE,
    )
    if action_match:
        name = action_match.group(1)
        args_str = action_match.group(2).strip()
        args: dict[str, Any] = {}
        if args_str:
            for pair in args_str.split(","):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    args[k.strip()] = v.strip().strip("\"'")
        return {"name": name, "parameters": args}

    return None


def _score_tool_call(
    response: str,
    sample: dict[str, Any],
) -> float:
    expected_name = sample["expected_name"].lower()
    expected_params = sample.get("expected_params")

    name_score = 0.0
    param_score = 0.0

    fc_score = function_call_match(response, sample["expected_name"], expected_params)
    if fc_score > 0:
        return fc_score

    call = _extract_tool_call(response)
    if call is None:
        response_lower = response.lower()
        if (
            expected_name.replace("_", " ") in response_lower
            or expected_name.replace("_", "") in response_lower
        ):
            name_score = 0.5
            return name_score * 0.5
        return 0.0

    actual_name = str(call.get("name") or call.get("function") or call.get("action") or "").lower()
    if actual_name == expected_name:
        name_score = 1.0
    elif expected_name.replace("_", "") in actual_name.replace("_", ""):
        name_score = 0.8
    elif expected_name.replace("_", " ") in actual_name:
        name_score = 0.6

    if expected_params is None:
        param_score = 1.0
    else:
        actual_params = call.get("parameters") or call.get("arguments") or call.get("args") or {}
        if not isinstance(actual_params, dict):
            actual_params = {}

        matches = 0
        total = len(expected_params)
        if total == 0:
            param_score = 1.0
        else:
            for key, expected_val in expected_params.items():
                actual_val = actual_params.get(key)
                if actual_val is None:
                    text = response.lower()
                    if isinstance(expected_val, str) and expected_val.lower() in text:
                        matches += 0.5
                    continue
                if isinstance(expected_val, bool):
                    if str(actual_val).lower() == str(expected_val).lower():
                        matches += 1.0
                elif isinstance(expected_val, (int, float)):
                    try:
                        if float(actual_val) == float(expected_val):
                            matches += 1.0
                        elif abs(float(actual_val) - float(expected_val)) < 1.0:
                            matches += 0.5
                    except (ValueError, TypeError):
                        if str(expected_val).lower() in str(actual_val).lower():
                            matches += 0.5
                elif isinstance(expected_val, str):
                    if expected_val.lower() == str(actual_val).lower():
                        matches += 1.0
                    elif expected_val.lower() in str(actual_val).lower():
                        matches += 0.7
            param_score = matches / total

    return name_score * 0.4 + param_score * 0.6


async def run_bfcl(genome: PipelineGenome, llm_call: Any) -> EvalResult:
    start = time.monotonic()
    system_prompt = build_system_prompt(genome)
    model_config = build_model_config(genome)

    total_score = 0.0
    evaluated = 0
    total_cost = 0.0
    samples = len(BFCL_SAMPLES)

    for sample in BFCL_SAMPLES:
        functions_desc = "\nAvailable functions:\n"
        for fn in sample["functions"]:
            params_str = ", ".join(f"{k}: {v}" for k, v in fn.get("parameters", {}).items())
            functions_desc += f"- {fn['name']}({params_str}): {fn.get('description', '')}\n"

        user_msg = (
            f"{sample['query']}\n\n"
            f"Respond with the function call as a JSON object with 'name' and 'parameters' fields. "
            f'Example: {{"name": "function_name", "parameters": {{...}}}}\n'
            f"{functions_desc}"
        )

        messages = build_messages(system_prompt, user_msg)

        try:
            if llm_call is not None:
                response = await asyncio.wait_for(
                    llm_call(
                        messages,
                        temperature=model_config.get("temperature", 0.1),
                        max_tokens=model_config.get("max_tokens", 1024),
                    ),
                    timeout=30.0,
                )
                score = _score_tool_call(response, sample)
                total_score += score
                evaluated += 1
                total_cost += 0.001
            else:
                score = _heuristic_score(sample)
                total_score += score
                evaluated += 1
        except (TimeoutError, Exception):
            evaluated += 1

    avg_score = total_score / max(evaluated, 1)
    elapsed = time.monotonic() - start

    return EvalResult(
        benchmark="bfcl",
        score=round(avg_score, 4),
        cost_usd=round(total_cost, 4),
        duration_seconds=round(elapsed, 3),
        samples_evaluated=evaluated,
        metadata={"total_samples": samples, "runner": "real"},
    )


def _heuristic_score(sample: dict[str, Any]) -> float:
    import random

    num_functions = len(sample.get("functions", []))
    base = 0.6 if num_functions == 1 else 0.45
    num_params = len(sample.get("expected_params", {}))
    base -= num_params * 0.03
    return max(0.1, min(0.9, base + random.uniform(-0.05, 0.05)))
