"""Afrika Korps movement-gate validation (spec #12 evidence, re-runnable).

Every case is a worked example quoted from AfrikaKorps_3d_Ed_Rules.pdf
(section cited). trace_path() runs the SAME step-legality code as the
engine's legal-destination search, so a PASS here validates the gate.

Run:  python games/afrika-korps-classic-ah/validate_movement.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "engine"))
import gamespec

g = gamespec.load(os.path.dirname(os.path.abspath(__file__)))


def cr(name):
    li = ord(name[0]) - ord("A")
    return int(name[1:]) - li // 2 + 9, li + 5


def U(name, at, side="Axis", uid="t1"):
    c, r = cr(at)
    return dict(id=uid, name=name, side=side, col=c, row=r)


fails = []


def check(cond, what):
    print(("  PASS  " if cond else "  FAIL  ") + what)
    if not cond:
        fails.append(what)


def path_case(want_legal, ma, chain, cite, board=()):
    unit = U("G 15Pz 8", chain[0])          # 3-3-10 (any combat unit works)
    legal, why = g.trace_path(unit, ma, list(board), [cr(h) for h in chain])
    check(legal == want_legal,
          f"{'-'.join(chain)} {'LEGAL' if want_legal else 'ILLEGAL'} ({cite}) -> {why}")


print("rule 18 worked path examples:")
path_case(True, 6, ["G25", "H26", "I27", "J27", "J28"],
          "rule 18 ex.3: Tobruch sortie, one non-road move")
path_case(False, 6, ["G25", "H26", "I27", "J28"],
          "rule 18 ex.3: I27/J28 would be a second non-road move")
path_case(True, 10, ["H24", "I25", "I26", "J27", "I27", "I28", "H28", "H29", "I30"],
          "rule 18 ex.1: legal 8-step road ride ending on escarpment I30")
path_case(True, 6, ["G22", "H23", "H24", "H25", "H26", "H27"],
          "rule 18 ex.2: H25/H26 is the single non-road move")
path_case(False, 6, ["G24", "H24", "H25", "H26"],
          "rule 18 ex.1: cannot move on (H24) and off (H26) same turn")
path_case(True, 6, ["G24", "H24", "H23"],
          "rule 18 ex.1: onto H24 then along the road, no delay")
path_case(False, 6, ["G24", "H24", "I24"],
          "18.41: after non-road entry to H24, a non-road exit (I24) "
          "is a second non-road move")

print("rule 17.3 two-road hex I26:")
path_case(True, 6, ["I25", "I26", "J27", "I26"],
          "17.32: out and back in along the proper hexside")
path_case(True, 6, ["I25", "I26", "H26"],
          "17.32: road transfer inside I26 allowed at MP cost, counts per 18.5")
path_case(False, 6, ["I25", "I26", "H26", "I27"],
          "17.32+18.5: the transfer used the allowance; H26/I27 would be second")

print("rule 5.6/5.7 terrain prohibitions:")
path_case(False, 6, ["Q60", "R60"], "5.6: full Qattara hex impassable")
path_case(True, 6, ["Q60", "Q61"], "5.6: partial Qattara plays as clear")
path_case(False, 6, ["E18", "F19"], "5.7: all-water hexside")
path_case(False, 6, ["W62", "X62"], "5.7: Qattara Depression hexside")
path_case(False, 6, ["S68", "R68"], "5.8: partial east-edge hex")

print("rule 17.1 coast road bonus (worked example: 2-2-6 moves 16 hexes):")
# walk the road-hexside graph eastward from H30 to build a pure road chain
roads = g._hex_road_sides()
chain = [cr("H29"), cr("H30")]
while len(chain) < 17:
    nxt = [h for h in roads.get(chain[-1], ()) if h != chain[-2]]
    if not nxt:
        break
    chain.append(max(nxt, key=lambda h: h[0]))
unit = U("A 4 I Inf 23", "H29", side="Allied")
if len(chain) >= 17:
    legal16, why16 = g.trace_path(unit, 6, [], chain[:17])   # 16 steps
    check(legal16, f"16 consecutive road hexes with MA 6 (17.1) -> {why16}")
sixteen_plus = chain[:17]
# 17 road steps must fail for MA 6 (10 road + 6 normal max)
if len(chain) >= 18:
    legal17, why17 = g.trace_path(unit, 6, [], chain[:18])
    check(not legal17, f"17th hex exceeds budgets (17.1) -> {why17}")
else:
    # extend with any adjacent clear hex off-road
    ext = [h for h in g.neighbors(*chain[16])
           if g.on_map(*h) and h not in chain and
           g.hex_terrain(*h) not in ("escarpment",)]
    legal17, why17 = g.trace_path(unit, 6, [], chain[:17] + [ext[0]])
    check(not legal17, f"17th hex exceeds budgets (17.1) -> {why17}")

print("rules 7.1/8.1/8.3 ZOC:")
axis = U("G 21Pz 5", "M30")
allied = U("A 22 Gds Inf", "M32", side="Allied", uid="e1")
board = [axis, allied]
dests = g.legal_destinations_t(axis, 6, board)
zoc = g.zoc_hexes(board, "Allied")
in_zoc_dests = [h for h in dests if h in zoc]
check(len(in_zoc_dests) > 0, "8.2: may enter enemy ZOC (combat trigger)")
# 8.1/8.3: entering ZOC ends the move — continuing THROUGH must fail
legal, why = g.trace_path(axis, 6, board, [cr("M30"), cr("M31"), cr("M33")])
check(not legal, f"8.1/8.3: cannot continue M31->M33 through ZOC -> {why}")
# but M33 as a DESTINATION is legal (enter the ZOC there and stop, 8.2)
check(cr("M33") in dests, "8.2: M33 reachable by entering the ZOC last")
# 8.3 same-unit first step: unit starting in e1's ZOC may not hop directly
# to another hex of e1's ZOC...
axis2 = U("G 21Pz 5", "M31")
board2 = [axis2, allied]
zset = g.zoc_by_unit(board2, "Allied")["e1"]
hop = sorted(h for h in zset if h in g.neighbors(*cr("M31")))[0]
legal, why = g.trace_path(axis2, 6, board2, [cr("M31"), hop])
check(not legal, f"8.3: direct same-unit ZOC hop illegal -> {why}")
# ...but MAY re-enter after touching a ZOC-free hex (8.3 explicit)
d2 = g.legal_destinations_t(axis2, 6, board2)
reenter = [h for h in d2 if h in zset]
check(len(reenter) > 0, "8.3: re-entry via a ZOC-free hex is legal")
check(len(d2) > 0, "8.3: the unit may leave the ZOC entirely")
# supply may not enter enemy ZOC at all (13.2)
sup = U("G Supply 1", "M30")
d3 = g.legal_destinations_t(sup, 10, [sup, allied])
check(not [h for h in d3 if h in zoc], "13.2: supply unit cannot enter enemy ZOC")
# markers and supply exert no ZOC (7.1/5.4)
marker = U("G RD 1", "M32", uid="m1")
supz = U("A Supply 1", "M32", side="Allied", uid="s1")
check(not g.zoc_hexes([marker], "Axis"), "5.4: markers exert no ZOC")
check(not g.zoc_hexes([supz], "Allied"), "5.4: supply units exert no ZOC")

print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILURES'}")
sys.exit(1 if fails else 0)
