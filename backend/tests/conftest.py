import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("CERT_DEMO_KEY", "test-cert-key")  # required by app.verification.certificate at import
# Explicit empty admin token opts the write-capable settings endpoints into the
# open dev gate. A generated token would gate them and break the provider tests
# that exercise activation without a token.
os.environ["ADMIN_TOKEN"] = ""
# Test isolation: a throwaway sqlite DB in a temp dir, set BEFORE any app
# import reads settings — tests must never touch the demo DB (cybergenesis.db).
_TEST_DB_PATH = Path(tempfile.mkdtemp(prefix="cybergenesis-tests-")) / "cybergenesis-test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.as_posix()}"
os.environ["SIM_STEP_DELAY_MS"] = "0"
os.environ["OFFLINE_MODE"] = "true"  # hermetic tests: never call the live provider by default
os.environ["HUMAN_APPROVAL_ENABLED"] = "false"  # approval gate is exercised in its own test with a resolver
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import models
from app.db import SessionLocal, init_db
from app.simulation.scenarios import SCENARIOS

init_db()
_db = SessionLocal()
for _sid, _s in SCENARIOS.items():
    if not _db.get(models.Scenario, _sid):
        _db.add(models.Scenario(id=_sid, name=_s["name"], description=_s["description"], definition=_s))
_db.commit()
_db.close()
