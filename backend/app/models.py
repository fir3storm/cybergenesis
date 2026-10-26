import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _id() -> str:
    return uuid.uuid4().hex[:16]


def _now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    email: Mapped[str] = mapped_column(String, unique=True, default="local@cybergenesis.dev")
    role: Mapped[str] = mapped_column(String, default="operator")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class InfrastructureAsset(Base):
    __tablename__ = "infrastructure_assets"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    asset_type: Mapped[str] = mapped_column(String)
    zone: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="healthy")
    posture: Mapped[float] = mapped_column(Float, default=0.9)
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class AssetConnection(Base):
    __tablename__ = "asset_connections"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    source: Mapped[str] = mapped_column(String)
    target: Mapped[str] = mapped_column(String)
    trust: Mapped[str] = mapped_column(String, default="medium")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    traversable: Mapped[bool] = mapped_column(Boolean, default=True)


class AssetStateSnapshot(Base):
    __tablename__ = "asset_state_snapshots"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    run_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    label: Mapped[str] = mapped_column(String)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Scenario(Base):
    __tablename__ = "scenarios"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    definition: Mapped[dict] = mapped_column(JSON, default=dict)


class SimulationRun(Base):
    __tablename__ = "simulation_runs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    scenario_id: Mapped[str] = mapped_column(String, index=True)
    seed: Mapped[int] = mapped_column(Integer, default=42)
    state: Mapped[str] = mapped_column(String, default="IDLE", index=True)
    mode: Mapped[str] = mapped_column(String, default="offline")  # live | offline
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)


class SimulationEvent(Base):
    __tablename__ = "simulation_events"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    run_id: Mapped[str] = mapped_column(String, ForeignKey("simulation_runs.id"), index=True)
    event_type: Mapped[str] = mapped_column(String, index=True)
    agent: Mapped[str | None] = mapped_column(String, nullable=True)
    asset_id: Mapped[str | None] = mapped_column(String, nullable=True)
    message: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AgentDecision(Base):
    __tablename__ = "agent_decisions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    run_id: Mapped[str] = mapped_column(String, index=True)
    agent: Mapped[str] = mapped_column(String)
    decision: Mapped[str] = mapped_column(String)
    justification: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    model: Mapped[str] = mapped_column(String, default="deterministic")
    mode: Mapped[str] = mapped_column(String, default="offline")
    evidence_refs: Mapped[list] = mapped_column(JSON, default=list)
    asset_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DefenseProposal(Base):
    __tablename__ = "defense_proposals"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    run_id: Mapped[str] = mapped_column(String, index=True)
    actions: Mapped[list] = mapped_column(JSON, default=list)
    justification: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    mode: Mapped[str] = mapped_column(String, default="offline")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PolicyEvaluation(Base):
    __tablename__ = "policy_evaluations"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    run_id: Mapped[str] = mapped_column(String, index=True)
    action_type: Mapped[str] = mapped_column(String)
    asset_id: Mapped[str] = mapped_column(String)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DefenseExecution(Base):
    __tablename__ = "defense_executions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    run_id: Mapped[str] = mapped_column(String, index=True)
    action_type: Mapped[str] = mapped_column(String)
    asset_id: Mapped[str] = mapped_column(String)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    transition: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class VerificationResultRow(Base):
    __tablename__ = "verification_results"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    run_id: Mapped[str] = mapped_column(String, index=True)
    outcome: Mapped[str] = mapped_column(String)  # PASS | FAIL | INCONCLUSIVE
    invariant: Mapped[str] = mapped_column(Text, default="")
    checks: Mapped[list] = mapped_column(JSON, default=list)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class EvidenceRecord(Base):
    __tablename__ = "evidence_records"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    run_id: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String)
    ref: Mapped[str] = mapped_column(String)
    summary: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ModelUsage(Base):
    __tablename__ = "model_usage"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    run_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    model: Mapped[str] = mapped_column(String)
    prompt_version: Mapped[str] = mapped_column(String, default="v1")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
