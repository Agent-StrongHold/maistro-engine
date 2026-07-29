"""Persona authoring pipeline — declarative domain templates (ADR-060, SPEC-192).

Public surface:

- :mod:`maistro.personas.vocabulary` — declarative check vocabulary (P0).
- :mod:`maistro.personas.rubric` — ``RubricEval`` + generic YAML loader (P0).
- :mod:`maistro.personas.scorer` — ``RubricScorer`` / optional ``DeepEvalScorer`` (P0/P1).
- :mod:`maistro.personas.schema` — persona template schema (P1).
- :mod:`maistro.personas.expander` — persona → ``AgentRecipe`` roster expansion (P1).
- :mod:`maistro.personas.golden` — versioned ``GoldenRecord`` store (P1).
"""

from __future__ import annotations

from maistro.personas.expander import ExpandedAgent, ExpandedPersona, expand_persona
from maistro.personas.golden import (
    EvidencedCriterion,
    GoldenRecord,
    GoldenRecordDiff,
    GoldenRecordStore,
    InMemoryGoldenRecordStore,
    SourceEvidence,
)
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
    "PersonaTemplate",
    "RubricEval",
    "RubricScorer",
    "SourceEvidence",
    "SpawnSpec",
    "VoiceSpec",
    "create_judge_scorer",
    "expand_persona",
    "load_evals",
    "load_templates",
]
