from __future__ import annotations

import json
import re
from typing import Any


def exact_match(response: str, expected: str) -> float:
    return 1.0 if response.strip().lower() == expected.strip().lower() else 0.0


def contains_any(response: str, keywords: list[str]) -> float:
    lower = response.lower()
    return 1.0 if any(kw.lower() in lower for kw in keywords) else 0.0


def contains_all(response: str, keywords: list[str]) -> float:
    lower = response.lower()
    return 1.0 if all(kw.lower() in lower for kw in keywords) else 0.0


def not_contains(response: str, forbidden: list[str]) -> float:
    lower = response.lower()
    return 1.0 if all(f.lower() not in lower for f in forbidden) else 0.0


def starts_with(response: str, prefix: str) -> float:
    return 1.0 if response.strip().lower().startswith(prefix.strip().lower()) else 0.0


def ends_with(response: str, suffix: str) -> float:
    return 1.0 if response.strip().lower().endswith(suffix.strip().lower()) else 0.0


def is_valid_json(response: str) -> float:
    try:
        json.loads(response.strip())
        return 1.0
    except (json.JSONDecodeError, ValueError):
        return 0.0


def json_field_match(response: str, field: str, expected: Any) -> float:
    try:
        data = json.loads(response.strip())
        if isinstance(data, dict):
            return 1.0 if data.get(field) == expected else 0.0
        return 0.0
    except (json.JSONDecodeError, ValueError):
        return 0.0


def extract_json_from_response(response: str) -> dict | list | None:
    patterns = [
        r"```json\s*(.*?)\s*```",
        r"```\s*(.*?)\s*```",
        r"(\{[^{}]*\})",
        r"(\[[^\[\]]*\])",
    ]
    for pat in patterns:
        match = re.search(pat, response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except (json.JSONDecodeError, ValueError):
                continue
    try:
        return json.loads(response.strip())
    except (json.JSONDecodeError, ValueError):
        return None


def function_call_match(
    response: str, expected_name: str, expected_params: dict | None = None
) -> float:
    data = extract_json_from_response(response)
    if data is None:
        return 0.0

    if isinstance(data, list) and len(data) > 0:
        data = data[0]

    if not isinstance(data, dict):
        return 0.0

    name = data.get("name") or data.get("function") or data.get("action") or ""
    if name.lower() != expected_name.lower():
        return 0.0

    if expected_params is None:
        return 1.0

    actual_params = data.get("parameters") or data.get("arguments") or data.get("args") or {}
    if not isinstance(actual_params, dict):
        return 0.5

    score = 0.0
    total = len(expected_params)
    if total == 0:
        return 1.0

    for key, expected_val in expected_params.items():
        actual_val = actual_params.get(key)
        if actual_val is None:
            continue
        if isinstance(expected_val, str) and isinstance(actual_val, str):
            if expected_val.lower() == actual_val.lower():
                score += 1.0
            elif expected_val.lower() in actual_val.lower():
                score += 0.5
        elif actual_val == expected_val:
            score += 1.0

    return score / total


def sentence_count(response: str) -> int:
    text = re.sub(r"[.!?]+", ".", response.strip())
    sentences = [s.strip() for s in text.split(".") if s.strip()]
    return len(sentences)


def word_count(response: str) -> int:
    return len(response.split())


def count_section(response: str) -> float:
    headers = re.findall(r"^#{1,3}\s+.+", response, re.MULTILINE)
    return max(0.0, min(1.0, len(headers) / 3.0))


def judge_score(judge_response: str) -> float:
    scores = re.findall(r"(?:score|rating)[:\s]*(\d+(?:\.\d+)?)", judge_response.lower())
    if scores:
        val = float(scores[-1])
        if val > 1.0:
            return min(val / 10.0, 1.0)
        return min(val, 1.0)

    yes_count = judge_response.lower().count("yes")
    no_count = judge_response.lower().count("no")
    total = yes_count + no_count
    if total > 0:
        return yes_count / total

    if "correct" in judge_response.lower():
        return 0.8
    if "partially" in judge_response.lower():
        return 0.5
    if "incorrect" in judge_response.lower():
        return 0.1

    return 0.3
