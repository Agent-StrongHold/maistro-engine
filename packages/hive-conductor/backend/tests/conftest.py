import sys
from pathlib import Path

# Allow `pytest packages/hive-conductor/backend/tests` from repo root.
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
