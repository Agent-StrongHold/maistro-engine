"""Sentinel policy enforcement: pre-call and post-call security pipeline.

Pre-call: validate + repair args, check permissions, audit log.
Post-call: Warden scan tool result, PII filter, token optimize, audit log.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from maistro.security._types import AuditEntry, SentinelVerdict, Violation, WardenVerdict
from maistro.security.sentinel.pii_filter import scan_and_redact
from maistro.security.sentinel.token_optimizer import optimize_result
from maistro.security.sentinel.validator import validate_and_repair

logger = logging.getLogger("maistro.sentinel")

if TYPE_CHECKING:
    from maistro.security._types import AuditLog
    from maistro.security._types import AuthContext, PermissionTable
    from maistro.security.warden.detector import Warden


def check_permission(
    auth_context: AuthContext,
    tool_name: str,
    permission_table: PermissionTable,
) -> bool:
    return auth_context.can_use_tool(tool_name, permission_table)


class Sentinel:
    """Policy enforcement at every boundary crossing.

    Pre-call: validates args, checks permissions, logs audit.
    Post-call: scans result for threats + PII, optimizes tokens, logs audit.
    """

    def __init__(
        self,
        *,
        warden: Warden,
        permission_table: PermissionTable,
        audit_log: AuditLog | None = None,
    ) -> None:
        self._warden = warden
        self._permission_table = permission_table
        self._audit_log = audit_log

    async def pre_call(
        self,
        tool_name: str,
        args: dict[str, Any],
        auth: AuthContext,
        schema: dict[str, Any],
    ) -> SentinelVerdict:
        violations: list[Violation] = []

        if not check_permission(auth, tool_name, self._permission_table):
            violations.append(
                Violation(
                    boundary="pre_call",
                    rule="permission_denied",
                    severity="error",
                    detail=f"User '{auth.user_id}' lacks permission for tool '{tool_name}'",
                )
            )
            verdict = SentinelVerdict(
                allowed=False,
                violations=tuple(violations),
            )
            await self._log_audit(
                boundary="pre_call",
                user_id=auth.user_id,
                team_id=auth.team_id,
                tool_name=tool_name,
                verdict="denied",
                violations=tuple(violations),
            )
            return verdict

        schema_verdict = validate_and_repair(args, schema)
        if schema_verdict.violations:
            violations.extend(schema_verdict.violations)

        verdict = SentinelVerdict(
            allowed=True,
            repaired=schema_verdict.repaired,
            repaired_data=schema_verdict.repaired_data,
            violations=tuple(violations),
        )

        await self._log_audit(
            boundary="pre_call",
            user_id=auth.user_id,
            team_id=auth.team_id,
            tool_name=tool_name,
            verdict="allowed" if verdict.allowed else "denied",
            violations=tuple(violations),
            detail=f"repaired={schema_verdict.repaired}" if schema_verdict.repaired else "",
            repaired_data=schema_verdict.repaired_data if schema_verdict.repaired else None,
        )

        return verdict

    async def post_call(
        self,
        tool_name: str,
        result: str,
        auth: AuthContext,
    ) -> str:
        violations: list[Violation] = []
        processed = result

        warden_verdict = await self._warden.scan(processed, "tool_result")
        if not warden_verdict.clean:
            violations.append(
                Violation(
                    boundary="post_call",
                    rule="warden_tool_result",
                    severity="warning" if not warden_verdict.blocked else "error",
                    detail=f"Warden flags: {', '.join(warden_verdict.flags)}",
                )
            )
            if warden_verdict.blocked:
                processed = "[Tool result blocked by Warden -- contained injection attempt]"
            else:
                from maistro.security.warden.flag_response import build_flagged_response

                processed = build_flagged_response(
                    processed,
                    flags=list(warden_verdict.flags),
                    detection_layer=_detection_layer(warden_verdict),
                    flag_id=f"{auth.user_id}:{tool_name}:{id(result)}",
                )
                logger.warning(
                    "Tool result flagged: tool=%s, user=%s, flags=%s",
                    tool_name,
                    auth.user_id,
                    warden_verdict.flags,
                )

        processed, pii_matches = scan_and_redact(processed)
        if pii_matches:
            violations.append(
                Violation(
                    boundary="post_call",
                    rule="pii_detected",
                    severity="warning",
                    detail=f"Redacted {len(pii_matches)} PII pattern(s): "
                    + ", ".join(m.pii_type for m in pii_matches),
                )
            )

        processed = optimize_result(processed, tool_name)

        await self._log_audit(
            boundary="post_call",
            user_id=auth.user_id,
            team_id=auth.team_id,
            tool_name=tool_name,
            verdict="clean" if not violations else "flagged",
            violations=tuple(violations),
        )

        return processed

    async def _log_audit(
        self,
        *,
        boundary: str,
        user_id: str,
        team_id: str = "",
        tool_name: str,
        verdict: str,
        violations: tuple[Violation, ...] = (),
        detail: str = "",
        repaired_data: dict[str, Any] | None = None,
    ) -> None:
        if self._audit_log is None:
            return
        if repaired_data and not detail:
            detail = f"repaired_data_keys={list(repaired_data.keys())}"
        try:
            await self._audit_log.log(
                AuditEntry(
                    boundary=boundary,
                    user_id=user_id,
                    team_id=team_id,
                    tool_name=tool_name,
                    verdict=verdict,
                    violations=violations,
                    detail=detail,
                )
            )
        except Exception:
            logger.exception("Audit log write failed (boundary=%s, tool=%s)", boundary, tool_name)


def _detection_layer(verdict: WardenVerdict) -> str:
    for flag in verdict.flags:
        if flag.startswith("llm_classification"):
            return "Layer 3 (LLM)"
        if flag.startswith("prescriptive_"):
            return "Layer 2.5 (Semantic)"
        if flag.startswith("high_instruction") or flag.startswith("encoded_"):
            return "Layer 2 (Heuristic)"
    return "Layer 1 (Pattern)"
