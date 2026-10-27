"""Deterministic config compiler: (devices, configs, cables) -> reachability with hop evidence.

Pure and content-hash cached. Attack traversal A->B requires: cable UP (both ends
enabled, VLAN compatible, neither isolated/quarantined), filtering allows it
(ACLs, firewall policies for transit, host firewall), B exposes an enabled
service, and B is weak (weakness/missing patch) or the attacker holds a session.
"""

import hashlib
import json
from collections import deque

from app.netmodel.config import DeviceConfig

_cache: dict[str, "CompiledTwin"] = {}


def content_hash(configs: dict[str, DeviceConfig], cables: list[dict]) -> str:
    blob = json.dumps({"configs": {k: v.model_dump() for k, v in sorted(configs.items())},
                       "cables": cables}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _iface_for(cfg: DeviceConfig, peer: str) -> dict | None:
    for i in cfg.interfaces:
        if i.peer == peer:
            return i.model_dump()
    return cfg.interfaces[0].model_dump() if cfg.interfaces else None


def _vlan_ok(ia: dict | None, ib: dict | None) -> bool:
    if not ia or not ib:
        return True
    if ia["mode"] == "access" and ib["mode"] == "access":
        return ia["vlan"] == ib["vlan"]
    if ia["mode"] == "trunk" and ib["mode"] == "access":
        return ib["vlan"] in (ia["allowed_vlans"] or [ib["vlan"]])
    if ib["mode"] == "trunk" and ia["mode"] == "access":
        return ia["vlan"] in (ib["allowed_vlans"] or [ia["vlan"]])
    return True  # routed/host


def _acl_denies(cfg: DeviceConfig, acl_name: str | None, dst_ip: str, port: int | None) -> str | None:
    if not acl_name:
        return None
    for acl in cfg.acls:
        if acl.name != acl_name:
            continue
        for e in acl.entries:
            if e.action == "deny" and (e.dst in ("any", dst_ip) or dst_ip == "any"):
                if e.dst_port is None or e.dst_port == port:
                    return f"ACL {acl_name} seq {e.seq} deny"
    return None


class CompiledTwin:
    def __init__(self, configs: dict[str, DeviceConfig], cables: list[dict], categories: dict[str, str]):
        self.configs = configs
        self.cables = cables
        self.categories = categories
        self.hash = content_hash(configs, cables)
        self.adj: dict[str, list[str]] = {k: [] for k in configs}
        for c in cables:
            pairs = c["pairs"] if c.get("pairs") is not None else [(c["a"]["device"], c["b"]["device"]), (c["b"]["device"], c["a"]["device"])]
            for a, b in pairs:
                if b not in self.adj[a]:
                    self.adj[a].append(b)

    def link_up(self, a: str, b: str) -> tuple[bool, str]:
        ca, cb = self.configs.get(a), self.configs.get(b)
        if not ca or not cb:
            return False, "device missing"
        if ca.isolated or cb.isolated or ca.quarantine_vlan or cb.quarantine_vlan:
            return False, "device isolated/quarantined"
        ia, ib = _iface_for(ca, b), _iface_for(cb, a)
        if ia and not ia["enabled"]:
            return False, f"interface {ia['name']} on {a} is shutdown"
        if ib and not ib["enabled"]:
            return False, f"interface {ib['name']} on {b} is shutdown"
        if not _vlan_ok(ia, ib):
            return False, f"VLAN mismatch ({a}:{ia['vlan'] if ia else '?'} vs {b}:{ib['vlan'] if ib else '?'})"
        return True, "link up (cable present, interfaces enabled, VLAN compatible)"

    def _filter_block(self, a: str, b: str, service: dict | None) -> str | None:
        ca, cb = self.configs[a], self.configs[b]
        ia, ib = _iface_for(ca, b), _iface_for(cb, a)
        port = service["port"] if service else None
        deny = _acl_denies(ca, ia["acl_out"] if ia else None, ib["ip"] if ib else "any", port)
        if deny:
            return f"{a} outbound {deny}"
        deny = _acl_denies(cb, ib["acl_in"] if ib else None, ia["ip"] if ia else "any", port)
        if deny:
            return f"{b} inbound {deny}"
        # firewall transit: if the intermediate/source device is a firewall, an allow policy must match
        for dev, nxt in ((a, b),):
            if self.categories.get(dev) == "firewall":
                pols = [p for p in ca.fw_policies if p.enabled]
                svc_name = service["name"] if service else "any"
                allowed = any(p.action == "allow" and p.service in ("any", svc_name) for p in pols)
                denied = any(p.action == "deny" and p.service in ("any", svc_name) for p in pols)
                first = pols[0] if pols else None
                if first and first.action == "deny" and first.service in ("any", svc_name):
                    return f"firewall policy '{first.name}' denies {svc_name}"
                if pols and not allowed:
                    return f"firewall implicit deny (no allow policy for {svc_name})"
                if denied and not allowed:
                    return f"firewall policy denies {svc_name}"
        if service and cb.host_firewall.enabled:
            for r in cb.host_firewall.rules:
                if r.get("action") == "deny" and r.get("port") in (port, "any"):
                    return f"host firewall on {b} denies port {port}"
        return None

    def explain(self, src: str, dst: str) -> dict:
        if src not in self.configs or dst not in self.configs:
            return {"reachable": False, "path": [], "hops": [], "reason": "device missing"}
        cb = self.configs[dst]
        services = [s for s in cb.services if s.enabled]
        weak = bool(cb.weaknesses or cb.patches.missing)
        has_session = any(sess.active for u in cb.users for sess in u.sessions)
        q: deque = deque([[src]])
        seen = {src}
        parent: dict[str, tuple[str, str]] = {}
        found = None
        while q:
            path = q.popleft()
            node = path[-1]
            if node == dst:
                found = path
                break
            for nxt in self.adj.get(node, []):
                if nxt in seen:
                    continue
                up, why = self.link_up(node, nxt)
                if not up:
                    continue
                svc = services[0].model_dump() if (nxt == dst and services) else None
                if nxt == dst and not services:
                    continue
                if nxt == dst and not (weak or has_session):
                    continue  # target not weak and attacker holds no session: traversal refused
                block = self._filter_block(node, nxt, svc)
                if block:
                    continue
                seen.add(nxt)
                parent[nxt] = (node, f"{why}; service {svc['name'] if svc else 'transit'} reachable; "
                                      + ("weakness present" if weak else "valid session held" if has_session else "target"))
                q.append(path + [nxt])
        if not found:
            return {"reachable": False, "path": [], "hops": [],
                    "reason": "no forwarding path with an allowed, reachable service (or target not weak and no session)"}
        hops = []
        for i in range(len(found) - 1):
            hops.append({"from": found[i], "to": found[i + 1], "rule": parent[found[i + 1]][1]})
        return {"reachable": True, "path": found, "hops": hops,
                "reason": "path exists; target exposes a service and " + ("has a weakness/missing patch" if weak else "attacker holds a session")}


def compile_twin(configs: dict[str, DeviceConfig], cables: list[dict], categories: dict[str, str]) -> CompiledTwin:
    h = content_hash(configs, cables)
    if h not in _cache:
        _cache[h] = CompiledTwin(configs, cables, categories)
    return _cache[h]
