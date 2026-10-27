"""Deterministic graph-based digital twin. Synthetic assets only."""

import copy
import random
import zlib
from collections import deque

import networkx as nx

# Typed telemetry step types the adversary simulator may emit. Anything else is rejected.
ATTACK_STEP_TYPES = {
    "process_start", "file_modification_burst", "network_connection", "auth_anomaly",
    "session_created", "authorization_failure", "config_modification", "security_detection",
}

ASSETS = [
    {"id": "internet", "name": "Internet Gateway", "asset_type": "gateway", "zone": "external", "posture": 0.4, "pos": [-8.5, 1.4, -4.5], "vulnerabilities": ["exposed_surface"]},
    {"id": "firewall", "name": "Firewall", "asset_type": "firewall", "zone": "perimeter", "posture": 0.9, "pos": [-6, 1.2, -1.2], "vulnerabilities": ["permissive_default_rule"]},
    {"id": "web-server", "name": "Web Server", "asset_type": "web_server", "zone": "dmz", "posture": 0.65, "pos": [-4.4, 1.5, -5.2], "vulnerabilities": ["exposed_service"]},
    {"id": "app-server", "name": "Application Server", "asset_type": "app_server", "zone": "internal", "posture": 0.75, "pos": [0.2, 1.2, -0.8], "vulnerabilities": ["overprivileged_service_account"]},
    {"id": "database", "name": "Database", "asset_type": "database", "zone": "data", "posture": 0.85, "pos": [7.4, 1.3, -2.6], "vulnerabilities": []},
    {"id": "identity-provider", "name": "Identity Provider", "asset_type": "identity", "zone": "identity", "posture": 0.9, "pos": [1.1, 3.0, 3.2], "vulnerabilities": []},
    {"id": "admin-workstation", "name": "Admin Workstation", "asset_type": "workstation", "zone": "endpoints", "posture": 0.8, "pos": [5.5, 1.0, 2.8], "vulnerabilities": []},
    {"id": "employee-workstation", "name": "Employee Workstation", "asset_type": "workstation", "zone": "endpoints", "posture": 0.55, "pos": [-6.2, 0.8, 3.2], "vulnerabilities": ["unpatched_client"]},
    {"id": "file-server", "name": "File Server", "asset_type": "file_server", "zone": "internal", "posture": 0.7, "pos": [-1.2, 0.9, 5.2], "vulnerabilities": ["open_share"]},
    {"id": "security-sensor", "name": "Security Sensor", "asset_type": "sensor", "zone": "security", "posture": 0.95, "pos": [2.6, 2.9, 1.0], "vulnerabilities": []},
]

# source, target, trust, traversable (attack/data path), types
EDGES = [
    ("internet", "firewall", "low", True, ["https", "network"]),
    ("firewall", "web-server", "medium", True, ["https"]),
    ("web-server", "app-server", "medium", True, ["api"]),
    ("app-server", "database", "high", True, ["sql"]),
    ("app-server", "file-server", "medium", True, ["smb", "api"]),
    ("employee-workstation", "file-server", "medium", True, ["smb"]),
    ("employee-workstation", "app-server", "medium", True, ["https"]),
    ("admin-workstation", "app-server", "high", False, ["ssh_admin"]),
    ("admin-workstation", "database", "high", True, ["sql_admin"]),
    ("identity-provider", "app-server", "high", False, ["auth"]),
    ("identity-provider", "admin-workstation", "high", False, ["auth"]),
    ("identity-provider", "employee-workstation", "high", False, ["auth"]),
    ("security-sensor", "firewall", "high", False, ["telemetry"]),
    ("security-sensor", "app-server", "high", False, ["telemetry"]),
]

LEGITIMATE_PAIRS = [
    ("internet", "web-server", 1200),
    ("web-server", "app-server", 900),
    ("app-server", "database", 650),
    ("employee-workstation", "file-server", 240),
    ("employee-workstation", "app-server", 410),
    ("admin-workstation", "database", 25),
    ("admin-workstation", "app-server", 40),
]

ALLOWED_ACTIONS = {
    "isolate_asset", "block_connection", "revoke_session", "rotate_credential",
    "apply_patch", "disable_service", "restore_connectivity",
    "quarantine_vlan", "harden_mgmt", "kill_process", "restore_snapshot",
}


class DigitalTwin:
    def __init__(self, asset_defs: list[dict] | None = None, edge_defs: list[tuple] | None = None) -> None:
        self.asset_defs = copy.deepcopy(asset_defs) if asset_defs is not None else copy.deepcopy(ASSETS)
        self.edge_defs = list(edge_defs) if edge_defs is not None else list(EDGES)
        self.reset()

    @classmethod
    def from_dict(cls, assets: list[dict], connections: list[dict]) -> "DigitalTwin":
        """Build a twin from a user-designed definition (Twin Designer)."""
        defs = []
        for i, a in enumerate(assets):
            pos = a.get("pos") or [0, 1, 0]
            if len(pos) != 3:
                raise ValueError(f"asset {a.get('id')}: pos must be [x, y, z]")
            defs.append({"id": a["id"], "name": a.get("name", a["id"]), "asset_type": a.get("asset_type", "workstation"),
                         "zone": a.get("zone", "custom"), "posture": float(a.get("posture", 0.7)),
                         "pos": [float(pos[0]), float(pos[1]), float(pos[2])],
                         "vulnerabilities": list(a.get("vulnerabilities") or ["legacy_unpatched"])})
        ids = [d["id"] for d in defs]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate asset ids")
        edges = []
        for c in connections:
            s, t = c["source"], c["target"]
            if s not in ids or t not in ids:
                raise ValueError(f"connection references unknown asset: {s}->{t}")
            edges.append((s, t, c.get("trust", "medium"), bool(c.get("traversable", True)), list(c.get("types", ["network"]))))
        return cls(defs, edges)

    def reset(self) -> None:
        self.graph = nx.DiGraph()
        self.status: dict[str, str] = {}
        self.isolated: dict[str, bool] = {}
        self.service_disabled: dict[str, bool] = {}
        self.vulns: dict[str, list[str]] = {}
        for a in self.asset_defs:
            self.graph.add_node(a["id"])
            self.status[a["id"]] = "exposed" if a["id"] in ("internet", "web-server") else "healthy"
            self.isolated[a["id"]] = False
            self.service_disabled[a["id"]] = False
            self.vulns[a["id"]] = list(a["vulnerabilities"])
        self.edge_active: dict[frozenset, bool] = {}
        self.dir_active: dict[tuple[str, str], bool] = {}
        for s, t, trust, trav, types in self.edge_defs:
            # directed arcs both ways for data connections; auth/monitoring arcs keep listed direction
            self.graph.add_edge(s, t, trust=trust, traversable=trav, types=types)
            self.dir_active[(s, t)] = True
            if trav:
                self.graph.add_edge(t, s, trust=trust, traversable=trav, types=types)
                self.dir_active[(t, s)] = True
            self.edge_active[frozenset((s, t))] = True
        self.identities = {
            "admin-01": {"asset": "admin-workstation", "session_active": False, "compromised": False, "credential_version": 1},
            "employee-01": {"asset": "employee-workstation", "session_active": True, "compromised": False, "credential_version": 1},
        }
        # keep only identities whose asset exists in this twin
        self.identities = {k: v for k, v in self.identities.items() if v["asset"] in self.graph} or {
            "user-01": {"asset": self.asset_defs[0]["id"], "session_active": True, "compromised": False, "credential_version": 1}}
        self.containment: list[str] = []
        self.quarantined: set[str] = set()
        self.config_diffs: list[dict] = []
        self.pending_diffs: dict[str, dict] = {}
        self.config_versions: dict[str, list[dict]] = {}
        self.device_configs = self._build_device_configs()

    def _build_device_configs(self) -> dict:
        from app.devices.registry import BUILTIN_DEVICE_MAP
        from app.netmodel.config import DeviceConfig, Interface, Service, User, Session, Mgmt

        svc_by_type = {"web_server": [Service(name="http", port=80), Service(name="https", port=443)],
                       "database": [Service(name="postgres", port=5432), Service(name="sql", port=1433)],
                       "file_server": [Service(name="smb", port=445)],
                       "identity": [Service(name="ldaps", port=636), Service(name="https", port=443)],
                       "app_server": [Service(name="https", port=443), Service(name="api", port=8080)],
                       "sensor": [Service(name="ids", port=0)]}
        configs: dict[str, dict] = {}
        ip_octet = 10
        for a in self.asset_defs:
            aid = a["id"]
            ifaces = []
            for j, nb in enumerate(sorted(set(self.graph.successors(aid)) | set(self.graph.predecessors(aid)))):
                ip_octet += 1
                ifaces.append(Interface(name=f"eth{j}", peer=nb, ip=f"10.0.0.{ip_octet}", zone=a["zone"],
                                        description=f"to {nb}"))
            users = []
            for uname, idata in self.identities.items():
                if idata["asset"] == aid or aid == "identity-provider":
                    users.append(User(name=uname, role="admin" if "admin" in uname else "user", mfa="admin" not in uname,
                                      sessions=[Session(id=f"sess-{uname}", active=idata["session_active"], compromised=idata["compromised"])],
                                      credential_version=idata["credential_version"]))
            weak = list(a["vulnerabilities"])
            cfg = DeviceConfig(hostname=aid.upper().replace("-", "")[:10] + "-01", device_id=BUILTIN_DEVICE_MAP.get(aid, "generic"),
                               interfaces=ifaces, services=svc_by_type.get(a["asset_type"], []), users=users,
                               weaknesses=weak,
                               mgmt=Mgmt(telnet="telnet_enabled" in weak, snmp_community="public" if "snmp_public_community" in weak else None))
            cfg.patches.missing = ["CVE-SYNTH-001"] if weak else []
            configs[aid] = cfg.model_dump()
        return configs

    def config_hash(self) -> str:
        from app.netmodel.compiler import content_hash
        from app.netmodel.config import DeviceConfig

        cables = [{"a": {"device": s, "port": "eth0"}, "b": {"device": t, "port": "eth0"}}
                  for s, t, *_ in self.edge_defs]
        return content_hash({k: DeviceConfig(**v) for k, v in self.device_configs.items()}, cables)

    def cables_list(self) -> list[dict]:
        return [{"a": {"device": s, "port": "eth0"}, "b": {"device": t, "port": "eth0"}, "media": "copper"}
                for s, t, *_ in self.edge_defs]

    def explain_path(self, src: str, dst: str) -> dict:
        path = self.find_path(src, dst)
        if not path:
            return {"reachable": False, "path": [], "hops": [], "reason": "no traversable path (links, filtering, or vulnerability gate)"}
        hops = []
        for i in range(len(path) - 1):
            a, b = path[i], path[i + 1]
            services = self.device_configs.get(b, {}).get("services", [])
            svc = next((s["name"] for s in services if s.get("enabled")), "transit")
            weak = self.device_configs.get(b, {}).get("weaknesses", [])
            hops.append({"from": a, "to": b,
                         "rule": f"directed arc {a}->{b} active+traversable; service {svc}; "
                                 + (f"weakness {weak}" if weak else "final target / session-covered hop")})
        return {"reachable": True, "path": path, "hops": hops, "config_hash": self.config_hash()}

    # --- introspection -------------------------------------------------
    def asset_ids(self) -> list[str]:
        return [a["id"] for a in self.asset_defs]

    def assets_status_isolated(self) -> list[str]:
        return [aid for aid, v in self.isolated.items() if v]

    def live_graph(self, target: str | None = None) -> nx.DiGraph:
        """The one shared directed graph: exactly the arcs find_path can traverse.
        enumerate_paths (red team) and find_path must never disagree — both use this.
        Vulnerability gating is target-relative, so callers that know the objective
        should pass it; without a target, intermediate hops require a vulnerability."""
        g = nx.DiGraph()
        for u, v, data in self.graph.edges(data=True):
            if not (data.get("traversable") and self.dir_active.get((u, v), False)):
                continue
            if target is None:
                if not (self.vulns.get(v) or any(i["compromised"] for i in self.identities.values())):
                    continue
            elif not self.hop_allowed(v, target):
                continue
            g.add_edge(u, v)
        for aid in self.assets_status_isolated():
            if aid in g:
                g.remove_node(aid)
        return g

    def to_dict(self) -> dict:
        assets = []
        for a in self.asset_defs:
            aid = a["id"]
            assets.append({**a, "status": self.status[aid], "isolated": self.isolated[aid],
                           "service_disabled": self.service_disabled[aid], "vulnerabilities": list(self.vulns[aid]),
                           "connected": sorted(set(self.graph.successors(aid)) | set(self.graph.predecessors(aid)))})
        conns = []
        for s, t, trust, trav, types in self.edge_defs:
            fwd = self.dir_active.get((s, t), False) and not self.isolated[s] and not self.isolated[t]
            rev = self.dir_active.get((t, s), False) and not self.isolated[s] and not self.isolated[t]
            conns.append({"source": s, "target": t, "trust": trust, "traversable": trav, "types": types,
                          "active": fwd or rev, "dir_forward_active": fwd, "dir_reverse_active": rev,
                          "one_way_blocked": fwd != rev})
        from app.devices.registry import BUILTIN_DEVICE_MAP, BY_ID

        devices = []
        for a in self.asset_defs:
            aid = a["id"]
            dev_id = BUILTIN_DEVICE_MAP.get(aid)
            manifest = BY_ID.get(dev_id or "")
            links = []
            for s, t, *_ in self.edge_defs:
                if aid in (s, t):
                    peer = t if s == aid else s
                    state = "down" if (self.isolated[aid] or aid in self.quarantined) else \
                        "filtered" if not (self.dir_active.get((aid, peer), True)) else "up"
                    links.append({"peer": peer, "state": state})
            devices.append({"asset_id": aid, "device_id": dev_id, "model": manifest.model if manifest else aid,
                            "vendor": manifest.vendor if manifest else "Synthetic",
                            "ports": [f"{p['prefix']}{p['start'] + i}" for p in (manifest.hardware.model_dump()["ports"] if manifest else [])
                                      for i in range(p["count"])][:8],
                            "links": links, "config_hash": self.config_hash()})
        return {"assets": assets, "connections": conns, "devices": devices,
                "identities": copy.deepcopy(self.identities), "containment": list(self.containment)}

    def snapshot(self) -> dict:
        return {"status": dict(self.status), "isolated": dict(self.isolated),
                "service_disabled": dict(self.service_disabled),
                "vulns": copy.deepcopy(self.vulns),
                "edge_active": {"||".join(sorted(k)): v for k, v in self.edge_active.items()},
                "dir_active": {"||".join(k): v for k, v in self.dir_active.items()},
                "quarantined": sorted(self.quarantined),
                "device_configs": copy.deepcopy(self.device_configs),
                "identities": copy.deepcopy(self.identities), "containment": list(self.containment)}

    def restore(self, snap: dict) -> None:
        self.quarantined = set(snap.get("quarantined", []))
        if not hasattr(self, "config_diffs"):
            self.config_diffs = []; self.pending_diffs = {}; self.config_versions = {}
        if "device_configs" in snap:
            self.device_configs = copy.deepcopy(snap["device_configs"])
        self.status = dict(snap["status"]); self.isolated = dict(snap["isolated"])
        self.service_disabled = dict(snap["service_disabled"]); self.vulns = copy.deepcopy(snap["vulns"])
        self.edge_active = {frozenset(k.split("||") if isinstance(k, str) else k): v for k, v in snap["edge_active"].items()}
        if "dir_active" in snap:
            self.dir_active = {tuple(k.split("||")): v for k, v in snap["dir_active"].items()}  # type: ignore[assignment]
        else:  # legacy snapshot: derive both directions from the undirected flag
            self.dir_active = {}
            for s, t, _trust, trav, _types in self.edge_defs:
                v = self.edge_active.get(frozenset((s, t)), True)
                self.dir_active[(s, t)] = v
                if trav:
                    self.dir_active[(t, s)] = v
        self.identities = copy.deepcopy(snap["identities"]); self.containment = list(snap["containment"])

    def clone(self) -> "DigitalTwin":
        c = DigitalTwin.__new__(DigitalTwin)
        c.asset_defs = copy.deepcopy(self.asset_defs)
        c.edge_defs = list(self.edge_defs)
        c.graph = self.graph.copy()
        c.restore(self.snapshot())
        return c

    # --- graph queries ---------------------------------------------------
    def _blocked_node(self, n: str, src: str, dst: str) -> bool:
        if self.isolated[n] or self.service_disabled[n]:
            return n not in (src, dst) or self.isolated[n]
        return False

    def reachable(self, src: str, dst: str) -> bool:
        return self.find_path(src, dst) is not None

    def find_path(self, src: str, dst: str) -> list[str] | None:
        if src not in self.graph or dst not in self.graph:
            return None
        if self.isolated[src] or self.isolated[dst] or src in self.quarantined or dst in self.quarantined:
            return None
        q = deque([[src]]); seen = {src}
        while q:
            path = q.popleft()
            node = path[-1]
            if node == dst:
                return path
            for nb in self.graph.successors(node):
                if not self.dir_active.get((node, nb), False):
                    continue
                if not self.graph[node][nb].get("traversable", False):
                    continue
                if not self.hop_allowed(nb, dst):
                    continue
                if nb in seen or self.isolated[nb] or self.service_disabled[nb] or nb in self.quarantined:
                    continue
                seen.add(nb); q.append(path + [nb])
        return None

    def legitimate_disrupted(self, baseline: "DigitalTwin") -> int:
        disrupted = 0
        for s, t, _users in LEGITIMATE_PAIRS:
            if s in self.graph and t in self.graph and baseline.reachable(s, t) and not self.reachable(s, t):
                disrupted += 1
        return disrupted

    def hop_allowed(self, dest: str, final_target: str) -> bool:
        """A hop into an asset is traversable only if it has a vulnerability, is the
        final target, or a compromised synthetic identity covers the pivot."""
        if dest == final_target:
            return True
        if self.vulns.get(dest):
            return True
        return any(i["compromised"] for i in self.identities.values()) and dest in ("database", "admin-workstation", "identity-provider")

    # --- actions ---------------------------------------------------------
    def apply_action(self, action_type: str, asset_id: str, params: dict | None = None) -> dict:
        params = params or {}
        if action_type not in ALLOWED_ACTIONS:
            raise ValueError(f"unsupported action: {action_type}")
        if asset_id not in self.graph:
            raise ValueError(f"missing asset: {asset_id}")
        before = self.status[asset_id]
        if action_type == "isolate_asset":
            self.isolated[asset_id] = True; self.status[asset_id] = "contained"
            for k in list(self.dir_active):
                if asset_id in k:
                    self.dir_active[k] = False
            self.containment.append(f"isolate:{asset_id}")
        elif action_type == "block_connection":
            s, t = params.get("source", asset_id), params.get("target")
            if not t or not (self.graph.has_edge(s, t) or self.graph.has_edge(t, s)):
                raise ValueError("missing connection")
            direction = params.get("direction", "both")
            if direction in ("outbound", "egress"):  # one-way egress control: block s->t only, t->s keeps flowing
                self.dir_active[(s, t)] = False
                self.containment.append(f"block_outbound:{s}->{t}")
            elif direction == "ingress":  # block only the reverse arc t->s
                self.dir_active[(t, s)] = False
                self.containment.append(f"block_ingress:{s}->{t}")
            else:
                self.dir_active[(s, t)] = False; self.dir_active[(t, s)] = False
                self.containment.append(f"block:{s}->{t}")
            self.edge_active[frozenset((s, t))] = self.dir_active.get((s, t), False) or self.dir_active.get((t, s), False)
            self.status[asset_id] = "remediated" if self.status[asset_id] != "compromised" else "contained"
        elif action_type == "revoke_session":
            ident = self._identity_for(params, asset_id)
            self.identities[ident]["session_active"] = False
            self.identities[ident]["compromised"] = False
            self.containment.append(f"revoke:{ident}")
            self.status[asset_id] = "remediated"
        elif action_type == "rotate_credential":
            ident = self._identity_for(params, asset_id)
            self.identities[ident]["credential_version"] += 1
            self.identities[ident]["compromised"] = False
            self.identities[ident]["session_active"] = False
            self.containment.append(f"rotate:{ident}")
            self.status[asset_id] = "remediated"
        elif action_type == "apply_patch":
            self.vulns[asset_id] = []; self.status[asset_id] = "remediated"
            self.containment.append(f"patch:{asset_id}")
        elif action_type == "disable_service":
            self.service_disabled[asset_id] = True; self.status[asset_id] = "contained"
            self.containment.append(f"disable_service:{asset_id}")
        elif action_type == "quarantine_vlan":
            self.quarantined.add(asset_id); self.status[asset_id] = "contained"
            self.device_configs[asset_id]["quarantine_vlan"] = 999
            self.device_configs[asset_id]["interfaces"] = [
                {**i, "vlan": 999, "mode": "access"} for i in self.device_configs[asset_id]["interfaces"]]
            self.containment.append(f"quarantine:{asset_id}")
        elif action_type == "harden_mgmt":
            cfg = self.device_configs[asset_id]
            cfg["mgmt"] = {"telnet": False, "ssh": True, "http": False, "https": True, "snmp_community": None}
            cfg["weaknesses"] = [w for w in cfg["weaknesses"] if w not in ("telnet_enabled", "snmp_public_community")]
            self.vulns[asset_id] = [w for w in self.vulns[asset_id] if w not in ("telnet_enabled", "snmp_public_community")]
            self.status[asset_id] = "remediated"
            self.containment.append(f"harden_mgmt:{asset_id}")
        elif action_type == "kill_process":
            self.status[asset_id] = "contained" if self.status[asset_id] == "compromised" else self.status[asset_id]
            self.containment.append(f"kill_process:{params.get('process', 'suspicious')}")
        elif action_type == "restore_snapshot":
            self.status[asset_id] = "healthy"
            self.vulns[asset_id] = []
            self.device_configs[asset_id]["weaknesses"] = []
            self.containment.append(f"restore_snapshot:{asset_id}")
        elif action_type == "restore_connectivity":
            if params.get("source") and params.get("target"):  # un-block one connection (self-healing)
                s, t = params["source"], params["target"]
                self.dir_active[(s, t)] = True; self.dir_active[(t, s)] = True
                self.edge_active[frozenset((s, t))] = True
                self.containment = [c for c in self.containment
                                    if c not in (f"block:{s}->{t}", f"block_outbound:{s}->{t}", f"block:{t}->{s}", f"block_outbound:{t}->{s}")]
            else:
                self.isolated[asset_id] = False; self.status[asset_id] = "healthy"
                for s, t, _trust, trav, _types in self.edge_defs:
                    if asset_id in (s, t):
                        self.dir_active[(s, t)] = True
                        if trav:
                            self.dir_active[(t, s)] = True
                self.containment = [c for c in self.containment if c != f"isolate:{asset_id}"]
        # configuration is the twin: every action is recorded as a ConfigDiff and config state syncs
        self.device_configs[asset_id]["isolated"] = self.isolated[asset_id]
        if action_type == "apply_patch":
            self.device_configs[asset_id]["weaknesses"] = []
            self.device_configs[asset_id]["patches"] = {"level": "current", "missing": []}
        diff = {"device_id": asset_id, "action": action_type, "params": params,
                "config_hash_after": self.config_hash()}
        self.config_diffs.append(diff)
        return {"action_type": action_type, "asset_id": asset_id, "before_status": before,
                "after_status": self.status[asset_id], "params": params, "config_diff": diff}

    def _identity_for(self, params: dict, asset_id: str) -> str:
        if params.get("identity") in self.identities:
            return params["identity"]
        for name, data in self.identities.items():
            if data["asset"] == asset_id:
                return name
        return "admin-01"  # identity-provider manages admin-01

    # --- attack simulation -------------------------------------------------
    def apply_attack(self, scenario: dict, seed: int = 42) -> list[dict]:
        """Typed scenario steps only. Mutates twin to attacked state; returns telemetry."""
        # stable cross-process seed (builtin hash() is randomized per process)
        rng = random.Random(seed + zlib.crc32(scenario["id"].encode()) % 1000)
        events: list[dict] = []
        src, tgt = scenario["source_asset"], scenario["target_asset"]
        for i, step in enumerate(scenario["attack_steps"]):
            if step["type"] not in ATTACK_STEP_TYPES:
                raise ValueError(f"attack step type not in allowlist: {step['type']}")
            asset = step["asset"]
            if asset in self.status and self.status[asset] not in ("contained",):
                self.status[asset] = "suspicious" if i < len(scenario["attack_steps"]) - 1 else "compromised"
            events.append({"id": f"tele-{scenario['id']}-{seed}-{i}", "event_type": step["type"], "asset_id": asset, "synthetic": True,
                           "message": step["description"], "offset_ms": 400 * (i + 1),
                           "severity": "high" if i >= 1 else "medium",
                           "detail": {"step": i, "seed": seed}})
        if scenario["id"] == "ransomware_activity":
            self.status[src] = "compromised"
            if self.reachable(src, tgt):
                self.status[tgt] = "suspicious"
                events.append({"id": f"tele-{scenario['id']}-{seed}-spread", "event_type": "file_modification_burst", "asset_id": tgt, "synthetic": True,
                               "message": f"Synthetic shared-file modifications spreading ({180 + rng.randint(0, 60)} files/min)",
                               "offset_ms": 2400, "severity": "critical", "detail": {"spread": True}})
        if scenario.get("identity"):
            ident = self.identities[scenario["identity"]]
            ident["session_active"] = True; ident["compromised"] = True
            self.status["identity-provider"] = "suspicious"; self.status[src] = "compromised"
        if scenario["id"] == "lateral_movement" and self.reachable(src, tgt):
            self.status[tgt] = "suspicious"
        return events

    def attempt_attack_objective(self, scenario: dict) -> dict:
        """Replay check used by verification on a (possibly modified) twin."""
        kind = scenario["verification_kind"]
        if kind == "reachability":
            path = self.find_path(scenario["source_asset"], scenario["target_asset"])
            return {"objective_blocked": path is None, "reachable": path is not None, "path": path}
        ident = self.identities[scenario["identity"]]
        # access succeeds only with an active compromised session on the original credential
        success = bool(ident["session_active"] and ident["compromised"])
        return {"objective_blocked": not success, "access_granted": success,
                "session_active": ident["session_active"], "credential_version": ident["credential_version"]}
