"""Proof-carrying optimality: Menger / max-flow-min-cut duality proofs.

By Menger's theorem the maximum number k of edge-disjoint source->target
paths equals the size of a minimum edge cut. Publishing k edge-disjoint
witness paths therefore proves no defense can cut fewer than k edges, and
publishing the defense's removed-edge set C plus a check that the source
cannot reach the target without C proves C is a cut. If |C| == k the defense
is provably minimal; otherwise ``gap = |C| - k`` is the proven overpayment.

All graph semantics reuse ``DigitalTwin.live_graph(target)`` exactly as
``verifier.py`` / ``candidates.py`` do (directed, vulnerability-gated), so the
proof talks about the same graph the verifier replayed. This module is pure
and deterministic: no LLM, no database, networkx only.

Relevant-cut choice: ``defense_cut`` contains only removed edges that lie on
at least one baseline source->target path. An edge counts as "on a path" when
its tail is reachable from the source and its head can reach the target in
the baseline graph. Edges removed for unrelated reasons (e.g. isolating an
asset off the attack path) must not inflate the optimality gap, so they are
excluded from the cut and from the gap computation.
"""

import hashlib
import itertools
import json

import networkx as nx


def _canonical_edges(edges) -> list[list[str]]:
    return sorted([list(e) for e in edges])


def _graph_hash(graph_edges) -> str:
    blob = json.dumps(graph_edges, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def attack_graph_edges(twin, scenario) -> list[list[str]]:
    """Sorted traversable directed edges of the baseline live graph."""
    g = twin.live_graph(scenario["target_asset"])
    return _canonical_edges(g.edges())


def removed_edges(baseline_twin, final_twin, scenario) -> list[list[str]]:
    """Sorted edges traversable in baseline but not in final.

    Captures isolate/block/patch/disable uniformly, because every defense
    ultimately removes arcs from (or gates hops out of) the live graph.
    """
    base = {tuple(e) for e in attack_graph_edges(baseline_twin, scenario)}
    fin = {tuple(e) for e in attack_graph_edges(final_twin, scenario)}
    return _canonical_edges(base - fin)


def disjoint_paths_witness(edges, src, tgt) -> list[list[str]]:
    """Edge-disjoint src->tgt paths over a DiGraph built from ``edges``."""
    g = nx.DiGraph()
    g.add_edges_from([tuple(e) for e in edges])
    if src not in g or tgt not in g or src == tgt:
        return []
    try:
        paths = list(nx.edge_disjoint_paths(g, src, tgt))
    except (nx.NetworkXNoPath, nx.NetworkXError):
        return []
    return [list(p) for p in paths]


def _edges_on_some_path(g, src, tgt, cap: int = 2000) -> set:
    """Edges lying on at least one simple src->tgt path (enumerated, capped).

    Simple-path membership matters on the bidirected live graph: a reverse
    arc such as a->src lies on a src->tgt walk but on no *simple* path, so a
    plain reachability test would wrongly count it as relevant.
    """
    on_path: set = set()
    if src not in g or tgt not in g:
        return on_path
    try:
        for i, path in enumerate(nx.all_simple_paths(g, src, tgt)):
            if i >= cap:
                break
            on_path.update(itertools.pairwise(path))
    except (nx.NetworkXNoPath, nx.NetworkXError):
        pass
    return on_path


def build_optimality_proof(baseline_twin, final_twin, scenario) -> dict:
    """Build the optimality proof for a defense (see module docstring for the
    relevant-cut choice: only removed edges on some baseline src->tgt path
    count toward ``defense_cut`` / the gap)."""
    src, tgt = scenario["source_asset"], scenario["target_asset"]
    graph_edges = attack_graph_edges(baseline_twin, scenario)
    removed = removed_edges(baseline_twin, final_twin, scenario)
    g = nx.DiGraph()
    g.add_edges_from([tuple(e) for e in graph_edges])

    witness = disjoint_paths_witness(graph_edges, src, tgt)
    k = len(witness)

    if k == 0:
        return {"version": 1, "source": src, "target": tgt, "graph_edges": graph_edges,
                "graph_sha256": _graph_hash(graph_edges), "witness_paths": [],
                "lower_bound": 0, "defense_cut": [], "defense_cut_size": 0,
                "is_cut": True, "optimality_gap": None, "verdict": "NO_PATH_AT_BASELINE"}

    on_path = _edges_on_some_path(g, src, tgt)
    relevant = [e for e in removed if tuple(e) in on_path]

    def _cuts(edges) -> bool:
        cut_set = {tuple(e) for e in edges}
        remaining = nx.DiGraph()
        remaining.add_edges_from([tuple(e) for e in graph_edges if tuple(e) not in cut_set])
        return not (src in remaining and tgt in remaining and nx.has_path(remaining, src, tgt))

    is_cut = _cuts(relevant)
    if not is_cut and _cuts(removed):
        # the capped simple-path search missed a relevant edge on a large
        # graph: certify the full removed set instead. That can only overstate
        # the gap, never report a real cut as NOT_A_CUT.
        relevant, is_cut = removed, True

    if not is_cut:
        gap, verdict = None, "NOT_A_CUT"
    elif len(relevant) == k:
        gap, verdict = 0, "OPTIMAL"
    else:
        gap, verdict = len(relevant) - k, "SUBOPTIMAL"

    return {"version": 1, "source": src, "target": tgt, "graph_edges": graph_edges,
            "graph_sha256": _graph_hash(graph_edges), "witness_paths": witness,
            "lower_bound": k, "defense_cut": relevant, "defense_cut_size": len(relevant),
            "is_cut": is_cut, "optimality_gap": gap, "verdict": verdict}


def check_optimality_proof(proof) -> tuple[bool, list[str]]:
    """Third-party check using ONLY the proof (nothing recomputed from a twin).

    Recomputes: graph hash, witness validity + pairwise edge-disjointness,
    cut validity (no src->tgt path after removing defense_cut), and
    lower_bound / gap / verdict consistency.
    """
    reasons: list[str] = []
    if not isinstance(proof, dict):
        return False, ["proof is not an object"]
    for field in ("version", "source", "target", "graph_edges", "graph_sha256",
                  "witness_paths", "lower_bound", "defense_cut", "defense_cut_size",
                  "is_cut", "optimality_gap", "verdict"):
        if field not in proof:
            reasons.append(f"proof missing field: {field}")
    if reasons:
        return False, reasons
    if proof["version"] != 1:
        reasons.append(f"unsupported proof version: {proof['version']}")

    src, tgt = proof["source"], proof["target"]
    graph_edges = [list(e) for e in proof["graph_edges"]]
    edge_set = {tuple(e) for e in graph_edges}
    if len(edge_set) != len(graph_edges):
        reasons.append("graph_edges contains duplicate edges")
    if graph_edges != sorted(graph_edges):
        reasons.append("graph_edges is not sorted")

    if _graph_hash(graph_edges) != proof["graph_sha256"]:
        reasons.append("graph_sha256 mismatch (graph_edges tampered)")

    witness = [list(p) for p in proof["witness_paths"]]
    if proof["lower_bound"] != len(witness):
        reasons.append(f"lower_bound {proof['lower_bound']} != number of witness paths {len(witness)}")

    used: set = set()
    for i, path in enumerate(witness):
        if not path or path[0] != src or path[-1] != tgt:
            reasons.append(f"witness path {i} does not run {src}->{tgt}")
            continue
        for a, b in itertools.pairwise(path):
            if (a, b) not in edge_set:
                reasons.append(f"witness path {i} uses edge {a}->{b} not in graph_edges")
            if (a, b) in used:
                reasons.append(f"witness paths are not edge-disjoint: edge {a}->{b} reused")
            used.add((a, b))

    cut = [list(e) for e in proof["defense_cut"]]
    cut_set = {tuple(e) for e in cut}
    if proof["defense_cut_size"] != len(cut):
        reasons.append(f"defense_cut_size {proof['defense_cut_size']} != len(defense_cut) {len(cut)}")
    for a, b in cut:
        if (a, b) not in edge_set:
            reasons.append(f"defense_cut edge {a}->{b} not in graph_edges")

    g = nx.DiGraph()
    g.add_nodes_from([src, tgt])
    g.add_edges_from([tuple(e) for e in graph_edges if tuple(e) not in cut_set])
    has_path = src in g and tgt in g and nx.has_path(g, src, tgt)
    is_cut = not has_path
    if bool(proof["is_cut"]) != is_cut:
        reasons.append(f"is_cut claim {proof['is_cut']} disagrees with recomputation (path remains: {has_path})")

    k = len(witness)
    verdict = proof["verdict"]
    gap = proof["optimality_gap"]
    if verdict == "NO_PATH_AT_BASELINE":
        base = nx.DiGraph()
        base.add_nodes_from([src, tgt])
        base.add_edges_from([tuple(e) for e in graph_edges])
        if nx.has_path(base, src, tgt):
            reasons.append("verdict NO_PATH_AT_BASELINE but graph_edges contain a source->target path")
    if k == 0:
        if verdict != "NO_PATH_AT_BASELINE":
            reasons.append(f"verdict {verdict} inconsistent: no witness paths but verdict is not NO_PATH_AT_BASELINE")
        if gap is not None:
            reasons.append("optimality_gap must be null when there is no baseline path")
    elif not is_cut:
        if verdict != "NOT_A_CUT":
            reasons.append(f"verdict {verdict} inconsistent: defense_cut is not a cut")
        if gap is not None:
            reasons.append("optimality_gap must be null when defense is not a cut")
    else:
        expected_gap = len(cut) - k
        if gap != expected_gap:
            reasons.append(f"optimality_gap {gap} != defense_cut_size - lower_bound ({expected_gap})")
        expected_verdict = "OPTIMAL" if expected_gap == 0 else "SUBOPTIMAL"
        if verdict != expected_verdict:
            reasons.append(f"verdict {verdict} inconsistent: expected {expected_verdict}")

    return (not reasons), reasons
