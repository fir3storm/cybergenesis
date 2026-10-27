"""Adapters: the 10 existing agents ported onto the framework (same ids, same behaviour).

live() raises when the underlying role fell back internally, so the base class —
not the role — owns the live/offline label and the fallback_reason.
"""

from app.agents import agents, red_team
from app.agents.framework import io
from app.agents.framework.base import Agent, AgentContext
from app.agents.framework.registry import REGISTRY
from app.policies import engine as policy_engine
from app.schemas import AttackScenarioPlan, DefenseExecutionResult
from app.verification.verifier import verify as run_verify


def _spec(agent_id: str):
    return REGISTRY[agent_id]


class ObserverAgent(Agent):
    def __init__(self):
        super().__init__(_spec("observer"))

    async def offline(self, ctx: AgentContext, inp: io.TelemetryIn):
        return agents.observe(inp.telemetry or ctx.telemetry)


class AdversarySimulatorAgent(Agent):
    def __init__(self):
        super().__init__(_spec("adversary_simulator"))

    async def offline(self, ctx: AgentContext, inp: io.ScenarioIn):
        sc = inp.scenario or ctx.scenario
        return AttackScenarioPlan(scenario_id=sc.get("id", ""), steps=sc.get("attack_steps", []), seed=inp.seed)


class IncidentInvestigatorAgent(Agent):
    def __init__(self):
        super().__init__(_spec("incident_investigator"))

    async def live(self, ctx: AgentContext, inp: io.InvestigateIn):
        obs = agents.observe(inp.telemetry or ctx.telemetry)
        res = await agents.investigate(inp.scenario or ctx.scenario, obs, ctx.run_id,
                                       telemetry=inp.telemetry or ctx.telemetry, twin=ctx.twin)
        if res.mode != "live":
            raise RuntimeError(res.fallback_reason or "provider unavailable")
        return res

    async def offline(self, ctx: AgentContext, inp: io.InvestigateIn):
        obs = agents.observe(inp.telemetry or ctx.telemetry)
        return await agents.investigate(inp.scenario or ctx.scenario, obs, ctx.run_id,
                                        telemetry=inp.telemetry or ctx.telemetry, twin=ctx.twin)


class DefenseStrategistAgent(Agent):
    def __init__(self):
        super().__init__(_spec("defense_strategist"))

    async def live(self, ctx: AgentContext, inp: io.ProposeIn):
        from app.schemas import IncidentHypothesis

        hyp = IncidentHypothesis(**inp.hypothesis) if inp.hypothesis else IncidentHypothesis(hypothesis="incident")
        res = await agents.propose_defense(inp.scenario or ctx.scenario, hyp, ctx.run_id, twin=ctx.twin)
        if res.mode != "live":
            raise RuntimeError(res.fallback_reason or "provider unavailable")
        return res

    async def offline(self, ctx: AgentContext, inp: io.ProposeIn):
        from app.schemas import IncidentHypothesis

        hyp = IncidentHypothesis(**inp.hypothesis) if inp.hypothesis else IncidentHypothesis(hypothesis="incident")
        return await agents.propose_defense(inp.scenario or ctx.scenario, hyp, ctx.run_id, twin=ctx.twin)


class DefenseExecutorAgent(Agent):
    """The ONLY agent that mutates the twin — and only through the policy engine."""

    def __init__(self):
        super().__init__(_spec("defense_executor"))

    async def offline(self, ctx: AgentContext, inp: io.ExecuteIn):
        results = []
        for a in inp.actions:
            d = policy_engine.evaluate(a["action_type"], a["asset_id"], a.get("params", {}), ctx.twin)
            if not d.approved:
                results.append(DefenseExecutionResult(action_type=a["action_type"], asset_id=a["asset_id"],
                                                      success=False, transition={}, message=f"policy rejected: {'; '.join(d.reasons)}"))
                continue
            try:
                tr = ctx.twin.apply_action(a["action_type"], a["asset_id"], a.get("params", {}))
                results.append(DefenseExecutionResult(action_type=a["action_type"], asset_id=a["asset_id"],
                                                      success=True, transition=tr, message="applied via policy gate"))
            except ValueError as e:
                results.append(DefenseExecutionResult(action_type=a["action_type"], asset_id=a["asset_id"],
                                                      success=False, transition={}, message=str(e)))
        return results[0] if results else DefenseExecutionResult(action_type="none", asset_id="", success=False, message="no actions")


class VerificationScientistAgent(Agent):
    def __init__(self):
        super().__init__(_spec("verification_scientist"))

    async def offline(self, ctx: AgentContext, inp: io.VerifyIn):
        sc = inp.scenario or ctx.scenario
        return run_verify(sc, ctx.baseline_twin or ctx.twin, ctx.twin,
                          inp.baseline_result or {"objective_blocked": False}, 0.0, 0.4, 0.8)


class RedTeamPlannerAgent(Agent):
    def __init__(self):
        super().__init__(_spec("red_team_planner"))

    async def live(self, ctx: AgentContext, inp: io.CampaignIn):
        plan = await red_team.plan_campaign(ctx.twin, inp.source_asset, inp.target_asset, ctx.run_id)
        if plan is None:
            raise RuntimeError("no valid campaign exists")
        if plan.mode != "live":
            raise RuntimeError("deterministic campaign (provider unavailable or single path)")
        return plan

    async def offline(self, ctx: AgentContext, inp: io.CampaignIn):
        plan = await red_team.plan_campaign(ctx.twin, inp.source_asset, inp.target_asset, ctx.run_id)
        if plan is None:
            from app.schemas import CampaignPlan

            return CampaignPlan(foothold=inp.source_asset, objective=inp.target_asset, steps=[],
                                rationale="attack surface closed: no valid campaign", confidence=0.9, mode="offline")
        return plan


class RedTeamCriticAgent(Agent):
    def __init__(self):
        super().__init__(_spec("red_team_critic"))

    async def live(self, ctx: AgentContext, inp: io.CriticIn):
        from app.simulation.scenarios import SCENARIOS

        sc = ctx.scenario or SCENARIOS.get("ransomware_activity", {})
        res = await agents.criticize_defense(sc, inp.defense_label, inp.alternate_paths, ctx.run_id)
        if res["mode"] != "live":
            raise RuntimeError("deterministic critic")
        return io.GenericOut(summary=res["assessment"], confidence=0.75)

    async def offline(self, ctx: AgentContext, inp: io.CriticIn):
        from app.simulation.scenarios import SCENARIOS

        sc = ctx.scenario or SCENARIOS.get("ransomware_activity", {})
        res = await agents.criticize_defense(sc, inp.defense_label, inp.alternate_paths, ctx.run_id)
        return io.GenericOut(summary=res["assessment"], confidence=0.75)


class ScenarioAuthorAgent(Agent):
    def __init__(self):
        super().__init__(_spec("scenario_author"))

    async def live(self, ctx: AgentContext, inp: io.TextIn):
        from app.agents.generative import author_scenario

        row = await author_scenario(inp.text, "AI Scenario", [a["id"] for a in ctx.twin.to_dict()["assets"]])
        return io.GenericOut(summary=f"scenario created: {row['name']}", confidence=0.8)

    async def offline(self, ctx: AgentContext, inp: io.TextIn):
        return io.GenericOut(summary="text-to-scenario requires live Meta AI; no scenario was created offline",
                             confidence=0.0)


class TwinArchitectAgent(Agent):
    def __init__(self):
        super().__init__(_spec("twin_architect"))

    async def live(self, ctx: AgentContext, inp: io.TextIn):
        from app.agents.generative import architect_twin

        twin_def = await architect_twin(inp.text, "Photo Twin")
        return io.GenericOut(summary=f"twin generated: {len(twin_def.assets)} assets, {len(twin_def.connections)} connections",
                             confidence=0.8)

    async def offline(self, ctx: AgentContext, inp: io.TextIn):
        return io.GenericOut(summary="image-to-twin requires live Meta AI vision; nothing was generated offline",
                             confidence=0.0)


from app.agents.framework.new_agents import (AttackSurfaceMapperAgent, BusinessImpactAnalystAgent,  # noqa: E402
                                             ConfigAuditorAgent, ConfigEngineerAgent, DeceptionEngineerAgent,
                                             ForensicReporterAgent, IdentityGuardianAgent, IncidentCommanderAgent,
                                             RecoveryEngineerAgent, ThreatIntelAnalystAgent)

AGENT_CLASSES = {
    "observer": ObserverAgent, "adversary_simulator": AdversarySimulatorAgent,
    "incident_investigator": IncidentInvestigatorAgent, "defense_strategist": DefenseStrategistAgent,
    "defense_executor": DefenseExecutorAgent, "verification_scientist": VerificationScientistAgent,
    "red_team_planner": RedTeamPlannerAgent, "red_team_critic": RedTeamCriticAgent,
    "scenario_author": ScenarioAuthorAgent, "twin_architect": TwinArchitectAgent,
    "incident_commander": IncidentCommanderAgent, "threat_intel_analyst": ThreatIntelAnalystAgent,
    "identity_guardian": IdentityGuardianAgent, "config_engineer": ConfigEngineerAgent,
    "deception_engineer": DeceptionEngineerAgent, "recovery_engineer": RecoveryEngineerAgent,
    "config_auditor": ConfigAuditorAgent, "attack_surface_mapper": AttackSurfaceMapperAgent,
    "business_impact_analyst": BusinessImpactAnalystAgent, "forensic_reporter": ForensicReporterAgent,
}


def build_agent(agent_id: str) -> Agent:
    return AGENT_CLASSES[agent_id]()
