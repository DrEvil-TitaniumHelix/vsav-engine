import heapq
import math

try:
    from .gate import GateGame
except ImportError:
    from gate import GateGame


class NawGame(GateGame):
    HASH_KEYS = ("turn", "phase", "mover", "over", "winner", "rng_calls", "units",
                 "moved", "done", "pool", "exited", "dead", "losses", "demoralized",
                 "fought", "defended", "advanced", "battle_no", "pending")
    TURN_NOUN = "Game-Turn"

    def __init__(self, game, scenario_path, live_dir, seed=None, tier=None):
        super().__init__(game, scenario_path, live_dir)
        self.reserve = {u["id"]: u for u in self.scenario.get("reserve", [])}
        self.schedule = self.reserve
        self.catalog = {u["id"]: u for u in
                        self.scenario.get("units", []) + self.scenario.get("reserve", [])}
        self.exit_hexes = {(int(h[:2]), int(h[2:])) for h in game.spec["exit"]["hexes"]}
        self.exit_side = game.spec["exit"]["side"]
        self.exit_cost = float(game.spec["exit"]["cost_mp"])
        self._resolve_tier(tier)
        self._resume_or_new(seed, required=("losses", "moved"))

    def new_game(self, seed=None):
        seed = self._fresh_seed(seed)
        units = self._scenario_units()
        self.s = {
            "seed": seed, "rng_calls": 0, "n": 0, "tier": self.tier,
            "turn": 1, "phase": "movement", "mover": self.first_player,
            "over": False, "winner": None,
            "units": units,
            "moved": {},
            "done": [],
            "pool": {pid: e["due"] for pid, e in self.reserve.items()},
            "exited": [],
            "dead": [],
            "losses": {s: 0 for s in self.game.side_order},
            "demoralized": False,
            "fought": [], "defended": [], "advanced": [],
            "battle_no": 0,
            "pending": None,
        }
        self._reset_log()
        self._log({"event": "init", "mode": "naw",
                   "scenario": self.scenario["name"], "tier": self.tier,
                   "rules_scope": self.rules_scope(), "seed": seed,
                   "turns": self.turns, "first_player": self.first_player,
                   "units": self._units_for_log(units)})
        self.save()

    def rules_scope(self):
        sc = self.scenario.get("rules_scope", {})
        return {"enforced": sc.get("enforced", []),
                "not_enforced": sc.get("not_yet_enforced", []),
                "rulings": sc.get("rulings", []) + [f"OPEN for Bruce: {q}" for q in sc.get("open_for_bruce", [])]}

    def _scenario_units(self):
        return {u["id"]: {"pid": u["id"], "slot": u["slot"], "name": u.get("name", u["slot"]), "side": u["side"],
                          "col": u["hex"][0], "row": u["hex"][1]}
                for u in self.scenario["units"]}

    def cat(self, pid):
        return self.catalog[str(pid)]

    def cls(self, pid):
        return self.cat(pid)["cls"]

    def stats(self, pid):
        return self.cat(pid)["stats"]

    def _live(self, side=None):
        for u in self.s["units"].values():
            if side is None or u["side"] == side:
                yield u

    def rules_board(self, exclude_pid=None):
        return [dict(id=u["pid"], name=u["slot"], side=u["side"], col=u["col"], row=u["row"])
                for u in self._live() if u["pid"] != exclude_pid]

    def _board_sets(self, side, exclude_pid=None):
        board = self.rules_board(exclude_pid=exclude_pid)
        enemy = self.game.enemy(side)
        epos = {(b["col"], b["row"]) for b in board if b["side"] == enemy}
        fpos = {(b["col"], b["row"]) for b in board if b["side"] == side}
        ezoc = self.game.zoc_hexes(board, enemy)
        return board, epos, fpos, ezoc

    def in_ezoc(self, pid):
        u = self.unit(pid)
        _, _, _, ezoc = self._board_sets(u["side"], exclude_pid=str(pid))
        return (u["col"], u["row"]) in ezoc

    def budget(self, pid):
        return float(self.stats(pid)["ma"])

    def dests(self, pid):
        pid = str(pid)
        u = self.unit(pid)
        board, epos, fpos, ezoc = self._board_sets(u["side"], exclude_pid=pid)
        start = (u["col"], u["row"])
        if start in ezoc:
            return {}
        ma = self.budget(pid)
        best = {start: 0.0}
        pq = [(0.0, start)]
        while pq:
            cost, cur = heapq.heappop(pq)
            if cost > best.get(cur, 1e9):
                continue
            if cur != start and cur in ezoc:
                continue
            for nb in self.game.neighbors(*cur):
                if nb in epos or not self.game.on_map(*nb):
                    continue
                c = self.game.move_cost(cur, nb)
                if c is None:
                    continue
                nc = cost + c
                if nc > ma + 1e-9 or nc >= best.get(nb, 1e9):
                    continue
                best[nb] = nc
                heapq.heappush(pq, (nc, nb))
        best.pop(start, None)
        return {h: c for h, c in best.items() if h not in fpos}

    def exit_options(self, pid):
        pid = str(pid)
        u = self.unit(pid)
        if u["side"] != self.exit_side:
            return {}
        start = (u["col"], u["row"])
        _, _, _, ezoc = self._board_sets(u["side"], exclude_pid=pid)
        if start in ezoc:
            return {}
        cand = dict(self.dests(pid))
        cand[start] = 0.0
        ma = self.budget(pid)
        return {h: c + self.exit_cost for h, c in cand.items()
                if h in self.exit_hexes and h not in ezoc and c + self.exit_cost <= ma + 1e-9}

    def _cbt(self):
        return self.game.spec["combat"]

    def attack_strength(self, atk_ids):
        return sum(self.stats(p)["att"] for p in atk_ids)

    def defense_strength(self, def_ids):
        doubles = set(self._cbt()["terrain_effects"]["defender_doubles_in"])
        tot = 0
        for p in def_ids:
            u = self.unit(p)
            d = self.stats(p)["def"]
            tot += d * 2 if self.game.hex_terrain(u["col"], u["row"]) in doubles else d
        return tot

    def odds_column(self, a, d):
        cols = self._cbt()["crt"]["odds_columns"]
        if d <= 0:
            return cols[-1]
        if a <= 0:
            return cols[0]
        col = f"{int(math.floor(a / d))}:1" if a >= d else f"1:{int(math.ceil(d / a))}"
        if col not in cols:
            n, m = (int(x) for x in col.split(":"))
            return cols[-1] if n > m else cols[0]
        return col

    def crt_result(self, col, die):
        crt = self._cbt()["crt"]
        return crt["die_rows"][str(die)][crt["odds_columns"].index(col)]

    def _adjacent(self, a, b):
        return (b["col"], b["row"]) in self.game.neighbors(a["col"], a["row"])

    def _bombard_los(self, art, dfd):
        a, d = (art["col"], art["row"]), (dfd["col"], dfd["row"])
        if self.game.hex_distance(a, d) != 2:
            return False, "not exactly two hexes away [ART-01: artillery bombards a unit from two hexes distance]"
        between = set(self.game.neighbors(*a)) & set(self.game.neighbors(*d))
        woods = [self.game.grid.hexnum(*h) for h in sorted(between) if self.game.hex_terrain(*h) == "woods"]
        if woods:
            return False, f"line of fire crosses Woods hex {'/'.join(woods)} [ART-17/TEC row 3: artillery may not fire over an intervening Woods hex - enforced on every candidate intervening hex, NAW2-OR-9 pending]"
        return True, "bombardment at two hexes; intervening units and Town hexes do not block [ART-01/ART-16]"

    def battle_check(self, side, atk_ids, def_ids):
        s = self.s
        atk_ids = [str(p) for p in atk_ids]
        def_ids = [str(p) for p in def_ids]
        if s["phase"] != "combat":
            return False, ["attacks only in the own Combat Phase [SEQ-06/MOV-04: no combat during the Movement Phase]"], None
        if not atk_ids or not def_ids:
            return False, ["an attack names at least one attacker and one defender [CBT-01]"], None
        if len(set(atk_ids)) != len(atk_ids) or len(set(def_ids)) != len(def_ids):
            return False, ["a unit is named twice [CBT-17: Combat Strength is used as an integral whole]"], None
        enemy = self.game.enemy(side)
        for p in atk_ids:
            if p not in s["units"] or self.unit(p)["side"] != side:
                return False, [f"attacker {p} is not a {side} unit on the map [SEQ-08]"], None
            if p in s["fought"]:
                return False, [f"{self.unit(p)['name']} has already attacked this Combat Phase [CBT-10]"], None
        for p in def_ids:
            if p not in s["units"] or self.unit(p)["side"] != enemy:
                return False, [f"defender {p} is not an enemy unit on the map [CBT-05]"], None
            if p in s["defended"]:
                return False, [f"{self.unit(p)['name']} has already been attacked this Combat Phase [CBT-10]"], None
        dfd = [self.unit(p) for p in def_ids]
        melee, bomb = [], []
        for p in atk_ids:
            u = self.unit(p)
            adj = [d for d in dfd if self._adjacent(u, d)]
            if len(adj) == len(dfd):
                melee.append(p)
                continue
            if self.cls(p) != "artillery":
                return False, [f"{u['name']} is not adjacent to every defender it attacks [CBT-05 adjacency; CBT-11 all attackers adjacent to the defender; CBT-12 the attacker adjacent to every defender it combines]"], None
            if adj:
                return False, [f"{u['name']} is adjacent to some but not all defenders [CBT-11/CBT-12/ART-14]"], None
            if len(dfd) != 1:
                return False, [f"{u['name']} bombards from two hexes: a bombarding artillery unit may only attack a single unit [ART-13]"], None
            ok, why = self._bombard_los(u, dfd[0])
            if not ok:
                return False, [f"{u['name']}: {why}"], None
            bomb.append(p)
        a = self.attack_strength(atk_ids)
        d = self.defense_strength(def_ids)
        col = self.odds_column(a, d)
        return True, [f"attack {a} vs {d} = {col} [CBT-01/CBT-02 rounded in favour of the defender; clamp 1:5..6:1]"], {
            "attack": a, "defense": d, "column": col, "melee": melee, "bombarding": bomb}

    def battle_preview(self, side, atk_ids, def_ids, bomb_ids=None):
        ok, reasons, meta = self.battle_check(side, atk_ids, def_ids)
        out = {"legal": ok, "reasons": reasons, "needs_supply": False}
        if meta:
            out.update(odds=meta["column"], column=meta["column"], factors=[meta["attack"], meta["defense"]],
                       bombarding=meta["bombarding"], melee=meta["melee"])
        else:
            out.update(odds=None)
        return out

    def propose(self, side, action):
        s = self.s
        t = action.get("type")
        if s["over"]:
            return self._v(False, "the game is over [SEQ-05: play ends when one player wins or the tenth turn is completed]")
        if s["pending"]:
            p = s["pending"]
            if t != p["awaiting"]:
                return self._v(False, f"pending {p['awaiting']} must be resolved first")
            if side != p["by"]:
                return self._v(False, f"the {p['by']} player owns the pending {p['awaiting']}")
        elif side != s["mover"]:
            return self._v(False, f"not {side}'s Player-Turn [SEQ-02/SEQ-08: no Allied movement or attacking during the French Player-Turn and vice-versa]")
        fn = {"move": self._propose_move, "exit": self._propose_exit}.get(t)
        if fn:
            return fn(side, action)
        if t == "end_movement":
            if s["phase"] != "movement":
                return self._v(False, "not the Movement Phase [SEQ-03]")
            return self._v(True, "Movement Phase complete; Combat Phase begins [SEQ-03/SEQ-04]")
        if t == "end_phase":
            return self._propose_end_phase(side)
        return self._v(False, f"unknown action type {t!r}")

    def _gate_unit(self, side, action):
        pid = str(action.get("unit"))
        if pid not in self.s["units"]:
            return None, self._v(False, f"no such unit on the map: {pid}")
        u = self.unit(pid)
        if u["side"] != side:
            return None, self._v(False, f"{u['slot']} is not a {side} unit [SEQ-08]")
        return u, None

    def _propose_move(self, side, action):
        s = self.s
        if s["phase"] != "movement":
            return self._v(False, "movement only in the own Movement Phase [SEQ-07: no movement during the Combat Phase except as directed by the CRT]")
        u, err = self._gate_unit(side, action)
        if err:
            return err
        pid = u["pid"]
        if pid in s["done"]:
            return self._v(False, f"{u['slot']} has already moved this Player-Turn [MOV-19: once a unit has been moved it may not be moved any further during that Player-Turn]")
        if self.in_ezoc(pid):
            return self._v(False, f"{u['slot']} begins the Movement Phase in an enemy Zone of Control and MAY NOT MOVE AT ALL [MOV-13; ZOC-05/ZOC-08 mutual lock until combat destroys or retreats one of the units]")
        dest = tuple(action.get("dest", ()))
        dd = self.dests(pid)
        if dest not in dd:
            return self._v(False, f"{self.game.grid.hexnum(*dest) if len(dest) == 2 else dest} is not a legal destination for {u['slot']} [MOV-05/MOV-15 one MP per hex within MA {self.stats(pid)['ma']}; MOV-06 consecutive hexes; MOV-08 never through or into enemy units; MOV-09 never end stacked; MOV-10/ZOC-04 stop on entering an enemy ZOC, MOV-11 never through one; MOV-16/17/18 Woods only via Woods/Road hexes along the road]")
        return self._v(True, f"move {u['slot']} to {self.game.grid.hexnum(*dest)} for {dd[dest]:g} MP [MOV-02/MOV-05: one Movement Point per hex entered]")

    def _propose_exit(self, side, action):
        s = self.s
        if s["phase"] != "movement":
            return self._v(False, "exiting is movement: own Movement Phase only [VIC-09/SEQ-07]")
        u, err = self._gate_unit(side, action)
        if err:
            return err
        pid = u["pid"]
        if side != self.exit_side:
            return self._v(False, "Allied units may never exit from the map, even to avoid being destroyed [VIC-12; REI-07 Prussians may not leave the map once brought on]")
        if pid in s["done"]:
            return self._v(False, f"{u['slot']} has already moved this Player-Turn [MOV-19]")
        via = tuple(action.get("via") or (u["col"], u["row"]))
        opts = self.exit_options(pid)
        if via not in opts:
            if via not in self.exit_hexes:
                return self._v(False, f"{self.game.grid.hexnum(*via) if len(via) == 2 else via} is not an arrowed exit hex - French units exit only from the eleven arrowed North-edge hexes 0101-1101 [VIC-08]")
            return self._v(False, f"{u['slot']} cannot reach {self.game.grid.hexnum(*via)} and still pay the exit: exiting expends one Movement Point [VIC-09], the exit hex must be reachable within MA {self.stats(pid)['ma']} and free of enemy ZOC [MOV-10/MOV-13: a unit in an enemy ZOC must stop / may not move]")
        return self._v(True, f"{u['slot']} exits the map via {self.game.grid.hexnum(*via)} for {opts[via]:g} MP [VIC-08/VIC-09; VIC-10 it may not return; VIC-06 not a French loss]")

    def _propose_end_phase(self, side):
        s = self.s
        if s["phase"] != "combat":
            return self._v(False, "end_phase closes the Combat Phase - use end_movement to close the Movement Phase [SEQ-03]")
        if s["pending"]:
            return self._v(False, "resolve the pending step first")
        return self._v(True, "Combat Phase complete [SEQ-04]")

    def _apply(self, side, action, verdict):
        s = self.s
        t = action["type"]
        ev = []
        if t == "move":
            pid = str(action["unit"])
            u = self.unit(pid)
            dest = tuple(action["dest"])
            cost = self.dests(pid)[dest]
            frm = self.game.grid.hexnum(u["col"], u["row"])
            u["col"], u["row"] = dest
            s["moved"][pid] = cost
            s["done"].append(pid)
            ev.append({"move": u["slot"], "from": frm, "to": list(dest), "mp": cost})
        elif t == "exit":
            pid = str(action["unit"])
            u = self.unit(pid)
            via = tuple(action.get("via") or (u["col"], u["row"]))
            cost = self.exit_options(pid)[via]
            s["exited"].append(pid)
            s["moved"][pid] = cost
            s["done"].append(pid)
            del s["units"][pid]
            ev.append({"exit": u["slot"], "via": self.game.grid.hexnum(*via), "mp": cost,
                       "exited_total": len(s["exited"])})
        elif t == "end_movement":
            s["phase"] = "combat"
            ev.append({"phase": "combat", "mover": s["mover"]})
        elif t == "end_phase":
            ev += self._end_player_turn(side)
        return ev

    def _end_player_turn(self, side):
        s = self.s
        ev = []
        order = self.game.side_order
        s["phase"] = "movement"
        s["moved"], s["done"] = {}, []
        s["fought"], s["defended"], s["advanced"] = [], [], []
        s["pending"] = None
        if s["mover"] == order[0]:
            s["mover"] = order[1]
            ev.append({"player_turn": s["mover"], "turn": s["turn"]})
        else:
            s["turn"] += 1
            s["mover"] = order[0]
            if s["turn"] > self.turns:
                ev += self._game_end()
            else:
                ev.append({"game_turn": s["turn"], "label": self.turn_label()})
        return ev

    def _game_end(self):
        s = self.s
        s["over"] = True
        s["winner"] = "draw"
        return [{"game_over": True, "winner": "draw",
                 "why": "tenth Game-Turn completed with neither side at forty Strength Points [SEQ-05/VIC-04]"}]

    def legal_moves(self, pid):
        pid = str(pid)
        s = self.s
        if pid not in s["units"]:
            return {"can_act": False, "reasons": ["unit is not on the map"], "dests": []}
        u = self.unit(pid)
        if s["over"]:
            return {"can_act": False, "reasons": ["the game is over [SEQ-05]"], "dests": []}
        if s["phase"] != "movement":
            return {"can_act": False, "reasons": ["movement only in the Movement Phase [SEQ-07]"], "dests": []}
        if u["side"] != s["mover"]:
            return {"can_act": False, "reasons": [f"not {u['side']}'s Player-Turn [SEQ-08]"], "dests": []}
        if pid in s["done"]:
            return {"can_act": False, "reasons": [f"{u['slot']} has already moved this Player-Turn [MOV-19]"], "dests": []}
        if self.in_ezoc(pid):
            return {"can_act": False, "reasons": [f"{u['slot']} begins the Movement Phase in an enemy Zone of Control - it may not move at all [MOV-13]"], "dests": []}
        out = {"can_act": True, "reasons": [], "budget": self.budget(pid), "dests": [], "exits": []}
        for (c, r), cost in sorted(self.dests(pid).items()):
            x, y = self.game.grid.hex_to_pixel(c, r)
            out["dests"].append(dict(col=c, row=r, x=x, y=y, cost=round(cost, 1),
                                     hexnum=self.game.grid.hexnum(c, r),
                                     terrain=self.game.hex_terrain(c, r)))
        for (c, r), cost in sorted(self.exit_options(pid).items()):
            out["exits"].append(dict(col=c, row=r, cost=round(cost, 1), hexnum=self.game.grid.hexnum(c, r)))
        return out

    def flow(self):
        s = self.s
        due = sorted([{"pid": pid, "slot": self.reserve[pid]["slot"], "side": self.reserve[pid]["side"],
                       "due": d, "arrival": self.reserve[pid].get("arrival")}
                      for pid, d in s["pool"].items() if d <= s["turn"] and self.reserve[pid]["side"] == s["mover"]],
                     key=lambda e: e["pid"])
        return {
            "mode": "naw", "turn": s["turn"], "turns": self.turns,
            "turn_label": self.turn_label(), "night": False,
            "phase": s["phase"], "mover": s["mover"],
            "over": s["over"], "winner": s["winner"],
            "vp": {"Fr": s["losses"]["Al"], "Al": s["losses"]["Fr"]},
            "moved": dict(s["moved"]),
            "combat": None,
            "naw": {"due": due, "exited": list(s["exited"]), "losses": dict(s["losses"]),
                    "demoralized": s["demoralized"], "pending": None,
                    "exit_hexes": sorted(self.game.grid.hexnum(*h) for h in self.exit_hexes)},
            "exited": {pid: "north" for pid in s["exited"]},
            "scenario": self.scenario["name"],
            "tier": self.tier, "tier_earned": self.tier_earned,
            "rules_scope": self.rules_scope(),
        }
