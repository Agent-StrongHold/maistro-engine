"""maistro-evolve: Elo tournament optimizer for agent self-improvement.

v1 stability statement (SPEC-202): this package's public API/CLI contract
guarantees a genome-evolution pipeline (crossover, mutation, tournament
selection, fitness scoring) that runs against seven named benchmarks —
``ifeval``, ``bfcl``, ``swebench``, ``tau_bench``, ``gaia``, ``ragas``,
``terminalbench`` (``osworld`` is defined but not runnable; it has no scoring
implementation). None of the seven run the official published benchmark
harness against the official dataset: they score real model output at a
small, handcrafted scale (see ``benchmarks/datasets.py``). Six score by a
genuine structural check (rule verification, exact-match, tool-call recall,
or real sandboxed execution); ``ragas`` is the exception and scores
primarily by keyword/word overlap. Best-effort, not guaranteed: the specific
sample sets, exact scores for a given genome, and which model rosters are
exercised in CI. Full per-benchmark detail lives in this package's
``CLAUDE.md``.
"""

from __future__ import annotations

import importlib.metadata

# Single source of truth for version — read from installed package metadata.
try:
    __version__ = importlib.metadata.version("maistro-evolve")
except importlib.metadata.PackageNotFoundError:  # pragma: no cover - editable/unbuilt checkout
    __version__ = "0.9.0-dev"
