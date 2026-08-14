import os
import sys

import pytesseract
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from naw_ocr import full_page, columns

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
Image.MAX_IMAGE_PIXELS = None

PACK = r"C:\VassalNaW\prep_packs\NAW_PREP5"
KEY = "ed2scan"

CROPS = [
    ("b_p5_sheet_left_third", 5, 0.000, 0.000, 0.400, 1.000, 90, 0.0, 2000),
    ("b_p5_sheet_right_third", 5, 0.600, 0.000, 1.000, 1.000, 270, 0.0, 2000),
    ("b_p5_allied_chartblock", 5, 0.000, 0.000, 0.240, 0.620, 90, 0.0, 1700),
    ("b_p5_french_chartblock", 5, 0.600, 0.000, 1.000, 0.440, 270, 0.0, 1700),
    ("b_p5_middle_strip", 5, 0.380, 0.000, 0.620, 1.000, 90, 0.0, 1500),
    ("b_p5_retreat_advance", 5, 0.033, 0.170, 0.120, 0.320, 90, 2.5, 0),
    ("b_p5_disruption_open", 5, 0.010, 0.168, 0.058, 0.322, 90, 3.0, 0),
    ("b_p5_disruption_full", 5, 0.090, 0.318, 0.200, 0.475, 90, 3.0, 0),
    ("b_p5_disruption_bridge_6x", 5, 0.160, 0.318, 0.199, 0.475, 90, 6.0, 0),
    ("b_p5_optional_advance", 5, 0.016, 0.318, 0.100, 0.475, 90, 2.5, 0),
    ("b_p5_advances_useful", 5, 0.140, 0.468, 0.200, 0.612, 90, 3.0, 0),
    ("b_p2_examples", 2, 0.000, 0.000, 1.000, 1.000, 0, 0.0, 1500),
]

OCR_CROPS = [
    "b_p5_retreat_advance",
    "b_p5_disruption_open",
    "b_p5_disruption_full",
    "b_p5_disruption_bridge_6x",
    "b_p5_optional_advance",
    "b_p5_advances_useful",
]


def render():
    os.makedirs(PACK, exist_ok=True)
    cache = {}
    for name, page, x0, y0, x1, y1, rot, scale, thumb in CROPS:
        if page not in cache:
            cache[page] = full_page(KEY, page)
        im = cache[page]
        w, h = im.size
        c = im.crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)))
        if rot:
            c = c.rotate(rot, expand=True)
        if scale:
            c = c.resize((int(c.size[0] * scale), int(c.size[1] * scale)), Image.LANCZOS)
        if thumb:
            c.thumbnail((thumb, thumb))
        path = os.path.join(PACK, name + ".png")
        c.save(path)
        print(f"{path}  {c.size[0]}x{c.size[1]}  p{page} frac=({x0},{y0},{x1},{y1}) rot={rot} scale={scale}")


def ocr():
    out = []
    for name in OCR_CROPS:
        path = os.path.join(PACK, name + ".png")
        txt = pytesseract.image_to_string(Image.open(path), config="--psm 6")
        out.append(f"===== {name}\n{txt}")
    path = os.path.join(PACK, "b_ocr_crosscheck.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print(path)
    print("\n".join(out))


def sweep():
    im = full_page(KEY, 1)
    cols = columns(im)
    parts = [f"[{KEY}] page 1 size={im.size} cols={cols}"]
    hits = 0
    for ci, (a, b) in enumerate(cols, start=1):
        txt = pytesseract.image_to_string(im.crop((a, 0, b, im.size[1])), config="--psm 6")
        hits += txt.lower().count("disrupt")
        parts.append(f"\n----- COL {ci} x={a}..{b} -----\n{txt}")
    path = os.path.join(PACK, "b_p1_rules_full_ocr.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(parts))
    print(f"{path}  page1 'disrupt' occurrences = {hits}")

    im5 = full_page(KEY, 5)
    W, H = im5.size
    want = {"DISRUPTION", "RETREAT", "TERRAIN", "EXPLANATION", "OPTIONAL"}
    found = {}
    for tx in range(4):
        for ty in range(3):
            box = (int(tx / 4 * W), int(ty / 3 * H), int((tx + 1) / 4 * W), int((ty + 1) / 3 * H))
            sub = im5.crop(box)
            for rot in (90, 270):
                d = pytesseract.image_to_data(sub.rotate(rot, expand=True), config="--psm 6",
                                              output_type=pytesseract.Output.DICT)
                for i, t in enumerate(d["text"]):
                    s = t.strip().strip(".,:").upper()
                    if s in want:
                        found.setdefault(s, set()).add((tx, ty, rot))
    for k in sorted(found):
        print(f"p5 heading {k}: {len(found[k])} site(s) {sorted(found[k])}")


def main():
    a = sys.argv[1:] or ["render", "ocr", "sweep"]
    if "render" in a:
        render()
    if "ocr" in a:
        ocr()
    if "sweep" in a:
        sweep()


if __name__ == "__main__":
    main()
