import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "engine"))
import gamespec  # noqa: E402
import verify_game  # noqa: E402
from naw import NawGame  # noqa: E402

G = gamespec.Game(HERE)
SCEN = os.path.join(HERE, "scenario_2nd_ed.json")
CAT = json.load(open(SCEN, encoding="utf-8"))
ok = True


def check(cond, msg):
    global ok
    print(("PASS  " if cond else "FAIL  ") + msg)
    ok = ok and bool(cond)


def fresh(seed=42):
    return NawGame(G, SCEN, tempfile.mkdtemp(), seed=seed)


def hx(s):
    return int(s[:2]), int(s[2:])


def hn(h):
    return f"{h[0]:02d}{h[1]:02d}"


def place(g, pid, h):
    e = g.catalog[str(pid)]
    g.s["units"][str(pid)] = {"pid": str(pid), "slot": e["slot"], "name": e["name"], "side": e["side"], "col": h[0], "row": h[1]}
    g.s["pool"].pop(str(pid), None)


def to_allied_turn(g, turn):
    while not (g.s["turn"] == turn and g.s["mover"] == "Al" and g.s["phase"] == "movement"):
        for pid in g.due_reserve(g.s["mover"]):
            eh = g.entry_hexes(pid)
            if eh:
                g.submit(g.s["mover"], {"type": "reinforce", "unit": pid, "hex": list(sorted(eh)[0])})
        g.submit(g.s["mover"], {"type": "end_movement"})
        g.submit(g.s["mover"], {"type": "end_phase"})


PR = [u["id"] for u in CAT["reserve"]]
FR = [u["id"] for u in CAT["units"] if u["side"] == "Fr"]
AL = [u["id"] for u in CAT["units"] if u["side"] == "Al"]

print("== Prussian reinforcement (REI-01..07) ==")
g = fresh()
check(set(g.s["pool"]) == set(PR) and all(g.s["pool"][p] == 2 for p in PR) and not any(p in g.s["units"] for p in PR),
      "nine Prussians staged OFF the map, due Game-Turn 2 [REI-01; NAW2-OR-1 off-map staging]")
r = g.submit("Fr", {"type": "reinforce", "unit": PR[0], "hex": [27, 5]})
check(not r["verdict"]["legal"], "French cannot bring on Prussians [REI-01]")
g.submit("Fr", {"type": "end_movement"})
g.submit("Fr", {"type": "end_phase"})
r = g.submit("Al", {"type": "reinforce", "unit": PR[0], "hex": [27, 5]})
check(not r["verdict"]["legal"] and "REI-01" in r["verdict"]["reasons"][0], "Game-Turn 1: Prussians may not enter yet [REI-01]")
r = g.submit("Al", {"type": "end_movement"})
check(r["verdict"]["legal"], "Game-Turn 1 Allied movement closes without Prussians")
g.submit("Al", {"type": "end_phase"})
g.submit("Fr", {"type": "end_movement"})
g.submit("Fr", {"type": "end_phase"})
check(g.s["turn"] == 2 and g.s["mover"] == "Al", "at the Allied Movement Phase of Game-Turn 2")
r = g.submit("Al", {"type": "end_movement"})
check(not r["verdict"]["legal"] and "REI-06" in r["verdict"]["reasons"][0], "end_movement REFUSED while due Prussians can still enter [REI-06]")
eh = g.entry_hexes(PR[0])
check(all(c == 27 for c, _ in eh) and len(eh) == 18 and all(G.hex_terrain(*h) != "woods" for h in eh),
      f"entry hexes = column 27 minus the 4 Woods hexes = 18 on an empty edge ({len(eh)}) [REI-02/MOV-16]")
r = g.submit("Al", {"type": "reinforce", "unit": PR[0], "hex": [26, 5]})
check(not r["verdict"]["legal"] and "REI-02" in r["verdict"]["reasons"][0], "column 26 is not the East edge [REI-02]")
r = g.submit("Al", {"type": "reinforce", "unit": PR[0], "hex": [27, 9]})
check(not r["verdict"]["legal"], "Woods hex 2709 refused [MOV-16]")
r = g.submit("Al", {"type": "reinforce", "unit": PR[0], "hex": [27, 5]})
check(r["verdict"]["legal"] and PR[0] in g.s["units"] and PR[0] not in g.s["pool"] and g.s["moved"][PR[0]] == 1,
      "Prussian enters at 2705 for 1 MP [REI-02/REI-03]")
lm = g.legal_moves(PR[0])
check(lm["can_act"] and lm["budget"] == g.stats(PR[0])["ma"] - 1 and lm["dests"], f"it may still move with MA-1 = {lm['budget']} this turn [REI-04]")
r = g.submit("Al", {"type": "reinforce", "unit": PR[0], "hex": [27, 6]})
check(not r["verdict"]["legal"], "a unit cannot enter twice [REI-01]")
r = g.submit("Al", {"type": "reinforce", "unit": PR[1], "hex": [27, 5]})
check(not r["verdict"]["legal"], "entry onto the hex a friend occupies refused [MOV-09]")
place(g, FR[0], hx("2707"))
r = g.submit("Al", {"type": "reinforce", "unit": PR[1], "hex": [27, 7]})
check(not r["verdict"]["legal"], "enemy-occupied edge hex refused [MOV-08]")
r = g.submit("Al", {"type": "reinforce", "unit": PR[1], "hex": [27, 8]})
check(not r["verdict"]["legal"] and "7.2" in r["verdict"]["reasons"][0], "edge hex in enemy ZOC refused [SPI 1979 7.2, NAW2-OR-4 A]")
r = g.submit("Al", {"type": "reinforce", "unit": PR[1], "hex": [27, 3]})
check(r["verdict"]["legal"], "a free edge hex accepted")
for pid in PR[2:]:
    eh = g.entry_hexes(pid)
    g.submit("Al", {"type": "reinforce", "unit": pid, "hex": list(sorted(eh)[0])})
r = g.submit("Al", {"type": "end_movement"})
check(r["verdict"]["legal"] and not g.s["pool"], "all nine on: Allied movement closes; pool empty")
lm = g.legal_moves(PR[0])
g.submit("Al", {"type": "end_phase"})
g.submit("Fr", {"type": "end_movement"})
g.submit("Fr", {"type": "end_phase"})
r = g.submit("Al", {"type": "exit", "unit": PR[0], "via": [3, 1]})
check(not r["verdict"]["legal"], "Prussians may never leave the map [REI-07/VIC-12]")

g = fresh()
to_allied_turn(g, 2)
g.s["units"] = {}
for i, pid in enumerate(FR[:22]):
    place(g, pid, (27, i + 1))
check(all(g.entry_hexes(p) == {} for p in PR), "every East-edge hex enemy-occupied: no legal entry hex")
r = g.submit("Al", {"type": "end_movement"})
check(r["verdict"]["legal"], "entry physically impossible: end_movement accepted, Prussians wait [REI-06 read with NAW2-OR-4 A]")
check(all(g.s["pool"][p] == 2 for p in PR), "they stay due (enter at the first later phase they can)")

print("== loss ledgers, victory, demoralization ==")
g = fresh()
ev = g._eliminate([AL[0]], "test")
cs = g.stats(AL[0])["att"]
check(g.s["losses"]["Al"] == cs and g.s["losses"]["Fr"] == 0 and AL[0] in g.s["dead"] and AL[0] not in g.s["units"], f"eliminating an Allied {cs}-point unit adds {cs} to the Allied ledger [VIC-05]")
g = fresh()
g.s["pool"] = {}
place(g, PR[0], hx("2705"))
g._eliminate([PR[0]], "test")
check(g.s["losses"]["Al"] == g.stats(PR[0])["att"], "Prussian losses count as Allied losses [REI-05]")
g = fresh()
place(g, FR[0], hx("0301"))
g.submit("Fr", {"type": "exit", "unit": FR[0], "via": [3, 1]})
check(g.s["losses"]["Fr"] == 0 and len(g.s["exited"]) == 1, "an exited French unit is not a French loss [VIC-06]")

g = fresh()
tot = 0
for pid in FR:
    if tot >= 40:
        break
    tot += g.stats(pid)["att"]
    g._eliminate([pid], "test")
check(g.s["over"] and g.s["winner"] == "Al" and g.s["first_forty"] == "Al", f"forty French points destroyed first ({tot}) -> Allied win, immediately [VIC-03/VIC-07]")

g = fresh()
tot = 0
for pid in AL:
    if tot >= 40:
        break
    tot += g.stats(pid)["att"]
    ev = g._eliminate([pid], "test")
check(not g.s["over"] and g.s["demoralized"] and g.s["first_forty"] == "Fr" and any("demoralized" in e for e in ev),
      f"forty Allied points destroyed ({tot}) with no exits -> game continues, Allies DEMORALIZED [DEM-01/DEM-02]")
raw = g.odds_column(8, 4)
col, note = g.demoralization_shift("Al", raw)
check(raw == "2:1" and col == "1:1", "demoralized Allied attack 2:1 -> 1:1 [DEM-06]")
col, note = g.demoralization_shift("Fr", raw)
check(col == "3:1", "French attack 2:1 -> 3:1 while the Allies are demoralized [DEM-07]")
col, note = g.demoralization_shift("Al", "1:5")
check(col == "1:5" and "OR-19" in note, "Allied attack already at 1:5 stays at 1:5 (clamp) [NAW2-OR-19 A]")
col, note = g.demoralization_shift("Fr", "6:1")
check(col == "6:1", "French attack already at 6:1 stays at 6:1 (clamp) [NAW2-OR-19 A]")
g.s["phase"] = "combat"
d = next(p for p in AL if p in g.s["units"])
du = g.unit(d)
a = next(p for p in FR if p in g.s["units"])
g.unit(a)["col"], g.unit(a)["row"] = G.neighbors(du["col"], du["row"])[0]
legal, reasons, meta = g.battle_check("Fr", [a], [d])
check(legal and meta["column"] == g.shift_column(meta["raw_column"], 1) and "DEMORALIZED" in reasons[0], "battle_check applies the shift and says so in the verdict")
tot2 = 0
for pid in FR:
    if pid not in g.s["units"] or tot2 >= 40:
        continue
    tot2 += g.stats(pid)["att"]
    g._eliminate([pid], "test")
check(not g.s["over"] and g.s["demoralized"] and g.s["winner"] is None, "forty French points AFTER demoralization: no Allied win, demoralization stands [DEM-09]")
g.s["turn"] = 11
ev = g._game_end()
check(g.s["over"] and g.s["winner"] == "draw", "end of Game-Turn 10 while demoralized and under seven exits -> DRAW [VIC-04/DEM-04]")

g = fresh()
for i, pid in enumerate(FR[:7]):
    place(g, pid, (i + 1, 1))
    g.submit("Fr", {"type": "exit", "unit": pid, "via": [i + 1, 1]})
check(len(g.s["exited"]) == 7 and not g.s["over"], "seven exits alone do not win [VIC-01 needs forty points too]")
tot = 0
for pid in AL:
    if tot >= 40:
        break
    tot += g.stats(pid)["att"]
    g._eliminate([pid], "test")
check(g.s["over"] and g.s["winner"] == "Fr" and not g.s["demoralized"], "forty Allied points with seven already exited -> French win at once, no demoralization [VIC-01/VIC-07/DEM-01]")

g = fresh()
tot = 0
for pid in AL:
    if tot >= 40:
        break
    tot += g.stats(pid)["att"]
    g._eliminate([pid], "test")
check(g.s["demoralized"] and not g.s["over"], "demoralized first ...")
for i, pid in enumerate([p for p in FR if p in g.s["units"]][:7]):
    place(g, pid, (i + 1, 1))
    g.submit("Fr", {"type": "exit", "unit": pid, "via": [i + 1, 1]})
check(g.s["over"] and g.s["winner"] == "Fr", "... then the seventh exit wins for France [VIC-11: exits may come after the forty points]")

FR3 = next(p for p in FR if G.stats(g.catalog[p]["slot"])[0] >= 3)
g = fresh()
g.s["losses"] = {"Fr": 37, "Al": 38}
g._eliminate([AL[0], FR3], "simultaneous EX")
check(g.s["over"] and g.s["first_forty"] == "both" and g.s["winner"] == "Al", "both ledgers cross forty in one elimination step with fewer than seven exits -> Allied win [VIC-14]")
g = fresh()
g.s["losses"] = {"Fr": 37, "Al": 38}
g.s["exited"] = [p for p in FR if p != FR3][:7]
g._eliminate([AL[0], FR3], "simultaneous EX")
check(g.s["over"] and g.s["winner"] == "Fr", "same with seven already exited -> French win [VIC-14]")

print("== replay ==")
g = fresh(seed=9)
to_allied_turn(g, 3)
okv, msg = verify_game.verify(HERE, g.log_path)
check(okv, f"log with reinforcement entries replays: {msg[:90]}")

print("ALL PASS" if ok else "FAILURES ABOVE")
sys.exit(0 if ok else 1)
