# Main/develop history reconciliation

This temporary marker exists only to create a normal merge commit from the historical `main` lineage into `develop` without rewriting protected branch history.

After the merge commit is created, this file is removed from `develop`. The merge commit remains in history, making the historical `main` promotion commit an ancestor of `develop` so the final `develop` → `main` promotion can proceed normally.
