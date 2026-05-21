from __future__ import annotations

from .ifeval import run_ifeval
from .bfcl import run_bfcl
from .swebench import run_swebench
from .terminalbench import run_terminalbench
from .tau_bench import run_tau_bench
from .gaia import run_gaia
from .ragas import run_ragas
from .osworld import run_osworld

REAL_BENCHMARKS = {
    "ifeval": run_ifeval,
    "bfcl": run_bfcl,
    "swebench": run_swebench,
    "terminalbench": run_terminalbench,
    "tau_bench": run_tau_bench,
    "gaia": run_gaia,
    "ragas": run_ragas,
    "osworld": run_osworld,
}
