"""LiteLLM config parsing for interactive builder sessions."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from maistro_bootstrap.builders.models import (
    _model_from_entry,
    load_litellm_models,
    role_mapping_from_models,
)


def test_load_litellm_models_reads_model_aliases(tmp_path: Path) -> None:
    config = tmp_path / "litellm_config.yaml"
    config.write_text(
        """
model_list:
  - model_name: maistro-tier-1
    litellm_params:
      model: ollama/qwen2.5-coder:7b
  - model_name: cloud-sonnet
    litellm_params:
      model: anthropic/claude-sonnet-4-6
""",
        encoding="utf-8",
    )

    models = load_litellm_models(config)

    assert [m.alias for m in models] == ["maistro-tier-1", "cloud-sonnet"]
    assert models[0].provider_model == "ollama/qwen2.5-coder:7b"


def test_role_mapping_prefers_builder_tiers_and_cloud_fallback(tmp_path: Path) -> None:
    config = tmp_path / "litellm_config.yaml"
    config.write_text(
        """
model_list:
  - model_name: maistro-tier-1
    litellm_params: {model: ollama/qwen2.5-coder:7b}
  - model_name: maistro-tier-2
    litellm_params: {model: ollama/qwen2.5-coder:32b}
  - model_name: maistro-tier-3
    litellm_params: {model: ollama/qwen3-coder:80b}
  - model_name: cloud-opus
    litellm_params: {model: anthropic/claude-opus-4-6}
""",
        encoding="utf-8",
    )

    roles = role_mapping_from_models(load_litellm_models(config))

    assert roles.architect == "maistro-tier-3"
    assert roles.editor == "maistro-tier-2"
    assert roles.tester == "maistro-tier-1"
    assert roles.fallback == "cloud-opus"


def test_missing_litellm_config_uses_environment_defaults(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DEFAULT_MODEL", "cloud-sonnet")

    models = load_litellm_models(tmp_path / "missing.yaml")
    roles = role_mapping_from_models(models)

    assert [m.alias for m in models] == ["cloud-sonnet"]
    assert models[0].provider_model == "cloud-sonnet"
    assert models[0].metadata == {"source": "env"}
    assert roles.architect == "cloud-sonnet"
    assert roles.editor == "cloud-sonnet"
    assert roles.tester == "cloud-sonnet"
    assert roles.fallback == "cloud-sonnet"


def test_empty_role_mapping_uses_same_default_for_every_role(monkeypatch) -> None:
    monkeypatch.delenv("DEFAULT_MODEL", raising=False)
    monkeypatch.setenv("CHAT_DEFAULT_MODEL", "chat-default")

    roles = role_mapping_from_models([])

    assert roles.as_rows() == [
        ("architect", "chat-default"),
        ("editor", "chat-default"),
        ("tester", "chat-default"),
        ("fallback", "chat-default"),
    ]


# ---------------------------------------------------------------------------
# _model_from_entry edge cases
# ---------------------------------------------------------------------------


def test_model_from_entry_returns_none_for_non_dict_input() -> None:
    assert _model_from_entry("a string") is None
    assert _model_from_entry(42) is None
    assert _model_from_entry([{"model_name": "x"}]) is None


def test_model_from_entry_returns_none_when_model_name_missing() -> None:
    assert _model_from_entry({"litellm_params": {"model": "anthropic/claude"}}) is None


def test_model_from_entry_returns_none_for_empty_string_model_name() -> None:
    assert _model_from_entry({"model_name": "", "litellm_params": {}}) is None


def test_model_from_entry_returns_none_for_whitespace_only_model_name() -> None:
    assert _model_from_entry({"model_name": "   ", "litellm_params": {}}) is None


def test_model_from_entry_parses_valid_entry() -> None:
    model = _model_from_entry(
        {"model_name": "my-model", "litellm_params": {"model": "openai/gpt-4o"}}
    )

    assert model is not None
    assert model.alias == "my-model"
    assert model.provider_model == "openai/gpt-4o"


# ---------------------------------------------------------------------------
# load_litellm_models with corrupt YAML
# ---------------------------------------------------------------------------


def test_load_litellm_models_raises_on_corrupt_yaml(tmp_path: Path) -> None:
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text(": bad: yaml: {{{", encoding="utf-8")

    with pytest.raises(yaml.YAMLError):
        load_litellm_models(bad_yaml)


def test_load_litellm_models_falls_back_when_model_list_entries_all_invalid(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # All entries are non-dicts — every _model_from_entry returns None.
    config = tmp_path / "litellm_config.yaml"
    config.write_text("model_list:\n  - null\n  - 42\n", encoding="utf-8")
    monkeypatch.setenv("DEFAULT_MODEL", "fallback-env-model")

    models = load_litellm_models(config)

    assert len(models) == 1
    assert models[0].alias == "fallback-env-model"
    assert models[0].metadata == {"source": "env"}
