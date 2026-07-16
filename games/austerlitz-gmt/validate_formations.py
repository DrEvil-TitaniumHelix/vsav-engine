"""
validate_formations.py - Family B validation for Austerlitz (GMT 2000).

Every check below asserts a statement the RULEBOOK ITSELF makes (section
cited inline), evaluated against the transcribed TEC + the formations
geometry engine. A transcription slip or a geometry bug breaks a cited
assertion. Run: python games/austerlitz-gmt/validate_formations.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "engine"))

import gamespec
import formations as fm

FAILS = []


def check(label, ok):
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILS.append(label)


game = gamespec.load(HERE)
F = fm.Formations(game)

inf_line = {"arm": "infantry", "formation": "line"}
inf_col = {"arm": "infantry", "formation": "column"}
inf_dis = {"arm": "infantry", "formation": "disorder"}
inf_sq = {"arm": "infantry", "formation": "square"}
inf_sk = {"arm": "infantry", "formation": "skirmish"}
cav_line = {"arm": "cavalry", "formation": "line"}
cav_col = {"arm": "cavalry", "formation": "column"}
art_f = {"arm": "artillery_foot", "formation": "limbered"}
art_h = {"arm": "artillery_horse", "formation": "limbered"}
leader = {"arm": "leader", "formation": "column"}

print("== TEC action rows vs rulebook 6.3.x prose ==")
# 6.3.1: Line About Face costs HALF its movement allowance (m, round up)
check("6.3.1 line About Face = half MA (MA 4 -> 2)",
      F.action_cost(inf_line, "about_face", 4) == 2)
check("6.3.1 line About Face rounds up (MA 5 -> 3)",
      F.action_cost(inf_line, "about_face", 5) == 3)
# 6.3.2: Column About Face costs 2 MPs (infantry)
check("6.3.2 infantry column About Face = 2 MP",
      F.action_cost(inf_col, "about_face", 4) == 2)
# 6.3.5/6.3.6: cavalry About Face = 3 MPs in line AND column
check("6.3.5 cavalry line About Face = 3 MP",
      F.action_cost(cav_line, "about_face", 8) == 3)
check("6.3.6 cavalry column About Face = 3 MP",
      F.action_cost(cav_col, "about_face", 8) == 3)
# 6.3.4 + TEC note S: a unit in square pays 2 MPs to change formation
check("6.3.4/TEC-S square change formation = 2 MP",
      F.action_cost(inf_sq, "change_formation", 4) == 2)
# TEC: artillery may never About Face (NA)
check("TEC artillery About Face = NA",
      F.action_cost(art_f, "about_face", 3) is None)
# 6.3.3: skirmisher facing changes are free
check("6.3.3 skirmish change facing = 0 MP",
      F.action_cost(inf_sk, "change_facing", 4) == 0)

print("== TEC movement cells vs rulebook/TEC key ==")
# Reverse: line = entire MA [6.3.1], column = 2x terrain [6.3.2]
c = F.tec.cell("reverse", "infantry_line")
check("6.3.1 line Reverse = M (whole MA)", c.whole_ma)
c = F.tec.cell("reverse", "infantry_column")
check("6.3.2 column Reverse = 2x terrain cost", c.double)
# Slide: line only [6.3.1/6.3.2]; disorder has no flank (na) [Fig K]
check("6.3.1 line Slide = 2x", F.tec.cell("slide", "infantry_line").double)
check("6.3.2 column Slide = NA", F.tec.cell("slide", "infantry_column").prohibited)
check("Fig K disorder Slide = na (no flank hex)",
      F.tec.cell("slide", "infantry_disorder").not_applicable)
# Artillery prohibited in woods/swamp; infantry line prohibited in castle
check("TEC artillery woods = P", F.tec.cell("woods", "artillery_foot").prohibited)
check("TEC infantry line castle = P", F.tec.cell("castle", "infantry_line").prohibited)
# Cavalry may not cross walls (P), infantry line takes +1 with disorder check
w = F.tec.cell("wall_hexside", "infantry_line")
check("TEC wall inf line = +1 with disorder check",
      w.surcharge == 1 and w.disorder_check and not w.auto_disorder)
check("TEC wall cavalry = P", F.tec.cell("wall_hexside", "cavalry_line").prohibited)
# WOODS auto-disorders line/column infantry (D), not already-disordered
wd = F.tec.cell("woods", "infantry_line")
check("TEC woods inf line = 2 + auto-disorder (D)",
      wd.cost == 2 and wd.auto_disorder)
check("TEC woods inf disorder = 2, no further disorder",
      F.tec.cell("woods", "infantry_disorder").cost == 2
      and not F.tec.cell("woods", "infantry_disorder").auto_disorder)
# Roads: OT for Lines (cannot use Road Movement) [5.3/TEC key]
check("5.3/TEC line primary road = OT (no road movement in line)",
      F.tec.cell("primary_road", "infantry_line").other_terrain)
check("TEC column primary road = 1/2 MP",
      F.tec.cell("primary_road", "infantry_column").cost == 0.5)
# entry() honors road movement for column but falls back for line
check("entry(): column on primary road pays 1/2",
      F.entry(inf_col, "clear", road="primary_road").cost == 0.5)
check("entry(): line on primary road pays the CLEAR cost (2)",
      F.entry(inf_line, "clear", road="primary_road").cost == 2)
# Minor slope escalators: infantry † (+1 each after first), cavalry ‡ (+2)
check("TEC minor slope infantry = † (first free, +1 after)",
      F.tec.cell("minor_slope_up", "infantry_column").minor_slope == 1)
check("TEC minor slope cavalry = ‡ (first free, +2 after)",
      F.tec.cell("minor_slope_up", "cavalry_column").minor_slope == 2)
# Stream: cavalry line +3 with check, foot artillery +3 flat
s = F.tec.cell("stream_hexside", "cavalry_line")
check("TEC stream cav line = +3 with disorder check",
      s.surcharge == 3 and s.disorder_check)
check("TEC stream foot artillery = +3",
      F.tec.cell("stream_hexside", "artillery_foot").surcharge == 3)
# Leaders: 12 MPs is rulebook 5.4; TEC leader clear = 1
check("TEC leader clear = 1 MP", F.tec.cell("clear", "leader").cost == 1)

print("== Facing geometry (Figures A/B, 6.1/6.3) ==")
# Use a mid-map hex on the real Austerlitz grid, both column parities.
for col, row in ((30, 40), (31, 40)):
    n_all = {tuple(x) for x in game.neighbors(col, row)}
    sides = [fm.side_neighbor(game, col, row, s) for s in range(6)]
    check(f"side_neighbor covers all 6 gamespec neighbors @({col},{row})",
          set(filter(None, sides)) == n_all and len(set(sides)) == 6)
# Column (hexside facing): exactly ONE front hex, opposite ONE rear hex
f = fm.front_hexes(game, 30, 40, 0, "hexside")
r = fm.rear_hexes(game, 30, 40, 0, "hexside")
check("Fig B column: 1 front hex", len(f) == 1)
check("Fig B column: 1 rear hex, opposite the front",
      len(r) == 1 and r[0] != f[0])
# Line (vertex facing): TWO front hexes, both adjacent, sharing the vertex
f = fm.front_hexes(game, 30, 40, 1, "vertex")
check("Fig A line: 2 front hexes", len(f) == 2)
check("Fig A line: front hexes are themselves adjacent (share the vertex)",
      tuple(f[1]) in {tuple(x) for x in game.neighbors(*f[0])})
# Line flanks: 2, disjoint from front; rear: 2, disjoint from both
fl = fm.flank_hexes(game, 30, 40, 1, "vertex")
re_ = fm.rear_hexes(game, 30, 40, 1, "vertex")
check("Fig A line: 2 flank hexes disjoint from front",
      len(fl) == 2 and not set(map(tuple, fl)) & set(map(tuple, f)))
check("Fig A line: 2 rear hexes disjoint from front+flank",
      len(re_) == 2 and not set(map(tuple, re_))
      & (set(map(tuple, f)) | set(map(tuple, fl))))
# front+flank+rear = all 6 neighbors for a line unit
allsets = set(map(tuple, f)) | set(map(tuple, fl)) | set(map(tuple, re_))
check("Fig A line: front+flank+rear partition all 6 neighbors",
      allsets == {tuple(x) for x in game.neighbors(30, 40)})
# Skirmish/square all-around: 6 front hexes [6.3.3/6.3.4]
check("6.3.3 skirmish: all 6 neighbors are front",
      len(fm.front_hexes(game, 30, 40, 0, "all")) == 6)

print("== Stacking Chart [7.1] ==")
check("7.1 infantry line clear = 8 SP", F.stack_limit("infantry", "line", "clear") == 8)
check("7.1 infantry line woods = NA", F.stack_limit("infantry", "line", "woods_swamp") is None)
check("7.1 infantry skirmish clear = 12 SP", F.stack_limit("infantry", "skirmish", "clear") == 12)
check("7.1 cavalry line clear = 6 SP", F.stack_limit("cavalry", "line", "clear") == 6)
check("7.1 cavalry column village = 8 SP", F.stack_limit("cavalry", "column", "village_castle") == 8)

print()
if FAILS:
    print(f"FAILED: {len(FAILS)}")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("ALL FORMATION CHECKS PASS")
