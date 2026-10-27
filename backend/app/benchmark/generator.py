"""Seeded benchmark generator: random layered twins (8-20 assets) + reachable scenarios."""

import random
from itertools import pairwise

from app.simulation.twin import DigitalTwin

LAYERS = [
    ("edge", ["internet", "firewall"], "gateway"),
    ("dmz", ["web-a", "web-b"], "web_server"),
    ("app", ["app-a", "app-b", "app-c"], "app_server"),
    ("data", ["db-main", "files-a", "db-replica"], "database"),
    ("endpoints", ["ws-a", "ws-b", "admin-a", "ws-c"], "workstation"),
]


def generate_pair(rng: random.Random, idx: int) -> tuple[list[dict], list[dict], dict]:
    assets: list[dict] = []
    by_layer: list[list[str]] = []
    total = 0
    for li, (zone, pool, atype) in enumerate(LAYERS):
        take = rng.randint(1, min(len(pool), 2 if li in (0, 1) else 3))
        names = pool[:take]
        layer_ids = []
        for n in names:
            aid = f"{n}-{idx}" if total + 1 > 12 else n
            assets.append({"id": aid, "name": aid, "asset_type": atype, "zone": zone,
                           "pos": [li * 3.5 - 7, 1, (len(layer_ids) - 1) * 2.2],
                           "vulnerabilities": rng.choice([[], ["legacy_unpatched"], ["exposed_service"]])})
            layer_ids.append(aid)
            total += 1
        by_layer.append(layer_ids)
    if rng.random() < 0.7:
        assets.append({"id": f"idp-{idx}", "name": "IdP", "asset_type": "identity", "zone": "identity",
                       "pos": [3, 2.5, 3], "vulnerabilities": []})
    conns: list[dict] = []
    for li in range(len(by_layer) - 1):
        for a in by_layer[li]:
            for b in by_layer[li + 1]:
                if rng.random() < 0.65:
                    conns.append({"source": a, "target": b, "traversable": True, "types": ["network"]})
    src = by_layer[0][0]
    data_ids = [a["id"] for a in assets if a["asset_type"] == "database"] or by_layer[3]
    tgt = data_ids[0]
    twin = DigitalTwin.from_dict(assets, conns)
    if not twin.reachable(src, tgt):  # guarantee baseline reachability with a spine
        spine = [by_layer[i][0] for i in range(4)]
        for a, b in pairwise(spine):
            if not any({c["source"], c["target"]} == {a, b} for c in conns):
                conns.append({"source": a, "target": b, "traversable": True, "types": ["network"]})
    scenario = {"id": f"gen-{idx}", "name": f"Generated Pair {idx}", "source_asset": src, "target_asset": tgt, "verification_kind": "reachability",
                "objectives": ["reach_target"], "invariant": f"{src} cannot reach {tgt}",
                "attack_steps": [{"type": "network_connection", "asset": src, "description": "generated attack"}],
                "expected_defense": [{"action_type": "isolate_asset", "asset_id": src, "params": {}}]}
    return assets, conns, scenario
