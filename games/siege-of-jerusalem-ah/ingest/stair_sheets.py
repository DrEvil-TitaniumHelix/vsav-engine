"""SoJ support tool — per-strongpoint contact sheets for art-confirming Staircases.

Six hexes per sheet.  Each tile: the printed map around one Elevated hex at zoom, with the
hex grid, the six hexside labels, the currently-encoded staircase marks, the per-hexside
evidence score, and the protrusion highlight (structure-palette pixels that lie inside an
adjacent Ground hex — the printed staircase is the only art that does that).

    python stair_sheets.py encoded      # every hex that currently carries a staircase
    python stair_sheets.py new          # unencoded hexsides above the ground-truth threshold
    python stair_sheets.py hexes P33 S30 ...
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_hex_crop import (MAP, TERRAIN, SX, SY, DX, DY, centre_row, corners, key_of,
                             name_of, neighbours, parse_name, side_midpoints, SIDES)
from stair_scan import ELEVATED, GROUND

OUT = r"C:\Users\fisch\Desktop\SoJ_PREP3\sheets"
ZOOM = 2.6
RAD = 1


def highlight(a, terrain, x0, y0):
    h, w, _ = a.shape
    yy, xx = np.mgrid[0:h, 0:w]
    mx = xx + x0
    my = yy + y0
    L = np.round((mx - 207.60) / DX).astype(int)
    N = np.round((my + 1840.52) / DY - L / 2.0).astype(int)
    row = N + L // 2
    keys = np.char.add(np.char.zfill(L.astype(str), 2), np.char.zfill(row.astype(str), 2))
    lut = {k: (v["t"] in ("clear", "slope")) for k, v in terrain["hexes"].items()}
    ground = np.array([lut.get(k, False) for k in keys.ravel()]).reshape(h, w)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    lum = a.mean(axis=-1)
    struct = ((r - b) > -12) & ((r - b) < 45) & (lum > 85) & (lum < 205) & ((b - r) < 15)
    m = ground & struct
    out = a.copy()
    out[m] = out[m] * 0.4 + np.array([0, 255, 0]) * 0.6
    return out


def tile(img, terrain, ev, name):
    L, N = parse_name(name)
    row = N + L // 2
    cx, cy = centre_row(L, row)
    hw = SX * (1 + 2 * RAD) * 0.92
    hh = SY * (1 + 2 * RAD) * 0.92
    box = (int(cx - hw), int(cy - hh), int(cx + hw), int(cy + hh))
    a = np.asarray(img.crop(box).convert("RGB")).astype(np.float32)
    a = highlight(a, terrain, box[0], box[1])
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    im = im.resize((int((box[2] - box[0]) * ZOOM), int((box[3] - box[1]) * ZOOM)), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype("arial.ttf", 15)
        small = ImageFont.truetype("arial.ttf", 13)
    except Exception:
        font = small = ImageFont.load_default()

    def T(x, y):
        return ((x - box[0]) * ZOOM, (y - box[1]) * ZOOM)

    for dl in range(-RAD - 1, RAD + 2):
        for dr in range(-RAD - 1, RAD + 2):
            LL, rr = L + dl, row + dr
            ncx, ncy = centre_row(LL, rr)
            if not (box[0] - SX < ncx < box[2] + SX and box[1] - SY < ncy < box[3] + SY):
                continue
            k = "%02d%02d" % (LL, rr)
            t = terrain["hexes"].get(k, {}).get("t", "?")
            self_ = (LL == L and rr == row)
            d.polygon([T(*q) for q in corners(ncx, ncy)],
                      outline=(255, 0, 0) if self_ else (0, 170, 255))
            px, py = T(ncx, ncy)
            d.text((px - 22, py - 8), "%s\n%s" % (name_of(LL, rr), t), fill=(255, 255, 0),
                   font=small, stroke_width=3, stroke_fill=(0, 0, 0))
    k = "%02d%02d" % (L, row)
    mids = side_midpoints(cx, cy)
    nb = neighbours(L, row)
    for s in SIDES:
        nL, nrow = nb[s]
        sk = "|".join(sorted([k, "%02d%02d" % (nL, nrow)]))
        a_, b_, m_ = mids[s]
        rs = terrain["sides"].get(sk, {})
        e = ev.get(sk)
        if rs.get("staircase"):
            d.line([T(*a_), T(*b_)],
                   fill=(0, 255, 0) if rs.get("inferred") is False else (255, 0, 255), width=5)
        if rs.get("entrance"):
            d.line([T(*a_), T(*b_)], fill=(255, 255, 0), width=4)
        ncx, ncy = centre_row(nL, nrow)
        tx, ty = T(m_[0] + (ncx - m_[0]) * 0.40, m_[1] + (ncy - m_[1]) * 0.40)
        lab = s + (" %02d" % round(e["frac"] * 100) if e else "")
        d.text((tx - 16, ty - 8), lab, fill=(255, 255, 255), font=font,
               stroke_width=3, stroke_fill=(0, 0, 0))
    return im


def sheets(names, tag):
    terrain = json.load(open(TERRAIN, encoding="utf-8"))
    ev = {r["side_key"]: r for r in
          json.load(open(r"C:\VassalSoJ\stair_evidence.json", encoding="utf-8"))}
    img = Image.open(MAP)
    os.makedirs(OUT, exist_ok=True)
    try:
        big = ImageFont.truetype("arial.ttf", 20)
    except Exception:
        big = ImageFont.load_default()
    per = 6
    paths = []
    for i in range(0, len(names), per):
        chunk = names[i:i + per]
        tiles = [tile(img, terrain, ev, n) for n in chunk]
        tw, th = tiles[0].size
        cols = 3
        rows_n = (len(tiles) + cols - 1) // cols
        sh = Image.new("RGB", (cols * (tw + 10) + 10, rows_n * (th + 34) + 36), (20, 20, 20))
        d = ImageDraw.Draw(sh)
        d.text((10, 8), "%s  sheet %d — GREEN line = art-confirmed stair, MAGENTA = inferred, "
                        "YELLOW = gate entrance; green tint = structure art protruding into a Ground hex"
               % (tag, i // per + 1), fill=(255, 255, 255), font=big)
        for j, (n, t) in enumerate(zip(chunk, tiles)):
            r, c = divmod(j, cols)
            x = 10 + c * (tw + 10)
            y = 36 + r * (th + 34)
            sh.paste(t, (x, y))
            d.text((x, y + th + 4), n, fill=(120, 255, 120), font=big)
        p = os.path.join(OUT, "sheet_%s_%d.png" % (tag, i // per + 1))
        sh.save(p)
        paths.append(p)
        print(p)
    return paths


def main():
    terrain = json.load(open(TERRAIN, encoding="utf-8"))
    ev = json.load(open(r"C:\VassalSoJ\stair_evidence.json", encoding="utf-8"))
    cmd = sys.argv[1] if len(sys.argv) > 1 else "encoded"
    if cmd == "encoded":
        names = []
        for sk, rs in terrain["sides"].items():
            if not rs.get("staircase"):
                continue
            for part in sk.split("|"):
                L, rr = int(part[:2]), int(part[2:])
                t = terrain["hexes"].get(part, {}).get("t")
                if t in ELEVATED:
                    n = name_of(L, rr)
                    if n not in names:
                        names.append(n)
        names.sort(key=lambda n: (parse_name(n)[0], parse_name(n)[1]))
        sheets(names, "encoded")
    elif cmd == "new":
        thr = float(sys.argv[2]) if len(sys.argv) > 2 else 0.06
        names = []
        for r in ev:
            if r["encoded"] or r["frac"] < thr:
                continue
            if r["elev"] not in names:
                names.append(r["elev"])
        names.sort(key=lambda n: (parse_name(n)[0], parse_name(n)[1]))
        print("hexes:", len(names))
        sheets(names, "new")
    else:
        sheets(sys.argv[2:], "hexes")


if __name__ == "__main__":
    main()
