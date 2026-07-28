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
LEGACY_DIR="$HOME/.maistro"
DEFAULT_INSTALL_DIR="$HOME/.maistro/maistro-engine"
INSTALL_DIR="${MAISTRO_DIR:-$DEFAULT_INSTALL_DIR}"
REPO_URL="https://github.com/${REPO}.git"
ARCHIVE_URL="https://github.com/${REPO}/archive/refs/heads/${BRANCH}.tar.gz"
ARCHIVE_MARKER=".maistro-archive-install"

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
    if [[ -e "$INSTALL_DIR" && ! -e "$INSTALL_DIR/$ARCHIVE_MARKER" ]]; then
        fail "$INSTALL_DIR exists but was not created by this installer. Move it aside or set MAISTRO_DIR."
    fi
    command -v curl >/dev/null 2>&1 || fail "curl is required when git is unavailable."
    command -v tar >/dev/null 2>&1 || fail "tar is required when git is unavailable."

    if [[ -e "$INSTALL_DIR/$ARCHIVE_MARKER" ]]; then
        info "Updating existing maistro-engine archive checkout at $INSTALL_DIR..."
    else
        info "Downloading maistro-engine ${BRANCH} archive..."
    fi

    local tmp
    tmp="$(mktemp -d "${TMPDIR:-/tmp}/maistro.XXXXXX")"
    curl -fsSL "$ARCHIVE_URL" | tar -xz -C "$tmp" --strip-components=1
    if [[ -e "$INSTALL_DIR/$ARCHIVE_MARKER" ]]; then
        # Updating in place: drop the old tree (keep .env) before laying down the
        # fresh archive, so files removed/renamed upstream don't linger as stale.
        find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 ! -name '.env' -exec rm -rf {} +
    fi
    mkdir -p "$INSTALL_DIR"
    cp -R "$tmp"/. "$INSTALL_DIR"/
    rm -rf "$tmp"
    touch "$INSTALL_DIR/$ARCHIVE_MARKER"
    ok "Source archive is up to date."
}

migrate_legacy_install() {
    # The previous public installer wrote .env directly into ~/.maistro.
    # The new default is the nested ~/.maistro/maistro-engine checkout. If
    # we're on the default path and the old .env exists without a new one,
    # copy it over so existing users keep their tokens and provider keys.
    [[ "$INSTALL_DIR" == "$DEFAULT_INSTALL_DIR" ]] || return 0
    [[ -f "$LEGACY_DIR/.env" ]] || return 0
    [[ -f "$INSTALL_DIR/.env" ]] && return 0

    warn "Found legacy install at $LEGACY_DIR — migrating .env to $INSTALL_DIR."
    mkdir -p "$INSTALL_DIR"
    cp "$LEGACY_DIR/.env" "$INSTALL_DIR/.env"
    chmod 600 "$INSTALL_DIR/.env" 2>/dev/null || true
    ok "Migrated .env. Old copy left at $LEGACY_DIR/.env — remove it once verified."
}

bootstrap_source() {
    # Download FIRST — migrate_legacy_install would otherwise create $INSTALL_DIR
    # (with a copied .env), which trips the "exists but not a checkout" guard in
    # download_with_git and the missing-marker guard in download_with_archive,
    # blocking legacy users from installing/updating. Copy the .env afterward,
    # once the checkout exists.
    if command -v git >/dev/null 2>&1; then
        download_with_git
    else
        warn "git not found; falling back to source archive download."
        download_with_archive
    fi
    migrate_legacy_install
}

resolve_args_paths() {
    # Rewrite relative --answers-file paths to absolute while cwd is still
    # the caller's, before run_installer cd's into INSTALL_DIR.
    local args=() arg prev=""
    for arg in "$@"; do
        if [[ "$prev" == "--answers-file" && "$arg" != /* ]]; then
            arg="$(cd "$(dirname "$arg")" && pwd)/$(basename "$arg")"
        elif [[ "$arg" == --answers-file=* && "${arg#--answers-file=}" != /* ]]; then
            local rel="${arg#--answers-file=}"
            arg="--answers-file=$(cd "$(dirname "$rel")" && pwd)/$(basename "$rel")"
        fi
        args+=("$arg")
        prev="$arg"
    done
    printf '%s\0' "${args[@]}"
}

# Verify the downloaded install.sh against a published SHA256SUMS manifest
# before executing it (SPEC-072726-3439 Phase 5). Opt-in via
# MAISTRO_SHA256SUMS_URL until the production release URL is wired in as a
# default constant.
verify_installer_checksum() {
    [[ -n "${MAISTRO_SHA256SUMS_URL:-}" ]] || return 0
    command -v curl >/dev/null 2>&1 || fail "curl is required for checksum verification."

    local sha_cmd
    if command -v sha256sum >/dev/null 2>&1; then
        sha_cmd="sha256sum"
    elif command -v shasum >/dev/null 2>&1; then
        sha_cmd="shasum -a 256"
    else
        fail "sha256sum or shasum is required for checksum verification."
    fi

    info "Verifying install.sh against $MAISTRO_SHA256SUMS_URL ..."
    local sums expected actual
    sums="$(curl -fsSL "$MAISTRO_SHA256SUMS_URL")" || fail "Could not fetch checksum manifest."
    expected="$(printf '%s\n' "$sums" | awk '$NF == "install.sh" {print $1}' | head -1)"
    [[ -n "$expected" ]] || fail "Checksum manifest has no entry for install.sh."
    actual="$($sha_cmd "$INSTALL_DIR/install.sh" | awk '{print $1}')"
    if [[ "$actual" != "$expected" ]]; then
        fail "install.sh checksum mismatch (expected $expected, got $actual). Refusing to run it."
    fi
    ok "install.sh checksum verified."
}

run_installer() {
    local resolved=()
    if [[ $# -gt 0 ]]; then
        while IFS= read -r -d '' item; do
            resolved+=("$item")
        done < <(resolve_args_paths "$@")
        set -- "${resolved[@]}"
    fi

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
    verify_installer_checksum
    run_installer "$@"
}

main "$@"
