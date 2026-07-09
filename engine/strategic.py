"""
strategic.py - The legality gate for strategic (player-turn) games: Afrika
Korps campaign movement, Tier 1 scope.

EVERY action enters through propose()/submit(). propose() returns a verdict
with rulebook-cited reasons; submit() applies legal actions and LOGS EVERY
PROPOSAL — including rejected ones — to an append-only JSONL game log. The
log is self-contained (initial setup + seed + every action) and
engine/verify_game.py replays it independently, re-checking every verdict,
every die roll and every state hash. Same anti-cheat trinity as
gamestate.TacticalGame.

Turn structure (AK rules 3.1-3.5): each game turn = the Axis player turn
(supply roll/landing and reinforcement placement, then movement), then the
Allied player turn (same shape, no roll). Combat resolution (3.2/3.4),
replacements (20), substitutes (21) and isolation (24) are NOT in this
scope — the scenario's rules_scope declares exactly what is enforced.

Actions:
  {"type":"move", "unit":pid, "dest":[col,row],
   "path":[[c,r],...]?, "rommel_bonus":1|2?}
      path: optional explicit route, validated step by step (required for
      the mover's hq unit if bonus claims will follow, and for any move
      claiming a bonus)
  {"type":"rommel_extend", "unit":pid, "path":[[c,r],...]}
      up to two extra hexes after a completed path move, escorted by the
      hq unit (22.1 + module tournament clarification)
  {"type":"roll_supply"}                     Axis Supply Table roll (12.2)
  {"type":"land_supply", "port":[c,r]}       place an arriving supply unit
  {"type":"land_reinforcement", "unit":pid, "port":[c,r]}   (19.1-19.7)
  {"type":"embark", "unit":pid}              put out to sea (23.4/23.44)
  {"type":"debark", "unit":pid, "port":[c,r]}  land from sea (23.4/23.42-44)
  {"type":"end_phase"}     (current mover is done; 6.1/2.3 stacking check,
                            12.4 supply forfeit, 23.42 at-sea elimination)
"""
import hashlib
import json
import os
import random


class StrategicGame:
    def __init__(self, game, scenario_path, live_dir, seed=None):
        self.game = game                      # gamespec.Game
        self.scenario = json.load(open(scenario_path, encoding="utf-8"))
        gkey = os.path.basename(os.path.normpath(game.dir))
        self.state_path = os.path.join(live_dir, f"game_{gkey}.state.json")
        self.log_path = os.path.join(live_dir, f"game_{gkey}.log.jsonl")
        cfg = self.scenario["game"]
        self.turns = int(cfg["turns"])
        self.first_player = cfg["first_player"]
        self.turn_labels = cfg.get("turn_labels", [])
        self.reserve = {u["id"]: u for u in self.scenario.get("reserve", [])}
        self.schedule = {u["id"]: u for u in self.scenario.get("reserve", [])
                         if "due" in u}
        self.supply_table = (self.scenario.get("supply_table") or {}).get("windows", [])
        self.supply_max = self.scenario.get("supply_max_on_board", {})
        p = (game.spec.get("ports") or {}).get("list", [])
        self.ports = {tuple(e["hex"]): e for e in p}
        if os.path.exists(self.state_path):
            self.s = json.load(open(self.state_path, encoding="utf-8"))
            if "pool" not in self.s:      # pre-arrivals state file: reset
                self.new_game(seed)
        else:
            self.new_game(seed)

    # ------------------------------------------------------------ lifecycle
    def new_game(self, seed=None):
        seed = seed if seed is not None else random.SystemRandom().randrange(10 ** 9)
        units = {}
        for u in self.scenario["units"]:
            units[u["id"]] = {
                "pid": u["id"], "slot": u["slot"], "side": u["side"],
                "col": u["hex"][0], "row": u["hex"][1],
            }
        self.s = {
            "seed": seed, "rng_calls": 0, "n": 0,
            "turn": 1, "phase": "movement", "mover": self.first_player,
            "moved": {}, "over": False, "winner": None,
            "units": units,
            # arrivals / sea / bonus state (all replayed by the verifier)
            "pool": {pid: e["due"] for pid, e in self.schedule.items()},
            "supply_pool": dict(self.scenario.get("supply_pool", {})),
            "supply_rolled": False, "supply_pending": False,
            "allied_supply_done": False,
            "paths": {}, "bonus": {}, "landed_sea": [],
            "ports": [],
        }
        self.s["ports"] = self._controlled_ports(self.first_player)
        if os.path.exists(self.log_path):
            os.remove(self.log_path)
        self._log({"event": "init", "mode": "strategic",
                   "scenario": self.scenario["name"],
                   "rules_scope": self.scenario.get("rules_scope"),
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
                ("turn", "phase", "mover", "moved", "over", "winner",
                 "rng_calls", "units", "pool", "supply_pool", "supply_rolled",
                 "supply_pending", "allied_supply_done", "paths", "bonus",
                 "landed_sea", "ports")}
        blob = json.dumps(core, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    # ------------------------------------------------------------ dice
    def _rng(self):
        r = random.Random(self.s["seed"])
        for _ in range(self.s["rng_calls"]):
            r.random()
        return r

    def roll_die(self):
        """Engine-owned d6: seeded, counted, replayable (spec #11)."""
        r = self._rng()
        v = 1 + int(r.random() * 6)
        self.s["rng_calls"] += 1
        return v

    # ------------------------------------------------------------ helpers
    def unit(self, pid):
        return self.s["units"][str(pid)]

    def turn_label(self, t=None):
        t = self.s["turn"] if t is None else t
        return self.turn_labels[t - 1] if 0 < t <= len(self.turn_labels) else f"turn {t}"

    def on_map(self, u):
        return u.get("loc") != "at_sea"

    def rules_board(self, exclude_pid=None):
        """Gate units as the movement engine's board (markers, reserve
        pieces and units at sea are not on the map and never block)."""
        return [dict(id=u["pid"], name=u["slot"], side=u["side"],
                     col=u["col"], row=u["row"])
                for u in self.s["units"].values()
                if u["pid"] != exclude_pid and self.on_map(u)]

    def budget(self, u):
        return self.game.stats(u["slot"])[2]

    def dests(self, u):
        """Legal destinations for a gate unit via the validated spec engine
        (terrain, roads/escarpments 17/18, ZOC 7/8 incl. fortress immunity
        19.5, stacking 6, enemy hexes 5.4)."""
        me = dict(id=u["pid"], name=u["slot"], side=u["side"],
                  col=u["col"], row=u["row"])
        return self.game.legal_destinations_t(
            me, self.budget(u), self.rules_board(exclude_pid=u["pid"]))

    def overstacked_hexes(self, side):
        """Hexes where `side` exceeds the stacking limit (6.1; exempt
        classes stack above it)."""
        st = self.game.stacking
        if not st:
            return []
        exempt = set(st.get("exempt_classes", []))
        count = {}
        for u in self.s["units"].values():
            if u["side"] == side and self.on_map(u) \
               and self.game.unit_class(u["slot"]) not in exempt:
                count[(u["col"], u["row"])] = count.get((u["col"], u["row"]), 0) + 1
        return sorted(h for h, n in count.items() if n > int(st["max"]))

    # ------------------------------------------------------------ ports & supply
    def _controlled_ports(self, side):
        """Ports usable by `side` and controlled at this snapshot (4.3:
        occupied by a combat, supply or Rommel unit; a home base must also
        be free of enemy ZOC — fortress ports are ZOC-immune per 19.5)."""
        board = self.rules_board()
        ezoc = self.game.zoc_hexes(board, self.game.enemy(side))
        out = []
        for hx, port in self.ports.items():
            if side not in port["usable_by"]:
                continue
            occ = any(u["side"] == side and self.on_map(u)
                      and (u["col"], u["row"]) == hx
                      and self.game.unit_class(u["slot"]) != "markers"
                      for u in self.s["units"].values())
            if not occ:
                continue
            if self.game.hex_terrain(*hx) == "homebase" and hx in ezoc:
                continue
            out.append(list(hx))
        return sorted(out)

    def _own_supply_on_board(self, side):
        return sum(1 for u in self.s["units"].values()
                   if u["side"] == side and self.on_map(u)
                   and self.game.unit_class(u["slot"]) == "supply"
                   and "Captured" not in u["slot"])

    def _supply_sunk_rolls(self, turn):
        for w in self.supply_table:
            if w["turns"][0] <= turn <= w["turns"][1]:
                return set(w["sunk"])
        return set()

    def _port_ok(self, side, dest):
        """dest is a controlled (start-of-turn snapshot), side-usable port."""
        return list(dest) in self.s["ports"] and tuple(dest) in self.ports \
            and side in self.ports[tuple(dest)]["usable_by"]

    # ------------------------------------------------------------ Rommel 22.1
    def _hq_unit(self, side):
        for u in self.s["units"].values():
            if u["side"] == side and self.game.unit_class(u["slot"]) == "hq":
                return u
        return None

    @staticmethod
    def _coseg(a, b, n):
        """A directed contiguous segment of n edges (n+1 hexes) present in
        both paths a and b — 'moves with that unit for n hexes' (22.1)."""
        if n <= 0:
            return True
        a = [tuple(h) for h in a]
        b = [tuple(h) for h in b]
        for i in range(len(a) - n):
            seg = a[i:i + n + 1]
            for j in range(len(b) - n):
                if b[j:j + n + 1] == seg:
                    return True
        return False

    def _check_path_move(self, u, path, bonus):
        """Validate an explicit path (optionally with a claimed Rommel
        bonus) under the full movement rules. Returns a verdict dict."""
        if not path or len(path) < 2:
            return self._v(False, "path must list start hex and at least one step")
        if tuple(path[0]) != (u["col"], u["row"]):
            return self._v(False, "path must start at the unit's current hex")
        if bonus:
            if bonus not in (1, 2):
                return self._v(False, "rommel_bonus must be 1 or 2 [22.1]")
            hq = self._hq_unit(u["side"])
            if not hq:
                return self._v(False, "no headquarters unit on this side — "
                                      "the bonus is Rommel's [22.1]")
            if u["pid"] == hq["pid"]:
                return self._v(False, "Rommel provides the bonus to OTHER "
                                      "friendly units [22.1]")
            if u["pid"] in self.s["bonus"]:
                return self._v(False, "Rommel can help each unit only once "
                                      "per turn [22.1]")
            rpath = self.s["paths"].get(hq["pid"])
            if not rpath:
                return self._v(False, "claiming the Rommel bonus requires "
                                      "Rommel to have moved this turn with an "
                                      "explicit path — submit his path move "
                                      "first [22.1 + clarification: escort "
                                      "order inside the turn is free, the "
                                      "gate validates against his route]")
            if not self._coseg(rpath, path, bonus):
                return self._v(False, f"Rommel's route this turn does not move "
                                      f"with this unit for {bonus} hex(es) — no "
                                      f"shared {bonus}-hex path segment [22.1]")
        me = dict(id=u["pid"], name=u["slot"], side=u["side"],
                  col=u["col"], row=u["row"])
        ma = self.budget(u) + (bonus or 0)
        ok, why = self.game.trace_path(
            me, ma, self.rules_board(exclude_pid=u["pid"]),
            [tuple(h) for h in path])
        if not ok:
            return self._v(False, f"illegal path: {why}")
        v = self._v(True)
        v["path_check"] = why
        return v

    # ------------------------------------------------------------ verdicts
    def _v(self, ok, *reasons):
        return {"legal": ok, "reasons": list(reasons)}

    def propose(self, side, action):
        t = action.get("type")
        if self.s["over"]:
            return self._v(False, "game is over")
        if side not in self.game.side_order:
            return self._v(False, f"unknown side '{side}'")
        if side != self.s["mover"]:
            return self._v(False, f"it is the {self.s['mover']} player turn — "
                                  f"no {side} movement is allowed [3.1/3.3]")
        if t == "end_phase":
            over = self.overstacked_hexes(side)
            if over:
                names = ", ".join(self.game.grid.display_name(*h) for h in over)
                return self._v(False, f"stacking limit exceeded at {names} — limits "
                                      "must be adhered to at the conclusion of each "
                                      "player's movement [2.3, 6.1, 6.3]")
            return self._v(True)
        if t == "roll_supply":
            return self._propose_roll_supply(side)
        if t == "land_supply":
            return self._propose_land_supply(side, action)
        if t == "land_reinforcement":
            return self._propose_land_reinforcement(side, action)
        if t == "embark":
            return self._propose_embark(side, action)
        if t == "debark":
            return self._propose_debark(side, action)
        if t == "rommel_extend":
            return self._propose_extend(side, action)
        if t != "move":
            return self._v(False, f"unknown action type '{t}'")
        return self._propose_move(side, action)

    def _gate_unit(self, side, action, allow_at_sea=False):
        """Common unit resolution for unit-bearing actions. Returns
        (unit, verdict|None)."""
        pid = str(action.get("unit"))
        if pid in self.schedule and pid not in self.s["units"]:
            e = self.schedule[pid]
            return None, self._v(False,
                f"'{e['slot']}' is a scheduled reinforcement (due "
                f"{self.turn_label(e['due'])}) — land it at a controlled "
                f"port first [19.1/19.2]")
        if pid in self.reserve and pid not in self.s["units"]:
            return None, self._v(False,
                "reserve piece (substitute/captured-supply/marker) — "
                "outside this scenario's Tier-1 scope [20/21/15]")
        u = self.s["units"].get(pid)
        if not u:
            return None, self._v(False, "no such unit in the gated scenario")
        if u["side"] != side:
            return None, self._v(False, f"unit belongs to {u['side']} — you may "
                                        f"move your units only [3.1/3.3]")
        if self.game.unit_class(u["slot"]) == "markers":
            return None, self._v(False, "status marker, not a playing piece")
        if not allow_at_sea and not self.on_map(u):
            return None, self._v(False, "unit is at sea — it may only land at a "
                                        "controlled port on this player turn, or "
                                        "be eliminated at its end [23.42/23.44]")
        return u, None

    def _propose_move(self, side, action):
        u, err = self._gate_unit(side, action)
        if err:
            return err
        if u["pid"] in self.s["moved"]:
            return self._v(False, "unit has already moved this player turn — "
                                  "movement factors are not transferable nor "
                                  "accumulated [5.2, 5.5]")
        dest = tuple(action.get("dest") or ())
        if len(dest) != 2:
            return self._v(False, "dest [col,row] required")
        path = action.get("path")
        bonus = action.get("rommel_bonus")
        if bonus and not path:
            return self._v(False, "a move claiming the Rommel bonus must carry "
                                  "an explicit path — the escort is a shared "
                                  "route, not a destination [22.1]")
        if path:
            if tuple(path[-1]) != dest:
                return self._v(False, "path must end at dest")
            v = self._check_path_move(u, path, bonus)
            if v["legal"]:
                v["cost"] = len(path) - 1
            return v
        dd = self.dests(u)
        if dest not in dd:
            ma = self.budget(u)
            return self._v(False, f"not a legal destination for this unit "
                                  f"(MF {ma}) — movement 5.2/5.4, stacking 6.1, "
                                  f"ZOC 7.1/8.1/8.3, roads 17, escarpments 18")
        v = self._v(True)
        v["cost"] = dd[dest]
        return v

    def _propose_extend(self, side, action):
        u, err = self._gate_unit(side, action)
        if err:
            return err
        prior = self.s["paths"].get(u["pid"])
        if u["pid"] not in self.s["moved"] or not prior:
            return self._v(False, "the Rommel extension continues a completed "
                                  "path move — this unit has no recorded path "
                                  "this turn (submit its move with an explicit "
                                  "path first) [22.1 + clarification]")
        ext = action.get("path") or []
        if len(ext) < 2 or tuple(ext[0]) != (u["col"], u["row"]):
            return self._v(False, "extension path must start at the unit's "
                                  "current hex and add 1-2 hexes")
        n = len(ext) - 1
        if n > 2:
            return self._v(False, "the Rommel bonus is two hexes at most [22.1]")
        combined = [list(h) for h in prior] + [list(h) for h in ext[1:]]
        fake = dict(u)
        fake["col"], fake["row"] = prior[0][0], prior[0][1]
        v = self._check_path_move(fake, combined, n)
        if v["legal"]:
            v["cost"] = n
            v["combined"] = combined
        return v

    def _no_moves_yet(self, what, cite):
        if self.s["moved"]:
            return self._v(False, f"{what} must precede movement — units have "
                                  f"already moved this player turn [{cite}]")
        return None

    def _propose_roll_supply(self, side):
        if side != "Axis":
            return self._v(False, "only the Axis player rolls on the Supply "
                                  "Table — the Allied player is due one supply "
                                  "unit per turn without a roll [12.1/12.2]")
        err = self._no_moves_yet("the supply roll", "3.1")
        if err:
            return err
        if self.s["supply_rolled"]:
            return self._v(False, "the Axis player is allowed to roll once per "
                                  "game turn [12.2]")
        if not self.s["ports"]:
            return self._v(False, "no controlled port at which to land supply — "
                                  "no roll (the Axis player cannot roll on the "
                                  "first game turn) [12.2, 4.3]")
        return self._v(True)

    def _propose_land_supply(self, side, action):
        err = self._no_moves_yet("supply landing", "3.1/3.3")
        if err:
            return err
        port = tuple(action.get("port") or ())
        if not self._port_ok(side, port):
            return self._v(False, "supply lands at a controlled port — Tobruch "
                                  "or your own home base, controlled at the "
                                  "start of your turn [12.4, 4.3, 19.7]")
        mx = self.supply_max.get(side)
        if mx is not None and self._own_supply_on_board(side) >= int(mx):
            return self._v(False, f"never more than {mx} of your own supply "
                                  f"units on board [12.1/12.2]")
        if not self.s["supply_pool"].get(side):
            return self._v(False, "no own supply counters left off board [2.4]")
        if side == "Axis":
            if not self.s["supply_pending"]:
                return self._v(False, "no Axis supply unit has arrived this turn "
                                      "— roll on the Supply Table first [12.2, 3.1]")
        else:
            if self.s["allied_supply_done"]:
                return self._v(False, "the Allied player is due ONE supply unit "
                                      "per turn [12.1]")
        return self._v(True)

    def _propose_land_reinforcement(self, side, action):
        err = self._no_moves_yet("reinforcement placement", "3.1/3.3")
        if err:
            return err
        pid = str(action.get("unit"))
        e = self.schedule.get(pid)
        if not e:
            return self._v(False, "not a scheduled reinforcement [19.1, Order "
                                  "of Appearance]")
        if pid not in self.s["pool"]:
            return self._v(False, "this reinforcement has already entered play "
                                  "[19.1]")
        if e["side"] != side:
            return self._v(False, f"'{e['slot']}' is a {e['side']} reinforcement "
                                  f"— reinforcements enter only during their own "
                                  f"player turn [19.6]")
        if self.s["turn"] < e["due"]:
            return self._v(False, f"'{e['slot']}' is due {self.turn_label(e['due'])} "
                                  f"— the Order of Appearance states the EARLIEST "
                                  f"time it can enter play [19.1]")
        port = tuple(action.get("port") or ())
        if not self._port_ok(side, port):
            return self._v(False, "reinforcements enter at Tobruch or your own "
                                  "home base, controlled by friendly forces at "
                                  "the start of the player turn [19.2, 19.7, 4.3]")
        return self._v(True)

    def _propose_embark(self, side, action):
        u, err = self._gate_unit(side, action)
        if err:
            return err
        if u["pid"] in self.s["landed_sea"]:
            return self._v(False, "a unit which lands at a port may not move "
                                  "out to sea again in the same turn [23.42, 23.41]")
        hx = (u["col"], u["row"])
        port = self.ports.get(hx)
        if not port or side not in port["usable_by"]:
            if self.game.hex_terrain(*hx) == "fortress":
                return self._v(False, "sea movement in and out of Bengasi is "
                                      "not allowed [23.3]")
            return self._v(False, "sea movement runs between Tobruch and your "
                                  "own controlled home base — the unit must be "
                                  "on such a port hex [23.4, 23.5]")
        if list(hx) not in self.s["ports"]:
            # not controlled at start of turn: still allowed OUT unless the
            # port is in enemy ZOC at embarkation (23.44)
            board = self.rules_board()
            ezoc = self.game.zoc_hexes(board, self.game.enemy(side))
            if hx in ezoc:
                return self._v(False, "you may move out of a port you did not "
                                      "control at the start of your turn only "
                                      "if it is not in an enemy ZOC at the time "
                                      "of embarkation [23.44]")
        return self._v(True)

    def _propose_debark(self, side, action):
        u, err = self._gate_unit(side, action, allow_at_sea=True)
        if err:
            return err
        if self.on_map(u):
            return self._v(False, "unit is not at sea")
        if u.get("embark_turn") == self.s["turn"]:
            return self._v(False, "sea movement lands in the FOLLOWING friendly "
                                  "player turn, not the turn of embarkation [23.4]")
        err = self._no_moves_yet("landing from sea", "3.1/3.3, 23.4")
        if err:
            return err
        port = tuple(action.get("port") or ())
        if not self._port_ok(side, port):
            return self._v(False, "to use sea movement into a port you must "
                                  "control the port at the beginning of your "
                                  "turn — Tobruch or your own home base "
                                  "[23.44, 23.5, 4.3]")
        return self._v(True)

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

    def _apply(self, side, action, verdict):
        s = self.s
        t = action["type"]
        if t == "move":
            u = self.unit(action["unit"])
            old = [u["col"], u["row"]]
            u["col"], u["row"] = action["dest"]
            s["moved"][u["pid"]] = {"from": old, "cost": verdict.get("cost")}
            if action.get("path"):
                s["paths"][u["pid"]] = [list(h) for h in action["path"]]
            if action.get("rommel_bonus"):
                s["bonus"][u["pid"]] = int(action["rommel_bonus"])
            return {"from": old, "to": [u["col"], u["row"]],
                    "cost": verdict.get("cost")}
        if t == "rommel_extend":
            u = self.unit(action["unit"])
            old = [u["col"], u["row"]]
            comb = verdict["combined"]
            u["col"], u["row"] = comb[-1]
            s["paths"][u["pid"]] = comb
            s["bonus"][u["pid"]] = int(verdict["cost"])
            s["moved"][u["pid"]]["bonus"] = int(verdict["cost"])
            return {"from": old, "to": [u["col"], u["row"]],
                    "bonus_hexes": verdict["cost"],
                    "note": "Rommel escort extension [22.1]"}
        if t == "roll_supply":
            roll = self.roll_die()
            sunk = self._supply_sunk_rolls(s["turn"])
            lost = roll in sunk
            s["supply_rolled"] = True
            s["supply_pending"] = not lost
            return {"roll": roll, "sunk_on": sorted(sunk),
                    "result": "Sunk — supplies lost [12.2]" if lost else
                              "supply unit arrives — land it at a controlled "
                              "port this turn or forfeit [12.2, 12.4]"}
        if t == "land_supply":
            pid = s["supply_pool"][side].pop(0)
            slot = self.reserve[pid]["slot"]
            s["units"][pid] = {"pid": pid, "slot": slot, "side": side,
                               "col": action["port"][0], "row": action["port"][1]}
            if side == "Axis":
                s["supply_pending"] = False
            else:
                s["allied_supply_done"] = True
            return {"placed": pid, "slot": slot, "at": list(action["port"]),
                    "note": "initial placement does not count against movement; "
                            "it may move this turn [13.1]"}
        if t == "land_reinforcement":
            pid = str(action["unit"])
            e = self.schedule[pid]
            del s["pool"][pid]
            s["units"][pid] = {"pid": pid, "slot": e["slot"], "side": side,
                               "col": action["port"][0], "row": action["port"][1]}
            return {"placed": pid, "slot": e["slot"], "at": list(action["port"]),
                    "due": self.turn_label(e["due"]),
                    "note": "no movement penalty for entering at a controlled "
                            "port; it may move and fight this turn [19.2]"}
        if t == "embark":
            u = self.unit(action["unit"])
            old = [u["col"], u["row"]]
            u["loc"] = "at_sea"
            u["embark_turn"] = s["turn"]
            u["col"] = u["row"] = None
            s["moved"][u["pid"]] = {"from": old, "to_sea": True}
            return {"from": old, "at_sea": True,
                    "note": "must land at Tobruch or the home base on the next "
                            "friendly player turn or be eliminated [23.4, 23.42]"}
        if t == "debark":
            u = self.unit(action["unit"])
            u.pop("loc", None)
            u.pop("embark_turn", None)
            u["col"], u["row"] = action["port"]
            s["landed_sea"].append(u["pid"])
            return {"landed": u["pid"], "at": list(action["port"]),
                    "note": "may move inland this turn; may not go back out "
                            "to sea [23.4, 23.42]"}
        # end_phase
        notes = []
        if side == "Axis" and s["supply_pending"]:
            s["supply_pending"] = False
            notes.append("arrived Axis supply unit was not landed — forfeited; "
                         "supply may not accumulate off board [12.4]")
        lost_at_sea = [u for u in s["units"].values()
                       if u["side"] == side and not self.on_map(u)
                       and u.get("embark_turn", s["turn"]) < s["turn"]]
        for u in lost_at_sea:
            del s["units"][u["pid"]]
            notes.append(f"'{u['slot']}' failed to return to a port on the turn "
                         f"following its removal from the board — ELIMINATED [23.42]")
        s["moved"] = {}
        s["paths"] = {}
        s["bonus"] = {}
        s["landed_sea"] = []
        other = self.game.enemy(side)
        if side == self.first_player:
            s["mover"] = other
            s["allied_supply_done"] = False
            s["ports"] = self._controlled_ports(other)
            return {"note": f"{side} player turn over — {other} moves now [3.3]",
                    "events": notes}
        s["turn"] += 1
        s["mover"] = self.first_player
        s["supply_rolled"] = False
        s["ports"] = self._controlled_ports(self.first_player)
        if s["turn"] > self.turns:
            s["over"] = True
            unlanded = sorted(self.schedule[pid]["slot"] for pid in s["pool"])
            s["pool"] = {}
            if unlanded:
                notes.append("reinforcements not in play by the last October "
                             "1942 turn are eliminated [19.8]: "
                             + ", ".join(unlanded))
            return {"note": "GAME OVER — final turn complete. Victory conditions "
                            "(4.1/4.2) require combat resolution: not in Tier-1 "
                            "scope, no winner adjudicated.",
                    "turn": s["turn"], "over": True, "events": notes}
        return {"note": f"game turn complete — {self.turn_label()} begins, "
                        f"{self.first_player} moves first [3.5]",
                "turn": s["turn"], "over": False, "events": notes}

    # ------------------------------------------------------------ queries (UI/AI)
    def legal_moves(self, pid):
        """For the UI: every legal destination with cost, or the reason the
        unit cannot act."""
        pid = str(pid)
        if pid not in self.s["units"]:
            side = self.s["mover"]
        else:
            side = self.s["units"][pid]["side"]
        chk = self.propose(side, {"type": "move", "unit": pid, "dest": [-99, -99]})
        # a unit that fails for any reason OTHER than the fake dest can't act
        blocked = chk["reasons"] and "legal destination" not in chk["reasons"][0] \
            and "dest [col,row] required" not in chk["reasons"][0]
        if blocked:
            return {"can_act": False, "reasons": chk["reasons"], "dests": []}
        u = self.s["units"][pid]
        out = {"can_act": True, "reasons": [], "budget": self.budget(u), "dests": []}
        for (c, r), cost in sorted(self.dests(u).items()):
            x, y = self.game.grid.hex_to_pixel(c, r)
            out["dests"].append(dict(
                col=c, row=r, x=x, y=y, cost=round(cost, 1),
                hexnum=self.game.grid.hexnum(c, r),
                terrain=self.game.hex_terrain(c, r)))
        return out

    def arrivals_panel(self):
        """Everything the mover can place/roll right now (UI helper)."""
        s = self.s
        side = s["mover"]
        due = [dict(pid=pid, slot=self.schedule[pid]["slot"],
                    due=self.turn_label(self.schedule[pid]["due"]))
               for pid, d in sorted(s["pool"].items())
               if self.schedule[pid]["side"] == side and d <= s["turn"]]
        at_sea = [dict(pid=u["pid"], slot=u["slot"],
                       must_land=u.get("embark_turn", s["turn"]) < s["turn"])
                  for u in s["units"].values()
                  if u["side"] == side and not self.on_map(u)]
        ports = [dict(hex=h, name=self.ports[tuple(h)]["name"])
                 for h in s["ports"]]
        supply = dict(
            on_board=self._own_supply_on_board(side),
            max=self.supply_max.get(side),
            pool=len(s["supply_pool"].get(side, [])),
            can_roll=(side == "Axis" and not s["supply_rolled"]
                      and bool(s["ports"]) and not s["moved"]),
            pending=(s["supply_pending"] if side == "Axis"
                     else not s["allied_supply_done"]),
            sunk_on=sorted(self._supply_sunk_rolls(s["turn"])))
        return dict(due=due, at_sea=at_sea, ports=ports, supply=supply,
                    placements_open=not s["moved"])

    def flow(self):
        s = self.s
        return dict(turn=s["turn"], turns=self.turns,
                    turn_label=self.turn_label(),
                    phase=s["phase"], mover=s["mover"],
                    moved=len(s["moved"]), over=s["over"], winner=s["winner"],
                    overstacked=[self.game.grid.display_name(*h)
                                 for h in self.overstacked_hexes(s["mover"])],
                    seed=s["seed"], n=s["n"],
                    first_player=self.first_player,
                    scenario=self.scenario["name"],
                    rules_scope=self.scenario.get("rules_scope"),
                    arrivals=self.arrivals_panel())
