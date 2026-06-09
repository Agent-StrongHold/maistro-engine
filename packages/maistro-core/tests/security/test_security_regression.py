"""Failure-mode regression tests for security fixes #1, #5, #7, #11, #13, #15.

These test the FAILURE paths — the configurations that were untested before
and where all 15 holes lived. Each test asserts that the dangerous path
is now closed, not that the happy path works.
"""

import asyncio
import pytest


# ─── #1: Fail-closed executor refuses when no sandbox available ───────────────

class TestFailClosedExecutor:
    """The executor MUST refuse when no isolation backend is installed."""

    def test_no_backend_refuses_execution(self):
        """With all backends unavailable, execute_node returns fail-closed."""
        from services.hyperlight_executor import SandboxExecutor

        executor = SandboxExecutor()
        # Force no backend
        executor._backend = None

        result = asyncio.run(executor.execute_node("print('hi')"))
        assert result["success"] is False
        assert result["isolation"] == "fail-closed"
        assert "REFUSED" in result["error"]

    def test_no_backend_available_property_false(self):
        from services.hyperlight_executor import SandboxExecutor

        executor = SandboxExecutor()
        executor._backend = None
        assert executor.available is False


# ─── #5: Default-deny node classification ─────────────────────────────────────

class TestDefaultDenyNodeClassification:
    """Unconfigured nodes MUST NOT get the trusted 'async' tier."""

    def test_unconfigured_node_gets_sandbox(self):
        from services.graph_runner import _classify_node_execution

        node = {"config": {}}  # No tier, no capabilities
        result = _classify_node_execution(node, "test-node")
        assert result == "sandbox"

    def test_untrusted_without_approval_is_blocked(self):
        from services.graph_runner import _classify_node_execution

        node = {"config": {"untrusted": True}}  # No tier_approved_by
        result = _classify_node_execution(node, "test-node")
        assert result == "blocked"

    def test_untrusted_with_approval_gets_sandbox(self):
        from services.graph_runner import _classify_node_execution

        node = {"config": {"untrusted": True, "tier_approved_by": "admin"}}
        result = _classify_node_execution(node, "test-node")
        assert result == "sandbox"

    def test_explicitly_safe_gets_async(self):
        from services.graph_runner import _classify_node_execution

        node = {"config": {"execution_tier": "safe"}}
        result = _classify_node_execution(node, "test-node")
        assert result == "async"


# ─── #11: Static key no longer returns user identity from headers ─────────────

class TestNoOpenWebUIImpersonation:
    """Static key auth MUST NOT accept identity from X-OpenWebUI headers."""

    def test_static_key_ignores_openwebui_headers(self):
        from maistro.security.auth_static import StaticKeyAuthProvider

        provider = StaticKeyAuthProvider(api_key="test-key-123")
        result = asyncio.run(provider.authenticate(
            authorization="Bearer test-key-123",
            headers={
                "x-openwebui-user-email": "attacker@evil.com",
                "x-openwebui-user-id": "attacker-id",
                "x-openwebui-user-name": "Attacker",
            },
        ))
        # Must return system identity, NOT the attacker's headers
        assert result.user_id == "system"
        assert result.auth_method == "api_key"
        assert "attacker" not in result.user_id
        assert "attacker" not in result.username


# ─── #13: Composite provider aborts on auth failure, not falls through ────────

class TestCompositeFailClosed:
    """JWT signature failure MUST abort the chain, not fall through to static key."""

    def test_jwt_failure_does_not_fall_through(self):
        from maistro.security.auth_composite import AuthError, CompositeAuthProvider

        class FakeJWTProvider:
            async def authenticate(self, authorization, headers=None):
                raise AuthError("JWT signature invalid")

        class FakeStaticKeyProvider:
            async def authenticate(self, authorization, headers=None):
                from maistro.security._types import SYSTEM_AUTH
                return SYSTEM_AUTH

        composite = CompositeAuthProvider([FakeJWTProvider(), FakeStaticKeyProvider()])

        with pytest.raises(AuthError, match="signature invalid"):
            asyncio.run(composite.authenticate("Bearer fake-jwt-token"))

    def test_infra_failure_does_not_fall_through(self):
        from maistro.security.auth_composite import AuthError, CompositeAuthProvider

        class BrokenProvider:
            async def authenticate(self, authorization, headers=None):
                raise ConnectionError("JWKS endpoint unreachable")

        class FakeStaticKeyProvider:
            async def authenticate(self, authorization, headers=None):
                from maistro.security._types import SYSTEM_AUTH
                return SYSTEM_AUTH

        composite = CompositeAuthProvider([BrokenProvider(), FakeStaticKeyProvider()])

        with pytest.raises(AuthError, match="infrastructure failure"):
            asyncio.run(composite.authenticate("Bearer some-token"))


# ─── #15: Test seam blocked in production config ──────────────────────────────

class TestJWTTestSeamBlocked:
    """jwt_decode override MUST raise when jwks_url is configured."""

    def test_test_seam_raises_with_jwks_url(self):
        from maistro.security.auth_jwt import JWTAuthProvider

        provider = JWTAuthProvider(
            jwks_url="https://idp.example.com/.well-known/jwks.json",
            issuer="https://idp.example.com",
            jwt_decode=lambda t: {"sub": "attacker", "preferred_username": "hacked"},
        )

        with pytest.raises(RuntimeError, match="SECURITY.*forbidden"):
            asyncio.run(provider.authenticate("Bearer fake-token"))

    def test_test_seam_works_without_jwks_url(self):
        from maistro.security.auth_jwt import JWTAuthProvider

        provider = JWTAuthProvider(
            jwks_url="",
            issuer="test",
            jwt_decode=lambda t: {"sub": "test-user", "preferred_username": "tester"},
        )

        result = asyncio.run(provider.authenticate("Bearer fake-token"))
        assert result.user_id == "test-user"
