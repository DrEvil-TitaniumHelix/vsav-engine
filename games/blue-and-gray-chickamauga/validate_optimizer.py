"""Spec #22 plumbing evidence: the strategy family + tournament optimizer
play complete gate-checked campaigns and evolve deterministically.

Checks: a tiny serial run (pop 4, 1 generation, 4-GT games) completes,
plays every scheduled game, writes status/checkpoint, and the baseline
theta reproduces policy-comparable play (game completes, VP recorded).

Run:  python games/blue-and-gray-chickamauga/validate_optimizer.py
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "engine"))

fails = []


def check(cond, what):
    if not cond:
        fails.append(what)
    print(("PASS " if cond else "FAIL ") + what)


# 1. one strategy-vs-baseline campaign through the gate, full length
import optimize  # noqa: E402
import strategy_bg  # noqa: E402

res = optimize.play_one((HERE, strategy_bg.baseline(), None, 7, 4))
check(res["vp"] and "winner" in res,
      f"strategy-vs-policy campaign completes (vp={res['vp']})")

# 2. tiny optimizer run end-to-end
with tempfile.TemporaryDirectory() as out:
    p = subprocess.run(
        [sys.executable, os.path.join(ROOT, "engine", "optimize.py"),
         "--game", HERE, "--out", out, "--pop", "4", "--gens", "1",
         "--procs", "1", "--peers", "1", "--max-gts", "4",
         "--unbeaten", "99", "--seeds-per-gen", "1"],
        capture_output=True, text=True, timeout=600)
    check(p.returncode == 0, "optimizer generation ran clean"
          + ("" if p.returncode == 0 else f" - {p.stderr[-300:]}"))
    status = json.load(open(os.path.join(out, "status.json"), encoding="utf-8"))
    check(status["games_played"] >= 20,
          f"tournament played its schedule ({status['games_played']} games)")
    check(os.path.exists(os.path.join(out, "checkpoint.json")),
          "checkpoint written (run is resumable)")
    check("champion" in status and "garrison_per_10vp" in status["champion"],
          "champion genome recorded in status")

print()
if fails:
    print(f"{len(fails)} FAILURES")
    sys.exit(1)
print("ALL PASS")
