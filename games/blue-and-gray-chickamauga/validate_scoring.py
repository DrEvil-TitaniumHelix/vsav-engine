import json, os, shutil, sys, tempfile
from collections import Counter

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

TMP = tempfile.mkdtemp(prefix="bg_sc_")
N = [0]

def U(uid, slot, side, c, r, cls="inf"):
    return {"id": uid, "slot": slot, "side": side, "hex": [c, r],
            "str": max(G.stats(slot)[0], G.stats(slot)[1]), "cls": cls}

def mkscen(units, reserve=(), turns=1, occ=None, start=None):
    N[0] += 1
    scen = {"name": f"scoring-test-{N[0]}",
            "game": {"turns": turns, "first_player": "Union", "night_turns": [],
                     "turn_labels": [f"GT {i}" for i in range(1, turns + 1)]},
            "units": list(units), "reserve": list(reserve),
            "vp": {"per_enemy_csp_eliminated": 1,
                   "exit_per_csp": {"Union": 1, "Confederate": 10},
                   "confederate_train_fail": 10,
                   "occupation": occ or {}, "start_occupation": start or {}},
            "rules_scope": {"enforced": ["t"], "enforced_tier2": ["t"], "umpired": []}}
    p = os.path.join(TMP, f"scenario_sc{N[0]}.json")
    json.dump(scen, open(p, "w"), indent=1)
    return p

def mkgame(scen_path, seed=1):
    live = os.path.join(TMP, f"live_sc{N[0]}_{seed}")
    os.makedirs(live, exist_ok=True)
    return bluegray.BlueGrayGame(G, scen_path, live, seed=seed), live

def run_out(bg):
    bg.submit("Union", {"type": "end_movement"})
    bg.submit("Union", {"type": "end_phase"})
    bg.submit("Confederate", {"type": "end_movement"})
    return bg.submit("Confederate", {"type": "end_phase"})

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

print("--- 1: reinforcement schedule vs the 1975 transcription [15.51/15.52] ---")
tr = json.load(open(os.path.join(HERE, "rules_transcription.json"), encoding="utf-8"))
sc = json.load(open(os.path.join(HERE, "scenario_chickamauga.json"), encoding="utf-8"))
cx = tr["chickamauga_exclusive"]
for side, key in (("Union", "union"), ("Confederate", "confederate")):
    printed = Counter()
    for grp in cx[f"reinforcements_{key}"]:
        for u in grp["units"]:
            printed[(grp["gt"], u["type"], u["str"])] += 1
    encoded = Counter((e["due"], e["cls"], e["str"])
                      for e in sc["reserve"] if e["side"] == side)
    check(printed == encoded,
          f"{side} schedule matches print per (GT, class, strength): "
          f"{sum(printed.values())} units [15.51/15.52]")
    ent_print = sorted(cx[f"reinforcements_{key}_entry"])
    ent_enc = sorted({f"{h[0]:02d}{h[1]:02d}"
                      for e in sc["reserve"] if e["side"] == side for h in e["entry"]})
    check(ent_print == ent_enc,
          f"{side} entry hexes {ent_print} match print [15.51/15.52]")

print("--- 2: start-occupation seeding [17.23] ---")
sp = mkscen([], occ={"union": {"2223": 10}, "confederate": {"2124": 20}, "either": {"2024": 5}},
            start={"union": ["2124"], "confederate": ["2223"]})
bg, live = mkgame(sp)
check(bg.s["occ"] == {"2124": "Union", "2223": "Confederate"},
      "occupation seeded from the scenario start list [17.23]")

print("--- 3: move credit + occupation scoring + on-map 17.32 [17.21/17.22/17.12] ---")
sp = mkscen([U("m", "1/1/XIV c", "Union", 21, 22)],
            occ={"union": {"2223": 10}, "confederate": {"2124": 20}, "either": {"2024": 5}},
            start={"union": ["2124"], "confederate": ["2223"]})
bg, live = mkgame(sp)
check(ok(bg.submit("Union", {"type": "move", "unit": "m", "dest": [22, 23]})),
      "unit moves onto the VP hex [5.0]")
check(bg.s["occ"].get("2223") == "Union",
      "moving onto a VP hex flips occupation credit [17.21/17.22]")
r = run_out(bg)
check(bg.s["over"], "game ends after the final GT [17.0]")
check(bg.s["vp"]["Union"] == 10,
      f"Union scores exactly the union-pool hex it occupies (+10) [17.12] "
      f"(got {bg.s['vp']})")
check(bg.s["vp"]["Confederate"] == 15,
      f"CSA = train 10 + on-map cut-off 5; the Union-held confederate-pool hex and the "
      f"unheld either-pool hex score nothing [17.12/17.11] (got {bg.s['vp']})")
check(any(e.get("cut_off") == "1/1/XIV c" and e.get("csp") == 5 for e in r["result"]),
      "the 17.32 sweep scores the road-unreachable on-map unit [17.32]")
replay(bg, live, "move-credit session")

print("--- 4: reinforcement entry credit [17.22] ---")
sp = mkscen([], reserve=[{"id": "r1", "slot": "1/2/XIV c", "side": "Union", "str": 5,
                          "cls": "inf", "due": 1, "entry": [[7, 28], [10, 27]]}],
            occ={"union": {"0728": 7}})
bg, _ = mkgame(sp)
check(ok(bg.submit("Union", {"type": "reinforce", "unit": "r1", "hex": [7, 28]})),
      "reinforcement enters at the charted hex [15.0]")
check(bg.s["occ"].get("0728") == "Union",
      "entering the map credits occupation [17.22]")
run_out(bg)
check(bg.s["vp"]["Union"] == 7,
      f"occupation VP awarded for the entry hex (+7) [17.12] (got {bg.s['vp']})")

print("--- 5: advance credit [17.22] ---")
seed_found = None
for seed in range(1, 60):
    sp = mkscen([U("a1", "Wilder c", "Union", 22, 22),
                 U("d1", "Russell c", "Confederate", 22, 23)],
                occ={"either": {"2223": 5}})
    bg, live = mkgame(sp, seed=seed)
    bg.submit("Union", {"type": "end_movement"})
    r = bg.submit("Union", {"type": "battle", "attackers": ["a1"], "defenders": ["d1"]})
    if ok(r) and r["result"][0]["result"] == "De":
        seed_found = seed
        break
check(seed_found is not None, "found a seed rolling De on the staged battle")
if seed_found:
    check(ok(bg.submit("Union", {"type": "advance", "unit": "a1", "dest": [22, 23]})),
          "victorious unit advances into the vacated VP hex [7.75]")
    check(bg.s["occ"].get("2223") == "Union",
          "advancing onto a VP hex credits occupation [17.22]")
    r2 = run_out(bg)
    check(bg.s["vp"]["Union"] == 7,
          f"either-pool VP scored for the occupier (2 elimination + 5 occupation) "
          f"[17.11/17.12] (got {bg.s['vp']})")
    check(any(e.get("cut_off") == "Wilder c" and e.get("csp") == 8 for e in r2["result"]),
          f"CSA = train 10 + advance-occupier cut off 8 [17.32] (got {bg.s['vp']})")
    replay(bg, live, "advance-credit session")

print("--- 6: exact tie = draw [17.0] ---")
sp = mkscen([], occ={"union": {"2223": 10}}, start={"union": ["2223"]})
bg, _ = mkgame(sp)
run_out(bg)
check(bg.s["vp"] == {"Union": 10, "Confederate": 10} and bg.s["winner"] == "draw",
      f"equal VP is a draw [17.0] (got {bg.s['vp']}, {bg.s['winner']})")

print()
shutil.rmtree(TMP, ignore_errors=True)
if fails:
    print(f"{len(fails)} FAILURES")
    sys.exit(1)
print("ALL PASS")
