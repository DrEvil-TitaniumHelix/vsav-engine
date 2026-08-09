"""SoJ PREP-3 — assemble the staircase verdict table.

Combines:
  * stair_evidence.py's protrusion score for all 462 Elevated<->Ground hexsides,
  * the adjacency check on every hexside key currently in terrain.json,
  * The Vassal's by-eye verdicts read off the per-strongpoint contact sheets
    (stair_sheets.py, evidence pack at Desktop\\SoJ_PREP3\\sheets).

Emits games/siege-of-jerusalem-ah/ingest/staircases_evidence.json.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_hex_crop import TERRAIN, name_of, neighbours, parse_name

OUT = r"C:\VassalArnhem\games\siege-of-jerusalem-ah\ingest\staircases_evidence.json"

# ---------------------------------------------------------------- by-eye pass
# CONFIRMED  = a stair bar is plainly visible crossing that hexside on the printed map
# AMBIGUOUS  = something is there but it cannot be told from wall art / ring bleed / road
# ABSENT     = nothing at all at readable resolution
# CONTAMINATED = the neighbouring "ground" hex carries structure or road art, so the
#                protrusion score is meaningless there (usually an unverified-terrain hex)
VERDICT = {
    # -- session-1 hand-confirmed, independently re-confirmed this pass --
    "P33:S": "CONFIRMED", "P33:SE": "CONFIRMED",
    "S30:S": "CONFIRMED", "S30:SE": "CONFIRMED",
    "Y24:S": "CONFIRMED", "Y24:SE": "CONFIRMED",
    "PP23:NW": "CONFIRMED", "PP23:SW": "CONFIRMED",
    # -- newly art-confirmed this pass (were "inferred from pattern") --
    "M36:S": "CONFIRMED", "M36:SE": "CONFIRMED",
    "AA22:S": "CONFIRMED", "AA22:SE": "CONFIRMED",
    "CC30:S": "CONFIRMED", "CC30:SE": "CONFIRMED",
    "V27:S": "CONFIRMED", "V27:SE": "CONFIRMED",
    "V39:NE": "CONFIRMED", "V39:SE": "CONFIRMED",
    "Z33:SE": "CONFIRMED",
    "FF28:S": "CONFIRMED",
    "MM17:S": "CONFIRMED",
    "R45:SE": "CONFIRMED",
    "GG17:S": "CONFIRMED",
    "PP20:NW": "CONFIRMED", "PP20:SW": "CONFIRMED",
    "QQ29:NW": "CONFIRMED", "QQ29:SW": "CONFIRMED",
    # -- encoded, but the art will not settle it --
    "II27:S": "AMBIGUOUS", "JJ17:S": "AMBIGUOUS", "L50:NE": "AMBIGUOUS",
    "LL30:SW": "AMBIGUOUS", "MM32:SE": "AMBIGUOUS", "QQ25:SW": "AMBIGUOUS",
    "O50:NE": "AMBIGUOUS", "DD19:S": "AMBIGUOUS",
    "MM33:S": "CONTAMINATED",
    # -- encoded, no printed evidence whatsoever --
    "G40:SE": "ABSENT", "G43:NE": "ABSENT", "G43:SE": "ABSENT",
    "O50:N": "ABSENT", "L50:N": "CONTAMINATED", "M50:N": "ABSENT", "M50:NE": "ABSENT",
    "PP17:SW": "ABSENT", "V42:SE": "ABSENT",
    "MM30:SE": "ABSENT", "MM31:SE": "ABSENT", "PP33:S": "ABSENT",
    # -- NOT currently encoded, but a bar is visible --
    "Z33:S": "CONFIRMED-NEW",
}

# hexes lying beyond the Gallus battlefield (Antonia / Temple complex, old city).
# INGEST_NOTES: "Antonia complex (II33-JJ36 fortresses, KK35/KK36 forts) + Temple north
# wall (MM30-33/NN31-33) lie beyond it (out of Gallus play)".  MM30 is listed BOTH as a
# Second-Wall bastion and as part of the Temple north wall — flagged, not decided.
OUT_OF_SCOPE = {"MM31", "MM32", "MM33", "NN31", "NN32", "NN33"}
SCOPE_DISPUTED = {"MM30"}


def adjacency(sk):
    a, b = sk.split("|")
    L, row = int(a[:2]), int(a[2:])
    nb = neighbours(L, row)
    return b in {"%02d%02d" % v for v in nb.values()}


def main():
    terrain = json.load(open(TERRAIN, encoding="utf-8"))
    ev = {r["side_key"]: r for r in
          json.load(open(r"C:\VassalSoJ\stair_evidence.json", encoding="utf-8"))}
    rows = []
    # every hexside terrain.json currently calls a staircase
    for sk, rs in terrain["sides"].items():
        if not rs.get("staircase"):
            continue
        adj = adjacency(sk)
        e = ev.get(sk)
        rec = {"side_key": sk, "encoded": True, "adjacent": adj,
               "was_inferred": rs.get("inferred"),
               "frac": e["frac"] if e else None,
               "elev": e["elev"] if e else None, "elev_t": e["elev_t"] if e else None,
               "ground": e["ground"] if e else None, "dir": e["dir"] if e else None}
        if not adj:
            rec["verdict"] = "NOT-A-HEXSIDE"
            a, b = sk.split("|")
            rec["note"] = ("keys %s|%s name two hexes that do not share a hexside (%s / %s) — "
                           "inert data, the gate can never read it"
                           % (a, b, name_of(int(a[:2]), int(a[2:])), name_of(int(b[:2]), int(b[2:]))))
        else:
            rec["verdict"] = VERDICT.get("%s:%s" % (rec["elev"], rec["dir"]), "UNREVIEWED")
        if rec["elev"] in OUT_OF_SCOPE:
            rec["scope"] = "outside-Gallus"
        elif rec["elev"] in SCOPE_DISPUTED:
            rec["scope"] = "scope-disputed"
        else:
            rec["scope"] = "Gallus"
        rows.append(rec)
    # newly found, not encoded
    for key, v in VERDICT.items():
        if v != "CONFIRMED-NEW":
            continue
        hexname, d = key.split(":")
        for sk, e in ev.items():
            if e["elev"] == hexname and e["dir"] == d:
                rows.append({"side_key": sk, "encoded": False, "adjacent": True,
                             "was_inferred": None, "frac": e["frac"], "elev": e["elev"],
                             "elev_t": e["elev_t"], "ground": e["ground"], "dir": e["dir"],
                             "verdict": "CONFIRMED-NEW", "scope": "Gallus"})
    counts = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    doc = {
        "provenance": {
            "phase": "PREP-3 (2026-08-09) — art-confirmation of the printed Staircase hexsides",
            "map": "extracted/images/SoJ_map.jpg 4051x5656 (~82 dpi; the only scan we hold)",
            "grid": "ingest fit x=71.0749*L+207.60, y=82.2902*(N+L/2)-1840.52; registration "
                    "re-verified this pass against the printed hex lines (median offset "
                    "+1,+3 px over 5 windows, 0.66-0.90 dark-line hit)",
            "symbol": "no Staircase entry exists in the printed TERRAIN KEY or in the TEC's "
                      "terrain list; the symbol is known from the module's own Stairway 1-6.png "
                      "markers, whose bar bboxes register on the six hexside midpoints of a "
                      "map-scale hex (NE +35,-21 vs geometric +35.5,-20.6, etc.)",
            "method": "structure-palette pixels lying inside an adjacent GROUND hex within a "
                      "15 px disc 0.32 of the way into that hex ('frac'); then a by-eye pass "
                      "over per-strongpoint contact sheets",
            "tools": ["ingest/stair_evidence.py", "ingest/stair_sheets.py",
                      "ingest/render_hex_crop.py", "ingest/grid_register.py"],
            "evidence_pack": r"Desktop\SoJ_PREP3 (sheets/, panels/, calibration)",
            "verdict_counts": counts,
        },
        "verdict_legend": {
            "CONFIRMED": "stair bar plainly visible crossing this hexside on the printed map",
            "CONFIRMED-NEW": "visible bar on a hexside terrain.json does NOT currently encode",
            "AMBIGUOUS": "something is present but cannot be separated from wall art / ring bleed",
            "ABSENT": "no printed evidence at all at the resolution available",
            "CONTAMINATED": "the neighbouring ground hex carries structure or road art, so the "
                            "score is meaningless there (unverified-terrain hex)",
            "NOT-A-HEXSIDE": "the two hexes named by the key are not adjacent",
        },
        "hexsides": sorted(rows, key=lambda r: (r["verdict"], r["elev"] or "", r["dir"] or "")),
    }
    json.dump(doc, open(OUT, "w"), indent=1)
    print("wrote", OUT)
    for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
        print("  %-16s %d" % (k, v))


if __name__ == "__main__":
    main()
