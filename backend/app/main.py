import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app import models
from app.db import get_db, init_db
from app.integrations.meta_client import meta_client
from app.orchestration import orchestrator
from app.policies import engine as policy_engine
from pydantic import BaseModel

from app.schemas import (CreateCustomExperiment, CreateCustomScenario, CreateCustomTwin,
                         CreateExperiment, TwinActionRequest)
from app.simulation.component_library import ASSET_TYPES, library
from app.simulation.scenarios import SCENARIOS
from app.simulation.twin import ALLOWED_ACTIONS, ATTACK_STEP_TYPES, DigitalTwin

@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    db = next(get_db())
    try:
        for sid, s in SCENARIOS.items():
            if not db.get(models.Scenario, sid):
                db.add(models.Scenario(id=sid, name=s["name"], description=s["description"], definition=s))
        if not db.query(models.User).first():
            db.add(models.User())
        db.commit()
    finally:
        db.close()
    yield


app = FastAPI(title="CYBERGENESIS", description="Autonomous Self-Defending Digital Twin — synthetic simulation only", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


def _run_dict(r: models.SimulationRun) -> dict:
    return {"id": r.id, "scenario_id": r.scenario_id, "custom_twin_id": r.custom_twin_id,
            "custom_scenario_id": r.custom_scenario_id, "seed": r.seed, "state": r.state, "mode": r.mode,
            "error": r.error, "metrics": r.metrics or {},
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "ended_at": r.ended_at.isoformat() if r.ended_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None}


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "cybergenesis", "synthetic_only": True}


@app.get("/api/models/status")
async def model_status():
    h = await meta_client.health()
    return {**h, "provider": "meta", "base_url": meta_client.base, "api_key_exposed": False}


@app.get("/api/twin")
def get_twin():
    return orchestrator.TWIN.to_dict()


@app.get("/api/twin/assets")
def get_assets():
    return orchestrator.TWIN.to_dict()["assets"]


@app.get("/api/twin/connections")
def get_connections():
    return orchestrator.TWIN.to_dict()["connections"]


@app.post("/api/twin/reset")
def reset_twin():
    orchestrator.TWIN.reset()
    return {"reset": True, "twin": orchestrator.TWIN.to_dict()}


@app.post("/api/twin/action")
def twin_action(body: TwinActionRequest):
    """Direct manual defense control — still policy-gated, simulation only."""
    d = policy_engine.evaluate(body.action_type, body.asset_id, body.params, orchestrator.TWIN)
    if not d.approved:
        raise HTTPException(403, detail={"approved": False, "reasons": d.reasons})
    try:
        transition = orchestrator.TWIN.apply_action(body.action_type, body.asset_id, body.params)
    except ValueError as e:
        raise HTTPException(400, detail=str(e)) from e
    return {"approved": True, "transition": transition, "twin": orchestrator.TWIN.to_dict()}


@app.get("/api/scenarios")
def list_scenarios():
    return [{k: s[k] for k in ("id", "name", "description", "severity", "source_asset", "target_asset", "invariant", "objectives")} for s in SCENARIOS.values()]


@app.get("/api/scenarios/custom")
def list_custom_scenarios_early(db: Session = Depends(get_db)):
    # registered before /{scenario_id} so "custom" is not captured as an id
    return [_scenario_row(r) for r in db.query(models.CustomScenarioDefinition).order_by(models.CustomScenarioDefinition.created_at.desc()).all()]


@app.get("/api/scenarios/{scenario_id}")
def get_scenario(scenario_id: str):
    if scenario_id not in SCENARIOS:
        raise HTTPException(404, "scenario not found")
    return SCENARIOS[scenario_id]


@app.post("/api/experiments", status_code=201)
def create_experiment(body: CreateExperiment, db: Session = Depends(get_db)):
    if body.scenario_id not in SCENARIOS:
        raise HTTPException(422, "unknown scenario_id")
    run = models.SimulationRun(scenario_id=body.scenario_id, seed=body.seed)
    db.add(run); db.commit(); db.refresh(run)
    return _run_dict(run)


@app.get("/api/experiments")
def list_experiments(db: Session = Depends(get_db)):
    return [_run_dict(r) for r in db.query(models.SimulationRun).order_by(models.SimulationRun.created_at.desc()).limit(50)]


@app.get("/api/experiments/{run_id}")
def get_experiment(run_id: str, db: Session = Depends(get_db)):
    r = db.get(models.SimulationRun, run_id)
    if not r:
        raise HTTPException(404, "experiment not found")
    return _run_dict(r)


@app.post("/api/experiments/{run_id}/run")
async def run_exp(run_id: str, step_delay_ms: int | None = None, db: Session = Depends(get_db)):
    r = db.get(models.SimulationRun, run_id)
    if not r:
        raise HTTPException(404, "experiment not found")
    if r.state not in ("IDLE", "FAILED", "COMPLETED"):
        raise HTTPException(409, f"experiment already in state {r.state}")
    delay = None if step_delay_ms is None else max(0, min(step_delay_ms, 2000))
    asyncio.create_task(orchestrator.run_experiment(run_id, step_delay_ms=delay))
    return {"started": True, "run_id": run_id, "step_delay_ms": delay}


@app.get("/api/experiments/{run_id}/snapshots")
def exp_snapshots(run_id: str, db: Session = Depends(get_db)):
    if not db.get(models.SimulationRun, run_id):
        raise HTTPException(404, "experiment not found")
    rows = db.query(models.AssetStateSnapshot).filter_by(run_id=run_id).order_by(models.AssetStateSnapshot.created_at).all()
    return [{"label": r.label, "snapshot": r.snapshot, "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]


@app.post("/api/experiments/{run_id}/cancel")
def cancel_exp(run_id: str, db: Session = Depends(get_db)):
    if not db.get(models.SimulationRun, run_id):
        raise HTTPException(404, "experiment not found")
    orchestrator.cancel(run_id)
    return {"cancelling": True, "run_id": run_id}


@app.get("/api/experiments/{run_id}/events")
def exp_events(run_id: str, db: Session = Depends(get_db)):
    rows = db.query(models.SimulationEvent).filter_by(run_id=run_id).order_by(models.SimulationEvent.seq).all()
    return [{"id": e.id, "event_type": e.event_type, "agent": e.agent, "asset_id": e.asset_id,
             "message": e.message, "payload": e.payload, "seq": e.seq,
             "timestamp": e.created_at.isoformat() if e.created_at else None} for e in rows]


@app.get("/api/experiments/{run_id}/results")
def exp_results(run_id: str, db: Session = Depends(get_db)):
    r = db.get(models.SimulationRun, run_id)
    if not r:
        raise HTTPException(404, "experiment not found")
    ver = db.query(models.VerificationResultRow).filter_by(run_id=run_id).order_by(models.VerificationResultRow.created_at.desc()).first()
    dec = db.query(models.AgentDecision).filter_by(run_id=run_id).all()
    pol = db.query(models.PolicyEvaluation).filter_by(run_id=run_id).all()
    exe = db.query(models.DefenseExecution).filter_by(run_id=run_id).all()
    usage = db.query(models.ModelUsage).filter_by(run_id=run_id).all()
    return {"run": _run_dict(r),
            "usage": {"prompt_tokens": sum(u.prompt_tokens for u in usage), "completion_tokens": sum(u.completion_tokens for u in usage),
                      "calls": len(usage), "models": sorted({u.model for u in usage})},
            "verification": {"outcome": ver.outcome, "invariant": ver.invariant, "checks": ver.checks, "metrics": ver.metrics} if ver else None,
            "decisions": [{"agent": d.agent, "decision": d.decision, "justification": d.justification, "confidence": d.confidence, "model": d.model, "mode": d.mode, "evidence_refs": d.evidence_refs, "asset_ids": d.asset_ids} for d in dec],
            "policy": [{"action_type": p.action_type, "asset_id": p.asset_id, "approved": p.approved, "reasons": p.reasons} for p in pol],
            "executions": [{"action_type": e.action_type, "asset_id": e.asset_id, "success": e.success, "transition": e.transition} for e in exe]}


@app.get("/api/experiments/{run_id}/evidence")
def exp_evidence(run_id: str, db: Session = Depends(get_db)):
    rows = db.query(models.EvidenceRecord).filter_by(run_id=run_id).all()
    return [{"id": e.id, "kind": e.kind, "ref": e.ref, "summary": e.summary, "data": e.data,
             "timestamp": e.created_at.isoformat() if e.created_at else None} for e in rows]


@app.get("/api/experiments/{run_id}/report")
def exp_report(run_id: str, db: Session = Depends(get_db)):
    data = exp_results(run_id, db)
    ev = exp_evidence(run_id, db)
    report = {**data, "evidence_count": len(ev), "evidence": ev,
              "conclusion": "CYBERGENESIS does not merely detect cyberattacks. It tests defenses and verifies resilience."}
    return report


@app.get("/api/experiments/{run_id}/report/markdown")
def exp_report_markdown(run_id: str, db: Session = Depends(get_db)):
    from fastapi.responses import PlainTextResponse

    r = db.get(models.SimulationRun, run_id)
    if not r:
        raise HTTPException(404, "experiment not found")
    sc = SCENARIOS.get(r.scenario_id, {})
    data = exp_results(run_id, db)
    ver = data["verification"] or {}
    metrics = ver.get("metrics", {})
    mode_label = "LIVE META AI (muse-spark-1.3)" if r.mode == "live" else "OFFLINE SIMULATION (deterministic, no Meta inference)"
    lines = [
        "# CYBERGENESIS Experiment Report", "",
        f"**Run ID:** {r.id} · **Scenario:** {sc.get('name', r.scenario_id)} · **Seed:** {r.seed}",
        f"**Mode:** {mode_label}",
        f"**State:** {r.state} · **Started:** {r.started_at.isoformat() if r.started_at else '—'} · **Ended:** {r.ended_at.isoformat() if r.ended_at else '—'}",
        f"**Model usage:** {data['usage']['prompt_tokens']} prompt + {data['usage']['completion_tokens']} completion tokens across {data['usage']['calls']} calls",
        "", "## Incident & Agent Decisions",
    ]
    for d in data["decisions"]:
        lines.append(f"- **{d['agent']}** ({d['model']}, mode={d['mode']}, confidence {d['confidence']}): {d['decision']}")
        if d["justification"]:
            lines.append(f"  > {d['justification']}")
    lines += ["", "## Defense Proposal & Policy"]
    for p in data["policy"]:
        lines.append(f"- {p['action_type']} on {p['asset_id']}: {'✅ APPROVED' if p['approved'] else '❌ REJECTED'} — {'; '.join(p['reasons'])}")
    for e in data["executions"]:
        lines.append(f"- Executed {e['action_type']} on {e['asset_id']}: success={e['success']} · {e['transition']}")
    lines += ["", "## Verification", f"**Invariant:** {ver.get('invariant', '—')}", "", "| Check | Result | Detail |", "|---|---|---|"]
    for c in ver.get("checks", []):
        lines.append(f"| {c['name']} | {'✅ PASS' if c['passed'] else '❌ FAIL'} | {c['detail']} |")
    lines += ["", f"**Outcome: {ver.get('outcome', '—')}** · **Effectiveness:** {metrics.get('defense_effectiveness_pct', '—')}% "
              f"· **Time to detect:** {metrics.get('time_to_detect_s', '—')}s · **Time to contain:** {metrics.get('time_to_contain_s', '—')}s "
              f"· **Operational cost:** {metrics.get('operational_impact_disrupted_legit_paths', '—')} legitimate paths disrupted",
              f"· **Path before:** {metrics.get('baseline_path')} · **Path after:** {metrics.get('after_path')}",
              "", "_All data is synthetic. Generated by CYBERGENESIS — it does not merely detect attacks; it tests defenses and verifies resilience._"]
    return PlainTextResponse("\n".join(lines), media_type="text/markdown")


# --- component library + custom twins/scenarios -------------------------

@app.get("/api/benchmark")
def get_benchmark():
    """Latest benchmark run (scripts/benchmark.py). Honest about offline vs live scope."""
    import json as _json
    from pathlib import Path

    p = Path(__file__).resolve().parents[2] / "scripts" / "benchmark_results.json"
    if not p.exists():
        return {"available": False, "detail": "run scripts/benchmark.py to generate", "rows": []}
    rows = _json.loads(p.read_text(encoding="utf-8"))

    def agg(key: str) -> dict:
        vals = [r[key] for r in rows]
        return {"pass_rate_pct": round(100 * sum(v["pass"] for v in vals) / len(vals), 1),
                "mean_effectiveness_pct": round(sum(v["effectiveness"] for v in vals) / len(vals), 1),
                "mean_optimality_gap": round(sum(v["gap"] for v in vals if v["gap"] is not None) / max(1, sum(1 for v in vals if v["gap"] is not None)), 2),
                "mean_disrupted": round(sum(v["disrupted"] for v in vals) / len(vals), 2)}

    return {"available": True, "pairs": len(rows), "scope": "50 seeded pairs, offline/simulate defenders; live Muse Spark spot-checked on 4 builtin scenarios",
            "summary": {k: agg(k) for k in ("none", "offline", "simulate")}, "rows": rows}


@app.get("/api/library")
def get_library():
    return library()


def _twin_row(r: models.CustomTwinDefinition) -> dict:
    return {"id": r.id, "name": r.name, "description": r.description, "assets": r.assets,
            "connections": r.connections, "created_at": r.created_at.isoformat() if r.created_at else ""}


def _validate_twin(body: CreateCustomTwin) -> DigitalTwin:
    if len(body.assets) < 2:
        raise HTTPException(422, "a twin needs at least 2 assets")
    known_types = {a["id"] for a in ASSET_TYPES}
    for a in body.assets:
        if a.asset_type not in known_types:
            raise HTTPException(422, f"unknown asset_type '{a.asset_type}' (see /api/library)")
    try:
        return DigitalTwin.from_dict([a.model_dump() for a in body.assets],
                                     [c.model_dump() for c in body.connections])
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@app.post("/api/twins/custom", status_code=201)
def create_custom_twin(body: CreateCustomTwin, db: Session = Depends(get_db)):
    _validate_twin(body)
    row = models.CustomTwinDefinition(name=body.name, description=body.description,
                                      assets=[a.model_dump() for a in body.assets],
                                      connections=[c.model_dump() for c in body.connections])
    db.add(row); db.commit(); db.refresh(row)
    return _twin_row(row)


@app.get("/api/twins/custom")
def list_custom_twins(db: Session = Depends(get_db)):
    return [_twin_row(r) for r in db.query(models.CustomTwinDefinition).order_by(models.CustomTwinDefinition.created_at.desc()).all()]


@app.get("/api/twins/custom/{twin_id}")
def get_custom_twin(twin_id: str, db: Session = Depends(get_db)):
    row = db.get(models.CustomTwinDefinition, twin_id)
    if not row:
        raise HTTPException(404, "custom twin not found")
    return _twin_row(row)


@app.delete("/api/twins/custom/{twin_id}")
def delete_custom_twin(twin_id: str, db: Session = Depends(get_db)):
    row = db.get(models.CustomTwinDefinition, twin_id)
    if not row:
        raise HTTPException(404, "custom twin not found")
    db.delete(row); db.commit()
    return {"deleted": True, "id": twin_id}


@app.post("/api/twins/custom/{twin_id}/activate")
def activate_custom_twin(twin_id: str, db: Session = Depends(get_db)):
    row = db.get(models.CustomTwinDefinition, twin_id)
    if not row:
        raise HTTPException(404, "custom twin not found")
    twin = DigitalTwin.from_dict(row.assets, row.connections)
    orchestrator.activate_twin(twin)
    return {"activated": True, "id": twin_id, "twin": twin.to_dict()}


class FromImageRequest(BaseModel):
    image_data_url: str
    name: str = "Whiteboard Twin"


@app.post("/api/twins/from-image", status_code=201)
async def twin_from_image(body: FromImageRequest, db: Session = Depends(get_db)):
    """Muse Spark multimodal: network diagram photo -> validated twin definition."""
    from app.integrations.meta_client import ProviderUnavailable

    if not body.image_data_url.startswith("data:image/"):
        raise HTTPException(422, "image_data_url must be a data:image/... URL")
    prompt = (
        "Read this network diagram and return ONLY JSON: {\"assets\": [{\"id\": str, \"name\": str, "
        "\"asset_type\": one of [gateway, firewall, web_server, app_server, database, identity, workstation, file_server, sensor], "
        "\"zone\": str, \"pos\": [x, y, z]}], \"connections\": [{\"source\": str, \"target\": str, \"traversable\": bool}]}. "
        "Use lowercase hyphenated ids (e.g. web-server). Lay assets out left-to-right by trust zone, x from -8 to 8, y=1, z spread -4..4. "
        "Only include assets/connections actually visible in the diagram."
    )
    try:
        data, _usage = await meta_client.chat_vision_json(prompt, body.image_data_url)
    except ProviderUnavailable as e:
        raise HTTPException(503, f"Meta vision unavailable: {e}") from e
    try:
        twin_body = CreateCustomTwin(name=body.name, description="Generated from uploaded diagram via Meta vision",
                                     assets=data.get("assets", []), connections=data.get("connections", []))
    except Exception as e:  # noqa: BLE001 - model output is untrusted
        raise HTTPException(422, f"model output failed schema validation: {e}") from e
    _validate_twin(twin_body)
    row = models.CustomTwinDefinition(name=twin_body.name, description=twin_body.description,
                                      assets=[a.model_dump() for a in twin_body.assets],
                                      connections=[c.model_dump() for c in twin_body.connections])
    db.add(row); db.commit(); db.refresh(row)
    return _twin_row(row)


@app.post("/api/twins/builtin/activate")
def activate_builtin_twin():
    twin = DigitalTwin()
    orchestrator.activate_twin(twin)
    return {"activated": True, "id": "builtin", "twin": twin.to_dict()}


def _scenario_row(r: models.CustomScenarioDefinition) -> dict:
    return {"id": r.id, "name": r.name, "description": r.description, "definition": r.definition,
            "created_at": r.created_at.isoformat() if r.created_at else ""}


def _validate_scenario(body: CreateCustomScenario) -> dict:
    if body.verification_kind not in ("reachability", "identity_access"):
        raise HTTPException(422, "verification_kind must be reachability or identity_access")
    if not body.attack_steps:
        raise HTTPException(422, "a scenario needs at least 1 attack step")
    for st in body.attack_steps:
        if st.type not in ATTACK_STEP_TYPES:
            raise HTTPException(422, f"attack step type '{st.type}' not in allowlist (see /api/library)")
    for a in body.expected_defense:
        if a.get("action_type") not in ALLOWED_ACTIONS:
            raise HTTPException(422, f"defense action '{a.get('action_type')}' not in allowlist")
    return {"source_asset": body.source_asset, "target_asset": body.target_asset, "severity": body.severity,
            "invariant": body.invariant or f"{body.source_asset} cannot reach/affect {body.target_asset}",
            "objectives": body.objectives or ["custom_objective"], "verification_kind": body.verification_kind,
            "identity": body.identity, "attack_steps": [s.model_dump() for s in body.attack_steps],
            "expected_defense": body.expected_defense, "description": body.description}


@app.post("/api/scenarios/custom", status_code=201)
def create_custom_scenario(body: CreateCustomScenario, db: Session = Depends(get_db)):
    definition = _validate_scenario(body)
    row = models.CustomScenarioDefinition(name=body.name, description=body.description, definition=definition)
    db.add(row); db.commit(); db.refresh(row)
    return _scenario_row(row)


@app.get("/api/scenarios/custom/{scenario_id}")
def get_custom_scenario(scenario_id: str, db: Session = Depends(get_db)):
    row = db.get(models.CustomScenarioDefinition, scenario_id)
    if not row:
        raise HTTPException(404, "custom scenario not found")
    return _scenario_row(row)


@app.delete("/api/scenarios/custom/{scenario_id}")
def delete_custom_scenario(scenario_id: str, db: Session = Depends(get_db)):
    row = db.get(models.CustomScenarioDefinition, scenario_id)
    if not row:
        raise HTTPException(404, "custom scenario not found")
    db.delete(row); db.commit()
    return {"deleted": True, "id": scenario_id}


@app.post("/api/experiments/custom", status_code=201)
def create_custom_experiment(body: CreateCustomExperiment, db: Session = Depends(get_db)):
    if body.custom_scenario_id:
        if not db.get(models.CustomScenarioDefinition, body.custom_scenario_id):
            raise HTTPException(422, "unknown custom_scenario_id")
        scenario_id = body.custom_scenario_id
    elif body.scenario_id:
        if body.scenario_id not in SCENARIOS:
            raise HTTPException(422, "unknown scenario_id")
        scenario_id = body.scenario_id
    else:
        raise HTTPException(422, "provide custom_scenario_id or scenario_id")
    if body.custom_twin_id and not db.get(models.CustomTwinDefinition, body.custom_twin_id):
        raise HTTPException(422, "unknown custom_twin_id")
    run = models.SimulationRun(scenario_id=scenario_id, seed=body.seed,
                               custom_twin_id=body.custom_twin_id, custom_scenario_id=body.custom_scenario_id)
    db.add(run); db.commit(); db.refresh(run)
    return _run_dict(run)


@app.websocket("/ws/experiments/{run_id}")
async def ws_exp(ws: WebSocket, run_id: str):
    await ws.accept()
    q = orchestrator.subscribe(run_id)
    try:
        # replay stored events first
        db = next(get_db())
        try:
            rows = db.query(models.SimulationEvent).filter_by(run_id=run_id).order_by(models.SimulationEvent.seq).all()
            for e in rows:
                await ws.send_text(json.dumps({"event_type": e.event_type, "run_id": run_id, "agent": e.agent,
                                               "asset_id": e.asset_id, "message": e.message, "payload": e.payload, "seq": e.seq}))
        finally:
            db.close()
        while True:
            data = await q.get()
            await ws.send_text(json.dumps(data))
    except WebSocketDisconnect:
        pass
    finally:
        orchestrator.unsubscribe(run_id, q)
