"""
validate_combat.py - phase-2c fire-combat gate validation.
Exercises fire/return-fire/morale/retreat/rally through the REAL gate,
then replays the whole log independently via verify_game.
Run: python games/austerlitz-gmt/validate_combat.py
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


def fresh(seed):
    live = tempfile.mkdtemp(prefix="aus_cmb_")
    g = NapoleonicGame(gamespec.load(HERE),
                       os.path.join(HERE, "scenario_northern_flank.json"),
                       live, seed=seed, command=False)   # mechanics harness
    return g, live


def by_slot(g, slot):
    for u in g.s["units"].values():
        if u["slot"] == slot:
            return u
    raise KeyError(slot)


print("== fire legality [8.1] ==")
g, live = fresh(5)
hus = by_slot(g, "10 Hus")
leg = by_slot(g, "2/17 Leg")
rus = by_slot(g, "3/Pskv")
r = g.propose("French", {"type": "fire", "unit": hus["pid"],
                         "target": rus["pid"]})
check("cavalry may not fire [8.1]", not r["legal"])
r = g.propose("French", {"type": "fire", "unit": leg["pid"],
                         "target": rus["pid"]})
check("infantry beyond range 1 may not fire [8.1.6]", not r["legal"])
art = by_slot(g, "a/V")     # unlimbered foot 8pdr at (59,15) facing NNE
far = by_slot(g, "G/Arkh")  # Russian at (68,13): range ~9, in arc?
r = g.propose("French", {"type": "fire", "unit": art["pid"],
                         "target": far["pid"]})
print("   (a/V vs G/Arkh:", r["reasons"] if not r["legal"] else "legal", ")")
lim = by_slot(g, "b/V")
g.submit("French", {"type": "change_formation", "unit": lim["pid"],
                    "to": "limbered"})
r = g.propose("French", {"type": "fire", "unit": lim["pid"],
                         "target": rus["pid"]})
check("limbered artillery may not fire [6.3.7]", not r["legal"])

print("== adjacent firefight with return fire [8.1.1/8.1.2] ==")
g2, live2 = fresh(9)
# march 2/17 Leg adjacent to the Russian line over two turns
leg = by_slot(g2, "2/17 Leg")
r = g2.submit("French", {"type": "move", "unit": leg["pid"],
                         "dest": [64, 10], "facing": 3})
check("approach move legal", r["verdict"]["legal"])
g2.submit("French", {"type": "end_turn"})
g2.submit("Allied", {"type": "end_turn"})
r = g2.submit("French", {"type": "move", "unit": leg["pid"],
                         "dest": [66, 10], "facing": 3})
check("moves into the enemy front-hex zone and STOPS there [5.1.3]",
      r["verdict"]["legal"])
tgt = by_slot(g2, "3/Pskv")   # at (67,10), line facing west
r = g2.submit("French", {"type": "fire", "unit": leg["pid"],
                         "target": tgt["pid"]})
check("adjacent offensive fire accepted", r["verdict"]["legal"])
check("defender got a return-fire window [8.1.2]",
      r["result"].get("pending_return") == tgt["pid"])
r = g2.submit("French", {"type": "end_turn"})
check("nothing else may happen while the window is open",
      not r["verdict"]["legal"])
r = g2.submit("Allied", {"type": "return_fire"})
check("return fire resolves", r["verdict"]["legal"])
res = r["result"]
check("both shots recorded (simultaneous) [8.1.2]",
      "offensive" in res and "return" in res)
check("effects landed on the ledger",
      any("sp_loss" in e or "morale_die" in e or "result" in e
          for e in res.get("effects", [])))
check("firer letter: legere C in line fired as B [8.1.8 adj]",
      res["offensive"]["letter"] == "B")
check("target class: Allied line = d [8.1.8]",
      res["offensive"]["class"] == "d")

print("== morale ladder / artillery morale [9.2/9.3] ==")
g3, live3 = fresh(1)
u = by_slot(g3, "2/Arkh")
out = {}
g3._morale_check(u, 9, out)     # +9 DRM forces a big failure
check("forced failure drops morale state",
      u["morale_state"] in ("shaken", "unsteady", "routed"))
if u["morale_state"] in ("unsteady", "routed"):
    check("unsteady/rout triggered a retreat [10.0]",
          any("retreat" in e for e in out["effects"]))
art = by_slot(g3, "a/B")
sp0 = art["sp"]
out = {}
g3._morale_check(art, 9, out)
check("artillery converts lost morale levels to SPs [9.3]",
      art["morale_state"] == "good" and art["sp"] < sp0)

print("== breakpoint [11.1] ==")
g4, live4 = fresh(2)
u = by_slot(g4, "1/40 Ln")     # 6 SP
out = {}
g4._lose_sp(u, 4, out)          # 4 > 6/2 -> breakpoint
check("cumulative losses over half strength = breakpoint",
      g4._at_breakpoint(u))
check("breakpoint adds +1 to morale checks [11.1.1]",
      1 in g4._morale_drms(u))

print("== rally phase [12.0/12.4] ==")
g5, live5 = fresh(3)
u = by_slot(g5, "G/Pskv")
u["morale_state"] = "shaken"    # synthetic state, then play the phase
g5.submit("French", {"type": "end_turn"})
r = g5.submit("Allied", {"type": "end_turn"})
check("rally phase opens when units are below good morale",
      g5.s["phase"] == "rally")
r = g5.submit("French", {"type": "rally", "unit": u["pid"]})
check("cannot rally the enemy's unit", not r["verdict"]["legal"])
g5.submit("French", {"type": "end_rally"})
r = g5.submit("Allied", {"type": "rally", "unit": u["pid"]})
check("owner may attempt rally [12.1]", r["verdict"]["legal"])
r = g5.submit("Allied", {"type": "end_rally"})
check("turn advances after rally + rout loss [12.4]",
      g5.s["turn"] == 2 and g5.s["phase"] == "movement")

print("== victory counting [A15.1] ==")
g6, live6 = fresh(4)
n = 0
for u in g6.s["units"].values():
    if u["side"] == "Allied" and u["arm"] != "leader" and n < 7:
        u["morale_state"] = "routed"
        n += 1
v = g6._victory_state()
check("7 Russian units routed = French victory [A15.1]",
      v["winner"] == "French")

print("== independent replay of the firefight game ==")
ok, msg = verify_game.verify(HERE, g2.log_path)
print(("  PASS  " if ok else "  FAIL  ") + "verify_game: " + msg)
if not ok:
    FAILS.append("replay")

for d in (live, live2, live3, live4, live5, live6):
    shutil.rmtree(d, ignore_errors=True)
print()
if FAILS:
    print(f"FAILED: {len(FAILS)}")
    for x in FAILS:
        print("  -", x)
    sys.exit(1)
print("ALL COMBAT CHECKS PASS")
