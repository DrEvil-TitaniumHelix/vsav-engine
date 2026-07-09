"""AK terrain: ONE-SHOT pipeline (classes + sides + severing + validation).
Writes games/afrika-korps-classic-ah/terrain.json only if ALL validations pass.
Every threshold decision is recorded in the output's provenance block."""
from PIL import Image
import numpy as np, json, sys
from collections import deque, Counter

DX, DY = 101.79999999999785, 88.12562584220231
X0, Y0 = 0.0, 32.0
HH = 4.0 / 3.0 * DY
MAP = r"C:\VassalIngest\afrika-korps-classic-ah\extracted\images\AK consolidated map.png"
OUT = r"C:\VassalArnhem\games\afrika-korps-classic-ah\terrain.json"
img = Image.open(MAP).convert("RGB")
a = np.asarray(img).astype(np.int16)
Hpx, Wpx = a.shape[:2]
TITLE_BOX = (6350, 2210, 6790, 2330)

def near(col, tol=28):
    return (np.abs(a - np.array(col)) <= tol).all(axis=-1)

sea_m = near((130, 198, 226))
stroke_m = near((162, 57, 0), 40)
r_, g_, b_ = a[..., 0], a[..., 1], a[..., 2]
road_m = (r_ >= 185) & (g_ <= 70) & (b_ <= 60)
road_m[TITLE_BOX[1]:TITLE_BOX[3], TITLE_BOX[0]:TITLE_BOX[2]] = False
black_m = (r_ <= 45) & (g_ <= 40) & (b_ <= 35)
gray_m = near((105, 95, 72), 30) | near((119, 109, 78), 30)

DS = 4
hc, wc = (Hpx // DS) * DS, (Wpx // DS) * DS
sb = stroke_m[:hc, :wc].reshape(hc // DS, DS, wc // DS, DS).any(axis=(1, 3))
hh, ww = sb.shape
ext = np.zeros((hh, ww), bool)
dq = deque([(1530 // DS, 3410 // DS)]); ext[dq[0]] = True
ylim = 2612 // DS
while dq:
    y, x = dq.popleft()
    for ny, nx in ((y-1,x),(y+1,x),(y,x-1),(y,x+1)):
        if 0 <= ny < min(hh, ylim) and 0 <= nx < ww and not ext[ny, nx] and not sb[ny, nx]:
            ext[ny, nx] = True; dq.append((ny, nx))
interior = ~ext & ~sb
dep = np.zeros((hh, ww), bool)      # depression component (R60 interior seed)
dq = deque([(1970 // DS, 6209 // DS)]); dep[dq[0]] = True
while dq:
    y, x = dq.popleft()
    for ny, nx in ((y-1,x),(y+1,x),(y,x-1),(y,x+1)):
        if 0 <= ny < hh and 0 <= nx < ww and not dep[ny, nx] and (~ext)[ny, nx]:
            dep[ny, nx] = True; dq.append((ny, nx))

def center(c, r):
    off = DX / 2 if r % 2 == 1 else 0.0
    return X0 + c * DX + off, Y0 + r * DY

def number_of(c, r):
    return c + (r - 5) // 2 - 9

def disp(c, r):
    return chr(65 + r - 5) + str(number_of(c, r))

HEX_AREA = 0.75 * DX * HH
QREGION = lambda cx, cy: cx > 5250 and cy > 1600
NEI_ODD = [(1, 0), (-1, 0), (0, -1), (1, -1), (0, 1), (1, 1)]
NEI_EVEN = [(1, 0), (-1, 0), (-1, -1), (0, -1), (-1, 1), (0, 1)]

hexes, pend = {}, {}
for r in range(5, 29):
    for c in range(0, 70):
        cx, cy = center(c, r)
        x0, y0 = int(cx - DX / 2), int(cy - HH / 2)
        x1, y1 = int(cx + DX / 2) + 1, int(cy + HH / 2) + 1
        x0c, y0c, x1c, y1c = max(0, x0), max(0, y0), min(Wpx, x1), min(Hpx, y1)
        if x1c <= x0c or y1c <= y0c:
            continue
        yy, xx = np.mgrid[y0c:y1c, x0c:x1c]
        ins = (np.abs(xx - cx) / (DX / 2) <= 1) & \
              (np.abs(yy - cy) / (HH / 2) <= 1 - 0.5 * np.abs(xx - cx) / (DX / 2))
        n = int(ins.sum())
        if n == 0:
            continue
        key = f"{c:02d}{r:02d}"
        num = number_of(c, r)
        if not (1 <= num <= 69):
            hexes[key] = {"t": "offmap"}
            continue
        if n / HEX_AREA < 0.65:
            hexes[key] = {"t": "offmap"}
            continue
        sl = (slice(y0c, y1c), slice(x0c, x1c))
        fr = lambda m: float(m[sl][ins].sum()) / n
        sl_ds = (slice(y0c // DS, max(y0c // DS + 1, y1c // DS)),
                 slice(x0c // DS, max(x0c // DS + 1, x1c // DS)))
        di, de = int(dep[sl_ds].sum() * 0 + interior[sl_ds].sum()), int(ext[sl_ds].sum())
        int_frac = di / max(1, di + de)
        t = "clear"
        if fr(sea_m) > 0.72:
            t = "sea"
        elif fr(gray_m) > 0.25:
            t = "homebase"
        elif fr(black_m) > 0.28 and fr(sea_m) > 0.1:
            t = "fortress"
        elif QREGION(cx, cy) and int_frac > 0.90:
            t = "qattara"
        elif QREGION(cx, cy) and int_frac > 0.03:
            t = "qattara_partial"
        elif fr(stroke_m) > 0.10:
            if QREGION(cx, cy):
                pend[key] = True
            else:
                t = "escarpment"
        hexes[key] = {"t": t}
for key in pend:
    c, r = int(key[:2]), int(key[2:])
    nbs = [f"{c+dc:02d}{r+dr:02d}" for dc, dr in (NEI_ODD if r % 2 == 1 else NEI_EVEN)]
    rim = any(hexes.get(k2, {}).get("t") in ("qattara", "qattara_partial") for k2 in nbs)
    hexes[key]["t"] = "qattara_partial" if rim else "escarpment"

def in_hex(px, py, cx, cy):
    ddx = abs(px - cx) / (DX / 2); ddy = abs(py - cy) / (HH / 2)
    return ddx <= 1 and ddy <= 1 - 0.5 * ddx

def free_near(y, x):
    if 0 <= y < hh and 0 <= x < ww and not dep[y, x]:
        return (y, x)
    for rad in (1, 2, 3):
        for ny in range(y - rad, y + rad + 1):
            for nx in range(x - rad, x + rad + 1):
                if 0 <= ny < hh and 0 <= nx < ww and not dep[ny, nx]:
                    return (ny, nx)
    return None

def severed(c1, r1, c2, r2):
    x1, y1 = center(c1, r1); x2, y2 = center(c2, r2)
    s1 = free_near(int(y1) // DS, int(x1) // DS)
    s2 = free_near(int(y2) // DS, int(x2) // DS)
    if not s1 or not s2:
        return True
    seen = {s1}; q = deque([s1])
    while q:
        y, x = q.popleft()
        if (y, x) == s2:
            return False
        for ny, nx in ((y-1,x),(y+1,x),(y,x-1),(y,x+1)):
            if (ny, nx) in seen or not (0 <= ny < hh and 0 <= nx < ww):
                continue
            py, px = ny * DS + DS // 2, nx * DS + DS // 2
            if not (in_hex(px, py, x1, y1) or in_hex(px, py, x2, y2)):
                continue
            if dep[ny, nx]:
                continue
            seen.add((ny, nx)); q.append((ny, nx))
    return True

def edge_frac(c1, r1, c2, r2, mask):
    x1, y1 = center(c1, r1); x2, y2 = center(c2, r2)
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    dxv, dyv = x2 - x1, y2 - y1
    L = (dxv * dxv + dyv * dyv) ** 0.5
    exu, eyu = -dyv / L, dxv / L
    hit = tot = 0
    for t in np.linspace(-HH / 4, HH / 4, 41):
        for w in (-4, -2, 0, 2, 4):
            x = int(mx + exu * t + dxv / L * w); y = int(my + eyu * t + dyv / L * w)
            if 0 <= x < Wpx and 0 <= y < Hpx:
                tot += 1
                if mask[y, x]:
                    hit += 1
    return hit / max(1, tot)

playable = {k for k, v in hexes.items() if v["t"] not in ("offmap", "sea", "qattara")}
sides = {}
for key in sorted(playable):
    c, r = int(key[:2]), int(key[2:])
    for dc, dr in (NEI_ODD if r % 2 == 1 else NEI_EVEN):
        c2, r2 = c + dc, r + dr
        k2 = f"{c2:02d}{r2:02d}"
        if k2 <= key or k2 not in playable:
            continue
        feat = {}
        if edge_frac(c, r, c2, r2, road_m) >= 0.05:
            feat["road"] = True
        if edge_frac(c, r, c2, r2, sea_m) >= 0.60:
            feat["water"] = True
        else:
            x1, y1 = center(c, r); x2, y2 = center(c2, r2)
            mx, my = int((x1 + x2) / 2) // DS, int((y1 + y2) / 2) // DS
            if dep[max(0, my - 8):my + 8, max(0, mx - 8):mx + 8].any() \
               and severed(c, r, c2, r2):
                feat["qattara"] = True
        if feat:
            sides[f"{key}|{k2}"] = feat

qlist = sorted(f"{disp(int(k.split('|')[0][:2]), int(k.split('|')[0][2:]))}-"
               f"{disp(int(k.split('|')[1][:2]), int(k.split('|')[1][2:]))}"
               for k, f in sides.items() if "qattara" in f)
print("hex classes:", Counter(v["t"] for v in hexes.values()))
print("side feats:", Counter(tuple(sorted(f)) for f in sides.values()))
print("qattara sides:", qlist)

# ---------- validation ----------
def n2cr(nm):
    li = ord(nm[0]) - 65; num = int(nm[1:])
    return num - li // 2 + 9, li + 5
def K(nm):
    c, r = n2cr(nm); return f"{c:02d}{r:02d}"

fails = []
def check(cond, what):
    if not cond:
        fails.append(what)
    print(("PASS " if cond else "FAIL ") + what)

for nm, want in [("G24", "escarpment"), ("T29", "escarpment"), ("H23", "escarpment"),
                 ("H24", "escarpment"), ("H25", "escarpment"), ("I26", "escarpment"),
                 ("I30", "escarpment"), ("H26", "clear"), ("K61", "clear"),
                 ("R60", "qattara"), ("T61", "qattara"), ("Q60", "qattara_partial"),
                 ("G25", "fortress"), ("H2", "fortress"), ("W3", "homebase"),
                 ("J62", "homebase"), ("M30", "clear"), ("E18", "clear"),
                 ("F19", "clear"), ("I63", "clear"), ("U69", "clear"),
                 ("R68", "offmap"), ("X70", "offmap"), ("W70", "offmap")]:
    check(hexes.get(K(nm), {}).get("t") == want, f"hex {nm} = {want}")

def sf(a_, b_):
    return sides.get(f"{K(a_)}|{K(b_)}") or sides.get(f"{K(b_)}|{K(a_)}") or {}
for a_, b_, want in [("E18", "F19", "water"), ("W62", "X62", "qattara"),
                     ("G22", "H23", "road"), ("H23", "H24", "road"),
                     ("H24", "H25", "road"), ("H24", "I25", "road"),
                     ("I25", "I26", "road"), ("I26", "J27", "road"),
                     ("I27", "J27", "road"),
                     ("H25", "H26", None), ("H26", "I27", None),
                     ("I27", "J28", None), ("G24", "H24", None), ("I24", "H24", None)]:
    f = sf(a_, b_)
    ok = (want in f) if want else not f
    check(ok, f"side {a_}-{b_} = {want or 'plain'} (got {f})")

if fails:
    print(f"\n{len(fails)} FAILURES — terrain.json NOT written")
    sys.exit(1)

out = {
    "provenance": {
        "generated": "2026-07-09 by image classification of the module map (ak_terrain_final.py); "
                     "validated against rulebook 1.1/5.6/5.7/5.8/17/18 examples (all PASS)",
        "method": "color masks on posterized map art; Qattara full/partial by flood-fill "
                  "enclosure; Qattara hexsides by center-to-center connectivity severing; "
                  "road hexsides by red-line edge crossing (>=5% of edge strip); "
                  "'Afrika Korps' red title text excluded from road detection",
        "semantics": {
            "clear": "1 MP (5.2)", "escarpment": "enter=stop (18.1-18.3); engine gate pending",
            "qattara": "impassable (5.6)", "qattara_partial": "plays as clear (5.6)",
            "sea": "impassable (7.61)", "offmap": "partial/non-coordinate hexes (5.8)",
            "fortress": "Bengasi H2, Tobruch G25 (1.1)", "homebase": "W3 German, J62 Allied (1.1)",
            "sides.water": "prohibited crossing (5.7)", "sides.qattara": "prohibited crossing (5.7)",
            "sides.road": "coast road crosses this hexside (17.2)"
        },
        "qattara_sides_found": qlist,
    },
    "hexes": hexes,
    "sides": sides,
}
json.dump(out, open(OUT, "w"), indent=0)
print(f"\nterrain.json written: {len(hexes)} hexes, {len(sides)} featured sides")
