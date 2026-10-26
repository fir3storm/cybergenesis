import os
import sys

os.environ["SIM_STEP_DELAY_MS"] = "0"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import models  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.simulation.scenarios import SCENARIOS  # noqa: E402

init_db()
_db = SessionLocal()
for _sid, _s in SCENARIOS.items():
    if not _db.get(models.Scenario, _sid):
        _db.add(models.Scenario(id=_sid, name=_s["name"], description=_s["description"], definition=_s))
_db.commit()
_db.close()
