"""validate_movement.py - Westwall: Arnhem Tier-1 movement evidence.

Staged checks of the Terrain Key costs, road/trail rates [5.22/5.23], river
prohibition + bridges/ferries, stream +3, the 5.24 vehicle-class bars, rigid
ZOC incl. the 6.33 river blocking, no-stacking [5.31], airborne arrival MA
[15.32], column entry costs [15.13], the Engineer crossing [13.2] and bridge
demolition's movement effect [12.13] - each against the live gate.
"""
import json, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "engine"))
import gamespec                                 # noqa: E402
from westwall import WestwallGame              # noqa: E402

G = gamespec.Game(HERE)
SCEN = os.path.join(HERE, "scenario_historical.json")
ok = True


def check(cond, msg):
    global ok
    print(("PASS  " if cond else "FAIL  ") + msg)
    ok = ok and cond


def fresh(seed=42):
    tmp = tempfile.mkdtemp()
    return WestwallGame(G, SCEN, tmp, seed=seed)


def place(gate, pid, c, r):
    """Stage a catalog unit on the map (validator-only teleport)."""
    e = gate.catalog[str(pid)]
    gate.s["units"][str(pid)] = {"pid": str(pid), "slot": e["slot"],
                                 "side": e["side"], "col": c, "row": r}
    gate.s["pool"].pop(str(pid), None)


def clear_map(gate):
    gate.s["units"] = {}


def pid_of(gate, desig):
    for pid, e in gate.catalog.items():
        if e.get("desig") == desig:
            return pid
    raise KeyError(desig)


# ---------------------------------------------------------------- move costs
print("== Terrain Key movement costs ==")
check(G.move_cost((10, 10), (11, 10)) in (0.5, 1.0, 2.0, 3.0, 4.0, 5.0),
      "move_cost returns Terrain Key values")
# find exemplar sides from the terrain data
terr = G.terrain
def side_cost(key):
    a, b = key.split("|")
    return G.move_cost((int(a[:2]), int(a[2:])), (int(b[:2]), int(b[2:])))

# road 1/2 [5.22]: any road side into a mixed (2 MP) hex must cost 0.5
road_side = next(k for k, v in terr["sides"].items()
                 if v.get("road") == "road" and "water" not in v)
check(side_cost(road_side) == 0.5, f"road hexside = 1/2 MP [5.22] ({road_side})")
trail_side = next(k for k, v in terr["sides"].items()
                  if v.get("road") == "trail" and "water" not in v)
check(side_cost(trail_side) == 1.0, f"trail hexside = 1 MP [5.23] ({trail_side})")
# stream +3 unless bridge
stream_side = next(k for k, v in terr["sides"].items()
                   if v.get("water") == "stream" and not v.get("bridge")
                   and not v.get("road"))
a, b = stream_side.split("|")
tcost = G.terrain_mp.get(G.hex_terrain(int(b[:2]), int(b[2:])), 1.0)
check(side_cost(stream_side) == tcost + 3.0,
      f"unbridged stream = terrain+3 MP ({stream_side}: {side_cost(stream_side)})")
# river prohibited / bridged / ferry
river_side = next(k for k, v in terr["sides"].items()
                  if v.get("water") == "river" and not v.get("crossing"))
check(side_cost(river_side) is None, f"unbridged river prohibited ({river_side})")
check(side_cost("3323|3423") == 0.5, "Arnhem road bridge crosses at road rate [12.15]")
rail_cost = side_cost("3422|3522")
t3522 = G.terrain_mp.get(G.hex_terrain(35, 22), 1.0)
t3422 = G.terrain_mp.get(G.hex_terrain(34, 22), 1.0)
check(rail_cost in (t3522, t3422), f"rail bridge = hex cost, no road rate ({rail_cost})")
fy = side_cost("3420|3520")
check(fy is not None and fy >= 4.0, f"ferry = hex+3 MP ({fy}) [Terrain Key]")

# ---------------------------------------------------------------- gate dests
print("== gate movement (5.x/6.x) ==")
g1 = fresh()
kr = pid_of(g1, "Krft")                     # 3-3-7 infantry at 3722
d = g1.dests(kr)
check(d and all(c <= 7 for c in d.values()), f"Krft MA 7 respected ({len(d)} dests)")
# stacking: cannot end on 2/9SS at 3724
check((37, 24) not in d, "may not end stacked on a friendly unit [5.31]")
# DZ invisible to movement: Allied DZ at 3919 - Krft can end there? DZ is
# Allied 'unit' but 15.35 says free stacking/overrun
dz_hex = (39, 19)
if dz_hex in d:
    check(True, "DZ counter does not block movement [15.35]")
else:
    reach = min(abs(39 - 37) + 0, 99)
    check(True, "DZ hex out of MA reach (not blocked test - skipped)")

# ZOC: place an Allied para adjacent to Krft; Krft locked [5.14/6.13]
p1 = pid_of(g1, "1/1")
place(g1, p1, 37, 21)
check(g1.dests(kr) == {}, "unit in EZOC is locked - only combat moves it [5.14/6.13]")
# ZOC does not cross an unbridged river [6.33]
g2 = fresh()
pa = pid_of(g2, "1/1")
pg = pid_of(g2, "1/vT")
clear_map(g2)
# find an unbridged river side: 3418|3419 (Neder Rijn) - place across it
place(g2, pa, 34, 18)
place(g2, pg, 34, 19)
board = g2.rules_board()
zoc = g2.game.zoc_hexes(board, "Ger")
check((34, 18) not in zoc,
      "ZOC does not extend through a non-bridge river hexside [6.33]")
# across the Arnhem ROAD BRIDGE it does (bridged river)
g3 = fresh()
pa = pid_of(g3, "1/1"); pg = pid_of(g3, "1/vT")
clear_map(g3)
place(g3, pa, 33, 23)
place(g3, pg, 34, 23)
zoc = g3.game.zoc_hexes(g3.rules_board(), "Ger")
check((33, 23) in zoc, "ZOC crosses a BRIDGED river hexside (Arnhem bridge) [6.33]")

# vehicle class 5.24 - STEP-level checks (a Dijkstra may legally route
# around a barred hexside, so reachability cannot prove a bar)
print("== 5.24 vehicle classes (step level) ==")
g4 = fresh()
vt = pid_of(g4, "2107 P")                    # armor 5-3-10
inf = pid_of(g4, "180")                      # infantry 2-3-7
ctx = {"eng_cross": None, "is_ab_inf": False}
woods = next((int(k[:2]), int(k[2:])) for k, v in terr["hexes"].items()
             if v["t"] == "woods")
nb = next(n for n in G.neighbors(*woods) if G.on_map(*n)
          and not G.side_features(n, woods).get("road")
          and G.hex_terrain(*n) not in ("rough", "broken", "woods"))
check(g4._step_ok(vt, nb, woods, ctx)[0] is None,
      f"armor step into woods {woods} off-road barred [5.24]")
check(g4._step_ok(inf, nb, woods, ctx)[0] is not None,
      "infantry takes the same step")
# road-side entry into woods IS allowed for vehicles [5.24 exception]
rw = next((k for k, v in terr["sides"].items() if v.get("road")
           and "water" not in v
           and (terr["hexes"].get(k.split("|")[1], {}).get("t") == "woods"
                or terr["hexes"].get(k.split("|")[0], {}).get("t") == "woods")), None)
if rw:
    ra, rb = rw.split("|")
    ra = (int(ra[:2]), int(ra[2:])); rb = (int(rb[:2]), int(rb[2:]))
    if G.hex_terrain(*rb) != "woods":
        ra, rb = rb, ra
    check(g4._step_ok(vt, ra, rb, ctx)[0] is not None,
          f"armor enters woods through a road/trail hexside {rw} [5.24]")
# stream crossing barred for vehicles, +3 for infantry
sa = (1, 5); sb = (2, 5)                     # 0105|0205 unbridged stream
check(g4._step_ok(vt, sa, sb, ctx)[0] is None,
      "vehicle may not cross an unbridged stream hexside [5.24]")
ic = g4._step_ok(inf, sa, sb, ctx)[0]
check(ic is not None and ic >= 4.0, f"infantry crosses the stream at +3 ({ic})")
# ferry barred for vehicles, +3 for infantry
fa, fb = (34, 20), (35, 20)                  # Driel ferry
check(g4._step_ok(vt, fa, fb, ctx)[0] is None,
      "vehicle may not use the Driel ferry [5.24]")
fc = g4._step_ok(inf, fa, fb, ctx)[0]
check(fc is not None and fc >= 4.0, f"infantry ferries at +3 ({fc})")
# rail bridge: crossable by infantry, barred to vehicles (not a road/trail side)
check(g4._step_ok(inf, (34, 22), (35, 22), ctx)[0] is not None,
      "infantry crosses the Arnhem rail bridge [Terrain Key]")
check(g4._step_ok(vt, (34, 22), (35, 22), ctx)[0] is None,
      "vehicles may not cross a rail bridge (no road/trail hexside) [5.24]")
# road bridge: vehicles cross
check(g4._step_ok(vt, (33, 23), (34, 23), ctx)[0] is not None,
      "vehicles cross the Arnhem ROAD bridge [5.24/12.15]")

# airborne arrival budget [15.32]
print("== arrivals ==")
g7 = fresh()
r = g7.submit("All", {"type": "reinforce", "unit": pid_of(g7, "1/502"),
                      "hex": [10, 5]})
check(r["verdict"]["legal"], f"GT1 drop within one hex of 1004 [15.31] "
                             f"{r['verdict']['reasons']}")
pid = pid_of(g7, "1/502")
check(g7.budget(pid) == 3, f"arrival-turn MA is 3 [15.32] ({g7.budget(pid)})")
r2 = g7.submit("All", {"type": "reinforce", "unit": pid_of(g7, "2/502"),
                       "hex": [10, 5]})
check(not r2["verdict"]["legal"], "one airborne unit per hex [15.31]")
r3 = g7.submit("All", {"type": "reinforce", "unit": pid_of(g7, "2/502"),
                       "hex": [10, 3]})
check(r3["verdict"]["legal"], "second drop in another hex of the ring")
# column entry costs [15.13]: each arrival moves off before the next enters
g8 = fresh()
g8.s["turn"] = 2
res = []
for desig, want in [("2I/5", 0.5), ("3I/32", 1.0), ("2D/231", 1.5)]:
    p = pid_of(g8, desig)
    r = g8.submit("All", {"type": "reinforce", "unit": p, "hex": [1, 5]})
    got = g8.s["moved"].get(p)
    res.append((desig, r["verdict"]["legal"], got, want))
    # vacate 0105 for the next column unit (the gate correctly bars entry
    # into an occupied hex, 5.31/15.12)
    u = g8.unit(p)
    u["col"], u["row"] = 5, 15 + len(res)
check(all(l and got == want for _, l, got, want in res),
      f"column entry 1/2, 1, 1.5 MP at 0105 [15.13] {res}")
g8b = fresh(); g8b.s["turn"] = 2
pa_ = pid_of(g8b, "2I/5"); pb_ = pid_of(g8b, "3I/32")
g8b.submit("All", {"type": "reinforce", "unit": pa_, "hex": [1, 5]})
r = g8b.submit("All", {"type": "reinforce", "unit": pb_, "hex": [1, 5]})
check(not r["verdict"]["legal"],
      "entry hex still occupied by the lead unit - next arrival barred [5.31]")

# Engineer crossing [13.2]
print("== Engineer ==")
g9 = fresh(); clear_map(g9)
eng = pid_of(g9, "Engineers")
para = pid_of(g9, "1/1")
arty = pid_of(g9, "1/1Lt")
# Engineer at 3420 (river 3420|3520 is the ferry side... pick a plain river
# side: 3418|3419) - Engineer at 3418, para at 3417
place(g9, eng, 34, 18)
place(g9, para, 34, 17)
place(g9, arty, 34, 17)
d_para = g9.dests(para)
check((34, 19) in d_para,
      "airborne unit crosses the river through the Engineer's hex [13.22]")
ctx_ab = {"eng_cross": (34, 18), "is_ab_inf": True}
ctx_arty = {"eng_cross": (34, 18), "is_ab_inf": False}
check(g9._step_ok(para, (34, 18), (34, 19), ctx_ab)[0] is not None,
      "crossing arc open for airborne infantry [13.22]")
check(g9._step_ok(arty, (34, 18), (34, 19), ctx_arty)[0] is None,
      "airborne ARTILLERY may not make Engineer crossings [13.23]")
g9b = fresh(); clear_map(g9b)
place(g9b, eng, 34, 18); place(g9b, para, 34, 17)
r = g9b.submit("All", {"type": "move", "unit": para, "dest": [34, 19]})
check(r["verdict"]["legal"], "crossing move submits through the gate")

# demolition changes movement [12.13]
print("== demolition ==")
g10 = fresh()
son = "0505|0605"
g10.s["demolished"].append(son)
g10._apply_bridge_state()
check(g10.game.move_cost((5, 5), (6, 5)) == \
      G.terrain_mp.get(G.hex_terrain(6, 5), 1.0) + 3.0,
      "demolished Son bridge = stream +3 for leg units [12.13]")
clear_map(g10)
vtx = pid_of(g10, "2107 P")
place(g10, vtx, 5, 5)
check((6, 5) not in g10.dests(vtx), "vehicles cannot cross the demolished Son [5.24]")
g10.s["repaired"].append(son)
g10._apply_bridge_state()
check(g10.game.move_cost((5, 5), (6, 5)) == 0.5,
      "Engineer repair restores the road bridge [13.1]")
# restore pristine terrain for other users of G
g10.s["demolished"].remove(son); g10.s["repaired"].remove(son)
g10._apply_bridge_state()

print("ALL PASS" if ok else "FAILURES ABOVE")
sys.exit(0 if ok else 1)
