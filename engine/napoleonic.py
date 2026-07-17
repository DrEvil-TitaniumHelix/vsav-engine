"""
napoleonic.py - NapoleonicGame: the GBoNW-family legality gate.

Tier 1 (this phase): MOVEMENT is enforced — formation-and-facing-true
movement over the transcribed TEC, stacking [7.1], enemy-front-hex stops
[5.1.3], road movement [5.3], movement-caused disorder [5.1.1/6.4.1] with
engine-owned logged dice, one activation per unit per game turn. The
command system [4.0], combat [8.0], morale [9.0+] and reactions [6.2] are
NOT enforced yet (umpired; phases 2-4) and the scenario's rules_scope says
so honestly.

Movement model (engine/formations.py geometry):
  facing 0-11 (even = hexside, odd = vertex); Line-family formations face
  vertices, Column-family face hexsides [6.3.1/6.3.2]. A unit advances
  only through its front hexside(s), pays TEC entry + hexside surcharges,
  may rotate at the TEC change-facing cost per 30-degree step, and may
  spend its whole budget on the special moves (slide/reverse/about-face)
  the TEC prices for its formation. Reachability = Dijkstra over
  (col,row,facing) states.
"""
import heapq
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import json

import fire as fire_mod
import formations as fm
from gate import GateGame

TURN_NOUN = "turn"


class NapoleonicGame(GateGame):
    HASH_KEYS = ("turn", "mover", "units", "moved", "seed", "rng_calls",
                 "tier")
    TURN_NOUN = "turn"
    PHASE_FIELD = "phase"

    def __init__(self, game, scenario_path, live_dir, seed=None, tier=None):
        super().__init__(game, scenario_path, live_dir)
        self.F = fm.Formations(game)
        self._load_terrain()
        self.ctables = game.spec.get("combat_tables")
        self._resolve_tier(tier)
        self._resume_or_new(self._fresh_seed(seed),
                            required=("units", "moved", "tier", "schema"))

    # ------------------------------------------------------------ terrain
    def _load_terrain(self):
        path = os.path.join(self.game.dir,
                            self.scenario.get("terrain_file",
                                              "terrain_nf.json"))
        t = json.load(open(path, encoding="utf-8"))
        self.thex = t["hexes"]
        self.televation = t["elevation"]
        (c0, c1), (r0, r1) = t["area"]["cols"], t["area"]["rows"]
        self.area = (c0, c1, r0, r1)
        pk = lambda a, b: tuple(sorted((tuple(a), tuple(b))))
        self.h_stream = {pk(a, b) for a, b in t["hexsides"]["stream"]}
        self.h_bridge = {pk(a, b) for a, b in t["hexsides"]["bridge"]}
        self.h_minor = {pk(a, b) for a, b in t["hexsides"]["minor_slope"]}
        self.h_sharp = {pk(a, b) for a, b in t["hexsides"]["sharp_slope"]}
        self.r_pri = {pk(a, b) for a, b in t["road_pairs"]["primary"]}
        self.r_sec = {pk(a, b) for a, b in t["road_pairs"]["secondary"]}

    def in_area(self, c, r):
        c0, c1, r0, r1 = self.area
        return c0 <= c <= c1 and r0 <= r <= r1


    def _dist(self, a, b):
        return self.game.hex_distance(tuple(a), tuple(b))
    def hex_terrain(self, c, r):
        return self.thex.get(f"{c},{r}", "clear")

    # ---------------------------------------------------------- lifecycle
    def _resolve_tier(self, tier):
        # Napoleonic family: combat ships in later phases; earned = 1 now.
        self.combat = None
        self.tier_earned = 1
        self.tier = 1 if tier is None else max(1, min(int(tier), 1))

    def new_game(self, seed):
        units = {}
        for u in self.scenario["units"]:
            units[u["id"]] = {
                "pid": u["id"], "slot": u["slot"], "side": u["side"],
                "col": u["hex"][0], "row": u["hex"][1],
                "arm": u["arm"], "formation": u["formation"],
                "facing": u["facing"], "ma": u["stats"]["ma"],
                "morale": u["stats"]["morale"], "sp": u["stats"]["sp"],
                "fire": u["stats"].get("fire", ""),
                "gun": u.get("gun"),
                "skirmish_capable": u.get("skirmish_capable", False),
                "div": u.get("div", ""),
                "vertex_turns": 0,
                # Family C ledger [9.2/11.1]
                "morale_state": "good", "sp_lost": 0, "r_cap": False,
                "dead": False,
            }
        self.s = {"turn": 1, "phase": "movement", "schema": 2,
                  "mover": self.first_player, "units": units,
                  "moved": [], "fired": [], "returned": [],
                  "pending_fire": None,
                  "seed": seed, "rng_calls": 0,
                  "tier": self.tier, "n": 0}
        self._reset_log()
        self._log({"event": "init", "mode": "napoleonic",
                   "scenario": self.scenario["name"],
                   "tier": self.tier, "seed": seed,
                   "units": self._units_for_log(units)})
        self.save()

    def _units_for_log(self, units):
        return [dict(pid=u["pid"], slot=u["slot"], side=u["side"],
                     hex=[u["col"], u["row"]], facing=u["facing"],
                     formation=u["formation"]) for u in units.values()]

    # ----------------------------------------------------------- geometry
    def _kind(self, u):
        return self.F.kind(u["formation"])

    def occupants(self, c, r, exclude=None):
        return [v for v in self.s["units"].values()
                if v["col"] == c and v["row"] == r
                and v["pid"] != exclude and self.on_map(v)]

    def enemy_front_hexes(self, side):
        """Hexes in any enemy COMBAT unit's front [5.1.3]; routed units
        project nothing (no rout state yet at tier 1)."""
        out = {}
        for v in self.s["units"].values():
            if v["side"] == side or v["arm"] == "leader":
                continue
            for h in fm.front_hexes(self.game, v["col"], v["row"],
                                    v["facing"], self._kind(v)):
                out.setdefault(tuple(h), []).append(v["pid"])
        return out

    # ------------------------------------------------------------ costing
    def _road(self, a, b):
        key = tuple(sorted((tuple(a), tuple(b))))
        if key in self.r_pri:
            return "primary_road"
        if key in self.r_sec:
            return "secondary_road"
        return None

    def _hexside_rows(self, a, b):
        key = tuple(sorted((tuple(a), tuple(b))))
        rows = []
        if key in self.h_stream:
            rows.append("stream_hexside")
        if key in self.h_minor:
            rows.append(("minor_slope_up", "minor_slope_down"))
        if key in self.h_sharp:
            rows.append(("sharp_slope_up", "sharp_slope_down"))
        return rows, key in self.h_bridge

    def step_cost(self, u, frm, to, minor_crossed):
        """(cost, disorder_mode, new_minor_count) for one hex entry, or
        (None, reason, _) if prohibited. disorder_mode: '' | 'check' |
        'auto' [TEC 5.0; keys d / D]."""
        c, r = to
        terr = self.hex_terrain(c, r)
        if terr == "water":
            return None, "pond/water hex is prohibited [TEC 5.0 Pond]", 0
        road = self._road(frm, to)
        rows, bridge = self._hexside_rows(frm, to)
        cell = self.F.entry(u, terr, road=road)
        if cell is None:
            return None, f"no TEC entry for {terr}", 0
        if cell.prohibited:
            return None, (f"{terr} prohibited for {u['arm']} in "
                          f"{u['formation']} [TEC 5.0]"), 0
        cost = cell.cost if cell.cost is not None else 0.0
        dis = "auto" if cell.auto_disorder else (
            "check" if cell.disorder_check else "")
        using_road = road is not None and \
            self.F.may_road_move(u["formation"]) and not cell.other_terrain
        nmc = minor_crossed
        going_up = self.televation.get(f"{c},{r}", 0) >= \
            self.televation.get(f"{frm[0]},{frm[1]}", 0)
        for row in rows:
            if isinstance(row, tuple):
                row = row[0] if going_up else row[1]
            if row.startswith("stream") and using_road and bridge:
                continue        # bridge: no additional cost [TEC 5.0]
            hcell = self.F.hexside(u, row)
            if hcell is None:
                continue
            if hcell.prohibited:
                return None, (f"{row} prohibited for {u['arm']} in "
                              f"{u['formation']} [TEC 5.0]"), 0
            if hcell.minor_slope:
                if nmc >= 1:
                    cost += hcell.minor_slope
                nmc += 1
                continue
            if hcell.surcharge:
                cost += hcell.surcharge
            if hcell.auto_disorder:
                dis = "auto"
            elif hcell.disorder_check and dis != "auto":
                dis = "check"
        return cost, dis, nmc

    # -------------------------------------------------------- reachability
    def reachable(self, pid):
        """Dijkstra over (col,row,facing): every reachable (hex, facing)
        with its cheapest MP cost, its path, and pending disorder events.
        Facing changes cost the TEC row per 30-degree step; advancing goes
        through front hexsides only; entering an enemy front hex is
        terminal [5.1.3]."""
        u = self.unit(pid)
        if self.F.immobile(u["formation"]):
            return {}
        ma = float(u["ma"])
        efh = self.enemy_front_hexes(u["side"])
        start_in_efh = (u["col"], u["row"]) in efh
        adj_start = {tuple(h) for h in
                     self.game.neighbors(u["col"], u["row"])}
        face_cost = self.F.action_cost(u, "change_facing", ma)
        free_face = self.F.defs[u["formation"]].get("free_facing")
        kind = self._kind(u)
        start = (u["col"], u["row"], u["facing"])
        best = {start: (0.0, [], 0)}     # cost, disorder-events, minors
        paths = {start: [(u["col"], u["row"])]}
        pq = [(0.0, start)]
        out = {}
        while pq:
            cost, node = heapq.heappop(pq)
            if best.get(node, (1e9,))[0] < cost - 1e-9:
                continue
            c, r, f = node
            _, dis_events, nmc = best[node]
            out.setdefault((c, r, f),
                           (cost, paths[node], list(dis_events)))
            if (c, r) in efh and (c, r) != (u["col"], u["row"]):
                continue                # movement ends here [5.1.3]
            # rotate in place
            if kind != "all" and face_cost is not None:
                for df in (-2, 2):
                    nf = (f + df) % fm.FACINGS
                    ncost = cost + (0 if free_face else face_cost)
                    nn = (c, r, nf)
                    if ncost <= ma + 1e-9 and \
                            ncost < best.get(nn, (1e9,))[0]:
                        nd = list(dis_events)
                        # line: 2nd+ vertex turn per activation = check
                        if kind == "vertex" and \
                                self._line_turn_checks(u, dis_events):
                            nd = dis_events + [("facing_check", c, r)]
                        best[nn] = (ncost, nd, nmc)
                        paths[nn] = paths[node]
                        heapq.heappush(pq, (ncost, nn))
            # advance through front hexside(s)
            for s in fm.facing_sides(f, kind):
                nb = fm.side_neighbor(self.game, c, r, s)
                if not nb or not self.in_area(*nb):
                    continue
                if (u["col"], u["row"]) == (c, r) and start_in_efh and \
                        tuple(nb) in adj_start and tuple(nb) in efh:
                    # may not stay adjacent to the same enemy [5.1.3]
                    shared = set(efh.get((u["col"], u["row"]), [])) & \
                        set(efh.get(tuple(nb), []))
                    if shared:
                        continue
                sc, dis, nmc2 = self.step_cost(u, (c, r), nb, nmc)
                if sc is None:
                    continue
                if not self._stack_ok(u, *nb, moving_through=True):
                    continue
                ncost = cost + sc
                if ncost > ma + 1e-9:
                    continue
                nn = (nb[0], nb[1], f)
                nd = dis_events + ([(dis, nb[0], nb[1])] if dis else [])
                if ncost < best.get(nn, (1e9,))[0]:
                    best[nn] = (ncost, nd, nmc2)
                    paths[nn] = paths[node] + [tuple(nb)]
                    heapq.heappush(pq, (ncost, nn))
        out = {k: v for k, v in out.items()
               if self._stack_ok(self.unit(pid), k[0], k[1])
               or (k[0], k[1]) == (u["col"], u["row"])}
        return out

    def _line_turn_checks(self, u, dis_events):
        """6.3.1/6.3.5: a Line changing facing more than one vertex per
        activation checks disorder for each additional vertex."""
        turns = sum(1 for d in dis_events if d[0] == "facing_check")
        return turns + 1 > 1 or u.get("vertex_turns", 0) + turns + 1 > 1

    def _stack_ok(self, u, c, r, moving_through=False):
        """Stacking Chart [7.1]: same type+formation+division only, SP
        limits by terrain class; skirmishers pass through freely; leaders
        stack free; artillery: 2 batteries alone / 1 with troops."""
        if u["arm"] == "leader":
            return True
        occ = [o for o in self.occupants(c, r, exclude=u["pid"])
               if o["arm"] != "leader"]
        if not occ:
            return True
        if u["formation"] == "skirmish" and moving_through:
            return True     # 6.3.3: moves through at no penalty
        arts = [o for o in occ if o["arm"].startswith("artillery")]
        troops = [o for o in occ if not o["arm"].startswith("artillery")]
        if u["arm"].startswith("artillery"):
            if troops:
                return len(arts) < 1
            return len(arts) < 2
        # troops: same arm + formation + division only [7.1]
        for o in troops:
            if o["arm"] != u["arm"] or o["formation"] != u["formation"] \
                    or o["div"] != u["div"]:
                return False
        terr = self.hex_terrain(c, r)
        tclass = ("village_castle" if terr == "village" else
                  "woods_swamp" if terr in ("woods", "swamp") else "clear")
        lim = self.F.stack_limit(u["arm"].split("_")[0], u["formation"],
                                 tclass)
        if lim is None:
            return False
        return sum(o["sp"] for o in troops) + u["sp"] <= lim

    # ------------------------------------------------------------ propose
    def propose(self, side, action):
        t = action.get("type")
        # pending return-fire window: ONLY the defender may act [8.1.2]
        pf = self.s.get("pending_fire")
        if pf:
            if t not in ("return_fire", "decline_return"):
                return self._v(False,
                               "return-fire decision pending for "
                               f"{pf['defender_side']} [8.1.2]")
            if side != pf["defender_side"]:
                return self._v(False, "the return-fire decision belongs "
                                      "to the defender [8.1.2]")
            return self._propose_return(side, action)
        if t in ("return_fire", "decline_return"):
            return self._v(False, "no offensive fire is pending")
        if self.s["phase"] == "rally":
            if t not in ("rally", "end_rally"):
                return self._v(False, "rally phase: only rally/end_rally "
                                      "[12.0]")
            if side != self.s["mover"]:
                return self._v(False,
                               f"it is {self.s['mover']}'s rally")
            return self._propose_rally(side, action)
        if t in ("rally", "end_rally"):
            return self._v(False, "not the rally phase [12.0]")
        if side != self.s["mover"]:
            return self._v(False, f"it is {self.s['mover']}'s activation")
        if t == "fire":
            return self._propose_fire(side, action)
        if t == "end_turn":
            return self._v(True)
        pid = str(action.get("unit"))
        if pid not in self.s["units"]:
            return self._v(False, f"unknown unit {pid}")
        u = self.unit(pid)
        if u["side"] != side:
            return self._v(False, "not your unit")
        if u.get("dead"):
            return self._v(False, "unit is destroyed")
        if u.get("morale_state") == "routed":
            return self._v(False,
                           "routed units may not move voluntarily "
                           "[9.2.4]")
        if pid in self.s["moved"]:
            return self._v(False,
                           "unit already activated this turn [5.0: one "
                           "activation per unit per turn]")
        if t == "move":
            dest = action.get("dest")
            facing = action.get("facing", u["facing"])
            reach = self.reachable(pid)
            key = (int(dest[0]), int(dest[1]), int(facing))
            if key not in reach:
                return self._v(False,
                               f"({dest[0]},{dest[1]}) facing {facing} is "
                               f"not reachable within MA {u['ma']} through "
                               "front hexsides [5.1/6.1/TEC 5.0]")
            return self._v(True)
        if t == "about_face":
            cost = self.F.action_cost(u, "about_face", u["ma"])
            if cost is None:
                return self._v(False, "about face not allowed for this "
                                      "unit/formation [TEC 5.0]")
            return self._v(True)
        if t == "change_formation":
            to = action.get("to")
            if to not in self.F.defs:
                return self._v(False, f"unknown formation {to}")
            ok, why = self._formation_change_ok(u, to)
            if not ok:
                return self._v(False, why)
            return self._v(True)
        if t == "slide" or t == "reverse":
            ok, why = self._special_move_ok(u, t, action.get("dest"))
            return self._v(ok, *([why] if why else []))
        return self._v(False, f"unknown action type {t}")

    def _formation_change_ok(self, u, to):
        cost = self.F.action_cost(u, "change_formation", u["ma"])
        if cost is None:
            return False, "formation change not allowed [TEC 5.0]"
        if to == u["formation"]:
            return False, "already in that formation"
        if to == "skirmish" and not u.get("skirmish_capable"):
            return False, ("only skirmish-capable units may form "
                           "skirmish order [6.3.3]")
        arm = u["arm"]
        allowed = {
            "infantry": {"line", "column", "disorder", "square",
                         "skirmish"},
            "cavalry": {"line", "column", "disorder"},
            "artillery_foot": {"limbered", "unlimbered"},
            "artillery_horse": {"limbered", "unlimbered"},
        }.get(arm, set())
        if to not in allowed:
            return False, f"{arm} cannot assume {to} [6.3]"
        terr = self.hex_terrain(u["col"], u["row"])
        if u["formation"] == "disorder" and terr in ("woods",):
            return False, ("may not change out of Disorder in woods "
                           "[6.4.1 + designer Q&A: only in proper "
                           "terrain]")
        return True, ""

    def _special_move_ok(self, u, t, dest):
        row = "slide" if t == "slide" else "reverse"
        cell = self.F.tec.cell(row, fm.column_id(u["arm"], u["formation"]))
        if cell is None or cell.prohibited or cell.not_applicable:
            return False, f"{t} not allowed for {u['formation']} [TEC 5.0]"
        hexes = (fm.flank_hexes if t == "slide" else fm.rear_hexes)(
            self.game, u["col"], u["row"], u["facing"], self._kind(u))
        if not dest or tuple(dest) not in {tuple(h) for h in hexes}:
            return False, (f"{t} must target a "
                           f"{'flank' if t == 'slide' else 'rear'} hex "
                           "[6.3.1/6.3.2]")
        if self.occupants(*dest):
            return False, (f"{t} target must be unoccupied "
                           "[6.3.1/6.3.2]")
        terr = self.hex_terrain(*dest)
        base = self.F.entry(u, terr)
        if base is None or base.prohibited or base.cost is None:
            return False, f"{terr} prohibited [TEC 5.0]"
        if cell.whole_ma:
            cost = float(u["ma"])
        elif cell.double:
            cost = 2 * base.cost
        else:
            cost = cell.cost
        if cost > u["ma"] + 1e-9:
            return False, f"costs {cost} MPs, MA is {u['ma']}"
        if not self._stack_ok(u, *dest):
            return False, "stacking violation [7.1]"
        return True, ""

    # ------------------------------------------------------- fire combat
    def on_map(self, u):
        return not u.get("dead")

    def _fire_capable(self, u):
        if u["arm"] == "leader" or u["arm"] == "cavalry":
            return False, "only infantry and artillery fire [8.1]"
        if u.get("dead"):
            return False, "destroyed"
        if u.get("morale_state") == "routed":
            return False, "routed units may not perform combat [9.2.4]"
        if u["formation"] == "limbered":
            return False, "limbered artillery may not fire [6.3.7]"
        return True, ""

    def _fire_range(self, u):
        """Max range: infantry 1 [8.1.6]; artillery per its gun's range
        table (last listed hex)."""
        if not u["arm"].startswith("artillery"):
            return 1
        bands = self.ctables["artillery_range"][u["gun"]["nation"]][
            u["gun"]["type"]]
        return max(b[1] for k, b in bands.items() if k != "note")

    def _in_fire_arc(self, u, tc, tr):
        """Target hex within the firer's front arc: all-around for
        skirmish/square [8.1.5]; otherwise the cone through the front
        hexside(s) (vertex facing = +/-60deg, hexside = +/-30deg)."""
        kind = self._kind(u)
        if kind == "all":
            return True
        fx, fy = self.game.grid.hex_to_pixel(u["col"], u["row"])
        tx, ty = self.game.grid.hex_to_pixel(tc, tr)
        ang = math.degrees(math.atan2(tx - fx, -(ty - fy))) % 360
        face = (u["facing"] * 30.0) % 360
        diff = abs((ang - face + 180) % 360 - 180)
        halfarc = 60.0 if fm.is_vertex(u["facing"]) else 30.0
        return diff <= halfarc + 1e-6

    def _los(self, a, b):
        """Line of Sight [8.1.7]. Returns (clear, why). Conservative on
        straddles: if the center line passes near a hexside, both hexes
        are tested (rule: blocking terrain in either straddled hex
        blocks)."""
        if a == b:
            return False, "same hex"
        na = {tuple(n) for n in self.game.neighbors(*a)}
        if tuple(b) in na:
            return True, "adjacent [8.1.7]"
        ax, ay = self.game.grid.hex_to_pixel(*a)
        bx, by = self.game.grid.hex_to_pixel(*b)
        ea = self.televation.get(f"{a[0]},{a[1]}", 0)
        eb = self.televation.get(f"{b[0]},{b[1]}", 0)
        lo, hi = min(ea, eb), max(ea, eb)
        # collect intervening hexes along two offset sample lines
        steps = max(24, int(math.hypot(bx - ax, by - ay) / 12))
        px, py = -(by - ay), (bx - ax)
        norm = math.hypot(px, py) or 1.0
        px, py = px / norm * 3.0, py / norm * 3.0
        hexes = set()
        for off in (-1, 1):
            for i in range(1, steps):
                x = ax + (bx - ax) * i / steps + px * off
                y = ay + (by - ay) * i / steps + py * off
                c, r, _ = self.game.grid.pixel_to_hex(x, y)
                if (c, r) not in (tuple(a), tuple(b)):
                    hexes.add((c, r))
        occupied = {(v["col"], v["row"]) for v in self.s["units"].values()
                    if self.on_map(v) and v["arm"] != "leader"}
        for h in hexes:
            eh = self.televation.get(f"{h[0]},{h[1]}", 0)
            terr = self.hex_terrain(*h)
            blocker = (h in occupied) or terr in ("village", "castle",
                                                  "woods")
            if eh > hi:
                return False, f"higher ground at {h} [8.1.7]"
            if not blocker:
                continue
            if eh < lo:
                continue                       # below both: clear [8.1.7]
            if eh > lo or ea == eb:
                return False, (f"{'unit' if h in occupied else terr} at "
                               f"{h} blocks [8.1.7]")
            # blocker on the lower unit's level: blocks if closer to it
            lower = a if ea < eb else b
            other = b if lower == a else a
            if self._dist(h, lower) <= \
                    self._dist(h, other):
                return False, f"blocker at {h} near the lower unit [8.1.7]"
        # steep/sharp hexsides between different elevations [8.1.7]
        if ea != eb:
            for pair in self.h_sharp:
                (c1, r1), (c2, r2) = pair
                x1, y1 = self.game.grid.hex_to_pixel(c1, r1)
                x2, y2 = self.game.grid.hex_to_pixel(c2, r2)
                mx, my = (x1 + x2) / 2, (y1 + y2) / 2
                t = ((mx - ax) * (bx - ax) + (my - ay) * (by - ay)) / \
                    ((bx - ax) ** 2 + (by - ay) ** 2)
                if not 0 < t < 1:
                    continue
                lx, ly = ax + (bx - ax) * t, ay + (by - ay) * t
                if math.hypot(lx - mx, ly - my) > 46:
                    continue
                higher = a if ea > eb else b
                dh = min(self._dist((c1, r1), higher),
                         self._dist((c2, r2), higher))
                lowr = b if higher == a else a
                dl = min(self._dist((c1, r1), lowr),
                         self._dist((c2, r2), lowr))
                if dh >= dl:
                    return False, ("sharp slope hexside blocks from "
                                   "below [8.1.7]")
        return True, "clear"

    def _propose_fire(self, side, action):
        pid = str(action.get("unit"))
        if pid not in self.s["units"]:
            return self._v(False, f"unknown unit {pid}")
        u = self.unit(pid)
        if u["side"] != side:
            return self._v(False, "not your unit")
        ok, why = self._fire_capable(u)
        if not ok:
            return self._v(False, why)
        if pid in self.s["fired"]:
            return self._v(False, "unit already fired this turn [8.1.1]")
        tid = str(action.get("target"))
        if tid not in self.s["units"]:
            return self._v(False, f"unknown target {tid}")
        tgt = self.unit(tid)
        if tgt["side"] == side:
            return self._v(False, "cannot fire at friends")
        if not self.on_map(tgt) or tgt["arm"] == "leader":
            return self._v(False, "invalid target")
        rng = self._dist((u["col"], u["row"]), (tgt["col"], tgt["row"]))
        if rng > self._fire_range(u):
            return self._v(False,
                           f"range {rng} exceeds {self._fire_range(u)} "
                           "[8.1.6]")
        if not self._in_fire_arc(u, tgt["col"], tgt["row"]):
            return self._v(False, "target outside the front arc "
                                  "[8.1.5]")
        clear, why = self._los((u["col"], u["row"]),
                               (tgt["col"], tgt["row"]))
        if not clear:
            return self._v(False, f"no LOS: {why}")
        # target hierarchy [8.1.1]: an adjacent front-hex enemy must be
        # targeted before anything farther away
        front = {tuple(h) for h in fm.front_hexes(
            self.game, u["col"], u["row"], u["facing"], self._kind(u))}
        adjacent_enemies = [v for v in self.s["units"].values()
                            if v["side"] != side and self.on_map(v)
                            and v["arm"] != "leader"
                            and (v["col"], v["row"]) in front]
        if adjacent_enemies and (tgt["col"], tgt["row"]) not in front:
            return self._v(False,
                           "an enemy adjacent to a front hexside must "
                           "be targeted first [8.1.1 hierarchy]")
        return self._v(True)

    def _propose_return(self, side, action):
        pf = self.s["pending_fire"]
        if action["type"] == "decline_return":
            return self._v(True)
        d = self.unit(pf["defender"])
        ok, why = self._fire_capable(d)
        if not ok:
            return self._v(False, why)
        if pf["defender"] in self.s["returned"]:
            return self._v(False,
                           "already return/reaction fired this "
                           "activation [8.1.2/8.1.4]")
        firer = self.unit(pf["firer"])
        front = {tuple(h) for h in fm.front_hexes(
            self.game, d["col"], d["row"], d["facing"], self._kind(d))}
        if (firer["col"], firer["row"]) not in front:
            return self._v(False, "firer is not in a front hex [8.1.2]")
        rng = self._dist((d["col"], d["row"]), (firer["col"], firer["row"]))
        if rng > self._fire_range(d):
            return self._v(False, "firer out of range [8.1.2]")
        return self._v(True)

    def _resolve_shot(self, firer, target):
        """One shot through fire.py: returns (record, effect)."""
        T = self.ctables
        steps = 0
        band = None
        if firer["arm"].startswith("artillery"):
            rng = self._dist((firer["col"], firer["row"]), (target["col"], target["row"]))
            steps, band = fire_mod.range_adjustment(
                T, firer["gun"]["nation"], firer["gun"]["type"], rng)
        letter = fire_mod.firer_letter(
            T, firer["fire"], firer["formation"],
            at_breakpoint=self._at_breakpoint(firer), range_steps=steps)
        cls = fire_mod.defense_class(T, target["side"], target["arm"],
                                     target["formation"])
        # column shifts: flank/rear facing + terrain fire shift [8.1.8]
        shift = self._facing_shift(firer, target)
        shift += self._terrain_fire_shift(target)
        die = self.roll_d10()
        res = fire_mod.resolve(T, cls, letter, die, column_shift=shift)
        rec = {"firer": firer["pid"], "target": target["pid"],
               "letter": letter, "class": cls, "die": die,
               "column": res["column"], "cell": res.get("cell", "off"),
               "shift": shift}
        if band:
            rec["band"] = band
        return rec, res["effect"]

    def _facing_shift(self, firer, target):
        """Firing at flank = 1 left, rear = 2 left [8.1.8]; left = lower
        column = harsher. All-around targets have no flank/rear."""
        kind = self._kind(target)
        if kind == "all":
            return 0
        fh = {tuple(h) for h in fm.front_hexes(
            self.game, target["col"], target["row"], target["facing"],
            kind)}
        fl = {tuple(h) for h in fm.flank_hexes(
            self.game, target["col"], target["row"], target["facing"],
            kind)}
        re_ = {tuple(h) for h in fm.rear_hexes(
            self.game, target["col"], target["row"], target["facing"],
            kind)}
        # nearest step of the firer->target line = which aspect: use the
        # adjacent hex of the target closest to the firer's direction
        fx, fy = self.game.grid.hex_to_pixel(firer["col"], firer["row"])
        tx, ty = self.game.grid.hex_to_pixel(target["col"], target["row"])
        best, aspect = None, "front"
        for h, asp in [(h, "front") for h in fh] + \
                      [(h, "flank") for h in fl] + \
                      [(h, "rear") for h in re_]:
            hx, hy = self.game.grid.hex_to_pixel(*h)
            d = math.hypot(hx - fx, hy - fy)
            if best is None or d < best:
                best, aspect = d, asp
        return {"front": 0, "flank": -1, "rear": -2}[aspect]

    def _terrain_fire_shift(self, target):
        """TEC fire column shifts (1R/2R) for the target's hex — columns
        RIGHT (softer) [TEC 5.0 Combat Effects]."""
        eff = self.game.spec["formations"].get("combat_effects") or \
            self.game.spec.get("combat_effects")
        eff = eff or {}
        rows = eff.get("rows", {})
        terr = self.hex_terrain(target["col"], target["row"])
        cell = rows.get(terr, [None])[0] if terr in rows else None
        if cell and cell.endswith("R"):
            return int(cell[0])
        return 0

    def _at_breakpoint(self, u):
        """Unit breakpoint: cumulative losses > half original strength
        [11.1]; artillery never [11.1 exception]."""
        if u["arm"].startswith("artillery"):
            return False
        orig = u["sp"] + u["sp_lost"]
        return u["sp_lost"] > orig / 2

    # -------------------------------------------------- effects (Family C)
    def _apply_effect(self, u, effect, out, drm_extra=0):
        """Apply a typed fire effect [8.1.8] to the ledger [9.x/10/11]."""
        if effect["kind"] == "no_effect":
            out.setdefault("effects", []).append(
                {"unit": u["pid"], "result": "no effect"})
            return
        if u["morale_state"] == "routed":
            # any non-NE fire result destroys a routed unit [9.2.4]
            self._destroy(u, out, "routed unit hit [9.2.4]")
            return
        if effect["kind"] == "sp_loss":
            self._lose_sp(u, effect["sp"], out)
            if u.get("dead"):
                return
            self._morale_check(u, effect["then"]["drm"], out)
        elif effect["kind"] == "morale_check":
            self._morale_check(u, effect["drm"] + drm_extra, out)

    def _lose_sp(self, u, n, out):
        n = min(n, u["sp"])
        u["sp"] -= n
        u["sp_lost"] += n
        out.setdefault("effects", []).append(
            {"unit": u["pid"], "sp_loss": n, "sp_left": u["sp"]})
        if u["sp"] <= 0:
            self._destroy(u, out, "no strength points remain")

    def _destroy(self, u, out, why):
        u["dead"] = True
        out.setdefault("effects", []).append(
            {"unit": u["pid"], "destroyed": True, "why": why})

    def _morale_drms(self, u):
        d = []
        if u["formation"] == "square":
            d.append(-1)
        if u["formation"] == "line":
            d.append(1)
        if self._at_breakpoint(u):
            d.append(1)
        if u["morale_state"] == "shaken":
            d.append(1)
        elif u["morale_state"] in ("unsteady", "routed"):
            d.append(2)
        if any(v["arm"] == "leader" and v["side"] == u["side"]
               and (v["col"], v["row"]) == (u["col"], u["row"])
               and self.on_map(v) for v in self.s["units"].values()):
            d.append(-1)
        return d

    _LADDER = ["good", "shaken", "unsteady", "routed"]

    def _morale_check(self, u, drm, out):
        """Morale Check Table [9.1] with unit-state DRMs [9.1 panel];
        artillery converts lost levels to SPs [9.3]."""
        die = self.roll_d10()
        drms = self._morale_drms(u) + [drm]
        lost = fire_mod.morale_check(self.ctables, die, u["morale"], drms)
        rec = {"unit": u["pid"], "morale_die": die, "drms": drms,
               "vs": u["morale"], "levels_lost": lost}
        out.setdefault("effects", []).append(rec)
        if lost == 0:
            return
        if u["arm"].startswith("artillery"):
            rec["artillery_sp_for_levels"] = lost      # [9.3]
            self._lose_sp(u, lost, out)
            return
        i = self._LADDER.index(u["morale_state"])
        new = self._LADDER[min(3, i + lost)]
        self._set_morale_state(u, new, out)

    def _set_morale_state(self, u, new, out):
        old = u["morale_state"]
        if new == old:
            return
        u["morale_state"] = new
        out.setdefault("effects", []).append(
            {"unit": u["pid"], "morale_state": new})
        if new == "routed":
            self._disorder(u)                          # [9.2.4]
            self._retreat(u, -(-u["ma"] // 2), out, routed=True)
            self._neighbor_checks(u, out)
        elif new == "unsteady":
            dist = 2 if u["arm"] == "cavalry" else 1   # [9.2.3/10.0]
            self._retreat(u, dist, out, routed=False)
            self._neighbor_checks(u, out)

    def _neighbor_checks(self, u, out):
        """Stacked + adjacent friends check morale on rout/unsteady
        retreat [9.2.3/9.2.4]; chains bound by the ladder's top."""
        here_or_adj = {(u["col"], u["row"])} | \
            {tuple(n) for n in self.game.neighbors(u["col"], u["row"])}
        for v in list(self.s["units"].values()):
            if v["pid"] == u["pid"] or v["side"] != u["side"]:
                continue
            if not self.on_map(v) or v["arm"] == "leader":
                continue
            if (v["col"], v["row"]) in here_or_adj:
                self._morale_check(v, 0, out)

    def _retreat(self, u, dist, out, routed):
        """Retreat procedure [10.1]: away from enemies, unoccupied
        preferred, no prohibited terrain/enemy hexes, no revisits;
        1 SP per hex short [10.1.1]. Unsteady keeps facing; routed
        faces the retreat direction [10.1]."""
        enemies = [(v["col"], v["row"]) for v in self.s["units"].values()
                   if v["side"] != u["side"] and self.on_map(v)
                   and v["arm"] != "leader"]

        def edist(c, r):
            return min([self._dist((c, r), (ec, er))
                        for ec, er in enemies] or [99])

        path = [(u["col"], u["row"])]
        for _ in range(dist):
            c, r = path[-1]
            best = None
            for nb in self.game.neighbors(c, r):
                nb = tuple(nb)
                if nb in path or not self.in_area(*nb):
                    continue
                if self.hex_terrain(*nb) == "water":
                    continue
                cell = self.F.entry(u, self.hex_terrain(*nb))
                if cell is None or cell.prohibited:
                    continue
                if any((v["col"], v["row"]) == nb and v["side"] != u["side"]
                       and self.on_map(v)
                       for v in self.s["units"].values()):
                    continue
                occ = bool(self.occupants(*nb, exclude=u["pid"]))
                key = (edist(*nb), not occ)
                if best is None or key > best[0]:
                    best = (key, nb)
            if best is None or best[0][0] < edist(c, r):
                break
            path.append(best[1])
        short = dist - (len(path) - 1)
        if len(path) > 1:
            u["col"], u["row"] = path[-1]
            if routed:
                # face the retreat direction (away from origin)
                fx, fy = self.game.grid.hex_to_pixel(*path[-2])
                tx, ty = self.game.grid.hex_to_pixel(*path[-1])
                ang = math.degrees(math.atan2(tx - fx, -(ty - fy))) % 360
                u["facing"] = int(round(ang / 30.0)) % 12
        out.setdefault("effects", []).append(
            {"unit": u["pid"], "retreat": [list(p) for p in path[1:]],
             "short": short})
        if short > 0:
            self._lose_sp(u, short, out)               # [10.1.1]

    # ------------------------------------------------------------ rally
    def _propose_rally(self, side, action):
        if action["type"] == "end_rally":
            return self._v(True)
        pid = str(action.get("unit"))
        if pid not in self.s["units"]:
            return self._v(False, f"unknown unit {pid}")
        u = self.unit(pid)
        if u["side"] != side:
            return self._v(False, "not your unit")
        if not self.on_map(u):
            return self._v(False, "unit is destroyed")
        if u["morale_state"] == "good":
            return self._v(False, "already in good morale [12.0]")
        if pid in self.s.setdefault("rallied", []):
            return self._v(False, "already attempted this rally phase")
        enemies_adj = any(
            v["side"] != side and self.on_map(v) and v["arm"] != "leader"
            and self._dist((u["col"], u["row"]), (v["col"], v["row"])) == 1
            for v in self.s["units"].values())
        if enemies_adj:
            return self._v(False,
                           "units adjacent to the enemy may not rally "
                           "[12.0 exception]")
        return self._v(True)

    # -------------------------------------------------------------- apply
    def _apply(self, side, action, verdict):
        t = action["type"]
        if t == "end_turn":
            return self._end_turn()
        if t == "fire":
            return self._apply_fire(side, action)
        if t in ("return_fire", "decline_return"):
            return self._apply_return(side, action)
        if t == "rally":
            return self._apply_rally(side, action)
        if t == "end_rally":
            return self._end_rally()
        pid = str(action["unit"])
        u = self.unit(pid)
        result = {"unit": pid}
        if t == "move":
            dest = action["dest"]
            facing = int(action.get("facing", u["facing"]))
            cost, path, dis_events = self.reachable(pid)[
                (int(dest[0]), int(dest[1]), facing)]
            u["col"], u["row"], u["facing"] = int(dest[0]), int(dest[1]), \
                facing
            result.update(cost=round(cost, 2), path=[list(p) for p in path],
                          facing=facing)
            rolls = []
            for kind, c, r in dis_events:
                if u["formation"] == "disorder":
                    continue
                if kind == "auto":
                    self._disorder(u)
                    rolls.append({"at": [c, r], "auto": True})
                else:   # movement disorder check [5.1.1]: d10 vs morale
                    v = self.roll_d10()
                    failed = v > u["morale"]
                    if failed:
                        self._disorder(u)
                    rolls.append({"at": [c, r], "roll": v,
                                  "vs_morale": u["morale"],
                                  "disordered": failed})
                    if failed:
                        break
            if rolls:
                result["disorder"] = rolls
                result["formation"] = u["formation"]
        elif t == "about_face":
            u["facing"] = (u["facing"] + fm.HEXSIDES) % fm.FACINGS
            result.update(facing=u["facing"])
        elif t == "change_formation":
            to = action["to"]
            u["formation"] = to
            # facing parity follows the formation family [6.3.1/6.3.2]
            want_vertex = self.F.kind(to) == "vertex"
            if want_vertex and u["facing"] % 2 == 0:
                u["facing"] = (u["facing"] + 1) % fm.FACINGS
            elif not want_vertex and u["facing"] % 2 == 1 \
                    and self.F.kind(to) == "hexside":
                u["facing"] = (u["facing"] + 1) % fm.FACINGS
            result.update(formation=to, facing=u["facing"])
        elif t in ("slide", "reverse"):
            dest = action["dest"]
            u["col"], u["row"] = int(dest[0]), int(dest[1])
            result.update(dest=[u["col"], u["row"]])
        self.s["moved"].append(pid)
        return result

    def _disorder(self, u):
        u["formation"] = "disorder"
        if u["facing"] % 2 == 1:
            u["facing"] = (u["facing"] + 1) % fm.FACINGS

    def roll_d10(self):
        """Engine-owned d10, 0-9 (the game die: 0 is 0, not 10 [2.0])."""
        r = self._rng()
        v = int(r.random() * 10)
        self.s["rng_calls"] += 1
        return v

    def _apply_fire(self, side, action):
        pid, tid = str(action["unit"]), str(action["target"])
        u, tgt = self.unit(pid), self.unit(tid)
        self.s["fired"].append(pid)
        self.s["moved"].append(pid) if pid not in self.s["moved"] else None
        # is the defender entitled to a return-fire decision? [8.1.2]
        can_return = False
        ok, _ = self._fire_capable(tgt)
        if ok and tid not in self.s["returned"]:
            front = {tuple(h) for h in fm.front_hexes(
                self.game, tgt["col"], tgt["row"], tgt["facing"],
                self._kind(tgt))}
            if (u["col"], u["row"]) in front and \
                    self._dist((u["col"], u["row"]), (tgt["col"], tgt["row"])) \
                    <= self._fire_range(tgt):
                can_return = True
        if can_return:
            self.s["pending_fire"] = {
                "firer": pid, "defender": tid,
                "defender_side": tgt["side"]}
            return {"pending_return": tid,
                    "note": "defender decides return fire [8.1.2]"}
        rec, effect = self._resolve_shot(u, tgt)
        out = {"offensive": rec}
        self._apply_effect(tgt, effect, out)
        return out

    def _apply_return(self, side, action):
        pf = self.s["pending_fire"]
        self.s["pending_fire"] = None
        firer = self.unit(pf["firer"])
        dfn = self.unit(pf["defender"])
        of_rec, of_eff = self._resolve_shot(firer, dfn)
        out = {"offensive": of_rec}
        if action["type"] == "return_fire":
            self.s["returned"].append(pf["defender"])
            rf_rec, rf_eff = self._resolve_shot(dfn, firer)
            out["return"] = rf_rec
            # simultaneous [8.1.2]: both resolved on pre-fire states,
            # then both applied
            self._apply_effect(firer, rf_eff, out)
        self._apply_effect(dfn, of_eff, out)
        return out

    def _apply_rally(self, side, action):
        u = self.unit(str(action["unit"]))
        self.s.setdefault("rallied", []).append(u["pid"])
        die = self.roll_d10()
        drms = self._morale_drms(u)
        lost = fire_mod.morale_check(self.ctables, die, u["morale"], drms)
        out = {"unit": u["pid"], "rally_die": die, "drms": drms,
               "passed": lost == 0}
        if lost == 0:
            i = self._LADDER.index(u["morale_state"])
            new = self._LADDER[max(0, i - 1)]
            # routed-once units cap at shaken [12.2]; mark the cap
            if u["morale_state"] == "routed":
                u["r_cap"] = True
                u["formation"] = "disorder"    # stays disordered [12.2]
            if u["r_cap"] and new == "good":
                new = "shaken"
            u["morale_state"] = new
            out["morale_state"] = new
        return out

    def _end_rally(self):
        a, b = self.game.side_order
        if self.s["mover"] == self.first_player:
            self.s["mover"] = b if self.first_player == a else a
            return {"rally": self.s["mover"]}
        # both sides done: Rout Loss Segment [12.4], then next turn
        out = {"rout_loss": []}
        for u in self.s["units"].values():
            if self.on_map(u) and u["morale_state"] == "routed":
                sub = {}
                self._lose_sp(u, 1, sub)
                if not u.get("dead"):
                    self._retreat(u, 1, sub, routed=True)
                out["rout_loss"].append({"unit": u["pid"], **sub})
        self._next_turn()
        out.update(turn=self.s["turn"], mover=self.s["mover"])
        return out

    def _end_turn(self):
        a, b = self.game.side_order
        if self.s["mover"] == self.first_player:
            self.s["mover"] = b if self.first_player == a else a
            self.s["moved"] = []
            self.s["returned"] = []
            return {"turn": self.s["turn"], "mover": self.s["mover"]}
        # second side finished: rally phase if anyone can/needs it [12.0]
        needy = any(self.on_map(u) and u.get("morale_state", "good")
                    != "good" for u in self.s["units"].values())
        if needy:
            self.s["phase"] = "rally"
            self.s["mover"] = self.first_player
            self.s["rallied"] = []
            self.s["moved"] = []
            self.s["returned"] = []
            return {"phase": "rally", "mover": self.s["mover"]}
        self._next_turn()
        return {"turn": self.s["turn"], "mover": self.s["mover"]}

    def _next_turn(self):
        self.s["mover"] = self.first_player
        self.s["turn"] += 1
        self.s["phase"] = "movement"
        self.s["moved"] = []
        self.s["fired"] = []
        self.s["returned"] = []
        self.s["rallied"] = []
        self.s["victory"] = self._victory_state()

    # ---------------------------------------------------------- victory
    def _victory_state(self):
        """A15.1: French win at 7 Russian units destroyed/routed/
        unsteady; Russians at 10 French; first to reach it wins."""
        counts = {}
        for side in self.game.side_order:
            counts[side] = sum(
                1 for u in self.s["units"].values()
                if u["side"] == side and u["arm"] != "leader"
                and (u.get("dead")
                     or u.get("morale_state") in ("routed", "unsteady")))
        french_needs, russian_needs = 7, 10
        if counts.get("Allied", 0) >= french_needs:
            return {"winner": "French", "cite": "A15.1", "counts": counts}
        if counts.get("French", 0) >= russian_needs:
            return {"winner": "Allied", "cite": "A15.1", "counts": counts}
        return {"winner": None, "counts": counts}

    # ------------------------------------------------------------ queries
    def flow(self):
        v = self.s.get("victory") or self._victory_state()
        return {"turn": self.s["turn"], "turn_label": self.turn_label(),
                "mover": self.s["mover"], "phase": self.s["phase"],
                "moved": list(self.s["moved"]),
                "pending_fire": self.s.get("pending_fire"),
                "victory": v,
                "over": bool(v.get("winner"))
                or self.s["turn"] > self.turns}

    def legal_moves(self, pid):
        u = self.unit(pid)
        reach = self.reachable(pid)
        out = []
        for (c, r, f), (cost, path, dis) in reach.items():
            if (c, r, f) == (u["col"], u["row"], u["facing"]):
                continue
            out.append({"dest": [c, r], "facing": f,
                        "cost": round(cost, 2),
                        "disorder_risk": bool(dis)})
        return out
