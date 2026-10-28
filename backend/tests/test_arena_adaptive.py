import pytest

from app.arena.engine import play_match
from app.simulation.twin import DigitalTwin


def arena_fixture():
    names = ['source', 'left', 'right', 'target']
    twin = DigitalTwin.from_dict(
        [{'id': n, 'name': n, 'asset_type': 'app_server', 'zone': 'test', 'pos': [0, 0, 0],
          'vulnerabilities': ['unpatched_service']} for n in names],
        [{'source': a, 'target': b, 'traversable': True} for a, b in
         [('source', 'left'), ('left', 'target'), ('source', 'right'), ('right', 'target')]])
    scenario = {'id': 'adaptive-test', 'source_asset': 'source', 'target_asset': 'target',
                'verification_kind': 'reachability', 'attack_steps': [], 'expected_defense': []}
    return twin, scenario


def cut_selected(twin, baseline, scenario, history):
    path = scenario['arena_red_path']
    return {'label': 'cut selected', 'disrupted': 999, 'actions': [
        {'action_type': 'block_connection', 'asset_id': path[0],
         'params': {'source': path[0], 'target': path[1], 'direction': 'egress'}}]}


def test_red_reroutes_after_selected_route_blocked():
    twin, scenario = arena_fixture()
    result = play_match(scenario, twin=twin, blue_chooser=cut_selected, max_rounds=5)
    assert result['rounds_played'] == 2
    assert result['rounds'][0]['red_path'] != result['rounds'][1]['red_path']
    assert result['rounds'][0]['selected_path_blocked']
    assert result['rounds'][0]['target_reachable_after']
    assert result['winner'] == 'blue'
    assert result['total_disrupted'] != 1998


def test_residual_exposure_at_round_budget_is_red_win():
    twin, scenario = arena_fixture()
    result = play_match(scenario, twin=twin, blue_chooser=cut_selected, max_rounds=1)
    assert result['winner'] == 'red'
    assert result['target_reachable_final']


def test_invalid_red_route_rejected():
    twin, scenario = arena_fixture()
    with pytest.raises(ValueError, match='validated'):
        play_match(scenario, twin=twin, red_chooser=lambda *args: ['source', 'target'])


@pytest.mark.parametrize('limit', [0, -1, 11, True])
def test_round_limits(limit):
    twin, scenario = arena_fixture()
    with pytest.raises(ValueError):
        play_match(scenario, twin=twin, max_rounds=limit)



def test_rejected_proposal_is_atomic_and_audited():
    twin, scenario = arena_fixture()
    def unsafe(*args):
        return {'label': 'mixed', 'actions': [
            {'action_type': 'block_connection', 'asset_id': 'source', 'params': {'source': 'source', 'target': 'left'}},
            {'action_type': 'arbitrary_shell', 'asset_id': 'source', 'params': {}}]}
    result = play_match(scenario, twin=twin, blue_chooser=unsafe)
    assert result['rounds'][0]['blue_actions'] == []
    assert result['rounds'][0]['policy_rejections']
    assert result['decisions'][0]['evidence_refs'] == ['arena-round-1']
    assert result['rounds'][0]['twin_after']['connections'] == result['initial_twin']['connections']
