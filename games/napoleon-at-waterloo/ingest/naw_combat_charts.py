import os
import sys

import pytesseract
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from naw_ocr import full_page

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
Image.MAX_IMAGE_PIXELS = None

PACK = r"C:\VassalNaW\prep_packs\NAW_PREP5"

CROPS = [
    ("c_sheet_overview", 0.000, 0.000, 1.000, 1.000, 0, 0.216),
    ("c_tec_right_full", 0.800, 0.000, 1.000, 0.335, 270, 1.0),
    ("c_tec_head", 0.808, 0.028, 0.837, 0.325, 270, 2.0),
    ("c_tec_row_clear", 0.831, 0.028, 0.877, 0.325, 270, 2.0),
    ("c_tec_row_towns", 0.873, 0.028, 0.917, 0.325, 270, 2.0),
    ("c_tec_row_woods", 0.913, 0.028, 0.957, 0.325, 270, 2.0),
    ("c_tec_footnote", 0.952, 0.028, 0.974, 0.325, 270, 2.0),
    ("c_tec_towns_combat", 0.873, 0.028, 0.917, 0.132, 270, 3.0),
    ("c_tec_towns_label", 0.873, 0.220, 0.917, 0.325, 270, 3.0),
    ("c_expl_right_full", 0.780, 0.320, 1.000, 0.535, 270, 1.0),
    ("c_expl_right_top", 0.780, 0.320, 1.000, 0.430, 270, 1.0),
    ("c_expl_right_bot", 0.780, 0.420, 1.000, 0.535, 270, 1.0),
    ("c_left_strip", 0.000, 0.000, 0.215, 0.500, 90, 1.0),
    ("c_expl_left_col", 0.015, 0.015, 0.200, 0.180, 90, 1.0),
    ("c_expl_left_a", 0.015, 0.015, 0.200, 0.100, 90, 1.0),
    ("c_expl_left_b", 0.015, 0.090, 0.200, 0.180, 90, 1.0),
    ("c_retreat_col", 0.015, 0.170, 0.200, 0.335, 90, 1.0),
    ("c_retreat_body", 0.015, 0.235, 0.200, 0.300, 90, 1.0),
    ("c_disruption", 0.015, 0.293, 0.200, 0.340, 90, 1.0),
    ("c_col3_disruption_optadv", 0.015, 0.320, 0.200, 0.478, 90, 1.0),
    ("c_col3_top", 0.015, 0.320, 0.200, 0.400, 90, 1.0),
    ("c_col3_bot", 0.015, 0.395, 0.200, 0.478, 90, 1.0),
    ("c_col4_advances", 0.015, 0.468, 0.200, 0.625, 90, 1.0),
    ("c_left_tec_check", 0.000, 0.480, 0.215, 1.000, 90, 0.5),
    ("c_right_lower_check", 0.780, 0.520, 1.000, 1.000, 270, 0.5),
    ("c_zoom_ae_left", 0.074, 0.024, 0.092, 0.170, 90, 3.0),
    ("c_zoom_ae_right", 0.814, 0.333, 0.830, 0.482, 270, 3.0),
    ("c_zoom_ex_left", 0.158, 0.228, 0.187, 0.332, 90, 3.0),
    ("c_zoom_ex_right", 0.893, 0.328, 0.927, 0.492, 270, 3.0),
    ("c_zoom_victorious", 0.082, 0.173, 0.102, 0.318, 90, 3.0),
    ("c_zoom_retreat_bars", 0.062, 0.173, 0.086, 0.318, 90, 3.0),
    ("c_zoom_advparticipate", 0.152, 0.468, 0.196, 0.614, 90, 2.5),
    ("c_zoom_tec_towns", 0.868, 0.176, 0.960, 0.262, 270, 2.0),
    ("c_zoom_tec_types", 0.800, 0.100, 0.872, 0.340, 270, 2.0),
]


CROPS_P1 = [
    ("c_p1_rules_towns_double", 0.620, 0.560, 0.755, 0.760, 0, 2.0),
    ("c_p1_col6_context", 0.620, 0.400, 0.755, 0.800, 0, 1.0),
]


def render_p1():
    im = full_page("ed2scan", 1)
    W, H = im.size
    os.makedirs(PACK, exist_ok=True)
    print(f"source page 1 = {W}x{H}")
    for name, x0, y0, x1, y1, rot, sc in CROPS_P1:
        box = (int(x0 * W), int(y0 * H), int(x1 * W), int(y1 * H))
        o = im.crop(box)
        if rot:
            o = o.rotate(rot, expand=True)
        if sc != 1.0:
            o = o.resize((max(1, int(o.size[0] * sc)), max(1, int(o.size[1] * sc))), Image.LANCZOS)
        p = os.path.join(PACK, name + ".png")
        o.save(p)
        print(f"{name:24s} {o.size[0]:5d}x{o.size[1]:5d} rot={rot:3d} box={box}")


OLIVER_TEC = r"C:\VassalNaW\modules\ed2_oliver\images\NapatWat TEC.jpg"


def render_corroboration():
    if not os.path.exists(OLIVER_TEC):
        print(f"MISSING {OLIVER_TEC}")
        return
    im = Image.open(OLIVER_TEC)
    p = os.path.join(PACK, "c_oliver_tec.png")
    im.save(p)
    print(f"{'c_oliver_tec':24s} {im.size[0]:5d}x{im.size[1]:5d} from {OLIVER_TEC}")


def clean():
    os.makedirs(PACK, exist_ok=True)
    keep = {n for n, *_ in CROPS} | {n for n, *_ in CROPS_P1} | {"c_oliver_tec"}
    for f in os.listdir(PACK):
        if f.startswith("c_") and f.endswith(".png") and f[:-4] not in keep:
            os.remove(os.path.join(PACK, f))
            print(f"removed stale {f}")


def render():
    im = full_page("ed2scan", 5)
    W, H = im.size
    os.makedirs(PACK, exist_ok=True)
    print(f"source page 5 = {W}x{H}")
    for name, x0, y0, x1, y1, rot, sc in CROPS:
        box = (int(x0 * W), int(y0 * H), int(x1 * W), int(y1 * H))
        o = im.crop(box)
        if rot:
            o = o.rotate(rot, expand=True)
        if sc != 1.0:
            o = o.resize((max(1, int(o.size[0] * sc)), max(1, int(o.size[1] * sc))), Image.LANCZOS)
        p = os.path.join(PACK, name + ".png")
        o.save(p)
        print(f"{name:24s} {o.size[0]:5d}x{o.size[1]:5d} rot={rot:3d} box={box}")


def ocr(name, psm=6):
    p = os.path.join(PACK, name + ".png")
    im = Image.open(p)
    t = pytesseract.image_to_string(im, config=f"--psm {psm}")
    print(f"===== OCR {name} psm={psm} =====")
    print(t)


def main():
    a = sys.argv[1:]
    if not a or a[0] == "render":
        clean()
        render()
        render_p1()
        render_corroboration()
        return
    if a[0] == "p1":
        render_p1()
        return
    if a[0] == "ocr":
        psm = 6
        names = []
        for t in a[1:]:
            if t.startswith("psm="):
                psm = int(t.split("=")[1])
            else:
                names.append(t)
        for n in names:
            ocr(n, psm)


if __name__ == "__main__":
    main()
