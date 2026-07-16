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
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import json

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
        self._resolve_tier(tier)
        self._resume_or_new(self._fresh_seed(seed),
                            required=("units", "moved", "tier"))

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
                "skirmish_capable": u.get("skirmish_capable", False),
                "div": u.get("div", ""),
                "vertex_turns": 0,
            }
        self.s = {"turn": 1, "phase": "movement",
                  "mover": self.first_player, "units": units,
                  "moved": [], "seed": seed, "rng_calls": 0,
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
        if side != self.s["mover"]:
            return self._v(False, f"it is {self.s['mover']}'s activation")
        if t == "end_turn":
            return self._v(True)
        pid = str(action.get("unit"))
        if pid not in self.s["units"]:
            return self._v(False, f"unknown unit {pid}")
        u = self.unit(pid)
        if u["side"] != side:
            return self._v(False, "not your unit")
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

    # -------------------------------------------------------------- apply
    def _apply(self, side, action, verdict):
        t = action["type"]
        if t == "end_turn":
            return self._end_turn()
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

    def _end_turn(self):
        a, b = self.game.side_order
        if self.s["mover"] == self.first_player:
            self.s["mover"] = b if self.first_player == a else a
        else:
            self.s["mover"] = self.first_player
            self.s["turn"] += 1
        self.s["moved"] = []
        return {"turn": self.s["turn"], "mover": self.s["mover"]}

    # ------------------------------------------------------------ queries
    def flow(self):
        return {"turn": self.s["turn"], "turn_label": self.turn_label(),
                "mover": self.s["mover"], "phase": self.s["phase"],
                "moved": list(self.s["moved"]),
                "over": self.s["turn"] > self.turns}

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
