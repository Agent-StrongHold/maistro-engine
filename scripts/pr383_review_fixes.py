from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(rel: str, old: str, new: str) -> None:
    path = ROOT / rel
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{rel}: expected exactly one match, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def write(rel: str, content: str) -> None:
    (ROOT / rel).write_text(content, encoding="utf-8")


# 1. State writer lifecycle: close the submit gate atomically before the drain
# marker, and make submit's check+enqueue one lifecycle operation.
state = "packages/maistro-core/src/maistro/state.py"
replace_once(
    state,
    "        self._writer_lock = threading.Lock()\n        self._writer_open = False\n",
    "        self._writer_lock = threading.Lock()\n"
    "        # Serializes writer lifecycle transitions with submit's check+enqueue.\n"
    "        # This is intentionally separate from _writer_lock, which protects\n"
    "        # SQLite statements and may be held by the writer thread.\n"
    "        self._writer_state_lock = threading.Lock()\n"
    "        self._writer_open = False\n",
)
replace_once(
    state,
    '''    def open_writer(self) -> sqlite3.Connection:\n        if self._writer_open:\n            raise RuntimeError("open_writer may be called exactly once")\n        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)\n        conn.execute("PRAGMA journal_mode=WAL")\n        conn.execute(\n            "CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TEXT)"\n        )\n        conn.commit()\n        self._writer = conn\n        self._writer_open = True\n\n        self._writer_thread = threading.Thread(target=self._writer_loop, daemon=True)\n        self._writer_thread.start()\n\n        return conn\n''',
    '''    def open_writer(self) -> sqlite3.Connection:\n        with self._writer_state_lock:\n            if self._writer_open:\n                raise RuntimeError("open_writer may be called exactly once")\n            conn = sqlite3.connect(str(self._db_path), check_same_thread=False)\n            conn.execute("PRAGMA journal_mode=WAL")\n            conn.execute(\n                "CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TEXT)"\n            )\n            conn.commit()\n            self._writer = conn\n            self._writer_open = True\n\n            self._writer_thread = threading.Thread(target=self._writer_loop, daemon=True)\n            self._writer_thread.start()\n\n            return conn\n''',
)
replace_once(
    state,
    '''        if not self._writer_open:\n            raise RuntimeError(\n                "State writer is not open: call open_writer() first, or this "\n                "State has been closed and can no longer accept writes"\n            )\n        try:\n            self._tx_queue.put_nowait(fn)\n        except queue.Full:\n            raise RuntimeError(\n                f"backpressure: submit queue full (depth={self._max_queue_depth})"\n            ) from None\n''',
    '''        with self._writer_state_lock:\n            if not self._writer_open:\n                raise RuntimeError(\n                    "State writer is not open: call open_writer() first, or this "\n                    "State has been closed and can no longer accept writes"\n                )\n            try:\n                self._tx_queue.put_nowait(fn)\n            except queue.Full:\n                raise RuntimeError(\n                    f"backpressure: submit queue full (depth={self._max_queue_depth})"\n                ) from None\n''',
)
replace_once(
    state,
    '''        if self._writer_thread is not None:\n            drained = threading.Event()\n''',
    '''        # Close the admission gate before enqueueing the drain marker. A\n        # submit that acquired this lock first has already put its transaction\n        # in the queue; every later submit observes _writer_open=False and is\n        # rejected, so nothing can land behind the marker and be lost.\n        with self._writer_state_lock:\n            self._writer_open = False\n            writer_thread = self._writer_thread\n\n        if writer_thread is not None:\n            drained = threading.Event()\n''',
)
replace_once(
    state,
    '''            self._shutdown.set()\n            self._writer_thread.join(timeout=timeout)\n            if self._writer_thread.is_alive():\n                logger.error("State.close: writer thread did not exit within %.1fs", timeout)\n            self._writer_thread = None\n''',
    '''            self._shutdown.set()\n            writer_thread.join(timeout=timeout)\n            if writer_thread.is_alive():\n                logger.error("State.close: writer thread did not exit within %.1fs", timeout)\n            self._writer_thread = None\n''',
)
replace_once(
    state,
    '''        # `submit()` must stop accepting work. Without this, `_writer_open`\n        # stayed True after close() and put() kept succeeding — the write was\n        # queued to a thread that would never run again and vanished silently,\n        # which is the exact fire-and-forget failure H7 exists to remove. The\n        # contract is "close() means the writes you handed me are on disk", and\n        # that has to include refusing writes handed over afterwards.\n        self._writer_open = False\n\n''',
    '''        # The submit gate was closed under _writer_state_lock before the\n        # drain marker was queued, so no accepted write can sit behind it.\n\n''',
)

# 2. Preserve the first durable-node start timestamp across retries.
replace_once(
    "packages/maistro-core/src/maistro/graph/durable_runs/executor.py",
    '                "started_at": node_record.started_at and datetime.now(UTC),\n',
    '                "started_at": node_record.started_at or datetime.now(UTC),\n',
)

# 3. Memory decay is healthy only when the driver is actually running.
health = "packages/hive-conductor/backend/routes/health.py"
replace_once(
    health,
    '    memory_decay_enabled = bool(memory_decay.get("enabled"))\n',
    '    memory_decay_enabled = memory_decay.get("state") == "running"\n',
)
replace_once(
    health,
    '    checks["memory_decay"] = bool(_memory_decay_state().get("enabled"))\n',
    '    checks["memory_decay"] = _memory_decay_state().get("state") == "running"\n',
)

# 4. Creating one's own workspace is an ordinary authenticated user operation.
# Nested workspace mutations retain their existing permission/elevation checks.
auth = "packages/hive-conductor/backend/middleware/auth.py"
replace_once(
    auth,
    '''        path = request.url.path\n        # Agent invoke (POST /v1/agents/{id}/invoke) is autonomous read — don't\n''',
    '''        path = request.url.path\n        # A workspace tab is the authenticated user's product ownership boundary,\n        # not an administrative mutation. Route-level ownership checks govern\n        # subsequent edits; requiring task-scoped elevation here made the daily\n        # account unable to use the workspace creation UI at all.\n        if request.method == "POST" and path.rstrip("/") == "/v1/workspaces":\n            return None\n        # Agent invoke (POST /v1/agents/{id}/invoke) is autonomous read — don't\n''',
)

# 5. Scope persona feedback to workspaces visible to the requester and cascade
# workspace deletion to the materialized agents it owns.
workspaces = "packages/hive-conductor/backend/routes/workspaces.py"
replace_once(
    workspaces,
    "from services.agent_materialization import materialize_workspace_agents\n",
    "from services.agent_materialization import materialize_workspace_agents, workspace_agents\n",
)
replace_once(
    workspaces,
    '''@router.get("/persona-templates/{persona_id}/feedback", response_model=PersonaFeedbackSummary)\ndef get_persona_feedback(persona_id: str) -> PersonaFeedbackSummary:\n    """Aggregated thumbs +/- across every workspace instantiating this\n    persona -- not scoped to one workspace, since the whole point is that\n    feedback steers the persona itself, wherever it's adopted."""\n    return summarize(persona_id, list(stores.persona_feedback.values()))\n''',
    '''@router.get("/persona-templates/{persona_id}/feedback", response_model=PersonaFeedbackSummary)\ndef get_persona_feedback(persona_id: str, request: Request) -> PersonaFeedbackSummary:\n    """Aggregate feedback only across workspaces visible to the requester.\n\n    Persona calibration is cross-workspace, but raw comments/user ids from a\n    private workspace are not. The summary remains persona-scoped while its\n    source rows respect the same workspace visibility boundary as the rest of\n    this router.\n    """\n    requester = _user_id(request)\n    visible_workspace_ids = {\n        workspace.id\n        for workspace in stores.workspaces.values()\n        if _visible_to(requester, workspace)\n    }\n    visible_feedback = [\n        feedback\n        for feedback in stores.persona_feedback.values()\n        if feedback.workspace_id in visible_workspace_ids\n    ]\n    return summarize(persona_id, visible_feedback)\n''',
)
replace_once(
    workspaces,
    '''    if _member_role(workspace, requester) != "owner":\n        raise HTTPException(status_code=403, detail="only an owner can delete this workspace")\n    stores.workspaces.pop(workspace_id, None)\n''',
    '''    if _member_role(workspace, requester) != "owner":\n        raise HTTPException(status_code=403, detail="only an owner can delete this workspace")\n    for agent in workspace_agents(workspace_id):\n        stores.agents.pop(agent.id, None)\n    stores.workspaces.pop(workspace_id, None)\n''',
)

# 6. Canvas: support browser-native HTTP Basic auth in exposed deployments and
# guard the whole app so the challenge happens before the SPA loads.
security = "packages/maistro-canvas/frontend/server/security.js"
replace_once(
    security,
    '''export function requireToken(config) {\n  return (req, res, next) => {\n    if (!config.token) return next();           // loopback-only mode\n    const header = req.get("authorization") || "";\n    const supplied = header.startsWith("Bearer ") ? header.slice(7) : req.get("x-canvas-token") || "";\n    if (!tokensMatch(supplied, config.token)) return res.status(401).json({ error: "unauthorized" });\n    next();\n  };\n}\n''',
    '''function suppliedToken(req) {\n  const header = req.get("authorization") || "";\n  if (header.startsWith("Bearer ")) return header.slice(7);\n  if (header.startsWith("Basic ")) {\n    try {\n      const decoded = Buffer.from(header.slice(6), "base64").toString("utf8");\n      const separator = decoded.indexOf(":");\n      if (separator >= 0) return decoded.slice(separator + 1);\n    } catch {\n      return "";\n    }\n  }\n  return req.get("x-canvas-token") || "";\n}\n\nexport function requireToken(config) {\n  return (req, res, next) => {\n    if (!config.token) return next();           // loopback-only mode\n    const supplied = suppliedToken(req);\n    if (!tokensMatch(supplied, config.token)) {\n      // Browsers visiting an exposed Canvas get a native credential prompt\n      // before the SPA loads. Use any username and CANVAS_API_TOKEN as the\n      // password. Bearer/x-canvas-token remain supported for API clients.\n      if (typeof res.set === "function") {\n        res.set("WWW-Authenticate", 'Basic realm="MAIstro Canvas", charset="UTF-8"');\n      }\n      return res.status(401).json({ error: "unauthorized" });\n    }\n    next();\n  };\n}\n''',
)
server = "packages/maistro-canvas/frontend/server.js"
replace_once(
    server,
    'app.use("/api", requireToken(security));\n',
    'app.use(requireToken(security));\n',
)

# 7. Canvas export slots remain held until the child exits on disconnect.
replace_once(
    server,
    '''  activeExports += 1;\n  let released = false;\n  let tmpDir;\n\n  const release = () => {\n    if (released) return;\n    released = true;\n    activeExports -= 1;\n    if (tmpDir) rmdir(tmpDir, { recursive: true }).catch(() => {});\n  };\n\n  // Registered BEFORE the first await, and that ordering is the whole point.\n  // The render below takes as long as a PDF takes; if the client disconnects\n  // during it, `res` emits 'close' while we are still suspended. Attaching the\n  // listener afterwards means that event has already fired and nothing ever\n  // decrements the counter — two aborted exports would wedge this endpoint at\n  // 503 until the process restarted, which is exactly the denial the cap exists\n  // to prevent. 'close' also fires on normal completion; `release` is\n  // idempotent, so the double-notify is harmless.\n  res.on("close", release);\n''',
    '''  activeExports += 1;\n  let released = false;\n  let tmpDir;\n  let child = null;\n  let clientClosed = false;\n\n  const release = () => {\n    if (released) return;\n    released = true;\n    activeExports -= 1;\n    if (tmpDir) rmdir(tmpDir, { recursive: true }).catch(() => {});\n  };\n\n  // A disconnected client must not free the concurrency slot while the Python\n  // renderer is still alive. Terminate it, then let its exit callback release\n  // the slot and temp directory. On normal completion child is already null,\n  // so response close releases after the PDF stream is done.\n  res.on("close", () => {\n    clientClosed = true;\n    if (child && child.exitCode === null) {\n      child.kill("SIGTERM");\n      return;\n    }\n    release();\n  });\n''',
)
replace_once(
    server,
    '''    await new Promise((resolve, reject) => {\n      const proc = execFile("python3", [EXPORT_SCRIPT], { maxBuffer: 100 * 1024 * 1024 }, (err, stdout, stderr) => {\n        if (err) return reject(stderr || err.message);\n        try {\n          const result = JSON.parse(stdout.trim());\n          if (!result.ok) return reject(result.error || "export failed");\n          resolve(result.path);\n        } catch (e) { reject(e.message); }\n      });\n      proc.stdin.write(payload);\n      proc.stdin.end();\n    });\n''',
    '''    await new Promise((resolve, reject) => {\n      child = execFile("python3", [EXPORT_SCRIPT], { maxBuffer: 100 * 1024 * 1024 }, (err, stdout, stderr) => {\n        child = null;\n        if (clientClosed) {\n          release();\n          return reject("client disconnected");\n        }\n        if (err) return reject(stderr || err.message);\n        try {\n          const result = JSON.parse(stdout.trim());\n          if (!result.ok) return reject(result.error || "export failed");\n          resolve(result.path);\n        } catch (e) { reject(e.message); }\n      });\n      child.stdin.write(payload);\n      child.stdin.end();\n    });\n''',
)
replace_once(
    server,
    '''  } catch (e) {\n    release();\n    console.error("Export error:", e);\n    res.status(500).json({ error: typeof e === "string" ? e : e.message });\n  }\n});\n''',
    '''  } catch (e) {\n    release();\n    console.error("Export error:", e);\n    if (!res.headersSent && !res.destroyed) {\n      res.status(500).json({ error: typeof e === "string" ? e : e.message });\n    }\n  }\n});\n''',
)

# 8. Generated benchmark code executes only in MAIstro's hardened Docker
# sandbox. If maistro-core/Docker is unavailable, evaluation fails closed.
write(
    "packages/maistro-evolve/src/maistro_evolve/benchmarks/sandbox_exec.py",
    '''"""Isolated execution for model-generated benchmark code.\n\nCandidate code is untrusted. It is written into MAIstro's existing hardened\nDocker sandbox (network disabled, resource limited, capability dropped) and\nexecuted there. If that sandbox is unavailable, the check fails closed rather\nthan falling back to host subprocess execution.\n"""\n\nfrom __future__ import annotations\n\nimport math\nimport shutil\nimport tempfile\nimport uuid\nfrom pathlib import Path\nfrom typing import Any\n\n_DEFAULT_TIMEOUT = 10.0\n_MAX_OUTPUT_CHARS = 500\n_PASS_MARKER = "PASS"\n\n\ndef _build_check_script(\n    code: str, function_name: str, call_args: list[Any], expected_value: Any\n) -> str:\n    """Candidate code followed by a maintainer-authored call + comparison."""\n    expected_expr = repr(expected_value)\n    return (\n        f"{code}\\n\\n"\n        "import datetime as _maistro_datetime_module\\n"\n        f"_result = {function_name}(*{call_args!r})\\n"\n        f"_expected = eval({expected_expr!r}, {'{'}'datetime': _maistro_datetime_module{'}'})\\n"\n        "print('PASS' if _result == _expected else "\n        "f'FAIL: got {_result!r}, expected {_expected!r}')\\n"\n    )\n\n\nasync def run_function_check(\n    code: str,\n    function_name: str,\n    call_args: list[Any],\n    expected_value: Any,\n    *,\n    timeout: float = _DEFAULT_TIMEOUT,\n) -> tuple[bool, str]:\n    """Run one candidate assertion inside the hardened container sandbox."""\n    try:\n        from maistro.tools.sandbox.docker import create_sandbox\n    except (ImportError, ModuleNotFoundError) as exc:\n        return False, f"isolated sandbox unavailable: {exc}"[:_MAX_OUTPUT_CHARS]\n\n    script = _build_check_script(code, function_name, call_args, expected_value)\n    workspace = (\n        Path(tempfile.gettempdir())\n        / "maistro-workspace"\n        / f"swebench-{uuid.uuid4().hex}"\n    )\n    sandbox = None\n    try:\n        sandbox = await create_sandbox(str(workspace))\n        await sandbox.write_file("check.py", script)\n        exit_code, output = await sandbox.exec(\n            "python check.py", timeout=max(1, math.ceil(timeout))\n        )\n    except (FileNotFoundError, PermissionError, RuntimeError, OSError) as exc:\n        return False, f"isolated sandbox unavailable: {exc}"[:_MAX_OUTPUT_CHARS]\n    finally:\n        if sandbox is not None:\n            await sandbox.destroy()\n        shutil.rmtree(workspace, ignore_errors=True)\n\n    output = output.strip()\n    if exit_code != 0:\n        detail = output or f"exit code {exit_code}"\n        return False, detail[:_MAX_OUTPUT_CHARS]\n    if output == _PASS_MARKER:\n        return True, "ok"\n    return False, (output or "no PASS marker in output")[:_MAX_OUTPUT_CHARS]\n''',
)

# 9. Proxy SWE-bench evaluates every real sample on undisclosed cases. The
# displayed prompt example is never sufficient by itself to score a sample.
write(
    "packages/maistro-evolve/src/maistro_evolve/benchmarks/swebench.py",
    '''from __future__ import annotations\n\nimport asyncio\nimport re\nimport time\nfrom datetime import datetime, timedelta, timezone\nfrom typing import Any\n\nfrom ..types import EvalResult, PipelineGenome\nfrom .datasets import SWEBENCH_SAMPLES\nfrom .prompt_builder import build_messages, build_model_config, build_system_prompt\nfrom .sandbox_exec import run_function_check\n\n_FUNCTION_NAME_RE = re.compile(r"def\\s+(\\w+)\\s*\\(")\n\n\ndef _fib(n: int) -> int:\n    a, b = 0, 1\n    for _ in range(n):\n        a, b = b, a + b\n    return a\n\n\n# Evaluator-only cases. These are deliberately separate from the examples\n# disclosed in datasets.py's user prompt so a constant-answer patch cannot\n# receive credit. A sample passes only if every hidden case passes.\n_HIDDEN_CASES: dict[str, list[tuple[list[Any], Any]]] = {\n    "swe_01": [\n        ([[1, [2, [3, []]], 4]], [1, 2, 3, 4]),\n        ([[]], []),\n    ],\n    "swe_02": [\n        (["person@example.com"], True),\n        (["person@localhost"], False),\n    ],\n    "swe_03": [\n        ([{"a": {"x": 1}, "keep": 1}, {"a": {"y": 2}}], {"a": {"x": 1, "y": 2}, "keep": 1}),\n        ([{"a": {"x": {"p": 1}}}, {"a": {"x": {"q": 2}}}], {"a": {"x": {"p": 1, "q": 2}}}),\n    ],\n    "swe_04": [\n        (["2024-06-01T12:45:30-05:00"], datetime(2024, 6, 1, 12, 45, 30, tzinfo=timezone(timedelta(hours=-5)))),\n        (["2025-02-03T01:02:03+02:30"], datetime(2025, 2, 3, 1, 2, 3, tzinfo=timezone(timedelta(hours=2, minutes=30)))),\n    ],\n    "swe_05": [\n        ([[1, 2, 3], 2], [[1, 2], [3]]),\n        ([[1, 2, 3], 5], [[1, 2, 3]]),\n    ],\n    "swe_06": [\n        (["One, two; ONE!"], {"one": 2, "two": 1}),\n        (["hello... hello? world"], {"hello": 2, "world": 1}),\n    ],\n    "swe_07": [\n        ([10, "2"], 5.0),\n        ([10, "0.0"], None),\n    ],\n    "swe_08": [\n        ([[3, 1, 3, 2, 1]], [3, 1, 2]),\n        ([[i % 60_000 for i in range(120_000)]], list(range(60_000))),\n    ],\n    "swe_09": [\n        (["simpleTest"], "simple_test"),\n        (["already_snake"], "already_snake"),\n    ],\n    "swe_10": [\n        ([17], 1597),\n        ([1000], _fib(1000)),\n    ],\n}\n\n\ndef _extract_code(response: str) -> str:\n    code_blocks = re.findall(r"```(?:python)?\\s*(.*?)```", response, re.DOTALL)\n    return "\\n".join(code_blocks) if code_blocks else response\n\n\ndef _function_name(buggy_code: str) -> str:\n    match = _FUNCTION_NAME_RE.search(buggy_code)\n    if match is None:\n        raise ValueError(f"could not find a function definition in: {buggy_code!r}")\n    return match.group(1)\n\n\ndef _evaluation_cases(sample: dict[str, Any]) -> list[tuple[list[Any], Any]]:\n    hidden = _HIDDEN_CASES.get(str(sample.get("id")))\n    if hidden is not None:\n        return hidden\n    # Unit-test/custom samples still use their explicit assertion. Real\n    # SWEBENCH_SAMPLES all have hidden cases above.\n    return [(sample["call_args"], sample["expected_value"])]\n\n\nasync def run_swebench(genome: PipelineGenome, llm_call: Any) -> EvalResult:\n    """Score model fixes by executing them against evaluator-only assertions."""\n    if llm_call is None:\n        raise ValueError(\n            "run_swebench requires an llm_call — there is no stub/heuristic "\n            "fallback (SPEC-202: never produce a fabricated score)"\n        )\n\n    start = time.monotonic()\n    system_prompt = build_system_prompt(genome)\n    model_config = build_model_config(genome)\n    code_system = (\n        system_prompt + "\\n\\n"\n        "You are an expert software engineer. When given a bug report, provide a corrected "\n        "version of the code wrapped in ```python``` code blocks. Explain the fix briefly."\n    )\n\n    total_score = 0.0\n    evaluated = 0\n    total_cost = 0.0\n    samples = len(SWEBENCH_SAMPLES)\n    failures: list[dict[str, Any]] = []\n\n    for sample in SWEBENCH_SAMPLES:\n        user_msg = (\n            f"## Bug Report\\n{sample['problem']}\\n\\n"\n            f"## Buggy Code\\n```python\\n{sample['buggy_code']}\\n```\\n\\n"\n            f"Please provide the fixed code. The expected output for test input "\n            f"{sample['test_input']} is {sample['expected_output']}."\n        )\n        messages = build_messages(code_system, user_msg)\n\n        try:\n            response = await asyncio.wait_for(\n                llm_call(\n                    messages,\n                    temperature=model_config.get("temperature", 0.2),\n                    max_tokens=model_config.get("max_tokens", 2048),\n                ),\n                timeout=45.0,\n            )\n            total_cost += 0.002\n\n            code = _extract_code(response)\n            function_name = _function_name(sample["buggy_code"])\n            passed = True\n            detail = "ok"\n            for call_args, expected_value in _evaluation_cases(sample):\n                case_passed, case_detail = await run_function_check(\n                    code, function_name, call_args, expected_value\n                )\n                if not case_passed:\n                    passed = False\n                    detail = case_detail\n                    break\n            total_score += 1.0 if passed else 0.0\n            evaluated += 1\n            if not passed and len(failures) < 5:\n                failures.append({"id": sample["id"], "detail": detail})\n        except Exception as exc:\n            evaluated += 1\n            if len(failures) < 5:\n                failures.append({"id": sample["id"], "detail": f"error: {exc}"})\n\n    avg_score = total_score / max(evaluated, 1)\n    elapsed = time.monotonic() - start\n\n    return EvalResult(\n        benchmark="proxy_swebench",\n        score=round(avg_score, 4),\n        cost_usd=round(total_cost, 4),\n        duration_seconds=round(elapsed, 3),\n        samples_evaluated=evaluated,\n        metadata={\n            "total_samples": samples,\n            "fidelity": "proxy",\n            "check": "isolated_hidden_assertion_execution",\n            "failures": failures,\n        },\n    )\n''',
)

# Update the existing test's metadata expectation and pin browser Basic auth.
replace_once(
    "packages/maistro-evolve/tests/benchmarks/test_swebench.py",
    '        assert result.metadata["check"] == "real_assertion_execution"\n',
    '        assert result.metadata["check"] == "isolated_hidden_assertion_execution"\n',
)
replace_once(
    "packages/maistro-canvas/frontend/server/security.test.js",
    '''    const b = vi.fn();\n    requireToken({ token: "secret" })(req({ "x-canvas-token": "secret" }), res(), b);\n    expect(b).toHaveBeenCalled();\n''',
    '''    const b = vi.fn();\n    requireToken({ token: "secret" })(req({ "x-canvas-token": "secret" }), res(), b);\n    expect(b).toHaveBeenCalled();\n\n    const c = vi.fn();\n    const basic = Buffer.from("canvas:secret").toString("base64");\n    requireToken({ token: "secret" })(req({ authorization: `Basic ${basic}` }), res(), c);\n    expect(c).toHaveBeenCalled();\n''',
)

print("PR #383 review fixes applied")
