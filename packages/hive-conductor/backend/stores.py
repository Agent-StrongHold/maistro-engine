"""In-memory stores with optional SQLite persistence for the Hive Conductor API.

When a PersistedStore is configured via ``configure_persistence()``, all
mutable stores (missions, chat_sessions, memory_entries, etc.) are backed
by SQLite. Read-only stores (agents, skills, containers, mcp_servers,
mcp_tools, schedules) stay in-memory since they reflect live system state.

Seed data is loaded when the store is empty and no persisted data exists.
"""

from __future__ import annotations

import logging
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
from services.model_store import JsonStore, ModelStore

logger = logging.getLogger(__name__)

def now() -> datetime:
    return datetime.now(UTC)

_persisted: Any | None = None


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


missions: ModelStore = ModelStore("missions", Mission)
mission_steps: JsonStore = JsonStore("mission_steps")
schedules: ModelStore = ModelStore("schedules", Schedule)
skills: ModelStore = ModelStore("skills", Skill)
agents: ModelStore = ModelStore("agents", Agent)
mcp_servers: ModelStore = ModelStore("mcp_servers", MCPServer)
mcp_tools: ModelStore = ModelStore("mcp_tools", MCPTool)
containers: ModelStore = ModelStore("containers", Container)
memory_entries: ModelStore = ModelStore("memory_entries", MemoryEntry)
memory_namespaces: dict[str, MemoryNamespace] = {
    "default": MemoryNamespace(name="default", entry_count=1, size_bytes=1024)
}
settings: SettingsModel = SettingsModel()
chat_sessions: ModelStore = ModelStore("chat_sessions", ChatSession)
cli_sessions: JsonStore = JsonStore("cli_sessions")

_all_model_stores: list[ModelStore] = [
    missions,
    schedules,
    skills,
    agents,
    mcp_servers,
    mcp_tools,
    containers,
    memory_entries,
    chat_sessions,
]
_all_json_stores: list[JsonStore] = [mission_steps, cli_sessions]


def configure_persistence(persisted_store: Any) -> None:
    """Wire a PersistedStore into all mutable stores."""
    global _persisted
    _persisted = persisted_store
    for store in _all_model_stores:
        store._persisted = persisted_store
    for store in _all_json_stores:
        store._persisted = persisted_store


def initialize_stores() -> None:
    """Load persisted data, then seed if empty."""
    for store in _all_model_stores:
        store.initialize()
    for store in _all_json_stores:
        store.initialize()
    _seed_if_empty()
    logger.info(
        "Stores initialized (persisted=%s)", _persisted is not None
    )


def _seed_if_empty() -> None:
    if len(missions) == 0:
        missions["m-1"] = _mission("m-1", "Deploy canary", "running", 0.6)
        missions["m-2"] = _mission("m-2", "Backfill embeddings", "pending", 0.0)
    if len(mission_steps) == 0:
        t = now()
        mission_steps["m-1"] = [
            MissionStep(
                id="s-1",
                mission_id="m-1",
                name="Validate config",
                description="Check env",
                status="completed",
                order=0,
                agent_id="agent-1",
                started_at=t,
                completed_at=t,
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
                started_at=t,
                completed_at=None,
                output=None,
                error=None,
            ),
        ]
    if len(schedules) == 0:
        t = now()
        schedules["sch-1"] = Schedule(
            id="sch-1",
            name="Nightly eval",
            description="Run benchmark suite",
            cron_expression="0 3 * * *",
            mission_template_id="tpl-eval",
            enabled=True,
            last_run=None,
            next_run=None,
            created_at=t,
            updated_at=t,
        )
    if len(skills) == 0:
        skills["sk-1"] = Skill(
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
    if len(agents) == 0:
        t = now()
        agents["agent-1"] = Agent(
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
            last_active=t,
            created_at=t,
            config={"temperature": 0.2},
        )
    if len(mcp_servers) == 0:
        t = now()
        mcp_servers["mcp-1"] = MCPServer(
            id="mcp-1",
            name="Filesystem",
            description="Local workspace tools",
            url="http://127.0.0.1:9999/mcp",
            status="connected",
            tools_count=6,
            last_ping=t,
            version="0.4.0",
            capabilities=["tools"],
        )
    if len(mcp_tools) == 0:
        mcp_tools["t-1"] = MCPTool(
            id="t-1",
            server_id="mcp-1",
            name="read_file",
            description="Read a UTF-8 file",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
            category="fs",
        )
    if len(containers) == 0:
        t = now()
        containers["c-1"] = Container(
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
            created_at=t,
            started_at=t,
            labels={"app": "hive"},
        )
    if len(memory_entries) == 0:
        t = now()
        memory_entries["mem-1"] = MemoryEntry(
            id="mem-1",
            key="default/welcome",
            value="Hive Conductor stub memory",
            namespace="default",
            tags=["seed"],
            embedding=None,
            created_at=t,
            updated_at=t,
            accessed_count=0,
            ttl_seconds=None,
        )


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
