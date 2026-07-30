from __future__ import annotations

from .bfcl import run_bfcl
from .gaia import run_gaia
from .ifeval import run_ifeval
from .ifeval_real import IFEvalUnavailableError, run_ifeval_real
from .osworld import run_osworld
from .ragas import run_ragas
from .swebench import run_swebench
from .tau_bench import run_tau_bench
from .terminalbench import run_terminalbench

# Small handcrafted/lite sample sets, NOT the official benchmark corpora
# despite sharing their names (SPEC-202). The scoring methodology is real —
# ifeval/gaia/bfcl/tau_bench/ragas apply the same kind of check the official
# benchmark does (rule verification, exact-match, tool-call matching), and
# swebench/terminalbench execute the candidate and verify a real outcome
# (assertion / filesystem state) — just at a much smaller, cheaper scale than
# the official dataset + harness ("real" tier, not yet implemented for any
# benchmark).
#
# osworld is deliberately NOT registered here: there is no honest way to
# score it without real desktop-VM infrastructure that does not exist in
# this repo. run_osworld raises rather than producing any score — see
# osworld.py.
PROXY_BENCHMARKS = {
    "ifeval": run_ifeval,
    "bfcl": run_bfcl,
    "swebench": run_swebench,
    "terminalbench": run_terminalbench,
    "tau_bench": run_tau_bench,
    "gaia": run_gaia,
    "ragas": run_ragas,
}

# Official dataset + official harness (SPEC-202's `real` tier). One entry, not
# seven: a name only belongs here once its score is comparable to a published
# one. IFEval qualified first because its grader is deterministic Python over
# response text — no container, no reference solution, no judge model — so the
# entire cost of making it real was 541 LLM calls. See ifeval_real.py.
#
# Registration is not the same as availability: the real IFEval adapter needs
# the `ifeval` extra installed and its vendored corpus intact, and raises
# IFEvalUnavailableError rather than downgrading if either is missing.
REAL_BENCHMARKS = {
    "ifeval": run_ifeval_real,
}

__all__ = [
    "PROXY_BENCHMARKS",
    "REAL_BENCHMARKS",
    "IFEvalUnavailableError",
    "run_osworld",
]
