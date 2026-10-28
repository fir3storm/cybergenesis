"""Bring-your-own-network importers: running-configs and CSV inventories -> twin definition.

Output is the same {"assets": [...], "connections": [...]} shape the Twin
Designer saves, so imported twins go through the identical validation and
compiler path. Parsing is deterministic and offline; nothing here calls a model.
"""

import csv
import io
import ipaddress
import math
import re

from app.simulation.component_library import ASSET_TYPES

_KNOWN_TYPES = {a["id"] for a in ASSET_TYPES}

# hostname keyword -> asset_type; first match wins
_TYPE_HINTS = [
    (("fw", "firewall", "asa", "palo", "forti"), "firewall"),
    (("rtr", "router", "gw", "gateway", "edge", "core", "sw", "switch"), "gateway"),
    (("db", "sql", "oracle", "mongo"), "database"),
    (("dc", "ad", "idp", "ldap", "radius", "okta"), "identity"),
    (("web", "www", "nginx", "iis"), "web_server"),
    (("app", "api"), "app_server"),
    (("file", "nas", "smb", "share"), "file_server"),
    (("ws", "pc", "laptop", "desk"), "workstation"),
]
_DIALECT_TYPE = {"cisco_ios": "gateway", "junos": "gateway", "routeros": "gateway",
                 "fortios": "firewall", "panos": "firewall", "bash": "app_server", "powershell": "workstation"}
_ZONE = {"firewall": "perimeter", "gateway": "perimeter", "database": "data", "identity": "identity",
         "web_server": "dmz", "app_server": "internal", "file_server": "internal", "workstation": "endpoints",
         "sensor": "internal"}
_SLUG = re.compile(r"[^a-z0-9-]+")


class ImportError_(ValueError):
    """Input could not be turned into a twin; the message is safe to show the user."""


def _slug(name: str) -> str:
    return _SLUG.sub("-", name.strip().lower()).strip("-") or "device"


def _guess_type(hostname: str, dialect: str) -> str:
    tokens = set(re.split(r"[^a-z0-9]+", hostname.lower()))
    for keys, t in _TYPE_HINTS:
        if tokens & set(keys):
            return t
    return _DIALECT_TYPE.get(dialect, "gateway")


def _circle(n: int, i: int, r: float = 6.0) -> list[float]:
    if n == 1:
        return [0.0, 1.0, 0.0]
    a = 2 * math.pi * i / n
    return [round(r * math.cos(a), 2), 1.0, round(r * math.sin(a), 2)]


def _iface_network(line: str) -> ipaddress.IPv4Interface | None:
    """'ip address 10.0.0.1/24' or 'ip address 10.0.0.1 255.255.255.0' (also 'set ip ...')."""
    parts = line.replace("set ip", "ip address").split()
    try:
        i = parts.index("address")
    except ValueError:
        return None
    rest = parts[i + 1:]
    if not rest:
        return None
    try:
        if "/" in rest[0]:
            return ipaddress.IPv4Interface(rest[0])
        if len(rest) > 1:
            return ipaddress.IPv4Interface(f"{rest[0]}/{rest[1]}")
        return ipaddress.IPv4Interface(f"{rest[0]}/24")
    except ValueError:
        return None


def _split_devices(text: str) -> list[list[str]]:
    """Several configs may be pasted together; each 'hostname X' starts a device."""
    blocks: list[list[str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("hostname ") or not blocks:
            blocks.append([])
        blocks[-1].append(line)
    return [b for b in blocks if any(x for x in b)]


def parse_running_configs(text: str, dialect: str = "cisco_ios") -> dict:
    """Running-config text (one or many devices) -> assets + inferred links.

    Links are inferred two ways: interfaces on the same IPv4 subnet, and an
    interface description that names another device's hostname. Weaknesses
    the config itself proves (telnet, default SNMP community, permit-any ACL,
    users without MFA) become the asset's vulnerabilities.
    """
    if not text.strip():
        raise ImportError_("config text is empty")
    devices = []
    for block in _split_devices(text):
        host = next((ln.split(None, 1)[1] for ln in block if ln.startswith("hostname ") and len(ln.split()) > 1), None)
        nets, descs, vulns = [], [], []
        for ln in block:
            low = ln.lower()
            if "address" in low and ("ip address" in low or low.startswith("set ip")):
                n = _iface_network(ln)
                if n:
                    nets.append(n.network)
            elif low.startswith("description"):
                descs.append(low[len("description"):])
            # IOS 'transport input telnet'; JunOS/FortiOS/PAN-OS 'set ... telnet'
            if "transport input telnet" in low or (low.startswith("set ") and "telnet" in low.split()):
                vulns.append("telnet_enabled")
            if low.startswith("snmp-server community") and len(low.split()) > 2 and low.split()[2] in ("public", "private"):
                vulns.append("default_snmp_community")
            if low.startswith("access-list") and "permit" in low and low.rstrip().endswith("any any"):
                vulns.append("permissive_default_rule")
            if low.startswith("username") and "mfa on" not in low:
                vulns.append("no_mfa_admin")
        if host is None and not nets:
            continue
        devices.append({"hostname": host or f"{dialect}-device-{len(devices) + 1}", "nets": nets,
                        "descs": descs, "vulns": sorted(set(vulns))})
    if not devices:
        raise ImportError_("no device found: expected at least a 'hostname' line or an 'ip address' line")

    assets, seen = [], set()
    for i, d in enumerate(devices):
        aid = _slug(d["hostname"])
        while aid in seen:
            aid += "-x"
        seen.add(aid)
        d["id"] = aid
        t = _guess_type(d["hostname"], dialect)
        assets.append({"id": aid, "name": d["hostname"], "asset_type": t, "zone": _ZONE[t],
                       "posture": round(max(0.3, 0.85 - 0.12 * len(d["vulns"])), 2),
                       "pos": _circle(len(devices), i), "vulnerabilities": d["vulns"]})

    pairs: set[tuple[str, str]] = set()
    for a in devices:
        for b in devices:
            if a["id"] >= b["id"]:
                continue
            shared = set(a["nets"]) & set(b["nets"])
            named = any(b["hostname"].lower() in s for s in a["descs"]) or any(a["hostname"].lower() in s for s in b["descs"])
            if shared or named:
                pairs.add((a["id"], b["id"]))
    connections = []
    for s, t in sorted(pairs):
        # Links are bidirectional at L3, so both directions are traversable.
        connections.append({"source": s, "target": t, "trust": "medium", "traversable": True, "types": ["network"]})
        connections.append({"source": t, "target": s, "trust": "medium", "traversable": True, "types": ["network"]})
    return {"assets": assets, "connections": connections}


def parse_csv_inventory(csv_text: str) -> dict:
    """CSV inventory -> twin. Columns: id,name,asset_type,zone,posture,vulnerabilities,connects_to
    (only id is required; vulnerabilities and connects_to are ';'-separated;
    connects_to lists asset ids this row can reach, i.e. directed edges)."""
    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    if not reader.fieldnames or "id" not in [f.strip() for f in reader.fieldnames]:
        raise ImportError_("CSV must have a header row with at least an 'id' column")
    rows = [{(k or "").strip(): (v or "").strip() for k, v in r.items()} for r in reader]
    rows = [r for r in rows if r.get("id")]
    if not rows:
        raise ImportError_("CSV has no asset rows")
    assets, connections = [], []
    for i, r in enumerate(rows):
        t = r.get("asset_type") or _guess_type(r["id"], "")
        if t not in _KNOWN_TYPES:
            raise ImportError_(f"row {i + 2}: unknown asset_type '{t}' (one of: {', '.join(sorted(_KNOWN_TYPES))})")
        try:
            posture = float(r.get("posture") or 0.7)
        except ValueError:
            raise ImportError_(f"row {i + 2}: posture must be a number between 0 and 1") from None
        if not 0 <= posture <= 1:
            raise ImportError_(f"row {i + 2}: posture must be between 0 and 1")
        assets.append({"id": r["id"], "name": r.get("name") or r["id"], "asset_type": t,
                       "zone": r.get("zone") or _ZONE[t], "posture": posture, "pos": _circle(len(rows), i),
                       "vulnerabilities": [v.strip() for v in (r.get("vulnerabilities") or "").split(";") if v.strip()]})
        for target in (r.get("connects_to") or "").split(";"):
            if target.strip():
                connections.append({"source": r["id"], "target": target.strip(), "trust": "medium",
                                    "traversable": True, "types": ["network"]})
    ids = {a["id"] for a in assets}
    for c in connections:
        if c["target"] not in ids:
            raise ImportError_(f"connects_to references unknown asset id '{c['target']}' (from '{c['source']}')")
    return {"assets": assets, "connections": connections}
