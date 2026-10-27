"""Closed-loop orchestrator: Observe -> Reason -> Propose -> Simulate -> Validate -> Act -> Retest -> Red-team -> Prove.

Each run owns its twin instance (cloned from the active/display twin or built from a
custom definition). Concurrent runs cannot overwrite each other; the display twin is
only synced to a run's final state when that run finishes.
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


def subscribe(run_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _ws_queues.setdefault(run_id, []).append(q)
    return q


def unsubscribe(run_id: str, q: asyncio.Queue) -> None:
    if run_id in _ws_queues and q in _ws_queues[run_id]:
        _ws_queues[run_id].remove(q)


def cancel(run_id: str) -> None:
    _cancelled.add(run_id)


def activate_twin(twin: DigitalTwin) -> DigitalTwin:
    """Replace the display twin (builtin or user-designed) and return it."""
    global TWIN
    TWIN = twin
    return TWIN


def _emit(db, run_id: str, event_type: str, message: str, agent: str | None = None,
          asset_id: str | None = None, payload: dict | None = None, twin: DigitalTwin | None = None) -> dict:
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


def _check_cancel(run_id: str) -> bool:
    return run_id in _cancelled


async def run_experiment(run_id: str, step_delay_ms: int | None = None) -> None:
    db = SessionLocal()
    twin: DigitalTwin | None = None
    delay_s = (settings.sim_step_delay_ms if step_delay_ms is None else step_delay_ms) / 1000

    async def _delay() -> None:
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
            twin = TWIN.clone()  # per-run twin: concurrent runs are isolated
            twin.reset()
        for aid in (scenario["source_asset"], scenario["target_asset"]):
            if aid not in twin.asset_ids():
                raise ValueError(f"scenario asset '{aid}' not in twin '{twin.asset_ids()}'")
        for step in scenario["attack_steps"]:
            if step["asset"] not in twin.asset_ids():
                raise ValueError(f"attack step asset '{step['asset']}' not in twin")

        run.started_at = datetime.now(timezone.utc)
        mode = "live" if meta_client.configured else "offline"
        run.mode = mode; db.commit()

        async def set_state(state: str, msg: str, agent: str | None = None):
            run.state = state; db.commit()
            emit("state", msg, agent=agent, payload={"state": state, "mode": mode})
            await _delay()

        if _check_cancel(run_id):
            raise asyncio.CancelledError()
        await set_state("SCENARIO_SELECTED", f"Scenario selected: {scenario['name']}", "adversary_simulator")
        baseline_twin = twin.clone()
        db.add(models.AssetStateSnapshot(run_id=run_id, label="baseline", snapshot=twin.snapshot())); db.commit()
        emit("snapshot", "Baseline snapshot saved", payload={"label": "baseline"})

        await set_state("ATTACK_SIMULATING", "Executing typed synthetic attack simulation", "adversary_simulator")
        telemetry = twin.apply_attack(scenario, seed=run.seed)
        attacked_clone = baseline_twin.clone(); attacked_clone.apply_attack(scenario, seed=run.seed)
        baseline_result = attacked_clone.attempt_attack_objective(scenario)
        db.add(models.AssetStateSnapshot(run_id=run_id, label="attacked", snapshot=twin.snapshot())); db.commit()
        for e in telemetry:
            db.add(models.EvidenceRecord(run_id=run_id, kind="telemetry", ref=e["id"],
                                         summary=e["message"], data=e))
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

        await set_state("INVESTIGATING", "Meta Muse Spark investigating evidence" if mode == "live" else "Investigating evidence (OFFLINE deterministic mode — no Meta inference)", "incident_investigator")
        hyp = await agents.investigate(scenario, obs, run_id, telemetry=telemetry, twin=twin)
        if hyp.fallback_reason:
            emit("provider_fallback", f"Investigator fell back to offline: {hyp.fallback_reason}", agent="incident_investigator")
        db.add(models.AgentDecision(run_id=run_id, agent="incident_investigator", decision=hyp.hypothesis,
                                    justification="; ".join(hyp.confirmed), confidence=hyp.confidence,
                                    model=hyp.model, mode=hyp.mode, evidence_refs=hyp.evidence_refs,
                                    asset_ids=hyp.affected_assets)); db.commit()
        emit("agent_decision", hyp.hypothesis, agent="incident_investigator", payload=hyp.model_dump())
        await _delay()

        await set_state("DEFENSE_PROPOSED", "Defense strategist proposing countermeasure", "defense_strategist")
        proposal = await agents.propose_defense(scenario, hyp, run_id, twin=twin)
        if proposal.fallback_reason:
            emit("provider_fallback", f"Strategist fell back to offline: {proposal.fallback_reason}", agent="defense_strategist")
        modes = {hyp.mode, proposal.mode}
        run.mode = "live" if modes == {"live"} else "offline" if modes == {"offline"} else "mixed"
        db.add(models.DefenseProposal(run_id=run_id, actions=[a.model_dump() for a in proposal.actions],
                                      justification=proposal.justification, confidence=proposal.confidence, mode=proposal.mode))
        db.add(models.AgentDecision(run_id=run_id, agent="defense_strategist",
                                    decision=", ".join(f"{a.action_type}:{a.asset_id}" for a in proposal.actions),
                                    justification=proposal.justification, confidence=proposal.confidence,
                                    model=proposal.model, mode=proposal.mode, evidence_refs=proposal.evidence_refs,
                                    asset_ids=[a.asset_id for a in proposal.actions])); db.commit()
        emit("agent_decision", proposal.justification, agent="defense_strategist", payload=proposal.model_dump())

        # Simulate-before-acting: replay the proposal + alternatives on clones, pick best trade-off
        emit("state", "Simulating candidate defenses on cloned twins", agent="defense_strategist", payload={"state": "SIMULATING_CANDIDATES"})
        candidates = evaluate_candidates(attacked_clone, baseline_twin, scenario, [a.model_dump() for a in proposal.actions])
        for c in candidates:
            emit("candidate_evaluation", f"{c['label']} [{c['origin']}]: blocked={c['blocked']} disrupted={c['disrupted']} — {c['detail']}",
                 agent="defense_strategist", payload=c)
        best = candidates[0] if candidates else None
        if best and best["feasible"] and best["blocked"]:
            chosen = [DefenseAction(**a) for a in best["actions"]]
            if best["origin"] != "ai":
                emit("candidate_selected", f"Simulation selected '{best['label']}' over the agent proposal (blocked with disruption={best['disrupted']})",
                     agent="defense_executor", payload=best)
        else:
            chosen = list(proposal.actions)
        run.metrics = {"candidates": candidates}; db.commit()
        await _delay()

        await set_state("POLICY_VALIDATING", "Deterministic policy engine validating chosen defense", "defense_executor")
        decisions = []
        for a in chosen:
            d = policy_engine.evaluate(a.action_type, a.asset_id, a.params, twin)
            decisions.append(d)
            db.add(models.PolicyEvaluation(run_id=run_id, action_type=a.action_type, asset_id=a.asset_id,
                                           approved=d.approved, reasons=d.reasons))
            emit("policy_decision", f"{a.action_type} on {a.asset_id}: {'APPROVED' if d.approved else 'REJECTED'} — {'; '.join(d.reasons)}",
                 agent="defense_executor", asset_id=a.asset_id, payload=d.model_dump())
        db.commit()
        await _delay()

        await set_state("DEFENSE_APPLYING", "Applying approved simulated defenses", "defense_executor")
        applied = 0
        for a, d in zip(chosen, decisions):
            if not d.approved:
                emit("defense_rejected", f"Skipped rejected action {a.action_type}", agent="defense_executor", asset_id=a.asset_id)
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
        sim_contained = sim_detected + 0.4 * applied if applied else None

        async def do_verify():
            await set_state("VERIFYING", "Verification Scientist replaying attack against modified twin", "verification_scientist")
            res = verify(scenario, baseline_twin, twin, baseline_result, 0.0, sim_detected, sim_contained)
            db.add(models.VerificationResultRow(run_id=run_id, outcome=res.outcome, invariant=res.invariant,
                                                checks=[c.model_dump() for c in res.checks], metrics=res.metrics))
            db.add(models.EvidenceRecord(run_id=run_id, kind="verification", ref=f"verification:{res.outcome}",
                                         summary=res.invariant, data=res.model_dump()))
            emit("verification", f"Verification {res.outcome}: {res.invariant}", agent="verification_scientist", payload=res.model_dump())
            return res

        result = await do_verify()
        rounds = [{"round": 1, "path": baseline_result.get("path"), "effectiveness_pct": result.metrics["defense_effectiveness_pct"],
                   "outcome": result.outcome, "red_team_mode": None}]

        # AI red team: look for an alternate path; loop defense while one exists (max 3 rounds)
        if scenario["verification_kind"] == "reachability":
            for round_num in range(2, 4):
                paths = red_team.enumerate_paths(twin, scenario["source_asset"], scenario["target_asset"])
                if not paths:
                    emit("red_team", f"Red team (round {round_num}): no alternate path from {scenario['source_asset']} to {scenario['target_asset']} — attack surface closed",
                         agent="adversary_simulator", payload={"paths": []})
                    break
                chosen_path, rt_mode, rationale = await red_team.choose_path(paths, run_id)
                emit("red_team", f"Red team (round {round_num}, mode={rt_mode}) found alternate path: {' -> '.join(chosen_path)} — {rationale}",
                     agent="adversary_simulator", payload={"path": chosen_path, "mode": rt_mode, "candidates": paths})
                for node in chosen_path[1:-1]:
                    if twin.status.get(node) == "healthy":
                        twin.status[node] = "suspicious"
                twin.status[scenario["target_asset"]] = "suspicious"
                await set_state("DEFENSE_PROPOSED", f"Round {round_num}: strategist responding to red-team path", "defense_strategist")
                prop2 = await agents.propose_defense(scenario, hyp, run_id, twin=twin)
                applied2 = 0
                for a in prop2.actions:
                    d = policy_engine.evaluate(a.action_type, a.asset_id, a.params, twin)
                    db.add(models.PolicyEvaluation(run_id=run_id, action_type=a.action_type, asset_id=a.asset_id, approved=d.approved, reasons=d.reasons))
                    if d.approved:
                        try:
                            twin.apply_action(a.action_type, a.asset_id, a.params); applied2 += 1
                            emit("defense_applied", f"[round {round_num}] Applied {a.action_type} to {a.asset_id}", agent="defense_executor", asset_id=a.asset_id)
                        except ValueError:
                            pass
                db.commit()
                sim_contained = (sim_contained or sim_detected) + 0.4 * applied2
                result = await do_verify()
                rounds.append({"round": round_num, "path": chosen_path, "effectiveness_pct": result.metrics["defense_effectiveness_pct"],
                               "outcome": result.outcome, "red_team_mode": rt_mode})
                if result.outcome == "FAIL":
                    break

        result.metrics["rounds"] = rounds
        result.metrics["candidates"] = candidates
        latest_ver = db.query(models.VerificationResultRow).filter_by(run_id=run_id).order_by(
            models.VerificationResultRow.created_at.desc()).first()
        if latest_ver:
            latest_ver.metrics = dict(result.metrics); db.commit()
        db.add(models.AgentDecision(run_id=run_id, agent="verification_scientist", decision=f"VERIFICATION {result.outcome}",
                                    justification=result.invariant, confidence=1.0 if result.outcome != "INCONCLUSIVE" else 0.4,
                                    model="deterministic-replay", mode="offline", evidence_refs=result.evidence_refs,
                                    asset_ids=[scenario["target_asset"]])); db.commit()

        if result.outcome == "PASS":  # visuals must agree with the verdict
            for aid, st in list(twin.status.items()):
                if st == "suspicious":
                    twin.status[aid] = "remediated" if aid == scenario["target_asset"] else "healthy"

        for u in list(meta_client.usage):
            if u.get("run_id") == run_id:
                db.add(models.ModelUsage(run_id=run_id, model=u["model"], prompt_version=u["prompt_version"],
                                         prompt_tokens=u["prompt_tokens"], completion_tokens=u["completion_tokens"],
                                         latency_ms=u["latency_ms"], success=u["success"], error=u.get("error")))
        meta_client.usage = [u for u in meta_client.usage if u.get("run_id") != run_id]
        run.metrics = result.metrics
        db.add(models.AssetStateSnapshot(run_id=run_id, label="post_remediation", snapshot=twin.snapshot())); db.commit()
        run.state = "FAILED" if _check_cancel(run_id) else "COMPLETED"
        if _check_cancel(run_id):
            run.error = "cancelled by operator"
        run.ended_at = datetime.now(timezone.utc); db.commit()
        activate_twin(twin)  # display sync: last finished run wins the shared view
        emit("completed" if run.state == "COMPLETED" else "failed",
             f"Experiment {run.state} — verification {result.outcome}", payload={"verification": result.model_dump(), "metrics": result.metrics})
    except asyncio.CancelledError:
        run = db.get(models.SimulationRun, run_id)
        if run:
            run.state = "FAILED"; run.error = "cancelled"; run.ended_at = datetime.now(timezone.utc); db.commit()
            _emit(db, run_id, "failed", "Experiment cancelled", twin=twin)
    except Exception as e:  # noqa: BLE001 - honest failure state
        run = db.get(models.SimulationRun, run_id)
        if run:
            run.state = "FAILED"; run.error = f"{type(e).__name__}: {e}"; run.ended_at = datetime.now(timezone.utc); db.commit()
            _emit(db, run_id, "failed", run.error, twin=twin)
    finally:
        _cancelled.discard(run_id)
        db.close()
