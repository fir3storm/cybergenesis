"""Adaptive red team: campaign planning over the twin's own directed graph.

Muse Spark plans a campaign (foothold / identity pivot / objective / typed steps);
the deterministic evaluate_campaign in the policy engine validates it hop-by-hop.
Rejected campaigns get one retry with the rejection reasons. Offline fallback is a
deterministic foothold/objective search, labelled mode=offline.
"""

import networkx as nx

from app.integrations.meta_client import meta_client
from app.policies.engine import evaluate_campaign
from app.schemas import CampaignPlan
from app.simulation.twin import ATTACK_STEP_TYPES, DigitalTwin

RED_TEAM_SYSTEM = (
    "You are the Red Team campaign planner in CYBERGENESIS, a defensive simulation on synthetic data only. "
    "Given topology, live states, containments, identities and crown jewels, plan ONE campaign. Allowed adaptations: "
    "a new foothold adjacent to compromised/suspicious assets, pivoting through a compromised synthetic identity, "
    "or switching to another crown-jewel objective. "
    f"Step types allowed ONLY: {sorted(ATTACK_STEP_TYPES)}. "
    "Return ONLY JSON {\"foothold\": str, \"pivot_identity\": str|null, \"objective\": str, "
    "\"steps\": [{\"type\": str, \"asset\": str, \"description\": str}], \"rationale\": str, \"confidence\": float}. "
    "Every consecutive pair of step assets must be connected in the topology, unless the hop uses the pivot identity. No commands or payloads."
)

HIGH_VALUE_TYPES = ("database", "file_server")
ENTRY_POINTS = ["internet", "employee-workstation", "admin-workstation", "web-server"]


def crown_jewels(twin: DigitalTwin, primary_target: str) -> list[str]:
    jewels = [a["id"] for a in twin.asset_defs if a["asset_type"] in HIGH_VALUE_TYPES]
    return list(dict.fromkeys([primary_target] + jewels))


def enumerate_paths(twin: DigitalTwin, src: str, tgt: str, cutoff: int = 7, limit: int = 6) -> list[list[str]]:
    g = twin.live_graph(tgt)  # shared helper: always agrees with find_path
    if src not in g or tgt not in g:
        return []
    try:
        paths = list(nx.all_simple_paths(g, src, tgt, cutoff=cutoff))
    except Exception:  # noqa: BLE001
        return []
    paths.sort(key=len)
    return paths[:limit]


def _steps_for_path(path: list[str]) -> list[dict]:
    return [{"type": "network_connection", "asset": a,
             "description": f"Red team traverses {a} (synthetic)"} for a in path]


def _offline_campaign(twin: DigitalTwin, src: str, tgt: str) -> CampaignPlan | None:
    """Deterministic search: footholds near compromised assets first, shortest path wins.
    Decoy assets are never named as footholds/objectives (red must not learn they are decoys)."""
    states = {a: s for a, s in twin.status.items() if a not in twin.decoys}
    near = [a for a, s in states.items() if s in ("compromised", "suspicious")]
    footholds = list(dict.fromkeys(near + ENTRY_POINTS))
    objectives = crown_jewels(twin, tgt)
    for objective in objectives:
        for foothold in footholds:
            if foothold == objective:
                continue
            paths = enumerate_paths(twin, foothold, objective)
            if paths:
                path = paths[0]
                return CampaignPlan(foothold=foothold, objective=objective, steps=_steps_for_path(path),
                                    rationale="shortest validated path from nearest foothold (deterministic red team)",
                                    confidence=0.75, mode="offline", path=path)
    # original objective, original source
    paths = enumerate_paths(twin, src, tgt)
    if paths:
        return CampaignPlan(foothold=src, objective=tgt, steps=_steps_for_path(paths[0]),
                            rationale="shortest validated path (deterministic red team)",
                            confidence=0.75, mode="offline", path=paths[0])
    return None


def find_new_objective(twin: DigitalTwin, current_src: str, current_tgt: str) -> tuple[str, str, list[str], str] | None:
    camp = _offline_campaign(twin, current_src, current_tgt)
    if camp is None or not camp.path:
        return None
    if camp.objective != current_tgt:
        kind = "stolen-identity pivot" if camp.pivot_identity else "new crown-jewel objective"
    elif camp.foothold != current_src:
        kind = "new foothold"
    else:
        return None
    return camp.foothold, camp.objective, camp.path, kind


async def plan_campaign(twin: DigitalTwin, src: str, tgt: str, run_id: str) -> CampaignPlan | None:
    """Live campaign with one policy-feedback retry; deterministic offline fallback."""
    d = twin.to_dict()
    context = (
        f"Topology (directed arcs): {[(c['source'], c['target']) for c in d['connections'] if c['traversable']]}. "
        f"Live states: {[(a['id'], a['status'], a['isolated']) for a in d['assets'] if not a.get('is_decoy')]}. "
        f"Active containments: {d['containment']}. Identities: {d['identities']}. "
        f"Crown jewels: {crown_jewels(twin, tgt)}. Preferred foothold area: {src}; preferred objective: {tgt}. "
        f"Currently reachable path foothold->objective: {twin.find_path(src, tgt)}."
    )
    feedback = ""
    for _attempt in range(2):
        try:
            data, _ = await meta_client.chat_json(RED_TEAM_SYSTEM, context + feedback, run_id)
            plan = CampaignPlan(**{**data, "mode": "live"})
            plan.path = [s.asset for s in plan.steps]
            verdict = evaluate_campaign(plan.model_dump(), twin)
            if verdict["approved"]:
                plan.path = verdict["path"]
                return plan
            feedback = (" Your campaign was REJECTED by the policy engine: " + "; ".join(verdict["reasons"])
                        + ". Plan a corrected campaign whose hops all exist in the topology (or use a compromised pivot identity).")
        except Exception:  # noqa: BLE001 - fall through to labelled offline search
            break
    offline = _offline_campaign(twin, src, tgt)
    if offline is not None:
        verdict = evaluate_campaign(offline.model_dump(), twin)
        if not verdict["approved"]:
            return None
        offline.path = verdict["path"]
    return offline


async def choose_path(paths: list[list[str]], run_id: str) -> tuple[list[str], str, str]:
    """Back-compat helper (deterministic shortest path)."""
    if not paths:
        return [], "offline", "no alternate path exists"
    return paths[0], "offline", "shortest validated path (deterministic red team)"
