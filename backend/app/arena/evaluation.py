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

from app.arena.engine import deterministic_red, play_match_async
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


def edge_cut_metrics(before: nx.DiGraph, after: nx.DiGraph, source: str, target: str) -> dict:
    """Count directed attack arcs, never business-flow pairs. A surviving path has no gap."""
    baseline_reachable = source in before and target in before and nx.has_path(before, source, target)
    removed = sorted(set(before.edges()) - set(after.edges()))
    reachable_after = source in after and target in after and nx.has_path(after, source, target)
    # Check that the removed baseline edges themselves form a cut, including
    # defenses that also add edges (for example decoys).
    cut_graph = before.copy()
    cut_graph.remove_edges_from(removed)
    cut_valid = bool(baseline_reachable and not reachable_after and not nx.has_path(cut_graph, source, target))
    minimum = len(nx.minimum_edge_cut(before, source, target)) if baseline_reachable else 0
    return {'min_cut': minimum, 'edges_removed': len(removed), 'removed_edges': removed,
            'cut_valid': cut_valid, 'optimality_gap': len(removed) - minimum if cut_valid else None}


def minimum_cut_blue(twin: DigitalTwin, baseline: DigitalTwin, scenario: dict, history: list[dict]) -> dict:
    """Pure directed minimum-edge cut. It does not rank by business impact or use learned scores.

    The match engine still policy-checks all actions atomically. A rejected
    graph-theoretic cut is reported as a failed defense, never silently replaced.
    """
    graph = twin.live_graph(scenario['target_asset'])
    source, target = scenario['source_asset'], scenario['target_asset']
    cut = sorted(nx.minimum_edge_cut(graph, source, target)) if nx.has_path(graph, source, target) else []
    return {'label': 'Minimum directed edge cut', 'actions': [
        {'action_type': 'block_connection', 'asset_id': a, 'params': {'source': a, 'target': b, 'direction': 'egress'}}
        for a, b in cut]}


async def evaluate_strategies(cases: int = 5, training_matches: int = 5, seed: int = 42, live: bool = False) -> dict:
    if not 1 <= cases <= 30 or not 0 <= training_matches <= 30:
        raise ValueError('cases must be 1..30 and training_matches 0..30')
    memory = ArenaMemory()
    training_ids, within_context = [], []
    for i in range(training_matches):
        scenario, twin = make_case(seed + i, f'train-{i}')
        training_ids.append(scenario['id'])
        context = memory.for_context(scenario['id'], None)
        red, blue = _choosers('learned', context)
        cold = await play_match_async(scenario, twin=twin, seed=seed + i, red_chooser=red, blue_chooser=blue)
        context.record_match(cold)
        # Same topology and seed, separate repeated-context diagnostic. This
        # is deliberately not pooled into the unseen-topology benchmark.
        warm = await play_match_async(scenario, twin=twin, seed=seed + i, red_chooser=red, blue_chooser=blue)
        within_context.append({'case_id': scenario['id'], 'cold_prior_matches': 0, 'warm_prior_matches': 1,
                               'cold_winner': cold['winner'], 'warm_winner': warm['winner'],
                               'cold_disrupted': cold['total_disrupted'], 'warm_disrupted': warm['total_disrupted']})
    frozen = json.dumps(memory.data, sort_keys=True)
    rows = []
    for i in range(cases):
        case_seed = seed + 10000 + i
        scenario, twin = make_case(case_seed, f'heldout-{i}')
        for strategy in ['min_cut', 'simulate', 'learned'] + (['ai'] if live else []):
            run_id = f'eval-{seed}-{i}-{strategy}-{time.time_ns()}'
            context = ArenaMemory(json.loads(frozen)).for_context(scenario['id'], None)
            red, blue = (deterministic_red, minimum_cut_blue) if strategy == 'min_cut' else _choosers(strategy, context)
            if strategy == 'ai':
                red.run_id = blue.run_id = run_id
            start = time.perf_counter()
            result = await play_match_async(scenario, twin=twin, seed=case_seed, red_chooser=red, blue_chooser=blue)
            latency_ms = round((time.perf_counter()-start)*1000, 1)
            modes = {d['mode'] for d in result['decisions']}
            mode = 'live' if modes == {'live'} else ('mixed' if 'live' in modes else 'offline')
            # Rebuild the attacked baseline, then replay only actions the
            # engine actually applied. Proposed/rejected actions do not count.
            replay = twin.clone()
            replay.apply_attack(scenario, seed=case_seed)
            before = replay.live_graph(scenario['target_asset']).copy()
            for round_result in result['rounds']:
                for action in round_result['blue_actions']:
                    replay.apply_action(action['action_type'], action['asset_id'], action.get('params', {}))
            edge_metrics = edge_cut_metrics(before, replay.live_graph(scenario['target_asset']),
                                            scenario['source_asset'], scenario['target_asset'])
            rows.append({'case_id': scenario['id'], 'case_seed': case_seed, 'strategy': strategy,
                         'prior_matches': context.summary()['matches'], 'mode': mode,
                         'provider': meta_client.provider_id if strategy == 'ai' else None,
                         'model': meta_client.model if strategy == 'ai' else None,
                         'provider_failed': strategy == 'ai' and mode != 'live',
                         'winner': result['winner'], 'rounds': result['rounds_played'],
                         'disrupted': result['total_disrupted'], **edge_metrics,
                         'latency_ms': latency_ms, 'tokens': meta_client.tokens_used(run_id),
                         'fallbacks': sum(bool(d.get('fallback_reason')) for d in result['decisions']),
                         'decisions': result['decisions'], 'config_hash': twin.config_hash()})
    summary = {}
    for strategy in dict.fromkeys(r['strategy'] for r in rows):
        group = [r for r in rows if r['strategy'] == strategy]
        gaps = [r['optimality_gap'] for r in group if r['optimality_gap'] is not None]
        summary[strategy] = {'cases': len(group), 'blue_wins': sum(r['winner'] == 'blue' for r in group),
                             'mean_disrupted': sum(r['disrupted'] for r in group)/len(group),
                             'mean_edges_removed': sum(r['edges_removed'] for r in group)/len(group),
                             'valid_cuts': len(gaps), 'mean_optimality_gap': round(sum(gaps)/len(gaps), 2) if gaps else None,
                             'mean_latency_ms': round(sum(r['latency_ms'] for r in group)/len(group), 1),
                             'tokens': sum(r['tokens'] for r in group),
                             'live_cases': sum(r['mode'] == 'live' for r in group),
                             'provider_failures': sum(r['provider_failed'] for r in group),
                             'fallbacks': sum(r['fallbacks'] for r in group)}
    return {'version': 1, 'created_at': datetime.now(UTC).isoformat(), 'seed': seed,
            'live_requested': live, 'training_cases': training_ids, 'within_context': within_context,
            'heldout_cases': [f'heldout-{i}' for i in range(cases)],
            'evaluation_memory_unchanged': frozen == json.dumps(memory.data, sort_keys=True),
            'memory_sha256': hashlib.sha256(frozen.encode()).hexdigest(), 'summary': summary, 'cases': rows,
            'limitations': 'Small generated synthetic topologies; different seeds can share topology structure. '
                            'Minimum-cut minimizes removed directed attack edges; simulation ranks business disruption, and learned uses outcome scores. '
                            'Edge gap is removed attack edges minus minimum edge cut, defined only for valid cuts; business disruption is a separate unit. '
                            'Paired full-team comparison, not an isolated model ablation. '
                            'Unseen scenarios start with zero prior matches. Repeated-context cold/warm outcomes are separate diagnostics, not evidence of generalization. '
                            'AI fallback outcomes remain in the report but are provider failures, not successful live cases. '
                            'No claim of production resilience or improvement; ties are reported as ties.'}
