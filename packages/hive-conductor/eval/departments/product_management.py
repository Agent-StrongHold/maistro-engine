"""Product Management evals — requirements completeness, stakeholder alignment, prioritization, decomposition, timeline."""

from __future__ import annotations

import re
from typing import ClassVar

from eval.departments import RubricEval


class RequirementsCompleteness(RubricEval):
    department = "product_management"
    eval_name = "requirements_completeness"
    criteria: ClassVar = [
        {
            "name": "has_user_stories",
            "weight": 20,
            "check": lambda o, c: "as a" in o.lower() and "i want" in o.lower(),
        },
        {
            "name": "has_acceptance_criteria",
            "weight": 25,
            "check": lambda o, c: any(
                w in o.lower() for w in ["acceptance criteria", "given", "when", "then"]
            ),
        },
        {
            "name": "has_non_functional",
            "weight": 20,
            "check": lambda o, c: any(
                w in o.lower() for w in ["performance", "security", "scalability", "availability"]
            ),
        },
        {
            "name": "has_constraints",
            "weight": 15,
            "check": lambda o, c: any(
                w in o.lower() for w in ["constraint", "limitation", "assumption", "out of scope"]
            ),
        },
        {
            "name": "measurable",
            "weight": 20,
            "check": lambda o, c: bool(re.search(r"\d+%|\d+\s*(ms|seconds|users)", o)),
        },
    ]


class StakeholderAlignment(RubricEval):
    department = "product_management"
    eval_name = "stakeholder_alignment"
    criteria: ClassVar = [
        {
            "name": "identifies_stakeholders",
            "weight": 25,
            "check": lambda o, c: any(
                w in o.lower() for w in ["stakeholder", "user", "customer", "engineering", "design"]
            ),
        },
        {
            "name": "addresses_concerns",
            "weight": 25,
            "check": lambda o, c: any(
                w in o.lower() for w in ["concern", "risk", "tradeoff", "trade-off", "impact"]
            ),
        },
        {
            "name": "clear_ownership",
            "weight": 25,
            "check": lambda o, c: any(
                w in o.lower() for w in ["owner", "responsible", "accountable", "dri"]
            ),
        },
        {
            "name": "communication_plan",
            "weight": 25,
            "check": lambda o, c: any(
                w in o.lower() for w in ["update", "sync", "review", "demo", "communicate"]
            ),
        },
    ]


class PrioritizationLogic(RubricEval):
    department = "product_management"
    eval_name = "prioritization_logic"
    criteria: ClassVar = [
        {
            "name": "uses_framework",
            "weight": 25,
            "check": lambda o, c: any(
                w in o.lower() for w in ["rice", "moscow", "ice", "impact", "effort", "value"]
            ),
        },
        {
            "name": "quantified",
            "weight": 25,
            "check": lambda o, c: bool(re.search(r"(score|priority|rank).*\d+", o.lower())),
        },
        {
            "name": "justifies_ranking",
            "weight": 25,
            "check": lambda o, c: any(
                w in o.lower() for w in ["because", "since", "due to", "rationale"]
            ),
        },
        {
            "name": "considers_dependencies",
            "weight": 25,
            "check": lambda o, c: any(
                w in o.lower() for w in ["depends on", "blocked by", "prerequisite"]
            ),
        },
    ]


class DecompositionQuality(RubricEval):
    department = "product_management"
    eval_name = "decomposition_quality"
    criteria: ClassVar = [
        {
            "name": "atomic_tasks",
            "weight": 25,
            "check": lambda o, c: len(re.findall(r"^[\-\*]\s|^\d+\.", o, re.MULTILINE)) >= 5,
        },
        {
            "name": "estimable",
            "weight": 25,
            "check": lambda o, c: any(
                w in o.lower() for w in ["point", "hour", "day", "sprint", "estimate"]
            ),
        },
        {
            "name": "independent",
            "weight": 25,
            "check": lambda o, c: any(
                w in o.lower() for w in ["independent", "parallel", "standalone"]
            ),
        },
        {
            "name": "testable",
            "weight": 25,
            "check": lambda o, c: any(
                w in o.lower() for w in ["test", "verify", "validate", "acceptance"]
            ),
        },
    ]


class TimelineRealism(RubricEval):
    department = "product_management"
    eval_name = "timeline_realism"
    criteria: ClassVar = [
        {
            "name": "has_dates",
            "weight": 20,
            "check": lambda o, c: bool(re.search(r"\d{4}[-/]\d{2}|week \d|sprint \d|Q[1-4]", o)),
        },
        {
            "name": "includes_buffer",
            "weight": 20,
            "check": lambda o, c: any(
                w in o.lower() for w in ["buffer", "contingency", "slack", "risk"]
            ),
        },
        {
            "name": "phased_delivery",
            "weight": 20,
            "check": lambda o, c: any(
                w in o.lower() for w in ["phase", "milestone", "mvp", "iteration"]
            ),
        },
        {
            "name": "resource_aware",
            "weight": 20,
            "check": lambda o, c: any(
                w in o.lower() for w in ["resource", "team size", "capacity", "bandwidth"]
            ),
        },
        {
            "name": "dependencies_mapped",
            "weight": 20,
            "check": lambda o, c: any(
                w in o.lower() for w in ["depends", "blocked", "critical path"]
            ),
        },
    ]


ALL_EVALS = [
    RequirementsCompleteness,
    StakeholderAlignment,
    PrioritizationLogic,
    DecompositionQuality,
    TimelineRealism,
]
