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


# Workspace lifecycle: deleting a workspace must delete the agents it owns.
workspaces = "packages/hive-conductor/backend/routes/workspaces.py"
replace_once(
    workspaces,
    "from services.agent_materialization import materialize_workspace_agents\n",
    "from services.agent_materialization import materialize_workspace_agents, workspace_agents\n",
)
replace_once(
    workspaces,
    '''    if _member_role(workspace, requester) != "owner":\n        raise HTTPException(status_code=403, detail="only an owner can delete this workspace")\n    stores.workspaces.pop(workspace_id, None)\n''',
    '''    if _member_role(workspace, requester) != "owner":\n        raise HTTPException(status_code=403, detail="only an owner can delete this workspace")\n    # Materialized agents are workspace-owned resources. Delete them before\n    # removing the ownership record or they become unreachable orphans.\n    for agent in workspace_agents(workspace_id):\n        stores.agents.pop(agent.id, None)\n    stores.workspaces.pop(workspace_id, None)\n''',
)

# Canvas browser auth: HTTP Basic lets an exposed browser present the API token
# without putting it into frontend JavaScript. Password = token; username ignored.
security = "packages/maistro-canvas/frontend/server/security.js"
replace_once(
    security,
    '''export function requireToken(config) {\n  return (req, res, next) => {\n    if (!config.token) return next();           // loopback-only mode\n    const header = req.get("authorization") || "";\n    const supplied = header.startsWith("Bearer ") ? header.slice(7) : req.get("x-canvas-token") || "";\n    if (!tokensMatch(supplied, config.token)) return res.status(401).json({ error: "unauthorized" });\n    next();\n  };\n}\n''',
    '''function suppliedToken(req) {\n  const header = req.get("authorization") || "";\n  if (header.startsWith("Bearer ")) return header.slice(7);\n  if (header.startsWith("Basic ")) {\n    try {\n      const decoded = Buffer.from(header.slice(6), "base64").toString("utf8");\n      const separator = decoded.indexOf(":");\n      return separator >= 0 ? decoded.slice(separator + 1) : "";\n    } catch {\n      return "";\n    }\n  }\n  return req.get("x-canvas-token") || "";\n}\n\nexport function requireToken(config) {\n  return (req, res, next) => {\n    if (!config.token) return next();           // loopback-only mode\n    const supplied = suppliedToken(req);\n    if (!tokensMatch(supplied, config.token)) {\n      if (typeof res.set === "function") {\n        res.set("WWW-Authenticate", 'Basic realm="MAIstro Canvas", charset="UTF-8"');\n      }\n      return res.status(401).json({ error: "unauthorized" });\n    }\n    next();\n  };\n}\n''',
)

# Canvas export concurrency: disconnecting kills an active renderer but does not
# free its slot until the child actually exits. An early disconnect cannot spawn
# a renderer after the response is already gone.
server = "packages/maistro-canvas/frontend/server.js"
replace_once(
    server,
    '''  activeExports += 1;\n  let released = false;\n  let tmpDir;\n\n  const release = () => {\n    if (released) return;\n    released = true;\n    activeExports -= 1;\n    if (tmpDir) rmdir(tmpDir, { recursive: true }).catch(() => {});\n  };\n\n  // Registered BEFORE the first await, and that ordering is the whole point.\n  // The render below takes as long as a PDF takes; if the client disconnects\n  // during it, `res` emits 'close' while we are still suspended. Attaching the\n  // listener afterwards means that event has already fired and nothing ever\n  // decrements the counter — two aborted exports would wedge this endpoint at\n  // 503 until the process restarted, which is exactly the denial the cap exists\n  // to prevent. 'close' also fires on normal completion; `release` is\n  // idempotent, so the double-notify is harmless.\n  res.on("close", release);\n''',
    '''  activeExports += 1;\n  let released = false;\n  let tmpDir;\n  let child = null;\n  let clientClosed = false;\n\n  const release = () => {\n    if (released) return;\n    released = true;\n    activeExports -= 1;\n    if (tmpDir) rmdir(tmpDir, { recursive: true }).catch(() => {});\n  };\n\n  res.on("close", () => {\n    clientClosed = true;\n    if (child && child.exitCode === null) {\n      child.kill("SIGTERM");\n      return;\n    }\n    release();\n  });\n''',
)
replace_once(
    server,
    '''    tmpDir = await mkdtemp(join(tmpdir(), "canvas-export-"));\n    const payload = JSON.stringify({ mode: mode || "interior", title, author, product_id, pages, front_cover, back_cover, output_dir: tmpDir });\n\n    await new Promise((resolve, reject) => {\n      const proc = execFile("python3", [EXPORT_SCRIPT], { maxBuffer: 100 * 1024 * 1024 }, (err, stdout, stderr) => {\n        if (err) return reject(stderr || err.message);\n        try {\n          const result = JSON.parse(stdout.trim());\n          if (!result.ok) return reject(result.error || "export failed");\n          resolve(result.path);\n        } catch (e) { reject(e.message); }\n      });\n      proc.stdin.write(payload);\n      proc.stdin.end();\n    });\n''',
    '''    tmpDir = await mkdtemp(join(tmpdir(), "canvas-export-"));\n    if (clientClosed) throw new Error("client disconnected");\n    const payload = JSON.stringify({ mode: mode || "interior", title, author, product_id, pages, front_cover, back_cover, output_dir: tmpDir });\n\n    await new Promise((resolve, reject) => {\n      child = execFile("python3", [EXPORT_SCRIPT], { maxBuffer: 100 * 1024 * 1024 }, (err, stdout, stderr) => {\n        child = null;\n        if (clientClosed) {\n          release();\n          return reject(new Error("client disconnected"));\n        }\n        if (err) return reject(stderr || err.message);\n        try {\n          const result = JSON.parse(stdout.trim());\n          if (!result.ok) return reject(result.error || "export failed");\n          resolve(result.path);\n        } catch (e) { reject(e.message); }\n      });\n      child.stdin.write(payload);\n      child.stdin.end();\n    });\n''',
)
replace_once(
    server,
    '''  } catch (e) {\n    release();\n    console.error("Export error:", e);\n    res.status(500).json({ error: typeof e === "string" ? e : e.message });\n  }\n});\n''',
    '''  } catch (e) {\n    release();\n    console.error("Export error:", e);\n    if (!clientClosed && !res.destroyed && !res.headersSent) {\n      res.status(500).json({ error: typeof e === "string" ? e : e.message });\n    }\n  }\n});\n''',
)

# Proxy SWE-bench: examples shown in the prompt are demonstrations, never the
# grading cases. Each real sample receives evaluator-only assertions.
swebench = "packages/maistro-evolve/src/maistro_evolve/benchmarks/swebench.py"
replace_once(
    swebench,
    "import time\nfrom typing import Any\n",
    "import time\nfrom datetime import datetime, timedelta, timezone\nfrom typing import Any\n",
)
replace_once(
    swebench,
    '''_FUNCTION_NAME_RE = re.compile(r"def\\s+(\\w+)\\s*\\(")\n\n\ndef _extract_code(response: str) -> str:\n''',
    '''_FUNCTION_NAME_RE = re.compile(r"def\\s+(\\w+)\\s*\\(")\n\n\ndef _fib(n: int) -> int:\n    a, b = 0, 1\n    for _ in range(n):\n        a, b = b, a + b\n    return a\n\n\n_HIDDEN_CASES: dict[str, list[tuple[list[Any], Any]]] = {\n    "swe_01": [([[1, [2, [3, []]], 4]], [1, 2, 3, 4]), ([[[["x"]], "y"]], ["x", "y"])],\n    "swe_02": [(["person@example.com"], True), (["person@localhost"], False)],\n    "swe_03": [\n        ([{"a": {"x": 1}, "keep": 1}, {"a": {"y": 2}}], {"a": {"x": 1, "y": 2}, "keep": 1}),\n        ([{"a": {"x": {"p": 1}}}, {"a": {"x": {"q": 2}}}], {"a": {"x": {"p": 1, "q": 2}}}),\n    ],\n    "swe_04": [\n        (["2024-06-01T12:45:30-05:00"], datetime(2024, 6, 1, 12, 45, 30, tzinfo=timezone(timedelta(hours=-5)))),\n        (["2025-02-03T01:02:03+05:30"], datetime(2025, 2, 3, 1, 2, 3, tzinfo=timezone(timedelta(hours=5, minutes=30)))),\n    ],\n    "swe_05": [([[1, 2, 3], 2], [[1, 2], [3]]), ([[], 3], [])],\n    "swe_06": [(["One, two; ONE!"], {"one": 2, "two": 1}), (["hello... hello? world"], {"hello": 2, "world": 1})],\n    "swe_07": [([10, "2"], 5.0), ([10, "0.0"], None)],\n    "swe_08": [([list(range(60_000)) + list(range(60_000))], list(range(60_000))), ([[3, 1, 3, 2, 1]], [3, 1, 2])],\n    "swe_09": [(["simpleTest"], "simple_test"), (["already_snake"], "already_snake")],\n    "swe_10": [([17], 1597), ([1000], _fib(1000))],\n}\n\n\ndef _evaluation_cases(sample: dict[str, Any]) -> list[tuple[list[Any], Any]]:\n    hidden = _HIDDEN_CASES.get(str(sample.get("id")))\n    if hidden is not None:\n        return hidden\n    return [(sample["call_args"], sample["expected_value"])]\n\n\ndef _extract_code(response: str) -> str:\n''',
)
replace_once(
    swebench,
    '''            passed, detail = await run_function_check(\n                code,\n                function_name,\n                sample["call_args"],\n                sample["expected_value"],\n            )\n            total_score += 1.0 if passed else 0.0\n''',
    '''            passed = True\n            detail = "ok"\n            for call_args, expected_value in _evaluation_cases(sample):\n                case_passed, case_detail = await run_function_check(\n                    code, function_name, call_args, expected_value\n                )\n                if not case_passed:\n                    passed = False\n                    detail = case_detail\n                    break\n            total_score += 1.0 if passed else 0.0\n''',
)
replace_once(
    swebench,
    '            "check": "real_assertion_execution",\n',
    '            "check": "isolated_hidden_assertion_execution",\n',
)

# Pin hidden-case behavior and Canvas Basic auth in unit tests.
test_swebench = "packages/maistro-evolve/tests/benchmarks/test_swebench.py"
replace_once(
    test_swebench,
    '        assert result.metadata["check"] == "real_assertion_execution"\n',
    '        assert result.metadata["check"] == "isolated_hidden_assertion_execution"\n',
)
replace_once(
    test_swebench,
    '''    async def test_real_dataset_has_call_args_and_expected_value_on_every_sample(self) -> None:\n''',
    '''    async def test_real_dataset_uses_evaluator_only_cases(self) -> None:\n        for sample in SWEBENCH_SAMPLES:\n            cases = swebench_module._evaluation_cases(sample)\n            assert cases\n            assert any(\n                call_args != sample["call_args"] or expected != sample["expected_value"]\n                for call_args, expected in cases\n            )\n\n    async def test_real_dataset_has_call_args_and_expected_value_on_every_sample(self) -> None:\n''',
)

canvas_test = "packages/maistro-canvas/frontend/server/security.test.js"
replace_once(
    canvas_test,
    '''    const b = vi.fn();\n    requireToken({ token: "secret" })(req({ "x-canvas-token": "secret" }), res(), b);\n    expect(b).toHaveBeenCalled();\n''',
    '''    const b = vi.fn();\n    requireToken({ token: "secret" })(req({ "x-canvas-token": "secret" }), res(), b);\n    expect(b).toHaveBeenCalled();\n\n    const c = vi.fn();\n    const basic = Buffer.from("canvas:secret").toString("base64");\n    requireToken({ token: "secret" })(req({ authorization: `Basic ${basic}` }), res(), c);\n    expect(c).toHaveBeenCalled();\n''',
)

print("remaining PR #383 review fixes applied")
