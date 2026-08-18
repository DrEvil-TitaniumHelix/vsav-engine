import heapq
import math

try:
    from .gate import GateGame
except ImportError:
    from gate import GateGame


class NawGame(GateGame):
    HASH_KEYS = ("turn", "phase", "mover", "over", "winner", "rng_calls", "units",
                 "moved", "done", "pool", "exited", "dead", "losses", "first_forty", "demoralized",
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
        self._resume_or_new(seed, required=("losses", "moved", "first_forty"))

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
            "first_forty": None,
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

    def _nm(self, pid):
        u = self.unit(pid)
        return u.get("name") or u["slot"]

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
        return float(self.stats(pid)["ma"]) - float(self.s["moved"].get(str(pid), 0))

    def entry_hexes(self, pid):
        pid = str(pid)
        e = self.reserve[pid]
        side = e["side"]
        _, epos, fpos, ezoc = self._board_sets(side)
        col = self.game.spec["reinforcements"]["entry_column"]
        out = {}
        for r in range(1, 40):
            h = (col, r)
            if not self.game.on_map(*h):
                continue
            t = self.game.hex_terrain(*h)
            if t == "woods" or h in epos or h in ezoc or h in fpos:
                continue
            out[h] = float(self.game.spec["reinforcements"]["entry_cost_mp"])
        return out

    def due_reserve(self, side):
        return sorted(pid for pid, d in self.s["pool"].items() if d <= self.s["turn"] and self.reserve[pid]["side"] == side)

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
        occ = {(v["col"], v["row"]): v["pid"] for v in self._live(u["side"]) if v["pid"] != pid}
        return {h: c for h, c in best.items()
                if h not in occ or (h not in ezoc and occ[h] not in self.s["done"])}

    def stacked_hexes(self, side):
        seen, dup = {}, {}
        for u in self._live(side):
            h = (u["col"], u["row"])
            if h in seen:
                dup.setdefault(h, [seen[h]]).append(u["pid"])
            else:
                seen[h] = u["pid"]
        return dup

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
        between = sorted(set(self.game.neighbors(*a)) & set(self.game.neighbors(*d)))
        blocked = [self.game.grid.hexnum(*h) for h in between if self.game.hex_terrain(*h) in ("woods", "woods_road")]
        if len(blocked) == len(between):
            return False, f"line of fire crosses Woods hex {'/'.join(blocked)} [ART-17/TEC row 3 + footnote (a hex with any woods symbol is Woods): artillery may not fire over an intervening Woods hex; a bent two-hex shot is open if either candidate hex is clear - SPI 1979 Terrain Key example 0803->0705 legal past woods 0804, 0803->0805 blocked]"
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
        raw = self.odds_column(a, d)
        col, shift_note = self.demoralization_shift(side, raw)
        return True, [f"attack {a} vs {d} = {raw} [CBT-01/CBT-02 rounded in favour of the defender; clamp 1:5..6:1]" + shift_note], {
            "attack": a, "defense": d, "column": col, "raw_column": raw, "melee": melee, "bombarding": bomb}

    def shift_column(self, col, n):
        cols = self._cbt()["crt"]["odds_columns"]
        i = cols.index(col) + n
        return cols[max(0, min(len(cols) - 1, i))]

    def demoralization_shift(self, side, col):
        if not self.s["demoralized"]:
            return col, ""
        dm = self.game.spec["demoralization"]
        n = dm["effects"].get(f"{side}_attack_column_shift", 0)
        if not n:
            return col, ""
        new = self.shift_column(col, n)
        clamp = " (already at the table's end - no further shift, NAW2-OR-19)" if new == col else ""
        return new, f"; Allied DEMORALIZED: {side} attack shifted {n:+d} column to {new} [DEM-06/DEM-07]" + clamp

    def _eliminate(self, pids, why):
        s = self.s
        ev = []
        for pid in pids:
            pid = str(pid)
            if pid not in s["units"]:
                continue
            u = self.unit(pid)
            cs = self.stats(pid)["att"]
            s["losses"][u["side"]] += cs
            s["dead"].append(pid)
            del s["units"][pid]
            ev.append({"eliminated": self._nm_cat(pid), "side": u["side"], "cs": cs, "why": why,
                       "losses": dict(s["losses"])})
        ev += self._check_victory()
        return ev

    def _nm_cat(self, pid):
        return self.cat(pid).get("name") or self.cat(pid)["slot"]

    def _check_victory(self):
        s = self.s
        v = self.game.spec["victory"]
        need = v["loss_threshold_cs"]
        ex_need = v["french_exit_required"]
        fr_side, al_side = self.exit_side, self.game.enemy(self.exit_side)
        al_lost = s["losses"][al_side]
        fr_lost = s["losses"][fr_side]
        ev = []
        if s.get("first_forty") is None:
            if al_lost >= need and fr_lost >= need:
                s["first_forty"] = "both"
            elif al_lost >= need:
                s["first_forty"] = fr_side
            elif fr_lost >= need:
                s["first_forty"] = al_side
        ff = s.get("first_forty")
        if s["over"]:
            return ev
        if ff == "both":
            s["over"] = True
            s["winner"] = fr_side if len(s["exited"]) >= ex_need else al_side
            ev.append({"game_over": True, "winner": s["winner"],
                       "why": f"both sides reached forty Strength Points at the same instant; French exited {len(s['exited'])}/{ex_need} [VIC-14]"})
            return ev
        if ff == al_side:
            s["over"] = True
            s["winner"] = al_side
            ev.append({"game_over": True, "winner": al_side,
                       "why": f"forty French Combat Strength Points destroyed first ({fr_lost}) [VIC-03/VIC-07]"})
            return ev
        if ff == fr_side:
            if len(s["exited"]) >= ex_need:
                s["over"] = True
                s["winner"] = fr_side
                ev.append({"game_over": True, "winner": fr_side,
                           "why": f"forty Allied Combat Strength Points destroyed ({al_lost}) and {len(s['exited'])} French units exited [VIC-01/VIC-02/VIC-07]"})
                return ev
            if not s["demoralized"]:
                s["demoralized"] = True
                ev.append({"demoralized": al_side,
                           "why": f"forty Allied Strength Points destroyed ({al_lost}) with only {len(s['exited'])} French units exited: the Allies are DEMORALIZED for the rest of the game - Allied attacks -1 column, French attacks +1 [DEM-01/DEM-02/DEM-03/DEM-06/DEM-07]"})
        return ev

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
        fn = {"move": self._propose_move, "exit": self._propose_exit, "reinforce": self._propose_reinforce}.get(t)
        if fn:
            return fn(side, action)
        if t == "end_movement":
            if s["phase"] != "movement":
                return self._v(False, "not the Movement Phase [SEQ-03]")
            owed = [pid for pid in self.due_reserve(side) if self.entry_hexes(pid)]
            if owed:
                return self._v(False, f"the Prussian reinforcements must enter now and may not be deliberately delayed: {', '.join(self._nm_cat(p) for p in owed)} can still enter on the East edge [REI-01/REI-06; entry hexes must be free of enemy units and enemy ZOC - SPI 1979 7.2, NAW2-OR-4]")
            dup = self.stacked_hexes(side)
            if dup:
                names = "; ".join(f"{self.game.grid.hexnum(*h)}: " + ", ".join(self._nm(p) for p in ps) for h, ps in sorted(dup.items()))
                return self._v(False, f"units may not finish their Movement Phase in the same hex - un-stack {names} [MOV-09; SPI 1979 4.4 'never end a Movement Phase stacked' - reading A, NAW2-OR-2]")
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
            return self._v(False, f"{self.game.grid.hexnum(*dest) if len(dest) == 2 else dest} is not a legal destination for {u['slot']} [MOV-05/MOV-15 one MP per hex within MA {self.stats(pid)['ma']}; MOV-06 consecutive hexes; MOV-08 never through or into enemy units; MOV-09 a friendly hex may be ended on mid-phase only if its occupant can still move off (not yet moved, not in enemy ZOC); MOV-10/ZOC-04 stop on entering an enemy ZOC, MOV-11 never through one; MOV-16/17/18 Woods only via Woods/Road hexes along the road]")
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

    def _propose_reinforce(self, side, action):
        s = self.s
        pid = str(action.get("unit"))
        if s["phase"] != "movement":
            return self._v(False, "reinforcements enter during the own Movement Phase [REI-01/REI-04]")
        if pid not in self.reserve or self.reserve[pid]["side"] != side:
            return self._v(False, f"{pid} is not a {side} reinforcement [REI-01]")
        if pid not in s["pool"]:
            return self._v(False, f"{self._nm_cat(pid)} has already entered [REI-01]")
        if s["pool"][pid] > s["turn"]:
            return self._v(False, f"{self._nm_cat(pid)} enters at the beginning of the Allied Player's second turn (Game-Turn {s['pool'][pid]}), not before [REI-01; printed Time Record 2 pm slot]")
        h = tuple(action.get("hex", ()))
        eh = self.entry_hexes(pid)
        if h not in eh:
            return self._v(False, f"{self.game.grid.hexnum(*h) if len(h) == 2 else h} is not a legal entry hex: the Prussians enter anywhere along the East edge (column 27), a non-Woods hex free of enemy units, enemy ZOC and friendly units [REI-02; MOV-08/MOV-16; SPI 1979 7.2 no entry into an enemy ZOC, NAW2-OR-4]")
        return self._v(True, f"{self._nm_cat(pid)} enters at {self.game.grid.hexnum(*h)} for {eh[h]:g} MP; it may move and fight this turn [REI-02/REI-03 ('extends' = expends, NAW2-SD-1)/REI-04]")

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
            ev += self._check_victory()
        elif t == "reinforce":
            pid = str(action["unit"])
            e = self.reserve[pid]
            h = tuple(action["hex"])
            cost = self.entry_hexes(pid)[h]
            s["units"][pid] = {"pid": pid, "slot": e["slot"], "name": e.get("name", e["slot"]), "side": side, "col": h[0], "row": h[1]}
            s["pool"].pop(pid, None)
            s["moved"][pid] = cost
            ev.append({"reinforce": e.get("name", e["slot"]), "at": self.game.grid.hexnum(*h), "mp": cost, "remaining_ma": self.budget(pid)})
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
        if s["over"]:
            return []
        s["over"] = True
        s["winner"] = "draw"
        why = "tenth Game-Turn completed with neither side at forty Strength Points [SEQ-05/VIC-04]"
        if s["demoralized"]:
            why = f"tenth Game-Turn completed: the Allies were demoralized but the French exited only {len(s['exited'])} of {self.game.spec['victory']['french_exit_required']} units [VIC-04/DEM-04]"
        return [{"game_over": True, "winner": "draw", "why": why}]

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
        due = []
        if s["phase"] == "movement" and not s["over"]:
            for pid in self.due_reserve(s["mover"]):
                eh = self.entry_hexes(pid)
                due.append({"pid": pid, "slot": self.reserve[pid]["slot"], "name": self.reserve[pid].get("name"),
                            "side": self.reserve[pid]["side"], "due": s["pool"][pid], "arrival": "edge",
                            "entry": [list(h) for h in sorted(eh)]})
        return {
            "mode": "naw", "turn": s["turn"], "turns": self.turns,
            "turn_label": self.turn_label(), "night": False,
            "phase": s["phase"], "mover": s["mover"],
            "over": s["over"], "winner": s["winner"],
            "vp": {"Fr": s["losses"]["Al"], "Al": s["losses"]["Fr"]},
            "moved": dict(s["moved"]),
            "combat": None,
            "naw": {"due": due, "exited": list(s["exited"]), "losses": dict(s["losses"]),
                    "loss_threshold": self.game.spec["victory"]["loss_threshold_cs"],
                    "exit_required": self.game.spec["victory"]["french_exit_required"],
                    "first_forty": s.get("first_forty"),
                    "demoralized": s["demoralized"], "pending": None,
                    "exit_hexes": sorted(self.game.grid.hexnum(*h) for h in self.exit_hexes)},
            "exited": {pid: "north" for pid in s["exited"]},
            "scenario": self.scenario["name"],
            "tier": self.tier, "tier_earned": self.tier_earned,
            "rules_scope": self.rules_scope(),
        }
