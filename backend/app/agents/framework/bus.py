import uuid
from datetime import datetime, timezone
from typing import Callable

from pydantic import BaseModel, Field


class AgentMessage(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    run_id: str
    from_agent: str
    to_agent: str | None = None  # None = broadcast
    kind: str = "observation"  # observation|hypothesis|proposal|critique|finding|request|decision|report
    payload: dict = {}
    evidence_refs: list[str] = []
    in_reply_to: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Blackboard:
    """Per-run agent blackboard. Persist/stream callbacks are wired by the orchestrator."""

    def __init__(self, run_id: str, persist: Callable[[AgentMessage], None] | None = None,
                 stream: Callable[[AgentMessage], None] | None = None):
        self.run_id = run_id
        self.messages: list[AgentMessage] = []
        self._persist = persist
        self._stream = stream

    def publish(self, from_agent: str, kind: str, payload: dict, to_agent: str | None = None,
                evidence_refs: list[str] | None = None, in_reply_to: str | None = None) -> AgentMessage:
        msg = AgentMessage(run_id=self.run_id, from_agent=from_agent, to_agent=to_agent, kind=kind,
                           payload=payload, evidence_refs=evidence_refs or [], in_reply_to=in_reply_to)
        self.messages.append(msg)
        if self._persist:
            self._persist(msg)
        if self._stream:
            self._stream(msg)
        return msg

    def for_agent(self, agent_id: str) -> list[AgentMessage]:
        return [m for m in self.messages if m.to_agent in (None, agent_id)]

    def of_kind(self, kind: str) -> list[AgentMessage]:
        return [m for m in self.messages if m.kind == kind]
