#!/usr/bin/env bash
set -euo pipefail

# ─── maistro-engine remote installer ──────────────────────────────────────
# Usage: curl -fsSL https://get.hiveconductor.dev | bash
#    or: curl -fsSL https://raw.githubusercontent.com/BlakeMatthews-dev/maistro-engine/develop/get.sh | bash
#
# What it does:
# 1. Installs Podman (rootless) if no container runtime found
# 2. Downloads the latest release (compose + config, no full repo)
# 3. Generates unique access token + DB password
# 4. Starts the engine bound to localhost only
# 5. Prints URL + token
#
# No git required. No Docker required. No root required (Podman is rootless).
# ───────────────────────────────────────────────────────────────────────────

VERSION="${MAISTRO_VERSION:-latest}"
INSTALL_DIR="${MAISTRO_DIR:-$HOME/.maistro}"
REPO="BlakeMatthews-dev/maistro-engine"
BRANCH="develop"
RAW="https://raw.githubusercontent.com/${REPO}/${BRANCH}"
PORT="${MAISTRO_PORT:-8000}"
BIND="${MAISTRO_BIND_HOST:-127.0.0.1}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()  { echo -e "${BLUE}[maistro]${NC} $*"; }
ok()    { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
fail()  { echo -e "${RED}[✗]${NC} $*"; exit 1; }

# ─── Detect + install container runtime ───────────────────────────────────
ensure_runtime() {
    if command -v podman &>/dev/null; then
        RUNTIME="podman"; ok "Podman found"
    elif command -v docker &>/dev/null; then
        RUNTIME="docker"; ok "Docker found"
    else
        info "Installing Podman (rootless, no daemon)..."
        if [[ "$OSTYPE" == "darwin"* ]]; then
            command -v brew &>/dev/null || fail "Install Homebrew first: https://brew.sh"
            brew install podman >/dev/null 2>&1
            podman machine init --now 2>/dev/null || true
        elif command -v apt-get &>/dev/null; then
            sudo apt-get update -qq && sudo apt-get install -y -qq podman >/dev/null 2>&1
        elif command -v dnf &>/dev/null; then
            sudo dnf install -y -q podman >/dev/null 2>&1
        elif command -v pacman &>/dev/null; then
            sudo pacman -Sy --noconfirm podman >/dev/null 2>&1
        else
            fail "Auto-install failed. Install Podman manually: https://podman.io/docs/installation"
        fi
        RUNTIME="podman"; ok "Podman installed"
    fi

    if $RUNTIME compose version &>/dev/null 2>&1; then
        COMPOSE="$RUNTIME compose"
    elif command -v podman-compose &>/dev/null; then
        COMPOSE="podman-compose"
    elif command -v docker-compose &>/dev/null; then
        COMPOSE="docker-compose"
    else
        pip3 install --quiet podman-compose 2>/dev/null || pip install --quiet podman-compose
        COMPOSE="podman-compose"
    fi
    ok "Compose: $COMPOSE"
}

# ─── Download minimal deploy bundle ──────────────────────────────────────
download_bundle() {
    mkdir -p "$INSTALL_DIR"
    cd "$INSTALL_DIR"

    info "Downloading maistro-engine ($VERSION)..."
    local files=(
        "docker-compose.yml"
        "Dockerfile"
        "init-db.sql"
        "litellm_config.yaml"
    )
    for f in "${files[@]}"; do
        curl -fsSL "${RAW}/${f}" -o "$f" 2>/dev/null || warn "Optional file missing: $f"
    done
    ok "Downloaded to $INSTALL_DIR"
}

# ─── Generate secure .env ────────────────────────────────────────────────
generate_env() {
    cd "$INSTALL_DIR"
    if [[ -f .env ]]; then
        warn ".env exists — preserving (delete to regenerate)"
        return
    fi

    local token db_pass litellm_key
    token=$(python3 -c "import secrets;print(secrets.token_urlsafe(32))" 2>/dev/null || openssl rand -base64 32 | tr -d '/+=' | head -c 43)
    db_pass=$(python3 -c "import secrets;print(secrets.token_urlsafe(16))" 2>/dev/null || openssl rand -base64 16 | tr -d '/+=' | head -c 22)
    litellm_key=$(python3 -c "import secrets;print('sk-' + secrets.token_urlsafe(24))" 2>/dev/null || echo "sk-$(openssl rand -base64 24 | tr -d '/+=')")

    cat > .env <<EOF
# maistro-engine — generated $(date -Iseconds)
# Regenerate: rm .env && curl -fsSL https://get.hiveconductor.dev | bash

MAISTRO_ACCESS_TOKEN=${token}
MAISTRO_BIND_HOST=${BIND}
MAISTRO_PORT=${PORT}

POSTGRES_PASSWORD=${db_pass}
DB_PASSWORD=${db_pass}
DATABASE_URL=postgresql://maistro:${db_pass}@postgres:5432/maistro

LITELLM_MASTER_KEY=${litellm_key}

# Configure your LLM provider(s):
# ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY=sk-...
# GEMINI_API_KEY=...

CHAT_DEFAULT_MODEL=anthropic/claude-sonnet-4-20250514
BENCHMARK_FIDELITY=proxy
EOF
    chmod 600 .env
    ok "Generated .env with unique credentials"
}

# ─── Start ────────────────────────────────────────────────────────────────
start() {
    cd "$INSTALL_DIR"
    info "Starting maistro-engine..."
    $COMPOSE up -d 2>&1 | tail -3

    info "Waiting for health..."
    local i=0
    while ! curl -sf "http://${BIND}:${PORT}/health" >/dev/null 2>&1; do
        i=$((i+1))
        [[ $i -gt 30 ]] && fail "Timeout. Check: cd $INSTALL_DIR && $COMPOSE logs"
        sleep 2
    done
    ok "Engine healthy"
}

# ─── Print success ────────────────────────────────────────────────────────
print_success() {
    cd "$INSTALL_DIR"
    local token
    token=$(grep MAISTRO_ACCESS_TOKEN .env | cut -d= -f2)

    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}  maistro-engine is running${NC}"
    echo ""
    echo -e "  URL:    ${BLUE}http://${BIND}:${PORT}${NC}"
    echo -e "  Token:  ${YELLOW}${token}${NC}"
    echo -e "  Dir:    ${INSTALL_DIR}"
    echo ""
    echo -e "  ${YELLOW}⚠  Localhost only. To expose externally:${NC}"
    echo -e "     edit ${INSTALL_DIR}/.env → MAISTRO_BIND_HOST=0.0.0.0"
    echo ""
    echo -e "  Logs:   cd $INSTALL_DIR && $COMPOSE logs -f"
    echo -e "  Stop:   cd $INSTALL_DIR && $COMPOSE down"
    echo -e "  Update: curl -fsSL https://get.hiveconductor.dev | bash"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

# ─── Main ─────────────────────────────────────────────────────────────────
main() {
    echo ""
    echo -e "${BLUE}  maistro-engine installer${NC}"
    echo -e "${BLUE}  Security-first agent runtime${NC}"
    echo ""
    ensure_runtime
    download_bundle
    generate_env
    start
    print_success
}

main "$@"
