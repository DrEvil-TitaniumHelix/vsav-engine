"""
gamespec.py - The generalized game layer: one engine, many games.

A game is a directory holding game.json — grid geometry, side detection, unit
stats, terrain MP costs, hexside effects, ZOC behavior — plus pointers to its
terrain data, setup save and map assets. The movement engine below reads ONLY
the spec; nothing in this file knows about any particular game. Adding a game
means authoring a spec directory, not writing engine code.

Spec-driven today: hex grid + numbering, sides, stats, terrain costs, hexside
rules (prohibit / override / add, each with an "unless" feature like a bridge),
ZOC flags, off-map classification. Combat (CRT) generalizes next.
"""
import heapq, json, os
from collections import deque


class Grid:
    """Staggered hex grid: pixel <-> (col,row) <-> printed hex number.

    orient "flat"  : flat-top hexes, staggered COLUMNS (odd cols shift +dy/2) — Arnhem.
    orient "pointy": pointy-top hexes, staggered ROWS (offset rows shift +dx/2) — Tobruk.
    """

    def __init__(self, cfg):
        self.dx = float(cfg["dx"]); self.dy = float(cfg["dy"])
        self.x0 = float(cfg["x0"]); self.y0 = float(cfg["y0"])
        self.orient = cfg.get("orient", "flat")
        self.stagger = bool(cfg.get("stagger", True))
        self.stagger_sign = int(cfg.get("stagger_sign", 1))    # flat: +1 odd cols shift DOWN, -1 UP
        self.odd_row_carry = int(cfg.get("odd_row_carry", 1))
        self.offset_parity = int(cfg.get("offset_parity", 1))  # pointy: rows with row%2==this shift +dx/2
        self.digits = int(cfg.get("hexnum_digits", 2))

    def pixel_to_hex(self, x, y):
        if self.orient == "pointy":
            row = round((y - self.y0) / self.dy)
            xoff = (self.dx / 2.0) if (self.stagger and row % 2 == self.offset_parity) else 0.0
            col = round((x - self.x0 - xoff) / self.dx)
            return col, row, self.hexnum(col, row)
        col = round((x - self.x0) / self.dx)
        odd = (col % 2 == 1)
        yoff = (self.stagger_sign * self.dy / 2.0) if (self.stagger and odd) else 0.0
        row = round((y - self.y0 - yoff) / self.dy) + (self.odd_row_carry if odd else 0)
        return col, row, self.hexnum(col, row)

    def hex_to_pixel(self, col, row):
        if self.orient == "pointy":
            xoff = (self.dx / 2.0) if (self.stagger and row % 2 == self.offset_parity) else 0.0
            return round(self.x0 + col * self.dx + xoff), round(self.y0 + row * self.dy)
        odd = (col % 2 == 1)
        yoff = (self.stagger_sign * self.dy / 2.0) if (self.stagger and odd) else 0.0
        base = row - (self.odd_row_carry if odd else 0)
        return round(self.x0 + col * self.dx), round(self.y0 + base * self.dy + yoff)

    def hexnum(self, col, row):
        return f"{col:0{self.digits}d}{row:0{self.digits}d}"

    def hexnum_to_pixel(self, hexnum):
        s = f"{int(hexnum):0{self.digits * 2}d}"
        return self.hex_to_pixel(int(s[:self.digits]), int(s[self.digits:]))

    def set_naming(self, cfg):
        """Optional printed-map hex naming (display only; engine math stays col/row).
        style "letter_diag": letter rows (A..Z, then AA..ZZ doubled) starting at
        name_row0, numbers constant along down-left diagonals (AH Tobruk style)."""
        self.name_style = cfg.get("style")
        self.name_row0 = int(cfg.get("row0", 1))
        self.name_num0 = int(cfg.get("num0", -1))

    @staticmethod
    def _letters(i):
        return chr(65 + i) if i < 26 else chr(65 + i - 26) * 2

    def display_name(self, col, row):
        style = getattr(self, "name_style", None)
        if style == "letter_diag":      # Tobruk: letter ROWS, numbers on down-left diagonals
            li = row - self.name_row0
            if li >= 0:
                return f"{self._letters(li)}{col + li // 2 + self.name_num0 + 1}"
        if style == "colletter":        # ASL geoboards: letter COLUMNS (A..Z,AA..GG) + row
            return f"{self._letters(col)}{row}"
        return self.hexnum(col, row)


class Game:
    """A loaded game spec + its terrain data + the spec-driven movement engine."""

    def __init__(self, game_dir):
        self.dir = os.path.abspath(game_dir)
        with open(os.path.join(self.dir, "game.json")) as f:
            spec = json.load(f)
        self.spec = spec
        self.name = spec["name"]
        self.map_name = spec.get("map_name", "Main Map")
        self.save_key = int(spec.get("save_key", "a3"), 16)
        self.grid = Grid(spec["grid"])

        s = spec["sides"]
        self.side_order = s["order"]
        self.default_side = s["default"]
        self.detect_tokens = s.get("detect_tokens", {})

        g = spec["grid"]
        if "naming" in g:
            self.grid.set_naming(g["naming"])

        st = spec.get("stats", {})
        self.stat_patterns = [(frag, tuple(v)) for frag, v in st.get("patterns", [])]
        self.default_stat = tuple(st.get("default", (0, 0, 0)))

        m = spec["movement"]
        self.terrain_mp = m["terrain_mp"]
        self.default_mp = float(m.get("default_mp", 1.0))
        self.hexside_rules = m.get("hexside_rules", [])
        self.zoc_cfg = m.get("zoc", {})
        self.impassable = set(m.get("impassable_terrain", ["offmap", "water"]))
        self.holding_row_max = m.get("holding_row_max")
        self.bounds = m.get("bounds")          # {"cols":[min,max],"rows":[min,max]}
        self.unit_kinds = set(spec.get("unit_kinds", ["mark"]))

        self.facing = spec.get("facing")   # {"count": N, "step_deg": d} or None

        tf = spec.get("terrain_file")
        tp = self._path(tf)
        self.terrain = json.load(open(tp)) if tp and os.path.exists(tp) else None
        self.setup_save = self._path(spec.get("setup_save"))
        self.assets = {k: self._path(v) for k, v in spec.get("assets", {}).items()}

    def _path(self, rel):
        return os.path.normpath(os.path.join(self.dir, rel)) if rel else None

    # ------------------------------------------------------------- sides & stats
    def side(self, unit_name):
        for side_id, tokens in self.detect_tokens.items():
            if any(t in unit_name for t in tokens):
                return side_id
        return self.default_side

    def enemy(self, side_id):
        a, b = self.side_order
        return b if side_id == a else a

    def stats(self, unit_name):
        """(attack, defense, movement allowance) by ordered name-fragment match."""
        for frag, st in self.stat_patterns:
            if frag in unit_name:
                return st
        return self.default_stat

    # ------------------------------------------------------------- geometry
    def neighbors(self, col, row):
        g = self.grid
        x, y = g.hex_to_pixel(col, row)
        if g.orient == "pointy":
            offs = [(-g.dx, 0), (g.dx, 0),
                    (-g.dx / 2, -g.dy), (g.dx / 2, -g.dy),
                    (-g.dx / 2, g.dy), (g.dx / 2, g.dy)]
        else:
            offs = [(0, -g.dy), (0, g.dy),
                    (g.dx, -g.dy / 2), (g.dx, g.dy / 2),
                    (-g.dx, -g.dy / 2), (-g.dx, g.dy / 2)]
        out = []
        for dx, dy in offs:
            c, r, _ = g.pixel_to_hex(round(x + dx), round(y + dy))
            out.append((c, r))
        return out

    def hex_distance(self, a, b):
        seen = {a}; q = deque([(a, 0)])
        while q:
            cur, d = q.popleft()
            if cur == b:
                return d
            for nb in self.neighbors(*cur):
                if nb not in seen:
                    seen.add(nb); q.append((nb, d + 1))
            if d > 60:
                break
        return None

    # ------------------------------------------------------------- terrain
    def hexkey(self, c, r):
        return self.grid.hexnum(c, r)

    def hex_terrain(self, c, r):
        v = self.terrain["hexes"].get(self.hexkey(c, r)) if self.terrain else None
        return v["t"] if v else None

    def on_map(self, c, r):
        t = self.hex_terrain(c, r)
        if t is not None:
            return t not in self.impassable
        if self.bounds:   # no terrain data: rectangular col/row bounds
            (c0, c1), (r0, r1) = self.bounds["cols"], self.bounds["rows"]
            return c0 <= c <= c1 and r0 <= r <= r1
        return False

    def side_features(self, a, b):
        if not self.terrain:
            return {}
        return (self.terrain["sides"].get(f"{self.hexkey(*a)}|{self.hexkey(*b)}")
                or self.terrain["sides"].get(f"{self.hexkey(*b)}|{self.hexkey(*a)}") or {})

    def move_cost(self, a, b):
        """MP cost to enter hex b from adjacent hex a, or None if prohibited.
        Hexside rules fire in spec order: prohibit short-circuits, the first
        matching override sets the base cost, adds accumulate; otherwise the
        base is the destination hex's terrain cost."""
        if not self.on_map(*b):
            return None
        f = self.side_features(a, b)
        base, add = None, 0.0
        for rule in self.hexside_rules:
            if f.get(rule["feature"]) != rule["value"]:
                continue
            if rule.get("unless") and f.get(rule["unless"]):
                continue
            effect = rule["effect"]
            if effect == "prohibit":
                return None
            if effect == "override" and base is None:
                base = float(rule["mp"])
            elif effect == "add":
                add += float(rule["mp"])
        if base is None:
            t = self.hex_terrain(*b)
            base = float(self.terrain_mp[t]) if t in self.terrain_mp else self.default_mp
        return base + add

    # ------------------------------------------------------------- ZOC & movement
    def occupied(self, board):
        return {(u["col"], u["row"]): u for u in board}

    def zoc_hexes(self, board, enemy_side):
        z = set()
        if not self.zoc_cfg.get("exerts", False):
            return z
        for u in board:
            if u["side"] == enemy_side:
                for nb in self.neighbors(u["col"], u["row"]):
                    z.add(nb)
        return z

    def legal_destinations(self, unit, ma, board):
        """Uniform-cost BFS (1 MP/hex): the pre-terrain model, kept for the
        watcher's quick judgments. Same ZOC/occupancy semantics as below."""
        enemy = self.enemy(unit["side"])
        occ = self.occupied(board)
        ezoc = self.zoc_hexes(board, enemy)
        start = (unit["col"], unit["row"])
        dest = set()
        q = deque([(start, 0)])
        best = {start: 0}
        while q:
            cur, cost = q.popleft()
            for nb in self.neighbors(*cur):
                if nb in occ:
                    continue
                nc = cost + 1
                if nc > ma:
                    continue
                if nb in best and best[nb] <= nc:
                    continue
                best[nb] = nc
                dest.add(nb)
                if nb not in ezoc or not self.zoc_cfg.get("stop_on_enter", False):
                    q.append((nb, nc))
        return dest

    def legal_destinations_t(self, unit, ma, board):
        """Terrain-aware legal destinations: Dijkstra over spec move costs.
        Semantics (each spec-gated): may pass through friendly hexes but not
        end there, never enter enemy hexes, stop on entering enemy ZOC, may
        not leave a ZOC hex it starts in. Returns {(col,row): cost}."""
        enemy = self.enemy(unit["side"])
        epos = {(u["col"], u["row"]) for u in board if u["side"] == enemy}
        fpos = {(u["col"], u["row"]) for u in board if u["side"] != enemy}
        ezoc = self.zoc_hexes(board, enemy)
        start = (unit["col"], unit["row"])
        if self.zoc_cfg.get("locked_at_start", False) and start in ezoc:
            return {}
        stop_on_enter = self.zoc_cfg.get("stop_on_enter", False)
        enter_enemy = self.spec["movement"].get("enter_enemy_hex", False)
        best = {start: 0.0}
        pq = [(0.0, start)]
        while pq:
            cost, cur = heapq.heappop(pq)
            if cost > best.get(cur, 1e9):
                continue
            if cur != start and cur in ezoc and stop_on_enter:
                continue
            for nb in self.neighbors(*cur):
                if nb in epos and not enter_enemy:
                    continue
                c = self.move_cost(cur, nb)
                if c is None:
                    continue
                nc = cost + c
                if nc > ma + 1e-9:
                    continue
                if nc < best.get(nb, 1e9):
                    best[nb] = nc
                    heapq.heappush(pq, (nc, nb))
        return {h: c for h, c in best.items()
                if h != start and h not in fpos and h not in epos}


def load(game_dir):
    return Game(game_dir)


def games_root():
    """The repo's games/ directory."""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "games")


def default_game_dir(name="arnhem"):
    return os.path.join(games_root(), name)
