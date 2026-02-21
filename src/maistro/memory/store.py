"""SQLAlchemy models for PostgreSQL persistence.

Defines the database schema for tasks, memory embeddings,
and knowledge graph entries. Uses pgvector for vector search.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

try:
    from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]
except ImportError:
    Vector = None


class Base(DeclarativeBase):
    pass


class TaskRecord(Base):
    """Persistent task records for durability across restarts."""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    workspace: Mapped[str] = mapped_column(String(500), nullable=False)
    tier: Mapped[int] = mapped_column(Integer, default=2)
    phase: Mapped[str | None] = mapped_column(String(20))
    progress: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    constraints: Mapped[list[Any] | None] = mapped_column(JSONB)
    branch: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


class MemoryEntry(Base):
    """Vector-searchable memory entries for codebase knowledge."""

    __tablename__ = "memory_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    layer: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Vector embedding — 1536 dims (OpenAI ada-002 compatible)
    # Will be None if pgvector is not installed
    if Vector is not None:
        embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))


class KnowledgeNode(Base):
    """Knowledge graph nodes for module/function dependency tracking."""

    __tablename__ = "knowledge_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    node_type: Mapped[str] = mapped_column(String(50), nullable=False)  # module, function, class
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    depends_on: Mapped[list[Any] | None] = mapped_column(JSONB)  # list of node names
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (Index("ix_knowledge_workspace_type", "workspace", "node_type"),)
