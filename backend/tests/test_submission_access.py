import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.orchestration import orchestrator


@pytest.mark.parametrize('method,path,body', [
    ('post', '/api/twin/reset', {}),
    ('post', '/api/experiments/missing/approve', {'approved': True}),
    ('post', '/api/experiments/missing/deny', {}),
    ('get', '/api/experiments/missing/approval', None),
    ('post', '/api/arena/matches', {'scenario_id': 'ransomware_activity'}),
])
def test_operator_gate_precedes_mutation_or_token_disclosure(monkeypatch, tmp_path, method, path, body):
    monkeypatch.setattr(settings, 'admin_token', 'review-operator')
    monkeypatch.setattr(settings, 'arena_memory_path', str(tmp_path / 'memory.json'))
    client = TestClient(app)
    assert client.request(method, path, json=body).status_code == 403
    assert client.request(method, path, json=body, headers={'x-admin-token': 'wrong'}).status_code == 403


def test_operator_can_read_approval_without_exposing_token_to_anonymous(monkeypatch):
    monkeypatch.setattr(settings, 'admin_token', 'review-operator')
    client = TestClient(app)
    # Authentication succeeds; the unknown run is then correctly rejected.
    assert client.get('/api/experiments/missing/approval', headers={'x-admin-token': 'review-operator'}).status_code == 404
    assert client.get('/api/health').status_code == 200


def test_mobile_capability_remains_single_use_with_operator_gate(monkeypatch):
    monkeypatch.setattr(settings, 'admin_token', 'review-operator')
    entry = {'token': 'one-time-review', 'event': asyncio.Event(), 'approved': None,
             'expires_at': time.time() + 60}
    monkeypatch.setitem(orchestrator._approvals, 'review-run', entry)
    client = TestClient(app)
    assert client.post('/api/m/approve/review-run', json={'t': 'wrong', 'approved': True}).status_code == 403
    assert client.post('/api/m/approve/review-run', json={'t': 'one-time-review', 'approved': True}).status_code == 200
    assert client.post('/api/m/approve/review-run', json={'t': 'one-time-review', 'approved': True}).status_code == 403


def test_cors_allows_configured_host_only(monkeypatch):
    # A fresh process reads the deploy environment before building middleware.
    import os
    import subprocess
    import sys
    env = {**os.environ, 'CORS_ORIGINS': '["https://judge.example"]'}
    code = '''
from fastapi.testclient import TestClient
from app.main import app
c = TestClient(app)
for origin, expected in [('https://judge.example', 200), ('https://untrusted.example', 400)]:
    r = c.options('/api/experiments', headers={'Origin': origin, 'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'x-admin-token,content-type'})
    assert r.status_code == expected, (origin, r.status_code)
'''
    result = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_cli_socket_requires_operator_token(monkeypatch):
    from starlette.websockets import WebSocketDisconnect
    monkeypatch.setattr(settings, 'admin_token', 'review-operator')
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect) as denied, client.websocket_connect('/ws/cli/firewall'):
        pass
    assert denied.value.code == 1008
    with client.websocket_connect('/ws/cli/firewall?t=review-operator') as socket:
        socket.send_json({'input': 'help'})
        assert socket.receive_json()['event_type'] == 'cli_output'


def test_pinned_dotenv_operator_token_is_not_bootstrapped(monkeypatch):
    from app import main
    monkeypatch.delenv('ADMIN_TOKEN', raising=False)
    monkeypatch.setattr(settings, 'admin_token', 'pinned-dotenv-token')
    monkeypatch.setattr(main, '_is_loopback', lambda request: True)
    with TestClient(app) as client:
        assert 'admin_token' not in client.get('/api/settings/providers').json()
