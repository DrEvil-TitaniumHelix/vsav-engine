"""validate_grid.py - Westwall: Arnhem grid + module cross-validation.

Evidence chain:
1. The grid formula (module buildFile HexGrid dx=96 dy=119 x0=60 y0=60,
   flat-top col-stagger, odd_row_carry 1 == the legacy hand-validated values)
   resolves EVERY printed position in the module's own 'Arnhem Historical'
   setup save:
   - the 7 German 18.12 at-start hexes,
   - the 3 Airborne Supply DZ counters' 18.11 hexes,
   - the 8 GT1 airborne groups stacked on their printed 18.13 target hexes
     (the module pre-places the GT1 drop stacked on the target - a recorded
     deviation from 15.31's one-per-hex; the TARGET hex is the grid anchor).
2. Pixel<->hex roundtrip over every on-map hex.
3. The generated setup.vsav loads through the engine with all 99 scenario
   pieces at their scenario positions.
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
ING = os.path.normpath(os.path.join(ROOT, "..", "VassalIngest", "westwall"))
sys.path.insert(0, os.path.join(ROOT, "engine"))
import gamespec, vsav                                            # noqa: E402

G = gamespec.Game(HERE)
BS, ESC = chr(92), chr(27)
ok = True


def check(cond, msg):
    global ok
    print(("PASS  " if cond else "FAIL  ") + msg)
    ok = ok and cond


# ------------------------------------------------ 1. module setup positions
plain, _, _ = vsav.read_vsav(os.path.join(ING, "setups", "Arnhem Historical.vsav"))
cmds = plain.split(ESC)
imgrx = re.compile(r'piece;[^;]*;[^;]*;([^;]+)' + re.escape('.') + r'(png|gif|svg);')
prx = re.compile(r'^\+/(\d+)/')
img_of = {}
for c in cmds:
    m = prx.match(c)
    if not m:
        continue
    im = imgrx.search(c)
    if im:
        img_of[m.group(1)] = im.group(1) + '.' + im.group(2)
srx = re.compile(r'^\+/\d+/stack/([^;]+);(\d+);(\d+);(.*)$')
at = {}
for c in cmds:
    m = srx.match(c.rstrip(BS))
    if m and m.group(1) == "Main Map":
        col, row, hx = G.grid.pixel_to_hex(int(m.group(2)), int(m.group(3)))
        for pid in m.group(4).split(';'):
            if pid.isdigit() and pid in img_of:
                at.setdefault(img_of[pid], hx)

GERMAN_1812 = {"A Kraft.png": "3722", "A 2-9SS.png": "3724", "A 9SS Recon.png": "3322",
               "A Grsn.png": "0702", "A 1-406.png": "2325", "A 2-406.png": "2025",
               "A BrDf.png": "2621"}
DZ_1811 = {"A 101 DZ.png": "1007", "A 82 DZ.png": "2323", "A 1 DZ.png": "3919"}
DROPS_1813 = {"A 101-502-1.png": "1004", "A 101-506-1.png": "0804",
              "A 101-501-1.png": "1308", "A 82-508-1.png": "2223",
              "A 82-505-1.png": "2023", "A 82-504-1.png": "2117",
              "A 1-1-1.png": "3719", "A 1-1-2S.png": "3718"}
n = 0
for table, label in ((GERMAN_1812, "18.12"), (DZ_1811, "18.11"), (DROPS_1813, "18.13")):
    for img, want in table.items():
        got = at.get(img)
        check(got == want, f"[{label}] {img} at {want} (module save resolves {got})")
        n += 1
check(n == 18, f"18 printed anchors checked ({n})")

# --------------------------------------------------------- 2. grid roundtrip
terr = G.terrain
bad = 0
total = 0
for key, v in terr["hexes"].items():
    if v["t"] == "offmap":
        continue
    c, r = int(key[:2]), int(key[2:])
    x, y = G.grid.hex_to_pixel(c, r)
    c2, r2, _ = G.grid.pixel_to_hex(x, y)
    total += 1
    if (c2, r2) != (c, r):
        bad += 1
check(bad == 0, f"pixel<->hex roundtrip on all {total} on-map hexes ({bad} bad)")

# --------------------------------------------- 3. generated setup.vsav loads
import board                                                     # noqa: E402
b = board.Board(os.path.join(HERE, "setup.vsav"), G)
scen = json.load(open(os.path.join(HERE, "scenario_historical.json"), encoding="utf-8"))
want_pos = {u["id"]: tuple(u["hex"]) for u in scen["units"]}
uu = b.units()
found = {u["id"]: (u["col"], u["row"]) for u in uu if u["id"] in want_pos}
check(len(uu) == 99, f"setup.vsav holds 99 pieces ({len(uu)})")
check(found == want_pos,
      f"all {len(want_pos)} at-start pieces at scenario hexes")
# side detection on the board layer: every German piece resolves Ger
germ = [u for u in uu if u["side"] == "Ger"]
check(len(germ) == 38, f"38 German pieces detected by image tokens ({len(germ)})")

print("ALL PASS" if ok else "FAILURES ABOVE")
sys.exit(0 if ok else 1)
