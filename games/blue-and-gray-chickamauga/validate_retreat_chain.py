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

SWAP = None
with tempfile.TemporaryDirectory() as tmp:
    def U5(uid, slot, side, c, r):
        return {"id": uid, "slot": slot, "side": side, "hex": [c, r],
                "str": max(G.stats(slot)[0], G.stats(slot)[1]), "cls": "inf"}
    scen = {
        "name": "swap-test-1",
        "game": {"turns": 1, "first_player": "Union", "night_turns": [],
                 "turn_labels": ["GT 1"]},
        "units": [
            U5("A", "Wilder c", "Union", 21, 22),
            U5("d1", "Fulton c", "Confederate", 22, 23),
            U5("d2", "Strahl c", "Confederate", 22, 23),
            U5("R", "Russell c", "Confederate", 22, 22),
            U5("e1", "1/1/XIV c", "Union", 21, 25),
            U5("e2", "2/1/XIV c", "Union", 24, 23),
            U5("e3", "3/1/XIV c", "Union", 20, 23),
            U5("e4", "1/3/XIV c", "Union", 24, 22),
        ],
        "reserve": [],
        "vp": {"per_enemy_csp_eliminated": 1,
               "exit_per_csp": {"Union": 1, "Confederate": 10},
               "confederate_train_fail": 10, "occupation": {},
               "start_occupation": {}},
        "rules_scope": {"enforced": ["t"], "enforced_combat": ["t"], "umpired": []}}
    spath = os.path.join(tmp, "scenario_swap.json")
    json.dump(scen, open(spath, "w"), indent=1)
    for seed in (3, 5, 7, 11, 13):
        bg = bluegray.BlueGrayGame(G, spath, tmp, seed=seed)
        bg.submit("Union", {"type": "end_movement"})
        r = bg.submit("Union", {"type": "battle", "attackers": ["A"],
                                "defenders": ["R"]})
        if not r["verdict"]["legal"] or r["result"][0]["result"] != "Dr":
            continue
        oh, dh = bg._retreat_hexes(bg.unit("R"))
        if oh or dh != [(22, 23)]:
            continue
        r = bg.submit("Confederate", {"type": "retreat", "unit": "R",
                                      "dest": [22, 23]})
        if not r["verdict"]["legal"]:
            continue
        if bg.s["pending"]["units"] != ["d1"]:
            continue
        oh2, dh2 = bg._retreat_hexes(bg.unit("d1"))
        if oh2 or dh2:
            continue
        SWAP = (bg, seed)
        break
    check(SWAP is not None, "staged the displacement-that-would-eliminate [7.82]")
    if SWAP:
        bg, seed = SWAP
        r = bg.submit("Confederate", {"type": "retreat", "unit": "d1", "dest": None})
        check(r["verdict"]["legal"], "the displaced unit's no-retreat resolution is legal [7.72/7.82]")
        check("R" not in bg.s["units"] and "R" in bg.s["dead"],
              f"the RETREATING unit is eliminated instead [7.82] "
              f"(dead={bg.s['dead']})")
        check("d1" in bg.s["units"] and (bg.s["units"]["d1"]["col"],
                                         bg.s["units"]["d1"]["row"]) == (22, 23),
              "the displaced unit lives, on its original hex [7.82]")
        check("d2" in bg.s["units"] and (bg.s["units"]["d2"]["col"],
                                         bg.s["units"]["d2"]["row"]) == (22, 23),
              "the stack mate is untouched [7.8]")
        check(bg.s["vp"]["Union"] == 2,
              f"the eliminator scores the retreater's CSP [17.11] (got {bg.s['vp']})")
        while bg.s["pending"]:
            item = ai_bluegray._resolve_pending(bg)
            if item is None:
                break
            side, action, desc = item
            r = bg.submit(side, action)
            check(r["verdict"]["legal"],
                  f"swap-chain resolution accepted ({desc[:50]})")
        check(bg.s["pending"] is None, "the swap chain terminated")

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
