"""Device catalog registry: loads catalog.csv, expands family templates, validates at startup."""

import csv
from pathlib import Path

from app.devices.schema import DeviceManifest, Hardware, OSPersonality, Personality, PortSpec
from app.devices.templates import CATEGORY_BY_FAMILY, FAMILY_TEMPLATES

_CSV = Path(__file__).with_name("catalog.csv")

EXPECTED_COUNTS = {"router": 24, "switch": 30, "firewall": 24, "wireless": 12, "security": 16,
                   "server": 28, "endpoint": 30, "virtual": 16, "ot": 14, "identity": 6}

# built-in twin asset -> catalog device id
BUILTIN_DEVICE_MAP = {
    "internet": "synthetic-internet-cloud",
    "firewall": "fortinet-fortigate-200f",
    "web-server": "hpe-proliant-dl380-gen11-ubuntu-server-24-04-web",
    "app-server": "canonical-ubuntu-server-22-04",
    "database": "lenovo-sr650-rhel-9-postgresql",
    "identity-provider": "dell-poweredge-r760-windows-server-2022-ad-dc",
    "admin-workstation": "dell-latitude-7440-windows-11-enterprise",
    "employee-workstation": "dell-latitude-7440-windows-11-enterprise",
    "file-server": "microsoft-windows-server-2022-file-server",
    "security-sensor": "synthetic-ids-sensor-snort",
}


def _split(v: str) -> list[str]:
    return [x for x in (v or "").split(";") if x]


def load_catalog() -> list[DeviceManifest]:
    manifests: list[DeviceManifest] = []
    with _CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            fam = row["family"]
            tpl = FAMILY_TEMPLATES[fam]
            cli = row["cli"] or tpl["cli"]
            gui = row["gui"] or tpl["gui"]
            manifests.append(DeviceManifest(
                id=row["id"], vendor=row["vendor"], family=fam, model=row["model"],
                category=CATEGORY_BY_FAMILY[fam], tier=row["tier"] or "catalog",
                os=OSPersonality(name=row["os_name"], version=row["os_version"]),
                personality=Personality(cli=cli, gui=gui, skin=tpl["skin"]),
                hardware=Hardware(form=tpl["form"], ports=[PortSpec(**p) for p in tpl["ports"]],
                                  mgmt_port=tpl["ports"][0]["prefix"] + str(tpl["ports"][0]["start"])),
                capabilities=list(tpl["capabilities"]),
                default_config={"hostname": row["id"].split("-")[0].upper() + "-01", "device_id": row["id"]},
                weaknesses=_split(row["weaknesses"]), services=_split(row["services"]) or list(tpl["services"]),
                model3d=tpl["model3d"], icon=tpl["icon"],
                mitre_defends=["T1562", "T1078"] if fam in ("firewall", "identity") else ["T1059"],
            ))
    ids = [m.id for m in manifests]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate device ids in catalog")
    if len(manifests) != 200:
        raise ValueError(f"catalog must contain 200 devices, got {len(manifests)}")
    counts: dict[str, int] = {}
    for m in manifests:
        counts[m.category] = counts.get(m.category, 0) + 1
    if counts != EXPECTED_COUNTS:
        raise ValueError(f"category counts wrong: {counts}")
    if sum(1 for m in manifests if m.tier == "flagship") != 20:
        raise ValueError("catalog must contain exactly 20 flagship devices")
    return manifests


CATALOG: list[DeviceManifest] = load_catalog()
BY_ID: dict[str, DeviceManifest] = {m.id: m for m in CATALOG}


def query_catalog(category: str | None = None, vendor: str | None = None, q: str | None = None,
                  tier: str | None = None, limit: int = 50, offset: int = 0) -> dict:
    items = CATALOG
    if category:
        items = [m for m in items if m.category == category]
    if vendor:
        items = [m for m in items if m.vendor.lower() == vendor.lower()]
    if tier:
        items = [m for m in items if m.tier == tier]
    if q:
        needle = q.lower()
        items = [m for m in items if needle in f"{m.vendor} {m.model} {m.id}".lower()]
    return {"total": len(items), "items": [m.model_dump() for m in items[offset:offset + limit]],
            "limit": limit, "offset": offset}
