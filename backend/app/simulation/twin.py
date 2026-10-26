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
    {"id": "firewall", "name": "Firewall", "asset_type": "firewall", "zone": "perimeter", "posture": 0.9, "pos": [-6, 1.2, -1.2], "vulnerabilities": []},
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
    ("internet", "web-server"),
    ("web-server", "app-server"),
    ("app-server", "database"),
    ("employee-workstation", "file-server"),
    ("employee-workstation", "app-server"),
    ("admin-workstation", "database"),
    ("admin-workstation", "app-server"),
]

ALLOWED_ACTIONS = {
    "isolate_asset", "block_connection", "revoke_session", "rotate_credential",
    "apply_patch", "disable_service", "restore_connectivity",
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
                         "vulnerabilities": list(a.get("vulnerabilities", []))})
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
        self.graph = nx.Graph()
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
        for s, t, trust, trav, types in self.edge_defs:
            self.graph.add_edge(s, t, trust=trust, traversable=trav, types=types)
            self.edge_active[frozenset((s, t))] = True
        self.identities = {
            "admin-01": {"asset": "admin-workstation", "session_active": False, "compromised": False, "credential_version": 1},
            "employee-01": {"asset": "employee-workstation", "session_active": True, "compromised": False, "credential_version": 1},
        }
        # keep only identities whose asset exists in this twin
        self.identities = {k: v for k, v in self.identities.items() if v["asset"] in self.graph} or {
            "user-01": {"asset": self.asset_defs[0]["id"], "session_active": True, "compromised": False, "credential_version": 1}}
        self.containment: list[str] = []

    # --- introspection -------------------------------------------------
    def asset_ids(self) -> list[str]:
        return [a["id"] for a in self.asset_defs]

    def to_dict(self) -> dict:
        assets = []
        for a in self.asset_defs:
            aid = a["id"]
            assets.append({**a, "status": self.status[aid], "isolated": self.isolated[aid],
                           "service_disabled": self.service_disabled[aid], "vulnerabilities": list(self.vulns[aid]),
                           "connected": sorted(self.graph.neighbors(aid))})
        conns = []
        for s, t, trust, trav, types in self.edge_defs:
            conns.append({"source": s, "target": t, "trust": trust, "traversable": trav, "types": types,
                          "active": self.edge_active[frozenset((s, t))] and not self.isolated[s] and not self.isolated[t]})
        return {"assets": assets, "connections": conns,
                "identities": copy.deepcopy(self.identities), "containment": list(self.containment)}

    def snapshot(self) -> dict:
        return {"status": dict(self.status), "isolated": dict(self.isolated),
                "service_disabled": dict(self.service_disabled),
                "vulns": copy.deepcopy(self.vulns),
                "edge_active": {"||".join(sorted(k)): v for k, v in self.edge_active.items()},
                "identities": copy.deepcopy(self.identities), "containment": list(self.containment)}

    def restore(self, snap: dict) -> None:
        self.status = dict(snap["status"]); self.isolated = dict(snap["isolated"])
        self.service_disabled = dict(snap["service_disabled"]); self.vulns = copy.deepcopy(snap["vulns"])
        self.edge_active = {frozenset(k.split("||") if isinstance(k, str) else k): v for k, v in snap["edge_active"].items()}
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
        if self.isolated[src] or self.isolated[dst]:
            return None
        q = deque([[src]]); seen = {src}
        while q:
            path = q.popleft()
            node = path[-1]
            if node == dst:
                return path
            for nb in self.graph.neighbors(node):
                key = frozenset((node, nb))
                if not self.edge_active.get(key, False):
                    continue
                if not self.graph[node][nb].get("traversable", False):
                    continue
                if nb in seen or self.isolated[nb] or self.service_disabled[nb]:
                    continue
                seen.add(nb); q.append(path + [nb])
        return None

    def legitimate_disrupted(self, baseline: "DigitalTwin") -> int:
        disrupted = 0
        for s, t in LEGITIMATE_PAIRS:
            if s in self.graph and t in self.graph and baseline.reachable(s, t) and not self.reachable(s, t):
                disrupted += 1
        return disrupted

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
            self.containment.append(f"isolate:{asset_id}")
        elif action_type == "block_connection":
            s, t = params.get("source", asset_id), params.get("target")
            if not t or not self.graph.has_edge(s, t):
                raise ValueError("missing connection")
            self.edge_active[frozenset((s, t))] = False
            self.containment.append(f"block:{s}->{t}")
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
        elif action_type == "restore_connectivity":
            self.isolated[asset_id] = False; self.status[asset_id] = "healthy"
            self.containment = [c for c in self.containment if c != f"isolate:{asset_id}"]
        return {"action_type": action_type, "asset_id": asset_id, "before_status": before,
                "after_status": self.status[asset_id], "params": params}

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
            events.append({"event_type": step["type"], "asset_id": asset, "synthetic": True,
                           "message": step["description"], "offset_ms": 400 * (i + 1),
                           "severity": "high" if i >= 1 else "medium",
                           "detail": {"step": i, "seed": seed}})
        if scenario["id"] == "ransomware_activity":
            self.status[src] = "compromised"
            if self.reachable(src, tgt):
                self.status[tgt] = "suspicious"
                events.append({"event_type": "file_modification_burst", "asset_id": tgt, "synthetic": True,
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
