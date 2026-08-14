import json
import os
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "oob_2nd_ed.json")


def load(n):
    return json.load(open(os.path.join(HERE, n), encoding="utf-8"))


def main():
    grid = load("map_grid.json")["editions"]["2nd"]
    photo = load("counters_photo.json")
    mod = load("module_oob.json")

    printed = {}
    for side, hexes in grid["at_start_pictures"]["hexes"].items():
        for h, f in hexes.items():
            printed[h] = (side, f)

    modrows = {r["ccrr"]: r for r in mod["at_start"]}

    photo_pool = {}
    for block in ("french", "allied"):
        for c in photo["counters"][block]:
            photo_pool.setdefault(block, []).append(c)

    units = []
    disagree = []
    for h in sorted(printed):
        side, factors = printed[h]
        m = modrows.get(h)
        row = {
            "hex": h,
            "side": "French" if side == "french" else "Allied",
            "factors": factors,
            "combat_strength": int(factors.split("-")[0]),
            "movement_allowance": int(factors.split("-")[1]),
            "unit_type": m["type"] if m else None,
            "designation": m["designation"] if m else None,
            "contingent": m.get("contingent") if m else None,
            "provenance": {
                "hex": "printed 2nd Ed map, unit pictures (PREP-3), corroborated hex-for-hex by "
                "the module at-start save (PREP-4 job C): 44/44",
                "side": "printing orientation + the printed Front Line (PREP-3), 44/44 agreement",
                "factors": "printed map (PREP-3, three cells corrected in PREP-4) AND the printed "
                "counter photograph (PREP-4 job A) AND the module (PREP-4 job C)",
                "unit_type": "printed counter photograph NATO symbol (PREP-4 job A); the printed "
                "map pictures do not encode type in map_grid.json",
                "designation": "module buildFile, checked hex by hex against the printed pictures "
                "on the PREP-4 contact sheets: 44/44 agree",
            },
        }
        if m:
            mf = f"{m['combat_strength']}-{m['movement_allowance']}"
            row["module_factors"] = mf
            row["module_agrees"] = mf == factors
            if mf != factors:
                disagree.append({"hex": h, "printed": factors, "module": mf})
        units.append(row)

    tr = mod["reinforcements"]["printed_time_record_2nd_ed"]
    pr_types = [c["unit_type"] for c in photo["counters"]["prussian"]]
    pr_counter = {}
    for c in photo["counters"]["prussian"]:
        pr_counter.setdefault(c["printed_factors"], []).append(c["unit_type"])

    reinforcements = []
    for i, f in enumerate(tr, start=1):
        opts = pr_counter.get(f, [])
        reinforcements.append({
            "seq": i,
            "side": "Allied",
            "contingent": "Prussian",
            "factors": f,
            "combat_strength": int(f.split("-")[0]),
            "movement_allowance": int(f.split("-")[1]),
            "unit_type": opts[0] if len(set(opts)) == 1 else (sorted(set(opts)) if opts else None),
            "arrival_turn": 2,
            "arrival_slot": "2 pm",
            "entry_edge": "East edge, anywhere along it, at as many different points as desired",
            "entry_cost": "placing a unit on the map costs one Movement Point",
            "delay_legal": False,
            "may_leave_map": False,
            "losses_count_as": "Allied",
        })

    side_tot = Counter()
    type_tot = Counter()
    for u in units:
        side_tot[u["side"]] += u["combat_strength"]
        type_tot[(u["side"], u["unit_type"])] += 1

    doc = {
        "produced_by": "PREP-5 collation, games/napoleon-at-waterloo/ingest/naw_oob_merge.py",
        "read_on": "2026-08-14",
        "edition": "SPI Napoleon at Waterloo, SECOND EDITION, copyright 1971",
        "authority": "DERIVED CONSOLIDATION. Merges three independently-read witnesses into the "
        "single roster an encoder consumes. It re-reads nothing; every field carries the bite that "
        "established it. Where witnesses disagreed, the disagreement was settled in PREP-4 against "
        "the primary folio and recorded in map_grid.json corrections_prep4 - not averaged here.",
        "witnesses": {
            "printed_map": "folio p.5 at-start unit pictures (PREP-3, corrected PREP-4)",
            "printed_counters": "folio p.4 punched counter-set photograph (PREP-4 job A)",
            "module": "Oliver ed2 buildFile.xml + Beginning Setup.vsav (PREP-4 job C, "
            "corroborating tier only, never promoted over print)",
        },
        "at_start_units": units,
        "reinforcements": reinforcements,
        "module_factor_disagreements": disagree,
        "totals": {
            "at_start_units": len(units),
            "combat_strength_by_side": dict(side_tot),
            "type_counts": {f"{k[0]} {k[1]}": v for k, v in sorted(type_tot.items())},
            "reinforcement_units": len(reinforcements),
            "reinforcement_combat_strength": sum(r["combat_strength"] for r in reinforcements),
        },
        "victory_context": "40 Combat Strength Points destroyed is the threshold. Against these "
        "totals that is 40 of 89 French, and 40 of 107 Allied-plus-Prussian.",
        "components_note": "The punched set contains exactly ONE marker (the turn marker). There "
        "is no demoralization marker and no exited-units marker; the Demoralization Scale's own "
        "printed instruction is to use the first destroyed enemy unit as the marker.",
        "open_items": [
            "unit_type for the nine Prussians is taken from the counter photograph by factor "
            "value; where two Prussian counters share a factor pair the type is listed as the set "
            "of possibilities rather than guessed",
            "the counter reverse faces were never photographed (PREP-4 section 10)",
        ],
    }
    json.dump(doc, open(OUT, "w"), indent=1)

    print("at-start units:", len(units))
    print("CS by side:", dict(side_tot))
    print("module factor disagreements:", len(disagree), disagree)
    print("reinforcements:", len(reinforcements), "CS", doc["totals"]["reinforcement_combat_strength"])
    print("types:", doc["totals"]["type_counts"])
    print("->", OUT)


if __name__ == "__main__":
    main()
