"""Node catalog + registry.

Public surface:
  - :func:`register_node(cls)` — decorator + plain registration for node kinds
  - :func:`get_node(kind)` — fetch a node class by its `kind` identifier
  - :func:`list_kinds()` — enumerate all registered kinds
  - :func:`catalog_json()` — serialize the catalog for the frontend palette
  - :class:`Node`, :class:`BaseNode`, :class:`NodeContext`, :class:`NodeResult`
    (re-exported from :mod:`.base`)

Concrete node implementations import + register themselves at module import
time. Importing this package triggers the eager-import sweep so every kind
is available without callers having to discover modules manually.
"""

from __future__ import annotations

from typing import Any

from .base import (
    BaseNode,
    KindCategory,
    Node,
    NodeContext,
    NodeResult,
    now_utc,
    pause_until,
)

_REGISTRY: dict[str, type[BaseNode]] = {}


def register_node(node_cls: type[BaseNode]) -> type[BaseNode]:
    """Register a node class by its `kind` identifier. Usable as a decorator.

    Raises ``ValueError`` on:
      - kind collision (cannot register two classes with the same kind)
      - missing required ClassVars (kind, input_schema, output_schema)
    """
    kind = getattr(node_cls, "kind", "") or ""
    if not kind:
        raise ValueError(f"{node_cls.__name__} missing required `kind` ClassVar")
    for required in ("input_schema", "output_schema"):
        if not hasattr(node_cls, required):
            raise ValueError(f"{node_cls.__name__} missing required `{required}` ClassVar")
    if kind in _REGISTRY and _REGISTRY[kind] is not node_cls:
        raise ValueError(
            f"Node kind collision: {kind!r} already registered to "
            f"{_REGISTRY[kind].__name__}, refusing to overwrite with {node_cls.__name__}"
        )
    _REGISTRY[kind] = node_cls
    return node_cls


def get_node(kind: str) -> type[BaseNode]:
    """Look up a node class by kind. Raises ``KeyError`` if not registered."""
    if kind not in _REGISTRY:
        raise KeyError(
            f"No node registered for kind={kind!r}. "
            f"Available: {sorted(_REGISTRY.keys())[:10]}{'...' if len(_REGISTRY) > 10 else ''}"
        )
    return _REGISTRY[kind]


def list_kinds() -> list[str]:
    """Sorted list of all registered node kinds."""
    return sorted(_REGISTRY.keys())


def catalog_json() -> list[dict[str, Any]]:
    """Catalog serialized for the frontend palette.

    One entry per registered kind, ordered by category then kind, with the
    metadata the DagBuilder UI needs to render a draggable tile + the schemas
    it uses to validate edge connections.
    """
    entries: list[dict[str, Any]] = []
    for kind in list_kinds():
        cls = _REGISTRY[kind]
        entries.append(
            {
                "kind": cls.kind,
                "kind_category": cls.kind_category,
                "display_name": cls.display_name or cls.kind,
                "description": cls.description or "",
                "cost_hint": cls.cost_hint,
                "idempotent": cls.idempotent,
                "external_io": cls.external_io,
                "input_schema": _schema_summary(cls.input_schema),
                "output_schema": _schema_summary(cls.output_schema),
            }
        )
    entries.sort(key=lambda e: (e["kind_category"], e["kind"]))
    return entries


def _schema_summary(model_cls: type) -> dict[str, Any]:
    """Compact representation of a Pydantic schema for the frontend.

    Full JSON Schema is overkill for the palette tooltip; the UI only needs
    field name + type + required-ness for the wiring validator.
    """
    if not hasattr(model_cls, "model_fields"):
        return {"fields": []}
    fields = []
    for name, info in model_cls.model_fields.items():
        fields.append(
            {
                "name": name,
                "type": _annotation_str(info.annotation),
                "required": info.is_required(),
                "description": info.description or "",
            }
        )
    return {"name": model_cls.__name__, "fields": fields}


def _annotation_str(ann: Any) -> str:
    if ann is None:
        return "Any"
    name = getattr(ann, "__name__", None)
    if name:
        return name
    return str(ann).replace("typing.", "")


# Side-effect imports: every concrete node module self-registers on import.
# Keep this list flat + alphabetical so new kinds are obvious to add.
from . import airtable_poll  # noqa: E402, F401  registers "airtable.poll"
from . import compliance_block  # noqa: E402, F401  registers "compliance.block"
from . import dashboard_append_section  # noqa: E402, F401  registers "dashboard.append_section"
from . import human_approve_draft  # noqa: E402, F401  registers "human.approve_draft"
from . import human_ask_question  # noqa: E402, F401  registers "human.ask_question"
from . import jira_poll  # noqa: E402, F401  registers "jira.poll"
from . import jira_wait_for_subtasks  # noqa: E402, F401  registers "jira.wait_for_subtasks"
from . import llm_summarize  # noqa: E402, F401  registers "llm.summarize"
from . import transform_alias_keys  # noqa: E402, F401  registers "transform.alias_keys"
from . import transform_extract_field  # noqa: E402, F401  registers "transform.extract_field"
from . import transform_filter_by_type  # noqa: E402, F401  registers "transform.filter_by_type"
from . import transform_format_markdown  # noqa: E402, F401  registers "transform.format_markdown"


__all__ = [
    "BaseNode",
    "KindCategory",
    "Node",
    "NodeContext",
    "NodeResult",
    "catalog_json",
    "get_node",
    "list_kinds",
    "now_utc",
    "pause_until",
    "register_node",
]
