"""Input sanitization: strip zero-width chars, normalize unicode."""

from __future__ import annotations

import re


def sanitize(text: str) -> str:
    text = re.sub(r"[\u200b\u200c\u200d\u200e\u200f\ufeff]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
