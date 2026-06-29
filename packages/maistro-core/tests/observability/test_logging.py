"""Coverage for observability/logging.py."""

from __future__ import annotations

import logging

import structlog

from maistro.observability.logging import configure_logging


def test_configure_logging_json_output_uses_json_renderer() -> None:
    configure_logging(debug=False, json_output=True)
    config = structlog.get_config()
    renderers = [type(p).__name__ for p in config["processors"]]
    assert "JSONRenderer" in renderers


def test_configure_logging_debug_uses_console_renderer_even_if_json_requested() -> None:
    configure_logging(debug=True, json_output=True)
    config = structlog.get_config()
    renderers = [type(p).__name__ for p in config["processors"]]
    assert "ConsoleRenderer" in renderers


def test_configure_logging_non_json_uses_console_renderer() -> None:
    configure_logging(debug=False, json_output=False)
    config = structlog.get_config()
    renderers = [type(p).__name__ for p in config["processors"]]
    assert "ConsoleRenderer" in renderers


def test_configure_logging_quiets_noisy_third_party_loggers() -> None:
    configure_logging(debug=True)
    for noisy in ("httpx", "httpcore", "uvicorn.access", "docker", "asyncio"):
        assert logging.getLogger(noisy).level == logging.WARNING
