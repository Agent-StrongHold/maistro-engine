"""Minimal, self-contained subprocess sandbox for checking model-generated code.

Executes a candidate function against a real assertion (call it, compare the
return value to a known-good expected value) instead of scoring the response
text with keyword/line-diff heuristics. This is genuine pass/fail signal, not
an approximation of one.

Isolation posture — read before reusing elsewhere: this provides **process-level
isolation only** (subprocess boundary, wall-clock timeout, process-group kill on
timeout — mirroring the tested pattern in
``maistro_rsi.sandbox.local.LocalSandbox.exec``). It does **not** disable
networking, cap memory, or restrict the filesystem the way
``maistro.tools.sandbox.docker.SandboxContainer`` does. ``maistro-evolve`` has
zero dependency on ``maistro-core``/``maistro-rsi`` by design (see
``pyproject.toml``; the dependency direction is the reverse — ``maistro-rsi``
depends on ``maistro-evolve``), so this module stays self-contained rather than
reaching for that container-backed sandbox. That is a proportionate choice for
the current dataset (``SWEBENCH_SAMPLES`` — pure list/string/arithmetic
functions, no filesystem or network calls) and matches ``LocalSandbox``'s own
documented caveat that it provides no isolation of its own and must run inside
an already-isolated context. Do not point this at untrusted code in a
context that isn't already sandboxed (container, CI runner, VM).

POSIX-only (``start_new_session``/``os.killpg``), matching the same
precedent set by ``LocalSandbox.exec``.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys
import tempfile
from pathlib import Path
from typing import Any

_DEFAULT_TIMEOUT = 10.0
_MAX_OUTPUT_CHARS = 500
_REAP_GRACE_SECONDS = 1.0
_PASS_MARKER = "PASS"


def _build_check_script(
    code: str, function_name: str, call_args: list[Any], expected_value: Any
) -> str:
    """Candidate code followed by a real call + comparison, as plain source.

    ``call_args``/``expected_value`` come only from the maintainer-authored
    dataset (never from model output), so embedding their ``repr()`` is safe —
    ``repr()`` of the list/dict/str/int/None/datetime types used there always
    round-trips to valid Python source.

    The expected value's repr is evaluated in an isolated namespace (its own
    ``eval()`` globals dict, keyed only on a module reference the candidate
    code cannot see) rather than as plain top-level statements sharing the
    candidate's globals. A sample like swe_04's ``from datetime import
    datetime`` at module scope would otherwise rebind the name ``datetime`` in
    the shared namespace, and since Python functions resolve globals at *call*
    time, ``parse_date``'s later call to ``datetime.fromisoformat`` would
    silently resolve to whatever this harness bound that name to last.
    """
    expected_expr = repr(expected_value)
    return (
        f"{code}\n\n"
        "import datetime as _maistro_datetime_module\n"
        f"_result = {function_name}(*{call_args!r})\n"
        f"_expected = eval({expected_expr!r}, {{'datetime': _maistro_datetime_module}})\n"
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
    """Run ``function_name(*call_args)`` from ``code`` in a subprocess and
    compare the result to ``expected_value``.

    Returns ``(passed, detail)`` — ``detail`` is ``"ok"`` on pass, or a short
    (truncated) description of the failure: a mismatch, an exception from the
    candidate code, or a timeout.
    """
    script = _build_check_script(code, function_name, call_args, expected_value)
    with tempfile.TemporaryDirectory(prefix="maistro-swebench-") as tmp_name:
        tmp = Path(tmp_name)
        script_path = tmp / "check.py"
        script_path.write_text(script, encoding="utf-8")

        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(script_path),
            cwd=str(tmp),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={"PATH": os.environ.get("PATH", "")},
            start_new_session=True,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            # Kill the whole process group, not just the direct child — a
            # candidate "fix" that spawns children (or never terminates) must
            # not outlive the check.
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(proc.pid, signal.SIGKILL)
            proc.kill()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(proc.wait(), timeout=_REAP_GRACE_SECONDS)
            return False, f"timed out after {timeout}s"

    output = stdout.decode(errors="replace").strip()
    if proc.returncode != 0:
        detail = output or f"exit code {proc.returncode}"
        return False, detail[:_MAX_OUTPUT_CHARS]
    if output == _PASS_MARKER:
        return True, "ok"
    return False, (output or "no PASS marker in output")[:_MAX_OUTPUT_CHARS]
