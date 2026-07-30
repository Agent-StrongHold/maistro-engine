"""maistro-evolve: Elo tournament optimizer for agent self-improvement."""

from __future__ import annotations

import importlib.metadata

# Single source of truth for version — read from installed package metadata.
try:
    __version__ = importlib.metadata.version("maistro-evolve")
except importlib.metadata.PackageNotFoundError:  # pragma: no cover - editable/unbuilt checkout
    __version__ = "0.9.0-dev"
