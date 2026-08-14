import os
import sys

import pytesseract
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from naw_ocr import full_page

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
Image.MAX_IMAGE_PIXELS = None

PACK = r"C:\VassalNaW\prep_packs\NAW_FIX"


def cut(key, pageno, x0, y0, x1, y1, name, rotate=0, scale=1.0, psm=6, ocr=True):
    im = full_page(key, pageno)
    w, h = im.size
    c = im.crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)))
    if rotate:
        c = c.rotate(rotate, expand=True)
    if scale != 1.0:
        c = c.resize((int(c.size[0] * scale), int(c.size[1] * scale)), Image.LANCZOS)
    os.makedirs(PACK, exist_ok=True)
    p = os.path.join(PACK, name + ".png")
    c.save(p)
    print(f"== {name}  {c.size[0]}x{c.size[1]}  src={im.size}")
    if ocr:
        t = pytesseract.image_to_string(c, config=f"--psm {psm}")
        print(t.strip())
    print()
    return p


def pageocr(key, pageno, needles, psm=6):
    im = full_page(key, pageno)
    txt = pytesseract.image_to_string(im, config=f"--psm {psm}")
    os.makedirs(PACK, exist_ok=True)
    p = os.path.join(PACK, f"{key}_p{pageno}_fullocr.txt")
    open(p, "w", encoding="utf-8").write(txt)
    low = txt.lower()
    print(f"== full-page OCR {key} p{pageno} -> {p}  chars={len(txt)}")
    for n in needles:
        print(f"   count('{n}') = {low.count(n.lower())}")
    print()


if __name__ == "__main__":
    exec(open(sys.argv[1], encoding="utf-8").read())
