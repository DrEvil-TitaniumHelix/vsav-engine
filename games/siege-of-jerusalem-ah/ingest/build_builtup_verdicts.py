"""SoJ support tool — PREP-4: turn builtup_scan.py measurements into per-hex verdicts.

Scope = the Gallus playable area, recomputed here read-only exactly as engine/soj.py
_compute_playable does it (flood from the outside seed, barred by Elevated hexes and the
New City, rows > row_max excluded) so the verdict set matches what the gate can reach.

Bands (calibrated on the printed TERRAIN KEY swatches and on the bimodal coverage
distribution of the New City — see BUILTUP_VERIFIED.md):

    struct >= HI      BUILT-UP        art fills the hex to its hexsides
    struct <= LO      CLEAR           bare tan ground
    LO < struct < HI  ADJUDICATE      partial fill; decided by eye off a rendered crop

Edifice (2.13 "dark gray background") is a second, independent test applied to hexes that
are already Built-up: the background is dark AND no open tan ground is left in the hex.

    python build_builtup_verdicts.py                 # verdict table + disagreements
    python build_builtup_verdicts.py --json OUT.json # write the evidence file

The verdict file is EVIDENCE, not terrain.json — nothing here writes game data.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_hex_crop import TERRAIN, centre, parse_name, key_of

SCAN = r"C:\VassalSoJ\builtup_scan.json"
SCEN = os.path.join(os.path.dirname(TERRAIN), "scenario_gallus.json")

HI, LO = 0.45, 0.15
# Edifice test (2.13 "dark gray background"): the BACKGROUND is dark and there is no open
# tan ground left in the hex.  Measured on the printed key swatches and on the map's own
# large structures: Edifice LL40/NN38/MM40 = dark .60-.76 with tan .000-.001; the darkest
# Built-up hexes (LL20 .468 / I45 .528 / J39 .504) all keep tan .16-.22 — grey buildings
# standing ON tan ground.  Two conditions, not one; darkness alone does not separate them.
DARK_HI, TAN_MAX = 0.55, 0.05
ELEVATED = {"wall", "north_wall", "gate_wall", "gate", "gate_north_wall",
            "fort", "fortress", "bastion", "bridge"}

# Verdicts for the ADJUDICATE band, read off rendered crops this pass.  The band is where
# coverage alone cannot tell a building drawn INSIDE the hex from a neighbour's building
# overlapping the hexside; the eye can.  Sheets: Desktop\SoJ_PREP4\band_newcity.png,
# band_zoom.png (see BUILTUP_VERIFIED.md sec 4).
HAND = {
    "NN19": ("builtup", "block drawn inside the hex, NW half; confirms the shipped type"),
    "X30":  ("builtup", "block drawn inside the hex, SE half; confirms the shipped type"),
    "K40":  ("builtup", "block fills the SW half, drawn inside the hex"),
    "I40":  ("builtup", "block occupies the NE third, drawn inside the hex; road crosses SW"),
    "BB23": ("clear", "only CC23's block overlapping the shared hexside; interior is road+tan"),
    "O44":  ("clear", "only P44/O45 art overlapping the E hexsides"),
    "Z25":  ("clear", "only Y26/Z26 art overlapping the S hexsides; interior is road+tan"),
    "NN28": ("clear", "only OO28's block overlapping the SE hexside"),
    "Q43":  ("clear", "sliver of P43's block over the W hexside"),
}


# The printed TERRAIN KEY panel and its drop-shadow are drawn ON TOP of the hexfield in the
# NW corner; those pixels are ink, not terrain, and the scan reads them as very dark
# structure.  Same for the map's dark border band.  Hexes whose centre falls in this box are
# reported `offmap` instead of being classified.  All of them are outside the Gallus
# battlefield, so this affects nothing but tidiness of the campaign-scope table.
KEY_PANEL_BOX = (215, 200, 520, 900)     # x0, y0, x1, y1 in full-map pixels
OFFMAP_EXTRA = {"WW2"}                   # dark Mount Scopus border shading + label


def neighbours(h):
    L, N = int(h[:2]), int(h[2:])
    odd = L % 2
    return ["%02d%02d" % (l, r) for l, r in
            [(L, N - 1), (L, N + 1), (L + 1, N - 1 + odd), (L + 1, N + odd),
             (L - 1, N - 1 + odd), (L - 1, N + odd)]]


def playable(terrain, scen):
    cfg = scen["deployment"]["playable_area"]
    hexes = terrain["hexes"]
    name_hex = {v["name"]: k for k, v in hexes.items()}
    new_city = set(terrain["areas"]["new_city"])
    barrier = {h for h, v in hexes.items() if v["t"] in ELEVATED}
    row_max = int(cfg["row_max"])
    seen, stack = set(), [name_hex[cfg["outside_seed"]]]
    while stack:
        h = stack.pop()
        if h in seen or h in barrier or h in new_city or h not in hexes:
            continue
        if int(h[2:]) > row_max:
            continue
        seen.add(h)
        stack.extend(n for n in neighbours(h) if n in hexes)
    return seen | new_city | barrier, seen, new_city


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--hi", type=float, default=HI)
    ap.add_argument("--lo", type=float, default=LO)
    args = ap.parse_args()

    terrain = json.load(open(TERRAIN, encoding="utf-8"))
    scen = json.load(open(SCEN, encoding="utf-8"))
    scan = json.load(open(SCAN, encoding="utf-8"))
    hexes = terrain["hexes"]
    play, outside, new_city = playable(terrain, scen)

    rows = []
    for h in sorted(play):
        rec = hexes.get(h)
        if not rec:
            continue
        nm = rec["name"]
        m = scan.get(nm)
        if not m:
            continue
        cur = rec["t"]
        if cur in ELEVATED or cur == "slope":
            continue                       # ground/wall classes settled by other passes
        s, d = m["struct"], m["dark"]
        L, N = parse_name(nm)
        px, py = centre(L, N)
        if (nm in OFFMAP_EXTRA or
                (KEY_PANEL_BOX[0] <= px <= KEY_PANEL_BOX[2]
                 and KEY_PANEL_BOX[1] <= py <= KEY_PANEL_BOX[3])):
            verdict, how = "offmap", "printed key panel / map border, not terrain"
        elif nm in HAND:
            verdict, how = HAND[nm][0], "hand:" + HAND[nm][1]
        elif s >= args.hi:
            verdict, how = "builtup", "auto"
        elif s <= args.lo:
            verdict, how = "clear", "auto"
        else:
            verdict, how = "adjudicate", "band"
        if verdict == "builtup" and d >= DARK_HI and m["tan"] <= TAN_MAX:
            verdict = "edifice"
        rows.append({"hex": nm, "key": h, "zone": "new_city" if h in new_city else "outside",
                     "current": cur, "verdict": verdict, "how": how,
                     "struct": s, "dark": d, "tan": m["tan"], "v_med": m["v_med"]})

    agree = [r for r in rows if r["verdict"] == r["current"]]
    disag = [r for r in rows if r["verdict"] not in (r["current"], "adjudicate", "offmap")]
    band = [r for r in rows if r["verdict"] == "adjudicate"]

    print("playable hexes scanned: %d  (new_city %d / outside %d)" % (
        len(rows), sum(1 for r in rows if r["zone"] == "new_city"),
        sum(1 for r in rows if r["zone"] == "outside")))
    print("agree with terrain.json: %d   disagree: %d   adjudicate band: %d"
          % (len(agree), len(disag), len(band)))

    for zone in ("new_city", "outside"):
        z = [r for r in disag if r["zone"] == zone]
        z.sort(key=lambda r: -r["struct"])
        print("\n--- DISAGREEMENTS in %s (%d) ---" % (zone, len(z)))
        for r in z:
            print("  %-6s %-8s -> %-8s struct=%.3f dark=%.3f v=%5.1f" % (
                r["hex"], r["current"], r["verdict"], r["struct"], r["dark"], r["v_med"]))

    band.sort(key=lambda r: -r["struct"])
    print("\n--- ADJUDICATE BAND (%.2f < struct < %.2f), %d ---" % (args.lo, args.hi, len(band)))
    for r in band:
        print("  %-6s %-8s struct=%.3f dark=%.3f v=%5.1f  zone=%s" % (
            r["hex"], r["current"], r["struct"], r["dark"], r["v_med"], r["zone"]))

    nb = sum(1 for r in rows if r["verdict"] in ("builtup", "edifice"))
    print("\nBuilt-up (incl. Edifice) hexes in the Gallus playable area: %d "
          "(terrain.json currently: %d)   Roman victory needs 10."
          % (nb, sum(1 for r in rows if r["current"] == "builtup")))

    if args.json:
        json.dump({"thresholds": {"hi": args.hi, "lo": args.lo, "dark_hi": DARK_HI},
                   "rows": rows}, open(args.json, "w"), indent=1)
        print("wrote", args.json)


if __name__ == "__main__":
    main()
