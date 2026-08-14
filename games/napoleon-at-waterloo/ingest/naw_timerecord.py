import io
import os
import sys

import fitz
import pytesseract
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from naw_render import DOCS

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
Image.MAX_IMAGE_PIXELS = None

PACK = r"C:\VassalNaW\prep_packs\NAW_PREP4"
KEY = "ed2scan"
MAP_PAGE = 5
RULES_PAGE = 1

MAP_REGIONS = {
    "b_sheet_topband": (0.000, 0.000, 1.000, 0.075, 0, 1.0),
    "b_sheet_botband": (0.000, 0.900, 1.000, 1.000, 180, 1.0),
    "b_sheet_leftband": (0.000, 0.000, 0.230, 1.000, 0, 0.55),
    "b_sheet_rightband": (0.780, 0.000, 1.000, 1.000, 0, 0.55),
    "b_timerecord_full": (0.190, 0.004, 0.835, 0.060, 0, 1.0),
    "b_timerecord_L_head_1pm_2pm": (0.190, 0.004, 0.520, 0.060, 0, 2.0),
    "b_timerecord_M1_units_1_5": (0.363, 0.020, 0.480, 0.058, 0, 4.0),
    "b_timerecord_M2_units_5_9": (0.470, 0.020, 0.580, 0.058, 0, 4.0),
    "b_timerecord_R_3pm_10pm": (0.580, 0.004, 0.835, 0.060, 0, 2.5),
    "b_timerecord_slot_edges": (0.190, 0.000, 0.900, 0.075, 0, 1.5),
    "b_exited_french_context": (0.015, 0.480, 0.215, 0.975, 90, 1.0),
    "b_exited_french_box": (0.146, 0.680, 0.202, 0.945, 270, 2.2),
    "b_exited_french_arrows_above": (0.100, 0.600, 0.215, 0.960, 270, 1.0),
    "b_exit_arrows_northedge": (0.170, 0.000, 0.255, 1.000, 90, 1.0),
    "b_exit_arrows_zoom": (0.160, 0.540, 0.275, 1.000, 90, 2.0),
    "b_demoralization_full": (0.010, 0.930, 0.985, 1.000, 180, 1.0),
    "b_demoralization_L_1_20": (0.500, 0.930, 0.985, 1.000, 180, 2.5),
    "b_demoralization_R_21_40": (0.010, 0.930, 0.520, 1.000, 180, 2.5),
    "b_demoralization_caption": (0.840, 0.940, 0.985, 1.000, 180, 4.0),
    "b_demoral_howto_french": (0.925, 0.740, 0.975, 0.935, 270, 3.0),
    "b_second_edition_copyright": (0.952, 0.730, 0.995, 0.935, 270, 3.0),
    "b_copyright_block": (0.870, 0.860, 1.000, 0.980, 0, 3.0),
    "b_retreat_advance_allied": (0.148, 0.150, 0.215, 0.560, 90, 1.6),
    "b_disruption_allied": (0.148, 0.400, 0.215, 0.700, 90, 1.8),
}

RULES_REGIONS = {
    "b_p1_prussian_entry_caseB": (0.258, 0.640, 0.380, 0.990, 0, 2.2),
    "b_p1_prussian_entry_cont": (0.374, 0.020, 0.496, 0.180, 0, 2.2),
    "b_p1_extends_typo_zoom": (0.258, 0.940, 0.380, 0.975, 0, 6.0),
    "b_p1_allied_demoral_head": (0.866, 0.130, 0.990, 0.420, 0, 2.2),
    "b_p1_running_total_procedure": (0.866, 0.255, 0.990, 0.395, 0, 3.0),
    "b_p1_loss_accounting_procedure": (0.866, 0.380, 0.990, 0.575, 0, 2.2),
    "b_p1_allied_demoral_shift": (0.866, 0.560, 0.990, 0.860, 0, 2.2),
}

OLIVER = r"C:\VassalNaW\modules\ed2_oliver\images\Nap at Waterloo map 20mm hexes.jpg"

OLIVER_REGIONS = {
    "b_w2_oliver_timerecord": (0.948, 0.030, 1.000, 1.000, 90, 1.0),
    "b_w2_oliver_tr_units": (0.948, 0.260, 1.000, 0.630, 90, 3.0),
    "b_w2_oliver_demoral": (0.000, 0.000, 0.108, 1.000, 90, 1.0),
    "b_w2_oliver_exited": (0.160, 0.000, 0.410, 0.050, 0, 3.0),
}

UNIT_SLOTS = 9
UNIT_X0 = 0.3664
UNIT_X1 = 0.5755
UNIT_Y0 = 0.0230
UNIT_Y1 = 0.0560


def page_image(pageno=MAP_PAGE):
    doc = fitz.open(DOCS[KEY])
    page = doc[pageno - 1]
    imgs = page.get_images(full=True)
    if len(imgs) == 1:
        info = doc.extract_image(imgs[0][0])
        im = Image.open(io.BytesIO(info["image"]))
        if im.width >= 1700:
            return im.convert("RGB")
    pix = page.get_pixmap(dpi=600)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def cut(im, name, x0, y0, x1, y1, rotate=0, scale=1.0):
    w, h = im.size
    box = (int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h))
    c = im.crop(box)
    if rotate:
        c = c.rotate(rotate, expand=True)
    if scale != 1.0:
        c = c.resize((max(1, int(c.size[0] * scale)), max(1, int(c.size[1] * scale))), Image.LANCZOS)
    os.makedirs(PACK, exist_ok=True)
    p = os.path.join(PACK, f"{name}.png")
    c.save(p)
    print(f"{name}.png  {c.size[0]}x{c.size[1]}  box={box}  src={im.size}")
    return p


def units(im):
    span = (UNIT_X1 - UNIT_X0) / UNIT_SLOTS
    for i in range(UNIT_SLOTS):
        a = UNIT_X0 + i * span
        cut(im, f"b_unit_{i + 1:02d}", a - 0.0015, UNIT_Y0, a + span + 0.0015, UNIT_Y1, 0, 9.0)


def witness():
    w = Image.open(OLIVER).convert("RGB")
    print(f"oliver {w.size}")
    for n, r in OLIVER_REGIONS.items():
        cut(w, n, *r)
    t = w.copy()
    t.thumbnail((1400, 1400))
    t.save(os.path.join(PACK, "b_w2_oliver_layout.png"))
    print(f"b_w2_oliver_layout.png  {t.size[0]}x{t.size[1]}")


def ocr(name, psm=6):
    im = Image.open(os.path.join(PACK, f"{name}.png")).convert("L")
    txt = pytesseract.image_to_string(im, config=f"--psm {psm}")
    print(f"----- {name} psm={psm} -----")
    print(txt.strip())


def main():
    a = sys.argv[1:]
    if a and a[0] == "--ocr":
        for n in a[1:]:
            ocr(n)
        return
    if a and a[0] == "--witness":
        witness()
        return
    m = page_image(MAP_PAGE)
    print(f"map page {MAP_PAGE} native {m.size}")
    for n, r in MAP_REGIONS.items():
        if not a or n in a:
            cut(m, n, *r)
    if not a or "units" in a:
        units(m)
    p1 = page_image(RULES_PAGE)
    print(f"rules page {RULES_PAGE} native {p1.size}")
    for n, r in RULES_REGIONS.items():
        if not a or n in a:
            cut(p1, n, *r)
    if not a:
        witness()


if __name__ == "__main__":
    main()
