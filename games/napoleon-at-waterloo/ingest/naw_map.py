import io
import json
import math
import os
import sys

import fitz
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from naw_render import DOCS, OUT

Image.MAX_IMAGE_PIXELS = None

SOURCES = {
    "ed2folio": ("pdf", "ed2scan", 5),
    "ed2oliver": ("file", r"C:\VassalNaW\modules\ed2_oliver\images\Nap at Waterloo map 20mm hexes.jpg", 0),
    "ed3davejm": ("file", r"C:\VassalNaW\modules\ed3_davejm\images\Map to use 3 copy.jpg", 0),
}

_cache = {}


def source(key):
    if key in _cache:
        return _cache[key]
    kind, a, b = SOURCES[key]
    if kind == "pdf":
        doc = fitz.open(DOCS[a])
        page = doc[b - 1]
        imgs = page.get_images(full=True)
        im = None
        if len(imgs) == 1:
            info = doc.extract_image(imgs[0][0])
            cand = Image.open(io.BytesIO(info["image"]))
            if cand.width >= 1700:
                im = cand.convert("RGB")
        if im is None:
            pix = page.get_pixmap(dpi=300)
            im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    else:
        im = Image.open(a).convert("RGB")
    _cache[key] = im
    return im


def save(im, name):
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, f"{name}.png")
    im.save(p)
    print(f"{p}  {im.size[0]}x{im.size[1]}")
    return p


def thumb(key, name=None, box=None, rot=0, maxw=1400):
    im = source(key)
    if rot:
        im = im.rotate(rot, expand=True)
    if box:
        w, h = im.size
        im = im.crop((int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)))
    print(f"[{key}] full={source(key).size} shown={im.size}")
    t = im.copy()
    t.thumbnail((maxw, maxw))
    return save(t, name or f"{key}_thumb")


def zoom(key, x0, y0, x1, y1, name, rot=0, maxw=1500):
    im = source(key)
    if rot:
        im = im.rotate(rot, expand=True)
    w, h = im.size
    c = im.crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)))
    if c.size[0] > maxw:
        s = maxw / c.size[0]
        c = c.resize((maxw, int(c.size[1] * s)), Image.LANCZOS)
    return save(c, name)


def hex_center(g, col, row):
    x = g["x0"] + (col - 1) * g["dx"]
    y = g["y0"] + (row - 1) * g["dy"] + (g["dy"] / 2.0 if (col % 2 == 0) == g["even_down"] else 0.0)
    return x, y


def load_grid(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def overlay(key, g, name, box=None, rot=0, maxw=1500, labels=True, marks=None, every=1):
    im = source(key)
    if rot:
        im = im.rotate(rot, expand=True)
    im = im.convert("RGB").copy()
    d = ImageDraw.Draw(im)
    r = g["dx"] / 1.5
    try:
        font = ImageFont.truetype("arial.ttf", int(g["dx"] * 0.30))
    except OSError:
        font = None
    marks = marks or {}
    for col in range(1, g["cols"] + 1):
        for row in range(1, g["rows"] + 1):
            x, y = hex_center(g, col, row)
            pts = [(x + r * math.cos(math.radians(a)), y + r * math.sin(math.radians(a)))
                   for a in range(0, 360, 60)]
            hid = f"{col:02d}{row:02d}"
            col_line = marks.get(hid, (255, 0, 0))
            d.line(pts + [pts[0]], fill=col_line, width=max(2, int(g["dx"] * 0.02)))
            d.ellipse([x - 6, y - 6, x + 6, y + 6], fill=col_line)
            if labels and (col + row) % every == 0:
                d.text((x - r * 0.55, y - r * 0.2), hid, fill=(0, 0, 255), font=font)
    if box:
        w, h = im.size
        im = im.crop((int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)))
    s = maxw / im.size[0]
    im = im.resize((maxw, int(im.size[1] * s)), Image.LANCZOS)
    return save(im, name)


def tiles(key, g, hexes, name, rot=0, pad=0.62, cols=8, cell=190):
    im = source(key)
    if rot:
        im = im.rotate(rot, expand=True)
    n = len(hexes)
    rows = (n + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + 18)), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    for i, hid in enumerate(hexes):
        c, r = int(hid[:2]), int(hid[2:])
        x, y = hex_center(g, c, r)
        rad = g["dx"] * pad
        t = im.crop((int(x - rad), int(y - rad), int(x + rad), int(y + rad))).resize((cell, cell), Image.LANCZOS)
        px, py = (i % cols) * cell, (i // cols) * (cell + 18)
        sheet.paste(t, (px, py + 18))
        rr = cell / (3.0 * pad)
        cx, cy = px + cell / 2, py + 18 + cell / 2
        hp = [(cx + rr * math.cos(math.radians(a)), cy + rr * math.sin(math.radians(a))) for a in range(0, 360, 60)]
        d.line(hp + [hp[0]], fill=(255, 0, 0), width=2)
        d.text((px + 4, py + 4), hid, fill=(0, 0, 0))
    return save(sheet, name)


def main():
    a = sys.argv[1:]
    cmd = a[0]
    kw = dict(t.split("=", 1) for t in a if "=" in t)
    pos = [t for t in a[1:] if "=" not in t]
    if cmd == "thumb":
        box = tuple(float(v) for v in kw["box"].split(",")) if "box" in kw else None
        thumb(pos[0], kw.get("name"), box, int(kw.get("rot", 0)), int(kw.get("maxw", 1400)))
    elif cmd == "zoom":
        zoom(pos[0], *[float(v) for v in pos[1:5]], pos[5], int(kw.get("rot", 0)), int(kw.get("maxw", 1500)))
    elif cmd == "overlay":
        g = load_grid(pos[1])
        box = tuple(float(v) for v in kw["box"].split(",")) if "box" in kw else None
        overlay(pos[0], g, pos[2], box, int(kw.get("rot", 0)), int(kw.get("maxw", 1500)),
                kw.get("labels", "1") == "1", every=int(kw.get("every", 1)))
    elif cmd == "tiles":
        g = load_grid(pos[1])
        hexes = pos[2].split(",")
        tiles(pos[0], g, hexes, pos[3], int(kw.get("rot", 0)), float(kw.get("pad", 0.62)),
              int(kw.get("cols", 8)), int(kw.get("cell", 190)))


if __name__ == "__main__":
    main()
