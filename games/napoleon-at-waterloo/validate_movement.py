import json
import os
import random
import sys
import tempfile
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "engine"))
import gamespec  # noqa: E402
import verify_game  # noqa: E402
from naw import NawGame  # noqa: E402
sys.path.insert(0, HERE)
import naw_drive as D  # noqa: E402

G = gamespec.Game(HERE)
SCEN = os.path.join(HERE, "scenario_2nd_ed.json")
HG = json.load(open(os.path.join(HERE, "ingest", "hexgraph_2nd_ed.json"), encoding="utf-8"))["hexes"]
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


def place(gate, pid, h):
    e = gate.catalog[str(pid)]
    gate.s["units"][str(pid)] = {"pid": str(pid), "slot": e["slot"], "side": e["side"], "col": h[0], "row": h[1]}
    gate.s["pool"].pop(str(pid), None)


def clear(gate):
    gate.s["units"] = {}
    gate.s["done"] = []


def fr(ma):
    return next(pid for pid, e in sorted(G_CAT.items()) if e["side"] == "Fr" and e["stats"]["ma"] == ma)


G_CAT = {u["id"]: u for u in json.load(open(SCEN, encoding="utf-8"))["units"]}


def oracle_dests(gate, pid):
    u = gate.unit(pid)
    side = u["side"]
    enemy = {hn((v["col"], v["row"])) for v in gate.s["units"].values() if v["side"] != side}
    friends = {hn((v["col"], v["row"])) for v in gate.s["units"].values() if v["side"] == side and v["pid"] != pid}
    ezoc = set()
    for e in enemy:
        ezoc |= {n for n in HG[e]["neighbours"].values() if n}
    start = hn((u["col"], u["row"]))
    ma = gate.stats(pid)["ma"]
    if start in ezoc:
        return {}
    dist = {start: 0}
    q = deque([start])
    while q:
        cur = q.popleft()
        if cur != start and cur in ezoc:
            continue
        if dist[cur] >= ma:
            continue
        for d, nb in HG[cur]["neighbours"].items():
            if not nb or nb in dist or nb in enemy:
                continue
            if HG[nb]["terrain"] == "woods":
                continue
            if HG[cur]["terrain"] == "woods_road" and d not in HG[cur]["road_sides"]:
                continue
            back = HG["0101"]["neighbours"] and {"N": "S", "S": "N", "NE": "SW", "SW": "NE", "SE": "NW", "NW": "SE"}[d]
            if HG[nb]["terrain"] == "woods_road" and back not in HG[nb]["road_sides"]:
                continue
            dist[nb] = dist[cur] + 1
            q.append(nb)
    dist.pop(start)
    occ = {hn((v["col"], v["row"])): v["pid"] for v in gate.s["units"].values() if v["side"] == side and v["pid"] != pid}

    def can_step_off(b, h):
        if b in gate.s["done"] or h in ezoc:
            return False
        after = (friends - {start}) | {h}
        for d, nb in HG[h]["neighbours"].items():
            if not nb or nb in enemy or nb in after or HG[nb]["terrain"] == "woods":
                continue
            if HG[h]["terrain"] == "woods_road" and d not in HG[h]["road_sides"]:
                continue
            back = {"N": "S", "S": "N", "NE": "SW", "SW": "NE", "SE": "NW", "NW": "SE"}[d]
            if HG[nb]["terrain"] == "woods_road" and back not in HG[nb]["road_sides"]:
                continue
            return True
        return False
    return {h: c for h, c in dist.items() if h not in occ or can_step_off(occ[h], h)}


def bring_prussians(g):
    n = 0
    for pid in g.due_reserve(g.s["mover"]):
        eh = g.entry_hexes(pid)
        if eh:
            r = g.submit(g.s["mover"], {"type": "reinforce", "unit": pid, "hex": list(sorted(eh)[0])})
            n += r["verdict"]["legal"]
    return n


print("== turn structure ==")
g = fresh()
check(g.s["mover"] == "Fr" and g.s["phase"] == "movement" and g.s["turn"] == 1, "game opens with the French Movement Phase of Game-Turn 1 [SET-04/SEQ-02]")
r = g.submit("Al", {"type": "move", "unit": "201", "dest": [4, 11]})
check(not r["verdict"]["legal"] and "SEQ-08" in r["verdict"]["reasons"][0], "Allied move during the French Player-Turn refused [SEQ-08]")
r = g.submit("Fr", {"type": "end_phase"})
check(not r["verdict"]["legal"], "end_phase refused during the Movement Phase")
r = g.submit("Fr", {"type": "end_movement"})
check(r["verdict"]["legal"] and g.s["phase"] == "combat", "end_movement opens the French Combat Phase [SEQ-03]")
r = g.submit("Fr", {"type": "move", "unit": "101", "dest": [6, 13]})
check(not r["verdict"]["legal"] and "SEQ-07" in r["verdict"]["reasons"][0], "movement refused in the Combat Phase [SEQ-07]")
D.discharge_combat(g)
r = g.submit("Fr", {"type": "end_phase"})
check(r["verdict"]["legal"] and g.s["mover"] == "Al" and g.s["phase"] == "movement" and g.s["turn"] == 1, "end_phase passes to the Allied Movement Phase of the same Game-Turn [SEQ-04]")
for _ in range(19):
    D.end_player_turn(g)
check(g.s["over"] and g.s["winner"] == "draw" and g.s["turn"] == 11, "ten Game-Turns then the game ends [SEQ-01/SEQ-05]; with no losses it is a draw [VIC-04]")
r = g.submit("Fr", {"type": "end_movement"})
check(not r["verdict"]["legal"], "no action after the game is over")

print("== movement points, paths, terrain (gate vs independent hexgraph oracle) ==")
g = fresh()
mism = 0
tested = 0
for pid in list(g.s["units"]):
    u = g.unit(pid)
    if u["side"] != "Fr":
        continue
    d1 = {hn(h): c for h, c in g.dests(pid).items()}
    d2 = oracle_dests(g, pid)
    tested += 1
    if d1 != d2:
        mism += 1
        if mism < 3:
            print("   mismatch", pid, u["slot"], sorted(set(d1) ^ set(d2))[:8])
check(mism == 0 and tested == 26, f"at-start position: gate dests == oracle for all 26 French units ({mism} mismatches)")
rng = random.Random(7)
mism = 0
tot = 0
allh = sorted(h for h, v in HG.items() if v["terrain"] != "woods")
for trial in range(120):
    g = fresh(seed=trial)
    clear(g)
    pids = list(g.catalog)
    rng.shuffle(pids)
    taken = set()
    for pid in pids[:rng.randint(6, 30)]:
        h = rng.choice(allh)
        if h in taken:
            continue
        taken.add(h)
        place(g, pid, hx(h))
    for pid in list(g.s["units"]):
        d1 = {hn(h): c for h, c in g.dests(pid).items()}
        d2 = oracle_dests(g, pid)
        tot += 1
        if d1 != d2:
            mism += 1
            if mism < 3:
                print("   mismatch trial", trial, pid, sorted(set(d1) ^ set(d2))[:8], {k: (d1.get(k), d2.get(k)) for k in list(set(d1) ^ set(d2))[:3]})
check(mism == 0 and tot > 1500, f"random boards: gate dests == oracle on {tot} unit positions ({mism} mismatches) [MOV-02/05/06/07/08/09/10/11/13/15/16/17/18, ZOC-01..08]")

g = fresh()
clear(g)
place(g, "103", hx("1010"))
d = g.dests("103")
ma = g.stats("103")["ma"]
check(all(c == G.hex_distance((10, 10), h) for h, c in d.items()) and all(c <= ma for c in d.values()) and max(d.values()) == ma,
      f"open field: every destination costs exactly its hex distance, none beyond MA {ma} [MOV-02/MOV-05/MOV-15]")
check(not any(G.hex_terrain(*h) == "woods" for h in d), "no Woods hex is ever a destination [MOV-18/TEC row 3]")

print("== Woods/Road hexsides ==")
g = fresh()
clear(g)
place(g, "103", hx("0913"))
check(hx("1014") in g.dests("103"), "1014 (Hougoumont) entered from 0913 across its single road hexside [MOV-16/MOV-17]")
for frm in ("1013", "1015", "1114", "1115", "0914"):
    g = fresh()
    clear(g)
    place(g, "103", hx(frm))
    d = g.dests("103")
    check(d.get(hx("1014")) != 1 and (hx("1014") not in d or d[hx("1014")] >= 2), f"1014 not enterable directly from adjacent {frm} (non-road hexside) - only round through 0913 ({d.get(hx('1014'))} MP) [MOV-17]")
g = fresh()
clear(g)
place(g, "103", hx("1014"))
d = g.dests("103")
check(d.get(hx("0913")) == 1 and all(c >= 2 for h, c in d.items() if h != hx("0913")), "from 1014 the only 1-MP step is back to 0913 - the printed road dead-ends in the hex (N2 verified on the map scan) [MOV-17]")
p4 = fr(4)
g = fresh()
clear(g)
place(g, p4, hx("1503"))
d = g.dests(p4)
check(d.get(hx("1603")) == 1 and d.get(hx("1702")) == 2 and d.get(hx("1701")) == 3 and d.get(hx("1801")) == 4,
      "1503-1603-1702-1701-1801 along the road: 1, 2, 3, 4 MP [MOV-17]")
g = fresh()
clear(g)
place(g, p4, hx("1603"))
d = g.dests(p4)
check(hx("1602") not in d and d.get(hx("1702")) == 1 and d.get(hx("1503")) == 1 and d.get(hx("1701")) == 2 and G.hex_terrain(16, 2) == "woods", "from 1603: 1702 and 1503 (road) 1 MP, 1701 via 1702 2 MP; adjacent 1602 is Woods - never enterable [MOV-17/MOV-18]")
g = fresh()
clear(g)
place(g, "103", hx("1002"))
check(g.dests("103").get(hx("1101")) == 2, "1101 not enterable directly from adjacent 1002 (non-road hexside): via 1102 for 2 MP [MOV-17]")
g = fresh()
clear(g)
place(g, "103", hx("1102"))
check(g.dests("103").get(hx("1101")) == 1, "1101 entered from 1102 along the road [MOV-17]")

print("== stacking, friendly pass-through, enemy hexes ==")
g = fresh()
clear(g)
place(g, "103", hx("1010"))
place(g, "104", hx("1110"))
d = g.dests("103")
check(hx("1110") in d and d[hx("1110")] == 1, "may END its own move on a friendly unit mid-phase [MOV-09 reading A per SPI 1979 4.4; NAW2-OR-2]")
check(hx("1210") in d and d[hx("1210")] == 2, "moves THROUGH the friendly hex [MOV-07]")
r = g.submit("Fr", {"type": "move", "unit": "103", "dest": [11, 10]})
check(r["verdict"]["legal"], "gate accepts the mid-phase stack")
r = g.submit("Fr", {"type": "end_movement"})
check(not r["verdict"]["legal"] and "MOV-09" in r["verdict"]["reasons"][0] and "1110" in r["verdict"]["reasons"][0], "end_movement REFUSED while a hex holds two units, naming the hex [MOV-09]")
r = g.submit("Fr", {"type": "move", "unit": "104", "dest": [12, 10]})
check(r["verdict"]["legal"], "the other unit moves off")
r = g.submit("Fr", {"type": "end_movement"})
check(r["verdict"]["legal"], "un-stacked: end_movement accepted")
g = fresh()
clear(g)
place(g, "103", hx("1010"))
place(g, "104", hx("1110"))
g.s["done"].append("104")
check(hx("1110") not in g.dests("103"), "may NOT end on a friend that has already moved (it could never un-stack - wedge guard) [MOV-09/MOV-19]")
g = fresh()
clear(g)
place(g, "103", hx("0810"))
place(g, "104", hx("1010"))
place(g, "201", hx("1110"))
check(hx("1010") not in g.dests("103"), "may NOT end on a friend that sits in enemy ZOC (it may not move at all) [MOV-09/MOV-13]")
g = fresh()
clear(g)
place(g, "103", hx("1010"))
place(g, "201", hx("1210"))
d = g.dests("103")
check(hx("1210") not in d, "enemy-occupied hex never entered [MOV-08]")
check(hx("1110") in d and hx("1109") in d, "adjacent-to-enemy hexes ARE enterable (entering a ZOC is legal) [ZOC-04]")
check(hx("1310") not in d and hx("1309") not in d, "hexes beyond the enemy ZOC hex are not reachable through it [MOV-11/ZOC-04]")

print("== Zones of Control ==")
g = fresh()
clear(g)
place(g, "103", hx("1010"))
place(g, "201", hx("1110"))
check(g.dests("103") == {} and "MOV-13" in g.legal_moves("103")["reasons"][0], "unit beginning its Movement Phase adjacent to an enemy may not move at all [MOV-13/ZOC-05]")
r = g.submit("Fr", {"type": "move", "unit": "103", "dest": [9, 10]})
check(not r["verdict"]["legal"] and "MOV-13" in r["verdict"]["reasons"][0], "gate refuses it with the citation")
p5 = fr(5)
g = fresh()
clear(g)
place(g, p5, hx("1108"))
d0 = g.dests(p5)
place(g, "201", hx("1110"))
d = g.dests(p5)
check(d.get(hx("1109")) == 1 and hx("1010") in d and hx("1210") in d, "may move INTO the enemy ZOC [ZOC-04]")
check(d0.get(hx("1112")) == 4 and hx("1112") not in d, "must STOP on entering it - 1112 (4 MP without the enemy) is unreachable when every short path crosses the ZOC ring [MOV-10/MOV-11]")
r = g.submit("Fr", {"type": "move", "unit": p5, "dest": [11, 9]})
check(r["verdict"]["legal"] and g.unit(p5)["row"] == 9, "moving into the ZOC accepted and applied")
r = g.submit("Fr", {"type": "move", "unit": p5, "dest": [11, 8]})
check(not r["verdict"]["legal"] and "MOV-19" in r["verdict"]["reasons"][0], "the unit may not be moved again this Player-Turn [MOV-19]")
board = g.rules_board()
z = G.zoc_hexes(board, "Al")
check(len(z) == 6 and all(h in z for h in G.neighbors(11, 10)), "an enemy unit controls exactly its six adjacent hexes [ZOC-01/ZOC-06]")
g = fresh()
clear(g)
place(g, "201", hx("1013"))
z = G.zoc_hexes(g.rules_board(), "Al")
woods_nb = [h for h in G.neighbors(10, 13) if G.hex_terrain(*h) == "woods"]
check(woods_nb and all(h in z for h in woods_nb), f"ZOC is projected into adjacent Woods hexes too (Z.5 trap): {[hn(h) for h in woods_nb]} [ZOC-01]")
g = fresh()
clear(g)
place(g, "103", hx("1010"))
place(g, "104", hx("1110"))
place(g, "105", hx("0910"))
check(hx("0810") in g.dests("103") and hx("1210") in g.dests("103"), "friendly ZOC never inhibits friendly movement [ZOC-03]")

print("== exit ==")
g = fresh()
clear(g)
place(g, "103", hx("0301"))
lm = g.legal_moves("103")
ex = {e["hexnum"]: e["cost"] for e in lm["exits"]}
check(ex.get("0301") == 1 and ex.get("0201") == 2 and ex.get("0101") == 3, f"French unit (MA 3) on exit hex 0301: exit offered for 1 MP, 0201 for 2, 0101 for 3 {ex} [VIC-08/VIC-09]")
r = g.submit("Fr", {"type": "exit", "unit": "103", "via": [3, 1]})
check(r["verdict"]["legal"] and "103" not in g.s["units"] and g.s["exited"] == ["103"], "exit applied: unit off the map, exited ledger 1 [VIC-10]")
r = g.submit("Fr", {"type": "move", "unit": "103", "dest": [3, 2]})
check(not r["verdict"]["legal"], "an exited unit is gone for good [VIC-10]")
g = fresh()
clear(g)
place(g, p4, hx("0304"))
opts = {hn(h): c for h, c in g.exit_options(p4).items()}
check(opts == {"0301": 4}, f"unit at 0304 (MA 4): exit only via 0301 for 3 hexes + 1 = 4 MP; 0201/0401 lie 4 hexes off {opts} [VIC-09/MOV-15]")
check("1201" not in opts and hx("1201") not in g.exit_hexes, "column 12+ of row 01 carries no arrow - not an exit hex [VIC-08]")
r = g.submit("Fr", {"type": "exit", "unit": p4, "via": [3, 3]})
check(not r["verdict"]["legal"] and "VIC-08" in r["verdict"]["reasons"][0], "exit from a non-arrowed hex refused [VIC-08]")
g = fresh()
clear(g)
place(g, p4, hx("0305"))
check(g.exit_options(p4) == {}, "unit at 0305 (MA 4) cannot reach an exit hex AND pay the exit point [VIC-09/MOV-15]")
g = fresh()
clear(g)
place(g, "103", hx("0302"))
place(g, "201", hx("0401"))
check(hx("0301") not in g.exit_options("103") and hx("0301") in g.dests("103"), "exit hex inside an enemy ZOC: the unit may enter it but must stop there - no exit [MOV-10]")
g = fresh()
clear(g)
place(g, "201", hx("0301"))
g.s["mover"] = "Al"
r = g.submit("Al", {"type": "exit", "unit": "201", "via": [3, 1]})
check(not r["verdict"]["legal"] and "VIC-12" in r["verdict"]["reasons"][0], "Allied units may never exit [VIC-12]")
g = fresh()
clear(g)
place(g, "103", hx("1102"))
opts = {hn(h): c for h, c in g.exit_options("103").items()}
check(opts.get("1101") == 2, "exit through Woods/Road hex 1101 from 1102: 1 + 1 = 2 MP (arrow printed in the hex; NAW2-OR-18)")
g = fresh()
clear(g)
place(g, "103", hx("1002"))
opts = {hn(h): c for h, c in g.exit_options("103").items()}
check(opts.get("1101") == 3 and opts.get("1001") == 2, "from 1002: 1101 only via 1102 along the road (3 MP), 1001 direct (2 MP) [MOV-17/VIC-09]")

g = fresh()
clear(g)
place(g, "103", hx("0303"))
place(g, "104", hx("0302"))
g.s["done"].append("104")
opts = {hn(h): c for h, c in g.exit_options("103").items()}
check(opts.get("0301") == 3, f"exit path may pass THROUGH a friendly unit that has already moved (0303-0302-0301, 3 MP) {opts} [MOV-07/VIC-09]")
check(hx("0302") not in g.dests("103"), "...though it may not END on that unit's hex [MOV-09]")

print("== log replay ==")
g = fresh(seed=5)
live = os.path.dirname(g.log_path)
rng = random.Random(11)
n_legal = n_illegal = 0
for _ in range(900):
    if g.s["over"]:
        break
    side = g.s["mover"]
    if g.s["phase"] == "combat":
        D.discharge_combat(g, rng)
        if not g.s["over"]:
            g.submit(side, {"type": "end_phase"})
        continue
    mine = [p for p in g.s["units"] if g.unit(p)["side"] == side and p not in g.s["done"]]
    if not mine or rng.random() < 0.05:
        bring_prussians(g)
        r = g.submit(side, {"type": "end_movement"})
        if not r["verdict"]["legal"]:
            D.unstack(g)
        continue
    pid = rng.choice(mine)
    lm = g.legal_moves(pid)
    if rng.random() < 0.1:
        r = g.submit(side, {"type": "move", "unit": pid, "dest": [rng.randint(0, 28), rng.randint(0, 23)]})
        n_illegal += not r["verdict"]["legal"]
        n_legal += r["verdict"]["legal"]
        continue
    if lm.get("exits") and rng.random() < 0.5:
        e = lm["exits"][0]
        r = g.submit(side, {"type": "exit", "unit": pid, "via": [e["col"], e["row"]]})
    elif lm.get("dests"):
        d = rng.choice(lm["dests"])
        r = g.submit(side, {"type": "move", "unit": pid, "dest": [d["col"], d["row"]]})
    else:
        r = g.submit(side, {"type": "move", "unit": pid, "dest": [1, 1]})
    n_illegal += not r["verdict"]["legal"]
    n_legal += r["verdict"]["legal"]
check(n_legal > 100 and n_illegal > 10, f"random walk through the gate: {n_legal} legal, {n_illegal} rejected proposals logged")
okv, msg = verify_game.verify(HERE, g.log_path)
check(okv, f"verify_game replays the log: {msg[:120]}")
h1 = g.state_hash()
g2 = fresh(seed=5)
lines = [json.loads(l) for l in open(g.log_path, encoding="utf-8")]
for e in lines[1:]:
    g2.submit(e["side"], e["action"])
check(g2.state_hash() == h1, "same seed + same proposals -> identical state hash in a second process-independent gate")

print("ALL PASS" if ok else "FAILURES ABOVE")
sys.exit(0 if ok else 1)
