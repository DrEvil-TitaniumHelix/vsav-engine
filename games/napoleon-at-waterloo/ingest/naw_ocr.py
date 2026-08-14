import io
import os
import sys

import fitz
import numpy as np
import pytesseract
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from naw_render import DOCS, OUT

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def full_page(key, pageno, dpi=300):
    doc = fitz.open(DOCS[key])
    page = doc[pageno - 1]
    imgs = page.get_images(full=True)
    if len(imgs) == 1:
        info = doc.extract_image(imgs[0][0])
        im = Image.open(io.BytesIO(info["image"]))
        if im.width >= 1700:
            return im.convert("L")
    pix = page.get_pixmap(dpi=dpi)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("L")


def gutters(im, min_gap_frac=0.006, ink_thresh=0.004):
    a = np.asarray(im, dtype=np.uint8)
    h, w = a.shape
    y0, y1 = int(0.06 * h), int(0.97 * h)
    band = a[y0:y1]
    ink = (band < 160).mean(axis=0)
    blank = ink < ink_thresh
    runs = []
    i = 0
    while i < w:
        if blank[i]:
            j = i
            while j < w and blank[j]:
                j += 1
            runs.append((i, j))
            i = j
        else:
            i += 1
    min_gap = max(4, int(min_gap_frac * w))
    return [r for r in runs if r[1] - r[0] >= min_gap]


def columns(im, **kw):
    w = im.size[0]
    gs = gutters(im, **kw)
    edges = [0]
    for a, b in gs:
        edges.append((a + b) // 2)
    edges.append(w)
    edges = sorted(set(edges))
    cols = []
    for a, b in zip(edges, edges[1:]):
        if b - a > 0.02 * w:
            cols.append((a, b))
    return cols


def ocr_page(key, pageno, psm=6, save_cols=False, **kw):
    im = full_page(key, pageno)
    cols = columns(im, **kw)
    os.makedirs(OUT, exist_ok=True)
    parts = []
    for ci, (a, b) in enumerate(cols, start=1):
        crop = im.crop((a, 0, b, im.size[1]))
        if save_cols:
            crop.save(os.path.join(OUT, f"{key}_p{pageno:02d}_col{ci:02d}.png"))
        txt = pytesseract.image_to_string(crop, config=f"--psm {psm}")
        parts.append(f"\n----- COL {ci}  x={a}..{b} -----\n{txt}")
    path = os.path.join(OUT, f"{key}_p{pageno:02d}_ocr.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"[{key}] page {pageno}  size={im.size}  cols={len(cols)}\n")
        f.write("".join(parts))
    print(f"{path}  size={im.size} cols={[c for c in cols]}")


def main():
    a = sys.argv[1:]
    key = a[0]
    kw = {}
    pages = []
    for tok in a[1:]:
        if "=" in tok:
            k, v = tok.split("=", 1)
            kw[k] = float(v) if "." in v else (v == "1" if k == "save_cols" else int(v))
        else:
            pages.append(int(tok))
    for p in pages:
        ocr_page(key, p, **kw)


if __name__ == "__main__":
    main()
