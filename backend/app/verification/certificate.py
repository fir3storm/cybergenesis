"""Proof-carrying defense: a verifiable certificate for a PASS/FAIL run.

Contains everything an independent checker needs — no LLM, no database:
scenario, seed, config hashes, applied diffs, min-cut, per-campaign replay
proofs (BFS frontier + the rule blocking each frontier edge), an event hash
chain, and two signatures:
- ``ed25519``: public-key signature. Anyone can verify it with only the
  public key (published at /api/certificates/public-key), no shared secret.
- ``signature``: the legacy HMAC (CERT_DEMO_KEY), kept for older checkers.
"""

import hashlib
import hmac
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core.config import settings
from app.simulation.twin import DigitalTwin

# pydantic-settings reads backend/.env but does not export it to os.environ,
# so fall back to settings or a key kept only in .env is never seen.
DEMO_KEY = os.environ.get("CERT_DEMO_KEY") or settings.cert_demo_key
if not DEMO_KEY:
    raise RuntimeError(
        "CERT_DEMO_KEY environment variable is not set: set CERT_DEMO_KEY to a long random "
        "secret before starting the backend (see .env.example / README 'Proof-carrying defense')."
    )


_SIGNING_KEY: Ed25519PrivateKey | None = None


def signing_key() -> Ed25519PrivateKey:
    """Ed25519 key, created on first use and kept on this machine (gitignored PEM)."""
    global _SIGNING_KEY
    if _SIGNING_KEY is None:
        path = Path(os.environ.get("CERT_SIGNING_KEY_PATH") or settings.cert_signing_key_path)
        if path.exists():
            key = serialization.load_pem_private_key(path.read_bytes(), password=None)
            if not isinstance(key, Ed25519PrivateKey):
                raise RuntimeError(f"{path} is not an Ed25519 private key")
        else:
            key = Ed25519PrivateKey.generate()
            path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                               serialization.NoEncryption()))
        _SIGNING_KEY = key
    return _SIGNING_KEY


def public_key_hex() -> str:
    return signing_key().public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()


def ed25519_payload(cert: dict) -> bytes:
    """Bytes covered by the Ed25519 signature: everything except the two signature fields."""
    body = {k: cert[k] for k in sorted(cert) if k not in ("signature", "ed25519")}
    return json.dumps(body, sort_keys=True, default=str).encode()


def _chain(events: list[dict]) -> str:
    h = "cybergenesis-genesis"
    for e in events:
        blob = json.dumps(e, sort_keys=True, default=str)
        h = hashlib.sha256(f"{h}:{blob}".encode()).hexdigest()
    return h


def _frontier_proof(twin: DigitalTwin, src: str, tgt: str) -> dict:
    """BFS from src over the gated live graph; every frontier arc gets its blocking rule."""
    g = twin.live_graph(tgt)
    visited = {src}
    stack = [src]
    while stack:
        node = stack.pop()
        for nb in (g.successors(node) if node in g else []):
            if nb not in visited:
                visited.add(nb)
                stack.append(nb)
    frontier = []
    for u in visited:
        for v in twin.graph.successors(u):
            if v in visited:
                continue
            if not twin.graph[u][v].get("traversable", False):
                reason = "arc not traversable (auth/monitoring)"
            elif not twin.dir_active.get((u, v), False):
                reason = "directed arc blocked (segmentation/egress rule)"
            elif twin.isolated.get(v) or twin.isolated.get(u):
                reason = "endpoint isolated"
            elif v in twin.quarantined:
                reason = "endpoint quarantined (VLAN 999)"
            elif not twin.hop_allowed(v, tgt):
                reason = "vulnerability gate: no weakness and no identity session"
            else:
                reason = "not reachable in gated graph"
            frontier.append({"from": u, "to": v, "blocking_rule": reason})
    return {"target_reachable": tgt in visited, "visited": sorted(visited), "frontier": frontier}


def build_certificate(run, scenario: dict, baseline_twin: DigitalTwin, final_twin: DigitalTwin,
                      executions: list[dict], verifications: list[dict], events: list[dict]) -> dict:
    from app.verification.verifier import _min_edge_cut

    cert: dict = {
        "version": 1,
        "run_id": run.id,
        "scenario": {"id": scenario["id"], "name": scenario.get("name"), "source": scenario["source_asset"],
                     "target": scenario["target_asset"], "invariant": scenario["invariant"]},
        "seed": run.seed,
        "mode": run.mode,
        "config_hash_before": baseline_twin.config_hash(),
        "config_hash_after": final_twin.config_hash(),
        "applied_diffs": executions,
        "min_cut_edges": _min_edge_cut(baseline_twin, scenario),
        "campaigns": [],
        "final_twin": final_twin.to_dict(),
        "event_hash_chain": _chain(events),
        "events_count": len(events),
    }
    for v in verifications:
        cert["campaigns"].append({
            "outcome": v["outcome"], "invariant": v["invariant"], "checks": v["checks"],
            "metrics": {k: v["metrics"].get(k) for k in ("defense_effectiveness_pct", "optimal_edge_cut",
                                                         "defense_edges_removed", "optimality_gap", "rounds")},
            "unreachable_proof": _frontier_proof(final_twin, scenario["source_asset"], scenario["target_asset"]),
        })
    # Optimality proof (Menger duality) BEFORE both signatures so Ed25519 and
    # HMAC cover it; legacy fields above stay unchanged for old checkers.
    if scenario.get("verification_kind", "reachability") == "reachability":
        from app.verification.optimality import build_optimality_proof

        cert["optimality_proof"] = build_optimality_proof(baseline_twin, final_twin, scenario)
    cert["ed25519"] = {"alg": "Ed25519", "public_key": public_key_hex(),
                       "signature": signing_key().sign(ed25519_payload(cert)).hex()}
    # HMAC last, over everything above (including the Ed25519 block) — unchanged legacy semantics
    canonical = json.dumps({k: cert[k] for k in sorted(cert)}, sort_keys=True, default=str)
    cert["signature"] = hmac.new(DEMO_KEY.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    return cert
