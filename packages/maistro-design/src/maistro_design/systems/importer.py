"""Importer for Open Design (nexu-io/open-design) design-systems content.

Bridges Open Design's `manifest.json` (schema `od-design-system-project/v1`) +
`DESIGN.md` + `tokens.css` + `design-tokens.json` into a `DesignSystem` instance,
behind a repeatable content security scan.

Two import paths:

- `load_bundled(registry)` — registers the small, install-time "Tier-1" set
  (`BUNDLED_SLUGS`) shipped in `systems/bundled/` at `TrustTier.T1`
  (verified/audited third-party).
- `import_from_catalog(slug, registry)` — one-click import of any system from the
  pre-scanned "Tier-2" catalog shipped in `systems/catalog/`, registered at
  `TrustTier.T2` (community/unaudited) after re-running the scan.

Both tiers are sourced from Open Design's Apache-2.0-licensed `design-systems/`
corpus; see `THIRD_PARTY_NOTICES.md` for provenance and licensing.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from maistro_design.trust import InMemoryTrustBanishList, TrustTier
from maistro_design.types import (
    ColorToken,
    DesignSystem,
    DesignSystemNotFoundError,
    SpacingToken,
    TrustBannedError,
)

if TYPE_CHECKING:
    from maistro_design.protocols import DesignSystemRegistry

_PACKAGE_ROOT = Path(__file__).resolve().parent
BUNDLED_ROOT = _PACKAGE_ROOT / "bundled"
CATALOG_ROOT = _PACKAGE_ROOT / "catalog"
CATALOG_INDEX = CATALOG_ROOT / "catalog.json"

# The four files that carry meaning for prompt-stack assembly and token export.
ESSENTIAL_FILES = ("manifest.json", "DESIGN.md", "tokens.css", "design-tokens.json")

# Install-time "Tier-1" set, registered automatically by load_bundled().
BUNDLED_SLUGS = ("default", "shadcn", "apple", "material", "editorial", "enterprise")


# ─── Scan ──────────────────────────────────────────────────────────────────

_SCRIPT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"<script\b", re.IGNORECASE),
    re.compile(r"<iframe\b", re.IGNORECASE),
    re.compile(r"<object\b", re.IGNORECASE),
    re.compile(r"<embed\b", re.IGNORECASE),
    re.compile(r"\beval\s*\(", re.IGNORECASE),
    re.compile(r"\bFunction\s*\(", re.IGNORECASE),
    re.compile(r"\bXMLHttpRequest\b"),
    re.compile(r"\bnew\s+WebSocket\s*\("),
    re.compile(r"\bfetch\s*\("),
    re.compile(r"javascript:", re.IGNORECASE),
)

_PROMPT_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore\s+(all\s+|any\s+)?(previous|prior|above)\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+|any\s+)?(previous|prior|above)", re.IGNORECASE),
    re.compile(r"\bjailbreak\b", re.IGNORECASE),
    re.compile(r"forget\s+(all\s+|your\s+)?(previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"\bdeveloper\s+mode\b", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(in\s+)?(DAN|jailbroken)", re.IGNORECASE),
    re.compile(r"reveal\s+(your\s+)?system\s+prompt", re.IGNORECASE),
)

_URL_RE = re.compile(r"https?://[^\s\"'<>)]+")
_BASE64_RE = re.compile(r"[A-Za-z0-9+/]{200,}={0,2}")

# Documentation/font-CDN links that are expected to appear in design-system prose.
DEFAULT_URL_ALLOWLIST: tuple[str, ...] = (
    "https://fonts.googleapis.com",
    "https://fonts.gstatic.com",
    "https://fonts.google.com",
    "https://developer.mozilla.org",
    "https://www.w3.org",
)


@dataclass(frozen=True)
class ScanReport:
    """Result of `scan_design_system_content`.

    `blocking_flags` covers script/eval injection, prompt-injection phrasing,
    base64 blobs, Unicode steganography, and banish-list hits — any of these
    means `passed=False`. `external_urls` is informational only (e.g. citation
    links in DESIGN.md prose) and never blocks import.
    """

    passed: bool
    blocking_flags: tuple[str, ...] = ()
    external_urls: tuple[str, ...] = ()


def _scan_blocking_patterns(
    filename: str, content: str, banish_list: InMemoryTrustBanishList | None
) -> list[str]:
    blocking: list[str] = []
    if banish_list is not None and banish_list.is_banned(content):
        blocking.append(f"{filename}: matches banish-list pattern")

    for pattern in _SCRIPT_PATTERNS:
        if pattern.search(content):
            blocking.append(f"{filename}: matched script pattern {pattern.pattern!r}")

    for pattern in _PROMPT_INJECTION_PATTERNS:
        if pattern.search(content):
            blocking.append(f"{filename}: matched prompt-injection pattern {pattern.pattern!r}")

    for match in _BASE64_RE.finditer(content):
        blocking.append(f"{filename}: base64 blob ({len(match.group(0))} chars)")

    for offset, ch in enumerate(content):
        category = unicodedata.category(ch)
        if category in ("Cf", "Co") or (category == "Cc" and ch not in "\t\n\r"):
            blocking.append(
                f"{filename}: suspicious Unicode {category} U+{ord(ch):04X} at offset {offset}"
            )
            break

    return blocking


def _find_external_urls(content: str, url_allowlist: tuple[str, ...]) -> set[str]:
    found: set[str] = set()
    for url in _URL_RE.findall(content):
        url = url.rstrip("`).,;\"'")
        if not any(url.startswith(prefix) for prefix in url_allowlist):
            found.add(url)
    return found


def scan_design_system_content(
    files: dict[str, str],
    *,
    banish_list: InMemoryTrustBanishList | None = None,
    url_allowlist: tuple[str, ...] = DEFAULT_URL_ALLOWLIST,
) -> ScanReport:
    """Scan a design system's source files for injection and exfiltration risks.

    `files` maps filenames (e.g. "DESIGN.md") to their text content. Returns a
    `ScanReport`; `passed=False` means the content must not be imported without
    admin review.
    """
    blocking: list[str] = []
    external_urls: set[str] = set()

    for filename, content in files.items():
        blocking.extend(_scan_blocking_patterns(filename, content, banish_list))
        external_urls.update(_find_external_urls(content, url_allowlist))

    return ScanReport(
        passed=not blocking,
        blocking_flags=tuple(blocking),
        external_urls=tuple(sorted(external_urls)),
    )


# ─── manifest.json + DESIGN.md + tokens.css + design-tokens.json → DesignSystem ──


def import_open_design_system(
    manifest: dict[str, Any],
    *,
    design_md: str = "",
    tokens_css: str = "",
    design_tokens: dict[str, Any] | None = None,
    trust_tier: TrustTier = TrustTier.T2,
) -> DesignSystem:
    """Build a `DesignSystem` from Open Design's bundled-package shape.

    `manifest` is the parsed `manifest.json` (schema `od-design-system-project/v1`,
    keyed by `id` rather than `slug`, with nested `files`/`craft`/`preview`/
    `sourceFiles`). `design_tokens` is the parsed `design-tokens.json`
    (`od-design-tokens/v1`); its flat `tokens` array is used to populate
    `colors` (type == "color") and `spacing` (dimension tokens named `--space-*`).
    """
    colors: list[ColorToken] = []
    spacing: list[SpacingToken] = []
    for token in (design_tokens or {}).get("tokens", []):
        name = token.get("name", "")
        value = token.get("value", "")
        token_type = token.get("type")
        if token_type == "color":
            colors.append(ColorToken(name=name, value=value, group="open-design"))
        elif token_type == "dimension" and name.startswith("--space-"):
            spacing.append(SpacingToken(name=name, value=value))

    slug = manifest.get("id") or manifest.get("slug") or "unknown"
    metadata = {
        "category": manifest.get("category", ""),
        "source": manifest.get("source", {}),
        "open_design_id": slug,
        "license": "Apache-2.0",
    }

    return DesignSystem(
        slug=slug,
        name=manifest.get("name", slug),
        description=manifest.get("description", ""),
        colors=colors,
        spacing=spacing,
        tokens_css=tokens_css,
        design_md=design_md,
        metadata=metadata,
        trust_tier=trust_tier,
    )


# ─── Loading from disk ────────────────────────────────────────────────────────


def _read_system_files(
    system_dir: Path,
) -> tuple[dict[str, Any], dict[str, str], dict[str, Any] | None]:
    manifest = json.loads((system_dir / "manifest.json").read_text(encoding="utf-8"))
    design_md = (system_dir / "DESIGN.md").read_text(encoding="utf-8")
    tokens_css = (system_dir / "tokens.css").read_text(encoding="utf-8")
    design_tokens_path = system_dir / "design-tokens.json"
    design_tokens = (
        json.loads(design_tokens_path.read_text(encoding="utf-8"))
        if design_tokens_path.exists()
        else None
    )
    files = {
        "manifest.json": json.dumps(manifest),
        "DESIGN.md": design_md,
        "tokens.css": tokens_css,
    }
    if design_tokens is not None:
        files["design-tokens.json"] = json.dumps(design_tokens)
    return manifest, files, design_tokens


def load_bundled(registry: DesignSystemRegistry) -> None:
    """Register the Tier-1 install-time design systems (`BUNDLED_SLUGS`) at T1."""
    for slug in BUNDLED_SLUGS:
        system_dir = BUNDLED_ROOT / slug
        manifest, files, design_tokens = _read_system_files(system_dir)
        system = import_open_design_system(
            manifest,
            design_md=files["DESIGN.md"],
            tokens_css=files["tokens.css"],
            design_tokens=design_tokens,
            trust_tier=TrustTier.T1,
        )
        registry.register(system)


def load_catalog() -> list[dict[str, Any]]:
    """Return the full Tier-2 catalog index (`catalog.json`)."""
    return json.loads(CATALOG_INDEX.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def import_from_catalog(
    slug: str,
    registry: DesignSystemRegistry,
    *,
    trust_tier: TrustTier = TrustTier.T2,
    banish_list: InMemoryTrustBanishList | None = None,
) -> DesignSystem:
    """One-click import of a pre-scanned Tier-2 design system into `registry`.

    Re-runs `scan_design_system_content` at import time (defense-in-depth — the
    catalog's `scan_status` reflects the scan at vendoring time, not now) and
    raises `TrustBannedError` if it no longer passes.
    """
    system_dir = CATALOG_ROOT / slug
    if not system_dir.is_dir():
        msg = f"Design system '{slug}' not found in the Open Design catalog"
        raise DesignSystemNotFoundError(msg)

    manifest, files, design_tokens = _read_system_files(system_dir)
    report = scan_design_system_content(files, banish_list=banish_list)
    if not report.passed:
        msg = f"Design system '{slug}' failed the import scan: {report.blocking_flags}"
        raise TrustBannedError(msg)

    system = import_open_design_system(
        manifest,
        design_md=files["DESIGN.md"],
        tokens_css=files["tokens.css"],
        design_tokens=design_tokens,
        trust_tier=trust_tier,
    )
    registry.register(system)
    return system
