"""Design skill routes — project creation, discovery, artifact retrieval.

POST /design/projects — generate design project
GET /design/projects/{id} — fetch project + outputs
GET /design/projects — list org projects
GET /design/skills — list available skills
GET /design/skills/{slug}/discovery — get skill discovery form
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from services.design_service import get_design_engine, get_design_store

from maistro_design.types import (
    DesignError,
    DesignSystemNotFoundError,
    DiscoveryIncompleteError,
    DiscoveryResult,
    SkillNotFoundError,
)

router = APIRouter(prefix="/design", tags=["design"])


@router.post("/projects")
async def create_design_project(discovery: DiscoveryResult) -> dict[str, Any]:
    """Generate a design project from discovery responses.

    Pipeline:
    1. Validate skill + design system exist
    2. Scan discovery responses (Warden)
    3. Assemble prompt stack
    4. Persist project + outputs to database

    Request body:
      {skill_slug, responses, design_system_slug, trust_tier}

    Returns:
      {id, name, skill_slug, design_system_slug, org_id, team_id, trust_tier,
       output_count, created_at, updated_at}
    """
    try:
        engine = get_design_engine()
        # TODO: extract org_id from request auth context
        org_id = "default-org"
        project = await engine.generate(discovery, org_id=org_id, team_id=None)
        return project.to_dict()
    except SkillNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DesignSystemNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DiscoveryIncompleteError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except DesignError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {e!s}")


@router.get("/projects/{project_id}")
async def get_design_project(project_id: str) -> dict[str, Any]:
    """Fetch a design project with all outputs.

    Returns:
      {id, name, skill_slug, design_system_slug, org_id, team_id, trust_tier,
       outputs: [{format, content, url, trust_tier, metadata}], discovery: {...}, ...}
    """
    try:
        store = get_design_store()
        project = await store.get(project_id)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        return project.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects")
async def list_design_projects(skill_slug: str | None = None) -> list[dict[str, Any]]:
    """List design projects for an org, optionally filtered by skill.

    Query params:
      skill_slug: filter by skill (e.g. "login-flow")

    Returns:
      [{id, name, skill_slug, design_system_slug, org_id, output_count, created_at, ...}]
    """
    try:
        store = get_design_store()
        # TODO: extract org_id from request auth context
        org_id = "default-org"

        if skill_slug:
            projects = await store.list_by_skill(skill_slug, org_id)
        else:
            projects = await store.list_by_org(org_id)

        return [p.to_dict() for p in projects]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/skills")
async def list_design_skills() -> list[dict[str, Any]]:
    """List all available design skills (registered in engine).

    Returns:
      [{slug, name, mode, description, featured, output_formats, tags, discovery_form}]
    """
    try:
        engine = get_design_engine()
        skills = engine._skills.list_all()
        return [
            {
                "slug": s.slug,
                "name": s.name,
                "mode": s.mode.value,
                "description": s.description,
                "featured": s.featured,
                "output_formats": [fmt.value for fmt in s.output_formats],
                "tags": s.tags,
                "discovery_form": [f.to_dict() for f in s.discovery_form],
            }
            for s in skills
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/skills/{skill_slug}/discovery")
async def get_skill_discovery_form(skill_slug: str) -> list[dict[str, Any]]:
    """Get the discovery form for a skill.

    Used by frontend to render the skill configuration form.

    Returns:
      [{key, label, description, field_type, options, required, default}]
    """
    try:
        engine = get_design_engine()
        form = await engine.run_discovery(skill_slug)
        return form
    except SkillNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
