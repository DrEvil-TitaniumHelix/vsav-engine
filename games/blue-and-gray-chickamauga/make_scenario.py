"""Build scenario_chickamauga.json from the 1975 charts + the module's pieces.

Sources: rules_transcription.json (canonical 1975 deployment/reinforcement
charts, two-source validated) + the module buildFile (piece slots, images).
The scenario follows the PRINTED chart; the module's two setup deviations
(Wilder at 0822, 2/4/XIV omitted) are corrected and logged.

Also injects the stats patterns into game.json (att=def=printed strength,
MA 6 for all units [5.0]; Train 0-1-6 [18.11/18.12]).

Assertion-guarded: every chart unit must resolve to a module slot whose
image file exists on disk; totals must match the chart counts.
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BUILDFILE = os.path.normpath(os.path.join(HERE, "..", "..", "..", "VassalBlueGray", "extracted", "buildFile"))
IMAGES = os.path.normpath(os.path.join(HERE, "..", "..", "..", "VassalBlueGray", "extracted", "images"))

chart = json.load(open(os.path.join(HERE, "rules_transcription.json"), encoding="utf-8"))
cx = chart["chickamauga_exclusive"]

# ---------------------------------------------------------------- module slots
bf = open(BUILDFILE, encoding="utf-8").read()
slots = {}
for m in re.finditer(r'<VASSAL\.build\.widget\.PieceSlot entryName="([^"]+)"[^>]*gpid="(\d+)"[^>]*>(.*?)</VASSAL\.build\.widget\.PieceSlot>', bf, re.S):
    name, gpid, body = m.group(1), m.group(2), m.group(3)
    mi = re.search(r'piece;;;([^;]+?\.(?:png|gif|svg));', body)
    if mi:
        slots[name] = {"gpid": gpid, "img": mi.group(1)}
print(f"module slots parsed: {len(slots)}")

# chart name -> module slot name
ALIAS = {
    "Hmphry": "Humphrey", "Rbrtsn": "Robertson", "Andrsn": "Anderson",
    "Wlthll": "Walthall", "Armstng": "Armstrong", "Davdsn": "Davidson",
    "Andrsn (Anderson)": "Anderson6", "Mnigalt (Manigault)": "Manigault",
    "Harisn (Harrison)": "Harrison",
    "1/2 Cav": "1/2 Cavalry", "1/1 Cav": "1/1 Cavalry", "2/1 Cav": "2/1 Cavalry",
    "3/1 Cav": "3/1 Cavalry", "2/2 Cav": "2/2 Cavalry",
    "Train": "Union Supply Train",
}
ARTY = {"3": "3 Artillery", "2": "2 Artillery", "1": "1 Artillery",
        "XIV": "XIV Artillery", "XX": "XX Artillery", "XXI": "XXI Artillery"}

def slotname(u):
    nm = u["name"]
    if u["type"] == "arty":
        nm = ARTY[nm]
    else:
        nm = ALIAS.get(nm, nm)
    if nm + " c" in slots:
        return nm + " c"
    return nm     # module naming inconsistency: 'Benning' has no ' c' suffix

NEXT_ID = [101]   # numeric piece ids: gate pids == .vsav piece ids (mirror sync)

def mkunit(u, side, hexnum=None, due=None, entry=None):
    sn = slotname(u)
    assert sn in slots, f"chart unit {u['name']} -> slot '{sn}' not in module"
    img = slots[sn]["img"]
    assert os.path.exists(os.path.join(IMAGES, img)), f"image missing: {img}"
    e = {"id": str(NEXT_ID[0]), "slot": sn, "side": side, "img": img,
         "str": u["str"], "cls": u["type"]}
    NEXT_ID[0] += 1
    if hexnum:
        e["hex"] = [int(hexnum[:2]), int(hexnum[2:])]
    if due is not None:
        e["due"] = due
        e["entry"] = entry
    return e

units, reserve = [], []
for u in cx["initial_deployment_union"]:
    units.append(mkunit(u, "Union", hexnum=u["hex"]))
for u in cx["initial_deployment_confederate"]:
    units.append(mkunit(u, "Confederate", hexnum=u["hex"]))
for grp in cx["reinforcements_union"]:
    for u in grp["units"]:
        reserve.append(mkunit(u, "Union", due=grp["gt"],
                              entry=[[int(h[:2]), int(h[2:])] for h in cx["reinforcements_union_entry"]]))
for grp in cx["reinforcements_confederate"]:
    for u in grp["units"]:
        reserve.append(mkunit(u, "Confederate", due=grp["gt"],
                              entry=[[int(h[:2]), int(h[2:])] for h in cx["reinforcements_confederate_entry"]]))

# ------------------------------------------------------------------ assertions
assert len(units) == 46, f"at-start count {len(units)} != 46 (14 Union + 32 CSA)"
assert sum(1 for u in units if u["side"] == "Union") == 14
assert sum(1 for u in units if u["side"] == "Confederate") == 32
assert len(reserve) == 40, f"reserve count {len(reserve)} != 40 (26 Union + 14 CSA)"
assert sum(1 for u in reserve if u["side"] == "Union") == 26
assert sum(1 for u in reserve if u["side"] == "Confederate") == 14
ids = [u["id"] for u in units + reserve]
assert len(ids) == len(set(ids)), "duplicate unit ids"
# chart corrections vs module setup (module_deviations_worksheet)
wilder = next(u for u in units if u["slot"] == "Wilder c")
assert wilder["hex"] == [10, 22], "Wilder must sit at chart hex 1022, not module 0822"
assert any(u["slot"] == "2/4/XIV c" and u["hex"] == [8, 22] for u in units), "2/4/XIV at 0822"
# artillery: exactly three per side among units+reserve [19.12]
na = {"Union": 0, "Confederate": 0}
for u in units + reserve:
    if u["cls"] == "arty":
        na[u["side"]] += 1
assert na == {"Union": 3, "Confederate": 3}, na

vp = cx["vp_schedule"]
scenario = {
    "name": "Chickamauga - The Last Victory (campaign, 15 GTs)",
    "mode": "bluegray",
    "game": {
        "turns": 15,
        "first_player": "Union",
        "night_turns": [9],
        "turn_labels": [f"GT {i}" + (" (Night)" if i == 9 else "") for i in range(1, 16)],
    },
    "units": units,
    "reserve": reserve,
    "vp": {
        "per_enemy_csp_eliminated": 1,
        "exit_per_csp": {"Union": 1, "Confederate": 10},
        "confederate_train_fail": 10,
        "occupation": vp["occupation_end_of_game"],
        "start_occupation": vp["start_occupation"],
        "loc_confederate": "road trace 0101/0111 to the eastern edge free of Union units at game end [17.31]",
        "loc_union_path": 10,
        "cite": "[17.1] VP schedule; [17.2] occupation; [17.3] lines of communication"
    },
    "rules_scope": {
        "enforced": [
            "Movement Allowance 6 MP, all units [5.0]",
            "Terrain costs: clear 1 / forest 3 / rough 3 / forest+rough 6 MP [9.0 TEC]",
            "Roads 1 MP through road hexsides regardless of terrain [5.22]; trails cap the cost at 2 MP (1 in clear) [5.23]",
            "Creek hexsides impassable except bridges (free) and fords (+1 MP) [5.25]",
            "No entering enemy-occupied hexes [5.12]; no skipping hexes [5.16]; no MP accumulation [5.15]",
            "Stacking: max two units per hex at phase end [5.32]; free friendly pass-through [5.31/5.33]",
            "ZOC: all six adjacent hexes [6.0/6.6]; entering an EZOC ends movement [6.0]; a unit in an EZOC may NOT move during the Movement Phase [5.13/6.3]; ZOC never crosses non-bridge/ford creek hexsides [6.6]",
            "Reinforcements: printed schedule, southern-edge entry hexes, column entry costs, delay when both entry hexes are occupied [15.0-15.5]",
            "Exit at 0101/0111 for 1 MP; exited units are out permanently [16.1-16.7]",
            "Night GT 9: no combat of any kind; no entering EZOC [10.0-10.2]",
            "Train: roads/trails only, never stacks, blocks its hex, no ZOC [18.2]",
            "Turn sequence: Union first player, movement then combat, 15 GTs [4.0/14.3/15.53]"
        ],
        "enforced_tier2": [
            "Mandatory combat: every adjacent enemy attacked, every adjacent friendly participates [7.0/7.11/7.12/7.23]",
            "CRT 1d6, odds rounded down for the defender, >6-1 as 6-1, <1-5 as 1-5 [7.0/7.6]",
            "Voluntary odds reduction before the roll [7.9]",
            "Defending stacks fight as one total [7.21]; co-stacked attackers combine [7.22]; multi-hex combat adjacency [7.24/7.25]",
            "Combat results Ae/De/Ex/Ar/Dr with printed-strength exchange [7.6]",
            "Retreat 1 hex out of EZOC, owner's choice, elimination when no hex is open [7.7]; displacement chains [7.8]",
            "Advance after combat: one victorious unit, optional, immediate [7.75/7.76]",
            "Defender doubled in rough/forest+rough [9.0]; doubled behind bridge/ford hexsides when all attackers cross them [9.0]",
            "Artillery: bombardment at 2-3 hexes, LOS blocked by forest/forest+rough, bombarding artillery immune to results, mandatory normal combat when adjacent [8.0-8.5]",
            "Victory Points: eliminations, exits (with the Confederate LOC road trace), occupation hexes, Union 10-hex path check, the Train's 10 VP [17.0-17.3, 18.0]"
        ],
        "umpired": [
            "Attack Effectiveness (optional rule 11.0 - not used, as published default)",
            "Ford+trail cost composition: encoded as trail cap + 1 MP (see source_defects ford-trail-cost-composition)",
            "5.17 touched-piece etiquette (table rule, meaningless under a gate)"
        ]
    }
}

out = os.path.join(HERE, "scenario_chickamauga.json")
json.dump(scenario, open(out, "w", encoding="utf-8"), indent=1)
print(f"scenario written: {out}")
print(f"  units {len(units)} (U14/C32), reserve {len(reserve)} (U26/C14)")

# ------------------------------------------------- stats patterns -> game.json
# The board layer names pieces by their counter-IMAGE basename (names collide
# across modules; images don't — engine convention). Stats patterns, classes
# and side tokens are emitted in BOTH name spaces: slot names (the gate) and
# image basenames (the board/Tier-0 layer).
gj_path = os.path.join(HERE, "game.json")
gj = json.load(open(gj_path, encoding="utf-8"))
pats = []
for u in units + reserve:
    att = 0 if u["cls"] == "train" else u["str"]
    deff = 1 if u["cls"] == "train" else u["str"]
    img_base = os.path.splitext(u["img"])[0]
    pats.append([u["slot"], [att, deff, 6]])
    if img_base != u["slot"]:
        pats.append([img_base, [att, deff, 6]])
# longest-first so no shorter fragment shadows a longer name
pats.sort(key=lambda p: (-len(p[0]), p[0]))
gj["stats"]["patterns"] = pats
# side detection for the board layer: exact image basenames of Union pieces
gj["sides"]["detect_tokens"] = {"Union": sorted(
    {os.path.splitext(u["img"])[0] for u in units + reserve if u["side"] == "Union"}
    | {u["slot"] for u in units + reserve if u["side"] == "Union"})}
# classes in both name spaces
cls_map = {"train": "train", "arty": "artillery", "cav": "cavalry"}
classes = {"train": set(), "artillery": set(), "cavalry": set()}
for u in units + reserve:
    cl = cls_map.get(u["cls"])
    if cl:
        classes[cl].add(u["slot"])
        classes[cl].add(os.path.splitext(u["img"])[0])
gj["classes"] = {k: sorted(v) for k, v in classes.items()}
gj["classes"]["note"] = ("generated by make_scenario.py in both name spaces "
                         "(gate slot names + board image basenames); artillery "
                         "= the six bombardment units [19.12], train = 18.0, "
                         "everything else infantry (cavalry move identically "
                         "at MA 6 in the original)")
json.dump(gj, open(gj_path, "w", encoding="utf-8"), indent=1)
print(f"game.json stats patterns: {len(pats)}")

# ------------------------------------------------- setup .vsav (board mirror)
# Built from the module's own PieceSlot definitions with our numeric piece
# ids, so the server's .vsav mirror maps 1:1 onto gate pids (Tobruk pattern).
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "..", "engine")))
import gamespec, make_save            # noqa: E402
G = gamespec.Game(HERE)
save_units = [{"id": u["id"], "slot": u["slot"], "hex": u["hex"]} for u in units]
# reserves parked in a column off the playfield's east edge (the printed
# holding-box strip) until their GT — sync_mirror walks them on at entry
for i, u in enumerate(reserve):
    save_units.append({"id": u["id"], "slot": u["slot"],
                       "xy": [2620, 120 + i * 82]})
make_save.build(G, {"units": save_units}, os.path.join(HERE, "setup.vsav"))
print("ALL ASSERTIONS PASS")
