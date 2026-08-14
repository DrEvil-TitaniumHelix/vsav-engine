import os
import sys

from PIL import Image, ImageDraw

import naw_render as R

PAGE = 4
DOC = "ed2scan"
OUT = r"C:\VassalNaW\pages"
PACK = r"C:\VassalNaW\prep_packs\NAW_PREP4"
NATIVE = os.path.join(OUT, "ed2_p4_native.png")

BLOCKS = {
    "french": {
        "colour": "blue",
        "x0": 246, "x1": 1348, "y0": 222, "y1": 1302,
        "cols": 5, "rows": 5,
        "extra": [(1367, 1063, 1560, 1272)],
    },
    "allied": {
        "colour": "orange",
        "x0": 1725, "x1": 2597, "y0": 255, "y1": 1360,
        "cols": 4, "rows": 5,
        "extra": [],
    },
    "prussian": {
        "colour": "pale green",
        "x0": 2722, "x1": 3155, "y0": 292, "y1": 1372,
        "cols": 2, "rows": 5,
        "extra": [],
    },
    "turn": {
        "colour": "pale green",
        "x0": 3360, "x1": 3600, "y0": 730, "y1": 1000,
        "cols": 1, "rows": 1,
        "extra": [],
    },
}

SKIP = {("prussian", 0, 1), ("allied", 0, 3), ("allied", 1, 3)}


def native(force=False):
    if force or not os.path.exists(NATIVE):
        import fitz
        doc = fitz.open(R.DOCS[DOC])
        im = R.page_image(doc, PAGE, 400)
        os.makedirs(OUT, exist_ok=True)
        im.save(NATIVE)
    return Image.open(NATIVE).convert("RGB")


def cells(block):
    b = BLOCKS[block]
    w = (b["x1"] - b["x0"]) / b["cols"]
    h = (b["y1"] - b["y0"]) / b["rows"]
    out = []
    for r in range(b["rows"]):
        for c in range(b["cols"]):
            if (block, r, c) in SKIP:
                continue
            out.append((r, c,
                        int(b["x0"] + c * w), int(b["y0"] + r * h),
                        int(b["x0"] + (c + 1) * w), int(b["y0"] + (r + 1) * h)))
    for i, (x0, y0, x1, y1) in enumerate(b["extra"]):
        out.append((b["rows"] - 1, b["cols"] + i, x0, y0, x1, y1))
    return out


def upright(im, pad, zoom):
    c = im.crop(pad)
    c = c.rotate(-90, expand=True)
    return c.resize((int(c.width * zoom), int(c.height * zoom)), Image.LANCZOS)


def overview():
    im = native()
    os.makedirs(PACK, exist_ok=True)
    o = im.copy()
    o.thumbnail((1500, 1500))
    o.save(os.path.join(PACK, "a_00_overview.png"))
    d = ImageDraw.Draw(o)
    s = o.width / im.width
    for name, b in BLOCKS.items():
        d.rectangle([b["x0"] * s, b["y0"] * s, b["x1"] * s, b["y1"] * s], outline=(255, 0, 0), width=2)
        d.text((b["x0"] * s, b["y0"] * s - 12), name, fill=(255, 0, 0))
        for x0, y0, x1, y1 in b["extra"]:
            d.rectangle([x0 * s, y0 * s, x1 * s, y1 * s], outline=(0, 128, 255), width=2)
    o.save(os.path.join(PACK, "a_01_overview_blocks.png"))
    print(os.path.join(PACK, "a_01_overview_blocks.png"), im.size)


def cell(block, r, c, over=0.10, zoom=4.0, save=True):
    im = native()
    for rr, cc, x0, y0, x1, y1 in cells(block):
        if rr == r and cc == c:
            px, py = int((x1 - x0) * over), int((y1 - y0) * over)
            u = upright(im, (x0 - px, y0 - py, x1 + px, y1 + py), zoom)
            if save:
                os.makedirs(PACK, exist_ok=True)
                p = os.path.join(PACK, f"a_cell_{block}_r{r + 1}c{c + 1}.png")
                u.save(p)
                print(p, u.size)
            return u
    raise SystemExit(f"no cell {block} {r} {c}")


def sheet(block, over=0.06, zoom=3.0, percol=None):
    im = native()
    cs = cells(block)
    tiles = []
    for r, c, x0, y0, x1, y1 in cs:
        px, py = int((x1 - x0) * over), int((y1 - y0) * over)
        tiles.append((r, c, upright(im, (x0 - px, y0 - py, x1 + px, y1 + py), zoom)))
    tw = max(t.width for _, _, t in tiles)
    th = max(t.height for _, _, t in tiles)
    ncol = percol or BLOCKS[block]["cols"] + len(BLOCKS[block]["extra"])
    nrow = (len(tiles) + ncol - 1) // ncol
    gap, lab = 14, 30
    out = Image.new("RGB", (ncol * (tw + gap) + gap, nrow * (th + gap + lab) + gap), (250, 250, 250))
    d = ImageDraw.Draw(out)
    for i, (r, c, t) in enumerate(tiles):
        gx, gy = i % ncol, i // ncol
        X = gap + gx * (tw + gap)
        Y = gap + gy * (th + gap + lab)
        d.text((X + 4, Y + 4), f"{block[:2]} r{r + 1}c{c + 1}", fill=(0, 0, 0))
        out.paste(t, (X, Y + lab))
    os.makedirs(PACK, exist_ok=True)
    p = os.path.join(PACK, f"a_sheet_{block}.png")
    out.save(p)
    print(p, out.size, f"tiles={len(tiles)}")


def ocr(block):
    import numpy as np
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    im = native()
    for r, c, x0, y0, x1, y1 in cells(block):
        u = upright(im, (x0, y0, x1, y1), 6.0)
        w, h = u.size
        z = u.crop((int(w * 0.20), int(h * 0.45), int(w * 0.95), int(h * 0.90))).convert("L")
        a = np.asarray(z)
        z = Image.fromarray(((a > a.mean() - 1.2 * a.std()) * 255).astype("uint8"))
        t = pytesseract.image_to_string(z, config="--psm 7 -c tessedit_char_whitelist=0123456789-")
        print(f"{block} r{r + 1}c{c + 1}  {t.strip()!r}")


def main():
    a = sys.argv[1:]
    if not a or a[0] == "overview":
        overview()
        return
    if a[0] == "sheet":
        for b in (a[1:] or list(BLOCKS)):
            sheet(b)
        return
    if a[0] == "allcells":
        for b in (a[1:] or list(BLOCKS)):
            for r, c, *_ in cells(b):
                cell(b, r, c, zoom=4.0)
        return
    if a[0] == "cell":
        cell(a[1], int(a[2]) - 1, int(a[3]) - 1,
             zoom=float(a[4]) if len(a) > 4 else 4.0)
        return
    if a[0] == "ocr":
        for b in (a[1:] or list(BLOCKS)):
            ocr(b)
        return
    raise SystemExit("usage: naw_counters.py [overview|sheet [block]|cell BLOCK ROW COL [zoom]|ocr [block]]")


if __name__ == "__main__":
    main()
