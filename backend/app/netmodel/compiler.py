"""Deterministic config compiler: (devices, configs, cables) -> reachability with hop evidence.

Pure, LRU-cached (maxsize 256) by content hash. BFS runs over (device,
ingress_interface) states so interface/VLAN/ACL behaviour is honoured exactly.
ACLs are first-match by seq (permit stops evaluation; implicit deny only when a
bound ACL matches nothing). Firewall transit is evaluated per target service,
first matching policy wins.
"""

import hashlib
import json
from collections import OrderedDict, deque

from app.netmodel.config import DeviceConfig

_cache: "OrderedDict[str, CompiledTwin]" = OrderedDict()
CACHE_MAXSIZE = 256


def content_hash(configs: dict[str, DeviceConfig], cables: list[dict]) -> str:
    blob = json.dumps({"configs": {k: v.model_dump() for k, v in sorted(configs.items())},
                       "cables": cables}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def cache_size() -> int:
    return len(_cache)


def _matches(entry, src_id: str, src_ip: str, dst_id: str, dst_ip: str, proto: str, port: int | None) -> bool:
    if entry.get("src") not in ("any", src_id, src_ip):
        return False
    if entry.get("dst") not in ("any", dst_id, dst_ip):
        return False
    if entry.get("proto") not in ("ip", "any", proto):
        return False
    return entry.get("dst_port") is None or entry.get("dst_port") == port


def _acl_verdict(cfg: DeviceConfig, acl_name: str | None, src_id: str, src_ip: str,
                 dst_id: str, dst_ip: str, proto: str, port: int | None) -> tuple[bool, str]:
    """First-match by seq. Permit stops; implicit deny only if bound and nothing matches."""
    if not acl_name:
        return True, "no ACL bound"
    acl = next((a for a in cfg.acls if a.name == acl_name), None)
    if acl is None:
        return False, f"ACL {acl_name} bound but not defined"
    for e in sorted(acl.entries, key=lambda x: x.seq):
        d = e.model_dump() if hasattr(e, "model_dump") else e
        if _matches(d, src_id, src_ip, dst_id, dst_ip, proto, port):
            if d["action"] == "permit":
                return True, f"ACL {acl_name} seq {d['seq']} permit (first match)"
            return False, f"ACL {acl_name} seq {d['seq']} deny (first match)"
    return False, f"ACL {acl_name} implicit deny (no entry matched)"


class CompiledTwin:
    def __init__(self, configs: dict[str, DeviceConfig], cables: list[dict], categories: dict[str, str]):
        self.configs = configs
        self.cables = cables
        self.categories = categories
        self.hash = content_hash(configs, cables)
        self.refusals: list[str] = []
        self.adj: dict[str, list[str]] = {k: [] for k in configs}
        self._hop_cables: dict[tuple[str, str], dict] = {}
        for c in cables:
            pairs = c["pairs"] if c.get("pairs") is not None else [(c["a"]["device"], c["b"]["device"]), (c["b"]["device"], c["a"]["device"])]
            for a, b in pairs:
                if b not in self.adj[a]:
                    self.adj[a].append(b)
                self._hop_cables[(a, b)] = c

    # -- interface selection by actual cable port -------------------------
    def _iface(self, device: str, port: str) -> dict | None:
        cfg = self.configs.get(device)
        if cfg is None:
            return None
        for i in cfg.interfaces:
            if i.name == port:
                return i.model_dump()
        return None

    def _cable_for(self, a: str, b: str) -> tuple[dict, str, str] | None:
        """Returns (cable, port_on_a, port_on_b) for directed hop a->b."""
        c = self._hop_cables.get((a, b))
        if c is None:
            return None
        if c["a"]["device"] == a:
            return c, c["a"]["port"], c["b"]["port"]
        return c, c["b"]["port"], c["a"]["port"]

    def link_up(self, a: str, b: str) -> tuple[bool, str]:
        found = self._cable_for(a, b)
        if found is None:
            return False, f"no cable {a}->{b}"
        _c, pa, pb = found
        ca, cb = self.configs.get(a), self.configs.get(b)
        if not ca or not cb:
            return False, "device missing"
        if ca.isolated or cb.isolated or ca.quarantine_vlan or cb.quarantine_vlan:
            return False, "device isolated/quarantined"
        ia, ib = self._iface(a, pa), self._iface(b, pb)
        if ia is None:
            return False, f"missing port {pa} on {a}"
        if ib is None:
            return False, f"missing port {pb} on {b}"
        if not ia["enabled"]:
            return False, f"interface {pa} on {a} is shutdown"
        if not ib["enabled"]:
            return False, f"interface {pb} on {b} is shutdown"
        if ia["mode"] == "access" and ib["mode"] == "access" and ia["vlan"] != ib["vlan"]:
            return False, f"VLAN mismatch ({a}:{ia['vlan']} vs {b}:{ib['vlan']})"
        if ia["mode"] == "trunk" and ib["mode"] == "access" and ib["vlan"] not in (ia["allowed_vlans"] or [ib["vlan"]]):
            return False, "VLAN not allowed on trunk"
        if ib["mode"] == "trunk" and ia["mode"] == "access" and ia["vlan"] not in (ib["allowed_vlans"] or [ia["vlan"]]):
            return False, "VLAN not allowed on trunk"
        return True, f"link up via {a}:{pa} -> {b}:{pb}"

    # -- filtering ---------------------------------------------------------
    def _filter_block(self, a: str, b: str, ingress_iface: str | None, service: dict, dst: str) -> str | None:
        """ACL in/out + host firewall for a hop a->b seeking `service` on dst.
        Firewall *transit* policy is evaluated when leaving a firewall device."""
        found = self._cable_for(a, b)
        if found is None:
            return "no cable"
        _c, pa, pb = found
        ca, cb = self.configs[a], self.configs[b]
        ia, ib = self._iface(a, pa), self._iface(b, pb)
        proto = service.get("proto", "tcp") if service else "tcp"
        port = service.get("port") if service else None
        dst_cfg = self.configs[dst]
        dst_ip = dst_cfg.interfaces[0].ip if dst_cfg.interfaces else ""
        ok, why = _acl_verdict(ca, ia["acl_out"] if ia else None, a, ia["ip"] if ia else "", dst, dst_ip, proto, port)
        if not ok:
            return f"{a} outbound: {why}"
        ok, why = _acl_verdict(cb, ib["acl_in"] if ib else None, a, ia["ip"] if ia else "", dst, dst_ip, proto, port)
        if not ok:
            return f"{b} inbound: {why}"
        if service and cb.host_firewall.enabled and b == dst:
            for r in cb.host_firewall.rules:
                if r.get("action") == "deny" and r.get("port") in (port, "any"):
                    return f"host firewall on {b} denies port {port}"
        return None

    def _fw_transit_block(self, fw: str, ingress_zone: str, egress_zone: str, service: dict) -> str | None:
        cfg = self.configs[fw]
        pols = [p for p in cfg.fw_policies if p.enabled]
        if not pols:
            return None
        for p in sorted(pols, key=lambda x: x.id):
            if p.src_zone not in ("any", ingress_zone) or p.dst_zone not in ("any", egress_zone):
                continue
            if p.service not in ("any", service["name"]):
                continue
            if p.action == "allow":
                return None
            return f"firewall policy '{p.name}' denies {service['name']} (first match)"
        return f"firewall implicit deny (no allow policy for {service['name']})"

    # -- BFS over (device, ingress_interface) -------------------------------
    def explain(self, src: str, dst: str) -> dict:
        if src not in self.configs or dst not in self.configs:
            return {"reachable": False, "path": [], "hops": [], "reason": "device missing"}
        cb = self.configs[dst]
        weak = bool(cb.weaknesses or cb.patches.missing)
        has_session = any(sess.active for u in cb.users for sess in u.sessions)
        services = [s.model_dump() for s in cb.services if s.enabled]
        if not services:
            return {"reachable": False, "path": [], "hops": [], "reason": f"{dst} exposes no enabled service"}
        if not (weak or has_session):
            return {"reachable": False, "path": [], "hops": [],
                    "reason": f"{dst} has no weakness/missing patch and attacker holds no session"}
        for service in services:  # consider EVERY enabled target service
            result = self._bfs_service(src, dst, service)
            if result["reachable"]:
                return result
        return {"reachable": False, "path": [], "hops": [],
                "reason": f"no path allows any of {[s['name'] for s in services]} (link/filter/firewall rules refused; {'; '.join(self.refusals[:3])})"}

    def _bfs_service(self, src: str, dst: str, service: dict) -> dict:
        start = (src, None)
        q: deque = deque([[start]])
        seen = {start}
        parent: dict[tuple, tuple[tuple, str]] = {}
        while q:
            states = q.popleft()
            device, _ingress = states[-1]
            if device == dst:
                path = [s[0] for s in states]
                hops = []
                for i in range(len(states) - 1):
                    frm = states[i][0]
                    hops.append({"from": frm, "to": states[i + 1][0], "rule": parent[states[i + 1]][1]})
                return {"reachable": True, "path": path, "hops": hops,
                        "reason": f"path exists for service {service['name']}; target weak or session held"}
            for nxt in self.adj.get(device, []):
                found = self._cable_for(device, nxt)
                if found is None:
                    continue
                _c, _pa, pb = found
                up, why = self.link_up(device, nxt)
                if not up:
                    if "missing port" in why and why not in self.refusals:
                        self.refusals.append(why)
                    continue
                block = self._filter_block(device, nxt, _ingress, service, dst)
                if block:
                    continue
                # firewall transit: leaving a firewall (that is not the source) toward the next hop
                if self.categories.get(device) == "firewall" and device != src:
                    in_iface = self._iface(device, states[-1][1]) if states[-1][1] else None
                    ib = self._iface(nxt, pb)
                    fw_block = self._fw_transit_block(device, in_iface["zone"] if in_iface else "any",
                                                      ib["zone"] if ib else "any", service)
                    if fw_block:
                        continue
                    why = f"{why}; firewall transit allowed for {service['name']}"
                state = (nxt, pb)
                if state in seen:
                    continue
                seen.add(state)
                parent[state] = (states[-1], f"{why}; service {service['name']} allowed")
                q.append(states + [state])
        return {"reachable": False, "path": [], "hops": [], "reason": "no path for this service"}


def compile_twin(configs: dict[str, DeviceConfig], cables: list[dict], categories: dict[str, str]) -> CompiledTwin:
    h = content_hash(configs, cables)
    if h in _cache:
        _cache.move_to_end(h)
        return _cache[h]
    twin = CompiledTwin(configs, cables, categories)
    _cache[h] = twin
    while len(_cache) > CACHE_MAXSIZE:
        _cache.popitem(last=False)
    return twin
