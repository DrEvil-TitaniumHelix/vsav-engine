"""
build_terrain.py - generate terrain_nf.json for the Northern Flank area
(cols 38-74, rows 2-28) from the module's own map art.

Method (mixed, everything auditable):
  elevation    hex-center color sampling -> banded levels 0-5 (map fills
               are flat colors). Adjacent level-delta >= 1 -> minor slope
               hexside, EXCEPT stretches hand-classified as sharp (the
               map hachures them): Santon Hill west face, Raussnitzer
               bluff. No steep-slope symbology occurs in this area.
  roads        HAND-TRACED hex sequences from the map image (tiles at
               1.6x with coordinate overlay). The white-cream road is the
               Olmutz primary road (GMT errata 2000-07-20: THE only
               primary road on the map, A1016-B4613 = our (38,16)-(74,14)
               with the printed-number offset col-28/row-1). All tan
               roads are secondary.
  streams      HAND-TRACED: Bosenitzer brook (NE source, SW past
               Bosenitz, then south along cols 38-39) and Raussnitzer
               brook (south along cols 73-74). A stream hexside = the
               hexside the traced line crosses between consecutive path
               hexes' shared neighbors — encoded directly as hex pairs.
  villages     anchor-seeded (module's own SetupStack names) + building-
               art density.
  woods        tree-green art density.
  bridges      explicit: where a traced road crosses a traced stream.
Validation: render_terrain_overlay.py draws every encoded feature back
onto the map for visual diff; VALIDATION.md records the spot checks.
"""
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "engine"))
import gamespec
import formations as fm
from PIL import Image

game = gamespec.load(HERE)
MAP = Image.open(r"C:\VassalIngest\austerlitz-gmt\assets\map.png").convert("RGB")
C0, C1, R0, R1 = 38, 74, 2, 28
in_area = lambda c, r: C0 <= c <= C1 and R0 <= r <= R1

# --------------------------------------------------------------- elevation
LEVELS = [
    ((240, 240, 240), 0), ((216, 228, 228), 0),
    ((216, 228, 216), 1),
    ((204, 204, 180), 2), ((204, 204, 192), 2),
    ((192, 180, 156), 3), ((204, 192, 168), 3), ((204, 192, 156), 3),
    ((168, 168, 132), 4), ((180, 180, 144), 4),
    ((156, 144, 108), 5),
]
WATER = (168, 192, 228)
dist2 = lambda a, b: sum((x - y) ** 2 for x, y in zip(a, b))


def classify_level(px):
    if dist2(px, WATER) < 2200:
        return "water"
    return min(LEVELS, key=lambda rl: dist2(px, rl[0]))[1]


def hex_level(c, r):
    x, y = game.grid.hex_to_pixel(c, r)
    votes = Counter()
    for dx, dy in ((0, 0), (14, 8), (-14, 8), (14, -8), (-14, -8),
                   (0, 18), (0, -18), (22, 0), (-22, 0)):
        votes[classify_level(MAP.getpixel((x + dx, y + dy)))] += 1
    return votes.most_common(1)[0][0]


elev = {(c, r): hex_level(c, r)
        for c in range(C0, C1 + 1) for r in range(R0, R1 + 1)}

# ------------------------------------------------------------- hand traces
# Path notation: consecutive hexes the feature passes through; expanded to
# adjacent pairs below. Traced from nf_tile_*.png (1.6x, coord overlay).
OLMUTZ_ROAD = [  # primary; west edge -> To Olmutz exit at (74,14)
    (38, 16), (39, 16), (40, 16), (41, 17), (42, 16), (43, 17), (44, 16),
    (45, 17), (46, 16), (47, 16), (48, 16), (49, 16), (50, 16), (51, 16),
    (52, 16), (53, 16), (54, 16), (55, 16), (56, 16), (57, 16), (58, 16),
    (59, 15), (60, 15), (61, 15), (62, 15), (63, 15), (64, 15), (65, 14),
    (66, 15), (67, 14), (68, 15), (69, 14), (70, 15), (71, 14), (72, 15),
    (73, 14), (74, 14),
]
SECONDARY_ROADS = [
    # Brunn road: west edge along row 9 into Bosenitz
    [(38, 9), (39, 9), (40, 9), (41, 9), (42, 9), (43, 9), (44, 9),
     (45, 9), (45, 10)],
    # north road: map edge down into Bosenitz
    [(45, 2), (45, 3), (45, 4), (45, 5), (45, 6), (45, 7), (45, 8),
     (45, 9)],
    # Bosenitz south to the Olmutz road junction
    [(45, 10), (45, 11), (45, 12), (45, 13), (45, 14), (45, 15), (45, 16),
     (45, 17)],
    # NE road: Bosenitz along the brook's east bank, exits the top edge
    # (corridor_ne.png zoom: through the 49,7 / 51,6 / 53,5 hex centers)
    [(45, 10), (46, 10), (47, 10), (47, 9), (48, 8), (49, 7), (50, 6),
     (51, 6), (52, 5), (53, 5), (54, 4), (55, 4), (55, 3), (55, 2)],
    # Krug spur off the Olmutz road
    [(63, 15), (63, 16), (63, 17), (63, 18), (62, 18)],
    # Krug -> Holubitz
    [(62, 18), (63, 18), (64, 18), (65, 18), (66, 18), (67, 18), (68, 18)],
    # Holubitz north to the To Austerlitz exit road
    [(68, 18), (69, 17), (70, 16), (71, 17), (72, 16), (73, 17), (74, 17)],
    # Austerlitz exit road joins the Olmutz road near (72,15)
    [(72, 15), (72, 16)],
    # Holubitz village streets / south spur
    [(68, 18), (68, 19), (69, 19), (70, 20)],
]
STREAMS = [
    # Bosenitzer brook: enters NE, west along row 5, SW past Bosenitz,
    # then south along the area's west edge (corridor_ne.png zoom)
    [(61, 4), (60, 4), (59, 4), (58, 4), (57, 5), (56, 5), (55, 5),
     (54, 5), (53, 6), (52, 6), (51, 7), (50, 7), (49, 8), (48, 9),
     (47, 10), (46, 10), (46, 11), (45, 11), (44, 12), (43, 12),
     (42, 13), (41, 13), (40, 14), (39, 15), (38, 16), (39, 17),
     (38, 18), (39, 19), (38, 20), (39, 21), (38, 22), (39, 23),
     (38, 24), (39, 25), (38, 26), (39, 27), (38, 28)],
    # Raussnitzer brook: east edge, south from the bluff
    [(74, 19), (73, 20), (74, 21), (73, 22), (74, 23), (73, 24),
     (74, 25), (73, 26), (74, 27), (73, 28)],
]
# Bridges drawn on the map (][ symbols), hand-verified at zoom:
#   NE road over the brook NE of Bosenitz; south road over the brook
#   below Bosenitz; the Olmutz road over the brook at the west edge.
BRIDGES = [((46, 10), (47, 10)), ((45, 11), (45, 12)), ((38, 16), (39, 16))]
# Sharp (hachured) slope hexsides, hand-verified on the map image
SHARP = [
    ((41, 13), (42, 13)), ((41, 14), (42, 13)), ((41, 14), (42, 14)),
    ((41, 15), (42, 14)), ((41, 15), (42, 15)),
    ((72, 20), (73, 20)), ((72, 21), (73, 20)), ((72, 21), (73, 21)),
    ((73, 19), (74, 19)), ((73, 20), (74, 20)),
    ((72, 22), (73, 21)), ((72, 22), (73, 22)),
]

# ------------------------------------------------------------ expansion
def path_pairs(path):
    out = set()
    for a, b in zip(path, path[1:]):
        if in_area(*a) and in_area(*b):
            out.add(tuple(sorted((tuple(a), tuple(b)))))
    return out


roads_pri = path_pairs(OLMUTZ_ROAD)
roads_sec = set()
for p in SECONDARY_ROADS:
    roads_sec |= path_pairs(p)
roads_sec -= roads_pri

# stream hexsides: the traced line passes BETWEEN hexes; for each
# consecutive path pair (a,b) the stream also separates the two hexes
# adjacent to both a and b (the line snakes hex-to-hex, so the crossing
# hexside is between the common neighbors of consecutive path hexes).
stream_pairs = set()
for path in STREAMS:
    for a, b in zip(path, path[1:]):
        if not (in_area(*a) and in_area(*b)):
            continue
        na = {tuple(n) for n in game.neighbors(*a)}
        nb = {tuple(n) for n in game.neighbors(*b)}
        common = [h for h in na & nb if in_area(*h)]
        # the brook between a and b makes a<->b NOT a crossing (you move
        # along the water) — the crossings are common-neighbor<->a/b?
        # No: the stream OCCUPIES the a-b corridor; crossing it means
        # moving between the two common neighbors of a and b.
        if len(common) == 2:
            stream_pairs.add(tuple(sorted((common[0], common[1]))))
        # and moving a<->b along the line also crosses it
        stream_pairs.add(tuple(sorted((tuple(a), tuple(b)))))

sharp = {tuple(sorted((tuple(a), tuple(b)))) for a, b in SHARP}
bridges = {tuple(sorted((tuple(a), tuple(b)))) for a, b in BRIDGES}
bridges |= {p for p in stream_pairs if p in roads_pri or p in roads_sec}
stream_pairs -= bridges

# --------------------------------------------------------- hex features
TREE = (110, 160, 90)
is_tree = lambda p: dist2(p, TREE) < 3000


def art_density(c, r, hit, radius=28, grid=9):
    x, y = game.grid.hex_to_pixel(c, r)
    n = 0
    for i in range(grid):
        for j in range(grid):
            px = MAP.getpixel((x - radius + 2 * radius * i // (grid - 1),
                               y - radius + 2 * radius * j // (grid - 1)))
            if hit(px):
                n += 1
    return n / grid ** 2


woods = {h for h in elev if art_density(*h, is_tree) > 0.10}

# villages: flood from the module's own anchors over building-art density
ANCHORS = {"bosenitz": (43, 9), "krug": (63, 18), "holubitz": (69, 19),
           "post_house": (74, 13)}
is_bldg = lambda p: p[0] < 110 and p[1] < 105 and p[2] < 105


def bldg(c, r):
    return art_density(c, r, is_bldg, radius=34, grid=11)


village = set()
for name, seed in ANCHORS.items():
    frontier = [seed]
    seen = set()
    while frontier:
        h = frontier.pop()
        if h in seen or not in_area(*h):
            continue
        seen.add(h)
        if bldg(*h) < (0.035 if h == seed else 0.05):
            continue
        village.add(h)
        frontier += [tuple(n) for n in game.neighbors(*h)]
village.add(ANCHORS["post_house"])   # single building, art density is low

# minor slopes from elevation deltas (excluding sharp + water)
slopes_minor = set()
for (c, r), lv in elev.items():
    if lv == "water":
        continue
    for s in range(6):
        nb = fm.side_neighbor(game, c, r, s)
        if not nb or not in_area(*nb):
            continue
        key = tuple(sorted(((c, r), tuple(nb))))
        lv2 = elev[tuple(nb)]
        if lv2 == "water" or key in sharp:
            continue
        if abs(lv - lv2) >= 1:
            slopes_minor.add(key)

# --------------------------------------------------------------- emit
def pairs(s):
    return sorted([list(a), list(b)] for a, b in s)


out = {
    "note": "Northern Flank scenario area only; generated by build_terrain.py (method in docstring): elevation/woods auto from map colors, roads+streams+sharp slopes hand-traced from the map image, villages anchor-seeded",
    "area": {"cols": [C0, C1], "rows": [R0, R1]},
    "hexes": {f"{c},{r}": ("water" if elev[(c, r)] == "water" else
                           "village" if (c, r) in village else
                           "woods" if (c, r) in woods else "clear")
              for (c, r) in sorted(elev)},
    "elevation": {f"{c},{r}": (elev[(c, r)] if elev[(c, r)] != "water" else 0)
                  for (c, r) in sorted(elev)},
    "hexsides": {"stream": pairs(stream_pairs), "bridge": pairs(bridges),
                 "minor_slope": pairs(slopes_minor), "sharp_slope": pairs(sharp)},
    "road_pairs": {"primary": pairs(roads_pri), "secondary": pairs(roads_sec)},
}
dst = os.path.join(HERE, "terrain_nf.json")
json.dump(out, open(dst, "w"), indent=0)
print("hexes:", len(out["hexes"]), "| village:", len(village),
      "| woods:", len(woods),
      "| water:", sum(1 for v in elev.values() if v == "water"))
print("streams:", len(stream_pairs), "| bridges:", len(bridges),
      "| minor slopes:", len(slopes_minor), "| sharp:", len(sharp))
print("roads primary:", len(roads_pri), "| secondary:", len(roads_sec))
print("->", dst)
