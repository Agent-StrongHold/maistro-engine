"""`maistro` command-line interface — a thin client of the hive-conductor API.

Per the UI-parity principle, every operation lives in the HTTP API; this CLI
(like the web UI and any TUI) is just a client. Phase 1b ships the
`maistro approvals` subcommands so the built-in approval inbox is drivable from
a shell, not only the web GUI:

    maistro approvals list
    maistro approvals approve <request_id>
    maistro approvals deny <request_id>

Config via env: MAISTRO_API_URL (default http://127.0.0.1:8101),
MAISTRO_API_TOKEN (bearer session token).
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

import httpx

_DEFAULT_BASE = "http://127.0.0.1:8101"


def _default_client() -> httpx.Client:
    base = os.environ.get("MAISTRO_API_URL", _DEFAULT_BASE)
    token = os.environ.get("MAISTRO_API_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.Client(base_url=base, headers=headers, timeout=10.0)


def approvals_list(client: httpx.Client) -> list[dict[str, Any]]:
    resp = client.get("/v1/capabilities/approvals")
    resp.raise_for_status()
    pending: list[dict[str, Any]] = resp.json()["pending"]
    return pending


def approvals_resolve(client: httpx.Client, request_id: str, *, approved: bool) -> dict[str, Any]:
    resp = client.post(f"/v1/capabilities/approvals/{request_id}", json={"approved": approved})
    resp.raise_for_status()
    out: dict[str, Any] = resp.json()
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="maistro", description="mAIstro command-line interface")
    sub = parser.add_subparsers(dest="command")

    approvals = sub.add_parser("approvals", help="manage the HITL approval inbox")
    actions = approvals.add_subparsers(dest="action")
    actions.add_parser("list", help="list pending approval requests")
    approve = actions.add_parser("approve", help="approve a pending request")
    approve.add_argument("request_id")
    deny = actions.add_parser("deny", help="deny a pending request")
    deny.add_argument("request_id")

    return parser


def _cmd_approvals(args: argparse.Namespace, client: httpx.Client) -> int:
    if args.action == "list":
        pending = approvals_list(client)
        if not pending:
            print("No pending approvals.")
            return 0
        for req in pending:
            print(
                f"{req.get('request_id', '?')}  {req.get('action', '?')}  "
                f"[{req.get('tier', '?')}]  by {req.get('requester', '?')}"
            )
        return 0

    if args.action in {"approve", "deny"}:
        out = approvals_resolve(client, args.request_id, approved=args.action == "approve")
        verb = "approved" if out.get("approved") else "denied"
        print(f"Request {out.get('request_id', args.request_id)} {verb}.")
        return 0

    print("usage: maistro approvals {list|approve|deny}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None, *, client: httpx.Client | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help(sys.stderr)
        return 2

    owns_client = client is None
    client = client or _default_client()
    try:
        if args.command == "approvals":
            return _cmd_approvals(args, client)
        parser.print_help(sys.stderr)
        return 2
    except httpx.HTTPError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        if owns_client:
            client.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
