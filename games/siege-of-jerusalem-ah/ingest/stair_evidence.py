"""SoJ support tool — printed-staircase EVIDENCE score for every Elevated<->Ground hexside.

Signal: a Staircase is the only fortification art that protrudes across a hexside into an
open Ground hex.  So for each candidate hexside we count structure-palette pixels lying
INSIDE the ground hex within a disc just past the hexside, and normalise by the disc area.

The blue / orange / red strongpoint rings are excluded by colour, so a plain wall or
bastion edge scores ~0 while a staircase scores high.  Validated against the four
hand-confirmed staircases from ingest session 1 (P33, S30, Y24, PP23).

    python stair_evidence.py            -> stair_evidence.json + ranked report
    python stair_evidence.py sheets     -> contact sheets of the ranked hexsides
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_hex_crop import (MAP, TERRAIN, SX, SY, DX, DY, centre_row, name_of,
                             neighbours, side_midpoints, SIDES)
from stair_scan import ELEVATED, GROUND

R_DISC = 15.0        # radius of the evidence disc, px
DEPTH = 0.32         # how far into the ground hex the disc centre sits (0 = on the hexside)


def struct_mask(a):
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    lum = a.mean(axis=-1)
    return ((r - b) > -12) & ((r - b) < 45) & (lum > 85) & (lum < 205) & ((b - r) < 15)


def build():
    terrain = json.load(open(TERRAIN, encoding="utf-8"))
    hexes, sides = terrain["hexes"], terrain["sides"]
    img = np.asarray(Image.open(MAP).convert("RGB")).astype(np.float32)
    H, W, _ = img.shape
    mask = struct_mask(img)

    # per-pixel hex ownership, so the disc only counts pixels really inside the ground hex
    yy, xx = np.mgrid[0:H:1, 0:W:1]

    def hex_key_at(px, py):
        L = np.round((px - 207.60) / DX).astype(int)
        N = np.round((py + 1840.52) / DY - L / 2.0).astype(int)
        return L, N + L // 2

    rows = []
    for k, rec in hexes.items():
        if rec["t"] not in ELEVATED:
            continue
        L, row = int(k[:2]), int(k[2:])
        cx, cy = centre_row(L, row)
        mids = side_midpoints(cx, cy)
        nb = neighbours(L, row)
        for s in SIDES:
            nL, nrow = nb[s]
            nk = "%02d%02d" % (nL, nrow)
            nrec = hexes.get(nk)
            if not nrec or nrec["t"] not in GROUND:
                continue
            sk = "|".join(sorted([k, nk]))
            _, _, m = mids[s]
            ncx, ncy = centre_row(nL, nrow)
            dx_, dy_ = m[0] + (ncx - m[0]) * DEPTH, m[1] + (ncy - m[1]) * DEPTH
            x0 = int(dx_ - R_DISC); x1 = int(dx_ + R_DISC) + 1
            y0 = int(dy_ - R_DISC); y1 = int(dy_ + R_DISC) + 1
            if x0 < 0 or y0 < 0 or x1 > W or y1 > H:
                continue
            sub = mask[y0:y1, x0:x1]
            gy, gx = np.mgrid[y0:y1, x0:x1]
            inside = ((gx - dx_) ** 2 + (gy - dy_) ** 2) <= R_DISC ** 2
            LL, rr = hex_key_at(gx, gy)
            own = (LL == nL) & (rr == nrow)
            sel = inside & own
            if sel.sum() < 40:
                continue
            frac = float((sub & sel).sum()) / float(sel.sum())
            rs = sides.get(sk, {})
            rows.append({"side_key": sk, "elev": name_of(L, row), "elev_t": rec["t"],
                         "ground": name_of(nL, nrow), "ground_t": nrec["t"], "dir": s,
                         "frac": round(frac, 4), "npx": int((sub & sel).sum()),
                         "disc_px": int(sel.sum()),
                         "encoded": bool(rs.get("staircase")),
                         "inferred": rs.get("inferred")})
    rows.sort(key=lambda r: -r["frac"])
    return rows, terrain


def main():
    rows, terrain = build()
    json.dump(rows, open(r"C:\VassalSoJ\stair_evidence.json", "w"), indent=1)
    sides = terrain["sides"]
    art = [r for r in rows if r["encoded"] and r["inferred"] is False]
    print("candidate hexsides scored:", len(rows))
    print("\n-- ground truth: the 8 hand-confirmed staircase hexsides --")
    for r in rows:
        if r in art:
            print(" rank %3d  %-5s->%-5s %-3s frac=%.3f (%d/%d px)"
                  % (rows.index(r) + 1, r["elev"], r["ground"], r["dir"],
                     r["frac"], r["npx"], r["disc_px"]))
    thr = min(r["frac"] for r in art)
    print("\nlowest ground-truth frac = %.3f" % thr)
    above = [r for r in rows if r["frac"] >= thr]
    print("hexsides at or above that threshold: %d  (encoded %d / new %d)"
          % (len(above), sum(1 for r in above if r["encoded"]),
             sum(1 for r in above if not r["encoded"])))
    print("\n-- top 60 --")
    for i, r in enumerate(rows[:60]):
        st = "ART" if (r["encoded"] and r["inferred"] is False) else ("ENC" if r["encoded"] else "new")
        print(" %3d %-5s->%-5s %-3s %-16s frac=%.3f %-3s" %
              (i + 1, r["elev"], r["ground"], r["dir"], r["elev_t"], r["frac"], st))
    print("\n-- encoded hexsides ranked (worst last) --")
    enc = [(i + 1, r) for i, r in enumerate(rows) if r["encoded"]]
    for i, r in enc:
        st = "ART" if r["inferred"] is False else "inf"
        print(" %3d %-5s->%-5s %-3s frac=%.3f %s" %
              (i, r["elev"], r["ground"], r["dir"], r["frac"], st))


if __name__ == "__main__":
    main()
