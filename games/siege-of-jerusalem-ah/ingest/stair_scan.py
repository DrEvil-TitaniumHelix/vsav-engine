"""SoJ support tool — rectified hexside patches + matched-filter score for STAIRCASE art.

Printed staircase art (confirmed against the module's own Stairway 1-6.png markers, which
Rob cut from the map at map scale and which register exactly on the hexside midpoint) is a
brown bar ~40 x 10 px lying PERPENDICULAR to the hexside, centred on it, half in the
Elevated hex and half in the Ground hex.

For every Elevated<->Ground hexside this script builds a rectified patch: the hexside is
rotated to horizontal, the GROUND hex is downward.  A staircase then always looks the same:
a dark vertical bar in the middle of the lower half.  That makes both the numeric score and
the by-eye confirmation uniform across all 462 candidates.

  python stair_scan.py score          -> stair_scan.json, ranked
  python stair_scan.py sheet [N]      -> contact sheets of the top N rectified patches
  python stair_scan.py sheet-encoded  -> contact sheet of every currently-encoded hexside
  python stair_scan.py sheet-keys A|B ...
"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_hex_crop import (MAP, TERRAIN, SX, SY, centre_row, key_of, name_of,
                             neighbours, side_midpoints, SIDES)

ELEVATED = {"wall", "north_wall", "bastion", "fort", "fortress",
            "gate", "gate_wall", "gate_north_wall", "bridge"}
GROUND = {"clear", "builtup", "slope", "edifice", "breach", "court", "road", "ramp"}

PW, PH = 41, 30          # rectified patch: +/-20 along the hexside, -4..+25 into the ground
Y0 = -4

_IMG = None


def img():
    global _IMG
    if _IMG is None:
        _IMG = np.asarray(Image.open(MAP).convert("RGB")).astype(np.float32)
    return _IMG


def sample(px, py):
    """bilinear sample, px/py float arrays"""
    a = img()
    H, W, _ = a.shape
    x0 = np.clip(np.floor(px).astype(int), 0, W - 2)
    y0 = np.clip(np.floor(py).astype(int), 0, H - 2)
    fx = (px - x0)[..., None]
    fy = (py - y0)[..., None]
    return (a[y0, x0] * (1 - fx) * (1 - fy) + a[y0, x0 + 1] * fx * (1 - fy) +
            a[y0 + 1, x0] * (1 - fx) * fy + a[y0 + 1, x0 + 1] * fx * fy)


def rectify(m, u, v):
    xs = np.arange(-(PW // 2), PW // 2 + 1)
    ys = np.arange(Y0, Y0 + PH)
    X, Y = np.meshgrid(xs, ys)
    px = m[0] + u[0] * X + v[0] * Y
    py = m[1] + u[1] * X + v[1] * Y
    return sample(px, py)


def score_patch(p):
    """p: (PH,PW,3) rectified patch. Ground half = rows for Y in 3..22."""
    ys = np.arange(Y0, Y0 + PH)
    xs = np.arange(-(PW // 2), PW // 2 + 1)
    band = (ys >= 3) & (ys <= 22)
    sub = p[band]
    lum = sub.mean(axis=-1)
    centre = np.abs(xs) <= 5
    flank = (np.abs(xs) >= 9) & (np.abs(xs) <= 19)
    c = lum[:, centre]
    f = lum[:, flank]
    contrast = float(f.mean() - c.mean())          # bar is darker than open ground
    # brownness of the centre bar: R>G>B, mid-dark
    cb = sub[:, centre]
    mean_rgb = cb.reshape(-1, 3).mean(axis=0)
    brown = float(mean_rgb[0] - mean_rgb[2])
    # vertical continuity: the bar must be present across most rows of the ground band
    rowc = f.mean(axis=1) - c.mean(axis=1)
    cont = float((rowc > 12).mean())
    return {"contrast": round(contrast, 2), "brown": round(brown, 2),
            "cont": round(cont, 3),
            "score": round(contrast * (0.5 + 0.5 * cont), 2)}


def candidates():
    terrain = json.load(open(TERRAIN, encoding="utf-8"))
    hexes, sides = terrain["hexes"], terrain["sides"]
    out, seen = [], set()
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
            if sk in seen:
                continue
            seen.add(sk)
            a, b, m = mids[s]
            ncx, ncy = centre_row(nL, nrow)
            ux, uy = b[0] - a[0], b[1] - a[1]
            n = math.hypot(ux, uy)
            u = (ux / n, uy / n)
            vx, vy = ncx - cx, ncy - cy
            n2 = math.hypot(vx, vy)
            v = (vx / n2, vy / n2)
            rs = sides.get(sk, {})
            out.append({"side_key": sk, "elev": name_of(L, row), "elev_t": rec["t"],
                        "ground": name_of(nL, nrow), "ground_t": nrec["t"], "dir": s,
                        "m": m, "u": u, "v": v,
                        "encoded": bool(rs.get("staircase")),
                        "inferred": rs.get("inferred"),
                        "entrance": bool(rs.get("entrance"))})
    return out


def scored():
    rows = []
    for c in candidates():
        p = rectify(c["m"], c["u"], c["v"])
        d = dict(c)
        d.pop("m"); d.pop("u"); d.pop("v")
        d.update(score_patch(p))
        rows.append(d)
    rows.sort(key=lambda r: -r["score"])
    return rows


def sheet(cands, path, cols=8, zoom=5, title=""):
    tiles = []
    for c in cands:
        p = rectify(c["m"], c["u"], c["v"])
        im = Image.fromarray(np.clip(p, 0, 255).astype(np.uint8))
        im = im.resize((PW * zoom, PH * zoom), Image.LANCZOS)
        d = ImageDraw.Draw(im)
        d.line([(PW // 2 * zoom, 0), (PW // 2 * zoom, PH * zoom)], fill=(0, 255, 0), width=1)
        d.line([(0, (0 - Y0) * zoom), (PW * zoom, (0 - Y0) * zoom)], fill=(255, 0, 255), width=1)
        tiles.append((c, im))
    if not tiles:
        return None
    tw, th = tiles[0][1].size
    lab = 30
    rows_n = (len(tiles) + cols - 1) // cols
    sheet_im = Image.new("RGB", (cols * (tw + 8) + 8, rows_n * (th + lab + 8) + 34), (25, 25, 25))
    d = ImageDraw.Draw(sheet_im)
    try:
        font = ImageFont.truetype("arial.ttf", 14)
        big = ImageFont.truetype("arial.ttf", 18)
    except Exception:
        font = big = ImageFont.load_default()
    d.text((8, 6), title, fill=(255, 255, 255), font=big)
    for i, (c, im) in enumerate(tiles):
        r, col = divmod(i, cols)
        x = 8 + col * (tw + 8)
        y = 30 + r * (th + lab + 8)
        sheet_im.paste(im, (x, y))
        tag = "%s-%s %s" % (c["elev"], c["ground"], c["dir"])
        state = ("ENC" if c["encoded"] else "new")
        if c["encoded"] and c["inferred"] is False:
            state = "ART"
        d.text((x, y + th + 1), tag, fill=(255, 255, 0), font=font)
        d.text((x, y + th + 15), "%s s=%.1f" % (state, c.get("score", 0)),
               fill=(0, 255, 120) if state == "ART" else (200, 200, 200), font=font)
    sheet_im.save(path)
    return path


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "score"
    outdir = r"C:\Users\fisch\Desktop\SoJ_PREP3"
    os.makedirs(outdir, exist_ok=True)
    if cmd == "score":
        rows = scored()
        json.dump(rows, open(r"C:\VassalSoJ\stair_scan.json", "w"), indent=1)
        print("scored", len(rows))
        print("\n-- the 8 art-confirmed hexsides (session 1) --")
        for i, r in enumerate(rows):
            if r["encoded"] and r["inferred"] is False:
                print(" rank %3d  %-5s->%-5s %-3s contrast=%5.1f brown=%5.1f cont=%.2f score=%5.1f"
                      % (i + 1, r["elev"], r["ground"], r["dir"], r["contrast"],
                         r["brown"], r["cont"], r["score"]))
        print("\n-- top 45 --")
        for i, r in enumerate(rows[:45]):
            print(" %3d %-5s->%-5s %-3s %-12s c=%5.1f b=%5.1f k=%.2f s=%5.1f enc=%s inf=%s"
                  % (i + 1, r["elev"], r["ground"], r["dir"], r["elev_t"], r["contrast"],
                     r["brown"], r["cont"], r["score"], r["encoded"], r["inferred"]))
        print("\n-- encoded hexsides that score LOW (bottom of the encoded set) --")
        enc = [(i, r) for i, r in enumerate(rows) if r["encoded"]]
        for i, r in enc[-20:]:
            print(" %3d %-5s->%-5s %-3s c=%5.1f k=%.2f s=%5.1f inf=%s"
                  % (i + 1, r["elev"], r["ground"], r["dir"], r["contrast"],
                     r["cont"], r["score"], r["inferred"]))
    elif cmd.startswith("sheet"):
        cs = candidates()
        rows = {r["side_key"]: r for r in scored()}
        for c in cs:
            c.update({k: v for k, v in rows[c["side_key"]].items() if k in
                      ("score", "contrast", "cont", "brown")})
        if cmd == "sheet-encoded":
            sel = [c for c in cs if c["encoded"]]
            sel.sort(key=lambda c: -c["score"])
            for i in range(0, len(sel), 32):
                p = sheet(sel[i:i + 32], os.path.join(outdir, "sheet_encoded_%d.png" % (i // 32 + 1)),
                          title="ENCODED staircase hexsides %d-%d (green line = hexside centre, magenta = the hexside)" % (i + 1, min(i + 32, len(sel))))
                print(p)
        else:
            n = int(sys.argv[2]) if len(sys.argv) > 2 else 64
            sel = sorted(cs, key=lambda c: -c["score"])[:n]
            for i in range(0, len(sel), 32):
                p = sheet(sel[i:i + 32], os.path.join(outdir, "sheet_top_%d.png" % (i // 32 + 1)),
                          title="TOP-SCORING hexsides %d-%d" % (i + 1, min(i + 32, len(sel))))
                print(p)


if __name__ == "__main__":
    main()
