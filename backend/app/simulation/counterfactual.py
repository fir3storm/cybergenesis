"""Counterfactual time machine: fork a finished run at its decision point.

The fork restores the run's "attacked" snapshot (the moment Blue had to
decide), applies an ALTERNATIVE candidate from that run's simulated
candidate table through the same deterministic policy engine, and
re-verifies with the same verifier. No LLM is involved, so the fork is
exactly reproducible. The original run is never modified.
"""

from datetime import UTC, datetime

from app import models
from app.policies.engine import evaluate
from app.simulation.scenarios import SCENARIOS
from app.simulation.twin import DigitalTwin
from app.verification.verifier import verify

FORK_POINTS = ("attacked",)


class ForkError(ValueError):
    pass


def scenario_for_run(db, run: models.SimulationRun) -> dict:
    if run.custom_scenario_id:
        row = db.get(models.CustomScenarioDefinition, run.custom_scenario_id)
        if not row:
            raise ForkError(f"custom scenario not found: {run.custom_scenario_id}")
        return {**row.definition, "id": row.id, "name": row.name}
    if run.scenario_id not in SCENARIOS:
        raise ForkError(f"unknown scenario: {run.scenario_id}")
    return SCENARIOS[run.scenario_id]


def _structure(db, run: models.SimulationRun) -> DigitalTwin:
    if run.custom_twin_id:
        trow = db.get(models.CustomTwinDefinition, run.custom_twin_id)
        if not trow:
            raise ForkError(f"custom twin not found: {run.custom_twin_id}")
        return DigitalTwin.from_dict(trow.assets, trow.connections)
    return DigitalTwin()


def summarize(verification: dict | None, actions: list[dict]) -> dict:
    m = (verification or {}).get("metrics", {})
    return {
        "outcome": (verification or {}).get("outcome"),
        "effectiveness_pct": m.get("defense_effectiveness_pct"),
        "disrupted": m.get("operational_impact_disrupted_legit_paths"),
        "risk_after_pct": m.get("risk_after_pct"),
        "users_affected": m.get("users_affected"),
        "rounds": len(m.get("rounds") or []) or None,
        "actions": [f"{a.get('action_type')}:{a.get('asset_id')}" for a in actions],
    }


def _delta(a: dict, b: dict) -> dict:
    out = {}
    for k in ("effectiveness_pct", "disrupted", "risk_after_pct", "users_affected", "rounds"):
        if isinstance(a.get(k), (int, float)) and isinstance(b.get(k), (int, float)):
            out[k] = round(b[k] - a[k], 2)
    out["verdict_changed"] = a.get("outcome") != b.get("outcome")
    return out


def _timeline(db, run_id: str) -> list[dict]:
    rows = (db.query(models.SimulationEvent).filter_by(run_id=run_id)
            .order_by(models.SimulationEvent.seq).all())
    return [{"seq": e.seq, "event_type": e.event_type, "message": e.message} for e in rows]


def fork_run(db, run_id: str, choose_candidate: int | str, at_event: str = "attacked") -> dict:
    run = db.get(models.SimulationRun, run_id)
    if run is None:
        raise ForkError("experiment not found")
    if at_event not in FORK_POINTS:
        raise ForkError(f"fork point must be one of {FORK_POINTS}")
    candidates = (run.metrics or {}).get("candidates") or []
    if not candidates:
        raise ForkError("run has no simulated candidates to fork from")
    if isinstance(choose_candidate, int):
        if not 0 <= choose_candidate < len(candidates):
            raise ForkError(f"candidate index out of range (0..{len(candidates) - 1})")
        cand = candidates[choose_candidate]
    else:
        cand = next((c for c in candidates if c.get("label") == choose_candidate), None)
        if cand is None:
            raise ForkError(f"no candidate labelled '{choose_candidate}'")

    snaps = {s.label: s.snapshot for s in db.query(models.AssetStateSnapshot).filter_by(run_id=run_id).all()}
    if "baseline" not in snaps or at_event not in snaps:
        raise ForkError(f"run is missing the '{at_event}' snapshot (only finished runs can be forked)")
    scenario = scenario_for_run(db, run)

    baseline = _structure(db, run); baseline.restore(snaps["baseline"])
    attacked = _structure(db, run); attacked.restore(snaps[at_event])
    baseline_result = attacked.clone().attempt_attack_objective(scenario)
    after = attacked.clone()

    fork = models.SimulationRun(scenario_id=run.scenario_id, custom_twin_id=run.custom_twin_id,
                                custom_scenario_id=run.custom_scenario_id, seed=run.seed, state="RUNNING",
                                mode="offline", started_at=datetime.now(UTC))
    db.add(fork); db.commit(); db.refresh(fork)
    seq = {"n": 0}

    def emit(event_type: str, message: str, agent: str | None = None, asset_id: str | None = None, payload: dict | None = None):
        seq["n"] += 1
        db.add(models.SimulationEvent(run_id=fork.id, event_type=event_type, agent=agent, asset_id=asset_id,
                                      message=message, payload=payload or {}, seq=seq["n"]))

    emit("fork", f"Counterfactual fork of run {run_id} at '{at_event}': choosing '{cand.get('label')}' instead",
         agent="verification_scientist", payload={"parent_run_id": run_id, "at_event": at_event, "candidate": cand})
    db.add(models.AssetStateSnapshot(run_id=fork.id, label="baseline", snapshot=baseline.snapshot()))
    db.add(models.AssetStateSnapshot(run_id=fork.id, label="attacked", snapshot=attacked.snapshot()))

    applied: list[dict] = []
    rejected: list[str] = []
    for a in cand.get("actions", []):
        d = evaluate(a["action_type"], a["asset_id"], a.get("params", {}), after)
        db.add(models.PolicyEvaluation(run_id=fork.id, action_type=a["action_type"], asset_id=a["asset_id"],
                                       approved=d.approved, reasons=d.reasons))
        emit("policy_decision", f"{a['action_type']} on {a['asset_id']}: {'APPROVED' if d.approved else 'REJECTED'} — {'; '.join(d.reasons)}",
             agent="defense_executor", asset_id=a["asset_id"])
        if not d.approved:
            rejected.append(f"{a['action_type']}: {'; '.join(d.reasons)}")
            continue
        try:
            transition = after.apply_action(a["action_type"], a["asset_id"], a.get("params", {}))
        except ValueError as e:
            rejected.append(f"{a['action_type']}: {e}")
            continue
        applied.append(a)
        db.add(models.DefenseExecution(run_id=fork.id, action_type=a["action_type"], asset_id=a["asset_id"],
                                       success=True, transition=transition))
        emit("defense_applied", f"Applied {a['action_type']} to {a['asset_id']} (counterfactual)", agent="defense_executor",
             asset_id=a["asset_id"])

    t_detected = float((run.metrics or {}).get("time_to_detect_s") or 0.4)
    t_contained = t_detected + 0.4 * len(applied) if applied else None
    res = verify(scenario, baseline, after, baseline_result, 0.0, t_detected, t_contained)
    res.metrics.update({"forked_from": run_id, "fork_point": at_event, "counterfactual_candidate": cand.get("label"),
                        "policy_rejections": rejected, "candidates": candidates})
    db.add(models.VerificationResultRow(run_id=fork.id, outcome=res.outcome, invariant=res.invariant,
                                        checks=[c.model_dump() for c in res.checks], metrics=res.metrics))
    db.add(models.AssetStateSnapshot(run_id=fork.id, label="post_remediation", snapshot=after.snapshot()))
    emit("verification", f"Counterfactual verification {res.outcome}: {res.invariant}", agent="verification_scientist",
         payload=res.model_dump())
    fork.state = "COMPLETED"
    fork.ended_at = datetime.now(UTC)
    fork.metrics = res.metrics
    emit("completed", f"Counterfactual COMPLETED — verification {res.outcome}")
    db.commit()

    orig_ver = (db.query(models.VerificationResultRow).filter_by(run_id=run_id)
                .order_by(models.VerificationResultRow.created_at.desc()).first())
    orig_actions = [{"action_type": e.action_type, "asset_id": e.asset_id}
                    for e in db.query(models.DefenseExecution).filter_by(run_id=run_id).all()]
    original = summarize({"outcome": orig_ver.outcome, "metrics": orig_ver.metrics} if orig_ver else None, orig_actions)
    forked = summarize({"outcome": res.outcome, "metrics": res.metrics}, applied)
    original_twin = _structure(db, run)
    original_twin.restore(snaps.get("post_remediation", snaps[at_event]))
    return {"fork_id": fork.id, "parent_run_id": run_id, "at_event": at_event, "candidate": cand.get("label"),
            "original": original, "fork": forked, "delta": _delta(original, forked),
            "original_twin": original_twin.to_dict(), "fork_twin": after.to_dict(),
            "original_timeline": _timeline(db, run_id), "fork_timeline": _timeline(db, fork.id)}
