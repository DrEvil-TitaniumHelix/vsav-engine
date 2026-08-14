import json
import math
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from naw_map import source

Image.MAX_IMAGE_PIXELS = None


def perim_unit(n=48):
    pts = []
    for i in range(n):
        t = 360.0 * i / n
        seg = int(t // 60)
        f = (t % 60) / 60.0
        a0, a1 = math.radians(seg * 60), math.radians((seg + 1) * 60)
        x = math.cos(a0) + (math.cos(a1) - math.cos(a0)) * f
        y = math.sin(a0) + (math.sin(a1) - math.sin(a0)) * f
        pts.append((x, y))
    return np.array(pts)


UNIT = perim_unit()


def dark_img(key, rot=0):
    im = source(key)
    if rot:
        im = im.rotate(rot, expand=True)
    return 255.0 - np.asarray(im.convert("L"), dtype=np.float32)


def score(a, x0, y0, dx, dy, even_down, cols, rows, c0=1, r0=1):
    H, W = a.shape
    R = dx / 1.5
    xs, ys = [], []
    for c in range(c0, c0 + cols):
        for r in range(r0, r0 + rows):
            cx = x0 + (c - 1) * dx
            cy = y0 + (r - 1) * dy + (dy / 2.0 if (c % 2 == 0) == even_down else 0.0)
            xs.append(cx + R * UNIT[:, 0])
            ys.append(cy + R * UNIT[:, 1])
    xs = np.concatenate(xs).round().astype(np.int64)
    ys = np.concatenate(ys).round().astype(np.int64)
    ok = (xs >= 0) & (xs < W) & (ys >= 0) & (ys < H)
    if ok.sum() < 100:
        return -1.0
    return float(a[ys[ok], xs[ok]].mean())


def fit(key, x0r, y0r, dxr, dyr, cols, rows, c0=1, r0=1, even_down=True, rot=0, steps=(8.0, 2.0, 0.5)):
    a = dark_img(key, rot)
    best = (-1, x0r[0], y0r[0], dxr[0], dyr[0], even_down)
    eds = [even_down] if even_down is not None else [True, False]
    for ed in eds:
        for dx in np.arange(dxr[0], dxr[1] + 1e-9, dxr[2] if len(dxr) > 2 else 1.0):
            for dy in np.arange(dyr[0], dyr[1] + 1e-9, dyr[2] if len(dyr) > 2 else 1.0):
                x = x0r[0]
                while x <= x0r[1]:
                    y = y0r[0]
                    while y <= y0r[1]:
                        s = score(a, x, y, dx, dy, ed, cols, rows, c0, r0)
                        if s > best[0]:
                            best = (s, x, y, dx, dy, ed)
                        y += steps[0]
                    x += steps[0]
    s, x, y, dx, dy, ed = best
    for st in steps[1:]:
        cands = []
        for ddx in np.arange(-3 * st, 3 * st + 1e-9, st):
            for ddy in np.arange(-3 * st, 3 * st + 1e-9, st):
                for sdx in np.arange(-st / 4, st / 4 + 1e-9, st / 8):
                    for sdy in np.arange(-st / 4, st / 4 + 1e-9, st / 8):
                        cands.append((score(a, x + ddx, y + ddy, dx + sdx, dy + sdy, ed, cols, rows, c0, r0),
                                      x + ddx, y + ddy, dx + sdx, dy + sdy))
        s, x, y, dx, dy = max(cands, key=lambda t: t[0])
    return {"x0": float(x), "y0": float(y), "dx": float(dx), "dy": float(dy), "even_down": ed, "score": float(s)}


def main():
    a = sys.argv[1:]
    kw = dict(t.split("=", 1) for t in a if "=" in t)
    key = a[0]
    rng = lambda k: [float(v) for v in kw[k].split(",")]
    r = fit(key, rng("x0r"), rng("y0r"), rng("dxr"), rng("dyr"),
            int(kw["cols"]), int(kw["rows"]), int(kw.get("c0", 1)), int(kw.get("r0", 1)),
            None if kw.get("even_down", "1") == "?" else kw.get("even_down", "1") == "1",
            int(kw.get("rot", 0)))
    print(json.dumps(r, indent=1))
    if "out" in kw:
        r["cols"] = int(kw.get("gcols", kw["cols"]))
        r["rows"] = int(kw.get("grows", kw["rows"]))
        json.dump(r, open(kw["out"], "w"), indent=1)


if __name__ == "__main__":
    main()
