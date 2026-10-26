"""Closed-loop experiment orchestrator: Observe -> Reason -> Propose -> Validate -> Act -> Retest -> Prove."""

import asyncio
import time
from datetime import datetime, timezone

from app import models
from app.agents import agents
from app.core.config import settings
from app.db import SessionLocal
from app.integrations.meta_client import meta_client
from app.policies import engine as policy_engine
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


async def _delay() -> None:
    if settings.sim_step_delay_ms:
        await asyncio.sleep(settings.sim_step_delay_ms / 1000)


def _emit(db, run_id: str, event_type: str, message: str, agent: str | None = None,
          asset_id: str | None = None, payload: dict | None = None) -> dict:
    _seq[run_id] = _seq.get(run_id, 0) + 1
    ev = models.SimulationEvent(run_id=run_id, event_type=event_type, agent=agent, asset_id=asset_id,
                                message=message, payload=payload or {}, seq=_seq[run_id])
    db.add(ev); db.commit(); db.refresh(ev)
    data = {"event_type": event_type, "run_id": run_id, "agent": agent, "asset_id": asset_id,
            "message": message, "payload": payload or {}, "seq": ev.seq,
            "timestamp": ev.created_at.isoformat() if ev.created_at else datetime.now(timezone.utc).isoformat(),
            "twin": TWIN.to_dict()}
    for q in _ws_queues.get(run_id, []):
        q.put_nowait(data)
    return data


def _check_cancel(run_id: str) -> bool:
    return run_id in _cancelled


async def run_experiment(run_id: str) -> None:
    db = SessionLocal()
    try:
        run = db.get(models.SimulationRun, run_id)
        if not run:
            return
        scenario = SCENARIOS[run.scenario_id]
        run.started_at = datetime.now(timezone.utc)
        db.commit()
        mode = "live" if meta_client.configured else "offline"
        run.mode = mode; db.commit()

        async def set_state(state: str, msg: str, agent: str | None = None):
            run.state = state; db.commit()
            _emit(db, run_id, "state", msg, agent=agent, payload={"state": state, "mode": mode})
            await _delay()

        if _check_cancel(run_id):
            raise asyncio.CancelledError()
        await set_state("SCENARIO_SELECTED", f"Scenario selected: {scenario['name']}", "adversary_simulator")
        TWIN.reset()
        baseline_twin = TWIN.clone()
        db.add(models.AssetStateSnapshot(run_id=run_id, label="baseline", snapshot=TWIN.snapshot())); db.commit()
        _emit(db, run_id, "snapshot", "Baseline snapshot saved", payload={"label": "baseline"})

        t0 = time.monotonic()
        await set_state("ATTACK_SIMULATING", "Executing typed synthetic attack simulation", "adversary_simulator")
        telemetry = TWIN.apply_attack(scenario, seed=run.seed)
        # baseline objective measured on an attacked clone of the baseline (pre-defense)
        attacked_clone = DigitalTwin(); attacked_clone.apply_attack(scenario, seed=run.seed)
        baseline_result = attacked_clone.attempt_attack_objective(scenario)
        for e in telemetry:
            db.add(models.EvidenceRecord(run_id=run_id, kind="telemetry", ref=f"telemetry:{e['event_type']}:{e['asset_id']}",
                                         summary=e["message"], data=e))
            _emit(db, run_id, "telemetry", e["message"], agent="adversary_simulator", asset_id=e["asset_id"], payload=e)
            await _delay()
        db.commit()
        t_detected = time.monotonic()

        await set_state("TELEMETRY_COLLECTED", f"{len(telemetry)} synthetic telemetry events collected", "observer")
        obs = agents.observe(telemetry)
        db.add(models.AgentDecision(run_id=run_id, agent="observer", decision=obs.anomaly_type,
                                    justification=obs.summary, confidence=obs.confidence, model="deterministic",
                                    mode="offline", evidence_refs=obs.event_ids, asset_ids=obs.asset_ids)); db.commit()
        _emit(db, run_id, "agent_decision", obs.summary, agent="observer", payload=obs.model_dump())

        await set_state("INVESTIGATING", "Meta Muse Spark investigating evidence" if mode == "live" else "Investigating evidence (OFFLINE deterministic mode — no Meta inference)", "incident_investigator")
        hyp = await agents.investigate(scenario, obs, run_id)
        run.mode = hyp.mode; db.commit()
        db.add(models.AgentDecision(run_id=run_id, agent="incident_investigator", decision=hyp.hypothesis,
                                    justification="; ".join(hyp.confirmed), confidence=hyp.confidence,
                                    model=hyp.model, mode=hyp.mode, evidence_refs=hyp.evidence_refs,
                                    asset_ids=hyp.affected_assets)); db.commit()
        _emit(db, run_id, "agent_decision", hyp.hypothesis, agent="incident_investigator", payload=hyp.model_dump())
        await _delay()

        await set_state("DEFENSE_PROPOSED", "Defense strategist proposing countermeasure", "defense_strategist")
        proposal = await agents.propose_defense(scenario, hyp, run_id)
        db.add(models.DefenseProposal(run_id=run_id, actions=[a.model_dump() for a in proposal.actions],
                                      justification=proposal.justification, confidence=proposal.confidence, mode=proposal.mode)); db.commit()
        _emit(db, run_id, "agent_decision", proposal.justification, agent="defense_strategist", payload=proposal.model_dump())

        await set_state("POLICY_VALIDATING", "Deterministic policy engine validating proposal", "defense_executor")
        decisions = []
        for a in proposal.actions:
            d = policy_engine.evaluate(a.action_type, a.asset_id, a.params, TWIN)
            decisions.append(d)
            db.add(models.PolicyEvaluation(run_id=run_id, action_type=a.action_type, asset_id=a.asset_id,
                                           approved=d.approved, reasons=d.reasons))
            _emit(db, run_id, "policy_decision", f"{a.action_type} on {a.asset_id}: {'APPROVED' if d.approved else 'REJECTED'} — {'; '.join(d.reasons)}",
                  agent="defense_executor", asset_id=a.asset_id, payload=d.model_dump())
        db.commit()
        await _delay()

        await set_state("DEFENSE_APPLYING", "Applying approved simulated defenses", "defense_executor")
        t_contained = None
        for a, d in zip(proposal.actions, decisions):
            if not d.approved:
                _emit(db, run_id, "defense_rejected", f"Skipped rejected action {a.action_type}", agent="defense_executor", asset_id=a.asset_id)
                continue
            try:
                transition = TWIN.apply_action(a.action_type, a.asset_id, a.params)
                t_contained = time.monotonic()
                db.add(models.DefenseExecution(run_id=run_id, action_type=a.action_type, asset_id=a.asset_id, success=True, transition=transition))
                db.add(models.EvidenceRecord(run_id=run_id, kind="defense", ref=f"defense:{a.action_type}:{a.asset_id}", summary=str(transition), data=transition))
                _emit(db, run_id, "defense_applied", f"Applied {a.action_type} to {a.asset_id}", agent="defense_executor", asset_id=a.asset_id, payload=transition)
            except ValueError as e:
                db.add(models.DefenseExecution(run_id=run_id, action_type=a.action_type, asset_id=a.asset_id, success=False, transition={"error": str(e)}))
                _emit(db, run_id, "defense_failed", str(e), agent="defense_executor", asset_id=a.asset_id)
            db.commit()
            await _delay()

        await set_state("VERIFYING", "Verification Scientist replaying attack against modified twin", "verification_scientist")
        result = verify(scenario, baseline_twin, TWIN, baseline_result, t0, t_detected, t_contained)
        db.add(models.VerificationResultRow(run_id=run_id, outcome=result.outcome, invariant=result.invariant,
                                            checks=[c.model_dump() for c in result.checks], metrics=result.metrics))
        db.add(models.EvidenceRecord(run_id=run_id, kind="verification", ref=f"verification:{result.outcome}",
                                     summary=result.invariant, data=result.model_dump()))
        db.add(models.AgentDecision(run_id=run_id, agent="verification_scientist", decision=f"VERIFICATION {result.outcome}",
                                    justification=result.invariant, confidence=1.0 if result.outcome != "INCONCLUSIVE" else 0.4,
                                    model="deterministic-replay", mode="offline", evidence_refs=result.evidence_refs,
                                    asset_ids=[scenario["target_asset"]])); db.commit()
        _emit(db, run_id, "verification", f"Verification {result.outcome}: {result.invariant}",
              agent="verification_scientist", payload=result.model_dump())

        # persist model usage from client buffer
        for u in list(meta_client.usage):
            if u.get("run_id") == run_id:
                db.add(models.ModelUsage(run_id=run_id, model=u["model"], prompt_version=u["prompt_version"],
                                         prompt_tokens=u["prompt_tokens"], completion_tokens=u["completion_tokens"],
                                         latency_ms=u["latency_ms"], success=u["success"], error=u.get("error")))
        meta_client.usage = [u for u in meta_client.usage if u.get("run_id") != run_id]
        db.commit()

        run.metrics = result.metrics
        db.add(models.AssetStateSnapshot(run_id=run_id, label="post_remediation", snapshot=TWIN.snapshot())); db.commit()
        if _check_cancel(run_id):
            run.state = "FAILED"; run.error = "cancelled by operator"
        else:
            run.state = "COMPLETED"
        run.ended_at = datetime.now(timezone.utc); db.commit()
        _emit(db, run_id, "completed" if run.state == "COMPLETED" else "failed",
              f"Experiment {run.state} — verification {result.outcome}", payload={"verification": result.model_dump(), "metrics": result.metrics})
    except asyncio.CancelledError:
        run = db.get(models.SimulationRun, run_id)
        if run:
            run.state = "FAILED"; run.error = "cancelled"; run.ended_at = datetime.now(timezone.utc); db.commit()
            _emit(db, run_id, "failed", "Experiment cancelled")
    except Exception as e:  # noqa: BLE001 - honest failure state
        run = db.get(models.SimulationRun, run_id)
        if run:
            run.state = "FAILED"; run.error = f"{type(e).__name__}: {e}"; run.ended_at = datetime.now(timezone.utc); db.commit()
            _emit(db, run_id, "failed", run.error)
    finally:
        _cancelled.discard(run_id)
        db.close()
