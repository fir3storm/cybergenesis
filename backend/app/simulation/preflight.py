"""Attack-path regression preflight: replay a proposed network change against
every saved scenario on a CLONE of the twin (the stored twin is never mutated).

Deterministic only: typed allowlisted change ops, the twin's own live_graph
path enumeration, and max-flow/min-cut. No LLM in this trust path.
"""

import itertools

import networkx as nx
from pydantic import BaseModel, ConfigDict, Field

from app.simulation.twin import DigitalTwin

MAX_PATHS = 20
NEW_PATH_SEARCH_CAP = 500


class ChangeOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: str
    src: str | None = None
    dst: str | None = None
    asset_id: str | None = None
    vuln: str | None = None
    posture: float | None = Field(default=None, ge=0, le=1)
    asset: dict | None = None


_ALLOWED_OPS = {"add_link", "remove_link", "add_vulnerability", "remove_vulnerability", "set_posture", "add_asset"}


def validate_ops(raw_ops) -> list[ChangeOp]:
    """Validate a raw op list; unknown ops / shapes raise ValueError (-> 422)."""
    if not isinstance(raw_ops, list):
        raise ValueError("change ops must be a list")  # noqa: TRY004
    ops: list[ChangeOp] = []
    for i, raw in enumerate(raw_ops):
        if not isinstance(raw, dict):
            raise ValueError(f"change op {i} must be an object")  # noqa: TRY004
        op_name = raw.get("op")
        if op_name not in _ALLOWED_OPS:
            raise ValueError(f"unknown change op: {op_name!r} (allowed: {', '.join(sorted(_ALLOWED_OPS))})")
        try:
            op = ChangeOp(**raw)
        except Exception as e:  # pydantic validation
            raise ValueError(f"change op {i} invalid: {e}") from e
        # per-op required fields
        if op_name in ("add_link", "remove_link") and not (op.src and op.dst):
            # also accept source/target spellings
            op.src = op.src or raw.get("source")
            op.dst = op.dst or raw.get("target")
            if not (op.src and op.dst):
                raise ValueError(f"change op {i} ({op_name}) requires src and dst")
        if op_name in ("add_vulnerability", "remove_vulnerability") and not (op.asset_id and op.vuln):
            raise ValueError(f"change op {i} ({op_name}) requires asset_id and vuln")
        if op_name == "set_posture" and not (op.asset_id and op.posture is not None):
            raise ValueError(f"change op {i} (set_posture) requires asset_id and posture")
        if op_name == "add_asset" and not (op.asset and op.asset.get("id")):
            raise ValueError(f"change op {i} (add_asset) requires asset with an id")
        ops.append(op)
    return ops


def _ensure_interface(twin: DigitalTwin, asset_id: str, peer: str) -> None:
    cfg = twin.device_configs.get(asset_id)
    if cfg is None:
        return
    ifaces = cfg.setdefault("interfaces", [])
    if not any(i.get("name") == "eth0" for i in ifaces):
        ifaces.append({"name": "eth0", "peer": peer, "ip": "", "zone": "internal",
                       "description": f"to {peer}", "enabled": True, "mode": "routed", "vlan": 1,
                       "allowed_vlans": [], "prefix": 24, "acl_in": None, "acl_out": None})


def apply_change_op(twin: DigitalTwin, op: ChangeOp) -> None:
    if op.op == "add_link":
        if op.src not in twin.graph or op.dst not in twin.graph:
            raise ValueError(f"add_link references unknown asset: {op.src}->{op.dst}")
        if not any(s == op.src and t == op.dst for s, t, *_ in twin.edge_defs):
            twin.edge_defs.append((op.src, op.dst, "medium", True, ["network"]))
        twin.graph.add_edge(op.src, op.dst, trust="medium", traversable=True, types=["network"])
        twin.graph.add_edge(op.dst, op.src, trust="medium", traversable=True, types=["network"])
        twin.dir_active[(op.src, op.dst)] = True
        twin.dir_active[(op.dst, op.src)] = True
        twin.edge_active[frozenset((op.src, op.dst))] = True
        _ensure_interface(twin, op.src, op.dst)
        _ensure_interface(twin, op.dst, op.src)
    elif op.op == "remove_link":
        if op.src not in twin.graph or op.dst not in twin.graph:
            raise ValueError(f"remove_link references unknown asset: {op.src}->{op.dst}")
        twin.dir_active[(op.src, op.dst)] = False
        twin.dir_active[(op.dst, op.src)] = False
        twin.edge_active[frozenset((op.src, op.dst))] = False
    elif op.op == "add_vulnerability":
        if op.asset_id not in twin.graph:
            raise ValueError(f"add_vulnerability references unknown asset: {op.asset_id}")
        cur = list(twin.vulns.get(op.asset_id, []))
        if op.vuln not in cur:
            cur.append(op.vuln)
        twin.set_state(op.asset_id, "weaknesses", cur)
        # re-enabling telnet-style weaknesses must be visible to mgmt checks
        if op.vuln == "telnet_enabled" and op.asset_id in twin.device_configs:
            twin.device_configs[op.asset_id].setdefault("mgmt", {})["telnet"] = True
    elif op.op == "remove_vulnerability":
        if op.asset_id not in twin.graph:
            raise ValueError(f"remove_vulnerability references unknown asset: {op.asset_id}")
        twin.set_state(op.asset_id, "weaknesses",
                       [v for v in twin.vulns.get(op.asset_id, []) if v != op.vuln])
    elif op.op == "set_posture":
        if op.asset_id not in twin.graph:
            raise ValueError(f"set_posture references unknown asset: {op.asset_id}")
        for a in twin.asset_defs:
            if a["id"] == op.asset_id:
                a["posture"] = float(op.posture)
    elif op.op == "add_asset":
        asset = dict(op.asset)
        aid = asset["id"]
        if aid in twin.graph:
            raise ValueError(f"add_asset duplicates existing asset: {aid}")
        asset.setdefault("name", aid)
        asset.setdefault("asset_type", "workstation")
        asset.setdefault("zone", "internal")
        asset.setdefault("posture", 0.7)
        asset.setdefault("pos", [0, 1, 0])
        asset.setdefault("vulnerabilities", ["legacy_unpatched"])
        twin.asset_defs.append({"id": aid, "name": asset["name"], "asset_type": asset["asset_type"],
                                "zone": asset["zone"], "posture": float(asset["posture"]),
                                "pos": list(asset["pos"]), "vulnerabilities": list(asset["vulnerabilities"]),
                                "device_id": asset.get("device_id")})
        twin.graph.add_node(aid)
        twin.status[aid] = "healthy"
        twin.isolated[aid] = False
        twin.service_disabled[aid] = False
        twin.vulns[aid] = list(asset["vulnerabilities"])
        from app.netmodel.config import DeviceConfig, Interface, Service

        twin.device_configs[aid] = DeviceConfig(
            hostname=aid.upper().replace("-", "")[:10] + "-01", device_id=asset.get("device_id") or "generic",
            interfaces=[Interface(name="eth0", peer="", enabled=True)],
            services=[Service(name="https", port=443)], weaknesses=list(asset["vulnerabilities"])).model_dump()
    else:  # pragma: no cover - validate_ops guards this
        raise ValueError(f"unknown change op: {op.op}")


def apply_change(twin: DigitalTwin, ops: list[ChangeOp]) -> DigitalTwin:
    clone = twin.clone()
    for op in ops:
        apply_change_op(clone, op)
    return clone


def derive_ops_from_definition(twin: DigitalTwin, definition: dict) -> list[ChangeOp]:
    """Diff an imported twin definition (assets+connections) against the twin."""
    ops: list[dict] = []
    cur_assets = {a["id"]: a for a in twin.to_dict()["assets"]}
    new_assets = {a["id"]: a for a in definition.get("assets", [])}
    for aid, a in sorted(new_assets.items()):
        if aid not in cur_assets:
            ops.append({"op": "add_asset", "asset": a})
        else:
            if float(a.get("posture", 0.7)) != float(cur_assets[aid].get("posture", 0.7)):
                ops.append({"op": "set_posture", "asset_id": aid, "posture": float(a.get("posture", 0.7))})
            for v in sorted(set(a.get("vulnerabilities") or []) - set(cur_assets[aid].get("vulnerabilities") or [])):
                ops.append({"op": "add_vulnerability", "asset_id": aid, "vuln": v})
            for v in sorted(set(cur_assets[aid].get("vulnerabilities") or []) - set(a.get("vulnerabilities") or [])):
                ops.append({"op": "remove_vulnerability", "asset_id": aid, "vuln": v})
    # importer connections list each direction separately, as (source, target) pairs
    def _pairs(conns):
        return {(c["source"], c["target"]) for c in conns}

    # current traversable directed pairs: to_dict has one entry per edge_def,
    # so expand both directions when active
    cur_directed = set()
    for c in twin.to_dict()["connections"]:
        if c.get("dir_forward_active", c.get("active")):
            cur_directed.add((c["source"], c["target"]))
        if c.get("dir_reverse_active", c.get("active")):
            cur_directed.add((c["target"], c["source"]))
    new_directed = _pairs(definition.get("connections", []))
    for s, t in sorted(new_directed - cur_directed):
        ops.append({"op": "add_link", "src": s, "dst": t})
    for s, t in sorted(cur_directed - new_directed):
        # only report a removal once per undirected pair when both directions vanish
        if (t, s) not in new_directed:
            ops.append({"op": "remove_link", "src": s, "dst": t})
    return validate_ops(ops)


def resolve_change(twin: DigitalTwin, change) -> tuple[list[ChangeOp], list[dict]]:
    """Accept ops list / {ops} / {configs,dialect} / {csv}. Returns (ops, derived_ops_dicts)."""
    if isinstance(change, list):
        ops = validate_ops(change)
        return ops, [o.model_dump(exclude_none=True) for o in ops]
    if not isinstance(change, dict):
        raise ValueError("change must be a list of ops or an object with ops/configs/csv")  # noqa: TRY004
    if "ops" in change:
        ops = validate_ops(change["ops"])
        return ops, [o.model_dump(exclude_none=True) for o in ops]
    if change.get("configs") is not None:
        from app.simulation.importers import parse_running_configs

        definition = parse_running_configs(str(change["configs"]), str(change.get("dialect") or "cisco_ios"))
        ops = derive_ops_from_definition(twin, definition)
        return ops, [o.model_dump(exclude_none=True) for o in ops]
    if change.get("csv") is not None:
        from app.simulation.importers import parse_csv_inventory

        definition = parse_csv_inventory(str(change["csv"]))
        ops = derive_ops_from_definition(twin, definition)
        return ops, [o.model_dump(exclude_none=True) for o in ops]
    raise ValueError("change must provide ops, configs, or csv")


def _paths(g, src: str, tgt: str, limit: int = MAX_PATHS) -> list[list[str]]:
    """Up to ``limit`` shortest simple paths, generated lazily (never enumerates all)."""
    if src not in g or tgt not in g:
        return []
    try:
        return [list(p) for p in itertools.islice(nx.shortest_simple_paths(g, src, tgt), limit)]
    except (nx.NetworkXNoPath, nx.NetworkXError):
        return []


def _new_paths(before_g, after_g, src: str, tgt: str) -> list[list[str]]:
    """Attack paths that exist only because of the change.

    A path is new iff it uses an edge that was not traversable at baseline.
    Comparing truncated path lists instead would flag old paths that merely
    moved into the visible window (e.g. after a link removal) as regressions.
    """
    new_edges = set(after_g.edges()) - set(before_g.edges())
    if not new_edges or src not in after_g or tgt not in after_g:
        return []
    # Necessary condition, exact and cheap: tail reachable from src, head reaches tgt.
    from_src = nx.descendants(after_g, src) | {src}
    to_tgt = nx.ancestors(after_g, tgt) | {tgt}
    candidates = {(u, v) for u, v in new_edges if u in from_src and v in to_tgt}
    if not candidates:
        return []
    found: list[list[str]] = []
    try:
        for p in itertools.islice(nx.shortest_simple_paths(after_g, src, tgt), NEW_PATH_SEARCH_CAP):
            if any(e in candidates for e in itertools.pairwise(p)):
                found.append(list(p))
                if len(found) >= MAX_PATHS:
                    break
    except (nx.NetworkXNoPath, nx.NetworkXError):
        pass
    if not found:
        # Search cap hit without a concrete simple path: report conservatively
        # as a possible route through the new edge rather than a silent PASS.
        u, v = min(candidates)
        found.append([src, "...", u, v, "...", tgt])
    return found


def _min_cut(twin: DigitalTwin, src: str, tgt: str) -> int | None:
    g = twin.live_graph(tgt)
    if src not in g or tgt not in g:
        return None
    try:
        return len(nx.minimum_edge_cut(g, src, tgt))
    except Exception:  # noqa: BLE001 - no path -> 0
        return 0


def run_preflight(twin: DigitalTwin, scenarios: list[dict], change) -> dict:
    """Replay ``change`` on a clone per scenario. Never mutates ``twin``."""
    ops, ops_dicts = resolve_change(twin, change)
    changed = apply_change(twin, ops)
    results = []
    for scenario in scenarios:
        src, tgt = scenario["source_asset"], scenario["target_asset"]
        before_g, after_g = twin.live_graph(tgt), changed.live_graph(tgt)
        before_paths = _paths(before_g, src, tgt)
        after_paths = _paths(after_g, src, tgt)
        new_paths = _new_paths(before_g, after_g, src, tgt)
        before_reach, after_reach = bool(before_paths), bool(after_paths)
        if new_paths or (after_reach and not before_reach):
            status = "REGRESSION"
        elif before_reach and not after_reach:
            status = "IMPROVED"
        elif before_reach and after_reach:
            status = "STILL_EXPOSED"
        else:
            status = "OK"
        results.append({
            "scenario_id": scenario["id"], "scenario_name": scenario.get("name", scenario["id"]),
            "source": src, "target": tgt, "status": status,
            "baseline_reachable": before_reach, "after_reachable": after_reach,
            "baseline_paths": before_paths, "after_paths": after_paths, "new_paths": new_paths,
            "min_cut_before": _min_cut(twin, src, tgt), "min_cut_after": _min_cut(changed, src, tgt),
        })
    verdict = "FAIL" if any(r["status"] == "REGRESSION" for r in results) else "PASS"
    return {"verdict": verdict, "results": results, "change_ops": ops_dicts}
