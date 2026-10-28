"""Paired synthetic evaluation. Training and held-out cases are separate; no online learning during scoring."""
import hashlib
import json
import random
import time
from datetime import UTC, datetime

from app.arena.engine import play_match_async
from app.arena.learning import ArenaMemory
from app.arena.service import _choosers
from app.integrations.meta_client import meta_client
from app.simulation.twin import DigitalTwin


def make_case(seed: int, name: str) -> tuple[dict, DigitalTwin]:
    rng = random.Random(seed)
    branches = rng.randint(2, 4)
    names = ['employee-workstation', 'file-server'] + [f'relay-{i}' for i in range(branches)]
    assets = [{'id': n, 'name': n, 'asset_type': 'app_server', 'zone': 'synthetic',
               'posture': rng.uniform(0.2, 0.8), 'pos': [0, 0, 0],
               'vulnerabilities': ['legacy_unpatched']} for n in names]
    edges = [{'source': a, 'target': b, 'traversable': True} for i in range(branches)
             for a, b in [('employee-workstation', f'relay-{i}'), (f'relay-{i}', 'file-server')]]
    scenario = {'id': name, 'name': name, 'source_asset': 'employee-workstation', 'target_asset': 'file-server',
                'verification_kind': 'reachability', 'attack_steps': [], 'expected_defense': []}
    return scenario, DigitalTwin.from_dict(assets, edges)


async def evaluate_strategies(cases: int = 5, training_matches: int = 5, seed: int = 42, live: bool = False) -> dict:
    if not 1 <= cases <= 30 or not 0 <= training_matches <= 30:
        raise ValueError('cases must be 1..30 and training_matches 0..30')
    memory = ArenaMemory()
    training_ids = []
    for i in range(training_matches):
        scenario, twin = make_case(seed + i, f'train-{i}')
        training_ids.append(scenario['id'])
        context = memory.for_context(scenario['id'], None)
        red, blue = _choosers('learned', context)
        context.record_match(await play_match_async(scenario, twin=twin, red_chooser=red, blue_chooser=blue))
    frozen = json.dumps(memory.data, sort_keys=True)
    rows = []
    for i in range(cases):
        scenario, twin = make_case(seed + 10000 + i, f'heldout-{i}')
        for strategy in ['deterministic', 'learned'] + (['ai'] if live else []):
            run_id = f'eval-{seed}-{i}-{strategy}-{time.time_ns()}'
            context = ArenaMemory(json.loads(frozen)).for_context(scenario['id'], None)
            red, blue = _choosers(strategy, context)
            if strategy == 'ai':
                red.run_id = blue.run_id = run_id
            start = time.perf_counter()
            result = await play_match_async(scenario, twin=twin, red_chooser=red, blue_chooser=blue)
            modes = {d['mode'] for d in result['decisions']}
            mode = 'live' if modes == {'live'} else ('mixed' if 'live' in modes else 'offline')
            rows.append({'case_id': scenario['id'], 'case_seed': seed + 10000 + i, 'strategy': strategy,
                         'prior_matches': context.summary()['matches'], 'mode': mode, 'winner': result['winner'], 'rounds': result['rounds_played'],
                         'disrupted': result['total_disrupted'], 'latency_ms': round((time.perf_counter()-start)*1000, 1),
                         'tokens': meta_client.tokens_used(run_id),
                         'fallbacks': sum(bool(d.get('fallback_reason')) for d in result['decisions']),
                         'decisions': result['decisions'], 'config_hash': twin.config_hash()})
    summary = {}
    for strategy in dict.fromkeys(r['strategy'] for r in rows):
        group = [r for r in rows if r['strategy'] == strategy]
        summary[strategy] = {'cases': len(group), 'blue_wins': sum(r['winner'] == 'blue' for r in group),
                             'mean_disrupted': sum(r['disrupted'] for r in group)/len(group),
                             'mean_latency_ms': round(sum(r['latency_ms'] for r in group)/len(group), 1),
                             'tokens': sum(r['tokens'] for r in group),
                             'live_cases': sum(r['mode'] == 'live' for r in group),
                             'fallbacks': sum(r['fallbacks'] for r in group)}
    return {'version': 1, 'created_at': datetime.now(UTC).isoformat(), 'seed': seed,
            'live_requested': live, 'training_cases': training_ids,
            'heldout_cases': [f'heldout-{i}' for i in range(cases)],
            'evaluation_memory_unchanged': frozen == json.dumps(memory.data, sort_keys=True),
            'memory_sha256': hashlib.sha256(frozen.encode()).hexdigest(), 'summary': summary, 'cases': rows,
            'limitations': 'Small generated synthetic topologies; different seeds can share topology structure. '
                            'Paired full-team comparison, not an isolated model ablation. '
                            'Unseen scenarios start with zero prior matches, matching production scope; this measures cold-start behavior, not learning improvement. '
                            'No claim of production resilience or improvement; ties are reported as ties.'}
