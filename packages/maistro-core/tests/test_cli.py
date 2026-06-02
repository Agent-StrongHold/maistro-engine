"""`maistro` shell CLI — a thin client of the HTTP API (UI parity, SPEC-184).

Covers the `maistro approvals list/approve/deny` subcommands: arg parsing and
request building against an httpx.MockTransport (no live server).
"""

from __future__ import annotations

import json

import httpx
import pytest

from maistro import cli


def _client(handler) -> httpx.Client:
    return httpx.Client(base_url="http://api:8101", transport=httpx.MockTransport(handler))


def test_parser_approvals_list() -> None:
    args = cli.build_parser().parse_args(["approvals", "list"])
    assert args.command == "approvals"
    assert args.action == "list"


def test_parser_approvals_approve_requires_id() -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["approvals", "approve"])


def test_approvals_list_returns_pending() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/capabilities/approvals"
        return httpx.Response(200, json={"pending": [{"request_id": "r1", "action": "restart_stack"}]})

    pending = cli.approvals_list(_client(handler))
    assert pending == [{"request_id": "r1", "action": "restart_stack"}]


def test_approvals_resolve_approve_posts_true() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"resolved": True, "approved": True})

    out = cli.approvals_resolve(_client(handler), "r1", approved=True)
    assert out["resolved"] is True
    assert seen["path"] == "/v1/capabilities/approvals/r1"
    assert seen["body"] == {"approved": True}


def test_approvals_resolve_deny_posts_false() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content) == {"approved": False}
        return httpx.Response(200, json={"resolved": True, "approved": False})

    out = cli.approvals_resolve(_client(handler), "r9", approved=False)
    assert out["approved"] is False


def test_main_approvals_list_prints(capsys) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"pending": [{"request_id": "r1", "action": "restart_stack",
                                                      "tier": "destructive", "requester": "infra_action"}]})

    rc = cli.main(["approvals", "list"], client=_client(handler))
    assert rc == 0
    out = capsys.readouterr().out
    assert "r1" in out
    assert "restart_stack" in out


def test_main_approve_prints_confirmation(capsys) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"resolved": True, "approved": True, "request_id": "r1"})

    rc = cli.main(["approvals", "approve", "r1"], client=_client(handler))
    assert rc == 0
    assert "r1" in capsys.readouterr().out


def test_main_no_command_returns_nonzero(capsys) -> None:
    rc = cli.main([])
    assert rc != 0
