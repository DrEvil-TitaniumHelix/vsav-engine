"""
strategic.py - The legality gate for strategic (player-turn) games: Afrika
Korps campaign movement, Tier 1 scope.

EVERY action enters through propose()/submit(). propose() returns a verdict
with rulebook-cited reasons; submit() applies legal actions and LOGS EVERY
PROPOSAL — including rejected ones — to an append-only JSONL game log. The
log is self-contained (initial setup + seed + every action) and
engine/verify_game.py replays it independently, re-checking every verdict
and every state hash. Same anti-cheat trinity as gamestate.TacticalGame.

Turn structure (AK rules 3.1-3.5): each game turn = the Axis player moves
all/some/none of his units, then the Allied player does. Combat resolution
(3.2/3.4), supply/reinforcement arrival (3.1/3.3), the Rommel movement
bonus (22.1) and sea movement (23.4) are NOT in this scope — the scenario's
rules_scope declares exactly what is enforced.

Actions:
  {"type":"move", "unit":pid, "dest":[col,row]}
  {"type":"end_phase"}     (current mover is done; 6.1/2.3 stacking check)
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
        if os.path.exists(self.state_path):
            self.s = json.load(open(self.state_path, encoding="utf-8"))
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
        }
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
                 "rng_calls", "units")}
        blob = json.dumps(core, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    # ------------------------------------------------------------ helpers
    def unit(self, pid):
        return self.s["units"][str(pid)]

    def turn_label(self, t=None):
        t = self.s["turn"] if t is None else t
        return self.turn_labels[t - 1] if 0 < t <= len(self.turn_labels) else f"turn {t}"

    def rules_board(self, exclude_pid=None):
        """Gate units as the movement engine's board (markers and reserve
        pieces are not gate units and never block map movement)."""
        return [dict(id=u["pid"], name=u["slot"], side=u["side"],
                     col=u["col"], row=u["row"])
                for u in self.s["units"].values() if u["pid"] != exclude_pid]

    def budget(self, u):
        return self.game.stats(u["slot"])[2]

    def dests(self, u):
        """Legal destinations for a gate unit via the validated spec engine
        (terrain, roads/escarpments 17/18, ZOC 7/8, stacking 6, enemy hexes
        5.4)."""
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
            if u["side"] == side and self.game.unit_class(u["slot"]) not in exempt:
                count[(u["col"], u["row"])] = count.get((u["col"], u["row"]), 0) + 1
        return sorted(h for h, n in count.items() if n > int(st["max"]))

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
        if t != "move":
            return self._v(False, f"unknown action type '{t}'")

        pid = str(action.get("unit"))
        if pid in self.reserve:
            return self._v(False, "reinforcement on the Order of Appearance track — "
                                  "arrivals (3.1/3.3, Time Record Card) are not in "
                                  "this scenario's Tier-1 scope")
        u = self.s["units"].get(pid)
        if not u:
            return self._v(False, "no such unit in the gated scenario")
        if u["side"] != side:
            return self._v(False, f"unit belongs to {u['side']} — you may move "
                                  f"your units only [3.1/3.3]")
        if self.game.unit_class(u["slot"]) == "markers":
            return self._v(False, "status marker, not a playing piece")
        if pid in self.s["moved"]:
            return self._v(False, "unit has already moved this player turn — "
                                  "movement factors are not transferable nor "
                                  "accumulated [5.2, 5.5]")
        dest = tuple(action.get("dest") or ())
        if len(dest) != 2:
            return self._v(False, "dest [col,row] required")
        dd = self.dests(u)
        if dest not in dd:
            ma = self.budget(u)
            return self._v(False, f"not a legal destination for this unit "
                                  f"(MF {ma}) — movement 5.2/5.4, stacking 6.1, "
                                  f"ZOC 7.1/8.1/8.3, roads 17, escarpments 18")
        v = self._v(True)
        v["cost"] = dd[dest]
        return v

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
        if action["type"] == "move":
            u = self.unit(action["unit"])
            old = [u["col"], u["row"]]
            u["col"], u["row"] = action["dest"]
            s["moved"][u["pid"]] = {"from": old, "cost": verdict.get("cost")}
            return {"from": old, "to": [u["col"], u["row"]],
                    "cost": verdict.get("cost")}
        # end_phase
        other = self.game.enemy(side)
        if side == self.first_player:
            s["mover"] = other
            s["moved"] = {}
            return {"note": f"{side} player turn over — {other} moves now [3.3]"}
        s["moved"] = {}
        s["turn"] += 1
        s["mover"] = self.first_player
        if s["turn"] > self.turns:
            s["over"] = True
            return {"note": "GAME OVER — final turn complete. Victory conditions "
                            "(4.1/4.2) require combat resolution: not in Tier-1 "
                            "scope, no winner adjudicated.",
                    "turn": s["turn"], "over": True}
        return {"note": f"game turn complete — {self.turn_label()} begins, "
                        f"{self.first_player} moves first [3.5]",
                "turn": s["turn"], "over": False}

    # ------------------------------------------------------------ queries (UI/AI)
    def legal_moves(self, pid):
        """For the UI: every legal destination with cost, or the reason the
        unit cannot act."""
        pid = str(pid)
        if pid in self.reserve or pid not in self.s["units"]:
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
                    rules_scope=self.scenario.get("rules_scope"))
