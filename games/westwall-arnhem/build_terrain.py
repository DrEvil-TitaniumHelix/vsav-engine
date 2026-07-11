"""
build_terrain.py - Terrain layer for Westwall: Arnhem (games/westwall-arnhem).

Starts from the VALIDATED legacy Arnhem terrain (ref/terrain.json - palette
self-calibrated from the map's own Terrain Key, hexsides by midpoint band +
line-coverage; validated vs 7 player-aid anchors, PROJECT_HISTORY) and applies
the corrections the Westwall EXCLUSIVE rules need, every one pinned by eye on
the map art 2026-07-11 (annotated 2x crops with hex-center overlays; contact
prints in the session log):

1. CITY hexes (11.0) - the Terrain Key distinguishes City (dark red-brown
   dense blocks) from Town (grey blocks). Programmatic block-color census over
   every hex + eye confirmation: city>1400 brown-block pixels, towns >1400
   grey; no hex in between (road ink tops out ~560).
2. Bridge TYPES (12.0 demolition): highway (never demolished), rail
   (demolishable, never repaired), canal (demolishable, Engineer-repairable).
   Canals are drawn in STREAM ink (measured: canal/stream both ~(40,160,200);
   rivers ~(10,130,172)) so an unbridged/demolished canal hexside IS a stream
   hexside: +3 MP, crossable by leg units, vehicles barred by 5.24 - exactly
   the Son-bridge story. The three canal courses are the map-labeled
   Wilhelmina / Zuid Willems / Waal-Maas canals.
3. FERRIES (Terrain Key: +3 MP, non-bridge per 6.33 - no ZOC or attacks
   across): white-arrow symbols at Driel/Heveadorp, Huissen, Renkum.
4. Bridges the legacy band-detector MISSED (all bracket-symbol verified):
   Grave, Heijen, Best, Veghel road+rail, Ravenstein rail, Mook rail,
   Gennep rail, Rhenen rail, Arnhem rail, four Waal-Maas canal crossings.
5. Legacy FALSE-POSITIVE bridges removed (no bridge symbol on the map at
   2x zoom): 2610|2710, 2623|2724, 3011|3112.
6. Every bridge/ferry side gets "crossing": true (movement escape from the
   river prohibition, B&G creek pattern); ferries do NOT count as bridges
   for ZOC/attack (6.33) or LOC (17.34) - the gate reads bridge/ferry apart.

Known limitation (declared in rules_scope): the printed map's RAILWAY lines
are not movement features, but the legacy line-coverage extraction may carry
some railway ink as trail/road on specific sides (suspects listed in
RAIL_SUSPECTS below). Movement along those chains can be cheaper than
strictly printed. The road/trail layer is otherwise kept exactly as
validated; re-deriving it from ink is a future pass.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "engine"))

SRC = os.path.join(ROOT, "ref", "terrain.json")
OUT = os.path.join(HERE, "terrain.json")

# ---------------------------------------------------------------- corrections
CITY_HEXES = {
    # Eindhoven
    "0203": 1406, "0204": 1921, "0304": 1696,
    # Nijmegen
    "2520": 2037, "2521": 2389, "2620": 1620, "2621": 2270,
    # Arnhem (3423 = bridge-north hex, city blocks confirmed)
    "3423": 1562, "3523": 1870, "3524": 2062,
    # Oosterbeek (city blocks, NOT grey town - confirmed at 2x zoom)
    "3521": 2050,
}   # value = measured city-brown block pixel count (evidence)

# Sides where the printed waterway passes under a bridge but the legacy
# band-detector assigned the water to a NEIGHBORING side: the water feature is
# added here so the bridge (and its demolition) is functionally real. Values:
# water class to add. Movement is unchanged while the bridge stands (crossing
# escapes the prohibition; stream+bridge adds nothing) and becomes print-true
# when it falls.
ADD_WATER = {
    "1207|1308": "stream",   # Zuid Willems Canal under the Veghel road bridge
    "2219|2220": "stream",   # Waal-Maas Canal under the Malden road bridge
    "2120|2121": "stream",   # Waal-Maas Canal under the Heumen road bridge
    "2619|2720": "stream",   # Waal-Maas Canal under the mouth trail bridge
    "2216|2316": "river",    # Maas under the Grave road bridge
    "3411|3512": "river",    # Neder Rijn under the Rhenen rail bridge
}
ADD_ROAD = {
    "2216|2316": "road",     # the Grave bridge carries the printed main road
    "2619|2720": "trail",    # the mouth crossing carries a printed trail
}

# bridge sides: side -> (bridge_type, road_feature_or_None, evidence)
BRIDGES = {
    # --- legacy bridges kept, now typed ---
    "0310|0311": ("highway", None,   "road bridge over the Aa stream at Helmond (legacy, bracket verified)"),
    "0505|0605": ("canal",   None,   "SON: main road over the Wilhelmina Canal N of Eindhoven (legacy; canal course by map label)"),
    "0710|0711": ("canal",   None,   "trail over the Wilhelmina/Zuid Willems junction reach (legacy)"),
    "2319|2419": ("canal",   None,   "trail over the Waal-Maas Canal (legacy)"),
    "2621|2721": ("highway", None,   "NIJMEGEN road bridge over the Waal (legacy, bracket verified)"),
    "2721|2722": ("highway", None,   "second Waal crossing at Nijmegen; drawn WITHOUT the R-R rail marking, carried as trail - neither canal nor rail, so never demolishable [12.15]"),
    "3323|3423": ("highway", None,   "ARNHEM road bridge over the Neder Rijn (legacy, bracket verified)"),
    "3325|3424": ("highway", None,   "road over the west river arm S of Arnhem (legacy, bracket verified)"),
    "3325|3425": ("highway", None,   "road over the south river arm S of Arnhem (legacy, bracket verified)"),
    # --- added: bracket symbols the band-detector missed ---
    "0503|0603": ("canal",   "road", "road over the Wilhelmina Canal NE of Best (bracket at 2x zoom)"),
    "1207|1308": ("canal",   "road", "VEGHEL: main corridor road over the Zuid Willems Canal (bracket)"),
    "1206|1307": ("rail",    None,   "rail bridge over the Zuid Willems Canal NW of Veghel (R-R marking)"),
    "2518|2519": ("canal",   "road", "road over the Waal-Maas Canal (bracket)"),
    "2219|2220": ("canal",   "road", "MALDEN road over the Waal-Maas Canal (bracket)"),
    "2120|2121": ("canal",   "road", "HEUMEN road over the Waal-Maas Canal (bracket)"),
    "2619|2720": ("canal",   None,   "trail over the Waal-Maas Canal at its Waal mouth (bracket; trail feature already present 2619|2720? added if missing as trail)"),
    "2216|2316": ("highway", "road", "GRAVE road bridge over the Maas (bracket)"),
    "1422|1423": ("highway", None,   "HEIJEN road bridge over the Maas (bracket; legacy water course runs 1323|1423 + 1423|1523 so this side carries no water - bridge recorded for the printed ink, inert for movement)"),
    "1523|1524": ("rail",    None,   "GENNEP rail bridge over the Maas (R-R marking)"),
    "1920|2020": ("rail",    None,   "MOOK rail bridge over the Maas (R-R marking)"),
    "2413|2513": ("rail",    None,   "RAVENSTEIN rail bridge over the Maas (R-R marking)"),
    "3411|3512": ("rail",    None,   "RHENEN rail bridge over the Neder Rijn (R-R marking)"),
    "3422|3522": ("rail",    None,   "ARNHEM rail bridge over the Neder Rijn (R-R marking)"),
}

FALSE_POSITIVE_BRIDGES = {
    "2610|2710": "Maas N of Ravenstein - no bridge symbol at 2x zoom; trail ink on both banks fooled the detector",
    "2623|2724": "Waal S of Nijmegen - no bridge symbol at 2x zoom",
    "3011|3112": "Waal (Betuwe reach) - no bridge symbol at 2x zoom; dike trails parallel both banks",
    "3608|3709": "NOT a bridge: white ARROW symbol = FERRY (Renkum) - retyped below",
    "3124|3125": "NOT a bridge: the Huissen white FERRY arrow prints one side east; the trail ink here is the ferry approach - retyped as the ferry's water side",
}

FERRIES = {
    "3420|3520": "DRIEL/HEVEADORP ferry over the Neder Rijn (white arrow symbol)",
    "3124|3125": "HUISSEN ferry (arrow prints between 3125/3225 which carries no legacy water; the legacy river course puts the crossed side here - trail feature dropped so the +3 ferry rate applies)",
    "3608|3709": "RENKUM ferry over the Neder Rijn (white arrow; legacy had bridge+trail here - retyped)",
}

RAIL_SUSPECTS = [
    # legacy road/trail sides that may be railway ink (declared limitation)
    "1921|2020", "2020|2121", "2121|2220", "2119|2120",     # Mook/Heumen rail
    "1206|1306", "1305|1306",                               # Veghel rail approach
    "3119|3120", "3120|3121", "3118|3119",                  # island (Valburg) line
    "2920|3020", "2921|3021", "3021|3121",                  # island line W
    "3317|3417", "3318|3319", "3319|3419",                  # island NE
    "1524|1623",                                            # Gennep rail approach
]


def build():
    t = json.load(open(SRC, encoding="utf-8"))
    sides, hexes = t["sides"], t["hexes"]
    report = {"city": [], "bridges": [], "removed": [], "ferries": []}

    # 1. city hexes
    for h in sorted(CITY_HEXES):
        assert h in hexes, f"city hex {h} missing from terrain"
        assert hexes[h]["t"] == "town", f"city hex {h} was {hexes[h]['t']!r}, expected town"
        hexes[h]["t"] = "city"
        report["city"].append(h)

    # 2. drop false positives (ferry sides keep water, lose bridge+road)
    for k, why in FALSE_POSITIVE_BRIDGES.items():
        assert k in sides, f"false-positive side {k} not in terrain"
        sides[k].pop("bridge", None)
        if k in ("3608|3709", "3124|3125"):
            sides[k].pop("road", None)
        report["removed"].append(k)

    # 3. water/road under printed bridges the band-detector put one side over
    for k, wclass in ADD_WATER.items():
        s = sides.setdefault(k, {})
        assert "water" not in s, f"{k} already has water"
        s["water"] = wclass
    for k, rclass in ADD_ROAD.items():
        s = sides.setdefault(k, {})
        if "road" not in s:
            s["road"] = rclass

    # 4. bridges + types + crossing
    for k, (btype, road, why) in BRIDGES.items():
        s = sides.setdefault(k, {})
        s["bridge"] = True
        s["bridge_type"] = btype
        s["crossing"] = True
        if road and "road" not in s:
            s["road"] = road
        report["bridges"].append((k, btype))

    # 4. ferries: +3 crossing, NOT a bridge (6.33), no road link
    for k, why in FERRIES.items():
        s = sides.setdefault(k, {})
        assert not s.get("bridge"), f"ferry side {k} still has a bridge flag"
        s["ferry"] = True
        s["crossing"] = True
        report["ferries"].append(k)

    t["provenance"] = {
        "base": "ref/terrain.json (legacy validated extraction)",
        "corrections": "build_terrain.py 2026-07-11 eye-verified pass (see module docstring)",
        "rail_suspects": RAIL_SUSPECTS,
    }
    json.dump(t, open(OUT, "w", encoding="utf-8"), indent=1)
    return t, report


def validate(t, report):
    sides, hexes = t["sides"], t["hexes"]
    ok = True

    def check(cond, msg):
        nonlocal ok
        print(("  PASS  " if cond else "  FAIL  ") + msg)
        ok = ok and cond

    check(len(report["city"]) == 11, f"11 city hexes retyped ({len(report['city'])})")
    check(sum(1 for v in hexes.values() if v['t'] == 'city') == 11, "terrain holds exactly 11 city hexes")
    check(sum(1 for v in hexes.values() if v['t'] == 'town') == 154 - 11, "towns = legacy 154 minus 11 cities")

    n_br = sum(1 for v in sides.values() if v.get("bridge"))
    check(n_br == len(BRIDGES), f"bridge count == curated table ({n_br} vs {len(BRIDGES)})")
    check(all(v.get("bridge_type") in ("highway", "rail", "canal")
              for v in sides.values() if v.get("bridge")), "every bridge carries a type")
    check(all(v.get("crossing") for v in sides.values()
              if v.get("bridge") or v.get("ferry")), "every bridge/ferry side carries crossing")
    n_fy = sum(1 for v in sides.values() if v.get("ferry"))
    check(n_fy == 3, f"3 ferries ({n_fy})")
    for k in FALSE_POSITIVE_BRIDGES:
        check(not sides.get(k, {}).get("bridge"), f"false positive {k} removed")
    # every bridge/ferry except the documented Heijen ink case lies on a water side
    for k in list(BRIDGES) + list(FERRIES):
        if k == "1422|1423":
            continue
        check("water" in sides.get(k, {}), f"{k} lies on a water side")
    # demolishable set = canal + rail only
    demo = sorted(k for k, v in sides.items()
                  if v.get("bridge") and v.get("bridge_type") in ("canal", "rail"))
    check(len(demo) == 15, f"15 demolishable bridges (9 canal + 6 rail): {len(demo)}")
    n_canal = sum(1 for k in demo if sides[k]["bridge_type"] == "canal")
    check(n_canal == 9, f"9 canal bridges ({n_canal})")
    print("  demolishable:", ", ".join(demo))
    return ok


if __name__ == "__main__":
    t, report = build()
    print(f"terrain written: {OUT}")
    print(f"cities: {report['city']}")
    good = validate(t, report)
    print("ALL PASS" if good else "FAILURES ABOVE")
    sys.exit(0 if good else 1)
