"""
napoleonic.py - NapoleonicGame: the GBoNW-family legality gate.

Enforced through phase 3: movement (formation-and-facing-true over the
transcribed TEC, stacking [7.1], enemy-front-hex stops [5.1.3], road
movement [5.3], movement disorder [5.1.1/6.4.1]), fire combat with return
fire, LOS and the morale/rout/rally ledger [8.1/9.x/10.x/12.x], victory
[A15.1], and — schema 3 — the COMMAND SYSTEM [3.0/4.0]: voluntary LIM
pool (A15.1 special rule), seeded initiative and LIM draws, activation
rolls, the Command Breakdown Table [4.7] including the ENEMY opportunity,
full/limited activation budgets [4.6], In/Out of Command marking [4.3.3],
the Non-LIM phase [3.0.C], division fatigue [13.x] and division
breakpoint LIM withdrawal [11.2.1]. Melee, reactions and strategic
movement remain umpired (phase 4) and the scenario's rules_scope says so.

Log compatibility: games recorded before phase 3 carry state schema 2 and
replay through the pre-command flow (side-alternating mass activations);
new games with scenario `command` data run schema 3. verify_game passes
the init entry's schema so old logs keep verifying hash-for-hash.

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

import command as cmd_mod
import fire as fire_mod
import formations as fm
from gate import GateGame

TURN_NOUN = "turn"


class NapoleonicGame(GateGame):
    HASH_KEYS = ("turn", "mover", "units", "moved", "seed", "rng_calls",
                 "tier")
    TURN_NOUN = "turn"
    PHASE_FIELD = "phase"

    def __init__(self, game, scenario_path, live_dir, seed=None, tier=None,
                 command=None):
        super().__init__(game, scenario_path, live_dir)
        self.F = fm.Formations(game)
        self._load_terrain()
        self.ctables = game.spec.get("combat_tables")
        self.schedule = {}          # no reinforcements in this scenario
        # command=None -> scenario decides; False forces the pre-command
        # schema-2 flow (old-log replay + mechanics test harnesses)
        self.CMD = game.spec.get("command")
        self.SCMD = self.scenario.get("command")
        self._cmd = bool(self.CMD and self.SCMD) if command is None \
            else bool(command)
        # leader ratings are static scenario data (counter art), read at
        # runtime - NOT copied into hashed unit state (log contract)
        self._ratings = {(u["side"], u["slot"]): u["command"]
                         for u in self.scenario["units"]
                         if u.get("command")}
        self._resolve_tier(tier)
        self._resume_or_new(self._fresh_seed(seed),
                            required=("units", "moved", "tier", "schema"))
        if (self.s.get("schema", 2) >= 3) != self._cmd:
            self.new_game(self._fresh_seed(seed))   # flow mismatch: reset

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
        if self._cmd:
            self.s["schema"] = 3
            self.s["phase"] = "command"
            self.s.update({
                "pool_decl": {},        # side -> this turn's declared LIMs
                "pool": [],             # undrawn "Side:LIM" refs
                "initiative": None,
                "act": None,            # open activation context
                "act_count": {},        # div_key -> activations this turn
                "arty_used": {},        # arty pid -> div_key attached to
                "turn_units": [],       # pids granted an activation
                "ooc": [],              # pids marked Out of Command [4.3.3]
                "nonlim_used": {s_: [] for s_ in self.game.side_order},
                "nonlim_passed": {s_: False for s_ in self.game.side_order},
                "fatigue": {dk: 0 for dk in self._divisions()},
                "fat_crossed": {},      # div_key -> [7/8/9 thresholds hit]
                "fat_lim": [], "fat_combat": [],
            })
        self._reset_log()
        self._log({"event": "init", "mode": "napoleonic",
                   "scenario": self.scenario["name"],
                   "tier": self.tier, "seed": seed,
                   "schema": self.s["schema"],
                   "units": self._units_for_log(units)})
        self.save()

    def _units_for_log(self, units):
        return [dict(pid=u["pid"], slot=u["slot"], side=u["side"],
                     hex=[u["col"], u["row"]], facing=u["facing"],
                     formation=u["formation"]) for u in units.values()]

    # ==================================================== command system
    # [3.0/4.0]; schema 3 only. All draws and rolls are the seeded stream.
    def _divisions(self):
        """div_key ('French:3') -> scenario command.divisions entry + side/key."""
        out = {}
        for side, divs in (self.SCMD or {}).get("divisions", {}).items():
            for key, d in divs.items():
                out[f"{side}:{key}"] = dict(d, side=side, key=key)
        return out

    def _leader_of(self, dk):
        d = self._divisions()[dk]
        for u in self.s["units"].values():
            if u["slot"] == d["leader"] and u["side"] == d["side"]:
                return u
        return None

    def _rating(self, dk):
        """The division leader's printed ratings (activation/personality/
        range) - static scenario data, cited to the counter art."""
        d = self._divisions()[dk]
        return self._ratings[(d["side"], d["leader"])]

    def _div_key_of(self, u):
        """The unit's division for command/fatigue. Leaders map to the
        division they lead; artillery to the division it attached to this
        turn (flexible attachment, A15.1 special rule); combat units to
        their printed division band."""
        for dk, d in self._divisions().items():
            if u["arm"] == "leader":
                if d["leader"] == u["slot"] and d["side"] == u["side"]:
                    return dk
            elif d["side"] == u["side"] and d["key"] == u.get("div"):
                if u["arm"].startswith("artillery"):
                    break               # flexible: only via attachment
                return dk
        if u["arm"].startswith("artillery"):
            return self.s["arty_used"].get(u["pid"])
        return None

    def _organic(self, dk):
        """Alive organic (non-leader, non-artillery) members [4.3.3]."""
        d = self._divisions()[dk]
        return [u for u in self.s["units"].values()
                if u["side"] == d["side"] and u.get("div") == d["key"]
                and u["arm"] not in ("leader",)
                and not u["arm"].startswith("artillery")
                and self.on_map(u)]

    def _attachable_arty(self, dk):
        """Artillery eligible to attach to this division's activation:
        listed for it in the scenario, alive, not yet activated this turn
        (A15.1 special rule; one activation per unit per turn)."""
        att = (self.SCMD or {}).get("artillery_attach", {})
        d = self._divisions()[dk]
        out = []
        for u in self.s["units"].values():
            if not u["arm"].startswith("artillery") or not self.on_map(u):
                continue
            if u["side"] != d["side"] or u["pid"] in self.s["turn_units"]:
                continue
            if d["key"] in att.get(u["slot"], []):
                out.append(u)
        return out

    def _at_div_breakpoint(self, dk):
        """Division Breakpoint [11.2]: organic combat units at Unit
        Breakpoint [11.1] (dead units count - they broke past it) >= the
        division's printed Breakpoint Level."""
        d = self._divisions()[dk]
        broke = 0
        for u in self.s["units"].values():
            if u["side"] != d["side"] or u.get("div") != d["key"]:
                continue
            if u["arm"] == "leader" or u["arm"].startswith("artillery"):
                continue                # artillery never breaks [11.1]
            if u.get("dead") or self._at_breakpoint(u):
                broke += 1
        return broke >= int(d["breakpoint"])

    def _lim_side(self, ref):
        return ref.split(":", 1)[0]

    def _lim_name(self, ref):
        return ref.split(":", 1)[1]

    def _div_by_lim(self, side, lim):
        """The division a DIVISION LIM belongs to. The Independent LIM
        maps to no single division: its divisions fatigue only if they
        activate [13.1.1] and its pool eligibility is per-division at
        draw time [11.2.1] - so it returns None here."""
        if lim == "Independent":
            return None
        for dk, d in self._divisions().items():
            if d["side"] == side and d["lim"] == lim:
                return dk
        return None

    def _side_key(self, side):
        """game.json command tables key ('french'/'allied')."""
        return side.lower()

    def _enemy(self, side):
        a, b = self.game.side_order
        return b if side == a else a

    def _enemies_within(self, dk, hexes):
        """Any organic unit of the division within `hexes` of an enemy
        combat unit [4.7 RETREAT/CHARGE preconditions]."""
        d = self._divisions()[dk]
        foes = [(v["col"], v["row"]) for v in self.s["units"].values()
                if v["side"] != d["side"] and self.on_map(v)
                and v["arm"] != "leader"]
        for u in self._organic(dk):
            if any(self._dist((u["col"], u["row"]), f) <= hexes
                   for f in foes):
                return True
        return False

    # -------------------------------------------------- pool + initiative
    def _available_lims(self, side):
        """LIMs a side may declare: the scenario roster minus LIMs of
        divisions at Breakpoint [11.2.1 - may NEVER be re-added]."""
        out = []
        for lim in self.scenario["initial_lims"][side]:
            dk = self._div_by_lim(side, lim)
            if dk and self._at_div_breakpoint(dk):
                continue
            if dk and not self._leader_of(dk):
                continue
            out.append(lim)
        return out

    def _both_pools_declared(self, out):
        """Close the Pool Placement Phase [3.0.A]: fatigue bookings for
        committed division LIMs (designer Q&A: any LIM in the pool
        fatigues its division, whatever happens), then the opposed
        initiative roll [4.4] (ties reroll), then the pool fills."""
        pool = []
        for side, lims in self.s["pool_decl"].items():
            for lim in lims:
                pool.append(f"{side}:{lim}")
                dk = self._div_by_lim(side, lim)
                if dk and dk not in self.s["fat_lim"]:
                    self.s["fat_lim"].append(dk)
        self.s["pool"] = sorted(pool)      # draw order is the RNG's job
        mods = (self.SCMD or {}).get("initiative_mod", {})
        rolls = []
        while True:
            pair = {}
            for side in self.game.side_order:
                pair[side] = self.roll_d10() + int(mods.get(side, 0))
            rolls.append(pair)
            vals = list(pair.values())
            if vals[0] != vals[1]:
                break
        a, b = self.game.side_order
        winner = a if pair[a] > pair[b] else b
        self.s["initiative"] = winner
        out["initiative"] = {"rolls": rolls, "winner": winner,
                             "cite": "4.4"}
        if not self.s["pool"]:
            out["note"] = "empty pool: no LIM activations this turn"
            self._enter_nonlim(out)
        else:
            self.s["phase"] = "initiative"
            self.s["mover"] = winner

    # ------------------------------------------------------- activations
    def _open_lim(self, ref, out):
        """A LIM comes up (initiative choice or pool draw) [4.5]."""
        side, lim = self._lim_side(ref), self._lim_name(ref)
        out["lim"] = ref
        if lim == "Independent":
            die = self.roll_d10()
            allowed = cmd_mod.independent_allowance(
                self.CMD, self._side_key(side), die)
            eligible = [dk for dk, d in self._divisions().items()
                        if d["side"] == side and d["lim"] == "Independent"
                        and self._leader_of(dk)
                        and not self._at_div_breakpoint(dk)   # [11.2.1]
                        and self.s["act_count"].get(dk, 0) == 0]
            out["independent"] = {"die": die, "allowed": allowed,
                                  "eligible": eligible, "cite": "A4.3.2"}
            if allowed == 0 or not eligible:
                out["note"] = "no independent leader may activate"
                self._draw_next(out)
                return
            self.s["act"] = {"lim": ref, "side": side,
                             "kind": "independent", "div": None,
                             "pending": "choice", "atype": None,
                             "stage": None, "incommand": [], "budget": {},
                             "indep": {"allowed": allowed, "done": [],
                                       "eligible": eligible},
                             "prior_bd": None, "bd_after": None}
            self.s["mover"] = side
            return
        dk = self._div_by_lim(side, lim)
        self.s["act"] = {"lim": ref, "side": side, "kind": "division",
                         "div": dk, "pending": "choice", "atype": None,
                         "stage": None, "incommand": [], "budget": {},
                         "indep": None, "prior_bd": None, "bd_after": None}
        self.s["mover"] = side

    def _open_activation(self, dk, atype, out, budget_frac=None):
        """In Command determination happens NOW [4.3.3]; budgets by
        activation type [4.6.1/4.6.2]."""
        act = self.s["act"]
        leader = self._leader_of(dk)
        rng = int(self._rating(dk)["range"])
        frac = budget_frac if budget_frac is not None else \
            (1.0 if atype == "full" else 0.5)
        members = []
        for u in self._organic(dk):
            if self._dist((u["col"], u["row"]),
                          (leader["col"], leader["row"])) <= rng:
                members.append(u)
            elif u["pid"] not in self.s["ooc"]:
                self.s["ooc"].append(u["pid"])          # [4.3.3]
        for u in self._attachable_arty(dk):
            if self._dist((u["col"], u["row"]),
                          (leader["col"], leader["row"])) <= rng:
                members.append(u)
                self.s["arty_used"][u["pid"]] = dk
        members.append(leader)
        act["div"] = dk
        act["atype"] = atype
        act["pending"] = None
        act["stage"] = "move"
        act["incommand"] = [u["pid"] for u in members]
        act["budget"] = {
            u["pid"]: float(int(u["ma"] * frac) if frac < 1.0
                            else u["ma"]) for u in members}
        self.s["moved"] = []
        self.s["returned"] = []      # once per enemy activation (Q&A)
        self.s["act_count"][dk] = self.s["act_count"].get(dk, 0) + 1
        self.s["turn_units"] = sorted(set(self.s["turn_units"])
                                      | set(act["incommand"]))
        # fatigue: activating under the Independent LIM fatigues [13.1.1];
        # breakdown free activations don't (designer Q&A)
        if act["kind"] == "independent" and dk not in self.s["fat_lim"]:
            self.s["fat_lim"].append(dk)
        out.setdefault("activation", {}).update(
            div=dk, type=atype,
            in_command=list(act["incommand"]),
            out_of_command=[u["pid"] for u in self._organic(dk)
                            if u["pid"] not in act["incommand"]],
            budgets={p: act["budget"][p] for p in act["incommand"]})
        self.s["mover"] = act["side"]

    def _resolve_choice(self, dk, choice, out):
        """Activation Procedure (charts p1 / 4.5.1): limited is automatic;
        full rolls vs the leader's activation rating, failure rolls the
        Command Breakdown Table on his personality column [4.7]."""
        act = self.s["act"]
        leader = self._leader_of(dk)
        if choice == "limited":
            self._open_activation(dk, "limited", out)
            return
        die = self.roll_d10()
        rate = self._rating(dk)
        rating = int(rate["activation"])
        out["activation_roll"] = {"div": dk, "die": die, "vs": rating,
                                  "cite": "4.5.1"}
        if die <= rating:
            self._open_activation(dk, "full", out)
            return
        bd_die = self.roll_d10()
        res = cmd_mod.breakdown(self.CMD, rate["personality"],
                                bd_die, prior=act.get("prior_bd"))
        out["breakdown"] = {"die": bd_die,
                            "column": rate["personality"],
                            "result": res, "cite": "4.7"}
        if res == "charge":
            # unreachable in validated scope: no Aggressive leader exists
            # in this scenario; melee lands in phase 4
            raise RuntimeError("CHARGE breakdown result outside validated "
                               "scope [4.7; phase 4]")
        if res == "full":
            self._open_activation(dk, "full", out)
        elif res == "limited":
            self._open_activation(dk, "limited", out)
        elif res == "stop":
            out["breakdown"]["effect"] = "commander finished [4.7]"
            self._close_division(out)
        elif res == "retreat":
            self._breakdown_retreat(dk, out)
            self._close_division(out)
        elif res == "enemy":
            out["breakdown"]["effect"] = ("stop; enemy may activate his "
                                          "closest division [4.7]")
            self._offer_breakdown(self._enemy(act["side"]),
                                  (leader["col"], leader["row"]),
                                  "enemy", out)
        elif res == "reactivate":
            act["bd_after"] = {"side": act["side"],
                               "origin": (leader["col"], leader["row"]),
                               "result": "reactivate"}
            self._open_activation(dk, "full", out)

    def _breakdown_retreat(self, dk, out):
        """RETREAT [4.7]: if any division unit is within 3 hexes of an
        enemy, all In Command units retreat half MA (rounded up) away
        (unlimbered artillery limbers first); no SP loss for shortfall -
        this is not a rout retreat."""
        if not self._enemies_within(dk, 3):
            out["breakdown"]["effect"] = \
                "no enemy within 3 hexes: no retreat; commander finished"
            return
        leader = self._leader_of(dk)
        rng = int(self._rating(dk)["range"])
        moved = []
        for u in self._organic(dk) + \
                [a for a in self._attachable_arty(dk)]:
            if self._dist((u["col"], u["row"]),
                          (leader["col"], leader["row"])) > rng:
                continue                        # In Command units only
            if u["formation"] == "unlimbered":
                u["formation"] = "limbered"     # [4.7]
            sub = {}
            self._retreat(u, -(-int(u["ma"]) // 2), sub, routed=False,
                          sp_short=False)
            moved.append({"unit": u["pid"], **sub})
        out["breakdown"]["retreat"] = moved

    def _offer_breakdown(self, side, origin, result, out):
        """ENEMY/REACTIVATE opportunity [4.7]: `side` may activate its
        division closest to `origin` (leader distance, ties = chooser's
        pick), even one already activated - but no division reactivates
        twice. Optional (designer Q&A)."""
        cands = {}
        for dk, d in self._divisions().items():
            if d["side"] != side:
                continue
            ldr = self._leader_of(dk)
            if not ldr:
                continue
            cands[dk] = self._dist((ldr["col"], ldr["row"]), origin)
        if not cands:
            self._draw_next(out)
            return
        best = min(cands.values())
        closest = sorted(k for k, v in cands.items() if v == best)
        self.s["act"] = {"lim": None, "side": side, "kind": "breakdown",
                         "div": None, "pending": "bd_offer", "atype": None,
                         "stage": None, "incommand": [], "budget": {},
                         "indep": None, "prior_bd": result,
                         "bd_after": None,
                         "bd_closest": closest}
        self.s["mover"] = side
        out["breakdown_offer"] = {"side": side, "closest": closest,
                                  "cite": "4.7 + designer Q&A (optional)"}

    def _close_division(self, out):
        """One division's activation ends; route the flow onward."""
        act = self.s["act"]
        if act.get("bd_after"):
            after = act.pop("bd_after")
            self._offer_breakdown(after["side"], after["origin"],
                                  after["result"], out)
            return
        if act["kind"] == "independent":
            ind = act["indep"]
            if act["div"] and act["div"] not in ind["done"]:
                ind["done"].append(act["div"])
            remaining = [dk for dk in ind["eligible"]
                         if dk not in ind["done"]
                         and self.s["act_count"].get(dk, 0) == 0]
            if remaining and len(ind["done"]) < ind["allowed"]:
                act["div"] = None
                act["atype"] = None
                act["stage"] = None
                act["incommand"] = []
                act["budget"] = {}
                act["pending"] = "choice"
                self.s["mover"] = act["side"]
                return
        if act["kind"] in ("nonlim_div", "nonlim_unit"):
            self._nonlim_next(out)
            return
        self._draw_next(out)

    def _draw_next(self, out):
        """LIM Selection Segment [3.0.B.2]: seeded blind draw."""
        self.s["act"] = None
        if self.s["pool"]:
            r = self._rng()
            idx = int(r.random() * len(self.s["pool"]))
            self.s["rng_calls"] += 1
            ref = self.s["pool"].pop(idx)
            out["drawn"] = {"lim": ref, "left": len(self.s["pool"]),
                            "cite": "3.0.B.2"}
            self._open_lim(ref, out)
            return
        self._enter_nonlim(out)

    # ---------------------------------------------------- non-LIM phase
    def _nonlim_options(self, side):
        """Eligible picks [3.0.C.1]: divisions that did not activate and
        whose own LIM was not committed (Independent-LIM divisions that
        never activated qualify per A4.3.2), or one Out of Command /
        never-attached artillery unit [4.6.2.b]."""
        opts = {"divisions": [], "units": []}
        declared = self.s["pool_decl"].get(side, [])
        for dk, d in self._divisions().items():
            if d["side"] != side or not self._leader_of(dk):
                continue
            if self.s["act_count"].get(dk, 0) > 0:
                continue
            if dk in self.s["nonlim_used"][side]:
                continue
            if d["lim"] != "Independent" and d["lim"] in declared:
                continue
            opts["divisions"].append(dk)
        for u in self.s["units"].values():
            if u["side"] != side or not self.on_map(u):
                continue
            if u["arm"] == "leader" or u["pid"] in self.s["turn_units"]:
                continue
            if u.get("morale_state") == "routed":
                continue        # nothing it could legally do [9.2.4]
            if f"u:{u['pid']}" in self.s["nonlim_used"][side]:
                continue
            if u["pid"] in self.s["ooc"] or (
                    u["arm"].startswith("artillery")
                    and u["pid"] not in self.s["arty_used"]):
                opts["units"].append(u["pid"])
        return opts

    def _enter_nonlim(self, out):
        self.s["phase"] = "non_lim"
        self.s["act"] = None
        self.s["mover"] = self.s["initiative"]
        self._nonlim_next(out, entering=True)

    def _nonlim_next(self, out, entering=False):
        """Alternate C.1/C.2 [3.0]; a side with nothing left is passed
        automatically (logged); both passed -> Rally Phase."""
        if not entering:
            self.s["act"] = None
        order = [self._enemy(self.s["mover"]), self.s["mover"]] \
            if not entering else \
            [self.s["mover"], self._enemy(self.s["mover"])]
        for side in order:
            if self.s["nonlim_passed"][side]:
                continue
            o = self._nonlim_options(side)
            if not o["divisions"] and not o["units"]:
                self.s["nonlim_passed"][side] = True
                out.setdefault("auto_passed", []).append(side)
                continue
            self.s["mover"] = side
            self.s["phase"] = "non_lim"
            return
        self._end_nonlim(out)

    def _end_nonlim(self, out):
        """LIM Removal Segment [3.0.C.3] is subsumed by the per-turn
        voluntary pool declaration (A15.1) + the breakpoint LIM ban
        enforced in _available_lims [11.2.1]. On to the Rally Phase."""
        needy = any(self.on_map(u) and u.get("morale_state", "good")
                    != "good" for u in self.s["units"].values())
        if needy:
            self.s["phase"] = "rally"
            self.s["mover"] = self.first_player
            self.s["rallied"] = []
            self.s["moved"] = []
            out["phase"] = "rally"
            return
        self._fatigue_segment(out)
        self._next_turn()
        out.update(turn=self.s["turn"], mover=self.s["mover"])

    # ------------------------------------------------------ fatigue [13]
    def _fatigue_segment(self, out):
        """Fatigue Segment [3.0.D.4]: +1 for a committed LIM or combat
        [13.1, designer Q&A], -1 for idle rested divisions 3+ hexes from
        the enemy [13.2]; one-time 7/8/9 immediate effects per the
        errata [13.3]."""
        changes = []
        foes = {s_: [(v["col"], v["row"])
                     for v in self.s["units"].values()
                     if v["side"] != s_ and self.on_map(v)
                     and v["arm"] != "leader"]
                for s_ in self.game.side_order}
        for dk in sorted(self._divisions()):
            lvl = self.s["fatigue"].get(dk, 0)
            up = dk in self.s["fat_lim"] or dk in self.s["fat_combat"]
            if up:
                new = min(9, lvl + 1)
            else:
                far = all(min([self._dist((u["col"], u["row"]), f)
                               for f in foes[u["side"]]] or [99]) >= 3
                          for u in self._organic(dk))
                new = max(0, lvl - 1) if (far and lvl > 0) else lvl
            if new == lvl:
                continue
            self.s["fatigue"][dk] = new
            rec = {"div": dk, "from": lvl, "to": new}
            if new > lvl:
                crossed = self.s["fat_crossed"].setdefault(dk, [])
                effects, newly = cmd_mod.fatigue_threshold_effects(
                    new, set(crossed))
                crossed.extend(newly)
                if effects:
                    rec["immediate"] = []
                    for u in self._organic(dk):
                        for eff in effects:
                            if eff == "morale_level":
                                i = self._LADDER.index(u["morale_state"])
                                sub = {}
                                self._set_morale_state(
                                    u, self._LADDER[min(3, i + 1)], sub)
                                rec["immediate"].append(
                                    {"unit": u["pid"], **sub})
                            elif eff == "disorder":
                                self._disorder(u)
                                rec["immediate"].append(
                                    {"unit": u["pid"],
                                     "formation": "disorder"})
            changes.append(rec)
        self.s["fat_lim"] = []
        self.s["fat_combat"] = []
        if changes:
            out["fatigue"] = {"changes": changes, "cite": "13.1-13.3"}

    def _mark_combat_fatigue(self, u, band=None):
        """[13.1.2]: performing or suffering combat fatigues the unit's
        division - except medium/long-range artillery fire. Unattached
        artillery has no division to mark this turn."""
        if band in ("medium", "long"):
            return
        dk = self._div_key_of(u)
        if dk and dk not in self.s["fat_combat"]:
            self.s["fat_combat"].append(dk)

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
    def reachable(self, pid, budget=None, avoid_adjacent=False):
        """Dijkstra over (col,row,facing): every reachable (hex, facing)
        with its cheapest MP cost, its path, and pending disorder events.
        Facing changes cost the TEC row per 30-degree step; advancing goes
        through front hexsides only; entering an enemy front hex is
        terminal [5.1.3]. `budget` caps spendable MPs below the MA
        (limited activations [4.6.2]); `avoid_adjacent` bars ENTERING any
        hex adjacent to an enemy combat unit (limited activations may not
        move adjacent to enemy units - any hexside, designer Q&A)."""
        u = self.unit(pid)
        if self.F.immobile(u["formation"]):
            return {}
        ma = float(u["ma"]) if budget is None else float(budget)
        no_adj = set()
        if avoid_adjacent:
            for v in self.s["units"].values():
                if v["side"] == u["side"] or v["arm"] == "leader" \
                        or not self.on_map(v):
                    continue
                no_adj.add((v["col"], v["row"]))
                for nb in self.game.neighbors(v["col"], v["row"]):
                    no_adj.add(tuple(nb))
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
                if tuple(nb) in no_adj:
                    continue    # limited: never adjacent to enemy [4.6.2]
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
        if self._cmd:
            return self._propose_cmd(side, action)
        if side != self.s["mover"]:
            return self._v(False, f"it is {self.s['mover']}'s activation")
        if t == "fire":
            return self._propose_fire(side, action)
        if t == "end_turn":
            return self._v(True)
        return self._propose_unit_action(side, action)

    def _propose_unit_action(self, side, action, budget=None,
                             avoid_adjacent=False):
        """Shared unit-action legality (both schemas). `budget` = the MP
        allowance this activation (None = full MA); `avoid_adjacent` = the
        limited-activation adjacency ban [4.6.2 + designer Q&A]."""
        t = action.get("type")
        pid = str(action.get("unit"))
        if pid not in self.s["units"]:
            return self._v(False, f"unknown unit {pid}")
        u = self.unit(pid)
        bud = float(u["ma"]) if budget is None else float(budget)
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
                           "unit already acted in this activation "
                           "[4.6.1: one move per unit]")
        if t == "move":
            dest = action.get("dest")
            reach = self.reachable(pid, budget=bud,
                                   avoid_adjacent=avoid_adjacent)
            facing = action.get("facing")
            if facing is None:      # engine picks the cheapest facing
                opts = [(v[0], k[2]) for k, v in reach.items()
                        if (k[0], k[1]) == (int(dest[0]), int(dest[1]))]
                if not opts:
                    return self._v(False,
                                   f"({dest[0]},{dest[1]}) is not "
                                   f"reachable within {bud} MPs "
                                   "through front hexsides "
                                   "[5.1/6.1/TEC 5.0]")
                return self._v(True)
            key = (int(dest[0]), int(dest[1]), int(facing))
            if key not in reach:
                return self._v(False,
                               f"({dest[0]},{dest[1]}) facing {facing} is "
                               f"not reachable within {bud} MPs through "
                               "front hexsides [5.1/6.1/TEC 5.0]")
            return self._v(True)
        if t == "about_face":
            cost = self.F.action_cost(u, "about_face", u["ma"])
            if cost is None:
                return self._v(False, "about face not allowed for this "
                                      "unit/formation [TEC 5.0]")
            if cost > bud + 1e-9:
                return self._v(False, f"about face costs {cost} MPs, "
                                      f"budget is {bud} [4.6.2]")
            return self._v(True)
        if t == "change_formation":
            to = action.get("to")
            if to not in self.F.defs:
                return self._v(False, f"unknown formation {to}")
            ok, why = self._formation_change_ok(u, to)
            if not ok:
                return self._v(False, why)
            cost = self.F.action_cost(u, "change_formation", u["ma"])
            if cost is not None and cost > bud + 1e-9:
                return self._v(False, f"formation change costs {cost} "
                                      f"MPs, budget is {bud} [4.6.2]")
            return self._v(True)
        if t == "slide" or t == "reverse":
            ok, why = self._special_move_ok(u, t, action.get("dest"),
                                            budget=bud)
            return self._v(ok, *([why] if why else []))
        return self._v(False, f"unknown action type {t}")

    # ------------------------------------------- command-flow proposals
    def _propose_cmd(self, side, action):
        t = action.get("type")
        ph = self.s["phase"]
        if ph == "command":
            if t != "set_pool":
                return self._v(False, "Pool Placement Phase: declare your "
                                      "LIMs with set_pool [3.0.A / A15.1]")
            if side != self.s["mover"]:
                return self._v(False, f"it is {self.s['mover']}'s pool "
                                      "declaration")
            lims = action.get("lims")
            if not isinstance(lims, list):
                return self._v(False, "set_pool needs a lims list")
            avail = self._available_lims(side)
            if len(set(lims)) != len(lims):
                return self._v(False, "duplicate LIM")
            for lim in lims:
                if lim in avail:
                    continue
                if lim in self.scenario["initial_lims"][side]:
                    return self._v(False,
                                   f"{lim}: division at Breakpoint - its "
                                   "LIM may never be added [11.2.1]")
                return self._v(False, f"{lim} is not one of your LIMs")
            return self._v(True)
        if ph == "initiative":
            if t != "choose_initiative_lim":
                return self._v(False, "Initiative Choice Segment: pick "
                                      "the Initiative LIM [3.0.A.3]")
            if side != self.s["initiative"]:
                return self._v(False, f"{self.s['initiative']} won the "
                                      "initiative [4.4]")
            ref = action.get("lim")
            if ref not in self.s["pool"]:
                return self._v(False, f"{ref} is not in the pool "
                                      "(any pool LIM may be chosen [4.4])")
            return self._v(True)
        if ph == "activation":
            act = self.s["act"]
            if act is None:
                return self._v(False, "no activation open")
            if side != act["side"]:
                return self._v(False, f"it is {act['side']}'s activation")
            if act["pending"] == "bd_offer":
                if t == "bd_decline":
                    return self._v(True)
                if t != "bd_activate":
                    return self._v(False,
                                   "breakdown opportunity: bd_activate "
                                   "your closest division or bd_decline "
                                   "[4.7]")
                dk = action.get("division")
                if dk not in act["bd_closest"]:
                    return self._v(False,
                                   f"closest division(s): "
                                   f"{act['bd_closest']} [4.7]")
                if self.s["act_count"].get(dk, 0) >= 2:
                    return self._v(False, "no division may be reactivated "
                                          "more than once per turn [4.7]")
                return self._v(True)
            if act["pending"] == "choice":
                if t == "end_activation":
                    return self._v(True)    # decline the attempt [4.5.1
                    # 'may attempt'] / remaining independent leaders
                if t != "activation_choice":
                    return self._v(False, "choose full or limited "
                                          "activation [4.5.1/4.6]")
                choice = action.get("choice")
                if choice not in ("full", "limited"):
                    return self._v(False, "choice must be full or limited")
                if act["kind"] == "independent":
                    dk = action.get("division")
                    ind = act["indep"]
                    if dk not in ind["eligible"] or dk in ind["done"]:
                        return self._v(False,
                                       "not an eligible independent "
                                       "division [A4.3.2]")
                    if len(ind["done"]) >= ind["allowed"]:
                        return self._v(False,
                                       f"only {ind['allowed']} independent "
                                       "leaders may activate this draw "
                                       "[A4.3.2]")
                else:
                    dk = act["div"]
                if choice == "full" and self._at_div_breakpoint(dk):
                    return self._v(False,
                                   "division at Breakpoint may not "
                                   "conduct a Full Activation [11.2.1]")
                return self._v(True)
            # an activation is open: unit actions, fire, end_activation
            if t == "end_activation":
                return self._v(True)
            if t == "fire":
                pid = str(action.get("unit"))
                if pid not in act["incommand"]:
                    return self._v(False,
                                   "only In Command units of the "
                                   "activated division act [4.3.3]")
                return self._propose_fire(side, action)
            if t in ("move", "about_face", "change_formation", "slide",
                     "reverse"):
                if act["stage"] == "combat":
                    return self._v(False,
                                   "the division has opened fire: no "
                                   "more movement this activation "
                                   "[4.6.1]")
                pid = str(action.get("unit"))
                if pid not in act["incommand"]:
                    return self._v(False,
                                   "only In Command units of the "
                                   "activated division act [4.3.3]")
                return self._propose_unit_action(
                    side, action, budget=act["budget"].get(pid),
                    avoid_adjacent=act["atype"] == "limited")
            return self._v(False, f"unknown action type {t}")
        if ph == "non_lim":
            if side != self.s["mover"]:
                return self._v(False, f"it is {self.s['mover']}'s "
                                      "Non-LIM pick [3.0.C]")
            if t == "pass_non_lim":
                return self._v(True)
            if t != "non_lim":
                return self._v(False, "Non-LIM Phase: pick a division or "
                                      "an Out of Command unit, or pass "
                                      "[3.0.C]")
            o = self._nonlim_options(side)
            if action.get("division"):
                dk = action["division"]
                if dk not in o["divisions"]:
                    return self._v(False,
                                   f"{dk} is not eligible: it activated, "
                                   "had its LIM committed, or was used "
                                   "[3.0.C.1]")
                return self._v(True)
            if action.get("unit"):
                pid = str(action["unit"])
                if pid not in o["units"]:
                    return self._v(False,
                                   "not an eligible Out of Command / "
                                   "unattached unit [3.0.C.1/4.6.2.b]")
                return self._v(True)
            return self._v(False, "non_lim needs a division or a unit")
        return self._v(False, f"no {t} in phase {ph}")

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

    def _special_move_ok(self, u, t, dest, budget=None):
        bud = float(u["ma"]) if budget is None else float(budget)
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
        if cost > bud + 1e-9:
            return False, f"costs {cost} MPs, budget is {bud}"
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
        if self._cmd:
            self._mark_combat_fatigue(firer, band)     # [13.1.2]
            self._mark_combat_fatigue(target, band)
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
        if self._cmd and not u["arm"].startswith("artillery"):
            dk = self._div_key_of(u)
            if dk and self.s.get("fatigue", {}).get(dk, 0) >= 4:
                d.append(1)     # Fatigue Effects Table, level 4+ [13.3]
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

    def _retreat(self, u, dist, out, routed, sp_short=True):
        """Retreat procedure [10.1]: away from enemies, unoccupied
        preferred, no prohibited terrain/enemy hexes, no revisits;
        1 SP per hex short [10.1.1] (sp_short=False for the Command
        Breakdown RETREAT [4.7], which is not a rout retreat). Unsteady
        keeps facing; routed faces the retreat direction [10.1]."""
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
        if short > 0 and sp_short:
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
        if t in ("set_pool", "choose_initiative_lim", "activation_choice",
                 "end_activation", "bd_activate", "bd_decline", "non_lim",
                 "pass_non_lim"):
            return self._apply_cmd(side, action)
        pid = str(action["unit"])
        u = self.unit(pid)
        result = {"unit": pid}
        act = self.s.get("act") if self._cmd else None
        budget = act["budget"].get(pid) if act else None
        avoid = bool(act and act["atype"] == "limited")
        if t == "move":
            dest = action["dest"]
            reach = self.reachable(pid, budget=budget, avoid_adjacent=avoid)
            facing = action.get("facing")
            if facing is None:      # cheapest facing at the destination
                facing = min(((v[0], k[2]) for k, v in reach.items()
                              if (k[0], k[1]) == (int(dest[0]),
                                                  int(dest[1]))))[1]
            facing = int(facing)
            cost, path, dis_events = reach[
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

    def _apply_cmd(self, side, action):
        """Command-flow transitions [3.0/4.0]; every cascade (draws,
        rolls, breakdown results) lands in the returned result dict and
        is therefore in the log, replayable from the seed."""
        t = action["type"]
        out = {}
        if t == "set_pool":
            lims = list(action["lims"])
            self.s["pool_decl"][side] = lims
            out["declared"] = {"side": side, "lims": lims,
                               "cite": "A15.1 voluntary pool"}
            if len(self.s["pool_decl"]) == len(self.game.side_order):
                self._both_pools_declared(out)
            else:
                self.s["mover"] = self._enemy(side)
            return out
        if t == "choose_initiative_lim":
            ref = action["lim"]
            self.s["pool"].remove(ref)
            out["initiative_lim"] = {"lim": ref, "cite": "3.0.A.3/4.4"}
            self.s["phase"] = "activation"
            self._open_lim(ref, out)
            return out
        if t == "activation_choice":
            act = self.s["act"]
            dk = action.get("division") if act["kind"] == "independent" \
                else act["div"]
            out["choice"] = {"div": dk, "choice": action["choice"]}
            self._resolve_choice(dk, action["choice"], out)
            return out
        if t == "end_activation":
            act = self.s["act"]
            if act["pending"] == "choice":
                if act["kind"] == "independent":
                    out["note"] = "remaining independent leaders " \
                                  "declined (they may act in the " \
                                  "Non-LIM Phase [A4.3.2])"
                else:
                    out["note"] = "activation attempt declined [4.5.1]"
                self._draw_next(out)
                return out
            self._close_division(out)
            return out
        if t == "bd_activate":
            act = self.s["act"]
            act["div"] = action["division"]
            act["pending"] = "choice"
            out["breakdown_take"] = {"div": act["div"], "cite": "4.7"}
            return out
        if t == "bd_decline":
            out["breakdown_declined"] = {"side": side,
                                         "cite": "4.7 + designer Q&A "
                                                 "(optional)"}
            self._draw_next(out)
            return out
        if t == "non_lim":
            if action.get("division"):
                dk = action["division"]
                self.s["nonlim_used"][side].append(dk)
                self.s["act"] = {"lim": None, "side": side,
                                 "kind": "nonlim_div", "div": dk,
                                 "pending": None, "atype": None,
                                 "stage": None, "incommand": [],
                                 "budget": {}, "indep": None,
                                 "prior_bd": None, "bd_after": None}
                self.s["phase"] = "activation"
                self._open_activation(dk, "limited", out)
                out["cite"] = "3.0.C.1/4.6.2.a"
                return out
            pid = str(action["unit"])
            u = self.unit(pid)
            self.s["nonlim_used"][side].append(f"u:{pid}")
            self.s["act"] = {"lim": None, "side": side,
                             "kind": "nonlim_unit", "div": None,
                             "pending": None, "atype": "limited",
                             "stage": "move", "incommand": [pid],
                             "budget": {pid: float(int(u["ma"]) // 3)},
                             "indep": None, "prior_bd": None,
                             "bd_after": None}
            self.s["phase"] = "activation"
            self.s["moved"] = []
            self.s["returned"] = []
            self.s["turn_units"] = sorted(set(self.s["turn_units"])
                                          | {pid})
            out["single_unit"] = {"unit": pid,
                                  "budget": self.s["act"]["budget"][pid],
                                  "cite": "4.6.2.b: one-third MA "
                                          "(rounded down)"}
            return out
        if t == "pass_non_lim":
            self.s["nonlim_passed"][side] = True
            out["passed"] = side
            self._nonlim_next(out)
            return out
        raise RuntimeError(f"unhandled command action {t}")

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
        if self._cmd and self.s.get("act"):
            self.s["act"]["stage"] = "combat"   # movement is over [4.6.1]
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
        # both sides done: Rout Loss Segment [12.4], then (schema 3) the
        # Fatigue Segment [3.0.D.4], then next turn
        out = {"rout_loss": []}
        for u in self.s["units"].values():
            if self.on_map(u) and u["morale_state"] == "routed":
                sub = {}
                self._lose_sp(u, 1, sub)
                if not u.get("dead"):
                    self._retreat(u, 1, sub, routed=True)
                out["rout_loss"].append({"unit": u["pid"], **sub})
        if self._cmd:
            self._fatigue_segment(out)
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
        self.s["moved"] = []
        self.s["fired"] = []
        self.s["returned"] = []
        self.s["rallied"] = []
        if self._cmd:
            self.s["phase"] = "command"        # Pool Placement [3.0.A]
            self.s["pool_decl"] = {}
            self.s["pool"] = []
            self.s["initiative"] = None
            self.s["act"] = None
            self.s["act_count"] = {}
            self.s["arty_used"] = {}
            self.s["turn_units"] = []
            self.s["ooc"] = []
            self.s["nonlim_used"] = {s_: [] for s_ in self.game.side_order}
            self.s["nonlim_passed"] = {s_: False
                                       for s_ in self.game.side_order}
        else:
            self.s["phase"] = "movement"
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
        out = {"mode": "napoleonic",
               "turn": self.s["turn"], "turn_label": self.turn_label(),
               "mover": self.s["mover"], "phase": self.s["phase"],
               "moved": list(self.s["moved"]),
               "fired": list(self.s.get("fired", [])),
               "pending_fire": self.s.get("pending_fire"),
               "victory": v,
               "napoleonic": {"units": {
                   u["pid"]: {"facing": u["facing"],
                              "formation": u["formation"],
                              "morale": u.get("morale_state", "good"),
                              "sp": u["sp"], "dead": u.get("dead", False)}
                   for u in self.s["units"].values()}},
               "over": bool(v.get("winner"))
               or self.s["turn"] > self.turns}
        if self._cmd:
            act = self.s.get("act")
            out["command"] = {
                "initiative": self.s.get("initiative"),
                "pool_left": len(self.s.get("pool", [])),
                "pool": list(self.s.get("pool", [])),
                "declared": {s_: s_ in self.s.get("pool_decl", {})
                             for s_ in self.game.side_order},
                "available": {s_: self._available_lims(s_)
                              for s_ in self.game.side_order},
                "act": act,
                "ooc": list(self.s.get("ooc", [])),
                "fatigue": dict(self.s.get("fatigue", {})),
                "act_count": dict(self.s.get("act_count", {})),
                "divisions": {dk: {"leader": d["leader"],
                                   "lim": d["lim"], "side": d["side"],
                                   "breakpoint": self._at_div_breakpoint(dk)}
                              for dk, d in self._divisions().items()},
                "nonlim": {s_: self._nonlim_options(s_)
                           for s_ in self.game.side_order}
                if self.s["phase"] == "non_lim" else None,
            }
        return out

    def legal_moves(self, pid):
        """SG-client contract: {can_act, reasons, budget, dests[], plus
        napoleonic extras (rotations, formations)} — api_legal_sg passes
        dests straight to the map overlay."""
        u = self.unit(pid)
        if self.s.get("pending_fire"):
            return {"can_act": False, "budget": 0, "dests": [],
                    "reasons": ["return-fire decision pending [8.1.2]"]}
        if self.s["phase"] == "rally":
            return {"can_act": False, "budget": 0, "dests": [],
                    "reasons": ["rally phase [12.0]"]}
        budget = None
        avoid = False
        if self._cmd:
            act = self.s.get("act")
            if self.s["phase"] != "activation" or not act \
                    or act.get("pending"):
                return {"can_act": False, "budget": 0, "dests": [],
                        "reasons": ["no activation is open "
                                    f"({self.s['phase']} phase) [3.0]"]}
            if pid not in act["incommand"]:
                return {"can_act": False, "budget": 0, "dests": [],
                        "reasons": ["not In Command of the activated "
                                    "division [4.3.3]"]}
            if act["stage"] == "combat":
                return {"can_act": False, "budget": 0, "dests": [],
                        "reasons": ["the division has opened fire: no "
                                    "more movement [4.6.1]"]}
            budget = act["budget"].get(pid)
            avoid = act["atype"] == "limited"
        elif u["side"] != self.s["mover"]:
            return {"can_act": False, "budget": 0, "dests": [],
                    "reasons": [f"it is {self.s['mover']}'s activation"]}
        if pid in self.s["moved"]:
            return {"can_act": False, "budget": 0, "dests": [],
                    "reasons": ["already acted in this activation"]}
        if u.get("dead") or u.get("morale_state") == "routed":
            return {"can_act": False, "budget": 0, "dests": [],
                    "reasons": ["destroyed" if u.get("dead") else
                                "routed: may not move voluntarily "
                                "[9.2.4]"]}
        reach = self.reachable(pid, budget=budget, avoid_adjacent=avoid)
        best = {}
        rotations = []
        for (c, r, f), (cost, path, dis) in reach.items():
            if (c, r) == (u["col"], u["row"]):
                if f != u["facing"]:
                    rotations.append({"facing": f, "cost": round(cost, 2)})
                continue
            k = (c, r)
            if k not in best or cost < best[k][0]:
                best[k] = (cost, f, bool(dis))
        dests = []
        for (c, r), (cost, f, risk) in best.items():
            x, y = self.game.grid.hex_to_pixel(c, r)
            dests.append({"col": c, "row": r, "x": x, "y": y,
                          "hexnum": self.game.grid.hexnum(c, r),
                          "cost": round(cost, 2), "facing": f,
                          "disorder_risk": risk})
        return {"can_act": True,
                "budget": float(u["ma"]) if budget is None else budget,
                "reasons": [], "dests": sorted(dests,
                                               key=lambda d: d["cost"]),
                "rotations": sorted(rotations, key=lambda r_: r_["cost"]),
                "formations": self._formation_options(u)}

    def _formation_options(self, u):
        out = []
        for name in self.F.defs:
            ok, _ = self._formation_change_ok(u, name)
            if ok:
                out.append(name)
        return out
