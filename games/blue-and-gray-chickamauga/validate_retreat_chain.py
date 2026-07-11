"""Regression: displacement-retreat chains terminate (7.81/7.82).

Found 2026-07-11 during interactive LLM-vs-policy play: a tightly packed
defensive pocket produced an INFINITE displacement chain - units bouncing
between two full hexes, each retreat legally displacing the next occupant,
14,000+ log entries before the driver gave up. Classification: OUR bug
(spec #21) - the gate permitted a chain that can never reach an open hex.
Printed rule [7.81]: a displacement chain must terminate; a chain that
ends in elimination eliminates rather than recursing. Fix: within one
battle's pending retreat, a unit that has already retreated (the chain
list) cannot be displaced again; a full stack of chain members is not a
retreat path, so the existing no-hex-open elimination [7.72] terminates
the resolution.

Fixture: the exact stuck state, captured live (test_fixtures/
retreat_cycle_state.json, pending retreat mid-cycle).

Run:  python games/blue-and-gray-chickamauga/validate_retreat_chain.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..")))
from engine import gamespec, bluegray, ai_bluegray  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
G = gamespec.load(HERE)
SCEN = os.path.join(HERE, "scenario_chickamauga.json")
FIX = os.path.join(HERE, "test_fixtures", "retreat_cycle_state.json")

fails = []


def check(cond, what):
    if not cond:
        fails.append(what)
    print(("PASS " if cond else "FAIL ") + what)


with tempfile.TemporaryDirectory() as tmp:
    bg = bluegray.BlueGrayGame(G, SCEN, tmp, seed=1)
    bg.s = json.load(open(FIX, encoding="utf-8"))
    n_units_before = len(bg.s["units"])
    check(bg.s["pending"] and bg.s["pending"]["awaiting"] == "retreat",
          "fixture reproduces the mid-cycle pending retreat")

    # resolve the pending exactly as the AI-vs-AI driver does; before the
    # fix this loop never emptied the queue (units re-displaced forever)
    steps = 0
    CAP = 60
    while bg.s["pending"] and steps < CAP:
        item = ai_bluegray._resolve_pending(bg)
        if item is None:
            break
        side, action, desc = item
        r = bg.submit(side, action)
        check(r["verdict"]["legal"],
              f"step {steps}: resolver proposal accepted ({desc[:60]})") \
            if not r["verdict"]["legal"] else None
        steps += 1

    check(bg.s["pending"] is None or bg.s["pending"]["awaiting"] != "retreat",
          f"displacement chain TERMINATED in {steps} steps (cap {CAP}; "
          f"pre-fix this ran forever)")
    n_units_after = len(bg.s["units"])
    print(f"  chain resolution: {steps} steps, "
          f"{n_units_before - n_units_after} unit(s) eliminated "
          f"[7.72/7.81], vp={bg.s['vp']}")
    check(steps < CAP, "resolution well under the step cap")

# and the fix must not disturb normal play: the full seed-1 policy game
# replays to the same final state as before the change
with tempfile.TemporaryDirectory() as tmp:
    bg = bluegray.BlueGrayGame(G, SCEN, tmp, seed=1)
    ai_bluegray.play_game(bg)
    check(bg.s["over"] and bg.s["vp"] == {"Union": 33, "Confederate": 123},
          f"seed-1 policy campaign unchanged by the fix "
          f"(vp={bg.s['vp']}, expected Union 33 / Confederate 123)")

print()
if fails:
    print(f"{len(fails)} FAILURES")
    sys.exit(1)
print("ALL PASS")
