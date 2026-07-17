"""
validate_melee.py - phase-4 melee resolver checks: charts p4 tables
(three-source verified), playbook A8.1.x charge arithmetic, and the
GMT errata's own worked example of the Retreat result.
Run: python games/austerlitz-gmt/validate_melee.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "engine"))
import melee

FAILS = []


def check(label, ok):
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILS.append(label)


G = json.load(open(os.path.join(HERE, "game.json"), encoding="utf-8"))
T = G["combat_tables"]
ROWS = G["formations"]["combat_effects"]["rows"]

print("== Melee Result Table [8.5] shape ==")
rt = T["melee"]["result_table"]
rows = [k for k in rt if k != "note"]
check("10 result rows (<=0, 1-8, >=9)", len(rows) == 10)
check("rows <=3 hit the attacker, 4-5 both, >=6 the defender",
      all(rt[k]["loser"] == "attacker" for k in ("le_0", "1", "2", "3"))
      and all(rt[k]["loser"] == "both" for k in ("4", "5"))
      and all(rt[k]["loser"] == "defender" for k in ("6", "7", "8", "ge_9")))
check("extremes rout: <=0 attacker -2 SP, >=9 defender -3 SP",
      rt["le_0"]["morale"] == "routs" and rt["le_0"]["sp_lost"] == 2
      and rt["ge_9"]["morale"] == "routs" and rt["ge_9"]["sp_lost"] == 3)
check("4-5 = both lose 1 SP, check, melee continues [8.5.3]",
      all(rt[k]["sp_lost"] == 1 and rt[k]["morale"] == "check"
          and rt[k]["other"] == "melee_continues" for k in ("4", "5")))

print("== errata worked example (2000-07-20) - AUS-MEL-2 gold case ==")
# "An attacking infantry unit in Good Morale that rolls a 1 loses 2 SPs,
#  loses 2 Morale levels from Good to Shaken to Unsteady, retreats 1 hex
#  for the Retreat result, then retreats again for the Unsteady result."
r = melee.resolve_melee(T, die=1, drm_total=0)
check("roll 1: attacker loses 2 SP", r["loser"] == "attacker"
      and r["sp"] == 2)
check("roll 1: loses 2 morale levels (Good->Shaken->Unsteady)",
      r["morale"] == {"kind": "lose_levels", "levels": 2})
check("roll 1: Retreat result = one extra unsteady-style retreat",
      r["other"] == "retreat")
# "If the attacking unit was in Good Morale and rolled a 3, it would
#  lose 1 SP, lose 1 Morale level from Good to Shaken, and retreat 1 hex"
r = melee.resolve_melee(T, die=3, drm_total=0)
check("roll 3: attacker loses 1 SP + 1 level + retreat",
      r["loser"] == "attacker" and r["sp"] == 1
      and r["morale"]["levels"] == 1 and r["other"] == "retreat")
r = melee.resolve_melee(T, die=7, drm_total=4)
check("modified >=9 clamps to the rout row (die 7 + 4 = 11)",
      r["loser"] == "defender" and r["morale"]["kind"] == "rout"
      and r["other"] == "rout_retreat")
r = melee.resolve_melee(T, die=2, drm_total=-5)
check("modified <=0 clamps to the attacker-rout row",
      r["loser"] == "attacker" and r["morale"]["kind"] == "rout")

print("== size ratio [8.3.1#5 + chart panel] ==")
check("1:1 (and fractions below 2x) = 0",
      melee.size_ratio_drm(6, 6) == 0 and melee.size_ratio_drm(7, 6) == 0
      and melee.size_ratio_drm(6, 7) == 0)
check("2:1 = +1, 3:1 = +2, 4:1+ = +3",
      melee.size_ratio_drm(12, 6) == 1 and melee.size_ratio_drm(18, 6) == 2
      and melee.size_ratio_drm(24, 6) == 3
      and melee.size_ratio_drm(30, 6) == 3)
check("1:2 = -1, 1:3 or lower = -2",
      melee.size_ratio_drm(6, 12) == -1 and melee.size_ratio_drm(6, 18) == -2
      and melee.size_ratio_drm(6, 30) == -2)
check("fractions round down (11 vs 6 = 1:1, not 2:1)",
      melee.size_ratio_drm(11, 6) == 0)

print("== SP totals [8.4.2#6] ==")
check("artillery SPs never count",
      melee.melee_sp([(6, "infantry", "line", False),
                      (4, "artillery_foot", "unlimbered", False)]) == 6)
check("charging cavalry in column counts 1/3 rounded down",
      melee.melee_sp([(7, "cavalry", "column", True)]) == 2)
check("non-charging cavalry in column counts full SPs",
      melee.melee_sp([(7, "cavalry", "column", False)]) == 7)

print("== charge range + bonus [A8.1.1 / A8.1.2] ==")
check("never adjacent; 2-4 legal; 5 too far",
      not melee.charge_range_ok(T, "light", 1)
      and melee.charge_range_ok(T, "light", 2)
      and melee.charge_range_ok(T, "light", 4)
      and not melee.charge_range_ok(T, "light", 5))
check("bonus roster: cossack 0 / light +1 / lancer +2 / cuirassier +4",
      melee.charge_bonus(T, "cossack", 3) == 0
      and melee.charge_bonus(T, "light", 3) == 1
      and melee.charge_bonus(T, "lancer", 3) == 2
      and melee.charge_bonus(T, "cuirassier", 3) == 4)
check("cuirassier from 2 hexes: legal but bonus forfeited",
      melee.charge_range_ok(T, "cuirassier", 2)
      and melee.charge_bonus(T, "cuirassier", 2) == 0)
check("light from 2 hexes keeps its bonus (min 2 for non-heavy)",
      melee.charge_bonus(T, "light", 2) == 1)
check("vs square halves round up (+3 heavy -> +2)",
      melee.charge_bonus(T, "heavy", 3, vs_square=True) == 2)
check("charger in column halves round up (+1 light -> +1)",
      melee.charge_bonus(T, "light", 3, in_column=True) == 1)
check("countercharge offset may go negative (light vs heavy = -2)",
      melee.charge_bonus(T, "light", None, countercharger_bonus=3) == -2)

print("== pre-shock checks [8.2/8.3/8.4 chart] ==")
check("attacker at morale: may melee",
      melee.pre_shock_attacker(4, 4, []) == {"kind": "may_melee"})
check("attacker 3 over: may NOT melee, no other penalty",
      melee.pre_shock_attacker(7, 4, []) == {"kind": "no_melee"})
check("attacker 4 over: no melee + disorder + 1 level",
      melee.pre_shock_attacker(8, 4, []) ==
      {"kind": "no_melee", "disorder": True, "levels": 1})
check("attacker DRMs: rear -3 turns a 3-over into a pass",
      melee.pre_shock_attacker(7, 4, [-3]) == {"kind": "may_melee"})
check("defender at morale: stands",
      melee.pre_shock_defender(4, 4, []) == {"kind": "stand"})
check("defender 2 over: 1 SP + disorder + retreat + 1 level",
      melee.pre_shock_defender(6, 4, []) ==
      {"kind": "shock_loss", "sp": 1, "disorder": True,
       "retreat": True, "levels": 1})
check("defender 5 over: 2 SP + disorder + retreat + 2 levels",
      melee.pre_shock_defender(9, 4, []) ==
      {"kind": "shock_loss", "sp": 2, "disorder": True,
       "retreat": True, "levels": 2})
check("defender 6 over: 2 SP + rout & retreat",
      melee.pre_shock_defender(9, 3, []) ==
      {"kind": "shock_loss", "sp": 2, "rout": True, "retreat": True})
check("defender DRMs: attacked in rear +3 breaks an at-morale stand",
      melee.pre_shock_defender(4, 4, [3])["kind"] == "shock_loss")

print("== forming square [8.4.2 #4] ==")
check("at morale: square formed",
      melee.form_square(4, 4, []) == {"kind": "square_formed"})
check("2 over: not formed, disordered",
      melee.form_square(6, 4, []) ==
      {"kind": "square_failed", "disorder": True})
check("3 over: not formed, disordered, -1 level",
      melee.form_square(7, 4, []) ==
      {"kind": "square_failed", "disorder": True, "levels": 1})
check("DRMs: leader -2 + column -1 save a 3-over",
      melee.form_square(7, 4, [-2, -1]) == {"kind": "square_formed"})
check("skirmish +4 dooms an at-morale roll",
      melee.form_square(4, 4, [4])["kind"] == "square_failed")

print("== pursuit [8.4.2 #8] ==")
check("at morale: no pursuit", melee.pursuit(4, 4, []) == 0)
check("2 over: 1 hex / 4 over: 2 hexes / 5+ over: 3 hexes",
      melee.pursuit(6, 4, []) == 1 and melee.pursuit(8, 4, []) == 2
      and melee.pursuit(9, 4, []) == 3)
check("cossack +3 turns an at-morale roll into a 2-hex pursuit (3 over)",
      melee.pursuit(4, 4, [3]) == 2)

print("== terrain gates [TEC combat_effects] ==")
drm, ok = melee.terrain_melee_drm(ROWS, ["village"])
check("village: melee DRM -2, allowed", drm == -2 and ok)
drm, ok = melee.terrain_melee_drm(ROWS, ["deep_stream_hexside"])
check("deep stream: melee NOT allowed (NA)", not ok)
drm, ok = melee.terrain_melee_drm(ROWS, ["stream_hexside", "wall_hexside"])
check("stream -1 + wall -1 stack to -2", drm == -2 and ok)
check("village/castle/wall are Defensive (assault only) [8.2/8.3]",
      melee.terrain_defensive(ROWS, ["village"])
      and melee.terrain_defensive(ROWS, ["castle"])
      and melee.terrain_defensive(ROWS, ["wall_hexside"])
      and not melee.terrain_defensive(ROWS, ["clear"]))
check("cavalry may charge in clear but not woods/village [8.4.1]",
      melee.terrain_chargeable(ROWS, ["clear"])
      and not melee.terrain_chargeable(ROWS, ["woods"])
      and not melee.terrain_chargeable(ROWS, ["village"]))

print("== source-defect register entries present ==")
ids = [d["id"] for d in G["source_defects"]]
check("AUS-MEL-1 (A13.1 cross-ref) registered", "AUS-MEL-1" in ids)
check("AUS-MEL-2 (Retreat-result conflict, errata wins) registered",
      "AUS-MEL-2" in ids)
check("AUS-MEL-3 ('repeat step 5' misprint) registered",
      "AUS-MEL-3" in ids)

print()
if FAILS:
    print(f"FAILED: {len(FAILS)}")
    for x in FAILS:
        print("  -", x)
    sys.exit(1)
print("ALL MELEE RESOLVER CHECKS PASS")
