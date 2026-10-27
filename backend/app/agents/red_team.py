"""AI red team: campaign planning over the twin's real directed graph.

Paths are enumerated on twin.graph itself (same arcs find_path uses). When live,
Muse Spark plans a multi-step campaign (foothold -> pivots -> objective); the
engine validates every hop against the graph before anything is executed.
Red moves use allowlisted typed steps only and are policy-checked by the caller.
"""

import networkx as nx

from app.integrations.meta_client import meta_client
from app.simulation.twin import DigitalTwin

RED_TEAM_SYSTEM = (
    "You are the Red Team in CYBERGENESIS, a defensive simulation on synthetic data only. "
    "Plan a multi-step campaign from the given foothold to the objective using ONLY the listed validated paths. "
    "Return ONLY JSON {\"path_index\": int, \"campaign\": {\"foothold\": str, \"pivots\": [str], \"objective\": str, "
    "\"technique\": str}, \"rationale\": str}. No commands, no payloads."
)

HIGH_VALUE_TARGETS = ["database", "file-server", "identity-provider"]
ENTRY_POINTS = ["internet", "employee-workstation", "admin-workstation", "web-server"]


def _live_graph(twin: DigitalTwin) -> nx.DiGraph:
    g = nx.DiGraph()
    for u, v, data in twin.graph.edges(data=True):
        if data.get("traversable") and twin.dir_active.get((u, v), False):
            g.add_edge(u, v)
    for a in twin.assets_status_isolated():
        if a in g:
            g.remove_node(a)
    return g


def enumerate_paths(twin: DigitalTwin, src: str, tgt: str, cutoff: int = 6, limit: int = 6) -> list[list[str]]:
    g = _live_graph(twin)
    if src not in g or tgt not in g:
        return []
    try:
        paths = list(nx.all_simple_paths(g, src, tgt, cutoff=cutoff))
    except Exception:  # noqa: BLE001
        return []
    paths.sort(key=len)
    return paths[:limit]


def find_new_objective(twin: DigitalTwin, current_src: str, current_tgt: str) -> tuple[str, str, list[str], str] | None:
    """Change approach: new foothold and/or high-value target (incl. identity pivot)."""
    footholds: list[str] = []
    for a in twin.to_dict()["assets"]:
        if a["status"] in ("compromised", "suspicious"):
            footholds.append(a["id"])
    for e in ENTRY_POINTS + footholds:
        if e not in footholds:
            footholds.append(e)
    for tgt in HIGH_VALUE_TARGETS:
        if tgt == current_tgt and len(HIGH_VALUE_TARGETS) > 1:
            continue
        for src in footholds:
            if src == tgt:
                continue
            paths = enumerate_paths(twin, src, tgt)
            if paths:
                kind = "stolen-identity pivot" if src in ("admin-workstation",) or "identity-provider" in paths[0] else "new foothold"
                return src, tgt, paths[0], kind
    # same target, different foothold
    for src in footholds:
        if src != current_src:
            paths = enumerate_paths(twin, src, current_tgt)
            if paths:
                return src, current_tgt, paths[0], "new foothold"
    return None


async def plan_campaign(twin: DigitalTwin, src: str, tgt: str, paths: list[list[str]], run_id: str) -> dict:
    """Returns {path, campaign, mode, rationale}; campaign hops are validated against the graph."""
    if not paths:
        return {"path": [], "campaign": None, "mode": "offline", "rationale": "no validated path exists"}
    fallback = {"path": paths[0],
                "campaign": {"foothold": src, "pivots": paths[0][1:-1], "objective": tgt, "technique": "network_connection chain"},
                "mode": "offline", "rationale": "shortest validated path (deterministic campaign)"}
    if len(paths) == 1:
        return fallback
    try:
        listing = "\n".join(f"{i}: {' -> '.join(p)}" for i, p in enumerate(paths))
        data, _ = await meta_client.chat_json(
            RED_TEAM_SYSTEM,
            f"Foothold={src} Objective={tgt}. Validated paths:\n{listing}\nLive asset states: "
            + ", ".join(f"{a['id']}={a['status']}" for a in twin.to_dict()["assets"]), run_id)
        idx = int(data.get("path_index", 0))
        camp = data.get("campaign") or {}
        path = paths[idx] if 0 <= idx < len(paths) else paths[0]
        # validate the model's campaign against the real graph, hop by hop
        seq = [camp.get("foothold", path[0])] + list(camp.get("pivots", [])) + [camp.get("objective", path[-1])]
        g = _live_graph(twin)
        if seq[0] != path[0] or seq[-1] != path[-1] or any(not g.has_edge(seq[i], seq[i + 1]) for i in range(len(seq) - 1)):
            return {**fallback, "rationale": "model campaign failed graph validation; deterministic campaign used"}
        return {"path": path, "campaign": {"foothold": seq[0], "pivots": seq[1:-1], "objective": seq[-1],
                                           "technique": str(camp.get("technique", "network_connection chain"))[:80]},
                "mode": "live", "rationale": str(data.get("rationale", "model-planned campaign"))[:220]}
    except Exception:  # noqa: BLE001 - labelled deterministic fallback
        return fallback


async def choose_path(paths: list[list[str]], run_id: str) -> tuple[list[str], str, str]:
    """Back-compat wrapper around plan_campaign for callers that need a twin-free signature."""
    if not paths:
        return [], "offline", "no alternate path exists"
    return paths[0], "offline", "shortest alternate path (deterministic red team)"
