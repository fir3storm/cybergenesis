"""Arena B6: winner proof certificate verifies offline; tampering fails."""

import json
import os
import subprocess
import sys

os.environ["OFFLINE_MODE"] = "true"
os.environ["SIM_STEP_DELAY_MS"] = "0"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


@pytest.fixture(autouse=True)
def _mem(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "arena_memory_path", str(tmp_path / "arena_memory.json"))


def _verify(path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "verify_cert.py"), str(path)],
                          capture_output=True, text=True)


def test_arena_certificate_valid_then_tampered_invalid(tmp_path):
    mid = client.post("/api/arena/matches", json={"scenario_id": "red_vs_blue_battle", "mode": "deterministic"}).json()["id"]
    cert = client.get(f"/api/arena/matches/{mid}/certificate")
    assert cert.status_code == 200, cert.text
    data = cert.json()
    assert data["kind"] == "arena_match" and data["winner"] in ("red", "blue") and len(data["signature"]) == 64

    good = tmp_path / "arena-cert.json"
    good.write_text(json.dumps(data), encoding="utf-8")
    out = _verify(good)
    assert out.returncode == 0 and "VALID" in out.stdout, out.stdout + out.stderr

    tampered = json.loads(json.dumps(data))
    tampered["winner"] = "red" if data["winner"] == "blue" else "blue"
    bad = tmp_path / "arena-cert-tampered.json"
    bad.write_text(json.dumps(tampered), encoding="utf-8")
    out = _verify(bad)
    assert out.returncode == 1 and "INVALID" in out.stdout


def test_arena_certificate_unknown_match_404():
    assert client.get("/api/arena/matches/missing/certificate").status_code == 404


def test_deterministic_replay_same_winner():
    a = client.post("/api/arena/matches", json={"scenario_id": "lateral_movement", "mode": "deterministic", "seed": 7}).json()
    b = client.post("/api/arena/matches", json={"scenario_id": "lateral_movement", "mode": "deterministic", "seed": 7}).json()
    assert a["winner"] == b["winner"] and a["rounds"] == b["rounds"]
