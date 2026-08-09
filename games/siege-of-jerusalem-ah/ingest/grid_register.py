"""SoJ support tool — verify/refine the printed-map registration of our hex grid.

Builds a synthetic hex-boundary line mask from the ingest grid fit over a window of the
map, then searches (dx,dy) for the shift that best lands those lines on the map's printed
dark hex lines.  Reports the best offset per window and overall.

    python grid_register.py            # several windows over the Gallus battlefield
"""
import sys, os, math
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_hex_crop import MAP, SX, SY, DX, DY, centre_row, corners

WINDOWS = [  # (name, x0, y0, w, h) — clear-ish areas of the printed map
    ("north-outside", 1400, 1200, 500, 500),
    ("east-approach", 2900, 2200, 500, 500),
    ("west-approach", 700, 2600, 500, 500),
    ("south-outside", 1800, 4200, 500, 500),
    ("centre-city", 2000, 2600, 500, 500),
]


def line_mask(x0, y0, w, h, dx, dy):
    im = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(im)
    Lmin = int((x0 - 200) / DX) - 2
    Lmax = int((x0 + w + 200) / DX) + 2
    for L in range(max(1, Lmin), Lmax):
        for row in range(0, 80):
            cx, cy = centre_row(L, row)
            cx += dx; cy += dy
            if not (x0 - 100 < cx < x0 + w + 100 and y0 - 100 < cy < y0 + h + 100):
                continue
            pts = [(p[0] - x0, p[1] - y0) for p in corners(cx, cy)]
            d.polygon(pts, outline=255)
    return np.asarray(im) > 0


def main():
    img = np.asarray(Image.open(MAP).convert("L")).astype(np.float32)
    best_all = []
    for name, x0, y0, w, h in WINDOWS:
        sub = img[y0:y0 + h, x0:x0 + w]
        dark = (sub < np.percentile(sub, 12)).astype(np.float32)
        best = None
        for dxi in np.arange(-14, 14.5, 1.0):
            for dyi in np.arange(-14, 14.5, 1.0):
                m = line_mask(x0, y0, w, h, dxi, dyi)
                if m.sum() == 0:
                    continue
                sc = float(dark[m].mean())
                if best is None or sc > best[0]:
                    best = (sc, dxi, dyi)
        print("%-14s best dx=%+5.1f dy=%+5.1f  darkline-hit=%.3f" % (name, best[1], best[2], best[0]))
        best_all.append(best)
    dxs = [b[1] for b in best_all]; dys = [b[2] for b in best_all]
    print("\nmedian offset: dx=%+.1f dy=%+.1f" % (float(np.median(dxs)), float(np.median(dys))))


if __name__ == "__main__":
    main()
