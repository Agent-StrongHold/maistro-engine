"""Graph runner — bridges hive-conductor DAGs to maistro-core graph executor.

Converts a DAGFile dict from the store into a GraphConfig, builds an
LLM callable from settings, and runs the graph.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

import httpx
from config import get_settings

logger = logging.getLogger(__name__)


# Static subprocess body. All untrusted values (system prompt, task description,
# parent context) are read from environment variables at runtime — NEVER
# templated into this source — so triple-quotes, backslashes and newlines in a
# node prompt cannot break out of a string literal and inject Python (RCE).
_NODE_SCRIPT = '''
import json, os, sys
import httpx

base = os.environ.get("LITELLM_API_BASE", "").rstrip("/")
if not base.endswith("/v1"):
    base += "/v1"
key = os.environ.get("LITELLM_API_KEY", "")
model = os.environ.get("DAG_NODE_MODEL", "gemini-3.5-flash")
system = os.environ.get("DAG_NODE_SYSTEM", "")
task = os.environ.get("DAG_NODE_TASK", "")
context = os.environ.get("DAG_NODE_CONTEXT", "")
user = "Task: " + task + "\\n\\nContext:\\n" + context
r = httpx.post(
    base + "/chat/completions",
    headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    json={
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
    },
    timeout=120,
)
r.raise_for_status()
print(r.json()["choices"][0]["message"]["content"])
'''


def _run_node_subprocess(
    node: dict[str, Any],
    task_desc: str,
    context: str,
    base_env: dict[str, str],
) -> dict[str, Any]:
    """Run a single DAG node in an isolated executor.

    Untrusted strings (prompt/task/context) are passed via env vars, not
    interpolated into source. Module-level (not a closure) so it is picklable
    for ProcessPoolExecutor.
    """
    from services.hyperlight_executor import get_executor
    import asyncio as _aio

    node_env = {
        **base_env,
        "DAG_NODE_MODEL": node.get("model", "gemini-3.5-flash"),
        "DAG_NODE_SYSTEM": node.get("prompt", "") or "",
        "DAG_NODE_TASK": task_desc,
        "DAG_NODE_CONTEXT": context[:2000],
    }
    try:
        executor = get_executor()
        result = _aio.run(
            executor.execute_node(
                _NODE_SCRIPT,
                env=node_env,
                timeout_s=120,
                allow_network=True,  # nodes need to call LiteLLM
            )
        )
        if result["success"]:
            return {
                "role": node.get("role", "worker"),
                "response": result["output"].strip(),
                "success": True,
                "isolation": result.get("isolation", "unknown"),
            }
        return {
            "role": node.get("role", "worker"),
            "response": result.get("error", "")[:500],
            "success": False,
            "isolation": result.get("isolation", "unknown"),
        }
    except Exception as e:
        return {"role": node.get("role", "worker"), "response": str(e), "success": False}


async def execute_dag(dag_data: dict, *, user_id: str = "", user_credentials: dict[str, str] | None = None) -> dict[str, Any]:
    """Execute a DAG — each node is its own process, scoped to user context. No cross-user data leakage."""
    import asyncio
    import subprocess
    import tempfile

    nodes = dag_data.get("nodes", [])
    edges = dag_data.get("edges", [])
    if not nodes:
        return {"status": "completed", "cycles": 0, "node_results": {}}

    # Per-user scoped env — only what this user's nodes need, nothing else
    node_env = {
        "LITELLM_API_BASE": os.environ.get("LITELLM_API_BASE", ""),
        "LITELLM_API_KEY": os.environ.get("LITELLM_API_KEY", ""),
        "CHAT_DEFAULT_MODEL": os.environ.get("CHAT_DEFAULT_MODEL", "gemini-3.5-flash"),
        "DAG_USER_ID": user_id,
        "DAG_ID": dag_data.get("id", ""),
        "PATH": os.environ.get("PATH", ""),
    }
    if user_credentials:
        for k, v in user_credentials.items():
            node_env[f"USER_CRED_{k.upper()}"] = v

    task_desc = dag_data.get("description", dag_data.get("name", ""))

    # Build dependency graph
    node_map = {n["id"]: n for n in nodes}
    inbound: dict[str, set[str]] = {n["id"]: set() for n in nodes}
    outbound: dict[str, set[str]] = {n["id"]: set() for n in nodes}
    for e in edges:
        src, dst = e.get("from_node", ""), e.get("to_node", "")
        if src and dst and src in node_map and dst in node_map:
            inbound[dst].add(src)
            outbound[src].add(dst)

    results: dict[str, dict[str, Any]] = {}
    completed: set[str] = set()

    # Execute in waves — execution strategy per node
    cycles = 0
    while len(completed) < len(nodes):
        ready = [nid for nid in node_map if nid not in completed and inbound[nid].issubset(completed)]
        if not ready:
            break

        import concurrent.futures

        # Group by execution tier — uses security infrastructure
        async_nodes = []
        subprocess_nodes = []
        for nid in ready:
            node = node_map[nid]
            tier = node.get("config", {}).get("execution_tier", "")
            role = node.get("role", "")
            capabilities = node.get("config", {}).get("capabilities", [])

            # Security classification determines execution tier:
            # - trust_boundary: what data/systems can this node access?
            # - dangerous_tools: does it use shell, file write, network?
            # - task_policy: does it exceed budget/rate limits?
            is_dangerous = any(c in ("shell", "file_write", "code_exec", "browser") for c in capabilities)
            needs_secrets = any(c in ("jira_write", "deploy", "git_push") for c in capabilities)
            needs_filesystem = any(c in ("code_exec", "file_write", "repo_clone", "pytest") for c in capabilities)
            is_untrusted = node.get("config", {}).get("untrusted", False)

            if tier == "light" or tier == "safe":
                async_nodes.append(nid)
            elif is_untrusted or needs_filesystem:
                if node.get("config", {}).get("tier_approved_by") != "admin":
                    logger.warning("node_tier_not_approved node=%s tier=container — running as subprocess. Admin must approve via optimizer.", nid)
                subprocess_nodes.append(nid)
            elif is_dangerous or needs_secrets:
                subprocess_nodes.append(nid)
            elif tier == "container" or tier == "heavy":
                subprocess_nodes.append(nid)
            else:
                async_nodes.append(nid)

        # Run async nodes (light, safe — in-process, no GIL issue for I/O)
        async def run_node_inline(nid: str) -> None:
            node = node_map[nid]
            prompt = node.get("prompt", "")
            model = node.get("model", os.environ.get("CHAT_DEFAULT_MODEL", "gemini-3.5-flash"))

            # --- TOOL NODE: execute tool instead of LLM ---
            tool_name = node.get("tool")
            if tool_name:
                try:
                    from services.tool_executor import TOOLS
                    tool_fn = TOOLS.get(tool_name)
                    if not tool_fn:
                        results[nid] = {"role": node.get("role", "worker"), "response": f"Unknown tool: {tool_name}", "success": False}
                        return
                    tool_config = node.get("tool_config", {})
                    parent_outputs = {pid: results[pid]["response"] for pid in inbound[nid] if pid in results and results[pid].get("success")}

                    if tool_name == "web_search":
                        # Execute search queries from parent node output or config
                        iterate_over = tool_config.get("iterate_over", "")
                        queries = []
                        if iterate_over and "." in iterate_over:
                            src_node, src_field = iterate_over.split(".", 1)
                            src_data = parent_outputs.get(src_node, "")
                            try:
                                parsed = json.loads(src_data) if isinstance(src_data, str) else src_data
                                queries = parsed.get(src_field, []) if isinstance(parsed, dict) else []
                            except (json.JSONDecodeError, AttributeError):
                                queries = [task_desc]
                        elif tool_config.get("queries_from_input"):
                            template = tool_config.get("query_template", "{input}")
                            queries = [template.replace("{input}", task_desc)]
                        if not queries:
                            queries = [task_desc]

                        from services.tool_executor import web_search
                        all_results = []
                        max_r = tool_config.get("max_results", 5)
                        for q in queries[:5]:
                            sr = await web_search(q, max_results=max_r)
                            all_results.append(sr)
                        results[nid] = {"role": node.get("role", "worker"), "response": json.dumps(all_results, indent=2), "success": True}

                    elif tool_name == "clarify":
                        from services.tool_executor import clarify
                        questions = tool_config.get("questions", [])
                        ctx = {"input": task_desc}
                        answers = await clarify(questions, ctx)
                        # Format as readable brief
                        brief = "\n".join(f"Q: {q}\nA: {answers.get(str(i+1), answers.get(q, 'Not specified'))}\n" for i, q in enumerate(questions))
                        results[nid] = {"role": node.get("role", "worker"), "response": brief, "success": True}

                    elif tool_name == "browse_url":
                        from services.tool_executor import browse_url
                        url = tool_config.get("url", "")
                        task = tool_config.get("task", "Extract key information")
                        br = await browse_url(url, task)
                        results[nid] = {"role": node.get("role", "worker"), "response": json.dumps(br, indent=2), "success": True}

                    else:
                        result = await tool_fn(task_desc)
                        results[nid] = {"role": node.get("role", "worker"), "response": json.dumps(result) if isinstance(result, dict) else str(result), "success": True}
                except Exception as e:
                    logger.error(f"Tool node {nid} failed: {e}")
                    results[nid] = {"role": node.get("role", "worker"), "response": f"Tool error: {e}", "success": False}
                return
            # --- END TOOL NODE ---

            system = prompt or f"You are a {node.get('name', 'worker')} agent."
            user_content = f"Task: {task_desc}"
            parent_outputs = [results[pid]["response"] for pid in inbound[nid] if pid in results and results[pid].get("success")]
            if parent_outputs:
                user_content += "\n\nContext from previous steps:\n" + "\n---\n".join(parent_outputs[-3:])
            messages = [{"role": "system", "content": system}, {"role": "user", "content": user_content}]
            try:
                response = await _build_llm_call()(messages, model=model)
                results[nid] = {"role": node.get("role", "worker"), "response": response, "success": True}
            except Exception as e:
                results[nid] = {"role": node.get("role", "worker"), "response": str(e), "success": False}

        # Run subprocess nodes (heavy, risky — own process, own GIL)
        if subprocess_nodes:
            with concurrent.futures.ProcessPoolExecutor(max_workers=len(subprocess_nodes)) as pool:
                loop = asyncio.get_event_loop()
                futures = []
                for nid in subprocess_nodes:
                    ctx = "\n---\n".join(results[pid]["response"] for pid in inbound[nid] if pid in results and results[pid].get("success"))
                    futures.append(loop.run_in_executor(
                        pool, _run_node_subprocess, node_map[nid], task_desc, ctx, node_env
                    ))
                subprocess_results = await asyncio.gather(*futures)
                for nid, res in zip(subprocess_nodes, subprocess_results):
                    results[nid] = res

        # Run async nodes concurrently
        if async_nodes:
            await asyncio.gather(*[run_node_inline(nid) for nid in async_nodes])

        completed.update(ready)
        cycles += 1

    return {"status": "completed", "cycles": cycles, "node_results": results}


def genome_to_dag(genome: Any) -> dict[str, Any]:
    """Convert an evolved PipelineGenome into a DAG dict for execute_dag."""
    nodes = []
    for n in genome.topology.nodes:
        nodes.append({
            "id": n.id,
            "name": f"{n.role}-{n.id[:6]}",
            "role": n.role,
            "model": n.model,
            "prompt": n.system_prompt,
            "strategy": n.strategy,
            "temperature": n.temperature,
            "max_tokens": n.max_tokens,
            "max_tool_rounds": n.max_tool_rounds,
        })

    edges = []
    for e in genome.topology.edges:
        edges.append({
            "id": e.id,
            "from_node": e.from_node,
            "to_node": e.to_node,
            "condition": e.condition,
        })

    return {
        "name": genome.name,
        "description": f"Evolved pipeline (gen={genome.generation}, fitness={genome.fitness_score})",
        "nodes": nodes,
        "edges": edges,
        "entry_node": genome.topology.entry_node,
        "max_cycles": genome.topology.max_cycles,
        "run_scout": genome.topology.use_scout,
        "genome_id": genome.id,
        "evolved": True,
    }


async def execute_champion() -> dict[str, Any]:
    """Run the current evolution champion's pipeline through the graph executor."""
    try:
        from services.evolution import get_evolution_service
        svc = get_evolution_service()
    except RuntimeError:
        return {"status": "error", "error": "evolution service not started"}

    if svc.population is None:
        return {"status": "error", "error": "population not initialized"}

    champion = svc.population.get_champion()
    if champion is None:
        return {"status": "error", "error": "no champion yet"}

    dag_data = genome_to_dag(champion)
    result = await execute_dag(dag_data)
    result["genome_id"] = champion.id
    result["fitness"] = champion.fitness_score
    result["generation"] = champion.generation
    return result


def _build_llm_call():
    import os
    base = os.environ.get("LITELLM_API_BASE") or os.environ.get("LITELLM_PROXY_URL") or ""
    raw_key = os.environ.get("LITELLM_API_KEY") or os.environ.get("LITELLM_PROXY_KEY") or ""
    model = os.environ.get("CHAT_DEFAULT_MODEL", "gemini-3.5-flash")

    if not base:
        async def _stub_llm(messages: list[dict], **kwargs: Any) -> str:
            return json.dumps({"response": "stub: no LLM configured", "done": True})
        return _stub_llm

    # Ensure /v1 suffix
    if not base.endswith("/v1"):
        base = base.rstrip("/") + "/v1"

    async def _httpx_llm(messages: list[dict], **kwargs: Any) -> str:
        m = kwargs.get("model", model)
        temperature = kwargs.get("temperature", 0.3)
        max_tokens = kwargs.get("max_tokens", 4096)
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {raw_key}"}
        payload: dict[str, Any] = {
            "model": m,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        # Use json_schema if provided, otherwise json_object
        schema = kwargs.get("response_schema")
        if schema:
            payload["response_format"] = {"type": "json_schema", "json_schema": {"name": "output", "schema": schema}}
        else:
            payload["response_format"] = {"type": "json_object"}
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{base}/chat/completions", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            logger.info("graph_llm_response model=%s content_len=%d content_start=%s", m, len(content) if content else 0, (content or "")[:100])
            return content or ""

    return _httpx_llm


async def execute_dag_streaming(dag_data: dict):
    """Yield progress events as the DAG executes, one per node completion."""
    from maistro.graph.executor import run_graph
    from maistro.graph.types import GraphBlackboard, GraphConfig, GraphEdge, NodeConfig

    nodes_cfg = {}
    for n in dag_data.get("nodes", []):
        nodes_cfg[n["id"]] = NodeConfig(
            role=n.get("role", "worker"),
            name=n.get("name", n["id"]),
            model=n.get("model"),
            system_prompt=n.get("prompt"),
            temperature=0.3,
            max_tokens=4096,
        )

    edges = []
    for e in dag_data.get("edges", []):
        edges.append(GraphEdge(
            from_node=e["from_node"],
            to_node=e.get("to_node"),
            condition=e.get("condition"),
        ))

    entry_node = dag_data.get("entry_node") or (dag_data["nodes"][0]["id"] if dag_data.get("nodes") else "")

    config = GraphConfig(
        nodes=nodes_cfg,
        edges=edges,
        entry=entry_node,
        max_cycles=dag_data.get("max_cycles", 10),
        run_scout=dag_data.get("run_scout", False),
    )

    blackboard = GraphBlackboard(
        task_objective=dag_data.get("name", "Unnamed DAG"),
        workspace=dag_data.get("workspace", "/tmp/maistro-workspace"),  # nosec B108
    )
    llm_call = _build_llm_call()

    yield {"status": "started", "node_count": len(nodes_cfg), "entry": entry_node}

    try:
        result = await run_graph(
            task=dag_data.get("description", dag_data.get("name", "")),
            config=config,
            blackboard=blackboard,
            llm_call=llm_call,
        )
        for nr in result.node_results:
            yield {
                "status": "node_complete",
                "node_id": nr.node_id,
                "role": nr.role,
                "response": nr.selected_candidate or "",
                "success": nr.success,
            }
        yield {
            "status": "completed",
            "cycles": result.total_cycles,
            "annotations": dict(blackboard.node_annotations) if blackboard.node_annotations else {},
        }
    except Exception as exc:
        yield {"status": "failed", "error": str(exc)}
