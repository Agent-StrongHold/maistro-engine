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
#   tools/run_rsi_isolated.sh [CYCLES] [ENV_FILE] [MODEL] [REPORT_EVERY] [REPORT_DIR]
#     CYCLES        number of self-improvement cycles       (default 150)
#     ENV_FILE      .env with the gateway key (LITELLM_*)   (default: the install's)
#     MODEL         LiteLLM model alias for the agent       (default: code)
#     REPORT_EVERY  emit a checkpoint report every N cycles (default 5; 0 = end only)
#     REPORT_DIR    host dir to receive reports + export/   (default ./rsi-reports/<ts>)
#
# The baseline ratchets forward across the WHOLE run — a checkpoint is an
# observation point, not a reset — so each report covers cumulative progress and
# REPORT_DIR/export/ always holds the complete promotion set to date (harvestable,
# and recoverable if a long run is interrupted). REPORT_DIR is mounted at
# /run/reports, OUTSIDE the edited /workspace, so the agent can't see or touch it.

CYCLES="${1:-150}"
ENV_FILE="${2:-}"
MODEL="${3:-code}"
REPORT_EVERY="${4:-5}"
REPORT_DIR="${5:-}"
IMAGE="${MAISTRO_RSI_IMAGE:-maistro-rsi-runner:latest}"
# The LiteLLM gateway is published to host-loopback only (compose maps
# 127.0.0.1:4000:4000), so it is NOT reachable via host.docker.internal. Instead
# join the compose network and reach the gateway by its container name. We use
# the container name `maistro-litellm` (not the `litellm` service alias) on
# purpose: the builders agent rewrites a `://litellm:` URL to 127.0.0.1 (a
# bare-host convenience that would misfire in-container), and that pattern does
# not match `://maistro-litellm:`.
# Default to whatever network the gateway container is actually on. Compose names
# the default network `<project>_default`, which varies by layout — `maistro_default`
# for the C:\maistro install, `maistro-engine_default` for a repo-root `docker
# compose up` — so hardcoding one breaks the other. The `maistro-litellm`
# container_name is fixed across layouts, so inspect it; fall back if it's not up.
NETWORK="${MAISTRO_RSI_NETWORK:-}"
if [[ -z "$NETWORK" ]]; then
    NETWORK="$(docker inspect maistro-litellm \
        --format '{{range $k,$_ := .NetworkSettings.Networks}}{{$k}}{{"\n"}}{{end}}' \
        2>/dev/null | head -1)"
    NETWORK="${NETWORK:-maistro_default}"
fi
GATEWAY_URL="${MAISTRO_RSI_GATEWAY_URL:-http://maistro-litellm:4000}"

# Default the reports dir to a timestamped host dir next to the repo, and make it
# an absolute path docker can bind-mount.
if [[ -z "$REPORT_DIR" ]]; then
    REPORT_DIR="$(pwd)/rsi-reports/$(date +%Y%m%d-%H%M%S)"
fi
mkdir -p "$REPORT_DIR"
REPORT_DIR="$(cd "$REPORT_DIR" && pwd)"

# Locate the .env holding the gateway key if not given.
if [[ -z "$ENV_FILE" ]]; then
    for c in "/c/maistro/.env" "$HOME/.maistro/maistro-engine/.env" "C:/maistro/.env"; do
        [[ -f "$c" ]] && { ENV_FILE="$c"; break; }
    done
fi
[[ -f "$ENV_FILE" ]] || { echo "error: no gateway .env found (pass as arg 2)"; exit 2; }

# Windows/git-bash: docker.exe needs Windows-style mount SOURCES, and MSYS path
# conversion would otherwise rewrite the container-side mount TARGETS
# (/run/gateway.env, /run/reports) into Windows paths and silently break both
# mounts — the symptom is "stub" LLM responses (the .env never mounts) and empty
# host reports. Convert sources to mixed (C:/...) form and disable MSYS conversion
# for the docker call. No-op on Linux/macOS (cygpath absent).
ENV_MOUNT="$ENV_FILE"
REPORT_MOUNT="$REPORT_DIR"
if command -v cygpath >/dev/null 2>&1; then
    ENV_MOUNT="$(cygpath -m "$ENV_FILE")"
    REPORT_MOUNT="$(cygpath -m "$REPORT_DIR")"
    export MSYS_NO_PATHCONV=1
fi

# Scope tests/coverage to the evolve + rsi suites, excluding the optional-dep
# benchmarks tests that error at collection without their extras. Relative paths
# resolve under each candidate worktree, so the tests exercise the candidate's
# own edited source (not the container's installed copy).
TEST_CMD='python -m pytest packages/maistro-evolve/tests packages/maistro-rsi/tests --ignore=packages/maistro-evolve/tests/benchmarks -q'
COV_ARGS='packages/maistro-evolve/tests packages/maistro-rsi/tests --ignore=packages/maistro-evolve/tests/benchmarks'
COV_SOURCE='packages/maistro-evolve/src,packages/maistro-rsi/src'

# Source files to improve, one per cycle (the loop rotates through them), drawn
# from BOTH target packages.
E='packages/maistro-evolve/src/maistro_evolve'
R='packages/maistro-rsi/src/maistro_rsi'
TARGETS="$E/serialize.py,$E/audit.py,$E/diversity.py,$E/crossover.py,$E/mutate.py,\
$E/optimizer.py,$E/population.py,$E/tournament.py,$E/reflect.py,$E/harness.py,\
$E/fitness.py,$E/cycle.py,$E/architecture_fit.py,$E/scorecard.py,$E/types.py,\
$R/merge.py,$R/competitors.py,$R/scout.py,$R/harvest.py,$R/evolve_bridge.py,\
$R/candidate_fitness.py,$R/quota_burn.py,$R/quarantine.py,$R/htr.py,$R/coordinator.py"

echo "RSI (full isolation) -> image=$IMAGE cycles=$CYCLES model=$MODEL gateway=$GATEWAY_URL"
echo "  reports -> $REPORT_DIR (every $REPORT_EVERY cycles)"

# Keep the gateway secret OUT of the editable workspace. Mount the .env OUTSIDE
# /workspace (so the builders agent's workspace-rooted read_file/search can't
# reach it), source it into THIS process's env only, then override the URL. The
# agent's shell commands run with a curated _SAFE_ENV that doesn't inherit these
# vars, and the clone the agent edits excludes the gitignored .env — so the key
# reaches the LiteLLM call but not the agent's tools.
# Mount the reports dir RW at /run/reports — OUTSIDE /workspace, so checkpoint
# reports + the rolling export leave the container while staying invisible to the
# workspace-rooted agent tools.
exec docker run --rm \
    --network "$NETWORK" \
    --add-host=host.docker.internal:host-gateway \
    -v "${ENV_MOUNT}:/run/gateway.env:ro" \
    -v "${REPORT_MOUNT}:/run/reports" \
    -e "PYTHONPATH=packages/maistro-core/src:packages/maistro-evolve/src:packages/maistro-rsi/src:packages/maistro-bootstrap/src" \
    "$IMAGE" \
    bash -lc "sed 's/\r\$//' /run/gateway.env > /tmp/gw.env; set -a; . /tmp/gw.env; set +a; \
        export LITELLM_URL='$GATEWAY_URL' LITELLM_BASE_URL='$GATEWAY_URL' LITELLM_PROXY_URL='$GATEWAY_URL'; \
        unset DB_PASSWORD LANGFUSE_PUBLIC_KEY LANGFUSE_SECRET_KEY LANGFUSE_NEXTAUTH_SECRET LANGFUSE_SALT \
              API_KEYS MAISTRO_ACCESS_TOKEN OPENAI_API_KEY ANTHROPIC_API_KEY GEMINI_API_KEY MISTRAL_API_KEY \
              GROQ_API_KEY CEREBRAS_API_KEY COHERE_API_KEY NVIDIA_API_KEY OPENROUTER_API_KEY SAMBANOVA_API_KEY \
              XAI_API_KEY DEEPSEEK_API_KEY TOGETHER_API_KEY FIREWORKS_API_KEY DEEPINFRA_API_KEY 2>/dev/null || true; \
        source /workspace/.venv/bin/activate && \
        python -m maistro_rsi run \
        --repo /workspace \
        --test-cmd '$TEST_CMD' \
        --cycles $CYCLES --fitness --model '$MODEL' \
        --coverage-source '$COV_SOURCE' \
        --coverage-pytest-args '$COV_ARGS' \
        --targets '$TARGETS' \
        --agent-turns 6 \
        --scout \
        --report-every $REPORT_EVERY \
        --report-dir /run/reports \
        --work-root /tmp/rsi-work"
