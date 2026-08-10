"""SoJ B8 - final interior-road hexside verdicts -> road_hexsides.json + terrain.json patch.

RULES SERVED (rulebook p.8 + p.11; The General 26-4 p.13):
  8.94  roads within the city usable by both sides; roads outside Jerusalem destroyed
  8.95  Cavalry and Artillery may enter or exit Built-up hexes ONLY through road hexsides
  12.4 / General 26-4 p.13: road movement rate = 1/2 MF

PIPELINE (all evidence local at C:\\VassalSoJ, method mirrors the crest pass):
  1. extract_road_hexsides.py  - detector v1: paired 3x3-mean sampling at 6+10px inside
     both hexes along each of the 1041 new_city-interior hexsides; point = road iff BOTH
     sides read lum>=150 and warm(R-B)>=35; score = longest consecutive run of 21.
     Road art = smooth pale-cream band (lum ~163-169, warm ~55-68) vs speckled tan
     (~117-143, warm ~70-79) and grey structure art (warm ~14-21). The dark hexside
     border line overprints crossings, hence inside-hex sampling.
  2. detector v2 (road_scan_v2.json): per-side footprint-overlap - projected road
     presence 4-14px inside each hex along the side, dilated +-2, longest overlap run.
     Used only to nominate v1=0 sides for review (v2>=10), never to accept alone
     (pale wash areas saturate it).
  3. ADJUDICATION (2026-08-10): every side with v1>=1 or v2>=10 (282 sides) read by eye -
     17 review contact sheets + 8 autopass sheets (road_sheets/), 9 labeled region zooms,
     13 close-up crops for junction knots. Centerline rule: a side is a road hexside iff
     the road's PATH crosses it (band-edge corner slivers, width-straddles and parallel
     riding do NOT count). Verdicts + reasons below are the complete record.

The three verdict tables below are the AUTHORITATIVE hand-audit record; the script
mechanically merges them with the detector output and fails loudly on any drift
(a table key that is not a valid new_city-interior side, or an auto side that
vanishes from the scan).
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
TERRAIN = os.path.join(HERE, '..', 'terrain.json')
SCAN = r'C:\VassalSoJ\road_scan_all.json'          # detector v1 (local evidence)
OUT = os.path.join(HERE, 'road_hexsides.json')

# ---- detector autopasses REJECTED on verification (v1 run >= 4 but NOT a crossing)
AUTO_REJECT = {
    'Q42|R42':  'pale rubble wash W of the Q-road at R42/R43, no coherent band (zoom E)',
    'CC26|CC27': 'pale wash around the printed NEW CITY map text; isolated, no '
                 'continuation either end (zoom F)',
    'II26|JJ26': 'wall-glacis wash N of the II27 gate; close-up shows bare tan, '
                 'no cream band (II26 close-up)',
    'KK25|KK26': 'wash false positive; KK25 close-up shows the whole neighbourhood '
                 'bare tan',
    'NN31|OO30': 'the NN-column road band straddles this boundary; centerline runs '
                 'inside OO30 (OO30 close-up)',
    'Y32|Z31':  'band hugs the Y31/Z31/Y32 corner; Z31 close-up shows Z31 clean - '
                 'the crossing is Y31|Y32',
}

# ---- review-band sides CONFIRMED as crossings (detector v1 run 1-3, art-verified)
REVIEW_CONFIRM = {
    'H41|H42': 'west-wall interior road, band crosses (sheet 00)',
    'H42|H43': 'west-wall interior road (sheet 00)',
    'H43|H44': 'west-wall interior road (sheet 00)',
    'H45|H46': 'west-wall interior road (sheet 00)',
    'I46|J46': 'southern road, band crosses (sheet 00)',
    'J46|J47': 'southern road (sheet 00)',
    'J47|K47': 'southern road (sheet 00)',
    'M47|N46': 'southern road (sheet 00)',
    'R36|S36': 'builtup artery, band crosses lower side (sheet 03, R36 close-up)',
    'S37|T36': 'Q-road link into the T36 junction (zoom A, T36 close-up)',
    'Z28|Z29': "Women's-Gate road, band continues straight S (zoom B art)",
    'Y31|Y32': 'bend fork S leg; Y32+Z31 close-ups show the band passing Y31->Y32',
    'X33|Y32': 'fork leg Y32->X33 (3/20 + Y32 close-up); road art fades at X33 - '
               'dead end as drawn, see open_observations',
    'Z32|AA31': 'inside-wall belt from CC30 gate; band along the wall N side '
                '(zoom D + Z31 close-up bottom edge)',
    'DD22|EE22': 'east road, band crosses through wall-shadowed area (zoom F)',
    'HH23|II23': 'east road, faint print (zoom G)',
    'II23|JJ23': 'east road, faint print (zoom G)',
    'MM20|NN19': 'NE-corner spur, band crosses mid-side (sheet 14, zoom G)',
    'NN23|NN24': 'NN-column road, band crosses (sheet 15, zoom G2)',
    'NN28|NN29': 'NN-column road, band crosses left portion (sheet 15, zoom G2)',
    'KK22|KK23': 'east-road / NE-spur link; band partially masked by print fade, '
                 'confirmed by art + chain continuity (zoom G)',
}

# ---- crossings the detector missed entirely (art + continuity, hand-added)
HAND_ADD = {
    'Q36|R36': 'builtup artery P36->Q36->R36; crossing hidden under building art '
               '(R36 close-up shows the band passing)',
    'S36|T36': 'builtup artery into the T36 junction; crossing suppressed by builtup '
               'shadow at the boundary (T36 close-up, 4-way junction)',
    'W28|W29': 'south spur fork off the NE artery; band passes behind building art '
               '(W29 close-up); connects the W29|X29 crossing (v1=9)',
    'NN30|OO30': 'SE bend of the NN-column road; crossing sits hard against the '
                 'NN30/OO29/OO30 corner (OO30 close-up)',
}

OPEN_OBSERVATIONS = [
    'X33 leg (Y31->Y32->X33) dead-ends as drawn - the band fades SW of X33; possible '
    'bleached continuation toward Damascus W35 entrance. Encoded exactly as visible. '
    'Module-author worksheet item.',
    'Damascus Gate in-city approach: the U36|V36 road ends at V36 - which IS the '
    'gate\'s in-city entrance hex per gates_overlay.json (PREP-2 corrected W35->V36), '
    'i.e. the road is that entrance\'s 8.91 "connecting road". No road side is ever '
    'encoded into a gate hex - entrance hexsides govern gate movement.',
    'W29|X29 south spur ends at X29 (building complex; no coherent band beyond).',
    'Gates reached by roads (via their entrance hexsides, which are separate data): '
    'H40-area west gate, Q49, V42, Womens Gate Z23, Z33, CC30, PP17-area NE corner '
    'gate, Tadi (via OO32), II27/GG17 have bare approaches.',
]

DIRS = [(0, -1), (0, 1), (1, -1), (1, 0), (-1, 0), (-1, 1)]


def col_index(s):
    return ord(s) - 64 if len(s) == 1 else 26 + ord(s[0]) - 64


def key_of(name):
    m = re.match(r'([A-Za-z]+)(\d+)$', name)
    L = col_index(m.group(1).upper())
    N = int(m.group(2))
    return '%02d%02d' % (L, N + L // 2)


def side_key(name_pair):
    a, b = name_pair.split('|')
    return '|'.join(sorted([key_of(a), key_of(b)]))


def main():
    terrain = json.load(open(TERRAIN, encoding='utf-8'))
    nc = set(terrain['areas']['new_city'])
    scan = json.load(open(SCAN))
    by_name = {'%s|%s' % tuple(sorted((r['a'], r['b']))): r for r in scan}

    # validate every hand table key is a real candidate side
    for table, tag in ((AUTO_REJECT, 'AUTO_REJECT'),
                       (REVIEW_CONFIRM, 'REVIEW_CONFIRM'), (HAND_ADD, 'HAND_ADD')):
        for name in table:
            nm = '%s|%s' % tuple(sorted(name.split('|')))
            assert nm in by_name, '%s key %s is not a scanned candidate side' % (tag, name)
            a, b = nm.split('|')
            ka, kb = key_of(a), key_of(b)
            assert ka in nc and kb in nc, '%s key %s not inside new_city' % (tag, name)

    roads = []
    for nm, r in sorted(by_name.items()):
        run = r['run']
        rej = {'%s|%s' % tuple(sorted(k.split('|'))): v
               for k, v in AUTO_REJECT.items()}
        cfm = {'%s|%s' % tuple(sorted(k.split('|'))): v
               for k, v in REVIEW_CONFIRM.items()}
        add = {'%s|%s' % tuple(sorted(k.split('|'))): v
               for k, v in HAND_ADD.items()}
        if run >= 4 and nm not in rej:
            roads.append((nm, run, 'auto', 'detector run %d, verified on autopass '
                                           'sheets/zooms' % run))
        elif nm in cfm:
            assert run < 4, '%s listed as REVIEW_CONFIRM but run=%d' % (nm, run)
            roads.append((nm, run, 'review', cfm[nm]))
        elif nm in add:
            roads.append((nm, run, 'hand', add[nm]))

    n_auto = sum(1 for r in roads if r[2] == 'auto')
    n_rev = sum(1 for r in roads if r[2] == 'review')
    n_hand = sum(1 for r in roads if r[2] == 'hand')
    assert (n_auto, n_rev, n_hand) == (80, 21, 4), \
        'verdict drift: auto=%d review=%d hand=%d (expected 80/21/4)' % \
        (n_auto, n_rev, n_hand)

    # connectivity audit: every road side must touch another road side or be a
    # documented terminus (gate approach / evidence-limit dead end)
    # degree-1 road hexes, each with its documented reason to end there:
    # Z24 (Women's Gate entrance), Q48 (Q49 gate), U42 (V42 gate), Z32 (Z33 gate),
    # BB30 (CC30 gate), OO18 (NE corner gate), OO32 (Tadi Gate), V36 (Damascus
    # approach, rut-mark entrance), X33 + X29 (art dead ends, open_observations)
    TERMINI = {key_of(n) for n in
               ('Z24', 'Q48', 'U42', 'Z32', 'BB30', 'OO18', 'OO32', 'V36',
                'X33', 'X29')}
    hexes_in = {}
    for nm, _, _, _ in roads:
        ka, kb = side_key(nm).split('|')
        hexes_in.setdefault(ka, 0)
        hexes_in.setdefault(kb, 0)
        hexes_in[ka] += 1
        hexes_in[kb] += 1
    lonely = [h for h, n in hexes_in.items() if n == 1 and h not in TERMINI]
    assert not lonely, 'undocumented road termini: %s' % lonely

    out = dict(
        source='SoJ_map.jpg (printed map scan, module SOJ)',
        rule='8.94 roads within the city usable / outside destroyed; 8.95 Cavalry+'
             'Artillery enter/exit Built-up only through road hexsides; road rate '
             '1/2 MF [12.4; The General 26-4 p.13]',
        scope='both hexes in terrain.json areas.new_city (Gallus in-wall city '
              'interior, 383 hexes, 1041 candidate sides); off-wall and Tyropean/'
              'Old-City roads excluded by 8.94 / the A4 battlefield bound',
        method='detector (extract_road_hexsides.py at C:\\VassalSoJ: paired bright+'
               'warm band sampling inside both hexes, run>=4 of 21) + full visual '
               'adjudication of all 282 signal sides on contact sheets, 9 region '
               'zooms and 13 close-ups; centerline rule - band-edge corner slivers, '
               'width straddles and parallel riding rejected',
        audit='verdict tables with reasons in ingest/build_road_verdicts.py; sheet/'
              'zoom/close-up PNGs local at C:\\VassalSoJ\\road_sheets and the '
              'session scratchpad; ROADS_VERIFIED.md (local literature/) narrates '
              'the full network',
        counts=dict(candidates=len(by_name), road=len(roads), auto=n_auto,
                    review_confirmed=n_rev, hand_added=n_hand,
                    auto_rejected=len(AUTO_REJECT)),
        auto_rejected={k: v for k, v in sorted(AUTO_REJECT.items())},
        open_observations=OPEN_OBSERVATIONS,
        roads=[dict(names=nm, key=side_key(nm), run=run, basis=basis, how=how)
               for nm, run, basis, how in roads],
    )
    with open(OUT, 'w') as fh:
        json.dump(out, fh, indent=1)

    # patch terrain.json sides
    sides = terrain['sides']
    added = 0
    for r in out['roads']:
        rec = sides.setdefault(r['key'], {})
        if not rec.get('road'):
            rec['road'] = True
            added += 1
    for k, rec in sides.items():
        if rec.get('road') and not any(r['key'] == k for r in out['roads']):
            raise SystemExit('stale road flag on %s' % k)
    terrain['provenance']['amended4'] = (
        '2026-08-10 B8/M.6: interior-road flags on %d hexsides per '
        'ingest/road_hexsides.json (build_road_verdicts.py; 8.94/8.95/12.4; '
        'detector + full contact-sheet adjudication, centerline rule). '
        'known_limits roads entry retired.' % len(out['roads']))
    terrain['provenance']['known_limits'] = [
        k for k in terrain['provenance']['known_limits']
        if 'interior roads' not in k]
    with open(TERRAIN, 'w', encoding='utf-8') as fh:
        json.dump(terrain, fh, indent=1)
    print('roads %d (auto %d / review %d / hand %d), rejected autopasses %d; '
          'terrain.json: %d side flags written' %
          (len(roads), n_auto, n_rev, n_hand, len(AUTO_REJECT), added))


if __name__ == '__main__':
    main()
