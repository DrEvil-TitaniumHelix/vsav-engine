"""Assemble games/siege-of-jerusalem-ah/terrain.json from pass2 + hand verification.

Engine coords: col = L (letter index, A=1..Z=26, AA=27..), row = N + L//2.
Hex key = f'{col:02d}{row:02d}'. Display name recovered as letters(col) + (row - col//2).
"""
import json

pass2 = json.load(open(r'C:\VassalSoJ\terrain_pass2.json'))

def Lof(s): return ord(s[0]) - 64 + (26 if len(s) > 1 else 0)
def LN(name):
    Ls = ''.join(c for c in name if c.isalpha()); return Lof(Ls), int(name[len(Ls):])
def letters(L): return chr(64 + L) if L <= 26 else chr(64 + L - 26) * 2
def key(name):
    L, N = LN(name); return f'{L:02d}{N + L // 2:02d}'

# ---------------- hand-verified wall network (2026-08-07/08 zoom passes) ----------------
NORTH_WALL_STRONG = {  # name -> type
 'O50': 'fort', 'M50': 'bastion', 'L50': 'bastion', 'G43': 'fort', 'G40': 'fort',
 'G39': 'fortress',  # Psephinus Tower
 'M36': 'bastion', 'P33': 'bastion', 'S30': 'bastion', 'V27': 'bastion', 'Y24': 'bastion',
 'Z23': 'gate',     # Women's Gate
 'AA22': 'bastion', 'DD19': 'fort', 'GG17': 'fort', 'JJ17': 'bastion', 'MM17': 'bastion',
 'PP17': 'fort', 'PP20': 'bastion', 'PP23': 'bastion', 'QQ25': 'fort', 'QQ29': 'bastion',
}
NORTH_WALL_PLAIN = [  # plain "north_wall" hexes (breach defense 6, North Wall missile row)
 'N50', 'K50', 'J50', 'I50', 'I49', 'I48', 'H48', 'H47', 'G48', 'G47', 'G46', 'G45', 'G44',
 'G42', 'G41', 'H39', 'I38', 'J37', 'K37', 'L37', 'N35', 'O34', 'Q32', 'R31', 'T29', 'U28',
 'W26', 'X25', 'BB21', 'CC20', 'EE19', 'FF18', 'HH17', 'II17', 'KK17', 'LL17', 'NN17',
 'OO17', 'PP18', 'PP19', 'PP21', 'PP22', 'PP24', 'PP25', 'QQ26', 'QQ27', 'QQ28', 'QQ30', 'QQ31',
]
SECOND_WALL_STRONG = {
 'Q49': 'gate',     # west reinforcement gate
 'R49': 'fort', 'R45': 'bastion', 'V42': 'fort', 'V39': 'bastion',
 'W36': 'gate',     # Damascus Gate
 'Z33': 'bastion', 'CC30': 'bastion', 'FF28': 'bastion', 'II27': 'bastion', 'LL27': 'bastion',
 'LL30': 'bastion', 'MM30': 'bastion', 'MM31': 'fortress', 'MM32': 'bastion', 'MM33': 'fortress',
 'OO33': 'gate',    # Tadi Gate (east reinforcement gate)
 'PP33': 'fortress',
}
SECOND_WALL_PLAIN = [
 'R48', 'R47', 'R46', 'S44', 'T44', 'U43', 'V41', 'V40', 'V38', 'W37', 'X35', 'Y34',
 'AA32', 'BB31', 'DD29', 'EE28', 'GG28', 'HH27', 'JJ27', 'KK27', 'LL28', 'LL29', 'NN33',
]
# garrison-area junction strongpoints (in play as terrain, Roman entry PROHIBITED by scenario)
GARRISON = {'P50': 'fort', 'QQ32': 'fort', 'Q50': 'fortress', 'P51': 'gate', 'O51': 'fort',
            'O52': 'fortress', 'O53': 'fortress', 'P52': 'fortress', 'P53': 'fortress',
            'Q51': 'fortress', 'Q52': 'bastion', 'Q53': 'fort', 'R51': 'bastion'}

# hand-verified builtup inside the crescent (zoom passes; VC-relevant)
BUILTUP = [
 'Q36', 'R35', 'R36', 'R37', 'S35', 'S36', 'S37', 'T35',                      # NW lobe
 'V33', 'W32', 'W33', 'W29', 'X27', 'X28', 'X30', 'X31', 'Y26', 'Y27', 'Y29',
 'Y30', 'Y31', 'Z26', 'Z28', 'Z29', 'Z30', 'AA25', 'AA26', 'AA28', 'AA29',   # N central
 'CC23', 'DD22', 'DD23', 'EE20', 'EE21', 'EE22',                              # NE band W end
 'GG22', 'GG23', 'HH22', 'II23', 'JJ20', 'JJ22', 'JJ23', 'KK20', 'LL20',
 'LL21', 'MM20', 'MM21', 'NN19', 'NN20', 'NN23',                              # NE band
]
BUILTUP_UNCERTAIN = ['X26', 'X32', 'Z25', 'T36', 'R38', 'BB24', 'W34', 'MM19']  # Rob worksheet
# pass2 misclassifications to force back to clear
FORCE_CLEAR = ['P34', 'HH16', 'W39', 'V37', 'OO28', 'Z34', 'S45', 'S49', 'T50', 'U50',
               'V50', 'V49', 'W42', 'X48', 'Z47', 'EE43', 'GG46', 'FF47', 'DD51', 'KK50',
               'LL45', 'X36', 'W37', 'GG28', 'JJ27', 'QQ22', 'QQ23', 'RR25', 'V40']
# (S49..LL45 are FIRST-wall / old-city features south of the second wall — out of Gallus
#  bounds; zeroed here rather than encoded wrong. Full-city encoding re-does them.)

# staircase hexsides: strongpoint -> city-side ground neighbors (art-confirmed where noted)
STAIRS = {
 'P33': ['P34', 'Q33'],    # art-confirmed
 'S30': ['S31', 'T30'],    # art-confirmed
 'Y24': ['Y25', 'Z24'],    # art-confirmed
 'AA22': ['AA23', 'BB22'],
 'V27': ['V28', 'W27'],
 'M36': ['M37', 'N36'],
 'M50': ['M49', 'N49'], 'L50': ['L49', 'M49'],
 'G43': ['H42', 'H43'], 'G40': ['H40'], 'G39': ['H40'],
 'DD19': ['DD20'], 'GG17': ['GG18'], 'JJ17': ['JJ18', 'KK18'], 'MM17': ['MM18', 'NN18'],
 'PP17': ['OO18'], 'PP20': ['OO20', 'OO21'],
 'PP23': ['OO23', 'OO24'],  # art-confirmed
 'QQ25': ['PP26'], 'QQ29': ['PP29', 'PP30'],
 'O50': ['O49', 'P49'],
 # second wall (city side = old-city side) — ALL inferred
 'R45': ['S45', 'S46'], 'V42': ['W42', 'W43'], 'V39': ['W38', 'W39'],
 'Z33': ['AA33', 'AA34'], 'CC30': ['CC31', 'DD30'], 'FF28': ['FF29', 'GG29'],
 'II27': ['II28', 'JJ28'], 'LL27': ['MM28'], 'LL30': ['KK31'], 'MM30': ['NN30'],
 'MM31': ['NN31'], 'MM32': ['NN32'], 'MM33': ['MM34'], 'PP33': ['PP34'], 'R49': ['S50'],
}
ART_CONFIRMED_STAIRS = {'P33', 'S30', 'Y24', 'PP23'}

# gate entrance hexsides (ground-level passage)
ENTRANCES = {
 'Z23': ['Z22', 'Z24'],        # Women's Gate: road N-S, art-confirmed
 'W36': ['W35', 'X36'],        # Damascus: N road confirmed; X36 side inferred (connecting road)
 'Q49': ['Q48', 'Q50'],        # west reinforcement gate: inferred
 'OO33': ['OO32', 'PP32'],     # Tadi: inferred
 'P51': ['O51_int', ],         # Yafo — garrison area, out of Gallus bounds; placeholder
}

hexes = {}
for name, info in pass2.items():
    cls = info['cls']
    if name in FORCE_CLEAR: cls = 'clear'
    if cls in ('bastion', 'fort', 'fortress'): cls = 'clear'  # re-add only verified ones below
    if cls == 'edifice': cls = 'builtup'  # no verified edifices in scope; density artifact
    if cls == 'builtup': cls = 'clear'    # re-add only verified ones below
    hexes[name] = cls                     # clear or slope survive from pass2
for n in BUILTUP: hexes[n] = 'builtup'
for n in NORTH_WALL_PLAIN: hexes[n] = 'north_wall'
for n, t in NORTH_WALL_STRONG.items(): hexes[n] = t if t != 'gate' else 'gate_north_wall'
for n in SECOND_WALL_PLAIN: hexes[n] = 'wall'
for n, t in SECOND_WALL_STRONG.items(): hexes[n] = t if t != 'gate' else 'gate_wall'
for n, t in GARRISON.items(): hexes[n] = t

# ---------------- New City crescent (deployment area) by flood fill ----------------
WALLSET = set(NORTH_WALL_PLAIN) | set(NORTH_WALL_STRONG) | set(SECOND_WALL_PLAIN) \
        | set(SECOND_WALL_STRONG) | set(GARRISON)
NB = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, -1), (-1, 1)]
def nm(L, N): return f'{letters(L)}{N}'
seen = set(); stack = ['Z28']
while stack:
    c = stack.pop()
    if c in seen or c in WALLSET or c not in pass2: continue
    seen.add(c)
    L, N = LN(c)
    for dl, dn in NB:
        x = nm(L + dl, N + dn)
        if x not in seen: stack.append(x)
crescent = sorted(seen, key=lambda n: LN(n))
assert len(crescent) < 700, f'flood fill escaped the walls: {len(crescent)}'

out = {
 'provenance': {
   'generated': '2026-08-07/08 by The Vassal: classify_terrain.py pass 2 (calibrated palette + '
                'ring detection on SoJ_map.jpg) + hand verification of every wall/strongpoint/'
                'builtup hex via labeled zoom crops. Grid: x=71.0749*L+207.60, '
                'y=82.2902*(N+L/2)-1840.52 (validated, 3071 v2.3 regions <10px + rulebook '
                'landmarks W36/P51/G39). Hex key = col(L)+row(N+L//2), 2 digits each.',
   'scope': 'Gallus-intro battlefield verified (North Wall arc + Second Wall + New City '
            'crescent + outside approach). Old city south of the Second Wall NOT verified — '
            'strongpoints there zeroed to clear, re-encode on campaign touch.',
   'known_limits': [
     'interior roads NOT encoded (v1.1 with module author verification)',
     'crest hexsides NOT encoded (no slopes in primary battlefield; verify west/east approaches)',
     'builtup_uncertain hexes excluded from builtup (Rob worksheet)',
     'second-wall staircases inferred from pattern, not art-confirmed',
   ],
   'builtup_uncertain': BUILTUP_UNCERTAIN,
   'stairs_art_confirmed': sorted(ART_CONFIRMED_STAIRS),
 },
 'hexes': {key(n): {'t': t, 'name': n} for n, t in sorted(hexes.items(), key=lambda kv: LN(kv[0]))},
 'sides': {},
 'areas': {'new_city': [key(n) for n in crescent]},
}
for sp, targets in STAIRS.items():
    for t in targets:
        if not t.endswith('_int'):
            k = '|'.join(sorted([key(sp), key(t)]))
            out['sides'][k] = {'staircase': True, 'inferred': sp not in ART_CONFIRMED_STAIRS}
for g, targets in ENTRANCES.items():
    for t in targets:
        if not t.endswith('_int'):
            k = '|'.join(sorted([key(g), key(t)]))
            out['sides'].setdefault(k, {})['entrance'] = True

json.dump(out, open(r'games/siege-of-jerusalem-ah/terrain.json', 'w'), indent=0)
import collections
print('hexes:', len(out['hexes']), collections.Counter(v['t'] for v in out['hexes'].values()))
print('sides:', len(out['sides']))
print('crescent size:', len(crescent))
print('crescent builtup check:', sum(1 for n in crescent if hexes.get(n) == 'builtup'), 'of', len(BUILTUP))
EOF = None
