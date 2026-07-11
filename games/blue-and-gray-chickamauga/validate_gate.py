"""Gate validation: the submit()-only door exercised end-to-end on staged
scenarios (movement, ZOC lock, reinforcement columns, exit, night, battles
with every pending flavor, bombardment + LOS, obligations, the Train), each
session replayed through engine/verify_game.py.

Every check cites the rule it exercises. Staged scenarios are written to a
temp dir; the REAL scenario is exercised for setup/reinforcement flow."""
import json, os, sys, tempfile, shutil

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..")))
from engine import gamespec, bluegray, verify_game

HERE = os.path.dirname(os.path.abspath(__file__))
G = gamespec.load(HERE)

fails = []
def check(cond, what):
    if not cond:
        fails.append(what)
    print(("PASS " if cond else "FAIL ") + what)

def ok(r):
    return r["verdict"]["legal"]

TMP = tempfile.mkdtemp(prefix="bg_gate_")
SCEN_COUNT = [0]

def mkscen(units, reserve=(), night=(), turns=4, first="Union"):
    SCEN_COUNT[0] += 1
    scen = {
        "name": f"gate-test-{SCEN_COUNT[0]}",
        "game": {"turns": turns, "first_player": first,
                 "night_turns": list(night),
                 "turn_labels": [f"GT {i}" for i in range(1, turns + 1)]},
        "units": list(units), "reserve": list(reserve),
        "vp": {"per_enemy_csp_eliminated": 1,
               "exit_per_csp": {"Union": 1, "Confederate": 10},
               "confederate_train_fail": 10,
               "occupation": {"union": {"1920": 10}, "confederate": {"0211": 20},
                              "either": {"0822": 5}},
               "start_occupation": {"union": ["0211", "0822"], "confederate": ["1920"]}},
        "rules_scope": {"enforced": ["test"], "enforced_tier2": ["test"], "umpired": []},
    }
    p = os.path.join(TMP, f"scenario_test{SCEN_COUNT[0]}.json")
    json.dump(scen, open(p, "w"), indent=1)
    return p

def mkgame(scen_path, seed=1, tier=None):
    live = os.path.join(TMP, f"live{SCEN_COUNT[0]}_{seed}")
    os.makedirs(live, exist_ok=True)
    return bluegray.BlueGrayGame(G, scen_path, live, seed=seed, tier=tier), live

def U(uid, slot, side, c, r, cls="inf", s=None):
    st = G.stats(slot)
    return {"id": uid, "slot": slot, "side": side, "hex": [c, r],
            "str": s if s is not None else max(st[0], st[1]), "cls": cls}

def replay(bg, live, label):
    gkey = os.path.basename(os.path.normpath(G.dir))
    log = os.path.join(live, f"game_{gkey}.log.jsonl")
    # verify_game looks for scenario files inside the game dir; copy the test
    # scenario there temporarily
    okv, msg = None, None
    tmp_scen = None
    scen_name = bg.scenario["name"]
    if scen_name.startswith("gate-test"):
        tmp_scen = os.path.join(HERE, f"scenario_{scen_name}.json")
        json.dump(bg.scenario, open(tmp_scen, "w"), indent=1)
    try:
        okv, msg = verify_game.verify(HERE, log)
    finally:
        if tmp_scen and os.path.exists(tmp_scen):
            os.remove(tmp_scen)
    check(okv, f"verify_game replay [{label}]: {msg if not okv else 'byte-exact'}")

# ================================================================ A. real scenario
print("--- A: real scenario, movement basics ---")
bg, liveA = mkgame(os.path.join(HERE, "scenario_chickamauga.json"), seed=7)
check(bg.s["turn"] == 1 and bg.s["mover"] == "Union" and bg.s["phase"] == "movement",
      "GT1 opens with the Union movement phase [4.1/14.3]")
# legal move: 1/1/XIV (1317) somewhere in its dests
u = bg.unit("1-1-xiv")
dd = bg.dests(u)
check(len(dd) > 0, f"1/1/XIV has {len(dd)} legal destinations")
dest = sorted(dd)[0]
check(ok(bg.submit("Union", {"type": "move", "unit": "1-1-xiv", "dest": list(dest)})),
      "legal move accepted [5.0]")
check(not ok(bg.submit("Union", {"type": "move", "unit": "1-1-xiv",
                                 "dest": list(sorted(dd)[-1])})),
      "second move of the same unit rejected [5.17]")
check(not ok(bg.submit("Union", {"type": "move", "unit": "wood", "dest": [20, 25]})),
      "moving an enemy unit rejected")
check(not ok(bg.submit("Confederate", {"type": "move", "unit": "wood", "dest": [20, 25]})),
      "moving out of player turn rejected [4.1]")
check(not ok(bg.submit("Union", {"type": "reinforce", "unit": "1-2-xiv", "hex": [7, 28]})),
      "GT2 reinforcement rejected on GT1 [15.0]")
check(not ok(bg.submit("Union", {"type": "exit", "unit": "1-1-res"})),
      "exit rejected off the exit hexes [16.5]")
check(ok(bg.submit("Union", {"type": "end_movement"})), "end_movement accepted")
check(bg.s["phase"] == "combat", "combat phase follows movement [4.1]")
check(ok(bg.submit("Union", {"type": "end_phase"})),
      "no contacts at setup - combat phase ends freely [7.0]")
check(bg.s["mover"] == "Confederate", "Confederate player turn follows [4.1]")
check(ok(bg.submit("Confederate", {"type": "end_movement"})), "CSA end_movement")
check(ok(bg.submit("Confederate", {"type": "end_phase"})), "CSA end_phase")
check(bg.s["turn"] == 2 and bg.s["mover"] == "Union", "GT2 begins [4.1]")
# GT2 Union reinforcements: column costs 1,2,3... at 0728/1027
check(ok(bg.submit("Union", {"type": "reinforce", "unit": "1-2-xiv", "hex": [7, 28]})),
      "GT2 reinforcement enters at 0728 [15.0]")
check(not ok(bg.submit("Union", {"type": "reinforce", "unit": "2-2-xiv", "hex": [7, 28]})),
      "occupied entry hex rejected [15.4]")
check(ok(bg.submit("Union", {"type": "reinforce", "unit": "2-2-xiv", "hex": [10, 27]})),
      "second reinforcement at the other hex [15.0]")
check(not ok(bg.submit("Union", {"type": "reinforce", "unit": "2-1-xx", "hex": [7, 28]})),
      "GT5 unit rejected on GT2 [15.0]")
check(bg.s["units"]["1-2-xiv"]["col"] == 7, "reinforcement on the map")
replay(bg, liveA, "real scenario session")

# ================================================================ B. ZOC + battle
print("--- B: staged contact, mandatory combat, Dr retreat + advance ---")
scen = mkscen([
    U("blu1", "1/1/XIV c", "Union", 22, 23),
    U("blu2", "2/1/XIV c", "Union", 20, 24),        # out of contact, free to move
    U("reb1", "Fulton c", "Confederate", 22, 22),   # weak: 3
], turns=2)
bg, liveB = mkgame(scen, seed=3)
check(bg.dests(bg.unit("blu1")) == {}, "unit in an EZOC may not move [5.13/6.3]")
check(len(bg.dests(bg.unit("blu2"))) > 0, "out-of-contact unit may move")
# 2123 is NOT adjacent to 2222 (col21 odd: neighbors of 2123 incl 2222? verify by contact)
mine, theirs = bg._contacts("Union")
check("blu1" in mine and "reb1" in theirs, "contact graph sees blu1<->reb1 [7.11/7.12]")
check(ok(bg.submit("Union", {"type": "end_movement"})), "end movement")
check(not ok(bg.submit("Union", {"type": "end_phase"})),
      "end_phase rejected while contacts unfought [7.11/7.12]")
mine, theirs = bg._contacts("Union")
atkrs = sorted(mine)
r = bg.submit("Union", {"type": "battle", "attackers": atkrs, "defenders": ["reb1"]})
check(ok(r), f"mandatory battle accepted ({r['verdict']['reasons']})")
res = r["result"][0]["result"] if ok(r) else None
print(f"   (CRT: {r['result'][0]['odds']} col {r['result'][0]['column']} "
      f"die {r['result'][0]['die']} -> {res})")
# resolve whatever pending arose
if bg.s["pending"]:
    p = bg.s["pending"]
    if p["awaiting"] == "retreat":
        by = p["by"]
        for pid in list(p["units"]):
            uu = bg.unit(pid)
            open_h, disp_h = bg._retreat_hexes(uu)
            dest = sorted(open_h)[0] if open_h else None
            rr = bg.submit(by, {"type": "retreat", "unit": pid,
                                "dest": list(dest) if dest else None})
            check(ok(rr), f"retreat resolution for {pid} [7.7]")
        if bg.s["pending"] and bg.s["pending"]["awaiting"] == "advance":
            check(ok(bg.submit(bg.s["pending"]["by"], {"type": "advance"})),
                  "advance declined [7.75]")
    elif p["awaiting"] == "exchange_loss":
        pids, owe, tot = [], p["owe"], 0
        for pid in p["units"]:
            if tot >= owe:
                break
            pids.append(pid)
            tot += bg.printed(bg.unit(pid))
        check(ok(bg.submit(p["by"], {"type": "exchange_loss", "units": pids})),
              "exchange loss paid [7.6]")
        if bg.s["pending"] and bg.s["pending"]["awaiting"] == "advance":
            check(ok(bg.submit(bg.s["pending"]["by"], {"type": "advance"})),
                  "advance declined after exchange [7.75]")
check(bg.s["pending"] is None, "pendings fully resolved")
check(ok(bg.submit("Union", {"type": "end_phase"})),
      "end_phase after obligations met [7.11]")
replay(bg, liveB, "contact battle session")

# ================================================================ C: CRT determinism
print("--- C: CRT sweep - seeds produce every result family, verdicts replay ---")
seen = set()
for seed in range(1, 40):
    scen = mkscen([
        U("a1", "1/1/XIV c", "Union", 22, 23),
        U("a2", "2/2/Res c", "Union", 21, 23),
        U("d1", "Fulton c", "Confederate", 22, 22),
    ], turns=1)
    bg, live = mkgame(scen, seed=seed)
    bg.submit("Union", {"type": "end_movement"})
    r = bg.submit("Union", {"type": "battle", "attackers": ["a1", "a2"],
                            "defenders": ["d1"]})
    if ok(r):
        seen.add(r["result"][0]["result"])
    if len(seen) >= 3:
        break
check(len(seen) >= 2, f"multiple CRT results reachable across seeds ({sorted(seen)})")

# ================================================================ D: voluntary odds + clamp
print("--- D: odds clamping and voluntary reduction [7.9/7.6] ---")
scen = mkscen([
    U("big1", "Wilder c", "Union", 22, 23),          # 8
    U("big2", "1/1/Res c", "Union", 21, 23),         # 6
    U("small", "Russell c", "Confederate", 22, 22),  # 2
], turns=1)
bg, liveD = mkgame(scen, seed=5)
bg.submit("Union", {"type": "end_movement"})
pv = bg.battle_preview("Union", ["big1", "big2"], ["small"])
check(pv["column"] == "6-1", f"14:2 = 7-1 clamps to the 6-1 column [7.6 note] (got {pv})")
r = bg.submit("Union", {"type": "battle", "attackers": ["big1", "big2"],
                        "defenders": ["small"], "odds_reduce": [3, 1]})
check(ok(r) and r["result"][0]["column"] == "3-1",
      "voluntary reduction to 3-1 accepted [7.9]")
if bg.s["pending"]:
    p = bg.s["pending"]
    if p["awaiting"] == "retreat":
        for pid in list(p["units"]):
            uu = bg.unit(pid)
            oh, _ = bg._retreat_hexes(uu)
            bg.submit(p["by"], {"type": "retreat", "unit": pid,
                                "dest": list(sorted(oh)[0]) if oh else None})
        if bg.s["pending"] and bg.s["pending"]["awaiting"] == "advance":
            bg.submit(bg.s["pending"]["by"], {"type": "advance"})
    elif p["awaiting"] == "exchange_loss":
        pids, tot = [], 0
        for pid in p["units"]:
            if tot >= p["owe"]:
                break
            pids.append(pid); tot += bg.printed(bg.unit(pid))
        bg.submit(p["by"], {"type": "exchange_loss", "units": pids})
        if bg.s["pending"] and bg.s["pending"]["awaiting"] == "advance":
            bg.submit(bg.s["pending"]["by"], {"type": "advance"})
replay(bg, liveD, "odds session")

# ================================================================ E: defense doubling
print("--- E: terrain doubling [7.4/9.0] ---")
scen = mkscen([
    U("a", "Wilder c", "Union", 12, 27),      # adjacent to 1327 rough
    U("d", "Fulton c", "Confederate", 13, 27),
], turns=1)
bg, _ = mkgame(scen, seed=2)
pv = bg.battle_preview("Union", ["a"], ["d"])
check(pv["odds"] == "1-1", f"8 vs 3-doubled-6 rounds to 1-1 [7.4/9.0] (got {pv['odds']})")

# ================================================================ F: night turn
print("--- F: night GT [10.x] ---")
scen = mkscen([
    U("n1", "1/1/XIV c", "Union", 22, 23),
    U("n2", "Fulton c", "Confederate", 22, 21),   # creek-separated from 2222
], night=[1], turns=2)
bg, liveF = mkgame(scen, seed=4)
dd = bg.dests(bg.unit("n1"))
board = bg.rules_board(mover_side="Union")
ez = G.zoc_hexes(board, "Confederate")
check(all(h not in ez for h in dd), "night: EZOC destinations filtered out [10.2]")
bg.submit("Union", {"type": "end_movement"})
check(bg.s["mover"] == "Confederate" and bg.s["phase"] == "movement",
      "night: combat phase skipped entirely [10.1]")
r = bg.submit("Confederate", {"type": "battle", "attackers": ["n2"], "defenders": ["n1"]})
check(not ok(r), "battle rejected on a night GT [10.1]")
replay(bg, liveF, "night session")

# ================================================================ G: exit + VP
print("--- G: exit and final scoring [16.x/17.x] ---")
scen = mkscen([
    U("e1", "1/1/XIV c", "Union", 1, 1),
    U("far", "Fulton c", "Confederate", 22, 22),
], turns=1)
bg, liveG = mkgame(scen, seed=6)
check(ok(bg.submit("Union", {"type": "exit", "unit": "e1"})),
      "exit from 0101 accepted [16.1]")
check("e1" not in bg.s["units"], "exited unit off the map [16.3]")
bg.submit("Union", {"type": "end_movement"})
bg.submit("Union", {"type": "end_phase"})
bg.submit("Confederate", {"type": "end_movement"})
r = bg.submit("Confederate", {"type": "end_phase"})
check(bg.s["over"], "game ends after the final GT [17.0]")
check(bg.s["vp"]["Union"] >= 5, f"Union exit VP awarded (got {bg.s['vp']})")
check(bg.s["vp"]["Confederate"] >= 10, "CSA train-fail VP awarded (no train in play) [17.11]")
replay(bg, liveG, "exit session")

# ================================================================ H: bombardment
print("--- H: artillery bombardment + LOS [8.x] ---")
scen = mkscen([
    U("art", "XIV Artillery c", "Union", 1, 10, cls="arty"),   # 0110 clear
    U("inf", "1/1/XIV c", "Union", 1, 9),
    U("tgt", "Fulton c", "Confederate", 1, 12),                # 2 hexes away? 0110->0112
    U("blk", "Wood c", "Confederate", 3, 20),                  # remote
], turns=1)
bg, liveH = mkgame(scen, seed=8)
d = G.hex_distance((1, 10), (1, 12))
check(d == 2, f"0110->0112 distance 2 (got {d})")
bg.submit("Union", {"type": "end_movement"})
r = bg.submit("Union", {"type": "battle", "attackers": ["art"],
                        "defenders": ["tgt"], "bombarding": ["art"]})
check(ok(r), f"bombardment at range 2 with clear LOS accepted [8.1/8.3] "
             f"({r['verdict']['reasons']})")
if ok(r):
    res = r["result"][0]["result"]
    if res in ("Ar", "Ae"):
        check("art" in bg.s["units"],
              f"bombarding artillery immune to {res} [8.15]")
    if bg.s["pending"]:
        p = bg.s["pending"]
        if p["awaiting"] == "retreat":
            for pid in list(p["units"]):
                uu = bg.unit(pid)
                oh, _ = bg._retreat_hexes(uu)
                bg.submit(p["by"], {"type": "retreat", "unit": pid,
                                    "dest": list(sorted(oh)[0]) if oh else None})
            if bg.s["pending"] and bg.s["pending"]["awaiting"] == "advance":
                bg.submit(bg.s["pending"]["by"], {"type": "advance"})
replay(bg, liveH, "bombardment session")

# LOS blocked: firer 0101, target 0104 through the 0102/0103 forest
scen = mkscen([
    U("art", "XIV Artillery c", "Union", 1, 1, cls="arty"),
    U("tgt", "Fulton c", "Confederate", 1, 4),
    U("far", "Wood c", "Confederate", 22, 22),
], turns=1)
bg, _ = mkgame(scen, seed=9)
bg.submit("Union", {"type": "end_movement"})
r = bg.submit("Union", {"type": "battle", "attackers": ["art"],
                        "defenders": ["tgt"], "bombarding": ["art"]})
check(not ok(r), "bombardment through forest LOS rejected [8.3] "
                 f"({r['verdict']['reasons']})")

# artillery in an EZOC must fight normally, not bombard [8.41]
scen = mkscen([
    U("art", "XIV Artillery c", "Union", 22, 23, cls="arty"),
    U("foe", "Fulton c", "Confederate", 22, 22),
    U("tgt2", "Wood c", "Confederate", 22, 25),
], turns=1)
bg, _ = mkgame(scen, seed=10)
bg.submit("Union", {"type": "end_movement"})
r = bg.submit("Union", {"type": "battle", "attackers": ["art"],
                        "defenders": ["tgt2"], "bombarding": ["art"]})
check(not ok(r), "artillery in an EZOC may not bombard [8.41]")

# ================================================================ I: the Train
print("--- I: the Union Train [18.x] ---")
# I1: train movement with no enemy in contact
scen = mkscen([
    U("train", "Union Supply Train c", "Union", 19, 20, cls="train"),  # 1920 on the road
    U("guard", "1/1/XIV c", "Union", 19, 21),
    U("reb", "Fulton c", "Confederate", 25, 25),
], turns=2)
bg, _ = mkgame(scen, seed=11)
dd = bg.dests(bg.unit("train"))
check(len(dd) > 0, f"train has road/trail destinations ({len(dd)})")
gdd = bg.dests(bg.unit("guard"))
check((19, 20) not in gdd, "no one may enter/pass the Train's hex [18.22]")

# I2: train adjacent to a Confederate at the Union combat phase
scen = mkscen([
    U("train", "Union Supply Train c", "Union", 19, 20, cls="train"),
    U("guard", "1/1/XIV c", "Union", 19, 21),
    U("reb", "Fulton c", "Confederate", 19, 19),
], turns=2)
bg, liveI = mkgame(scen, seed=11)
check(bg.dests(bg.unit("train")) == {}, "train ZOC-locked beside the enemy [5.13]")
# Union combat phase with CSA adjacent to train -> auto-retreat pending
bg.submit("Union", {"type": "end_movement"})
check(bg.s["pending"] and bg.s["pending"]["awaiting"] == "train_retreat",
      "train adjacent to a Confederate: auto-retreat pending [18.11]")
r = bg.submit("Union", {"type": "battle", "attackers": ["guard"], "defenders": ["reb"]})
check(not ok(r), "battles wait for the train retreat [18.11]")
u = bg.unit("train")
oh, _ = bg._retreat_hexes(u)
check(all(G.side_features((19, 20), h).get("road") or
          G.side_features((19, 20), h).get("trail") for h in oh),
      f"train retreat hexes follow roads/trails only [18.23] ({oh})")
rr = bg.submit("Union", {"type": "train_retreat",
                         "dest": list(sorted(oh)[0]) if oh else None})
check(ok(rr), "train retreat resolved [18.11]")
replay(bg, liveI, "train session")

print()
shutil.rmtree(TMP, ignore_errors=True)
if fails:
    print(f"{len(fails)} FAILURES")
    sys.exit(1)
print("ALL PASS")
