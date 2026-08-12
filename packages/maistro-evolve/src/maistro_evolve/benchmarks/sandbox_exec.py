"""Execute model-generated benchmark code inside MAIstro's Docker sandbox.

The proxy SWE-bench evaluator receives raw LLM output, so candidate code is
untrusted by definition. It must never execute directly on the evaluator host.
This module therefore delegates execution to ``maistro.tools.sandbox`` and
fails closed when the isolated runtime is unavailable.

The sandbox provides the controls the benchmark needs at this trust boundary:
network isolation, bounded memory/CPU/PIDs, a restricted temporary workspace
mount, environment sanitization, timeout handling, and container teardown.
``maistro-evolve`` intentionally does not add a package dependency on
``maistro-core`` because the dependency direction is otherwise reversed. The
import is runtime-only: MAIstro's integrated RSI/evolve runtime provides core;
a standalone evolve installation simply cannot execute this untrusted-code
benchmark and returns a failed check instead of weakening isolation.
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path
from typing import Any

_DEFAULT_TIMEOUT = 10.0
_MAX_OUTPUT_CHARS = 500
_PASS_MARKER = "PASS"


def _build_check_script(
    code: str, function_name: str, call_args: list[Any], expected_value: Any
) -> str:
    """Candidate code followed by a real call + comparison, as plain source.

    ``call_args``/``expected_value`` come only from the maintainer-authored
    evaluator dataset, never from model output. The expected value is evaluated
    in a separate namespace so candidate globals cannot accidentally rebind
    names used by values such as ``datetime``.
    """
    expected_expr = repr(expected_value)
    return (
        f"{code}\n\n"
        "import datetime as _maistro_datetime_module\n"
        f"_result = {function_name}(*{call_args!r})\n"
        f"_expected = eval({expected_expr!r}, {'{'}'datetime': _maistro_datetime_module{'}'})\n"
        "print('PASS' if _result == _expected else "
        "f'FAIL: got {_result!r}, expected {_expected!r}')\n"
    )


async def run_function_check(
    code: str,
    function_name: str,
    call_args: list[Any],
    expected_value: Any,
    *,
    timeout: float = _DEFAULT_TIMEOUT,
) -> tuple[bool, str]:
    """Run one candidate assertion in the isolated Docker sandbox.

    Returns ``(passed, detail)``. There is deliberately no host-process
    fallback: if Docker/core sandbox support is unavailable, the check fails
    rather than executing model-generated Python with host filesystem/network
    access.
    """
    script = _build_check_script(code, function_name, call_args, expected_value)

    try:
        from maistro.config.settings import SandboxSettings
        from maistro.tools.sandbox.docker import create_sandbox
    except ImportError as exc:
        return False, f"isolated sandbox unavailable: {exc}"[:_MAX_OUTPUT_CHARS]

    # ``ensure_workspace`` only permits MAIstro's dedicated temporary root (or
    # /repos). Build the evaluator directory under that root rather than using
    # an arbitrary tempfile path that the sandbox correctly refuses to mount.
    sandbox_root = Path(tempfile.gettempdir()) / "maistro-workspace" / "swebench-eval"
    sandbox_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="case-", dir=sandbox_root) as tmp_name:
        tmp = Path(tmp_name)
        (tmp / "check.py").write_text(script, encoding="utf-8")

        # Keep the container alive slightly longer than the per-command budget;
        # network isolation is forced on even if an operator's general sandbox
        # defaults are looser.
        settings = SandboxSettings(
            memory_limit="256m",
            cpu_count=1,
            timeout=max(15, math.ceil(timeout) + 5),
            network_disabled=True,
        )

        try:
            sandbox = await create_sandbox(str(tmp), settings=settings, env={})
            async with sandbox:
                exit_code, output = await sandbox.exec(
                    "python check.py",
                    timeout=max(1, math.ceil(timeout)),
                )
        except (FileNotFoundError, PermissionError, RuntimeError, ValueError, OSError) as exc:
            return False, f"isolated sandbox unavailable: {exc}"[:_MAX_OUTPUT_CHARS]

    output = output.strip()
    if exit_code != 0:
        detail = output or f"exit code {exit_code}"
        return False, detail[:_MAX_OUTPUT_CHARS]
    if output == _PASS_MARKER:
        return True, "ok"
    return False, (output or "no PASS marker in output")[:_MAX_OUTPUT_CHARS]
