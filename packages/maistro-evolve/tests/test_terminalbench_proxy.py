from __future__ import annotations

from maistro_evolve.benchmarks.datasets import TERMINALBENCH_SAMPLES
from maistro_evolve.benchmarks.terminalbench import score_terminal_response


def test_public_terminal_proxy_scorer_distinguishes_partial_and_complete_commands() -> None:
    sample = next(sample for sample in TERMINALBENCH_SAMPLES if sample["id"] == "tb_03")

    partial = score_terminal_response("```bash\ntail app.log\n```", sample)
    complete = score_terminal_response("```bash\ntail -fn 50 app.log\n```", sample)

    assert partial == 0.5
    assert complete == 1.0
