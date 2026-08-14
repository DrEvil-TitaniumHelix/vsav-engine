import io
import os
import sys

import fitz
from PIL import Image

SRC = r"C:\VassalLibrary\launchbox\Manuals\VASSAL"
OUT = r"C:\VassalNaW\pages"

DOCS = {
    "rules": os.path.join(SRC, "Napoleon at Waterloo (2nd & 3rd Ed)", "rules.pdf"),
    "org": os.path.join(SRC, "Napoleon at Waterloo (2nd & 3rd Ed)", "org.pdf"),
    "ed2scan": os.path.join(SRC, "Napoleon at Waterloo (2nd Ed)", "NapoleonatWaterloo.pdf"),
    "ed2exp": os.path.join(SRC, "Napoleon at Waterloo (2nd Ed)", "NapExpansionRules.pdf"),
    "ed3": os.path.join(SRC, "Napoleon at Waterloo (3rd Ed)", "Napoleon at Waterloo rules org and 79 and tweeks.pdf"),
    "sabin": os.path.join(SRC, "Napoleon at Waterloo (3rd Ed)", "Napoleon_at_Waterloo_Improved_Rules_Tweaks_Sabin_11.23.pdf"),
}


def page_image(doc, pageno, dpi):
    page = doc[pageno - 1]
    imgs = page.get_images(full=True)
    if len(imgs) == 1:
        info = doc.extract_image(imgs[0][0])
        im = Image.open(io.BytesIO(info["image"]))
        if im.width >= 1700:
            return im.convert("RGB")
    pix = page.get_pixmap(dpi=dpi)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def dump_text(key):
    doc = fitz.open(DOCS[key])
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"{key}_text.txt")
    with open(path, "w", encoding="utf-8") as f:
        for i in range(len(doc)):
            f.write(f"\n===== [{key}] PAGE {i + 1} =====\n")
            f.write(doc[i].get_text())
    print(f"{path}  pages={len(doc)}")


def layout(key, pageno, dpi=200):
    doc = fitz.open(DOCS[key])
    im = page_image(doc, pageno, dpi)
    os.makedirs(OUT, exist_ok=True)
    small = im.copy()
    small.thumbnail((1400, 1400))
    path = os.path.join(OUT, f"{key}_p{pageno:02d}_layout.png")
    small.save(path)
    print(f"{im.size} -> {path}")


def cut(key, pageno, cols=2, chunks=2, dpi=400, top=0.02, bot=0.99, over=0.02):
    doc = fitz.open(DOCS[key])
    im = page_image(doc, pageno, dpi)
    w, h = im.size
    os.makedirs(OUT, exist_ok=True)
    y_top, y_bot = top * h, bot * h
    span = (y_bot - y_top) / chunks
    pad = over * h
    xs = []
    for c in range(cols):
        x0 = max(0.0, c / cols - 0.01)
        x1 = min(1.0, (c + 1) / cols + 0.01)
        xs.append((x0, x1))
    for ci, (x0, x1) in enumerate(xs, start=1):
        for k in range(chunks):
            y0 = max(y_top, y_top + k * span - pad)
            y1 = min(y_bot, y_top + (k + 1) * span + pad)
            crop = im.crop((int(x0 * w), int(y0), int(x1 * w), int(y1)))
            name = f"{key}_p{pageno:02d}_c{ci}_{chr(ord('a') + k)}.png"
            crop.save(os.path.join(OUT, name))
            print(f"  {name} {crop.size[0]}x{crop.size[1]}")


def main():
    a = sys.argv[1:]
    if not a:
        for k, v in DOCS.items():
            n = len(fitz.open(v)) if os.path.exists(v) else -1
            print(f"{k:8s} pages={n:3d}  {v}")
        return
    if a[0] == "--text":
        for k in (a[1:] or list(DOCS)):
            dump_text(k)
        return
    if a[0] == "--layout":
        key = a[1]
        for p in a[2:]:
            layout(key, int(p))
        return
    key = a[0]
    kw = {}
    for tok in a[1:]:
        if "=" in tok:
            k, v = tok.split("=", 1)
            kw[k] = float(v) if "." in v else int(v)
    pages = [int(t) for t in a[1:] if "=" not in t]
    for p in pages:
        print(f"[{key}] page {p}:")
        cut(key, p, **kw)


if __name__ == "__main__":
    main()
