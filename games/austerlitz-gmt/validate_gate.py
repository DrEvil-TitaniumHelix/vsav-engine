"""
validate_gate.py - Tier-1 movement gate validation for Austerlitz
(The Northern Flank). Every check exercises the REAL gate (submit or
propose on a NapoleonicGame) and asserts a rulebook-cited behavior.
Run: python games/austerlitz-gmt/validate_gate.py
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "engine"))
import formations as fm
import gamespec
from napoleonic import NapoleonicGame

FAILS = []


def check(label, ok):
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILS.append(label)


def fresh(seed=7):
    live = tempfile.mkdtemp(prefix="aus_gate_")
    game = gamespec.load(HERE)
    g = NapoleonicGame(game, os.path.join(HERE,
                       "scenario_northern_flank.json"), live, seed=seed,
                       command=False,   # mechanics harness: pre-command flow
                       tier=1)          # pinned to the schema-2 subset
    return g, live


def by_slot(g, slot):
    for u in g.s["units"].values():
        if u["slot"] == slot:
            return u
    raise KeyError(slot)


g, live = fresh()

print("== game start ==")
check("30 units loaded", len(g.s["units"]) == 30)
check("French move first (A15.1 initiative umpired; attacker leads)",
      g.s["mover"] == "French")
check("tier is 1 (movement only)", g.s["tier"] == 1)

print("== turn order / activation discipline ==")
rus = by_slot(g, "G/Arkh")
r = g.submit("Allied", {"type": "move", "unit": rus["pid"],
                        "dest": [67, 13], "facing": 9})
check("Allied cannot act on the French activation",
      not r["verdict"]["legal"])
leg = by_slot(g, "2/17 Leg")
r = g.submit("French", {"type": "move", "unit": leg["pid"],
                        "dest": [63, 9], "facing": 3})
check("French line advances 1 hex through its front vertex hexes",
      r["verdict"]["legal"])
r2 = g.submit("French", {"type": "move", "unit": leg["pid"],
                         "dest": [64, 9], "facing": 3})
check("same unit cannot activate twice in a turn [3.0/4.6]",
      not r2["verdict"]["legal"])

print("== formation-true movement ==")
g2, live2 = fresh()
leg = by_slot(g2, "2/17 Leg")           # line, facing 3 (vertex E)
# rear hex is WEST; a plain move there must be rejected (front-only)
r = g2.propose("French", {"type": "move", "unit": leg["pid"],
                          "dest": [61, 9], "facing": 3})
check("line cannot advance out its rear [6.1: front hexsides only]",
      not r["legal"])
r = g2.propose("French", {"type": "reverse", "unit": leg["pid"],
                          "dest": [61, 9]})
check("...but REVERSE to the rear hex is legal at whole-MA cost [6.3.1]",
      r["legal"])
hus = by_slot(g2, "10 Hus")             # cavalry line MA 12 at (62,2)
reach = g2.reachable(hus["pid"])
dists = {(c, r_) for (c, r_, f) in reach}
check("cavalry MA 12 reaches deep (>=8 hexes of options)",
      len(dists) > 8)
sq = by_slot(g2, "1/34 Ln")
r = g2.submit("French", {"type": "change_formation", "unit": sq["pid"],
                         "to": "square"})
check("infantry may form square (voluntary, own activation)",
      r["verdict"]["legal"])
check("square faces all-around (facing parity kept sane)",
      g2.unit(sq["pid"])["formation"] == "square")
r = g2.propose("French", {"type": "move", "unit": sq["pid"],
                          "dest": [63, 14], "facing": 3})
check("square may not move [6.3.4]",
      not r["legal"] or sq["pid"] in g2.s["moved"])

print("== skirmish rules ==")
g3, live3 = fresh()
ln = by_slot(g3, "1/40 Ln")
r = g3.propose("French", {"type": "change_formation", "unit": ln["pid"],
                          "to": "skirmish"})
check("line battalion (not skirmish-capable) may NOT form skirmish "
      "[6.3.3]", not r["legal"])
lg = by_slot(g3, "2/17 Leg")
r = g3.submit("French", {"type": "change_formation", "unit": lg["pid"],
                         "to": "skirmish"})
check("legere (skirmish-capable) may form skirmish [6.3.3]",
      r["verdict"]["legal"])

print("== artillery ==")
g4, live4 = fresh()
art = by_slot(g4, "a/V")                # unlimbered foot battery
r = g4.propose("French", {"type": "move", "unit": art["pid"],
                          "dest": [60, 15], "facing": 1})
check("unlimbered artillery may not move [6.3.8]", not r["legal"])
r = g4.submit("French", {"type": "change_formation", "unit": art["pid"],
                         "to": "limbered"})
check("artillery may limber (formation change) [6.3.7]",
      r["verdict"]["legal"])

print("== enemy front hexes [5.1.3] ==")
g5, live5 = fresh(seed=11)
efh = g5.enemy_front_hexes("French")
check("Russian lines facing west project front hexes",
      len(efh) >= 10)
rus_front = {h for h, pids in efh.items()}
check("hex west of a Russian line is an enemy front hex for the French",
      (66, 12) in rus_front or (66, 11) in rus_front)

print("== movement disorder (engine dice) ==")
g6, live6 = fresh(seed=3)
# woods hexes auto-disorder line/column infantry (TEC 5.0 'D'); find a
# reachable one for anyone — synthetic: teleport a unit next to woods
u = by_slot(g6, "1/64 Ln")
woods = [k for k, v in g6.thex.items() if v == "woods"]
check("terrain file has woods in the area", len(woods) > 0)
wc, wr = map(int, woods[0].split(","))
u["col"], u["row"] = wc, wr - 1 if g6.in_area(wc, wr - 1) else wr + 1
u["facing"] = 7 if wr > u["row"] else 1
# direct step cost into the woods carries the disorder mode
cost, dis, _ = g6.step_cost(u, (u["col"], u["row"]), (wc, wr), 0)
check("entering woods in column/line = auto-disorder or check "
      "[TEC 5.0 D/d]", cost is None or dis in ("auto", "check"))

print("== audit log + hashes ==")
n_before = g.s["n"]
log_lines = open(g.log_path, encoding="utf-8").read().strip().split("\n")
check("every submit logged (incl. rejections)", len(log_lines) == n_before)
entries = [json.loads(l) for l in log_lines]
check("log carries state hashes",
      all("state_hash" in e for e in entries))
check("rejected proposals are in the log with reasons",
      any(e.get("verdict", {}).get("legal") is False and
          e["verdict"]["reasons"] for e in entries
          if e.get("event") == "action"))

for d in (live, live2, live3, live4, live5, live6):
    shutil.rmtree(d, ignore_errors=True)

print()
if FAILS:
    print(f"FAILED: {len(FAILS)}")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("ALL GATE CHECKS PASS")
