"""Afrika Korps Tier-2 COMBAT validation (spec #9/#12 evidence).

Three layers, every one required:
  1. CRT DATA: the encoded table is re-checked cell-by-cell against BOTH
     independent sources — the rulebook back-page text (pypdf extraction)
     and the mastermind image-only map transcription. 66 cells x 2 sources.
  2. RULE MATH: the rulebook's own worked examples (7.3 odds rounding,
     7.5 both exchange examples, 11.6 soak-off limits, 23.7 fortress
     no-retreat) reproduced through the engine.
  3. THE GATE: staged scenarios driven through StrategicGame.submit() —
     legal actions accepted, illegal proposals rejected with citations,
     every session replayed through engine/verify_game.py.

Run:  python games/afrika-korps-classic-ah/validate_combat.py
"""
import json
import os
import re
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
INGEST = os.path.normpath(os.path.join(
    HERE, "..", "..", "..", "VassalIngest", "afrika-korps-classic-ah"))


def check(cond, what):
    print(("  PASS  " if cond else "  FAIL  ") + what)
    if not cond:
        fails.append(what)


# =====================================================================
print("=== 1. CRT DATA: two independent sources vs the encoded table ===")
CODES = {"A elim": "AE", "A back 2": "AB2", "Exchange": "EX",
         "D back 2": "DB2", "D elim": "DE"}
enc = g.combat_cfg["crt"]
cols = enc["columns"]

# source A: rulebook back-page text
from pypdf import PdfReader  # noqa: E402
rt = "\n".join(p.extract_text() for p in PdfReader(
    os.path.join(INGEST, "extracted", "AfrikaKorps_3d_Ed_Rules.pdf")).pages)
block = rt[rt.find("COMBAT RESULTS TABLE"):][:900]
book = {}
for m in re.finditer(r"([1-6]) ((?:(?:AE|AB2|EX|DB2|DE) ){10}(?:AE|AB2|EX|DB2|DE))",
                     block):
    book[m.group(1)] = m.group(2).split()
check(sorted(book) == list("123456"), "rulebook text: all 6 CRT die rows parsed")

# source B: image-only map transcription (mastermind, no rulebook consulted)
mt = json.load(open(os.path.join(INGEST, "map_tables_transcription.json"),
                    encoding="utf-8"))["combat_results_table"]
check(mt["odds_columns"] == cols, "map transcription: same 11 odds columns")

mism = []
for die in "123456":
    for ci, c in enumerate(cols):
        e = enc["rows"][die][ci]
        if book[die][ci] != e:
            mism.append(f"book {die}/{c}")
        if CODES[mt["die_rolls"][die][c]] != e:
            mism.append(f"map {die}/{c}")
check(not mism, f"all 66 encoded cells match BOTH sources ({mism[:4] or 'exact'})")
check(any("greater than 6-1" in n and "automatic elimination" in n
          for n in mt["printed_notes"]),
      "map's printed note confirms >6-1 = automatic elimination (with 7.4/9.1)")

# =====================================================================
print("=== 2. RULE MATH: rulebook worked examples through the engine ===")
check(g.odds(7, 2) == (3, 1) and g.odds(2, 7) == (1, 4),
      "7.3: fractions round in the defender's favor (7:2 -> 3-1, 2:7 -> 1-4)")
check(g.odds(3, 2) == (1, 1),
      "7.3 example: 3-3-7 attacks 2-2-4 -> battle odds 3-2 or 1-1")
check(g.odds_column(*g.odds(7, 1)) == "auto_elim"
      and g.odds_column(*g.odds(14, 1)) == "auto_elim",
      "7.4/9.1: odds greater than 6-1 resolve as automatic elimination")
check(g.odds_column(*g.odds(1, 7)) is None and g.odds_column(*g.odds(1, 8)) is None,
      "7.4/11.6: odds worse than 1-6 are not allowed (the 1-8 soak-off example)")
check(g.odds_column(*g.odds(2, 8)) == "1-4",
      "11.6 escarpment example: 2 vs doubled 4-4-7 = 2 to 8 = 1-4")
check(g.odds_column(*g.odds(6, 2)) == "3-1",
      "11.6/23.7 example: 6 vs doubled 1-1-6 = 6 to 2 = 3-1")


# =====================================================================
# staged scenarios through the gate
# =====================================================================
SCEN = os.path.join(HERE, "scenario_validate_combat_tmp.json")
SCEN_NAME = "AK combat validation (temp stage)"
tmpdirs = []


def stat_slots(side_prefixes, stats):
    """All unit slots with exactly these (a,d,m) stats, by name prefix."""
    out = []
    for frag, st in g.stat_patterns:
        if tuple(st) == tuple(stats) and any(frag.startswith(p) for p in side_prefixes):
            if g.unit_class(frag) is None:
                out.append(frag)
    return out


ALLIED116 = stat_slots(("A ",), (1, 1, 6))
assert len(ALLIED116) >= 7, "need seven Allied 1-1-6 slots"


def stage(units, seed, turns=6, first="Axis"):
    """Write a temp scenario and boot a gated game on it."""
    scen = {
        "name": SCEN_NAME, "mode": "strategic",
        "game": {"turns": turns, "first_player": first},
        "units": [dict(id=f"u{i}", slot=s, side=side, hex=list(h))
                  for i, (s, side, h) in enumerate(units)],
        "reserve": [], "supply_pool": {},
        "supply_max_on_board": {"Axis": 3, "Allied": 4},
        "supply_table": {"windows": []},
    }
    json.dump(scen, open(SCEN, "w", encoding="utf-8"))
    tmp = tempfile.mkdtemp()
    tmpdirs.append(tmp)
    return strategic.StrategicGame(g, SCEN, tmp, seed=seed), tmp


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
    check(ok, f"verify_game replay [{what}]: {msg[:100]}")


def find_seed(rolls, skip=0):
    """Seed whose engine d6 stream begins with `rolls` (after `skip` calls)."""
    for seed in range(1, 100000):
        r = _random.Random(seed)
        seq = [1 + int(r.random() * 6) for _ in range(skip + len(rolls))][skip:]
        if seq == list(rolls):
            return seed
    raise AssertionError(f"no seed for {rolls}")


def ring(h):
    return g.neighbors(*h)


def clear_area(need_r=3):
    """A deep-desert hex: everything within need_r clear, no road hexsides."""
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
    raise AssertionError("no clear area found")


BASE = clear_area()
N = ring(BASE)
NN = ring(N[0])
# hexes adjacent to the attacker at N[0] but NOT adjacent to BASE (i.e.
# outside a defender-on-BASE's ZOC) — safe supply spots
SAFE2 = [h for h in NN if h != BASE and BASE not in ring(h)]
def bfs_ring(start, depth, avoid=()):
    """Clear hexes exactly `depth` BFS steps from start over clear terrain."""
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


def roomy(cands):
    """First candidate with at least 4 clear neighbors."""
    return next(h for h in cands
                if sum(1 for nb in ring(h)
                       if g.hex_terrain(*nb) == "clear") >= 4)


FAR = roomy(bfs_ring(BASE, 8))           # distant bystander spots, mutually
FAR2 = roomy(bfs_ring(BASE, 12))         # out of ZOC range of each other

# =====================================================================
print("=== 3a. THE 7.3 EXAMPLE BATTLE + supply rules 14.1-14.6 ===")
# British 3-3-7 attacks Italian Savena 2-2-4: odds 1-1, supply needed.
seed = find_seed([6])                    # 1-1 die 6 -> A Elim
sg, tmp = stage([
    ("A 7 Arm 7", "Allied", N[0]),       # 3-3-7 attacker
    ("I Savena", "Axis", BASE),          # 2-2-4 defender
    ("A Supply 1", "Allied", SAFE2[0]),  # supply beside the attacker, no ZOC
    ("G 90Inf 55", "Axis", FAR),         # bystanders so neither side empties
    ("A 7A Inf 2", "Allied", FAR2),
], seed, first="Allied")
A = by_slot(sg, "A 7 Arm 7")
D = by_slot(sg, "I Savena")
S = by_slot(sg, "A Supply 1")

expect(sg, "Allied", {"type": "battle", "attackers": [A["pid"]],
                      "defenders": [D["pid"]], "supply": S["pid"]},
       False, "battle during MOVEMENT phase is illegal", "end movement")
expect(sg, "Allied", {"type": "end_phase"}, False,
       "ending the player turn with units in enemy ZOC is illegal", "8.4")
expect(sg, "Allied", {"type": "end_movement"}, True,
       "end_movement opens the combat portion [3.2]")
expect(sg, "Allied", {"type": "move", "unit": S["pid"], "dest": list(NN[2])},
       False, "moving after end_movement is illegal", "movement portion")
expect(sg, "Allied", {"type": "battle", "attackers": [A["pid"]],
                      "defenders": [D["pid"]]},
       False, "attack at 1-1 without stating a supply is illegal [14.1/14.6]",
       "supply")
r = expect(sg, "Allied", {"type": "battle", "attackers": [A["pid"]],
                          "defenders": [D["pid"]], "supply": S["pid"]},
           True, "the 7.3 example battle: 3-3-7 vs 2-2-4 at 1-1, supplied")
res = r["result"]
check(res["odds"] == "1-1" and res["column"] == "1-1",
      f"odds computed 3:2 -> 1-1 (rulebook 7.3 example) [{res['odds']}]")
check(res["roll"] == 6 and res["result"] == "AE",
      f"die {res['roll']} at 1-1 -> A Elim per the validated CRT")
check(A["pid"] not in sg.s["units"], "A Elim removed all attacking units [7.5]")
check(D["pid"] in sg.s["units"], "the defender survives an A Elim")
expect(sg, "Allied", {"type": "end_phase"}, True,
       "obligations discharged; the player turn ends")
check(S["pid"] not in sg.s["units"],
      "the sustaining supply was removed at the end of the player turn [14.1]")
replay(sg, tmp, "7.3 example battle")

print("=== 3b. SUPPLY ROUTE 14.2: radius, ZOC block, fig-15 carve-out ===")
seed = find_seed([1])
# supply seven hexes from the attacker: the 1-1 attack must be rejected
# (pick the candidate farthest from the Axis bystander at FAR)
supfar = max(bfs_ring(N[0], 7),
             key=lambda h: abs(h[0] - FAR[0]) + abs(h[1] - FAR[1]))
sg, tmp = stage([
    ("A 7 Arm 7", "Allied", N[0]),
    ("I Savena", "Axis", BASE),
    ("A Supply 1", "Allied", supfar),
    ("G 90Inf 55", "Axis", FAR),
    ("A 7A Inf 2", "Allied", FAR2),
], seed, first="Allied")
A, D, S = by_slot(sg, "A 7 Arm 7"), by_slot(sg, "I Savena"), by_slot(sg, "A Supply 1")
sg.submit("Allied", {"type": "end_movement"})
expect(sg, "Allied", {"type": "battle", "attackers": [A["pid"]],
                      "defenders": [D["pid"]], "supply": S["pid"]},
       False, "supply beyond the five-hex radius is illegal [14.2]", "14.2")
replay(sg, tmp, "supply radius")

# fig 15 carve-out: supply INSIDE the defender's ZOC still sustains the
# attack on that defender; a different enemy's ZOC on the supply hex blocks.
seed = find_seed([1])                    # 1-1 die 1 -> D Elim
sg, tmp = stage([
    ("A 7 Arm 7", "Allied", N[0]),
    ("I Savena", "Axis", BASE),
    ("A Supply 1", "Allied", N[1]),      # adjacent to the defender = in its ZOC
    ("G 90Inf 55", "Axis", FAR),
    ("A 7A Inf 2", "Allied", FAR2),
], seed, first="Allied")
A, D, S = by_slot(sg, "A 7 Arm 7"), by_slot(sg, "I Savena"), by_slot(sg, "A Supply 1")
sg.submit("Allied", {"type": "end_movement"})
r = expect(sg, "Allied", {"type": "battle", "attackers": [A["pid"]],
                          "defenders": [D["pid"]], "supply": S["pid"]},
           True, "supply in the ATTACKED unit's ZOC sustains the attack "
                 "(13.2 + clarifications fig 15)")
check(r["result"]["result"] == "DE" and D["pid"] not in sg.s["units"],
      "D Elim removed the defender [7.5]")
expect(sg, "Allied", {"type": "end_phase"}, True, "turn ends clean")
replay(sg, tmp, "fig-15 carve-out")

SUP = SAFE2[0]
blk = next(nb for nb in ring(SUP)
           if g.hex_terrain(*nb) == "clear" and nb != N[0] and nb != BASE)
seed = find_seed([1])
sg, tmp = stage([
    ("A 7 Arm 7", "Allied", N[0]),
    ("I Savena", "Axis", BASE),
    ("A Supply 1", "Allied", SUP),
    ("G 15Pz 33", "Axis", blk),          # UNINVOLVED enemy: its ZOC covers the supply
    ("A 7A Inf 2", "Allied", FAR2),
], seed, first="Allied")
A, D, S = by_slot(sg, "A 7 Arm 7"), by_slot(sg, "I Savena"), by_slot(sg, "A Supply 1")
blocker = by_slot(sg, "G 15Pz 33")
check((S["col"], S["row"]) in g.zoc_by_unit(sg.rules_board(), "Axis")[blocker["pid"]],
      "stage: the uninvolved blocker's ZOC covers the supply hex")
sg.submit("Allied", {"type": "end_movement"})
expect(sg, "Allied", {"type": "battle", "attackers": [A["pid"]],
                      "defenders": [D["pid"]], "supply": S["pid"]},
       False, "an UNINVOLVED enemy's ZOC on the supply hex blocks the "
              "route (fig 12 flavor) [14.2]", "14.2")

print("=== 3c. EXCHANGE: both rulebook 7.5 worked examples ===")
# example 1: doubled 2-3-4 attacked by seven 1-1-6 at 1-1 -> exchange:
# the 2-3-4 is lost along with SIX of the seven 1-1-6s.
esc = None
for key, v in sorted(g.terrain["hexes"].items()):
    if v["t"] != "escarpment":
        continue
    c, r = int(key[:2]), int(key[2:])
    nbs = [nb for nb in g.neighbors(c, r) if g.hex_terrain(*nb) == "clear"]
    if len(nbs) >= 4:
        esc, ESCN = (c, r), nbs
        break
assert esc, "no escarpment hex with 4 clear neighbors"
seed = find_seed([2])                    # 1-1 die 2 -> Exchange
units = [("I Pavia", "Axis", esc)]      # 2-3-4, defense doubled to 6
for i, s in enumerate(ALLIED116[:7]):
    units.append((s, "Allied", ESCN[i % 3]))     # 3+3+1 in three adjacent hexes
units.append(("A Supply 1", "Allied", ESCN[3]))
units.append(("G 90Inf 55", "Axis", FAR))
sg, tmp = stage(units, seed, first="Allied")
atk = [by_slot(sg, s)["pid"] for s in ALLIED116[:7]]
D = by_slot(sg, "I Pavia")
S = by_slot(sg, "A Supply 1")
sg.submit("Allied", {"type": "end_movement"})
r = expect(sg, "Allied", {"type": "battle", "attackers": atk,
                          "defenders": [D["pid"]], "supply": S["pid"]},
           True, "seven 1-1-6 attack a DOUBLED 2-3-4 on an escarpment")
check(r["result"]["odds"] == "1-1" and r["result"]["factors"] == [7, 6],
      f"7 attack vs 6 doubled defense -> 1-1 [10.2] ({r['result']['factors']})")
check(r["result"]["result"] == "EX", "die 2 at 1-1 -> Exchange")
check(D["pid"] not in sg.s["units"],
      "the defender (fewer factors: 6 < 7) removed all units [7.5]")
expect(sg, "Allied", {"type": "end_phase"}, False,
       "the exchange must be settled before anything else [8.6]", "8.6")
expect(sg, "Allied", {"type": "exchange_loss", "units": atk[:5]},
       False, "five 1-1-6s (5 factors) do not reach 6 [7.5]", "do not reach")
expect(sg, "Allied", {"type": "exchange_loss", "units": atk[:7]},
       False, "removing all seven over-pays: the seventh is not needed [7.5]",
       "not needed")
expect(sg, "Axis", {"type": "exchange_loss", "units": atk[:6]},
       False, "the LOSER of the exchange does not choose the winner's losses",
       "owes")
expect(sg, "Allied", {"type": "exchange_loss", "units": atk[:6]},
       True, "SIX of the seven 1-1-6s satisfy the exchange — the rulebook's "
             "own arithmetic [7.5 example 1]")
check(sum(1 for p in atk if p in sg.s["units"]) == 1,
      "exactly one 1-1-6 survives, as the rulebook example states")
expect(sg, "Allied", {"type": "end_phase"}, True, "turn ends after settlement")
replay(sg, tmp, "exchange example 1")

# example 2: a 3-4-6 attacking four 1-1-6s at 1-2 -> exchange: the 3-4-6
# is eliminated along with THREE of the four 1-1-6s.
seed = find_seed([2])                    # 1-2 die 2 -> Exchange
units = [("I Trieste", "Axis", BASE)]   # 3-4-6 attacker
defs = []
for i, s in enumerate(ALLIED116[:4]):
    units.append((s, "Allied", N[i]))   # four defenders around it
units.append(("G Supply 1", "Axis", N[4]))   # beside the attacker (carve-out)
units.append(("G 90Inf 55", "Axis", FAR))    # bystander: Axis keeps a combat unit
sg, tmp = stage(units, seed, first="Axis")
A = by_slot(sg, "I Trieste")
defs = [by_slot(sg, s)["pid"] for s in ALLIED116[:4]]
GS = by_slot(sg, "G Supply 1")
sg.submit("Axis", {"type": "end_movement"})
r = expect(sg, "Axis", {"type": "battle", "attackers": [A["pid"]],
                        "defenders": defs, "supply": GS["pid"]},
           True, "one 3-4-6 attacks four 1-1-6s at 1-2 (supplied)")
check(r["result"]["odds"] == "1-2" and r["result"]["factors"] == [3, 4],
      f"3 attack vs 4 defense -> 1-2 [7.3] ({r['result']['factors']})")
check(r["result"]["result"] == "EX" and A["pid"] not in sg.s["units"],
      "Exchange: the attacker (3 < 4) removes all his units [7.5]")
expect(sg, "Allied", {"type": "exchange_loss",
                      "units": defs[:3]},
       True, "THREE of the four 1-1-6s satisfy the exchange [7.5 example 2]")
check(sum(1 for p in defs if p in sg.s["units"]) == 1,
      "exactly one defending 1-1-6 survives, as the rulebook states")
expect(sg, "Axis", {"type": "end_phase"}, True, "turn ends")
replay(sg, tmp, "exchange example 2")

print("=== 3d. AUTO-ELIM >6-1, illegal <1-6, 11.7/11.8, 8.5 ===")
seed = find_seed([4])
sg, tmp = stage([
    ("G 21Pz 5", "Axis", N[0]),          # 7-7-10
    ("G 15Pz 115", "Axis", N[1]),        # 3-3-10
    (ALLIED116[0], "Allied", BASE),      # 1-1-6
    (ALLIED116[1], "Allied", FAR),
    ("G Supply 1", "Axis", SAFE2[0]),
    ("G 90Inf 200", "Axis", SAFE2[1]),   # never fights: probes the dead hex
], seed, first="Axis")
PZ = by_slot(sg, "G 21Pz 5")
PZ2 = by_slot(sg, "G 15Pz 115")
D = by_slot(sg, ALLIED116[0])
GS = by_slot(sg, "G Supply 1")
sg.submit("Axis", {"type": "end_movement"})
expect(sg, "Axis", {"type": "battle", "attackers": [PZ["pid"]],
                    "defenders": [by_slot(sg, ALLIED116[1])["pid"]],
                    "supply": GS["pid"]},
       False, "attacking a NON-adjacent defender is illegal [8.5]", "8.5")
rng_before = sg.s["rng_calls"]
r = expect(sg, "Axis", {"type": "battle",
                        "attackers": [PZ["pid"], PZ2["pid"]],
                        "defenders": [D["pid"]], "supply": GS["pid"]},
           True, "10 attack factors vs 1: odds above 6-1")
check(r["result"]["column"] == "auto_elim" and r["result"]["roll"] is None
      and sg.s["rng_calls"] == rng_before,
      "greater than 6-1: automatic elimination, NO die rolled [7.4/9.1 + CRT note]")
check(D["pid"] not in sg.s["units"], "defender auto-eliminated")
expect(sg, "Axis", {"type": "battle",
                    "attackers": [by_slot(sg, "G 90Inf 200")["pid"]],
                    "defenders": [D["pid"]]},
       False, "the eliminated defender cannot be attacked again", "not an enemy")
expect(sg, "Axis", {"type": "end_phase"}, True, "turn ends")
replay(sg, tmp, "auto-elim")

seed = find_seed([2])                    # 1-4 die 2 -> A Elim (clean finish)
sg, tmp = stage([
    (ALLIED116[0], "Allied", N[0]),
    (ALLIED116[1], "Allied", N[2]),
    ("G 21Pz 5", "Axis", BASE),          # 7-7-10 monster
    ("A Supply 1", "Allied", SAFE2[0]),
    ("A 7A Inf 2", "Allied", FAR),
], seed, first="Allied")
u1, u2 = by_slot(sg, ALLIED116[0]), by_slot(sg, ALLIED116[1])
PZ = by_slot(sg, "G 21Pz 5")
sg.submit("Allied", {"type": "end_movement"})
expect(sg, "Allied", {"type": "battle", "attackers": [u1["pid"]],
                      "defenders": [PZ["pid"]]},
       False, "a lone 1-1-6 vs 7-7-10 is 1-7: no voluntary attack worse "
              "than 1-6 [7.4]", "7.4")
r = expect(sg, "Allied", {"type": "battle", "attackers": [u1["pid"], u2["pid"]],
                          "defenders": [PZ["pid"]]},
           True, "two 1-1-6s together reach 2:7 = 1-4 — legal, no supply "
                 "needed [14.3]")
check(r["result"]["odds"] == "1-4" and r["result"]["result"] == "AE",
      "die 2 at 1-4 -> A Elim; the soak-off costs both units [11.6]")
expect(sg, "Allied", {"type": "end_phase"}, True, "turn ends")
replay(sg, tmp, "min odds soak-off")

print("=== 3d2. ONE BATTLE PER UNIT PER TURN [11.7/11.8] + orphan guard ===")
D2H = next(nb for nb in ring(FAR2) if g.hex_terrain(*nb) == "clear")
GS2H = next(nb for nb in ring(FAR2)
            if g.hex_terrain(*nb) == "clear" and nb != D2H)
seed = find_seed([3, 5])                 # 3-1 die 3 -> DB2; 1-2 die 5 -> AE
sg, tmp = stage([
    ("G 15Pz 115", "Axis", N[0]),        # 3-3-10 vs D1
    (ALLIED116[0], "Allied", BASE),      # D1
    ("G 90Inf 55", "Axis", FAR2),        # 2-2-7 vs D2 (a separate pair)
    ("A 7 Arm 4", "Allied", D2H),        # D2: 4-4-7 beside it
    ("G Supply 1", "Axis", SAFE2[0]),
    ("G Supply 2", "Axis", GS2H),
], seed, first="Axis")
A1 = by_slot(sg, "G 15Pz 115")
A2 = by_slot(sg, "G 90Inf 55")
D1 = by_slot(sg, ALLIED116[0])
D2 = by_slot(sg, "A 7 Arm 4")
GS = by_slot(sg, "G Supply 1")
GS2 = by_slot(sg, "G Supply 2")
sg.submit("Axis", {"type": "end_movement"})
r = expect(sg, "Axis", {"type": "battle", "attackers": [A1["pid"]],
                        "defenders": [D1["pid"]], "supply": GS["pid"]},
           True, "first battle: 3-3-10 vs 1-1-6 at 3-1")
check(r["result"]["result"] == "DB2", "die 3 at 3-1 -> D back 2")
ezoc = g.zoc_hexes(sg.rules_board(), "Axis")
occ = {(u["col"], u["row"]) for u in sg.s["units"].values() if sg.on_map(u)}
dh = (D1["col"], D1["row"])
h1, h2 = next((a, b) for a in ring(dh) for b in ring(a)
              if a not in ezoc and b not in ezoc and a not in occ
              and b not in occ and g.on_map(*a) and g.on_map(*b)
              and b != dh and b != a)
expect(sg, "Axis", {"type": "retreat", "unit": D1["pid"],
                    "path": [list(h1), list(h2)]},
       True, "the winner retreats the defender two hexes")
expect(sg, "Axis", {"type": "battle", "attackers": [A1["pid"]],
                    "defenders": [D1["pid"]]},
       False, "the same attacker may not fight a second battle [11.8]", "11.8")
expect(sg, "Axis", {"type": "battle", "attackers": [A2["pid"]],
                    "defenders": [D1["pid"]]},
       False, "the same defender may not be attacked twice in a turn [11.7]",
       "11.7")
r = expect(sg, "Axis", {"type": "battle", "attackers": [A2["pid"]],
                        "defenders": [D2["pid"]], "supply": GS2["pid"]},
           True, "the second pair fights its own battle at 1-2 (supplied)")
check(r["result"]["result"] == "AE", "die 5 at 1-2 -> A Elim")
expect(sg, "Axis", {"type": "end_phase"}, True,
       "all obligations discharged; turn ends")
replay(sg, tmp, "11.7/11.8")

print("=== 3d3. ORPHAN GUARD: partitions must let every unit attack ===")
seed = find_seed([3])
sg, tmp = stage([
    ("G 15Pz 115", "Axis", N[0]),        # both Axis units in D's ZOC...
    ("G 90Inf 55", "Axis", N[2]),
    (ALLIED116[0], "Allied", BASE),      # ...their ONLY adjacent enemy
    ("G Supply 1", "Axis", SAFE2[0]),
    ("A 7A Inf 2", "Allied", FAR),
], seed, first="Axis")
A1 = by_slot(sg, "G 15Pz 115")
A2 = by_slot(sg, "G 90Inf 55")
D = by_slot(sg, ALLIED116[0])
GS = by_slot(sg, "G Supply 1")
sg.submit("Axis", {"type": "end_movement"})
expect(sg, "Axis", {"type": "battle", "attackers": [A1["pid"]],
                    "defenders": [D["pid"]], "supply": GS["pid"]},
       False, "a battle that would strand the OTHER unit in the defender's "
              "ZOC with nothing left to attack is an illegal partition "
              "[11.31-11.33]", "11.3")
r = expect(sg, "Axis", {"type": "battle",
                        "attackers": [A1["pid"], A2["pid"]],
                        "defenders": [D["pid"]], "supply": GS["pid"]},
           True, "both units attack together: 5-1")
check(r["result"]["odds"] == "5-1", "5 attack factors vs 1 -> 5-1")
replay(sg, tmp, "orphan guard")

print("=== 3e. RETREATS 7.6/7.61/7.62 + clarification 9, advance 16.1 ===")
# DB2 on an escarpment defender, then advance after combat
seed = find_seed([3])                    # 3-1 die 3 -> D back 2
FARE = roomy(bfs_ring(esc, 10))          # bystander far from THIS cluster
sg, tmp = stage([
    ("G 21Pz 5", "Axis", ESCN[0]),       # 7-7-10 vs doubled 1-1-6 = 7:2 = 3-1
    (ALLIED116[0], "Allied", esc),
    ("G Supply 1", "Axis",
     next(c for c in ring(ESCN[0])
          if c != esc and g.hex_terrain(*c) == "clear")),
    ("A 7A Inf 2", "Allied", FARE),
], seed, first="Axis")
PZ = by_slot(sg, "G 21Pz 5")
D = by_slot(sg, ALLIED116[0])
GS = by_slot(sg, "G Supply 1")
sg.submit("Axis", {"type": "end_movement"})
r = expect(sg, "Axis", {"type": "battle", "attackers": [PZ["pid"]],
                        "defenders": [D["pid"]], "supply": GS["pid"]},
           True, "7-7-10 attacks a doubled 1-1-6 on an escarpment at 3-1 [10.2]")
check(r["result"]["odds"] == "3-1" and r["result"]["result"] == "DB2",
      "die 3 at 3-1 -> D back 2 (the 23.7 example's row)")
pend = sg.s["pending"]
check(pend and pend["kind"] == "retreat" and pend["chooser"] == "Axis",
      "the ATTACKER (winner) retreats the defending units [7.5]")
expect(sg, "Allied", {"type": "retreat", "unit": D["pid"],
                      "path": [list(h) for h in
                               [n for n in ring(esc) if g.hex_terrain(*n) == "clear"][:1] * 2]},
       False, "the LOSER may not choose the retreat route [7.5]", "winner")
# a legal 2-hex route away from the attacker's ZOC
ezoc = g.zoc_hexes(sg.rules_board(), "Axis")
occ = {(u["col"], u["row"]) for u in sg.s["units"].values() if sg.on_map(u)}
h1, h2 = next((a, b) for a in ring(esc) for b in ring(a)
              if a not in ezoc and b not in ezoc and a not in occ
              and b not in occ and g.on_map(*a) and g.on_map(*b)
              and b != esc and b != a)
bad = next((n for n in ring(esc) if n in ezoc and g.on_map(*n)), None)
if bad:
    expect(sg, "Axis", {"type": "retreat", "unit": D["pid"],
                        "path": [list(bad), list(h2)]},
           False, "retreat into enemy ZOC is illegal while safe routes exist "
                  "[7.61/7.62]", "")
expect(sg, "Axis", {"type": "retreat", "unit": D["pid"],
                    "path": [list(h1), list(esc)]},
       False, "retreating back into the battle hex is illegal "
              "[clarifications 9]", "")
expect(sg, "Axis", {"type": "retreat", "unit": D["pid"], "eliminate": True},
       False, "eliminating while survival routes exist is illegal [7.62]",
       "7.62")
expect(sg, "Axis", {"type": "retreat", "unit": D["pid"],
                    "path": [list(h1), list(h2)]},
       True, "a legal zigzag retreat two hexes away [7.6]")
check([D["col"], D["row"]] == list(h2), "defender moved by the winner")
pend = sg.s["pending"]
check(pend and pend["kind"] == "advance" and pend["hexes"] == [list(esc)],
      "the vacated ESCARPMENT hex opens advance after combat [16.1]")
expect(sg, "Axis", {"type": "advance", "unit": PZ["pid"], "hex": list(esc)},
       True, "the surviving attacker advances into the vacated hex [16.1]")
check([PZ["col"], PZ["row"]] == list(esc), "attacker stands on the escarpment")
expect(sg, "Axis", {"type": "end_phase"}, True, "turn ends")
replay(sg, tmp, "DB2 + advance")

print("=== 3f. FORTRESS: 23.1 all-in, 23.7 no-retreat elimination ===")
TOB = (31, 11)
land = [n for n in ring(TOB) if g.on_map(*n)]
# Axis attack units on every land neighbor, total attack <= 7 for 3-1 vs 2
axis_pool = [("G 15Pz 115", 3), ("G 90Inf 55", 2), ("G 90Inf 200", 2),
             ("G 164Inf 125", 2), ("I Savena", 2)]
picked, total = [], 0
for slot, a in axis_pool:
    if len(picked) < len(land):
        picked.append(slot)
        total += a
seed = find_seed([3])                    # 3-1 die 3 -> DB2 -> no retreat -> dead
units = [(ALLIED116[0], "Allied", TOB), (ALLIED116[1], "Allied", TOB)]
for i, h in enumerate(land):
    units.append((picked[i % len(picked)] if i < len(picked) else axis_pool[-1][0],
                  "Axis", h))
units = units[:2 + len(land)]
units.append(("G Supply 1", "Axis",
              next(n for n in ring(land[0]) if g.on_map(*n) and n not in land
                   and n != TOB and g.hex_terrain(*n) in ("clear", "escarpment"))))
units.append(("A 7A Inf 2", "Allied", FAR))
sg, tmp = stage(units, seed, first="Axis")
g1, g2 = by_slot(sg, ALLIED116[0]), by_slot(sg, ALLIED116[1])
GS = by_slot(sg, "G Supply 1")
atk_pids = [u["pid"] for u in sg.s["units"].values()
            if u["side"] == "Axis" and sg._is_combat(u)
            and (u["col"], u["row"]) in [tuple(h) for h in land]]
check((tuple(TOB) not in g.zoc_hexes(sg.rules_board(), "Axis")),
      "attackers adjacent to Tobruch exert NO ZOC into the fortress [19.5/23.1]")
check((tuple(land[0]) not in g.zoc_hexes(sg.rules_board(), "Allied")),
      "the garrison exerts NO ZOC out of the fortress [7.1/23.1 - the "
      "outward-immunity defect fix]")
expect(sg, "Axis", {"type": "end_phase"}, True,
       "besieging without attacking is LEGAL — fortress attacks are optional "
       "both ways [23.1/23.2]")
# Allied turn: garrison need not attack either
expect(sg, "Allied", {"type": "end_phase"}, True,
       "the garrison may also decline to attack [23.2]")
# Axis turn 2: attack the fortress — must engage ALL units in it
expect(sg, "Axis", {"type": "end_movement"}, True, "combat portion opens")
expect(sg, "Axis", {"type": "battle", "attackers": atk_pids,
                    "defenders": [g1["pid"]], "supply": GS["pid"]},
       False, "attacking into a fortress must engage ALL units in it [23.1]",
       "23.1")
r = expect(sg, "Axis", {"type": "battle", "attackers": atk_pids,
                        "defenders": [g1["pid"], g2["pid"]],
                        "supply": GS["pid"]},
           True, "the whole garrison is attacked together")
check(r["result"]["factors"][1] == 4,
      f"two 1-1-6s DOUBLED in the fortress = 4 defense [10.2] "
      f"({r['result']['factors']})")
if r["result"]["result"] == "DB2":
    expect(sg, "Axis", {"type": "retreat", "unit": g1["pid"],
                        "path": [list(land[0]), list(land[1])]},
           False, "no retreat route out of the besieged fortress is legal "
                  "[7.61/23.7]", "")
    expect(sg, "Axis", {"type": "retreat", "unit": g1["pid"], "eliminate": True},
           True, "surrounded by ZOC and the sea: the back-2 result eliminates "
                 "[23.7]")
    expect(sg, "Axis", {"type": "retreat", "unit": g2["pid"], "eliminate": True},
           True, "the second garrison unit dies the same way [23.7]")
    pend = sg.s["pending"]
    check(pend and pend["kind"] == "advance" and list(TOB) in pend["hexes"],
          "the emptied fortress opens advance after combat [16.1]")
    expect(sg, "Axis", {"type": "advance", "unit": atk_pids[0],
                        "hex": list(TOB)},
           True, "an attacker advances into Tobruch [16.1]")
expect(sg, "Axis", {"type": "end_phase"}, True, "turn ends")
replay(sg, tmp, "fortress siege")

print("=== 3g. 11.9 trapped units + forced elimination 7.4 ===")
# isolated in enemy ZOC, no supply anywhere, only a 1-7 'attack' available:
# eliminated automatically at end_movement (clarifications sec. 5)
seed = find_seed([1])
sg, tmp = stage([
    (ALLIED116[0], "Allied", N[0]),
    ("G 21Pz 5", "Axis", BASE),
    ("A 7A Inf 2", "Allied", FAR),       # far bystander, not in ZOC
], seed, first="Allied")
doomed = by_slot(sg, ALLIED116[0])
r = expect(sg, "Allied", {"type": "end_movement"}, True,
           "end_movement sweeps trapped units")
check(doomed["pid"] not in sg.s["units"],
      "isolated in enemy ZOC with no legal supply-free attack: eliminated "
      "BEFORE combat [11.9, clarifications 5]")
expect(sg, "Allied", {"type": "end_phase"}, True, "no obligations remain")
replay(sg, tmp, "11.9 sweep")

# same but with a supply in range: unit survives movement, but its only
# 'attack' is 1-7, so it must be force-eliminated before battles [7.4]
seed = find_seed([1])
sg, tmp = stage([
    (ALLIED116[0], "Allied", N[0]),
    ("G 21Pz 5", "Axis", BASE),
    ("A Supply 1", "Allied", SAFE2[0]),
    ("A 7A Inf 2", "Allied", FAR),
], seed, first="Allied")
doomed = by_slot(sg, ALLIED116[0])
sg.submit("Allied", {"type": "end_movement"})
check(doomed["pid"] in sg.s["units"],
      "with supply reachable the unit is NOT auto-eliminated (not isolated)")
expect(sg, "Allied", {"type": "end_phase"}, False,
       "but it is in enemy ZOC and must attack [8.4]", "8.4")
expect(sg, "Allied", {"type": "forced_elim", "unit": doomed["pid"]}, True,
       "its only option is 1-7: eliminated before any battle [7.4]")
expect(sg, "Allied", {"type": "end_phase"}, True, "turn may end now")
replay(sg, tmp, "forced elim")

# forced_elim on a unit that HAS a legal attack must be rejected
seed = find_seed([1])
sg, tmp = stage([
    (ALLIED116[0], "Allied", N[0]),
    ("I Savena", "Axis", BASE),          # 1 vs 2-2-4: 1:2 = 1-2... supply needed
    ("A Supply 1", "Allied", SAFE2[0]),
    ("A 7A Inf 2", "Allied", FAR),
], seed, first="Allied")
u = by_slot(sg, ALLIED116[0])
sg.submit("Allied", {"type": "end_movement"})
expect(sg, "Allied", {"type": "forced_elim", "unit": u["pid"]},
       False, "a unit with a legal (supplied 1-2) attack may not be "
              "force-eliminated [8.4]", "")
replay(sg, tmp, "forced elim rejected")

print("=== 3h. ZOC anomalies: E18-F19 water hexside [7.1/5.7] ===")
E18, F19 = (25, 9), (26, 10)
if g.hex_terrain(*E18) and g.hex_terrain(*F19) \
   and F19 in g.neighbors(*E18) and g.hexside_prohibited(E18, F19):
    board = [dict(id="x", name="G 90Inf 55", side="Axis",
                  col=E18[0], row=E18[1])]
    check(F19 not in g.zoc_hexes(board, "Axis"),
          "a unit on E18 exerts NO ZOC into F19 across the water hexside "
          "[7.1 exceptions]")
    seed = find_seed([1])
    sg, tmp = stage([
        ("G 90Inf 55", "Axis", E18),
        (ALLIED116[0], "Allied", F19),
        ("G Supply 1", "Axis", FAR),
        ("A 7A Inf 2", "Allied", FAR2),
    ], seed, first="Axis")
    a = by_slot(sg, "G 90Inf 55")
    d = by_slot(sg, ALLIED116[0])
    expect(sg, "Axis", {"type": "end_movement"}, True, "no obligations arise")
    expect(sg, "Axis", {"type": "battle", "attackers": [a["pid"]],
                        "defenders": [d["pid"]]},
           False, "units on the E18/F19 anomalous hexes may not engage each "
                  "other in battle [5.7]", "")
    replay(sg, tmp, "anomalous hexside")
else:
    check(False, "E18-F19 anomaly hexes not found where expected")

print("=== 3i. VICTORY 4.1-4.3: elimination + two-turn control ===")
seed = find_seed([1])                    # 6-1... no: 7:1 auto-elim, no roll
sg, tmp = stage([
    ("G 21Pz 5", "Axis", N[0]),
    (ALLIED116[0], "Allied", BASE),      # the LAST Allied combat unit
    ("G Supply 1", "Axis", SAFE2[0]),
], seed, first="Axis")
PZ = by_slot(sg, "G 21Pz 5")
D = by_slot(sg, ALLIED116[0])
GS = by_slot(sg, "G Supply 1")
sg.submit("Axis", {"type": "end_movement"})
r = expect(sg, "Axis", {"type": "battle", "attackers": [PZ["pid"]],
                        "defenders": [D["pid"]], "supply": GS["pid"]},
           True, "the last Allied combat unit is auto-eliminated at 7-1")
check(sg.s["over"] and sg.s["winner"] == "Axis",
      "no Allied combat units on the board -> Axis WINS [4.1]")
expect(sg, "Axis", {"type": "end_phase"}, False, "the game is over", "over")
replay(sg, tmp, "elimination victory")

VICS = {(1, 27): "W3", (8, 12): "H2", (31, 11): "G25", (67, 14): "J62"}
seed = find_seed([1])
units = [(s, "Axis", h) for s, h in zip(
    ["G 90Inf 55", "G 90Inf 200", "G 164Inf 125", "G 15Pz 115"], VICS)]
units.append((ALLIED116[0], "Allied", FAR))
# supplies keep the 24.2/24.5 isolation clocks quiet during the 3 turns
units.append(("G Supply 1", "Axis", (1, 27)))
units.append(("A Supply 1", "Allied", FAR2))
sg, tmp = stage(units, seed, first="Axis", turns=8)
expect(sg, "Axis", {"type": "end_phase"}, True,
       "Axis holds both fortresses + both home bases at start AND end (streak 1)")
check(sg.s["vic_streak"]["Axis"] == 1 and not sg.s["over"],
      "one player turn of total control is not yet victory [4.1]")
expect(sg, "Allied", {"type": "end_phase"}, True, "Allied turn passes")
r = expect(sg, "Axis", {"type": "end_phase"}, True,
           "second consecutive Axis player turn of total control")
check(sg.s["over"] and sg.s["winner"] == "Axis",
      "two consecutive controlled Axis player turns -> Axis WINS [4.1/4.3]")
replay(sg, tmp, "control victory")

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
