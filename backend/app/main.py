import asyncio
import html
import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import models
from app.agents.generative import architect_twin, author_scenario
from app.core.config import settings
from app.db import get_db, init_db
from app.integrations.meta_client import meta_client
from app.orchestration import orchestrator
from app.policies import engine as policy_engine
from app.schemas import CreateCustomExperiment, CreateCustomScenario, CreateCustomTwin, CreateExperiment, TwinActionRequest
from app.simulation.component_library import ASSET_TYPES, library
from app.simulation.scenarios import SCENARIOS
from app.simulation.twin import ALLOWED_ACTIONS, ATTACK_STEP_TYPES, DigitalTwin

TERMINAL_RUN_STATES = ("COMPLETED", "FAILED")

logger = logging.getLogger(__name__)


def _on_experiment_done(run_id: str, task: asyncio.Task) -> None:
    orchestrator.unregister_task(run_id, task)
    if task.cancelled():
        logger.warning("experiment task cancelled run_id=%s", run_id)
        return
    exc = task.exception()
    if exc is not None:
        logger.error("experiment task failed run_id=%s", run_id, exc_info=(type(exc), exc, exc.__traceback__))


def sweep_stale_runs(db: Session) -> int:
    """Mark runs left in non-terminal states by a previous backend process.

    The frontend only treats COMPLETED/FAILED as terminal (its polling stops
    on those two), so a distinct ABORTED state would strand the UI; the
    aborted reason is therefore carried in ``error`` on a FAILED row.
    """
    stale = (db.query(models.SimulationRun)
             .filter(~models.SimulationRun.state.in_(TERMINAL_RUN_STATES)).all())
    for row in stale:
        row.state = "FAILED"
        row.error = "ABORTED: backend restarted"
        row.ended_at = datetime.now(UTC)
    if stale:
        db.commit()
    return len(stale)


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
        sweep_stale_runs(db)
    finally:
        db.close()
    yield
    active = orchestrator.active_runs()
    if active:
        logger.warning("shutdown with %d experiment task(s) still running: %s", len(active), ", ".join(sorted(active)))


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
    return {**h, "provider": meta_client.provider_id, "provider_label": meta_client.provider_label,
            "base_url": meta_client.base, "api_key_exposed": False}


@app.get("/api/settings/providers")
def settings_providers():
    from app.integrations.providers import public_catalogue

    return {"providers": public_catalogue(), "active": meta_client.provider_id, "api_keys_exposed": False}


class ProviderActivate(BaseModel):
    provider: str
    api_key: str | None = None
    model: str | None = None
    base_url: str | None = None


@app.post("/api/settings/provider")
async def settings_activate_provider(body: ProviderActivate):
    from app.integrations import providers

    try:
        cfg = providers.activate(body.provider, api_key=body.api_key, model=body.model, base_url=body.base_url)
    except ValueError as e:
        raise HTTPException(422, str(e))
    meta_client.apply_provider(cfg)
    h = await meta_client.health()
    return {"active": cfg["id"], "provider_label": cfg["label"], "model": cfg["model"], "base_url": cfg["base_url"],
            "configured": bool(cfg["api_key"] and cfg["model"]), **h, "api_key_exposed": False}


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


@app.post("/api/demo/reset")
def demo_reset():
    """Seeded clean demo state: builtin twin activated, pending approvals
    cleared. Historical runs are kept (audit trail); only the display
    twin and approval queue are reset."""
    twin = DigitalTwin()
    orchestrator.activate_twin(twin)
    cleared = orchestrator.clear_pending_approvals()
    return {"reset": True, "cleared_approvals": cleared, "twin": twin.to_dict()}


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
    return [{**{k: s[k] for k in ("id", "name", "description", "severity", "source_asset", "target_asset", "invariant", "objectives")},
             "max_rounds": s.get("max_rounds")} for s in SCENARIOS.values()]


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
    task = asyncio.create_task(orchestrator.run_experiment(run_id, step_delay_ms=delay))
    orchestrator.register_task(run_id, task)
    task.add_done_callback(lambda done, _run_id=run_id: _on_experiment_done(_run_id, done))
    return {"started": True, "run_id": run_id, "step_delay_ms": delay}


@app.get("/api/experiments/{run_id}/snapshots")
def exp_snapshots(run_id: str, db: Session = Depends(get_db)):
    if not db.get(models.SimulationRun, run_id):
        raise HTTPException(404, "experiment not found")
    rows = db.query(models.AssetStateSnapshot).filter_by(run_id=run_id).order_by(models.AssetStateSnapshot.created_at).all()
    return [{"label": r.label, "snapshot": r.snapshot, "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]


class ApprovalRequest(BaseModel):
    approved: bool


@app.post("/api/experiments/{run_id}/approve")
def approve_exp(run_id: str, body: ApprovalRequest, db: Session = Depends(get_db)):
    if not db.get(models.SimulationRun, run_id):
        raise HTTPException(404, "experiment not found")
    if not orchestrator.resolve_approval(run_id, body.approved):
        raise HTTPException(409, "no approval pending for this run")
    return {"recorded": True, "approved": body.approved, "run_id": run_id}


@app.post("/api/experiments/{run_id}/deny")
def deny_exp(run_id: str, db: Session = Depends(get_db)):
    if not db.get(models.SimulationRun, run_id):
        raise HTTPException(404, "experiment not found")
    if not orchestrator.resolve_approval(run_id, False):
        raise HTTPException(409, "no approval pending for this run")
    return {"recorded": True, "approved": False, "run_id": run_id}


def _lan_base_url() -> str:
    if settings.public_base_url:
        return settings.public_base_url.rstrip("/")
    import socket

    ip = "127.0.0.1"
    try:  # UDP connect sends no packets; it only selects the outbound interface
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
    except OSError:
        pass
    return f"http://{ip}:8000"


@app.get("/api/experiments/{run_id}/approval")
def approval_status(run_id: str, db: Session = Depends(get_db)):
    if not db.get(models.SimulationRun, run_id):
        raise HTTPException(404, "experiment not found")
    p = orchestrator.pending_approval(run_id)
    if not p:
        return {"pending": False}
    return {"pending": True, "label": p["label"], "actions": p["actions"], "disrupted": p["disrupted"],
            "expires_in_s": max(0, int(p["expires_at"] - time.time())),
            "mobile_url": f"{_lan_base_url()}/m/approve/{run_id}?t={p['token']}"}


class MobileApproval(BaseModel):
    t: str
    approved: bool


@app.post("/api/m/approve/{run_id}")
def mobile_approve(run_id: str, body: MobileApproval):
    if not orchestrator.resolve_approval_token(run_id, body.t, body.approved):
        raise HTTPException(403, "approval link is invalid, already used, or expired")
    return {"recorded": True, "approved": body.approved, "via": "mobile"}


@app.get("/m/approve/{run_id}", response_class=HTMLResponse)
def mobile_approve_page(run_id: str, t: str = ""):
    """Minimal phone page. Wrong/expired tokens get 403; the token is also single-use on submit."""
    import secrets as _secrets

    p = orchestrator.pending_approval(run_id)
    if not p:
        if t:
            return HTMLResponse(_MOBILE_PAGE.replace("{{BODY}}", "<p class=warn>Approval link is invalid, already used, or expired.</p>"), status_code=403)
        return HTMLResponse(_MOBILE_PAGE.replace("{{BODY}}", "<p class=muted>No approval is pending (it was already decided or expired).</p>"))
    if not t or not _secrets.compare_digest(str(p["token"]), str(t)):
        return HTMLResponse(_MOBILE_PAGE.replace("{{BODY}}", "<p class=warn>Approval link is invalid, already used, or expired.</p>"), status_code=403)
    acts = "".join(f"<li>{html.escape(a['action_type'])} on <b>{html.escape(a['asset_id'])}</b></li>" for a in p["actions"])
    body = (f"<h2>{html.escape(p['label'])}</h2><ul>{acts}</ul>"
            f"<p class=warn>Disrupts {p['disrupted']} legitimate path(s) in the synthetic twin.</p>"
            "<button id=ok>Approve defense</button><button id=no class=no>Reject</button><p id=msg class=muted></p>"
            "<script>const send=a=>fetch(location.pathname.replace('/m/','/api/m/'),{method:'POST',headers:{'Content-Type':'application/json'},"
            f"body:JSON.stringify({{t:{json.dumps(t)},approved:a}})}}).then(r=>r.ok?'Recorded — you can close this page.':'Link invalid, used or expired.')"
            ".then(m=>{document.getElementById('msg').textContent=m;document.querySelectorAll('button').forEach(b=>b.disabled=true)});"
            "document.getElementById('ok').onclick=()=>send(true);document.getElementById('no').onclick=()=>send(false);</script>")
    return HTMLResponse(_MOBILE_PAGE.replace("{{BODY}}", body))


_MOBILE_PAGE = """<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>CYBERGENESIS approval</title><style>body{font-family:system-ui;background:#020617;color:#e2e8f0;padding:20px;max-width:480px;margin:auto}
h1{color:#67e8f9;font-size:18px;letter-spacing:.2em}h2{font-size:17px}.warn{color:#fcd34d}.muted{color:#94a3b8;font-size:13px}
button{display:block;width:100%;padding:14px;margin:10px 0;border:0;border-radius:10px;font-weight:700;font-size:16px;background:#10b981;color:#022c22}
button.no{background:transparent;border:1px solid #f87171;color:#fca5a5}button:disabled{opacity:.4}</style></head>
<body><h1>CYBERGENESIS</h1><p class=muted>Human approval gate · synthetic simulation only</p>{{BODY}}</body></html>"""


class ArenaMatchRequest(BaseModel):
    scenario_id: str = "red_vs_blue_battle"
    mode: str = "ai"
    max_rounds: int | None = None
    seed: int = 42
    custom_twin_id: str | None = None


@app.post("/api/arena/matches")
async def arena_play(body: ArenaMatchRequest, db: Session = Depends(get_db)):
    from app.arena.service import ArenaError, play_and_store

    try:
        return await play_and_store(db, body.scenario_id, mode=body.mode, max_rounds=body.max_rounds,
                                    seed=body.seed, custom_twin_id=body.custom_twin_id)
    except ArenaError as e:
        raise HTTPException(422, str(e))


@app.get("/api/arena/matches")
def arena_matches(db: Session = Depends(get_db)):
    rows = db.query(models.ArenaMatch).order_by(models.ArenaMatch.created_at.desc()).limit(100).all()
    return [{"id": r.id, "scenario_id": r.scenario_id, "winner": r.winner, "reason": r.reason, "mode": r.mode,
             "rounds_played": r.rounds_played, "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]


@app.get("/api/arena/matches/{match_id}")
def arena_match(match_id: str, db: Session = Depends(get_db)):
    r = db.get(models.ArenaMatch, match_id)
    if not r:
        raise HTTPException(404, "arena match not found")
    return {"id": r.id, "scenario_id": r.scenario_id, "winner": r.winner, "mode": r.mode,
            "created_at": r.created_at.isoformat() if r.created_at else None, **r.payload}


@app.get("/api/arena/matches/{match_id}/certificate")
def arena_certificate(match_id: str, db: Session = Depends(get_db)):
    from app.arena.service import ArenaError, build_arena_certificate

    try:
        return build_arena_certificate(db, match_id)
    except ArenaError as e:
        raise HTTPException(404, str(e))


@app.get("/api/arena/memory")
def arena_memory():
    from app.arena.learning import ArenaMemory

    return ArenaMemory.load(settings.arena_memory_path).summary()


@app.get("/api/arena/league")
def arena_league(db: Session = Depends(get_db)):
    from app.arena.service import league

    return league(db)


class ForkRequest(BaseModel):
    at_event: str = "attacked"
    choose_candidate: int | str


@app.post("/api/experiments/{run_id}/fork")
def fork_experiment(run_id: str, body: ForkRequest, db: Session = Depends(get_db)):
    from app.simulation.counterfactual import ForkError, fork_run

    try:
        return fork_run(db, run_id, body.choose_candidate, body.at_event)
    except ForkError as e:
        raise HTTPException(404 if "not found" in str(e) else 422, str(e))


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
            "decisions": [{"agent": d.agent, "decision": d.decision, "justification": d.justification, "confidence": d.confidence, "model": d.model, "mode": d.mode, "evidence_refs": d.evidence_refs, "asset_ids": d.asset_ids, "data": d.data or {}} for d in dec],
            "policy": [{"action_type": p.action_type, "asset_id": p.asset_id, "approved": p.approved, "reasons": p.reasons} for p in pol],
            "executions": [{"action_type": e.action_type, "asset_id": e.asset_id, "success": e.success, "transition": e.transition} for e in exe]}


@app.get("/api/experiments/{run_id}/evidence")
def exp_evidence(run_id: str, db: Session = Depends(get_db)):
    rows = db.query(models.EvidenceRecord).filter_by(run_id=run_id).all()
    return [{"id": e.id, "kind": e.kind, "ref": e.ref, "summary": e.summary, "data": e.data,
             "timestamp": e.created_at.isoformat() if e.created_at else None} for e in rows]


@app.get("/api/experiments/{run_id}/certificate")
def exp_certificate(run_id: str, db: Session = Depends(get_db)):
    from app.simulation.scenarios import SCENARIOS as _SC
    from app.simulation.twin import DigitalTwin as _DT
    from app.verification.certificate import build_certificate

    r = db.get(models.SimulationRun, run_id)
    if not r:
        raise HTTPException(404, "experiment not found")
    vers = db.query(models.VerificationResultRow).filter_by(run_id=run_id).all()
    if not vers:
        raise HTTPException(409, "no verification yet for this run")
    if r.custom_scenario_id:
        srow = db.get(models.CustomScenarioDefinition, r.custom_scenario_id)
        scenario = {**srow.definition, "id": srow.id, "name": srow.name}
    else:
        scenario = _SC[r.scenario_id]
    snaps = {s.label: s.snapshot for s in db.query(models.AssetStateSnapshot).filter_by(run_id=run_id).all()}
    baseline = _DT()
    if "baseline" in snaps:
        baseline.restore(snaps["baseline"])
    final = orchestrator.TWIN.clone()
    if "post_remediation" in snaps:
        final.restore(snaps["post_remediation"])
    executions = [{"action_type": e.action_type, "asset_id": e.asset_id, "success": e.success, "transition": e.transition}
                  for e in db.query(models.DefenseExecution).filter_by(run_id=run_id).all()]
    verifications = [{"outcome": v.outcome, "invariant": v.invariant, "checks": v.checks, "metrics": v.metrics} for v in vers]
    events = [{"event_type": e.event_type, "agent": e.agent, "asset_id": e.asset_id, "message": e.message, "seq": e.seq}
              for e in db.query(models.SimulationEvent).filter_by(run_id=run_id).order_by(models.SimulationEvent.seq).all()]
    return build_certificate(r, scenario, baseline, final, executions, verifications, events)


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
    mode_label = {"live": "LIVE META AI (muse-spark-1.3)",
                  "mixed": "MIXED (live Meta AI + deterministic offline agents)"}.get(
                      r.mode, "OFFLINE SIMULATION (deterministic, no Meta inference)")
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
    lines += ["", "## Attack Steps (MITRE ATT&CK)"]
    for st in sc.get("attack_steps", []):
        lines.append(f"- {st.get('type')} on {st.get('asset')}: {st.get('description', '')} · MITRE {st.get('mitre', '—')}")
    lines += ["", "## Defense Proposal & Policy"]
    for p in data["policy"]:
        lines.append(f"- {p['action_type']} on {p['asset_id']}: {'✅ APPROVED' if p['approved'] else '❌ REJECTED'} — {'; '.join(p['reasons'])}")
    _d3 = {d["id"]: d.get("d3fend", "") for d in library()["defense_actions"]}
    for e in data["executions"]:
        lines.append(f"- Executed {e['action_type']} on {e['asset_id']}: success={e['success']} · D3FEND {_d3.get(e['action_type'], '')} · {e['transition']}")
    lines += ["", "## Verification", f"**Invariant:** {ver.get('invariant', '—')}", "", "| Check | Result | Detail |", "|---|---|---|"]
    for c in ver.get("checks", []):
        lines.append(f"| {c['name']} | {'✅ PASS' if c['passed'] else '❌ FAIL'} | {c['detail']} |")
    lines += ["", (f"**Outcome: {ver.get('outcome', '—')}** · **Effectiveness:** {metrics.get('defense_effectiveness_pct', '—')}% "
              f"· **Time to detect:** {metrics.get('time_to_detect_s', '—')}s · **Time to contain:** {metrics.get('time_to_contain_s', '—')}s "
              f"· **Operational cost:** {metrics.get('operational_impact_disrupted_legit_paths', '—')} legitimate paths disrupted"),
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

    # confidence calibration from the evidence store: stated confidence vs verified outcome
    calibration = {"runs_scored": 0, "mean_confidence_pass": None, "mean_confidence_fail": None}
    db2 = next(get_db())
    try:
        scored = []
        for run_row in db2.query(models.SimulationRun).filter(models.SimulationRun.state == "COMPLETED").all():
            ver = (db2.query(models.VerificationResultRow).filter_by(run_id=run_row.id)
                   .order_by(models.VerificationResultRow.created_at.desc()).first())
            inv = (db2.query(models.AgentDecision).filter_by(run_id=run_row.id, agent="incident_investigator")
                   .order_by(models.AgentDecision.created_at.desc()).first())
            if ver and inv:
                scored.append((inv.confidence, ver.outcome == "PASS"))
        if scored:
            passes = [c for c, ok in scored if ok]; fails = [c for c, ok in scored if not ok]
            calibration = {"runs_scored": len(scored),
                           "mean_confidence_pass": round(sum(passes) / len(passes), 3) if passes else None,
                           "mean_confidence_fail": round(sum(fails) / len(fails), 3) if fails else None,
                           "note": "calibration improves as failed runs accumulate; a single-class sample cannot show discrimination"}
    finally:
        db2.close()
    return {"available": True, "pairs": len(rows), "scope": "50 seeded pairs, offline/simulate defenders; live Muse Spark spot-checked on builtin scenarios",
            "summary": {k: agg(k) for k in ("none", "offline", "simulate")}, "rows": rows, "calibration": calibration}


@app.get("/api/learning/curve")
def learning_curve(db: Session = Depends(get_db)):
    """Optimality gap over completed runs (learning-across-runs evidence)."""
    points = []
    for run_row in db.query(models.SimulationRun).filter(models.SimulationRun.state == "COMPLETED") \
            .order_by(models.SimulationRun.created_at).all():
        ver = (db.query(models.VerificationResultRow).filter_by(run_id=run_row.id)
               .order_by(models.VerificationResultRow.created_at.desc()).first())
        if ver:
            points.append({"run_id": run_row.id, "scenario_id": run_row.scenario_id, "mode": run_row.mode,
                           "outcome": ver.outcome, "optimality_gap": ver.metrics.get("optimality_gap"),
                           "ai_matched_optimum": ver.metrics.get("ai_matched_optimum"),
                           "created_at": run_row.created_at.isoformat() if run_row.created_at else None})
    return {"points": points, "runs": len(points)}


@app.get("/api/benchmark/calibration")
def benchmark_calibration(db: Session = Depends(get_db)):
    """Investigator confidence in 5 buckets vs verified PASS rate."""
    buckets = [{"bucket": f"{i / 5:.1f}-{(i + 1) / 5:.1f}", "n": 0, "passes": 0} for i in range(5)]
    for run_row in db.query(models.SimulationRun).filter(models.SimulationRun.state == "COMPLETED").all():
        ver = (db.query(models.VerificationResultRow).filter_by(run_id=run_row.id)
               .order_by(models.VerificationResultRow.created_at.desc()).first())
        inv = (db.query(models.AgentDecision).filter_by(run_id=run_row.id, agent="incident_investigator")
               .order_by(models.AgentDecision.created_at.desc()).first())
        if ver and inv:
            idx = min(int(inv.confidence * 5), 4)
            buckets[idx]["n"] += 1
            buckets[idx]["passes"] += int(ver.outcome == "PASS")
    for b in buckets:
        b["pass_rate_pct"] = round(100 * b["passes"] / b["n"], 1) if b["n"] else None
    return {"buckets": buckets, "note": "buckets with n=0 have no scored runs yet"}


_bench_runs: dict[str, dict] = {}


class BenchmarkRunRequest(BaseModel):
    n: int = 20
    seed: int = 7
    mode: str = "offline"


@app.post("/api/benchmark/run", status_code=202)
async def benchmark_run(body: BenchmarkRunRequest):
    import uuid as _uuid

    from app.benchmark.runner import run_benchmark, summarize

    run_id = _uuid.uuid4().hex[:12]
    _bench_runs[run_id] = {"state": "RUNNING", "done": 0, "total": body.n, "rows": [], "summary": None}

    def _progress(done: int, total: int, _row: dict) -> None:
        _bench_runs[run_id]["done"] = done

    def _job() -> None:
        try:
            rows = run_benchmark(body.n, body.seed, _progress)
            _bench_runs[run_id].update({"state": "COMPLETED", "rows": rows, "summary": summarize(rows)})
        except Exception as e:  # noqa: BLE001 - honest failure
            _bench_runs[run_id].update({"state": "FAILED", "error": f"{type(e).__name__}: {e}"})

    import threading

    threading.Thread(target=_job, daemon=True, name=f"benchmark-{run_id}").start()
    return {"run_id": run_id, "state": "RUNNING", "n": body.n, "seed": body.seed, "mode": body.mode}


@app.get("/api/benchmark/run/{run_id}")
def benchmark_run_status(run_id: str):
    row = _bench_runs.get(run_id)
    if not row:
        raise HTTPException(404, "benchmark run not found")
    return {"run_id": run_id, **row}


@app.get("/api/benchmark/run/{run_id}/export")
def benchmark_run_export(run_id: str, format: str = "json"):
    import csv
    import io
    import json as _json

    from fastapi.responses import PlainTextResponse

    row = _bench_runs.get(run_id)
    if not row:
        raise HTTPException(404, "benchmark run not found")
    if format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["pair", "source", "target", "defender", "pass", "effectiveness", "gap", "disrupted", "risk_after"])
        for r in row["rows"]:
            for k in ("none", "offline", "simulate"):
                w.writerow([r["pair"], r["source"], r["target"], k, r[k]["pass"], r[k]["effectiveness"], r[k]["gap"], r[k]["disrupted"], r[k]["risk_after"]])
        return PlainTextResponse(buf.getvalue(), media_type="text/csv")
    return PlainTextResponse(_json.dumps(row, indent=1), media_type="application/json")


@app.websocket("/ws/benchmark/{run_id}")
async def ws_benchmark(ws: WebSocket, run_id: str):
    await ws.accept()
    try:
        while True:
            row = _bench_runs.get(run_id)
            if not row:
                await ws.send_text(json.dumps({"state": "NOT_FOUND"}))
                break
            await ws.send_text(json.dumps({"run_id": run_id, "state": row["state"], "done": row["done"], "total": row["total"]}))
            if row["state"] in ("COMPLETED", "FAILED"):
                break
            await asyncio.sleep(0.7)
    except WebSocketDisconnect:
        pass


@app.get("/api/devices/catalog")
def devices_catalog(category: str | None = None, vendor: str | None = None, q: str | None = None,
                    tier: str | None = None, limit: int = 50, offset: int = 0):
    from app.devices.registry import query_catalog

    return query_catalog(category=category, vendor=vendor, q=q, tier=tier, limit=min(limit, 200), offset=offset)


@app.get("/api/devices/catalog/{device_id}")
def device_by_id(device_id: str):
    from app.devices.registry import BY_ID

    m = BY_ID.get(device_id)
    if not m:
        raise HTTPException(404, "device not in catalog")
    return m.model_dump()


@app.get("/api/devices/builtin-map")
def devices_builtin_map():
    from app.devices.registry import BUILTIN_DEVICE_MAP

    return BUILTIN_DEVICE_MAP


_twin_ws: set = set()


@app.websocket("/ws/twin")
async def ws_twin(ws: WebSocket):
    await ws.accept()
    _twin_ws.add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _twin_ws.discard(ws)


async def _broadcast_twin_updated() -> None:
    payload = json.dumps({"event_type": "twin_updated", "twin": orchestrator.TWIN.to_dict()})
    for ws in list(_twin_ws):
        try:
            await ws.send_text(payload)
        except Exception:  # noqa: BLE001
            _twin_ws.discard(ws)


@app.get("/api/twin/devices/{asset_id}/config")
def get_device_config(asset_id: str):
    twin = orchestrator.TWIN
    if asset_id not in twin.device_configs:
        raise HTTPException(404, "device not in twin")
    return {"asset_id": asset_id, "config": twin.device_configs[asset_id], "config_hash": twin.config_hash(),
            "version": len(twin.config_versions.get(asset_id, [])) + 1}


class StageDiffRequest(BaseModel):
    diff: dict
    author: str = "human"


@app.post("/api/twin/devices/{asset_id}/config/diff")
def stage_device_diff(asset_id: str, body: StageDiffRequest, db: Session = Depends(get_db)):
    twin = orchestrator.TWIN
    if asset_id not in twin.device_configs:
        raise HTTPException(404, "device not in twin")
    known_ifaces = {i["name"] for i in twin.device_configs[asset_id].get("interfaces", [])}
    for op in body.diff.get("ops", []):
        if op.get("op") == "bind_acl":
            iface = (op.get("value") or {}).get("interface")
            if iface and iface != "current" and iface not in known_ifaces:
                raise HTTPException(422, f"bind_acl: unknown interface '{iface}' on {asset_id} (known: {sorted(known_ifaces)})")
    twin.stage_diff(asset_id, body.diff)  # append-only
    row = models.ConfigCommit(device_id=asset_id, status="pending", diff=body.diff)
    db.add(row); db.commit(); db.refresh(row)
    return {"staged": True, "commit_id": row.id, "pending_count": len(twin.pending_diffs[asset_id]),
            "pending": twin.pending_diffs[asset_id]}


@app.get("/api/twin/devices/{asset_id}/config/pending")
def get_pending_diff(asset_id: str):
    pending = orchestrator.TWIN.pending_diffs.get(asset_id, [])
    if isinstance(pending, dict):  # legacy shape
        pending = [pending]
    return {"asset_id": asset_id, "pending": pending, "pending_count": len(pending)}


@app.post("/api/twin/devices/{asset_id}/config/preview")
def preview_device_diff(asset_id: str, body: StageDiffRequest):
    """Compile on a clone with the diff applied; report which scenario paths open/close."""
    twin = orchestrator.TWIN
    if asset_id not in twin.device_configs:
        raise HTTPException(404, "device not in twin")
    clone = twin.clone()
    _apply_config_diff(clone, asset_id, body.diff)
    pairs = [(s["source_asset"], s["target_asset"]) for s in SCENARIOS.values()]
    changes = []
    for src, dst in pairs:
        before = twin.find_path(src, dst) is not None
        after = clone.find_path(src, dst) is not None
        if before != after:
            changes.append({"src": src, "dst": dst, "before_reachable": before, "after_reachable": after})
    return {"changes": changes, "config_hash_after": clone.config_hash()}


ROLE_RANK = {"viewer": 0, "user": 1, "operator": 2, "admin": 3, "administrator": 3}


def _resolve_asset_by_ip(twin, ip_or_id: str) -> str | None:
    if ip_or_id in twin.device_configs:
        return ip_or_id
    for aid, cfg in twin.device_configs.items():
        for iface in cfg.get("interfaces", []):
            if iface.get("ip") == ip_or_id:
                return aid
    return None


def _op_semantics(op: dict, twin=None, asset_id: str = "") -> tuple[str, str | None, dict] | None:
    """Explicit op->semantic table. Returns (semantic, action_to_evaluate|None, params).
    None = reject. There is deliberately NO catch-all."""
    kind = op.get("op")
    if kind == "action":
        return (op["value"]["action_type"], op["value"]["action_type"], op["value"].get("params", {}))
    if kind in ("add_acl_entry", "bind_acl", "add_acl_deny"):
        entry = (op.get("value") or {}).get("entry", {}) if kind == "add_acl_entry" else {}
        dst_raw = entry.get("dst", "any")
        target = _resolve_asset_by_ip(twin, dst_raw) if twin is not None and dst_raw != "any" else None
        if target is None and twin is not None:
            target = next(iter(twin.graph.successors(asset_id)), asset_id) if asset_id in twin.graph else asset_id
        return ("block_connection", "block_connection",
                {"source": asset_id, "target": target, "direction": "egress"})
    if kind != "set":
        return None
    path = op.get("path", "")
    value = op.get("value")
    if path == "isolated":
        return ("isolate_asset", "isolate_asset", {}) if value else ("restore_connectivity", "restore_connectivity", {})
    if path == "quarantine_vlan":
        return ("quarantine_vlan", "quarantine_vlan", {})
    if path == "weaknesses" or path.startswith("patches."):
        return ("apply_patch", "apply_patch", {})
    if path.startswith("mgmt."):
        return ("harden_mgmt", "harden_mgmt", {})
    if path.startswith("interfaces."):
        if path.endswith(".enabled"):
            return ("disable_service", "disable_service", {}) if not value else ("restore_connectivity", "restore_connectivity", {})
        return ("interface_config", None, {})  # vlan/mode/ip/description on an interface: validated structurally at apply
    if path.startswith("services."):
        if path.endswith(".enabled"):
            return ("disable_service", "disable_service", {}) if not value else ("benign", None, {})
        return None
    if path.startswith("users."):
        if path.endswith(".role"):
            return ("privilege_change", None, {})  # special-cased in _validate_diff_ops (lowering only)
        if path.endswith(".mfa"):
            return ("enforce_mfa", "enforce_mfa", {}) if value else ("mfa_disable", None, {})  # disabling MFA is always denied below
        if ".sessions" in path:
            return ("revoke_session", "revoke_session", {})
        return None
    if path in ("hostname",) or path.endswith(".description"):
        return ("benign", None, {})
    return None


def _validate_diff_ops(twin, asset_id: str, diff: dict) -> list[str]:
    reasons: list[str] = []
    cfg = twin.device_configs.get(asset_id, {})
    for op in diff.get("ops", []):
        sem = _op_semantics(op, twin, asset_id)
        if sem is None:
            reasons.append(f"unknown config path/op rejected: {op.get('op')} {op.get('path', '')}".strip())
            continue
        name, action_type, params = sem
        if name == "mfa_disable":
            reasons.append("users.*.mfa=false is denied: MFA may only be enforced, never removed")
            continue
        if name == "privilege_change":
            # users.<idx>.role: only lowering a privilege is allowed
            parts = op["path"].split(".")
            try:
                current = cfg.get("users", [])[int(parts[1])].get("role", "user")
            except (IndexError, ValueError, TypeError):
                reasons.append(f"privilege_change: cannot resolve current role at {op['path']}")
                continue
            if ROLE_RANK.get(str(op.get("value", "")).lower(), 99) >= ROLE_RANK.get(str(current).lower(), 1):
                reasons.append(f"privilege escalation denied: {current} -> {op.get('value')} (only lowering is allowed)")
            continue
        if action_type is None:
            continue  # benign / structural: nothing to evaluate
        d = policy_engine.evaluate(action_type, asset_id, params, twin)
        if not d.approved:
            reasons.append(f"{op.get('op')} ({name}->{action_type}): {'; '.join(d.reasons)}")
    return reasons


def _apply_config_diff(twin, asset_id: str, diff: dict) -> None:
    import copy as _copy

    versions = twin.config_versions.setdefault(asset_id, [])
    if not versions:  # version 0 = untouched baseline, saved on first touch
        versions.append({"version": 0, "config": _copy.deepcopy(twin.device_configs[asset_id])})
    cfg = twin.device_configs[asset_id]
    for op in diff.get("ops", []):
        if op.get("op") == "action":
            twin.apply_action(op["value"]["action_type"], op["value"].get("asset_id", asset_id), op["value"].get("params", {}))
            cfg = twin.device_configs[asset_id]
        elif op.get("op") == "set":
            parts = op["path"].split(".")
            if parts[0] == "interfaces" and len(parts) >= 3 and not parts[1].isdigit():
                iface = next((i for i in cfg.get("interfaces", []) if i["name"] == parts[1]), None)
                if iface is not None:
                    iface[parts[2]] = op.get("value")
                continue
            node = cfg
            for p in parts[:-1]:
                node = node.setdefault(p, {}) if isinstance(node, dict) else node[int(p)]
            if isinstance(node, dict):
                node[parts[-1]] = op.get("value")
            elif isinstance(node, list):
                node[int(parts[-1])] = op.get("value")
            # resync twin state through the single mutator
            if op["path"] == "isolated":
                twin.set_state(asset_id, "isolated", bool(op.get("value")))
            if op["path"] == "weaknesses":
                twin.set_state(asset_id, "weaknesses", list(op.get("value") or []))
            if op["path"] == "quarantine_vlan":
                twin.set_state(asset_id, "quarantine_vlan", bool(op.get("value")))
        elif op.get("op") == "add_acl_entry":
            v = op["value"]
            acl = next((a for a in cfg.setdefault("acls", []) if a["name"] == v["name"]), None)
            if acl is None:
                acl = {"name": v["name"], "entries": []}
                cfg["acls"].append(acl)
            acl["entries"].append(v["entry"])
        elif op.get("op") == "bind_acl":
            v = op["value"]
            iface = next((i for i in cfg.get("interfaces", []) if i["name"] == v.get("interface")), None) \
                or (cfg["interfaces"][0] if cfg.get("interfaces") else None)
            if iface is not None:
                iface["acl_in" if v.get("direction") == "in" else "acl_out"] = v["name"]
        elif op.get("op") == "add_acl_deny":  # legacy fixed rule, kept for compatibility
            cfg.setdefault("acls", []).append({"name": "CYBERGENESIS", "entries": [
                {"seq": 10, "action": "deny", "proto": "ip", "src": "any", "dst": "any", "dst_port": None, "log": True}]})
    versions.append({"version": len(versions), "config": _copy.deepcopy(cfg)})


@app.post("/api/twin/devices/{asset_id}/config/commit")
async def commit_device_diff(asset_id: str, db: Session = Depends(get_db)):
    twin = orchestrator.TWIN
    staged = twin.pending_diffs.pop(asset_id, None)
    if not staged:
        raise HTTPException(409, "no pending diff for this device")
    diffs = staged if isinstance(staged, list) else [staged]
    diff = {"ops": [op for d in diffs for op in d.get("ops", [])]}
    def _finish(status: str, verification: dict):
        # finalize ALL pending rows for this device, not just the latest
        rows = db.query(models.ConfigCommit).filter_by(device_id=asset_id, status="pending").all()
        for r in rows:
            r.status = status
            r.verification = verification
            r.diff = diff
        if rows:
            db.commit()
            return rows[-1]
        row = models.ConfigCommit(device_id=asset_id, status=status, diff=diff, verification=verification)
        db.add(row); db.commit()
        return row

    # policy gate: EVERY op is mapped to a semantic action and evaluated first
    gate_reasons = _validate_diff_ops(twin, asset_id, diff)
    if gate_reasons:
        _finish("rejected", {"approved": False, "reasons": gate_reasons})
        raise HTTPException(403, detail={"status": "rejected", "reasons": gate_reasons})
    # Verified Commit: replay every known campaign objective on a clone with the diff applied.
    # Reject if the change reopens a blocked path or opens a new crown-jewel path.
    clone = twin.clone()
    _apply_config_diff(clone, asset_id, diff)
    campaigns = [(s["source_asset"], s["target_asset"], s["id"]) for s in SCENARIOS.values()]
    rejected_reasons: list[str] = []
    for src, dst, sid in campaigns:
        before = twin.find_path(src, dst)
        after = clone.find_path(src, dst)
        if before is None and after is not None:
            expl = clone.explain_path(src, dst)
            hop = expl["hops"][0] if expl.get("hops") else {"rule": "unknown hop"}
            rejected_reasons.append(
                f"campaign {sid}: change opens {src}->{dst} via {hop.get('from')}->{hop.get('to')} ({hop.get('rule')})")
    if rejected_reasons:
        _finish("rejected", {"approved": False, "reasons": rejected_reasons, "campaigns_checked": len(campaigns)})
        raise HTTPException(403, detail={"status": "rejected", "reasons": rejected_reasons})
    _apply_config_diff(twin, asset_id, diff)  # appends exactly one new version (deep-copied)
    _finish("committed", {"config_hash": twin.config_hash(), "campaigns_checked": len(campaigns),
                          "all_campaigns_still_blocked_or_unchanged": True})
    await _broadcast_twin_updated()
    return {"committed": True, "asset_id": asset_id, "config_hash": twin.config_hash(), "twin": twin.to_dict()}


@app.post("/api/twin/devices/{asset_id}/config/rollback/{version}")
async def rollback_device_config(asset_id: str, version: int):
    twin = orchestrator.TWIN
    versions = twin.config_versions.get(asset_id, [])
    match = next((v for v in versions if v["version"] == version), None)
    if not match:
        raise HTTPException(404, "config version not found")
    import copy as _copy

    twin.device_configs[asset_id] = _copy.deepcopy(match["config"])
    twin.set_state(asset_id, "weaknesses", list(match["config"].get("weaknesses", [])))
    twin.set_state(asset_id, "isolated", bool(match["config"].get("isolated", False)))
    twin.set_state(asset_id, "quarantine_vlan", bool(match["config"].get("quarantine_vlan")))
    await _broadcast_twin_updated()
    return {"rolled_back": True, "asset_id": asset_id, "version": version}


@app.get("/api/twin/compile/explain")
def compile_explain(src: str, dst: str):
    twin = orchestrator.TWIN
    if src not in twin.asset_ids() or dst not in twin.asset_ids():
        raise HTTPException(422, "src/dst must be twin assets")
    return twin.explain_path(src, dst)


@app.get("/api/agents")
def list_agents(db: Session = Depends(get_db)):
    from app.agents.framework.registry import all_specs

    out = []
    for s in all_specs():
        runs = db.query(models.AgentDecision).filter_by(agent=s.id).count()
        last = (db.query(models.AgentDecision).filter_by(agent=s.id)
                .order_by(models.AgentDecision.created_at.desc()).first())
        out.append({"id": s.id, "name": s.name, "team": s.team, "engine": s.engine, "description": s.description,
                    "tools": s.tools, "can_propose_actions": s.can_propose_actions,
                    "prompt_version": s.prompt_version, "prompt_hash": s.prompt_hash,
                    "scorecard": {"runs": runs, "last_mode": last.mode if last else None,
                                  "last_confidence": last.confidence if last else None}})
    return out


@app.get("/api/agents/{agent_id}")
def get_agent(agent_id: str):
    from app.agents.framework.registry import get_spec

    s = get_spec(agent_id)
    if not s:
        raise HTTPException(404, "agent not in registry")
    return {"id": s.id, "name": s.name, "team": s.team, "engine": s.engine, "description": s.description,
            "duties": s.duties, "tools": s.tools, "can_propose_actions": s.can_propose_actions,
            "input_model": s.input_model.__name__, "output_model": s.output_model.__name__,
            "timeout_s": s.timeout_s, "max_tokens": s.max_tokens, "max_tool_steps": s.max_tool_steps,
            "prompt_version": s.prompt_version, "prompt_hash": s.prompt_hash}


@app.get("/api/agents/{agent_id}/runs")
def agent_runs(agent_id: str, limit: int = 20, db: Session = Depends(get_db)):
    rows = (db.query(models.AgentDecision).filter_by(agent=agent_id)
            .order_by(models.AgentDecision.created_at.desc()).limit(limit).all())
    return [{"run_id": r.run_id, "decision": r.decision, "confidence": r.confidence, "model": r.model,
             "mode": r.mode, "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]


@app.get("/api/experiments/{run_id}/messages")
def experiment_messages(run_id: str, db: Session = Depends(get_db)):
    rows = db.query(models.AgentMessageRow).filter_by(run_id=run_id).order_by(models.AgentMessageRow.seq).all()
    return [{"id": r.id, "from_agent": r.from_agent, "to_agent": r.to_agent, "kind": r.kind,
             "payload": r.payload, "evidence_refs": r.evidence_refs, "seq": r.seq} for r in rows]


_eval_runs: dict[str, dict] = {}


class EvalRunRequest(BaseModel):
    n: int = 10
    seed: int = 7
    mode: str = "offline"


@app.post("/api/agents/eval/run", status_code=202)
def agents_eval_run(body: EvalRunRequest):
    import threading
    import uuid as _uuid

    from app.agents.eval import run_eval_sync

    run_id = _uuid.uuid4().hex[:12]
    _eval_runs[run_id] = {"state": "RUNNING", "done": 0, "total": body.n, "result": None}

    def _job():
        try:
            result = run_eval_sync(body.n, body.seed, body.mode,
                                   progress=lambda d, t: _eval_runs[run_id].update({"done": d}))
            _eval_runs[run_id].update({"state": "COMPLETED", "result": result})
        except Exception as e:  # noqa: BLE001
            _eval_runs[run_id].update({"state": "FAILED", "error": f"{type(e).__name__}: {e}"})

    threading.Thread(target=_job, daemon=True, name=f"eval-{run_id}").start()
    return {"run_id": run_id, "state": "RUNNING", "n": body.n, "seed": body.seed, "mode": body.mode}


@app.get("/api/agents/eval/run/{run_id}")
def agents_eval_status(run_id: str):
    row = _eval_runs.get(run_id)
    if not row:
        raise HTTPException(404, "eval run not found")
    return {"run_id": run_id, **row}


@app.get("/api/agents/eval/latest")
def agents_eval_latest(mode: str | None = None):
    done = [r for r in _eval_runs.values() if r["state"] == "COMPLETED" and r["result"]]
    if mode:
        done = [r for r in done if r["result"].get("mode") == mode]
    if not done:
        return {"available": False, "detail": "no eval run yet — POST /api/agents/eval/run"}
    return {"available": True, "result": done[-1]["result"]}


@app.websocket("/ws/agents/eval/{run_id}")
async def ws_eval(ws: WebSocket, run_id: str):
    await ws.accept()
    try:
        while True:
            row = _eval_runs.get(run_id)
            if not row:
                await ws.send_text(json.dumps({"state": "NOT_FOUND"}))
                break
            await ws.send_text(json.dumps({"run_id": run_id, "state": row["state"], "done": row["done"], "total": row["total"]}))
            if row["state"] in ("COMPLETED", "FAILED"):
                break
            await asyncio.sleep(0.7)
    except WebSocketDisconnect:
        pass


class CliExecRequest(BaseModel):
    input: str
    user: str = "admin"


@app.post("/api/cli/{asset_id}/exec")
def cli_exec(asset_id: str, body: CliExecRequest):
    from app.cli.engine import execute

    if asset_id not in orchestrator.TWIN.device_configs:
        raise HTTPException(404, "device not in twin")
    return execute(orchestrator.TWIN, asset_id, body.input, body.user)


@app.post("/api/cli/{asset_id}/complete")
def cli_complete(asset_id: str, body: CliExecRequest):
    from app.cli.engine import complete

    return {"completions": complete(orchestrator.TWIN, asset_id, body.input)}


@app.websocket("/ws/cli/{asset_id}")
async def ws_cli(ws: WebSocket, asset_id: str):
    from app.cli.engine import execute

    await ws.accept()
    try:
        while True:
            data = await ws.receive_json()
            out = execute(orchestrator.TWIN, asset_id, str(data.get("input", "")), str(data.get("user", "admin")))
            await ws.send_text(json.dumps({"event_type": "cli_output", **out}))
    except WebSocketDisconnect:
        pass


@app.get("/api/twin/devices/{asset_id}/os")
def device_os_state(asset_id: str, db: Session = Depends(get_db)):
    """Live OS state for shells: processes, telemetry events, services, users, files."""
    twin = orchestrator.TWIN
    if asset_id not in twin.device_configs:
        raise HTTPException(404, "device not in twin")
    cfg = twin.device_configs[asset_id]
    status = twin.status.get(asset_id, "healthy")
    events = (db.query(models.SimulationEvent).filter(models.SimulationEvent.asset_id == asset_id)
              .order_by(models.SimulationEvent.seq.desc()).limit(12).all())
    files = ["report.docx", "budget.xlsx", "notes.txt", "photo.jpg"]
    if status in ("compromised", "suspicious"):
        files = [f"{f}.locked" for f in files]
    return {
        "asset_id": asset_id, "status": status,
        "processes": twin.processes.get(asset_id, [{"name": "explorer.exe", "pid": 1002, "suspicious": False}]),
        "events": [{"type": e.event_type, "message": e.message, "agent": e.agent} for e in events],
        "services": cfg.get("services", []), "users": cfg.get("users", []),
        "host_firewall": cfg.get("host_firewall", {}), "files": files,
        "patches": cfg.get("patches", {}),
    }


@app.post("/api/audit/run")
def audit_run():
    import asyncio as _asyncio

    from app.agents.framework import io as _aio
    from app.agents.framework.adapters import build_agent
    from app.agents.framework.base import AgentContext

    async def _run():
        agent = build_agent("config_auditor")
        return await agent.run(AgentContext(run_id="audit", twin=orchestrator.TWIN), _aio.TextIn())

    result = _asyncio.run(_run())
    return {"findings": result.output.findings, "mode": result.mode, "fallback_reason": result.fallback_reason}


class ExplainRequest(BaseModel):
    text: str


@app.post("/api/config/explain")
async def explain_config(body: ExplainRequest):
    from app.agents.agents import wrap_data

    text = body.text.strip()
    if not text:
        raise HTTPException(422, "empty config text")
    try:
        with meta_client.use_budget_tier("advisory"):
            data, _u = await meta_client.chat_json(
                "Explain the security impact of config lines in plain language. JSON only: {\"explanation\": str}.",
                wrap_data("config", text))
        return {"explanation": str(data.get("explanation", "")), "mode": "live"}
    except Exception:  # noqa: BLE001 - deterministic offline explanation
        low = text.lower()
        hints = []
        if "telnet" in low:
            hints.append("Telnet management is cleartext and a common foothold — disable it (harden_mgmt).")
        if "deny" in low:
            hints.append("Deny entries reduce reachable services and can cut attack paths; check legitimate flows first.")
        if "any any" in low or "any-any" in low:
            hints.append("An any-any allow is effectively no filtering — a critical exposure.")
        if not hints:
            hints.append("No known risky pattern matched offline; live Meta explanation is unavailable in offline mode.")
        return {"explanation": " ".join(hints), "mode": "offline"}


@app.get("/api/twin/drift")
def twin_drift():
    twin = orchestrator.TWIN
    drift = []
    for aid, versions in twin.config_versions.items():
        if not versions:
            continue
        committed = versions[-1]["config"]
        current = twin.device_configs.get(aid, {})
        for field in ("weaknesses", "isolated", "quarantine_vlan"):
            if committed.get(field) != current.get(field):
                drift.append({"asset_id": aid, "field": field, "committed": committed.get(field),
                              "current": current.get(field),
                              "risky": field == "weaknesses" and bool(current.get(field))})
    return {"drift": drift}


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
    twin_body = await architect_twin(body.image_data_url, body.name)
    _validate_twin(twin_body)
    row = models.CustomTwinDefinition(name=twin_body.name, description=twin_body.description,
                                      assets=[a.model_dump() for a in twin_body.assets],
                                      connections=[c.model_dump() for c in twin_body.connections])
    db.add(row); db.commit(); db.refresh(row)
    return _twin_row(row)


class FromTextRequest(BaseModel):
    prompt_text: str = ""
    prompt: str = ""
    name: str = "Text Scenario"


@app.post("/api/scenarios/from-text", status_code=201)
async def scenario_from_text(body: FromTextRequest, db: Session = Depends(get_db)):
    """Text-to-scenario: Muse Spark writes a scenario; deterministic validation decides if it may run."""
    assets = [a["id"] for a in orchestrator.TWIN.to_dict()["assets"]]
    result = await author_scenario(body.prompt_text or body.prompt, body.name, assets)
    sc_body = result["body"]
    definition = _validate_scenario(sc_body)
    row = models.CustomScenarioDefinition(name=sc_body.name, description=sc_body.description, definition=definition)
    db.add(row); db.commit(); db.refresh(row)
    return _scenario_row(row)


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
            "identity": body.identity, "max_rounds": body.max_rounds,
            "attack_steps": [s.model_dump() for s in body.attack_steps],
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
