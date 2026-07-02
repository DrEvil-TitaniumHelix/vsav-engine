"""
rules.py - The Arnhem (SPI Westwall) rules engine. The "brain".

Transcribed from the Westwall Standard Rules + Arnhem Exclusive Rules (the Integrated CRT).
Combat is DIFFERENTIAL-based (attack strength minus defense strength), terrain-integrated.
Validated against the rulebook's own worked example: Town, +9 differential, die 5 -> D1.
"""
import arnhem  # hex geometry + board reader

# ----------------------------------------------------------------- hex geometry
def neighbors(col, row):
    """6 adjacent hexes, via pixel centers (reuses the validated pixel<->hex)."""
    g = arnhem.GRID
    x, y = arnhem.hex_to_pixel(col, row)
    offs = [(0, -g["dy"]), (0, g["dy"]),
            (g["dx"], -g["dy"] / 2), (g["dx"], g["dy"] / 2),
            (-g["dx"], -g["dy"] / 2), (-g["dx"], g["dy"] / 2)]
    out = []
    for dx, dy in offs:
        c, r, _ = arnhem.pixel_to_hex(round(x + dx), round(y + dy))
        out.append((c, r))
    return out

def hex_distance(a, b):
    """BFS hex distance between (col,row) tuples."""
    from collections import deque
    seen = {a}; q = deque([(a, 0)])
    while q:
        cur, d = q.popleft()
        if cur == b: return d
        for nb in neighbors(*cur):
            if nb not in seen:
                seen.add(nb); q.append((nb, d + 1))
        if d > 60: break
    return None

# ----------------------------------------------------------------- Integrated CRT [7.61]
# Each terrain row lists its differential brackets left-to-right; the column POSITION
# (1-based) indexes the shared result matrix. Terrain is integrated: better defensive
# terrain has more left-columns, shifting a given differential to a lower position.
TERRAIN_COLUMNS = {
    "rough":  ["-2", "-1", "0", "+1", "+2,3", "+4,5", "+6-8", "+9-11", "+12"],
    "broken": ["-3", "-2", "-1", "0", "+1", "+2,3", "+4,5", "+6-8", "+9-11", "+12"],   # broken/town/woods/stream
    "grove":  ["-5", "-4,3", "-2", "-1", "0", "+1", "+2,3", "+4,5", "+6-8", "+9-11", "+12"],  # grove/bridge
    "clear":  ["-7", "-6,5", "-4,3", "-2", "-1", "0", "+1", "+2,3", "+4,5", "+6-8", "+9-11", "+12"],  # clear/mixed
}
TERRAIN_ALIAS = {"town": "broken", "woods": "broken", "stream": "broken",
                 "bridge": "grove", "mixed": "clear"}

RESULT_MATRIX = {  # die -> result per column position (1..12)
    1: ["A1", "A1", "A1", "Br", "D1", "D2", "D2", "D2", "D2", "D3", "D4", "De"],
    2: ["A1", "A1", "A1", "A1", "Br", "D1", "D2", "D2", "D2", "D2", "D3", "D4"],
    3: ["A1", "A1", "A1", "A1", "A1", "Br", "D1", "D2", "D2", "D2", "D2", "D3"],
    4: ["A2", "A1", "A1", "A1", "A1", "Br", "Br", "D1", "D2", "D2", "D2", "D2"],
    5: ["A2", "A2", "A1", "A1", "A1", "A1", "Br", "Br", "D1", "D2", "D2", "D2"],
    6: ["Ae", "Ae", "A2", "A1", "A1", "A1", "A1", "Br", "Br", "Br", "D2", "D2"],
}

def _bracket_matches(bracket, diff):
    if "," in bracket:                      # e.g. "+2,3" or "-6,5" or "-4,3"
        lo, hi = bracket.replace("+", "").split(",")
        lo, hi = int(lo), int(hi if not bracket.startswith("-") else "-" + hi)
        a, b = sorted((int(bracket.split(",")[0]), hi))
        return a <= diff <= b
    if "-" in bracket[1:]:                   # range like "+6-8" or "+9-11"
        sign = 1
        body = bracket
        lo, hi = body.replace("+", "").split("-")
        return int(lo) <= diff <= int(hi)
    return diff == int(bracket)

def _column_position(terrain, diff):
    cols = TERRAIN_COLUMNS[TERRAIN_ALIAS.get(terrain, terrain)]
    # clamp: below lowest bracket -> position 1; at/above +12 -> last position
    first = cols[0]
    # parse the lowest threshold
    low_val = int(first.split(",")[0]) if "," in first else int(first)
    if diff <= low_val:
        return 1
    if diff >= 12:
        return len(cols)
    for i, bracket in enumerate(cols):
        if _bracket_matches(bracket, diff):
            return i + 1
    return len(cols)  # fallback (shouldn't hit)

def resolve_combat(att_strength, def_strength, terrain, die):
    """Return the combat result code (A1/A2/Ae/Br/D1..D4/De)."""
    diff = att_strength - def_strength
    pos = _column_position(terrain, diff)
    return RESULT_MATRIX[die][pos - 1]

# ----------------------------------------------------------------- ZOC & movement
def occupied(board):
    return {(u["col"], u["row"]): u for u in board}

def zoc_hexes(board, enemy_side):
    """All hexes in any enemy unit's ZOC (the 6 around each enemy unit)."""
    z = set()
    for u in board:
        if u["side"] == enemy_side:
            for nb in neighbors(u["col"], u["row"]):
                z.add(nb)
    return z

def legal_destinations(unit, ma, board):
    """BFS reachable hexes for `unit` (col,row,side) given movement allowance `ma`.
    Rules used: 1 MP/hex (terrain costs TODO), can't enter occupied hex, must STOP on
    entering an enemy ZOC hex (6.0), can't end stacked (no-stacking 5.31).
    Returns set of (col,row)."""
    from collections import deque
    enemy = "All" if unit["side"] == "Ger" else "Ger"
    occ = occupied(board)
    ezoc = zoc_hexes(board, enemy)
    start = (unit["col"], unit["row"])
    dest = set()
    q = deque([(start, 0, start in ezoc)])
    best = {start: 0}
    while q:
        cur, cost, inzoc = q.popleft()
        for nb in neighbors(*cur):
            if nb in occ:                 # 5.12 can't enter occupied
                continue
            nc = cost + 1                  # uniform cost; terrain TODO
            if nc > ma:
                continue
            if nb in best and best[nb] <= nc:
                continue
            best[nb] = nc
            dest.add(nb)
            # 6.0: entering an enemy ZOC hex ends movement -> don't expand further
            if nb not in ezoc:
                q.append((nb, nc, False))
    # no-stacking: destinations must be empty (already ensured by occ check)
    return dest

# ----------------------------------------------------------------- terrain-aware movement
# Loaded from ref/terrain.json (extracted from the map image + printed Terrain Key).
# Costs per the key: Mixed 2 / Woods 2 / Broken 3 / Rough 4 / Town+City 1;
# road hex-to-hex 1/2 [5.22]; trail 1 [5.23]; river hexside PROHIBITED unless bridged;
# stream +3 unless bridged; bridges add nothing.
import json as _json
import os as _os

_TPATH = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "ref", "terrain.json")
TERRAIN = _json.load(open(_TPATH)) if _os.path.exists(_TPATH) else None
TERRAIN_MP = {"mixed": 2.0, "woods": 2.0, "broken": 3.0, "rough": 4.0,
              "town": 1.0, "city": 1.0}


def hexkey(c, r):
    return f"{c:02d}{r:02d}"


def hex_terrain(c, r):
    v = TERRAIN["hexes"].get(hexkey(c, r)) if TERRAIN else None
    return v["t"] if v else None


def on_map(c, r):
    t = hex_terrain(c, r)
    return t is not None and t not in ("offmap", "water")


def side_features(a, b):
    if not TERRAIN:
        return {}
    return (TERRAIN["sides"].get(f"{hexkey(*a)}|{hexkey(*b)}")
            or TERRAIN["sides"].get(f"{hexkey(*b)}|{hexkey(*a)}") or {})


def move_cost(a, b):
    """MP cost to enter hex b from adjacent hex a, or None if prohibited [5.2]."""
    if not on_map(*b):
        return None
    f = side_features(a, b)
    water, bridge, road = f.get("water"), f.get("bridge"), f.get("road")
    if water == "river" and not bridge:
        return None                       # river hexside: prohibited
    if road == "road":
        base = 0.5                        # 5.22, regardless of terrain (incl. over a bridge)
    elif road == "trail":
        base = 1.0                        # 5.23
    else:
        base = TERRAIN_MP[hex_terrain(*b)]
    add = 3.0 if (water == "stream" and not bridge) else 0.0
    return base + add


def legal_destinations_t(unit, ma, board):
    """Terrain-aware legal destinations: Dijkstra with real MP costs.
    Rules: river/stream hexsides & terrain costs [5.2], may PASS THROUGH friendly
    hexes but not end there [5.31], may never enter enemy hexes [5.12], must stop
    on entering enemy ZOC [6.0], may not leave an enemy ZOC hex [5.14].
    Returns {(col,row): cost}."""
    import heapq
    enemy = "All" if unit["side"] == "Ger" else "Ger"
    epos = {(u["col"], u["row"]) for u in board if u["side"] == enemy}
    fpos = {(u["col"], u["row"]) for u in board if u["side"] != enemy}
    ezoc = zoc_hexes(board, enemy)
    start = (unit["col"], unit["row"])
    if start in ezoc:
        return {}                          # locked in ZOC: leave only via combat [5.14]
    best = {start: 0.0}
    pq = [(0.0, start)]
    while pq:
        cost, cur = heapq.heappop(pq)
        if cost > best.get(cur, 1e9):
            continue
        if cur != start and cur in ezoc:
            continue                       # entered enemy ZOC -> movement ends [6.0]
        for nb in neighbors(*cur):
            if nb in epos:
                continue                   # never enter an enemy hex [5.12]
            c = move_cost(cur, nb)
            if c is None:
                continue
            nc = cost + c
            if nc > ma + 1e-9:
                continue
            if nc < best.get(nb, 1e9):
                best[nb] = nc
                heapq.heappush(pq, (nc, nb))
    # destinations: not the start, not occupied by ANY unit (no stacking on the move)
    return {h: c for h, c in best.items()
            if h != start and h not in fpos and h not in epos}


# ----------------------------------------------------------------- self-test
if __name__ == "__main__":
    # Rulebook checksum: Town terrain, 13 atk vs 4 def (+9), die 5 -> D1
    r = resolve_combat(13, 4, "town", 5)
    print(f"CRT checksum  Town +9 die5 = {r}   (rulebook says D1)  -> {'PASS' if r=='D1' else 'FAIL'}")
    # a few more spot checks
    for (a, d, t, die) in [(13, 4, "town", 1), (5, 5, "clear", 6), (20, 2, "clear", 1), (2, 8, "grove", 6)]:
        print(f"  {a} vs {d} {t} die{die} -> {resolve_combat(a,d,t,die)}")
    # geometry: 9SS Recon hex (33,22) neighbors
    print("neighbors of 3322:", [f"{c:02d}{r:02d}" for c, r in neighbors(33, 22)])
