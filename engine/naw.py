import heapq
import math

try:
    from .gate import GateGame
except ImportError:
    from gate import GateGame


class NawGame(GateGame):
    HASH_KEYS = ("turn", "phase", "mover", "over", "winner", "rng_calls", "units",
                 "moved", "done", "pool", "exited", "dead", "losses", "first_forty", "demoralized",
                 "fought", "defended", "advanced", "contacts", "disrupted", "battle_no", "pending")
    TURN_NOUN = "Game-Turn"

    def __init__(self, game, scenario_path, live_dir, seed=None):
        super().__init__(game, scenario_path, live_dir)
        self.reserve = {u["id"]: u for u in self.scenario.get("reserve", [])}
        self.schedule = self.reserve
        self.catalog = {u["id"]: u for u in
                        self.scenario.get("units", []) + self.scenario.get("reserve", [])}
        self.exit_hexes = {(int(h[:2]), int(h[2:])) for h in game.spec["exit"]["hexes"]}
        self.exit_side = game.spec["exit"]["side"]
        self.exit_cost = float(game.spec["exit"]["cost_mp"])
        self._resume_or_new(seed, required=("losses", "moved", "first_forty", "contacts"))

    def new_game(self, seed=None):
        seed = self._fresh_seed(seed)
        units = self._scenario_units()
        self.s = {
            "seed": seed, "rng_calls": 0, "n": 0,
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
            "contacts": [], "disrupted": [],
            "battle_no": 0,
            "pending": None,
        }
        self._reset_log()
        self._log({"event": "init", "mode": "naw",
                   "scenario": self.scenario["name"],
                   "rules_scope": self.rules_scope(), "seed": seed,
                   "turns": self.turns, "first_player": self.first_player,
                   "units": self._units_for_log(units)})
        self.save()

    def rules_scope(self):
        sc = self.scenario.get("rules_scope", {})
        open_rows = sc.get("not_yet_enforced", [])
        return {"enforced": sc.get("enforced", []),
                "not_enforced": open_rows,
                "rulings": sc.get("rulings", []) + [f"OPEN for Bruce: {q}" for q in sc.get("open_for_bruce", [])],
                "banner": ("PLAYABLE - every coverage-matrix cell enforced or unreachable (validate_data/movement/combat/battle/victory; "
                           "the one open cell is the platform UNDO policy, NAW2-OR-3)" if not open_rows
                           else "BUILD IN PROGRESS - NOT PLAYABLE by the coverage-matrix standard (open rows below)")}

    def side_to_move(self):
        p = self.s["pending"]
        return p["by"] if p else self.s["mover"]

    def decider(self):
        return self.side_to_move()

    def _scenario_units(self):
        return {u["id"]: {"pid": u["id"], "slot": u["slot"], "name": u.get("name", u["slot"]), "side": u["side"],
                          "col": u["hex"][0], "row": u["hex"][1]}
                for u in self.scenario["units"]}

    def cat(self, pid):
        return self.catalog[str(pid)]

    def _nm(self, pid):
        u = self.unit(pid)
        return u.get("name") or u["slot"]

    def _nm_cat(self, pid):
        return self.cat(pid).get("name") or self.cat(pid)["slot"]

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

    def _hx(self, pid):
        u = self.unit(pid)
        return (u["col"], u["row"])

    def _hn(self, h):
        return self.game.grid.hexnum(*h)

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

    def _reach(self, pid):
        pid = str(pid)
        u = self.unit(pid)
        board, epos, fpos, ezoc = self._board_sets(u["side"], exclude_pid=pid)
        start = (u["col"], u["row"])
        if start in ezoc:
            return {}, ezoc
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
        return best, ezoc

    def _unstack_feasible(self, side, hyp=None):
        s = self.s
        done = set(s["done"])
        pos = {}
        for v in self._live(side):
            pos[v["pid"]] = (v["col"], v["row"])
        if hyp:
            pid, dest = hyp
            pos[pid] = tuple(dest)
            done.add(pid)
        byhex = {}
        for pid, h in pos.items():
            byhex.setdefault(h, []).append(pid)
        stacked = {h: ps for h, ps in byhex.items() if len(ps) > 1}
        if not stacked:
            return True
        _, epos, _, ezoc = self._board_sets(side)
        fpos = set(byhex)
        need = {h: len(ps) - 1 for h, ps in stacked.items()}
        opts = {}
        for h, ps in stacked.items():
            for p in ps:
                if p in done or h in ezoc or self.budget(p) < 1:
                    continue
                opts[p] = {n for n in self.game.neighbors(*h)
                           if self.game.on_map(*n) and self.game.hex_terrain(*n) != "woods"
                           and self.game.move_cost(h, n) is not None and n not in epos and n not in fpos}
        cap = {}
        adj = {"S": set(), "T": set()}

        def edge(a, b, c):
            cap[(a, b)] = c
            cap.setdefault((b, a), 0)
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)
        for h, n in need.items():
            edge("S", ("H", h), n)
            for p in stacked[h]:
                if p in opts:
                    edge(("H", h), ("P", p), 1)
                    for f in opts[p]:
                        edge(("P", p), ("F", f), 1)
                        if (("F", f), "T") not in cap:
                            edge(("F", f), "T", 1)
        flow = 0
        while True:
            prev = {"S": None}
            q = ["S"]
            while q and "T" not in prev:
                x = q.pop(0)
                for y in adj.get(x, ()):
                    if y not in prev and cap.get((x, y), 0) > 0:
                        prev[y] = x
                        q.append(y)
            if "T" not in prev:
                break
            y = "T"
            while prev[y] is not None:
                x = prev[y]
                cap[(x, y)] -= 1
                cap[(y, x)] += 1
                y = x
            flow += 1
        return flow == sum(need.values())

    def dests(self, pid):
        pid = str(pid)
        u = self.unit(pid)
        best, _ = self._reach(pid)
        side = u["side"]
        return {h: c for h, c in best.items() if self._unstack_feasible(side, (pid, h))}

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
        cand, ezoc = self._reach(pid)
        if start in ezoc:
            return {}
        cand = dict(cand)
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

    # ------------------------------------------------------------ obligations (CBT-06/07/10, NAW2-OR-6 A)
    def _contact_pairs(self, side):
        enemy = self.game.enemy(side)
        mine = sorted(self._live(side), key=lambda u: u["pid"])
        theirs = sorted(self._live(enemy), key=lambda u: u["pid"])
        return [[f["pid"], e["pid"], [f["col"], f["row"]], [e["col"], e["row"]]]
                for f in mine for e in theirs if self._adjacent(f, e)]

    def _at(self, pid, h):
        u = self.s["units"].get(pid)
        return bool(u) and [u["col"], u["row"]] == list(h)

    def live_pairs(self, exclude_atk=(), exclude_def=()):
        s = self.s
        out = []
        for f, e, fh, eh in s["contacts"]:
            if f in s["fought"] or f in exclude_atk or e in s["defended"] or e in exclude_def:
                continue
            if not self._at(f, fh) or not self._at(e, eh):
                continue
            out.append((f, e))
        return out

    def obligations(self):
        lp = self.live_pairs()
        return sorted({f for f, _ in lp}), sorted({e for _, e in lp})

    def stranded_by(self, atk_ids, def_ids):
        before_f, before_e = self.obligations()
        lp = self.live_pairs(exclude_atk=set(atk_ids), exclude_def=set(def_ids))
        fs = {f for f, _ in lp}
        es = {e for _, e in lp}
        sf = [f for f in before_f if f not in atk_ids and f not in fs]
        se = [e for e in before_e if e not in def_ids and e not in es]
        return sf, se

    def complete_assignment(self):
        lp = self.live_pairs()
        adj = {}
        for f, e in lp:
            adj.setdefault(("F", f), set()).add(("E", e))
            adj.setdefault(("E", e), set()).add(("F", f))
        tree = {v: set() for v in adj}
        seen = set()
        for v in sorted(adj):
            if v in seen:
                continue
            seen.add(v)
            stack = [v]
            while stack:
                x = stack.pop()
                for y in sorted(adj[x]):
                    if y not in seen:
                        seen.add(y)
                        tree[x].add(y)
                        tree[y].add(x)
                        stack.append(y)
        attacks = []
        alive = set(tree)
        while alive:
            leaves = [v for v in sorted(alive) if len(tree[v]) == 1]
            if leaves:
                c = next(iter(tree[leaves[0]]))
                star = {v for v in tree[c] if len(tree[v]) == 1}
            else:
                c = sorted(alive)[0]
                star = set(tree[c])
            members = star | {c}
            attacks.append(([p for k, p in sorted(members) if k == "F"], [p for k, p in sorted(members) if k == "E"]))
            for v in members:
                for y in tree[v]:
                    tree[y].discard(v)
                tree[v] = set()
                alive.discard(v)
        return attacks

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
            if p in s["advanced"]:
                return False, [f"{self.unit(p)['name']} advanced after combat this phase and may not participate in another attack [OPTIONAL ADVANCE p.5; NAW2-OR-16 A]"], None
            if p in s["disrupted"] and self.cls(p) == "artillery":
                return False, [f"{self.unit(p)['name']} was disrupted this Combat Phase: disrupted artillery units may NOT fire in the Combat Phase in which they were disrupted [DISRUPTION S6, p.5]"], None
        for p in def_ids:
            if p not in s["units"] or self.unit(p)["side"] != enemy:
                return False, [f"defender {p} is not an enemy unit on the map [CBT-05]"], None
            if p in s["defended"]:
                return False, [f"{self.unit(p)['name']} has already been attacked this Combat Phase [CBT-10]"], None
            if p in s["advanced"]:
                return False, [f"{self.unit(p)['name']} advanced after combat this phase and may not participate in another defense [OPTIONAL ADVANCE p.5]"], None
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
        sf, se = self.stranded_by(atk_ids, def_ids)
        if sf or se:
            why = []
            if sf:
                why.append(f"{', '.join(self._nm(p) for p in sf)} would be left adjacent to enemy units with no attack open (every enemy it touches would already have been attacked) - ALL friendly units adjacent to enemy units MUST participate [CBT-07/CBT-10]")
            if se:
                why.append(f"{', '.join(self._nm(p) for p in se)} would be left with no friendly unit able to attack it - ALL enemy units adjacent to friendly units MUST be attacked [CBT-06/CBT-10]")
            return False, ["; ".join(why) + " - fold the stranded unit(s) into this attack or resolve another attack first [obligations fixed at the start of the Combat Phase, NAW2-OR-6 A; a complete assignment always exists, NAW2-OR-5]"], None
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
            ev.append({"eliminated": self._nm_cat(pid), "pid": pid, "side": u["side"], "cs": cs, "why": why,
                       "losses": dict(s["losses"])})
        ev += self._check_victory()
        return ev

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

    # ------------------------------------------------------------ retreat / disruption (p.5 RETREAT AND ADVANCE, DISRUPTION)
    def _safe_hex(self, frm, to, epos, ezoc):
        return (self.game.on_map(*to) and self.game.hex_terrain(*to) != "woods"
                and self.game.move_cost(frm, to) is not None and to not in epos and to not in ezoc)

    def _retreat_rec(self, pid, at, occ, epos, ezoc, involved, chain):
        cands = [n for n in self.game.neighbors(*at) if self._safe_hex(at, n, epos, ezoc)]
        empties = [n for n in cands if n not in occ]
        if empties:
            return {n: None for n in empties}
        out = {}
        for n in cands:
            f = occ[n]
            if f in involved or f in chain:
                continue
            occ2 = dict(occ)
            occ2.pop(at, None)
            occ2[n] = pid
            if self._retreat_rec(f, n, occ2, epos, ezoc, involved, chain | {pid}):
                out[n] = f
        return out

    def retreat_options(self, pid, involved, chain=()):
        pid = str(pid)
        u = self.unit(pid)
        _, epos, _, ezoc = self._board_sets(u["side"])
        occ = {(v["col"], v["row"]): v["pid"] for v in self._live(u["side"]) if v["pid"] != pid}
        return self._retreat_rec(pid, (u["col"], u["row"]), occ, epos, ezoc, set(involved), set(chain))

    def _run_queue(self, queue):
        s = self.s
        ev = []
        while queue and not s["over"]:
            step = queue.pop(0)
            if step["kind"] == "retreat":
                ev += self._settle_retreats(step)
                if step["owed"] and not s["over"]:
                    s["pending"] = dict(step, awaiting="retreat", queue=queue)
                    return ev
            elif step["kind"] == "exchange":
                s["pending"] = dict(step, awaiting="exchange_loss", queue=queue)
                return ev
            elif step["kind"] == "advance":
                if self.advance_pairs(step):
                    s["pending"] = dict(step, awaiting="advance", queue=queue)
                    return ev
        s["pending"] = None
        return ev

    def _settle_retreats(self, step):
        s = self.s
        ev = []
        if step.get("voluntary"):
            step["owed"] = [p for p in step["owed"] if p in s["units"] and self.retreat_options(p, step["involved"])]
            return ev
        while not s["over"]:
            step["owed"] = [p for p in step["owed"] if p in s["units"]]
            if not step["owed"]:
                return ev
            if step.get("chain"):
                front = step["owed"][0]
                opts = self.retreat_options(front, step["involved"], step["chain"])
                if len(opts) == 1:
                    ev += self._do_retreat(step, front, next(iter(opts)), forced=True)
                    continue
                return ev
            dead = [p for p in step["owed"] if not self.retreat_options(p, step["involved"])]
            if dead:
                p = dead[0]
                step["owed"].remove(p)
                ev += self._eliminate([p], f"battle {step['battle']}: no path of retreat - a unit may not retreat into enemy Zones of Control, off the map, into non-Road Woods, or into enemy-occupied hexes, and no uninvolved friendly unit can be disrupted out of the way [RETREAT AND ADVANCE p.5, DISRUPTION S1/S4; VIC-13]")
                continue
            if len(step["owed"]) == 1:
                p = step["owed"][0]
                opts = self.retreat_options(p, step["involved"])
                if len(opts) == 1:
                    ev += self._do_retreat(step, p, next(iter(opts)), forced=True)
                    continue
            return ev
        return ev

    def _do_retreat(self, step, pid, h, forced=False):
        s = self.s
        u = self.unit(pid)
        frm = (u["col"], u["row"])
        opts = self.retreat_options(pid, step["involved"], step.get("chain", []))
        f = opts[h]
        u["col"], u["row"] = h
        step["owed"].remove(pid)
        ev = [{"retreat": self._nm(pid), "pid": pid, "from": self._hn(frm), "to": self._hn(h),
               "chosen_by": step["by"], "forced": forced,
               "why": ("voluntary Attacker Retreat by bombarding artillery [ART-11, NAW2-OR-8 owner chooses]" if step.get("voluntary")
                       else "the victorious player decides the direction of retreat [RETREAT AND ADVANCE p.5]"
                       + (" - the only safe hex" if forced else ""))}]
        if pid in step.get("chain_units", []):
            ev[-1]["why"] = "disrupted (pushed out of its hex) by the retreating unit; moved back as if retreating, by the victorious player [DISRUPTION S2]"
        if f is not None:
            s["disrupted"].append(f)
            step.setdefault("chain", []).append(pid)
            step.setdefault("chain_units", []).append(f)
            step["owed"].insert(0, f)
            ev.append({"disrupted": self._nm(f), "pid": f, "at": self._hn(h), "by": self._nm(pid),
                       "why": "the only safe hex was occupied by an uninvolved friendly unit: it is disrupted and must itself be moved back one hex [DISRUPTION S1/S2/S5]"
                       + (" - disrupted artillery may not fire this Combat Phase [S6]" if self.cls(f) == "artillery" else "")})
        else:
            step["chain"], step["chain_units"] = [], []
        return ev

    def advance_pairs(self, step):
        s = self.s
        occ = {(v["col"], v["row"]) for v in self._live()}
        pairs = []
        for h in step["vacated"]:
            h = tuple(h)
            if h in occ:
                continue
            for p in step["candidates"]:
                if p not in s["units"] or p in s["advanced"]:
                    continue
                u = self.unit(p)
                if h not in self.game.neighbors(u["col"], u["row"]):
                    continue
                if self.game.move_cost((u["col"], u["row"]), h) is None:
                    continue
                pairs.append((p, h))
        return pairs

    # ------------------------------------------------------------ propose
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
        fn = {"move": self._propose_move, "exit": self._propose_exit, "reinforce": self._propose_reinforce,
              "battle": self._propose_battle, "retreat": self._propose_retreat,
              "exchange_loss": self._propose_exchange, "advance": self._propose_advance}.get(t)
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
            return self._v(True, "Movement Phase complete; Combat Phase begins - the mandatory-attack obligations are fixed now [SEQ-03/SEQ-04; CBT-06/CBT-07, NAW2-OR-6 A]")
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
            return self._v(False, f"{self.game.grid.hexnum(*dest) if len(dest) == 2 else dest} is not a legal destination for {u['slot']} [MOV-05/MOV-15 one MP per hex within MA {self.stats(pid)['ma']}; MOV-06 consecutive hexes; MOV-08 never through or into enemy units; MOV-09 a friendly hex may be ended on mid-phase only if its occupant can still move off (not yet moved, not in enemy ZOC, has a free hex to step to); MOV-10/ZOC-04 stop on entering an enemy ZOC, MOV-11 never through one; MOV-16/17/18 Woods only via Woods/Road hexes along the road]")
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

    def _propose_battle(self, side, action):
        s = self.s
        if s["pending"]:
            return self._v(False, "resolve the pending step first")
        atk = [str(p) for p in action.get("attackers", [])]
        dfd = [str(p) for p in action.get("defenders", [])]
        ok, reasons, meta = self.battle_check(side, atk, dfd)
        if not ok:
            return self._v(False, *reasons)
        return self._v(True, reasons[0] + f" - {len(meta['melee'])} adjacent, {len(meta['bombarding'])} bombarding; the die is the engine's [CBT-03]")

    def _propose_retreat(self, side, action):
        p = self.s["pending"]
        if not p or p["awaiting"] != "retreat":
            return self._v(False, "no retreat pending")
        if action.get("decline"):
            if not p.get("voluntary"):
                return self._v(False, "the retreat is not optional: a Defender Retreats / Attacker Retreats result moves the unit(s) back one hex [EXPLANATION OF RESULTS Dr/Ar]")
            return self._v(True, "the bombarding artillery stands fast - it is not affected by combat results [ART-03/ART-09/ART-11]")
        pid = str(action.get("unit"))
        if pid not in p["owed"]:
            return self._v(False, f"{pid} is not owed a retreat now; owed: {', '.join(self._nm(x) for x in p['owed'] if x in self.s['units'])}")
        if p.get("chain") and pid != p["owed"][0]:
            return self._v(False, f"the disruption chain must be completed first: {self._nm(p['owed'][0])} must be moved back before any other retreat [DISRUPTION S5]")
        path = action.get("path") or ([action["hex"]] if action.get("hex") else [])
        if not path:
            return self._v(False, "name the hex the unit retreats to (path: [[col,row]])")
        h = tuple(path[-1])
        opts = self.retreat_options(pid, p["involved"], p.get("chain", []))
        if h not in opts:
            return self._v(False, f"{self._hn(h) if len(h) == 2 else h} is not a legal retreat hex for {self._nm(pid)}: one hex back, not into enemy Zones of Control, off the map, into non-Road Woods, or into enemy-occupied hexes; Woods/Road only along the road (MOV-17, SPI 1979 4.2); a friendly-occupied hex only when it is the ONLY safe hex and the occupant can itself be moved back [RETREAT AND ADVANCE p.5, DISRUPTION S1-S5, NAW2-SD-3 A]; legal: {', '.join(self._hn(x) for x in sorted(opts))}")
        f = opts[h]
        return self._v(True, f"{self._nm(pid)} retreats to {self._hn(h)}" + (f", disrupting {self._nm(f)} out of it [DISRUPTION S1/S2]" if f else " [RETREAT AND ADVANCE p.5]"))

    def _propose_exchange(self, side, action):
        p = self.s["pending"]
        if not p or p["awaiting"] != "exchange_loss":
            return self._v(False, "no exchange loss pending")
        units = [str(x) for x in action.get("units", [])]
        if not units or len(set(units)) != len(units):
            return self._v(False, "name the attacking units removed to pay the exchange [EX]")
        bad = [x for x in units if x not in p["involved"] or x not in self.s["units"]]
        if bad:
            return self._v(False, f"{', '.join(bad)}: only attacking units directly involved in this attack from an ADJACENT position may pay the exchange - bombarding artillery is not affected [EX p.5; ART-04/ART-05]")
        pay = sum(self.stats(x)["att"] for x in units)
        if pay < p["owe"]:
            return self._v(False, f"the attacker's loss must be AT LEAST equal to the defender's printed Strength Points: {pay} offered, {p['owe']} owed [EX p.5; NAW2-OR-15 A printed value, whole units]")
        return self._v(True, f"exchange paid: {pay} Strength Points for {p['owe']} [EX p.5]")

    def _propose_advance(self, side, action):
        p = self.s["pending"]
        if not p or p["awaiting"] != "advance":
            return self._v(False, "no advance pending")
        if action.get("decline"):
            return self._v(True, "no advance - a unit is never forced to advance [OPTIONAL ADVANCE p.5]")
        pid = str(action.get("unit"))
        h = tuple(action.get("hex", ()))
        pairs = self.advance_pairs(p)
        if (pid, h) not in pairs:
            return self._v(False, f"{self._nm(pid) if pid in self.s['units'] else pid} may not advance into {self._hn(h) if len(h) == 2 else h}: only a victorious unit of this attack (bombarding artillery excepted, ART-18), one unit per vacated hex, one hex, adjacent, along the road into Woods/Road [CBT-14/CBT-15, OPTIONAL ADVANCE p.5, MOV-17]; open: {', '.join(f'{self._nm(a)}->{self._hn(b)}' for a, b in pairs)}")
        return self._v(True, f"{self._nm(pid)} advances into {self._hn(h)}; it takes no further part in this Combat Phase [CBT-14/CBT-15/CBT-16, OPTIONAL ADVANCE p.5, NAW2-OR-16 A]")

    def _propose_end_phase(self, side):
        s = self.s
        if s["phase"] != "combat":
            return self._v(False, "end_phase closes the Combat Phase - use end_movement to close the Movement Phase [SEQ-03]")
        if s["pending"]:
            return self._v(False, "resolve the pending step first")
        fs, es = self.obligations()
        if fs or es:
            return self._v(False, f"mandatory attacks remain: must attack {', '.join(self._nm(p) for p in fs) or '-'}; must be attacked {', '.join(self._nm(p) for p in es) or '-'} [CBT-06/CBT-07 - obligations fixed at the start of the Combat Phase, NAW2-OR-6 A]")
        return self._v(True, "Combat Phase complete [SEQ-04]")

    # ------------------------------------------------------------ apply
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
            s["moved"][pid] = s["moved"].get(pid, 0) + cost
            s["done"].append(pid)
            ev.append({"move": u["slot"], "from": frm, "to": list(dest), "mp": cost})
        elif t == "exit":
            pid = str(action["unit"])
            u = self.unit(pid)
            via = tuple(action.get("via") or (u["col"], u["row"]))
            cost = self.exit_options(pid)[via]
            s["exited"].append(pid)
            s["moved"][pid] = s["moved"].get(pid, 0) + cost
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
            s["contacts"] = self._contact_pairs(side)
            fs, es = self.obligations()
            ev.append({"phase": "combat", "mover": s["mover"], "obligations": len(s["contacts"]),
                       "must_attack": fs, "must_be_attacked": es})
        elif t == "battle":
            ev += self._apply_battle(side, [str(p) for p in action["attackers"]], [str(p) for p in action["defenders"]])
        elif t == "retreat":
            p = s["pending"]
            if action.get("decline"):
                ev.append({"stand_fast": [self._nm(x) for x in p["owed"] if x in s["units"]]})
                p["owed"] = []
            else:
                pid = str(action["unit"])
                path = action.get("path") or [action["hex"]]
                ev += self._do_retreat(p, pid, tuple(path[-1]))
                ev += self._settle_retreats(p)
            if not p["owed"] or s["over"]:
                ev += self._run_queue(p["queue"])
        elif t == "exchange_loss":
            p = s["pending"]
            units = [str(x) for x in action["units"]]
            ev += self._eliminate(units, f"battle {p['battle']}: exchange loss (defender {p['owe']} SP) [EX]")
            ev += self._run_queue(p["queue"])
        elif t == "advance":
            p = s["pending"]
            if action.get("decline"):
                ev.append({"advance_declined": p["by"]})
                ev += self._run_queue(p["queue"])
            else:
                pid = str(action["unit"])
                h = tuple(action["hex"])
                u = self.unit(pid)
                frm = self._hn((u["col"], u["row"]))
                u["col"], u["row"] = h
                s["advanced"].append(pid)
                p["vacated"] = [v for v in p["vacated"] if tuple(v) != h]
                ev.append({"advance": self._nm(pid), "pid": pid, "from": frm, "to": self._hn(h)})
                if not self.advance_pairs(p):
                    ev += self._run_queue(p["queue"])
        elif t == "end_phase":
            ev += self._end_player_turn(side)
        return ev

    def _apply_battle(self, side, atk_ids, def_ids):
        s = self.s
        ok, reasons, meta = self.battle_check(side, atk_ids, def_ids)
        die = self.roll_die()
        res = self.crt_result(meta["column"], die)
        s["battle_no"] += 1
        n = s["battle_no"]
        s["fought"] += atk_ids
        s["defended"] += def_ids
        enemy = self.game.enemy(side)
        melee, bomb = meta["melee"], meta["bombarding"]
        dhex = [[self.unit(p)["col"], self.unit(p)["row"]] for p in def_ids]
        ahex = [[self.unit(p)["col"], self.unit(p)["row"]] for p in melee]
        ev = [{"battle": n, "attackers": atk_ids, "defenders": def_ids, "melee": melee, "bombarding": bomb,
               "attack": meta["attack"], "defense": meta["defense"], "column": meta["column"],
               "raw_column": meta["raw_column"], "die": die, "result": res,
               "explanation": self._cbt()["crt"]["results"].get(res, res)}]
        involved = atk_ids + def_ids
        queue = []
        if res == "DE":
            ev += self._eliminate(def_ids, f"battle {n}: Defender Eliminated [DE]")
            queue.append({"kind": "advance", "by": side, "candidates": melee, "vacated": dhex, "battle": n})
        elif res == "EX":
            owe = sum(self.stats(p)["att"] for p in def_ids)
            ev += self._eliminate(def_ids, f"battle {n}: Exchange - defender eliminated [EX]")
            pay = sum(self.stats(p)["att"] for p in melee)
            if not melee:
                ev.append({"exchange": "free", "why": "every attacker bombarded from two hexes: bombarding artillery is not affected by an Exchange, the defender is eliminated at no cost [ART-05, SPI 1979 6.8, NAW2-OR-7 A]"})
            elif pay <= owe:
                ev.append({"exchange": "all", "owe": owe, "pay": pay, "why": "the adjacent attackers together cannot exceed the defender's printed strength: every adjacent attacker is lost [EX 'AT LEAST equal', ART-10]"})
                ev += self._eliminate(melee, f"battle {n}: exchange loss (defender {owe} SP) [EX]")
            else:
                queue.append({"kind": "exchange", "by": side, "owe": owe, "involved": melee, "battle": n})
            queue.append({"kind": "advance", "by": side, "candidates": melee, "vacated": dhex, "battle": n})
        elif res == "Dr":
            queue.append({"kind": "retreat", "by": side, "owed": list(def_ids), "involved": involved, "battle": n})
            queue.append({"kind": "advance", "by": side, "candidates": melee, "vacated": dhex, "battle": n})
        elif res == "Ar":
            if melee:
                queue.append({"kind": "retreat", "by": enemy, "owed": list(melee), "involved": involved, "battle": n})
            if bomb:
                queue.append({"kind": "retreat", "by": side, "owed": list(bomb), "involved": involved, "battle": n, "voluntary": True})
            queue.append({"kind": "advance", "by": enemy, "candidates": list(def_ids), "vacated": ahex, "battle": n})
        elif res == "AE":
            if melee:
                ev += self._eliminate(melee, f"battle {n}: Attacker Eliminated [AE]")
            if bomb:
                ev.append({"immune": [self._nm(p) for p in bomb], "why": "bombarding artillery is never destroyed or retreated by the result of its own attack [ART-03/ART-09]"})
            queue.append({"kind": "advance", "by": enemy, "candidates": list(def_ids), "vacated": ahex, "battle": n})
        s["pending"] = None
        ev += self._run_queue(queue)
        return ev

    def _end_player_turn(self, side):
        s = self.s
        ev = []
        order = self.game.side_order
        s["phase"] = "movement"
        s["moved"], s["done"] = {}, []
        s["fought"], s["defended"], s["advanced"] = [], [], []
        s["contacts"], s["disrupted"] = [], []
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

    def _pending_view(self):
        p = self.s["pending"]
        if not p:
            return None
        if p["awaiting"] == "retreat":
            units = []
            for pid in p["owed"]:
                if pid not in self.s["units"]:
                    continue
                if p.get("chain") and pid != p["owed"][0]:
                    continue
                opts = self.retreat_options(pid, p["involved"], p.get("chain", []))
                units.append({"pid": pid, "slot": self._nm(pid), "displaced": pid in p.get("chain_units", []),
                              "options": [{"path": [list(h)], "name": self._hn(h) + (f" (disrupts {self._nm(f)})" if f else "")}
                                          for h, f in sorted(opts.items())]})
            return {"kind": "retreat", "chooser": p["by"], "units": units, "voluntary": bool(p.get("voluntary")),
                    "can_decline": bool(p.get("voluntary")),
                    "note": ("bombarding artillery may voluntarily accept the Attacker Retreat [ART-11]" if p.get("voluntary")
                             else "the victorious player chooses each retreat hex [RETREAT AND ADVANCE p.5]")}
        if p["awaiting"] == "exchange_loss":
            return {"kind": "exchange", "winner": p["by"], "chooser": p["by"], "owe": p["owe"],
                    "involved": [{"pid": x, "slot": self._nm(x), "factor": self.stats(x)["att"]}
                                 for x in p["involved"] if x in self.s["units"]]}
        if p["awaiting"] == "advance":
            pairs = self.advance_pairs(p)
            hexes = sorted({h for _, h in pairs})
            return {"kind": "advance", "chooser": p["by"], "can_decline": True,
                    "advancers": [{"pid": x, "slot": self._nm(x)} for x in sorted({a for a, _ in pairs})],
                    "hexes": [list(h) for h in hexes], "hex_names": [self._hn(h) for h in hexes],
                    "pairs": [{"pid": a, "slot": self._nm(a), "hex": list(h), "name": self._hn(h)} for a, h in pairs]}
        return dict(p)

    def flow(self):
        s = self.s
        due = []
        if s["phase"] == "movement" and not s["over"]:
            for pid in self.due_reserve(s["mover"]):
                eh = self.entry_hexes(pid)
                due.append({"pid": pid, "slot": self.reserve[pid]["slot"], "name": self.reserve[pid].get("name"),
                            "side": self.reserve[pid]["side"], "due": s["pool"][pid], "arrival": "edge",
                            "entry": [list(h) for h in sorted(eh)]})
        if s["phase"] == "combat":
            fs, es = self.obligations()
        else:
            pairs = self._contact_pairs(s["mover"]) if not s["over"] else []
            fs, es = sorted({f for f, _, _, _ in pairs}), sorted({e for _, e, _, _ in pairs})
        combat = {"phase": s["phase"],
                  "must_attack": [{"pid": p, "slot": self._nm(p)} for p in fs],
                  "must_be_attacked": [{"pid": p, "slot": self._nm(p)} for p in es],
                  "obligations_fixed": s["phase"] == "combat",
                  "pending": self._pending_view(), "battles_fought": s["battle_no"],
                  "disrupted": list(s["disrupted"]), "advanced": list(s["advanced"])}
        return {
            "mode": "naw", "turn": s["turn"], "turns": self.turns,
            "turn_label": self.turn_label(), "night": False,
            "phase": s["phase"], "mover": s["mover"],
            "over": s["over"], "winner": s["winner"],
            "vp": {"Fr": s["losses"]["Al"], "Al": s["losses"]["Fr"]},
            "moved": dict(s["moved"]),
            "combat": combat,
            "naw": {"due": due, "exited": list(s["exited"]), "losses": dict(s["losses"]),
                    "loss_threshold": self.game.spec["victory"]["loss_threshold_cs"],
                    "exit_required": self.game.spec["victory"]["french_exit_required"],
                    "first_forty": s.get("first_forty"),
                    "demoralized": s["demoralized"], "pending": self._pending_view(),
                    "exit_hexes": sorted(self.game.grid.hexnum(*h) for h in self.exit_hexes)},
            "exited": {pid: "north" for pid in s["exited"]},
            "scenario": self.scenario["name"],
            "rules_scope": self.rules_scope(),
        }
