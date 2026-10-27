"""Closed-loop orchestrator v3.

Observe -> Reason -> Propose -> Simulate -> AI final choice -> Red critic -> (revise)
-> Policy -> [Human approval] -> Act -> Verify -> Red-team campaign rounds -> Self-heal -> Prove.
Each run owns its twin; the display twin syncs only when a run finishes.
"""

import asyncio
import time
from datetime import datetime, timezone

from app import models
from app.agents import agents, red_team
from app.agents.framework.bus import Blackboard
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


def clear_pending_approvals() -> int:
    """Clear all pending approvals, denying (and unblocking) any waiters."""
    entries = list(_approvals.values())
    _approvals.clear()
    for entry in entries:
        entry["approved"] = False
        entry["event"].set()
    return len(entries)


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
    """Run watchdog: the body runs as a task bounded by settings.run_timeout_s.

    On expiry the body is cancelled and the run is finished honestly as
    FAILED with error="run_timeout" plus a "run_timeout" event (not a
    verification FAIL: a timeout may occur before verification ever ran,
    so there is no verification verdict to report).
    """
    timeout = settings.run_timeout_s
    if not timeout or float(timeout) <= 0:
        await _run_experiment_impl(run_id, step_delay_ms=step_delay_ms)
        return
    task = asyncio.create_task(_run_experiment_impl(run_id, step_delay_ms=step_delay_ms))
    done, pending = await asyncio.wait({task}, timeout=float(timeout))
    if not pending:
        if not task.cancelled():
            exc = task.exception()
            if exc is not None:  # impl handles its own errors; this is defensive
                raise exc
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception:  # noqa: BLE001 - timeout bookkeeping below is the honest outcome
        pass
    db = SessionLocal()
    try:
        run = db.get(models.SimulationRun, run_id)
        if run is not None:
            run.state = "FAILED"
            run.error = "run_timeout"
            run.ended_at = datetime.now(timezone.utc)
            db.commit()
            _emit(db, run_id, "run_timeout",
                  f"Run exceeded run_timeout_s={float(timeout)}s and was stopped (error=run_timeout)")
    finally:
        _cancelled.discard(run_id)
        _approvals.pop(run_id, None)
        db.close()


async def _run_experiment_impl(run_id: str, step_delay_ms: int | None = None) -> None:
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

        _bb_seq = {"n": 0}

        def _persist_message(msg):
            _bb_seq["n"] += 1
            db.add(models.AgentMessageRow(id=msg.id, run_id=run_id, from_agent=msg.from_agent,
                                          to_agent=msg.to_agent, kind=msg.kind, payload=msg.payload,
                                          evidence_refs=msg.evidence_refs, in_reply_to=msg.in_reply_to,
                                          seq=_bb_seq["n"]))
            db.commit()

        def _stream_message(msg):
            emit("agent_message", f"{msg.from_agent}: {msg.kind}", agent=msg.from_agent,
                 payload={"id": msg.id, "from_agent": msg.from_agent, "to_agent": msg.to_agent,
                          "kind": msg.kind, "payload": msg.payload,
                          "evidence_refs": msg.evidence_refs, "in_reply_to": msg.in_reply_to})

        board = Blackboard(run_id, persist=_persist_message, stream=_stream_message)

        # framework routing: investigator / strategist / red planner run THROUGH their adapters,
        # so AgentResult carries framework mode, fallback_reason, prompt hash and token accounting
        from app.agents.framework.adapters import build_agent as _fw_build
        from app.agents.framework.base import AgentContext as _FwCtx
        from app.agents.framework import io as _fw_io

        _baseline_ref: dict = {}

        def _fw_ctx(telemetry_now=None):
            return _FwCtx(run_id=run_id, twin=twin, scenario=scenario, telemetry=telemetry_now or [],
                          baseline_twin=_baseline_ref.get("twin"), bus=board)

        async def _fw_investigate(scn, obs_obj, telemetry_now):
            res = await _fw_build("incident_investigator").run(
                _fw_ctx(telemetry_now), _fw_io.InvestigateIn(scenario=scn, telemetry=telemetry_now))
            out = res.output
            out.mode = res.mode
            if res.fallback_reason and not out.fallback_reason:
                out.fallback_reason = res.fallback_reason
            return out

        async def _fw_propose_with_context(scn, hyp_obj, extra_context=""):
            res = await _fw_build("defense_strategist").run(
                _fw_ctx(), _fw_io.ProposeIn(scenario=scn, hypothesis=hyp_obj.model_dump(),
                                            past_examples=past_examples, extra_context=extra_context))
            out = res.output
            out.mode = res.mode
            if res.fallback_reason and not out.fallback_reason:
                out.fallback_reason = res.fallback_reason
            return out

        async def set_state(state, msg, agent=None):
            run.state = state; db.commit()
            emit("state", msg, agent=agent, payload={"state": state, "mode": mode})
            await _delay()

        if run_id in _cancelled:
            raise asyncio.CancelledError()
        # Incident Commander plans the run (validated DAG); execution follows the mandatory backbone regardless
        commander_plan = None
        try:
            from app.agents.framework.adapters import build_agent as _build_agent
            from app.agents.framework.base import AgentContext as _AgentContext
            from app.agents.framework import io as _agent_io

            _cmd = await _build_agent("incident_commander").run(
                _AgentContext(run_id=run_id, twin=twin, scenario=scenario), _agent_io.TextIn(text=scenario["name"]))
            commander_plan = _cmd.output
            # Single source of truth for campaign length: scenario["max_rounds"]
            # (total rounds INCLUDING round 1). The commander plan is capped to
            # the same number by deterministic trimming, with the reason recorded.
            from app.agents.framework.new_agents import trim_plan_to_max_rounds

            _max_rounds_raw = scenario.get("max_rounds")
            commander_plan, _plan_trim_reason = trim_plan_to_max_rounds(commander_plan, _max_rounds_raw)
            _plan_payload = {**commander_plan.model_dump(), "max_rounds": _max_rounds_raw,
                             "plan_trim_reason": _plan_trim_reason}
            emit("commander_plan", f"Commander plan ({_cmd.mode}): {len(commander_plan.plan)} steps — {commander_plan.stop_condition}",
                 agent="incident_commander", payload=_plan_payload)
            if _plan_trim_reason:
                emit("commander_plan_trimmed", _plan_trim_reason, agent="incident_commander",
                     payload={"max_rounds": _max_rounds_raw, "reason": _plan_trim_reason,
                              "steps_after_trim": len(commander_plan.plan)})
            db.add(models.AgentDecision(run_id=run_id, agent="incident_commander", decision=f"plan: {[s.agents for s in commander_plan.plan]}",
                                        justification=commander_plan.stop_condition, confidence=commander_plan.confidence,
                                        model=_cmd.model, mode=_cmd.mode, evidence_refs=[], asset_ids=[],
                                        data={"fallback_reason": _cmd.fallback_reason,
                                              "max_rounds": _max_rounds_raw,
                                              "plan_trim_reason": _plan_trim_reason})); db.commit()
        except Exception as e:  # noqa: BLE001 - commander is advisory; backbone execution continues
            emit("provider_fallback", f"Commander unavailable, default backbone in use: {type(e).__name__}: {e}", agent="incident_commander")
        await set_state("SCENARIO_SELECTED", f"Scenario selected: {scenario['name']}", "adversary_simulator")
        baseline_twin = twin.clone()
        _baseline_ref["twin"] = baseline_twin
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
        # assurance agents publish to the bus/record; failures are honest, never silently swallowed
        from app.agents.framework.adapters import build_agent as _ba
        from app.agents.framework.base import AgentContext as _AC
        from app.agents.framework import io as _aio

        _ctx = _AC(run_id=run_id, twin=twin, scenario=scenario, telemetry=telemetry, baseline_twin=baseline_twin)
        for _aid, _inp in (("threat_intel_analyst", _aio.TelemetryIn(telemetry=telemetry)),
                           ("attack_surface_mapper", _aio.TextIn()),
                           ("identity_guardian", _aio.TextIn())):
            try:
                _r = await _ba(_aid).run(_ctx, _inp)
                emit("agent_decision", _r.output.summary, agent=_aid, payload={"mode": _r.mode})
                db.add(models.AgentDecision(run_id=run_id, agent=_aid, decision=_r.output.summary,
                                            justification="assurance analysis (deterministic/hybrid)", confidence=_r.output.confidence,
                                            model=_r.model, mode=_r.mode, evidence_refs=_r.evidence_refs, asset_ids=[],
                                            data={"fallback_reason": _r.fallback_reason}))
            except Exception as _e:  # noqa: BLE001 - record the failure, keep the loop honest and moving
                _reason = f"{type(_e).__name__}: {_e}"[:220]
                emit("provider_fallback", f"{_aid} failed: {_reason}", agent=_aid)
                db.add(models.AgentDecision(run_id=run_id, agent=_aid, decision="agent failed",
                                            justification=_reason, confidence=0.0, model="deterministic",
                                            mode="offline", evidence_refs=[], asset_ids=[],
                                            data={"fallback_reason": _reason}))
            db.commit()

        # Execute the Commander's optional (non-backbone) steps as a DAG:
        # steps run strictly in plan order — every agent of a step must have
        # finished (the await below) before any agent of a later step starts.
        # Within a step, agents run concurrently only when the step is marked
        # parallel; otherwise they run sequentially in listed order.
        # Authoring-time agents (scenario_author, twin_architect) never run
        # mid-incident: they are skipped with a recorded reason. Every agent
        # that actually runs persists an AgentDecision (success or failure).
        if commander_plan is not None:
            _sem = asyncio.Semaphore(4)
            _backbone = {"observer", "incident_investigator", "defense_strategist", "defense_executor", "verification_scientist"}
            _authoring = {"scenario_author", "twin_architect"}
            _finished_steps: list[int] = []

            async def _run_optional(_aid: str):
                async with _sem:
                    _t0 = time.monotonic()
                    try:
                        if _aid == "threat_intel_analyst":
                            _inp = _aio.TelemetryIn(telemetry=telemetry)
                        elif _aid == "red_team_planner":
                            _inp = _aio.CampaignIn(source_asset=scenario["source_asset"], target_asset=scenario["target_asset"])
                        elif _aid in ("config_engineer", "business_impact_analyst"):
                            _inp = _aio.ExecuteIn(actions=[])
                        else:
                            _inp = _aio.TextIn()
                        _res = await _ba(_aid).run(_ctx, _inp)
                        return _res, None, int((time.monotonic() - _t0) * 1000)
                    except Exception as _exc:  # noqa: BLE001 - reported by caller as a failed decision
                        return None, f"{type(_exc).__name__}: {_exc}"[:220], int((time.monotonic() - _t0) * 1000)

            for _step in commander_plan.plan:
                _optional = [a for a in _step.agents if a not in _backbone]
                if not _optional:
                    _finished_steps.append(_step.step)
                    continue
                _depends_on = list(_finished_steps)
                _runnable: list[str] = []
                for _aid in _optional:
                    if _aid in _authoring:
                        emit("plan_step_skipped",
                             f"Commander step {_step.step}: {_aid} skipped — authoring-time agent, not incident-relevant mid-run",
                             agent="incident_commander",
                             payload={"step": _step.step, "agent": _aid, "skipped": True,
                                      "reason": "authoring-time agent (scenario_author/twin_architect) excluded from in-run optional steps",
                                      "depends_on_steps": _depends_on})
                    else:
                        _runnable.append(_aid)
                if _runnable:
                    _step_started_at = datetime.now(timezone.utc).isoformat()
                    _step_t0 = time.monotonic()
                    for _aid in _runnable:
                        emit("plan_step_started", f"Commander step {_step.step}: {_aid} starting", agent="incident_commander",
                             payload={"step": _step.step, "agent": _aid, "started_at": _step_started_at,
                                      "depends_on_steps": _depends_on})
                    if _step.parallel:
                        _results = await asyncio.gather(*[_run_optional(a) for a in _runnable])
                    else:
                        _results = []
                        for _a in _runnable:  # sequential: listed order, each awaited
                            _results.append(await _run_optional(_a))
                    _step_finished_at = datetime.now(timezone.utc).isoformat()
                    _step_duration_ms = int((time.monotonic() - _step_t0) * 1000)
                    for _aid, (_r, _err, _agent_ms) in zip(_runnable, _results):
                        emit("plan_step_finished", f"Commander step {_step.step}: {_aid} {'done' if _r else 'failed'}",
                             agent="incident_commander",
                             payload={"step": _step.step, "agent": _aid, "ok": _r is not None,
                                      "started_at": _step_started_at, "finished_at": _step_finished_at,
                                      "duration_ms": _agent_ms, "step_duration_ms": _step_duration_ms,
                                      "depends_on_steps": _depends_on})
                        if _r is not None:
                            _out = _r.output
                            _decision = str(getattr(_out, "summary", None) or getattr(_out, "hypothesis", None)
                                            or _out.model_dump_json()[:220])
                            emit("agent_decision", _decision, agent=_aid, payload={"mode": _r.mode, "plan_step": _step.step})
                            db.add(models.AgentDecision(
                                run_id=run_id, agent=_aid, decision=_decision,
                                justification=f"commander optional step {_step.step} (after steps {_depends_on})",
                                confidence=_r.confidence, model=_r.model, mode=_r.mode,
                                evidence_refs=_r.evidence_refs, asset_ids=[],
                                data={"fallback_reason": _r.fallback_reason, "plan_step": _step.step,
                                      "duration_ms": _agent_ms}))
                        else:
                            db.add(models.AgentDecision(
                                run_id=run_id, agent=_aid, decision="agent failed",
                                justification=_err or "optional agent failed", confidence=0.0,
                                model="deterministic", mode="offline", evidence_refs=[], asset_ids=[],
                                data={"fallback_reason": _err, "plan_step": _step.step,
                                      "duration_ms": _agent_ms}))
                    db.commit()
                # DAG barrier: this step is finished before the next begins.
                _finished_steps.append(_step.step)
        db.add(models.AgentDecision(run_id=run_id, agent="observer", decision=obs.anomaly_type,
                                    justification=obs.summary, confidence=obs.confidence, model="deterministic",
                                    mode="offline", evidence_refs=obs.event_ids, asset_ids=obs.asset_ids)); db.commit()
        emit("agent_decision", obs.summary, agent="observer", payload=obs.model_dump())
        board.publish("observer", "observation", obs.model_dump(), evidence_refs=obs.event_ids)

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
        hyp = await _fw_investigate(scenario, obs, telemetry)
        if hyp.fallback_reason:
            emit("provider_fallback", f"Investigator fell back to offline: {hyp.fallback_reason}", agent="incident_investigator")
        db.add(models.AgentDecision(run_id=run_id, agent="incident_investigator", decision=hyp.hypothesis,
                                    justification="; ".join(hyp.confirmed), confidence=hyp.confidence, model=hyp.model,
                                    mode=hyp.mode, evidence_refs=hyp.evidence_refs, asset_ids=hyp.affected_assets,
                                    data={"claim_evidence": hyp.claim_evidence, "confirmed_items": hyp.confirmed_items,
                                          "citation_warnings": hyp.citation_warnings})); db.commit()
        emit("agent_decision", hyp.hypothesis, agent="incident_investigator", payload=hyp.model_dump())
        board.publish("incident_investigator", "hypothesis", hyp.model_dump(), evidence_refs=hyp.evidence_refs)

        # race against time: the attack advances one hop per 2.0s of simulated time;
        # live model latency is converted to simulated time, so slow reasoning costs nodes
        live_latency = sum(u["latency_ms"] for u in meta_client.usage_snapshot(run_id))
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
        defense_rejection: dict = {"reason": None}

        async def defend(hyp_obj, round_num: int, extra_context: str = "") -> tuple[list, float | None]:
            """Propose -> simulate -> AI final choice -> critic -> policy -> [approval] -> apply. Fully recorded."""
            await set_state("DEFENSE_PROPOSED", f"[round {round_num}] Defense strategist proposing countermeasure", "defense_strategist")
            proposal = await _fw_propose_with_context(scenario, hyp_obj, extra_context)
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
            board.publish("defense_strategist", "proposal", proposal.model_dump(), evidence_refs=proposal.evidence_refs)

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
                board.publish("defense_strategist", "final_choice",
                              {k: choice[k] for k in ("chosen_label", "justification", "confidence", "mode", "ai_matched_optimum", "candidates_considered")},
                              evidence_refs=proposal.evidence_refs)
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
                        proposal = await _fw_propose_with_context(
                            scenario, hyp_obj,
                            extra_context=(f"RED CRITIC: your previous defense can be bypassed via {' -> '.join(critic['bypass'])}. "
                                           f"Assessment: {critic['assessment']}. Propose a revised defense that also covers this bypass."))
                        db.add(models.DefenseProposal(run_id=run_id, actions=[a.model_dump() for a in proposal.actions],
                                                      justification=f"[revision after critic] {proposal.justification}",
                                                      confidence=proposal.confidence, mode=proposal.mode)); db.commit()
                        emit("agent_decision", f"[revision] {proposal.justification}", agent="defense_strategist", payload=proposal.model_dump())
                        board.publish("defense_strategist", "proposal", proposal.model_dump(), evidence_refs=proposal.evidence_refs)
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
                board.publish("defense_executor", "decision", d.model_dump())
            db.commit()

            # human approval gate for high-disruption defenses
            needs_approval = [d for d in decisions if d.requires_human_approval]
            disrupted_est = chosen_cand["disrupted"] if chosen_cand else None
            if settings.human_approval_enabled and disrupted_est is not None and disrupted_est >= 2:
                if settings.auto_approve:
                    emit("approval_auto", f"Auto-approved (demo setting): '{chosen_cand['label']}' disrupts {disrupted_est} legitimate paths — logged, not hidden",
                         agent="defense_executor", payload={"actions": [a.model_dump() for a in chosen], "disrupted": disrupted_est,
                                                            "requires_human_approval": bool(needs_approval)})
                else:
                    await set_state("AWAITING_APPROVAL", "Awaiting human approval for high-disruption defense", "defense_executor")
                    entry = {"event": asyncio.Event(), "approved": None}
                    _approvals[run_id] = entry
                    emit("approval_required", f"Human approval required: '{chosen_cand['label']}' disrupts {disrupted_est} legitimate paths. Approve in the UI.",
                         agent="defense_executor", payload={"actions": [a.model_dump() for a in chosen], "disrupted": disrupted_est})
                    approval_timed_out = False
                    try:
                        await asyncio.wait_for(entry["event"].wait(), timeout=settings.approval_timeout_seconds)
                        approved_by_human = bool(entry["approved"])
                    except asyncio.TimeoutError:
                        approved_by_human = False
                        approval_timed_out = True
                        emit("approval_timeout", f"Human approval auto-denied after {settings.approval_timeout_seconds}s — defense NOT applied", agent="defense_executor")
                    _approvals.pop(run_id, None)
                    if not approved_by_human:
                        # Operator rejection is not a run failure: apply nothing,
                        # contain nothing (t_contained=None), and let verification
                        # replay the attack and honestly FAIL. The run still
                        # finishes COMPLETED below; red-team rounds are skipped.
                        defense_rejection["reason"] = (
                            "defense rejected: approval timed out (auto-denied) — defense not applied"
                            if approval_timed_out else
                            "defense rejected by operator — defense not applied")
                        emit("defense_rejected", defense_rejection["reason"], agent="defense_executor")
                        return candidates, None
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
            board.publish("verification_scientist", "report", res.model_dump(), evidence_refs=res.evidence_refs)
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

        if scenario["verification_kind"] == "reachability" and not defense_rejection["reason"]:
            # max_rounds (scenario JSON) is the single source of truth: total
            # campaign rounds INCLUDING round 1 above, so adaptive retries are
            # rounds 2..max_rounds. Scenarios without max_rounds keep the
            # historical default of 4 total rounds.
            try:
                _max_rounds = int(scenario.get("max_rounds") or 4)
            except (TypeError, ValueError):
                _max_rounds = 4
            _max_rounds = max(1, _max_rounds)
            for round_num in range(2, _max_rounds + 1):
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
                board.publish("adversary_simulator", "campaign", plan.model_dump())
                # apply the campaign as this round's attack (typed steps only)
                round_scenario = {**scenario, "id": f"{scenario['id']}-r{round_num}",
                                  "source_asset": plan.foothold, "target_asset": plan.objective,
                                  "attack_steps": [s.model_dump() for s in plan.steps], "identity": None}
                if twin.decoys.intersection(chosen_path):
                    emit("decoy_tripped", f"DECOY TRIPPED: red campaign touched a decoy on path {' -> '.join(chosen_path)} — high-confidence detection; branch frozen",
                         agent="observer", asset_id=next(iter(twin.decoys.intersection(chosen_path))),
                         payload={"decoys": sorted(twin.decoys.intersection(chosen_path))})
                    emit("telemetry", f"Decoy telemetry: traversal frozen at {next(iter(twin.decoys.intersection(chosen_path)))}",
                         agent="observer", payload={"event_type": "security_detection", "asset_id": next(iter(twin.decoys.intersection(chosen_path)))})
                    db.add(models.AgentDecision(run_id=run_id, agent="observer", decision="decoy_tripped",
                                                justification="red traversal touched a decoy asset; branch frozen", confidence=0.99,
                                                model="deterministic", mode="offline", evidence_refs=[], asset_ids=chosen_path)); db.commit()
                    rounds.append({"round": round_num, "foothold": plan.foothold, "objective": plan.objective,
                                   "path": chosen_path, "red_mode": plan.mode, "blue_mode": "detection",
                                   "effectiveness_pct": result.metrics["defense_effectiveness_pct"],
                                   "resilience_score": resilience_now(), "outcome": "DECOY_TRIPPED",
                                   "disrupted": 0, "red_team_mode": plan.mode})
                    break
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
                hyp2 = await _fw_investigate(scenario, obs2, red_telemetry)
                db.add(models.AgentDecision(run_id=run_id, agent="incident_investigator", decision=hyp2.hypothesis,
                                            justification="; ".join(hyp2.confirmed), confidence=hyp2.confidence, model=hyp2.model,
                                            mode=hyp2.mode, evidence_refs=hyp2.evidence_refs, asset_ids=hyp2.affected_assets,
                                            data={"claim_evidence": hyp2.claim_evidence, "round": round_num})); db.commit()
                board.publish("incident_investigator", "hypothesis", hyp2.model_dump(), evidence_refs=hyp2.evidence_refs)
                _c, round_contained = await defend(hyp2, round_num)
                if defense_rejection["reason"]:
                    # A rejection in a later adaptive round stops the campaign
                    # rounds; the run's final verdict stays the last verified
                    # (primary) result, re-verified at the end below. Only a
                    # round-1 rejection makes the run's verification FAIL.
                    rounds.append({"round": round_num, "foothold": plan.foothold, "objective": plan.objective,
                                   "path": chosen_path, "red_mode": plan.mode, "blue_mode": hyp2.mode,
                                   "effectiveness_pct": result.metrics["defense_effectiveness_pct"],
                                   "resilience_score": resilience_now(), "outcome": "DEFENSE_REJECTED",
                                   "defense_rejection_reason": defense_rejection["reason"],
                                   "disrupted": result.metrics["operational_impact_disrupted_legit_paths"],
                                   "red_team_mode": plan.mode})
                    defense_rejection["reason"] = None
                    scenario = original_scenario
                    break
                sim_contained = round_contained
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
        result.metrics["max_rounds"] = scenario.get("max_rounds")
        result.metrics["candidates"] = candidates
        result.metrics["ai_final_choice"] = {"mode": final_choice_meta.get("mode"),
                                             "chosen_label": final_choice_meta.get("chosen_label"),
                                             "justification": final_choice_meta.get("justification"),
                                             "confidence": final_choice_meta.get("confidence")}
        result.metrics["ai_matched_optimum"] = final_choice_meta.get("ai_matched_optimum")
        result.metrics["candidates_considered"] = final_choice_meta.get("candidates_considered")
        if defense_rejection["reason"]:
            result.metrics["defense_rejected"] = True
            result.metrics["defense_rejection_reason"] = defense_rejection["reason"]
            result.metrics["failure_reason"] = defense_rejection["reason"]
        latest_ver = db.query(models.VerificationResultRow).filter_by(run_id=run_id).order_by(
            models.VerificationResultRow.created_at.desc()).first()
        if latest_ver:
            latest_ver.metrics = dict(result.metrics); db.commit()
        db.add(models.AgentDecision(run_id=run_id, agent="verification_scientist", decision=f"VERIFICATION {result.outcome}",
                                    justification=result.invariant, confidence=1.0, model="deterministic-replay",
                                    mode="offline", evidence_refs=result.evidence_refs, asset_ids=[scenario["target_asset"]])); db.commit()
        # run.mode reflects every persisted decision for the run, not only the
        # investigator: any live decision alongside any offline one is "mixed".
        decision_modes = {m for (m,) in db.query(models.AgentDecision.mode).filter_by(run_id=run_id).all() if m}
        if decision_modes == {"live"}:
            run.mode = "live"
        elif decision_modes == {"offline"}:
            run.mode = "offline"
        elif decision_modes:
            run.mode = "mixed"
        db.commit()

        if result.outcome == "PASS":
            for aid, st in list(twin.status.items()):
                if aid == scenario["target_asset"] and st in ("suspicious", "compromised"):
                    twin.status[aid] = "protected"  # target held: evidence of the attempt remains in the audit trail
                elif st in ("suspicious", "compromised") and not twin.isolated.get(aid):
                    twin.status[aid] = "cleared"  # attacker was here, now cleared — distinct from never-touched "healthy"

        for u in meta_client.usage_snapshot(run_id, clear=True):
            db.add(models.ModelUsage(run_id=run_id, model=u["model"], prompt_version=u["prompt_version"],
                                     prompt_hash=u.get("prompt_hash", ""),
                                     prompt_tokens=u["prompt_tokens"], completion_tokens=u["completion_tokens"],
                                     latency_ms=u["latency_ms"], success=u["success"], error=u.get("error")))
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
