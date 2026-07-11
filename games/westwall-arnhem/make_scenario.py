"""Build scenario_historical.json for Westwall: Arnhem [18.1] from the printed
Exclusive Rules schedule + the module's pieces.

Sources: rules_transcription.json (canonical 18.12-18.16 schedule, OCR text
counter-verified against all 95 Arnhem counter faces 2026-07-11) and
counter_stats_by_image.json (mastermind's factor->image binding, with the
contact-sheet corrections listed in rules_transcription binding_corrections).

Three-source agreement is ASSERTED for every unit: schedule factors ==
(corrected) image-bound factors, side and class from the counter art.

Also: stats patterns + German side tokens + classes -> game.json; the VP
zones "north of the Waal" / "north of the Neder Rijn" are computed by flood
fill over the terrain's river courses and sanity-asserted; setup.vsav is
built from the module's own PieceSlots with numeric gate ids.
"""
import json, os, re, sys
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
ING = os.path.normpath(os.path.join(ROOT, "..", "VassalIngest", "westwall"))
sys.path.insert(0, os.path.join(ROOT, "engine"))
import gamespec, make_save                                     # noqa: E402

tr = json.load(open(os.path.join(HERE, "rules_transcription.json"), encoding="utf-8"))
sc = tr["scenario_historical"]
bi = json.load(open(os.path.join(ING, "counter_stats_by_image.json"), encoding="utf-8"))
counters = bi.get("counters", bi)

# ---------------------------------------------------- corrected image factors
# contact-sheet corrections (rules_transcription.json binding_corrections)
FACTOR_FIX = {
    "A 1-1Lt.png": "2-1-4/1-7", "A 1-2Lt.png": "2-1-4/1-7",
    "A 1-2.png": "1-2-7", "A 2107 M.png": "4-4-10",
    "A 1-6P.png": "2-3-7", "A 2-6P.png": "2-3-7",
    "A Engineers.png": "3-3-10",
    "A 55.png": "4-2-7/3-10",
    "A 15-19.png": "2-1-4/3-10",
}

# unit class per image, read off the counter symbols (full visual pass)
CLASSES = {
    "mech": ["A Grsn.png", "A Hbr.png", "A 1-9SS.png", "A 2-9SS.png", "A 3-9SS.png",
             "A 1-10SS.png", "A 2-10SS.png", "A 3-10SS.png", "A 2107 M.png"],
    "armor": ["A 2107 P.png", "A Hnke.png", "A 5-1C.png", "A 5-2G.png", "A 5-2I.png",
              "A 29-3.png"],
    "recon": ["A 9SS Recon.png", "A 10SS Recon.png"],
    "sp_artillery": ["A 15-19.png", "A 44.png", "A 55.png"],
    "artillery": ["A 94.png", "A 112.png", "A 153.png", "A 179.png", "A 9SS Arty.png",
                  "A 1-10SS Arty.png", "A 2-10SS Arty.png", "A Hber Arty.png", "A Wltr.png"],
    "ab_artillery": ["A 1-1Lt.png", "A 1-2Lt.png", "A 82-1 Arty.png", "A 82-2 Arty.png",
                     "A 101-1 Arty.png", "A 101-2 Arty.png"],
    "glider": ["A 1-1-1B.png", "A 1-1-2S.png", "A 1-1-7K.png", "A 82-325-1.png",
               "A 82-325-2.png", "A 101-327-1.png", "A 101-327-2.png"],
    "engineer": ["A Engineers.png"],
    "dz": ["A 1 DZ.png", "A 101 DZ.png", "A 82 DZ.png"],
}
CLASS_OF = {img: cl for cl, imgs in CLASSES.items() for img in imgs}
# 5.24 vehicle classes; airborne = arrived by air (11.2/13.2/15.3/17.32)
VEHICLE = {"armor", "recon", "mech", "sp_artillery"}

# printed designation -> module image
IMG = {
    "Krft": "A Kraft.png", "2/9SS": "A 2-9SS.png", "9SS Recon": "A 9SS Recon.png",
    "Grsn": "A Grsn.png", "1/406": "A 1-406.png", "2/406": "A 2-406.png",
    "BrDf": "A BrDf.png",
    "101 DZ": "A 101 DZ.png", "82 DZ": "A 82 DZ.png", "1 DZ": "A 1 DZ.png",
    "1/1": "A 1-1-1.png", "2/1": "A 1-1-2.png", "3/1": "A 1-1-3.png",
    "2S/1": "A 1-1-2S.png", "7K/1": "A 1-1-7K.png", "1B/1": "A 1-1-1B.png",
    "10/4": "A 1-4-10.png", "11/4": "A 1-4-11.png", "156/4": "A 1-4-156.png",
    "1/1Lt": "A 1-1Lt.png", "2/1Lt": "A 1-2Lt.png",
    "1/82": "A 82-1 Arty.png", "2/82": "A 82-2 Arty.png",
    "1/101": "A 101-1 Arty.png", "2/101": "A 101-2 Arty.png",
    "1/Pol": "A Pol-1.png", "2/Pol": "A Pol-2.png", "3/Pol": "A Pol-3.png",
    "2I/5": "A 5-2I.png", "3I/32": "A 32-3I.png", "2D/231": "A 2D-231.png",
    "55": "A 55.png", "Engineers": "A Engineers.png",
    "15/19": "A 15-19.png", "44": "A 44.png", "1C/5": "A 5-1C.png",
    "2G/5": "A 5-2G.png", "32": "A 32.png", "129": "A 129.png", "153": "A 153.png",
    "130": "A 130.png", "214": "A 214.png",
    "94": "A 94.png", "112": "A 112.png", "179": "A 179.png", "3/29": "A 29-3.png",
    "1/vT": "A 1-vT.png", "2/vT": "A 2-vT.png", "3/vT": "A 3-vT.png",
    "1/9SS": "A 1-9SS.png", "3/9SS": "A 3-9SS.png",
    "1/10SS Arty": "A 1-10SS Arty.png", "10SS Recon": "A 10SS Recon.png",
    "1/59": "A 1-59.png", "2/59": "A 2-59.png",
    "2107 P": "A 2107 P.png", "2107 M": "A 2107 M.png",
    "1/6PT": "A 1-6P.png", "2/6PT": "A 2-6P.png", "180": "A 180.png",
    "9SS Arty": "A 9SS Arty.png", "2/10SS": "A 2-10SS.png", "Hnke": "A Hnke.png",
    "Wltr": "A Wltr.png", "1/1PT": "A 1-1P.png", "2/1PT": "A 2-1PT.png",
    "1/10SS": "A 1-10SS.png", "2/10SS Arty": "A 2-10SS Arty.png",
    "1/Hbr": "A 1-Hber.png", "2/Hbr": "A 2-Hber.png", "Hbr": "A Hbr.png",
    "Hber Arty": "A Hber Arty.png", "3/10SS": "A 3-10SS.png",
    "1/6": "A 1-6.png", "2/6": "A 2-6.png", "1/2": "A 1-2.png", "Jngw": "A Jngw.png",
    "1/501": "A 101-501-1.png", "2/501": "A 101-501-2.png", "3/501": "A 101-501-3.png",
    "1/502": "A 101-502-1.png", "2/502": "A 101-502-2.png", "3/502": "A 101-502-3.png",
    "1/506": "A 101-506-1.png", "2/506": "A 101-506-2.png", "3/506": "A 101-506-3.png",
    "1/504": "A 82-504-1.png", "2/504": "A 82-504-2.png", "3/504": "A 82-504-3.png",
    "1/505": "A 82-505-1.png", "2/505": "A 82-505-2.png", "3/505": "A 82-505-3.png",
    "1/508": "A 82-508-1.png", "2/508": "A 82-508-2.png", "3/508": "A 82-508-3.png",
    "1/325": "A 82-325-1.png", "2/325": "A 82-325-2.png",
    "1/327": "A 101-327-1.png", "2/327": "A 101-327-2.png",
}


def bound_factors(img):
    e = counters.get(img)
    assert e is not None, f"image not in counter_stats_by_image: {img}"
    if img in FACTOR_FIX:
        return FACTOR_FIX[img]
    f = e.get("factors")
    if e.get("factors_secondary"):
        f = f + "/" + e["factors_secondary"]
    return f


def parse_factors(s, cls):
    """'A-D-M' -> att/def/ma; artillery 'B-F-R/D-M' -> barrage/fpf/range/def/ma."""
    if "/" in s:
        top, bot = s.split("/")
        b, f, r = (int(x) for x in top.split("-"))
        d, m = (int(x) for x in bot.split("-"))
        return {"att": b, "def": d, "ma": m, "barrage": b, "fpf": f, "range": r}
    a, d, m = (int(x) for x in s.split("-"))
    return {"att": a, "def": d, "ma": m}


# ------------------------------------------------------------- terrain helpers
G = gamespec.Game(HERE)
terr = G.terrain
ONMAP = {k for k, v in terr["hexes"].items() if v["t"] != "offmap"}


def hx(s):
    return (int(s[:2]), int(s[2:]))


def edge_hexes(a, b):
    """Map-edge hexes 'on or between' printed endpoints a,b [15.41/18.15].
    Same column -> the column's on-map rows in range (east edge 3907-3916);
    same/staggered row -> per column the outermost on-map hex on that edge."""
    (ca, ra), (cb, rb) = hx(a), hx(b)
    out = []
    if ca == cb:
        for r in range(min(ra, rb), max(ra, rb) + 1):
            if f"{ca:02d}{r:02d}" in ONMAP:
                out.append([ca, r])
        return out
    top = min(ra, rb) <= 2      # row-1 edge vs row-25/26 edge
    for c in range(min(ca, cb), max(ca, cb) + 1):
        rows = [r for r in range(0, 28) if f"{c:02d}{r:02d}" in ONMAP]
        if not rows:
            continue
        r = min(rows) if top else max(rows)
        out.append([c, r])
    return out


# ------------------------------------------------------------------ VP zones
def river_blocked(a, b):
    key1 = f"{a[0]:02d}{a[1]:02d}|{b[0]:02d}{b[1]:02d}"
    key2 = f"{b[0]:02d}{b[1]:02d}|{a[0]:02d}{a[1]:02d}"
    s = terr["sides"].get(key1) or terr["sides"].get(key2) or {}
    return s.get("water") == "river"


def flood(seed):
    seen = {seed}
    q = deque([seed])
    while q:
        cur = q.popleft()
        for nb in G.neighbors(*cur):
            if nb in seen or f"{nb[0]:02d}{nb[1]:02d}" not in ONMAP:
                continue
            if river_blocked(cur, nb):
                continue
            seen.add(nb)
            q.append(nb)
    return seen


rijn_zone = flood((39, 19))          # seed: DZ 1 hex, deep north of the Rijn
island = flood((31, 20))             # seed: the Betuwe island (Valburg area)
bemmel = flood((31, 25))             # the Waal-far-bank strip enclosed by the
                                     # Waal and the Rijn arm (Bemmel/Gendt) -
                                     # north of the Waal, river-locked from the
                                     # island except via the Huissen ferry
south = flood((1, 5))                # seed: the Allied entry hex
assert not (rijn_zone & south), "Rijn zone leaks into the southern bank"
assert not (island & south), "island leaks into the southern bank"
assert not (rijn_zone & island), "Rijn zone leaks into the island"
assert not (bemmel & (south | rijn_zone | island)), "Bemmel strip leaks"
assert (31, 25) in bemmel and (33, 26) in bemmel
for h, zone, want in [((35, 23), rijn_zone, True), ((35, 21), rijn_zone, True),
                      ((37, 22), rijn_zone, True), ((27, 21), island, True),
                      ((31, 19), island, True), ((26, 21), south, True),
                      ((1, 5), south, True), ((21, 16), south, True)]:
    assert (h in zone) == want, f"zone sanity: {h} in expected zone = {want}"
waal_zone = rijn_zone | island | bemmel
print(f"zones: north-of-Rijn {len(rijn_zone)} hexes, island {len(island)}, "
      f"south {len(south)}, unassigned {len(ONMAP) - len(rijn_zone) - len(island) - len(south)}")

# ------------------------------------------------------------------ units
NEXT = [101]
used_imgs = []


def mk(desig, side, cls, factors, division=None, hexnum=None, due=None,
       arrival=None, entry=None, target=None):
    img = IMG[desig]
    used_imgs.append(img)
    st = parse_factors(factors, cls)
    e = {"id": str(NEXT[0]), "slot": os.path.splitext(img)[0], "img": img,
         "side": side, "desig": desig, "cls": cls or "infantry", "stats": st}
    NEXT[0] += 1
    if cls in ("glider", "ab_artillery", "polish", "para") or division:
        e["airborne"] = True
    if division:
        e["division"] = division
    if hexnum:
        e["hex"] = [int(hexnum[:2]), int(hexnum[2:])]
    if due is not None:
        e["due"] = due
        e["arrival"] = arrival
        if entry:
            e["entry"] = entry
        if target:
            e["target"] = [int(target[:2]), int(target[2:])]
    return e


units, reserve = [], []
for u in sc["german_initial"]:
    factors = bound_factors(IMG[u["desig"]])
    assert factors == u["factors"], f"{u['desig']}: schedule {u['factors']} != counter {factors}"
    units.append(mk(u["desig"], "Ger", u.get("class", "infantry"), factors,
                    hexnum=u["hex"]))
for d in sc["dz_counters"]:
    units.append(mk(d["desig"], "All", "dz", "0-0-0", hexnum=d["hex"]))

for gt_key, groups in sc["allied_airborne"].items():
    if not gt_key.startswith("gt"):
        continue
    gt = int(gt_key.replace("gt", ""))
    for grp in groups:
        cls = grp.get("class", "para")
        div = grp["division"]
        for desig in grp["units"]:
            factors = bound_factors(IMG[desig])
            assert factors == grp["factors"], \
                f"{desig}: schedule {grp['factors']} != counter {factors}"
            cl = "polish" if div == "1" and "Pol" in desig else cls
            e = mk(desig, "All", cl, factors, division=div, due=gt,
                   arrival="airborne", target=grp["target"])
            reserve.append(e)

GROUND_ENTRY = [[1, 5], [1, 6]]
for gt_key, groups in sc["allied_ground"].items():
    if not gt_key.startswith("gt"):
        continue
    gt = int(gt_key.replace("gt", ""))
    for u in groups:
        factors = bound_factors(IMG[u["desig"]])
        assert factors == u["factors"], f"{u['desig']}: {u['factors']} != {factors}"
        reserve.append(mk(u["desig"], "All", u.get("class", "infantry"), factors,
                          due=gt, arrival="column", entry=GROUND_ENTRY))

for gt_key, groups in sc["german_reinforcements"].items():
    if not gt_key.startswith("gt"):
        continue
    gt = int(gt_key.replace("gt", ""))
    for u in groups:
        factors = bound_factors(IMG[u["desig"]])
        assert factors == u["factors"], f"{u['desig']}: {u['factors']} != {factors}"
        ent = u["entry"]
        hexes = edge_hexes(*ent.split("-")) if "-" in ent else [list(hx(ent))]
        assert hexes, f"no entry hexes for {u['desig']} ({ent})"
        reserve.append(mk(u["desig"], "Ger", u.get("class", "infantry"), factors,
                          due=gt, arrival="edge", entry=hexes))

# ------------------------------------------------------------------ assertions
assert len(units) == 10, f"at-start {len(units)} != 7 German + 3 DZ"
assert len(reserve) == 89, f"reserve {len(reserve)} != 89"
assert sum(1 for u in reserve if u["side"] == "All") == 58
assert sum(1 for u in reserve if u["side"] == "Ger") == 31
ids = [u["id"] for u in units + reserve]
assert len(ids) == len(set(ids)), "duplicate ids"
assert len(used_imgs) == len(set(used_imgs)), "an image was used twice"
front_pieces = {k for k, v in counters.items()
                if v.get("battle") == "Arnhem" and v.get("state") == "front"
                and v.get("kind") == "piece"}
have = set(used_imgs) - {"A 1 DZ.png", "A 101 DZ.png", "A 82 DZ.png", "A Engineers.png"}
assert have == front_pieces, (f"schedule/counter mismatch: missing "
                              f"{sorted(front_pieces - have)}, extra {sorted(have - front_pieces)}")
n_arty = {"All": 0, "Ger": 0}
for u in units + reserve:
    if u["cls"] in ("artillery", "ab_artillery", "sp_artillery"):
        n_arty[u["side"]] += 1
assert n_arty == {"All": 13, "Ger": 5}, n_arty
gsp = {k: v for k, v in sc["allied_gsp"].items() if k != "cite"}
assert sum(gsp.values()) == 19 and gsp["3"] == 7, "GSP schedule [18.16]"

scenario = {
    "name": "Arnhem - Historical Scenario (10 GTs) [18.1]",
    "mode": "westwall",
    "game": {
        "turns": 10,
        "first_player": "All",
        "turn_labels": [f"GT {i}" for i in range(1, 11)],
        "gsp": {"All": gsp},
        "gsp_cite": "[18.16] Allied Ground Support Points per GT; [14.11] usable only within 3 hexes of an Allied non-airborne unit; [9.14] unused points are lost",
        "weather": "off",
        "weather_cite": "[18.17] the Weather Option requires both players' agreement - base Historical Scenario runs without it; airborne arrivals use the fixed 18.13 hexes"
    },
    "units": units,
    "reserve": reserve,
    "vp": {
        "allied_per_german_unit_eliminated": 1,
        "german_per_allied_unit_destroyed": 5,
        "waal_per_unit_per_turn": 5,
        "rijn_per_unit_end": 10,
        "german_per_loc_fail_per_turn": 3,
        "waal_zone": sorted(f"{c:02d}{r:02d}" for c, r in waal_zone),
        "rijn_zone": sorted(f"{c:02d}{r:02d}" for c, r in rijn_zone),
        "levels": [[3.0, "German Strategic"], [2.01, "German Tactical"],
                   [2.0, "Draw"], [1.01, "Allied Tactical"], [0.0, "Allied Strategic"]],
        "cite": "[17.1] VP schedule; [17.2] geographical VPs need a LOC; [17.35] LOC judged at the end of each German player-turn; [17.4] victory ratio German:Allied; zones computed by river-course flood fill (Waal course 2726-3005, Neder Rijn course 3706-3424)"
    },
    "loc": {
        "ground_exit": [[1, 5], [1, 6]],
        "airborne_max": 7,
        "cite": "[17.31] ground LOC to 0105/0106 (trail locks to road/trail, road locks to road); [17.32] airborne LOC <= 7 hexes to the divisional DZ counter; [17.33] blocked by enemy units/ZOC, friends negate ZOC; [17.34] never through unbridged river or stream hexsides; [17.36] Polish and German units exempt"
    },
    "rules_scope": {
        "enforced": [
            "Terrain costs: clear 1 / mixed 2 / woods 2 / broken 3 / rough 4 / town-city 1 MP [Terrain Key/5.21], cumulative hexside costs [5.21]",
            "Roads 1/2 MP, trails 1 MP through their hexsides regardless of hex terrain [5.22/5.23]",
            "Rivers prohibited except bridges and ferries (+3 MP); streams/canals +3 MP unless bridged [Terrain Key]",
            "Vehicle classes (armored/recon/mechanized/SP artillery) never enter rough, broken or woods hexes and never cross river/stream hexsides except through road/trail hexsides; eliminated when forced to retreat in violation [5.24]",
            "No entering enemy-occupied hexes [5.12]; MA never exceeded, no accumulation [5.13]",
            "STACKING PROHIBITED at phase end [5.31]; free friendly pass-through [5.31/5.32]; the Engineer assault stack [13.24] and DZ counters [15.35] excepted",
            "Rigid ZOC: stop on entry [6.0], no extra MP [6.12], never exit an EZOC by movement [5.14/6.13]; ZOC never through non-bridge river hexsides, ferries are non-bridge [6.33]",
            "Reinforcements: printed schedule [18.13-18.15]; road-rate column entry [15.13]; blocked-hex alternates [15.22]; withholding [15.23]",
            "Airborne arrivals: within one hex of the printed hex, one unit per hex, EZOC allowed, occupied hexes forbidden (eliminated if forced), MA 3 on the arrival GT [15.31-15.33]",
            "DZ counters: no ZOC/strength, free stacking, overrunnable, never destroyed [15.35]",
            "German map exit and same-edge re-entry (west 0601-2301, east 0126-2726) [15.4]",
            "Bridge demolition: canal+rail bridges, German option at first Allied adjacency, die 1-2, one attempt ever; highway bridges never [12.x]; engine-owned seeded die",
            "Engineer: canal-bridge repair [13.1]; airborne/glider river crossing [13.2]; assault stack on the Stream CRT line [13.24]; no Allied retreat across rivers / out of the Engineer hex, no German advance across rivers [13.25]; replacement at 0105/0106 [13.3]",
            "Turn sequence: Allied first player, movement then combat, 10 GTs [4.1/18.17]"
        ],
        "enforced_tier2": [
            "Mandatory combat: every adjacent enemy attacked, every adjacent friendly attacks [7.0/7.11/7.12/7.21]; multi-hex adjacency [7.23]; once per phase each way [7.14]",
            "Integrated differential CRT: attack+barrage+GSP minus defense+FPF, defender's terrain row, die 1-6 [7.0/7.61]; bounds clamp [7.61 notes]",
            "Never voluntarily reduce a differential [7.52]",
            "Defender's best terrain [7.44/7.45]; stream hexside benefit only when ALL attackers cross streams [7.42]; bridge line when all attackers cross a bridge [7.61]",
            "Retreats 1-4 hexes away from the combat position, EZOC blocked after the first hex, prohibited hexsides never, partial retreat = elimination [7.7]; displacement chains [7.8]",
            "Advance after combat along the Path of Retreat, any number of victorious adjacent participants, immediate, never forced [7.9]",
            "City hexes: retreat reduction by two at owner's option (D3 min 1, D4 min 2; not airborne artillery; negated when surrounded except Allied airborne/glider); Town CRT line [11.1/11.2]",
            "Artillery: barrage in range without LOS [8.1/8.61]; combined attacks [8.2]; mandatory adjacent participation, results suffered [8.3]; river-adjacency exception [8.34]; FPF under the 8.41 conditions, once per GT [8.46]; pure-artillery attacks only D2-D4/De apply [8.15]; max two artillery per combat [14.12]",
            "Allied GSP as barrage/FPF within 3 hexes of a non-airborne Allied unit [9.0/14.11/18.16]",
            "Victory: VP schedule, LOC traces at the end of each German player-turn, Waal/Rijn geographical awards, victory-level ratio [17.x]"
        ],
        "umpired": [
            "Weather Option 16.0 (off by default in the Historical Scenario [18.17]; Scenario II not offered)",
            "The printed map's railway LINES are decorative (rail bridges are enforced); the validated legacy road/trail extraction may carry railway ink as trail on a few sides (list in terrain provenance) - movement there can be one class cheaper than strictly printed",
            "5.15 touched-piece etiquette (table rule, meaningless under a gate)"
        ]
    }
}

out = os.path.join(HERE, "scenario_historical.json")
json.dump(scenario, open(out, "w", encoding="utf-8"), indent=1)
print(f"scenario written: {out}")
print(f"  units {len(units)} (7 Ger + 3 DZ), reserve {len(reserve)} (All 58 / Ger 31)")

# ------------------------------------------------- stats/classes -> game.json
gj_path = os.path.join(HERE, "game.json")
gj = json.load(open(gj_path, encoding="utf-8"))
pats = []
for u in units + reserve:
    st = u["stats"]
    pats.append([u["slot"], [st["att"], st["def"], st["ma"]]])
pats.sort(key=lambda p: (-len(p[0]), p[0]))
gj["stats"]["patterns"] = pats
# board-layer side fallback: substring matching means 'A 1-2' (German 1/2)
# would also hit 'A 1-2Lt' (Allied) - Allied tokens are emitted FIRST so the
# more specific Allied names win (gamespec.side() honors dict order)
gj["sides"]["detect_tokens"] = {
    "All": sorted(u["slot"] for u in units + reserve if u["side"] == "All"),
    "Ger": sorted(u["slot"] for u in units + reserve if u["side"] == "Ger")}
classes = {}
for u in units + reserve:
    classes.setdefault(u["cls"], set()).add(u["slot"])
gj["classes"] = {k: sorted(v) for k, v in sorted(classes.items())}
gj["classes"]["note"] = ("generated by make_scenario.py from the counter-symbol "
                         "visual pass; vehicle classes for 5.24 = armor, recon, "
                         "mech, sp_artillery; airborne flag lives on scenario "
                         "units (para/glider/ab_artillery/polish)")
json.dump(gj, open(gj_path, "w", encoding="utf-8"), indent=1)
print(f"game.json stats patterns: {len(pats)}")

# ------------------------------------------------- setup .vsav (board mirror)
bf = open(os.path.join(ING, "extracted", "buildFile"), encoding="utf-8").read()
img2gpid = {}
for m in re.finditer(r'<VASSAL\.build\.widget\.PieceSlot[^>]*?entryName="([^"]*)"'
                     r'[^>]*?gpid="(\d+)"[^>]*>(.*?)</VASSAL\.build\.widget\.PieceSlot>',
                     bf, re.S):
    mi = re.search(r'piece;;;([^;]+?\.(?:png|gif|svg));', m.group(3))
    if mi:
        img2gpid.setdefault(mi.group(1), m.group(2))
save_units = []
for u in units:
    assert u["img"] in img2gpid, f"module has no slot for {u['img']}"
    save_units.append({"id": u["id"], "gpid": img2gpid[u["img"]], "hex": u["hex"]})
for i, u in enumerate(reserve):
    assert u["img"] in img2gpid, f"module has no slot for {u['img']}"
    save_units.append({"id": u["id"], "gpid": img2gpid[u["img"]],
                       "xy": [3960 + (i // 24) * 110, 180 + (i % 24) * 96]})
make_save.build(G, {"units": save_units}, os.path.join(HERE, "setup.vsav"))
print("ALL ASSERTIONS PASS")
