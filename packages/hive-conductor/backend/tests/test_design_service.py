"""DesignService boot-path contracts.

Two regressions this file exists to catch, both of the "green under pytest,
false in production" shape:

- The "design.orchestrate" node kind was only registered when a test imported
  maistro_design.nodes directly; no live process ever did (ADR-061/AC-7 was
  true under pytest and false in production).
- start_design_service imported a module that does not exist
  (maistro_design.systems.builtins), and its `except Exception` fallback
  registered a lone "default" — so ADR-100's six bundled design systems never
  loaded in any live hive, on every boot, silently.
"""

import pytest


def test_importing_design_service_registers_orchestrate_node():
    """ADR-061 §6: the node kind must be in the registry because the app
    booted, not because a test imported the module."""
    import services.design_service  # noqa: F401  (module scope does the registration)

    from maistro.graph.nodes import get_node
    from maistro_design.nodes import DesignOrchestrateNode

    assert get_node("design.orchestrate") is DesignOrchestrateNode


@pytest.mark.anyio
async def test_bundled_design_systems_load_at_startup(monkeypatch):
    """ADR-100: all six bundled systems resolve after start_design_service,
    not just the bare 'default' fallback the swallowed ImportError left."""
    import services.design_service as ds
    from config import Settings

    from maistro_design.systems.importer import BUNDLED_SLUGS

    def _no_session_factory():
        return None

    # stop_design_service calls .cache_clear() on the real lru_cache'd function.
    _no_session_factory.cache_clear = lambda: None  # type: ignore[attr-defined]
    monkeypatch.setattr(ds, "_get_async_session_factory", _no_session_factory)
    await ds.start_design_service(Settings())
    try:
        registry = ds.get_design_engine()._systems
        for slug in BUNDLED_SLUGS:
            assert registry.get(slug) is not None, f"bundled system {slug!r} did not load"
    finally:
        await ds.stop_design_service()
