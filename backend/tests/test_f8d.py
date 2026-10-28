import json
import os
import subprocess
import sys

os.environ["OFFLINE_MODE"] = "true"
os.environ["SIM_STEP_DELAY_MS"] = "0"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.orchestration.orchestrator import run_experiment

client = TestClient(app)
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def _verify(path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "verify_cert.py"), str(path)],
                          capture_output=True, text=True, check=False)


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
    out = _verify(good)
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
    out = _verify(bad)
    assert out.returncode == 1 and "INVALID" in out.stdout


def _verify_args(*args, env_drop_hmac=False) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if env_drop_hmac:
        env.pop("CERT_DEMO_KEY", None)
    return subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "verify_cert.py"), *map(str, args)],
                          capture_output=True, text=True, check=False, env=env)


@pytest.mark.asyncio
async def test_ed25519_certificate_verifies_with_public_key_only(tmp_path):
    rid = client.post("/api/experiments", json={"scenario_id": "ransomware_activity", "seed": 7}).json()["id"]
    await run_experiment(rid)
    data = client.get(f"/api/experiments/{rid}/certificate").json()
    pub = client.get("/api/certificates/public-key").json()
    assert data["ed25519"]["alg"] == "Ed25519" and data["ed25519"]["public_key"] == pub["public_key"]

    good = tmp_path / "cert.json"
    good.write_text(json.dumps(data), encoding="utf-8")
    # no shared secret at all: the public key alone proves integrity
    out = _verify_args(good, "--pubkey", pub["public_key"], env_drop_hmac=True)
    assert out.returncode == 0 and "Ed25519 verified" in out.stdout, out.stdout + out.stderr

    # a different signer is rejected when the key is pinned
    out = _verify_args(good, "--pubkey", "00" * 32, env_drop_hmac=True)
    assert out.returncode == 1 and "pinned" in out.stdout

    # editing any signed field (here: the claimed seed) breaks the signature
    edited = json.loads(json.dumps(data)); edited["seed"] = 999
    bad = tmp_path / "edited.json"
    bad.write_text(json.dumps(edited), encoding="utf-8")
    out = _verify_args(bad, env_drop_hmac=True)
    assert out.returncode == 1 and "Ed25519 signature invalid" in out.stdout
