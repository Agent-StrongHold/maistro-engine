"""Persona authoring + live product-context domain.

Public surface:

- :mod:`maistro.personas.model` — live Workspace-owned ``Persona`` and known surfaces.
- :mod:`maistro.personas.vocabulary` — declarative check vocabulary (P0).
- :mod:`maistro.personas.rubric` — ``RubricEval`` + generic YAML loader (P0).
- :mod:`maistro.personas.scorer` — ``RubricScorer`` / optional ``DeepEvalScorer`` (P0/P1).
- :mod:`maistro.personas.schema` — reusable persona template schema (P1).
- :mod:`maistro.personas.expander` — persona template → ``AgentRecipe`` roster expansion (P1).
- :mod:`maistro.personas.golden` — versioned ``GoldenRecord`` store (P1).
"""

from __future__ import annotations

from maistro.personas.checklist import (
    CapabilityItem,
    capability_checklist,
    default_checklist_ids,
)
from maistro.personas.expander import ExpandedAgent, ExpandedPersona, expand_persona
from maistro.personas.golden import (
    EvidencedCriterion,
    GoldenRecord,
    GoldenRecordDiff,
    GoldenRecordStore,
    InMemoryGoldenRecordStore,
    SourceEvidence,
)
from maistro.personas.model import Persona, PersonaSurface
from maistro.personas.rubric import EvalResult, RubricEval, load_evals, load_templates
from maistro.personas.schema import (
    BrandSpec,
    CriterionSpec,
    EvalSpec,
    PersonaTemplate,
    SpawnSpec,
    VoiceSpec,
)
from maistro.personas.scorer import DeepEvalScorer, RubricScorer, create_judge_scorer

__all__ = [
    "BrandSpec",
    "CapabilityItem",
    "CriterionSpec",
    "DeepEvalScorer",
    "EvalResult",
    "EvalSpec",
    "EvidencedCriterion",
    "ExpandedAgent",
    "ExpandedPersona",
    "GoldenRecord",
    "GoldenRecordDiff",
    "GoldenRecordStore",
    "InMemoryGoldenRecordStore",
    "Persona",
    "PersonaSurface",
    "PersonaTemplate",
    "RubricEval",
    "RubricScorer",
    "SourceEvidence",
    "SpawnSpec",
    "VoiceSpec",
    "capability_checklist",
    "create_judge_scorer",
    "default_checklist_ids",
    "expand_persona",
    "load_evals",
    "load_templates",
]
