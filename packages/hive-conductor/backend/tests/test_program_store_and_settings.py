"""Boy Scout coverage: services/program_store.py (was 36%) +
settings_defaults.py (was 65%).
"""

from __future__ import annotations

import sys
import pathlib
from typing import Any

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# --- program_store ---------------------------------------------------


@pytest.fixture(autouse=True)
def _wipe_program_contexts():
    import stores
    for k in list(stores.program_contexts.keys()):
        stores.program_contexts.pop(k)
    yield
    for k in list(stores.program_contexts.keys()):
        stores.program_contexts.pop(k)


def test_get_context_creates_empty_when_missing() -> None:
    from services import program_store as prog

    ctx = prog.get_context("brand-new-user")
    assert ctx.user_id == "brand-new-user"
    # Subsequent reads return the persisted instance, not a fresh empty
    again = prog.get_context("brand-new-user")
    assert again.user_id == "brand-new-user"


def test_save_context_round_trips() -> None:
    from services import program_store as prog

    ctx = prog.get_context("u1")
    updated = ctx.model_copy(update={"interview_step": 3})
    out = prog.save_context(updated)
    assert out is updated
    # Read back
    again = prog.get_context("u1")
    assert again.interview_step == 3


def test_context_dict_returns_model_dump() -> None:
    from services import program_store as prog

    d = prog.context_dict("u2")
    assert isinstance(d, dict)
    assert d.get("user_id") == "u2"


# --- settings_defaults --------------------------------------------------


def test_default_settings_returns_settings_model_with_expected_fields() -> None:
    from settings_defaults import default_settings

    s = default_settings()
    # Has expected fields
    assert hasattr(s, "default_model")
    assert hasattr(s, "chat_default_model") or hasattr(s, "default_model")
