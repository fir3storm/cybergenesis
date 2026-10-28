import asyncio
import logging
import threading
import time

import pytest
from fastapi.testclient import TestClient

from app import main
from app.main import app
from app.orchestration import orchestrator


@pytest.fixture(autouse=True)
def _clean_registry():
    yield
    for run_id in list(orchestrator._tasks):
        orchestrator.unregister_task(run_id)


async def test_register_active_unregister():
    async def _pending():
        await asyncio.Event().wait()

    task_a = asyncio.create_task(_pending())
    task_b = asyncio.create_task(_pending())
    try:
        orchestrator.register_task("run-a", task_a)
        orchestrator.register_task("run-b", task_b)
        assert orchestrator.active_runs() == ["run-a", "run-b"]
        orchestrator.unregister_task("run-a", task_a)
        assert orchestrator.active_runs() == ["run-b"]
        orchestrator.unregister_task("run-b")
        assert orchestrator.active_runs() == []
        orchestrator.unregister_task("run-b")  # missing id is a no-op
    finally:
        task_a.cancel()
        task_b.cancel()


async def test_unregister_with_stale_task_keeps_current_entry():
    async def _pending():
        await asyncio.Event().wait()

    stale = asyncio.create_task(_pending())
    current = asyncio.create_task(_pending())
    try:
        orchestrator.register_task("run-x", current)
        orchestrator.unregister_task("run-x", stale)  # old callback must not evict the new task
        assert orchestrator.active_runs() == ["run-x"]
    finally:
        stale.cancel()
        current.cancel()


async def test_completed_task_not_in_active_runs():
    task = asyncio.create_task(asyncio.sleep(0))
    orchestrator.register_task("run-done", task)
    await task
    assert orchestrator.active_runs() == []
    orchestrator.unregister_task("run-done", task)


async def test_done_callback_logs_exception_and_unregisters(caplog):
    async def _boom():
        raise RuntimeError("kaboom")

    task = asyncio.create_task(_boom())
    orchestrator.register_task("run-fail", task)
    task.add_done_callback(lambda done: main._on_experiment_done("run-fail", done))
    with caplog.at_level(logging.ERROR, logger="app.main"):
        for _ in range(100):
            if "run-fail" not in orchestrator._tasks:
                break
            await asyncio.sleep(0.01)
    assert "run-fail" not in orchestrator._tasks
    assert "run-fail" in caplog.text and "kaboom" in caplog.text


async def test_done_callback_unregisters_on_success():
    task = asyncio.create_task(asyncio.sleep(0))
    orchestrator.register_task("run-ok", task)
    task.add_done_callback(lambda done: main._on_experiment_done("run-ok", done))
    for _ in range(100):
        if "run-ok" not in orchestrator._tasks:
            break
        await asyncio.sleep(0.01)
    assert "run-ok" not in orchestrator._tasks
    assert orchestrator.active_runs() == []


def test_endpoint_registers_then_drains(monkeypatch):
    release = threading.Event()

    async def _fake_run(run_id, step_delay_ms=None):
        while not release.is_set():
            await asyncio.sleep(0.01)

    monkeypatch.setattr(orchestrator, "run_experiment", _fake_run)
    # entered TestClient keeps one portal loop alive, so the background
    # task created by the endpoint survives between requests
    with TestClient(app) as client:
        created = client.post("/api/experiments", json={"scenario_id": "ransomware_activity", "seed": 42})
        assert created.status_code == 201, created.text
        run_id = created.json()["id"]
        started = client.post(f"/api/experiments/{run_id}/run", params={"step_delay_ms": 0})
        assert started.status_code == 200, started.text
        assert run_id in orchestrator.active_runs()
        release.set()
        deadline = time.monotonic() + 5
        while run_id in orchestrator._tasks and time.monotonic() < deadline:
            time.sleep(0.01)
        assert run_id not in orchestrator._tasks
        assert run_id not in orchestrator.active_runs()


async def test_shutdown_warns_naming_still_running_runs(caplog):
    task = asyncio.create_task(asyncio.Event().wait())
    orchestrator.register_task("run-shutdown", task)
    try:
        with caplog.at_level(logging.WARNING, logger="app.main"), TestClient(app):
            pass
        assert "still running" in caplog.text and "run-shutdown" in caplog.text
        # shutdown warns only; it does not forcibly cancel the task
        assert not task.done()
        assert orchestrator.active_runs() == ["run-shutdown"]
    finally:
        task.cancel()
        orchestrator.unregister_task("run-shutdown", task)
        with pytest.raises(asyncio.CancelledError):
            await task
