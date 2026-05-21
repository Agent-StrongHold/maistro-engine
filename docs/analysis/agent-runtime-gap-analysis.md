# Agent runtime gap analysis (internal)

This note replaces a retired line-by-line comparison document. **Naming policy:** maistro-engine does not host vendor-specific product comparisons in-tree.

The **five gap dimensions** below remain the engineering backlog signal (see [ADR-003](../adr/ADR-003-agent-runtime-gap-resolution.md)):

| # | Dimension | Snapshot at time of ADR-003 |
|---|-----------|------------------------------|
| 1 | Identity / personality beyond static system prompt | Missing |
| 2 | Memory wiring vs schema-only | Partial |
| 3 | Workspace context depth | Minimal |
| 4 | Scheduled autonomy (`scheduler/`) | Empty |
| 5 | Runtime skill discovery vs hardcoded | Hardcoded |

Track closure in the ADR tranches referenced from ADR-003.
