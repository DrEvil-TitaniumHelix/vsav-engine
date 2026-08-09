"""SoJ support tool — PREP-4: contact sheets for hand-adjudicating Built-up coverage.

Each cell is the hex plus a one-hex margin, with the hex itself outlined in red and its
neighbours in blue, captioned with the measured structure coverage.  Made for reading the
printed art directly: "does the building block fill this hex to its own hexsides?"

    python builtup_sheets.py --hexes X30,I40,BB23 --out DIR
    python builtup_sheets.py --band            # the whole adjudicate band, new_city first
    python builtup_sheets.py --mask            # magenta overlay of the structure mask
    python builtup_sheets.py --overview        # whole battlefield, verdicts colour-coded
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_hex_crop import (MAP, TERRAIN, DX, DY, SX, SY, centre, centre_row,
                             corners, key_of, name_of, parse_name)
from builtup_scan import classes

SCAN = r"C:\VassalSoJ\builtup_scan.json"


def cell(img, scan, terrain, nm, zoom, size, mask):
    L, N = parse_name(nm)
    row = N + L // 2
    cx, cy = centre(L, N)
    box = (int(cx - SX * 2.1), int(cy - SY * 2.4), int(cx + SX * 2.1), int(cy + SY * 2.4))
    crop = img.crop(box).convert("RGB")
    if mask:
        A = np.asarray(crop).astype(np.float32)
        v, warm, struct, tan, dark = classes(A.reshape(-1, 3))
        st = struct.reshape(A.shape[:2])
        out = np.asarray(crop).copy()
        out[st] = (out[st] * 0.45 + np.array([255, 0, 255]) * 0.55).astype("uint8")
        crop = Image.fromarray(out)
    crop = crop.resize((int(crop.width * zoom), int(crop.height * zoom)), Image.LANCZOS)
    d = ImageDraw.Draw(crop)
    try:
        font = ImageFont.truetype("arial.ttf", 15)
    except Exception:
        font = ImageFont.load_default()
    for dl in range(-2, 3):
        for dr in range(-3, 4):
            LL, rr = L + dl, row + dr
            if LL < 1:
                continue
            ncx, ncy = centre_row(LL, rr)
            if not (box[0] - SX < ncx < box[2] + SX and box[1] - SY < ncy < box[3] + SY):
                continue
            pts = [((p[0] - box[0]) * zoom, (p[1] - box[1]) * zoom) for p in corners(ncx, ncy)]
            me = (LL == L and rr == row)
            d.polygon(pts, outline=(255, 40, 40) if me else (60, 200, 255))
            if me:
                d.polygon([(p[0] + 1, p[1] + 1) for p in pts], outline=(255, 40, 40))
            n2 = name_of(LL, rr)
            m2 = scan.get(n2)
            d.text(((ncx - box[0]) * zoom - 22, (ncy - box[1]) * zoom - 8),
                   "%s\n%.2f" % (n2, m2["struct"] if m2 else -1),
                   fill=(255, 255, 0) if not me else (255, 255, 255), font=font,
                   stroke_width=2, stroke_fill=(0, 0, 0))
    m = scan.get(nm, {})
    cap = "%s  t=%s  struct=%.3f dark=%.3f" % (
        nm, terrain["hexes"].get(key_of(L, N), {}).get("t", "?"),
        m.get("struct", -1), m.get("dark", -1))
    d.rectangle([0, 0, crop.width, 22], fill=(0, 0, 0))
    d.text((5, 3), cap, fill=(255, 255, 255), font=font)
    return crop.resize(size, Image.LANCZOS) if size else crop


VERDICT_COLOUR = {          # RGB + alpha used for the overview wash
    "builtup": (255, 0, 255),      # magenta  = Built-up in the new verdict
    "edifice": (0, 90, 255),       # blue     = Edifice (dark-gray background)
    "adjudicate": (255, 200, 0),   # amber    = coverage band, decided by eye
}


def overview(out, evidence, terrain, zoom=0.55):
    """Whole-battlefield wash: every verdict painted over the printed map, with the hexes
    terrain.json already types builtup outlined in white so the delta is visible."""
    img = Image.open(MAP).convert("RGB")
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    for r in evidence["rows"]:
        col = VERDICT_COLOUR.get(r["verdict"])
        if not col:
            continue
        L, N = parse_name(r["hex"])
        pts = corners(*centre(L, N))
        d.polygon(pts, fill=col + (110,))
        if r["current"] == "builtup":
            d.polygon(pts, outline=(255, 255, 255, 255))
    img = Image.alpha_composite(img.convert("RGBA"), lay).convert("RGB")
    img = img.resize((int(img.width * zoom), int(img.height * zoom)), Image.LANCZOS)
    img.save(out)
    print(out, img.size)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hexes", default="")
    ap.add_argument("--band", action="store_true")
    ap.add_argument("--overview", action="store_true")
    ap.add_argument("--mask", action="store_true")
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--zoom", type=float, default=2.0)
    ap.add_argument("--out", default=r"C:\Users\fisch\Desktop\SoJ_PREP4")
    ap.add_argument("--name", default="sheet.png")
    args = ap.parse_args()

    scan = json.load(open(SCAN, encoding="utf-8"))
    terrain = json.load(open(TERRAIN, encoding="utf-8"))
    os.makedirs(args.out, exist_ok=True)
    if args.overview:
        ev = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "builtup_evidence.json"), encoding="utf-8"))
        overview(os.path.join(args.out, args.name), ev, terrain)
        return
    if args.band:
        names = [n for n, m in sorted(scan.items(), key=lambda kv: -kv[1]["struct"])
                 if 0.15 < m["struct"] < 0.45]
    else:
        names = [h.strip().upper() for h in args.hexes.split(",") if h.strip()]

    os.makedirs(args.out, exist_ok=True)
    img = Image.open(MAP)
    cells = [cell(img, scan, terrain, n, args.zoom, None, args.mask) for n in names]
    if not cells:
        print("nothing to render")
        return
    w, h = cells[0].size
    cols = min(args.cols, len(cells))
    rows = (len(cells) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w, rows * h), (20, 20, 20))
    for i, c in enumerate(cells):
        sheet.paste(c, ((i % cols) * w, (i // cols) * h))
    path = os.path.join(args.out, args.name)
    sheet.save(path)
    print(path, sheet.size, "cells:", len(cells))


if __name__ == "__main__":
    main()
