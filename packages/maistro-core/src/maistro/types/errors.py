"""Error hierarchy.

Every domain-specific error carries a `code` for programmatic handling
and a `detail` for human consumption.
"""

from __future__ import annotations


class MaistroError(Exception):
    """Base error for all domain errors."""

    code: str = "MAISTRO_ERROR"

    def __init__(self, detail: str = "", *, code: str | None = None) -> None:
        self.detail = detail
        if code is not None:
            self.code = code
        super().__init__(f"[{self.code}] {detail}")


# ── Routing ──────────────────────────────────────────────────────


class RoutingError(MaistroError):
    """Model routing failure."""

    code = "ROUTING_ERROR"


class QuotaReserveError(RoutingError):
    """All eligible models are in quota reserve."""

    code = "QUOTA_RESERVE_BLOCKED"


class QuotaExhaustedError(RoutingError):
    """All providers are at or above 100% quota usage."""

    code = "QUOTA_EXHAUSTED"


class NoModelsError(RoutingError):
    """No active models available for the request."""

    code = "NO_MODELS_AVAILABLE"


# ── Classification ───────────────────────────────────────────────


class ClassificationError(MaistroError):
    """Intent classification failure."""

    code = "CLASSIFICATION_ERROR"


# ── Authentication & Authorization ───────────────────────────────


class AuthError(MaistroError):
    """Authentication or authorization failure."""

    code = "AUTH_ERROR"


class TokenExpiredError(AuthError):
    """JWT token has expired."""

    code = "TOKEN_EXPIRED"


class PermissionDeniedError(AuthError):
    """User lacks permission for the requested action."""

    code = "PERMISSION_DENIED"


# ── Tool Execution ───────────────────────────────────────────────


class ToolError(MaistroError):
    """Tool execution failure."""

    code = "TOOL_ERROR"


# ── Security ─────────────────────────────────────────────────────


class SecurityError(MaistroError):
    """Security violation detected."""

    code = "SECURITY_ERROR"


class InjectionError(SecurityError):
    """Prompt injection detected."""

    code = "INJECTION_DETECTED"


class TrustViolationError(SecurityError):
    """Trust tier violation."""

    code = "TRUST_VIOLATION"


# ── Configuration ────────────────────────────────────────────────


class ConfigError(MaistroError):
    """Configuration validation failure."""

    code = "CONFIG_ERROR"


# ── Skills ───────────────────────────────────────────────────────


class SkillError(MaistroError):
    """Skill loading, parsing, or forge failure."""

    code = "SKILL_ERROR"


# ── Backwards compat aliases ─────────────────────────────────────

StrongholdError = MaistroError
