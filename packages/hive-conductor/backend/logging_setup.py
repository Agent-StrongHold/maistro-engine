"""Configure verbose console logging for local PM POC debugging."""

from __future__ import annotations

import logging
import os
import sys

_CONFIGURED = False


def configure_logging() -> str:
    """Apply log level from HIVE_LOG_LEVEL / PM mode. Returns active level name."""
    global _CONFIGURED
    if _CONFIGURED:
        return logging.getLogger().level

    from settings_defaults import is_pm_poc_mode

    level_name = os.getenv("HIVE_LOG_LEVEL", "").strip().lower()
    if not level_name and is_pm_poc_mode():
        level_name = "debug"
    if not level_name:
        level_name = "info"

    level = getattr(logging, level_name.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(level)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        root.addHandler(handler)

    for name in ("hive", "hive.engine", "hive.auth_middleware", "hive.request", "maistro"):
        logging.getLogger(name).setLevel(level)

    logging.getLogger("uvicorn.access").setLevel(
        logging.INFO if level <= logging.DEBUG else logging.WARNING
    )

    _CONFIGURED = True
    logging.getLogger("hive").info(
        "logging configured level=%s pm_poc=%s",
        level_name,
        is_pm_poc_mode(),
    )
    return level_name
