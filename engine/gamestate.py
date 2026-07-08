"""
gamestate.py - The legality gate: Tobruk Scenario One turn flow, movement and
fire legality, damage state, victory points, and the append-only audit log.

EVERY action by EITHER player (human or AI) enters through propose() /
submit(). propose() returns a verdict with rulebook-cited reasons; submit()
applies legal actions and LOGS EVERY PROPOSAL — including rejected ones —
to an append-only JSONL game log. The log is self-contained: initial setup +
seed + every action; engine/verify_game.py replays it independently and
re-checks every verdict, every die roll and every state hash. The AI cannot
cheat because the AI never adjudicates: it proposes, this gate disposes.

Turn structure (rulebook p.4 I.B):
  each turn = MOVEMENT SEGMENT (first player moves all/some/none of his
  units, then second player) then COMBAT SEGMENT (SECOND player fires one
  unit's armament at one target, then first player, alternating; a player
  may finish/pass; when both are done the turn ends).

Actions:
  {"type":"move",   "unit":pid, "dest":[col,row], "facing":0-5}
  {"type":"reverse","unit":pid, "dest":[col,row], "facing":0-5}
  {"type":"pivot",  "unit":pid, "facing":0-5}
  {"type":"end_movement"}                (current mover is done)
  {"type":"fire",   "unit":pid, "target":pid}
  {"type":"pass_fire"}                   (done firing this combat segment)
"""
import hashlib
import json
import os
import random
from collections import deque

import combat as combat_mod

REL_ARCS = {0: "front", 1: "flank", 2: "flank", 3: "rear", 4: "flank", 5: "flank"}
REAR_RELS = (2, 3, 4)   # the three rear-facing hexsides (p.4 I.C.4)


class TacticalGame:
    def __init__(self, game, scenario_path, live_dir, seed=None):
        self.game = game                      # gamespec.Game
        self.cd = combat_mod.CombatData(game.dir)
        self.scenario = json.load(open(scenario_path, encoding="utf-8"))
        gkey = os.path.basename(os.path.normpath(game.dir))
        self.state_path = os.path.join(live_dir, f"game_{gkey}.state.json")
        self.log_path = os.path.join(live_dir, f"game_{gkey}.log.jsonl")
        cfg = self.scenario["game"]
        self.turns = int(cfg["turns"])
        self.first_player = cfg["first_player"]
        self.combat_first = cfg["combat_first_fire"]
        self.bounds = cfg["bounds"]
        self.entry_moved = bool(cfg.get("entry_moved"))
        if os.path.exists(self.state_path):
            self.s = json.load(open(self.state_path, encoding="utf-8"))
        else:
            self.new_game(seed)

    # ------------------------------------------------------------ lifecycle
    def new_game(self, seed=None):
        seed = seed if seed is not None else random.SystemRandom().randrange(10 ** 9)
        units = {}
        pid = 1000000000001                    # make_save.py pid order = scenario order
        for u in self.scenario["units"]:
            key = str(pid)
            afv = None
            for k, t in self.cd.afv_types.items():
                if t["label"].split()[-1].strip("'\"") in u["slot"] or \
                   u["slot"].split()[0] in t["label"]:
                    afv = k
            # explicit mapping beats fuzzy: scenario slot -> afv type
            afv = {"Stuart Mk.III": "stuart", "M13/40": "m13_40"}.get(u["slot"], afv)
            units[key] = {
                "pid": key, "slot": u["slot"], "afv": afv, "side": u["side"],
                "col": u["hex"][0], "row": u["hex"][1], "facing": u.get("facing", 0),
                "K": False, "M": False, "F": False,
            }
            pid += 1
        self.s = {
            "seed": seed, "rng_calls": 0, "n": 0,
            "turn": 1, "segment": "movement", "mover": self.first_player,
            "movement_done": [], "initiative": None, "fire_done": [],
            "moved": {}, "pivoted": {}, "fired": {},        # pid -> info (this turn)
            "acquired": {},                                   # pid -> target pid (from last turn)
            "fired_pairs": [], "over": False, "winner": None,
            "units": units,
        }
        if os.path.exists(self.log_path):
            os.remove(self.log_path)
        self._log({"event": "init", "scenario": self.scenario["name"],
                   "rules_scope": self.scenario.get("rules_scope"),
                   "seed": seed, "turns": self.turns,
                   "first_player": self.first_player,
                   "combat_first_fire": self.combat_first,
                   "bounds": self.bounds,
                   "units": [dict(pid=u["pid"], slot=u["slot"], side=u["side"],
                                  hex=[u["col"], u["row"]], facing=u["facing"],
                                  afv=u["afv"], ma=self.cd.afv_types[u["afv"]]["ma"])
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
                ("turn", "segment", "mover", "movement_done", "initiative",
                 "fire_done", "moved", "fired", "acquired", "fired_pairs",
                 "over", "winner", "rng_calls", "units")}
        blob = json.dumps(core, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    # ------------------------------------------------------------ dice
    def _rng(self):
        r = random.Random(self.s["seed"])
        for _ in range(self.s["rng_calls"]):
            r.random()
        return r

    def roll(self, n_dice):
        """Roll dice by advancing the seeded stream; returns list of 1..6."""
        r = self._rng()
        out = []
        for _ in range(n_dice):
            out.append(1 + int(r.random() * 6))
            self.s["rng_calls"] += 1
        return out

    # ------------------------------------------------------------ geometry
    def xy(self, u):
        return self.game.grid.hex_to_pixel(u["col"], u["row"])

    def in_bounds(self, c, r):
        (c0, c1), (r0, r1) = self.bounds["cols"], self.bounds["rows"]
        return c0 <= c <= c1 and r0 <= r <= r1

    def facing_of_step(self, a, b):
        """Facing index a unit has after stepping from hex a into adjacent hex b."""
        sector, _ = combat_mod.bearing_sector(
            self.game.grid.hex_to_pixel(*a), self.game.grid.hex_to_pixel(*b))
        return sector

    def bfs(self, start, budget):
        """Hex distances from start within scenario bounds. Occupancy never
        blocks (p.4 I.C.5: vehicles move freely through occupied hexes)."""
        best = {start: 0}
        q = deque([(start, 0)])
        while q:
            cur, d = q.popleft()
            if d >= budget:
                continue
            for nb in self.game.neighbors(*cur):
                if not self.in_bounds(*nb) or nb in best:
                    continue
                best[nb] = d + 1
                q.append((nb, d + 1))
        return best

    def unit(self, pid):
        return self.s["units"][str(pid)]

    def alive(self, u):
        return not u["K"]

    def budget(self, u):
        ma = self.cd.afv_types[u["afv"]]["ma"]
        if self.s["turn"] == 1 and self.entry_moved:
            return ma - 1        # entering the map on turn 1 cost 1 MP (p.17 B.6)
        return ma

    def range_between(self, a, b):
        """Range in hexes, inclusive of the target hex (p.4 I.F.1.b) — i.e.
        the hex distance between the two units."""
        best = self.bfs((a["col"], a["row"]), 99)
        return best.get((b["col"], b["row"]))

    # ------------------------------------------------------------ verdicts
    def _v(self, ok, *reasons):
        return {"legal": ok, "reasons": list(reasons)}

    def propose(self, side, action):
        t = action.get("type")
        if self.s["over"]:
            return self._v(False, "game is over")
        if t in ("move", "reverse", "pivot", "end_movement"):
            return self._propose_movement(side, action)
        if t in ("fire", "pass_fire"):
            return self._propose_combat(side, action)
        return self._v(False, f"unknown action type '{t}'")

    def _propose_movement(self, side, action):
        s = self.s
        if s["segment"] != "movement":
            return self._v(False, f"not the movement segment (it is the {s['segment']} segment) [I.B]")
        if side != s["mover"]:
            return self._v(False, f"it is {s['mover']}'s movement, not {side}'s [I.B.1]")
        if action["type"] == "end_movement":
            return self._v(True)
        u = self.s["units"].get(str(action.get("unit")))
        if not u:
            return self._v(False, "no such unit")
        if u["side"] != side:
            return self._v(False, f"unit belongs to {u['side']} [I.B.1]")
        if u["K"]:
            return self._v(False, "unit is destroyed (K-kill)")
        if u["M"]:
            return self._v(False, "unit is immobilized — an M-kill 'may not move or pivot for remainder of game' [p.5.b 'M']")
        pid = u["pid"]
        if pid in s["moved"]:
            return self._v(False, "unit already moved this turn — 'once a unit has completed its movement, it may not be changed' [I.C.1.b]")
        if pid in s["pivoted"]:
            return self._v(False, "unit already pivoted in place this turn [I.C.1.b]")

        f = action.get("facing")
        if f is None or not (0 <= int(f) <= 5):
            return self._v(False, "facing 0-5 required — 'a vehicular unit must always face towards one definite hex side' [I.C.2.b]")
        f = int(f)

        if action["type"] == "pivot":
            return self._v(True)     # free, may still fire (I.C.3.a / I.E.4)

        dest = tuple(action.get("dest") or ())
        if len(dest) != 2:
            return self._v(False, "dest [col,row] required")
        if not self.in_bounds(*dest):
            return self._v(False, "destination is outside the playable mapboard section [Firefight setup, p.24]")
        start = (u["col"], u["row"])
        if dest == start:
            return self._v(False, "destination is the current hex — use a pivot instead [I.C.3.a]")

        if action["type"] == "reverse":
            rel = (self.facing_of_step(start, dest) - u["facing"]) % 6
            if rel not in REAR_RELS:
                return self._v(False, "reverse must move towards one of the three rear-facing hex sides [I.C.4]")
            if self.range_between(u, {"col": dest[0], "row": dest[1]}) != 1:
                return self._v(False, "reverse movement is one hex per movement segment [I.C.4]")
            dfa = (f - u["facing"]) % 6
            if dfa not in (0, 1, 5):
                return self._v(False, "reverse allows a pivot of at most ONE hex side [I.C.4]")
            back = self.facing_of_step(dest, start)
            if (back - f) % 6 not in (0, 1, 5):
                return self._v(False, "after reversing, the unit must face towards the hex it came from [I.C.4]")
            return self._v(True)

        # normal move
        budget = self.budget(u)
        best = self.bfs(start, budget)
        if dest not in best:
            d_any = self.bfs(start, 60).get(dest)
            need = d_any if d_any is not None else "?"
            return self._v(False, f"destination needs {need} MP, unit has {budget}"
                           + (" (turn-1 entry already cost 1 MP [p.17 B.6])" if self.s["turn"] == 1 and self.entry_moved else "")
                           + " [I.C.1]")
        d = best[dest]
        # facing: free if the unit can END its path entering dest through its
        # front hexside (I.C.2.c); otherwise pivoting in the last hex costs +1 MP (I.C.3.b)
        free = False
        for nb in self.game.neighbors(*dest):
            if self.facing_of_step(nb, dest) != f:
                continue
            if nb == start and d == 1:
                free = True
            elif nb in best and best[nb] <= budget - 1 and best[nb] + 1 == d:
                free = True
            elif nb in best and best[nb] + 1 <= budget:
                free = True     # longer path via nb still within budget
        cost = d if free else d + 1
        if cost > budget:
            return self._v(False, f"facing {f} needs a final pivot (+1 MP): cost {cost} exceeds MA budget {budget} [I.C.3.b]")
        v = self._v(True)
        v["cost"] = cost
        return v

    def _propose_combat(self, side, action):
        s = self.s
        if s["segment"] != "combat":
            return self._v(False, f"not the combat segment (it is the {s['segment']} segment) [I.B]")
        if side in s["fire_done"]:
            return self._v(False, f"{side} has finished firing this combat segment [I.B.2]")
        if s["initiative"] != side:
            return self._v(False, f"it is {s['initiative']}'s fire, not {side}'s — fire alternates [I.B.2]")
        if action["type"] == "pass_fire":
            return self._v(True)
        u = self.s["units"].get(str(action.get("unit")))
        tgt = self.s["units"].get(str(action.get("target")))
        if not u or not tgt:
            return self._v(False, "no such unit/target")
        if u["side"] != side:
            return self._v(False, f"firing unit belongs to {u['side']}")
        if tgt["side"] == side:
            return self._v(False, "target is friendly")
        if u["K"]:
            return self._v(False, "firing unit is destroyed")
        if u["F"]:
            return self._v(False, "unit's firepower is lost — an F-kill 'may not fire main armament for remainder of game' [p.5.b 'F']")
        if tgt["K"]:
            return self._v(False, "target is already destroyed (a wreck)")
        if u["pid"] in s["moved"]:
            return self._v(False, "no weapon or vehicle which has been MOVED may fire in the combat segment of the same turn [I.E.4]")
        if u["pid"] in s["fired"]:
            return self._v(False, "each unit may fire its available rounds only once per combat segment [I.E.5]")

        rng = self.range_between(u, tgt)
        if rng == 0:
            return self._v(True)   # same-hex combat (I.G.1): automatic hits
        weapon = self.cd.weapon_of(u["afv"])
        hpn = self.cd.hpn(weapon, rng)
        if hpn is None:
            return self._v(False, f"range {rng} is beyond the weapon's Hit Probability Table — 'the target may not be fired upon' [I.F.1.d]")
        # fire initiation doctrine (I.H)
        pair = [u["pid"], tgt["pid"]]
        if hpn > self.cd.init_max_hpn and pair not in s["fired_pairs"]:
            fired_at_me = [tgt["pid"], u["pid"]] in s["fired_pairs"]
            aspect = combat_mod.target_aspect(
                tgt["facing"], self.xy(tgt), self.xy(u),
                tgt["pid"] in s["moved"])
            if not fired_at_me and aspect not in ("flank", "rear"):
                return self._v(False,
                               f"fire initiation doctrine: unadjusted HPN {hpn} exceeds 8 and the target "
                               f"(aspect {aspect.upper()}) has not fired at this unit — may not initiate [I.H.1-2]")
        return self._v(True)

    # ------------------------------------------------------------ submit
    def submit(self, side, action):
        """The only door: validate, log the proposal + verdict, apply if legal."""
        verdict = self.propose(side, action)
        entry = {"event": "action", "turn": self.s["turn"], "segment": self.s["segment"],
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
        if t == "end_movement":
            s["movement_done"].append(side)
            other = self.game.enemy(side)
            if other in s["movement_done"]:
                s["segment"] = "combat"
                s["initiative"] = self.combat_first
                return {"note": f"movement segment over — combat segment begins, {self.combat_first} fires first [I.B.2.a]"}
            s["mover"] = other
            return {"note": f"{side} movement done — {other} moves now"}

        if t in ("move", "reverse", "pivot"):
            u = self.unit(action["unit"])
            old = {"hex": [u["col"], u["row"]], "facing": u["facing"]}
            u["facing"] = int(action["facing"])
            if t == "pivot":
                s["pivoted"][u["pid"]] = True
                return {"from": old, "to": {"hex": old["hex"], "facing": u["facing"]},
                        "note": "pivot in place — may still fire [I.C.3.a]"}
            u["col"], u["row"] = action["dest"]
            s["moved"][u["pid"]] = {"from": old["hex"], "reverse": t == "reverse"}
            return {"from": old, "to": {"hex": [u["col"], u["row"]], "facing": u["facing"]},
                    "cost": verdict.get("cost"),
                    "note": "movement arrow placed — this unit may not fire this turn [I.C.1.c]"}

        if t == "pass_fire":
            s["fire_done"].append(side)
            other = self.game.enemy(side)
            if other in s["fire_done"]:
                return self._end_turn()
            s["initiative"] = other
            return {"note": f"{side} finished firing — {other} may continue [I.B.2.c]"}

        if t == "fire":
            return self._apply_fire(side, action)

    def _apply_fire(self, side, action):
        s = self.s
        u, tgt = self.unit(action["unit"]), self.unit(action["target"])
        rng = self.range_between(u, tgt)
        acquired = s["acquired"].get(u["pid"]) == tgt["pid"]
        res = combat_mod.resolve_fire(
            self.cd, u["afv"], tgt["afv"], rng,
            target_moved=tgt["pid"] in s["moved"],
            target_facing=tgt["facing"], target_xy=self.xy(tgt),
            firer_xy=self.xy(u), acquired=acquired,
            roll2=lambda: tuple(self.roll(2)), roll1=lambda: self.roll(1)[0],
            same_hex=(rng == 0))
        tgt["K"] = tgt["K"] or res["k_kill"]
        tgt["M"] = tgt["M"] or res["m_kill"]
        tgt["F"] = tgt["F"] or res["f_kill"]
        s["fired"][u["pid"]] = tgt["pid"]
        if [u["pid"], tgt["pid"]] not in s["fired_pairs"]:
            s["fired_pairs"].append([u["pid"], tgt["pid"]])
        # alternate fire: initiative passes if the enemy is still firing (I.B.2)
        other = self.game.enemy(side)
        if other not in s["fire_done"]:
            s["initiative"] = other
        res["firer"] = u["pid"]
        res["target"] = tgt["pid"]
        return res

    def _end_turn(self):
        s = self.s
        s["acquired"] = dict(s["fired"])   # fired at same target previous turn = acquired (I.F.1.a.1)
        s["moved"] = {}
        s["pivoted"] = {}
        s["fired"] = {}
        s["movement_done"] = []
        s["fire_done"] = []
        s["turn"] += 1
        s["segment"] = "movement"
        s["mover"] = self.first_player
        note = f"turn ends — all movement arrows and 'F' counters removed [I.B.3]; turn {s['turn']} begins"
        # a side with every unit dead can no longer win on kills; game also ends on wipeout
        wiped = [sd for sd in self.game.side_order
                 if all(u["K"] for u in s["units"].values() if u["side"] == sd)]
        if s["turn"] > self.turns or wiped:
            s["over"] = True
            vp = self.victory()
            s["winner"] = vp["winner"]
            note = f"GAME OVER after turn {self.turns}: {vp['winner']} wins {vp['scores']}" \
                if s["turn"] > self.turns else f"GAME OVER — wipeout: {vp['winner']} wins {vp['scores']}"
        return {"note": note, "turn": s["turn"], "over": s["over"]}

    # ------------------------------------------------------------ queries (UI/AI)
    def victory(self):
        scores = {sd: 0 for sd in self.game.side_order}
        for u in self.s["units"].values():
            vp = self.cd.afv_types[u["afv"]]["vp"]
            enemy = self.game.enemy(u["side"])
            if u["K"]:
                scores[enemy] += vp["K"]      # K supersedes M/F (p.17 NOTE)
            else:
                if u["M"]:
                    scores[enemy] += vp["MF"]
                if u["F"]:
                    scores[enemy] += vp["MF"]  # both M and F may score (p.24 rule 4.b)
        a, b = self.game.side_order
        winner = a if scores[a] > scores[b] else b if scores[b] > scores[a] else "draw"
        return {"scores": scores, "winner": winner}

    def legal_moves(self, pid):
        """For the UI: every legal destination with its free facings, whether
        an any-facing pivot fits the budget, reverse hexes, pivot legality."""
        u = self.unit(pid)
        chk = self.propose(u["side"], {"type": "pivot", "unit": pid, "facing": u["facing"]})
        base_ok = chk["legal"]
        out = {"can_act": base_ok, "reasons": chk["reasons"], "budget": self.budget(u),
               "dests": [], "reverse": [], "pivot_ok": base_ok}
        if not base_ok:
            return out
        start = (u["col"], u["row"])
        best = self.bfs(start, self.budget(u))
        for dest, d in best.items():
            if dest == start:
                continue
            free_f = set()
            for nb in self.game.neighbors(*dest):
                fdir = self.facing_of_step(nb, dest)
                if (nb == start and d == 1) or (nb in best and best[nb] + 1 <= self.budget(u)):
                    free_f.add(fdir)
            x, y = self.game.grid.hex_to_pixel(*dest)
            out["dests"].append({
                "col": dest[0], "row": dest[1], "x": x, "y": y, "cost": d,
                "free_facings": sorted(free_f),
                "any_facing": d + 1 <= self.budget(u),
                "hexnum": self.game.grid.hexnum(*dest)})
        for nb in self.game.neighbors(*start):
            rel = (self.facing_of_step(start, nb) - u["facing"]) % 6
            if rel in REAR_RELS and self.in_bounds(*nb):
                x, y = self.game.grid.hex_to_pixel(*nb)
                facings = [f for f in range(6)
                           if self.propose(u["side"], {"type": "reverse", "unit": pid,
                                                       "dest": list(nb), "facing": f})["legal"]]
                if facings:
                    out["reverse"].append({"col": nb[0], "row": nb[1], "x": x, "y": y,
                                           "facings": facings,
                                           "hexnum": self.game.grid.hexnum(*nb)})
        return out

    # P(2d6 >= n) numerator out of 36
    P2D6 = {2: 36, 3: 35, 4: 33, 5: 30, 6: 26, 7: 21, 8: 15, 9: 10, 10: 6, 11: 3, 12: 1}

    def range_info(self, pid, col=None, row=None):
        """Fire picture for a unit from its current hex (col/row None) or a
        hypothetical hex (a move candidate). Movement forfeits this turn's
        fire [I.E.4], so hypothetical numbers are NEXT-turn shots: initial
        ROF, no target-moved modifier, acquisition lost."""
        u = self.unit(pid)
        hypo = col is not None and (col, row) != (u["col"], u["row"])
        pos = {"col": u["col"] if col is None else col,
               "row": u["row"] if row is None else row}
        weapon = self.cd.weapon_of(u["afv"])
        tbl = self.cd.weapons[weapon]["hpn_by_range"]
        init_range = max((r for r in range(1, len(tbl) + 1)
                          if tbl[r - 1] <= self.cd.init_max_hpn), default=0)
        out = {"weapon": weapon, "weapon_label": self.cd.weapons[weapon]["label"],
               "hypothetical": hypo, "initiation_range": init_range,
               "max_range": len(tbl),
               "secondary": "MG: no effect vs AFVs (machine guns engage personnel — out of Scenario 1 scope)",
               "targets": []}
        for tgt in self.s["units"].values():
            if tgt["side"] == u["side"] or tgt["K"]:
                continue
            rng = self.range_between(pos, tgt)
            hpn = self.cd.hpn(weapon, rng) if rng and rng > 0 else (0 if rng == 0 else None)
            rec = {"target": tgt["pid"], "range": rng, "hpn": hpn}
            if hpn is None:
                rec["note"] = "out of range"
                out["targets"].append(rec)
                continue
            moved = (not hypo) and tgt["pid"] in self.s["moved"]
            adj = hpn + (self.cd.target_moved_mod if moved else 0)
            acquired = (not hypo) and self.s["acquired"].get(u["pid"]) == tgt["pid"]
            rounds = self.cd.rof(weapon, acquired)
            p1 = self.P2D6.get(adj, 36 if rng == 0 else 0) / 36.0
            aspect = combat_mod.target_aspect(
                tgt["facing"], self.xy(tgt),
                self.game.grid.hex_to_pixel(pos["col"], pos["row"]), moved)
            can_init = (hpn <= self.cd.init_max_hpn
                        or [u["pid"], tgt["pid"]] in self.s["fired_pairs"]
                        or [tgt["pid"], u["pid"]] in self.s["fired_pairs"]
                        or aspect in ("flank", "rear"))
            rec.update(hpn_adjusted=adj, prob=round(p1 * 100),
                       rounds=rounds, acquired=acquired, aspect=aspect,
                       prob_any=round((1 - (1 - p1) ** rounds) * 100),
                       initiation_ok=can_init)
            out["targets"].append(rec)
        out["targets"].sort(key=lambda t: (t.get("hpn") is None, t.get("range") or 0))
        return out

    def legal_targets(self, pid):
        """For the UI/AI: every enemy unit with range, HPN, rounds, and the
        gate's verdict (so illegal choices are visible-but-blocked)."""
        u = self.unit(pid)
        out = []
        for tgt in self.s["units"].values():
            if tgt["side"] == u["side"] or tgt["K"]:
                continue
            rng = self.range_between(u, tgt)
            weapon = self.cd.weapon_of(u["afv"])
            hpn = self.cd.hpn(weapon, rng) if rng > 0 else 0
            v = self.propose(u["side"], {"type": "fire", "unit": pid, "target": tgt["pid"]})
            acquired = self.s["acquired"].get(u["pid"]) == tgt["pid"]
            moved = tgt["pid"] in self.s["moved"]
            out.append({
                "target": tgt["pid"], "range": rng, "hpn": hpn,
                "hpn_adjusted": (hpn + (self.cd.target_moved_mod if moved else 0)) if hpn else hpn,
                "acquired": acquired,
                "rounds": self.cd.rof(weapon, acquired),
                "aspect": combat_mod.target_aspect(tgt["facing"], self.xy(tgt),
                                                   self.xy(u), moved),
                "legal": v["legal"], "reasons": v["reasons"]})
        return sorted(out, key=lambda t: (not t["legal"], t["range"]))
