import copy

import pytest

from app.arena.evaluation import evaluate_strategies


@pytest.mark.asyncio
async def test_evaluation_has_paired_cases_and_frozen_memory():
    result = await evaluate_strategies(cases=2, training_matches=2, seed=17)
    assert result['live_requested'] is False
    assert set(result['summary']) == {'deterministic', 'simulate'}
    assert result['evaluation_memory_unchanged'] is True
    assert len(result['cases']) == 4
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
