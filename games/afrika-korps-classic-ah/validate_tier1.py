"""Afrika Korps Tier-1 FULL-scope gate validation: arrivals, supply dice,
sea movement, Rommel bonus, fortress ZOC immunity (spec #9/#12 evidence).

Every case is a rulebook-cited legal action or illegal proposal driven
through StrategicGame.submit(); the produced audit log then replays through
engine/verify_game.py (verdicts, dice, state hashes). The Rommel cases
replay the module tournament clarification's worked example verbatim
(Rommel W6->W8 with the El Agheila units; road + regular movement kept).

Run:  python games/afrika-korps-classic-ah/validate_tier1.py
"""
import json
import os
import shutil
import sys
import tempfile

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


def fresh(seed):
    tmp = tempfile.mkdtemp()
    sg = strategic.StrategicGame(
        g, os.path.join(HERE, "scenario_campaign.json"), tmp, seed=seed)
    return sg, tmp


def by_slot(sg, slot):
    return next(u for u in sg.s["units"].values() if u["slot"] == slot)


def pool_pid(sg, slot):
    return next(pid for pid in sg.s["pool"] if sg.schedule[pid]["slot"] == slot)


def expect(sg, side, action, legal, what, contains=None):
    r = sg.submit(side, action)
    ok = r["verdict"]["legal"] == legal
    if ok and contains:
        ok = any(contains in reason for reason in r["verdict"]["reasons"])
    check(ok, f"{what} -> {(r['verdict']['reasons'] or [str(r.get('result'))[:90]])[0]}")
    return r


W6, W3, G25, J62, H2 = [4, 27], [1, 27], [31, 11], [67, 14], [8, 12]

# =====================================================================
# a non-road desert corridor out of W6: exact MF+bonus budget boundaries
# need steps that consume the NORMAL budget only (no road hexsides, no
# stop-terrain) — built from the engine's own geometry, not guessed hexes.
roads = g._hex_road_sides()


def nonroad_chain(start, length, avoid=()):
    chain = [list(start)]
    seen = {tuple(start)} | {tuple(a) for a in avoid}
    cur = tuple(start)
    while len(chain) <= length:
        nxt = next((nb for nb in g.neighbors(*cur)
                    if nb not in seen
                    and nb not in roads.get(cur, set())
                    and g.move_cost(cur, nb) is not None
                    and g.hex_terrain(*nb) not in ("escarpment",)), None)
        assert nxt, f"desert chain dead-ends at {cur} ({len(chain)} hexes)"
        chain.append(list(nxt))
        seen.add(nxt)
        cur = nxt
    return chain


CH = nonroad_chain((4, 27), 8)          # 8 plain-desert edges out of W6

print("=== ROMMEL BONUS 22.1 (clarification interpretation, turn 1) ===")
sg, tmp1 = fresh(11)
rommel = by_slot(sg, "G Rommel")
sav = by_slot(sg, "I Savena")          # 2-2-4
pav = by_slot(sg, "I Pavia")           # 2-3-4
tre = by_slot(sg, "I Trenta")          # 2-3-4
pz5 = by_slot(sg, "G 21Pz 5")          # 7-7-10

expect(sg, "Axis", {"type": "move", "unit": sav["pid"], "dest": CH[6],
                    "path": CH[:7], "rommel_bonus": 2},
       False, "bonus claim BEFORE Rommel moved is ILLEGAL", "Rommel to have moved")

# Rommel escorts the first two chain hexes (his own path move, MF 12)
expect(sg, "Axis", {"type": "move", "unit": rommel["pid"], "dest": CH[2],
                    "path": CH[:3]},
       True, "Rommel moves 2 hexes out of W6 with an explicit path")

# exact budget boundary: MF 4 + escort 2 = 6 hexes legal, 7 illegal
expect(sg, "Axis", {"type": "move", "unit": sav["pid"], "dest": CH[6],
                    "path": CH[:7], "rommel_bonus": 2},
       True, "Savena 6 plain hexes (MF 4 + 2 escorted, shared 2-hex segment) is LEGAL")
expect(sg, "Axis", {"type": "move", "unit": pav["pid"], "dest": CH[7],
                    "path": CH[:8], "rommel_bonus": 2},
       False, "Pavia 7 plain hexes (MF 4 + 2 escorted + 1) is ILLEGAL", "illegal path")

# bonus without any shared segment: a route Rommel never used
branch = nonroad_chain((4, 27), 3, avoid=CH[1:])
expect(sg, "Axis", {"type": "move", "unit": pav["pid"], "dest": branch[3],
                    "path": branch, "rommel_bonus": 2},
       False, "bonus with NO shared 2-hex segment with Rommel is ILLEGAL",
       "does not move with")

# 1-hex co-move earns only +1 (clarification): share CH[0]->CH[1], diverge
div = next(nb for nb in g.neighbors(*CH[1])
           if nb not in (tuple(CH[0]), tuple(CH[2]))
           and nb not in roads.get(tuple(CH[1]), set())
           and g.move_cost(tuple(CH[1]), nb) is not None
           and g.hex_terrain(*nb) not in ("escarpment",))
p1 = [CH[0], CH[1], list(div)]
expect(sg, "Axis", {"type": "move", "unit": tre["pid"], "dest": p1[-1],
                    "path": p1, "rommel_bonus": 2},
       False, "claiming +2 with only a 1-hex shared segment is ILLEGAL",
       "does not move with")
expect(sg, "Axis", {"type": "move", "unit": tre["pid"], "dest": p1[-1],
                    "path": p1, "rommel_bonus": 1},
       True, "the same claim as +1 (1 shared hex = 1 bonus hex) is LEGAL")

# the clarification's Q&A: escort + coast road + regular movement combine.
# 21Pz/5's roadless reach is 10; with the +10 road budget the engine reaches
# col>=20; a path move claiming the bonus on top passes the same gate.
lm = sg.legal_moves(pz5["pid"])
far = max(lm["dests"], key=lambda d: d["col"])
check(far["col"] >= 20, f"MF10+road10 reaches col {far['col']} (>=20) without bonus")
expect(sg, "Axis", {"type": "move", "unit": pz5["pid"], "dest": CH[6],
                    "path": CH[:7], "rommel_bonus": 2},
       True, "a 10-MF unit combining escort with its regular budget passes "
             "the same one-door check (22.1 + 17.1 compose)")
sg2, tmp2 = sg, tmp1

print("=== ROMMEL EXTENSION (move first, escort later) ===")
sg3, tmp3 = fresh(12)
rr = by_slot(sg3, "G Rommel")
sav = by_slot(sg3, "I Savena")        # 2-2-4 at W6
# an eastward 6-hex corridor along row 27 (W6..W12) — all passable coast
corr = [[c, 27] for c in range(4, 11)]
for a, b in zip(corr, corr[1:]):
    assert g.move_cost(tuple(a), tuple(b)) is not None, f"corridor broken {a}-{b}"
# Savena moves its FULL 4 MF first, path recorded, no bonus
expect(sg3, "Axis", {"type": "move", "unit": sav["pid"], "dest": corr[4],
                     "path": corr[:5]},
       True, "Savena path-moves 4 hexes east (full MF, no bonus)")
expect(sg3, "Axis", {"type": "rommel_extend", "unit": sav["pid"],
                     "path": corr[4:]},
       False, "extension BEFORE Rommel moved is ILLEGAL", "Rommel to have moved")
# Rommel rides up the same corridor and escorts the last two hexes
expect(sg3, "Axis", {"type": "move", "unit": rr["pid"], "dest": corr[-1],
                     "path": corr},
       True, "Rommel moves the same corridor W6..W12 (6 of his 12 MF)")
expect(sg3, "Axis", {"type": "rommel_extend", "unit": sav["pid"],
                     "path": corr[4:]},
       True, "Savena's +2 extension along Rommel's route is LEGAL "
             "(clarification: units may move first, Rommel joins later)")
check([by_slot(sg3, "I Savena")["col"], by_slot(sg3, "I Savena")["row"]]
      == corr[-1], "Savena stands 6 hexes out (4 MF + 2 escorted)")
nxt = next(nb for nb in g.neighbors(*corr[-1])
           if g.move_cost(tuple(corr[-1]), nb) is not None)
expect(sg3, "Axis", {"type": "rommel_extend", "unit": sav["pid"],
                     "path": [corr[-1], list(nxt)]},
       False, "a SECOND extension for the same unit is ILLEGAL",
       "only once per turn")

print("=== ARRIVALS: turn-1 gates ===")
sg4, tmp4 = fresh(13)
expect(sg4, "Axis", {"type": "roll_supply"}, False,
       "Axis supply roll on turn 1 (no controlled port) is ILLEGAL", "first game turn")
pz8 = pool_pid(sg4, "G 15Pz 8")
expect(sg4, "Axis", {"type": "land_reinforcement", "unit": pz8, "port": W3},
       False, "landing 15Pz/8 on turn 1 (due 1 May) is ILLEGAL", "due 1 May 1941")
expect(sg4, "Axis", {"type": "move", "unit": pz8, "dest": W6},
       False, "MOVING an unlanded scheduled reinforcement is ILLEGAL",
       "scheduled reinforcement")
# Axis garrisons the home base W3 to control a port for later turns
bol = by_slot(sg4, "I Bologna")
expect(sg4, "Axis", {"type": "move", "unit": bol["pid"], "dest": W3},
       True, "Bologna W6->W3 garrisons the Axis home base (4.3 occupation)")
for slot in ["G 21Pz 104", "G 21Pz 3", "I Ariete", "I Brescia", "I Trenta"]:
    u = by_slot(sg4, slot)
    dd = sg4.legal_moves(u["pid"])["dests"]
    tgt = next(d for d in dd if (d["col"], d["row"]) != tuple(W6))
    sg4.submit("Axis", {"type": "move", "unit": u["pid"],
                        "dest": [tgt["col"], tgt["row"]]})
expect(sg4, "Axis", {"type": "roll_supply"}, False,
       "supply roll AFTER movement began is ILLEGAL", "precede movement")
expect(sg4, "Axis", {"type": "end_phase"}, True, "Axis turn 1 ends")

print("=== ARRIVALS: Allied supply (12.1) ===")
expect(sg4, "Allied", {"type": "land_supply", "port": J62}, False,
       "Allied supply at UNGARRISONED home base J62 is ILLEGAL", "controlled port")
expect(sg4, "Allied", {"type": "land_supply", "port": H2}, False,
       "Allied supply at Bengasi (fortress, not a port) is ILLEGAL", "controlled port")
r = expect(sg4, "Allied", {"type": "land_supply", "port": G25}, True,
           "Allied supply lands at controlled Tobruch (12.1)")
check(r["result"]["slot"] == "A Supply 2", "the next pool counter (A Supply 2) arrived")
expect(sg4, "Allied", {"type": "land_supply", "port": G25}, False,
       "a SECOND Allied supply the same turn is ILLEGAL", "ONE supply unit")
sup2 = r["result"]["placed"]
lm = sg4.legal_moves(sup2)
check(lm["can_act"], "the just-landed supply unit may move this turn (13.1)")
sub = next(pid for pid, e in sg4.reserve.items() if "Sub" in e["slot"])
expect(sg4, "Allied", {"type": "move", "unit": sub, "dest": G25},
       False, "substitute counters stay outside the Tier-1 scope",
       "outside this scenario")
# the March 1941 setup stacks 4 brigades at L59 (2.3 permits it during
# setup) — limits bind at the end of each player turn, so disperse one
l59 = by_slot(sg4, "A 4 I Inf 5")
dd = sg4.legal_moves(l59["pid"])["dests"]
tgt = next(d for d in dd if d["cost"] >= 1)
expect(sg4, "Allied", {"type": "move", "unit": l59["pid"],
                       "dest": [tgt["col"], tgt["row"]]},
       True, "one L59 brigade disperses (2.3/6.1 bind at end of the turn)")
expect(sg4, "Allied", {"type": "end_phase"}, True, "Allied turn 1 ends")

print("=== ARRIVALS: Axis Supply Table dice (12.2) — turn 2 ===")
check(sg4.s["turn"] == 2 and sg4.s["mover"] == "Axis", "turn 2 (15 April 1941), Axis")
check(sg4.s["ports"] == [W3], f"Axis controls W3 via the Bologna garrison: {sg4.s['ports']}")
r = expect(sg4, "Axis", {"type": "roll_supply"}, True,
           "Axis Supply Table roll with a controlled port is LEGAL")
roll1 = r["result"]["roll"]
check(r["result"]["sunk_on"] == [1, 2],
      f"April 1941 window: sunk on 1-2 (rolled {roll1}) [12.2 col Apr-Jun]")
expect(sg4, "Axis", {"type": "roll_supply"}, False,
       "a SECOND roll the same game turn is ILLEGAL", "once per game turn")
if roll1 >= 3:
    r = expect(sg4, "Axis", {"type": "land_supply", "port": W3}, True,
               "arrived Axis supply lands at W3")
    check(r["result"]["slot"] == "G Supply 2", "the next Axis counter (G Supply 2) arrived")
else:
    expect(sg4, "Axis", {"type": "land_supply", "port": W3}, False,
           "sunk supply cannot be landed", "no Axis supply unit")
expect(sg4, "Axis", {"type": "end_phase"}, True, "Axis turn 2 ends")
expect(sg4, "Allied", {"type": "end_phase"}, True, "Allied turn 2 ends (declines supply, 12.5)")

print("=== ARRIVALS: reinforcements land on their due turn (19.1-19.7) ===")
check(sg4.s["turn"] == 3 and sg4.turn_label() == "1 May 1941",
      "turn 3 = 1 May 1941 (reached through the gate, no state surgery)")
pz8 = pool_pid(sg4, "G 15Pz 8")
expect(sg4, "Axis", {"type": "land_reinforcement", "unit": pz8, "port": G25},
       False, "Axis reinforcement at ALLIED-held Tobruch is ILLEGAL", "controlled")
expect(sg4, "Axis", {"type": "land_reinforcement", "unit": pz8, "port": J62},
       False, "Axis reinforcement at the OPPONENT home base is ILLEGAL", "your own home base")
r = expect(sg4, "Axis", {"type": "land_reinforcement", "unit": pz8, "port": W3},
           True, "15Pz/8 lands at controlled W3 on its due turn (19.2)")
lm = sg4.legal_moves(pz8)
check(lm["can_act"] and lm["budget"] == 10,
      "landed 15Pz/8 may move its full MF 10 this turn (19.2)")
pz115 = pool_pid(sg4, "G 15Pz 115")
allied_due = pool_pid(sg4, "A 7 Arm 4")
expect(sg4, "Axis", {"type": "land_reinforcement", "unit": allied_due, "port": W3},
       False, "landing an ALLIED reinforcement on the Axis turn is ILLEGAL", "19.6")
mv = by_slot(sg4, "I Pavia")
dd = sg4.legal_moves(mv["pid"])["dests"]
tgt = next(d for d in dd if (d["col"], d["row"]) != tuple(W6))
sg4.submit("Axis", {"type": "move", "unit": mv["pid"], "dest": [tgt["col"], tgt["row"]]})
expect(sg4, "Axis", {"type": "land_reinforcement", "unit": pz115, "port": W3},
       False, "reinforcement placement AFTER movement began is ILLEGAL",
       "precede movement")
expect(sg4, "Axis", {"type": "end_phase"}, True,
       "Axis ends 1 May; 15Pz/115 and 33 Recce stay off-board (19.3 later landing)")

print("=== 19.3: later landing on a NON-due turn ===")
expect(sg4, "Allied", {"type": "end_phase"}, True, "Allied passes 1 May")
check(sg4.s["turn"] == 4, "turn 4 = 15 May 1941 (an empty OOA cell)")
r = expect(sg4, "Axis", {"type": "land_reinforcement", "unit": pz115, "port": W3},
           True, "15Pz/115 lands on 15 May — later than due is fine (19.3)")

print("=== verifier replay of the arrivals/dice session ===")
ok, msg = verify_game.verify(HERE, sg4.log_path)
check(ok, f"verify_game: {msg}")

print("=== SEA MOVEMENT 23.3-23.44 ===")
sg5, tmp5 = fresh(14)
# Axis turn 1: move 21Pz/5 to W3 (garrison); Bologna toward Tobruch later.
p5 = by_slot(sg5, "G 21Pz 5")
expect(sg5, "Axis", {"type": "move", "unit": p5["pid"], "dest": W3},
       True, "21Pz/5 garrisons W3")
expect(sg5, "Axis", {"type": "embark", "unit": p5["pid"]}, True,
       "21Pz/5 embarks from W3 the same turn it moved there (23.4 procedure)")
check(not sg5.on_map(sg5.unit(p5["pid"])), "21Pz/5 is at sea")
expect(sg5, "Axis", {"type": "debark", "unit": p5["pid"], "port": W3}, False,
       "landing the SAME player turn is ILLEGAL", "FOLLOWING friendly")
expect(sg5, "Axis", {"type": "move", "unit": p5["pid"], "dest": W6}, False,
       "map-moving a unit at sea is ILLEGAL", "at sea")
# disperse W6 (stacking) then end turn
for slot in ["G 21Pz 104", "G 21Pz 3", "I Ariete", "I Brescia", "I Trenta"]:
    u = by_slot(sg5, slot)
    dd = sg5.legal_moves(u["pid"])["dests"]
    tgt = next(d for d in dd if (d["col"], d["row"]) != tuple(W6))
    sg5.submit("Axis", {"type": "move", "unit": u["pid"],
                        "dest": [tgt["col"], tgt["row"]]})
expect(sg5, "Axis", {"type": "end_phase"}, True, "Axis turn 1 ends (unit at sea)")

# Allied turn 1: embark tests at Tobruch/Bengasi
gds = by_slot(sg5, "A 2 Arm 2 S.G")     # in Bengasi H2
expect(sg5, "Allied", {"type": "embark", "unit": gds["pid"]}, False,
       "embarking from BENGASI is ILLEGAL", "23.3")
tob = by_slot(sg5, "A 9A Inf 20")        # in Tobruch
expect(sg5, "Allied", {"type": "embark", "unit": tob["pid"]}, True,
       "embarking from Tobruch is LEGAL (fortress is never in enemy ZOC, 19.5/23.44)")
l59 = by_slot(sg5, "A 4 I Inf 5")
dd = sg5.legal_moves(l59["pid"])["dests"]
tgt = next(d for d in dd if d["cost"] >= 1)
sg5.submit("Allied", {"type": "move", "unit": l59["pid"],
                      "dest": [tgt["col"], tgt["row"]]})
expect(sg5, "Allied", {"type": "end_phase"}, True, "Allied turn 1 ends")

# Axis turn 2: W3 is EMPTY now (21Pz/5 at sea) -> not controlled -> landing barred
check(sg5.s["ports"] == [], "Axis controls no port at the start of turn 2 "
                            "(the garrison itself went to sea)")
expect(sg5, "Axis", {"type": "debark", "unit": p5["pid"], "port": W3}, False,
       "landing at a port NOT controlled at the start of the turn is ILLEGAL",
       "control the port")
r = expect(sg5, "Axis", {"type": "end_phase"}, True,
           "Axis ends turn 2 with 21Pz/5 still at sea")
check(any("ELIMINATED [23.42]" in e for e in r["result"]["events"]),
      "21Pz/5 is ELIMINATED — failed to return on the following friendly turn (23.42)")
check(p5["pid"] not in sg5.s["units"], "the eliminated unit left the game state")

# Allied turn 2: 9A/20 returns to the SAME port it left (23.43)
r = expect(sg5, "Allied", {"type": "debark", "unit": tob["pid"], "port": G25},
           True, "9A/20 lands back at Tobruch — same-port return (23.43/23.44)")
expect(sg5, "Allied", {"type": "embark", "unit": tob["pid"]}, False,
       "going back OUT to sea the turn it landed is ILLEGAL", "same turn")
lm = sg5.legal_moves(tob["pid"])
check(lm["can_act"], "the landed unit may still move inland (23.4)")
expect(sg5, "Allied", {"type": "end_phase"}, True, "Allied turn 2 ends")

print("=== verifier replay of the sea session ===")
ok, msg = verify_game.verify(HERE, sg5.log_path)
check(ok, f"verify_game: {msg}")

print("=== FORTRESS ZOC IMMUNITY (19.5/23.1) ===")
# H25=[31,12] is adjacent to Tobruch G25=[31,11] (rule 7.3/18 example chains)
check((31, 11) in g.neighbors(31, 12), "H25 is adjacent to Tobruch G25")
board = [dict(id="e1", name="G 21Pz 5", side="Axis", col=31, row=12)]
z = g.zoc_hexes(board, "Axis")
check((31, 11) not in z, "an Axis unit on H25 exerts NO ZOC over Tobruch (19.5)")
check(len(z) == 5, f"its other five neighbors ARE its ZOC ({len(z)}/5)")
# a unit INSIDE the fortress is not ZOC-pinned: 8.3's same-unit first-step
# ban does not apply because the fortress hex is not in the enemy's ZOC
me = dict(id="a1", name="A 9A Inf 20", side="Allied", col=31, row=11)
dd = g.legal_destinations_t(me, 6, board + [me])
h26 = (32, 12)
check((31, 11) in g.neighbors(*h26) and (31, 12) in g.neighbors(*h26),
      "H26 is adjacent to both G25 and the enemy on H25")
check(h26 in dd, "the garrison may step OUT of Tobruch directly into the "
                 "adjacent enemy's ZOC (stop on entry, 8.1) — it was never "
                 "ZOC-locked inside the fortress (19.5)")

for t in (tmp1, tmp2, tmp3, tmp4, tmp5):
    shutil.rmtree(t, ignore_errors=True)
print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILURES'}")
sys.exit(1 if fails else 0)
