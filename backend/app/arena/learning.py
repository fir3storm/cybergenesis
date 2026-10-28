"""Arena B2: deterministic score memory — the self-learning layer.

Both sides remember what worked across matches:
  blue:<candidate label>  -> plays, blocks, total disrupted paths
  red:<path signature>    -> plays, reaches (objective survived the defense)

Learned choosers score options with a smoothed success rate (prior 1/2, so
unseen options stay explorable), minus a disruption cost for Blue. The AI
(B3) still picks among the same validated options; this memory biases the
shortlist and breaks ties, and persists to JSON so learning survives
restarts. Synthetic data only.
"""

import json
import os
import tempfile
from pathlib import Path

from app.agents.red_team import enumerate_paths, sort_campaign_paths
from app.simulation.candidates import evaluate_candidates, invasiveness
from app.simulation.twin import DigitalTwin


class ArenaMemory:
    def __init__(self, data: dict | None = None):
        self.data: dict = data or {"blue": {}, "red": {}, "matches": 0}

    def for_context(self, scenario_id: str, twin_id: str | None) -> "ArenaMemory":
        """Share a persisted bucket scoped to a scenario and twin, never global priors."""
        key = json.dumps([scenario_id, twin_id], separators=(",", ":"))
        bucket = self.data.setdefault("contexts", {}).setdefault(
            key, {"blue": {}, "red": {}, "matches": 0})
        return ArenaMemory(bucket)

    # --- recording -----------------------------------------------------
    def record_match(self, result: dict) -> None:
        self.data["matches"] = int(self.data.get("matches", 0)) + 1
        for r in result.get("rounds", []):
            label = r.get("blue_candidate")
            if label:
                b = self.data["blue"].setdefault(label, {"plays": 0, "blocks": 0, "disrupted": 0})
                b["plays"] += 1
                b["blocks"] += 0 if r.get("target_reachable_after") else 1
                b["disrupted"] += int(r.get("disrupted") or 0)
            path = r.get("red_path")
            if path:
                k = " > ".join(path)
                e = self.data["red"].setdefault(k, {"plays": 0, "reaches": 0})
                e["plays"] += 1
                e["reaches"] += int(not r["selected_path_blocked"]) if "selected_path_blocked" in r else int(bool(r.get("target_reachable_after")))

    # --- scoring -------------------------------------------------------
    @staticmethod
    def _rate(entry: dict | None, win_key: str) -> float:
        if not entry:
            return 0.5
        return (entry.get(win_key, 0) + 1) / (entry.get("plays", 0) + 2)

    def blue_rate(self, label: str) -> float:
        return self._rate(self.data["blue"].get(label), "blocks")

    def red_rate(self, path: list[str]) -> float:
        return self._rate(self.data["red"].get(" > ".join(path)), "reaches")

    # --- persistence ---------------------------------------------------
    def save(self, path: str | Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=destination.parent, prefix="arena-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(self.data, stream, indent=2)
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @classmethod
    def load(cls, path: str | Path) -> "ArenaMemory":
        p = Path(path)
        if not p.exists():
            return cls()
        return cls(json.loads(p.read_text(encoding="utf-8")))

    def summary(self) -> dict:
        return {"matches": self.data.get("matches", 0),
                "blue_learned": len(self.data.get("blue", {})),
                "red_learned": len(self.data.get("red", {})),
                "blue": self.data.get("blue", {}), "red": self.data.get("red", {})}


def learned_blue_chooser(memory: ArenaMemory):
    """Feasible candidate with the best learned block rate.

    Ranking (min over tuples): blockers first, then the best learned block
    rate (Beta-smoothed, so unseen options stay explorable), then the lowest
    average disruption, then the least invasive action set, then label.
    A fresh blocking candidate therefore beats a non-blocking one regardless
    of history — that is the whole point of a defense.
    """
    def choose(twin: DigitalTwin, baseline: DigitalTwin, scenario: dict, history: list[dict]) -> dict | None:
        proposal = scenario.get("expected_defense") or []
        cands = [c for c in evaluate_candidates(twin, baseline, scenario, [dict(a) for a in proposal]) if c.get("feasible")]
        if not cands:
            return None
        def score(c: dict) -> tuple:
            entry = memory.data["blue"].get(c["label"]) or {}
            plays = entry.get("plays", 0)
            avg_disrupted = (entry.get("disrupted", 0) / plays) if plays else (c.get("disrupted") or 0)
            return (not c.get("blocked"), -memory.blue_rate(c["label"]), avg_disrupted,
                    invasiveness(c.get("actions", [])), c["label"])
        return min(cands, key=score)
    return choose


def learned_red_chooser(memory: ArenaMemory):
    """Validated path with the best learned reach rate (weakest/shortest breaks ties)."""
    def choose(twin: DigitalTwin, scenario: dict, history: list[dict]) -> list[str] | None:
        paths = enumerate_paths(twin, scenario["source_asset"], scenario["target_asset"])
        if not paths:
            return None
        ranked = sort_campaign_paths(twin, paths)
        return min(ranked, key=lambda p: -memory.red_rate(p))
    return choose
