"""YAML-to-RubricEval loader (ADR-060).

Loads a template YAML (kind: department|creator|author) and returns
instantiated RubricEval objects ready to call .score(output, context).

Usage
-----
    evals = load_department("templates/marketing.yaml")
    result = await evals[0].score(my_text)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from eval.departments import RubricEval
from eval.vocabulary import evaluate

# Canonical template root — one tree, kind: field discriminates department/creator/author.
_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def _make_check(criterion_spec: dict[str, Any]):
    check_spec = dict(criterion_spec["check"])

    def check(output: str, context: dict[str, Any]) -> bool:
        return evaluate(check_spec, output, context)

    return check


def _build_rubric_eval(name: str, eval_spec: dict[str, Any]) -> RubricEval:
    criteria = [
        {
            "name": c["name"],
            "weight": int(c["weight"]),
            "check": _make_check(c),
        }
        for c in eval_spec.get("criteria", [])
    ]
    DynamicEval = type(
        f"Yaml_{name}_{eval_spec['name']}",
        (RubricEval,),
        {
            "department": name,
            "eval_name": eval_spec["name"],
            "criteria": criteria,
        },
    )
    return DynamicEval()


def load_department(path: str | Path) -> list[RubricEval]:
    """Load a template YAML and return one RubricEval per eval block."""
    data = yaml.safe_load(Path(path).read_text())
    # Support both new schema (name:) and legacy (department:) key.
    name = data.get("name") or data["department"]
    return [_build_rubric_eval(name, ev) for ev in data.get("evals", [])]


def all_departments() -> dict[str, list[RubricEval]]:
    """Return {name: [RubricEval, ...]} for every kind=department template."""
    result: dict[str, list[RubricEval]] = {}
    if not _TEMPLATES_DIR.exists():
        return result
    for yaml_file in sorted(_TEMPLATES_DIR.glob("*.yaml")):
        data = yaml.safe_load(yaml_file.read_text())
        if data.get("kind") != "department":
            continue
        evals = load_department(yaml_file)
        if evals:
            result[evals[0].department] = evals
    return result
