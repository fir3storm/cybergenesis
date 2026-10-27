"""Closed-loop orchestrator v3.

Observe -> Reason -> Propose -> Simulate -> AI final choice -> Red critic -> (revise)
-> Policy -> [Human approval] -> Act -> Verify -> Red-team campaign rounds -> Self-heal -> Prove.
Each run owns its twin; the display twin syncs only when a run finishes.
"""

import asyncio
from datetime import datetime, timezone

from app import models
from app.agents import agents, red_team
from app.core.config import settings
from app.db import SessionLocal
from app.integrations.meta_client import meta_client
from app.policies import engine as policy_engine
from app.schemas import DefenseAction
from app.simulation.candidates import evaluate_candidates
from app.simulation.scenarios import SCENARIOS
from app.simulation.twin import DigitalTwin
from app.verification.verifier import verify

TWIN = DigitalTwin()
_ws_queues: dict[str, list[asyncio.Queue]] = {}
_cancelled: set[str] = set()
_seq: dict[str, int] = {}
_approvals: dict[str, dict] = {}


def subscribe(run_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _ws_queues.setdefault(run_id, []).append(q)
    return q


def unsubscribe(run_id: str, q: asyncio.Queue) -> None:
    if run_id in _ws_queues and q in _ws_queues[run_id]:
        _ws_queues[run_id].remove(q)


def cancel(run_id: str) -> None:
    _cancelled.add(run_id)


def _check_cancel(run_id: str) -> bool:
    return run_id in _cancelled


def resolve_approval(run_id: str, approved: bool) -> bool:
    entry = _approvals.get(run_id)
    if not entry:
        return False
    entry["approved"] = approved
    entry["event"].set()
    return True


def activate_twin(twin: DigitalTwin) -> DigitalTwin:
    global TWIN
    TWIN = twin
    return TWIN


def _emit(db, run_id, event_type, message, agent=None, asset_id=None, payload=None, twin=None):
    _seq[run_id] = _seq.get(run_id, 0) + 1
    ev = models.SimulationEvent(run_id=run_id, event_type=event_type, agent=agent, asset_id=asset_id,
                                message=message, payload=payload or {}, seq=_seq[run_id])
    db.add(ev); db.commit(); db.refresh(ev)
    data = {"event_type": event_type, "run_id": run_id, "agent": agent, "asset_id": asset_id,
            "message": message, "payload": payload or {}, "seq": ev.seq,
            "timestamp": ev.created_at.isoformat() if ev.created_at else datetime.now(timezone.utc).isoformat(),
            "twin": (twin or TWIN).to_dict()}
    for q in _ws_queues.get(run_id, []):
        q.put_nowait(data)
    return data


async def run_experiment(run_id: str, step_delay_ms: int | None = None) -> None:
    db = SessionLocal()
    twin: DigitalTwin | None = None
    delay_s = (settings.sim_step_delay_ms if step_delay_ms is None else step_delay_ms) / 1000

    async def _delay():
        if delay_s:
            await asyncio.sleep(delay_s)

    def emit(*args, **kwargs):
        return _emit(db, run_id, *args, twin=twin, **kwargs)

    try:
        run = db.get(models.SimulationRun, run_id)
        if not run:
            return
        if run.custom_scenario_id:
            row = db.get(models.CustomScenarioDefinition, run.custom_scenario_id)
            if not row:
                raise ValueError(f"custom scenario not found: {run.custom_scenario_id}")
            scenario = {**row.definition, "id": row.id, "name": row.name}
        else:
            scenario = SCENARIOS[run.scenario_id]
        if run.custom_twin_id:
            trow = db.get(models.CustomTwinDefinition, run.custom_twin_id)
            if not trow:
                raise ValueError(f"custom twin not found: {run.custom_twin_id}")
            twin = DigitalTwin.from_dict(trow.assets, trow.connections)
        else:
            twin = TWIN.clone()
            twin.reset()
        for aid in (scenario["source_asset"], scenario["target_asset"]):
            if aid not in twin.asset_ids():
                raise ValueError(f"scenario asset '{aid}' not in twin")
        run.started_at = datetime.now(timezone.utc)
        mode = "live" if meta_client.configured else "offline"
        run.mode = mode; db.commit()

        async def set_state(state, msg, agent=None):
            run.state = state; db.commit()
            emit("state", msg, agent=agent, payload={"state": state, "mode": mode})
            await _delay()

        if run_id in _cancelled:
            raise asyncio.CancelledError()
        await set_state("SCENARIO_SELECTED", f"Scenario selected: {scenario['name']}", "adversary_simulator")
        baseline_twin = twin.clone()
        db.add(models.AssetStateSnapshot(run_id=run_id, label="baseline", snapshot=twin.snapshot())); db.commit()
        emit("snapshot", "Baseline snapshot saved", payload={"label": "baseline"})

        await set_state("ATTACK_SIMULATING", "Executing typed synthetic attack simulation", "adversary_simulator")
        telemetry = twin.apply_attack(scenario, seed=run.seed)
        attacked_clone = baseline_twin.clone(); attacked_clone.apply_attack(scenario, seed=run.seed)
        baseline_result = attacked_clone.attempt_attack_objective(scenario)
        baseline_path = baseline_result.get("path") or [scenario["source_asset"], scenario["target_asset"]]
        db.add(models.AssetStateSnapshot(run_id=run_id, label="attacked", snapshot=twin.snapshot())); db.commit()
        for e in telemetry:
            db.add(models.EvidenceRecord(run_id=run_id, kind="telemetry", ref=e["id"], summary=e["message"], data=e))
            emit("telemetry", e["message"], agent="adversary_simulator", asset_id=e["asset_id"], payload=e)
            await _delay()
        db.commit()
        sim_detected = max((e["offset_ms"] for e in telemetry), default=0) / 1000.0

        await set_state("TELEMETRY_COLLECTED", f"{len(telemetry)} synthetic telemetry events collected", "observer")
        obs = agents.observe(telemetry)
        db.add(models.AgentDecision(run_id=run_id, agent="observer", decision=obs.anomaly_type,
                                    justification=obs.summary, confidence=obs.confidence, model="deterministic",
                                    mode="offline", evidence_refs=obs.event_ids, asset_ids=obs.asset_ids)); db.commit()
        emit("agent_decision", obs.summary, agent="observer", payload=obs.model_dump())

        # learning across runs: past verified defenses for this scenario, from the evidence store
        past_examples: list[str] = []
        try:
            past = (db.query(models.DefenseProposal)
                    .filter(models.DefenseProposal.run_id.in_(
                        db.query(models.SimulationRun.id).filter(models.SimulationRun.scenario_id == run.scenario_id)))
                    .order_by(models.DefenseProposal.created_at.desc()).limit(3).all())
            past_examples = [f"{p.actions} (confidence {p.confidence})" for p in past if p.actions]
        except Exception:  # noqa: BLE001 - learning is best-effort context, never a blocker
            past_examples = []

        await set_state("INVESTIGATING", "Meta Muse Spark investigating evidence" if mode == "live" else "Investigating evidence (OFFLINE)", "incident_investigator")
        hyp = await agents.investigate(scenario, obs, run_id, telemetry=telemetry, twin=twin)
        if hyp.fallback_reason:
            emit("provider_fallback", f"Investigator fell back to offline: {hyp.fallback_reason}", agent="incident_investigator")
        db.add(models.AgentDecision(run_id=run_id, agent="incident_investigator", decision=hyp.hypothesis,
                                    justification="; ".join(hyp.confirmed), confidence=hyp.confidence, model=hyp.model,
                                    mode=hyp.mode, evidence_refs=hyp.evidence_refs, asset_ids=hyp.affected_assets,
                                    data={"claim_evidence": hyp.claim_evidence})); db.commit()
        emit("agent_decision", hyp.hypothesis, agent="incident_investigator", payload=hyp.model_dump())

        # race against time: the attack advances one hop per 2.0s of simulated time;
        # live model latency is converted to simulated time, so slow reasoning costs nodes
        live_latency = sum(u["latency_ms"] for u in meta_client.usage if u.get("run_id") == run_id)
        sim_seconds = live_latency / 1000.0
        hops = int(sim_seconds // 2.0)
        if hops and baseline_path and len(baseline_path) > 2:
            for spread_to in [n for n in baseline_path[1:-1] if twin.status.get(n) == "healthy"][:hops]:
                twin.status[spread_to] = "suspicious"
                emit("telemetry", f"Attack spread to {spread_to} while the AI was reasoning ({live_latency} ms model latency = {sim_seconds:.1f}s simulated, {hops} hop ticks)",
                     agent="adversary_simulator", asset_id=spread_to,
                     payload={"id": f"tele-spread-{run_id[:6]}-{spread_to}", "event_type": "network_connection", "asset_id": spread_to})
        await _delay()

        sim_contained: float | None = None
        final_choice_meta: dict = {}

        async def defend(hyp_obj, round_num: int, extra_context: str = "") -> tuple[list, object]:
            """Propose -> simulate -> AI final choice -> critic -> policy -> [approval] -> apply. Fully recorded."""
            await set_state("DEFENSE_PROPOSED", f"[round {round_num}] Defense strategist proposing countermeasure", "defense_strategist")
            proposal = await agents.propose_defense(scenario, hyp_obj, run_id, twin=twin,
                                                    past_examples=past_examples, extra_context=extra_context)
            if proposal.fallback_reason:
                emit("provider_fallback", f"Strategist fell back to offline: {proposal.fallback_reason}", agent="defense_strategist")
            db.add(models.DefenseProposal(run_id=run_id, actions=[a.model_dump() for a in proposal.actions],
                                          justification=proposal.justification, confidence=proposal.confidence, mode=proposal.mode))
            db.add(models.AgentDecision(run_id=run_id, agent="defense_strategist",
                                        decision=", ".join(f"{a.action_type}:{a.asset_id}" for a in proposal.actions),
                                        justification=proposal.justification, confidence=proposal.confidence,
                                        model=proposal.model, mode=proposal.mode, evidence_refs=proposal.evidence_refs,
                                        asset_ids=[a.asset_id for a in proposal.actions])); db.commit()
            emit("agent_decision", proposal.justification, agent="defense_strategist", payload=proposal.model_dump())

            emit("state", "Simulating candidate defenses on cloned twins", agent="defense_strategist", payload={"state": "SIMULATING_CANDIDATES"})
            candidates = evaluate_candidates(twin.clone(), baseline_twin, scenario, [a.model_dump() for a in proposal.actions])
            for c in candidates:
                emit("candidate_evaluation", f"{c['label']} [{c['origin']}]: blocked={c['blocked']} disrupted={c['disrupted']} — {c['detail']}",
                     agent="defense_strategist", payload=c)
            chosen_cand = None
            chosen: list = list(proposal.actions)
            for _attempt in range(2):  # attempt 1 may be revised after the red-team critic debate
                choice = await agents.final_choice(candidates, scenario, run_id)
                final_choice_meta.update(choice)
                chosen_cand = choice["candidate"]
                emit("final_choice", f"Final choice by {'Meta AI' if choice['mode'] == 'live' else 'deterministic fallback'}: "
                                     f"{choice['chosen_label']} — {choice['justification']} (confidence {choice['confidence']}, "
                                     f"matched simulation optimum: {choice['ai_matched_optimum']})",
                     agent="defense_strategist", payload={k: choice[k] for k in ("chosen_label", "justification", "confidence", "mode", "ai_matched_optimum", "candidates_considered")})
                if chosen_cand is not None:
                    chosen = [DefenseAction(**a) for a in chosen_cand["actions"]]
                else:  # explicit substitution — never silent
                    emit("override", "System substitution: no feasible simulated candidate, executing the agent proposal verbatim (policy + verification will judge it)",
                         agent="defense_executor", payload={"reason": "no_feasible_candidate"})
                    chosen = list(proposal.actions)

                # red-team critic: how would red get around this, before it is applied?
                clone = twin.clone()
                for a in chosen:
                    if policy_engine.evaluate(a.action_type, a.asset_id, a.params, clone).approved:
                        try:
                            clone.apply_action(a.action_type, a.asset_id, a.params)
                        except ValueError:
                            pass
                alt = red_team.enumerate_paths(clone, scenario["source_asset"], scenario["target_asset"]) \
                    if scenario["verification_kind"] == "reachability" else []
                critic = await agents.criticize_defense(scenario, chosen_cand["label"] if chosen_cand else "proposal", alt, run_id)
                emit("red_critic", f"Red critic ({critic['mode']}): {critic['assessment']}" + (f" — bypass: {' -> '.join(critic['bypass'])}" if critic["bypass"] else ""),
                     agent="adversary_simulator", payload=critic)
                if _attempt == 0 and critic["bypass"] and critic["suggested_campaign"]:
                    verdict = policy_engine.evaluate_campaign(critic["suggested_campaign"], twin)
                    if verdict["approved"]:
                        emit("debate", f"DEBATE — Red: '{critic['assessment']}' via {' -> '.join(critic['bypass'])}. Blue gets one revision.",
                             agent="adversary_simulator", payload={"critic": critic, "campaign_valid": True})
                        proposal = await agents.propose_defense(
                            scenario, hyp_obj, run_id, twin=twin, past_examples=past_examples,
                            extra_context=(f"RED CRITIC: your previous defense can be bypassed via {' -> '.join(critic['bypass'])}. "
                                           f"Assessment: {critic['assessment']}. Propose a revised defense that also covers this bypass."))
                        db.add(models.DefenseProposal(run_id=run_id, actions=[a.model_dump() for a in proposal.actions],
                                                      justification=f"[revision after critic] {proposal.justification}",
                                                      confidence=proposal.confidence, mode=proposal.mode)); db.commit()
                        emit("agent_decision", f"[revision] {proposal.justification}", agent="defense_strategist", payload=proposal.model_dump())
                        emit("override", "Blue revised its defense after the red critic debate (strategist revision, recorded)",
                             agent="defense_strategist", payload={"reason": "critic_bypass_validated"})
                        candidates = evaluate_candidates(twin.clone(), baseline_twin, scenario, [a.model_dump() for a in proposal.actions])
                        for c in candidates:
                            emit("candidate_evaluation", f"[revision] {c['label']} [{c['origin']}]: blocked={c['blocked']} disrupted={c['disrupted']}",
                                 agent="defense_strategist", payload=c)
                        continue
                break

            await set_state("POLICY_VALIDATING", "Deterministic policy engine validating chosen defense", "defense_executor")
            decisions = []
            for a in chosen:
                d = policy_engine.evaluate(a.action_type, a.asset_id, a.params, twin)
                decisions.append(d)
                db.add(models.PolicyEvaluation(run_id=run_id, action_type=a.action_type, asset_id=a.asset_id, approved=d.approved, reasons=d.reasons))
                emit("policy_decision", f"{a.action_type} on {a.asset_id}: {'APPROVED' if d.approved else 'REJECTED'} — {'; '.join(d.reasons)}",
                     agent="defense_executor", asset_id=a.asset_id, payload=d.model_dump())
            db.commit()

            # human approval gate for high-disruption defenses
            disrupted_est = chosen_cand["disrupted"] if chosen_cand else None
            if settings.human_approval_enabled and disrupted_est is not None and disrupted_est >= 2:
                entry = {"event": asyncio.Event(), "approved": None}
                _approvals[run_id] = entry
                emit("approval_required", f"Human approval required: '{chosen_cand['label']}' disrupts {disrupted_est} legitimate paths. Approve in the UI.",
                     agent="defense_executor", payload={"actions": [a.model_dump() for a in chosen], "disrupted": disrupted_est})
                try:
                    await asyncio.wait_for(entry["event"].wait(), timeout=settings.approval_timeout_seconds)
                    approved_by_human = bool(entry["approved"])
                except asyncio.TimeoutError:
                    approved_by_human = False
                    emit("approval_timeout", "Human approval timed out — defense NOT applied", agent="defense_executor")
                _approvals.pop(run_id, None)
                if not approved_by_human:
                    emit("defense_rejected", "Defense rejected by human operator (or approval timeout)", agent="defense_executor")
                    return candidates, proposal
            await _delay()

            await set_state("DEFENSE_APPLYING", "Applying approved simulated defenses", "defense_executor")
            applied = 0
            for a, d in zip(chosen, decisions):
                if not d.approved:
                    emit("defense_rejected", f"Skipped rejected action {a.action_type} on {a.asset_id}: {'; '.join(d.reasons)}",
                         agent="defense_executor", asset_id=a.asset_id)
                    continue
                try:
                    transition = twin.apply_action(a.action_type, a.asset_id, a.params)
                    applied += 1
                    db.add(models.DefenseExecution(run_id=run_id, action_type=a.action_type, asset_id=a.asset_id, success=True, transition=transition))
                    db.add(models.EvidenceRecord(run_id=run_id, kind="defense", ref=f"defense:{a.action_type}:{a.asset_id}", summary=str(transition), data=transition))
                    emit("defense_applied", f"Applied {a.action_type} to {a.asset_id}", agent="defense_executor", asset_id=a.asset_id, payload=transition)
                except ValueError as e:
                    db.add(models.DefenseExecution(run_id=run_id, action_type=a.action_type, asset_id=a.asset_id, success=False, transition={"error": str(e)}))
                    emit("defense_failed", str(e), agent="defense_executor", asset_id=a.asset_id)
                db.commit()
                await _delay()
            nonlocal_sim = sim_detected + 0.4 * applied if applied else None
            return candidates, nonlocal_sim

        candidates, sim_contained = await defend(hyp, 1)

        async def do_verify():
            await set_state("VERIFYING", "Verification Scientist replaying attack against modified twin", "verification_scientist")
            res = verify(scenario, baseline_twin, twin, baseline_result, 0.0, sim_detected, sim_contained)
            db.add(models.VerificationResultRow(run_id=run_id, outcome=res.outcome, invariant=res.invariant,
                                                checks=[c.model_dump() for c in res.checks], metrics=res.metrics))
            db.add(models.EvidenceRecord(run_id=run_id, kind="verification", ref=f"verification:{res.outcome}", summary=res.invariant, data=res.model_dump()))
            emit("verification", f"Verification {res.outcome}: {res.invariant}", agent="verification_scientist", payload=res.model_dump())
            return res

        result = await do_verify()
        primary_result = result
        original_scenario = scenario
        initial_paths = red_team.enumerate_paths(baseline_twin, scenario["source_asset"], scenario["target_asset"]) \
            if scenario["verification_kind"] == "reachability" else []

        def resilience_now() -> float:
            if not initial_paths:
                return result.metrics["defense_effectiveness_pct"]
            remaining = red_team.enumerate_paths(twin, scenario["source_asset"], scenario["target_asset"])
            return round(100.0 * (1 - len(remaining) / max(len(initial_paths), 1)), 1)

        rounds = [{"round": 1, "foothold": scenario["source_asset"], "objective": scenario["target_asset"],
                   "path": baseline_path, "red_mode": None, "blue_mode": hyp.mode,
                   "effectiveness_pct": result.metrics["defense_effectiveness_pct"],
                   "resilience_score": resilience_now(), "outcome": result.outcome,
                   "disrupted": result.metrics["operational_impact_disrupted_legit_paths"], "red_team_mode": None}]

        if scenario["verification_kind"] == "reachability":
            for round_num in range(2, 5):  # up to 4 rounds total
                plan = await red_team.plan_campaign(twin, scenario["source_asset"], scenario["target_asset"], run_id)
                if plan is None:
                    emit("red_team", f"Red team (round {round_num}): no valid campaign — attack surface closed",
                         agent="adversary_simulator", payload={"campaign": None})
                    break
                verdict = policy_engine.evaluate_campaign(plan.model_dump(), twin)
                emit("policy_decision", f"Red campaign {'VALIDATED' if verdict['approved'] else 'REJECTED'}: {'; '.join(verdict['reasons'])}",
                     agent="defense_executor", payload={"approved": verdict["approved"], "campaign": plan.model_dump()})
                db.add(models.PolicyEvaluation(run_id=run_id, action_type="red_campaign", asset_id=plan.foothold,
                                               approved=verdict["approved"], reasons=verdict["reasons"])); db.commit()
                if not verdict["approved"]:
                    break
                chosen_path = verdict["path"] or plan.path
                is_pivot = plan.foothold != scenario["source_asset"] or plan.objective != scenario["target_asset"]
                if is_pivot:
                    emit("red_team_pivot", f"Red team changes approach: foothold {plan.foothold} -> objective {plan.objective} (pivot_identity={plan.pivot_identity})",
                         agent="adversary_simulator", payload=plan.model_dump())
                emit("red_team", f"Red campaign (round {round_num}, mode={plan.mode}): {' -> '.join(chosen_path)} — {plan.rationale}",
                     agent="adversary_simulator", payload=plan.model_dump())
                db.add(models.AgentDecision(run_id=run_id, agent="adversary_simulator",
                                            decision=f"campaign {plan.foothold} -> {plan.objective}: {' -> '.join(chosen_path)}",
                                            justification=plan.rationale, confidence=plan.confidence,
                                            model=meta_client.model if plan.mode == "live" else "deterministic",
                                            mode=plan.mode, evidence_refs=[], asset_ids=chosen_path,
                                            data={"campaign": plan.model_dump(), "round": round_num})); db.commit()
                # apply the campaign as this round's attack (typed steps only)
                round_scenario = {**scenario, "id": f"{scenario['id']}-r{round_num}",
                                  "source_asset": plan.foothold, "target_asset": plan.objective,
                                  "attack_steps": [s.model_dump() for s in plan.steps], "identity": None}
                red_telemetry = twin.apply_attack(round_scenario, seed=run.seed + round_num)
                for e in red_telemetry:
                    e["id"] = f"tele-red-{run_id[:6]}-{round_num}-{e['id'].rsplit('-', 1)[-1]}"
                    db.add(models.EvidenceRecord(run_id=run_id, kind="telemetry", ref=e["id"], summary=e["message"], data=e))
                    emit("telemetry", e["message"], agent="adversary_simulator", asset_id=e["asset_id"], payload=e)
                db.commit()
                scenario = {**scenario, "source_asset": plan.foothold, "target_asset": plan.objective,
                            "invariant": f"No path from {plan.foothold} to {plan.objective}"}
                baseline_result = {"objective_blocked": False, "path": chosen_path}
                obs2 = agents.observe(red_telemetry)
                hyp2 = await agents.investigate(scenario, obs2, run_id, telemetry=red_telemetry, twin=twin)
                db.add(models.AgentDecision(run_id=run_id, agent="incident_investigator", decision=hyp2.hypothesis,
                                            justification="; ".join(hyp2.confirmed), confidence=hyp2.confidence, model=hyp2.model,
                                            mode=hyp2.mode, evidence_refs=hyp2.evidence_refs, asset_ids=hyp2.affected_assets,
                                            data={"claim_evidence": hyp2.claim_evidence, "round": round_num})); db.commit()
                _c, sim_contained = await defend(hyp2, round_num)
                result = await do_verify()
                rounds.append({"round": round_num, "foothold": plan.foothold, "objective": plan.objective,
                               "path": chosen_path, "red_mode": plan.mode, "blue_mode": hyp2.mode,
                               "effectiveness_pct": result.metrics["defense_effectiveness_pct"],
                               "resilience_score": resilience_now(), "outcome": result.outcome,
                               "disrupted": result.metrics["operational_impact_disrupted_legit_paths"],
                               "red_team_mode": plan.mode})
                if is_pivot:
                    result = primary_result
                    scenario = original_scenario
                    break
                if _check_cancel(run_id):
                    break

        result.metrics["nodes_compromised_before_containment"] = sum(
            1 for s in twin.status.values() if s in ("compromised", "contained"))
        result.metrics["sim_time_to_contain_s"] = sim_contained
        disrupted_before_healing = result.metrics["operational_impact_disrupted_legit_paths"]

        # self-healing: win back legitimate traffic where the objective stays blocked
        if result.outcome == "PASS":
            for entry in list(twin.containment):
                clone = twin.clone()
                try:
                    if entry.startswith("isolate:"):
                        clone.apply_action("restore_connectivity", entry.split(":", 1)[1])
                    elif entry.startswith(("block:", "block_outbound:")):
                        pair = entry.split(":", 1)[1].split("->")
                        clone.apply_action("restore_connectivity", pair[0], {"source": pair[0], "target": pair[1]})
                    else:
                        continue
                except ValueError:
                    continue
                if clone.attempt_attack_objective(scenario)["objective_blocked"]:
                    # safe to restore on the real twin
                    if entry.startswith("isolate:"):
                        twin.apply_action("restore_connectivity", entry.split(":", 1)[1])
                    else:
                        pair = entry.split(":", 1)[1].split("->")
                        twin.apply_action("restore_connectivity", pair[0], {"source": pair[0], "target": pair[1]})
                    db.add(models.DefenseExecution(run_id=run_id, action_type="restore_connectivity",
                                                    asset_id=entry.split(":", 1)[1], success=True,
                                                    transition={"self_healing": entry}))
                    emit("self_healing", f"Self-healing: restored {entry} — attack objective still blocked, legitimate traffic recovered",
                         agent="defense_executor")
                    db.commit()
            result = await do_verify()

        result.metrics["disrupted_before_healing"] = disrupted_before_healing
        result.metrics["disrupted_after_healing"] = result.metrics["operational_impact_disrupted_legit_paths"]
        result.metrics["nodes_compromised_before_containment"] = sum(
            1 for s in twin.status.values() if s in ("compromised", "contained"))
        result.metrics["sim_time_to_contain_s"] = sim_contained
        result.metrics["users_affected"] = result.metrics.get("users_affected")
        result.metrics["rounds"] = rounds
        result.metrics["candidates"] = candidates
        result.metrics["ai_final_choice"] = {"mode": final_choice_meta.get("mode"),
                                             "chosen_label": final_choice_meta.get("chosen_label"),
                                             "justification": final_choice_meta.get("justification"),
                                             "confidence": final_choice_meta.get("confidence")}
        result.metrics["ai_matched_optimum"] = final_choice_meta.get("ai_matched_optimum")
        result.metrics["candidates_considered"] = final_choice_meta.get("candidates_considered")
        latest_ver = db.query(models.VerificationResultRow).filter_by(run_id=run_id).order_by(
            models.VerificationResultRow.created_at.desc()).first()
        if latest_ver:
            latest_ver.metrics = dict(result.metrics); db.commit()
        modes = {hyp.mode}
        run.mode = "live" if modes == {"live"} else "offline" if modes == {"offline"} else "mixed"
        db.add(models.AgentDecision(run_id=run_id, agent="verification_scientist", decision=f"VERIFICATION {result.outcome}",
                                    justification=result.invariant, confidence=1.0, model="deterministic-replay",
                                    mode="offline", evidence_refs=result.evidence_refs, asset_ids=[scenario["target_asset"]])); db.commit()

        if result.outcome == "PASS":
            for aid, st in list(twin.status.items()):
                if aid == scenario["target_asset"] and st in ("suspicious", "compromised"):
                    twin.status[aid] = "protected"  # target held: evidence of the attempt remains in the audit trail
                elif st in ("suspicious", "compromised") and not twin.isolated.get(aid):
                    twin.status[aid] = "cleared"  # attacker was here, now cleared — distinct from never-touched "healthy"

        for u in list(meta_client.usage):
            if u.get("run_id") == run_id:
                db.add(models.ModelUsage(run_id=run_id, model=u["model"], prompt_version=u["prompt_version"],
                                         prompt_hash=u.get("prompt_hash", ""),
                                         prompt_tokens=u["prompt_tokens"], completion_tokens=u["completion_tokens"],
                                         latency_ms=u["latency_ms"], success=u["success"], error=u.get("error")))
        meta_client.usage = [u for u in meta_client.usage if u.get("run_id") != run_id]
        run.metrics = result.metrics
        db.add(models.AssetStateSnapshot(run_id=run_id, label="post_remediation", snapshot=twin.snapshot())); db.commit()
        run.state = "FAILED" if _check_cancel(run_id) else "COMPLETED"
        if _check_cancel(run_id):
            run.error = "cancelled by operator"
        run.ended_at = datetime.now(timezone.utc); db.commit()
        activate_twin(twin)
        emit("completed" if run.state == "COMPLETED" else "failed",
             f"Experiment {run.state} — verification {result.outcome}", payload={"verification": result.model_dump(), "metrics": result.metrics})
    except asyncio.CancelledError:
        run = db.get(models.SimulationRun, run_id)
        if run:
            run.state = "FAILED"; run.error = "cancelled"; run.ended_at = datetime.now(timezone.utc); db.commit()
            _emit(db, run_id, "failed", "Experiment cancelled", twin=twin)
    except Exception as e:  # noqa: BLE001
        run = db.get(models.SimulationRun, run_id)
        if run:
            run.state = "FAILED"; run.error = f"{type(e).__name__}: {e}"; run.ended_at = datetime.now(timezone.utc); db.commit()
            _emit(db, run_id, "failed", run.error, twin=twin)
    finally:
        _cancelled.discard(run_id)
        _approvals.pop(run_id, None)
        db.close()
