"""Safe default sandbox backend registration."""

from __future__ import annotations

import os

from maistro.sandbox.backends.kata import KataSandboxBackend
from maistro.sandbox.selector import SandboxSelector


def build_default_selector() -> SandboxSelector:
    """Build the production selector without registering weaker fallbacks."""
    requested = os.environ.get("MAISTRO_SANDBOX_BACKEND", "auto").strip().lower()
    if requested not in {"auto", "kata"}:
        raise ValueError(
            f"Unsupported MAISTRO_SANDBOX_BACKEND={requested!r}; secure Builders supports 'kata'"
        )

    selector = SandboxSelector()
    kata = KataSandboxBackend()
    if kata.is_available():
        selector.register("vm", kata)
    return selector
