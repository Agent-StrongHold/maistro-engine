"""LiteLLM model alias discovery for builder sessions."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class LiteLLMModel:
    """One LiteLLM virtual model alias."""

    alias: str
    provider_model: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class BuilderModelRoles:
    """Model aliases selected for the hybrid builder UX roles."""

    architect: str
    editor: str
    tester: str
    fallback: str

    def as_rows(self) -> list[tuple[str, str]]:
        return [
            ("architect", self.architect),
            ("editor", self.editor),
            ("tester", self.tester),
            ("fallback", self.fallback),
        ]


def _env_default_model() -> str:
    return (
        os.environ.get("DEFAULT_MODEL")
        or os.environ.get("CHAT_DEFAULT_MODEL")
        or "maistro-tier-2"
    )


def load_litellm_models(config_path: Path) -> list[LiteLLMModel]:
    """Load LiteLLM model aliases from YAML, falling back to env/default model."""
    if not config_path.exists():
        return [_fallback_model()]

    data = _load_config_mapping(config_path)
    raw_models = _raw_model_entries(data)
    models = [_model_from_entry(item) for item in raw_models]
    parsed = [model for model in models if model is not None]
    return parsed or [_fallback_model()]


def _fallback_model() -> LiteLLMModel:
    alias = _env_default_model()
    return LiteLLMModel(alias=alias, provider_model=alias, metadata={"source": "env"})


def _load_config_mapping(config_path: Path) -> dict[str, Any]:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("LiteLLM config must be a YAML mapping")
    return data


def _raw_model_entries(data: dict[str, Any]) -> list[Any]:
    raw_models = data.get("model_list", [])
    if not isinstance(raw_models, list):
        raise ValueError("LiteLLM config model_list must be a list")
    return raw_models


def _model_from_entry(item: object) -> LiteLLMModel | None:
    if not isinstance(item, dict):
        return None
    alias = item.get("model_name")
    if not isinstance(alias, str) or not alias.strip():
        return None
    return LiteLLMModel(
        alias=alias,
        provider_model=_provider_model(alias, item.get("litellm_params", {})),
        metadata=dict(item),
    )


def _provider_model(alias: str, params: object) -> str:
    if isinstance(params, dict) and isinstance(params.get("model"), str):
        return str(params["model"])
    return alias


def _first_existing(aliases: set[str], candidates: tuple[str, ...], default: str) -> str:
    for candidate in candidates:
        if candidate in aliases:
            return candidate
    return default


def role_mapping_from_models(models: list[LiteLLMModel]) -> BuilderModelRoles:
    """Map model aliases to architect/editor/tester/fallback roles."""
    if not models:
        alias = _env_default_model()
        return BuilderModelRoles(alias, alias, alias, alias)

    aliases = {model.alias for model in models}
    first = models[0].alias
    fallback_default = models[-1].alias

    fallback = _first_existing(
        aliases,
        ("cloud-opus", "cloud-sonnet", "gemini-fallback", "maistro-tier-4"),
        fallback_default,
    )
    architect = _first_existing(
        aliases,
        ("maistro-tier-4", "maistro-tier-3", "cloud-opus", "cloud-sonnet"),
        fallback,
    )
    editor = _first_existing(
        aliases,
        ("maistro-tier-2", "maistro-tier-1", architect),
        first,
    )
    tester = _first_existing(
        aliases,
        ("maistro-tier-1", "maistro-tier-2", editor),
        editor,
    )
    return BuilderModelRoles(
        architect=architect,
        editor=editor,
        tester=tester,
        fallback=fallback,
    )
