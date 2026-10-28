from app.arena.learning import ArenaMemory


def test_context_learning_is_isolated_and_persistent(tmp_path):
    memory = ArenaMemory()
    first = memory.for_context('scenario-a', None)
    first.record_match({'rounds': [{'blue_candidate': 'block', 'target_reachable_after': False}]})
    assert first.blue_rate('block') > 0.5
    assert memory.for_context('scenario-b', None).blue_rate('block') == 0.5
    assert memory.for_context('scenario-a', 'custom').blue_rate('block') == 0.5
    path = tmp_path / 'memory.json'
    memory.save(path)
    assert ArenaMemory.load(path).for_context('scenario-a', None).blue_rate('block') == first.blue_rate('block')


def test_legacy_global_scores_do_not_leak_into_context():
    memory = ArenaMemory({'matches': 20, 'blue': {'block': {'plays': 20, 'blocks': 20}}, 'red': {}})
    assert memory.for_context('new-scenario', None).blue_rate('block') == 0.5
    assert memory.summary()['matches'] == 20
