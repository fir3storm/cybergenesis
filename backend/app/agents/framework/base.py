import asyncio
import time
from dataclasses import dataclass, field
from typing import Generic, TypeVar

from pydantic import BaseModel

from app.agents.framework.spec import AgentSpec
from app.agents.framework.tools import ToolExecutor
from app.core.config import settings
from app.integrations.meta_client import meta_client

Out = TypeVar("Out", bound=BaseModel)


@dataclass
class AgentContext:
    run_id: str
    twin: object
    scenario: dict = field(default_factory=dict)
    telemetry: list = field(default_factory=list)
    findings: list = field(default_factory=list)
    memory: list = field(default_factory=list)
    baseline_twin: object = None
    bus: object = None


class AgentResult(BaseModel, Generic[Out]):
    agent_id: str
    output: Out
    mode: str = "offline"  # live|offline
    fallback_reason: str | None = None
    confidence: float = 0.0
    evidence_refs: list[str] = []
    model: str = "deterministic"
    prompt_version: str = ""
    prompt_hash: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    tool_calls: list[dict] = []


class Agent(Generic[Out]):
    spec: AgentSpec

    def __init__(self, spec: AgentSpec):
        self.spec = spec
        self.tools = ToolExecutor(spec.tools)

    async def live(self, ctx: AgentContext, inp: BaseModel) -> Out:
        raise NotImplementedError

    async def offline(self, ctx: AgentContext, inp: BaseModel) -> Out:
        raise NotImplementedError

    async def run(self, ctx: AgentContext, inp) -> AgentResult[Out]:
        spec = self.spec
        inp_obj = spec.input_model.model_validate(inp if isinstance(inp, dict) else inp.model_dump())
        started = time.time()
        before_in = before_out = 0
        if spec.engine in ("meta", "hybrid"):
            snap = meta_client.usage_snapshot(ctx.run_id)
            before_in = sum(u["prompt_tokens"] for u in snap)
            before_out = sum(u["completion_tokens"] for u in snap)
        mode, reason, output = "offline", None, None
        try:
            if spec.engine == "deterministic":
                output = await asyncio.wait_for(self.offline(ctx, inp_obj), timeout=spec.timeout_s)
            elif not meta_client.configured:
                raise RuntimeError("Meta provider not configured (offline mode)")
            elif meta_client.tokens_used(ctx.run_id) >= settings.max_tokens_per_run:
                raise RuntimeError(f"per-run token budget exhausted ({settings.max_tokens_per_run})")
            else:
                output = await asyncio.wait_for(self.live(ctx, inp_obj), timeout=spec.timeout_s)
                mode = "live"
        except Exception as e:  # noqa: BLE001 - every failure becomes a labelled offline fallback
            reason = f"{type(e).__name__}: {e}"[:220]
            output = await self.offline(ctx, inp_obj)
            mode = "offline"
        output = spec.output_model.model_validate(output if isinstance(output, dict) else output.model_dump())
        latency = int((time.time() - started) * 1000)
        tokens_in = tokens_out = 0
        if spec.engine in ("meta", "hybrid"):
            snap = meta_client.usage_snapshot(ctx.run_id)
            tokens_in = sum(u["prompt_tokens"] for u in snap) - before_in
            tokens_out = sum(u["completion_tokens"] for u in snap) - before_out
            if tokens_in + tokens_out > spec.max_tokens:
                reason = (reason + "; " if reason else "") + f"agent token budget {spec.max_tokens} exceeded by this call"
        if ctx.bus is not None:
            ctx.bus.publish(spec.id, "decision",
                            {"mode": mode, "fallback_reason": reason, "latency_ms": latency},
                            evidence_refs=list(getattr(output, "evidence_refs", []) or []))
        return AgentResult(agent_id=spec.id, output=output, mode=mode, fallback_reason=reason,
                           confidence=float(getattr(output, "confidence", 0.0) or 0.0),
                           evidence_refs=list(getattr(output, "evidence_refs", []) or []),
                           model=meta_client.model if mode == "live" else "deterministic-offline",
                           prompt_version=spec.prompt_version, prompt_hash=spec.prompt_hash,
                           tokens_in=tokens_in, tokens_out=tokens_out, latency_ms=latency,
                           tool_calls=list(self.tools.log))
