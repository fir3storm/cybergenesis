"""Deterministic policy engine — independent of the LLM."""

from app.schemas import PolicyDecision
from app.simulation.twin import ALLOWED_ACTIONS, ATTACK_STEP_TYPES, DigitalTwin


def evaluate_campaign(campaign: dict, twin: DigitalTwin) -> dict:
    """Validate a red-team campaign. Approved only if every step is allowlisted,
    every asset exists, and every hop follows an active traversable arc — or is
    covered by a compromised/session-active synthetic identity pivot."""
    reasons: list[str] = []
    steps = campaign.get("steps", [])
    if not steps:
        return {"approved": False, "reasons": ["campaign has no steps"], "path": []}
    graph = twin.live_graph(campaign.get("objective"))
    assets = set(twin.asset_ids())
    seq: list[str] = []
    for st in steps:
        if st.get("type") not in ATTACK_STEP_TYPES:
            reasons.append(f"step type '{st.get('type')}' not in ATTACK_STEP_TYPES allowlist")
        if st.get("asset") not in assets:
            reasons.append(f"step asset '{st.get('asset')}' does not exist in twin")
        if st.get("asset") not in seq:
            seq.append(st.get("asset"))
    pivot = campaign.get("pivot_identity")
    pivot_ok = bool(pivot and pivot in twin.identities
                    and (twin.identities[pivot]["compromised"] or twin.identities[pivot]["session_active"]))
    if pivot and not pivot_ok:
        reasons.append(f"pivot identity '{pivot}' is not compromised/session-active")
    for i in range(len(seq) - 1):
        a, b = seq[i], seq[i + 1]
        if graph.has_edge(a, b):
            continue
        if pivot_ok and (a in ("identity-provider", "admin-workstation") or b in ("database", "identity-provider", "admin-workstation")):
            continue  # identity pivot: IdP/workstation -> protected asset with a live synthetic identity
        reasons.append(f"hop {a} -> {b} is not an active traversable arc")
    if campaign.get("foothold") not in assets:
        reasons.append("foothold does not exist")
    if campaign.get("objective") not in assets:
        reasons.append("objective does not exist")
    approved = not reasons
    if approved:
        reasons.append("all steps allowlisted, assets exist, hops graph-valid (or identity-pivot covered)")
    return {"approved": approved, "reasons": reasons, "path": seq}


# assets that may never be isolated (would break the twin's core)
NEVER_ISOLATE = {"firewall", "database", "internet", "security-sensor"}
PATCHABLE = {"web-server", "app-server", "employee-workstation", "admin-workstation", "file-server"}
SERVICE_DISABLEABLE = {"web-server", "app-server"}
QUARANTINABLE = PATCHABLE | {"database", "identity-provider"}


def evaluate(action_type: str, asset_id: str, params: dict, twin: DigitalTwin) -> PolicyDecision:
    reasons: list[str] = []
    approved = True
    if action_type not in ALLOWED_ACTIONS:
        approved = False; reasons.append(f"action '{action_type}' is not in the allowlist")
    if asset_id not in twin.asset_ids():
        approved = False; reasons.append(f"asset '{asset_id}' does not exist in the twin")
        return PolicyDecision(action_type=action_type, asset_id=asset_id, approved=False, reasons=reasons)
    if action_type == "isolate_asset" and asset_id in NEVER_ISOLATE:
        approved = False; reasons.append(f"isolating core asset '{asset_id}' is prohibited")
    if action_type == "isolate_asset" and twin.isolated[asset_id]:
        approved = False; reasons.append("asset already isolated")
    if action_type == "apply_patch" and asset_id not in PATCHABLE:
        approved = False; reasons.append(f"apply_patch not permitted on '{asset_id}'")
    if action_type == "disable_service" and asset_id not in SERVICE_DISABLEABLE:
        approved = False; reasons.append(f"disable_service not permitted on '{asset_id}'")
    if action_type == "block_connection":
        s, t = params.get("source", asset_id), params.get("target")
        if not t or not (twin.graph.has_edge(s, t) or twin.graph.has_edge(t, s)):
            approved = False; reasons.append("connection does not exist")
        elif params.get("direction") in ("outbound", "egress"):
            if not twin.dir_active.get((s, t), False):
                approved = False; reasons.append("egress direction already blocked")
        elif params.get("direction") == "ingress":
            if not twin.dir_active.get((t, s), False):
                approved = False; reasons.append("ingress direction already blocked")
        elif params.get("direction", "both") not in ("both",):
            approved = False; reasons.append(f"unknown direction '{params.get('direction')}' (use both|egress|ingress)")
        elif not (twin.dir_active.get((s, t), False) or twin.dir_active.get((t, s), False)):
            approved = False; reasons.append("connection already blocked")
    if action_type in ("revoke_session", "rotate_credential") and asset_id not in ("identity-provider", "admin-workstation", "employee-workstation"):
        approved = False; reasons.append(f"{action_type} only permitted on identity/workstation assets")
    if action_type == "quarantine_vlan" and asset_id in NEVER_ISOLATE:
        approved = False; reasons.append(f"quarantining core asset '{asset_id}' is prohibited")
    if action_type == "kill_process" and twin.status.get(asset_id) not in ("compromised", "suspicious", "contained"):
        approved = False; reasons.append("kill_process requires a suspicious/compromised asset")
    if action_type == "restore_snapshot" and asset_id in NEVER_ISOLATE:
        approved = False; reasons.append("snapshot restore not permitted on core assets")
    if approved:
        reasons.append("allowlisted action, asset in simulation boundary, preconditions satisfied")
    human = approved and action_type == "isolate_asset"
    if human:
        reasons.append("high-impact action: human approval required when estimated disruption is high")
    return PolicyDecision(action_type=action_type, asset_id=asset_id, approved=approved, reasons=reasons,
                          requires_human_approval=human)
