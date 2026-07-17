"""
validate_movement.py - plays a multi-turn scripted sequence through the
Tier-1 gate (moves, formation changes, special moves, rejections, dice)
and then hands the log to engine/verify_game.py for a full independent
replay: every verdict, every die, every state hash.
Run: python games/austerlitz-gmt/validate_movement.py
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "engine"))
import gamespec
import verify_game
from napoleonic import NapoleonicGame

FAILS = []


def check(label, ok):
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILS.append(label)


def by_slot(g, slot):
    for u in g.s["units"].values():
        if u["slot"] == slot:
            return u
    raise KeyError(slot)


live = tempfile.mkdtemp(prefix="aus_move_")
game = gamespec.load(HERE)
g = NapoleonicGame(game, os.path.join(HERE,
                   "scenario_northern_flank.json"), live, seed=42,
                   command=False)   # mechanics harness: pre-command flow

acted = 0
# --- French turn 1: advance the line, probe some rejections
for slot, action in [
    ("2/17 Leg", {"type": "move", "dest": [63, 9], "facing": 3}),
    ("1/34 Ln", {"type": "move", "dest": [63, 14], "facing": 3}),
    ("22 CaC", {"type": "move", "dest": [64, 7], "facing": 3}),
    ("10 Hus", {"type": "move", "dest": [65, 3], "facing": 3}),
    ("a/V", {"type": "change_formation", "to": "limbered"}),
    ("1/40 Ln", {"type": "about_face"}),
    ("2/40 Ln", {"type": "reverse", "dest": [61, 10]}),
]:
    u = by_slot(g, slot)
    action = dict(action, unit=u["pid"])
    r = g.submit("French", action)
    acted += 1
    check(f"French {slot} {action['type']} -> "
          f"{'legal' if r['verdict']['legal'] else 'REJECTED'}",
          r["verdict"]["legal"])
# deliberate illegal proposals (must be rejected AND logged)
u = by_slot(g, "1/64 Ln")
r = g.submit("French", {"type": "move", "unit": u["pid"],
                        "dest": [40, 25], "facing": 3})
check("teleport across the map rejected (beyond MA)",
      not r["verdict"]["legal"])
r = g.submit("Allied", {"type": "move",
                        "unit": by_slot(g, "G/Pskv")["pid"],
                        "dest": [66, 12], "facing": 9})
check("Allied move on French activation rejected", not r["verdict"]["legal"])
g.submit("French", {"type": "end_turn"})

# --- Allied turn 1
u = by_slot(g, "G/Arkh")     # at (68,13) facing W: both front hexes hold
r = g.submit("Allied", {"type": "move", "unit": u["pid"],
                        "dest": [67, 13], "facing": 9})
check("advance into a friendly line at the 8-SP cap rejected [7.1]",
      not r["verdict"]["legal"])
for slot, action in [
    ("G/O.Ing", {"type": "move", "dest": [66, 15], "facing": 9}),
    ("3/Pskv", {"type": "move", "dest": [66, 10], "facing": 9}),
    ("2/O.Ing", {"type": "slide", "dest": [67, 13]}),
]:
    u = by_slot(g, slot)
    action = dict(action, unit=u["pid"])
    r = g.submit("Allied", action)
    ok = r["verdict"]["legal"]
    # 2/O.Ing slide target (67,13) holds 3/O.Ing -> expect REJECTION
    if slot == "2/O.Ing":
        check("slide into an occupied flank hex rejected [6.3.1]", not ok)
    else:
        check(f"Allied {slot} {action['type']} legal", ok)
g.submit("Allied", {"type": "end_turn"})
check("turn advanced to 2 after both sides", g.s["turn"] == 2)
check("moved list reset for the new turn", g.s["moved"] == [])

# --- turn 2: march French infantry eastwards in column via the road
u = by_slot(g, "2/88 Ln")
r = g.submit("French", {"type": "change_formation", "unit": u["pid"],
                        "to": "column"})
check("2/88 Ln forms column", r["verdict"]["legal"])
g.submit("French", {"type": "end_turn"})
g.submit("Allied", {"type": "end_turn"})
check("turn advanced to 3", g.s["turn"] == 3)

# --- independent replay
ok, msg = verify_game.verify(HERE, g.log_path)
print(("  PASS  " if ok else "  FAIL  ") + "verify_game replay: " + msg)
if not ok:
    FAILS.append("replay")

shutil.rmtree(live, ignore_errors=True)
print()
if FAILS:
    print(f"FAILED: {len(FAILS)}")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("ALL MOVEMENT CHECKS PASS")
