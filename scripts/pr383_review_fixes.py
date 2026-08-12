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


# Workspace lifecycle: deleting a workspace must delete materialized agents.
workspaces = "packages/hive-conductor/backend/routes/workspaces.py"
replace_once(
    workspaces,
    "from services.agent_materialization import materialize_workspace_agents\n",
    "from services.agent_materialization import materialize_workspace_agents, workspace_agents\n",
)
replace_once(
    workspaces,
    '''    if _member_role(workspace, requester) != "owner":\n        raise HTTPException(status_code=403, detail="only an owner can delete this workspace")\n    stores.workspaces.pop(workspace_id, None)\n''',
    '''    if _member_role(workspace, requester) != "owner":\n        raise HTTPException(status_code=403, detail="only an owner can delete this workspace")\n    for agent in workspace_agents(workspace_id):\n        stores.agents.pop(agent.id, None)\n    stores.workspaces.pop(workspace_id, None)\n''',
)

# Canvas browser auth: exposed deployments accept HTTP Basic in addition to
# Bearer/x-canvas-token. The token is the Basic password; username is ignored.
security = "packages/maistro-canvas/frontend/server/security.js"
replace_once(
    security,
    '''export function requireToken(config) {\n  return (req, res, next) => {\n    if (!config.token) return next();           // loopback-only mode\n    const header = req.get("authorization") || "";\n    const supplied = header.startsWith("Bearer ") ? header.slice(7) : req.get("x-canvas-token") || "";\n    if (!tokensMatch(supplied, config.token)) return res.status(401).json({ error: "unauthorized" });\n    next();\n  };\n}\n''',
    '''function suppliedToken(req) {\n  const header = req.get("authorization") || "";\n  if (header.startsWith("Bearer ")) return header.slice(7);\n  if (header.startsWith("Basic ")) {\n    try {\n      const decoded = Buffer.from(header.slice(6), "base64").toString("utf8");\n      const separator = decoded.indexOf(":");\n      return separator >= 0 ? decoded.slice(separator + 1) : "";\n    } catch {\n      return "";\n    }\n  }\n  return req.get("x-canvas-token") || "";\n}\n\nexport function requireToken(config) {\n  return (req, res, next) => {\n    if (!config.token) return next();           // loopback-only mode\n    const supplied = suppliedToken(req);\n    if (!tokensMatch(supplied, config.token)) {\n      if (typeof res.set === "function") {\n        res.set("WWW-Authenticate", 'Basic realm="MAIstro Canvas", charset="UTF-8"');\n      }\n      return res.status(401).json({ error: "unauthorized" });\n    }\n    next();\n  };\n}\n''',
)

# Proxy SWE-bench: examples disclosed in prompts are never grading cases.
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

# Regression tests for the evaluator contract and browser-native auth.
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
