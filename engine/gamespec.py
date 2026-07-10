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
        with open(os.path.join(self.dir, "game.json"), encoding="utf-8") as f:
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

        # extended movement semantics (all optional; absent = legacy behavior)
        self.terrain_stop = set(m.get("terrain_stop", []))   # enter => movement ends
        self.road_bonus = m.get("road_bonus")  # {"feature","mp"}: extra budget on road hexsides
        # class-aware enemy hexes: units of pass_classes never block (AK 5.4
        # "supply and Rommel are not combat units"; 22.3 move onto lone Rommel)
        self.enemy_pass_classes = set((m.get("enemy_hex") or {}).get("pass_classes", []))
        # end-of-move stacking limit (AK 6.1-6.3); absent = never end on friendlies
        self.stacking = m.get("stacking")
        # per-hex whitelist of (entry,exit) neighbor pairs allowed as a free
        # road-through where several roads share a hex without connecting
        self.road_pairs = {k: {tuple(sorted(tuple(h) for h in pair)) for pair in v}
                           for k, v in m.get("road_through_pairs", {}).items()}
        self.classes = spec.get("classes", {})
        self._class_names = {cl: set(names) for cl, names in self.classes.items()
                             if isinstance(names, list)}

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

    def unit_class(self, unit_name):
        """Class from spec.classes name lists ('markers'/'supply'/'hq'...), or None."""
        for cl, names in self._class_names.items():
            if unit_name in names:
                return cl
        return None

    def _exerts_zoc(self, u):
        """ZOC comes from combat units only when zoc.exempt_classes is set;
        units standing on zoc.no_exert_terrain exert none at all (AK 7.1
        fortress exception + 23.1/23.2: attacks around a fortress are
        optional in both directions — a garrison exerts no ZOC outward).
        Units flagged zoc_negated (AK 9.1 Automatic Victory) exert none."""
        if u.get("zoc_negated"):
            return False
        exempt = self.zoc_cfg.get("exempt_classes")
        if exempt and self.unit_class(u["name"]) in exempt:
            return False
        noex = self.zoc_cfg.get("no_exert_terrain")
        if noex and self.hex_terrain(u["col"], u["row"]) in noex:
            return False
        return True

    def _zoc_immune(self, h):
        """ZOC never extends over hexes of zoc.immune_terrain (AK 19.5/23.1:
        adjacent units do not exert a ZOC over a fortress hex)."""
        imm = self.zoc_cfg.get("immune_terrain")
        return bool(imm) and self.hex_terrain(*h) in imm

    def hexside_prohibited(self, a, b):
        """True if the a-b hexside carries a prohibit rule (AK 5.7 all-water
        and Qattara hexsides, E18-F19 / W62-X62)."""
        f = self.side_features(a, b)
        for rule in self.hexside_rules:
            if rule["effect"] != "prohibit":
                continue
            if f.get(rule["feature"]) != rule["value"]:
                continue
            if rule.get("unless") and f.get(rule["unless"]):
                continue
            return True
        return False

    def _zoc_neighbors(self, u):
        """The hexes a unit's ZOC covers: its six neighbors, minus immune
        terrain, minus (spec-gated) neighbors across prohibited hexsides —
        AK 7.1 lists E18-F19 / W62-X62 with the fortresses as ZOC
        exceptions, and 5.7 says units on those adjoining hexes may not
        engage each other in battle."""
        across = self.zoc_cfg.get("blocked_by_prohibited_hexsides", False)
        src = (u["col"], u["row"])
        out = set()
        for nb in self.neighbors(*src):
            if self._zoc_immune(nb):
                continue
            if across and self.hexside_prohibited(src, nb):
                continue
            out.add(nb)
        return out

    def zoc_hexes(self, board, enemy_side):
        z = set()
        if not self.zoc_cfg.get("exerts", False):
            return z
        for u in board:
            if u["side"] == enemy_side and self._exerts_zoc(u):
                z |= self._zoc_neighbors(u)
        return z

    def zoc_by_unit(self, board, enemy_side):
        """Per-enemy-unit ZOC sets (for the AK 8.3 same-unit first-step rule)."""
        out = {}
        if not self.zoc_cfg.get("exerts", False):
            return out
        for u in board:
            if u["side"] == enemy_side and self._exerts_zoc(u):
                out[u["id"]] = self._zoc_neighbors(u)
        return out

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

    # ---------------------------------------------------- extended movement
    def _hex_road_sides(self):
        """(col,row) -> set of neighbor (col,row) reachable over a road
        hexside, from terrain.json sides. Cached."""
        cached = getattr(self, "_road_sides_cache", None)
        if cached is not None:
            return cached
        feat = self.road_bonus["feature"] if self.road_bonus else None
        out = {}
        if feat and self.terrain:
            for skey, f in self.terrain.get("sides", {}).items():
                if not f.get(feat):
                    continue
                a, b = skey.split("|")
                ca, ra = int(a[:2]), int(a[2:])
                cb, rb = int(b[:2]), int(b[2:])
                out.setdefault((ca, ra), set()).add((cb, rb))
                out.setdefault((cb, rb), set()).add((ca, ra))
        self._road_sides_cache = out
        return out

    def _is_stop_hex(self, h):
        return self.hex_terrain(*h) in self.terrain_stop

    def _enemy_hexes(self, board, enemy):
        """(blocked, passable, no_end): blocked = enemy-occupied hexes that
        may never be entered; passable = enemy hexes whose occupants are ALL
        of enemy_hex.pass_classes (AK 5.4: only COMBAT units block on-top/
        through; a lone supply or Rommel hex may be entered, 22.3/15.22) or
        zoc_negated combat units (AK 9.1 Automatic Victory: attackers may
        move OVER the AVed unit); no_end ⊆ passable = hexes holding a
        negated combat unit — passable but never a destination (9.1 'may
        not end their move directly on top of it')."""
        occ = {}
        for u in board:
            if u["side"] == enemy:
                occ.setdefault((u["col"], u["row"]), []).append(u)
        if not self.enemy_pass_classes:
            return set(occ), set(), set()
        def transparent(u):
            return self.unit_class(u["name"]) in self.enemy_pass_classes \
                or u.get("zoc_negated")
        blocked = {h for h, us in occ.items()
                   if any(not transparent(u) for u in us)}
        passable = set(occ) - blocked
        no_end = {h for h in passable
                  if any(u.get("zoc_negated") for u in occ[h])}
        return blocked, passable, no_end

    def _stack_ok(self, unit, h, board):
        """May `unit` END its move in friendly-occupied hex h? Only with a
        stacking spec (AK 6.1: three combat units per hex; exempt classes
        stack above the limit; 6.3: the limit binds only at end of move)."""
        if not self.stacking:
            return False
        exempt = set(self.stacking.get("exempt_classes", []))
        if self.unit_class(unit["name"]) in exempt:
            return True
        n = sum(1 for u in board
                if u["side"] == unit["side"] and (u["col"], u["row"]) == h
                and u.get("id") != unit.get("id")
                and self.unit_class(u["name"]) not in exempt)
        return n < int(self.stacking["max"])

    def _step_check(self, cur, nb, prev, came_by_road, nonroad_used, start):
        """Shared step legality for extended movement (AK rules 17/18).
        prev = hex we entered cur from (None at start); came_by_road = the
        prev->cur step crossed a road hexside.
        Returns (allowed, is_road_side, new_nonroad_used, terminal_entry).
        terminal_entry: entering nb ends movement (plain stop-terrain, 18.1)."""
        roads = self._hex_road_sides()
        is_road_side = nb in roads.get(cur, set())
        nb_stop = self._is_stop_hex(nb)
        cur_road_stop = self._is_stop_hex(cur) and bool(roads.get(cur))
        nb_road_stop = nb_stop and bool(roads.get(nb))
        # 17.3/17.32: in a multi-road hex, free road through-traffic only
        # along the same road — whitelisted (entry, exit) neighbor pairs;
        # any other exit is treated as a non-road move
        if is_road_side and cur_road_stop and came_by_road and prev is not None:
            key = f"{cur[0]:02d}{cur[1]:02d}"
            if key in self.road_pairs \
               and tuple(sorted((prev, nb))) not in self.road_pairs[key]:
                is_road_side = False
        new_nonroad = nonroad_used
        if not is_road_side and (cur_road_stop or nb_road_stop):
            # 18.41/18.42/18.5: ONE non-road move on-or-off a road
            # stop-terrain hex per turn
            if nonroad_used:
                return False, is_road_side, nonroad_used, False
            new_nonroad = True
        # entering plain stop-terrain always ends movement (18.1/18.3);
        # road stop-terrain never auto-stops: road exits are free (18.4) and
        # non-road exits are limited by the once-per-turn flag (18.41)
        terminal = nb_stop and not nb_road_stop
        return True, is_road_side, new_nonroad, terminal

    def _legal_destinations_ext(self, unit, ma, board):
        """Extended Dijkstra: dual budget (normal MA + road bonus), stop
        terrain, once-per-turn non-road escarpment moves, per-unit ZOC.
        State: (hex, nonroad_used, entry) where entry is the previous hex
        (tracked only inside multi-road exception hexes) — costs form a
        pareto frontier of (normal_used, road_used)."""
        enemy = self.enemy(unit["side"])
        fpos = {(u["col"], u["row"]) for u in board if u["side"] != enemy}
        eblock, epass, eno_end = self._enemy_hexes(board, enemy)
        # legacy bool applies only when no class rule is specified: everything
        # enterable, nothing endable
        if not self.enemy_pass_classes \
           and self.spec["movement"].get("enter_enemy_hex", False):
            epass, eblock = eblock | epass, set()

        def can_end(h):
            if h in eblock or (h in epass and not self.enemy_pass_classes):
                return False
            if h in eno_end:
                return False              # AV'd unit's hex (9.1): over, not on
            if h in fpos and not self._stack_ok(unit, h, board):
                return False
            return True

        ezoc = self.zoc_hexes(board, enemy)
        start = (unit["col"], unit["row"])
        if self.zoc_cfg.get("locked_at_start", False) and start in ezoc:
            return {}
        stop_on_enter = self.zoc_cfg.get("stop_on_enter", False)
        # supply units may not enter enemy ZOC during movement (AK 13.2's
        # sustain exception is a combat-phase decision, not a move)
        supply_no_zoc = (self.zoc_cfg.get("supply_no_enter")
                         and self.unit_class(unit["name"]) == "supply")
        # 8.3: a unit starting in ZOC may not step into another hex covered
        # by the ZOC of ANY unit already covering its start hex
        banned_first = set()
        if self.zoc_cfg.get("same_unit_first_step") and start in ezoc:
            for zset in self.zoc_by_unit(board, enemy).values():
                if start in zset:
                    banned_first |= zset
        road_mp = float(self.road_bonus["mp"]) if self.road_bonus else 0.0

        def entry_key(h, prev):
            return prev if f"{h[0]:02d}{h[1]:02d}" in self.road_pairs else None

        # state -> pareto list of (normal_used, road_used)
        best = {(start, False, None): [(0.0, 0.0)]}
        pq = [(0.0, 0.0, start, False, None, None, False)]
        # (normal, road, hex, nonroad_used, entry, prev, came_by_road)
        dests = {}
        while pq:
            n_used, r_used, cur, nr, entry, prev, by_road = heapq.heappop(pq)
            st = (cur, nr, entry)
            if all((n_used, r_used) != p for p in best.get(st, [])):
                continue
            if cur != start:
                if can_end(cur):
                    if cur not in dests or n_used < dests[cur]:
                        dests[cur] = n_used
                if cur in ezoc and stop_on_enter:
                    continue                      # 8.1: entered ZOC, stop
            for nb in self.neighbors(*cur):
                if nb in eblock:
                    continue                      # 5.4: enemy combat unit
                if cur == start and nb in banned_first:
                    continue
                if supply_no_zoc and nb in ezoc:
                    continue
                c = self.move_cost(cur, nb)
                if c is None:
                    continue
                ok, road_side, nr2, terminal = self._step_check(
                    cur, nb, prev, by_road, nr, start)
                if not ok:
                    continue
                pays = [(n_used + c, r_used)]
                if road_side and r_used + c <= road_mp + 1e-9:
                    pays.append((n_used, r_used + c))    # 17.1 bonus budget
                for n2, r2 in pays:
                    if n2 > ma + 1e-9 or r2 > road_mp + 1e-9:
                        continue
                    st2 = (nb, nr2, entry_key(nb, cur))
                    frontier = best.setdefault(st2, [])
                    if any(pn <= n2 + 1e-9 and pr <= r2 + 1e-9
                           for pn, pr in frontier):
                        continue
                    frontier[:] = [(pn, pr) for pn, pr in frontier
                                   if not (n2 <= pn + 1e-9 and r2 <= pr + 1e-9)]
                    frontier.append((n2, r2))
                    if terminal:
                        if can_end(nb) and (nb not in dests or n2 < dests[nb]):
                            dests[nb] = n2
                    else:
                        heapq.heappush(pq, (n2, r2, nb, nr2,
                                            entry_key(nb, cur), cur, road_side))
        dests.pop(start, None)
        return {h: c for h, c in dests.items() if can_end(h)}

    def trace_path(self, unit, ma, board, path):
        """Validate an explicit hex path (list of (col,row), start first)
        under the extended rules. Returns (legal, reason). Used to check the
        rulebook's worked movement examples verbatim."""
        enemy = self.enemy(unit["side"])
        fpos = {(u["col"], u["row"]) for u in board if u["side"] != enemy}
        eblock, epass, eno_end = self._enemy_hexes(board, enemy)
        if not self.enemy_pass_classes:
            eblock |= epass          # no class rule: every enemy hex blocks
        ezoc = self.zoc_hexes(board, enemy)
        stop_on_enter = self.zoc_cfg.get("stop_on_enter", False)
        banned_first = set()
        if self.zoc_cfg.get("same_unit_first_step") and path[0] in ezoc:
            for zset in self.zoc_by_unit(board, enemy).values():
                if path[0] in zset:
                    banned_first |= zset
        road_mp = float(self.road_bonus["mp"]) if self.road_bonus else 0.0
        n_used = r_used = 0.0
        nr = False
        prev, by_road = None, False
        start = path[0]
        for i, (cur, nb) in enumerate(zip(path, path[1:])):
            if nb in eblock:
                return False, f"step {i+1}: enemy combat unit blocks (5.4)"
            if cur == start and nb in banned_first:
                return False, f"step {i+1}: same-unit ZOC hop (8.3)"
            c = self.move_cost(cur, nb)
            if c is None:
                return False, f"step {i+1}: prohibited terrain/hexside"
            ok, road_side, nr, terminal = self._step_check(
                cur, nb, prev, by_road, nr, start)
            if not ok:
                return False, f"step {i+1}: second non-road escarpment move (18.5)"
            if road_side and r_used + c <= road_mp + 1e-9:
                r_used += c                       # prefer the bonus budget
            else:
                n_used += c
            if n_used > ma + 1e-9:
                return False, f"step {i+1}: movement factor exceeded"
            last = i == len(path) - 2
            if terminal and not last:
                return False, f"step {i+1}: stop terrain entered, move ends (18.1)"
            if stop_on_enter and nb in ezoc and not last:
                return False, f"step {i+1}: enemy ZOC entered, move ends (8.1)"
            prev, by_road = cur, road_side
        if path[-1] in fpos and not self._stack_ok(unit, path[-1], board):
            return False, "end hex over the stacking limit (6.1/6.3)"
        if path[-1] in eno_end:
            return False, "may not end the move on the AVed unit's hex (9.1)"
        return True, f"ok (normal {n_used:g}/{ma}, road {r_used:g}/{road_mp:g})"

    def legal_destinations_t(self, unit, ma, board):
        """Terrain-aware legal destinations: Dijkstra over spec move costs.
        Semantics (each spec-gated): may pass through friendly hexes but not
        end there, never enter enemy hexes, stop on entering enemy ZOC, may
        not leave a ZOC hex it starts in. Returns {(col,row): cost}.
        Dispatches to the extended engine when the spec uses stop-terrain,
        road bonus or per-unit ZOC semantics."""
        if self.terrain_stop or self.road_bonus \
           or self.zoc_cfg.get("same_unit_first_step") \
           or self.stacking or self.enemy_pass_classes:
            return self._legal_destinations_ext(unit, ma, board)
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


    # ------------------------------------------------------------- combat (CRT)
    @property
    def combat_cfg(self):
        return self.spec.get("combat")

    def odds(self, att, deff):
        """Battle odds after rounding in the defender's favor (AK 7.3:
        7:2 -> 3-1, 2:7 -> 1-4). Returns (n, d) for n-d odds."""
        att, deff = float(att), float(deff)
        if att >= deff:
            return int(att // deff), 1
        return 1, int(-(-deff // att))       # ceil

    def odds_column(self, n, d):
        """CRT column for n-d odds: the column string, 'auto_elim' above the
        table (AK 7.4/9.1 + printed CRT note: >6-1 eliminates without a
        roll), or None when worse than the lowest column (no voluntary
        attack below 1-6, 7.4)."""
        cb = self.combat_cfg
        hi = cb["odds"]["auto_elim_above"]
        lo = cb["odds"]["min_voluntary"]
        if d == 1 and n > hi[0]:
            return "auto_elim"
        if n == 1 and d > lo[1]:
            return None
        col = f"{n}-{d}"
        return col if col in cb["crt"]["columns"] else None

    def crt_result(self, column, die):
        """Result code for a CRT column and die roll."""
        cb = self.combat_cfg
        ci = cb["crt"]["columns"].index(column)
        return cb["crt"]["rows"][str(die)][ci]

    def defense_factor(self, unit_name, hexpos):
        """Defense factor, doubled on combat.defense_double_terrain (10.2)."""
        d = self.stats(unit_name)[1]
        dbl = (self.combat_cfg or {}).get("defense_double_terrain") or []
        return d * 2 if self.hex_terrain(*hexpos) in dbl else d


def load(game_dir):
    return Game(game_dir)


def games_root():
    """The repo's games/ directory."""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "games")


def default_game_dir(name="arnhem"):
    return os.path.join(games_root(), name)
