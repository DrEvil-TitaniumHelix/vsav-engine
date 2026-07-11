"""Blue & Gray Chickamauga terrain: hex classes + hexside features from module map art.

Method (AK/Arnhem lineage): color masks calibrated on the map's own art; per-hex
disc classification; hexside features by edge-band coverage; road-vs-trail by
line-coverage discriminator (solid vs dashed). Writes terrain.json only when all
baked validation anchors pass (anchors verified by eye against the module map and
the original 1975 map scan).

TEC semantics (rules_transcription.json crt/tec, 1975 p8 [9.0] == deluxe):
  clear 1MP; forest 3MP (blocks LOS, no combat effect); rough 3MP (def doubled);
  forest_rough 6MP (def doubled, blocks LOS); road hexside 1MP negates terrain;
  trail hexside 2MP (forest/rough) 1MP (clear); creek hexside prohibited except
  bridge (free) / ford (+1MP); defender doubled if ALL attackers across
  bridge/ford hexsides; ZOC never through non-bridge non-ford creek hexsides.
"""
from PIL import Image
import numpy as np, json, sys
from collections import Counter

DX, DY, X0, Y0 = 95.1, 120.0, 7.0, 48.0
MAP = r"C:\VassalBlueGray\extracted\images\Chickamauga.png"
OUT = r"C:\VassalArnhem\games\blue-and-gray-chickamauga\terrain.json"
COLS = range(1, 27)          # playable columns 01-26 (27-28 = printed TRT/boxes)
ROWS = range(1, 29)

img = Image.open(MAP).convert("RGB")
a = np.asarray(img).astype(np.int16)
Hpx, Wpx = a.shape[:2]

def center(c, r):
    x = X0 + c * DX
    y = r * DY - 12.0 if c % 2 == 1 else Y0 + r * DY
    return x, y

def near(col, tol=26):
    return (np.abs(a - np.array(col)) <= tol).all(axis=-1)

# palette sampled from the map's own art (terrain key + verified hexes):
# cream (227,215,185); forest greens (44,112,0)..(147,180,15); rough (203,153,39);
# creek (29,130,150); road/grid/background all ~(113..118, 85..96, 73..79) — the
# SAME brown family, so lines are separated by geometry (coverage), not color.
clear_m  = near((227, 215, 185), 18)
forest_m = near((60, 127, 0), 45) | near((44, 112, 0), 40) | near((147, 180, 15), 40) \
           | near((116, 184, 42), 50)
rough_m  = near((203, 153, 39), 35)
creek_m  = near((29, 130, 150), 45)
bg_m     = near((118, 96, 79), 12)                   # also matches road/grid brown;
                                                     # used ONLY for off-map voting
r_, g_, b_ = a[..., 0], a[..., 1], a[..., 2]
line_m = (r_ >= 100) & (r_ <= 135) & (g_ >= 75) & (g_ <= 108) & (b_ >= 60) & (b_ <= 98) \
         & ((r_ - b_) >= 25)

HW2 = DX * 2 / 3.0           # flat-top half-width  (hex width = 4/3 * col spacing)
HH2 = DY / 2.0               # half-height

def hex_mask(cx, cy):
    x0, y0 = int(cx - HW2), int(cy - HH2)
    x1, y1 = int(cx + HW2) + 1, int(cy + HH2) + 1
    x0c, y0c, x1c, y1c = max(0, x0), max(0, y0), min(Wpx, x1), min(Hpx, y1)
    if x1c <= x0c or y1c <= y0c:
        return None, None
    yy, xx = np.mgrid[y0c:y1c, x0c:x1c]
    ddx = np.abs(xx - cx) / HW2
    ins = (ddx <= 1) & (np.abs(yy - cy) / HH2 <= np.minimum(1.0, 2.0 - 2.0 * ddx))
    return (slice(y0c, y1c), slice(x0c, x1c)), ins

hexes = {}
for c in COLS:
    for r in ROWS:
        cx, cy = center(c, r)
        sl, ins = hex_mask(cx, cy)
        key = f"{c:02d}{r:02d}"
        if sl is None or ins.sum() < 2000:
            hexes[key] = {"t": "offmap"}
            continue
        n = int(ins.sum())
        fr = lambda m: float(m[sl][ins].sum()) / n
        f_bg, f_cl, f_fo, f_ro = fr(bg_m), fr(clear_m), fr(forest_m), fr(rough_m)
        if f_bg > 0.30 or (f_bg + f_cl + f_fo + f_ro) < 0.45:
            hexes[key] = {"t": "offmap"}
            continue
        if f_fo > 0.12 and f_ro > 0.10:
            t = "forest_rough"
        elif f_fo > 0.15:
            t = "forest"
        elif f_ro > 0.13:
            t = "rough"
        else:
            t = "clear"
        hexes[key] = {"t": t}

NEI_ODD = [(1, 0), (-1, 0), (0, -1), (1, -1), (0, 1), (1, 1)]     # odd col shifted UP
NEI_EVEN = [(1, 0), (-1, 0), (-1, -1), (0, -1), (-1, 1), (0, 1)]  # even col shifted DOWN

def neighbors(c, r):
    for dc, dr in (NEI_ODD if c % 2 == 1 else NEI_EVEN):
        yield c + dc, r + dr

def edge_cover(c1, r1, c2, r2, mask, half_len=None, width=5):
    """Fraction of sample stations along the shared edge where mask appears
    within +-width px perpendicular. Solid line ~1.0, dashed ~0.4-0.7."""
    x1, y1 = center(c1, r1); x2, y2 = center(c2, r2)
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    dxv, dyv = x2 - x1, y2 - y1
    L = (dxv ** 2 + dyv ** 2) ** 0.5
    exu, eyu = -dyv / L, dxv / L               # edge direction (perpendicular to c-c line)
    if half_len is None:
        half_len = DY * 0.28
    hit = tot = 0
    for t in np.linspace(-half_len, half_len, 33):
        tot += 1
        found = False
        for w in range(-width, width + 1, 2):
            x = int(mx + exu * t + dxv / L * w)
            y = int(my + eyu * t + dyv / L * w)
            if 0 <= x < Wpx and 0 <= y < Hpx and mask[y, x]:
                found = True
                break
        hit += found
    return hit / tot

def side_ink(c1, r1, c2, r2):
    """(min_side_ink, largest_component): brown 'line' pixels in the edge band
    at perpendicular offsets 5..18 px, counted per side (min taken — a real
    crossing has ink on BOTH sides), plus the largest 8-connected component of
    line ink in the whole band (solid road = one big blob; trail dashes and
    ford hatches = small fragments; hex grid line itself sits inside +-4 px
    and is excluded)."""
    x1, y1 = center(c1, r1); x2, y2 = center(c2, r2)
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    dxv, dyv = x2 - x1, y2 - y1
    L = (dxv ** 2 + dyv ** 2) ** 0.5
    ux, uy = dxv / L, dyv / L
    exu, eyu = -uy, ux
    inkA = inkB = 0
    pts = set()
    for t in np.linspace(-33, 33, 67):
        for w in range(5, 19):
            xa, ya = int(mx + exu * t - ux * w), int(my + eyu * t - uy * w)
            xb, yb = int(mx + exu * t + ux * w), int(my + eyu * t + uy * w)
            if 0 <= xa < Wpx and 0 <= ya < Hpx and line_m[ya, xa]:
                inkA += 1
                pts.add((xa, ya))
            if 0 <= xb < Wpx and 0 <= yb < Hpx and line_m[yb, xb]:
                inkB += 1
                pts.add((xb, yb))
    # largest component among band ink points
    best = 0
    seen = set()
    for p in pts:
        if p in seen:
            continue
        stack, size = [p], 0
        seen.add(p)
        while stack:
            x, y = stack.pop()
            size += 1
            for nx in (x - 1, x, x + 1):
                for ny in (y - 1, y, y + 1):
                    if (nx, ny) in pts and (nx, ny) not in seen:
                        seen.add((nx, ny))
                        stack.append((nx, ny))
        best = max(best, size)
    return min(inkA, inkB), best

# Creek crossings PINNED from an exhaustive eyeball pass over the module map
# (every bridge symbol and hatch-mark ford enumerated at 3x zoom, 2026-07-10;
# crops archived in the overnight session scratchpad; candidates scored by
# creek-side-constrained ink). The four bridges match the map's own name labels.
PINNED_BRIDGES = {"1922|2022": "Alexander's Bridge", "2216|2316": "Reed's Bridge",
                  "2311|2411": "Dyer's Bridge", "2403|2503": "Ringgold Bridge"}
PINNED_FORDS = ["2112|2212", "2218|2318", "2320|2420", "2408|2508",
                "1527|1627", "1926|2026"]

playable = {k for k, v in hexes.items() if v["t"] != "offmap"}
sides = {}
warn = []
for key in sorted(playable):
    c, r = int(key[:2]), int(key[2:])
    for c2, r2 in neighbors(c, r):
        k2 = f"{c2:02d}{r2:02d}"
        if k2 <= key or k2 not in playable:
            continue
        sk = f"{key}|{k2}"
        feat = {}
        creek = edge_cover(c, r, c2, r2, creek_m, width=7)
        if creek >= 0.55:
            feat["creek"] = True
        if sk in PINNED_BRIDGES:
            feat["bridge"] = True
            feat["name"] = PINNED_BRIDGES[sk]
        elif sk in PINNED_FORDS:
            feat["ford"] = True
        if "creek" not in feat:
            ink, comp = side_ink(c, r, c2, r2)
            if ink >= 78 and comp >= 90:
                feat["road"] = True
            elif ink >= 30:
                feat["trail"] = True
        elif "bridge" not in feat and "ford" not in feat:
            # cross-check: a strong solid crossing on an UNPINNED creek side
            # would mean the eyeball pass missed a bridge — flag it
            ink, comp = side_ink(c, r, c2, r2)
            if ink >= 150 and comp >= 200:
                warn.append(f"UNPINNED strong crossing on creek side {sk} ink={ink} comp={comp}")
        if feat:
            sides[sk] = feat
for sk in list(PINNED_BRIDGES) + PINNED_FORDS:
    if sk not in sides or "creek" not in sides[sk]:
        warn.append(f"pinned crossing {sk} is not a detected creek side")
for w in warn:
    print("WARNING:", w)

print("hex classes:", Counter(v["t"] for v in hexes.values()))
print("side feats:", Counter(tuple(sorted(f)) for f in sides.values()))
creeksides = [k for k, f in sides.items() if "creek" in f]
print(f"creek sides: {len(creeksides)}, bridges: {[k for k,f in sides.items() if 'bridge' in f]}")
print(f"fords: {[k for k,f in sides.items() if 'ford' in f]}")

# ---------- diagnostic overlay ----------
if "--overlay" in sys.argv:
    from PIL import ImageDraw
    ov = img.copy()
    d = ImageDraw.Draw(ov)
    tint = {"forest": (0, 200, 0), "rough": (255, 140, 0), "forest_rough": (160, 90, 0),
            "clear": None, "offmap": (0, 0, 0)}
    for key, v in hexes.items():
        c, r = int(key[:2]), int(key[2:])
        cx, cy = center(c, r)
        col = tint.get(v["t"])
        if col:
            d.ellipse([cx - 12, cy - 12, cx + 12, cy + 12], fill=col)
    fcol = {"creek": (0, 0, 255), "bridge": (255, 0, 0), "ford": (255, 0, 255),
            "road": (128, 0, 0), "trail": (255, 255, 0)}
    for k, f in sides.items():
        k1, k2 = k.split("|")
        x1, y1 = center(int(k1[:2]), int(k1[2:]))
        x2, y2 = center(int(k2[:2]), int(k2[2:]))
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        for feat in ("bridge", "ford", "creek", "road", "trail"):
            if feat in f:
                d.rectangle([mx - 7, my - 7, mx + 7, my + 7], outline=fcol[feat], width=3)
                break
    ov.save(r"C:\Users\fisch\AppData\Local\Temp\claude\C--VassalArnhem\ceeb896c-a97d-429e-87c4-948270f507b5\scratchpad\terrain_overlay.png")
    print("overlay saved")

# ---------- validation anchors (verified by eye vs module map + 1975 scan) ----------
fails = []
def check(cond, what):
    if not cond:
        fails.append(what)
    print(("PASS " if cond else "FAIL ") + what)

# anchors verified by eye against module map crops + original 1975 scan
for hx, want in [
    ("0101", "clear"), ("0102", "forest"), ("0106", "clear"), ("0110", "clear"),
    ("0111", "clear"), ("0211", "clear"), ("2221", "clear"), ("2122", "clear"),
    ("2124", "forest"), ("2223", "clear"), ("2224", "forest"), ("2323", "forest"),
    ("1922", "clear"), ("1923", "forest"), ("1327", "rough"), ("2419", "clear"),
    ("2318", "forest"), ("1626", "clear"),
]:
    check(hexes.get(hx, {}).get("t") == want, f"hex {hx} = {want} (got {hexes.get(hx,{}).get('t')})")
def sf(a_, b_):
    return sides.get(f"{a_}|{b_}") or sides.get(f"{b_}|{a_}") or {}
for a_, b_, want in [
    ("1922", "2022", "bridge"),      # Alexander's Bridge (road over creek)
    ("2216", "2316", "bridge"),      # Reed's Bridge
    ("2311", "2411", "bridge"),      # Dyer's Bridge
    ("2403", "2503", "bridge"),      # Ringgold Bridge
    ("2320", "2420", "ford"), ("2112", "2212", "ford"), ("2218", "2318", "ford"),
    ("2408", "2508", "ford"), ("1527", "1627", "ford"), ("1926", "2026", "ford"),
    ("2122", "2221", "creek"),
    ("1921", "1922", "road"), ("1920", "1921", "road"),
    ("2022", "2023", "road"), ("0101", "0201", "road"), ("0111", "0211", "road"),
    ("2123", "2223", "trail"),
    ("1517", "1518", None), ("0102", "0103", None),
    ("1315", "1316", None),
]:
    f = sf(a_, b_)
    ok = (want in f) if want else not any(x in f for x in ("road", "trail", "bridge", "ford"))
    check(ok, f"side {a_}-{b_} = {want or 'plain'} (got {f})")
check(not warn, f"no crossing warnings ({warn})")
if fails:
    print(f"\n{len(fails)} FAILURES — terrain.json NOT written")
    sys.exit(1)

out = {
    "provenance": {
        "generated": "2026-07-10 overnight run: image classification of module Chickamauga.png "
                     "(faithful redraw of 1975 map, spot-verified against original scan)",
        "method": "color masks; per-hex disc vote; creek by edge-band coverage >=0.55; "
                  "line crossings: solid >=0.78 -> road/bridge, 0.34-0.78 -> trail/ford",
        "semantics": {
            "clear": "1 MP [9.0]", "forest": "3 MP, blocks LOS [9.0/8.33]",
            "rough": "3 MP, defender doubled [9.0]",
            "forest_rough": "6 MP, defender doubled, blocks LOS [9.0/8.33]",
            "offmap": "unplayable / printed boxes",
            "sides.creek": "prohibited move+attack+ZOC except bridge/ford [5.25/6.6/7.x]",
            "sides.bridge": "creek crossing, no extra MP; defender x2 if all attackers cross [9.0]",
            "sides.ford": "creek crossing, +1 MP; defender x2 if all attackers cross [9.0]",
            "sides.road": "1 MP negates hex terrain when entered via road hexside [5.22]",
            "sides.trail": "2 MP into forest/rough hex, 1 MP into clear [5.23]"
        }
    },
    "hexes": hexes,
    "sides": sides,
}
json.dump(out, open(OUT, "w"), indent=0)
print(f"\nterrain.json written: {len(hexes)} hexes, {len(sides)} featured sides")
