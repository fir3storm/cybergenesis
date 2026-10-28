from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    # Lightweight additive migrations for pre-existing SQLite dev databases.
    # The ALTER TABLE syntax below (VARCHAR without length, JSON column type)
    # is SQLite-specific and would fail on PostgreSQL, where create_all above
    # already creates the correct columns on a fresh database — so only run
    # these on SQLite.
    if engine.dialect.name == "sqlite":
        from sqlalchemy import inspect, text

        insp = inspect(engine)
        if "simulation_runs" in insp.get_table_names():
            cols = {c["name"] for c in insp.get_columns("simulation_runs")}
            with engine.begin() as conn:
                for col in ("custom_twin_id", "custom_scenario_id"):
                    if col not in cols:
                        conn.execute(text(f"ALTER TABLE simulation_runs ADD COLUMN {col} VARCHAR"))
        if "agent_decisions" in insp.get_table_names():
            cols = {c["name"] for c in insp.get_columns("agent_decisions")}
            if "data" not in cols:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE agent_decisions ADD COLUMN data JSON"))
        if "model_usage" in insp.get_table_names():
            cols = {c["name"] for c in insp.get_columns("model_usage")}
            if "prompt_hash" not in cols:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE model_usage ADD COLUMN prompt_hash VARCHAR DEFAULT ''"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
