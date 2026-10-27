"""Simulate-before-acting: replay candidate defenses on cloned twins and score the trade-off."""

import networkx as nx

from app.policies.engine import evaluate
from app.simulation.twin import DigitalTwin

# Deterministic invasiveness ordering (lower = less invasive), used as the
# final ranking key after blocked/disrupted. Rationale: a one-way egress
# block removes a single directed arc and nothing else; an ingress block is
# the same arc controlled at the receiving device; targeted remediation
# (harden/patch/session actions) changes one asset's posture; a both-way
# block removes an arc pair; quarantine moves an asset onto an isolated
# VLAN; isolation removes the asset from the topology; disabling a service
# takes a production service down. Anything else (incl. multi-action agent
# proposals, scored by their most invasive action) sorts last.
_BLOCK_INVASIVENESS = {"egress": 0, "outbound": 0, "ingress": 1, "both": 3}
_ACTION_INVASIVENESS = {
    "harden_mgmt": 2,
    "apply_patch": 2,
    "revoke_session": 2,
    "rotate_credential": 2,
    "enforce_mfa": 2,
    "quarantine_vlan": 4,
    "isolate_asset": 5,
    "disable_service": 6,
}
_DEFAULT_INVASIVENESS = 7


def invasiveness(actions: list[dict]) -> int:
    """Candidate invasiveness = its most invasive action (empty = default)."""
    worst = -1
    for a in actions:
        if a.get("action_type") == "block_connection":
            rank = _BLOCK_INVASIVENESS.get((a.get("params") or {}).get("direction", "both"), 3)
        else:
            rank = _ACTION_INVASIVENESS.get(a.get("action_type", ""), _DEFAULT_INVASIVENESS)
        worst = max(worst, rank)
    return worst if worst >= 0 else _DEFAULT_INVASIVENESS


def _score(clone: DigitalTwin, baseline: DigitalTwin, scenario: dict, actions: list[dict], label: str, origin: str,
           original_path: list[str] | None = None) -> dict:
    rank = invasiveness(actions)
    applied = []
    for a in actions:
        d = evaluate(a["action_type"], a["asset_id"], a.get("params", {}), clone)
        if not d.approved:
            return {"label": label, "origin": origin, "actions": actions, "feasible": False,
                    "blocked": False, "disrupted": None, "invasiveness": rank,
                    "detail": f"policy rejected: {'; '.join(d.reasons)}"}
        try:
            clone.apply_action(a["action_type"], a["asset_id"], a.get("params", {}))
            applied.append(a["action_type"])
        except ValueError as e:
            return {"label": label, "origin": origin, "actions": actions, "feasible": False,
                    "blocked": False, "disrupted": None, "invasiveness": rank, "detail": str(e)}
    result = clone.attempt_attack_objective(scenario)
    disrupted = clone.legitimate_disrupted(baseline)
    new_path = clone.find_path(scenario["source_asset"], scenario["target_asset"])
    return {"label": label, "origin": origin, "actions": actions, "feasible": True,
            "blocked": bool(result["objective_blocked"]),
            "path_blocked": bool(original_path) and new_path != original_path,
            "disrupted": disrupted, "invasiveness": rank,
            "detail": f"applied {applied}; objective_blocked={result['objective_blocked']}"}


def _min_cut_edges(attacked: DigitalTwin, src: str, tgt: str) -> list[tuple[str, str]]:
    """Minimum edge cut src->tgt on the twin's live graph (attacker semantics),
    deterministically ordered. Empty when no path / no such nodes."""
    try:
        g = attacked.live_graph(tgt)
        if src not in g or tgt not in g:
            return []
        return sorted(nx.minimum_edge_cut(g, src, tgt))
    except Exception:  # noqa: BLE001 - no path -> no cut to offer
        return []


def _has_mgmt_weakness(attacked: DigitalTwin, asset_id: str) -> bool:
    cfg = attacked.device_configs.get(asset_id, {})
    mgmt = cfg.get("mgmt", {}) or {}
    weaknesses = set(attacked.vulns.get(asset_id, [])) | set(cfg.get("weaknesses", []) or [])
    return bool(mgmt.get("telnet") or mgmt.get("snmp_community")
                or "telnet_enabled" in weaknesses or "snmp_public_community" in weaknesses)


def evaluate_candidates(attacked: DigitalTwin, baseline: DigitalTwin, scenario: dict,
                        proposal_actions: list[dict]) -> list[dict]:
    """Candidates: the agent proposal + mechanically distinct alternatives from the live graph."""
    src, tgt = scenario["source_asset"], scenario["target_asset"]
    path = attacked.find_path(src, tgt) or []
    candidates: list[tuple[str, str, list[dict]]] = [("Agent proposal", "ai", proposal_actions)]
    if scenario["verification_kind"] == "reachability":
        candidates.append((f"Isolate source ({src})", "simulated",
                           [{"action_type": "isolate_asset", "asset_id": src, "params": {}}]))
        # Surgical options first: block every minimum-cut edge, controlled
        # from either end of the arc. Egress = block u->v at u; ingress =
        # block u->v at v (the receiving device's inbound control). Both
        # remove the same directed arc the attacker needs, so both are
        # directionally meaningful for every directed cut edge.
        for u, v in _min_cut_edges(attacked, src, tgt):
            candidates.append((f"Segment {u} → {v} (egress only, min-cut)", "simulated",
                               [{"action_type": "block_connection", "asset_id": u,
                                 "params": {"source": u, "target": v, "direction": "egress"}}]))
            candidates.append((f"Segment {u} → {v} (ingress only, min-cut)", "simulated",
                               [{"action_type": "block_connection", "asset_id": v,
                                 "params": {"source": v, "target": u, "direction": "ingress"}}]))
        for i in range(len(path) - 1):
            s, t = path[i], path[i + 1]
            candidates.append((f"Segment {s} → {t} (egress only)", "simulated",
                               [{"action_type": "block_connection", "asset_id": s,
                                 "params": {"source": s, "target": t, "direction": "egress"}}]))
        # Quarantine the source, and any distinct compromised intermediate.
        candidates.append((f"Quarantine source ({src})", "simulated",
                           [{"action_type": "quarantine_vlan", "asset_id": src, "params": {}}]))
        for node in path[1:-1]:
            if node != src and attacked.status.get(node) == "compromised":
                candidates.append((f"Quarantine compromised intermediate ({node})", "simulated",
                                   [{"action_type": "quarantine_vlan", "asset_id": node, "params": {}}]))
        # Harden management planes (telnet / SNMP public) along the attack path.
        for node in path:
            if _has_mgmt_weakness(attacked, node):
                candidates.append((f"Harden management ({node})", "simulated",
                                   [{"action_type": "harden_mgmt", "asset_id": node, "params": {}}]))
        if path:
            candidates.append((f"Patch source ({src}) only", "simulated",
                               [{"action_type": "apply_patch", "asset_id": src, "params": {}}]))
    else:
        ident = scenario.get("identity") or "admin-01"
        candidates.append(("Revoke session only", "simulated",
                           [{"action_type": "revoke_session", "asset_id": "identity-provider", "params": {"identity": ident}}]))
        candidates.append(("Rotate credential only", "simulated",
                           [{"action_type": "rotate_credential", "asset_id": "identity-provider", "params": {"identity": ident}}]))
    seen: set[str] = set()
    results = []
    for label, origin, actions in candidates:
        sig = str(sorted(str(a) for a in actions))
        if sig in seen:
            continue
        seen.add(sig)
        results.append(_score(attacked.clone(), baseline, scenario, [dict(a) for a in actions], label, origin, original_path=path))
    # Best trade-off first: blocked, then least legitimate disruption, then
    # least invasive (ordering documented above); the agent proposal wins
    # exact ties (it reasoned about context), then label for determinism.
    results.sort(key=lambda r: (not r["blocked"], r["disrupted"] if r["disrupted"] is not None else 99,
                                r.get("invasiveness", _DEFAULT_INVASIVENESS),
                                0 if r["origin"] == "ai" else 1, r["label"]))
    return results
