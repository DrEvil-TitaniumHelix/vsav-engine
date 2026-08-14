import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from naw_mapdata import GRIDS, ED2_TOWN, ED2_EXIT, build_ed2, build_ed3, load

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "map_grid.json")

ED2_WOODS_ROAD = {"1014": ["NW"], "1101": ["N", "S"], "1603": ["NE", "SW"], "1701": ["NE", "S"], "1702": ["N", "SW"]}

ED2_WOODS_ROAD_REJECTED = {
    "1918": "N-side hit is the Plancenoit building block in 1917, not a road (zoom p3_chk_1918)",
    "2401": "NW/NE hits are the printed words BRITISH/PRUSSIAN PLAYER crossing the hexsides (zoom p3_chk_2401)",
    "2604": "SE hit is the Ohain building block in 2704, not a road (zoom p3_chk_2604)",
}

ED2_SETUP = {
    "allied": {"0907": "2-4", "0410": "4-4", "0609": "6-4", "0811": "3-5", "0910": "6-4", "1014": "1-4",
               "1110": "1-4", "1209": "4-5", "1210": "7-3", "1307": "1-5", "1309": "6-4", "1410": "3-5",
               "1507": "4-5", "1509": "3-3", "1609": "6-4", "1708": "5-4", "1807": "3-5", "1808": "7-4"},
    "french": {"0614": "2-5", "0914": "7-4", "1015": "3-3", "1016": "2-5", "1114": "5-4", "1115": "2-5",
               "1116": "4-5", "1414": "4-4", "1415": "4-4", "1416": "2-4", "1417": "6-4", "1511": "5-3",
               "1514": "1-5", "1515": "2-3", "1516": "5-4", "1517": "7-4", "1611": "3-3", "1613": "4-4",
               "1615": "1-5", "1712": "5-4", "1812": "4-4", "1814": "1-5", "1912": "4-4", "1913": "1-5",
               "1914": "3-6", "2111": "2-5"},
}

ED3_EXIT = [f"{c:02d}01" for c in range(1, 10)]


def main():
    g2, ed2 = build_ed2()
    g3, ed3 = build_ed3()
    ocr = {k: v for k, v in load("ed3_ocr.json").items()
           if int(k[2:]) <= (17 if int(k[:2]) % 2 else 16)}
    ocr_hit = sum(1 for k, v in ocr.items() if k == v)
    ocr_read = sum(1 for k, v in ocr.items() if v)
    ocr_cells = len(ocr)

    for hid, v in ed2.items():
        rs = ED2_WOODS_ROAD.get(hid)
        if v["kind"].startswith("woods"):
            v["kind"] = "woods_road" if rs else "woods"
            v["road_sides"] = rs or []
        else:
            v["road_sides"] = []
        v["road_detected"] = v.pop("roads")

    ed3_out = {}
    for hid, v in ed3.items():
        ed3_out[hid] = {"kind_module_art": "woods" if v["kind"].startswith("woods") else "clear",
                        "exit": hid in ED3_EXIT}

    doc = {
        "produced_by": "PREP-3, games/napoleon-at-waterloo/ingest/naw_build_mapgrid.py",
        "read_on": "2026-08-13",
        "editions": {
            "2nd": {
                "authority": "PRIMARY printed folio scan (2nd Ed) NapoleonatWaterloo.pdf p.5; "
                             "Oliver module map restoration used as an independent second witness only",
                "sources": {
                    "folio": {"file": "Napoleon at Waterloo (2nd Ed)/NapoleonatWaterloo.pdf", "page": 5,
                              "rotation_for_north_up": 270, "size_px": [5171, 6952]},
                    "oliver_module": {"file": "ed2_oliver/images/Nap at Waterloo map 20mm hexes.jpg",
                                      "size_px": [6623, 5648], "authority": "faithful restoration, second witness"},
                },
                "numbering": {
                    "scheme": "OURS — the printed 2nd Ed map carries NO hex numbers (discrepancy D11)",
                    "definition": "CCRR, columns 01..27 west to east, rows 01..22 north to south within each column",
                    "anchor": "0101 = the north-westernmost hex of the field; it carries an exit arrow",
                    "parity": "ODD columns sit half a hex LOWER than even columns "
                              "(inverse of the printed 3rd Ed convention — do not cross the two)",
                    "neighbours": "N=(c,r-1) S=(c,r+1); odd c: NE=(c+1,r) SE=(c+1,r+1) NW=(c-1,r) SW=(c-1,r+1); "
                                  "even c: NE=(c+1,r-1) SE=(c+1,r) NW=(c-1,r-1) SW=(c-1,r)",
                },
                "grid_px": {"folio": {k: g2[k] for k in ("x0", "y0", "dx", "dy", "even_down")},
                            "oliver": {k: load("ed2oliver_canon.json")[k] for k in
                                       ("x0", "y0", "dx", "dy", "even_down")}},
                "geometry": "flat-top; dy/dx = 1.1576 (folio) / 1.1579 (oliver); hex = 400 m",
                "extent": {"cols": 27, "rows": 22, "hexes": 594,
                           "note": "every column has 22 rows; the north and south edges are jagged by half a hex"},
                "exit_hexes": ED2_EXIT,
                "exit_note": "eleven arrowed hexes, columns 01-11 of row 01; read off the folio, "
                             "columns 12+ of row 01 carry no arrow",
                "terrain_classes": {
                    "clear": "1 MP, no combat effect (roads give no movement or combat benefit in this game)",
                    "town": "1 MP, printed TEC doubles the defender",
                    "woods": "ENTRY PROHIBITED; artillery may not fire over",
                    "woods_road": "1 MP, defender doubles per printed TEC; may be entered and left "
                                  "ONLY along the road hexsides listed",
                },
                "counts": {"clear": sum(1 for v in ed2.values() if v["kind"] == "clear"),
                           "town": sum(1 for v in ed2.values() if v["kind"] == "town"),
                           "woods": sum(1 for v in ed2.values() if v["kind"] == "woods"),
                           "woods_road": sum(1 for v in ed2.values() if v["kind"] == "woods_road")},
                "woods_road_rejected": ED2_WOODS_ROAD_REJECTED,
                "road_layer_status": "ADVISORY ONLY — road_detected is machine-detected and carries "
                                     "false positives from printed text, the compass rose and building blocks. "
                                     "Roads have no movement or combat effect in this edition; the only "
                                     "play-relevant roads are road_sides on woods_road hexes, which were "
                                     "verified by eye one hex at a time.",
                "at_start_pictures": {
                    "status": "PROVISIONAL — hexes and side are verified from the printed map; the strength "
                              "readings still need PREP-4's counter photograph as a second witness",
                    "side_rule": "printed orientation gives the owner: upside-down (printed for the player at "
                                 "the north edge) = Allied, upright = French; corroborated by the printed "
                                 "Front Line, Allied north / French south",
                    "counts": {"allied": len(ED2_SETUP["allied"]), "french": len(ED2_SETUP["french"]),
                               "total": len(ED2_SETUP["allied"]) + len(ED2_SETUP["french"])},
                    "hexes": ED2_SETUP,
                },
                "terrain": {h: {"kind": v["kind"], "road_sides": v["road_sides"], "exit": v["exit"],
                                "road_detected": v["road_detected"]} for h, v in sorted(ed2.items())},
            },
            "3rd": {
                "authority": "MODULE ART ONLY — davejm module map. We hold no printed 3rd Ed map or TEC. "
                             "Grid and hex numbering are machine-verified against the numbers printed on that "
                             "art; terrain and exits are module-derived and are NOT a printed-source read.",
                "sources": {"davejm_module": {"file": "ed3_davejm/images/Map to use 3 copy.jpg",
                                              "size_px": [5960, 5496]}},
                "numbering": {"scheme": "PRINTED on the map: CCRR 0101..2317",
                              "parity": "EVEN columns sit half a hex lower than odd columns",
                              "verification": f"OCR of the printed number in every hex of the field: "
                                              f"{ocr_hit} exact and {ocr_read} legible of {ocr_cells} cells; "
                                              f"the misses are truncated leading zeros plus hexes whose "
                                              f"number is covered by map art. Off-field probes (row 18, and "
                                              f"row 17 of every even column) came back blank, which is how "
                                              f"the extent was measured."},
                "grid_px": {k: g3[k] for k in ("x0", "y0", "dx", "dy", "even_down")},
                "geometry": "flat-top; dy/dx = 1.1516; declared HexGrid dx=243.9 dy=281.7",
                "extent": {"cols": 23, "rows_odd_cols": 17, "rows_even_cols": 16, "hexes": 380,
                           "note": "odd columns run 01..17, even columns 01..16 — proven by OCR: "
                                   "every even column's row 17 probe is blank"},
                "exit_hexes": ED3_EXIT,
                "exit_note": "nine arrowed hexes, columns 01-09 of row 01, under the legend 'To Waterloo'; "
                             "1001 and 1101 are woods and carry no arrow. MODULE ART, not printed source.",
                "terrain_module_art": ed3_out,
                "terrain_status": "BLOCKED — E14/E15: the printed 3rd Ed rules never state defence doubling or "
                                  "artillery LOS blocking, and we hold no printed 3rd Ed TEC. Nothing here may "
                                  "be promoted to encoded terrain until that chart is obtained.",
            },
        },
        "edition_comparison": {
            "extent": "2nd Ed 27x22 = 594 hexes; 3rd Ed 23x(17/16) = 380 hexes. The 3rd Ed map is a "
                      "SMALLER battlefield, not a renumbering of the same field — this closes E36 with numbers.",
            "exits": "2nd Ed 11 exit hexes, 3rd Ed 9 — E41 closed per edition, the 3rd Ed's from module art.",
            "numbering_parity": "the two editions' column parities are opposite; a shared hex-id helper "
                                "would silently mis-stagger one of them.",
        },
    }
    json.dump(doc, open(OUT, "w"), indent=1)
    print(f"{OUT}")
    print("ed2", doc["editions"]["2nd"]["counts"], "hexes", len(doc["editions"]["2nd"]["terrain"]))
    print("ed3 hexes", len(ed3_out), "ocr", ocr_hit, "/", ocr_read)


if __name__ == "__main__":
    main()
