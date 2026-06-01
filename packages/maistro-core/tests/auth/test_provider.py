"""Tests for maistro.auth.provider — ServiceKeyAuthProvider."""

from __future__ import annotations

from maistro.auth._types import Scope
from maistro.auth.provider import ServiceKeyAuthProvider
from maistro.auth.registry import ServiceKeyRegistry


def _make_provider() -> ServiceKeyAuthProvider:
    registry = ServiceKeyRegistry()
    registry.load_dict(
        {
            "conductor-router": {
                "key": "sk-svc-conductor-test-key",
                "scopes": ["llm:*", "events:*"],
            },
        }
    )
    return ServiceKeyAuthProvider(registry)


class TestServiceKeyAuthProvider:
    def test_valid_x_service_key(self) -> None:
        provider = _make_provider()
        identity = provider.authenticate({"x-service-key": "sk-svc-conductor-test-key"})
        assert identity is not None
        assert identity.name == "conductor-router"

    def test_valid_bearer_with_svc_prefix(self) -> None:
        provider = _make_provider()
        identity = provider.authenticate({"authorization": "Bearer sk-svc-conductor-test-key"})
        assert identity is not None
        assert identity.name == "conductor-router"

    def test_bearer_without_svc_prefix_ignored(self) -> None:
        provider = _make_provider()
        identity = provider.authenticate({"authorization": "Bearer sk-user-regular-token"})
        assert identity is None

    def test_no_headers(self) -> None:
        provider = _make_provider()
        identity = provider.authenticate({})
        assert identity is None

    def test_invalid_key(self) -> None:
        provider = _make_provider()
        identity = provider.authenticate({"x-service-key": "sk-svc-wrong"})
        assert identity is None

    def test_empty_x_service_key(self) -> None:
        provider = _make_provider()
        identity = provider.authenticate({"x-service-key": ""})
        assert identity is None

    def test_scopes_present(self) -> None:
        provider = _make_provider()
        identity = provider.authenticate({"x-service-key": "sk-svc-conductor-test-key"})
        assert identity is not None
        assert Scope.CHAT_COMPLETIONS in identity.scopes
        assert Scope.EVENTS_EMIT in identity.scopes

    def test_x_service_key_takes_priority(self) -> None:
        provider = _make_provider()
        identity = provider.authenticate(
            {
                "x-service-key": "sk-svc-conductor-test-key",
                "authorization": "Bearer sk-svc-something-else",
            }
        )
        assert identity is not None
        assert identity.name == "conductor-router"
