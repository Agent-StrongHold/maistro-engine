"""Agent-backed ``ApplyPatchFn`` drivers: turn a CLI coding agent into the RSI
cycle's code-modification step.

The RSI cycle's ``apply_patch`` seam (`protocols.ApplyPatchFn`) is "given a
sandbox and a checked-out workspace, mutate the code." Any non-interactive CLI
coding agent can fill it — the agent runs *inside* the sandbox (provided there
by the sbx kit or the sandbox image), edits the checkout in place, and the
surrounding `selfbranch` plumbing commits, diffs, tests, and quarantines the
result. One generic template driver therefore covers opencode, claude, or any
future agent; the builders-pipeline driver (Phase B) slots in beside it as just
another ``ApplyPatchFn`` factory.
"""

from __future__ import annotations

import shlex

import structlog

from maistro_rsi.protocols import ApplyPatchFn, MicroVmSandbox

logger = structlog.get_logger()

#: Default agent template: opencode's non-interactive one-shot run. ``--auto``
#: auto-approves opencode's in-sandbox tool use; the sandbox is the containment.
OPENCODE_TEMPLATE = "opencode run --auto {prompt}"

_DEFAULT_AGENT_TIMEOUT_S = 900


class ApplyPatchError(RuntimeError):
    """The agent command failed — surfaced so the cycle's failure accounting
    (and the HTR tree's dead-end pruning) sees a real error, not a silent
    empty diff."""


def command_apply_patch(
    prompt: str,
    *,
    template: str = OPENCODE_TEMPLATE,
    timeout: int = _DEFAULT_AGENT_TIMEOUT_S,
) -> ApplyPatchFn:
    """Build an ``ApplyPatchFn`` that runs a CLI coding agent over the workspace.

    ``template`` is a shell-command template with a ``{prompt}`` placeholder
    (and, optionally, a ``{model}`` placeholder -- filled from the quota-burn
    scheduler's per-cycle choice, e.g. ``"opencode run --model {model} --auto
    {prompt}"``); both are shlex-quoted before substitution so hypothesis text
    or a model id can never smuggle shell syntax into the command. Formatting
    happens per call (not at construction) since the model is only known once
    ``RsiCycle.run`` picks it. The command runs via ``sandbox.exec`` (i.e.
    inside the isolation boundary) and a non-zero exit raises
    :class:`ApplyPatchError`.
    """
    quoted_prompt = shlex.quote(prompt)

    async def _patch(sandbox: MicroVmSandbox, workspace: str, model: str | None = None) -> None:
        command = template.format(
            prompt=quoted_prompt,
            model=shlex.quote(model) if model else "",
        )
        exit_code, output = await sandbox.exec(command, timeout=timeout)
        await logger.ainfo(
            "rsi_apply_agent_complete",
            workspace=workspace,
            exit_code=exit_code,
            output_tail=output[-400:],
        )
        if exit_code != 0:
            raise ApplyPatchError(f"agent command exited {exit_code}: {output[-400:]}")

    return _patch


__all__ = ["OPENCODE_TEMPLATE", "ApplyPatchError", "command_apply_patch"]
