#!/usr/bin/env bash
set -euo pipefail

# Public bootstrapper.
#
# Usage:
#   curl -fsSL https://get.hiveconductor.dev | bash
#   curl -fsSL https://raw.githubusercontent.com/BlakeMatthews-dev/maistro-engine/main/get.sh | bash
#
# This script needs bash and is the entrypoint for macOS, Linux, and WSL2.
# On native Windows (no bash), use get.ps1 instead — from PowerShell:
#   irm https://raw.githubusercontent.com/BlakeMatthews-dev/maistro-engine/main/get.ps1 | iex
# get.ps1 sets up WSL2 + Ubuntu, then runs this same script inside it.
#
# This script installs/updates the maistro-engine source tree, then delegates to
# ./install.sh so the same interactive feature/deployment flow is used everywhere.

REPO="${MAISTRO_REPO:-BlakeMatthews-dev/maistro-engine}"
BRANCH="${MAISTRO_BRANCH:-main}"
INSTALL_DIR="${MAISTRO_DIR:-$HOME/.maistro/maistro-engine}"
REPO_URL="https://github.com/${REPO}.git"
ARCHIVE_URL="https://github.com/${REPO}/archive/refs/heads/${BRANCH}.tar.gz"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${BLUE}[maistro]${NC} $*"; }
ok() { echo -e "${GREEN}[ok]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }
fail() { echo -e "${RED}[error]${NC} $*" >&2; exit 1; }

download_with_git() {
    if [[ -d "$INSTALL_DIR/.git" ]]; then
        info "Updating existing maistro-engine checkout at $INSTALL_DIR..."
        git -C "$INSTALL_DIR" fetch --depth 1 origin "$BRANCH"
        git -C "$INSTALL_DIR" checkout -B "$BRANCH" "origin/$BRANCH"
        ok "Updated source checkout."
        return
    fi

    if [[ -e "$INSTALL_DIR" ]]; then
        fail "$INSTALL_DIR exists but is not a git checkout. Move it aside or set MAISTRO_DIR."
    fi

    info "Cloning maistro-engine ${BRANCH} into $INSTALL_DIR..."
    git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
    ok "Cloned source checkout."
}

download_with_archive() {
    if [[ -e "$INSTALL_DIR" ]]; then
        fail "$INSTALL_DIR exists and git is unavailable. Move it aside or set MAISTRO_DIR."
    fi
    command -v curl >/dev/null 2>&1 || fail "curl is required when git is unavailable."
    command -v tar >/dev/null 2>&1 || fail "tar is required when git is unavailable."

    local tmp
    tmp="$(mktemp -d "${TMPDIR:-/tmp}/maistro.XXXXXX")"
    info "Downloading maistro-engine ${BRANCH} archive..."
    mkdir -p "$INSTALL_DIR"
    curl -fsSL "$ARCHIVE_URL" | tar -xz -C "$tmp" --strip-components=1
    cp -R "$tmp"/. "$INSTALL_DIR"/
    rm -rf "$tmp"
    ok "Downloaded source archive."
}

bootstrap_source() {
    if command -v git >/dev/null 2>&1; then
        download_with_git
    else
        warn "git not found; falling back to source archive download."
        download_with_archive
    fi
}

run_installer() {
    cd "$INSTALL_DIR"
    chmod +x ./install.sh 2>/dev/null || true

    if [[ -t 0 ]]; then
        exec bash ./install.sh "$@"
    fi

    if [[ -r /dev/tty ]]; then
        exec bash ./install.sh "$@" < /dev/tty
    fi

    exec bash ./install.sh "$@"
}

main() {
    echo ""
    echo "maistro-engine public installer"
    echo "repo:   ${REPO}"
    echo "branch: ${BRANCH}"
    echo "dir:    ${INSTALL_DIR}"
    echo ""

    bootstrap_source
    run_installer "$@"
}

main "$@"
