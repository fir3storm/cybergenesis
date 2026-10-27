import json
import os
import subprocess
import sys

os.environ["OFFLINE_MODE"] = "true"
os.environ["SIM_STEP_DELAY_MS"] = "0"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.orchestration.orchestrator import run_experiment  # noqa: E402

client = TestClient(app)
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


@pytest.mark.asyncio
async def test_certificate_valid_then_tampered_invalid(tmp_path):
    rid = client.post("/api/experiments", json={"scenario_id": "ransomware_activity", "seed": 42}).json()["id"]
    await run_experiment(rid)
    cert = client.get(f"/api/experiments/{rid}/certificate")
    assert cert.status_code == 200, cert.text
    data = cert.json()
    assert data["signature"] and data["event_hash_chain"] and data["campaigns"]
    assert data["config_hash_before"] != data["config_hash_after"] or data["applied_diffs"]

    good = tmp_path / "cert.json"
    good.write_text(json.dumps(data), encoding="utf-8")
    out = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "verify_cert.py"), str(good)],
                         capture_output=True, text=True)
    assert out.returncode == 0 and "VALID" in out.stdout, out.stdout + out.stderr

    tampered = json.loads(json.dumps(data))
    # flip one connection back to active: the certified twin now reaches the target
    for c in tampered["final_twin"]["connections"]:
        c["active"] = True
        c["dir_forward_active"] = True
        c["dir_reverse_active"] = True
    for a in tampered["final_twin"]["assets"]:
        a["isolated"] = False
    bad = tmp_path / "cert-tampered.json"
    bad.write_text(json.dumps(tampered), encoding="utf-8")
    out = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "verify_cert.py"), str(bad)],
                         capture_output=True, text=True)
    assert out.returncode == 1 and "INVALID" in out.stdout
