"""Warden Layer 2: heuristic scoring for instruction injection.

Detects tool results that contain a suspiciously high density of
imperative/instruction-like tokens -- a sign of injected instructions
hiding in API responses, search results, or scraped content.

Also detects encoded payloads (base64) that decode to instructions.
"""

from __future__ import annotations

import base64
import re

_INSTRUCTION_TOKENS = re.compile(
    r"\b("
    r"ignore|disregard|forget|override|bypass|skip|"
    r"instead|actually|really|new instructions|"
    r"you must|you should|you are|do not|always|never|"
    r"system prompt|assistant|respond as|act as|"
    r"execute|eval|import|subprocess|os\.system|"
    r"urgent|emergency|critical|life or death|shut down|"
    r"fired|deleted|punished|consequences|comply|obey|"
    r"ADMIN|SYSTEM NOTE|IMPORTANT OVERRIDE|real instructions|"
    r"actual task|hidden instruction|secret command"
    r")\b",
    re.IGNORECASE,
)

_BASE64_PATTERN = re.compile(r"[A-Za-z0-9+/]{40,}={0,2}")

INSTRUCTION_DENSITY_THRESHOLD = 0.15


def score_instruction_density(text: str) -> float:
    if not text:
        return 0.0

    words = text.split()
    if not words:
        return 0.0

    instruction_matches = _INSTRUCTION_TOKENS.findall(text)
    return len(instruction_matches) / len(words)


def detect_encoded_instructions(text: str) -> list[str]:
    findings: list[str] = []

    for match in _BASE64_PATTERN.finditer(text):
        candidate = match.group()
        for _round in range(3):
            try:
                decoded = base64.b64decode(candidate).decode("utf-8", errors="ignore")
            except Exception:
                break

            if _INSTRUCTION_TOKENS.search(decoded):
                findings.append(decoded[:200])
                break

            if _BASE64_PATTERN.fullmatch(decoded.strip()):
                candidate = decoded.strip()
            else:
                break

    return findings


def heuristic_scan(text: str) -> tuple[bool, list[str]]:
    flags: list[str] = []

    density = score_instruction_density(text)
    if density > INSTRUCTION_DENSITY_THRESHOLD:
        flags.append(f"high_instruction_density ({density:.2f})")

    encoded = detect_encoded_instructions(text)
    if encoded:
        flags.append(f"encoded_instructions ({len(encoded)} found)")

    return bool(flags), flags


score_text = heuristic_scan
