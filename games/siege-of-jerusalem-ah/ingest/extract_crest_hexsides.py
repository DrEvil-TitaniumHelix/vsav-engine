"""SoJ support tool - derive Crest hexsides from the printed map art [11.17].

RULE (rulebook p.9, 11.17): "Slope hexsides which are dark brown on one side and
Clear on the other are Crest hexsides." Printed examples: RR8-SS8 IS a crest
(RR8 clear + higher, SS8 slope); the 9.52 LOF example puts RR48 "at the crest
of the slope" above TT46 (so SS47|RR48 must classify crest too).

METHOD (validated on contact sheets, crest_sheets/ - see CRESTS_VERIFIED.md)
  Candidates = every slope|clear neighbouring pair in terrain.json (997) - the
  only pairs 11.17's criterion can apply to. The slope art shades its uphill
  edge dark brown (the crest) and fades toward the base, so per hexside we
  sample 15 points along the shared side, each point paired: luminance just
  inside the slope hex (offsets 7+12 px, 3x3 mean) vs just inside the clear
  hex (offset 9 px). A point is "dark" when clear-side minus slope-side
  luminance > 28. dark_frac = dark points / 15.
      CREST  <=>  dark_frac >= 0.50   ("dark brown on one side" = the shading
                                       abuts the MAJORITY of the hexside)
  The distribution is strongly bimodal (781 sides <= 0.27, 167 >= 0.53, only
  49 between 0.3 and 0.5); contact-sheet adjudication of the whole 0.30-0.80
  band plus 24 validation samples agreed with the threshold in every case.

CAVEAT recorded in the output: out-of-scope strongpoint hexes that bite-3
  zeroed to 'clear' (their printed art is a fort/bastion structure) can fake a
  dark strip - observed at W48|X48 and JJ45|JJ44, both far outside the Gallus
  battlefield bound. All such contamination sits on unplayable hexes, so the
  in-scope crest set is clean.

Usage:  python extract_crest_hexsides.py       (writes crest_hexsides.json)
"""
import json
import math
import os

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
NPT = 15
DARK_DELTA = 28.0
THRESHOLD = 0.50


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
    img_path = next(p for p in MAP_CANDIDATES if os.path.exists(p))
    img = np.asarray(Image.open(img_path).convert('L'))

    def lum_at(x, y):
        return float(img[int(y) - 1:int(y) + 2, int(x) - 1:int(x) + 2].mean())

    hexes = json.load(open(TERRAIN, encoding='utf-8'))['hexes']
    rows = []
    for k, v in hexes.items():
        if v.get('t') != 'slope':
            continue
        for nk in neighbours(k):
            nv = hexes.get(nk)
            if not nv or nv.get('t') != 'clear':
                continue
            scx, scy = centre(k)
            ccx, ccy = centre(nk)
            mx, my = (scx + ccx) / 2.0, (scy + ccy) / 2.0
            ux, uy = scx - mx, scy - my
            ul = math.hypot(ux, uy)
            ux, uy = ux / ul, uy / ul
            tx, ty = -uy, ux
            hl = SX / 2.0 * 0.66
            dark = 0
            for i in range(NPT):
                t = (i / (NPT - 1) * 2.0 - 1.0) * hl
                s1 = lum_at(mx + ux * 7 + tx * t, my + uy * 7 + ty * t)
                s2 = lum_at(mx + ux * 12 + tx * t, my + uy * 12 + ty * t)
                cpt = lum_at(mx - ux * 9 + tx * t, my - uy * 9 + ty * t)
                if cpt - (s1 + s2) / 2.0 > DARK_DELTA:
                    dark += 1
            rows.append(dict(slope=name_of(k), clear=name_of(nk),
                             key='|'.join(sorted([k, nk])),
                             dark_frac=round(dark / NPT, 2)))

    crests = [r for r in rows if r['dark_frac'] >= THRESHOLD]
    cal = {(r['slope'], r['clear']): r['dark_frac'] for r in rows}
    checks = [
        ('RR8-SS8 printed crest [11.17]', cal.get(('SS8', 'RR8'), -1) >= THRESHOLD),
        ('SS47|RR48 = the 9.52 example crest', cal.get(('SS47', 'RR48'), -1) >= THRESHOLD),
        ('SS7|SS6 band-tip fade is NOT crest', cal.get(('SS7', 'SS6'), 1) < THRESHOLD),
        ('TT8|UU8 band base is NOT crest', cal.get(('TT8', 'UU8'), 1) < THRESHOLD),
    ]
    out = dict(
        source=os.path.basename(img_path) + ' (printed map scan, module SOJ)',
        rule='11.17 - Slope hexsides dark brown on one side and Clear on the '
             'other are Crest hexsides; attacker Melee strength halved '
             'attacking across a Crest vs a Ground-level non-Slope defender',
        method='per-hexside paired luminance sampling, dark_frac = fraction '
               'of 15 points where clear-side minus slope-side luminance > '
               f'{DARK_DELTA:g}; crest <=> dark_frac >= {THRESHOLD}',
        audit='bimodal distribution; full 0.30-0.80 band + 24 validation '
              'samples adjudicated on contact sheets (crest_sheets/), '
              'threshold agreed in every case',
        caveat='out-of-Gallus-bound strongpoints zeroed to clear (W48|X48, '
               'JJ45|JJ44 areas) can fake a dark strip via structure art - '
               'all observed instances are on unplayable hexes',
        candidates=len(rows),
        crest_count=len(crests),
        calibration={n: 'PASS' if ok else 'FAIL' for n, ok in checks},
        crests=sorted(({'key': r['key'], 'slope': r['slope'],
                        'clear': r['clear'], 'dark_frac': r['dark_frac']}
                       for r in crests), key=lambda r: r['key']),
    )
    with open(os.path.join(HERE, 'crest_hexsides.json'), 'w') as fh:
        json.dump(out, fh, indent=1)
    print('candidates %d  crests %d' % (len(rows), len(crests)))
    for n, ok in checks:
        print('CALIBRATION  %-40s %s' % (n, 'PASS' if ok else 'FAIL'))
    assert all(ok for _, ok in checks), 'calibration failed'


if __name__ == '__main__':
    main()
