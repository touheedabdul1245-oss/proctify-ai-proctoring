"""Make backend/tests hermetic: point DATABASE_URL at a per-run temp SQLite
BEFORE any test module imports the app stack.

pytest imports this module before collecting test modules, so the env override
here always wins — regardless of what a test module imports (config/database/
main bind DATABASE_URL at import time, see backend/config.py, so any later
assignment in a test module body would be a no-op and the suite would silently
talk to the real dev DB).
"""
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="proctify_tests_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ.setdefault("PROCTIFY_JWT_SECRET", "stage-tests-secret")