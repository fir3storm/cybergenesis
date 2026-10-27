import os
import sys

os.environ["OFFLINE_MODE"] = "true"
os.environ["SIM_STEP_DELAY_MS"] = "0"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from app.agents.framework.base import Agent, AgentContext  # noqa: E402
from app.agents.framework.bus import Blackboard  # noqa: E402
from app.agents.framework.registry import REGISTRY  # noqa: E402
from app.agents.framework.spec import AgentSpec  # noqa: E402
from app.agents.framework.tools import ToolExecutor, ToolRefused  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app import models  # noqa: E402
from app.main import app  # noqa: E402
from app.simulation.twin import DigitalTwin  # noqa: E402

client = TestClient(app)
init_db()


class In(BaseModel):
    text: str = ""


class Out(BaseModel):
    summary: str = ""
    confidence: float = 0.5


def spec_for(live_impl="ok"):
    return AgentSpec(id="test-agent", name="Test", team="blue", engine="meta", input_model=In, output_model=Out,
                     tools=["get_twin_summary"], timeout_s=0.2, prompt_file="observer.md")


class OkAgent(Agent):
    async def live(self, ctx, inp):
        return Out(summary="live", confidence=0.9)

    async def offline(self, ctx, inp):
        return Out(summary="offline", confidence=0.5)


class SlowAgent(Agent):
    async def live(self, ctx, inp):
        await asyncio.sleep(2)
        return Out(summary="slow")

    async def offline(self, ctx, inp):
        return Out(summary="offline-after-timeout", confidence=0.4)


class BadJsonAgent(Agent):
    async def live(self, ctx, inp):
        raise ValueError("malformed JSON from provider")

    async def offline(self, ctx, inp):
        return Out(summary="offline-after-malformed", confidence=0.4)


def ctx():
    return AgentContext(run_id="fw-test", twin=DigitalTwin(), telemetry=[{"event_type": "x"}])


@pytest.mark.asyncio
async def test_fallback_after_timeout_and_malformed(monkeypatch):
    from app.integrations import meta_client as mc

    monkeypatch.setattr(mc.meta_client, "key", "k")
    monkeypatch.setattr(mc.settings, "offline_mode", False)
    r = await SlowAgent(spec_for("slow")).run(ctx(), In())
    assert r.mode == "offline" and "TimeoutError" in (r.fallback_reason or "") or "timeout" in (r.fallback_reason or "").lower()
    r2 = await BadJsonAgent(spec_for("bad")).run(ctx(), In())
    assert r2.mode == "offline" and r2.output.summary == "offline-after-malformed"
    assert r2.prompt_version.startswith("cybergenesis-") and r2.prompt_hash


@pytest.mark.asyncio
async def test_offline_when_unconfigured():
    r = await OkAgent(spec_for("ok")).run(ctx(), In(text="hi"))
    assert r.mode == "offline" and r.fallback_reason  # no key in test env


def test_tool_permission_refusal():
    ex = ToolExecutor(["get_twin_summary"])
    with pytest.raises(ToolRefused):
        ex.call(ctx(), "explain_path", {"src": "internet", "dst": "database"})
    with pytest.raises(ToolRefused):
        ex.call(ctx(), "nuke_everything", {})
    assert any("refused" in str(x) for x in ex.log)


def test_token_budget_cutoff(monkeypatch):
    from app.core.config import settings
    from app.integrations.meta_client import ProviderUnavailable, meta_client

    monkeypatch.setattr(settings, "max_tokens_per_run", 0)
    monkeypatch.setattr(meta_client, "key", "k")
    monkeypatch.setattr(settings, "offline_mode", False)
    with pytest.raises(ProviderUnavailable, match="token budget"):
        asyncio.run(meta_client.chat_json("s", "u", run_id="budget-x"))


def test_messages_persisted_and_ordered():
    init_db()
    db = SessionLocal()
    seq = {"n": 0}

    def persist(msg):
        seq["n"] += 1
        db.add(models.AgentMessageRow(id=msg.id, run_id=msg.run_id, from_agent=msg.from_agent, to_agent=msg.to_agent,
                                      kind=msg.kind, payload=msg.payload, evidence_refs=msg.evidence_refs, seq=seq["n"]))
        db.commit()

    bus = Blackboard("fw-run", persist=persist)
    bus.publish("observer", "observation", {"a": 1})
    bus.publish("incident_investigator", "hypothesis", {"h": "x"}, evidence_refs=["tele-1"])
    rows = client.get("/api/experiments/fw-run/messages").json()
    assert [r["kind"] for r in rows] == ["observation", "hypothesis"]
    db.query(models.AgentMessageRow).filter_by(run_id="fw-run").delete(); db.commit(); db.close()


def test_registry_has_ten_agents_and_endpoints():
    assert len(REGISTRY) == 10
    assert client.get("/api/agents").json()[0]["prompt_hash"]
    assert client.get("/api/agents/observer").json()["output_model"] == "AgentObservation"
    assert client.get("/api/agents/nope").status_code == 404
