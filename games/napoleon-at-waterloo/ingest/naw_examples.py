import os
import re
import sys

import fitz
import pytesseract
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from naw_render import DOCS, OUT, page_image

Image.MAX_IMAGE_PIXELS = None
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

PACK = r"C:\VassalNaW\prep_packs\NAW_PREP5"
DPI = 400
ROT = -90
PAGE = 2
BASE = os.path.join(OUT, "ed2_p02_rot.png")

REGIONS = {
    "a_00_overview": (0.000, 0.000, 1.000, 1.000, 0.42),
    "a_01_intro": (0.055, 0.035, 0.400, 0.290, 1.6),
    "a_02_left_arty": (0.050, 0.285, 0.480, 0.475, 1.5),
    "a_03_left_town": (0.050, 0.455, 0.480, 0.720, 1.5),
    "a_04_left_circle": (0.020, 0.720, 0.360, 0.960, 1.5),
    "a_05_mid_top": (0.380, 0.020, 0.750, 0.320, 1.6),
    "a_06_right_top": (0.660, 0.030, 1.000, 0.280, 1.6),
    "a_06b_right_top": (0.680, 0.055, 1.000, 0.200, 2.2),
    "a_07_right_mid": (0.660, 0.220, 1.000, 0.420, 1.6),
    "a_08_right_2to1": (0.700, 0.400, 1.000, 0.600, 2.0),
    "a_09_mid_4to1": (0.360, 0.320, 0.680, 0.540, 2.0),
    "a_10_row1_left": (0.330, 0.555, 0.720, 0.745, 1.9),
    "a_11_row1_right": (0.580, 0.600, 1.000, 0.745, 1.9),
    "a_12_row2_left": (0.330, 0.755, 0.720, 0.960, 1.9),
    "a_13_row2_right": (0.580, 0.790, 1.000, 0.960, 1.9),
    "a_14_row1_3to1": (0.600, 0.605, 0.860, 0.745, 2.6),
    "a_15_row2_1to1": (0.600, 0.795, 0.900, 0.955, 2.6),
    "a_16_row2_2to4": (0.500, 0.790, 0.720, 0.955, 3.0),
    "a_17_row1_2to4": (0.500, 0.600, 0.700, 0.755, 3.0),
    "a_18_row1_left2": (0.330, 0.585, 0.580, 0.745, 2.8),
    "a_19_row2_left2": (0.330, 0.780, 0.580, 0.940, 2.8),
    "a_20_mid_2to1": (0.400, 0.130, 0.680, 0.330, 2.4),
    "a_21_mid_top2to1": (0.500, 0.020, 0.780, 0.170, 2.4),
    "a_22_row2_7v34": (0.635, 0.800, 0.820, 0.945, 3.4),
}


def base(force=False):
    if os.path.exists(BASE) and not force:
        return Image.open(BASE).convert("RGB")
    doc = fitz.open(DOCS["ed2scan"])
    im = page_image(doc, PAGE, DPI).rotate(ROT, expand=True)
    os.makedirs(OUT, exist_ok=True)
    im.save(BASE)
    return im


def _cut(x0, y0, x1, y1, sc, name):
    im = base()
    w, h = im.size
    cr = im.crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)))
    if sc != 1.0:
        cr = cr.resize((int(cr.width * sc), int(cr.height * sc)), Image.LANCZOS)
    os.makedirs(PACK, exist_ok=True)
    p = os.path.join(PACK, f"{name}.png")
    cr.save(p)
    print(f"{p} {cr.width}x{cr.height}")
    return p


def region(name):
    return _cut(*REGIONS[name], name)


def grid(cols=3, rows=4, over=0.01, scale=1.0):
    for r in range(rows):
        for c in range(cols):
            _cut(max(0.0, c / cols - over), max(0.0, r / rows - over),
                 min(1.0, (c + 1) / cols + over), min(1.0, (r + 1) / rows + over),
                 scale, f"a_grid_r{r}c{c}")


def odds_ocr():
    im = base()
    w, h = im.size
    hits = {}
    for r in range(4):
        for c in range(3):
            x0, y0 = max(0.0, c / 3 - 0.01) * w, max(0.0, r / 4 - 0.01) * h
            cr = im.crop((int(x0), int(y0), int(min(1.0, (c + 1) / 3 + 0.01) * w),
                          int(min(1.0, (r + 1) / 4 + 0.01) * h))).convert("L")
            S = 3
            big = cr.resize((cr.width * S, cr.height * S), Image.LANCZOS)
            for psm in (11, 12):
                d = pytesseract.image_to_data(big, config=f"--psm {psm}",
                                              output_type=pytesseract.Output.DICT)
                t = [(d["text"][i].strip(), d["left"][i] / S + x0, d["top"][i] / S + y0)
                     for i in range(len(d["text"])) if d["text"][i].strip()]
                for tok in t:
                    if tok[0].lower() != "to":
                        continue
                    L = [z for z in t if abs(z[2] - tok[2]) < 25 and 0 < tok[1] - z[1] < 110
                         and re.fullmatch(r"[1-9]", z[0])]
                    R = [z for z in t if abs(z[2] - tok[2]) < 25 and 0 < z[1] - tok[1] < 140
                         and re.fullmatch(r"[1-9]", z[0])]
                    if L and R:
                        hits[(round(tok[2] / 50), round(tok[1] / 50))] = (
                            tok[2] / h, tok[1] / w, f"{L[-1][0]} to {R[0][0]}")
    for k in sorted(hits, key=lambda k: (hits[k][0], hits[k][1])):
        y, x, s = hits[k]
        print(f"y={y:.3f} x={x:.3f}   {s}")
    print(f"OCR-LOCATED LABELS {len(hits)}")


def main():
    a = sys.argv[1:]
    if not a or a[0] == "all":
        im = base()
        print(f"base {im.size} -> {BASE}")
        for n in REGIONS:
            region(n)
        return
    if a[0] == "base":
        print(f"base {base(force=True).size} -> {BASE}")
        return
    if a[0] == "grid":
        kw = dict(t.split("=", 1) for t in a[1:])
        grid(scale=float(kw.get("scale", 1.0)))
        return
    if a[0] == "odds":
        odds_ocr()
        return
    if a[0] == "box":
        x0, y0, x1, y1, name = a[1:6]
        kw = dict(t.split("=", 1) for t in a[6:])
        _cut(float(x0), float(y0), float(x1), float(y1), float(kw.get("scale", 2.0)), name)
        return
    for n in a:
        region(n)


if __name__ == "__main__":
    main()
