"""In-memory stores and seed data for the Hive Conductor stub API."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from models.schemas import (
    Agent,
    ChatMessage,
    ChatSession,
    Container,
    MCPServer,
    MCPTool,
    MemoryEntry,
    MemoryNamespace,
    Mission,
    MissionStep,
    Schedule,
    SettingsModel,
    Skill,
)

now = lambda: datetime.now(UTC)


def _mission(
    id: str,
    name: str,
    status: Literal["pending", "running", "completed", "failed", "paused"] = "running",
    progress: float = 0.5,
) -> Mission:
    t = now()
    return Mission(
        id=id,
        name=name,
        description=f"Stub mission: {name}",
        status=status,
        priority="medium",
        created_at=t,
        updated_at=t,
        progress=progress,
        steps_total=4,
        steps_completed=2,
        assigned_agents=["agent-1"],
        tags=["demo"],
        metadata={},
    )


missions: dict[str, Mission] = {
    "m-1": _mission("m-1", "Deploy canary", "running", 0.6),
    "m-2": _mission("m-2", "Backfill embeddings", "pending", 0.0),
}

mission_steps: dict[str, list[MissionStep]] = {
    "m-1": [
        MissionStep(
            id="s-1",
            mission_id="m-1",
            name="Validate config",
            description="Check env",
            status="completed",
            order=0,
            agent_id="agent-1",
            started_at=now(),
            completed_at=now(),
            output="ok",
            error=None,
        ),
        MissionStep(
            id="s-2",
            mission_id="m-1",
            name="Rollout",
            description="Apply change",
            status="running",
            order=1,
            agent_id="agent-1",
            started_at=now(),
            completed_at=None,
            output=None,
            error=None,
        ),
    ]
}

schedules: dict[str, Schedule] = {
    "sch-1": Schedule(
        id="sch-1",
        name="Nightly eval",
        description="Run benchmark suite",
        cron_expression="0 3 * * *",
        mission_template_id="tpl-eval",
        enabled=True,
        last_run=None,
        next_run=None,
        created_at=now(),
        updated_at=now(),
    )
}

skills: dict[str, Skill] = {
    "sk-1": Skill(
        id="sk-1",
        name="web_fetch",
        description="HTTP GET with guardrails",
        version="1.2.0",
        category="tools",
        author="hive",
        enabled=True,
        usage_count=42,
        avg_latency_ms=120.0,
        success_rate=0.98,
        tags=["network"],
        parameters=[{"name": "url", "type": "string", "required": True}],
    )
}

agents: dict[str, Agent] = {
    "agent-1": Agent(
        id="agent-1",
        name="Orchestrator Alpha",
        description="General mission runner",
        model="gpt-4.1",
        status="idle",
        capabilities=["missions", "tools"],
        skills=["sk-1"],
        current_mission=None,
        tasks_completed=128,
        avg_response_time_ms=890.0,
        last_active=now(),
        created_at=now(),
        config={"temperature": 0.2},
    )
}

mcp_servers: dict[str, MCPServer] = {
    "mcp-1": MCPServer(
        id="mcp-1",
        name="Filesystem",
        description="Local workspace tools",
        url="http://127.0.0.1:9999/mcp",
        status="connected",
        tools_count=6,
        last_ping=now(),
        version="0.4.0",
        capabilities=["tools"],
    )
}

mcp_tools: dict[str, MCPTool] = {
    "t-1": MCPTool(
        id="t-1",
        server_id="mcp-1",
        name="read_file",
        description="Read a UTF-8 file",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        category="fs",
    )
}

containers: dict[str, Container] = {
    "c-1": Container(
        id="c-1",
        name="hive-api",
        image="hive-conductor:local",
        status="running",
        ports=[{"host": 8101, "container": 8101}],
        cpu_usage=4.2,
        memory_usage_mb=256.0,
        memory_limit_mb=1024.0,
        network_rx_mb=1.2,
        network_tx_mb=0.4,
        created_at=now(),
        started_at=now(),
        labels={"app": "hive"},
    )
}

memory_entries: dict[str, MemoryEntry] = {
    "mem-1": MemoryEntry(
        id="mem-1",
        key="default/welcome",
        value="Hive Conductor stub memory",
        namespace="default",
        tags=["seed"],
        embedding=None,
        created_at=now(),
        updated_at=now(),
        accessed_count=0,
        ttl_seconds=None,
    )
}

memory_namespaces: dict[str, MemoryNamespace] = {
    "default": MemoryNamespace(name="default", entry_count=1, size_bytes=1024)
}

settings: SettingsModel = SettingsModel()

chat_sessions: dict[str, ChatSession] = {}

cli_sessions: dict[str, dict[str, Any]] = {}


def seed_chat_if_empty() -> None:
    if chat_sessions:
        return
    sid = "chat-seed-1"
    t = now()
    chat_sessions[sid] = ChatSession(
        id=sid,
        title="Welcome",
        messages=[
            ChatMessage(
                id=str(uuid4()),
                role="user",
                content="Hello Hive",
                timestamp=t,
            ),
            ChatMessage(
                id=str(uuid4()),
                role="assistant",
                content="Hi — this is stub data from the Hive Conductor API.",
                timestamp=t,
            ),
        ],
        created_at=t,
        updated_at=t,
    )
