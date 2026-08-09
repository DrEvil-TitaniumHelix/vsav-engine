"""Support tool (PREP-6): render the last unread Siege of Jerusalem sources to
readable crops.

Sources:
  * literature/siege-of-jerusalem/soj_errata1.gif  (406x712, greyscale scan)
  * literature/siege-of-jerusalem/soj_errata2.gif  (1100x850, greyscale scan)
  * C:/VassalSoJ/extracted/images/Combat_Tables.jpg (1628x1186 play-aid card)
  * The_General_Vol24i5.pdf / The_General_Vol26i4.pdf (magazine scans)

The GIFs and the play-aid are SMALL, so the usual "cut into chunks" trick is the
wrong way round: here we UPSCALE (Lanczos) and stretch contrast so the Read
tool's ~1568px downscale still lands above the original pixel grid.

Usage:
    python prep6_render.py errata          # both errata gifs, upscaled + tiled
    python prep6_render.py tables          # Combat_Tables.jpg, upscaled + tiled
    python prep6_render.py general 24 5 6  # Vol 24-5, pages 5 and 6, full page
    python prep6_render.py contact 24      # Vol 24-5 thumbnail contact sheet

Outputs to C:/VassalSoJ/prep6/.
"""
import io
import os
import sys

import fitz
import numpy as np
from PIL import Image, ImageOps

LIT = r"C:\VassalArnhem\literature\siege-of-jerusalem"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "prep6")
os.makedirs(OUT, exist_ok=True)


def enhance(im, scale, autocontrast=True):
    """Upscale with Lanczos and stretch contrast (these scans are washed out)."""
    im = im.convert("L")
    if autocontrast:
        im = ImageOps.autocontrast(im, cutoff=1)
    w, h = im.size
    return im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)


def tile(im, name, max_side=1500, overlap=0.06):
    """Cut an image into tiles no bigger than max_side so nothing is downscaled."""
    w, h = im.size
    nx = max(1, -(-w // max_side))
    ny = max(1, -(-h // max_side))
    ov_x, ov_y = int(w / nx * overlap), int(h / ny * overlap)
    paths = []
    for j in range(ny):
        for i in range(nx):
            x0 = max(0, int(w * i / nx) - ov_x)
            x1 = min(w, int(w * (i + 1) / nx) + ov_x)
            y0 = max(0, int(h * j / ny) - ov_y)
            y1 = min(h, int(h * (j + 1) / ny) + ov_y)
            p = os.path.join(OUT, f"{name}_r{j + 1}c{i + 1}.png")
            im.crop((x0, y0, x1, y1)).save(p)
            paths.append(p)
    return paths


def do_errata():
    for n, scale in ((1, 3.5), (2, 2.0)):
        src = os.path.join(LIT, f"soj_errata{n}.gif")
        im = enhance(Image.open(src), scale)
        print(f"errata{n}: {Image.open(src).size} -> {im.size}")
        for p in tile(im, f"errata{n}"):
            print("  ", p)


def do_tables():
    src = os.path.join(HERE, "extracted", "images", "Combat_Tables.jpg")
    raw = Image.open(src)
    im = enhance(raw, 2.2, autocontrast=False)  # colour-coded card: keep it honest
    print(f"tables: {raw.size} -> {im.size}")
    for p in tile(im, "tables"):
        print("  ", p)
    # also a colour copy at 1.0 so ink colours stay readable
    raw.save(os.path.join(OUT, "tables_colour.png"))


def general_doc(vol, issue):
    return fitz.open(os.path.join(LIT, f"The_General_Vol{vol}i{issue}.pdf"))


def do_general(vol, issue, pages):
    doc = general_doc(vol, issue)
    for pno in pages:
        page = doc[pno - 1]
        pm = page.get_pixmap(dpi=200)
        im = Image.open(io.BytesIO(pm.tobytes("png")))
        print(f"v{vol}i{issue} p{pno}: {im.size}")
        for p in tile(im, f"g{vol}_{issue}_p{pno:02d}"):
            print("  ", p)


def do_contact(vol, issue):
    doc = general_doc(vol, issue)
    n = doc.page_count
    thumbs = []
    for i in range(n):
        pm = doc[i].get_pixmap(dpi=36)
        thumbs.append(Image.open(io.BytesIO(pm.tobytes("png"))).convert("RGB"))
    tw, th = thumbs[0].size
    cols = 6
    rows = -(-n // cols)
    sheet = Image.new("RGB", (cols * tw, rows * th), "white")
    for i, t in enumerate(thumbs):
        sheet.paste(t.resize((tw, th)), ((i % cols) * tw, (i // cols) * th))
    p = os.path.join(OUT, f"contact_v{vol}i{issue}.png")
    sheet.save(p)
    print(f"v{vol}i{issue}: {n} pages -> {p} ({sheet.size})")


def do_text(vol, issue):
    """Dump whatever text layer the magazine PDF carries (scan OCR, if any)."""
    doc = general_doc(vol, issue)
    p = os.path.join(OUT, f"text_v{vol}i{issue}.txt")
    with open(p, "w", encoding="utf-8") as fh:
        for i in range(doc.page_count):
            fh.write(f"\n===== PAGE {i + 1} =====\n")
            fh.write(doc[i].get_text())
    print(p, os.path.getsize(p), "bytes")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "errata":
        do_errata()
    elif cmd == "tables":
        do_tables()
    elif cmd == "general":
        do_general(int(sys.argv[2]), int(sys.argv[3]), [int(x) for x in sys.argv[4:]])
    elif cmd == "contact":
        do_contact(int(sys.argv[2]), int(sys.argv[3]))
    elif cmd == "text":
        do_text(int(sys.argv[2]), int(sys.argv[3]))
    else:
        raise SystemExit(__doc__)
