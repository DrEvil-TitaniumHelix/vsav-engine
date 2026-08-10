"""SoJ support tool - derive interior-road hexsides from the printed map art.

RULES SERVED (rulebook p.8 + p.11, The General 26-4 p.13):
  8.94  "All roads outside Jerusalem are assumed to have been destroyed ...
         Roads within the city can be used by both sides"
  8.95  "Cavalry and Artillery may enter or exit Built-up hexes only through
         road hexsides"
  12.4 / General 26-4 p.13: road movement rate = 1/2 MF.

SCOPE: Gallus battlefield city interior = terrain.json areas.new_city (383
  hexes, the in-wall New City census area). Roads drawn OUTSIDE the walls are
  destroyed by 8.94 and deliberately not extracted; roads south of the Second
  Wall (Tyropean City / Old City) are off the Gallus battlefield (A4 bound).
  Candidate set = all 1041 hexside pairs with BOTH hexes in new_city.
  (An earlier 11-pair probe file mixed in off-battlefield Tyropean sides -
  superseded by this full pass.)

METHOD (validated on contact sheets, road_sheets/ - see ROADS_VERIFIED.md)
  Road art = a smooth pale-cream band ~14-18 px wide, clearly brighter than
  the speckled tan ground (lum ~163-169 vs ~117-143) and WARM (R-B ~55-70),
  which separates it from grey structure art (R-B ~14-21). The dark hexside
  border line overprints the road exactly where it crosses, so each side is
  sampled INSIDE both hexes: NPT points along the side, per point a 3x3 mean
  RGB at perpendicular offsets 6 and 10 px into each hex (brighter of the two
  kept per hex). A point is "road" when BOTH hexes' readings pass
  lum >= LUM_T and warm >= WARM_T - a road that merely touches a hexside
  without crossing it lights only one side and is rejected.
      ROAD  <=>  longest consecutive run of road points >= RUN_T
  (RUN_T consecutive points ~= the narrowest genuine crossing; single-point
  hits are speckle/corner noise.)

Usage:  python extract_road_hexsides.py          (writes road_hexsides.json)
        python extract_road_hexsides.py --dump   (also dumps every side score)
"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
MAP_CANDIDATES = [
    os.path.join(HERE, 'extracted', 'images', 'SoJ_map.jpg'),
    r'C:\VassalSoJ\extracted\images\SoJ_map.jpg',
]
TERRAIN = r'C:\VassalArnhem\games\siege-of-jerusalem-ah\terrain.json'

# Grid fit (validated: gates overlay extractor + render_hex_crop)
DX, X0, DY, Y0 = 71.0749, 207.60, 82.2902, -1840.52
SX = DX * 2.0 / 3.0
DIRS = [(0, -1), (0, 1), (1, -1), (1, 0), (-1, 0), (-1, 1)]
NPT = 21
OFFSETS = (6.0, 10.0)
LUM_T = 150.0
WARM_T = 35.0
RUN_T = 4


def centre(key):
    c, r = int(key[:2]), int(key[2:])
    return DX * c + X0, DY * ((r - c // 2) + c / 2.0) + Y0


def neighbours(key):
    c, r = int(key[:2]), int(key[2:])
    N = r - c // 2
    for dc, dn in DIRS:
        c2, n2 = c + dc, N + dn
        yield f'{c2:02d}{n2 + c2 // 2:02d}'


def col_letters(c):
    return chr(64 + c) if c <= 26 else chr(64 + c - 26) * 2


def name_of(key):
    c, r = int(key[:2]), int(key[2:])
    return '%s%d' % (col_letters(c), r - c // 2)


def main():
    dump = '--dump' in sys.argv
    img_path = next(p for p in MAP_CANDIDATES if os.path.exists(p))
    img = np.asarray(Image.open(img_path).convert('RGB')).astype(float)

    def rgb_at(x, y):
        return img[int(y) - 1:int(y) + 2, int(x) - 1:int(x) + 2] \
            .reshape(-1, 3).mean(axis=0)

    terrain = json.load(open(TERRAIN, encoding='utf-8'))
    nc = set(terrain['areas']['new_city'])

    def side_ok(x, y, ux, uy, sgn):
        """Brightest inside-hex reading at this side position; sgn picks
        which hex (+1 toward the first hex, -1 toward the second)."""
        best = None
        for off in OFFSETS:
            p = rgb_at(x + sgn * ux * off, y + sgn * uy * off)
            if best is None or p.mean() > best.mean():
                best = p
        lum = best.mean()
        warm = best[0] - best[2]
        return lum >= LUM_T and warm >= WARM_T

    rows = []
    for k in sorted(nc):
        for nk in neighbours(k):
            if nk not in nc or nk < k:
                continue
            acx, acy = centre(k)
            bcx, bcy = centre(nk)
            mx, my = (acx + bcx) / 2.0, (acy + bcy) / 2.0
            ux, uy = acx - mx, acy - my
            ul = math.hypot(ux, uy)
            ux, uy = ux / ul, uy / ul
            tx, ty = -uy, ux
            hl = SX / 2.0 * 0.85
            run = best_run = 0
            for i in range(NPT):
                t = (i / (NPT - 1) * 2.0 - 1.0) * hl
                x, y = mx + tx * t, my + ty * t
                if side_ok(x, y, ux, uy, +1) and side_ok(x, y, ux, uy, -1):
                    run += 1
                    best_run = max(best_run, run)
                else:
                    run = 0
            rows.append(dict(a=name_of(k), b=name_of(nk),
                             key='|'.join(sorted([k, nk])),
                             run=best_run))

    roads = [r for r in rows if r['run'] >= RUN_T]
    hist = {}
    for r in rows:
        hist[r['run']] = hist.get(r['run'], 0) + 1
    cal = {(r['a'], r['b']): r['run'] for r in rows}
    cal.update({(b, a): v for (a, b), v in list(cal.items())})
    checks = [
        ("Z24|Z25 Women's Gate road runs south", cal.get(('Z24', 'Z25'), -1) >= RUN_T),
        ("Z25|Z26 road into the builtup block", cal.get(('Z25', 'Z26'), -1) >= RUN_T),
        ("Z26|Z27 road out of the builtup block", cal.get(('Z26', 'Z27'), -1) >= RUN_T),
        ("Z25|AA24 NE fork (earlier probe 0.83)", cal.get(('Z25', 'AA24'), -1) >= RUN_T),
        ("AA23|AA24 clean tan is NOT road", cal.get(('AA23', 'AA24'), 99) < RUN_T),
    ]
    out = dict(
        source=os.path.basename(img_path) + ' (printed map scan, module SOJ)',
        rule='8.94 roads within the city usable / outside destroyed; 8.95 '
             'Cavalry+Artillery enter/exit Built-up only through road '
             'hexsides; road rate 1/2 MF [12.4, General 26-4 p.13]',
        scope='both hexes in terrain.json areas.new_city (Gallus in-wall '
              'city interior, 383 hexes, 1041 candidate sides). Off-wall '
              'and Tyropean/Old-City roads deliberately excluded (8.94 / '
              'A4 battlefield bound).',
        method='per-hexside paired RGB sampling: %d points along the side, '
               'per point 3x3 mean at %g+%g px inside EACH hex (brighter '
               'kept); point=road iff both hexes read lum>=%g and '
               'warm(R-B)>=%g; side=road iff longest consecutive run >= %d'
               % (NPT, OFFSETS[0], OFFSETS[1], LUM_T, WARM_T, RUN_T),
        audit='run-length histogram + full ambiguous band adjudicated on '
              'contact sheets (road_sheets/), see ROADS_VERIFIED.md',
        candidates=len(rows),
        road_count=len(roads),
        run_histogram={str(k): hist[k] for k in sorted(hist)},
        calibration={n: 'PASS' if ok else 'FAIL' for n, ok in checks},
        roads=sorted(({'key': r['key'], 'a': r['a'], 'b': r['b'],
                       'run': r['run']} for r in roads),
                     key=lambda r: r['key']),
    )
    with open(os.path.join(HERE, 'road_hexsides.json'), 'w') as fh:
        json.dump(out, fh, indent=1)
    if dump:
        with open(os.path.join(HERE, 'road_scan_all.json'), 'w') as fh:
            json.dump(rows, fh, indent=1)
    print('candidates %d  roads %d' % (len(rows), len(roads)))
    print('run histogram:', ' '.join('%d:%d' % (k, hist[k])
                                     for k in sorted(hist)))
    for n, ok in checks:
        print('CALIBRATION  %-42s %s' % (n, 'PASS' if ok else 'FAIL'))
    assert all(ok for _, ok in checks), 'calibration failed'


if __name__ == '__main__':
    main()
