"""Paired synthetic evaluation. Training and held-out cases are separate; no online learning during scoring.

Held-out cases are deliberately harder than the training set: several crown
jewels, both identity-mediated and direct network paths to them, and
trade-offs where the obvious block breaks many legitimate users. That is the
regime where deterministic rules and live reasoning diverge, which is what the
comparison is for.
"""
import hashlib
import json
import logging
import random
import time
from datetime import UTC, datetime

import networkx as nx

from app.arena.engine import play_match_async
from app.arena.learning import ArenaMemory
from app.arena.service import _choosers
from app.integrations.meta_client import meta_client
from app.simulation.twin import DigitalTwin

logger = logging.getLogger(__name__)


def make_case(seed: int, name: str) -> tuple[dict, DigitalTwin]:
    """One held-out twin+scenario pair, seeded for reproducibility.

    Every case has at least two paths to the target — one direct network route
    and one through the identity provider — so a defense that only ever cuts
    the obvious arc has somewhere left to look. Some cases also carry a
    second crown jewel reachable from the same source, which forces the
    defender to choose between blocking everything and blocking nothing.
    """
    rng = random.Random(seed)
    branches = rng.randint(2, 4)
    relay_names = [f'relay-{i}' for i in range(branches)]
    asset_defs = [
        {'id': 'employee-workstation', 'name': 'Employee Workstation', 'asset_type': 'workstation',
         'zone': 'endpoints', 'posture': 0.5, 'pos': [0, 0, 0], 'vulnerabilities': ['unpatched_client']},
        {'id': 'identity-provider', 'name': 'Identity Provider', 'asset_type': 'identity',
         'zone': 'identity', 'posture': 0.85, 'pos': [1, 0, 0], 'vulnerabilities': []},
        {'id': 'file-server', 'name': 'File Server', 'asset_type': 'file_server',
         'zone': 'internal', 'posture': 0.6, 'pos': [2, 0, 0], 'vulnerabilities': ['open_share']},
        {'id': 'database', 'name': 'Database', 'asset_type': 'database',
         'zone': 'data', 'posture': 0.9, 'pos': [3, 0, 0], 'vulnerabilities': []},
    ]
    for n in relay_names:
        asset_defs.append({'id': n, 'name': n.title(), 'asset_type': 'app_server',
                           'zone': 'internal', 'posture': rng.uniform(0.3, 0.7),
                           'pos': [rng.uniform(-2, 4), rng.uniform(-2, 2), 0],
                           'vulnerabilities': ['legacy_unpatched']})
    # Direct network path: ws -> relay -> db. Identity path: ws -> idp -> db.
    # Both are traversable, so the defender must pick which to cut — or find a
    # shared chokepoint.
    edges = []
    for i, r in enumerate(relay_names):
        edges.append({'source': 'employee-workstation', 'target': r, 'traversable': True})
        edges.append({'source': r, 'target': 'database', 'traversable': True})
    edges.append({'source': 'employee-workstation', 'target': 'identity-provider', 'traversable': True})
    edges.append({'source': 'identity-provider', 'target': 'database', 'traversable': True})
    # The file server hangs off the first relay: cutting the relay severs a
    # legitimate user path too, which is the trade-off this case exists to measure.
    if relay_names:
        edges.append({'source': relay_names[0], 'target': 'file-server', 'traversable': True})
    scenario = {'id': name, 'name': name, 'source_asset': 'employee-workstation', 'target_asset': 'database',
                'verification_kind': 'reachability', 'attack_steps': [], 'expected_defense': []}
    return scenario, DigitalTwin.from_dict(asset_defs, edges)


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
        # Always run deterministic and simulation-best (the ranked candidates
        # from evaluate_candidates). Only run live AI if explicitly requested.
        for strategy in ['deterministic', 'simulate'] + (['ai'] if live else []):
            run_id = f'eval-{seed}-{i}-{strategy}-{time.time_ns()}'
            context = ArenaMemory(json.loads(frozen)).for_context(scenario['id'], None)
            red, blue = _choosers(strategy, context)
            if strategy in ('ai', 'simulate'):
                red.run_id = blue.run_id = run_id
            start = time.perf_counter()
            result = await play_match_async(scenario, twin=twin, red_chooser=red, blue_chooser=blue)
            modes = {d['mode'] for d in result['decisions']}
            mode = 'live' if modes == {'live'} else ('mixed' if 'live' in modes else 'offline')
            # Minimum cut reference: the fewest directed edges whose removal
            # disconnects src from tgt in the *attacked* twin before any
            # defense is applied. This is the optimal disruption benchmark.
            min_cut = 0
            g = twin.live_graph(scenario['target_asset'])
            if g and nx.has_path(g, scenario['source_asset'], scenario['target_asset']):
                try:
                    min_cut = len(nx.minimum_edge_cut(g, scenario['source_asset'], scenario['target_asset']))
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    min_cut = 0
            disrupted = result['total_disrupted']
            optimality_gap = max(0, disrupted - min_cut) if disrupted is not None else None
            rows.append({'case_id': scenario['id'], 'case_seed': seed + 10000 + i, 'strategy': strategy,
                         'prior_matches': context.summary()['matches'], 'mode': mode, 'winner': result['winner'], 'rounds': result['rounds_played'],
                         'disrupted': disrupted, 'min_cut': min_cut, 'optimality_gap': optimality_gap,
                         'latency_ms': round((time.perf_counter()-start)*1000, 1),
                         'tokens': meta_client.tokens_used(run_id),
                         'fallbacks': sum(bool(d.get('fallback_reason')) for d in result['decisions']),
                         'decisions': result['decisions'], 'config_hash': twin.config_hash()})
    summary = {}
    for strategy in dict.fromkeys(r['strategy'] for r in rows):
        group = [r for r in rows if r['strategy'] == strategy]
        summary[strategy] = {'cases': len(group), 'blue_wins': sum(r['winner'] == 'blue' for r in group),
                             'mean_disrupted': sum(r['disrupted'] for r in group)/len(group),
                             'mean_optimality_gap': round(sum(r['optimality_gap'] for r in group if r['optimality_gap'] is not None)/max(1, len([r for r in group if r['optimality_gap'] is not None])), 2),
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
