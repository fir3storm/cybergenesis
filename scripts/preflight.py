"""Attack-path regression preflight CLI.

Online:  python scripts/preflight.py --api http://localhost:8000 --twin <twin-id> --change change.json
Offline: python scripts/preflight.py --offline --twin twin.json --change change.json [--scenarios scenarios.json]

Exit codes: 0 = PASS, 1 = FAIL (regression), 2 = error.
Deterministic only; no LLM.
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _print_table(result: dict) -> None:
    print(f"Verdict: {result['verdict']}")
    if result.get("change_ops") is not None:
        print(f"Change ops ({len(result['change_ops'])}): {json.dumps(result['change_ops'])}")
    print(f"{'scenario':<28} {'status':<15} {'before':<8} {'after':<8} {'cut b/a':<9} new paths")
    for r in result["results"]:
        cuts = f"{r.get('min_cut_before')}/{r.get('min_cut_after')}"
        newp = "; ".join("->".join(p) for p in r.get("new_paths", [])) or "-"
        print(f"{r['scenario_id']:<28} {r['status']:<15} {r['baseline_reachable']!s:<8} "
              f"{r['after_reachable']!s:<8} {cuts:<9} {newp}")
        if r["status"] == "REGRESSION":
            for p in r.get("new_paths", []):
                print(f"  REGRESSION new path: {' -> '.join(p)}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Attack-path regression preflight")
    ap.add_argument("--api", default=None, help="backend base URL (online mode)")
    ap.add_argument("--twin", required=True, help="twin id (online) or twin JSON file (offline)")
    ap.add_argument("--change", required=True, help="change JSON file")
    ap.add_argument("--offline", action="store_true", help="load twin JSON directly, no server")
    ap.add_argument("--scenarios", default=None, help="offline: JSON list of scenario objects")
    args = ap.parse_args()

    try:
        change = json.loads(Path(args.change).read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"error: cannot read change file: {e}", file=sys.stderr)
        return 2

    if args.offline:
        try:
            from app.simulation.preflight import run_preflight
            from app.simulation.scenarios import SCENARIOS
            from app.simulation.twin import DigitalTwin

            twin_data = json.loads(Path(args.twin).read_text(encoding="utf-8"))
            assets = twin_data.get("assets") or []
            connections = twin_data.get("connections") or []
            twin = DigitalTwin.from_dict(assets, connections)
            if args.scenarios:
                scenarios = json.loads(Path(args.scenarios).read_text(encoding="utf-8"))
            else:
                ids = set(twin.asset_ids())
                scenarios = [{**s, "id": sid} for sid, s in SCENARIOS.items()
                             if s.get("source_asset") in ids and s.get("target_asset") in ids
                             and s.get("verification_kind", "reachability") == "reachability"]
            result = run_preflight(twin, scenarios, change)
        except Exception as e:  # noqa: BLE001
            print(f"error: {e}", file=sys.stderr)
            return 2
    else:
        if not args.api:
            print("error: --api is required unless --offline is given", file=sys.stderr)
            return 2
        try:
            req = urllib.request.Request(
                f"{args.api.rstrip('/')}/api/twins/{args.twin}/preflight",
                data=json.dumps({"change": change}).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
        except Exception as e:  # noqa: BLE001
            print(f"error: {e}", file=sys.stderr)
            return 2

    _print_table(result)
    print("PASS" if result["verdict"] == "PASS" else "FAIL")
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
