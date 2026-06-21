#!/usr/bin/env bash
# Fast-forward the sibling product repo so maistro-engine work traces current specs.
# See docs/archive/CONSOLIDATION-PLAN.md § "Sibling product specs".
set -euo pipefail

root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${root}" ]]; then
  echo "Run from inside maistro-engine (git repo)." >&2
  exit 1
fi

repo="${MAISTRO_PRODUCT_REPO:-$(dirname "${root}")/Project_mAIstro}"

if [[ ! -d "${repo}/.git" ]]; then
  echo "Product repo not found at: ${repo}" >&2
  echo "Clone it beside maistro-engine or set MAISTRO_PRODUCT_REPO to the absolute path." >&2
  exit 1
fi

echo "Pulling: ${repo}"
git -C "${repo}" pull --ff-only

if [[ -d "${repo}/specs" ]]; then
  n="$(find "${repo}/specs" -type f -name '*.md' 2>/dev/null | wc -l | tr -d ' ')"
  echo "specs/: ${n} markdown file(s). Link driving paths in maistro-engine PR descriptions."
else
  echo "No specs/ directory at ${repo}/specs — check branch." >&2
  exit 1
fi
