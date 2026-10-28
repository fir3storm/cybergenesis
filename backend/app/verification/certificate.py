"""Proof-carrying defense: a verifiable certificate for a PASS/FAIL run.

Contains everything an independent checker needs — no LLM, no database:
scenario, seed, config hashes, applied diffs, min-cut, per-campaign replay
proofs (BFS frontier + the rule blocking each frontier edge), an event hash
chain, and an HMAC signature (demo key via CERT_DEMO_KEY).
"""

import hashlib
import hmac
import json
import os

from app.simulation.twin import DigitalTwin

DEMO_KEY = os.environ.get("CERT_DEMO_KEY")
if not DEMO_KEY:
    raise RuntimeError(
        "CERT_DEMO_KEY environment variable is not set: set CERT_DEMO_KEY to a long random "
        "secret before starting the backend (see .env.example / README 'Proof-carrying defense')."
    )


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
    canonical = json.dumps({k: cert[k] for k in sorted(cert)}, sort_keys=True, default=str)
    cert["signature"] = hmac.new(DEMO_KEY.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    return cert
