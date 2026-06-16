from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from maistro_evolve.benchmarks.datasets import TERMINALBENCH_SAMPLES
from maistro_evolve.benchmarks.terminalbench import run_terminalbench_samples
from maistro_evolve.providers.codex_cli import CodexCliProvider
from maistro_evolve.types import DAGTopology, EvalWeights, NodeGenome, PipelineGenome


def _fake_codex(tmp_path: Path) -> tuple[str, ...]:
    script = tmp_path / "fake_codex.py"
    script.write_text(
        """
import pathlib
import sys

args = sys.argv[1:]
output = pathlib.Path(args[args.index("--output-last-message") + 1])
prompt = sys.stdin.read()
output.write_text(f"ANSWER:{prompt}", encoding="utf-8")
""".strip(),
        encoding="utf-8",
    )
    return sys.executable, str(script)


@pytest.mark.asyncio
async def test_codex_provider_matches_evolve_llm_call_shape(tmp_path: Path) -> None:
    provider = CodexCliProvider(command_prefix=_fake_codex(tmp_path))

    response = await provider(
        [{"role": "system", "content": "Be exact."}, {"role": "user", "content": "Say hi."}],
        temperature=0.0,
        max_tokens=20,
    )

    assert response.startswith("ANSWER:Respond to the following conversation.")
    assert '"Say hi."' in response


@pytest.mark.asyncio
async def test_codex_provider_passes_model_and_read_only_flags(tmp_path: Path) -> None:
    script = tmp_path / "inspect_args.py"
    script.write_text(
        """
import pathlib
import sys

args = sys.argv[1:]
output = pathlib.Path(args[args.index("--output-last-message") + 1])
output.write_text("|".join(args), encoding="utf-8")
""".strip(),
        encoding="utf-8",
    )
    provider = CodexCliProvider(model="gpt-5.4-mini", command_prefix=(sys.executable, str(script)))

    response = await provider("hello")

    assert "--sandbox|read-only" in response
    assert "--skip-git-repo-check" in response
    assert "--model|gpt-5.4-mini" in response


@pytest.mark.asyncio
async def test_codex_provider_drives_terminalbench_sample(tmp_path: Path) -> None:
    script = tmp_path / "terminal_codex.py"
    script.write_text(
        """
import pathlib
import sys

args = sys.argv[1:]
output = pathlib.Path(args[args.index("--output-last-message") + 1])
prompt = sys.stdin.read()
assert "Show the last 50 lines" in prompt
output.write_text("```bash\\ntail -fn 50 app.log\\n```", encoding="utf-8")
""".strip(),
        encoding="utf-8",
    )
    provider = CodexCliProvider(command_prefix=(sys.executable, str(script)))
    now = datetime.now(UTC).isoformat()
    genome = PipelineGenome(
        id="codex-terminal",
        name="codex-terminal",
        topology=DAGTopology(
            nodes=[
                NodeGenome(
                    id="queen",
                    role="queen",
                    strategy="react",
                    model="codex",
                    temperature=0.0,
                    max_tokens=256,
                    system_prompt="Answer exactly.",
                    max_tool_rounds=0,
                )
            ],
            edges=[],
            entry_node="queen",
            max_cycles=1,
            beam_width=1,
            use_scout=False,
        ),
        eval_weights=EvalWeights(),
        created_at=now,
        updated_at=now,
    )
    sample = next(sample for sample in TERMINALBENCH_SAMPLES if sample["id"] == "tb_03")

    result = await run_terminalbench_samples(genome, provider, [sample])

    assert result.samples_evaluated == 1
    assert result.score == 1.0
