"""SoJ support tool — PREP-4: Built-up / Edifice / structure-art evidence scan.

Two printed facts drive this tool:

  * 2.13 "Built-up hexes depict terrain with numerous buildings ... Those Built-up hexes
    containing larger structures are *Edifices* and recognized by the DARK GRAY BACKGROUND
    of the hex."
  * The map's own drawing convention (established this pass, see BUILTUP_VERIFIED.md):
    the built-up art is CLIPPED TO HEXSIDES.  A built-up hex is filled with building art to
    its own hexsides; its clear neighbour is bare tan right up to the shared side.  So
    "is this hex Built-up" is a *coverage* question with a hard printed edge, not a
    judgement call about sprawling art.

Per hex it measures, over the hex polygon eroded by `--erode` px (so the printed hexgrid
line and the neighbour's art can never leak in):

    struct    share of the hex that is building/stone art (grey-ish, not the tan ground)
    tan       share that is open tan ground
    dark      share that is dark-gray background (the Edifice signature)
    v_med     median value of the whole hex
    v_struct  median value of the struct pixels  (Edifice art sits on a dark ground)

Calibration anchors are read off the map's own printed TERRAIN KEY swatches (--calib).

    python builtup_scan.py --calib                 # print the printed-key swatch palette
    python builtup_scan.py                         # scan every hex in terrain.json
    python builtup_scan.py --hexes X26,Z25,BB24    # scan named hexes
    python builtup_scan.py --report                # scan + the PREP-4 verdict tables

Writes C:\\VassalSoJ\\builtup_scan.json.
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_hex_crop import (MAP, TERRAIN, DX, DY, SX, SY, centre, corners,
                             key_of, parse_name)

OUT = r"C:\VassalSoJ\builtup_scan.json"

# --- printed TERRAIN KEY swatch centres, full-map pixels (verified visually, see
#     BUILTUP_VERIFIED.md §1; the key panel sits over hexes A26-C32) ---
KEY_SWATCHES = {
    "TempleOuterWall": (262, 266), "Wall": (262, 306), "NorthernWall": (262, 348),
    "Bridge": (262, 390), "Fortress": (262, 431), "Fort": (262, 476),
    "Bastion": (262, 518), "Edifice": (262, 562), "Builtup": (262, 605),
    "Clear": (262, 647), "Road": (262, 688), "Slope": (262, 730),
    "Crest": (262, 775), "Gate": (262, 818),
}

# --- pixel classes (thresholds fixed from the key swatches; see --calib) ---
def classes(px):
    r, g, b = px[:, 0], px[:, 1], px[:, 2]
    v = (r + g + b) / 3.0
    warm = r - b                     # tan ground is strongly warm (~75); stone art is not
    struct = (warm < 48) & (v < 155)
    tan = (warm >= 48) & (v >= 100)
    dark = (warm < 55) & (v < 88)    # Edifice background / deep shadow
    return v, warm, struct, tan, dark


def hex_mask(cx, cy, erode):
    """Boolean mask + pixel coords for the hex polygon eroded by `erode` px."""
    x0, y0 = int(cx - SX) - 2, int(cy - SY) - 2
    w, h = int(2 * SX) + 5, int(2 * SY) + 5
    im = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(im)
    k = 1.0 - erode / min(SX, SY)
    pts = [((p[0] - cx) * k + cx - x0, (p[1] - cy) * k + cy - y0) for p in corners(cx, cy)]
    d.polygon(pts, fill=255)
    m = np.asarray(im) > 0
    ys, xs = np.nonzero(m)
    return xs + x0, ys + y0


def scan_hex(A, cx, cy, erode):
    H, W = A.shape[:2]
    xs, ys = hex_mask(cx, cy, erode)
    ok = (xs >= 0) & (ys >= 0) & (xs < W) & (ys < H)
    if ok.sum() < 100:
        return None
    px = A[ys[ok], xs[ok]].astype(np.float32)
    v, warm, struct, tan, dark = classes(px)
    out = {
        "n": int(px.shape[0]),
        "struct": float(struct.mean()),
        "tan": float(tan.mean()),
        "dark": float(dark.mean()),
        "v_med": float(np.median(v)),
        "warm_med": float(np.median(warm)),
        "v_struct": float(np.median(v[struct])) if struct.sum() > 30 else -1.0,
    }
    return {k: (round(x, 4) if isinstance(x, float) else x) for k, x in out.items()}


def calib(A, erode):
    print("%-16s %7s %7s %7s %7s %7s" % ("KEY SWATCH", "struct", "tan", "dark", "v_med", "v_str"))
    for name, (cx, cy) in KEY_SWATCHES.items():
        # key swatches are drawn at ~1/3 map hex size; sample a disc inside them
        r = 15.0
        yy, xx = np.mgrid[int(cy - r):int(cy + r) + 1, int(cx - r):int(cx + r) + 1]
        m = (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r
        px = A[yy[m], xx[m]].astype(np.float32)
        v, warm, struct, tan, dark = classes(px)
        vs = float(np.median(v[struct])) if struct.sum() > 20 else -1.0
        print("%-16s %7.3f %7.3f %7.3f %7.1f %7.1f" % (
            name, struct.mean(), tan.mean(), dark.mean(), np.median(v), vs))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hexes", default="")
    ap.add_argument("--erode", type=float, default=6.0)
    ap.add_argument("--calib", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    A = np.asarray(Image.open(MAP).convert("RGB"))
    if args.calib:
        calib(A, args.erode)
        return

    terrain = json.load(open(TERRAIN, encoding="utf-8"))
    names = ([h.strip().upper() for h in args.hexes.split(",") if h.strip()]
             if args.hexes else [v["name"] for v in terrain["hexes"].values()])

    res = {}
    for nm in names:
        L, N = parse_name(nm)
        m = scan_hex(A, *centre(L, N), args.erode)
        if m is None:
            continue
        m["t"] = terrain["hexes"].get(key_of(L, N), {}).get("t", "?")
        res[nm] = m
    json.dump(res, open(args.out, "w"), indent=1, sort_keys=True)
    print("wrote %s  (%d hexes)" % (args.out, len(res)))

    if args.report:
        report(res, terrain)
    elif args.hexes:
        print("%-7s %-12s %7s %7s %7s %7s %7s" % ("hex", "type", "struct", "tan", "dark", "v_med", "v_str"))
        for nm in names:
            m = res.get(nm)
            if m:
                print("%-7s %-12s %7.3f %7.3f %7.3f %7.1f %7.1f" % (
                    nm, m["t"], m["struct"], m["tan"], m["dark"], m["v_med"], m["v_struct"]))


def report(res, terrain):
    unc = terrain["provenance"].get("builtup_uncertain", [])
    bu = sorted([n for n, m in res.items() if m["t"] == "builtup"],
                key=lambda n: -res[n]["struct"])
    print("\n--- accepted builtup (%d), by structure coverage ---" % len(bu))
    for n in bu:
        m = res[n]
        print("  %-6s struct=%.3f tan=%.3f dark=%.3f v=%5.1f" % (n, m["struct"], m["tan"], m["dark"], m["v_med"]))
    print("\n--- builtup_uncertain (%d) ---" % len(unc))
    for n in unc:
        m = res.get(n)
        if m:
            print("  %-6s struct=%.3f tan=%.3f dark=%.3f v=%5.1f  (typed %s)" % (
                n, m["struct"], m["tan"], m["dark"], m["v_med"], m["t"]))
    lo = min(res[n]["struct"] for n in bu) if bu else 0
    cand = sorted([(m["struct"], n) for n, m in res.items()
                   if m["t"] == "clear" and m["struct"] >= lo], reverse=True)
    print("\n--- hexes typed clear whose coverage >= the weakest accepted builtup (%.3f): %d ---" % (lo, len(cand)))
    for s, n in cand:
        print("  %-6s struct=%.3f" % (n, s))


if __name__ == "__main__":
    main()
