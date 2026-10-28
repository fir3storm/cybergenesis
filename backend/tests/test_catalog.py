"""Device catalog contract: size, unique ids, required fields, category counts, BY_ID."""

import os
import sys
from collections import Counter

os.environ["OFFLINE_MODE"] = "true"
os.environ["SIM_STEP_DELAY_MS"] = "0"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.devices.registry import BY_ID, CATALOG, EXPECTED_COUNTS

# Real count verified by loading the catalog (registry raises at import if it
# is not 200, and catalog.csv holds exactly 200 rows): the 200 claim holds.
REAL_CATALOG_SIZE = 200


def test_catalog_total_size():
    assert len(CATALOG) == REAL_CATALOG_SIZE


def test_every_device_has_unique_id():
    ids = [m.id for m in CATALOG]
    assert len(ids) == len(set(ids)) == REAL_CATALOG_SIZE
    assert all(isinstance(i, str) and i for i in ids)


def test_required_fields_present_on_every_device():
    for m in CATALOG:
        assert isinstance(m.id, str) and m.id
        assert isinstance(m.vendor, str) and m.vendor
        assert isinstance(m.model, str) and m.model
        assert isinstance(m.category, str) and m.category
        assert m.category in EXPECTED_COUNTS


def test_category_counts_match_expected_and_sum_to_total():
    counts = Counter(m.category for m in CATALOG)
    assert counts == EXPECTED_COUNTS
    assert sum(counts.values()) == len(CATALOG) == REAL_CATALOG_SIZE
    assert sum(EXPECTED_COUNTS.values()) == REAL_CATALOG_SIZE


def test_by_id_lookup_is_consistent_with_catalog_list():
    assert len(BY_ID) == len(CATALOG)
    assert set(BY_ID) == {m.id for m in CATALOG}
    for m in CATALOG:
        assert BY_ID[m.id] is m
        assert BY_ID[m.id].vendor == m.vendor
        assert BY_ID[m.id].model == m.model
        assert BY_ID[m.id].category == m.category
