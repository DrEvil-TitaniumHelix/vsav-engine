import json
import math
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from naw_map import source, hex_center

Image.MAX_IMAGE_PIXELS = None


def perim_pts(g, c, r, n=72, k=0.94):
    x, y = hex_center(g, c, r)
    R = g["dx"] / 1.5
    out = []
    for i in range(n):
        t = 2 * math.pi * i / n
        a = t
        seg = int((math.degrees(a) % 360) // 60)
        a0 = math.radians(seg * 60)
        a1 = math.radians((seg + 1) * 60)
        p0 = (x + R * math.cos(a0), y + R * math.sin(a0))
        p1 = (x + R * math.cos(a1), y + R * math.sin(a1))
        f = (math.degrees(a) % 60) / 60.0
        px = p0[0] + (p1[0] - p0[0]) * f
        py = p0[1] + (p1[1] - p0[1]) * f
        out.append((x + (px - x) * k, y + (py - y) * k))
    return out


def scan(key, g, c0, c1, r0, r1, rot=0, win=3):
    im = source(key)
    if rot:
        im = im.rotate(rot, expand=True)
    a = np.asarray(im.convert("L"), dtype=np.float32)
    H, W = a.shape
    res = {}
    for c in range(c0, c1 + 1):
        for r in range(r0, r1 + 1):
            vals = []
            for px, py in perim_pts(g, c, r):
                xi, yi = int(round(px)), int(round(py))
                if 0 <= xi - win and xi + win < W and 0 <= yi - win and yi + win < H:
                    vals.append(a[yi - win:yi + win + 1, xi - win:xi + win + 1].min())
            if not vals:
                res[(c, r)] = None
                continue
            v = np.array(vals)
            res[(c, r)] = float((v < 170).mean())
    return res


def main():
    a = sys.argv[1:]
    kw = dict(t.split("=", 1) for t in a if "=" in t)
    key = a[0]
    g = json.load(open(kw["grid"]))
    c0, c1 = (int(v) for v in kw["cols"].split(","))
    r0, r1 = (int(v) for v in kw["rows"].split(","))
    res = scan(key, g, c0, c1, r0, r1, int(kw.get("rot", 0)))
    thr = float(kw.get("thr", 0.85))
    print("     " + "".join(f"{c%10}" for c in range(c0, c1 + 1)))
    for r in range(r0, r1 + 1):
        line = ""
        for c in range(c0, c1 + 1):
            v = res[(c, r)]
            line += "." if v is None else ("#" if v >= thr else ("+" if v >= thr * 0.7 else " "))
        print(f"{r:3d}  {line}")
    if "out" in kw:
        json.dump({f"{c:02d}{r:02d}": res[(c, r)] for (c, r) in res}, open(kw["out"], "w"), indent=1)


if __name__ == "__main__":
    main()
