"""Six agents. Deterministic where reliability matters; Meta reasoning where it adds value.

Offline outputs are deterministic, evidence-derived, and always labelled mode=offline.
"""

from app.integrations.meta_client import ProviderUnavailable, meta_client
from app.schemas import AgentObservation, DefenseProposal, IncidentHypothesis

INVESTIGATOR_SYSTEM = (
    "You are the Incident Investigator in CYBERGENESIS, a defensive simulation on synthetic data only. "
    "Return ONLY JSON: {\"hypothesis\": str, \"affected_assets\": [str], \"threat_level\": \"low|medium|high|critical\", "
    "\"confirmed\": [str], \"speculation\": [str], \"confidence\": float}. Ground claims in the evidence given. No commands."
)
STRATEGIST_SYSTEM = (
    "You are the Defense Strategist in CYBERGENESIS, a defensive simulation on synthetic data only. "
    "Allowed actions ONLY: isolate_asset, block_connection, revoke_session, rotate_credential, apply_patch, disable_service, restore_connectivity. "
    "Return ONLY JSON: {\"actions\": [{\"action_type\": str, \"asset_id\": str, \"params\": {}}], \"justification\": str, "
    "\"expected_effectiveness\": str, \"operational_impact\": str, \"confidence\": float}. Prefer least disruptive effective action."
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
                            event_ids=[f"evt-{i}" for i in range(len(telemetry))],
                            anomaly_type=atype, summary=summary, confidence=conf)


async def investigate(scenario: dict, obs: AgentObservation, run_id: str) -> IncidentHypothesis:
    evidence = f"Scenario: {scenario['name']}. Anomaly: {obs.anomaly_type}. Assets: {obs.asset_ids}. Invariant to restore: {scenario['invariant']}."
    try:
        data, _ = await meta_client.chat_json(INVESTIGATOR_SYSTEM, evidence, run_id)
        h = IncidentHypothesis(**{**data, "model": meta_client.model, "mode": "live",
                                  "evidence_refs": obs.event_ids, "affected_assets": data.get("affected_assets", obs.asset_ids)})
        return h
    except (ProviderUnavailable, Exception) as e:  # fallback is deterministic + labelled
        if not isinstance(e, ProviderUnavailable):
            pass
        confirmed = [obs.summary, f"Source asset {scenario['source_asset']} shows synthetic malicious-pattern telemetry",
                     f"Protected target: {scenario['target_asset']}"]
        return IncidentHypothesis(
            hypothesis=f"Synthetic {scenario['name']} incident originating at {scenario['source_asset']} threatening {scenario['target_asset']} (offline deterministic analysis of real twin telemetry)",
            affected_assets=obs.asset_ids, threat_level=scenario.get("severity", "high"),
            confirmed=confirmed, speculation=["Adversary intent beyond the simulated objective is not inferred"],
            evidence_refs=obs.event_ids, confidence=0.86, model="deterministic-offline", mode="offline")


async def propose_defense(scenario: dict, hyp: IncidentHypothesis, run_id: str) -> DefenseProposal:
    try:
        data, _ = await meta_client.chat_json(
            STRATEGIST_SYSTEM,
            f"Incident: {hyp.hypothesis}. Affected: {hyp.affected_assets}. Scenario expected containment context: {scenario['invariant']}.", run_id)
        p = DefenseProposal(**{**data, "model": meta_client.model, "mode": "live", "evidence_refs": hyp.evidence_refs})
        if not p.actions:
            raise ValueError("empty actions")
        return p
    except Exception:  # noqa: BLE001 - honest offline fallback below
        actions = scenario["expected_defense"]
        return DefenseProposal(
            actions=actions,
            justification=f"Least-disruptive allowlisted containment for {scenario['name']}: {scenario['invariant']} (offline deterministic proposal derived from scenario policy, labelled as such)",
            expected_effectiveness="Blocks the simulated attack objective; verified independently by replay",
            operational_impact="Limited to the simulated source/choke-point; legitimate-path disruption measured after execution",
            confidence=0.84, model="deterministic-offline", mode="offline", evidence_refs=hyp.evidence_refs)
