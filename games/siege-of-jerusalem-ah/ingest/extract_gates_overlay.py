"""
PREP-2 support tool — extract the authoritative Gate / Gate-Entrance data from the
module's "Gates Overlay.png" (4051x5656 RGBA, pixel-registered to SoJ_map.jpg).

WHAT THE OVERLAY IS
  buildFile.xml: <MapShader name="Gates Overlay" image="Gates Overlay.png"
                 boardList="Main Map" pattern="Custom Image" scaleImage="true" hotkey="F1"/>
  Its only content is (a) red triangles and (b) one block of black text.
  The black text sits inside the printed TERRAIN KEY panel at C29/C30 and reads
  "Gate Entrance"; the red triangle beside it at C30 is the key's sample symbol.
  So the module author himself labels the red triangle = GATE ENTRANCE.

ARROW GEOMETRY (measured, not assumed — fitted from the 44 isolated arrows)
  Each arrow is an isoceles triangle drawn INSIDE the entrance hex:
    base  ~37 px wide, sitting ~10 px inside the shared hexside
    apex  ~48 px further in, pointing AWAY from the gate hex
  => gate hex = the neighbour on the far side of the arrow's base.

METHOD
  1. red mask -> connected components
  2. k = round(area / 905) arrows per component (arrows of adjacent gates touch)
  3. k>1: matching-pursuit with the empirical template to seed, then nearest-seed split
  4. per arrow: convex hull -> max-area triangle -> shortest edge = base, opposite
     vertex = apex -> gate direction = the hex-neighbour direction most opposed to
     (base_mid -> apex).  Discrimination margin is ~0.35-0.50 (next-best direction),
     i.e. unambiguous.

VALIDATION
  Rule 8.91 prints one worked example: "Susa Gate (QQ36) ... RR35 and PP37".
  This script derives exactly RR35 and PP37 for QQ36 without being told.

Usage:  python extract_gates_overlay.py            (writes gates_overlay.json)
"""
import json, math, os
import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.spatial import ConvexHull

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(HERE, 'extracted', 'images')
MAP_W, MAP_H = 4051, 5656

# Grid: identical to games/siege-of-jerusalem-ah/game.json ("colletter_diag"),
# letters 1-based (A=1). x = dx*L + x0 ; y = dy*(N + L/2) + y0
DX, X0, DY, Y0 = 71.0749, 207.60, 82.2902, -1840.52
LET = ['A','B','C','D','E','F','G','H','I','J','K','L','M','N','O','P','Q','R','S','T',
       'U','V','W','X','Y','Z','AA','BB','CC','DD','EE','FF','GG','HH','II','JJ','KK',
       'LL','MM','NN','OO','PP','QQ','RR','SS','TT','UU','VV','WW','XX']
DIRS = {'N': (0, -1), 'S': (0, 1), 'NE': (1, -1), 'SE': (1, 0), 'NW': (-1, 0), 'SW': (-1, 1)}

ctr = lambda L, N: (DX * L + X0, DY * (N + L / 2) + Y0)
nm = lambda L, N: '%s%d' % (LET[L - 1], N)


def hex_of(px, py):
    best = None
    Lf = (px - X0) / DX
    for L in range(max(1, int(Lf) - 1), min(51, int(Lf) + 3)):
        nf = (py - Y0) / DY - L / 2
        for N in (math.floor(nf), math.floor(nf) + 1):
            cx, cy = ctr(L, N)
            d = math.hypot(px - cx, py - cy)
            if best is None or d < best[0]:
                best = (d, L, N)
    return best[1], best[2]


def red_mask():
    a = np.array(Image.open(os.path.join(IMG, 'Gates Overlay.png')))
    assert a.shape[:2] == (MAP_H, MAP_W), a.shape
    al, rgb = a[:, :, 3], a[:, :, :3].astype(int)
    return (al > 32) & (rgb[:, :, 0] > 150) & (rgb[:, :, 1] < 110) & (rgb[:, :, 2] < 110)


def max_area_triangle(pts):
    hp = pts[ConvexHull(pts).vertices]
    k, best = len(hp), None
    for i in range(k):
        for j in range(i + 1, k):
            for m in range(j + 1, k):
                A = abs((hp[j, 0] - hp[i, 0]) * (hp[m, 1] - hp[i, 1]) -
                        (hp[m, 0] - hp[i, 0]) * (hp[j, 1] - hp[i, 1])) / 2
                if best is None or A > best[0]:
                    best = (A, i, j, m)
    return hp[list(best[1:])]


def fit_template(red):
    """Average the isolated arrows into a hexside-local occupancy template."""
    lab, n = ndimage.label(red, np.ones((3, 3)))
    sizes = ndimage.sum(red, lab, range(1, n + 1))
    acc, cnt, O = np.zeros((140, 140)), 0, 70
    for i in range(1, n + 1):
        if not (850 <= sizes[i - 1] <= 960):
            continue
        ys, xs = np.where(lab == i)
        pts = np.c_[xs, ys].astype(float)
        ent, _, gd, _, _ = arrow_axis(pts)
        L, N = ent
        Ex, Ey = ctr(L, N)
        Gx, Gy = ctr(L + DIRS[gd][0], N + DIRS[gd][1])
        ux, uy = Ex - Gx, Ey - Gy
        ul = math.hypot(ux, uy); ux, uy = ux / ul, uy / ul
        nx, ny = -uy, ux
        mx, my = (Ex + Gx) / 2, (Ey + Gy) / 2
        iu = np.round((pts[:, 0] - mx) * ux + (pts[:, 1] - my) * uy + O).astype(int)
        inn = np.round((pts[:, 0] - mx) * nx + (pts[:, 1] - my) * ny + O).astype(int)
        ok = (iu >= 0) & (iu < 140) & (inn >= 0) & (inn < 140)
        acc[iu[ok], inn[ok]] += 1
        cnt += 1
    return (acc / cnt) >= 0.55, cnt


def arrow_axis(pts):
    """-> (entrance L,N), gate (L,N), gate_dir, alignment, margin"""
    tri = max_area_triangle(pts)
    e = [math.dist(tri[1], tri[2]), math.dist(tri[2], tri[0]), math.dist(tri[0], tri[1])]
    ai = int(np.argmin(e))
    apex = tri[ai]
    oth = [tri[t] for t in range(3) if t != ai]
    bm = ((oth[0][0] + oth[1][0]) / 2, (oth[0][1] + oth[1][1]) / 2)
    v = (apex[0] - bm[0], apex[1] - bm[1])
    vl = math.hypot(*v); u = (v[0] / vl, v[1] / vl)
    L, N = hex_of(pts[:, 0].mean(), pts[:, 1].mean())
    Ex, Ey = ctr(L, N)
    sc = []
    for d in DIRS:
        Gx, Gy = ctr(L + DIRS[d][0], N + DIRS[d][1])
        gx, gy = Gx - Ex, Gy - Ey
        sc.append(((u[0] * gx + u[1] * gy) / math.hypot(gx, gy), d))
    sc.sort()
    gd = sc[0][1]
    return (L, N), (L + DIRS[gd][0], N + DIRS[gd][1]), gd, -sc[0][0], sc[1][0] - sc[0][0]


def main():
    red = red_mask()
    core, nfit = fit_template(red)
    O = 70
    cyy, cxx = np.where(core)
    cu, cn = cyy - O, cxx - O
    C = len(cu)

    slots = []
    for L in range(1, 51):
        for N in range(-2, 98):
            Gx, Gy = ctr(L, N)
            for d, (dL, dN) in DIRS.items():
                if not (1 <= L + dL <= 50):
                    continue
                Ex, Ey = ctr(L + dL, N + dN)
                ux, uy = Ex - Gx, Ey - Gy
                ul = math.hypot(ux, uy); ux, uy = ux / ul, uy / ul
                nx, ny = -uy, ux
                mx, my = (Ex + Gx) / 2, (Ey + Gy) / 2
                px = np.round(mx + cu * ux + cn * nx).astype(int)
                py = np.round(my + cu * uy + cn * ny).astype(int)
                if px.min() < 0 or py.min() < 0 or px.max() >= MAP_W or py.max() >= MAP_H:
                    continue
                if red[py, px].sum() < 0.3 * C:
                    continue
                slots.append((py, px, px.mean(), py.mean()))

    lab, n = ndimage.label(red, np.ones((3, 3)))
    sizes = ndimage.sum(red, lab, range(1, n + 1))
    arrows = []
    for i in range(1, n + 1):
        S = int(sizes[i - 1])
        if S < 300:
            continue
        m = (lab == i)
        k = max(1, int(round(S / 905.0)))
        ys, xs = np.where(m)
        pts = np.c_[xs, ys].astype(float)
        if k == 1:
            pieces = [pts]
        else:
            work = m.copy(); picked = []
            cand = [s for s in slots if m[s[0], s[1]].sum() > 0.25 * C]
            for _ in range(k):
                best = None
                for s in cand:
                    if any(s is p for p in picked):
                        continue
                    fr = float(work[s[0], s[1]].sum()) / C
                    if best is None or fr > best[0]:
                        best = (fr, s)
                if best is None or best[0] < 0.30:
                    break
                picked.append(best[1]); work[best[1][0], best[1][1]] = False
            cents = np.array([[s[2], s[3]] for s in picked])
            asg = ((pts[:, None, :] - cents[None, :, :]) ** 2).sum(2).argmin(1)
            pieces = [pts[asg == j] for j in range(len(picked))]
        for p in pieces:
            if len(p) < 300:
                continue
            ent, gate, gd, align, margin = arrow_axis(p)
            arrows.append(dict(entrance=nm(*ent), gate=nm(*gate), dir_gate_to_entrance={
                'N': 'S', 'S': 'N', 'NE': 'SW', 'SW': 'NE', 'NW': 'SE', 'SE': 'NW'}[gd],
                align=round(align, 3), margin=round(margin, 3), px=len(p)))

    gates = {}
    for a in arrows:
        gates.setdefault(a['gate'], []).append(a)
    out = dict(
        source='extracted/images/Gates Overlay.png (module SOJ 3.0.0, Rob McRae)',
        semantics='red triangle = "Gate Entrance" (per the overlay\'s own legend text at C29/C30)',
        rule='8.91 — movement in/out of a Gate at Ground level is limited to the two Entrance hexsides',
        template_fitted_from=nfit,
        arrows=len(arrows),
        gates={g: sorted(a['entrance'] for a in v) for g, v in sorted(gates.items())},
        detail={g: v for g, v in sorted(gates.items())},
    )
    with open(os.path.join(HERE, 'gates_overlay.json'), 'w') as fh:
        json.dump(out, fh, indent=1)

    print('arrows %d   gates %d   (template from %d isolated arrows)' % (len(arrows), len(gates), nfit))
    for g, v in sorted(gates.items()):
        flag = '' if len(v) == 2 else '   <-- NOT 2 (8.91 says exactly two)'
        print('%-7s %s%s' % (g, ' + '.join(sorted(a['entrance'] for a in v)), flag))
    susa = sorted(a['entrance'] for a in gates.get('QQ36', []))
    print('\nCALIBRATION 8.91  QQ36 (Susa Gate) -> %s   expected [PP37, RR35]  %s'
          % (susa, 'PASS' if susa == ['PP37', 'RR35'] else 'FAIL'))


if __name__ == '__main__':
    main()
