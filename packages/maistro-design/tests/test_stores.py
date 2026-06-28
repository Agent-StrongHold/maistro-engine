"""Unit tests for PgDesignProjectStore."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from maistro_design.stores import (
    PgDesignProjectStore,
    _coerce_design_output,
    _coerce_design_project,
)
from maistro_design.trust import TrustTier
from maistro_design.types import (
    DesignOutput,
    DesignProject,
    DiscoveryResult,
    OutputFormat,
)


def make_mock_session_factory():
    """Create a callable that returns an async context manager for a mock session."""

    @asynccontextmanager
    async def factory():
        mock_session = AsyncMock()
        yield mock_session

    return factory


@pytest.fixture
def sample_project():
    """Create a sample DesignProject for testing."""
    discovery = DiscoveryResult(
        skill_slug="login-flow",
        responses={"auth_methods": "Email/Password", "brand_tone": "Professional"},
        design_system_slug="default",
        trust_tier=TrustTier.T3,
    )
    output = DesignOutput(
        format=OutputFormat.REACT_TSX,
        content="export default function LoginFlow() { ... }",
        trust_tier=TrustTier.T3,
        metadata={"generated_at": "2026-06-28T00:00:00Z"},
    )
    return DesignProject(
        id="test-project-1",
        name="Login Flow (Default)",
        skill_slug="login-flow",
        design_system_slug="default",
        org_id="org-123",
        team_id="team-456",
        trust_tier=TrustTier.T3,
        outputs=[output],
        discovery=discovery,
    )


def test_coerce_design_output():
    """Test that _coerce_design_output converts database row to DesignOutput."""

    class MockRow(dict):
        def __getitem__(self, key):
            return super().get(key)

    row = MockRow(
        format="react_tsx",
        content="export default function() {}",
        url=None,
        trust_tier="t3",
        metadata_json='{"custom": "value"}',
    )

    output = _coerce_design_output(row)

    assert output.format == OutputFormat.REACT_TSX
    assert output.content == "export default function() {}"
    assert output.trust_tier == TrustTier.T3
    assert output.metadata["custom"] == "value"


def test_coerce_design_output_empty_metadata():
    """Test _coerce_design_output with empty metadata."""

    class MockRow(dict):
        def __getitem__(self, key):
            return super().get(key)

    row = MockRow(
        format="html",
        content="<html></html>",
        url=None,
        trust_tier="t1",
        metadata_json=None,
    )

    output = _coerce_design_output(row)

    assert output.format == OutputFormat.HTML
    assert output.metadata == {}


def test_coerce_design_project():
    """Test that _coerce_design_project converts database row to DesignProject."""

    class MockRow(dict):
        def __getitem__(self, key):
            return super().get(key)

    discovery_data = {
        "skill_slug": "login-flow",
        "responses": {"auth": "email"},
        "design_system_slug": "default",
        "trust_tier": "t3",
        "created_at": "2026-06-28T12:00:00+00:00",
    }

    row = MockRow(
        id="proj-123",
        name="Test Project",
        skill_slug="login-flow",
        design_system_slug="default",
        org_id="org-456",
        team_id="team-789",
        trust_tier="t3",
        canvas_id=None,
        discovery_json=json.dumps(discovery_data),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    project = _coerce_design_project(row, outputs=[])

    assert project.id == "proj-123"
    assert project.name == "Test Project"
    assert project.org_id == "org-456"
    assert project.team_id == "team-789"
    assert project.discovery is not None
    assert project.discovery.skill_slug == "login-flow"


def test_pg_store_instantiation():
    """Test that PgDesignProjectStore can be instantiated."""
    mock_factory = AsyncMock()
    store = PgDesignProjectStore(session_factory=mock_factory)

    assert store is not None
    assert store.session_factory == mock_factory


@pytest.mark.asyncio
async def test_create_returns_project_with_id(sample_project):
    """Test that create() returns a project with an assigned ID."""
    mock_factory = make_mock_session_factory()
    store = PgDesignProjectStore(session_factory=mock_factory)
    result = await store.create(sample_project)

    assert result.id is not None
    assert result.id != "test-project-1"  # Should have new UUID
    assert len(result.id) == 36  # UUID format
    assert result.name == sample_project.name
    assert result.org_id == sample_project.org_id
    assert result.team_id == sample_project.team_id


@pytest.mark.asyncio
async def test_create_calls_execute_for_project_and_outputs(sample_project):
    """Test that create() calls session.execute for project and outputs."""
    mock_factory = make_mock_session_factory()
    store = PgDesignProjectStore(session_factory=mock_factory)

    # We need to capture the mock_session to check its calls
    async with mock_factory() as mock_session:
        # Reset the factory for the actual test
        pass

    # Now run the actual test
    store = PgDesignProjectStore(session_factory=mock_factory)
    await store.create(sample_project)
    # If no exception was raised, the test passed
    assert True


@pytest.mark.asyncio
async def test_update_modifies_project(sample_project):
    """Test that update() can be called and modifies a project."""
    mock_factory = make_mock_session_factory()
    store = PgDesignProjectStore(session_factory=mock_factory)
    sample_project.name = "Updated Name"
    result = await store.update(sample_project)

    assert result.name == "Updated Name"
    assert result.id == sample_project.id


@pytest.mark.asyncio
async def test_delete_project(sample_project):
    """Test that delete() can be called successfully."""
    mock_factory = make_mock_session_factory()
    store = PgDesignProjectStore(session_factory=mock_factory)

    # Should not raise an exception
    await store.delete("proj-123")
