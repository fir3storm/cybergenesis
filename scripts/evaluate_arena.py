"""Run paired arena evaluation; --live explicitly enables provider calls."""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cases', type=int, default=5)
    parser.add_argument('--train', type=int, default=5)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--output', type=Path, help='Report path (live runs default to a separate report)')
    args = parser.parse_args()
    if args.output:
        args.output = args.output.resolve()
    if not args.live:
        os.environ['OFFLINE_MODE'] = 'true'
    # Match the application's local launch path so backend/.env and saved
    # provider settings are found even when this CLI is run at repo root.
    os.chdir(ROOT / 'backend')
    from app.arena.evaluation import evaluate_strategies
    report = asyncio.run(evaluate_strategies(args.cases, args.train, args.seed, args.live))
    path = args.output or ROOT / 'docs' / ('arena-evaluation-live.json' if args.live else 'arena-evaluation.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report['summary'], indent=2))
    print(f'Report: {path}')
    # Keep fallback evidence, but do not let a failed provider look like a
    # successful live evaluation in a shell/CI pipeline.
    return 1 if args.live and any(row['provider_failed'] for row in report['cases']) else 0


if __name__ == '__main__':
    raise SystemExit(main())
