"""Structured action protocol for interactive builder sessions."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

BuilderAction = Literal[
    "search",
    "read_file",
    "propose_patch",
    "run_command",
    "show_diff",
    "apply_diff",
    "summarize",
    "define_spec",
    "accept_spec",
    "comment_card",
    "post_question",
    "record_quality",
]

SUPPORTED_ACTIONS: frozenset[str] = frozenset(
    {
        "search",
        "read_file",
        "propose_patch",
        "run_command",
        "show_diff",
        "apply_diff",
        "summarize",
        "define_spec",
        "accept_spec",
        "comment_card",
        "post_question",
        "record_quality",
    }
)


class ActionRequest(BaseModel):
    """A model-requested builder action after validation."""

    action: BuilderAction
    args: dict[str, Any] = Field(default_factory=dict)

    @field_validator("action", mode="before")
    @classmethod
    def _known_action(cls, value: object) -> object:
        if isinstance(value, str) and value not in SUPPORTED_ACTIONS:
            raise ValueError(f"unsupported builder action: {value}")
        return value

    @classmethod
    def from_json(cls, payload: str) -> ActionRequest:
        """Parse and validate one JSON action object from the model."""
        try:
            raw = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid builder action JSON: {exc.msg}") from exc
        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc


class ActionResult(BaseModel):
    """Compact result returned to the session transcript."""

    status: Literal["ok", "error", "needs_approval"]
    output: str
    metadata: dict[str, Any] = Field(default_factory=dict)
