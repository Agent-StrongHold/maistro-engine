---
name: adr
description: Scaffold a new Architecture Decision Record in docs/adr/. Follows the existing ADR-NNN-slug.md naming convention. Pass a short title as the argument, e.g. /adr graph-caching-strategy
disable-model-invocation: false
---

The user wants to create a new ADR. The argument is $ARGUMENTS (the short title/slug).

Steps:
1. Run `ls docs/adr/ | sort | tail -3` to find the highest existing ADR number.
2. Compute the next number (zero-padded to 3 digits, e.g. ADR-043).
3. Convert $ARGUMENTS to kebab-case for the filename slug.
4. Create the file at `docs/adr/ADR-NNN-<slug>.md` with this template:

```markdown
# ADR-NNN — <Title>

**Status:** Proposed
**Date:** <today's date>

## Context

<What is the situation that motivates this decision?>

## Decision

<What is the change we're making?>

## Consequences

### Positive
- 

### Negative / Trade-offs
- 

### Neutral
- 
```

5. Show the user the created file path and remind them to update the status (Proposed → Accepted) once agreed.
