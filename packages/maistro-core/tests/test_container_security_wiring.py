"""Wiring tests for Batch 2 security fixes: C1 (empty Sentinel permission
table) and H3 (unwired strike tracker) plus H12 (Warden not bound to skill
import).

Every test here goes through ``create_container()`` and never constructs
``Gate`` or ``Sentinel`` directly -- unlike the property tests under
``formal/`` and the unit tests in ``tests/security/test_gate.py``, which
inject their own correctly-wired objects and therefore never caught the
missing wiring in the first place.
"""

from __future__ import annotations

import pytest

from maistro.container import Container, create_container
from maistro.security._types import AuthContext, WardenVerdict
from maistro.security.patterns import DANGEROUS_TOOL_NAMES
from maistro.security.sentinel.authz_types import Principal
from maistro.security.strikes import InMemoryStrikeTracker
from maistro.skills.import_pipeline import ImportSource, SkillImportRequest
from maistro.types.config import AgentConfig, SecurityConfig

IMPORTER = Principal(id="importer1", kind="human")

VALID_SKILL_MD = """---
name: my_skill
description: Does a thing
parameters:
  type: object
  properties: {}
---
Body text here.

Explains how to use the tool in plain factual prose.
"""


async def _container(**security_overrides: object) -> Container:
    return await create_container(
        AgentConfig(
            router_api_key="test-key",
            security=SecurityConfig(**security_overrides),  # type: ignore[arg-type]
        )
    )


# --- Sentinel permission table wiring (C1) ----------------------------------


@pytest.mark.contract("behavioral")
@pytest.mark.scope("integration")
async def test_container_sentinel_permission_table_empty_by_default() -> None:
    container = await _container()
    assert container.sentinel._permission_table == {}


@pytest.mark.contract("behavioral")
@pytest.mark.scope("integration")
async def test_container_sentinel_permission_table_from_explicit_config() -> None:
    container = await _container(permissions={"deploy": ["admin"]})
    assert container.sentinel._permission_table == {"deploy": frozenset({"admin"})}


@pytest.mark.contract("behavioral")
@pytest.mark.scope("integration")
async def test_container_permission_preset_arms_dangerous_tools() -> None:
    container = await _container(permission_preset="dangerous_tools_admin")
    table = container.sentinel._permission_table
    assert set(table.keys()) == set(DANGEROUS_TOOL_NAMES)
    assert all(roles == frozenset({"admin"}) for roles in table.values())


@pytest.mark.contract("behavioral")
@pytest.mark.scope("integration")
async def test_wired_sentinel_denies_dangerous_tool_for_non_admin() -> None:
    container = await _container(permission_preset="dangerous_tools_admin")

    verdict = await container.sentinel.pre_call(
        "exec", {}, AuthContext(user_id="u1", roles=frozenset({"user"})), {}
    )
    assert verdict.allowed is False
    assert len(verdict.violations) == 1
    assert verdict.violations[0].rule == "permission_denied"
    assert verdict.violations[0].boundary == "pre_call"

    verdict_admin = await container.sentinel.pre_call(
        "exec", {}, AuthContext(user_id="u2", roles=frozenset({"admin"})), {}
    )
    assert verdict_admin.allowed is True


@pytest.mark.contract("behavioral")
@pytest.mark.scope("integration")
async def test_wired_sentinel_permits_unlisted_tool() -> None:
    container = await _container(permission_preset="dangerous_tools_admin")

    verdict = await container.sentinel.pre_call(
        "read_file", {}, AuthContext(user_id="u1", roles=frozenset({"user"})), {}
    )
    assert verdict.allowed is True


# --- Strike tracker wiring (H3) ----------------------------------------------


@pytest.mark.contract("behavioral")
@pytest.mark.scope("integration")
async def test_container_strike_tracker_absent_by_default() -> None:
    container = await _container()
    assert container.strike_tracker is None
    assert container.gate._strike_tracker is None


@pytest.mark.contract("behavioral")
@pytest.mark.scope("integration")
async def test_container_wires_strike_tracker_when_enabled() -> None:
    container = await _container(strike_tracking_enabled=True)
    assert container.strike_tracker is not None
    assert isinstance(container.strike_tracker, InMemoryStrikeTracker)
    assert container.gate._strike_tracker is container.strike_tracker


@pytest.mark.contract("behavioral")
@pytest.mark.scope("e2e")
async def test_three_strikes_through_wired_gate_disables_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full ladder through the container's own wired Gate + strike_tracker.

    Note: strike 2 imposes an 8-hour lockout, and the Gate short-circuits
    (blocks before ever calling Warden.scan or recording a new violation)
    while a user is locked -- see gate.py's ``is_locked`` check. So three
    *consecutive* process_input calls only ever reach strike 2; reaching
    strike 3 requires the lockout to have expired first, exactly as
    tests/security/test_gate.py::test_expired_lockout_falls_through_to_normal_scan
    simulates by rewinding ``locked_until`` on the tracker's own record.
    """
    container = await _container(strike_tracking_enabled=True)
    assert container.strike_tracker is not None

    scan_calls = 0

    async def _dirty_scan(content: str, boundary: str) -> WardenVerdict:
        nonlocal scan_calls
        scan_calls += 1
        return WardenVerdict(clean=False, flags=("injection",))

    monkeypatch.setattr(container.warden, "scan", _dirty_scan)

    auth = AuthContext(user_id="u1")

    result1 = await container.gate.process_input("x", auth=auth)
    assert result1.strike_number == 1

    result2 = await container.gate.process_input("x", auth=auth)
    assert result2.strike_number == 2
    assert result2.locked_until != ""

    # Expire the lockout directly on the container's own tracker record (the
    # same technique test_gate.py uses) so the next call falls through to a
    # fresh Warden scan instead of being short-circuited by the lockout.
    from datetime import UTC, datetime, timedelta

    record = await container.strike_tracker.get("u1")
    assert record is not None
    record.locked_until = datetime.now(UTC) - timedelta(seconds=1)

    result3 = await container.gate.process_input("x", auth=auth)
    assert result3.strike_number == 3
    assert result3.account_disabled is True

    assert scan_calls == 3

    result4 = await container.gate.process_input("x", auth=auth)
    assert result4.blocked is True
    assert "disabled" in result4.block_reason
    assert scan_calls == 3  # short-circuited before a 4th scan


# --- Skill import Warden binding (H12) ---------------------------------------


@pytest.mark.contract("boundary")
@pytest.mark.scope("integration")
async def test_container_import_skill_binds_warden_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    container = await _container()

    calls: list[tuple[str, str]] = []

    async def _recording_scan(content: str, boundary: str) -> WardenVerdict:
        calls.append((content, boundary))
        return WardenVerdict(clean=True, flags=("probe_flag",))

    monkeypatch.setattr(container.warden, "scan", _recording_scan)

    verdict = await container.import_skill(
        SkillImportRequest(source=ImportSource.PASTE, importer=IMPORTER, raw=VALID_SKILL_MD)
    )

    assert len(calls) == 1
    assert calls[0][1] == "skill_import"
    assert "warden:probe_flag" in verdict.report.scan_issues


@pytest.mark.contract("boundary")
@pytest.mark.scope("unit")
async def test_container_import_skill_explicit_warden_scan_wins() -> None:
    container = await _container()

    calls: list[str] = []

    async def _other_scan(content: str, boundary: str) -> WardenVerdict:
        calls.append(boundary)
        return WardenVerdict(clean=True)

    verdict = await container.import_skill(
        SkillImportRequest(source=ImportSource.PASTE, importer=IMPORTER, raw=VALID_SKILL_MD),
        warden_scan=_other_scan,
    )

    assert calls == ["skill_import"]
    assert verdict.outcome == "registered"
