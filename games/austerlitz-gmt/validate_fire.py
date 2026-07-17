"""
validate_fire.py - phase-2 fire resolver checks against the chart's own
procedure, key example, and cited rules.
Run: python games/austerlitz-gmt/validate_fire.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "engine"))
import fire

FAILS = []


def check(label, ok):
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILS.append(label)


T = json.load(open(os.path.join(HERE, "game.json"),
                   encoding="utf-8"))["combat_tables"]

print("== chart key example [8.1.6] ==")
steps, band = fire.range_adjustment(T, "french", "6pdr", 10)
check("French 6pdr at range 10 = long range, down 1", steps == 1
      and band == "long")
check("base D downgraded to E", fire.adjust_letter("D", steps) == "E")
steps2, band2 = fire.range_adjustment(T, "french", "6pdr", 2)
check("range 2 = grapeshot, up 2", steps2 == -2 and band2 == "grapeshot")
steps3, band3 = fire.range_adjustment(T, "french", "6pdr", 12)
check("range 12 = out of range for a French 6pdr", steps3 is None)

print("== defense classes [8.1.8] ==")
check("skirmish formation -> class a",
      fire.defense_class(T, "French", "infantry", "skirmish") == "a")
check("artillery -> class b",
      fire.defense_class(T, "Allied", "artillery_horse", "unlimbered") == "b")
check("French line -> class c",
      fire.defense_class(T, "French", "infantry", "line") == "c")
check("Allied line -> class d (French column too)",
      fire.defense_class(T, "Allied", "infantry", "line") == "d"
      and fire.defense_class(T, "French", "infantry", "column") == "d")
check("cavalry column -> class f, square -> class g",
      fire.defense_class(T, "French", "cavalry", "column") == "f"
      and fire.defense_class(T, "Allied", "infantry", "square") == "g")

print("== column lookup + procedure [8.1.8] ==")
check("class c, rating C -> column 5",
      fire.fire_column(T, "c", "C") == 5)
check("class c, rating A -> column 4 (A-B cell)",
      fire.fire_column(T, "c", "A") == 4)
check("class g, rating A -> column 1 (squares are easy targets)",
      fire.fire_column(T, "g", "A") == 1)
check("class a, rating A -> column 5 (skirmishers are hard targets)",
      fire.fire_column(T, "a", "A") == 5)
# firer adjustments: line up 1 letter
check("firer in line: C becomes B [8.1.8 adjustments]",
      fire.firer_letter(T, "C", "line") == "B")
check("firer in square: C becomes E",
      fire.firer_letter(T, "C", "square") == "E")

print("== resolution + effects ==")
r = fire.resolve(T, "c", "C", die=9)
check("class c / C / die 9 -> column 5, cell '1' = 1 SP + check(+0)",
      r["column"] == 5 and r["effect"]["kind"] == "sp_loss"
      and r["effect"]["sp"] == 1 and r["effect"]["then"]["drm"] == 0)
r = fire.resolve(T, "c", "C", die=0)
check("class c / C / die 0 -> NE", r["effect"]["kind"] == "no_effect")
r = fire.resolve(T, "g", "A", die=9)
check("square / A / die 9 -> column 1 cell '3' = 3 SP + check(+2)",
      r["effect"]["sp"] == 3 and r["effect"]["then"]["drm"] == 2)
r = fire.resolve(T, "c", "C", die=5, column_shift=-1)
check("flank fire (1 column left) harshens the result",
      r["column"] == 4)

print("== morale check [9.1] ==")
check("roll at morale = pass", fire.morale_check(T, 4, 4, []) == 0)
check("roll 3 over = lose 1", fire.morale_check(T, 7, 4, []) == 1)
check("roll 6 over = lose 2", fire.morale_check(T, 8, 2, []) == 2)
check("roll 7+ over = lose 3", fire.morale_check(T, 9, 1, [2]) == 3)
check("DRMs shift the roll (square -1 saves a 1-over)",
      fire.morale_check(T, 5, 4, [-1]) == 0)

print()
if FAILS:
    print(f"FAILED: {len(FAILS)}")
    for x in FAILS:
        print("  -", x)
    sys.exit(1)
print("ALL FIRE RESOLVER CHECKS PASS")
