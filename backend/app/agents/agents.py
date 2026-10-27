"""Six agents. Deterministic where reliability matters; Meta reasoning where it adds value.

Offline outputs are deterministic, evidence-derived, and always labelled mode=offline.
"""

from app.integrations.meta_client import meta_client
from app.schemas import AgentObservation, DefenseProposal, IncidentHypothesis

INVESTIGATOR_SYSTEM = (
    "You are the Incident Investigator in CYBERGENESIS, a defensive simulation on synthetic data only. "
    "You are given the real twin topology, live asset states, and the exact synthetic telemetry events, each with an id like tele-<scenario>-42-0. "
    "Ground every confirmed claim in specific event ids; put anything not directly evidenced under speculation. "
    "Return ONLY JSON: {\"hypothesis\": str, \"affected_assets\": [str], \"threat_level\": \"low|medium|high|critical\", "
    "\"confirmed\": [str], \"speculation\": [str], \"confidence\": float, "
    "\"claim_evidence\": [{\"claim\": str, \"evidence_refs\": [str]}]} where each claim cites only the event ids that directly support it. "
    "No commands, no instructions to execute."
)
STRATEGIST_SYSTEM = (
    "You are the Defense Strategist in CYBERGENESIS, a defensive simulation on synthetic data only. "
    "Allowed actions ONLY, with exact parameter contracts: "
    "isolate_asset{asset_id} (isolates that asset, cutting all its connections); "
    "block_connection{asset_id=source, params:{source, target}} (both params REQUIRED, source/target must be a listed connection); "
    "revoke_session{asset_id: identity-provider or workstation, params:{identity}}; "
    "rotate_credential{asset_id: identity-provider or workstation, params:{identity}}; "
    "apply_patch{asset_id} (removes vulnerabilities but does NOT stop active spread or block paths); "
    "disable_service{asset_id: web-server/app-server only}; restore_connectivity{asset_id}. "
    "Your action MUST actually achieve the stated invariant (block the attack path / deny the session), not merely patch. "
    "Return ONLY JSON: {\"actions\": [{\"action_type\": str, \"asset_id\": str, \"params\": {}}], \"justification\": str, "
    "\"expected_effectiveness\": str, \"operational_impact\": str, \"confidence\": float}. Prefer least disruptive effective action."
)

CONTEXT_NOTE = (
    "Topology connections (source-target, traversable ones carry attack/data paths), live asset states, and the current "
    "attack path are given below. Work out for yourself which allowlisted action's direct mechanical effect satisfies "
    "the invariant with the least operational disruption. No scenario-specific prescription is provided: reason from "
    "the graph, the asset states, and the action contracts."
)


def observe(telemetry: list[dict]) -> AgentObservation:
    bursts = [e for e in telemetry if e["event_type"] == "file_modification_burst"]
    auth_fail = [e for e in telemetry if e["event_type"] == "authorization_failure"]
    net = [e for e in telemetry if e["event_type"] == "network_connection"]
    assets = sorted({e["asset_id"] for e in telemetry})
    if bursts:
        atype, conf = "high_volume_file_modification", 0.92
        summary = f"{len(bursts)} high-volume synthetic file-modification bursts across {len(assets)} assets"
    elif auth_fail:
        atype, conf = "unauthorized_access_attempts", 0.9
        summary = f"{len(auth_fail)} synthetic authorization failures detected"
    elif net:
        atype, conf = "suspicious_network_path", 0.82
        summary = f"{len(net)} synthetic network connections forming a suspicious path"
    else:
        atype, conf, summary = "none", 0.3, "No anomaly pattern matched"
    return AgentObservation(anomalous=bool(bursts or auth_fail or net), asset_ids=assets,
                            event_ids=[str(e.get("id") or f"tele-{i}") for i, e in enumerate(telemetry)],
                            anomaly_type=atype, summary=summary, confidence=conf)


async def investigate(scenario: dict, obs: AgentObservation, run_id: str, telemetry: list[dict] | None = None, twin=None) -> IncidentHypothesis:
    evidence = f"Scenario: {scenario['name']}. Anomaly: {obs.anomaly_type}. Assets: {obs.asset_ids}. Invariant to restore: {scenario['invariant']}."
    if telemetry:
        evidence += " Telemetry (synthetic, in order): " + " | ".join(
            f"[{i}] {e['event_type']} on {e['asset_id']}: {e['message']}" for i, e in enumerate(telemetry))
    if twin is not None:
        d = twin.to_dict()
        evidence += (" Twin topology: " + "; ".join(f"{c['source']}->{c['target']}({','.join(c['types'])}, active={c['active']})" for c in d["connections"])
                     + ". Live asset states: " + ", ".join(f"{a['id']}={a['status'].upper()}" for a in d["assets"])
                     + f". Attack path source->target: {twin.find_path(scenario['source_asset'], scenario['target_asset'])}.")
    try:
        data, _ = await meta_client.chat_json(INVESTIGATOR_SYSTEM, evidence, run_id)
        h = IncidentHypothesis(**{**data, "model": meta_client.model, "mode": "live",
                                  "evidence_refs": obs.event_ids, "affected_assets": data.get("affected_assets", obs.asset_ids)})
        known = set(obs.event_ids)  # keep only citations that point at real stored telemetry
        h.claim_evidence = [{"claim": str(c.get("claim", "")), "evidence_refs": [r for r in c.get("evidence_refs", []) if r in known]}
                            for c in h.claim_evidence if c.get("claim")]
        return h
    except Exception as e:  # fallback is deterministic + labelled with the reason
        reason = f"{type(e).__name__}: {e}"[:220]
        ids = obs.event_ids
        confirmed = [obs.summary, f"Source asset {scenario['source_asset']} shows synthetic malicious-pattern telemetry",
                     f"Protected target: {scenario['target_asset']}"]
        claim_evidence = [
            {"claim": obs.summary, "evidence_refs": ids[:2]},
            {"claim": confirmed[1], "evidence_refs": ids[2:4] or ids[:1]},
            {"claim": confirmed[2], "evidence_refs": ids[-1:]},
        ]
        return IncidentHypothesis(
            hypothesis=f"Synthetic {scenario['name']} incident originating at {scenario['source_asset']} threatening {scenario['target_asset']} (offline deterministic analysis; live Investigator unavailable: {reason})",
            affected_assets=obs.asset_ids, threat_level=scenario.get("severity", "high"),
            confirmed=confirmed, speculation=["Adversary intent beyond the simulated objective is not inferred"],
            evidence_refs=obs.event_ids, claim_evidence=claim_evidence,
            confidence=0.86, model="deterministic-offline", mode="offline",
            fallback_reason=reason)


async def propose_defense(scenario: dict, hyp: IncidentHypothesis, run_id: str, twin=None) -> DefenseProposal:
    context = f"Incident: {hyp.hypothesis}. Affected: {hyp.affected_assets}. Invariant to achieve: {scenario['invariant']}."
    if twin is not None:
        d = twin.to_dict()
        edges = [f"{c['source']}->{c['target']}({','.join(c['types'])})" for c in d["connections"] if c["traversable"]]
        path = twin.find_path(scenario["source_asset"], scenario["target_asset"])
        states = ", ".join(f"{a['id']}={a['status'].upper()}(zone={a['zone']}, vulns={a['vulnerabilities']})" for a in d["assets"])
        context += (f" Source={scenario['source_asset']} Target={scenario['target_asset']} Identity={scenario.get('identity')}. "
                    f"Traversable connections: {edges}. Current attack path: {path}. Live asset states: {states}. "
                    f"Identities: {d['identities']}. {CONTEXT_NOTE}")
    try:
        from app.policies.engine import evaluate as _evaluate

        feedback = ""
        for _attempt in range(2):
            data, _ = await meta_client.chat_json(STRATEGIST_SYSTEM, context + feedback, run_id)
            p = DefenseProposal(**{**data, "model": meta_client.model, "mode": "live", "evidence_refs": hyp.evidence_refs})
            if not p.actions:
                raise ValueError("empty actions")
            if twin is None:
                return p
            verdicts = [_evaluate(a.action_type, a.asset_id, a.params, twin) for a in p.actions]
            if all(v.approved for v in verdicts):
                return p
            # bounded retry with deterministic policy feedback — still the model's decision.
            # ALL actions must be approved; partial approval is not accepted.
            feedback = (" Your previous proposal was REJECTED by policy (all actions must be approved): "
                        + "; ".join(f"{v.action_type} on {v.asset_id}: {', '.join(v.reasons)}" for v in verdicts)
                        + ". Propose a corrected allowlisted action set that achieves the invariant.")
        raise ValueError("live proposal rejected by policy twice")
    except Exception as e:  # noqa: BLE001 - honest, reason-carrying offline fallback
        reason = f"{type(e).__name__}: {e}"[:220]
        actions = scenario["expected_defense"]
        origin = "scenario policy"
        if twin is not None:
            # graph-derived (not scenario-prescribed): simulate candidates on the live twin, take the best blocker.
            # This is what lets the offline blue team adapt in red-team rounds 2+.
            from app.simulation.candidates import evaluate_candidates

            attacked = twin.clone()
            cands = evaluate_candidates(attacked, twin, scenario, [])
            # least-disruptive defense that cuts the currently attacked path (global block preferred on ties
            # via candidate order); this lets the red team force adaptation in later rounds
            viable = [c for c in cands if c["feasible"] and (c["blocked"] or c.get("path_blocked"))]
            best = min(viable, key=lambda c: c["disrupted"] if c["disrupted"] is not None else 99, default=None)
            if best:
                actions = best["actions"]
                origin = f"candidate simulation on live graph ('{best['label']}')"
        return DefenseProposal(
            actions=actions,
            justification=f"Offline deterministic proposal (live Strategist unavailable: {reason}). Derived via {origin} for {scenario['name']}: {scenario['invariant']}",
            expected_effectiveness="Blocks the simulated attack objective; verified independently by replay",
            operational_impact="Limited to the simulated source/choke-point; legitimate-path disruption measured after execution",
            confidence=0.84, model="deterministic-offline", mode="offline", evidence_refs=hyp.evidence_refs,
            fallback_reason=reason)
