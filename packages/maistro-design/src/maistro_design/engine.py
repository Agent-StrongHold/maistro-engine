"""DesignEngine — discovery form → Warden scan → trust assignment → prompt stack.

The engine builds the prompt stack and creates artifacts but does NOT call an LLM.
The caller passes the assembled output to maistro-core's conduit (ADR-019 / ADR-058).

Trust contamination: context_trust_tier is monotonically decreasing per instance.
One engine instance per session; callers manage session lifecycle.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from maistro_design.trust import (
    InMemoryTrustBanishList,
    InMemoryTrustReviewQueue,
    TrustTier,
    scan_and_record,
)
from maistro_design.types import (
    DesignOutput,
    DesignProject,
    DesignSystemNotFoundError,
    DiscoveryIncompleteError,
    DiscoveryResult,
    IncompatibleDesignSystemError,
    OutputFormat,
    SkillModeError,
    SkillMode,
    SkillNotFoundError,
    TrustBannedError,
)

if TYPE_CHECKING:
    from maistro_canvas.protocols import CanvasStore, ImageGenClient

    from maistro_design.protocols import DesignSkillRegistry, DesignSystemRegistry


class DesignEngine:
    """Orchestrates skill → discovery → Warden scan → prompt stack → canvas/A2A.

    One instance per session. context_trust_tier is monotonically decreasing.
    """

    def __init__(
        self,
        skill_registry: DesignSkillRegistry,
        system_registry: DesignSystemRegistry,
        banish_list: InMemoryTrustBanishList | None = None,
        trust_review_queue: InMemoryTrustReviewQueue | None = None,
        canvas_store: CanvasStore | None = None,
        image_gen: ImageGenClient | None = None,
    ) -> None:
        self._skills = skill_registry
        self._systems = system_registry
        self._banish_list = banish_list if banish_list is not None else InMemoryTrustBanishList()
        self._trust_review_queue = trust_review_queue if trust_review_queue is not None else InMemoryTrustReviewQueue()
        self._canvas_store = canvas_store
        self._image_gen = image_gen
        self._context_trust_tier: TrustTier = TrustTier.T0

    @property
    def context_trust_tier(self) -> TrustTier:
        return self._context_trust_tier

    def _contaminate(self, tier: TrustTier) -> None:
        self._context_trust_tier = self._context_trust_tier.min(tier)

    async def run_discovery(self, skill_slug: str) -> list[dict[str, Any]]:
        """Return the skill's discovery form as a list of serialisable dicts.

        Raises SkillNotFoundError for unknown slugs.
        """
        skill = self._skills.get(skill_slug)
        if skill is None:
            msg = f"Design skill '{skill_slug}' not found"
            raise SkillNotFoundError(msg)
        return [f.to_dict() for f in skill.discovery_form]

    async def generate(self, discovery: DiscoveryResult) -> DesignProject:
        """Build a DesignProject from completed discovery responses.

        Pipeline:
          1. Resolve skill + design system; check compatibility
          2. Fail loudly if image-mode skill and no image_gen
          3. Banish-list pre-scan each response
          4. Warden scan each response → assign tier → contaminate context
          5. Validate required discovery fields
          6. Assemble prompt stack
          7. Optionally create CanvasRecord
          8. Return DesignProject at effective context_trust_tier
        """
        # 1. Resolve skill
        skill = self._skills.get(discovery.skill_slug)
        if skill is None:
            msg = f"Design skill '{discovery.skill_slug}' not found"
            raise SkillNotFoundError(msg)

        # 2. Resolve design system
        system = self._systems.get(discovery.design_system_slug)
        if system is None:
            msg = f"Design system '{discovery.design_system_slug}' not found"
            raise DesignSystemNotFoundError(msg)

        # 3. Compatibility check
        if skill.compatible_design_systems and discovery.design_system_slug not in skill.compatible_design_systems:
            msg = (
                f"Skill '{skill.slug}' is not compatible with design system "
                f"'{discovery.design_system_slug}'. "
                f"Compatible: {skill.compatible_design_systems}"
            )
            raise IncompatibleDesignSystemError(msg)

        # 4. Fail fast for image-mode without image_gen
        if skill.mode == SkillMode.IMAGE and self._image_gen is None:
            msg = (
                f"Skill '{skill.slug}' requires an image generation client "
                f"(mode={skill.mode}) but none was provided to DesignEngine."
            )
            raise SkillModeError(msg)

        # 5. Contaminate context with skill + system trust tiers
        self._contaminate(skill.trust_tier)
        self._contaminate(system.trust_tier)
        self._contaminate(discovery.trust_tier)

        # 6. Scan each discovery response through banish list + record for review
        for key, value in discovery.responses.items():
            if self._banish_list.is_banned(value):
                msg = f"Discovery response for field '{key}' matches a banished pattern"
                raise TrustBannedError(msg)

            response_tier = scan_and_record(
                value,
                source="discovery_field",
                source_key=key,
                record_id=str(uuid.uuid4()),
                banish_list=self._banish_list,
                review_queue=self._trust_review_queue,
            )
            self._contaminate(response_tier)

        # 7. Validate required fields
        for field in skill.discovery_form:
            if field.required and field.key not in discovery.responses:
                msg = (
                    f"Required discovery field '{field.key}' ('{field.label}') "
                    f"is missing for skill '{skill.slug}'"
                )
                raise DiscoveryIncompleteError(msg)

        # 8. Assemble prompt stack
        prompt_parts: list[str] = []
        if skill.system_prompt:
            prompt_parts.append(f"## Skill Instructions\n{skill.system_prompt}")
        if system.design_md:
            prompt_parts.append(f"## Design System: {system.name}\n{system.design_md}")
        elif system.tokens_css:
            prompt_parts.append(f"## Design Tokens ({system.name})\n```css\n{system.tokens_css}\n```")

        if discovery.responses:
            response_lines = "\n".join(f"- **{k}**: {v}" for k, v in discovery.responses.items())
            prompt_parts.append(f"## Discovery Responses\n{response_lines}")

        prompt_stack = "\n\n".join(prompt_parts)

        output = DesignOutput(
            format=OutputFormat.MARKDOWN,
            content=prompt_stack,
            trust_tier=self._context_trust_tier,
        )

        # 9. Optionally create a canvas record for visual output modes
        canvas_id: str | None = None
        if self._canvas_store is not None and skill.mode in (SkillMode.IMAGE, SkillMode.TEMPLATE):
            canvas_record = await self._canvas_store.create_canvas(
                name=f"{skill.name} — {discovery.design_system_slug}",
                width=1920,
                height=1080,
            )
            canvas_id = canvas_record.id

        project_id = str(uuid.uuid4())
        return DesignProject(
            id=project_id,
            name=f"{skill.name} ({system.name})",
            skill_slug=skill.slug,
            design_system_slug=system.slug,
            trust_tier=self._context_trust_tier,
            canvas_id=canvas_id,
            outputs=[output],
            discovery=discovery,
        )
