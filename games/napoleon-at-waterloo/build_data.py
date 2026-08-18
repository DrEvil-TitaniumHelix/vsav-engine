import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ING = os.path.join(HERE, "ingest")


def load(name):
    with open(os.path.join(ING, name), encoding="utf-8") as f:
        return json.load(f)


def dump(name, obj):
    with open(os.path.join(HERE, name), "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
        f.write("\n")


SIDE = {"French": "Fr", "Allied": "Al"}
CLS = {"infantry": "infantry", "cavalry": "cavalry", "artillery": "artillery"}


def build_terrain(hg):
    hexes, sides = {}, {}
    dropped_road_sides = []
    for hid, v in sorted(hg["hexes"].items()):
        cell = {"t": v["terrain"]}
        if v["exit"]:
            cell["exit"] = True
        hexes[hid] = cell
    for hid, v in sorted(hg["hexes"].items()):
        if v["terrain"] != "woods_road":
            continue
        for d, nb in v["neighbours"].items():
            if nb is None:
                if d in v["road_sides"]:
                    dropped_road_sides.append(f"{hid}:{d}")
                continue
            key = f"{hid}|{nb}" if f"{nb}|{hid}" not in sides else f"{nb}|{hid}"
            if d in v["road_sides"]:
                sides[key] = {"road": True}
            else:
                sides[key] = {"woods_edge": True}
    return {
        "hexes": hexes,
        "sides": sides,
        "provenance": {
            "built_by": "games/napoleon-at-waterloo/build_data.py from ingest/hexgraph_2nd_ed.json (PREP-5, adjacency PROVED against two fitted pixel grids); terrain kinds and exit flags read off the printed 1971 folio map (PREP-3, MAP_GRID_VERIFIED.md), witnessed by Oliver's module scan",
            "numbering": hg["numbering"],
            "kinds": {"clear": "1 MP, no combat effect [TEC row 1]",
                      "town": "1 MP, defender doubles [TEC row 2, CBT-18]",
                      "woods": "entry PROHIBITED [TEC row 3, MOV-16/MOV-18]; artillery may not bombard over it [ART-17]; never a retreat destination [RET bar (c)]",
                      "woods_road": "1 MP, defender doubles [TEC row 2 + ruling NAW2-D4]; entered and left ONLY across its road hexsides [MOV-16/MOV-17]"},
            "sides": {"road": "the road hexsides of the five Woods/Road hexes - the only hexsides that admit a unit to such a hex (MOV-17); roads have no movement or combat effect otherwise [TEC row 1]",
                      "woods_edge": "every non-road hexside of a Woods/Road hex - crossing it in either direction is prohibited (MOV-17: units must enter AND exit along the road)"},
            "road_sides_off_map": dropped_road_sides,
            "counts": hg["terrain_counts"],
            "exit_hexes": hg["exit_hexes"],
        },
    }


def unit_rows(oob, mod):
    by_hex = {}
    for m in mod["at_start"]:
        by_hex.setdefault(m["ccrr"], []).append(m)
    units = []
    for u in oob["at_start_units"]:
        ms = by_hex[u["hex"]]
        assert len(ms) == 1, u["hex"]
        m = ms[0]
        assert m["combat_strength"] == u["combat_strength"] and m["movement_allowance"] == u["movement_allowance"]
        assert m["type"] == u["unit_type"]
        assert m["designation"] == u["designation"]
        units.append({
            "side": SIDE[u["side"]],
            "hex": [int(u["hex"][:2]), int(u["hex"][2:])],
            "slot": m["image"].rsplit(".", 1)[0],
            "name": m["module_name"],
            "img": m["image"],
            "desig": u["designation"],
            "contingent": u["contingent"],
            "cls": CLS[u["unit_type"]],
            "stats": {"att": u["combat_strength"], "def": u["combat_strength"], "ma": u["movement_allowance"]},
            "module_piece_id": m["piece_id"],
        })
    units.sort(key=lambda x: (x["side"] != "Fr", x["hex"]))
    n = {"Fr": 100, "Al": 200}
    for u in units:
        n[u["side"]] += 1
        u["id"] = str(n[u["side"]])
    order = ["id", "slot", "name", "img", "side", "contingent", "desig", "cls", "stats", "hex", "module_piece_id"]
    return [{k: u[k] for k in order} for u in units]


def reserve_rows(oob, mod):
    staged = list(mod["off_field_staged"])
    out = []
    for r in oob["reinforcements"]:
        pick = None
        for m in staged:
            if m["combat_strength"] == r["combat_strength"] and m["movement_allowance"] == r["movement_allowance"] and m["type"] == r["unit_type"]:
                pick = m
                break
        assert pick, r
        staged.remove(pick)
        out.append({
            "id": str(300 + r["seq"]),
            "slot": pick["image"].rsplit(".", 1)[0],
            "name": pick["module_name"],
            "img": pick["image"],
            "side": SIDE[r["side"]],
            "contingent": r["contingent"],
            "desig": pick["designation"],
            "cls": CLS[r["unit_type"]],
            "stats": {"att": r["combat_strength"], "def": r["combat_strength"], "ma": r["movement_allowance"]},
            "due": r["arrival_turn"],
            "arrival": "east_edge",
            "module_piece_id": pick["piece_id"],
            "stage_px": pick["module_px"],
        })
    assert not staged, staged
    return out


def build_scenario(oob, mod, tr):
    slots = tr["time_record"]["slots"]
    labels = [s["printed"] for s in slots]
    units = unit_rows(oob, mod)
    reserve = reserve_rows(oob, mod)
    return {
        "name": "Napoleon at Waterloo, 2nd Edition (1971) - the game (10 Game-Turns, 1 pm to 10 pm)",
        "mode": "naw",
        "game": {
            "turns": 10,
            "first_player": "Fr",
            "turn_labels": labels,
            "turn_cite": "printed Time Record, folio p.5 (ingest/timerecord_oob.json, all ten slots read by eye); SEQ-01 'The game is ten Game-Turns in length'; SEQ-02/SEQ-04 French Player-Turn then Allied Player-Turn, each Movement Phase then Combat Phase",
            "opening_phase": "fr_move",
            "opening_cite": "SET-04: placement is not a turn or phase; the game begins with the French Player's first Movement Phase",
        },
        "units": units,
        "reserve": reserve,
        "reinforcement": {
            "event": "Prussians enter",
            "turn": 2,
            "player_turn": "Al",
            "phase": "movement",
            "entry": "anywhere along the East edge, at as many different points as desired",
            "entry_cost_mp": 1,
            "may_move_and_fight_on_entry": True,
            "delay_legal": False,
            "may_leave_map": False,
            "losses_count_as": "Al",
            "cite": "REI-01 (beginning of the Allied Player's second turn; printed Time Record 2 pm slot 'Prussians enter' with all nine unit pictures in that one slot), REI-02 (East edge, any points), REI-03 (placing a unit costs one Movement Point - printed 'extends', ruling NAW2-SD-1), REI-04 (move and fight on entry), REI-05 (Prussian losses are Allied losses), REI-06 (may not be delayed), REI-07 (may not leave the map)",
        },
        "oob_cite": "ingest/oob_2nd_ed.json - three independent witnesses (printed map unit pictures, printed counter photograph, Oliver module + Beginning Setup.vsav), 44/44 at-start hexes, factors, sides and types agree; nine Prussians in printed Time Record order; French 89 CS, Allied 73 CS + Prussian 34 CS",
        "rules_scope": {
            "status": "ENCODED - all seven bites enforced by engine/naw.py (data layer, movement/ZOC/exit, combat arithmetic, mandatory-attack assignment, result application, reinforcement/victory/demoralization, matrix closure). COVERAGE_MATRIX.md: 109/111 cells ENFORCED, 1 UNREACHABLE, 1 OPEN = the platform UNDO policy (M.13, NAW2-OR-3, Bruce). No game-level cell is open; nothing is human-umpired.",
            "enforced": [
                "Turn structure: 10 Game-Turns 1 pm-10 pm, French Player-Turn then Allied, each Movement Phase then Combat Phase; no enemy action in the friendly Player-Turn except the pendings the gate opens for it (retreat direction after Ar, defender advance) [SEQ-01..SEQ-08]",
                "Movement: one Movement Point per hex entered, never more than the printed Movement Allowance, consecutive hexes only, none/some/all units, no pooling or carry-over [MOV-01/02/05/06/14/15/20, PCS-03]",
                "Through friendly units yes, through or into enemy units never; a unit may end its own move on a friendly unit mid-phase only while every stacked hex can still be un-stacked (unmoved occupants matched to free step-off hexes, re-checked on every later move), and the Movement Phase cannot close while any hex holds two units [MOV-07/MOV-08/MOV-09 - reading A per SPI 1979 4.4 'never end a Movement Phase stacked', NAW2-OR-2]",
                "Once moved, a unit may not be moved again that Player-Turn; a submitted proposal is final [MOV-19 first clause]",
                "Woods: entry prohibited; Woods/Road hexes entered and left only across their road hexsides, in movement, retreat, disruption and advance alike (terrain.json sides) [MOV-16/MOV-17/MOV-18, TEC row 3; SPI 1979 4.2]",
                "Zones of Control: every unit controls its six adjacent hexes at all times, including Woods hexes no unit can enter; a unit entering an enemy-controlled hex must stop; it may not move through one nor leave one by movement; a unit beginning its Movement Phase in an enemy ZOC may not move at all; friendly ZOC never inhibits [ZOC-01..ZOC-08, MOV-10/11/12/13]",
                "Exit: French units only, from the eleven arrowed North-edge hexes 0101-1101, during the own Movement Phase, one Movement Point, exit hex reachable (through friendly units) and free of enemy ZOC; exited units never return and are not French losses; Allied units never exit [VIC-08/09/10/11/12, VIC-06, REI-07]",
                "Combat arithmetic: attacker total vs defender total, odds rounded in favour of the defender (floor(a/d):1, else 1:ceil(d/a)), clamped 1:5..6:1, the 60-cell CRT, one engine-owned seeded d6 per attack - proved against all 27 printed Examples of Attacks and the 8-vs-3 rules example [CBT-01/02/03, CBT-EX-01, CRT-01]",
                "Terrain effects on combat: a DEFENDER in a Town or Woods/Road hex doubles; attacking from such terrain confers nothing [CBT-18, TEC row 2, ruling NAW2-D4; EX-03/EX-04]",
                "Per-attack legality: every non-artillery attacker adjacent to every defender it attacks; several attackers may combine on one defender and one attacker on several defenders; a unit never split or named twice; a 1:5 diversionary attack is never refused; no unit attacks or is attacked twice a Player-Turn; artillery may bombard exactly two hexes away, one target only, over units and Towns but never across an intervening Woods hex (a bent shot is open if either candidate hex is clear, Woods/Road blocks - SPI 1979 Terrain Key); adjacent artillery attacks like any unit; a disrupted artillery unit may not fire that Combat Phase [CBT-05/10/11/12/13/17, ART-01/08/13/14/16/17, DISRUPTION S6]",
                "Mandatory attacks: the contact pairs (friendly unit adjacent to enemy unit) are FIXED when the Combat Phase opens; every such enemy must be attacked and every such friendly unit must attack; an attack is refused if it would leave any obligated unit with no attack open (forward check), so a complete assignment always remains available (star partition of the contact graph - constructive proof, NAW2-OR-5); an obligation lapses when its contact is lost (retreat, elimination, disruption, advance); the Combat Phase cannot close while an obligation stands; artillery adjacent to an enemy may discharge its obligation by bombarding another target [CBT-06/07/08/09/10, ART-02/06/07; NAW2-OR-6 A (Bruce 2026-08-17), OR-16 A]",
                "Results applied at once, before the next attack: AE eliminates the adjacent attackers (bombarding artillery immune); Ar retreats the adjacent attackers one hex, direction chosen by the VICTORIOUS defender, bombarding artillery may voluntarily retreat (owner chooses); EX eliminates the defenders and the attacker pays whole adjacent units totalling at least the defenders' PRINTED strength (attacker chooses; all adjacent units when they cannot cover it; nothing when every attacker bombarded); Dr retreats the defenders one hex, direction chosen by the attacker; DE eliminates the defenders [EXPLANATION OF RESULTS; ART-03/04/05/09/10/11/12; SPI 1979 6.3/6.8; NAW2-OR-7/OR-8/OR-15]",
                "Retreat: one hex, never into an enemy Zone of Control, off the map, into non-Road Woods or an enemy-occupied hex; sideways and forward legal; the victor also chooses the order; no path = eliminated (a unit forced off the map is destroyed, never exited) [RETREAT AND ADVANCE p.5, VIC-13]",
                "Disruption: a friendly-occupied safe hex is available only when no empty safe hex exists; the uninvolved occupant is pushed out (disrupted) and moved back one hex by the victor under the same bars (Woods/Road across its road hexside - NAW2-SD-3 A), chain reactions run to completion first, and if no chain can be completed nobody is disrupted and the retreating unit is eliminated instead; the flag lasts the Player-Turn and only bars artillery fire [DISRUPTION S1-S6; NAW2-OR-10..OR-14]",
                "Advance after combat: immediately, optional, one hex, one unit per vacated hex, each unit once, into or from an enemy ZOC, along the road into Woods/Road; the victorious attackers after Dr/DE/EX (bombarding artillery never), the DEFENDERS after Ar/AE (SPI 1979 6.3); an advanced unit takes no further part in that Combat Phase [CBT-14/15/16, ART-18, OPTIONAL ADVANCE p.5; NAW2-OR-16/OR-17]",
                "Prussian reinforcement: nine units due at the Allied Movement Phase of Game-Turn 2, entering anywhere on the East edge (column 27) in a non-Woods hex free of enemy units, enemy ZOC and friendly units, 1 MP to place, may move MA-1 and fight; the phase cannot close while a due unit has a legal entry hex; a unit with no legal entry hex waits (logged); Prussians never leave the map [REI-01..07; SPI 1979 7.2; NAW2-OR-1/OR-4]",
                "Loss ledgers and victory: printed Combat Strength destroyed per side, Prussian losses Allied, exited units not losses; Allied win on the fortieth French point first; French win on the fortieth Allied point first + seven exits (before or after); both-at-once (EX) -> French if seven exited else Allied; checked the instant it happens, mid-battle included; draw at the end of Game-Turn 10 [VIC-01..07, VIC-11, VIC-14, VIC-05/06, REI-05]",
                "Allied demoralization: latched the instant the fortieth Allied point falls with fewer than seven exits, permanent, Allied attacks -1 column / French +1 (clamped at the printed ends) from the very next attack, a later fortieth French point changes nothing [DEM-01..09; NAW2-OR-19 A]",
            ],
            "not_yet_enforced": [],
            "rulings": [
                "NAW2-D4 (Bruce 2026-08-14): a defender in a Town OR a Woods/Road hex doubles; attacking from such terrain confers nothing",
                "NAW2-SD-1: 'extends one Movement Point' is enforced as 'expends' (proven outcome-equivalence)",
                "NAW2-SD-3 (SPI 1979 6.4/4.2/6.5 - publisher clarification): a disrupted unit is barred exactly where a retreating unit is; Woods/Road allowed across its road hexside",
                "NAW2-OR-6 (Bruce 2026-08-17): mandatory-attack obligations are fixed at the start of the Combat Phase, resolved on the live board, and lapse when their contact disappears; OR-5 closed by proof (with the pairs fixed, the contact graph has no isolated vertex and a star partition into legal attacks always exists; the gate's forward check keeps it so); OR-16 A (an advanced unit leaves the list)",
                "SPI 1979 answers (publisher clarification): OR-7 all-bombardment EX free; OR-8 voluntary bombardment retreat = owner chooses; OR-9 bent bombardment line open if either candidate hex is clear; OR-10 disrupted-artillery ban forward-looking; OR-11 displaced unit to any safe hex; OR-12 chain compulsory, failure eliminates the original retreater; OR-13 'uninvolved' = not in the attack being resolved; OR-14 disruption lasts the Player-Turn; OR-15 EX paid in whole units >= printed defender strength, over-payment legal; OR-17 the defender may advance after Ar/AE (Stephen Oliver, BGG 2018, concurs)",
                "MOV-09 stacking under reading A (SPI 1979 4.4): a unit may end its own move on a friend mid-phase, the phase cannot close while any hex holds two units; wedge-proof: every stacked hex must remain un-stackable after every move (matching of unmoved occupants to free step-off hexes)",
                "Exit hex 1101 (Woods/Road, road N-S, printed exit arrow inside the hex): enterable only from 1102 along the road, exit crosses the north road hexside - legal (SPI 1979 4.2), NAW2-OR-18",
                "Woods/Road hex 1014 (Hougoumont) is a genuine printed cul-de-sac: the road enters from the NW and ends inside the hex - verified on Oliver's map scan 2026-08-17 (N2 closed); a unit attacked there from 1013 has no retreat",
                "Artillery line of fire (ART-17 + TEC footnote): Woods AND Woods/Road hexes block; a straight two-hex shot is blocked by its one intervening hex, a bent shot is OPEN if either candidate hex is clear; a Woods/Road hex may be bombarded INTO - SPI's own 1979 Terrain Key example (0803 into 0705 legal past woods 0804; 0803 into 0805 blocked) = publisher clarification, NAW2-OR-9 CLOSED",
                "Several-on-several attacks (EX-14) are legal only when every attacker is adjacent to every defender - the reading that satisfies CBT-11 and CBT-12 simultaneously and matches the printed geometry (SPI 1979 5.4)",
                "Retreat direction is chosen by the VICTOR in the 2nd Edition (RETREAT AND ADVANCE p.5) - the defender chooses where a beaten attacker goes; the 3rd Edition's owner-chooses rule is NOT this game (E21)",
            ],
            "open_for_bruce": [
                "M.13 / MOV-19 / NAW2-OR-3 (platform, all games): the printed rules require the opponent's consent to change a move; the platform ships UNDO - recommendation A: UNDO is a declared platform affordance, nothing changes",
            ],
        },
    }


def crt_block(crt):
    cols = crt["odds_columns"]
    return {
        "type": "odds_ratio",
        "odds_columns": cols,
        "die_rows": {d: [crt["table"][d][c] for c in cols] for d in ("1", "2", "3", "4", "5", "6")},
        "clamp": {"low": cols[0], "high": cols[-1], "printed": crt["clamp_printed_verbatim"]},
        "rounding": crt["odds_rounding"]["rule"],
        "results": crt["result_codes"],
        "cite": "folio p.5 Combat Resolution Table (printed twice, both copies agree cell for cell), read 4x - ingest/crt_2nd_ed.json; CBT-01/CBT-02 odds and rounding; validation corpus = the 27 printed Examples of Attacks (ingest/worked_examples.json, example_check.json 27/27)",
    }


def main():
    hg = load("hexgraph_2nd_ed.json")
    oob = load("oob_2nd_ed.json")
    mod = load("module_oob.json")
    tr = load("timerecord_oob.json")
    crt = load("crt_2nd_ed.json")
    dump("terrain.json", build_terrain(hg))
    scen = build_scenario(oob, mod, tr)
    dump("scenario_2nd_ed.json", scen)
    gp = os.path.join(HERE, "game.json")
    with open(gp, encoding="utf-8") as f:
        game = json.load(f)
    game["combat"]["crt"] = crt_block(crt)
    allu = scen["units"] + scen["reserve"]
    game["sides"]["detect_tokens"] = {"Al": sorted({u["slot"] for u in allu if u["side"] == "Al"}),
                                      "Fr": sorted({u["slot"] for u in allu if u["side"] == "Fr"})}
    pats = sorted({(u["slot"], (u["stats"]["att"], u["stats"]["def"], u["stats"]["ma"])) for u in allu}, key=lambda p: (-len(p[0]), p[0]))
    game["stats"]["patterns"] = [[s, list(v)] for s, v in pats]
    game["classes"] = {c: sorted({u["slot"] for u in allu if u["cls"] == c}) for c in ("infantry", "cavalry", "artillery")}
    game["classes"]["prussian"] = sorted({u["slot"] for u in allu if u["contingent"] == "Prussian"})
    game["classes"]["note"] = "generated by build_data.py from the scenario roster: unit type from the printed counter photograph (PREP-4); 'prussian' = the nine Time Record arrivals (Allied for every rule, REI-05)"
    game["exit"]["hexes"] = hg["exit_hexes"]
    dump("game.json", game)
    bf = os.path.join(HERE, game["buildfile"])
    if os.path.exists(bf):
        sys.path.insert(0, os.path.join(HERE, "..", "..", "engine"))
        import gamespec
        import make_save
        G = gamespec.Game(HERE)
        by_key = {}
        for r in mod["roster"]:
            by_key.setdefault((r["entry_name"], r["image"]), []).append(r["gpid"])
        used = {}
        save_units = []
        for u in scen["units"] + scen["reserve"]:
            k = (u["name"], u["img"])
            i = used.get(k, 0)
            gp = by_key[k][min(i, len(by_key[k]) - 1)]
            used[k] = i + 1
            rec = {"id": u["id"], "gpid": gp}
            if "hex" in u:
                rec["hex"] = u["hex"]
            else:
                rec["xy"] = u["stage_px"]
            save_units.append(rec)
        make_save.build(G, {"units": save_units}, os.path.join(HERE, "setup.vsav"))
    print("terrain", len(hg["hexes"]), "sides", len(build_terrain(hg)["sides"]), "units", len(scen["units"]), "reserve", len(scen["reserve"]))


if __name__ == "__main__":
    main()
