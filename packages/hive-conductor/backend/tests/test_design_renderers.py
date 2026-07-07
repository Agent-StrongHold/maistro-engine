"""Renderer-registry wiring in the design service (SPEC-070426-a22b / -6ea8)."""

from __future__ import annotations

import pytest
from services.design_service import _open_design_config


def test_open_design_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPEN_DESIGN_ENABLED", raising=False)
    assert _open_design_config() is None  # no daemon probe unless explicitly enabled


def test_open_design_config_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPEN_DESIGN_ENABLED", "1")
    monkeypatch.setenv("OPEN_DESIGN_URL", "http://od-host:7456")
    monkeypatch.setenv("OPEN_DESIGN_TOKEN", "secret")
    cfg = _open_design_config()
    assert cfg is not None
    assert cfg.enabled
    assert cfg.base_url == "http://od-host:7456"
    assert cfg.token == "secret"


def test_open_design_config_falsey_flag_stays_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPEN_DESIGN_ENABLED", "off")
    assert _open_design_config() is None


async def test_registry_with_no_provider_hides_web_skills_from_listing() -> None:
    """With Open Design disabled, discovered slots are the native floor and the design
    catalog's reflowable-web skills are filtered out — the production listing contract."""
    from maistro_design.renderers import NATIVE_SLOTS, RendererRegistry, RenderSlot
    from maistro_design.skills.builtins import load_builtins
    from maistro_design.skills.registry import InMemoryDesignSkillRegistry

    registry = RendererRegistry()
    filled = await registry.discover_all()
    assert filled == NATIVE_SLOTS
    assert RenderSlot.REFLOWABLE_WEB not in filled

    skills = InMemoryDesignSkillRegistry()
    load_builtins(skills)
    slugs = {s.slug for s in skills.list_available(filled)}
    assert "pitch-deck" in slugs  # native deck
    assert "landing-page" not in slugs  # external web, absent
