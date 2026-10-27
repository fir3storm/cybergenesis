import os
import sys
from collections import Counter

os.environ["OFFLINE_MODE"] = "true"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient  # noqa: E402

from app.devices.registry import BUILTIN_DEVICE_MAP, BY_ID, CATALOG, EXPECTED_COUNTS  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


def test_catalog_exactly_200_and_counts():
    assert len(CATALOG) == 200
    assert Counter(m.category for m in CATALOG) == EXPECTED_COUNTS
    assert len({m.id for m in CATALOG}) == 200
    assert sum(1 for m in CATALOG if m.tier == "flagship") == 20
    for m in CATALOG:
        assert m.vendor and m.model and m.os.name


def test_builtin_map_resolves():
    assert set(BUILTIN_DEVICE_MAP) == {"internet", "firewall", "web-server", "app-server", "database",
                                       "identity-provider", "admin-workstation", "employee-workstation",
                                       "file-server", "security-sensor"}
    for dev_id in BUILTIN_DEVICE_MAP.values():
        assert dev_id in BY_ID


def test_catalog_api_pagination_and_filter():
    r = client.get("/api/devices/catalog", params={"category": "firewall", "limit": 5})
    assert r.status_code == 200 and r.json()["total"] == 24 and len(r.json()["items"]) == 5
    f = client.get("/api/devices/catalog", params={"tier": "flagship"})
    assert f.json()["total"] == 20
    one = client.get("/api/devices/catalog/cisco-catalyst-9300-48p")
    assert one.status_code == 200 and "telnet_enabled" in one.json()["weaknesses"]
    assert client.get("/api/devices/catalog/nope").status_code == 404
