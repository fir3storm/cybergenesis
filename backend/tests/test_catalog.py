"""Catalog contract tests: the 200-device catalogue must stay in balance.

These are the assertions that load_catalog() already enforces at import time,
but they deserve their own module so a future refactor that relaxes them is
caught immediately rather than only at first import.
"""

import os
import sys

os.environ["OFFLINE_MODE"] = "true"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.devices.registry import (
    BUILTIN_DEVICE_MAP,
    BY_ID,
    CATALOG,
    EXPECTED_COUNTS,
    query_catalog,
)


def test_catalog_total_is_200():
    assert len(CATALOG) == 200


def test_catalog_category_counts_match_contract():
    counts = {}
    for m in CATALOG:
        counts[m.category] = counts.get(m.category, 0) + 1
    assert counts == EXPECTED_COUNTS


def test_catalog_has_exactly_20_flagships():
    flagships = [m for m in CATALOG if m.tier == "flagship"]
    assert len(flagships) == 20


def test_catalog_ids_are_unique():
    ids = [m.id for m in CATALOG]
    assert len(ids) == len(set(ids))


def test_catalog_lookup_by_id_is_complete():
    for m in CATALOG:
        assert BY_ID[m.id] is m


def test_builtin_device_map_resolves_to_catalog():
    for asset_id, device_id in BUILTIN_DEVICE_MAP.items():
        assert device_id in BY_ID, f"builtin asset {asset_id} -> {device_id} not in catalog"


def test_query_catalog_filters_by_category():
    firewalls = query_catalog(category="firewall", limit=50)
    assert all(m["category"] == "firewall" for m in firewalls["items"])
    assert len(firewalls["items"]) == EXPECTED_COUNTS["firewall"]


def test_query_catalog_filters_by_vendor():
    r = query_catalog(vendor="fortinet", limit=50)
    assert r["items"]
    assert all(m["vendor"].lower() == "fortinet" for m in r["items"])


def test_query_catalog_paging():
    page1 = query_catalog(limit=5, offset=0)
    page2 = query_catalog(limit=5, offset=5)
    assert page1["total"] == 200
    assert len(page1["items"]) == 5
    assert len(page2["items"]) == 5
    assert page1["items"][0]["id"] != page2["items"][0]["id"]


def test_query_catalog_unknown_category_is_empty():
    r = query_catalog(category="does-not-exist", limit=50)
    assert r["items"] == []
    assert r["total"] == 0