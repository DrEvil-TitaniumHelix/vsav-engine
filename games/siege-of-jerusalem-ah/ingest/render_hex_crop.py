"""SoJ support tool — render a labeled zoom crop of the printed map around a hex.

Usage:
    python render_hex_crop.py P33 [S30 Y24 ...] [--zoom 3] [--radius 1] [--out DIR]
    python render_hex_crop.py --grid P33,Q33,R33 --cols 3      (contact sheet)

Draws the hex outline (flat-top), labels the six hexsides (N/NE/SE/S/SW/NW) and
prints the neighbour hex name for each side, so hexside features (staircases,
gate entrances, crests) can be read off the art unambiguously.

Grid fit (validated in ingest session 1, see INGEST_NOTES.md):
    x = 71.0749*L + 207.60          L = column-letter index (A=1 .. Z=26, AA=27 ..)
    y = 82.2902*(N + L/2) - 1840.52 N = diagonal number
Hex key used by terrain.json = "%02d%02d" % (L, N + L//2).
"""
import argparse
import json
import os
import re

from PIL import Image, ImageDraw, ImageFont

MAP = r"C:\VassalSoJ\extracted\images\SoJ_map.jpg"
TERRAIN = r"C:\VassalArnhem\games\siege-of-jerusalem-ah\terrain.json"

DX = 71.0749
X0 = 207.60
DY = 82.2902
Y0 = -1840.52
SX = DX * 2.0 / 3.0          # centre -> E/W corner
SY = DY / 2.0                # centre -> flat top/bottom

SIDES = ["N", "NE", "SE", "S", "SW", "NW"]


def col_index(letters):
    letters = letters.upper()
    if len(letters) == 1:
        return ord(letters) - 64
    return 26 + (ord(letters[0]) - 64)


def col_letters(L):
    if L <= 26:
        return chr(64 + L)
    return chr(64 + L - 26) * 2


def parse_name(name):
    m = re.match(r"^([A-Za-z]+)(\d+)$", name.strip())
    if not m:
        raise ValueError("bad hex name %r" % name)
    L = col_index(m.group(1))
    N = int(m.group(2))
    return L, N


def key_of(L, N):
    return "%02d%02d" % (L, N + L // 2)


def name_of(L, row):
    return "%s%d" % (col_letters(L), row - L // 2)


def centre(L, N):
    return DX * L + X0, DY * (N + L / 2.0) + Y0


def centre_row(L, row):
    return centre(L, row - L // 2)


def corners(cx, cy):
    return [(cx + SX, cy), (cx + SX / 2, cy - SY), (cx - SX / 2, cy - SY),
            (cx - SX, cy), (cx - SX / 2, cy + SY), (cx + SX / 2, cy + SY)]


def side_midpoints(cx, cy):
    """side -> ((x1,y1),(x2,y2), (mx,my))"""
    c = corners(cx, cy)
    pairs = {"NE": (c[0], c[1]), "N": (c[1], c[2]), "NW": (c[2], c[3]),
             "SW": (c[3], c[4]), "S": (c[4], c[5]), "SE": (c[5], c[0])}
    out = {}
    for k, (a, b) in pairs.items():
        out[k] = (a, b, ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0))
    return out


def neighbours(L, row):
    """side -> (L,row) of the neighbouring hex (flat-top, odd columns shifted down)."""
    odd = L % 2
    return {
        "N": (L, row - 1),
        "S": (L, row + 1),
        "NE": (L + 1, row - 1 + odd),
        "SE": (L + 1, row + odd),
        "NW": (L - 1, row - 1 + odd),
        "SW": (L - 1, row + odd),
    }


def load_terrain():
    try:
        return json.load(open(TERRAIN, encoding="utf-8"))
    except Exception:
        return {"hexes": {}, "sides": {}}


def side_key(a_key, b_key):
    return "|".join(sorted([a_key, b_key]))


def render(name, zoom=3.0, radius=1, out_dir=".", img=None, terrain=None,
           annotate=True, suffix=""):
    img = img or Image.open(MAP)
    terrain = terrain if terrain is not None else load_terrain()
    L, N = parse_name(name)
    row = N + L // 2
    cx, cy = centre(L, N)
    half_w = SX * (1 + 2 * radius)
    half_h = SY * (1 + 2 * radius)
    box = (int(cx - half_w), int(cy - half_h), int(cx + half_w), int(cy + half_h))
    crop = img.crop(box).resize(
        (int((box[2] - box[0]) * zoom), int((box[3] - box[1]) * zoom)), Image.LANCZOS)
    if annotate:
        d = ImageDraw.Draw(crop)
        try:
            font = ImageFont.truetype("arial.ttf", int(13 * max(1.0, zoom / 2)))
        except Exception:
            font = ImageFont.load_default()

        def to_crop(p):
            return ((p[0] - box[0]) * zoom, (p[1] - box[1]) * zoom)

        nb = neighbours(L, row)
        for dl in range(-radius, radius + 1):
            for dr in range(-radius - 1, radius + 2):
                LL, rr = L + dl, row + dr
                if LL < 1:
                    continue
                ncx, ncy = centre_row(LL, rr)
                if not (box[0] - SX < ncx < box[2] + SX and box[1] - SY < ncy < box[3] + SY):
                    continue
                pts = [to_crop(p) for p in corners(ncx, ncy)]
                is_self = (LL == L and rr == row)
                d.polygon(pts, outline=(255, 0, 0) if is_self else (0, 160, 255))
                if is_self:
                    d.polygon([(p[0] + 1, p[1] + 1) for p in pts], outline=(255, 0, 0))
                nm = name_of(LL, rr)
                t = terrain["hexes"].get(key_of(LL, rr - LL // 2), {}).get("t", "?")
                d.text((to_crop((ncx, ncy))[0] - 22 * zoom / 2, to_crop((ncx, ncy))[1] - 8 * zoom / 2),
                       "%s\n%s" % (nm, t), fill=(255, 255, 0), font=font,
                       stroke_width=2, stroke_fill=(0, 0, 0))
        # hexside labels for the focus hex
        mids = side_midpoints(cx, cy)
        for s in SIDES:
            a, b, m = mids[s]
            nL, nr = nb[s]
            sk = side_key(key_of(L, N), key_of(nL, nr - nL // 2))
            rec = terrain["sides"].get(sk)
            tag = s
            if rec:
                if rec.get("staircase"):
                    tag += "*stair%s" % ("?" if rec.get("inferred") else "!")
                if rec.get("entrance"):
                    tag += "*entr"
            px, py = to_crop(m)
            # nudge label toward the hex centre so it sits on the side, not on art
            ccx, ccy = to_crop((cx, cy))
            px = px + (ccx - px) * 0.28
            py = py + (ccy - py) * 0.28
            d.text((px - 14, py - 7), tag, fill=(0, 255, 0), font=font,
                   stroke_width=2, stroke_fill=(0, 0, 0))
        d.text((6, 6), "%s  (L=%d N=%d key=%s)  t=%s" % (
            name, L, N, key_of(L, N),
            terrain["hexes"].get(key_of(L, N), {}).get("t", "?")),
            fill=(255, 255, 255), font=font, stroke_width=3, stroke_fill=(0, 0, 0))
    path = os.path.join(out_dir, "hex_%s%s.png" % (name.upper(), suffix))
    crop.save(path)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("hexes", nargs="*")
    ap.add_argument("--zoom", type=float, default=3.0)
    ap.add_argument("--radius", type=int, default=1)
    ap.add_argument("--out", default=r"C:\Users\fisch\Desktop\SoJ_PREP3")
    ap.add_argument("--raw", action="store_true", help="no overlay annotation")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    img = Image.open(MAP)
    terrain = load_terrain()
    for h in args.hexes:
        p = render(h, zoom=args.zoom, radius=args.radius, out_dir=args.out,
                   img=img, terrain=terrain, annotate=not args.raw,
                   suffix="_raw" if args.raw else "")
        print(p)


if __name__ == "__main__":
    main()
