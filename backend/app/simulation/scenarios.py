import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_SCEN_DIR = _ROOT / "scenarios"


def load_scenarios() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if _SCEN_DIR.exists():
        for p in sorted(_SCEN_DIR.glob("*.json")):
            data = json.loads(p.read_text(encoding="utf-8"))
            out[data["id"]] = data
    return out


SCENARIOS = load_scenarios()
