"""Arena B4: API plays, persists and learns across matches."""

import os
import sys

os.environ["OFFLINE_MODE"] = "true"
os.environ["SIM_STEP_DELAY_MS"] = "0"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _mem(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "arena_memory_path", str(tmp_path / "arena_memory.json"))


def test_play_match_persists_and_league_counts():
    r = client.post("/api/arena/matches", json={"scenario_id": "red_vs_blue_battle", "mode": "learned"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["winner"] in ("red", "blue") and body["rounds"] and body["id"]
    assert body["memory"]["matches"] == 1

    listed = client.get("/api/arena/matches").json()
    assert any(m["id"] == body["id"] for m in listed)
    one = client.get(f"/api/arena/matches/{body['id']}").json()
    assert one["winner"] == body["winner"] and one["final_twin"]["assets"]

    league = client.get("/api/arena/league").json()
    assert league["matches"] >= 1 and league["red_wins"] + league["blue_wins"] == league["matches"]


def test_second_match_learns_from_first():
    client.post("/api/arena/matches", json={"scenario_id": "lateral_movement", "mode": "learned"})
    r = client.post("/api/arena/matches", json={"scenario_id": "lateral_movement", "mode": "learned"})
    assert r.json()["memory"]["matches"] == 2
    mem = client.get("/api/arena/memory").json()
    assert mem["matches"] == 2 and mem["blue_learned"] >= 1


def test_unknown_scenario_and_mode_422():
    assert client.post("/api/arena/matches", json={"scenario_id": "nope"}).status_code == 422
    assert client.post("/api/arena/matches", json={"scenario_id": "ransomware_activity", "mode": "magic"}).status_code == 422
    assert client.get("/api/arena/matches/missing").status_code == 404
