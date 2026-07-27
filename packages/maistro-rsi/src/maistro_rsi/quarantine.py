"""Quarantine gate: scan and (when warranted) escalate every self-modification
before it's allowed out of the sandbox.

`maistro-rsi` deliberately does **not** carve out "files the agent may never
touch" — an RSI loop that can't propose changes to its own harness, sandbox
control, or security wiring isn't recursive, it's just a code-fixing bot with
extra steps. The actual safety property we want is narrower and stronger:
nothing self-modified reaches the outside world (a PR, a promoted genome)
without being scanned by Warden — the same content scanner that runs at every
other trust boundary in this codebase — and, when the diff touches the agent's
own cage, an additional adversarial review pass on top of the full test suite.

This is the seam where Sentinel/RedTeam-style adversarial review plugs in:
`AdversarialReview` is a protocol so the actual reviewer (an LLM judge, a
RedTeam agent persona, a human-in-the-loop queue) is swappable without
touching the gate logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from maistro.security.warden.detector import Warden

# Path fragments that mark the agent's own containment surface: sandbox
# control, security wiring, the self-modification pipeline itself, and the
# DAG-synthesis substrate that lets an agent spawn further sub-agents/DAGs
# (the recursion-depth cap and the two node kinds that dispatch through it).
# A diff touching any of these isn't blocked — it's escalated to require
# adversarial review on top of Warden + the full test suite, because a change
# here changes what *future* self-modifications are allowed to get away with.
SENSITIVE_PATH_PATTERNS: tuple[str, ...] = (
    "maistro_rsi/sandbox/",
    "maistro_rsi/quarantine.py",
    "maistro_rsi/selfbranch.py",
    "maistro_rsi/runner.py",
    "maistro_rsi/coordinator.py",
    "maistro/security/",
    "maistro/tools/sandbox/",
    "maistro/graph/depth.py",
    "maistro/graph/nodes/agent_synth_dag.py",
    "maistro/graph/nodes/agent_spawn_harness.py",
    # The driver that wires the quarantine check, and the module that builds the
    # shell command every cycle executes. `runner.py` and `coordinator.py` were
    # protected while the code constructing them was not, so a diff editing the
    # agent's own command template cleared on Warden alone.
    "maistro_rsi/autorun.py",
    "maistro_rsi/apply_agents.py",
    # Depth/attempt state that survives sandbox disposal — the budgets bounding
    # how far a run may go.
    "maistro_rsi/durable_runs/",
    # SafeHarnessRunner composes Warden and the ActionGate but lives under
    # capabilities/, so the "maistro/security/" pattern above never saw it.
    "maistro/capabilities/providers/",
    # Cumulative action-budget enforcement.
    "maistro/policy/",
    # The gates themselves, and the ratchet baselines they read. Previously the
    # only thing standing between the loop and its own CI config was a sentence
    # in a prompt telling the model not to touch it.
    ".github/",
    "quality/",
    # The sandbox kit: it sets the backend *and* attests the isolation that
    # makes LocalSandbox safe (see sandbox/microvm.py).
    "sbx/",
)


class AdversarialReview(Protocol):
    """A reviewer that judges whether a sensitive-surface diff is safe to promote.

    Implementations might be an LLM judge prompted adversarially, a dedicated
    RedTeam agent persona (see `hive-conductor` "RedTeam" guard role), or a
    human-in-the-loop approval queue — the gate doesn't care which, only that
    one ran and rendered a verdict.
    """

    async def review(self, diff: str, touched_paths: list[str]) -> bool:
        """Return True if the diff is cleared to proceed."""
        ...


@dataclass
class QuarantineVerdict:
    cleared: bool
    requires_adversarial_review: bool
    flags: tuple[str, ...]
    reason: str | None = None


def _touches_sensitive_surface(touched_paths: list[str]) -> list[str]:
    return [
        path
        for path in touched_paths
        if any(pattern in path for pattern in SENSITIVE_PATH_PATTERNS)
    ]


async def quarantine_scan(
    diff: str,
    touched_paths: list[str],
    warden: Warden,
    *,
    adversarial_review: AdversarialReview | None = None,
) -> QuarantineVerdict:
    """Scan a self-modification diff and decide whether it may leave the sandbox.

    Order of checks mirrors severity: a Warden-flagged diff never clears
    regardless of which files it touches (quarantine-1). A clean diff that
    only touches ordinary application surface clears immediately
    (quarantine-2). A clean diff that touches the agent's own containment
    surface is escalated — it clears only once an adversarial review has run
    and passed (quarantine-3, quarantine-4). Warden's flags are always
    surfaced verbatim; quarantine is an audit trail, not a summary
    (quarantine-5).
    """
    verdict = await warden.scan(diff, boundary="self_modification")
    sensitive = _touches_sensitive_surface(touched_paths)
    requires_review = bool(sensitive)

    if not verdict.clean:
        return QuarantineVerdict(
            cleared=False,
            requires_adversarial_review=requires_review,
            flags=verdict.flags,
            reason="warden_flagged_diff",
        )

    if not requires_review:
        return QuarantineVerdict(
            cleared=True,
            requires_adversarial_review=False,
            flags=verdict.flags,
        )

    if adversarial_review is None:
        return QuarantineVerdict(
            cleared=False,
            requires_adversarial_review=True,
            flags=verdict.flags,
            reason=f"sensitive_surface_pending_review:{','.join(sensitive)}",
        )

    approved = await adversarial_review.review(diff, touched_paths)
    return QuarantineVerdict(
        cleared=approved,
        requires_adversarial_review=True,
        flags=verdict.flags,
        reason=None if approved else "adversarial_review_rejected",
    )
