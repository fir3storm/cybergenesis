"""AI red team: after a defense, search for an alternate attack path (allowlisted steps only).

Path enumeration is deterministic (NetworkX). When live, Muse Spark only *chooses*
among the enumerated, already-validated paths; it cannot invent edges.
"""

import networkx as nx

from app.integrations.meta_client import meta_client
from app.simulation.twin import DigitalTwin

RED_TEAM_SYSTEM = (
    "You are the Red Team in CYBERGENESIS, a defensive simulation on synthetic data only. "
    "You are given a numbered list of validated alternate attack paths in a graph. "
    "Return ONLY JSON {\"path_index\": int, \"rationale\": str}. Choose the path you judge most viable. No commands."
)


def enumerate_paths(twin: DigitalTwin, src: str, tgt: str, cutoff: int = 6, limit: int = 6) -> list[list[str]]:
    g = nx.DiGraph()
    for c in twin.to_dict()["connections"]:
        if c["traversable"] and c["active"]:
            g.add_edge(c["source"], c["target"])
            g.add_edge(c["target"], c["source"])  # twin engine adds both arcs for traversable connections
    for a in twin.assets_status_isolated():
        if a in g:
            g.remove_node(a)
    if src not in g or tgt not in g:
        return []
    try:
        paths = list(nx.all_simple_paths(g, src, tgt, cutoff=cutoff))
    except Exception:  # noqa: BLE001
        return []
    paths.sort(key=len)
    return paths[:limit]


async def choose_path(paths: list[list[str]], run_id: str) -> tuple[list[str], str, str]:
    """Returns (path, mode, rationale). Offline/shortest fallback is labelled."""
    if not paths:
        return [], "offline", "no alternate path exists"
    if len(paths) == 1:
        return paths[0], "offline", "only one alternate path exists (deterministic choice)"
    try:
        listing = "\n".join(f"{i}: {' -> '.join(p)}" for i, p in enumerate(paths))
        data, _ = await meta_client.chat_json(RED_TEAM_SYSTEM, f"Validated alternate attack paths:\n{listing}", run_id)
        idx = int(data.get("path_index", 0))
        if 0 <= idx < len(paths):
            return paths[idx], "live", str(data.get("rationale", "model-selected path"))[:200]
    except Exception:  # noqa: BLE001 - labelled deterministic fallback
        pass
    return paths[0], "offline", "shortest alternate path (deterministic red team)"
