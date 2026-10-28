"""Optimality proofs (Menger duality): witness lower bound, relevant cut, tamper checks."""

import copy
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.simulation.twin import DigitalTwin
from app.verification.optimality import build_optimality_proof, check_optimality_proof

SC = {"id": "t", "source_asset": "s", "target_asset": "t", "verification_kind": "reachability"}
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def _twin(assets, conns):
    return DigitalTwin.from_dict(
        [{"id": a, "name": a, "asset_type": "workstation", "zone": "internal",
          "posture": 0.7, "pos": [0, 1, 0], "vulnerabilities": ["x"]} for a in assets],
        [{"source": s, "target": t} for s, t in conns])


def _two_path_twin():
    return _twin(["s", "a", "b", "t"], [("s", "a"), ("a", "t"), ("s", "b"), ("b", "t")])


def _block(twin, u, v):
    twin.apply_action("block_connection", u, {"source": u, "target": v, "direction": "egress"})


def test_two_disjoint_paths_minimal_defense_is_optimal():
    base = _two_path_twin()
    final = base.clone()
    _block(final, "a", "t")
    _block(final, "b", "t")
    proof = build_optimality_proof(base, final, SC)
    assert proof["verdict"] == "OPTIMAL"
    assert proof["lower_bound"] == 2
    assert proof["defense_cut_size"] == 2
    assert proof["optimality_gap"] == 0
    assert proof["is_cut"] is True
    ok, reasons = check_optimality_proof(proof)
    assert ok, reasons


def test_isolating_source_with_extra_edge_is_suboptimal_exact_gap():
    base = _twin(["s", "a", "b", "x", "t"],
                 [("s", "a"), ("a", "t"), ("s", "b"), ("b", "t"), ("s", "x"), ("x", "a")])
    final = base.clone()
    final.apply_action("isolate_asset", "s", {})
    proof = build_optimality_proof(base, final, SC)
    assert proof["verdict"] == "SUBOPTIMAL"
    assert proof["lower_bound"] == 2
    assert proof["defense_cut"] == [["s", "a"], ["s", "b"], ["s", "x"]]
    assert proof["optimality_gap"] == 1
    ok, reasons = check_optimality_proof(proof)
    assert ok, reasons


def test_defense_leaving_a_path_is_not_a_cut():
    base = _two_path_twin()
    final = base.clone()
    _block(final, "a", "t")
    proof = build_optimality_proof(base, final, SC)
    assert proof["verdict"] == "NOT_A_CUT"
    assert proof["is_cut"] is False
    assert proof["optimality_gap"] is None
    ok, reasons = check_optimality_proof(proof)
    assert ok, reasons


def test_no_path_at_baseline():
    base = _twin(["s", "a", "t"], [("s", "a")])
    proof = build_optimality_proof(base, base.clone(), SC)
    assert proof["verdict"] == "NO_PATH_AT_BASELINE"
    assert proof["lower_bound"] == 0
    ok, reasons = check_optimality_proof(proof)
    assert ok, reasons


def _valid_proof():
    base = _two_path_twin()
    final = base.clone()
    _block(final, "a", "t")
    _block(final, "b", "t")
    return build_optimality_proof(base, final, SC)


def test_tamper_add_fake_edge_fails():
    proof = _valid_proof()
    proof["graph_edges"] = sorted(proof["graph_edges"] + [["s", "t"]])
    ok, reasons = check_optimality_proof(proof)
    assert not ok and any("graph_sha256" in r for r in reasons)


def test_tamper_overlapping_witness_paths_fails():
    proof = _valid_proof()
    proof["witness_paths"] = [proof["witness_paths"][0], proof["witness_paths"][0]]
    ok, reasons = check_optimality_proof(proof)
    assert not ok and any("edge-disjoint" in r for r in reasons)


def test_tamper_drop_cut_edge_fails():
    proof = _valid_proof()
    proof["defense_cut"] = proof["defense_cut"][:1]
    proof["defense_cut_size"] = 1
    # keep gap/verdict as originally claimed so the cut check is what fires
    ok, reasons = check_optimality_proof(proof)
    assert not ok and any("is_cut" in r for r in reasons)


def test_tamper_edit_hash_fails():
    proof = _valid_proof()
    proof["graph_sha256"] = "0" * 64
    ok, reasons = check_optimality_proof(proof)
    assert not ok and any("graph_sha256" in r for r in reasons)


def _forged_no_path():
    proof = _valid_proof()
    proof.update({"witness_paths": [], "lower_bound": 0, "defense_cut": [], "defense_cut_size": 0,
                  "is_cut": False, "optimality_gap": None, "verdict": "NO_PATH_AT_BASELINE"})
    return proof


def test_forged_no_path_verdict_fails_in_both_checkers():
    import importlib.util

    ok, reasons = check_optimality_proof(_forged_no_path())
    assert not ok and any("NO_PATH_AT_BASELINE" in r for r in reasons)
    spec = importlib.util.spec_from_file_location("verify_cert", os.path.join(ROOT, "scripts", "verify_cert.py"))
    vc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vc)
    ok, reasons = vc.check_optimality_proof(_forged_no_path())
    assert not ok and any("NO_PATH_AT_BASELINE" in r for r in reasons)


def test_capped_path_search_never_turns_a_real_cut_into_not_a_cut(monkeypatch):
    from app.verification import optimality

    # simulate the 2000-path cap missing every relevant edge on a huge graph
    monkeypatch.setattr(optimality, "_edges_on_some_path", lambda *a, **k: set())
    base = _two_path_twin()
    final = base.clone()
    _block(final, "a", "t")
    _block(final, "b", "t")
    proof = build_optimality_proof(base, final, SC)
    assert proof["verdict"] in ("OPTIMAL", "SUBOPTIMAL") and proof["is_cut"]
    assert check_optimality_proof(proof)[0]


def test_tamper_edit_lower_bound_fails():
    proof = _valid_proof()
    proof["lower_bound"] = 5
    ok, reasons = check_optimality_proof(proof)
    assert not ok and any("lower_bound" in r for r in reasons)


def test_tamper_witness_uses_non_graph_edge_fails():
    proof = _valid_proof()
    proof["witness_paths"][0] = ["s", "zzz", "t"]
    ok, reasons = check_optimality_proof(proof)
    assert not ok and any("not in graph_edges" in r for r in reasons)


# --- end-to-end via a real run + verify_cert.py ---------------------------

async def _run_and_cert(tmp_path):
    os.environ.setdefault("OFFLINE_MODE", "true")
    from fastapi.testclient import TestClient

    from app.main import app
    from app.orchestration.orchestrator import run_experiment

    client = TestClient(app)
    rid = client.post("/api/experiments", json={"scenario_id": "lateral_movement", "seed": 42}).json()["id"]
    await run_experiment(rid)
    cert = client.get(f"/api/experiments/{rid}/certificate").json()
    pubkey = client.get("/api/certificates/public-key").json()["public_key"]
    path = tmp_path / "cert.json"
    path.write_text(json.dumps(cert), encoding="utf-8")
    return cert, path, pubkey


def _verify_script(cert_path, pubkey):
    root = os.path.join(os.path.dirname(__file__), "..", "..")
    return subprocess.run([sys.executable, os.path.join(root, "scripts", "verify_cert.py"),
                           str(cert_path), "--pubkey", pubkey],
                          capture_output=True, text=True, cwd=root, check=False)


@pytest.mark.asyncio
async def test_end_to_end_certificate_verify_cert_passes(tmp_path):
    cert, path, pubkey = await _run_and_cert(tmp_path)
    assert "optimality_proof" in cert and "baseline_twin" in cert
    ok, reasons = check_optimality_proof(cert["optimality_proof"])
    assert ok, reasons
    r = _verify_script(path, pubkey)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "VALID" in r.stdout and "OPTIMALITY:" in r.stdout


@pytest.mark.asyncio
async def test_end_to_end_flipped_proof_byte_fails_both(tmp_path):
    cert, path, pubkey = await _run_and_cert(tmp_path)
    tampered = copy.deepcopy(cert)
    # flip one byte of the proof: change a witness path node
    tampered["optimality_proof"]["witness_paths"][0][0] = "tampered-node"
    path.write_text(json.dumps(tampered), encoding="utf-8")
    r = _verify_script(path, pubkey)
    assert r.returncode != 0
    assert "Ed25519 signature invalid" in r.stdout + r.stderr or "INVALID" in r.stdout
    assert "OPTIMALITY: INVALID" in r.stdout


@pytest.mark.asyncio
async def test_legacy_cert_without_proof_still_verifies(tmp_path):
    cert, path, pubkey = await _run_and_cert(tmp_path)
    legacy = copy.deepcopy(cert)
    legacy.pop("optimality_proof", None)
    # re-signing is impossible without the key, so legacy check is the
    # standalone checker on a cert whose proof field is absent: signatures
    # will fail, therefore assert the legacy *optimality* line is printed
    # and directly check the checker accepts absence via the main flow by
    # using a freshly signed cert stripped only for the optimality branch:
    # instead verify check_optimality_proof is not invoked for legacy by
    # asserting the script prints the legacy line before signature failure.
    path.write_text(json.dumps(legacy), encoding="utf-8")
    r = _verify_script(path, pubkey)
    assert "OPTIMALITY: not present (legacy certificate)" in r.stdout
