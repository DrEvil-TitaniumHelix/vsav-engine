"""
bluegray.py - The legality gate for the SPI Blue & Gray quad family
(Chickamauga first). Same anti-cheat trinity as strategic.py/gamestate.py:
EVERY action enters through propose()/submit(); submit() logs EVERY proposal
(including rejections) with rulebook-cited reasons, engine-owned seeded dice
and state hashes to an append-only JSONL log that engine/verify_game.py
replays independently.

Turn structure (1975 standard rules 4.0): each Game Turn = First Player Turn
(movement phase, then combat phase) then Second Player Turn, then the GT
marker advances. Union is the first player every GT (14.3). Night GTs skip
the combat phase entirely (10.0-10.2).

Actions:
  {"type":"move", "unit":pid, "dest":[c,r], "path":[[c,r],...]?}
  {"type":"reinforce", "unit":pid, "hex":[c,r]}      (15.0-15.5 column entry)
  {"type":"exit", "unit":pid}                        (16.x, from 0101/0111)
  {"type":"end_movement"}
  {"type":"battle", "attackers":[pid,...], "defenders":[pid,...],
   "bombarding":[pid,...]?, "odds_reduce":[n,d]?}    (7.x, 8.x)
  {"type":"retreat", "unit":pid, "dest":[c,r], "displace":[[pid,[c,r]],...]?}
  {"type":"advance", "unit":pid?, "dest":[c,r]?}     (empty = decline, 7.75)
  {"type":"exchange_loss", "units":[pid,...]}        (7.6 Ex, attacker owes)
  {"type":"train_retreat", "dest":[c,r]?}            (18.11, dest None = destroyed)
  {"type":"end_phase"}                               (combat phase, 7.11/7.12 check)
"""
import hashlib
import json
import os
import random


class BlueGrayGame:
    def __init__(self, game, scenario_path, live_dir, seed=None, tier=None):
        self.game = game
        self.scenario = json.load(open(scenario_path, encoding="utf-8"))
        gkey = os.path.basename(os.path.normpath(game.dir))
        self.state_path = os.path.join(live_dir, f"game_{gkey}.state.json")
        self.log_path = os.path.join(live_dir, f"game_{gkey}.log.jsonl")
        cfg = self.scenario["game"]
        self.turns = int(cfg["turns"])
        self.first_player = cfg["first_player"]
        self.night_turns = set(cfg.get("night_turns", []))
        self.turn_labels = cfg.get("turn_labels", [])
        self.vp_cfg = self.scenario.get("vp", {})
        self.exit_cfg = game.spec.get("exit", {})
        self.exit_hexes = {tuple(h) for h in self.exit_cfg.get("hexes", [])}
        self.reserve = {u["id"]: u for u in self.scenario.get("reserve", [])}
        self.catalog = {u["id"]: u for u in
                        self.scenario.get("units", []) + self.scenario.get("reserve", [])}
        self.combat = game.spec.get("combat")
        self.tier_earned = (3 if game.spec.get("policy_ai") else 2) if self.combat else 1
        self.tier = self.tier_earned if tier is None \
            else max(1, min(int(tier), self.tier_earned))
        if self.tier < 2:
            self.combat = None
        if os.path.exists(self.state_path):
            self.s = json.load(open(self.state_path, encoding="utf-8"))
            if "occ" not in self.s or "retreated_phase" not in self.s \
               or self.s.get("tier", self.tier_earned) != self.tier:
                self.new_game(seed)
        else:
            self.new_game(seed)

    # ------------------------------------------------------------ lifecycle
    def new_game(self, seed=None):
        seed = seed if seed is not None else random.SystemRandom().randrange(10 ** 9)
        units = {}
        for u in self.scenario["units"]:
            units[u["id"]] = {"pid": u["id"], "slot": u["slot"], "side": u["side"],
                              "col": u["hex"][0], "row": u["hex"][1]}
        occ = {}
        for side, hexes in (self.vp_cfg.get("start_occupation") or {}).items():
            side_full = {"union": "Union", "confederate": "Confederate"}.get(side.lower(), side)
            for h in hexes:
                occ[h] = side_full
        self.s = {
            "seed": seed, "rng_calls": 0, "n": 0, "tier": self.tier,
            "turn": 1, "phase": "movement", "mover": self.first_player,
            "over": False, "winner": None,
            "units": units,
            "moved": {},                    # pid -> MP spent this movement phase
            "pool": {pid: e["due"] for pid, e in self.reserve.items()},
            "entered": 0,                   # reinforcements placed this player turn (column position)
            "exited": {},                   # pid -> side (16.3, permanent)
            "dead": [],
            "vp": {s: 0 for s in self.game.side_order},
            "occ": occ,                     # VP hex -> side last through (17.2)
            "attacked": {}, "defended": {}, "fought": [], "advanced": [],
            "retreated_phase": [],          # 7.74: no strength contribution after retreating
            "battle_no": 0,
            "pending": None,                # retreat/advance/exchange/train dict
            "train_checked": False,         # 18.11 auto-retreat handled this combat phase
        }
        if os.path.exists(self.log_path):
            os.remove(self.log_path)
        self._log({"event": "init", "mode": "bluegray",
                   "scenario": self.scenario["name"],
                   "tier": self.tier,
                   "rules_scope": self.rules_scope(),
                   "seed": seed, "turns": self.turns,
                   "first_player": self.first_player,
                   "units": [dict(pid=u["pid"], slot=u["slot"], side=u["side"],
                                  hex=[u["col"], u["row"]])
                             for u in units.values()]})
        self.save()

    def save(self):
        json.dump(self.s, open(self.state_path, "w", encoding="utf-8"), indent=1)

    def _log(self, entry):
        entry["n"] = self.s["n"]
        self.s["n"] += 1
        entry["state_hash"] = self.state_hash()
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def state_hash(self):
        core = {k: self.s[k] for k in
                ("turn", "phase", "mover", "over", "winner", "rng_calls",
                 "units", "moved", "pool", "entered", "exited", "dead", "vp",
                 "occ", "attacked", "defended", "fought", "advanced",
                 "retreated_phase", "battle_no", "pending", "train_checked")}
        blob = json.dumps(core, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    # ------------------------------------------------------------ dice
    def _rng(self):
        r = random.Random(self.s["seed"])
        for _ in range(self.s["rng_calls"]):
            r.random()
        return r

    def roll_die(self):
        r = self._rng()
        v = 1 + int(r.random() * 6)
        self.s["rng_calls"] += 1
        return v

    # ------------------------------------------------------------ helpers
    def unit(self, pid):
        return self.s["units"][str(pid)]

    def turn_label(self, t=None):
        t = self.s["turn"] if t is None else t
        return self.turn_labels[t - 1] if 0 < t <= len(self.turn_labels) else f"GT {t}"

    def is_night(self, t=None):
        return (self.s["turn"] if t is None else t) in self.night_turns

    def cls(self, u):
        return self.game.unit_class(u["slot"]) or "infantry"

    def strength(self, u):
        return self.game.stats(u["slot"])[0] or self.game.stats(u["slot"])[1]

    def printed(self, u):
        """Printed combat strength (Ex accounting, 7.6)."""
        st = self.game.stats(u["slot"])
        return max(st[0], st[1])

    def rules_board(self, exclude_pid=None, mover_side=None):
        """Units as the movement engine's board. The Train is presented as an
        ENEMY of whoever is moving: it blocks entry and pass-through for BOTH
        sides (18.21/18.22) while its zoc exempt-class keeps it ZOC-less
        (18.25)."""
        out = []
        for u in self.s["units"].values():
            if u["pid"] == exclude_pid:
                continue
            side = u["side"]
            if mover_side and self.cls(u) == "train" and u["side"] == mover_side:
                side = self.game.enemy(mover_side)
            out.append(dict(id=u["pid"], name=u["slot"], side=side,
                            col=u["col"], row=u["row"]))
        return out

    def budget(self, u):
        return self.game.stats(u["slot"])[2]

    def _crossable(self, a, b):
        """Sides a unit (or ZOC/attack) may cross: everything except a
        non-crossing creek hexside (5.25/6.6/TEC)."""
        return not self.game.hexside_prohibited(a, b)

    def _engage_adjacent(self, ua, ub):
        """Combat contact: adjacency across a crossable hexside (attacks only
        across bridges/fords on the creek, TEC; no ZOC through plain creek 6.6)."""
        pa, pb = (ua["col"], ua["row"]), (ub["col"], ub["row"])
        return pb in self.game.neighbors(*pa) and self._crossable(pa, pb)

    def dests(self, u):
        """Legal destinations {hex: mp} for a gate unit. Train: road/trail
        network only, never stacks, blocked hexes as usual (18.2). Night: may
        not enter an EZOC (10.2)."""
        me = dict(id=u["pid"], name=u["slot"], side=u["side"],
                  col=u["col"], row=u["row"])
        board = self.rules_board(exclude_pid=u["pid"], mover_side=u["side"])
        if self.cls(u) == "train":
            dd = self._train_dests(u, board)
        else:
            dd = self.game.legal_destinations_t(me, self.budget(u), board)
        if self.is_night():
            ezoc = self.game.zoc_hexes(board, self.game.enemy(u["side"]))
            dd = {h: c for h, c in dd.items() if h not in ezoc}
        return dd

    def _train_dests(self, u, board):
        """Train movement (18.23): roads/trails ONLY (bridges carry roads,
        fords carry trails), never stacks with anyone (18.21), blocked by all
        units, ZOC stop applies (it is a unit like any other for 6.0)."""
        import heapq
        start = (u["col"], u["row"])
        occ = {(b["col"], b["row"]) for b in board}
        enemy = self.game.enemy(u["side"])
        ezoc = self.game.zoc_hexes(board, enemy)
        if self.game.zoc_cfg.get("locked_at_start") and start in ezoc:
            return {}
        ma = self.budget(u)
        best = {start: 0.0}
        pq = [(0.0, start)]
        while pq:
            cost, cur = heapq.heappop(pq)
            if cost > best.get(cur, 1e9):
                continue
            if cur != start and cur in ezoc:
                continue
            for nb in self.game.neighbors(*cur):
                f = self.game.side_features(cur, nb)
                if not (f.get("road") or f.get("trail")):
                    continue
                if nb in occ:
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
        return best

    def _cheapest_path(self, u, dest):
        """Deterministic min-cost path start->dest under the same constraints
        as dests() (parent-tracked Dijkstra with sorted neighbor order).
        Used for occupation credit (17.22) when no explicit path is given."""
        import heapq
        me = dict(id=u["pid"], name=u["slot"], side=u["side"],
                  col=u["col"], row=u["row"])
        board = self.rules_board(exclude_pid=u["pid"], mover_side=u["side"])
        enemy = self.game.enemy(u["side"])
        occ_enemy = {(b["col"], b["row"]) for b in board if b["side"] == enemy}
        ezoc = self.game.zoc_hexes(board, enemy)
        start = (u["col"], u["row"])
        best = {start: 0.0}
        parent = {}
        pq = [(0.0, start)]
        while pq:
            cost, cur = heapq.heappop(pq)
            if cost > best.get(cur, 1e9):
                continue
            if cur == dest:
                break
            if cur != start and cur in ezoc:
                continue
            if self.cls(u) == "train":
                nbs = [nb for nb in self.game.neighbors(*cur)
                       if self.game.side_features(cur, nb).get("road")
                       or self.game.side_features(cur, nb).get("trail")]
            else:
                nbs = self.game.neighbors(*cur)
            for nb in sorted(nbs):
                if nb in occ_enemy:
                    continue
                c = self.game.move_cost(cur, nb)
                if c is None:
                    continue
                nc = cost + c
                if nc < best.get(nb, 1e9) - 1e-9:
                    best[nb] = nc
                    parent[nb] = cur
                    heapq.heappush(pq, (nc, nb))
        if dest not in parent and dest != start:
            return [start, dest]
        path = [dest]
        while path[-1] != start:
            path.append(parent[path[-1]])
        return list(reversed(path))

    def _credit_occupation(self, side, hexes):
        """17.21/17.22: occupation = last friendly unit on/through the hex."""
        vp_hexes = set()
        for d in (self.vp_cfg.get("occupation") or {}).values():
            vp_hexes |= set(d.keys())
        for h in hexes:
            key = f"{h[0]:02d}{h[1]:02d}"
            if key in vp_hexes:
                self.s["occ"][key] = side

    # ------------------------------------------------------------ contacts
    def _live(self, side=None):
        for u in self.s["units"].values():
            if side is None or u["side"] == side:
                yield u

    def _contacts(self, side):
        """(engaged_friendly_pids, engaged_enemy_pids) under 7.11/7.12:
        contact = crossable adjacency between a phasing unit and an enemy
        unit. The Train neither attacks nor must be attacked (18.11/18.25);
        advanced units are out of the phase entirely (7.75)."""
        adv = set(self.s["advanced"])
        mine, theirs = set(), set()
        enemies = [u for u in self._live(self.game.enemy(side))
                   if self.cls(u) != "train" and u["pid"] not in adv]
        for u in self._live(side):
            if self.cls(u) == "train" or u["pid"] in adv:
                continue
            for e in enemies:
                if self._engage_adjacent(u, e):
                    mine.add(u["pid"])
                    theirs.add(e["pid"])
        return mine, theirs

    # ------------------------------------------------------------ artillery LOS
    def _hex_line(self, a, b):
        """Hexes strictly between a and b along the center-to-center line,
        with hexside-congruent pairs returned as 2-tuples (8.32)."""
        ax, ay = self.game.grid.hex_to_pixel(*a)
        bx, by = self.game.grid.hex_to_pixel(*b)
        n = self.game.hex_distance(a, b)
        out = []
        for i in range(1, n):
            t = i / n
            px, py = ax + (bx - ax) * t, ay + (by - ay) * t
            c, r, _ = self.game.grid.pixel_to_hex(px, py)
            cx, cy = self.game.grid.hex_to_pixel(c, r)
            d2 = (px - cx) ** 2 + (py - cy) ** 2
            # find the second-closest hex center; if nearly equidistant the
            # LOS is congruent to their shared hexside
            second, sd2 = None, 1e18
            for nb in self.game.neighbors(c, r):
                nx, ny = self.game.grid.hex_to_pixel(*nb)
                dd = (px - nx) ** 2 + (py - ny) ** 2
                if dd < sd2:
                    second, sd2 = nb, dd
            if abs(sd2 - d2) < (self.game.grid.dy * 0.18) ** 2:
                out.append(((c, r), second))
            else:
                out.append(((c, r),))
        return out

    def _los_clear(self, a, b):
        """8.3: blocked when an intervening hex holds blocking terrain;
        congruent-hexside points block only if BOTH hexes block (8.32);
        firer and target hexes never block (8.34)."""
        blocking = set((self.combat or {}).get("artillery", {})
                       .get("los_blocking_terrain", []))
        for point in self._hex_line(a, b):
            hexes = [h for h in point if h not in (a, b)]
            if not hexes:
                continue
            if len(hexes) == 2:
                if all(self.game.hex_terrain(*h) in blocking for h in hexes):
                    return False
            elif self.game.hex_terrain(*hexes[0]) in blocking:
                return False
        return True

    def _los_crosses_double(self, a, b):
        """Deluxe 9.0 clarification: solely-bombarded defender is doubled when
        the LOS crosses a ford/bridge/creek hexside or an impassable hex."""
        for point in self._hex_line(a, b):
            for h in point:
                if h in (a, b):
                    continue
                t = self.game.hex_terrain(*h)
                if t is None or t in self.game.impassable:
                    return True
        # hexside crossings: consecutive hexes of the sampled line
        chain = [a] + [p[0] for p in self._hex_line(a, b)] + [b]
        for h1, h2 in zip(chain, chain[1:]):
            if h2 in self.game.neighbors(*h1):
                f = self.game.side_features(h1, h2)
                if f.get("creek") or f.get("ford") or f.get("bridge"):
                    return True
        return False

    # ------------------------------------------------------------ verdict
    def _v(self, ok, *reasons):
        return {"legal": bool(ok), "reasons": list(reasons)}

    # ------------------------------------------------------------ propose
    def propose(self, side, action):
        s = self.s
        t = action.get("type")
        if s["over"]:
            return self._v(False, "game is over [17.0]")
        if s["pending"]:
            # pending resolutions (retreat/advance/exchange/train) belong to
            # the pending owner, who may be the NON-phasing player (7.71: the
            # OWNING player retreats his units)
            p = s["pending"]
            if t != p["awaiting"]:
                return self._v(False, f"pending {p['awaiting']} must be resolved first [7.7/7.75]")
        elif side != s["mover"]:
            return self._v(False, f"not {side}'s player turn [4.1]")
        if t == "move":
            return self._propose_move(side, action)
        if t == "reinforce":
            return self._propose_reinforce(side, action)
        if t == "exit":
            return self._propose_exit(side, action)
        if t == "end_movement":
            if s["phase"] != "movement":
                return self._v(False, "not the movement phase [4.1]")
            return self._v(True, "movement phase complete [4.1]")
        if t == "battle":
            return self._propose_battle(side, action)
        if t == "retreat":
            return self._propose_retreat(side, action)
        if t == "advance":
            return self._propose_advance(side, action)
        if t == "exchange_loss":
            return self._propose_exchange_loss(side, action)
        if t == "train_retreat":
            return self._propose_train_retreat(side, action)
        if t == "end_phase":
            return self._propose_end_phase(side)
        return self._v(False, f"unknown action type {t!r}")

    def _gate_unit(self, side, action):
        pid = str(action.get("unit"))
        if pid not in self.s["units"]:
            return None, self._v(False, f"no such unit on the map: {pid}")
        u = self.unit(pid)
        if u["side"] != side:
            return None, self._v(False, f"{u['slot']} is not a {side} unit")
        return u, None

    def _propose_move(self, side, action):
        s = self.s
        if s["phase"] != "movement":
            return self._v(False, "movement only in the movement phase [5.11]")
        u, err = self._gate_unit(side, action)
        if err:
            return err
        if u["pid"] in s["moved"]:
            return self._v(False, f"{u['slot']} has already moved this phase [5.17]")
        dest = tuple(action.get("dest", ()))
        if len(dest) != 2:
            return self._v(False, "move needs a dest [c,r]")
        dd = self.dests(u)
        if dest not in dd:
            return self._v(False,
                           f"{dest} is not a legal destination for {u['slot']} "
                           f"[5.x movement / 6.x ZOC / 9.0 TEC"
                           + ("; night: no EZOC entry 10.2" if self.is_night() else "") + "]")
        return self._v(True, f"move {u['slot']} to {dest} for {dd[dest]:g} MP")

    def _propose_reinforce(self, side, action):
        s = self.s
        if s["phase"] != "movement":
            return self._v(False, "reinforcements enter during the movement phase [15.1]")
        pid = str(action.get("unit"))
        if pid not in self.reserve or pid in s["units"] or pid in s["exited"] \
           or pid in s["dead"]:
            return self._v(False, f"{pid} is not an available reinforcement")
        e = self.reserve[pid]
        if e["side"] != side:
            return self._v(False, f"{e['slot']} is not a {side} reinforcement")
        if s["pool"].get(pid, 99) > s["turn"]:
            return self._v(False,
                           f"{e['slot']} is due GT {s['pool'][pid]}, not GT {s['turn']} [15.0]")
        hexes = [tuple(h) for h in e["entry"]]
        h = tuple(action.get("hex", ()))
        if h not in hexes:
            return self._v(False, f"entry hexes for {e['slot']}: {hexes} [15.0]")
        occ = {(x["col"], x["row"]) for x in s["units"].values()}
        if h in occ:
            if all(hh in occ for hh in hexes):
                return self._v(False, "both entry hexes occupied - delayed [15.5]")
            return self._v(False, f"entry hex {h} is occupied [15.4 unstacked column]")
        cost = 1 + s["entered"]   # 15.0: 1st unit 1 MP, 2nd 2 MP, ...
        if cost > self.budget({"slot": e["slot"]}):
            return self._v(False,
                           f"column position {s['entered'] + 1} costs {cost} MP > MA [15.0/15.3]")
        return self._v(True, f"{e['slot']} enters at {h} (column cost {cost} MP) [15.0]")

    def _propose_exit(self, side, action):
        s = self.s
        if s["phase"] != "movement":
            return self._v(False, "exiting happens during movement [16.2]")
        u, err = self._gate_unit(side, action)
        if err:
            return err
        if (u["col"], u["row"]) not in self.exit_hexes:
            return self._v(False, f"{u['slot']} is not on an exit hex 0101/0111 [16.1/16.5]")
        spent = s["moved"].get(u["pid"], 0)
        if spent + self.exit_cfg.get("mp", 1) > self.budget(u):
            return self._v(False, f"no MP left to exit ({spent} spent) [16.2]")
        return self._v(True, f"{u['slot']} exits the map [16.1-16.4]")

    # ---------------------------------------------------------------- combat
    def _propose_battle(self, side, action):
        s = self.s
        if not self.combat:
            return self._v(False, f"combat is not enforced at tier {self.tier} [13]")
        if s["phase"] != "combat":
            return self._v(False, "battles happen in the combat phase [4.1/5.14]")
        if self.is_night():
            return self._v(False, "no combat of any kind on a night GT [10.1]")
        if s["pending"]:
            return self._v(False, "resolve the pending result first [7.7]")
        atk_ids = [str(p) for p in action.get("attackers", [])]
        def_ids = [str(p) for p in action.get("defenders", [])]
        bomb_ids = [str(p) for p in action.get("bombarding", [])]
        if not atk_ids or not def_ids:
            return self._v(False, "battle needs attackers and defenders [7.0]")
        if not set(bomb_ids) <= set(atk_ids):
            return self._v(False, "bombarding units must be listed as attackers [8.2]")
        for pid in atk_ids + def_ids:
            if pid not in s["units"]:
                return self._v(False, f"unit {pid} is not on the map")
        atk = [self.unit(p) for p in atk_ids]
        dfd = [self.unit(p) for p in def_ids]
        if any(u["side"] != side for u in atk):
            return self._v(False, "attackers must be the phasing player's units [7.0]")
        if any(u["side"] == side for u in dfd):
            return self._v(False, "defenders must be enemy units [7.0]")
        if any(p in s["fought"] for p in atk_ids):
            return self._v(False, "a unit may attack only once per combat phase [7.14]")
        pure_bombard = set(bomb_ids) == set(atk_ids) and bool(atk_ids)
        for p in def_ids:
            # 7.74 exception: a unit retreated this phase may be swept into a
            # BOMBARDMENT of its new hex (contributing no strength); melee
            # re-attacks stay barred by 7.14
            if p in s["defended"] and not (
                    p in s["retreated_phase"] and pure_bombard):
                return self._v(False, "a unit may be attacked only once per phase [7.14]")
        if any(p in s["advanced"] for p in atk_ids + def_ids):
            return self._v(False, "advanced units may neither attack nor be attacked [7.75]")
        if any(self.cls(u) == "train" for u in atk):
            return self._v(False, "the Train may never attack [18.11]")
        # full stacks fight together: defenders (7.21) and attackers (7.22)
        def stackmates(pids, pool):
            hexes = {(self.unit(p)["col"], self.unit(p)["row"]) for p in pids}
            for u in pool:
                if (u["col"], u["row"]) in hexes and u["pid"] not in pids \
                   and self.cls(u) != "train" and u["pid"] not in s["advanced"]:
                    return u
            return None
        m = stackmates(def_ids, list(self._live(self.game.enemy(side))))
        if m:
            return self._v(False,
                           f"all units in a defending hex are attacked as one total - "
                           f"{m['slot']} is co-stacked [7.21]")
        # co-stacked attackers must attack together only if both attack;
        # but a stacked pair engaged by 7.12 both must fight - checked at
        # end_phase. Here: co-stacked attackers in DIFFERENT battles is
        # prevented by 7.22 once either has fought.
        for p in atk_ids:
            u = self.unit(p)
            for v in self._live(side):
                if v["pid"] != p and (v["col"], v["row"]) == (u["col"], u["row"]) \
                   and v["pid"] in s["fought"] and self.cls(v) != "train":
                    return self._v(False,
                                   f"co-stacked attackers fight as one combined strength - "
                                   f"{v['slot']} already attacked separately [7.22]")
        # bombarding artillery checks (8.x)
        board = self.rules_board(mover_side=side)
        ezoc = self.game.zoc_hexes(board, self.game.enemy(side))
        rng_lo, rng_hi = (self.combat.get("artillery", {}).get("range") or [2, 3])
        for p in bomb_ids:
            u = self.unit(p)
            if self.cls(u) != "artillery":
                return self._v(False, f"{u['slot']} is not artillery - cannot bombard [8.0]")
            if (u["col"], u["row"]) in ezoc:
                return self._v(False,
                               f"{u['slot']} is in an EZOC - it must fight normally, "
                               f"not bombard [8.41]")
            src = (u["col"], u["row"])
            ok_target = False
            for d in dfd:
                dist = self.game.hex_distance(src, (d["col"], d["row"]))
                if rng_lo <= dist <= rng_hi and self._los_clear(src, (d["col"], d["row"])):
                    ok_target = True
                    break
            if not ok_target:
                return self._v(False,
                               f"{u['slot']} has no defending hex in range {rng_lo}-{rng_hi} "
                               f"with a clear LOS [8.1/8.3]")
        # stacked artillery must share the bombardment target hex (8.14):
        # both bombarding from one hex -> same battle by construction here.
        # bombardment-only attacks hit a single hex (8.13)
        dhexes = {(d["col"], d["row"]) for d in dfd}
        melee = [p for p in atk_ids if p not in bomb_ids]
        if not melee and len(dhexes) > 1:
            return self._v(False, "a pure bombardment attacks a single hex [8.13]")
        # every melee attacker adjacent (crossable) to EVERY defender (7.25)
        for p in melee:
            u = self.unit(p)
            if (u["col"], u["row"]) in dhexes:
                return self._v(False, "attacker and defender share a hex?!")
            for d in dfd:
                if not self._engage_adjacent(u, d):
                    return self._v(False,
                                   f"{u['slot']} is not adjacent to {d['slot']} across a "
                                   f"crossable hexside - multi-hex combat needs all "
                                   f"attackers adjacent to all defenders [7.25/6.6]")
        # odds
        odds_pair = self._battle_odds(atk, dfd, bomb_ids, dhexes)
        red = action.get("odds_reduce")
        if red:
            red = (int(red[0]), int(red[1]))
            if not self._odds_leq(red, odds_pair):
                return self._v(False,
                               f"may only REDUCE the odds ({red[0]}-{red[1]} is not below "
                               f"{odds_pair[0]}-{odds_pair[1]}) [7.9]")
            if self._col_of(red) is None:
                return self._v(False, f"{red[0]}-{red[1]} is not a CRT column [7.9]")
            odds_pair = red
        return self._v(True,
                       f"battle at {odds_pair[0]}-{odds_pair[1]} "
                       f"({len(atk_ids)} vs {len(def_ids)}) [7.0]")

    def _odds_leq(self, a, b):
        return a[0] * b[1] <= b[0] * a[1]

    def _col_of(self, pair):
        """CRT column for an odds pair, clamped per the printed note
        (>6-1 -> 6-1, <1-5 -> 1-5; both still roll)."""
        n, d = pair
        hi = self.combat["odds"]["clamp_high"]
        lo = self.combat["odds"]["clamp_low"]
        if d == 1 and n >= hi[0]:
            n, d = hi
        if n == 1 and d >= lo[1]:
            n, d = lo
        col = f"{n}-{d}"
        return col if col in self.combat["crt"]["columns"] else None

    def _battle_odds(self, atk, dfd, bomb_ids, dhexes):
        a_str = sum(self.strength(u) for u in atk)
        # 7.74: a unit already retreated this combat phase contributes NO
        # strength when its new hex is attacked, though it suffers the result
        retreated = set(self.s.get("retreated_phase", []))
        melee = [u for u in atk if u["pid"] not in bomb_ids]
        d_str = 0
        dbl_terr = set(self.combat.get("defense_double_terrain", []))
        hexside_feats = set((self.combat.get("defense_double_hexside") or {})
                            .get("features", []))
        for h in sorted(dhexes):
            stack = [d for d in dfd if (d["col"], d["row"]) == h]
            base = sum(self.strength(d) for d in stack
                       if d["pid"] not in retreated)
            doubled = self.game.hex_terrain(*h) in dbl_terr
            if not doubled:
                adj = [u for u in melee
                       if h in self.game.neighbors(u["col"], u["row"])]
                if adj and all(
                        any(self.game.side_features((u["col"], u["row"]), h).get(f)
                            for f in hexside_feats) for u in adj):
                    doubled = True     # all adjacent attackers cross bridge/ford
                elif not melee:
                    # solely bombarded: doubled if any firer's LOS crosses
                    # ford/bridge/creek or an impassable hex (deluxe 9.0)
                    firers = [u for u in atk if u["pid"] in bomb_ids]
                    if firers and all(self._los_crosses_double(
                            (u["col"], u["row"]), h) for u in firers):
                        doubled = True
            d_str += base * 2 if doubled else base
        if d_str <= 0:
            # every defender retreated this phase (7.74: zero contribution):
            # best odds the table offers
            return tuple(self.combat["odds"]["clamp_high"])
        if a_str <= 0:
            return tuple(self.combat["odds"]["clamp_low"])
        return self.game.odds(a_str, d_str)

    # ------------------------------------------------- retreats & advances
    def _retreat_hexes(self, u):
        """Legal 1-hex retreat destinations (7.71/7.72): adjacent, crossable,
        on-map, not into EZOC, not into an enemy hex, stacking respected
        (friendly stack not in EZOC, 7.73). Returns (open_hexes,
        displace_hexes): displace = full friendly stacks reachable only by
        displacement (7.8). The Train retreats only along roads/trails
        (18.23) and never stacks (18.21)."""
        board = self.rules_board(exclude_pid=u["pid"], mover_side=u["side"])
        enemy = self.game.enemy(u["side"])
        ezoc = self.game.zoc_hexes(board, enemy)
        epos = {(b["col"], b["row"]) for b in board if b["side"] == enemy}
        src = (u["col"], u["row"])
        open_h, disp_h = [], []
        for nb in self.game.neighbors(*src):
            if not self.game.on_map(*nb) or not self._crossable(src, nb):
                continue
            if self.cls(u) == "train":
                f = self.game.side_features(src, nb)
                if not (f.get("road") or f.get("trail")):
                    continue   # 18.23: forced to a non-road/trail hex = destroyed
            if nb in ezoc or nb in epos:
                continue
            friends = [v for v in self.s["units"].values()
                       if v["pid"] != u["pid"] and (v["col"], v["row"]) == nb
                       and v["side"] == u["side"]]
            if self.cls(u) == "train" and friends:
                continue                       # 18.21 never stacks
            if any(self.cls(v) == "train" for v in friends):
                continue                       # 18.21 no one stacks with it
            if not friends:
                open_h.append(nb)
            elif nb in ezoc:
                continue
            elif len(friends) < int(self.game.stacking["max"]):
                open_h.append(nb)
            else:
                disp_h.append(nb)
        return open_h, disp_h

    def _propose_retreat(self, side, action):
        s = self.s
        p = s["pending"]
        if not p or p["awaiting"] != "retreat":
            return self._v(False, "no retreat pending [7.7]")
        if side != p["by"]:
            return self._v(False, f"the {p['by']} player retreats his own units [7.71]")
        pid = str(action.get("unit"))
        if pid not in p["units"]:
            return self._v(False, f"{pid} is not among the retreating units")
        u = self.unit(pid)
        open_h, disp_h = self._retreat_hexes(u)
        dest = action.get("dest")
        if dest is None:
            if open_h or disp_h:
                return self._v(False,
                               f"{u['slot']} has retreat hexes open {open_h + disp_h} - "
                               f"elimination only when none exist [7.72]")
            return self._v(True, f"{u['slot']} has no retreat - eliminated [7.72]"
                           + (" (Train forced off road/trail is destroyed 18.23)"
                              if self.cls(u) == "train" else ""))
        dest = tuple(dest)
        if dest in open_h:
            return self._v(True, f"{u['slot']} retreats to {dest} [7.71]")
        if dest in disp_h:
            if open_h:
                return self._v(False,
                               f"displacement only when no other path exists - open: "
                               f"{open_h} [7.8/7.82]")
            return self._v(True, f"{u['slot']} retreats to {dest} displacing [7.8]")
        return self._v(False, f"{dest} is not a legal retreat hex for {u['slot']} [7.72]")

    def _propose_advance(self, side, action):
        s = self.s
        p = s["pending"]
        if not p or p["awaiting"] != "advance":
            return self._v(False, "no advance pending [7.75]")
        if side != p["by"]:
            return self._v(False, f"the {p['by']} player owns the advance [7.75]")
        if action.get("unit") is None:
            return self._v(True, "advance declined [7.75: never forced]")
        pid = str(action.get("unit"))
        if pid not in p["units"]:
            return self._v(False, "only a victorious participating unit may advance [7.75]")
        dest = tuple(action.get("dest", ()))
        if dest not in {tuple(h) for h in p["hexes"]}:
            return self._v(False, f"advance hexes: {p['hexes']} [7.75]")
        u = self.unit(pid)
        src = (u["col"], u["row"])
        if dest not in self.game.neighbors(*src):
            return self._v(False, f"{u['slot']} is not adjacent to {dest} [7.75 one hex]")
        if not self._crossable(src, dest):
            return self._v(False, "no advance across an uncrossable hexside [5.25]")
        return self._v(True, f"{u['slot']} advances into {dest} [7.75]")

    def _propose_exchange_loss(self, side, action):
        s = self.s
        p = s["pending"]
        if not p or p["awaiting"] != "exchange_loss":
            return self._v(False, "no exchange pending [7.6]")
        if side != p["by"]:
            return self._v(False, "the attacker chooses the exchange loss [7.6]")
        pids = [str(x) for x in action.get("units", [])]
        if not set(pids) <= set(p["units"]):
            return self._v(False,
                           "only participating non-bombarding attackers may be "
                           "exchanged [7.6/8.15]")
        total = sum(self.printed(self.unit(x)) for x in pids)
        owe = p["owe"]
        if total < owe:
            all_total = sum(self.printed(self.unit(x)) for x in p["units"])
            if set(pids) == set(p["units"]) and all_total < owe:
                return self._v(True,
                               "all participating units removed - printed total below "
                               "the owed strength [7.6, outcome-equivalent]")
            return self._v(False, f"exchange must remove >= {owe} printed strength "
                                  f"(chosen {total}) [7.6]")
        # no unnecessary over-removal: dropping any chosen unit must fall below owe
        for x in pids:
            if total - self.printed(self.unit(x)) >= owe:
                return self._v(False,
                               f"removing {self.unit(x)['slot']} is unnecessary - "
                               f"exchange removes no more than needed [7.6]")
        return self._v(True, f"exchange loss {total} >= {owe} [7.6]")

    def _propose_train_retreat(self, side, action):
        s = self.s
        p = s["pending"]
        if not p or p["awaiting"] != "train_retreat":
            return self._v(False, "no train retreat pending [18.11]")
        if side != p["by"]:
            return self._v(False, "the Union player moves the Train [18.11]")
        u = self.unit(p["unit"])
        open_h, _ = self._retreat_hexes(u)
        dest = action.get("dest")
        if dest is None:
            if open_h:
                return self._v(False, f"the Train can retreat to {open_h} [18.11/18.23]")
            return self._v(True, "no road/trail retreat open - the Train is destroyed [18.23]")
        dest = tuple(dest)
        if dest not in open_h:
            return self._v(False, f"legal Train retreat hexes: {open_h} [18.23]")
        return self._v(True, f"the Train retreats to {dest} [18.11]")

    def _propose_end_phase(self, side):
        s = self.s
        if s["phase"] != "combat":
            return self._v(False, "end_phase ends the combat phase - use end_movement [4.1]")
        if s["pending"]:
            return self._v(False, "resolve the pending result first [7.7]")
        if self.combat and not self.is_night():
            if not s["train_checked"] and self._train_contact(side):
                return self._v(False, "the Train must auto-retreat first [18.11]")
            mine, theirs = self._contacts(side)
            un_att = [p for p in sorted(theirs) if p not in s["defended"]]
            un_fgt = [p for p in sorted(mine) if p not in s["fought"]]
            if un_att:
                names = ", ".join(self.unit(p)["slot"] for p in un_att[:4])
                return self._v(False,
                               f"every enemy unit in contact must be attacked: {names} "
                               f"[7.0/7.11]")
            if un_fgt:
                names = ", ".join(self.unit(p)["slot"] for p in un_fgt[:4])
                return self._v(False,
                               f"every friendly unit in contact must attack: {names} "
                               f"[7.12/7.23]")
        return self._v(True, "combat phase complete [4.1]")

    def _train_contact(self, side):
        """18.11: the Union Train adjacent to a Confederate unit during the
        UNION combat phase must auto-retreat (plain adjacency)."""
        if side != "Union":
            return None
        for u in self._live("Union"):
            if self.cls(u) == "train":
                for e in self._live("Confederate"):
                    if (e["col"], e["row"]) in self.game.neighbors(u["col"], u["row"]):
                        return u["pid"]
        return None

    # ------------------------------------------------------------ submit
    def submit(self, side, action):
        """The only door: validate, log the proposal + verdict, apply if legal."""
        verdict = self.propose(side, action)
        entry = {"event": "action", "turn": self.s["turn"], "phase": self.s["phase"],
                 "side": side, "action": action, "verdict": verdict}
        if not verdict["legal"]:
            self._log(entry)
            self.save()
            return {"verdict": verdict}
        result = self._apply(side, action, verdict)
        entry["result"] = result
        self._log(entry)
        self.save()
        return {"verdict": verdict, "result": result}

    # ------------------------------------------------------------ apply
    def _apply(self, side, action, verdict):
        s = self.s
        t = action["type"]
        ev = []
        if t == "move":
            u = self.unit(str(action["unit"]))
            dest = tuple(action["dest"])
            dd = self.dests(u)
            path = [tuple(h) for h in action.get("path") or []] \
                or self._cheapest_path(u, dest)
            u["col"], u["row"] = dest
            s["moved"][u["pid"]] = dd[dest]
            self._credit_occupation(side, path + [dest])
            ev.append({"move": u["slot"], "to": list(dest), "mp": dd[dest]})
        elif t == "reinforce":
            pid = str(action["unit"])
            e = self.reserve[pid]
            h = tuple(action["hex"])
            cost = 1 + s["entered"]
            s["units"][pid] = {"pid": pid, "slot": e["slot"], "side": side,
                               "col": h[0], "row": h[1]}
            s["pool"].pop(pid, None)
            s["entered"] += 1
            s["moved"][pid] = cost         # column MP spent; may still move later? no - moved
            self._credit_occupation(side, [h])
            ev.append({"reinforce": e["slot"], "at": list(h), "column_mp": cost})
        elif t == "exit":
            u = self.unit(str(action["unit"]))
            s["exited"][u["pid"]] = side
            del s["units"][u["pid"]]
            ev.append({"exit": u["slot"], "csp": self.printed(u)})
        elif t == "end_movement":
            s["moved"] = {}
            s["entered"] = 0
            if self.combat and not self.is_night():
                s["phase"] = "combat"
                s["attacked"], s["defended"] = {}, {}
                s["fought"], s["advanced"] = [], []
                s["retreated_phase"] = []
                s["train_checked"] = False
                tr = self._train_contact(side)
                if tr:
                    s["pending"] = {"awaiting": "train_retreat", "by": "Union",
                                    "unit": tr}
                    ev.append({"train_must_retreat": tr})
                else:
                    s["train_checked"] = True
            else:
                ev += self._next_player()
        elif t == "battle":
            ev += self._apply_battle(side, action)
        elif t == "retreat":
            ev += self._apply_retreat(side, action)
        elif t == "advance":
            ev += self._apply_advance(side, action)
        elif t == "exchange_loss":
            ev += self._apply_exchange_loss(side, action)
        elif t == "train_retreat":
            ev += self._apply_train_retreat(side, action)
        elif t == "end_phase":
            ev += self._next_player()
        return ev

    def _next_player(self):
        s = self.s
        ev = []
        s["phase"] = "movement"
        s["moved"] = {}
        s["entered"] = 0
        s["attacked"], s["defended"] = {}, {}
        s["fought"], s["advanced"] = [], []
        s["retreated_phase"] = []
        s["pending"] = None
        s["train_checked"] = False
        order = self.game.side_order
        if s["mover"] == order[0]:
            s["mover"] = order[1]
            ev.append({"player_turn": s["mover"]})
        else:
            s["turn"] += 1
            s["mover"] = order[0]
            if s["turn"] > self.turns:
                ev += self._final_scoring()
            else:
                ev.append({"game_turn": s["turn"], "label": self.turn_label(),
                           "night": self.is_night()})
        return ev

    # ------------------------------------------------------------ battle core
    def _apply_battle(self, side, action):
        s = self.s
        atk_ids = [str(p) for p in action["attackers"]]
        def_ids = [str(p) for p in action["defenders"]]
        bomb_ids = [str(p) for p in action.get("bombarding", [])]
        atk = [self.unit(p) for p in atk_ids]
        dfd = [self.unit(p) for p in def_ids]
        dhexes = {(d["col"], d["row"]) for d in dfd}
        odds_pair = self._battle_odds(atk, dfd, bomb_ids, dhexes)
        red = action.get("odds_reduce")
        if red:
            odds_pair = (int(red[0]), int(red[1]))
        col = self._col_of(odds_pair)
        die = self.roll_die()
        res = self.combat["crt"]["rows"][str(die)][
            self.combat["crt"]["columns"].index(col)]
        s["battle_no"] += 1
        bno = s["battle_no"]
        for p in atk_ids:
            s["fought"].append(p)
            s["attacked"][p] = bno
        for p in def_ids:
            s["defended"][p] = bno
        ev = [{"battle": bno, "odds": f"{odds_pair[0]}-{odds_pair[1]}",
               "column": col, "die": die, "result": res,
               "attackers": [self.unit(p)["slot"] for p in atk_ids],
               "defenders": [self.unit(p)["slot"] for p in def_ids],
               "bombarding": [self.unit(p)["slot"] for p in bomb_ids]}]
        melee_ids = [p for p in atk_ids if p not in bomb_ids]
        a_hexes = sorted({(self.unit(p)["col"], self.unit(p)["row"])
                          for p in melee_ids})
        d_hexes = sorted(dhexes)
        if res == "De":
            ev += self._eliminate(def_ids, "De [7.6]")
            ev += self._offer_advance(side, atk_ids, bomb_ids, d_hexes, bno)
        elif res == "Ae":
            victims = melee_ids            # bombarding artillery immune [8.15]
            ev += self._eliminate(victims, "Ae [7.6/8.15]")
            ev += self._offer_advance(self.game.enemy(side), def_ids, [], a_hexes, bno)
        elif res == "Ex":
            owe = sum(self.printed(self.unit(p)) for p in def_ids)
            ev += self._eliminate(def_ids, "Ex defenders [7.6]")
            if melee_ids:
                s["pending"] = {"awaiting": "exchange_loss", "by": side,
                                "units": melee_ids, "owe": owe, "battle": bno,
                                "adv_hexes": d_hexes}
                ev.append({"exchange_owed": owe})
            else:
                # pure bombardment: defenders eliminated, bombarding artillery
                # unaffected by its own results [8.0 example / 8.15]
                ev.append({"exchange_owed": 0,
                           "note": "bombarding artillery immune [8.15]"})
        elif res == "Dr":
            s["pending"] = {"awaiting": "retreat", "by": self.game.enemy(side),
                            "units": list(def_ids), "battle": bno,
                            "vacating": d_hexes, "adv_by": side,
                            "adv_units": melee_ids}
            ev.append({"defender_retreats": [self.unit(p)["slot"] for p in def_ids]})
        elif res == "Ar":
            s["pending"] = {"awaiting": "retreat", "by": side,
                            "units": list(melee_ids), "battle": bno,
                            "vacating": a_hexes, "adv_by": self.game.enemy(side),
                            "adv_units": list(def_ids)}
            if melee_ids:
                ev.append({"attacker_retreats": [self.unit(p)["slot"] for p in melee_ids]})
            else:
                s["pending"] = None
                ev.append({"attacker_retreats": [],
                           "note": "pure bombardment suffers no results [8.15]"})
        return ev

    def _eliminate(self, pids, why):
        s = self.s
        ev = []
        for p in pids:
            if p not in s["units"]:
                continue
            u = self.unit(p)
            csp = self.printed(u)
            enemy = self.game.enemy(u["side"])
            s["vp"][enemy] += csp * self.vp_cfg.get("per_enemy_csp_eliminated", 1)
            s["dead"].append(p)
            del s["units"][p]
            ev.append({"eliminated": u["slot"], "csp": csp, "why": why,
                       "vp_to": enemy})
        return ev

    def _offer_advance(self, by, unit_ids, bomb_ids, hexes, bno):
        """7.75: one victorious participating unit (never bombarding
        artillery - it is at range) may advance into ONE vacated hex."""
        s = self.s
        cands = [p for p in unit_ids if p not in bomb_ids and p in s["units"]]
        hexes = [list(h) for h in hexes]
        if not cands or not hexes:
            return []
        s["pending"] = {"awaiting": "advance", "by": by, "units": cands,
                        "hexes": hexes, "battle": bno}
        return [{"advance_offered": by, "hexes": hexes}]

    def _apply_retreat(self, side, action):
        s = self.s
        p = s["pending"]
        pid = str(action["unit"])
        u = self.unit(pid)
        ev = []
        dest = action.get("dest")
        if dest is None:
            ev += self._eliminate([pid], "no retreat open [7.72]")
        else:
            dest = tuple(dest)
            # displacement (7.8): friendly full stack - displaced unit must
            # itself retreat; chains resolved as further pendings
            friends = [v for v in s["units"].values()
                       if v["pid"] != pid and (v["col"], v["row"]) == dest
                       and v["side"] == u["side"]]
            if len(friends) >= int(self.game.stacking["max"]):
                disp = friends[0]
                p["units"].append(disp["pid"])
                ev.append({"displaced": disp["slot"], "by": u["slot"]})
            u["col"], u["row"] = dest
            s["retreated_phase"].append(pid)
            ev.append({"retreat": u["slot"], "to": list(dest)})
        p["units"].remove(pid)
        if not p["units"]:
            adv_by, adv_units = p.get("adv_by"), p.get("adv_units", [])
            vacating = p.get("vacating", [])
            s["pending"] = None
            occupied = {(v["col"], v["row"]) for v in s["units"].values()}
            vac = [h for h in vacating if tuple(h) not in occupied]
            if adv_by and vac:
                ev += self._offer_advance(adv_by, adv_units, [], vac, p["battle"])
        return ev

    def _apply_advance(self, side, action):
        s = self.s
        ev = []
        if action.get("unit") is None:
            ev.append({"advance": "declined"})
        else:
            u = self.unit(str(action["unit"]))
            dest = tuple(action["dest"])
            u["col"], u["row"] = dest
            s["advanced"].append(u["pid"])
            self._credit_occupation(side, [dest])
            ev.append({"advance": u["slot"], "to": list(dest)})
        s["pending"] = None
        return ev

    def _apply_exchange_loss(self, side, action):
        s = self.s
        p = s["pending"]
        pids = [str(x) for x in action["units"]]
        ev = self._eliminate(pids, "Ex attacker share [7.6]")
        adv_units = [x for x in p["units"] if x not in pids]
        hexes = p.get("adv_hexes", [])
        s["pending"] = None
        occupied = {(v["col"], v["row"]) for v in s["units"].values()}
        vac = [h for h in hexes if tuple(h) not in occupied]
        if adv_units and vac:
            ev += self._offer_advance(side, adv_units, [], vac, p["battle"])
        return ev

    def _apply_train_retreat(self, side, action):
        s = self.s
        p = s["pending"]
        u = self.unit(p["unit"])
        ev = []
        dest = action.get("dest")
        if dest is None:
            s["dead"].append(u["pid"])
            csp = self.printed(u)
            s["vp"]["Confederate"] += csp
            del s["units"][u["pid"]]
            ev.append({"train_destroyed": u["slot"], "why": "18.23"})
        else:
            u["col"], u["row"] = tuple(dest)
            ev.append({"train_retreat": list(dest), "note": "no Confederate advance [18.11]"})
        s["pending"] = None
        s["train_checked"] = True
        return ev

    # ------------------------------------------------------------ final VP
    def _road_graph(self):
        g = {}
        for skey, f in (self.game.terrain or {}).get("sides", {}).items():
            if not f.get("road"):
                continue
            a, b = skey.split("|")
            pa = (int(a[:2]), int(a[2:])); pb = (int(b[:2]), int(b[2:]))
            g.setdefault(pa, set()).add(pb)
            g.setdefault(pb, set()).add(pa)
        return g

    def _final_scoring(self):
        from collections import deque
        s = self.s
        ev = [{"game_end": self.turns}]
        roads = self._road_graph()
        union_pos = {(u["col"], u["row"]) for u in self._live("Union")}
        csa_pos = {(u["col"], u["row"]) for u in self._live("Confederate")}
        # Confederate LOC (17.31): road chain from an exit hex to the east
        # edge, free of Union UNITS (ZOC irrelevant)
        east = {h for h in roads if h[0] >= 25}
        loc_ok = False
        for start in self.exit_hexes:
            if start not in roads or start in union_pos:
                continue
            seen, q = {start}, deque([start])
            while q:
                cur = q.popleft()
                if cur in east:
                    loc_ok = True
                    break
            # BFS over road graph avoiding Union-occupied hexes
                for nb in roads.get(cur, ()):
                    if nb not in seen and nb not in union_pos:
                        seen.add(nb)
                        q.append(nb)
            if loc_ok:
                break
        ev.append({"csa_loc_road_clear": loc_ok})
        # exit VPs (17.11)
        u_csp = sum(self.printed(self.catalog_unit(p)) for p, sd in s["exited"].items()
                    if sd == "Union")
        c_csp = sum(self.printed(self.catalog_unit(p)) for p, sd in s["exited"].items()
                    if sd == "Confederate")
        s["vp"]["Union"] += u_csp * self.vp_cfg["exit_per_csp"]["Union"]
        if loc_ok:
            s["vp"]["Confederate"] += c_csp * self.vp_cfg["exit_per_csp"]["Confederate"]
        # train (17.11): 10 VP to CSA unless the Train EXITED
        train_exited = any(self.catalog_unit(p)["cls"] == "train"
                           for p in s["exited"])
        if not train_exited:
            s["vp"]["Confederate"] += self.vp_cfg.get("confederate_train_fail", 10)
        # occupation (17.12) via the tracked occ map
        occ_cfg = self.vp_cfg.get("occupation") or {}
        for owner_key, hexes in occ_cfg.items():
            owner = {"union": "Union", "confederate": "Confederate",
                     "either": None}.get(owner_key.lower(), owner_key)
            for hx, pts in hexes.items():
                holder = s["occ"].get(hx)
                if holder and (owner is None or holder == owner):
                    if owner is None or holder == owner:
                        s["vp"][holder] += pts if owner is None else (
                            pts if holder == owner else 0)
        # Union 10-hex path check (17.32): live Union units unable to reach a
        # road hex (<=10 steps, through EZOC fine, never through CSA units)
        # whose road component contains an exit hex count as destroyed
        exit_road = set()
        for start in self.exit_hexes:
            if start not in roads:
                continue
            seen, q = {start}, deque([start])
            while q:
                cur = q.popleft()
                for nb in roads.get(cur, ()):
                    if nb not in seen and nb not in csa_pos:
                        seen.add(nb)
                        q.append(nb)
            exit_road |= seen
        for u in list(self._live("Union")):
            if self.cls(u) == "train":
                continue
            start = (u["col"], u["row"])
            found = start in exit_road
            seen, q = {start}, deque([(start, 0)])
            while q and not found:
                cur, d = q.popleft()
                if d >= 10:
                    continue
                for nb in self.game.neighbors(*cur):
                    if nb in seen or not self.game.on_map(*nb) \
                       or nb in csa_pos or not self._crossable(cur, nb):
                        continue
                    seen.add(nb)
                    if nb in exit_road:
                        found = True
                        break
                    q.append((nb, d + 1))
            if not found:
                csp = self.printed(u)
                s["vp"]["Confederate"] += csp
                ev.append({"cut_off": u["slot"], "csp": csp, "why": "17.32"})
        s["over"] = True
        vps = s["vp"]
        s["winner"] = max(vps, key=lambda k: vps[k]) \
            if vps[self.game.side_order[0]] != vps[self.game.side_order[1]] else "draw"
        ev.append({"final_vp": dict(vps), "winner": s["winner"]})
        return ev

    def catalog_unit(self, pid):
        e = self.catalog[pid]
        return {"slot": e["slot"], "cls": e.get("cls", "infantry")}

    # ------------------------------------------------------------ UI panels
    def legal_moves(self, pid):
        u = self.unit(str(pid))
        if self.s["phase"] != "movement" or u["side"] != self.s["mover"] \
           or u["pid"] in self.s["moved"]:
            return {}
        return self.dests(u)

    def battle_preview(self, side, atk_ids, def_ids, bomb_ids=()):
        atk = [self.unit(str(p)) for p in atk_ids]
        dfd = [self.unit(str(p)) for p in def_ids]
        dhexes = {(d["col"], d["row"]) for d in dfd}
        pair = self._battle_odds(atk, dfd, [str(b) for b in bomb_ids], dhexes)
        return {"odds": f"{pair[0]}-{pair[1]}", "column": self._col_of(pair)}

    def rules_scope(self):
        sc = self.scenario.get("rules_scope", {})
        if self.tier >= 2:
            return {"enforced": sc.get("enforced", []) + sc.get("enforced_tier2", []),
                    "not_enforced": sc.get("umpired", [])}
        return {"enforced": sc.get("enforced", []),
                "not_enforced": sc.get("enforced_tier2", []) + sc.get("umpired", []),
                "banner": f"TIER {self.tier} MODE selected - combat is umpired"}

    def flow(self):
        s = self.s
        due = sorted([{"pid": pid, "slot": self.reserve[pid]["slot"],
                       "side": self.reserve[pid]["side"],
                       "due": d, "entry": self.reserve[pid]["entry"]}
                      for pid, d in s["pool"].items() if d <= s["turn"]],
                     key=lambda e: e["pid"])
        ob = {}
        if self.combat and s["phase"] == "combat" and not self.is_night():
            mine, theirs = self._contacts(s["mover"])
            ob = {"must_attack": sorted(p for p in mine if p not in s["fought"]),
                  "must_be_attacked": sorted(p for p in theirs if p not in s["defended"])}
        return {
            "mode": "bluegray", "turn": s["turn"], "label": self.turn_label(),
            "night": self.is_night(), "phase": s["phase"], "mover": s["mover"],
            "over": s["over"], "winner": s["winner"], "vp": s["vp"],
            "moved": s["moved"], "pending": s["pending"],
            "due_reinforcements": due, "obligations": ob,
            "exited": {p: sd for p, sd in s["exited"].items()},
            "occ": s["occ"],
            "tier": self.tier, "tier_earned": self.tier_earned,
            "rules_scope": self.rules_scope(),
        }
