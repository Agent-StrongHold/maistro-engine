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
from datetime import datetime, timezone
from pathlib import Path

import structlog

from maistro.agents.types import AgentRole, HyperagentOutput, NodeConfig, OptimizationSignal

logger = structlog.get_logger()

_JSON_FENCE = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)
_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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
                await logger.awarning(
                    "obsidian_signal_load_error", path=str(path), error=str(exc)
                )

        return signals

    # --- Node configs (human-editable prompts) --------------------------------

    async def save_node_config(
        self, task_type: str, role: AgentRole, config: NodeConfig
    ) -> None:
        """Write the node config as an editable markdown file.

        The system prompt is stored as plain text body — engineers can open the
        file in Obsidian, edit the prompt directly, and the next run picks it up.
        The JSON block is omitted intentionally to keep the file readable.
        """
        ts = _utcnow()
        temp_override = config.temperature
        frontmatter = (
            f"---\n"
            f'role: "{role}"\n'
            f'task_type: "{task_type}"\n'
            f'updated: "{ts}"\n'
            f"temperature: {temp_override if temp_override is not None else 'null'}\n"
            f"---\n"
        )
        prompt_body = config.system_prompt or ""
        content = (
            frontmatter
            + f"\n<!-- Edit the prompt below. Changes are picked up on the next run. -->\n\n"
            + prompt_body
            + "\n"
        )
        path = self._config_dir(task_type) / f"{role}.md"
        await asyncio.to_thread(_write_file, path, content)
        await logger.ainfo("obsidian_config_saved", role=role, task_type=task_type, path=str(path))

    async def load_node_configs(self, task_type: str) -> dict[AgentRole, NodeConfig]:
        """Read node configs, including any human edits made in Obsidian."""
        dir_ = self._config_dir(task_type)
        if not dir_.exists():
            return {}

        configs: dict[AgentRole, NodeConfig] = {}

        for path in dir_.glob("*.md"):
            try:
                text = await asyncio.to_thread(_read_file, path)

                # Extract frontmatter for temperature override
                fm_match = _FRONTMATTER.match(text)
                temperature: float | None = None
                role_str: str = path.stem  # filename without .md = role name

                if fm_match:
                    for line in fm_match.group(1).splitlines():
                        if line.startswith("role:"):
                            role_str = line.split(":", 1)[1].strip().strip('"')
                        elif line.startswith("temperature:") and "null" not in line:
                            try:
                                temperature = float(line.split(":", 1)[1].strip())
                            except ValueError:
                                pass

                # Prompt is everything after the frontmatter and the comment line
                after_fm = _FRONTMATTER.sub("", text).strip()
                # Strip the editor comment if present
                prompt = re.sub(
                    r"^<!--.*?-->\s*", "", after_fm, flags=re.DOTALL
                ).strip()

                try:
                    role = AgentRole(role_str)
                except ValueError:
                    continue  # skip unrecognised role files

                configs[role] = NodeConfig(
                    role=role,
                    system_prompt=prompt or None,
                    temperature=temperature,
                )

            except Exception as exc:
                await logger.awarning(
                    "obsidian_config_load_error", path=str(path), error=str(exc)
                )

        return configs
