"""Obsidian vault implementation of WorkingMemoryProtocol.

Vault layout
────────────
<vault>/
  traces/          one .md per HyperagentOutput run
  signals/         one .md per OptimizationSignal
  node-configs/
    <task-type>/   one .md per AgentRole — directly editable by humans
  blackboards/     (future: checkpointed GraphBlackboard snapshots)

Storage format
──────────────
Each file has YAML-ish frontmatter followed by a fenced JSON block that holds
the full Pydantic model, followed by a human-readable summary section.

  ---
  run_id: abc123
  task: "..."
  timestamp: "2026-05-06T10:00:00"
  ...
  ---
  ```json
  { ...full model JSON... }
  ```
  ## Summary
  ...human-readable text...

Node config files are special: the prompt lives as plain text in the markdown
body (after the frontmatter) so engineers can edit it directly in Obsidian.
The optimizer writes the prompt; humans can correct it; load_node_configs
reads the corrected version back.  The JSON block is omitted for these files
so the file stays readable and diff-friendly.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import structlog

from maistro.agents.types import AgentRole, HyperagentOutput, NodeConfig, OptimizationSignal

logger = structlog.get_logger()

_JSON_FENCE = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)
_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def _utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_json_block(text: str) -> dict | None:
    m = _JSON_FENCE.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _trace_summary(trace: HyperagentOutput) -> str:
    roles = [r.role for r in trace.node_results]
    score = trace.review.score if trace.review else None
    score_str = f"{score:.1f}/10" if score is not None else "n/a"
    files = trace.code.files_changed if trace.code else []
    return (
        f"**Success**: {'✅' if trace.success else '❌'}  \n"
        f"**Cycles**: {trace.total_cycles}  \n"
        f"**Review score**: {score_str}  \n"
        f"**Nodes run**: {', '.join(roles)}  \n"
        f"**Files changed**: {', '.join(files) or 'none'}  \n"
    )


def _render_config_markdown(config: NodeConfig) -> str:
    """Generate the human-readable Markdown preview section for a node config.

    Called by save_node_config to regenerate the display whenever the JSON
    changes.  load_node_configs ignores this section entirely — JSON is the
    source of truth.
    """
    prompt = config.system_prompt or "_No system prompt set._"
    temp_line = (
        f"- **Temperature**: `{config.temperature}`"
        if config.temperature is not None
        else "- **Temperature**: model default"
    )
    return (
        f"## System Prompt\n\n"
        f"{prompt}\n\n"
        f"## Configuration\n\n"
        f"{temp_line}\n\n"
        f"---\n"
        f"_Markdown preview auto-generated from the JSON block above. "
        f"Edit the JSON to change the config; this section is overwritten on the next save._\n"
    )


def _signal_summary(signal: OptimizationSignal) -> str:
    lines = [
        f"**Weakest node**: {signal.weakest_node}  ",
        f"**Total runs analysed**: {signal.total_runs}  ",
    ]
    if signal.avg_review_score is not None:
        lines.append(f"**Avg review score**: {signal.avg_review_score:.1f}/10  ")
    lines.append("")
    lines.append("| Node | Runs | Success | Tokens | Bottleneck |")
    lines.append("|------|------|---------|--------|------------|")
    for m in signal.node_metrics:
        lines.append(
            f"| {m.role} | {m.run_count} | {m.success_rate:.0%} "
            f"| {m.avg_tokens:.0f} | {m.bottleneck_score:.2f} |"
        )
    return "\n".join(lines)


class ObsidianMemoryStore:
    """WorkingMemoryProtocol backed by an Obsidian vault directory.

    Args:
        vault_path: Absolute path to the Obsidian vault root.  The store
                    creates subdirectories automatically.
    """

    def __init__(self, vault_path: str | Path) -> None:
        self.vault = Path(vault_path)

    def _traces_dir(self) -> Path:
        return self.vault / "traces"

    def _signals_dir(self) -> Path:
        return self.vault / "signals"

    def _config_dir(self, task_type: str) -> Path:
        return self.vault / "node-configs" / task_type

    # --- Traces ---------------------------------------------------------------

    async def save_trace(self, run_id: str, trace: HyperagentOutput) -> None:
        ts = _utcnow()
        task_snippet = ""
        if trace.blackboard:
            task_snippet = trace.blackboard.task_objective[:80].replace('"', "'")

        frontmatter = (
            f"---\n"
            f'run_id: "{run_id}"\n'
            f'task: "{task_snippet}"\n'
            f'timestamp: "{ts}"\n'
            f"success: {str(trace.success).lower()}\n"
            f"cycles: {trace.total_cycles}\n"
            f"review_score: {trace.review.score if trace.review else 'null'}\n"
            f"---\n"
        )
        json_block = f"```json\n{trace.model_dump_json(indent=2)}\n```\n"
        summary = f"## Summary\n{_trace_summary(trace)}\n"

        content = frontmatter + "\n" + json_block + "\n" + summary
        path = self._traces_dir() / f"{ts[:10]}-{run_id}.md"
        await asyncio.to_thread(_write_file, path, content)
        await logger.ainfo("obsidian_trace_saved", path=str(path))

    async def load_traces(self, limit: int = 10) -> list[HyperagentOutput]:
        dir_ = self._traces_dir()
        if not dir_.exists():
            return []

        paths = sorted(dir_.glob("*.md"), reverse=True)[:limit]
        traces: list[HyperagentOutput] = []

        for path in paths:
            try:
                text = await asyncio.to_thread(_read_file, path)
                data = _extract_json_block(text)
                if data:
                    traces.append(HyperagentOutput.model_validate(data))
            except Exception as exc:
                await logger.awarning("obsidian_trace_load_error", path=str(path), error=str(exc))

        return traces

    # --- Signals --------------------------------------------------------------

    async def save_signal(self, run_id: str, signal: OptimizationSignal) -> None:
        ts = _utcnow()
        frontmatter = (
            f"---\n"
            f'run_id: "{run_id}"\n'
            f'timestamp: "{ts}"\n'
            f'weakest_node: "{signal.weakest_node}"\n'
            f"total_runs: {signal.total_runs}\n"
            f"avg_review_score: {signal.avg_review_score if signal.avg_review_score is not None else 'null'}\n"
            f"---\n"
        )
        json_block = f"```json\n{signal.model_dump_json(indent=2)}\n```\n"
        summary = f"## Summary\n{_signal_summary(signal)}\n"

        content = frontmatter + "\n" + json_block + "\n" + summary
        path = self._signals_dir() / f"{ts[:10]}-{run_id}.md"
        await asyncio.to_thread(_write_file, path, content)
        await logger.ainfo("obsidian_signal_saved", path=str(path))

    async def load_signals(self, limit: int = 5) -> list[OptimizationSignal]:
        dir_ = self._signals_dir()
        if not dir_.exists():
            return []

        paths = sorted(dir_.glob("*.md"), reverse=True)[:limit]
        signals: list[OptimizationSignal] = []

        for path in paths:
            try:
                text = await asyncio.to_thread(_read_file, path)
                data = _extract_json_block(text)
                if data:
                    signals.append(OptimizationSignal.model_validate(data))
            except Exception as exc:
                await logger.awarning("obsidian_signal_load_error", path=str(path), error=str(exc))

        return signals

    # --- Node configs (JSON source of truth + Markdown for readability) --------

    async def save_node_config(self, task_type: str, role: AgentRole, config: NodeConfig) -> None:
        """Persist a node config as YAML frontmatter + fenced JSON + Markdown preview.

        File layout
        ───────────
        ---                          ← YAML frontmatter (metadata only)
        role: "planner"
        task_type: "engineering-task"
        updated: "2026-05-06T12:00:00+00:00"
        ---

        ```json                      ← source of truth — load_node_configs reads this
        { "role": ..., "system_prompt": ..., "temperature": ... }
        ```

        ## System Prompt             ← human-readable preview, auto-regenerated
        ...prompt text...

        ## Configuration
        - Temperature: ...

        Engineers can read and understand the config in Obsidian.  To change a
        prompt, edit the JSON block — the Markdown preview is regenerated
        automatically on the next save_node_config call.  load_node_configs
        always reads from the JSON block so parse errors never silently
        corrupt the loaded config.
        """
        ts = _utcnow()
        frontmatter = f'---\nrole: "{role}"\ntask_type: "{task_type}"\nupdated: "{ts}"\n---\n'
        json_block = f"```json\n{config.model_dump_json(indent=2)}\n```\n"
        md_preview = _render_config_markdown(config)
        content = frontmatter + "\n" + json_block + "\n" + md_preview
        path = self._config_dir(task_type) / f"{role}.md"
        await asyncio.to_thread(_write_file, path, content)
        await logger.ainfo("obsidian_config_saved", role=role, task_type=task_type, path=str(path))

    async def load_node_configs(self, task_type: str) -> dict[AgentRole, NodeConfig]:
        """Read node configs from the fenced JSON block in each role file.

        The JSON block is the source of truth.  The Markdown preview section is
        ignored during loading so human annotations there don't corrupt the config.
        Returns an empty dict when the directory doesn't exist yet (first run).
        """
        dir_ = self._config_dir(task_type)
        if not dir_.exists():
            return {}

        configs: dict[AgentRole, NodeConfig] = {}

        for path in dir_.glob("*.md"):
            try:
                text = await asyncio.to_thread(_read_file, path)
                data = _extract_json_block(text)
                if data is None:
                    await logger.awarning("obsidian_config_no_json", path=str(path))
                    continue

                config = NodeConfig.model_validate(data)
                configs[config.role] = config

            except Exception as exc:
                await logger.awarning("obsidian_config_load_error", path=str(path), error=str(exc))

        return configs
