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

canvas_test = "packages/maistro-canvas/frontend/server/security.test.js"
replace_once(
    canvas_test,
    '''    const b = vi.fn();\n    requireToken({ token: "secret" })(req({ "x-canvas-token": "secret" }), res(), b);\n    expect(b).toHaveBeenCalled();\n''',
    '''    const b = vi.fn();\n    requireToken({ token: "secret" })(req({ "x-canvas-token": "secret" }), res(), b);\n    expect(b).toHaveBeenCalled();\n\n    const c = vi.fn();\n    const basic = Buffer.from("canvas:secret").toString("base64");\n    requireToken({ token: "secret" })(req({ authorization: `Basic ${basic}` }), res(), c);\n    expect(c).toHaveBeenCalled();\n''',
)

print("final PR #383 review fixes applied")
