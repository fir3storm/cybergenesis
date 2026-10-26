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
from app.schemas import CreateExperiment, TwinActionRequest
from app.simulation.scenarios import SCENARIOS

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
    return {"id": r.id, "scenario_id": r.scenario_id, "seed": r.seed, "state": r.state, "mode": r.mode,
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
async def run_exp(run_id: str, db: Session = Depends(get_db)):
    r = db.get(models.SimulationRun, run_id)
    if not r:
        raise HTTPException(404, "experiment not found")
    if r.state not in ("IDLE", "FAILED", "COMPLETED"):
        raise HTTPException(409, f"experiment already in state {r.state}")
    asyncio.create_task(orchestrator.run_experiment(run_id))
    return {"started": True, "run_id": run_id}


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
    return {"run": _run_dict(r),
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
