"""validate_gate.py - Westwall: Arnhem Tier-1 gate evidence.

Two layers:
1. REPLAYED SESSIONS - multi-turn games driven only through submit(); every
   session is replayed byte-exact through engine/verify_game.py (verdicts,
   dice, state hashes).
2. STAGED PROBES - rule corners on staged positions (validator teleports,
   propose()-level, no replay claimed).

Covers: turn sequence [4.1], arrival schedule + withholding [15.0/15.23],
airborne drops [15.31-15.33], column entries [15.13], illegal-action
rejections, bridge demolition [12.x] with the engine die, German exit +
same-edge re-entry [15.4], GSP schedule [18.16/9.14], LOC scoring [17.3x],
Engineer canal repair [13.1].
"""
import json, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "engine"))
import gamespec                                 # noqa: E402
from westwall import WestwallGame              # noqa: E402
import verify_game                              # noqa: E402

G = gamespec.Game(HERE)
SCEN = os.path.join(HERE, "scenario_historical.json")
ok = True


def check(cond, msg):
    global ok
    print(("PASS  " if cond else "FAIL  ") + msg)
    ok = ok and cond


def fresh(seed):
    tmp = tempfile.mkdtemp()
    return WestwallGame(G, SCEN, tmp, seed=seed), tmp


def pid_of(gate, desig):
    return next(p for p, e in gate.catalog.items() if e.get("desig") == desig)


def sub(gate, side, action, want=True, why=""):
    r = gate.submit(side, action)
    check(r["verdict"]["legal"] == want,
          (why or f"{action['type']}") + f" -> {r['verdict']['reasons'][:1]}")
    return r


# =============================================================== session A
print("== session A: GT1-GT3 sequencing, drops, columns, GSP ==")
g, tmp = fresh(seed=7)
check(g.s["turn"] == 1 and g.s["mover"] == "All" and g.s["phase"] == "movement",
      "GT1 opens in the Allied Movement Phase [4.1/18.17]")
check(g.s["gsp_left"] == 0, "GT1 GSP = 0 [18.16]")

# illegal probes (rejected actions never touch state; replay includes them)
sub(g, "Ger", {"type": "move", "unit": pid_of(g, "Krft"), "dest": [36, 22]},
    want=False, why="German acts in the Allied player-turn [4.1]")
sub(g, "All", {"type": "move", "unit": pid_of(g, "Krft"), "dest": [36, 22]},
    want=False, why="moving an enemy unit")
sub(g, "All", {"type": "reinforce", "unit": pid_of(g, "10/4"), "hex": [38, 17]},
    want=False, why="GT2 drop refused on GT1 [15.0]")
sub(g, "All", {"type": "exit", "unit": pid_of(g, "Krft")},
    want=False, why="only the German player exits [15.4]")

# GT1 airborne drops: spread one per hex around each target [15.31],
# programmatically avoiding hexes adjacent to German units (mandatory combat
# 7.11 is exercised in validate_combat, not here)
gpos = {(u["col"], u["row"]) for u in g._live("Ger")}
gadj = set()
for h in gpos:
    gadj |= set(G.neighbors(*h)) | {h}
used = set()
GT1 = [("1/502", "1004"), ("2/502", "1004"), ("3/502", "1004"),
       ("1/506", "0804"), ("2/506", "0804"), ("3/506", "0804"),
       ("1/501", "1308"), ("2/501", "1308"), ("3/501", "1308"),
       ("1/508", "2223"), ("2/508", "2223"), ("3/508", "2223"),
       ("1/505", "2023"), ("2/505", "2023"), ("3/505", "2023"),
       ("1/504", "2117"), ("2/504", "2117"), ("3/504", "2117"),
       ("1/1", "3719"), ("2/1", "3719"), ("3/1", "3719"),
       ("2S/1", "3718"), ("7K/1", "3718"), ("1B/1", "3718"),
       ("1/82", "2223"), ("1/1Lt", "3718")]
first_drop = None
for desig, tstr in GT1:
    tgt = (int(tstr[:2]), int(tstr[2:]))
    ring = [tgt] + [n for n in G.neighbors(*tgt) if G.on_map(*n)]
    h = next(x for x in ring if x not in used and x not in gadj)
    used.add(h)
    if first_drop is None:
        first_drop = (desig, h)
    sub(g, "All", {"type": "reinforce", "unit": pid_of(g, desig),
                   "hex": list(h)}, why=f"GT1 drop {desig} at {h} [15.31/18.13]")
    if g.s["pending"] and g.s["pending"]["awaiting"] == "demolition":
        # dropping next to a canal/rail bridge triggers the German option
        # immediately, no matter what the phase [12.11] - decline here
        bs = g.s["pending"]["bridges"]
        sub(g, "Ger", {"type": "demolition", "attempt": {k: False for k in bs}},
            why=f"demolition offer at the drop zone declined {bs} [12.11]")
occupied_drop = list(used)[0]
check(g.budget(pid_of(g, "1/502")) == 3, "drop-turn MA 3 [15.32]")
# occupied-hex landing refused [15.33]
sub(g, "All", {"type": "reinforce", "unit": pid_of(g, "2/82"),
               "hex": [10, 4]},
    want=False, why="landing on an occupied hex refused [15.31/15.33]")
# a dropped unit moves its 3 MP
p502 = pid_of(g, "1/502")
u502 = g.unit(p502)
dd = g.dests(p502)
if dd:
    dest = sorted(dd)[0]
    sub(g, "All", {"type": "move", "unit": p502, "dest": list(dest)},
        why="dropped unit moves within MA 3 [15.32]")
    sub(g, "All", {"type": "move", "unit": p502, "dest": list(dest)},
        want=False, why="a unit moves once per phase [5.15]")
sub(g, "All", {"type": "end_movement"})
sub(g, "All", {"type": "end_phase"}, why="no contacts - combat phase closes")
check(g.s["mover"] == "Ger", "German player-turn follows [4.1]")

# German GT1: schedule + withholding [15.23]
sub(g, "Ger", {"type": "reinforce", "unit": pid_of(g, "1/vT"), "hex": [39, 10]},
    why="1/vT enters on the 3907-3916 edge [18.15]")
sub(g, "Ger", {"type": "reinforce", "unit": pid_of(g, "1/9SS"), "hex": [39, 25]},
    why="1/9SS enters at 3925 [18.15]")
sub(g, "Ger", {"type": "reinforce", "unit": pid_of(g, "1/9SS"), "hex": [39, 25]},
    want=False, why="already on the map")
sub(g, "Ger", {"type": "reinforce", "unit": pid_of(g, "1/59"), "hex": [10, 1]},
    want=False, why="1/59 entry is 0701-0901, not 1001 [18.15]")
sub(g, "Ger", {"type": "reinforce", "unit": pid_of(g, "Hnke"), "hex": [3, 26]},
    want=False, why="Hnke is due GT3 [15.0]")
# 2/vT withheld this turn [15.23]
sub(g, "Ger", {"type": "end_movement"})
sub(g, "Ger", {"type": "end_phase"})
check(g.s["turn"] == 2 and g.s["mover"] == "All", "GT2 begins [4.1]")
check(g.s["gsp_left"] == 3, "GT2 GSP = 3 [18.16]")

# withheld 2/vT enters on GT2 at its scheduled edge [15.23/15.24]
# (German turn - first the Allied GT2)
sub(g, "All", {"type": "reinforce", "unit": pid_of(g, "2I/5"), "hex": [1, 5]},
    why="XXX Corps column lead enters 0105 [18.14]")
sub(g, "All", {"type": "move", "unit": pid_of(g, "2I/5"), "dest": [3, 4]},
    why="lead unit drives up the road")
sub(g, "All", {"type": "reinforce", "unit": pid_of(g, "3I/32"), "hex": [1, 5]},
    why="second column unit [15.13]")
ring = [(38, 17)] + [n for n in G.neighbors(38, 17) if G.on_map(*n)]
h104 = next(x for x in ring if x not in {(u["col"], u["row"]) for u in g._live()})
sub(g, "All", {"type": "reinforce", "unit": pid_of(g, "10/4"), "hex": list(h104)},
    why=f"GT2 drop 10/4 at {h104} within one hex of 3817 [18.13]")
sub(g, "All", {"type": "end_movement"})
sub(g, "All", {"type": "end_phase"})
sub(g, "Ger", {"type": "reinforce", "unit": pid_of(g, "2/vT"), "hex": [39, 12]},
    why="withheld 2/vT enters on GT2 [15.23]")
sub(g, "Ger", {"type": "end_movement"})
sub(g, "Ger", {"type": "end_phase"})
check(g.s["turn"] == 3 and g.s["gsp_left"] == 7, "GT3: GSP 7, unused GT2 GSP lost "
                                                 "[18.16/9.14]")
okA, msgA = verify_game.verify(HERE, os.path.join(tmp, "game_westwall-arnhem.log.jsonl"))
check(okA, f"session A replays byte-exact: {msgA}")

# =============================================================== session B
print("== session B: demolition + German exit/re-entry ==")
g, tmp = fresh(seed=11)
sub(g, "All", {"type": "end_movement"})
sub(g, "All", {"type": "end_phase"})
# German: walk Grsn (0702, MA 12) to the west edge and exit
sub(g, "Ger", {"type": "move", "unit": pid_of(g, "Grsn"), "dest": [7, 1]},
    why="Grsn reaches west-edge hex 0701")
sub(g, "Ger", {"type": "exit", "unit": pid_of(g, "Grsn")},
    why="Grsn exits the west edge on remaining MP [15.4/15.41]")
check(pid_of(g, "Grsn") not in g.s["units"], "exited unit leaves the map [15.42]")
sub(g, "Ger", {"type": "end_movement"})
sub(g, "Ger", {"type": "end_phase"})
# GT2 Allied: race armor toward the Son bridge (0505|0605)
sub(g, "All", {"type": "reinforce", "unit": pid_of(g, "2I/5"), "hex": [1, 5]})
r = g.submit("All", {"type": "move", "unit": pid_of(g, "2I/5"), "dest": [5, 5]})
check(r["verdict"]["legal"], "armor reaches 0505 (adjacent to the Son bridge)")
check(g.s["pending"] and g.s["pending"]["awaiting"] == "demolition"
      and "0505|0605" in g.s["pending"]["bridges"],
      "Son demolition offer triggers at first Allied adjacency [12.11]")
sub(g, "All", {"type": "end_movement"}, want=False,
    why="pending demolition blocks other actions")
r = sub(g, "Ger", {"type": "demolition", "attempt": {"0505|0605": True}},
        why="German attempts the Son demolition [12.12]")
res = r["result"][0]
demolished = res["result"] == "DEMOLISHED"
check(res["die"] in (1, 2, 3, 4, 5, 6), f"engine-owned die rolled ({res['die']})")
check(demolished == (res["die"] <= 2), "die 1-2 demolishes [12.12]")
check(("0505|0605" in g.s["demolished"]) == demolished, "demolition state recorded")
check("0505|0605" in g.s["offered"], "one attempt ever [12.11/12.14]")
sub(g, "All", {"type": "end_movement"})
sub(g, "All", {"type": "end_phase"})
# German GT2: Grsn re-enters on the same (west) edge [15.42]
grsn = pid_of(g, "Grsn")
check(g.s["pool"].get(grsn) == 2, "exited Grsn is available from GT2 [15.42]")
sub(g, "Ger", {"type": "reinforce", "unit": grsn, "hex": [39, 12]},
    want=False, why="re-entry only on the SAME edge segment [15.42]")
sub(g, "Ger", {"type": "reinforce", "unit": grsn, "hex": [12, 1]},
    why="Grsn re-enters on the west edge [15.42]")
sub(g, "Ger", {"type": "end_movement"})
sub(g, "Ger", {"type": "end_phase"})
okB, msgB = verify_game.verify(HERE, os.path.join(tmp, "game_westwall-arnhem.log.jsonl"))
check(okB, f"session B replays byte-exact: {msgB}")

# =============================================================== session C
print("== session C: LOC scoring at the end of the German player-turn ==")
g, tmp = fresh(seed=13)
# drop 1 Para Bde around Arnhem, in LOC range of DZ 1 (3919)
for desig, h in {"1/1": [37, 18], "2/1": [36, 19], "3/1": [36, 18]}.items():
    sub(g, "All", {"type": "reinforce", "unit": pid_of(g, desig), "hex": h})
# and 1/504 FAR from DZ 82 (2323): drop at 2117-ring then it cannot trace > 7?
# (2117 ring is within 7 of 2323 - use movement later; here test the pass case)
sub(g, "All", {"type": "end_movement"})
sub(g, "All", {"type": "end_phase"})
vp0 = dict(g.s["vp"])
sub(g, "Ger", {"type": "end_movement"})
sub(g, "Ger", {"type": "end_phase"})
check(g.s["vp"]["Ger"] == vp0["Ger"],
      "airborne units within 7 of their DZ: no LOC VP for Germany [17.32/17.35]")
okC, msgC = verify_game.verify(HERE, os.path.join(tmp, "game_westwall-arnhem.log.jsonl"))
check(okC, f"session C replays byte-exact: {msgC}")

# =============================================================== staged probes
print("== staged probes (propose level) ==")
g, _ = fresh(seed=17)


def place(gate, pid, c, r):
    e = gate.catalog[str(pid)]
    gate.s["units"][str(pid)] = {"pid": str(pid), "slot": e["slot"],
                                 "side": e["side"], "col": c, "row": r}
    gate.s["pool"].pop(str(pid), None)


# LOC: an airborne unit 8+ hexes from its DZ fails; German gets 3 VP
g.s["units"] = {p: u for p, u in g.s["units"].items()
                if g.cls(p) == "dz" or u["side"] == "Ger"}
p504 = pid_of(g, "1/504")
place(g, p504, 30, 20)         # ~8+ hexes from DZ 82 at 2323
loc = g._loc_status()
check(loc.get(p504) is False, "airborne LOC fails beyond 7 hexes to the DZ [17.32]")
place(g, p504, 22, 21)         # 2 hexes from 2323
loc = g._loc_status()
check(loc.get(p504) is True, "airborne LOC ok near the DZ [17.32]")
# ground LOC: XXX corps unit on the first corridor road hex traces to 0105
p5 = pid_of(g, "2I/5")
place(g, p5, 2, 4)             # 0204, the road hex out of 0105
loc = g._loc_status()
check(loc.get(p5) is True, "ground LOC along the corridor road at 0204 [17.31]")
# a ground unit cut off across the rivers has no LOC
place(g, p5, 39, 20)
loc = g._loc_status()
check(loc.get(p5) is False,
      "ground unit north of the Rijn without a road trace has no LOC [17.31/17.34]")
# Engineer repair staging [13.1]
g2, _ = fresh(seed=19)
son = "0505|0605"
g2.s["demolished"].append(son)
g2._apply_bridge_state()
eng = pid_of(g2, "Engineers")
place(g2, eng, 5, 5)
g2.s["mover"] = "Ger"
g2.s["phase"] = "combat"
g2.s["eng_start"] = [5, 5]
ev = g2._german_turn_end_scoring()
check(son in g2.s["repaired"] and any(e.get("bridge_repaired") == son for e in ev),
      "Engineer adjacent + stationary + EZOC-free repairs the canal bridge [13.1]")
g2.s["repaired"].remove(son)
g2.s["demolished"].remove(son)
g2._apply_bridge_state()
# rail bridges are never repaired [12.16]
g3, _ = fresh(seed=23)
rail = "1206|1307"
g3.s["demolished"].append(rail)
g3._apply_bridge_state()
place(g3, pid_of(g3, "Engineers"), 12, 6)
g3.s["eng_start"] = [12, 6]
ev = g3._german_turn_end_scoring()
check(rail not in g3.s["repaired"], "railroad bridges are never repaired [12.16]")
g3.s["demolished"].remove(rail)
g3._apply_bridge_state()

print("ALL PASS" if ok else "FAILURES ABOVE")
sys.exit(0 if ok else 1)
