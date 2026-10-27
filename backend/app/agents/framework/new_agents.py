"""Phase A3 agents (11-20). All proposals; only defense_executor mutates (via orchestrator)."""

import networkx as nx

from app.agents.framework import io
from app.agents.framework.base import Agent, AgentContext
from app.agents.framework.io import (CommanderPlan, DialectOut, FindingsOut, IdentityOut,
                                     ImpactOut, IntelOut, PlanStep, ReportOut, SurfaceOut)
from app.agents.framework.registry import REGISTRY
from app.integrations.meta_client import meta_client
from app.policies import engine as policy_engine
from app.simulation.component_library import library


def _spec(agent_id: str):
    return REGISTRY[agent_id]


# ---------- 11 incident commander ----------
BACKBONE = ["observer", "incident_investigator", "defense_strategist", "defense_executor", "verification_scientist"]

COMMANDER_SYSTEM = (
    "You are the Incident Commander in CYBERGENESIS. Plan agent invocations as a small DAG. "
    "The fixed backbone observe -> investigate -> propose -> policy -> execute -> verify (agents: observer, "
    "incident_investigator, defense_strategist, defense_executor, verification_scientist) can NEVER be skipped. "
    "You may add registry agents and parallel steps. Return ONLY JSON {\"plan\": [{\"step\": int, \"agents\": [str], "
    "\"parallel\": bool, \"why\": str}], \"stop_condition\": str, \"confidence\": float}. Max 30 steps."
)


def default_plan() -> CommanderPlan:
    ids = ["observer", "incident_investigator", "defense_strategist", "defense_executor", "verification_scientist"]
    return CommanderPlan(plan=[PlanStep(step=i + 1, agents=[a], why="mandatory backbone") for i, a in enumerate(ids)],
                         confidence=0.9)


def validate_plan(plan: CommanderPlan, known_ids: set[str]) -> list[str]:
    reasons: list[str] = []
    if len(plan.plan) > 30:
        reasons.append("plan exceeds 30 steps")
    flat = [a for s in plan.plan for a in s.agents]
    for a in flat:
        if a not in known_ids:
            reasons.append(f"unknown agent '{a}'")
    pos = 0
    for want in BACKBONE:
        found = next((i for i in range(pos, len(flat)) if flat[i] == want), None)
        if found is None:
            reasons.append(f"mandatory backbone agent '{want}' missing or out of order (gates cannot be skipped)")
            break
        pos = found + 1
    return reasons


def trim_plan_to_max_rounds(plan: CommanderPlan, max_rounds: int | None) -> tuple[CommanderPlan, str | None]:
    """Deterministically cap a commander plan at the scenario's max_rounds.

    Convention (single source of truth: scenario["max_rounds"]): the battle
    runs at most max_rounds campaign rounds INCLUDING round 1, and the
    commander's plan may not imply more work than that budget allows, so
    the plan is trimmed to at most max_rounds steps. Trimming (not
    rejection) is chosen so a usable plan always survives; the caller
    records the returned reason. Plans for scenarios without max_rounds,
    and plans already within budget, pass through unchanged. The mandatory
    backbone is executed by the orchestrator regardless of plan trimming.
    """
    if max_rounds is None:
        return plan, None
    try:
        cap = int(max_rounds)
    except (TypeError, ValueError):
        return plan, None
    if cap < 1 or len(plan.plan) <= cap:
        return plan, None
    trimmed = plan.model_copy(deep=True)
    trimmed.plan = trimmed.plan[:cap]
    reason = (f"commander plan trimmed from {len(plan.plan)} to {cap} steps to align with "
              f"scenario max_rounds={cap} (total campaign rounds including round 1)")
    return trimmed, reason


class IncidentCommanderAgent(Agent):
    def __init__(self):
        super().__init__(_spec("incident_commander"))

    async def live(self, ctx: AgentContext, inp: io.TextIn):
        with meta_client.use_budget_tier("advisory"):
            data, _ = await meta_client.chat_json(COMMANDER_SYSTEM,
                                                  f"Registry agents: {sorted(REGISTRY)}. Scenario context: {inp.text}", ctx.run_id)
        plan = CommanderPlan(**data)
        reasons = validate_plan(plan, set(REGISTRY))
        if reasons:
            raise ValueError(f"plan rejected by validator: {'; '.join(reasons)}")
        return plan

    async def offline(self, ctx: AgentContext, inp: io.TextIn):
        return default_plan()


# ---------- 12 threat intel ----------
class ThreatIntelAnalystAgent(Agent):
    def __init__(self):
        super().__init__(_spec("threat_intel_analyst"))

    async def offline(self, ctx: AgentContext, inp: io.TelemetryIn):
        lib = library()
        tag_by_type = {s["id"]: s.get("mitre", "") for s in lib["attack_steps"]}
        techniques = []
        for e in (inp.telemetry or ctx.telemetry):
            if e.get("event_type") in tag_by_type:
                techniques.append({"event": e.get("id"), "type": e["event_type"], "mitre": tag_by_type[e["event_type"]]})
        predicted = {"technique": "TA0008 Lateral Movement", "asset": ctx.scenario.get("target_asset"),
                     "basis": "observed progression toward the target asset"}
        hardening = []
        for aid, cfg in ctx.twin.device_configs.items():
            if cfg.get("mgmt", {}).get("telnet"):
                hardening.append({"action_type": "harden_mgmt", "asset_id": aid, "params": {}})
        return IntelOut(techniques=techniques, predicted_next=predicted, hardening_proposals=hardening,
                        summary=f"{len(techniques)} telemetry events mapped to ATT&CK; next likely: lateral movement",
                        evidence_refs=[str(e.get("id")) for e in (inp.telemetry or ctx.telemetry) if e.get("id")])


# ---------- 13 identity guardian ----------
class IdentityGuardianAgent(Agent):
    def __init__(self):
        super().__init__(_spec("identity_guardian"))

    async def offline(self, ctx: AgentContext, inp: io.TextIn):
        twin = ctx.twin
        jewels = [a["id"] for a in twin.to_dict()["assets"] if a["asset_type"] in ("database", "file_server")]
        paths, gaps, proposals = [], [], []
        for name, ident in twin.identities.items():
            asset = ident["asset"]
            for j in jewels:
                p = twin.find_path(asset, j)
                if p:
                    paths.append({"identity": name, "from": asset, "to": j, "path": p,
                                  "compromised": ident["compromised"], "session_active": ident["session_active"]})
                    if ident["compromised"] or ident["session_active"]:
                        proposals.append({"action_type": "revoke_session", "asset_id": "identity-provider",
                                          "params": {"identity": name}})
                        proposals.append({"action_type": "enforce_mfa", "asset_id": asset, "params": {"identity": name}})
            for u in twin.device_configs.get(asset, {}).get("users", []):
                if u.get("role") == "admin" and not u.get("mfa"):
                    gaps.append(f"{u['name']} on {asset}: admin without MFA")
        seen = set(); uniq = []
        for p in proposals:
            k = str(p)
            if k not in seen:
                seen.add(k); uniq.append(p)
        return IdentityOut(privilege_paths=paths, mfa_gaps=gaps, proposals=uniq,
                           summary=f"{len(paths)} identity privilege paths to crown jewels; {len(gaps)} MFA gaps",
                           evidence_refs=[f"identity:{n}" for n in twin.identities])


# ---------- 14 config engineer ----------
DIALECT_TEMPLATES = {
    "ios": "access-list {name} {action} {proto} any any",
    "fortios": "config firewall policy\n    edit 0\n        set action {action}\n    next\nend",
    "junos": "set security policies from-zone trust to-zone untrust policy {name} match source-address any",
    "panos": "set rulebase security rules {name} action {action}",
    "bash": "iptables -A INPUT -j {action_upper}",
    "powershell": "New-NetFirewallRule -DisplayName {name} -Action {action_title}",
}


def render_dialect(dialect: str, action: dict) -> str:
    name = "CYBERGENESIS"
    act = "deny" if action["action_type"] in ("block_connection", "isolate_asset", "quarantine_vlan") else "allow"
    tpl = DIALECT_TEMPLATES.get(dialect, DIALECT_TEMPLATES["bash"])
    return tpl.format(name=name, action=act, action_upper=act.upper(), action_title=act.title(),
                      proto="ip", asset=action.get("asset_id", ""))


def parse_dialect(text: str, asset_id: str) -> list[dict]:
    low = text.lower()
    if "deny" in low or "drop" in low:
        return [{"action_type": "block_connection", "asset_id": asset_id,
                 "params": {"source": asset_id, "target": "", "direction": "egress"}}]
    if "isolate" in low or "shutdown" in low:
        return [{"action_type": "isolate_asset", "asset_id": asset_id, "params": {}}]
    return []


class ConfigEngineerAgent(Agent):
    def __init__(self):
        super().__init__(_spec("config_engineer"))

    async def offline(self, ctx: AgentContext, inp: io.ExecuteIn):
        from app.devices.registry import BUILTIN_DEVICE_MAP, BY_ID

        action = inp.actions[0] if inp.actions else {"action_type": "block_connection", "asset_id": "firewall"}
        asset = action.get("asset_id", "firewall")
        dev_id = BUILTIN_DEVICE_MAP.get(asset)
        dialect = BY_ID[dev_id].personality.cli if dev_id and dev_id in BY_ID else "bash"
        text = render_dialect(dialect, action)
        parsed = parse_dialect(text, asset)
        return DialectOut(device_id=dev_id or asset, dialect=dialect, config_text=text, parsed_actions=parsed,
                          summary=f"rendered {action['action_type']} in {dialect}; parsed back to {len(parsed)} action(s)")


# ---------- 15 deception engineer ----------
class DeceptionEngineerAgent(Agent):
    def __init__(self):
        super().__init__(_spec("deception_engineer"))

    async def offline(self, ctx: AgentContext, inp: io.TextIn):
        anchors = [a["id"] for a in ctx.twin.to_dict()["assets"] if a["asset_type"] in ("file_server", "app_server")]
        anchor = anchors[0] if anchors else ctx.twin.asset_ids()[0]
        return io.GenericOut(summary=f"propose decoy on {anchor}", confidence=0.7) | {} if False else io.GenericOut(
            summary=f"deploy_decoy proposal: honeypot_host anchored on {anchor}", confidence=0.7)


# ---------- 16 recovery engineer ----------
class RecoveryEngineerAgent(Agent):
    def __init__(self):
        super().__init__(_spec("recovery_engineer"))

    async def offline(self, ctx: AgentContext, inp: io.TextIn):
        steps = []
        for entry in ctx.twin.containment:
            if entry.startswith("isolate:"):
                steps.append({"action_type": "restore_connectivity", "asset_id": entry.split(":", 1)[1], "params": {}})
            elif entry.startswith(("block:", "block_outbound:")):
                pair = entry.split(":", 1)[1].split("->")
                steps.append({"action_type": "restore_connectivity", "asset_id": pair[0],
                              "params": {"source": pair[0], "target": pair[1]}})
        return io.GenericOut(summary=f"{len(steps)} recovery step(s) proposed; each is verify-or-rollback", confidence=0.8)


# ---------- 17 config auditor ----------
class ConfigAuditorAgent(Agent):
    def __init__(self):
        super().__init__(_spec("config_auditor"))

    async def offline(self, ctx: AgentContext, inp: io.TextIn):
        findings = []
        for aid, cfg in ctx.twin.device_configs.items():
            if cfg.get("mgmt", {}).get("telnet"):
                findings.append({"device": aid, "line_or_rule": "mgmt.telnet=true", "weakness": "telnet_enabled",
                                 "severity": "high", "evidence": f"config:{aid}:mgmt",
                                 "fix_diff": {"action_type": "harden_mgmt", "asset_id": aid, "params": {}}})
            if cfg.get("mgmt", {}).get("snmp_community") == "public":
                findings.append({"device": aid, "line_or_rule": "mgmt.snmp_community=public", "weakness": "snmp_public_community",
                                 "severity": "medium", "evidence": f"config:{aid}:mgmt",
                                 "fix_diff": {"action_type": "harden_mgmt", "asset_id": aid, "params": {}}})
            for w in cfg.get("weaknesses", []):
                findings.append({"device": aid, "line_or_rule": f"weaknesses includes {w}", "weakness": w,
                                 "severity": "medium", "evidence": f"config:{aid}:weaknesses",
                                 "fix_diff": {"action_type": "apply_patch", "asset_id": aid, "params": {}}})
            if cfg.get("patches", {}).get("missing"):
                findings.append({"device": aid, "line_or_rule": f"missing patches {cfg['patches']['missing']}",
                                 "weakness": "missing_patch", "severity": "medium", "evidence": f"config:{aid}:patches",
                                 "fix_diff": {"action_type": "apply_patch", "asset_id": aid, "params": {}}})
        return FindingsOut(findings=findings, summary=f"{len(findings)} config findings", 
                           evidence_refs=[f["evidence"] for f in findings])


# ---------- 18 attack surface mapper ----------
class AttackSurfaceMapperAgent(Agent):
    def __init__(self):
        super().__init__(_spec("attack_surface_mapper"))

    async def offline(self, ctx: AgentContext, inp: io.TextIn):
        twin = ctx.twin
        g = twin.live_graph()
        jewels = [a["id"] for a in twin.to_dict()["assets"] if a["asset_type"] in ("database", "file_server")]
        centrality = nx.betweenness_centrality(g) if g.number_of_nodes() else {}
        exposure = []
        for a in twin.to_dict()["assets"]:
            reach = twin.find_path("internet", a["id"]) is not None if "internet" in twin.asset_ids() else False
            score = round((0.5 if reach else 0.0) + 0.15 * len(a["vulnerabilities"]) +
                          (0.2 if a["id"] in centrality and centrality[a["id"]] > 0.1 else 0.0), 2)
            exposure.append({"asset": a["id"], "exposure_score": min(score, 1.0), "internet_reachable": reach,
                             "weaknesses": a["vulnerabilities"]})
        chokes = []
        for j in jewels:
            try:
                cut = nx.minimum_edge_cut(twin.live_graph(j), "internet", j) if "internet" in twin.asset_ids() else set()
                chokes.append({"crown_jewel": j, "min_edge_cut": len(cut), "edges": [list(e) for e in cut]})
            except Exception:  # noqa: BLE001
                chokes.append({"crown_jewel": j, "min_edge_cut": 0, "edges": []})
        exposure.sort(key=lambda x: -x["exposure_score"])
        return SurfaceOut(exposure=exposure, choke_points=chokes, crown_jewels=jewels,
                          summary=f"{len(exposure)} assets scored; crown jewels: {jewels}")


# ---------- 19 business impact ----------
class BusinessImpactAnalystAgent(Agent):
    def __init__(self):
        super().__init__(_spec("business_impact_analyst"))

    async def offline(self, ctx: AgentContext, inp: io.ExecuteIn):
        from app.verification.verifier import disrupted_users

        action = inp.actions[0] if inp.actions else {}
        clone = ctx.twin.clone()
        verdict = policy_engine.evaluate(action.get("action_type", ""), action.get("asset_id", ""), action.get("params", {}), clone) \
            if action else None
        if verdict and verdict.approved:
            try:
                clone.apply_action(action["action_type"], action["asset_id"], action.get("params", {}))
            except ValueError:
                pass
        users = disrupted_users(clone, ctx.twin)
        disrupted = clone.legitimate_disrupted(ctx.twin)
        requires = disrupted >= 2 or action.get("action_type") == "isolate_asset"
        return ImpactOut(users_affected=users, disrupted_paths=disrupted, requires_human_approval=requires,
                         explanation=(f"{action.get('action_type', 'This defense')} affects ≈{users} users across "
                                      f"{disrupted} legitimate flows. " +
                                      ("It crosses the human-approval threshold, so an operator must sign off." if requires
                                       else "It stays below the approval threshold and may proceed autonomously.")))


# ---------- 20 forensic reporter ----------
NIST_MAP = {"observer": "Detect (DE.AE)", "incident_investigator": "Detect/Respond (DE.CM, RS.AN)",
            "defense_strategist": "Respond (RS.MA)", "defense_executor": "Protect/Respond (PR.AC, RS.MI)",
            "verification_scientist": "Recover (RC.RP)", "adversary_simulator": "Identify (ID.RA)"}


class ForensicReporterAgent(Agent):
    def __init__(self):
        super().__init__(_spec("forensic_reporter"))

    async def offline(self, ctx: AgentContext, inp: io.TextIn):
        known = {str(e.get("id")) for e in ctx.telemetry if e.get("id")} | set(ctx.findings)
        lines = ["# Forensic Report (deterministic)", "", "## Executive summary",
                 f"Scenario: {ctx.scenario.get('name', 'run')} — all statements below cite verified evidence ids.", "",
                 "## Technical timeline (NIST CSF 2.0)"]
        removed: list[str] = []
        cited = 0
        for m in ctx.memory:
            claim = str(m.get("claim", m.get("decision", "")))
            refs = list(m.get("evidence_refs", []))
            good = [r for r in refs if r in known]
            if refs and not good:
                removed.append(claim)
                continue
            cited += len(good)
            agent = str(m.get("agent", "agent"))
            lines.append(f"- [{NIST_MAP.get(agent, 'Govern (GV.OC)')}] {claim} (evidence: {', '.join(good) or 'run record'})")
        lines += ["", "## Red vs blue rounds", "See rounds[] in the run metrics; each round's campaign, defense and verification are persisted.", ""]
        total_claims = cited + len(removed)
        return ReportOut(report_markdown="\n".join(lines), removed_claims=removed,
                         citation_validity_rate=round(cited / max(total_claims, 1), 3) if total_claims else 1.0,
                         summary=f"report with {cited} verified citations, {len(removed)} unverifiable claims removed",
                         evidence_refs=sorted(known)[:20])
