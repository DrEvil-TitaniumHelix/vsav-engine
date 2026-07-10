"""Afrika Korps Tier-2 COMPLETION validation: supply capture (15),
isolation (24), replacements (20), substitutes (21), Automatic Victory (9).

Every case is a rulebook- or clarification-cited legal action or illegal
proposal driven through StrategicGame.submit(); every session log replays
through engine/verify_game.py. Worked material: tournament clarifications
sections 3-5, 8, 10 (figs 1-4, 7, 11); rules 9.1-9.7, 14.5, 15.1-15.4,
20.1-20.6, 21.1-21.7, 24.1-24.5.

Run:  python games/afrika-korps-classic-ah/validate_tier2.py
"""
import json
import os
import shutil
import sys
import tempfile
import random as _random

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "engine"))
import gamespec  # noqa: E402
import strategic  # noqa: E402
import verify_game  # noqa: E402

g = gamespec.Game(HERE)
fails = []


def check(cond, what):
    print(("  PASS  " if cond else "  FAIL  ") + what)
    if not cond:
        fails.append(what)


def ring(h):
    return g.neighbors(*h)


def bfs_ring(start, depth, avoid=()):
    seen = {tuple(start)} | {tuple(a) for a in avoid}
    frontier = [tuple(start)]
    for _ in range(depth):
        nxt = []
        for cur in frontier:
            for nb in ring(cur):
                if nb not in seen and g.hex_terrain(*nb) == "clear":
                    seen.add(nb)
                    nxt.append(nb)
        frontier = nxt
    return frontier


def clear_area(need_r=3):
    roads = g._hex_road_sides()
    for key, v in sorted(g.terrain["hexes"].items()):
        if v["t"] != "clear":
            continue
        c, r = int(key[:2]), int(key[2:])
        hexes = {(c, r)}
        frontier = [(c, r)]
        ok = True
        for _ in range(need_r):
            nxt = []
            for cur in frontier:
                for nb in g.neighbors(*cur):
                    if nb in hexes:
                        continue
                    if g.hex_terrain(*nb) != "clear" or roads.get(nb):
                        ok = False
                        break
                    hexes.add(nb)
                    nxt.append(nb)
                if not ok:
                    break
            if not ok:
                break
            frontier = nxt
        if ok:
            return (c, r)
    raise AssertionError("no clear area")


def roomy(cands):
    return next(h for h in cands
                if sum(1 for nb in ring(h)
                       if g.hex_terrain(*nb) == "clear") >= 4)


BASE = clear_area()
N = ring(BASE)
SAFE2 = [h for h in ring(N[0]) if h != BASE and BASE not in ring(h)]
FAR = roomy(bfs_ring(BASE, 8))
FAR2 = roomy(bfs_ring(BASE, 12))
FARN = ring(FAR)

SCEN = os.path.join(HERE, "scenario_validate_tier2_tmp.json")
SCEN_NAME = "AK tier2 validation (temp stage)"
tmpdirs = []


def stat_slots(prefixes, stats):
    out = []
    for frag, st in g.stat_patterns:
        if tuple(st) == tuple(stats) and any(frag.startswith(p) for p in prefixes) \
           and g.unit_class(frag) is None:
            out.append(frag)
    return out


ALLIED116 = stat_slots(("A ",), (1, 1, 6))


def stage(units, seed, turns=8, first="Axis", reserve=(), supply_pool=None,
          repl=None, subs=None):
    scen = {
        "name": SCEN_NAME, "mode": "strategic",
        "game": {"turns": turns, "first_player": first},
        "units": [dict(id=f"u{i}", slot=s, side=side, hex=list(h))
                  for i, (s, side, h) in enumerate(units)],
        "reserve": [dict(r) for r in reserve],
        "supply_pool": supply_pool or {},
        "supply_max_on_board": {"Axis": 3, "Allied": 4},
        "supply_table": {"windows": []},
    }
    if repl:
        scen["replacements"] = repl
    if subs:
        scen["substitutes"] = subs
    json.dump(scen, open(SCEN, "w", encoding="utf-8"))
    tmp = tempfile.mkdtemp()
    tmpdirs.append(tmp)
    return strategic.StrategicGame(g, SCEN, tmp, seed=seed), tmp


CAPT_RES = [dict(id="cap1", slot="G Supply Captured 4", side="Axis", cls="supply"),
            dict(id="cap2", slot="A Supply Captured 5", side="Allied", cls="supply")]


def by_slot(sg, slot):
    return next(u for u in sg.s["units"].values() if u["slot"] == slot)


def expect(sg, side, action, legal, what, contains=None):
    r = sg.submit(side, action)
    ok = r["verdict"]["legal"] == legal
    if ok and contains:
        blob = "; ".join(r["verdict"]["reasons"]) + json.dumps(r.get("result") or {})
        ok = contains in blob
    check(ok, f"{what} -> {(r['verdict']['reasons'] or [str(r.get('result'))[:110]])[0][:130]}")
    return r


def replay(sg, tmp, what):
    log = os.path.join(tmp, [f for f in os.listdir(tmp) if f.endswith(".jsonl")][0])
    ok, msg = verify_game.verify(HERE, log)
    check(ok, f"verify_game replay [{what}]: {msg[:95]}")


def find_seed(rolls, skip=0):
    for seed in range(1, 100000):
        r = _random.Random(seed)
        seq = [1 + int(r.random() * 6) for _ in range(skip + len(rolls))][skip:]
        if seq == list(rolls):
            return seed
    raise AssertionError(f"no seed for {rolls}")


# =====================================================================
print("=== 0. campaign scenario wiring (dates from the printed track) ===")
camp = json.load(open(os.path.join(HERE, "scenario_campaign.json"), encoding="utf-8"))
labels = camp["game"]["turn_labels"]
check(labels[camp["replacements"]["start_turn"] - 1] == "1 March 1942",
      "replacements begin 1 March 1942 (track 'Begin Replacement Rate') [20.1]")
check(labels[camp["substitutes"]["start_turn"] - 1] == "1 August 1942",
      "substitutes begin 1 August 1942 (track annotation) [21.1]")

# =====================================================================
print("=== 1. SUPPLY CAPTURE 15.21: movement adjacency, fig-1 sustain ===")
seed = find_seed([1])                    # 1-1 die 1 -> DE for the follow-up
sg, tmp = stage([
    ("G 15Pz 115", "Axis", FAR),         # 3-3-10 capturer, MF 10
    ("A Supply 2", "Allied", FARN[1]),   # LONE Allied supply beside it
    ("A 7 Arm 7", "Allied", BASE),       # 3-3-7 for the sustained attack later
    ("G 90Inf 55", "Axis", N[0]),        # 2-2-7 will attack it at 1-2... 2:3
    ("A 7A Inf 2", "Allied", FAR2),
    ("G Supply 1", "Axis", SAFE2[0]),
], seed, reserve=CAPT_RES)
pz = by_slot(sg, "G 15Pz 115")
sup = by_slot(sg, "A Supply 2")
r = expect(sg, "Axis", {"type": "move", "unit": pz["pid"],
                        "dest": [sup["col"], sup["row"]]},
           True, "Axis unit moves ONTO the lone Allied supply [15.1, 15.21]",
           "CAPTURED")
check(sup["pid"] not in sg.s["units"], "the original supply left the board")
check(sup["pid"] in sg.s["supply_pool"].get("Allied", []),
      "…returned to the ALLIED pool for re-entry [15.21]")
cap = next((u for u in sg.s["units"].values()
            if "Captured" in u["slot"] and u["side"] == "Axis"), None)
check(cap is not None and (cap["col"], cap["row"]) == (pz["col"], pz["row"]),
      "an Axis captured-supply counter stands in its place [15.21]")
lm = sg.legal_moves(cap["pid"])
check(lm["can_act"] and len(lm["dests"]) > 0,
      "the captured supply may move this turn [15.21, clarifications fig 1]")
sg.submit("Axis", {"type": "end_movement"})
gd = by_slot(sg, "G 90Inf 55")
tgt = by_slot(sg, "A 7 Arm 7")
gs = by_slot(sg, "G Supply 1")
r = expect(sg, "Axis", {"type": "battle", "attackers": [gd["pid"]],
                        "defenders": [tgt["pid"]], "supply": gs["pid"]},
           True, "a movement-captured supply's owner still fights normally")
replay(sg, tmp, "15.21 capture")

print("=== 1b. FIG-3 GUARD: no voluntary suicide capture [7.4 > 15.21] ===")
seed = find_seed([1])
sg, tmp = stage([
    (ALLIED116[0], "Allied", SAFE2[0]),  # 1-1-6 would-be captor, one move out
    ("G Supply 2", "Axis", N[1]),        # lone Axis supply...
    ("G 21Pz 5", "Axis", BASE),          # ...covered by a 7-7-10 ZOC
    ("A Supply 1", "Allied", roomy(bfs_ring(BASE, 6))),
    ("G 90Inf 55", "Axis", FAR),
], seed, first="Allied", reserve=CAPT_RES)
u = by_slot(sg, ALLIED116[0])
r = expect(sg, "Allied", {"type": "move", "unit": u["pid"], "dest": list(N[1])},
           False, "moving to capture the supply while trapped at 1-7 with no "
                  "support is ILLEGAL [clarifications fig 3, 7.4]", "fig 3")
replay(sg, tmp, "fig-3 guard")

print("=== 1c. FORTRESS SUPPLY 15.23 + capture-attack + advance 16.3 ===")
TOB = (31, 11)
land = [n for n in ring(TOB) if g.on_map(*n)]
seed = find_seed([1])
sg, tmp = stage([
    ("G 15Pz 115", "Axis", land[0]),
    ("A Supply 2", "Allied", TOB),       # LONE supply in Tobruch
    ("A 7A Inf 2", "Allied", FAR2),
    ("G Supply 1", "Axis",
     next(n for n in ring(land[0]) if g.on_map(*n) and n != TOB)),
], seed, reserve=CAPT_RES)
pz = by_slot(sg, "G 15Pz 115")
sup = by_slot(sg, "A Supply 2")
check(sup["pid"] in sg.s["units"],
      "adjacency does NOT capture a supply inside a fortress [15.23, fig 9]")
expect(sg, "Axis", {"type": "capture_supply", "unit": pz["pid"],
                    "supply": sup["pid"]},
       False, "the fortress supply can be 'attacked' only in the combat "
              "portion [15.23]", "combat portion")
sg.submit("Axis", {"type": "end_movement"})
r = expect(sg, "Axis", {"type": "capture_supply", "unit": pz["pid"],
                        "supply": sup["pid"]},
           True, "one adjacent unit 'attacks' the lone fortress supply [15.23]")
cap = next((u for u in sg.s["units"].values()
            if "Captured" in u["slot"] and u["side"] == "Axis"), None)
check(cap is not None and cap["pid"] in sg.s["no_sustain"]
      and cap["pid"] in sg.s["moved"],
      "captured at the conclusion of movement: it cannot move or sustain "
      "this turn [15.23, 15.33]")
pend = sg.s["pending"]
check(pend and pend["kind"] == "advance" and list(TOB) in pend["hexes"],
      "the capturing unit may advance into the fortress [16.3]")
expect(sg, "Axis", {"type": "advance", "unit": pz["pid"], "hex": list(TOB)},
       True, "…and does")
expect(sg, "Axis", {"type": "end_phase"}, True, "turn ends clean")
replay(sg, tmp, "15.23 fortress capture")

print("=== 1d. ACCOMPANIED SUPPLY 15.322 (figs 7/11) ===")
seed = find_seed([3])                    # escort battle 3-1 die 3 -> DB2
sg, tmp = stage([
    ("G 15Pz 115", "Axis", N[0]),        # 3-3-10 attacks the escort at 3-1
    ("G 90Inf 55", "Axis", N[2]),        # 2-2-7 'attacks' the supply
    (ALLIED116[0], "Allied", BASE),      # escort 1-1-6
    ("A Supply 2", "Allied", BASE),      # supply stacked with it
    ("G Supply 1", "Axis", SAFE2[0]),
    ("A 7A Inf 2", "Allied", FAR2),
], seed, reserve=CAPT_RES)
a1, a2 = by_slot(sg, "G 15Pz 115"), by_slot(sg, "G 90Inf 55")
esc_u, sup = by_slot(sg, ALLIED116[0]), by_slot(sg, "A Supply 2")
gs = by_slot(sg, "G Supply 1")
check(sup["pid"] in sg.s["units"],
      "an ACCOMPANIED supply is not captured by adjacency [15.2, 15.3]")
sg.submit("Axis", {"type": "end_movement"})
expect(sg, "Axis", {"type": "capture_supply", "unit": a2["pid"],
                    "supply": sup["pid"]},
       True, "one unit 'attacks' the accompanied supply [15.322, fig 7]")
expect(sg, "Axis", {"type": "battle", "attackers": [a2["pid"]],
                    "defenders": [esc_u["pid"]]},
       False, "the supply-capturer may not also join a battle [15.322, "
              "fig 7]", "11.8")
expect(sg, "Axis", {"type": "end_phase"}, False,
       "the escort must still be attacked at legal odds [15.322/8.4]",
       "attack")
lm = sg.legal_moves(next(u["pid"] for u in sg.s["units"].values()
                         if "Captured" in u["slot"] and u["side"] == "Axis"))
check(lm["can_act"] and len(lm["dests"]) > 0,
      "the combat-captured supply may be moved out of the old escort's ZOC "
      "[15.33, 15.34]")
r = expect(sg, "Axis", {"type": "battle", "attackers": [a1["pid"]],
                        "defenders": [esc_u["pid"]], "supply": gs["pid"]},
           True, "the other unit attacks the escort")
if r["result"]["result"] == "DB2":
    ez = g.zoc_hexes(sg.rules_board(), "Axis")
    occ = {(u["col"], u["row"]) for u in sg.s["units"].values() if sg.on_map(u)}
    h1, h2 = next((a, b) for a in ring(BASE) for b in ring(a)
                  if a not in ez and b not in ez and a not in occ
                  and b not in occ and g.on_map(*a) and g.on_map(*b)
                  and b != BASE and b != a)
    expect(sg, "Axis", {"type": "retreat", "unit": esc_u["pid"],
                        "path": [list(h1), list(h2)]}, True,
           "escort retreated by the winner")
expect(sg, "Axis", {"type": "end_phase"}, True, "obligations discharged")
replay(sg, tmp, "15.322 accompanied capture")

print("=== 1e. RETREAT CAPTURE 15.22 + no-sustain ===")
seed = find_seed([3])
# a hex the engine will offer as a retreat end: 2 steps from BASE, both
# steps clear and outside the attacker's (N[0]) ZOC
ez_stage = set(ring(N[0]))
sup_spot = next(b for a in ring(BASE) for b in ring(a)
                if a not in ez_stage and b not in ez_stage
                and a != BASE and b != BASE and b != a
                and g.hex_terrain(*a) == "clear"
                and g.hex_terrain(*b) == "clear")
sg, tmp = stage([
    ("G 15Pz 115", "Axis", N[0]),        # forces the retreat at 3-1
    (ALLIED116[0], "Allied", BASE),      # will retreat over the Axis supply
    ("G Supply 2", "Axis", sup_spot),    # LONE Axis supply on the escape route
    ("G Supply 1", "Axis", SAFE2[0]),
    ("A 7A Inf 2", "Allied", FAR2),
    ("G 90Inf 55", "Axis", FAR),
], seed, reserve=CAPT_RES)
a1 = by_slot(sg, "G 15Pz 115")
d1 = by_slot(sg, ALLIED116[0])
gs = by_slot(sg, "G Supply 1")
sg.submit("Axis", {"type": "end_movement"})
r = expect(sg, "Axis", {"type": "battle", "attackers": [a1["pid"]],
                        "defenders": [d1["pid"]], "supply": gs["pid"]},
           True, "3-1 battle vs the unit that will retreat")
check(r["result"]["result"] == "DB2", "die 3 at 3-1 -> D back 2")
pend = sg.s["pending"]
opts = pend and next(u for u in
                     sg.combat_panel()["pending"]["units"])["options"]
onto = next((o for o in (opts or []) if tuple(o["end"]) == sup_spot), None)
if onto:
    r = expect(sg, "Axis", {"type": "retreat", "unit": d1["pid"],
                            "path": onto["path"]},
               True, "the winner retreats the loser ONTO the lone enemy "
                     "supply [7.6]", "CAPTURED")
    cap = next((u for u in sg.s["units"].values()
                if "Captured" in u["slot"] and u["side"] == "Allied"), None)
    check(cap is not None and cap["pid"] in sg.s["no_sustain"],
          "supply captured during a retreat may not sustain attacks this "
          "turn [15.22]")
else:
    check(False, f"stage: no retreat option onto the supply at {sup_spot}")
replay(sg, tmp, "15.22 retreat capture")

print("=== 1f. DESTROY OWN SUPPLY 15.4 + counter recycling 12/14.1 ===")
seed = find_seed([1])
sg, tmp = stage([
    ("A Supply 2", "Allied", BASE),
    (ALLIED116[0], "Allied", N[0]),
    ("G 90Inf 55", "Axis", FAR),
    ("A 7A Inf 2", "Allied", FAR2),
], seed, first="Allied", supply_pool={"Allied": [], "Axis": []})
sup = by_slot(sg, "A Supply 2")
r = expect(sg, "Allied", {"type": "destroy_supply", "unit": sup["pid"]},
           True, "a player may destroy his own supply at any time in his "
                 "turn [15.4]")
check(sup["pid"] in sg.s["supply_pool"]["Allied"],
      "the destroyed counter returns to the off-board pool (12.1 maxima are "
      "counter counts)")
replay(sg, tmp, "15.4 destroy")

# =====================================================================
print("=== 2. ISOLATION 24.2/24.5 + clarification 8 ===")
seed = find_seed([1])
sg, tmp = stage([
    (ALLIED116[0], "Allied", BASE),      # no Allied supply anywhere: isolated
    ("G 90Inf 55", "Axis", FAR),
    ("G Supply 1", "Axis", FARN[1]),
], seed, first="Allied", turns=8,
    supply_pool={"Allied": ["ap1"], "Axis": []},
    reserve=[dict(id="ap1", slot="A Supply 1", side="Allied", cls="supply")])
u = by_slot(sg, ALLIED116[0])
expect(sg, "Allied", {"type": "end_phase"}, True, "Allied turn 1 ends")
check(sg.s["iso"].get(u["pid"]) == 1,
      "isolated at start AND end of the turn: one turn of isolation [24.2]")
expect(sg, "Axis", {"type": "end_phase"}, True, "Axis passes")
expect(sg, "Allied", {"type": "end_phase"}, True, "Allied turn 2 ends")
check(u["pid"] not in sg.s["units"],
      "two consecutive turns isolated -> ELIMINATED [24.2]")
replay(sg, tmp, "24.2 elimination")

# clarification 8: a supply landed then destroyed mid-turn does NOT break
# the isolation count (must be in supply at start OR end)
seed = find_seed([1])
J62 = (67, 14)
sg, tmp = stage([
    (ALLIED116[0], "Allied", J62),       # garrisons the Allied home base
    ("G 90Inf 55", "Axis", FAR),
    ("G Supply 1", "Axis", FARN[1]),
], seed, first="Allied", turns=8,
    supply_pool={"Allied": ["ap1"], "Axis": []},
    reserve=[dict(id="ap1", slot="A Supply 1", side="Allied", cls="supply")])
u = by_slot(sg, ALLIED116[0])
expect(sg, "Allied", {"type": "land_supply", "port": list(J62)}, True,
       "supply lands at the (isolated) home base")
sup = next(x for x in sg.s["units"].values()
           if sg.game.unit_class(x["slot"]) == "supply" and x["side"] == "Allied")
expect(sg, "Allied", {"type": "destroy_supply", "unit": sup["pid"]}, True,
       "…and is destroyed after movement to deny its capture [15.4]")
expect(sg, "Allied", {"type": "end_phase"}, True, "the turn ends")
check(sg.s["iso"].get(u["pid"]) == 1,
      "it still counts as a turn of isolation — in supply at start OR end "
      "is required [24.2, clarifications 8]")
replay(sg, tmp, "clarif-8 isolation count")

# 24.5: no supply units on board for two consecutive own turns = game loss
seed = find_seed([1])
sg, tmp = stage([
    (ALLIED116[0], "Allied", BASE),
    (ALLIED116[1], "Allied", FAR2),
    ("G 90Inf 55", "Axis", FAR),
    ("G Supply 1", "Axis", FARN[1]),
], seed, first="Allied", turns=8)
expect(sg, "Allied", {"type": "end_phase"}, True, "Allied t1 (no supplies)")
expect(sg, "Axis", {"type": "end_phase"}, True, "Axis passes")
r = expect(sg, "Allied", {"type": "end_phase"}, True, "Allied t2 (no supplies)")
check(sg.s["over"] and sg.s["winner"] == "Axis",
      "no supply units on board two consecutive turns -> loses ALL units "
      "and the game [24.5]")
replay(sg, tmp, "24.5 game loss")

# =====================================================================
print("=== 3. REPLACEMENTS 20 ===")
REPL = {"start_turn": 2,
        "rates": {"Axis": {"homebase": 1, "fortress_port": 1},
                  "Allied": {"homebase": 2, "fortress_port": 1}}}
W3 = (1, 27)
seed = find_seed([1])
sg, tmp = stage([
    ("G 90Inf 55", "Axis", W3),          # holds the Axis home base
    ("G 15Pz 115", "Axis", TOB),         # holds Tobruch
    ("G 21Pz 5", "Axis", N[0]),          # kills the victim at 7-1
    (ALLIED116[0], "Allied", BASE),      # the victim (1 attack factor)
    (ALLIED116[1], "Allied", FAR2),
    ("G Supply 1", "Axis", SAFE2[0]),
    ("A Supply 1", "Allied", FAR2),
], seed, turns=8, repl=REPL)
victim = by_slot(sg, ALLIED116[0])
pz, gs = by_slot(sg, "G 21Pz 5"), by_slot(sg, "G Supply 1")
sg.submit("Axis", {"type": "end_movement"})
sg.submit("Axis", {"type": "battle", "attackers": [pz["pid"]],
                   "defenders": [victim["pid"]], "supply": gs["pid"]})
check(victim["pid"] not in sg.s["units"], "stage: victim eliminated at 7-1")
expect(sg, "Axis", {"type": "replace", "unit": victim["pid"],
                    "port": list(TOB)},
       False, "replacements begin only at the configured turn [20.1]", "20.1")
r = expect(sg, "Axis", {"type": "end_phase"}, True, "Axis t1 ends")
expect(sg, "Allied", {"type": "end_phase"}, True, "Allied t1 ends")
check(sg.s["repl"]["Axis"] == 2,
      f"Axis turn 2 start: 1 (home base) + 1 (Tobruch) = 2 factors accrued "
      f"[20.2] (have {sg.s['repl']['Axis']})")
expect(sg, "Axis", {"type": "replace", "unit": victim["pid"], "port": list(TOB)},
       False, "an AXIS player cannot replace an ALLIED unit [20.1]", "own")
expect(sg, "Axis", {"type": "end_phase"}, True, "Axis t2 passes")
check(sg.s["repl"]["Allied"] == 0,
      "Allied controls neither home base nor Tobruch: no accrual [20.3]")
expect(sg, "Allied", {"type": "replace", "unit": victim["pid"],
                      "port": list(J62)},
       False, "no factors accrued and no controlled port — rejected", "")
expect(sg, "Allied", {"type": "end_phase"}, True, "Allied t2")
expect(sg, "Axis", {"type": "end_phase"}, True, "Axis t3 passes (repl 4)")
check(sg.s["repl"]["Axis"] == 4, "factors accumulate turn to turn [20.5]")
replay(sg, tmp, "20 accrual")

# spend: Allied resurrects its 1-factor unit at a controlled home base
seed = find_seed([1])
sg, tmp = stage([
    (ALLIED116[1], "Allied", J62),       # holds the Allied home base
    ("A Supply 1", "Allied", J62),
    ("G 90Inf 55", "Axis", FAR),
    ("G Supply 1", "Axis", SAFE2[0]),    # in range of the 7-1 attack
    ("G 21Pz 5", "Axis", N[0]),
    (ALLIED116[0], "Allied", BASE),      # dies turn 1
    ("A Supply 2", "Allied", FAR2),
], seed, turns=8, repl=REPL)
victim = by_slot(sg, ALLIED116[0])
pz, gs = by_slot(sg, "G 21Pz 5"), by_slot(sg, "G Supply 1")
sg.submit("Axis", {"type": "end_movement"})
sg.submit("Axis", {"type": "battle", "attackers": [pz["pid"]],
                   "defenders": [victim["pid"]], "supply": gs["pid"]})
sg.submit("Axis", {"type": "end_phase"})
expect(sg, "Allied", {"type": "end_phase"}, True, "Allied t1")
sg.submit("Axis", {"type": "end_phase"})
check(sg.s["repl"]["Allied"] == 2, "Allied accrues 2 for its home base [20.3]")
r = expect(sg, "Allied", {"type": "replace", "unit": victim["pid"],
                          "port": list(J62)},
           True, "the eliminated 1-1-6 returns for 1 attack factor at the "
                 "controlled home base [20.1, 20.4]")
check(victim["pid"] in sg.s["units"] and sg.s["repl"]["Allied"] == 1,
      "unit is back on the board; 1 factor remains banked [20.5]")
lm = sg.legal_moves(victim["pid"])
check(lm["can_act"], "the replacement may move this turn [20.4, 19.2]")
replay(sg, tmp, "20 spend")

# =====================================================================
print("=== 4. SUBSTITUTES 21 (types from the counter faces) ===")
SUBS = {"start_turn": 1, "side": "Allied"}
sub_res = [dict(id="sb1", slot="A Sub Inf 3", side="Allied"),
           dict(id="sb2", slot="A Sub Arm 1", side="Allied")]
seed = find_seed([1])
sg, tmp = stage([
    (ALLIED116[0], "Allied", BASE),      # three 1-1-6 infantry, same hex
    (ALLIED116[1], "Allied", BASE),
    (ALLIED116[2], "Allied", BASE),
    ("A 1 Arm 2", "Allied", N[0]),       # 4-4-7 armor
    ("A 7 Arm 7", "Allied", FAR2),       # 3-3-7 armored infantry
    ("A Supply 1", "Allied", SAFE2[0]),
    ("G 90Inf 55", "Axis", FAR),
    ("G Supply 1", "Axis", FARN[1]),
], seed, first="Allied", turns=8, subs=SUBS, reserve=sub_res)
i1, i2, i3 = (by_slot(sg, s) for s in ALLIED116[:3])
arm = by_slot(sg, "A 1 Arm 2")
expect(sg, "Allied", {"type": "substitute", "units": [i1["pid"], i2["pid"],
                                                      i3["pid"]],
                      "sub": "sb1"},
       False, "substitution happens at the END of the movement portion "
              "[21.2]", "21.2")
sg.submit("Allied", {"type": "end_movement"})
expect(sg, "Allied", {"type": "substitute",
                      "units": [i1["pid"], i2["pid"]], "sub": "sb1"},
       False, "two 1-1-6s total 2 attack factors, the 3-3-7 substitute is 3 "
              "— totals must be the same [21.1]", "21.1")
r = expect(sg, "Allied", {"type": "substitute",
                          "units": [i1["pid"], i2["pid"], i3["pid"]],
                          "sub": "sb1"},
           True, "three 1-1-6 infantry (3 factors) form the 3-3-7 substitute "
                 "[21.1, 21.2]")
sub = by_slot(sg, "A Sub Inf 3")
check((sub["col"], sub["row"]) == (i1["col"], i1["row"]) if False else
      sub["pid"] in sg.s["moved"],
      "the substitute may not move on its placement turn [21.2]")
expect(sg, "Allied", {"type": "breakdown", "sub": sub["pid"],
                      "into": [i1["pid"], i2["pid"], i3["pid"]]},
       True, "…and may break back down into its components [21.3, 21.4]")
check(all(p in sg.s["units"] for p in (i1["pid"], i2["pid"], i3["pid"])),
      "the components are back on the board in the substitute's hex")
expect(sg, "Allied", {"type": "end_phase"}, True, "turn ends")
replay(sg, tmp, "21 substitute cycle")

# type matching (counter-face symbols): armor never folds into an infantry
# substitute; the armor substitute takes armor at equal factors
seed = find_seed([1])
sg, tmp = stage([
    (ALLIED116[0], "Allied", BASE),      # 1-1-6 infantry
    ("A 1 Arm 2", "Allied", BASE),       # 4-4-7 armor, same hex
    ("A Supply 1", "Allied", SAFE2[0]),
    ("G 90Inf 55", "Axis", FAR),
    ("G Supply 1", "Axis", FARN[1]),
], seed, first="Allied", turns=8, subs=SUBS, reserve=sub_res)
i1 = by_slot(sg, ALLIED116[0])
arm = by_slot(sg, "A 1 Arm 2")
sg.submit("Allied", {"type": "end_movement"})
expect(sg, "Allied", {"type": "substitute",
                      "units": [i1["pid"], arm["pid"]], "sub": "sb1"},
       False, "ARMOR may not fold into an infantry substitute [21.1]", "21.1")
expect(sg, "Allied", {"type": "substitute", "units": [arm["pid"]],
                      "sub": "sb2"},
       True, "the 4-4-7 armor brigade forms the 4-4-10 armor substitute "
             "[21.1, counter faces]")
replay(sg, tmp, "21 type matching")

# =====================================================================
print("=== 5. AUTOMATIC VICTORY 9 ===")
seed = find_seed([2])                    # follow-up battle die (unused if auto)
sg, tmp = stage([
    ("G 21Pz 5", "Axis", N[0]),          # 7-7-10: 7-1 vs a 1-1-6
    ("G 15Pz 33", "Axis", SAFE2[0]),     # 2-2-12 will exploit the negated ZOC
    (ALLIED116[0], "Allied", BASE),      # the AV victim
    (ALLIED116[1], "Allied", FAR2),
    ("G Supply 1", "Axis", SAFE2[1] if len(SAFE2) > 1 else SAFE2[0]),
    ("A Supply 1", "Allied", FAR2),
], seed, turns=8)
pz = by_slot(sg, "G 21Pz 5")
rec = by_slot(sg, "G 15Pz 33")
vic = by_slot(sg, ALLIED116[0])
gs = by_slot(sg, "G Supply 1")
expect(sg, "Axis", {"type": "declare_av", "attackers": [pz["pid"]],
                    "defender": vic["pid"]},
       False, "an AV must name its sustaining supply at the instant [9.2, "
              "9.6]", "supply")
before = set(map(tuple, sg.dests(rec)))
r = expect(sg, "Axis", {"type": "declare_av", "attackers": [pz["pid"]],
                        "defender": vic["pid"], "supply": gs["pid"]},
           True, "7-7-10 adjacent to a 1-1-6 with supply in range: "
                 "AUTOMATIC VICTORY at 7-1 [9.1, 9.2]")
after = set(map(tuple, sg.dests(rec)))
gained = after - before
check(len(gained) > 0 and tuple((vic["col"], vic["row"])) not in after,
      f"the negated ZOC opens {len(gained)} new hexes to other units, but "
      f"never the AVed unit's own hex [9.1]")
expect(sg, "Axis", {"type": "move", "unit": pz["pid"], "dest": list(SAFE2[0])},
       False, "the AVing unit is frozen until the battle portion [9.2]", "")
expect(sg, "Axis", {"type": "end_movement"}, True,
       "end of movement: the AV supply is revalidated and expended [9.2, 14.5]")
check(gs["pid"] in sg.s["supplies_used"],
      "the sustaining supply is marked expended [9.6, 14.1]")
expect(sg, "Axis", {"type": "end_phase"}, False,
       "the declared AV must be resolved before the turn ends [9.1, 9.6]",
       "9.1")
rng_before = sg.s["rng_calls"]
r = expect(sg, "Axis", {"type": "battle", "attackers": [pz["pid"]],
                        "defenders": [vic["pid"]], "supply": gs["pid"]},
           True, "the AV attack resolves")
check(r["result"]["column"] == "auto_elim" and sg.s["rng_calls"] == rng_before,
      "…as automatic elimination, no die rolled [9.1, 7.4]")
expect(sg, "Axis", {"type": "end_phase"}, True, "turn ends")
check(not any(u.get("slot") == "G Supply 1" for u in sg.s["units"].values()),
      "the AV supply was consumed at the end of the player turn [14.1]")
replay(sg, tmp, "AV 7-1")

# 5-1 SURROUNDED: three units at alternating ring positions cover every
# retreat exit — the AV is legal at 5-1 and the blocker freezes too (9.3)
seed = find_seed([1])
# neighbors() lists W,E,NW,NE,SW,SE — the circular ring is [0,2,3,1,5,4],
# so alternating coverage = indices 0, 3, 5 (W, NE, SE)
sg, tmp = stage([
    ("G 15Pz 115", "Axis", N[0]),        # 3 attack
    ("G 90Inf 55", "Axis", N[3]),        # 2 attack -> 5-1 vs a 1-1-6
    ("G 90Inf 200", "Axis", N[5]),       # the BLOCKER closing the ring
    (ALLIED116[0], "Allied", BASE),
    ("G Supply 1", "Axis", SAFE2[0]),
    ("A Supply 1", "Allied", FAR2),
    (ALLIED116[1], "Allied", FAR2),
], seed, turns=8)
a1, a2 = by_slot(sg, "G 15Pz 115"), by_slot(sg, "G 90Inf 55")
blk = by_slot(sg, "G 90Inf 200")
vic = by_slot(sg, ALLIED116[0])
gs = by_slot(sg, "G Supply 1")
expect(sg, "Axis", {"type": "declare_av",
                    "attackers": [a1["pid"], a2["pid"]],
                    "defender": vic["pid"], "supply": gs["pid"],
                    "blockers": [blk["pid"]]},
       True, "5-1 with EVERY retreat exit in enemy ZOC: a surrounded AV "
             "[9.1]")
expect(sg, "Axis", {"type": "move", "unit": blk["pid"], "dest": list(FAR)},
       False, "the cutoff unit is frozen for the rest of the turn too [9.3]",
       "")
sg.submit("Axis", {"type": "end_movement"})
r = expect(sg, "Axis", {"type": "battle",
                        "attackers": [a1["pid"], a2["pid"]],
                        "defenders": [vic["pid"]], "supply": gs["pid"]},
           True, "the surrounded 5-1 resolves on the CRT")
if r["result"]["result"] == "DB2":
    expect(sg, "Axis", {"type": "retreat", "unit": vic["pid"],
                        "eliminate": True},
           True, "…every result kills: a back-2 with no route eliminates "
                 "[7.61, 9.1]")
expect(sg, "Axis", {"type": "end_phase"}, True, "turn ends")
replay(sg, tmp, "AV 5-1 surrounded")

# AV rejections: odds too low; 5-1 unsurrounded; supply blocked by the
# defender's own ZOC at the declaration instant (clarifications sec 10)
seed = find_seed([1])
sg, tmp = stage([
    ("G 15Pz 115", "Axis", N[0]),        # 3-3-10: only 3-1
    (ALLIED116[0], "Allied", BASE),
    ("G Supply 1", "Axis", SAFE2[0]),
    ("A Supply 1", "Allied", FAR2),
    (ALLIED116[1], "Allied", FAR2),
    ("G 90Inf 55", "Axis", FAR),
], seed, turns=8)
a = by_slot(sg, "G 15Pz 115")
vic = by_slot(sg, ALLIED116[0])
gs = by_slot(sg, "G Supply 1")
expect(sg, "Axis", {"type": "declare_av", "attackers": [a["pid"]],
                    "defender": vic["pid"], "supply": gs["pid"]},
       False, "3-1 is no automatic-elimination situation [9.1]", "9.1")
replay(sg, tmp, "AV odds rejection")

# supply behind the defender: its ZOC blocks the trace at the instant
seed = find_seed([1])
behind = next(h for h in ring(BASE) if h not in (N[0],) and h != BASE
              and g.hex_terrain(*h) == "clear"
              and not any(h in ring(x) for x in [N[0]]))
sg, tmp = stage([
    ("G 21Pz 5", "Axis", N[0]),
    (ALLIED116[0], "Allied", BASE),
    ("G Supply 1", "Axis", behind),      # adjacent to the DEFENDER: in its ZOC
    ("A Supply 1", "Allied", FAR2),
    (ALLIED116[1], "Allied", FAR2),
    ("G 90Inf 55", "Axis", FAR),
], seed, turns=8)
pz = by_slot(sg, "G 21Pz 5")
vic = by_slot(sg, ALLIED116[0])
gs = by_slot(sg, "G Supply 1")
expect(sg, "Axis", {"type": "declare_av", "attackers": [pz["pid"]],
                    "defender": vic["pid"], "supply": gs["pid"]},
       False, "at the DECLARATION instant the target's own ZOC still blocks "
              "the supply route [9.2, clarifications sec 10]", "sec 10")
replay(sg, tmp, "AV supply-instant rejection")

# =====================================================================
if os.path.exists(SCEN):
    os.remove(SCEN)
for t in tmpdirs:
    shutil.rmtree(t, ignore_errors=True)

print()
if fails:
    print(f"FAILURES: {len(fails)}")
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("ALL PASS")
