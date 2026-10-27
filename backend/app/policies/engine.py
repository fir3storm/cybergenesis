"""Deterministic policy engine — independent of the LLM."""

from app.schemas import PolicyDecision
from app.simulation.twin import ALLOWED_ACTIONS, DigitalTwin

# assets that may never be isolated (would break the twin's core)
NEVER_ISOLATE = {"firewall", "database", "internet", "security-sensor"}
PATCHABLE = {"web-server", "app-server", "employee-workstation", "admin-workstation", "file-server"}
SERVICE_DISABLEABLE = {"web-server", "app-server"}


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
        elif params.get("direction") == "outbound":
            if not twin.dir_active.get((s, t), False):
                approved = False; reasons.append("outbound direction already blocked")
        elif not (twin.dir_active.get((s, t), False) or twin.dir_active.get((t, s), False)):
            approved = False; reasons.append("connection already blocked")
    if action_type in ("revoke_session", "rotate_credential") and asset_id not in ("identity-provider", "admin-workstation", "employee-workstation"):
        approved = False; reasons.append(f"{action_type} only permitted on identity/workstation assets")
    if approved:
        reasons.append("allowlisted action, asset in simulation boundary, preconditions satisfied")
    human = approved and action_type == "isolate_asset"
    if human:
        reasons.append("high-impact action: human approval required when estimated disruption is high")
    return PolicyDecision(action_type=action_type, asset_id=asset_id, approved=approved, reasons=reasons,
                          requires_human_approval=human)
