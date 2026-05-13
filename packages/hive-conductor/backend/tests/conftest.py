import sys
from pathlib import Path

import pytest

# Allow `pytest packages/hive-conductor/backend/tests` from repo root.
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


@pytest.fixture(autouse=True, scope="session")
def _init_engine() -> None:
    """Initialise a stub EngineService singleton so routes don't raise on get_engine()."""
    import services.engine as engine_mod
    from adapters.maistro_core import StubAgentPort

    if engine_mod._singleton is None:
        svc = engine_mod.EngineService()
        svc._agent_port = StubAgentPort()
        # _queue stays None → missions route falls back to in-memory store
        engine_mod._singleton = svc
