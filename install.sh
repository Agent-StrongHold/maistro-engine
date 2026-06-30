#!/usr/bin/env bash
set -euo pipefail

# maistro-engine local installer.
#
# This script is intentionally conservative:
#   - it asks feature/deployment questions through maistro-install when a TTY exists;
#   - it preserves existing .env files and appends only missing runtime keys;
#   - it binds services to localhost by default;
#   - it starts the checked-out source tree with docker/podman compose.

COMPOSE_FILE="${MAISTRO_COMPOSE_FILE:-docker-compose.yml}"
ENV_FILE="${MAISTRO_ENV_FILE:-.env}"
BIND_HOST="${MAISTRO_BIND_HOST:-127.0.0.1}"
PORT="${MAISTRO_PORT:-8000}"
PLAN_DIR="${MAISTRO_INSTALL_PLAN_DIR:-.maistro-install}"
ANSWERS_FILE="${MAISTRO_INSTALL_ANSWERS:-}"
SKIP_WIZARD="${MAISTRO_SKIP_WIZARD:-0}"
START_STACK="${MAISTRO_START_STACK:-1}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PYTHON_CMD=()
UV_CMD=()
COMPOSE_CMD=()

info() { echo -e "${BLUE}[maistro]${NC} $*"; }
ok() { echo -e "${GREEN}[ok]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }
fail() { echo -e "${RED}[error]${NC} $*" >&2; exit 1; }

usage() {
    cat <<EOF
Usage: ./install.sh [options]

Options:
  --answers-file PATH  Use a maistro-install answers YAML file instead of prompts.
  --skip-wizard       Skip the feature/deployment questionnaire.
  --no-start          Generate/repair files but do not start compose.
  --plan-dir PATH     Directory for materialized install plan artifacts.
  -h, --help          Show this help.

Environment:
  MAISTRO_DIR, MAISTRO_PORT, MAISTRO_BIND_HOST, MAISTRO_INSTALL_ANSWERS,
  MAISTRO_SKIP_WIZARD, MAISTRO_START_STACK, MAISTRO_COMPOSE_FILE.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --answers-file)
            [[ $# -ge 2 ]] || fail "--answers-file requires a path"
            ANSWERS_FILE="$2"
            shift 2
            ;;
        --skip-wizard)
            SKIP_WIZARD=1
            shift
            ;;
        --no-start)
            START_STACK=0
            shift
            ;;
        --plan-dir)
            [[ $# -ge 2 ]] || fail "--plan-dir requires a path"
            PLAN_DIR="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            fail "Unknown option: $1"
            ;;
    esac
done

ensure_python() {
    if [[ ${#PYTHON_CMD[@]} -gt 0 ]]; then
        return
    fi

    local candidate
    for candidate in python3 python; do
        if command -v "$candidate" >/dev/null 2>&1 && "$candidate" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
        then
            PYTHON_CMD=("$candidate")
            ok "Python found: $("$candidate" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
            return
        fi
    done

    if command -v py >/dev/null 2>&1 && py -3 - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
    then
        PYTHON_CMD=(py -3)
        ok "Python found: $(py -3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
        return
    fi

    fail "Python 3.11+ is required. Install Python, then re-run ./install.sh."
}

ensure_uv() {
    if [[ ${#UV_CMD[@]} -gt 0 ]]; then
        return
    fi

    if command -v uv >/dev/null 2>&1; then
        UV_CMD=(uv)
        ok "uv found: $(uv --version)"
        return
    fi

    ensure_python
    info "Installing uv into the current user's Python environment..."
    "${PYTHON_CMD[@]}" -m pip install --user --quiet uv

    if "${PYTHON_CMD[@]}" -m uv --version >/dev/null 2>&1; then
        UV_CMD=("${PYTHON_CMD[@]}" -m uv)
        ok "uv installed: $("${PYTHON_CMD[@]}" -m uv --version)"
        return
    fi

    if command -v uv >/dev/null 2>&1; then
        UV_CMD=(uv)
        ok "uv installed: $(uv --version)"
        return
    fi

    fail "uv installed, but the executable is not on PATH. Add the Python user scripts directory to PATH and retry."
}

random_secret() {
    local prefix="${1:-}"
    local bytes="${2:-32}"
    "${PYTHON_CMD[@]}" - "$prefix" "$bytes" <<'PY'
import secrets
import sys

prefix = sys.argv[1]
size = int(sys.argv[2])
print(prefix + secrets.token_urlsafe(size))
PY
}

env_has() {
    local key="$1"
    [[ -f "$ENV_FILE" ]] && grep -qE "^${key}=" "$ENV_FILE"
}

env_get() {
    local key="$1"
    if [[ -f "$ENV_FILE" ]]; then
        grep -E "^${key}=" "$ENV_FILE" | tail -n 1 | cut -d= -f2- || true
    fi
}

append_env_once() {
    local key="$1"
    local value="$2"
    if ! env_has "$key"; then
        printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
    fi
}

append_provider_placeholders() {
    local key
    for key in \
        OPENAI_API_KEY \
        ANTHROPIC_API_KEY \
        GEMINI_API_KEY \
        CEREBRAS_API_KEY \
        COHERE_API_KEY \
        GROQ_API_KEY \
        MISTRAL_API_KEY \
        NVIDIA_API_KEY \
        OPENROUTER_API_KEY \
        SAMBANOVA_API_KEY \
        XAI_API_KEY \
        DEEPSEEK_API_KEY \
        TOGETHER_API_KEY \
        FIREWORKS_API_KEY \
        DEEPINFRA_API_KEY
    do
        append_env_once "$key" ""
    done
}

chmod_env_file() {
    chmod 600 "$ENV_FILE" 2>/dev/null || warn "Could not chmod 600 $ENV_FILE on this filesystem."
}

write_new_env() {
    local token db_pass litellm_key langfuse_secret langfuse_salt
    token="$(random_secret "" 32)"
    db_pass="$(random_secret "" 24)"
    litellm_key="$(random_secret "sk-" 32)"
    langfuse_secret="$(random_secret "" 32)"
    langfuse_salt="$(random_secret "" 24)"

    cat > "$ENV_FILE" <<EOF
# Generated by install.sh. Do not commit this file.
# Regenerate with: rm .env && ./install.sh

# API access
MAISTRO_ACCESS_TOKEN=${token}
API_KEYS=["${token}"]
REQUIRE_AUTH=true
MAISTRO_BIND_HOST=${BIND_HOST}
MAISTRO_PORT=${PORT}

# Database
POSTGRES_PASSWORD=${db_pass}
DB_PASSWORD=${db_pass}
DATABASE_URL=postgresql://maistro:${db_pass}@postgres:5432/maistro

# LiteLLM gateway
LITELLM_MASTER_KEY=${litellm_key}
LITELLM_URL=http://litellm:4000
LITELLM_BASE_URL=http://litellm:4000
LITELLM_PROXY_URL=http://litellm:4000
LITELLM_API_BASE=http://litellm:4000/v1
LITELLM_API_KEY=${litellm_key}
LITELLM_PROXY_KEY=${litellm_key}

# Default model aliases. Change after adding at least one provider key below.
DEFAULT_MODEL=gemini/gemini-2.5-flash
CHAT_DEFAULT_MODEL=gemini/gemini-2.5-flash
MAISTRO_BUILDERS_MODEL=gemini/gemini-2.5-flash

# Langfuse
LANGFUSE_NEXTAUTH_SECRET=${langfuse_secret}
LANGFUSE_SALT=${langfuse_salt}
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=

# Provider API keys. Leave blank for providers you do not use.
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
CEREBRAS_API_KEY=
COHERE_API_KEY=
GROQ_API_KEY=
MISTRAL_API_KEY=
NVIDIA_API_KEY=
OPENROUTER_API_KEY=
SAMBANOVA_API_KEY=
XAI_API_KEY=
DEEPSEEK_API_KEY=
TOGETHER_API_KEY=
FIREWORKS_API_KEY=
DEEPINFRA_API_KEY=

# Evolve / benchmark defaults
BENCHMARK_FIDELITY=proxy
EOF

    chmod_env_file
    ok "Generated $ENV_FILE with local credentials."
}

repair_existing_env() {
    local token db_pass litellm_key

    warn "$ENV_FILE exists; preserving values and appending missing installer keys."

    token="$(env_get MAISTRO_ACCESS_TOKEN)"
    if [[ -z "$token" ]]; then
        token="$(random_secret "" 32)"
        append_env_once MAISTRO_ACCESS_TOKEN "$token"
    fi

    db_pass="$(env_get DB_PASSWORD)"
    if [[ -z "$db_pass" ]]; then
        db_pass="$(env_get POSTGRES_PASSWORD)"
    fi
    if [[ -z "$db_pass" ]]; then
        db_pass="$(random_secret "" 24)"
    fi

    litellm_key="$(env_get LITELLM_MASTER_KEY)"
    if [[ -z "$litellm_key" ]]; then
        litellm_key="$(random_secret "sk-" 32)"
    fi

    append_env_once API_KEYS "[\"${token}\"]"
    append_env_once REQUIRE_AUTH "true"
    append_env_once MAISTRO_BIND_HOST "$BIND_HOST"
    append_env_once MAISTRO_PORT "$PORT"
    append_env_once POSTGRES_PASSWORD "$db_pass"
    append_env_once DB_PASSWORD "$db_pass"
    append_env_once DATABASE_URL "postgresql://maistro:${db_pass}@postgres:5432/maistro"
    append_env_once LITELLM_MASTER_KEY "$litellm_key"
    append_env_once LITELLM_URL "http://litellm:4000"
    append_env_once LITELLM_BASE_URL "http://litellm:4000"
    append_env_once LITELLM_PROXY_URL "http://litellm:4000"
    append_env_once LITELLM_API_BASE "http://litellm:4000/v1"
    append_env_once LITELLM_API_KEY "$litellm_key"
    append_env_once LITELLM_PROXY_KEY "$litellm_key"
    append_env_once DEFAULT_MODEL "gemini/gemini-2.5-flash"
    append_env_once CHAT_DEFAULT_MODEL "gemini/gemini-2.5-flash"
    append_env_once MAISTRO_BUILDERS_MODEL "gemini/gemini-2.5-flash"
    append_env_once LANGFUSE_NEXTAUTH_SECRET "$(random_secret "" 32)"
    append_env_once LANGFUSE_SALT "$(random_secret "" 24)"
    append_env_once LANGFUSE_PUBLIC_KEY ""
    append_env_once LANGFUSE_SECRET_KEY ""
    append_env_once BENCHMARK_FIDELITY "proxy"
    append_provider_placeholders
    chmod_env_file
    ok "Repaired missing installer keys in $ENV_FILE."
}

sync_env_file() {
    ensure_python
    if [[ -f "$ENV_FILE" ]]; then
        repair_existing_env
    else
        write_new_env
    fi
}

ensure_compose_runtime() {
    if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
        COMPOSE_CMD=(docker compose)
        ok "Compose runtime: docker compose"
        return
    fi

    if command -v docker-compose >/dev/null 2>&1; then
        COMPOSE_CMD=(docker-compose)
        ok "Compose runtime: docker-compose"
        return
    fi

    if command -v podman >/dev/null 2>&1 && podman compose version >/dev/null 2>&1; then
        COMPOSE_CMD=(podman compose)
        ok "Compose runtime: podman compose"
        return
    fi

    if command -v podman-compose >/dev/null 2>&1; then
        COMPOSE_CMD=(podman-compose)
        ok "Compose runtime: podman-compose"
        return
    fi

    fail "No compose runtime found. Install Docker Desktop, Docker Engine with compose, or Podman, then retry."
}

run_feature_wizard() {
    if [[ "$SKIP_WIZARD" == "1" || "$SKIP_WIZARD" == "true" ]]; then
        warn "Skipping maistro-install questionnaire."
        return
    fi

    ensure_uv
    mkdir -p "$PLAN_DIR"

    local args=(run --project packages/maistro-bootstrap maistro-install --materialize-dir "$PLAN_DIR" --maistro-root "$PWD")
    if [[ -n "$ANSWERS_FILE" ]]; then
        args+=(--answers-file "$ANSWERS_FILE")
    fi

    info "Collecting feature, deployment, provider, observability, sandbox, and crypto choices..."
    if [[ -n "$ANSWERS_FILE" ]]; then
        "${UV_CMD[@]}" "${args[@]}"
    elif [[ -t 0 ]]; then
        "${UV_CMD[@]}" "${args[@]}"
    elif [[ -r /dev/tty ]]; then
        "${UV_CMD[@]}" "${args[@]}" < /dev/tty
    else
        fail "No interactive terminal available. Re-run with --answers-file or MAISTRO_SKIP_WIZARD=1."
    fi

    ok "Installer plan written to $PLAN_DIR."
}

http_ok() {
    local url="$1"
    if command -v curl >/dev/null 2>&1; then
        curl -sf "$url" >/dev/null 2>&1 && return 0
    fi
    "${PYTHON_CMD[@]}" - "$url" <<'PY' >/dev/null 2>&1
import sys
import urllib.request

try:
    with urllib.request.urlopen(sys.argv[1], timeout=4) as response:
        raise SystemExit(0 if response.status == 200 else 1)
except Exception:
    raise SystemExit(1)
PY
}

start_engine() {
    if [[ "$START_STACK" == "0" || "$START_STACK" == "false" ]]; then
        warn "Skipping compose start because --no-start or MAISTRO_START_STACK=0 was set."
        return
    fi

    ensure_compose_runtime
    info "Starting maistro-engine from source..."
    "${COMPOSE_CMD[@]}" -f "$COMPOSE_FILE" up -d --build

    info "Waiting for engine health..."
    local attempts=0
    until http_ok "http://${BIND_HOST}:${PORT}/health/live" || http_ok "http://${BIND_HOST}:${PORT}/health"; do
        attempts=$((attempts + 1))
        if [[ $attempts -gt 60 ]]; then
            fail "Engine did not become healthy. Check: ${COMPOSE_CMD[*]} -f $COMPOSE_FILE logs maistro-engine"
        fi
        sleep 2
    done
    ok "Engine healthy."
}

print_success() {
    local token
    token="$(env_get MAISTRO_ACCESS_TOKEN)"

    echo ""
    echo "maistro-engine is ready"
    echo "  URL:        http://${BIND_HOST}:${PORT}"
    echo "  Token:      ${token}"
    echo "  Install dir: $PWD"
    echo "  Plan dir:    $PLAN_DIR"
    echo ""
    echo "Commands:"
    echo "  Logs:  ${COMPOSE_CMD[*]:-docker compose} -f $COMPOSE_FILE logs -f maistro-engine"
    echo "  Stop:  ${COMPOSE_CMD[*]:-docker compose} -f $COMPOSE_FILE down"
    echo ""
    echo "Security note: services are bound to localhost by default. Do not set"
    echo "MAISTRO_BIND_HOST=0.0.0.0 until auth, network, and sandbox exposure have been reviewed."
    echo ""
}

main() {
    echo ""
    echo "maistro-engine installer"
    echo "security-first agent runtime"
    echo ""

    [[ -f "$COMPOSE_FILE" ]] || fail "Missing $COMPOSE_FILE. Run this from the maistro-engine repo root."
    run_feature_wizard
    sync_env_file
    start_engine
    print_success
}

main
