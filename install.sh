#!/usr/bin/env bash
# maistro installer — https://get.maistro.ai
#
# Usage:
#   curl -fsSL https://get.maistro.ai | sh
#   curl -fsSL https://get.maistro.ai | sh -s -- --yes
#
# What it does:
#   1. Checks for Python 3.12+, git, Docker/Podman
#   2. Installs uv if not present
#   3. Clones maistro-engine (or uses existing checkout)
#   4. Syncs dependencies
#   5. Adds `maistro` to PATH
#   6. Builds the builders dev container image
#   7. Runs `maistro` to verify
#
set -euo pipefail

REPO="${MAISTRO_REPO_URL:-https://github.com/BlakeMatthews-dev/maistro-engine.git}"
INSTALL_DIR="${MAISTRO_HOME:-$HOME/.maistro}"
BRANCH="${MAISTRO_BRANCH:-main}"
YES=false
SKIP_DOCKER=false

# ── Colors ──────────────────────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
RESET='\033[0m'

info()  { printf "${CYAN}maistro:${RESET} %s\n" "$*"; }
ok()    { printf "${GREEN}✓${RESET} %s\n" "$*"; }
warn()  { printf "${YELLOW}!${RESET} %s\n" "$*"; }
err()   { printf "${RED}✗${RESET} %s\n" "$*" >&2; }

# ── Args ────────────────────────────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
  case "$1" in
    -y|--yes) YES=true; shift ;;
    --skip-docker) SKIP_DOCKER=true; shift ;;
    --dir) INSTALL_DIR="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: curl -fsSL https://get.maistro.ai | sh -s -- [opts]"
      echo ""
      echo "Options:"
      echo "  -y, --yes          Accept all defaults"
      echo "  --dir DIR          Install directory (default: ~/.maistro)"
      echo "  --branch BRANCH    Git branch (default: main)"
      echo "  --skip-docker      Skip Docker checks and image build"
      exit 0 ;;
    *) err "Unknown option: $1"; exit 1 ;;
  esac
done

# ── Step 1: Check prerequisites ─────────────────────────────────────────────

info "Checking prerequisites..."

check_cmd() {
  if command -v "$1" &>/dev/null; then
    ok "$1 found"
    return 0
  else
    return 1
  fi
}

# Python 3.12+
if check_cmd python3; then
  PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
  PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
  PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
  if [[ "$PY_MAJOR" -lt 3 ]] || [[ "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 12 ]]; then
    err "Python 3.12+ required, found $PY_VERSION"
    exit 1
  fi
  ok "Python $PY_VERSION"
else
  err "Python 3.12+ not found. Install it: https://python.org/downloads"
  exit 1
fi

# git
if ! check_cmd git; then
  err "git not found. Install it first."
  exit 1
fi

# Docker or Podman
if [[ "$SKIP_DOCKER" == "false" ]]; then
  if check_cmd docker; then
    if docker info &>/dev/null; then
      ok "D daemon running"
    else
      warn "Docker installed but daemon not running. Start it first."
    fi
  elif check_cmd podman; then
    ok "podman found (will use Podman)"
  else
    warn "Neither Docker nor Podman found."
    warn "Install Docker: https://docs.docker.com/get-docker/"
    warn "maistro builders requires a container runtime for isolated sessions."
    if [[ "$YES" == "false" ]]; then
      read -rp "Continue without container runtime? [y/N] " REPLY
      [[ "$REPLY" != "y" && "$REPLY" != "Y" ]] && exit 1
    fi
  fi
fi

# ── Step 2: Install uv ──────────────────────────────────────────────────────

if check_cmd uv; then
  ok "uv $(uv --version 2>/dev/null | head -1)"
else
  info "Installing uv (Python package manager)..."
  curl -fsSL https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  ok "uv installed"
fi

# ── Step 3: Clone or use local checkout ──────────────────────────────────────

# If running from inside the repo (detected via pyproject.toml with maistro-workspace),
# use this directory directly.
if [[ -z "${MAISTRO_HOME:-}" ]]; then
  SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
  if [[ -f "$SELF_DIR/pyproject.toml" ]] && grep -q "maistro-workspace" "$SELF_DIR/pyproject.toml" 2>/dev/null; then
    INSTALL_DIR="$SELF_DIR"
    info "Using local checkout at $INSTALL_DIR"
  elif [[ -d "$HOME/.maistro" && -d "$HOME/.maistro/.git" ]]; then
    INSTALL_DIR="$HOME/.maistro"
  else
    INSTALL_DIR="$HOME/.maistro"
  fi
fi

if [[ -d "$INSTALL_DIR" && -d "$INSTALL_DIR/.git" ]]; then
  info "Updating existing installation at $INSTALL_DIR..."
  git -C "$INSTALL_DIR" pull --ff-only 2>/dev/null || {
    warn "Could not fast-forward. Trying rebase..."
    git -C "$INSTALL_DIR" pull --rebase --autostash 2>/dev/null || {
      warn "Could not update. Using existing checkout."
    }
  }
else
  info "Cloning maistro-engine to $INSTALL_DIR..."
  git clone --depth 1 --branch "$BRANCH" "$REPO" "$INSTALL_DIR"
  ok "Cloned"
fi

# ── Step 4: Install dependencies ────────────────────────────────────────────

info "Installing dependencies..."
cd "$INSTALL_DIR"
uv sync --all-extras
ok "Dependencies installed"

# ── Step 5: Add to PATH ─────────────────────────────────────────────────────

SHELL_RC=""
if [[ -n "${ZSH_VERSION:-}" ]]; then
  SHELL_RC="$HOME/.zshrc"
elif [[ -n "${BASH_VERSION:-}" ]]; then
  SHELL_RC="$HOME/.bashrc"
fi

MAISTRO_BIN="$INSTALL_DIR/.venv/bin"

if [[ -n "$SHELL_RC" ]]; then
  if ! grep -q "maistro" "$SHELL_RC" 2>/dev/null; then
    echo "" >> "$SHELL_RC"
    echo "# maistro CLI" >> "$SHELL_RC"
    echo "export PATH=\"$MAISTRO_BIN:\$PATH\"" >> "$SHELL_RC"
    ok "Added to $SHELL_RC"
  else
    ok "Already in $SHELL_RC"
  fi
fi

export PATH="$MAISTRO_BIN:$PATH"

# ── Step 6: Build dev container image ───────────────────────────────────────

if [[ "$SKIP_DOCKER" == "false" ]]; then
  if command -v docker &>/dev/null && docker info &>/dev/null; then
    info "Building builders dev container image..."
    docker build -f "$INSTALL_DIR/Dockerfile.builders" -t maistro-builders:latest "$INSTALL_DIR" 2>/dev/null && {
      ok "Dev container image built"
    } || {
      warn "Image build failed. Run manually: docker build -f Dockerfile.builders -t maistro-builders:latest ."
    }
  fi
fi

# ── Step 7: Verify ──────────────────────────────────────────────────────────

info "Verifying..."
if command -v maistro &>/dev/null; then
  MAISTRO_VER=$(maistro --help 2>&1 | head -1 || echo "ok")
  ok "maistro CLI ready"
else
  "$MAISTRO_BIN/maistro" --help &>/dev/null && ok "maistro CLI ready"
fi

# ── Done ────────────────────────────────────────────────────────────────────

echo ""
printf "${BOLD}${CYAN}  maistro is ready.${RESET}\n"
echo ""
echo "  Next steps:"
echo ""
echo "    source $SHELL_RC    # reload your shell"
echo "    maistro builders    # start coding"
echo ""
if [[ "$SKIP_DOCKER" == "false" ]]; then
  echo "  For LLM access, you'll also need a LiteLLM proxy running."
  echo "  See: https://docs.litellm.ai/docs/proxy/quick_start"
  echo ""
fi
