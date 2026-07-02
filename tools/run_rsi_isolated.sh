#!/usr/bin/env bash
set -euo pipefail
# Run the FULL RSI self-improvement loop with COMPLETE isolation: the agent,
# git, tests, coverage, and the whole fitness scorecard all execute inside an
# ephemeral container. The host filesystem is never touched and nothing syncs
# back — agent-authored code only ever runs in the sandbox.
#
# This is the correct isolation model. `maistro_rsi --isolation container`
# only sandboxes the agent's *edits* and then runs the tests back on the host;
# running the whole loop in-container closes that gap (and sidesteps host-OS
# quirks like Windows temp-dir permissions).
#
# Prereqs:
#   docker build -f Dockerfile.rsi-runner -t maistro-rsi-runner:latest .
#   A running LiteLLM gateway on the host at :4000 with a `code` model group.
#
# Usage:
#   tools/run_rsi_isolated.sh [CYCLES] [ENV_FILE] [MODEL]
#     CYCLES    number of self-improvement cycles      (default 15)
#     ENV_FILE  .env with the gateway key (LITELLM_*)  (default: the install's)
#     MODEL     LiteLLM model alias for the agent      (default: code)

CYCLES="${1:-15}"
ENV_FILE="${2:-}"
MODEL="${3:-code}"
IMAGE="${MAISTRO_RSI_IMAGE:-maistro-rsi-runner:latest}"
GATEWAY_URL="${MAISTRO_RSI_GATEWAY_URL:-http://host.docker.internal:4000}"

# Locate the .env holding the gateway key if not given.
if [[ -z "$ENV_FILE" ]]; then
    for c in "/c/maistro/.env" "$HOME/.maistro/maistro-engine/.env" "C:/maistro/.env"; do
        [[ -f "$c" ]] && { ENV_FILE="$c"; break; }
    done
fi
[[ -f "$ENV_FILE" ]] || { echo "error: no gateway .env found (pass as arg 2)"; exit 2; }

# Scope tests/coverage to the evolve suite, excluding the optional-dep
# benchmarks tests that error at collection without their extras.
TEST_CMD='python -m pytest packages/maistro-evolve/tests --ignore=packages/maistro-evolve/tests/benchmarks -q'
COV_ARGS='packages/maistro-evolve/tests --ignore=packages/maistro-evolve/tests/benchmarks'
COV_SOURCE='packages/maistro-evolve/src'

# Evolve source files to improve, one per cycle (the loop rotates through them).
B='packages/maistro-evolve/src/maistro_evolve'
TARGETS="$B/serialize.py,$B/audit.py,$B/diversity.py,$B/crossover.py,$B/mutate.py,\
$B/optimizer.py,$B/population.py,$B/tournament.py,$B/reflect.py,$B/harness.py,\
$B/fitness.py,$B/cycle.py,$B/architecture_fit.py,$B/scorecard.py,$B/types.py"

echo "RSI (full isolation) -> image=$IMAGE cycles=$CYCLES model=$MODEL gateway=$GATEWAY_URL"

# Keep the gateway secret OUT of the editable workspace. Mount the .env OUTSIDE
# /workspace (so the builders agent's workspace-rooted read_file/search can't
# reach it), source it into THIS process's env only, then override the URL. The
# agent's shell commands run with a curated _SAFE_ENV that doesn't inherit these
# vars, and the clone the agent edits excludes the gitignored .env — so the key
# reaches the LiteLLM call but not the agent's tools.
exec docker run --rm \
    --add-host=host.docker.internal:host-gateway \
    -v "$ENV_FILE":/run/gateway.env:ro \
    -e "PYTHONPATH=packages/maistro-core/src:packages/maistro-evolve/src:packages/maistro-rsi/src:packages/maistro-bootstrap/src" \
    "$IMAGE" \
    bash -lc "set -a; . /run/gateway.env; set +a; \
        export LITELLM_URL='$GATEWAY_URL' LITELLM_BASE_URL='$GATEWAY_URL' LITELLM_PROXY_URL='$GATEWAY_URL'; \
        source /workspace/.venv/bin/activate && \
        python -m maistro_rsi run \
        --repo /workspace \
        --test-cmd '$TEST_CMD' \
        --cycles $CYCLES --fitness --model '$MODEL' \
        --coverage-source '$COV_SOURCE' \
        --coverage-pytest-args '$COV_ARGS' \
        --targets '$TARGETS' \
        --agent-turns 6 \
        --work-root /tmp/rsi-work"
