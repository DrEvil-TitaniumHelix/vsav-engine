import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "engine"))
import gamespec  # noqa: E402

ok = True


def check(cond, msg):
    global ok
    print(("PASS  " if cond else "FAIL  ") + msg)
    ok = ok and bool(cond)


def J(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return json.load(f)


DATA = ("game.json", "terrain.json", "scenario_2nd_ed.json")
before = {n: open(os.path.join(HERE, n), "rb").read().replace(b"\r\n", b"\n") for n in DATA}
subprocess.run([sys.executable, os.path.join(HERE, "build_data.py")], check=True, capture_output=True)
after = {n: open(os.path.join(HERE, n), "rb").read().replace(b"\r\n", b"\n") for n in DATA}
check(before == after, "build_data.py is idempotent: rebuilding from ingest/ reproduces game.json, terrain.json, scenario_2nd_ed.json byte for byte")

G = gamespec.load(HERE)
spec = G.spec
hg = J("ingest/hexgraph_2nd_ed.json")
oob = J("ingest/oob_2nd_ed.json")
mod = J("ingest/module_oob.json")
crt = J("ingest/crt_2nd_ed.json")
mg = J("ingest/map_grid.json")["editions"]["2nd"]
rules = {r["id"] for r in J("ingest/rules_2nd_ed.json")["rows"]}
ter = J("terrain.json")
scen = J(spec["scenario"])
tr = J("ingest/timerecord_oob.json")

hexes = hg["hexes"]
check(len(ter["hexes"]) == 594 == len(hexes), f"terrain.json carries 594 hexes ({len(ter['hexes'])})")
counts = {}
for k, v in ter["hexes"].items():
    counts[v["t"]] = counts.get(v["t"], 0) + 1
check(counts == hg["terrain_counts"] == {"clear": 503, "town": 30, "woods": 56, "woods_road": 5},
      f"terrain counts clear/town/woods/woods_road = {counts}")
check(all(ter["hexes"][h]["t"] == v["terrain"] for h, v in hexes.items()), "every hex kind equals hexgraph_2nd_ed.json")
exits = sorted(h for h, v in ter["hexes"].items() if v.get("exit"))
check(exits == hg["exit_hexes"] == mg["exit_hexes"] == spec["exit"]["hexes"] and len(exits) == 11
      and all(h.endswith("01") and 1 <= int(h[:2]) <= 11 for h in exits),
      f"11 exit hexes = columns 01-11 of row 01, identical in terrain.json / game.json / hexgraph / map_grid ({len(exits)})")

bad = 0
for h, v in hexes.items():
    got = {G.grid.hexnum(*n) for n in G.neighbors(v["col"], v["row"]) if G.on_map(*n)}
    exp = {x for x in v["neighbours"].values() if x}
    bad += got != exp
check(bad == 0, f"engine adjacency (grid dx/dy/x0/y0/stagger) == the PROVED hexgraph on all 594 hexes ({bad} mismatches)")
oli = mg["grid_px"]["oliver"]
cx, cy = G.grid.hex_to_pixel(1, 1)
check(abs(cx - oli["x0"]) <= 0.5 and abs(cy - (oli["y0"] + oli["dy"] / 2)) <= 0.5,
      f"hex 0101 centre = PREP-3 fitted centre ({cx},{cy}) vs ({oli['x0']},{oli['y0'] + oli['dy'] / 2})")
rt = sum(1 for h, v in hexes.items() if G.grid.pixel_to_hex(*G.grid.hex_to_pixel(v["col"], v["row"]))[2] != h)
check(rt == 0, f"pixel<->hex round trip on all 594 hexes ({rt} bad)")
mm = sum(1 for m in mod["at_start"] if G.grid.pixel_to_hex(*m["module_px"])[2] != m["ccrr"])
check(mm == 0 and len(mod["at_start"]) == 44, f"all 44 module at-start pixel positions map to their printed hexes ({mm} bad)")
offmap = [h for h in ("0000", "0023", "2800", "2823", "1200", "1223") if G.on_map(int(h[:2]), int(h[2:]))]
check(not offmap, "hexes outside 01..27 x 01..22 are off-map")

wr = {h: v for h, v in hexes.items() if v["terrain"] == "woods_road"}
sides = ter["sides"]
seen = set()
sbad = []
for h, v in wr.items():
    for d, nb in v["neighbours"].items():
        if nb is None:
            continue
        k1, k2 = f"{h}|{nb}", f"{nb}|{h}"
        keys = [k for k in (k1, k2) if k in sides]
        if len(keys) != 1:
            sbad.append((h, d, keys))
            continue
        f = sides[keys[0]]
        want = {"road": True} if d in v["road_sides"] else {"woods_edge": True}
        if f != want:
            sbad.append((h, d, f, want))
        seen.add(keys[0])
check(not sbad and seen == set(sides), f"terrain.json sides = exactly the hexsides of the 5 Woods/Road hexes: road where the road crosses, woods_edge elsewhere ({len(sides)} sides, {sbad})")
mv = [(h, n) for h, v in wr.items() for d, n in v["neighbours"].items() if n and d in v["road_sides"]
      and G.move_cost((v["col"], v["row"]), (int(n[:2]), int(n[2:]))) != 1.0]
check(not mv, "generic move_cost: leaving a Woods/Road hex along its road costs 1 MP")
mv2 = [(h, n) for h, v in wr.items() for d, n in v["neighbours"].items() if n and d not in v["road_sides"]
       and G.move_cost((int(n[:2]), int(n[2:])), (v["col"], v["row"])) is not None]
check(not mv2, "generic move_cost: entering a Woods/Road hex across a non-road hexside is prohibited")
wd = [h for h, v in hexes.items() if v["terrain"] == "woods"
      and any(n and (G.move_cost((int(n[:2]), int(n[2:])), (v["col"], v["row"])) or 99) < 7 for n in v["neighbours"].values())]
check(not wd, "generic move_cost: no unit (MA <= 6) can afford a Woods hex")
check(all(G.move_cost((v["col"], v["row"]), (int(n[:2]), int(n[2:]))) == 1.0
          for h, v in hexes.items() if v["terrain"] in ("clear", "town")
          for n in v["neighbours"].values() if n and hexes[n]["terrain"] in ("clear", "town")),
      "generic move_cost: clear/town to clear/town = 1 MP everywhere (roads have no movement effect)")

units = scen["units"]
res = scen["reserve"]
check(scen["mode"] == "naw" and scen["game"]["turns"] == 10 and scen["game"]["first_player"] == "Fr", "scenario: mode naw, 10 turns, French first")
check(scen["game"]["turn_labels"] == [s["printed"] for s in tr["time_record"]["slots"]] == [f"{n} pm" for n in range(1, 11)],
      "turn labels = the printed Time Record, 1 pm .. 10 pm")
check(len(units) == 44 and len(res) == 9, f"44 at-start units + 9 Prussian arrivals ({len(units)}/{len(res)})")
ids = [u["id"] for u in units + res]
check(len(set(ids)) == 53, "53 unique unit ids")
byhex = {}
for u in units:
    byhex.setdefault(tuple(u["hex"]), []).append(u)
check(all(len(v) == 1 for v in byhex.values()), "no two at-start units share a hex (MOV-09 stacking prohibited)")
check(all(G.on_map(*u["hex"]) and G.hex_terrain(*u["hex"]) != "woods" for u in units), "every at-start unit is on-map and not in Woods")
side_of = {"French": "Fr", "Allied": "Al"}
want = {(o["hex"], side_of[o["side"]], o["combat_strength"], o["movement_allowance"], o["unit_type"], o["designation"]) for o in oob["at_start_units"]}
got = {(f"{u['hex'][0]:02d}{u['hex'][1]:02d}", u["side"], u["stats"]["att"], u["stats"]["ma"], u["cls"], u["desig"]) for u in units}
check(want == got, "at-start roster (hex, side, CS, MA, type, designation) == oob_2nd_ed.json, 44/44")
check(all(u["stats"]["att"] == u["stats"]["def"] for u in units + res), "Combat Strength serves attack and defence alike (PCS-02)")
fr = sum(u["stats"]["att"] for u in units if u["side"] == "Fr")
al = sum(u["stats"]["att"] for u in units if u["side"] == "Al")
pr = sum(u["stats"]["att"] for u in res)
check((fr, al, pr) == (89, 73, 34) == (oob["totals"]["combat_strength_by_side"]["French"], oob["totals"]["combat_strength_by_side"]["Allied"], oob["totals"]["reinforcement_combat_strength"]),
      f"strength totals French 89 / Allied 73 / Prussian 34 ({fr}/{al}/{pr})")
check([f"{u['stats']['att']}-{u['stats']['ma']}" for u in res] == mod["reinforcements"]["printed_time_record_2nd_ed"]
      == [r["factors"] for r in oob["reinforcements"]], "the nine Prussians in printed Time Record order with printed factors")
check(all(u["side"] == "Al" and u["contingent"] == "Prussian" and u["due"] == 2 and u["arrival"] == "east_edge" for u in res)
      and scen["reinforcement"]["turn"] == 2 and scen["reinforcement"]["entry_cost_mp"] == 1 and scen["reinforcement"]["delay_legal"] is False,
      "Prussians: Allied side, due turn 2, east edge, 1 MP to place, not delayable (REI-01..07)")
mods = {m["piece_id"]: m for m in mod["at_start"] + mod["off_field_staged"]}
check(all(mods[u["module_piece_id"]]["image"] == u["img"] and mods[u["module_piece_id"]]["module_name"] == u["name"] and u["slot"] + ".png" == u["img"] for u in units + res),
      "every unit's img/name is the module piece PREP-4 matched to it; slot = image basename (board-layer convention)")
check(all(u["contingent"] in ("French", "British", "Prussian") for u in units + res)
      and sum(u["contingent"] == "British" for u in units) == 18 and sum(u["contingent"] == "French" for u in units) == 26,
      "contingents: 26 French, 18 British at start, 9 Prussian arrivals")

check(all(G.side(u["slot"]) == u["side"] for u in units + res), "sides.detect_tokens resolves every counter image name to its side")
check(all(G.stats(u["slot"]) == (u["stats"]["att"], u["stats"]["def"], u["stats"]["ma"]) for u in units + res),
      "stats.patterns resolve every counter image name to its printed factors (longest fragment first: NAW_1_10 before NAW_1_1)")
cls = spec["classes"]
check(all(u["slot"] in cls[u["cls"]] for u in units + res) and set(cls["prussian"]) == {u["slot"] for u in res}
      and sum(len(cls[c]) for c in ("infantry", "cavalry", "artillery")) == len({u["slot"] for u in units + res}),
      "classes partition every piece name by type; prussian class = the nine arrivals")
tc = oob["totals"]["type_counts"]
tc_got = {}
for u in units:
    k = f"{'French' if u['side'] == 'Fr' else 'Allied'} {u['cls']}"
    tc_got[k] = tc_got.get(k, 0) + 1
check(tc_got == tc, f"type counts by side == oob totals {tc_got}")

C = spec["combat"]["crt"]
cols = crt["odds_columns"]
check(C["odds_columns"] == cols and len(cols) == 10 and cols[0] == "1:5" and cols[-1] == "6:1", "CRT columns 1:5 .. 6:1")
cells = sum(1 for d in "123456" for i, c in enumerate(cols) if C["die_rows"][d][i] == crt["table"][d][c])
check(cells == 60, f"CRT 60/60 cells == crt_2nd_ed.json ({cells})")
check(set(x for d in "123456" for x in C["die_rows"][d]) == set(crt["result_codes"]) == {"AE", "Ar", "EX", "Dr", "DE"}
      and C["results"] == crt["result_codes"], "result code set AE/Ar/EX/Dr/DE with printed explanations")
check(C["clamp"] == {"low": "1:5", "high": "6:1", "printed": crt["clamp_printed_verbatim"]}, "clamp 1:5 / 6:1 with the printed footnote")
check(C["rounding"] == crt["odds_rounding"]["rule"], "rounding rule verbatim (in favour of the defender)")
check(spec["combat"]["terrain_effects"]["defender_doubles_in"] == ["town", "woods_road"], "terrain effects: defender doubles in town + woods_road (ruling NAW2-D4)")
check(spec["combat"]["artillery"]["bombard_range"] == 2 == spec["unit_types"]["artillery"]["bombard_range"], "artillery bombard range 2 (ART-01)")

check(spec["victory"]["loss_threshold_cs"] == 40 and spec["victory"]["french_exit_required"] == 7 == spec["exit"]["required_for_victory"]
      and spec["exit"]["cost_mp"] == 1 and spec["exit"]["side"] == "Fr",
      "victory: 40 CS threshold, 7 French exits, exit costs 1 MP, French only")
check(spec["demoralization"]["effects"] == {"Al_attack_column_shift": -1, "Fr_attack_column_shift": 1} and spec["demoralization"]["applies_to"] == "Al",
      "demoralization: Allied only, -1 / +1 odds column")
check(spec["save_key"] == "4e" and spec["sides"]["order"] == ["Fr", "Al"] and spec["sides"]["default"] == "Fr", "save key 0x4e (Oliver module), French = first player")

sd = spec["source_defects"]["list"]
need = ("id", "kind", "rules", "defect", "resolution", "authority", "enforced")
check(all(all(k in d for k in need) for d in sd) and len({d["id"] for d in sd}) == len(sd) == 5, "source_defects: 5 entries, complete, unique ids")
charts = {"TEC row 2", "TEC-01", "RET-01", "DIS-01"}
unres = [(d["id"], r) for d in sd for r in d["rules"] if r not in rules and r not in charts]
check(not unres, f"every source-defect rule reference resolves to a rules_2nd_ed.json row or a named chart ({unres})")
opens = [d["id"] for d in sd if d["authority"].startswith("PENDING")]
check(all(not d["enforced"] and d["resolution"].startswith("OPEN") for d in sd if d["id"] in opens) and not opens,
      f"no register entry is still PENDING a ruling (SD-3 resolved by SPI 1979, C.7 ruled by Bruce 2026-08-17) ({opens})")
check(all(d["authority"].split(" - ")[0].split(" (")[0] in ("DECLARED RULING", "PROVEN OUTCOME-EQUIVALENCE", "OBSERVED", "PUBLISHER CLARIFICATION") for d in sd),
      "every register entry names an authority rung")
check(all(spec["credits"][k].get(f) for k in ("game", "module") for f in ("title", "source")) and spec["credits"]["module"].get("library"),
      "credits: game + module with sources and library link")

man = J(os.path.join("..", "..", "web", "manifests", "napoleon-at-waterloo.json"))
req = man["requirements"][0]
check(req["sha256"] == "d74511843cc04e7cd81fc2d061517732fad80bddbefb642238ea3ee54778e498" and req["size"] == 12439999
      and man["assets"]["map"]["entry"] == "images/Nap at Waterloo map 20mm hexes.jpg",
      "web manifest pins Oliver 2.2.0 (sha + size) and the module map entry")

cdir = G.assets.get("counters_dir")
if cdir and os.path.isdir(cdir):
    missing = [u["img"] for u in units + res if not os.path.exists(os.path.join(cdir, u["img"]))]
    check(not missing and os.path.exists(G.assets["map"]), f"local module extract: map + all counter images present ({missing})")
else:
    print("SKIP  local module extract not present - image existence not checked")

print("ALL PASS" if ok else "FAILURES ABOVE")
sys.exit(0 if ok else 1)
