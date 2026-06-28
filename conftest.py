"""Repository-wide pytest compatibility hooks.

The workspace normally uses pytest-asyncio via the dev extra. Some constrained
scan environments can have pytest available before that plugin is installed. This
hook keeps async tests executable in those environments by running coroutine test
functions on a fresh event loop when no richer async plugin has handled them.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register async-related pytest settings when pytest-asyncio is absent."""
    parser.addini("asyncio_mode", "Fallback async test mode for this repository")


def pytest_configure(config: pytest.Config) -> None:
    """Register the asyncio marker for fallback async execution."""
    config.addinivalue_line("markers", "asyncio: run an async test function")


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    """Run coroutine test functions when pytest-asyncio is unavailable."""
    testfunction = pyfuncitem.obj
    if not inspect.iscoroutinefunction(testfunction):
        return None

    fixture_names = pyfuncitem._fixtureinfo.argnames
    testargs: dict[str, Any] = {
        name: pyfuncitem.funcargs[name]
        for name in fixture_names
        if name in pyfuncitem.funcargs
    }
    asyncio.run(testfunction(**testargs))
    return True
