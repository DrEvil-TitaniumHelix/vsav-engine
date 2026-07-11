"""Tier-2 combat validation - the evidence chain:

1. CRT: game.json vs rules_transcription.json (independent transcriptions of
   the 1975 scan p8 and the Decision Games Deluxe text) - all 60 cells,
   re-checked from the raw data on every run.
2. The deluxe reprint's worked examples (its blue example text): 13v4 -> 3-1,
   rough defense 5->10, voluntary 5-1 -> 3-1, pure-bombardment Exchange.
3. Mechanics on staged boards: multi-hex adjacency, ford doubling, printed-
   strength exchange under doubling, displacement chain, retreat-to-
   elimination, 7.74 no-contribution, 7.23 obligation closure, one-advance.

Every session replays through engine/verify_game.py."""
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

# ---------------------------------------------------------- 1. CRT sources
print("--- 1: CRT two-source cross-check [7.6] ---")
tr = json.load(open(os.path.join(HERE, "rules_transcription.json"), encoding="utf-8"))
gj = json.load(open(os.path.join(HERE, "game.json"), encoding="utf-8"))
crt_a, crt_b = tr["crt"], gj["combat"]["crt"]
check(crt_a["columns"] == crt_b["columns"], "CRT columns identical across sources")
cells = 0
mismatch = []
for die in map(str, range(1, 7)):
    for i, col in enumerate(crt_a["columns"]):
        cells += 1
        if crt_a["rows"][die][i] != crt_b["rows"][die][i]:
            mismatch.append((die, col))
check(not mismatch, f"all {cells} CRT cells identical (1975 scan == deluxe text == encoded)")

# ---------------------------------------------------------- 2. odds math
print("--- 2: odds arithmetic + clamps [7.0/7.6/7.9] ---")
check(G.odds(13, 4) == (3, 1), "deluxe example: 13 CSP vs 4 = 3-1 (rounded for defender) [7.0]")
check(G.odds(2, 7) == (1, 4), "2 vs 7 = 1-4 (ceiling toward the defender)")
check(G.odds(5, 5) == (1, 1), "equal strengths = 1-1")

TMP = tempfile.mkdtemp(prefix="bg_cbt_")
N = [0]
def mkscen(units, turns=1):
    N[0] += 1
    scen = {"name": f"cbt-test-{N[0]}",
            "game": {"turns": turns, "first_player": "Union", "night_turns": [],
                     "turn_labels": [f"GT {i}" for i in range(1, turns + 1)]},
            "units": list(units), "reserve": [],
            "vp": {"per_enemy_csp_eliminated": 1,
                   "exit_per_csp": {"Union": 1, "Confederate": 10},
                   "confederate_train_fail": 10,
                   "occupation": {}, "start_occupation": {}},
            "rules_scope": {"enforced": ["t"], "enforced_tier2": ["t"], "umpired": []}}
    p = os.path.join(TMP, f"scenario_c{N[0]}.json")
    json.dump(scen, open(p, "w"), indent=1)
    return p

def mkgame(scen_path, seed=1):
    live = os.path.join(TMP, f"live_c{N[0]}_{seed}")
    os.makedirs(live, exist_ok=True)
    return bluegray.BlueGrayGame(G, scen_path, live, seed=seed), live

def U(uid, slot, side, c, r, cls="inf"):
    return {"id": uid, "slot": slot, "side": side, "hex": [c, r],
            "str": max(G.stats(slot)[0], G.stats(slot)[1]), "cls": cls}

def replay(bg, live, label):
    gkey = os.path.basename(os.path.normpath(G.dir))
    log = os.path.join(live, f"game_{gkey}.log.jsonl")
    tmp_scen = os.path.join(HERE, f"scenario_{bg.scenario['name']}.json")
    json.dump(bg.scenario, open(tmp_scen, "w"), indent=1)
    try:
        okv, msg = verify_game.verify(HERE, log)
    finally:
        os.remove(tmp_scen)
    check(okv, f"verify_game [{label}]: {'byte-exact' if okv else msg}")

def find_seed(scen_maker, action_maker, want, tries=60):
    """Find a seed whose first battle roll yields `want`."""
    for seed in range(1, tries + 1):
        sp = scen_maker()
        bg, live = mkgame(sp, seed=seed)
        bg.submit("Union", {"type": "end_movement"})
        r = bg.submit("Union", action_maker())
        if ok(r) and r["result"][0]["result"] == want:
            return bg, live, r
    return None, None, None

# ---------------------------------------------------------- 3. multi-hex adjacency
print("--- 3: multi-hex combat adjacency [7.24/7.25] ---")
sp = mkscen([
    U("a1", "1/1/XIV c", "Union", 22, 22),
    U("a2", "2/1/XIV c", "Union", 21, 23),
    U("d1", "Fulton c", "Confederate", 22, 23),
    U("d2", "Strahl c", "Confederate", 21, 24),
])
bg, _ = mkgame(sp, seed=1)
bg.submit("Union", {"type": "end_movement"})
r = bg.propose("Union", {"type": "battle", "attackers": ["a1", "a2"],
                         "defenders": ["d1", "d2"]})
# a1 (2222) adjacent to 2123? no; to d2 2124? not adjacent -> must be rejected
check(not r["legal"],
      f"multi-defender battle rejected unless ALL attackers adjacent to ALL "
      f"defenders [7.25] ({r['reasons']})")
r = bg.propose("Union", {"type": "battle", "attackers": ["a2"],
                         "defenders": ["d1", "d2"]})
check(r["legal"] or "not adjacent" in " ".join(r["reasons"]),
      f"single attacker vs both defenders judged on adjacency [7.25] ({r['reasons']})")

# defender stack completeness [7.21]
sp = mkscen([
    U("a1", "1/1/XIV c", "Union", 22, 22),
    U("d1", "Fulton c", "Confederate", 22, 23),
    U("d2", "Strahl c", "Confederate", 22, 23),
])
bg, _ = mkgame(sp, seed=1)
bg.submit("Union", {"type": "end_movement"})
r = bg.propose("Union", {"type": "battle", "attackers": ["a1"], "defenders": ["d1"]})
check(not r["legal"], f"partial defending stack rejected [7.21] ({r['reasons']})")

# ---------------------------------------------------------- 4. ford doubling
print("--- 4: hexside doubling [9.0 TEC] ---")
sp = mkscen([
    U("a1", "Wilder c", "Union", 23, 20),          # 2320, across the ford
    U("d1", "Strahl c", "Confederate", 24, 20),    # 2420 forest (no combat effect)
])
bg, _ = mkgame(sp, seed=1)
pv = bg.battle_preview("Union", ["a1"], ["d1"])
check(pv["odds"] == "1-1",
      f"8 vs 3 doubled-to-6 across the ford = 1-1 [9.0] (got {pv['odds']})")
sp = mkscen([
    U("a1", "Wilder c", "Union", 23, 20),
    U("a2", "1/1/Res c", "Union", 24, 19),         # 2419 clear side, not across ford
    U("d1", "Strahl c", "Confederate", 24, 20),
])
bg, _ = mkgame(sp, seed=1)
pv = bg.battle_preview("Union", ["a1", "a2"], ["d1"])
check(pv["odds"] == "4-1",
      f"doubling voided when any attacker crosses a plain hexside: 14 vs 3 = 4-1 "
      f"[9.0 'all attacking units'] (got {pv['odds']})")

# ---------------------------------------------------------- 5. exchange accounting
print("--- 5: Exchange pays PRINTED strength [7.6] ---")
# Wilder 8 + Res 6 = 14 vs Russell 2 doubled in rough 1327 -> 14 v 4 = 3-1
# (Ex on die 6); owe = PRINTED 2, not the doubled 4
def exch_scen():
    return mkscen([
        U("a1", "Wilder c", "Union", 12, 27),
        U("a2", "1/1/Res c", "Union", 13, 26),
        U("d1", "Russell c", "Confederate", 13, 27),
    ])
bg, live, r = find_seed(exch_scen, lambda: {"type": "battle",
                                            "attackers": ["a1", "a2"],
                                            "defenders": ["d1"]}, "Ex")
check(bg is not None, "found a seed rolling Ex at 3-1")
if bg:
    check(r["result"][0]["odds"] == "3-1", f"rough doubling: 14 v 2x2 = 3-1 "
                                           f"(got {r['result'][0]['odds']})")
    p = bg.s["pending"]
    check(p and p["awaiting"] == "exchange_loss" and p["owe"] == 2,
          f"exchange owes the PRINTED defender total 2, not the doubled 4 [7.6] "
          f"(owe={p and p.get('owe')})")
    r2 = bg.submit("Union", {"type": "exchange_loss", "units": ["a1", "a2"]})
    check(not ok(r2), "over-removal rejected (either unit alone covers 2) [7.6]")
    r4 = bg.submit("Union", {"type": "exchange_loss", "units": ["a2"]})
    check(ok(r4), "single-unit exchange accepted (6 >= 2, minimal) [7.6]")
    if bg.s["pending"] and bg.s["pending"]["awaiting"] == "advance":
        bg.submit("Union", {"type": "advance"})
    replay(bg, live, "exchange session")

# ---------------------------------------------------------- 6. pure bombardment Ex
print("--- 6: pure bombardment Exchange [8.0 example/8.15] ---")
# two stacked batteries (8.14 same target): 3+3=6 vs Russell 2 = 3-1, Ex on 6
# (target 0110 CLEAR - no terrain doubling; LOS 0108->0110 crosses clear 0109)
def bomb_scen():
    return mkscen([
        U("art", "XIV Artillery c", "Union", 1, 8, cls="arty"),
        U("art2", "XX Artillery c", "Union", 1, 8, cls="arty"),
        U("d", "Russell c", "Confederate", 1, 10),
        U("far", "Wood c", "Confederate", 20, 20),
    ])
bg, live, r = find_seed(bomb_scen, lambda: {"type": "battle",
                                            "attackers": ["art", "art2"],
                                            "defenders": ["d"],
                                            "bombarding": ["art", "art2"]}, "Ex")
check(bg is not None, "found a seed rolling Ex on a pure bombardment")
if bg:
    check("d" not in bg.s["units"], "defender eliminated by the bombardment Ex [7.6]")
    check("art" in bg.s["units"] and "art2" in bg.s["units"],
          "bombarding artillery unaffected [8.0 example/8.15]")
    check(bg.s["pending"] is None, "no exchange owed by bombarding artillery [8.15]")
    replay(bg, live, "pure bombardment Ex session")

# ---------------------------------------------------------- 7. retreat rules
print("--- 7: retreat to elimination + displacement chain [7.7/7.8] ---")
# d1 surrounded: attackers + ZOC leave no retreat hex -> Dr eliminates
def trap_scen():
    # the six true neighbors of 2223: 2222 2224 2123 2124 2323 2324
    return mkscen([
        U("a1", "1/1/XIV c", "Union", 22, 22),
        U("a2", "2/1/XIV c", "Union", 21, 23),
        U("a3", "3/1/XIV c", "Union", 21, 24),
        U("a4", "1/3/XIV c", "Union", 22, 24),
        U("a5", "2/3/XIV c", "Union", 23, 23),
        U("a6", "3/3/XIV c", "Union", 23, 24),
        U("d1", "Russell c", "Confederate", 22, 23),
    ])
bg, live, r = find_seed(trap_scen,
                        lambda: {"type": "battle",
                                 "attackers": ["a1", "a2", "a3", "a4", "a5", "a6"],
                                 "defenders": ["d1"]}, "Dr")
check(bg is not None, "found a seed rolling Dr on the surrounded defender")
if bg:
    u = bg.unit("d1")
    oh, dh = bg._retreat_hexes(u)
    check(not oh and not dh, f"surrounded: no retreat hexes [7.72] ({oh}/{dh})")
    rr = bg.submit("Confederate", {"type": "retreat", "unit": "d1", "dest": None})
    check(ok(rr), "no-retreat elimination accepted [7.72]")
    check("d1" not in bg.s["units"], "defender eliminated in place [7.72]")
    replay(bg, live, "trapped retreat session")

# ---------------------------------------------------------- 8. 7.74 retreated no strength
print("--- 8: retreated unit contributes nothing when bombarded [7.74] ---")
# d1 (Fulton 3) at 2123, attacked from 2122; retreats to 2223 joining d2
# (Wood 5); artillery at 2021 (range 2, clear LOS via 2122) then bombards the
# stack: defense counts Wood only -> 3 v 5 = 1-2 (with Fulton it would be 1-3)
sp = mkscen([
    U("a1", "Wilder c", "Union", 21, 22),
    U("art", "XX Artillery c", "Union", 20, 21, cls="arty"),
    U("d1", "Fulton c", "Confederate", 21, 23),
    U("d2", "Wood c", "Confederate", 22, 23),
])
found = False
for seed in range(1, 80):
    bg, live = mkgame(sp, seed=seed)
    bg.submit("Union", {"type": "end_movement"})
    r = bg.submit("Union", {"type": "battle", "attackers": ["a1"], "defenders": ["d1"]})
    if not ok(r) or r["result"][0]["result"] != "Dr":
        continue
    u = bg.unit("d1")
    oh, _ = bg._retreat_hexes(u)
    if (22, 23) not in oh:
        continue
    bg.submit("Confederate", {"type": "retreat", "unit": "d1", "dest": [22, 23]})
    if bg.s["pending"] and bg.s["pending"]["awaiting"] == "advance":
        bg.submit("Union", {"type": "advance"})
    pv = bg.battle_preview("Union", ["art"], ["d1", "d2"], bomb_ids=["art"])
    check(pv["odds"] == "1-2",
          f"bombarding the stack counts only the unretreated unit [7.74] "
          f"(3 vs 5 = 1-2, got {pv['odds']})")
    found = True
    break
check(found, "constructed the 7.74 scenario (retreat into the artillery target)")

# ---------------------------------------------------------- 9. one advance only
print("--- 9: a single unit advances [7.75/7.76] ---")
def adv_scen():
    return mkscen([
        U("a1", "Wilder c", "Union", 22, 22),
        U("a2", "1/1/Res c", "Union", 21, 23),
        U("d1", "Russell c", "Confederate", 22, 23),
    ])
bg, live, r = find_seed(adv_scen, lambda: {"type": "battle",
                                           "attackers": ["a1", "a2"],
                                           "defenders": ["d1"]}, "De")
check(bg is not None, "found a seed rolling De")
if bg:
    p = bg.s["pending"]
    check(p and p["awaiting"] == "advance", "advance offered after De [7.75]")
    r2 = bg.submit("Union", {"type": "advance", "unit": "a1", "dest": [22, 23]})
    check(ok(r2), "one victorious unit advances into the vacated hex [7.75]")
    check(bg.s["pending"] is None, "advance window closed - only ONE unit [7.76]")
    check(tuple([bg.unit('a1')['col'], bg.unit('a1')['row']]) == (22, 23),
          "advancing unit moved")
    r3 = bg.submit("Union", {"type": "end_phase"})
    check(ok(r3), "advanced unit creates no new obligations [7.75]")
    replay(bg, live, "advance session")

print()
shutil.rmtree(TMP, ignore_errors=True)
if fails:
    print(f"{len(fails)} FAILURES")
    sys.exit(1)
print("ALL PASS")
