import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


@pytest.fixture(autouse=True, scope="session")
def _init_engine() -> None:
    import services.engine as engine_mod
    from adapters.maistro_core import StubAgentPort

    if engine_mod._singleton is None:
        svc = engine_mod.EngineService()
        svc._agent_port = StubAgentPort()
        engine_mod._singleton = svc

    import services.foundation as foundation_mod

    if foundation_mod._singleton is None:
        f = foundation_mod.Foundation()
        foundation_mod._singleton = f

    import stores

    stores.initialize_stores()
