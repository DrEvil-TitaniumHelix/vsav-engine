import os
import sys

import pytesseract
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from naw_ocr import full_page

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
Image.MAX_IMAGE_PIXELS = None


def find(key, pageno, words, maxw=2400):
    im = full_page(key, pageno)
    W, H = im.size
    s = min(1.0, maxw / W)
    small = im.resize((int(W * s), int(H * s)), Image.LANCZOS)
    sw, sh = small.size
    want = [w.lower() for w in words]
    for rot in (0, 90, 180, 270):
        r = small.rotate(rot, expand=True)
        d = pytesseract.image_to_data(r, output_type=pytesseract.Output.DICT)
        for i, txt in enumerate(d["text"]):
            t = txt.strip().lower()
            if not t or t not in want:
                continue
            x, y, w, h = d["left"][i], d["top"][i], d["width"][i], d["height"][i]
            rw, rh = r.size
            if rot == 0:
                px, py = x, y
            elif rot == 90:
                px, py = rh - y - h, x
            elif rot == 180:
                px, py = rw - x - w, rh - y - h
            else:
                px, py = y, rw - x - w
            fx, fy = px / sw, py / sh
            print(f"rot={rot:3d} '{txt.strip()}' frac=({fx:.3f},{fy:.3f}) "
                  f"size_frac=({w / sw:.3f},{h / sh:.3f}) conf={d['conf'][i]}")


def main():
    a = sys.argv[1:]
    find(a[0], int(a[1]), a[2:])


if __name__ == "__main__":
    main()
