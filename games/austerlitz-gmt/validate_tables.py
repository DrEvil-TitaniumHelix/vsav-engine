"""
validate_tables.py - phase-2 combat-table transcription checks.

The Fire Table / Artillery Range / Morale / Fatigue data in game.json was
transcribed from GMT's updated charts page 3 and cross-checked against
the module's original chart scan and the Italian translation. These
checks assert (a) the chart's own worked example, (b) structural
invariants a mis-transcription would break, (c) spot cells read
independently from both English sources.
Run: python games/austerlitz-gmt/validate_tables.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FAILS = []


def check(label, ok):
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILS.append(label)


T = json.load(open(os.path.join(HERE, "game.json"),
                   encoding="utf-8"))["combat_tables"]

print("== chart's own worked example [8.1.6 key] ==")
# "a French 6-pounder with base value D firing at range 10 would be at
#  Long Range, so the Fire Value would be downgraded to E"
band = T["artillery_range"]["french"]["6pdr"]
check("range 10 is in the French 6pdr down1 band",
      band["down1"][0] <= 10 <= band["down1"][1])
check("down 1 letter from D is E", chr(ord("D") + 1) == "E")

print("== artillery range structural invariants ==")
for nation, guns in T["artillery_range"].items():
    if nation == "note":
        continue
    for gun, bands in guns.items():
        seq = [bands["up2"]]
        seq.append(bands["base"])
        seq.append(bands.get("down1") or bands.get("down2"))
        ok = seq[0] == [1, 2] and all(
            seq[i + 1][0] == seq[i][1] + 1 for i in range(2))
        check(f"{nation} {gun}: bands contiguous from hex 1", ok)

print("== fire table structural invariants ==")
SEV = {"NE": 0, "M-1": 1, "M": 2, "M+1": 3, "1": 4, "2": 5, "3": 6}
rows = {k: v for k, v in T["fire_results"].items() if k != "note"}
check("10 die rows of 8 columns",
      len(rows) == 10 and all(len(v) == 8 for v in rows.values()))
mono_die = all(
    SEV[rows[str(d + 1)][c]] >= SEV[rows[str(d)][c]]
    for d in range(9) for c in range(8))
check("higher die never softer (per column)", mono_die)
mono_col = all(
    SEV[rows[str(d)][c + 1]] <= SEV[rows[str(d)][c]]
    for d in range(10) for c in range(7))
check("higher column never harsher (per die)", mono_col)
check("worst cell is column 1 die 9 = 3 SP", rows["9"][0] == "3")
check("best cells are NE (col 8, die 0-1)",
      rows["0"][7] == "NE" and rows["1"][7] == "NE")

print("== fire column letters: contiguous A..F per class ==")
for cls, cells in T["fire_table_columns"].items():
    if cls == "note":
        continue
    letters = []
    for col in sorted(cells, key=int):
        v = cells[col]
        if "-" in v:
            a, b = v.split("-")
            letters += [chr(x) for x in range(ord(a), ord(b) + 1)]
        else:
            letters.append(v)
    check(f"class {cls}: letters cover A-F once each in order",
          letters == ["A", "B", "C", "D", "E", "F"])

print("== spot cells vs both English sources ==")
check("class c col 5 = C (Italian's 'C-D' is its own typo)",
      T["fire_table_columns"]["c"]["5"] == "C")
check("class f col 1 = A with col 2 empty (both printings)",
      T["fire_table_columns"]["f"]["1"] == "A"
      and "2" not in T["fire_table_columns"]["f"])
check("die 4 row = 1,1,M+1,M+1,M,M,M-1,M-1",
      rows["4"] == ["1", "1", "M+1", "M+1", "M", "M", "M-1", "M-1"])

print("== morale + fatigue [9.1/13.0] ==")
m = T["morale_check"]
check("9.1 results ladder pass/-1/-2/-3",
      m["results"]["above_1_3"].startswith("lose 1")
      and m["results"]["above_7_plus"].startswith("lose 3"))
check("9.1 DRMs: square -1 / line +1 / leader -1 / routed +2",
      m["drm"]["unit_in_square"] == -1 and m["drm"]["unit_in_line"] == 1
      and m["drm"]["leader_in_hex"] == -1
      and m["drm"]["unsteady_or_routed"] == 2)
f = T["fatigue_effects"]
check("13.0 fatigue 8 = disorder + melee -2",
      f["8"]["immediate"] == "disordered" and f["8"]["melee_drm"] == -2)

print()
if FAILS:
    print(f"FAILED: {len(FAILS)}")
    for x in FAILS:
        print("  -", x)
    sys.exit(1)
print("ALL TABLE CHECKS PASS")
