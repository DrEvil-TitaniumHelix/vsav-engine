import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from naw_ocr import full_page
from naw_render import OUT

Image.MAX_IMAGE_PIXELS = None


def crop(key, pageno, x0, y0, x1, y1, name, rotate=0, scale=1.0):
    im = full_page(key, pageno)
    w, h = im.size
    box = (int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h))
    c = im.crop(box)
    if rotate:
        c = c.rotate(rotate, expand=True)
    if scale != 1.0:
        c = c.resize((int(c.size[0] * scale), int(c.size[1] * scale)), Image.LANCZOS)
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"{name}.png")
    c.save(path)
    print(f"{path}  {c.size[0]}x{c.size[1]}  from {box} of {im.size}")
    return path


def crop_file(path_in, x0, y0, x1, y1, name, rotate=0, scale=1.0):
    im = Image.open(path_in).convert("RGB")
    w, h = im.size
    box = (int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h))
    c = im.crop(box)
    if rotate:
        c = c.rotate(rotate, expand=True)
    if scale != 1.0:
        c = c.resize((int(c.size[0] * scale), int(c.size[1] * scale)), Image.LANCZOS)
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"{name}.png")
    c.save(path)
    print(f"{path}  {c.size[0]}x{c.size[1]}  from {box} of {im.size}")
    return path


def main():
    a = sys.argv[1:]
    if a[0] == "--file":
        _, src, x0, y0, x1, y1, name = a[:7]
        kw = dict(t.split("=", 1) for t in a[7:])
        crop_file(src, float(x0), float(y0), float(x1), float(y1), name,
                  rotate=int(kw.get("rotate", 0)), scale=float(kw.get("scale", 1.0)))
        return
    key, page, x0, y0, x1, y1, name = a[:7]
    kw = dict(t.split("=", 1) for t in a[7:])
    crop(key, int(page), float(x0), float(y0), float(x1), float(y1), name,
         rotate=int(kw.get("rotate", 0)), scale=float(kw.get("scale", 1.0)))


if __name__ == "__main__":
    main()
