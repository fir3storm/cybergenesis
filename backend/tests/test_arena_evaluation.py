import copy

import pytest

from app.arena.evaluation import evaluate_strategies


@pytest.mark.asyncio
async def test_evaluation_has_paired_cases_and_frozen_memory():
    result = await evaluate_strategies(cases=2, training_matches=2, seed=17)
    assert result['live_requested'] is False
    assert set(result['summary']) == {'min_cut', 'simulate', 'learned'}
    assert result['evaluation_memory_unchanged'] is True
    assert len(result['cases']) == 6
    assert {r['case_id'] for r in result['cases']} == {'heldout-0', 'heldout-1'}
    assert all(r['mode'] == 'offline' for r in result['cases'])
    assert result['training_cases'] != result['heldout_cases']
    assert copy.deepcopy(result)['seed'] == 17


def test_generated_case_measures_business_disruption():
    from app.arena.evaluation import make_case
    scenario, twin = make_case(17, 'case')
    baseline = twin.clone()
    twin.apply_action('isolate_asset', scenario['source_asset'], {})
    assert twin.legitimate_disrupted(baseline) > 0


@pytest.mark.asyncio
async def test_evaluation_does_not_transfer_memory_to_unseen_scenarios():
    report = await evaluate_strategies(cases=1, training_matches=1)
    assert all(r['prior_matches'] == 0 for r in report['cases'])

def test_committed_evaluation_report_matches_current_schema():
    import json
    from pathlib import Path

    report = json.loads((Path(__file__).resolve().parents[2] / "docs" / "arena-evaluation.json").read_text(encoding="utf-8"))
    assert report["version"] == 1 and report["evaluation_memory_unchanged"] is True
    assert set(report["summary"]) == {"min_cut", "simulate", "learned"}
    assert all("mean_optimality_gap" in row for row in report["summary"].values())


def test_edge_gap_counts_removed_edges_not_business_disruption():
    import networkx as nx

    from app.arena.evaluation import edge_cut_metrics

    before = nx.DiGraph([('s', 'a'), ('a', 't'), ('s', 'b'), ('b', 'a')])
    after = before.copy()
    after.remove_edges_from([('s', 'a'), ('s', 'b'), ('b', 'a')])
    result = edge_cut_metrics(before, after, 's', 't')
    assert result['min_cut'] == 1
    assert result['edges_removed'] == 3
    assert result['optimality_gap'] == 2


def test_surviving_path_has_no_optimality_gap():
    import networkx as nx

    from app.arena.evaluation import edge_cut_metrics

    graph = nx.DiGraph([('s', 'a'), ('a', 't')])
    result = edge_cut_metrics(graph, graph.copy(), 's', 't')
    assert result['cut_valid'] is False
    assert result['optimality_gap'] is None


@pytest.mark.asyncio
async def test_context_training_is_reported_separately_from_unseen_cases():
    report = await evaluate_strategies(cases=1, training_matches=1)
    assert all(row['prior_matches'] == 0 for row in report['cases'])
    assert report['within_context'][0]['cold_prior_matches'] == 0
    assert report['within_context'][0]['warm_prior_matches'] == 1


@pytest.mark.asyncio
async def test_requested_ai_failure_is_not_counted_as_live_success():
    report = await evaluate_strategies(cases=1, training_matches=0, live=True)
    ai = next(row for row in report['cases'] if row['strategy'] == 'ai')
    assert ai['mode'] == 'offline'
    assert ai['provider_failed'] is True
    assert report['summary']['ai']['live_cases'] == 0
    assert report['summary']['ai']['provider_failures'] == 1


@pytest.mark.asyncio
async def test_minimum_cut_and_candidate_search_are_distinct_baselines():
    report = await evaluate_strategies(cases=1, training_matches=0, seed=42)
    cut = next(row for row in report['cases'] if row['strategy'] == 'min_cut')
    simulated = next(row for row in report['cases'] if row['strategy'] == 'simulate')
    assert cut['winner'] == simulated['winner'] == 'blue'
    assert cut['edges_removed'] == 4
    assert cut['optimality_gap'] == 0
    assert simulated['edges_removed'] == 8
    assert simulated['optimality_gap'] == 4
