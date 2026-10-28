"""Held-out benchmark harness smoke test (small n, hermetic)."""

import os
import subprocess
import sys


def test_holdout_benchmark_script_runs():
    root = os.path.join(os.path.dirname(__file__), "..", "..")
    r = subprocess.run([sys.executable, os.path.join(root, "scripts", "holdout_benchmark.py"), "--n", "6"],
                       capture_output=True, text=True, cwd=root, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "deterministic" in r.stdout and "simulate" in r.stdout
