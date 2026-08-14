import json
import os
import sys

import pytesseract
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from naw_map import source, hex_center

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
Image.MAX_IMAGE_PIXELS = None
CFG = "--psm 7 -c tessedit_char_whitelist=0123456789"


def read_hex(im, g, c, r, dyfrac=0.36, w=0.55, h=0.22, up=3):
    x, y = hex_center(g, c, r)
    bw, bh = g["dx"] * w, g["dy"] * h
    box = (int(x - bw / 2), int(y - g["dy"] * dyfrac - bh / 2), int(x + bw / 2), int(y - g["dy"] * dyfrac + bh / 2))
    t = im.crop(box).convert("L")
    t = t.resize((t.size[0] * up, t.size[1] * up), Image.LANCZOS)
    return pytesseract.image_to_string(t, config=CFG).strip()


def main():
    a = sys.argv[1:]
    kw = dict(t.split("=", 1) for t in a if "=" in t)
    key = a[0]
    g = json.load(open(kw["grid"]))
    im = source(key)
    if g.get("rot"):
        im = im.rotate(g["rot"], expand=True)
    c0, c1 = (int(v) for v in kw.get("cols", f"1,{g['cols']}").split(","))
    r0, r1 = (int(v) for v in kw.get("rows", f"1,{g['rows']}").split(","))
    out = {}
    bad = 0
    for c in range(c0, c1 + 1):
        line = []
        for r in range(r0, r1 + 1):
            got = read_hex(im, g, c, r, float(kw.get("dyfrac", 0.36)))
            want = f"{c:02d}{r:02d}"
            out[want] = got
            ok = got == want
            bad += 0 if ok else 1
            line.append(f"{want}{'=' if ok else '!'}{got or '-'}")
        print(" ".join(line))
    print(f"MISMATCH {bad} / {len(out)}")
    if "out" in kw:
        json.dump(out, open(kw["out"], "w"), indent=1)


if __name__ == "__main__":
    main()
