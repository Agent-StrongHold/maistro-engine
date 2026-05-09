"""Front-matter registry validator and generator.

Implements [engine#engine-001] per [engine#ADR-031].
Validates ADR/spec front-matter, checks cross-references, generates
the canonical registry. Warn-only during the rollout window; hard
fail after day 30 (per `engine#ADR-031` §6).

No new external deps: uses pyyaml + Pydantic v2, both already in
`pyproject.toml`. Conforms to `engine#ADR-039` substrate posture
(no new pip deps for the engine).
"""

__version__ = "0.1.0"
