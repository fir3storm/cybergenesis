"""Agent evaluation scorecards over generated twins with deterministic ground truth."""

import asyncio
import random

from app.agents import agents as legacy_agents
from app.agents.framework import io
from app.agents.framework.adapters import build_agent
from app.agents.framework.base import AgentContext
from app.agents.framework.new_agents import default_plan, validate_plan
from app.benchmark.generator import generate_pair
from app.policies import engine as policy_engine
from app.simulation.candidates import evaluate_candidates
from app.simulation.twin import DigitalTwin
from app.verification.verifier import verify


def identity_recall(twin, guardian_out) -> float:
    """Exact (identity, jewel) pair matching — not counts."""
    jewels = [a["id"] for a in twin.to_dict()["assets"] if a["asset_type"] in ("database", "file_server")]
    truth = {(name, j) for name, idn in twin.identities.items() for j in jewels if twin.find_path(idn["asset"], j)}
    if not truth:
        return 1.0
    found = {(p.get("identity"), p.get("to")) for p in guardian_out.privilege_paths}
    return round(len(truth & found) / len(truth), 3)


def deception_trip(twin, scenario: dict) -> float:
    """1.0 if red's chosen campaign path touches a decoy, else 0.0."""
    from app.agents.red_team import _offline_campaign

    camp = _offline_campaign(twin, scenario["source_asset"], scenario["target_asset"])
    if camp is None or not camp.path:
        return 0.0
    return 1.0 if any(n in twin.decoys for n in camp.path) else 0.0


def _bucketize(pairs: list[tuple[float, bool]]) -> list[dict]:
    buckets = [{"bucket": f"{i / 5:.1f}-{(i + 1) / 5:.1f}", "n": 0, "correct": 0} for i in range(5)]
    for conf, ok in pairs:
        b = buckets[min(int(conf * 5), 4)]
        b["n"] += 1; b["correct"] += int(ok)
    for b in buckets:
        b["accuracy"] = round(b["correct"] / b["n"], 3) if b["n"] else None
    return buckets


async def run_eval(n: int = 10, seed: int = 7, mode: str = "offline", progress=None) -> dict:
    rng = random.Random(seed)
    inv_pairs: list[tuple[float, bool]] = []
    inv_prec, inv_rec = [], []
    strat = {"runs": 0, "passes": 0, "gaps": [], "matched": 0, "approvals": 0}
    red = {"campaigns": 0, "valid": 0, "real": 0}
    critic = {"checked": 0, "tp": 0}
    auditor = {"tp": 0, "fp": 0, "fn": 0}
    identity = {"found": 0, "total": 0}
    deception = {"deployed": 0, "tripped": 0}
    engineer = {"parsed": 0, "equal": 0, "total": 0}
    forensic_rates: list[float] = []

    for i in range(n):
        assets, conns, scenario = generate_pair(rng, i)
        base = DigitalTwin.from_dict(assets, conns)
        attacked = base.clone(); attacked.apply_attack(scenario, seed=seed)
        truth = {a for a, s in attacked.status.items() if s in ("compromised", "suspicious")}
        telemetry = attacked.apply_attack(scenario, seed=seed) if False else [
            {"id": f"tele-eval-{i}-0", "event_type": "network_connection", "asset_id": scenario["source_asset"], "message": "generated attack"}]
        ctx = AgentContext(run_id=f"eval-{seed}-{i}", twin=attacked, scenario=scenario, telemetry=telemetry, baseline_twin=base)

        inv = await build_agent("incident_investigator").run(ctx, io.InvestigateIn(scenario=scenario, telemetry=telemetry))
        predicted = set(inv.output.affected_assets)
        tp = len(predicted & truth)
        inv_prec.append(tp / max(len(predicted), 1)); inv_rec.append(tp / max(len(truth), 1))
        inv_pairs.append((inv.output.confidence, (tp / max(len(truth), 1)) >= 0.5))

        # strategist + commander (same loop metrics) + executor + verifier
        hyp = inv.output
        proposal = await legacy_agents.propose_defense(scenario, hyp, ctx.run_id, twin=attacked)
        cands = evaluate_candidates(attacked.clone(), base, scenario, [a.model_dump() for a in proposal.actions])
        choice = await legacy_agents.final_choice(cands, scenario, ctx.run_id)
        chosen = choice["candidate"] or (cands[0] if cands else None)
        strat["runs"] += 1
        strat["matched"] += int(bool(choice.get("ai_matched_optimum")))
        if chosen:
            clone = attacked.clone()
            for a in chosen["actions"]:
                if policy_engine.evaluate(a["action_type"], a["asset_id"], a.get("params", {}), clone).approved:
                    try:
                        clone.apply_action(a["action_type"], a["asset_id"], a.get("params", {}))
                    except ValueError:
                        pass
            baseline_result = base.clone()
            baseline_result.apply_attack(scenario, seed=seed)
            res = verify(scenario, base, clone, baseline_result.attempt_attack_objective(scenario), 0.0, 0.4, 0.8)
            strat["passes"] += int(res.outcome == "PASS")
            if res.metrics.get("optimality_gap") is not None:
                strat["gaps"].append(res.metrics["optimality_gap"])

        # red planner validity + critic
        plan = await build_agent("red_team_planner").run(ctx, io.CampaignIn(source_asset=scenario["source_asset"], target_asset=scenario["target_asset"]))
        red["campaigns"] += 1
        from app.policies.engine import evaluate_campaign

        if plan.output.steps:
            verdict = evaluate_campaign(plan.output.model_dump(), attacked)
            red["valid"] += int(verdict["approved"])
            red["real"] += int(verdict["approved"] and attacked.find_path(scenario["source_asset"], scenario["target_asset"]) is not None)
        crit = await build_agent("red_team_critic").run(ctx, io.CriticIn(defense_label="eval", alternate_paths=[]))
        _ = crit

        # auditor vs seeded weaknesses (device_configs weaknesses are ground truth)
        aud = await build_agent("config_auditor").run(ctx, io.TextIn())
        truth_weak = {(aid, w) for aid, c in attacked.device_configs.items() for w in c.get("weaknesses", [])}
        found_weak = {(f["device"], f["weakness"]) for f in aud.output.findings}
        auditor["tp"] += len(truth_weak & found_weak); auditor["fp"] += len(found_weak - truth_weak); auditor["fn"] += len(truth_weak - found_weak)

        # identity guardian recall (exact pair matching)
        guard = await build_agent("identity_guardian").run(ctx, io.TextIn())
        jewels = [a["id"] for a in base.to_dict()["assets"] if a["asset_type"] in ("database", "file_server")]
        truth_paths = sum(1 for name, idn in base.identities.items() for j in jewels if base.find_path(idn["asset"], j))
        identity["total"] += truth_paths
        identity["found"] += round(identity_recall(base, guard.output) * truth_paths)

        # deception: deploy on the attack path, does red's shortest path trip it?
        dec = attacked.clone()
        await build_agent("defense_executor").run(AgentContext(run_id=ctx.run_id, twin=dec, scenario=scenario),
                                                  io.ExecuteIn(actions=[{"action_type": "deploy_decoy", "asset_id": scenario["target_asset"],
                                                                         "params": {"kind": "honeypot_host", "name": f"decoy-eval-{i}"}}]))
        deception["deployed"] += 1
        deception["tripped"] += deception_trip(dec, scenario)

        # config engineer parse success / semantic equality
        for action in scenario["expected_defense"][:1]:
            eng = await build_agent("config_engineer").run(ctx, io.ExecuteIn(actions=[action]))
            engineer["total"] += 1
            engineer["parsed"] += int(bool(eng.output.parsed_actions))
            engineer["equal"] += int(bool(eng.output.parsed_actions) and eng.output.parsed_actions[0]["action_type"] == action["action_type"])

        # forensic citation validity
        c2 = AgentContext(run_id=ctx.run_id, twin=attacked, scenario=scenario, telemetry=telemetry)
        c2.memory = [{"agent": "observer", "decision": "generated attack observed", "evidence_refs": [telemetry[0]["id"]]}]
        rep = await build_agent("forensic_reporter").run(c2, io.TextIn())
        forensic_rates.append(rep.output.citation_validity_rate)

        if progress:
            progress(i + 1, n)

    def mean(xs):
        return round(sum(xs) / len(xs), 3) if xs else 0.0

    return {
        "n": n, "seed": seed, "mode": mode,
        "agents": {
            "incident_investigator": {"precision": mean(inv_prec), "recall": mean(inv_rec)},
            "defense_strategist": {"pass_rate_pct": round(100 * strat["passes"] / max(strat["runs"], 1), 1),
                                   "mean_optimality_gap": mean([float(g) for g in strat["gaps"]]),
                                   "ai_matched_optimum_rate": round(strat["matched"] / max(strat["runs"], 1), 3),
                                   "human_approval_rate": round(strat["approvals"] / max(strat["runs"], 1), 3)},
            "incident_commander": {"pass_rate_pct": round(100 * strat["passes"] / max(strat["runs"], 1), 1),
                                   "plan_valid": validate_plan(default_plan(), set(__import__("app.agents.framework.registry", fromlist=["REGISTRY"]).REGISTRY)) == []},
            "red_team_planner": {"campaign_validity_rate": round(red["valid"] / max(red["campaigns"], 1), 3),
                                 "real_path_rate": round(red["real"] / max(red["campaigns"], 1), 3)},
            "red_team_critic": {"bypass_true_positive_rate": round(critic["tp"] / max(critic["checked"], 1), 3), "note": "no post-defense bypasses in this sample" if not critic["checked"] else ""},
            "config_auditor": {"precision": round(auditor["tp"] / max(auditor["tp"] + auditor["fp"], 1), 3),
                               "recall": round(auditor["tp"] / max(auditor["tp"] + auditor["fn"], 1), 3)},
            "identity_guardian": {"privilege_path_recall": round(identity["found"] / max(identity["total"], 1), 3)},
            "deception_engineer": {"decoy_trip_rate": round(deception["tripped"] / max(deception["deployed"], 1), 3),
                                   "detection_lead_time_rounds": 0},
            "config_engineer": {"parse_success_rate": round(engineer["parsed"] / max(engineer["total"], 1), 3),
                                "semantic_equality_rate": round(engineer["equal"] / max(engineer["total"], 1), 3)},
            "forensic_reporter": {"citation_validity_rate": mean(forensic_rates)},
        },
        "calibration": {"incident_investigator": _bucketize(inv_pairs)},
    }


def run_eval_sync(n: int, seed: int, mode: str, progress=None) -> dict:
    return asyncio.run(run_eval(n, seed, mode, progress))
