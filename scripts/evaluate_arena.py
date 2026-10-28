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
    args = parser.parse_args()
    if not args.live:
        os.environ['OFFLINE_MODE'] = 'true'
    from app.arena.evaluation import evaluate_strategies
    report = asyncio.run(evaluate_strategies(args.cases, args.train, args.seed, args.live))
    path = ROOT / 'docs' / 'arena-evaluation.json'
    path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report['summary'], indent=2))
    print(f'Report: {path}')


if __name__ == '__main__':
    main()
