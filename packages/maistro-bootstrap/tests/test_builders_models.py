"""LiteLLM config parsing for interactive builder sessions."""

from __future__ import annotations

from pathlib import Path

from maistro_bootstrap.builders.models import load_litellm_models, role_mapping_from_models


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
