"""
make_scenario.py - build scenario_northern_flank.json from the module's
own setup save (positions + facings) merged with the transcribed unit
roster (counter stats read from the module's counter art; every value
sits on the printed counter).

Scenario data: playbook A15.1 (GMT's sanctioned Spanish translation,
literature/austerlitz/aus_spanish.pdf; translation noted per citation).
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "engine"))
import board as bd
import gamespec
import vsav

VSAV = r"C:\VassalIngest\austerlitz-gmt\setups\The Northern Flank.vsav"

# Transcribed from counter art (nf_counters.png contact sheet + battery
# limbered backs). Format: img-name fragment -> stats.
#   inf/cav: (arm, sp, fire, morale, ma, div, skirmish_capable)
#   art:     (arm, sp, fire, morale, ma(limbered side), div)
#   leader:  (activation, personality, range, command)
ROSTER = {
    # Allied - Markov / Vorpatzki (Bagration's advance guard)
    "Sheet 2 a F_13_1":  ("leader", "Markov", 4, "C", 4, "Bagration"),
    "Sheet 2 a F_13_3":  ("leader", "Vorpatzki", 4, "N", 5, "Bagration"),
    "Sheet 2 a F_3_39":  ("infantry", "G/Arkh", 7, "D", 4, 5, "2", False),
    "Sheet 2 a F_5_23":  ("infantry", "2/Arkh", 6, "D", 4, 5, "2", False),
    "Sheet 2 a F_5_25":  ("infantry", "3/Arkh", 6, "D", 4, 5, "2", False),
    "Sheet 2 a F_5_27":  ("infantry", "G/Pskv", 7, "D", 4, 5, "2", False),
    "Sheet 2 a F_5_29":  ("infantry", "2/Pskv", 7, "D", 4, 5, "2", False),
    "Sheet 2 a F_5_31":  ("infantry", "3/Pskv", 6, "D", 4, 5, "2", False),
    "Sheet 2 a F_5_33":  ("infantry", "G/O.Ing", 7, "D", 4, 5, "2", False),
    "Sheet 2 a F_5_35":  ("infantry", "2/O.Ing", 7, "D", 4, 5, "2", False),
    "Sheet 2 a F_5_37":  ("infantry", "3/O.Ing", 6, "D", 4, 5, "2", False),
    "Sheet 2 a F_5_39":  ("artillery_horse", "a/B", 6, "D", 6, 7, "2"),
    # French - Suchet's division (V Corps) + light cavalry
    "Sheet 1  a F_9_9":   ("leader", "Suchet", 5, "N", 5, "V Corps"),
    "Sheet 1  a F_11_33": ("leader", "Milhaud", 5, "N", 5, "Cav Res"),
    "Sheet 1  a F_11_3":  ("leader", "Treilhard", 5, "N", 6, "Cav Res"),
    "Sheet 1  a F_5_23":  ("infantry", "2/17 Leg", 6, "C", 7, 6, "3", True),
    "Sheet 1  a F_5_25":  ("infantry", "1/34 Ln", 8, "C", 5, 6, "3", False),
    "Sheet 1  a F_5_27":  ("infantry", "2/34 Ln", 8, "C", 5, 6, "3", False),
    "Sheet 1  a F_5_29":  ("infantry", "1/40 Ln", 6, "C", 5, 6, "3", False),
    "Sheet 1  a F_5_31":  ("infantry", "2/40 Ln", 6, "C", 5, 6, "3", False),
    "Sheet 1  a F_5_33":  ("infantry", "1/64 Ln", 6, "C", 5, 6, "3", False),
    "Sheet 1  a F_5_37":  ("infantry", "1/88 Ln", 7, "C", 5, 6, "3", False),
    "Sheet 1  a F_5_39":  ("infantry", "2/88 Ln", 7, "C", 5, 6, "3", False),
    "Sheet 1  a F_11_5":  ("cavalry", "22 CaC", 6, "", 6, 12, "M", False),
    "Sheet 1  a F_15_34": ("cavalry", "13 CaC", 5, "", 6, 12, "T", False),
    "Sheet 1  a F_15_37": ("cavalry", "21 CaC", 5, "", 6, 12, "T", False),
    "Sheet 1  a F_17_39": ("cavalry", "10 Hus", 5, "", 7, 12, "T", False),
    "Sheet 1  a F_3_27":  ("artillery_foot", "a/V", 3, "D", 6, 8, "3"),
    "Sheet 1  a F_3_29":  ("artillery_foot", "b/V", 4, "D", 6, 8, "1"),
    "Sheet 1  a F_3_31":  ("artillery_horse", "c/V", 1, "E", 7, 8, "3"),
}

game = gamespec.load(HERE)
brd = bd.Board(VSAV, game)
raw = vsav.read_vsav(VSAV)
txt = raw if isinstance(raw, str) else " ".join(str(p) for p in raw)

units = []
for u in brd.units():
    r = ROSTER.get(u["name"])
    if r is None:
        continue        # turn marker etc.
    m = re.search(re.escape(f"piece;;;{u['img']};")
                  + r"[^\x1b]*?true;Map0;1;-?\d+,-?\d+;true\\+\t(\d+)\\",
                  txt)
    facing = int(m.group(1)) % 12 if m else 0
    rec = {"id": u["id"], "slot": r[1], "img": u["img"],
           "side": u["side"], "hex": [u["col"], u["row"]],
           "facing": facing}
    if r[0] == "leader":
        rec.update(arm="leader", formation="column",
                   stats={"ma": 12, "morale": 0, "sp": 0},
                   command={"activation": r[2], "personality": r[3],
                            "range": r[4], "of": r[5]},
                   cite="leader ratings from counter; MA 12 [5.4]")
    elif r[0].startswith("artillery"):
        arm, name, sp, fire, morale, ma, div = r
        vertex = facing % 2 == 1
        # gun type for the Artillery Range Table [8.1.6]: printed gun
        # size (6lb/8lb from counter art) + nationality
        gun = {"a/B": ("russian", "6pdr_horse"),
               "a/V": ("french", "8pdr"), "b/V": ("french", "8pdr"),
               "c/V": ("french", "8pdr")}[name]
        rec.update(arm=arm, formation="unlimbered" if vertex
                   else "limbered", div=div,
                   gun={"nation": gun[0], "type": gun[1]},
                   stats={"ma": ma, "morale": morale, "sp": sp,
                          "fire": fire})
    else:
        arm, name, sp, fire, morale, ma, div, skirm = r
        rec.update(arm=arm, div=div, skirmish_capable=skirm,
                   formation="line" if facing % 2 == 1 else "column",
                   stats={"ma": ma, "morale": morale, "sp": sp,
                          "fire": fire})
    units.append(rec)

turn_labels = []
h, m = 11, 40
for _ in range(16):
    ampm = "am" if h < 12 else "pm"
    hh = h if h <= 12 else h - 12
    turn_labels.append(f"{hh}:{m:02d} {ampm}")
    m += 20
    if m >= 60:
        m -= 60
        h += 1

scenario = {
    "name": "The Northern Flank: A Learning Scenario",
    "mode": "napoleonic",
    "source": "setup from the module's own 'The Northern Flank' save; "
              "scenario rules from playbook A15.1 (GMT sanctioned "
              "Spanish translation, translated)",
    "game": {"turns": 16, "first_player": "French",
             "turn_labels": turn_labels,
             "duration_cite": "A15.1: from the 11:40 am turn to the "
                              "4:40 pm turn unless victory sooner"},
    "terrain_file": "terrain_nf.json",
    "initial_lims": {
        "French": ["Suchet", "Independent"],
        "Allied": ["Markov", "Vorpatzki"],
        "cite": "A15.1 initial LIMs (command NOT enforced at tier 1)"},
    "victory": {
        "french_win": "7 Russian battalions/regiments/batteries "
                      "destroyed, routed or unsteady",
        "russian_win": "10 French battalions/regiments/batteries "
                       "destroyed, routed or unsteady",
        "draw": "neither by the end of the 4:40 pm turn",
        "cite": "A15.1 VICTORIA (GMT's sanctioned Spanish translation, "
                "translated); checked by the engine every turn"},
    "units": units,
    "rules_scope": {
        "enforced": [
            "Formation-true movement: advance through front hexsides "
            "only; facing changes cost MPs [6.1/6.3/TEC 5.0]",
            "TEC terrain costs per arm+formation, incl. roads (Road "
            "Movement, not in Line), streams, slopes, bridges "
            "[5.0/5.1/5.3]",
            "Movement disorder: auto-disorder terrain and disorder "
            "checks vs morale, engine-rolled d10 [5.1.1/6.4.1]",
            "Line special moves: slide (2x, unoccupied flank), reverse "
            "(whole MA), about face (half MA) [6.3.1/6.3.5]",
            "Enemy front hexes end movement; no re-adjacency to the "
            "same enemy [5.1.3]",
            "Stacking limits by type/formation/division and terrain "
            "class [7.1]",
            "One activation per unit per game turn [3.0/4.6]",
            "Fire combat: offensive + return fire (simultaneous), "
            "range/facing arcs/LOS, target hierarchy, once per turn "
            "[8.1.1-8.1.8]",
            "Morale: check table + DRMs, shaken/unsteady/rout ladder, "
            "artillery morale as SP loss, chain checks on rout "
            "[9.1-9.3]",
            "Retreats + rout retreats with SP loss for shortfall "
            "[10.0/10.1]; unit breakpoint [11.1]",
            "Rally phase incl. routed-rally cap and rout loss "
            "[12.0-12.4]",
            "Victory conditions checked every turn [A15.1]",
        ],
        "enforced_tier2": [
            "Melee: bayonet/assault/charge combat [8.2-8.5] (phase 4)",
        ],
        "umpired": [
            "Command system: LIM pool, activations, command range "
            "[4.0] (phase 3)",
            "Reactions: reaction fire, countercharge, form square "
            "[6.2/8.4.2] (phase 4)",
            "Strategic movement [5.2]; limited-activation MA "
            "reduction [4.6.2] (needs the command system)",
            "Division fatigue accumulation [13.1] (tracks with the "
            "command system; fatigue DRMs are wired, level stays 0)",
        ],
    },
}
dst = os.path.join(HERE, "scenario_northern_flank.json")
json.dump(scenario, open(dst, "w", encoding="utf-8"), indent=1)
print("units:", len(units), "->", dst)
for u in units:
    print(f"  {u['side']:6s} {u['slot']:10s} {u['arm']:15s} "
          f"{u.get('formation',''):10s} f{u['facing']:<2d} "
          f"@{u['hex']}")
