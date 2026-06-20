"""maistro-rsi — recursive self-improvement on the agent's own codebase.

Wires together three things that already exist in the monorepo:

- An isolated execution environment (`maistro_rsi.sandbox`), abstracted behind
  the `MicroVmSandbox` protocol so the eventual backend (Firecracker, E2B,
  gVisor — ADR pending) is a swap-in, not a rewrite.
- The self-branch workflow (`maistro_rsi.selfbranch`), which reuses
  `maistro.tools.git` to clone, branch, patch, test, and propose changes to
  this very repository from inside a sandbox.
- The benchmark/tournament/fitness stack from `maistro_evolve` — extended
  here with longer-horizon adapters (e.g. SWE-Bench Pro) — to score whether a
  self-modification is actually an improvement before it's allowed out as a PR.

`maistro_rsi.quota_burn` adds a scheduler that spreads cycles across whatever
models the connected LiteLLM instance exposes, favoring the ones with the
most idle free-tier headroom so unused allowances get exercised.
"""

from __future__ import annotations

from maistro_rsi.coordinator import (
    CoordinatorResult,
    ExecutionReport,
    ExecutorFn,
    HtrContext,
    HtrCoordinator,
    HypothesisProposer,
    report_from_cycle_result,
)
from maistro_rsi.htr import (
    HypothesisEvidence,
    HypothesisNode,
    HypothesisTree,
    NodeStatus,
)
from maistro_rsi.protocols import ApplyPatchFn, MicroVmSandbox
from maistro_rsi.runner import RsiCycle, RsiCycleConfig, RsiCycleResult

__all__ = [
    "ApplyPatchFn",
    "CoordinatorResult",
    "ExecutionReport",
    "ExecutorFn",
    "HtrContext",
    "HtrCoordinator",
    "HypothesisEvidence",
    "HypothesisNode",
    "HypothesisProposer",
    "HypothesisTree",
    "MicroVmSandbox",
    "NodeStatus",
    "RsiCycle",
    "RsiCycleConfig",
    "RsiCycleResult",
    "report_from_cycle_result",
]
