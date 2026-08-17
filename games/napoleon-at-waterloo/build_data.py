import json
import os

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
            "slot": m["module_name"],
            "img": m["image"],
            "desig": u["designation"],
            "contingent": u["contingent"],
            "cls": CLS[u["unit_type"]],
            "stats": {"att": u["combat_strength"], "def": u["combat_strength"], "ma": u["movement_allowance"]},
            "module_piece_id": m["piece_id"],
        })
    units.sort(key=lambda x: (x["side"] != "Fr", x["hex"]))
    n = {"Fr": 0, "Al": 0}
    for u in units:
        n[u["side"]] += 1
        u["id"] = f"{'F' if u['side'] == 'Fr' else 'A'}{n[u['side']]:02d}"
    order = ["id", "slot", "img", "side", "contingent", "desig", "cls", "stats", "hex", "module_piece_id"]
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
            "id": f"P{r['seq']:02d}",
            "slot": pick["module_name"],
            "img": pick["image"],
            "side": SIDE[r["side"]],
            "contingent": r["contingent"],
            "desig": pick["designation"],
            "cls": CLS[r["unit_type"]],
            "stats": {"att": r["combat_strength"], "def": r["combat_strength"], "ma": r["movement_allowance"]},
            "due": r["arrival_turn"],
            "arrival": "east_edge",
            "module_piece_id": pick["piece_id"],
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
            "status": "DATA LAYER ONLY (bite 1). Nothing is enforced yet; the gate class lands in bites 2-7 of DECODE_PLAN.md and every cell of COVERAGE_MATRIX.md must be ENFORCED or UNREACHABLE-with-evidence before this scenario is playable.",
            "enforced": [],
            "rulings": [
                "NAW2-D4 (Bruce 2026-08-14): a defender in a Town OR a Woods/Road hex doubles; attacking from such terrain confers nothing",
                "NAW2-SD-1: 'extends one Movement Point' is enforced as 'expends' (proven outcome-equivalence)",
            ],
            "open_for_bruce": [
                "NAW2-SD-3: may a DISRUPTED unit be pushed into a Woods/Road hex?",
                "C.7: are the mandatory-attack obligations (CBT-06/07/10) fixed at Combat Phase start or re-evaluated as results apply?",
                "M.13 / MOV-19: the printed rules require the opponent's consent to change a move; the platform ships UNDO - engine policy",
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
    game["sides"]["detect_tokens"] = {"Fr": sorted({u["slot"] for u in allu if u["side"] == "Fr"}),
                                      "Al": sorted({u["slot"] for u in allu if u["side"] == "Al"})}
    game["stats"]["patterns"] = sorted({(u["slot"], (u["stats"]["att"], u["stats"]["def"], u["stats"]["ma"])) for u in allu})
    game["stats"]["patterns"] = [[s, list(v)] for s, v in game["stats"]["patterns"]]
    game["classes"] = {c: sorted({u["slot"] for u in allu if u["cls"] == c}) for c in ("infantry", "cavalry", "artillery")}
    game["classes"]["prussian"] = sorted({u["slot"] for u in allu if u["contingent"] == "Prussian"})
    game["classes"]["note"] = "generated by build_data.py from the scenario roster: unit type from the printed counter photograph (PREP-4); 'prussian' = the nine Time Record arrivals (Allied for every rule, REI-05)"
    game["exit"]["hexes"] = hg["exit_hexes"]
    dump("game.json", game)
    print("terrain", len(hg["hexes"]), "sides", len(build_terrain(hg)["sides"]), "units", len(scen["units"]), "reserve", len(scen["reserve"]))


if __name__ == "__main__":
    main()
