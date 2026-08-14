import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from naw_map import source, hex_center, save

Image.MAX_IMAGE_PIXELS = None

SIDE_ANGLE = {"NE": 330, "SE": 30, "S": 90, "SW": 150, "NW": 210, "N": 270}


def disc(a, cx, cy, rad):
    H, W = a.shape[:2]
    x0, x1 = max(0, int(cx - rad)), min(W, int(cx + rad) + 1)
    y0, y1 = max(0, int(cy - rad)), min(H, int(cy + rad) + 1)
    if x1 <= x0 or y1 <= y0:
        return None
    sub = a[y0:y1, x0:x1].astype(np.int16)
    yy, xx = np.mgrid[y0:y1, x0:x1]
    m = (xx - cx) ** 2 + (yy - cy) ** 2 <= rad * rad
    return sub[m]


def hexpix(a, g, c, r, frac=0.72):
    x, y = hex_center(g, c, r)
    R = g["dx"] / 1.5 * frac
    return disc(a, x, y, R)


def stats(p):
    if p is None or len(p) == 0:
        return None
    R, G, B = p[:, 0], p[:, 1], p[:, 2]
    lum = p.mean(axis=1)
    return {
        "n": int(len(p)),
        "green": float(((G - R) > 15).mean()),
        "dark": float((lum < 115).mean()),
        "vdark": float((lum < 80).mean()),
        "lum": float(lum.mean()),
        "sat": float((p.max(axis=1) - p.min(axis=1)).mean()),
    }


def boxblur(x, k):
    H, W = x.shape
    s = 2 * k + 1
    p = np.pad(x, ((k, k + 1), (k, k + 1)), mode="edge")
    cs = np.cumsum(np.cumsum(p, axis=0), axis=1)
    cs = np.pad(cs, ((1, 0), (1, 0)))
    Y0, X0 = np.meshgrid(np.arange(H), np.arange(W), indexing="ij")
    return (cs[Y0 + s, X0 + s] - cs[Y0, X0 + s] - cs[Y0 + s, X0] + cs[Y0, X0]) / (s * s)


def speck(gray, g, c, r, frac=0.66, k=9, thr=18):
    x, y = hex_center(g, c, r)
    R = g["dx"] / 1.5 * frac
    H, W = gray.shape
    x0, x1, y0, y1 = int(max(0, x - R)), int(min(W, x + R)), int(max(0, y - R)), int(min(H, y + R))
    if x1 - x0 < 8 or y1 - y0 < 8:
        return None
    sub = gray[y0:y1, x0:x1]
    d = boxblur(sub, k) - sub
    return float((d > thr).mean())


def blob(gray, g, c, r, frac=0.70, k=6, thr=110):
    x, y = hex_center(g, c, r)
    R = g["dx"] / 1.5 * frac
    H, W = gray.shape
    x0, x1, y0, y1 = int(max(0, x - R)), int(min(W, x + R)), int(max(0, y - R)), int(min(H, y + R))
    if x1 - x0 < 8 or y1 - y0 < 8:
        return None
    m = (gray[y0:y1, x0:x1] < thr).astype(np.float32)
    return float((boxblur(m, k) > 0.92).mean())


def side_stats(gray, g, c, r, rad=0.30, k=4, thr=165):
    x, y = hex_center(g, c, r)
    R = g["dx"] / 1.5
    apo = R * math.sqrt(3) / 2
    H, W = gray.shape
    out = {}
    for name, ang in SIDE_ANGLE.items():
        ax = x + apo * math.cos(math.radians(ang))
        ay = y + apo * math.sin(math.radians(ang))
        rr = R * rad
        x0, x1, y0, y1 = int(max(0, ax - rr)), int(min(W, ax + rr)), int(max(0, ay - rr)), int(min(H, ay + rr))
        if x1 - x0 < 8 or y1 - y0 < 8:
            out[name] = None
            continue
        m = (gray[y0:y1, x0:x1] < thr).astype(np.float32)
        out[name] = round(float((boxblur(m, k) > 0.9).mean()), 3)
    return out


def scan(key, g, cols, rows, frac=0.72):
    im = source(key)
    if g.get("rot"):
        im = im.rotate(g["rot"], expand=True)
    a = np.asarray(im.convert("RGB"))
    gray = np.asarray(im.convert("L"), dtype=np.float32)
    out = {}
    for c in range(1, cols + 1):
        for r in range(1, rows + 1):
            hid = f"{c:02d}{r:02d}"
            s = stats(hexpix(a, g, c, r, frac))
            if s is None:
                continue
            s["speck"] = speck(gray, g, c, r)
            s["blob"] = blob(gray, g, c, r, k=max(3, int(g["dx"] / 27)))
            s["sides"] = side_stats(gray, g, c, r, thr=float(os.environ.get("NAW_SIDE_THR", 165)))
            out[hid] = s
    return out


def paint(key, g, cols, rows, classes, name, box=None, maxw=1600):
    im = source(key)
    if g.get("rot"):
        im = im.rotate(g["rot"], expand=True)
    im = im.convert("RGB").copy()
    d = ImageDraw.Draw(im, "RGBA")
    try:
        font = ImageFont.truetype("arial.ttf", int(g["dx"] * 0.26))
    except OSError:
        font = None
    col = {"clear": (255, 255, 255, 0), "road": (0, 120, 255, 70), "town": (255, 0, 0, 90),
           "town_road": (255, 0, 255, 90), "woods": (0, 160, 0, 110), "woods_road": (255, 200, 0, 120)}
    for c in range(1, cols + 1):
        for r in range(1, rows + 1):
            hid = f"{c:02d}{r:02d}"
            if hid not in classes:
                continue
            x, y = hex_center(g, c, r)
            R = g["dx"] / 1.5
            pts = [(x + R * math.cos(math.radians(t)), y + R * math.sin(math.radians(t))) for t in range(0, 360, 60)]
            k = classes[hid]
            d.polygon(pts, fill=col.get(k, (0, 0, 0, 60)))
            d.line(pts + [pts[0]], fill=(80, 80, 80, 160), width=2)
            d.text((x - R * 0.5, y - R * 0.18), hid, fill=(0, 0, 160), font=font)
    if box:
        w, h = im.size
        im = im.crop((int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)))
    if im.size[0] > maxw:
        s = maxw / im.size[0]
        im = im.resize((maxw, int(im.size[1] * s)), Image.LANCZOS)
    return save(im, name)


def main():
    a = sys.argv[1:]
    kw = dict(t.split("=", 1) for t in a if "=" in t)
    key = a[0]
    g = json.load(open(kw["grid"]))
    res = scan(key, g, int(kw.get("cols", g["cols"])), int(kw.get("rows", g["rows"])), float(kw.get("frac", 0.72)))
    if "out" in kw:
        json.dump(res, open(kw["out"], "w"), indent=1)
        print(f"{kw['out']}  {len(res)} hexes")
    else:
        for hid in sorted(res):
            s = res[hid]
            print(hid, {k: round(v, 3) for k, v in s.items() if k != "sides"})


if __name__ == "__main__":
    main()
