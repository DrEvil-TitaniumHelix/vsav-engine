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
        # cavalry class (playbook A8.1) - static scenario data, same
        # non-hashed contract as leader ratings
        self._cavtype = {(u["side"], u["slot"]): u["cav_type"]
                         for u in self.scenario["units"]
                         if u.get("cav_type")}
        self._resolve_tier(tier)
        # phase 4 (tier 2): melee + reaction windows + strategic movement.
        # Tier 1 keeps the phase-3 flow so schema-3 logs replay untouched.
        self._p4 = self._cmd and self.tier >= 2
        self._resume_or_new(self._fresh_seed(seed),
                            required=("units", "moved", "tier", "schema"))
        have = self.s.get("schema", 2)
        if (have >= 3) != self._cmd or (have >= 4) != self._p4:
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
        # Napoleonic family earned tier 2 at phase 4 (fire + command +
        # melee + reactions enforced); tier 3 = tier 2 plus a validated
        # policy AI declared in game.json `policy_ai` (spec #13 - the
        # gate is identical, the AI is an opponent offered on top).
        # Tier 1 = the phase-3 subset (melee/reactions umpired); a tier
        # change starts a new game.
        self.combat = None
        melee = bool((self.game.spec.get("combat_tables") or {})
                     .get("melee"))
        self.tier_earned = (3 if self.game.spec.get("policy_ai")
                            else 2) if melee else 1
        self.tier = self.tier_earned if tier is None \
            else max(1, min(int(tier), self.tier_earned))

    def new_game(self, seed=None):
        seed = self._fresh_seed(seed)
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
        if self._p4:
            self.s["schema"] = 4
            for u in units.values():
                u["blown"] = 0          # Blown level 0/1/2 [8.4.4]
                u["recovery"] = False   # Recovery marker [8.4.5]
            self.s.update({
                "pending_melee": None,  # open shock-combat state machine
                "pending_react": None,  # open reaction window [6.2]
                "reacted": [],          # reaction-fired this activation
                                        # [8.1.3] (return fire = returned)
                "rev_blocked": [],      # reverse-move failures [6.2.5]
                "cc_failed": [],        # reaction-charge failures [6.2.3]
                "defended": [],         # defended in combat this turn
                                        # (blown recovery gate [8.4.5])
                "strat": [],            # divisions under Strategic
                                        # Movement markers [5.2]
                "strat_turn": [],       # divisions that strat-moved this
                                        # turn (fatigue exemption, Fox Q&A)
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

        def _ma(u):
            # Blown cavalry moves at half MA, rounded up [8.4.4]
            if self._p4 and u.get("blown", 0) > 0:
                return -(-int(u["ma"]) // 2)
            return u["ma"]
        act["budget"] = {
            u["pid"]: float(int(_ma(u) * frac) if frac < 1.0
                            else _ma(u)) for u in members}
        self.s["moved"] = []
        self.s["returned"] = []      # once per enemy activation (Q&A)
        if self._p4:
            self._p4_open_act(act)
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
        if self._p4 and act is not None:
            self._strat_close_checks(out)
            if act.get("side"):
                self._strat_proximity_sweep(act["side"], out)
            # Blown Recovery marking [8.4.5]: blown cavalry that
            # neither moved nor defended gets a Recovery marker when
            # its division's activation closes
            for pid in act.get("incommand", []):
                u = self.unit(pid)
                if u["arm"] == "cavalry" and u.get("blown", 0) > 0 \
                        and not u.get("dead") \
                        and pid not in self.s["moved"] \
                        and pid not in self.s.get("defended", []):
                    u["recovery"] = True
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
            if self._p4 and dk in self.s.get("strat_turn", []) \
                    and dk not in self.s["fat_combat"]:
                # 5.2.1 + Fox Q&A: a division whose only action was
                # strategic movement gains no activation fatigue (it
                # MAY still gain it from being attacked = fat_combat).
                # It marched, so it is not an idle rested division
                # either [13.2] - its level simply holds.
                continue
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
    def _near_enemy(self, hexx, dist, side):
        return any(v["side"] != side and v["arm"] != "leader"
                   and self.on_map(v)
                   and self._dist((v["col"], v["row"]), hexx) <= dist
                   for v in self.s["units"].values())

    def _strat_step_ok(self, u, frm, nb):
        """Strategic-movement step duties [5.2.1]: never within 3 hexes
        of an enemy; Road Movement required to enter village/swamp/
        woods or to cross a stream (or wall) hexside."""
        if self._near_enemy(nb, 3, u["side"]):
            return False
        road = self._road(frm, nb)
        using_road = road is not None and \
            self.F.may_road_move(u["formation"])
        if self.hex_terrain(*nb) in ("village", "swamp", "woods") \
                and not using_road:
            return False
        rows, bridge = self._hexside_rows(frm, nb)
        names = [rw[0] if isinstance(rw, tuple) else rw for rw in rows]
        crossing = [n for n in names
                    if n.startswith("stream") or n.startswith("deep")
                    or n == "wall_hexside"]
        if crossing and not (using_road and bridge):
            return False
        return True

    def reachable(self, pid, budget=None, avoid_adjacent=False,
                  strat=False):
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
                if strat and not self._strat_step_ok(u, (c, r),
                                                     tuple(nb)):
                    continue    # strategic movement duties [5.2.1]
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
        # phase-4 windows: an open shock combat or reaction window owns
        # the flow completely - only its decision-maker may submit
        pm = self.s.get("pending_melee")
        if pm:
            return self._propose_melee_window(side, action)
        pr = self.s.get("pending_react")
        if pr:
            return self._propose_react_window(side, action)
        if t in ("melee_return", "melee_no_return", "melee_stand",
                 "melee_withdraw", "square_choice", "reaction_fire",
                 "reaction_move", "reaction_reverse", "reaction_face",
                 "reaction_limber", "reaction_charge", "decline_reaction"):
            return self._v(False, "no shock combat or reaction window "
                                  "is open [6.2/8.2-8.5]")
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
                             avoid_adjacent=False, strat=False):
        """Shared unit-action legality (both schemas). `budget` = the MP
        allowance this activation (None = full MA); `avoid_adjacent` = the
        limited-activation adjacency ban [4.6.2 + designer Q&A]; `strat`
        = the division moves strategically [5.2.1]."""
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
        if strat and t == "move" and u["formation"] == "line":
            return self._v(False, "strategic movement: may not remain "
                                  "in Line - change formation first "
                                  "[5.2.1]")
        if t == "move":
            dest = action.get("dest")
            reach = self.reachable(pid, budget=bud,
                                   avoid_adjacent=avoid_adjacent,
                                   strat=strat)
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
                if self._p4 and act["stage"] == "melee":
                    return self._v(False,
                                   "melee combat has begun: all fire "
                                   "must precede melee [8.1.1]")
                pid = str(action.get("unit"))
                if pid not in act["incommand"]:
                    return self._v(False,
                                   "only In Command units of the "
                                   "activated division act [4.3.3]")
                return self._propose_fire(side, action)
            if self._p4 and t in ("melee", "charge"):
                return self._propose_shock(side, action)
            if self._p4 and t == "declare_strategic":
                return self._propose_strategic(side)
            if t in ("move", "about_face", "change_formation", "slide",
                     "reverse"):
                if act["stage"] == "combat":
                    return self._v(False,
                                   "the division has opened fire: no "
                                   "more movement this activation "
                                   "[4.6.1]")
                if self._p4 and act["stage"] == "melee":
                    return self._v(False,
                                   "melee combat has begun: movement is "
                                   "over [8.1.1/4.6.1]")
                pid = str(action.get("unit"))
                if pid not in act["incommand"]:
                    return self._v(False,
                                   "only In Command units of the "
                                   "activated division act [4.3.3]")
                return self._propose_unit_action(
                    side, action, budget=act["budget"].get(pid),
                    avoid_adjacent=act["atype"] == "limited",
                    strat=bool(act.get("strat")))
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
        if self._p4 and u.get("blown", 0) >= 2:
            return False, "Blown-2 cavalry is always disordered - it " \
                          "may not change formation [8.4.4]"
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
        if self._p4 and self._in_strat(u):
            return self._v(False, "strategic movement: may never "
                                  "initiate combat [5.2.1]")
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
        if self._p4 and self._in_strat(d):
            return self._v(False, "strategic movement: may not Return "
                                  "Fire [5.2.1]")
        if self._p4 and d["arm"].startswith("artillery") \
                and pf["defender"] in self.s.get("reacted", []):
            return self._v(False, "artillery may Reaction Fire OR "
                                  "Return Fire, not both [8.1.4]")
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
        if self._p4 and band not in ("medium", "long"):
            # defending in combat (except medium/long artillery fire)
            # blocks blown recovery [8.4.5]
            self.s["defended"] = sorted(
                set(self.s.get("defended", [])) | {target["pid"]})
            if target.get("blown"):
                target["recovery"] = False
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
        if self._p4 and self._in_strat(u):
            d.append(1)     # Strategic Movement +1 [9.1 panel/5.2.1]
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

    # ---------------------------------------- phase 4: shock combat
    # Bayonet [8.2] / Assault [8.3] / Charge [8.4] run as a state
    # machine in s["pending_melee"]: the engine auto-drives every
    # rolled step and stops only where the DEFENDER owns a decision
    # (return fire, form square, voluntary withdrawal). All rolls are
    # seeded and logged; window-open records list who was entitled to
    # what, so the verifier can prove every opportunity was surfaced.

    def _p4_open_act(self, act):
        """Per-activation phase-4 trackers (schema 4 only)."""
        act["spent"] = {}        # pid -> MPs spent (May Charge [5.1.2])
        act["meleed"] = []       # defender hexes shocked [8.2.1/8.3.1]
        act["attacked_with"] = []   # attacker hexes that declared shock
        act["supported"] = []    # pids that supported an attack
        act["charged"] = []      # defender hexes charged [8.4.2#1]
        self.s["reacted"] = []   # reaction fire, once/activation [8.1.3]
        self.s["rev_blocked"] = []   # failed reverse-move checks [6.2.5]
        self.s["cc_failed"] = []     # failed reaction-charge checks
                                     # [6.2.3: may not try again]

    def _stack(self, c, r, side=None, exclude_leaders=True):
        """Living units in a hex in stable (creation) order. The first
        non-artillery unit is 'top' [7.2/8.5.1] - stack reordering is
        not modelled (documented in rules_scope)."""
        out = [u for u in self.s["units"].values()
               if (u["col"], u["row"]) == (c, r) and self.on_map(u)
               and not (exclude_leaders and u["arm"] == "leader")
               and (side is None or u["side"] == side)]
        return sorted(out, key=lambda u: (u["arm"].startswith("art"),
                                          int(u["pid"])
                                          if u["pid"].isdigit()
                                          else 0, u["pid"]))

    def _top(self, stack):
        return stack[0] if stack else None

    def _cav_class(self, u):
        return self._cavtype.get((u["side"], u["slot"]), "light")

    def _aspect(self, defender, from_hex):
        """Which aspect of `defender` does `from_hex` touch [6.1]."""
        kind = self._kind(defender)
        if kind == "all":
            return "front"
        args = (self.game, defender["col"], defender["row"],
                defender["facing"], kind)
        if tuple(from_hex) in {tuple(h) for h in fm.rear_hexes(*args)}:
            return "rear"
        if tuple(from_hex) in {tuple(h) for h in fm.flank_hexes(*args)}:
            return "flank"
        return "front"

    def _in_strat(self, u):
        dk = self._div_key_of(u)
        return bool(dk and dk in self.s.get("strat", []))

    def _may_initiate_melee(self, u):
        """[6.4.1 / 9.2.3 / 11.1.1]: disordered, unsteady/routed and
        breakpoint units never initiate melee; strat-movement units may
        not initiate combat [5.2.1]."""
        if u.get("dead") or not self.on_map(u):
            return False, "unit is gone"
        if u["morale_state"] in ("unsteady", "routed"):
            return False, f"{u['morale_state']} units may not initiate " \
                          "melee [9.2.3/9.2.4]"
        if u["formation"] == "disorder":
            return False, "disordered units may not initiate melee [6.4.1]"
        if self._at_breakpoint(u):
            return False, "a unit at Breakpoint may never initiate " \
                          "melee [11.1.1]"
        if self._in_strat(u):
            return False, "strategic movement: may never initiate " \
                          "combat [5.2.1]"
        return True, ""

    def _melee_rows_between(self, ahex, dhex):
        """TEC row names the shock crosses: the hexside features plus
        the defender's hex terrain."""
        rows, _bridge = self._hexside_rows(ahex, dhex)
        going_up = self.televation.get(f"{dhex[0]},{dhex[1]}", 0) >= \
            self.televation.get(f"{ahex[0]},{ahex[1]}", 0)
        names = []
        for row in rows:
            if isinstance(row, tuple):
                row = row[0] if going_up else row[1]
            names.append(row)
        terr = self.hex_terrain(*dhex)
        if terr in self._eff_rows():
            names.append(terr)
        return names

    def _eff_rows(self):
        return self.game.spec["formations"]["combat_effects"]["rows"]

    # ---------------------------------------------- shock proposals
    def _propose_shock(self, side, action):
        import melee as melee_mod
        act = self.s["act"]
        t = action["type"]
        if act["atype"] != "full":
            return self._v(False, "only a Full Activation may melee "
                                  "[8.2/8.3/8.4]")
        pid = str(action.get("unit"))
        if pid not in self.s["units"]:
            return self._v(False, f"unknown unit {pid}")
        u = self.unit(pid)
        if pid not in act["incommand"]:
            return self._v(False, "only In Command units of the "
                                  "activated division act [4.3.3]")
        ok, why = self._may_initiate_melee(u)
        if not ok:
            return self._v(False, why)
        tid = str(action.get("target"))
        if tid not in self.s["units"]:
            return self._v(False, f"unknown target {tid}")
        tgt = self.unit(tid)
        if tgt["side"] == side or not self.on_map(tgt) \
                or tgt["arm"] == "leader":
            return self._v(False, "invalid melee target")
        dhex = (tgt["col"], tgt["row"])
        ahex = (u["col"], u["row"])
        if t == "melee":
            if u["arm"] != "infantry":
                return self._v(False, "only infantry conducts Bayonet/"
                                      "Assault combat [8.2/8.3]; cavalry "
                                      "charges [8.4]")
            front = {tuple(h) for h in fm.front_hexes(
                self.game, u["col"], u["row"], u["facing"],
                self._kind(u))}
            if dhex not in front:
                return self._v(False, "defender must be adjacent in the "
                                      "attacker's front hexsides [8.2.1/"
                                      "8.3.1]")
            drm, allowed = melee_mod.terrain_melee_drm(
                self._eff_rows(), self._melee_rows_between(ahex, dhex))
            if not allowed:
                return self._v(False, "melee not allowed across that "
                                      "hexside/terrain [TEC 5.0 Melee "
                                      "'NA']")
            if list(dhex) in act["meleed"] or dhex in \
                    [tuple(h) for h in act["meleed"]]:
                return self._v(False, "that stack has already been "
                                      "meleed this activation [8.2.1#1/"
                                      "8.3.1 Q&A]")
            if list(ahex) in act["attacked_with"] or ahex in \
                    [tuple(h) for h in act["attacked_with"]]:
                return self._v(False, "that stack has already attacked "
                                      "this activation [8.3.1#1]")
            for sp_ in action.get("supports", []):
                ok, why = self._support_ok(str(sp_), dhex, act,
                                           ahex=ahex)
                if not ok:
                    return self._v(False, why)
            return self._v(True)
        # charge [8.4]
        if u["arm"] != "cavalry":
            return self._v(False, "only cavalry charges [8.4]")
        if u.get("blown", 0) > 0:
            return self._v(False, "blown cavalry may not charge [8.4.4]")
        ma = int(u["ma"])
        if act["spent"].get(pid, 0) > ma // 2 + 1e-9:
            return self._v(False, "no May Charge marker: the unit moved "
                                  "more than half its MA [5.1.2]")
        dist = self._dist(ahex, dhex)
        ctype = self._cav_class(u)
        if not melee_mod.charge_range_ok(self.ctables, ctype, dist):
            return self._v(False, f"charge range is 2-4 hexes (never "
                                  f"adjacent); target at {dist} "
                                  "[A8.1.1]")
        clear, why = self._los(ahex, dhex)
        if not clear:
            return self._v(False, f"no LOS to the charge target: {why} "
                                  "[8.4.1]")
        if list(dhex) in act["charged"] or dhex in \
                [tuple(h) for h in act["charged"]]:
            return self._v(False, "that stack has already been charged "
                                  "this activation [8.4.2#1]")
        path = self._charge_path(u, dhex)
        if path is None:
            return self._v(False, "no legal charge path: front-hexside "
                                  "movement over chargeable terrain "
                                  "[8.4.1/8.4.2#2 + TEC Cav Charge]")
        return self._v(True)

    def _support_ok(self, pid, dhex, act, ahex=None):
        """Supporting stack legality [8.2.1#2/8.3.1#2 + Fox Q&A]."""
        if pid not in self.s["units"]:
            return False, f"unknown support {pid}"
        su = self.unit(pid)
        if ahex is not None and (su["col"], su["row"]) == tuple(ahex):
            return False, "the attacking stack may not also support " \
                          "[8.2.1#2]"
        if pid not in act["incommand"]:
            return False, "supports must be In Command active units " \
                          "[4.3.3]"
        ok, why = self._may_initiate_melee(su)
        if not ok:
            return False, f"support {pid}: {why}"
        if self._dist((su["col"], su["row"]), dhex) != 1:
            return False, "supports must be adjacent to the defender " \
                          "[8.2.1#2]"
        front = {tuple(h) for h in fm.front_hexes(
            self.game, su["col"], su["row"], su["facing"],
            self._kind(su))}
        if tuple(dhex) not in front:
            return False, "the defender must be in the supporting " \
                          "stack's front hexsides (Fox Q&A)"
        if pid in act["supported"]:
            return False, "a stack may only support one attack per " \
                          "activation [8.2.1#2]"
        ahx = [tuple(h) for h in act["attacked_with"]]
        if (su["col"], su["row"]) in ahx:
            return False, "an attacking stack may not also support " \
                          "[8.2.1#2]"
        return True, ""

    def _charge_path(self, u, dhex, max_len=8):
        """Charge movement [8.4.2#2]: hex-by-hex toward the target, MPs
        not counted, always entering through a front hexside, at most
        one facing change per hex entered, no prohibited/unchargeable
        terrain, stopping adjacent to the target. BFS over (hex,
        facing); returns the hex path or None."""
        import melee as melee_mod
        from collections import deque
        kind = self._kind(u)
        start = (u["col"], u["row"], u["facing"])
        seen = {start}
        q = deque([(start, [(u["col"], u["row"])])])
        while q:
            (c, r, f), path = q.popleft()
            if self._dist((c, r), dhex) == 1:
                # must be able to put the target in a front hexside
                # (a final one-hexside turn is allowed [8.4.2#2])
                for df in (0, -2, 2):
                    pf = (f + df) % fm.FACINGS
                    fh = {tuple(h) for h in fm.front_hexes(
                        self.game, c, r, pf, kind)}
                    if tuple(dhex) in fh:
                        return path
                continue
            if len(path) > max_len:
                continue
            # advance through the CURRENT facing's front hexside(s),
            # then may turn one hexside (60 deg = 2 facing steps) in
            # the hex entered [8.4.2#2]
            for s_ in fm.facing_sides(f, kind):
                nb = fm.side_neighbor(self.game, c, r, s_)
                if not nb or not self.in_area(*nb):
                    continue
                nb = tuple(nb)
                if nb == tuple(dhex):
                    continue          # stop ADJACENT, not on top
                rows, _ = self._hexside_rows((c, r), nb)
                names = [rw[0] if isinstance(rw, tuple) else rw
                         for rw in rows]
                terr = self.hex_terrain(*nb)
                if terr == "water":
                    continue
                if terr in self._eff_rows():
                    names.append(terr)
                if not melee_mod.terrain_chargeable(self._eff_rows(),
                                                    names):
                    continue
                if self.occupants(*nb):
                    continue          # may not charge through units
                for df in (0, -2, 2):
                    nf = (f + df) % fm.FACINGS
                    node = (nb[0], nb[1], nf)
                    if node in seen:
                        continue
                    seen.add(node)
                    q.append((node, path + [nb]))
        return None

    # ------------------------------------------------ shock machine
    def _apply_shock(self, side, action):
        import melee as melee_mod
        act = self.s["act"]
        act["stage"] = "melee"        # fire before melee [8.1.1]
        pid = str(action["unit"])
        u = self.unit(pid)
        tgt = self.unit(str(action["target"]))
        ahex, dhex = (u["col"], u["row"]), (tgt["col"], tgt["row"])
        out = {}
        if action["type"] == "melee":
            rows = self._melee_rows_between(ahex, dhex)
            defensive = melee_mod.terrain_defensive(self._eff_rows(),
                                                    rows)
            kind = "assault" if defensive else "bayonet"
            attackers = [v["pid"] for v in self._stack(*ahex, side=side)
                         if v["arm"] == "infantry"
                         and self._may_initiate_melee(v)[0]]
            supports = [str(x) for x in action.get("supports", [])]
            act["meleed"].append(list(dhex))
            act["attacked_with"].append(list(ahex))
            act["supported"].extend(supports)
            pm = {"kind": kind, "side": side,
                  "dside": tgt["side"], "ahex": list(ahex),
                  "dhex": list(dhex), "attackers": attackers,
                  "supports": supports, "stage": "attacker_check",
                  "round": 0, "returned_units": [], "charge": None}
            out["shock"] = {"kind": kind, "attackers": attackers,
                            "supports": supports, "defenders":
                            [v["pid"] for v in self._stack(
                                *dhex, side=tgt["side"])],
                            "cite": "8.2.1" if kind == "bayonet"
                            else "8.3.1",
                            "terrain_rows": rows}
        else:                          # charge [8.4.2]
            path = self._charge_path(u, dhex)
            act["charged"].append(list(dhex))
            act["attacked_with"].append(list(ahex))
            if pid not in self.s["moved"]:
                self.s["moved"].append(pid)
            pm = {"kind": "charge", "side": side, "dside": tgt["side"],
                  "ahex": [u["col"], u["row"]], "dhex": list(dhex),
                  "attackers": [pid], "supports": [],
                  "stage": "formation_check", "round": 0,
                  "returned_units": [],
                  "charge": {"dist": self._dist(ahex, dhex),
                             "ctype": self._cav_class(u),
                             "from": list(ahex),
                             "path": [list(p) for p in path]}}
            out["shock"] = {"kind": "charge", "unit": pid,
                            "target": tgt["pid"], "path": pm["charge"]
                            ["path"], "ctype": pm["charge"]["ctype"],
                            "dist": pm["charge"]["dist"],
                            "cite": "8.4.2"}
            # charge movement executes hex by hex, MPs not counted;
            # it triggers reactions - even on zone entry [6.2.1] -
            # from everyone EXCEPT the target stack (whose responses
            # are the machine's own steps)
            walk = {"path_left": [list(p) for p in path[1:]],
                    "final_facing": u["facing"], "nmc": 0,
                    "dis_left": [], "cost": 0.0, "full_cost": 0.0,
                    "charge": True, "pm": pm}
            # _walk_move starts the charge machine itself when the walk
            # completes [8.4.2#3]; if a reaction window interrupted, the
            # resumed walk starts it later (_close_react)
            self._walk_move(u, walk, out)
            return out
        self.s["pending_melee"] = pm
        self._book_strat_strip(pm)
        # any routed defender is automatically eliminated [8.2.1#1/
        # 8.3.1#1/8.4.2#4]
        for v in self._stack(*dhex, side=pm["dside"]):
            if v["morale_state"] == "routed":
                self._destroy(v, out, "routed unit meleed [8.2.1#1]")
        self._shock_run(pm, out)
        return out

    def _start_charge_machine(self, pm, out):
        """The charger has arrived adjacent: face the target and run
        the charge steps [8.4.2#3-9]."""
        u = self.unit(pm["attackers"][0])
        dhex = tuple(pm["dhex"])
        kindf = self._kind(u)
        for df in (0, -1, 1, 2, -2):
            pf = (u["facing"] + df) % fm.FACINGS
            fh = {tuple(h) for h in fm.front_hexes(
                self.game, u["col"], u["row"], pf, kindf)}
            if dhex in fh:
                u["facing"] = pf
                break
        pm["ahex"] = [u["col"], u["row"]]
        self.s["pending_melee"] = pm
        self._book_strat_strip(pm)
        for v in self._stack(*dhex, side=pm["dside"]):
            if v["morale_state"] == "routed":
                self._destroy(v, out, "routed unit charged [8.4.2#4]")
        self._shock_run(pm, out)

    def _shock_run(self, pm, out):
        """Drive the machine until a defender decision or completion."""
        while True:
            stage = pm["stage"]
            if stage == "attacker_check":
                if not self._shock_attacker_check(pm, out):
                    return self._shock_finish(pm, out)
                pm["stage"] = "return_window"
                continue
            if stage == "formation_check":
                # charge step 4: infantry may Stand or try to Form
                # Square [8.4.2#4]; artillery alone must stand;
                # strategic movement may not form square [5.2.1] - its
                # infantry Stands (with the pre-melee check) forced
                dstack = self._stack(*pm["dhex"], side=pm["dside"])
                if not dstack:
                    return self._shock_finish(pm, out, advance=True)
                inf = [v for v in dstack if v["arm"] == "infantry"]
                if inf and self._in_strat(inf[0]):
                    self._stand_check(inf[0], pm, out)
                    pm["stage"] = "return_window"
                    continue
                if inf:
                    self._open_window(pm, "square_window", out,
                                      entitled={inf[0]["pid"]:
                                                ["square_choice"]},
                                      cite="8.4.2#4")
                    return
                pm["stage"] = "return_window"
                continue
            if stage == "return_window":
                ent = self._return_entitled(pm)
                if not ent:
                    pm["stage"] = "defender_check" \
                        if pm["kind"] != "charge" else "melee_round"
                    continue
                self._open_window(pm, "return_window", out,
                                  entitled=ent, cite="8.2.1#3/8.3.1#3/"
                                  "8.4.2#5")
                return
            if stage == "defender_check":
                self._shock_defender_check(pm, out)
                if pm["kind"] == "bayonet":
                    # bayonet has no melee round [8.2.1 steps panel]
                    return self._shock_finish(pm, out)
                pm["stage"] = "melee_round"
                continue
            if stage == "melee_round":
                res = self._melee_round(pm, out)
                if res == "continue":
                    pm["stage"] = "continue_def"
                    continue
                return self._shock_finish(
                    pm, out, advance=res == "defender_gone")
            if stage in ("continue_def", "continue_att"):
                who = pm["dside"] if stage == "continue_def" \
                    else pm["side"]
                hexx = pm["dhex"] if stage == "continue_def" \
                    else pm["ahex"]
                stack = self._stack(*hexx, side=who)
                if not stack:
                    return self._shock_finish(
                        pm, out, advance=stage == "continue_def")
                self._open_window(
                    pm, stage, out,
                    entitled={self._top(stack)["pid"]:
                              ["melee_stand", "melee_withdraw"]},
                    cite="8.5.3 voluntary rout option")
                return
            raise RuntimeError(f"unknown shock stage {stage}")

    def _open_window(self, pm, stage, out, entitled, cite):
        """The honesty record: every window logs who was entitled to
        which decisions before anyone acts."""
        pm["stage"] = stage
        owner = pm["dside"] if stage != "continue_att" else pm["side"]
        pm["window_owner"] = owner
        pm["entitled"] = {k: list(v) for k, v in entitled.items()}
        out.setdefault("windows", []).append(
            {"stage": stage, "owner": owner, "entitled": pm["entitled"],
             "cite": cite})

    def _shock_attacker_check(self, pm, out):
        """Steps 8.2.1#2/8.3.1#2. Returns False if the attack ends."""
        stack = [self.unit(p) for p in pm["attackers"]
                 if not self.unit(p).get("dead")]
        if not stack:
            return False
        top = self._top(self._stack(*pm["ahex"], side=pm["side"]))
        if top is None or top["pid"] not in pm["attackers"]:
            top = stack[0]
        drms, detail = self._preshock_drms(top, "attacker", pm)
        die = self.roll_d10()
        import melee as melee_mod
        eff = melee_mod.pre_shock_attacker(die, top["morale"], drms)
        rec = {"unit": top["pid"], "die": die, "drms": detail,
               "vs": top["morale"], "result": eff["kind"],
               "cite": "8.2/8.3 Pre-Shock (attacker)"}
        out.setdefault("attacker_check", rec)
        if self._cmd:
            self._mark_combat_fatigue(top)
        if eff["kind"] == "may_melee":
            return True
        if eff.get("disorder"):
            self._disorder(top)
            rec["disordered"] = True
        if eff.get("levels"):
            i = self._LADDER.index(top["morale_state"])
            self._set_morale_state(
                top, self._LADDER[min(3, i + eff["levels"])], out)
        return False

    def _return_entitled(self, pm):
        """Who may return fire inside the melee window [8.2.1#3/
        8.3.1#3/8.4.2#5]: top defending unit plus one stacked battery
        [7.2], each under the once-per-activation caps [8.1.2/8.1.4];
        skirmishers may Reaction Move out instead [8.2.1#3]; strategic
        movement units never [5.2.1]; charge: only stacks that stood or
        formed square, with the charger in their front [8.4.2#5]."""
        atk = self._top(self._stack(*pm["ahex"], side=pm["side"]))
        if atk is None:
            return {}
        ent = {}
        dstack = self._stack(*pm["dhex"], side=pm["dside"])
        if pm["kind"] == "charge" and pm.get("square_failed"):
            return {}
        troops = [v for v in dstack
                  if not v["arm"].startswith("artillery")]
        arts = [v for v in dstack if v["arm"].startswith("artillery")]
        cands = troops[:1] + arts[:1]
        for v in cands:
            if self._in_strat(v):
                continue
            kinds = []
            ok, _ = self._fire_capable(v)
            if ok and v["pid"] not in self.s["returned"] \
                    and not (v["arm"].startswith("artillery")
                             and v["pid"] in self.s["reacted"]):
                front = {tuple(h) for h in fm.front_hexes(
                    self.game, v["col"], v["row"], v["facing"],
                    self._kind(v))}
                if (atk["col"], atk["row"]) in front and \
                        self._dist((v["col"], v["row"]),
                                   (atk["col"], atk["row"])) <= \
                        self._fire_range(v):
                    kinds.append("melee_return")
            if v["formation"] == "skirmish" and pm["kind"] != "charge":
                if self._skirmish_moves(v):
                    kinds.append("reaction_move")
            if kinds:
                ent[v["pid"]] = kinds
        return ent

    def _skirmish_moves(self, v):
        """Adjacent hexes a skirmisher may Reaction Move to [6.2.2/
        8.2.1#3]: stacking-legal, not adjacent to an enemy."""
        outs = []
        for nb in self.game.neighbors(v["col"], v["row"]):
            nb = tuple(nb)
            if not self.in_area(*nb) or self.hex_terrain(*nb) == "water":
                continue
            cell = self.F.entry(v, self.hex_terrain(*nb))
            if cell is None or cell.prohibited:
                continue
            if not self._stack_ok(v, *nb):
                continue
            adj_enemy = any(
                w["side"] != v["side"] and w["arm"] != "leader"
                and self.on_map(w)
                and self._dist((w["col"], w["row"]), nb) <= 1
                for w in self.s["units"].values())
            if adj_enemy:
                continue
            outs.append(nb)
        return outs

    def _shock_defender_check(self, pm, out):
        """Step 8.2.1#4 / 8.3.1#4: artillery alone dies; every defender
        checks; retreat kills unlimbered guns, limbered guns retreat."""
        import melee as melee_mod
        dstack = self._stack(*pm["dhex"], side=pm["dside"])
        recs = []
        troops = [v for v in dstack
                  if not v["arm"].startswith("artillery")]
        if not troops:
            for v in dstack:
                self._destroy(v, out,
                              "artillery defending alone in melee "
                              "[8.2.1#4/8.3.1#5]")
            out["defender_check"] = recs
            return
        for v in list(dstack):
            if v["arm"].startswith("artillery"):
                continue
            drms, detail = self._preshock_drms(v, "defender", pm)
            die = self.roll_d10()
            eff = melee_mod.pre_shock_defender(die, v["morale"], drms)
            rec = {"unit": v["pid"], "die": die, "drms": detail,
                   "vs": v["morale"], "result": eff["kind"]}
            recs.append(rec)
            if self._cmd:
                self._mark_combat_fatigue(v)
            self.s["defended"] = sorted(set(self.s.get("defended", []))
                                        | {v["pid"]})
            if eff["kind"] == "stand":
                continue
            self._lose_sp(v, eff["sp"], out)
            if v.get("dead"):
                continue
            if eff.get("disorder"):
                self._disorder(v)
            if eff.get("rout"):
                self._set_morale_state(v, "routed", out)
                self._capture_rout_path(v, pm, out)
            elif eff.get("levels"):
                i = self._LADDER.index(v["morale_state"])
                self._set_morale_state(
                    v, self._LADDER[min(3, i + eff["levels"])], out)
                if eff.get("retreat") and not v.get("dead") \
                        and (v["col"], v["row"]) == tuple(pm["dhex"]):
                    self._retreat(v, 1, out, routed=False)
        # defenders driven out: unlimbered artillery dies, limbered may
        # retreat [8.2.1#4]
        if not [v for v in self._stack(*pm["dhex"], side=pm["dside"])
                if not v["arm"].startswith("artillery")]:
            for v in list(self._stack(*pm["dhex"], side=pm["dside"])):
                if v["formation"] == "unlimbered":
                    self._destroy(v, out, "unlimbered artillery "
                                          "abandoned in melee [8.2.1#4]")
                else:
                    self._retreat(v, 1, out, routed=False)
        out["defender_check"] = recs
        self._strat_combat_penalty(pm, out)

    def _stand_check(self, u, pm, out):
        """Defender Pre-Melee Morale Check for a stack that Stands
        against a charge (or must - strat movement / errata's declined
        countercharge) [8.4.2#4 + errata 2000-07-20]."""
        import melee as melee_mod
        drms, detail = self._preshock_drms(u, "defender", pm)
        die = self.roll_d10()
        eff = melee_mod.pre_shock_defender(die, u["morale"], drms)
        rec = {"unit": u["pid"], "die": die, "drms": detail,
               "vs": u["morale"], "result": eff["kind"],
               "cite": "8.4.2#4 Stand"}
        out.setdefault("stand_check", rec)
        if eff["kind"] == "stand":
            return
        self._lose_sp(u, eff["sp"], out)
        if u.get("dead"):
            return
        if eff.get("disorder"):
            self._disorder(u)
        if eff.get("rout"):
            self._set_morale_state(u, "routed", out)
            self._capture_rout_path(u, pm, out)
        elif eff.get("levels"):
            i = self._LADDER.index(u["morale_state"])
            self._set_morale_state(
                u, self._LADDER[min(3, i + eff["levels"])], out)
            if eff.get("retreat") and not u.get("dead"):
                self._retreat(u, 1, out, routed=False)

    def _capture_rout_path(self, u, pm, out):
        """Remember a routed defender's retreat path for pursuit
        [8.4.2#8] - read back from the effect record just written."""
        for e in reversed(out.get("effects", [])):
            if e.get("unit") == u["pid"] and "retreat" in e:
                pm.setdefault("rout_paths", {})[u["pid"]] = \
                    [tuple(p) for p in e["retreat"]]
                return

    def _preshock_drms(self, u, role, pm):
        """Pre-Shock Morale Check Table DRMs (charts p4), as printed -
        no borrowing from the 9.1 list."""
        d, detail = [], {}

        def add(k, v):
            d.append(v)
            detail[k] = v
        dstack = self._stack(*pm["dhex"], side=pm["dside"])
        dtop = self._top(dstack)
        if role == "attacker":
            if dtop is not None:
                asp = self._aspect(dtop, pm["ahex"])
                if asp == "rear":
                    add("attacking_from_rear", -3)
                elif asp == "flank":
                    add("attacking_from_flank", -2)
                if dtop["formation"] == "skirmish":
                    add("defenders_are_skirmishers", -1)
            n = len(pm["supports"])
            if n:
                add("supporting_stacks", -1 * n)
            if self._leader_here(u):
                add("leader_in_hex", -1)
            if u.get("elite"):
                add("elite", -1)
            if u["formation"] == "line":
                add("in_line", 1)
            if u["morale_state"] == "shaken":
                add("shaken", 1)
            if u["formation"] == "disorder":
                add("disordered", 1)
            return d, detail
        asp = self._aspect(u, pm["ahex"])
        if asp == "rear":
            add("attacked_in_rear", 3)
        elif asp == "flank":
            add("attacked_in_flank", 1)
        if u["formation"] == "skirmish":
            add("in_skirmish_order", 3)
        if pm["kind"] != "assault":     # flank support NOT vs assault
            n = self._flank_supports(u)
            if n:
                add("flank_support", -1 * n)
        if self._leader_here(u):
            add("leader_in_hex", -1)
        if u.get("elite"):
            add("elite", -1)
        if u["formation"] == "square":
            add("in_square", -2)
        if u["formation"] == "line":
            add("in_line", 1)
        if u["morale_state"] == "shaken":
            add("shaken", 1)
        if u["formation"] == "disorder":
            add("disordered", 1)
        if u["morale_state"] == "unsteady":
            add("unsteady", 2)
        if self._in_strat(u):
            add("strategic_movement", 2)
        import melee as melee_mod
        if melee_mod.terrain_defensive(
                self._eff_rows(),
                self._melee_rows_between(pm["ahex"], pm["dhex"])):
            add("defensive_terrain", -1)
        return d, detail

    def _leader_here(self, u):
        return any(v["arm"] == "leader" and v["side"] == u["side"]
                   and (v["col"], v["row"]) == (u["col"], u["row"])
                   and self.on_map(v)
                   for v in self.s["units"].values())

    def _flank_supports(self, u):
        """Non-routed friendly combat units adjacent to a flank hexside
        [8.2.1#4 Flank Support]."""
        kind = self._kind(u)
        if kind == "all":
            return 0
        fl = {tuple(h) for h in fm.flank_hexes(
            self.game, u["col"], u["row"], u["facing"], kind)}
        n = 0
        for v in self.s["units"].values():
            if v["side"] != u["side"] or v["arm"] == "leader" \
                    or not self.on_map(v) or v["pid"] == u["pid"]:
                continue
            if (v["col"], v["row"]) in fl \
                    and v["morale_state"] != "routed":
                n += 1
        return n

    def _melee_round(self, pm, out):
        """One Melee Result Table round [8.3.1#5 / 8.4.2#6 / 8.5].
        Returns 'continue' / 'defender_gone' / 'attacker_gone' /
        'done'."""
        import melee as melee_mod
        astack = [v for v in self._stack(*pm["ahex"], side=pm["side"])
                  if v["pid"] in pm["attackers"]
                  and not v["arm"].startswith("artillery")]
        dstack = self._stack(*pm["dhex"], side=pm["dside"])
        dtroops = [v for v in dstack
                   if not v["arm"].startswith("artillery")]
        if not dtroops:
            for v in dstack:
                if v["formation"] == "unlimbered":
                    self._destroy(v, out, "artillery alone in melee "
                                          "[8.3.1#5]")
                else:
                    self._retreat(v, 1, out, routed=False)
            return "defender_gone"
        if not astack:
            return "attacker_gone"
        pm["round"] += 1
        charging = pm["kind"] == "charge" and pm["round"] == 1
        att_sp = melee_mod.melee_sp(
            [(v["sp"], v["arm"], v["formation"],
              pm["kind"] == "charge") for v in astack])
        def_sp = melee_mod.melee_sp(
            [(v["sp"], v["arm"], v["formation"], False)
             for v in dtroops])
        drms, detail = self._melee_drms(pm, astack, dtroops,
                                        att_sp, def_sp,
                                        charge_bonus_on=charging)
        die = self.roll_d10()
        res = melee_mod.resolve_melee(self.ctables, die, sum(drms))
        rec = {"round": pm["round"], "die": die, "drms": detail,
               "att_sp": att_sp, "def_sp": def_sp,
               "modified": res["modified"], "loser": res["loser"],
               "cite": "8.5"}
        out.setdefault("melee_rounds", []).append(rec)
        for v in astack + dtroops:
            self.s["defended"] = sorted(
                set(self.s.get("defended", []))
                | ({v["pid"]} if v in dtroops else set()))
            if self._cmd:
                self._mark_combat_fatigue(v)
        if res["loser"] == "both":      # melee continues [8.5.3]
            for stack in (astack, dtroops):
                top = stack[0]
                self._lose_sp(top, 1, out)
                if not top.get("dead"):
                    self._morale_check(top, 0, out)
            a_left = [v for v in self._stack(*pm["ahex"],
                                             side=pm["side"])
                      if v["pid"] in pm["attackers"]]
            d_left = [v for v in self._stack(*pm["dhex"],
                                             side=pm["dside"])
                      if not v["arm"].startswith("artillery")]
            if not d_left:
                return "defender_gone"
            if not a_left:
                return "attacker_gone"
            return "continue"
        loser_stack = astack if res["loser"] == "attacker" else dtroops
        top = loser_stack[0]
        self._lose_sp(top, res["sp"], out)
        if not top.get("dead"):
            if res["morale"]["kind"] == "rout":
                self._set_morale_state(top, "routed", out)
                if res["loser"] == "defender":
                    self._capture_rout_path(top, pm, out)
            else:
                i = self._LADDER.index(top["morale_state"])
                self._set_morale_state(
                    top, self._LADDER[min(3, i + res["morale"]
                                          ["levels"])], out)
            # 'Retreat' = one extra Unsteady-style retreat (errata
            # 2000-07-20, AUS-MEL-2) on top of any morale retreat
            if res["other"] == "retreat" and not top.get("dead"):
                self._retreat(top, 1, out, routed=False)
        self._strat_combat_penalty(pm, out)
        if res["loser"] == "defender":
            d_left = [v for v in self._stack(*pm["dhex"],
                                             side=pm["dside"])
                      if not v["arm"].startswith("artillery")]
            if not d_left:
                return "defender_gone"
        else:
            a_left = [v for v in self._stack(*pm["ahex"],
                                             side=pm["side"])
                      if v["pid"] in pm["attackers"]]
            if not a_left:
                return "attacker_gone"
        return "continue"

    def _melee_drms(self, pm, astack, dtroops, att_sp, def_sp,
                    charge_bonus_on):
        """Melee Die Roll Modifiers (charts p4), each recorded."""
        import melee as melee_mod
        d, detail = [], {}

        def add(k, v):
            if v:
                d.append(v)
                detail[k] = v
        atop, dtop = astack[0], dtroops[0]
        tdrm, _ = melee_mod.terrain_melee_drm(
            self._eff_rows(),
            self._melee_rows_between(pm["ahex"], pm["dhex"]))
        add("terrain", tdrm)
        asp = self._aspect(dtop, pm["ahex"])
        if asp == "rear":
            add("attacking_rear", 2)
        elif asp == "flank":
            add("attacking_flank", 1)
        if self._in_strat(dtop):
            add("defender_strategic_movement", 2)
        if dtop["arm"] == "cavalry" and dtop.get("blown", 0) > 0:
            add("defender_blown_cavalry", 1)
        # square: pick the formation most favorable to the DEFENDER
        # when formations are mixed (errata 6.5.6 principle)
        if any(v["formation"] == "square" for v in dtroops):
            add("vs_square", -3 if atop["arm"] == "cavalry" else -1)
        if charge_bonus_on:
            ch = pm["charge"]
            bonus = melee_mod.charge_bonus(
                self.ctables, ch["ctype"], dist=ch["dist"],
                vs_square=any(v["formation"] == "square"
                              for v in dtroops),
                in_column=atop["formation"] == "column",
                countercharger_bonus=ch.get("cc_bonus", 0))
            add("charge_bonus", bonus)
        # fatigue melee DRM [13.3]: against the fatigued side
        if self._cmd:
            for stack, sign, key in ((astack, 1, "attacker_fatigue"),
                                     (dtroops, -1, "defender_fatigue")):
                dk = self._div_key_of(stack[0])
                lvl = self.s.get("fatigue", {}).get(dk, 0)
                m = 0
                if lvl >= 8:
                    m = -2
                elif lvl >= 6:
                    m = -1
                add(key, m * sign)
        # Napoleon / Murat [charts p4] - not present in A15.1, but the
        # rule is data-driven on leader slots
        for v in self.s["units"].values():
            if v["arm"] == "leader" and self.on_map(v):
                if v["slot"] == "Napoleon" and \
                        (v["col"], v["row"]) in (tuple(pm["ahex"]),
                                                 tuple(pm["dhex"])):
                    add("napoleon", 2 if v["side"] == pm["side"] else -2)
                if v["slot"] == "Murat" and pm["kind"] == "charge" \
                        and (v["col"], v["row"]) == tuple(pm["ahex"]):
                    add("murat_charging", 1)
        add("size_ratio", melee_mod.size_ratio_drm(att_sp, def_sp))
        return d, detail

    def _strat_combat_penalty(self, pm, out):
        """5.2.1: a strat-movement defender loses the marker after all
        combat is completed. Booked at declaration (_book_strat_strip)
        so a routed/eliminated defender still costs the division its
        marker; this re-check only catches units that entered the hex
        mid-combat."""
        dtop = self._top(self._stack(*pm["dhex"], side=pm["dside"]))
        dk = dtop and self._div_key_of(dtop)
        if dk and dk in self.s.get("strat", []):
            pm["strat_strip"] = dk

    def _book_strat_strip(self, pm):
        """Record the defending division's 5.2.1 marker forfeit when the
        attack is DECLARED - the penalty applies even if every defender
        routs or dies before the combat completes."""
        dtop = self._top(self._stack(*pm["dhex"], side=pm["dside"]))
        dk = dtop and self._div_key_of(dtop)
        if dk and dk in self.s.get("strat", []):
            pm["strat_strip"] = dk

    def _shock_finish(self, pm, out, advance=False):
        """Close the combat: advance [8.3.1#7], charge pursuit/advance
        [8.4.2#8], blown markers [8.4.2#9], strat marker strip."""
        if pm["kind"] == "charge":
            self._charge_finish(pm, out, advance)
        elif advance and pm["kind"] == "assault":
            self._advance_attackers(pm, out)
        if pm.get("strat_strip"):
            dk = pm["strat_strip"]
            if dk in self.s["strat"]:
                self.s["strat"].remove(dk)
                out["strategic_marker_removed"] = {
                    "div": dk, "cite": "5.2.1 (attacked: marker removed "
                    "after combat)"}
        self.s["pending_melee"] = None
        out["shock_over"] = {"kind": pm["kind"], "rounds": pm["round"]}
        return None

    def _advance_attackers(self, pm, out):
        """Attacker advance [8.3.1#7]: mandatory, into the vacated hex."""
        moved = []
        for p in pm["attackers"]:
            v = self.unit(p)
            if v.get("dead") or (v["col"], v["row"]) != tuple(pm["ahex"]):
                continue
            if v["morale_state"] in ("unsteady", "routed"):
                continue
            v["col"], v["row"] = pm["dhex"]
            moved.append(p)
        if moved:
            out["advance"] = {"units": moved, "into": pm["dhex"],
                              "cite": "8.3.1#7"}

    def _charge_finish(self, pm, out, advance):
        """Charge steps 8-9: pursuit check vs routed opponents, else
        advance; charger disordered + Blown-2 [8.4.2#8-9]."""
        import melee as melee_mod
        charger = self.unit(pm["attackers"][0])
        routed_defs = [self.unit(p) for p in pm.get("rout_paths", {})
                       if not self.unit(p).get("dead")]
        if not charger.get("dead") \
                and charger["morale_state"] not in ("unsteady",
                                                    "routed"):
            if routed_defs:
                pu = routed_defs[0]
                drms, detail = [], {}
                ct = pm["charge"]["ctype"]
                if ct in ("light", "lancer"):
                    drms.append(1)
                    detail["light_or_lancer"] = 1
                if ct == "cossack":
                    drms.append(3)
                    detail["cossack"] = 3
                if self._leader_here(charger):
                    drms.append(-2)
                    detail["commander_in_hex"] = -2
                die = self.roll_d10()
                hexes = melee_mod.pursuit(die, charger["morale"], drms)
                rec = {"die": die, "drms": detail,
                       "vs": charger["morale"], "hexes": hexes,
                       "cite": "8.4.2#8"}
                out["pursuit"] = rec
                if hexes:
                    path = pm["rout_paths"][pu["pid"]][:hexes]
                    stepped = 0
                    for hx in path:
                        if not self.in_area(*hx) or \
                                self.hex_terrain(*hx) == "water":
                            break
                        charger["col"], charger["row"] = hx
                        stepped += 1
                        self._lose_sp(pu, 1, out)      # 1 SP per hex
                        if pu.get("dead"):
                            break
                    rec["pursued"] = stepped
                    self._disorder(charger)
            elif advance and not self._stack(*pm["dhex"],
                                             side=pm["dside"]):
                charger["col"], charger["row"] = pm["dhex"]
                out["advance"] = {"units": [charger["pid"]],
                                  "into": pm["dhex"], "cite": "8.4.2#8"}
        # step 9: charging cavalry disordered + Blown-2 [8.4.2#9]
        if not charger.get("dead"):
            self._disorder(charger)
            charger["blown"] = 2
            charger["recovery"] = False
            out["blown"] = {"unit": charger["pid"], "level": 2,
                            "cite": "8.4.2#9"}

    # ----------------------------------------- shock window actions
    def _propose_melee_window(self, side, action):
        pm = self.s["pending_melee"]
        t = action.get("type")
        owner = pm.get("window_owner")
        if side != owner:
            return self._v(False, f"the {pm['stage']} decision belongs "
                                  f"to {owner} [8.2-8.5]")
        ent = pm.get("entitled", {})
        if pm["stage"] == "square_window":
            if t != "square_choice":
                return self._v(False, "stand or form square: "
                                      "square_choice {form: bool} "
                                      "[8.4.2#4]")
            pid = str(action.get("unit") or next(iter(ent)))
            if pid not in ent:
                return self._v(False, "not the checking unit")
            return self._v(True)
        if pm["stage"] == "return_window":
            if t == "melee_no_return":
                return self._v(True)
            if t == "reaction_move":
                pid = str(action.get("unit"))
                if pid not in ent or "reaction_move" not in ent[pid]:
                    return self._v(False, "that unit may not reaction "
                                          "move [6.2.2/8.2.1#3]")
                dest = action.get("dest")
                if not dest or tuple(dest) not in \
                        self._skirmish_moves(self.unit(pid)):
                    return self._v(False, "illegal skirmish reaction "
                                          "move destination [6.2.2]")
                return self._v(True)
            if t != "melee_return":
                return self._v(False, "melee_return / reaction_move / "
                                      "melee_no_return [8.2.1#3]")
            pid = str(action.get("unit"))
            if pid not in ent or "melee_return" not in ent.get(pid, []):
                return self._v(False, "that unit may not return fire "
                                      "here [8.1.2/8.1.4/7.2]")
            return self._v(True)
        if pm["stage"] in ("continue_def", "continue_att"):
            if t not in ("melee_stand", "melee_withdraw"):
                return self._v(False, "melee continues: melee_stand or "
                                      "melee_withdraw (voluntary rout) "
                                      "[8.5.3]")
            return self._v(True)
        return self._v(False, f"no action fits stage {pm['stage']}")

    def _apply_melee_window(self, side, action):
        pm = self.s["pending_melee"]
        t = action["type"]
        out = {}
        if t == "square_choice":
            pid = str(action.get("unit")
                      or next(iter(pm["entitled"])))
            u = self.unit(pid)
            if action.get("form"):
                import melee as melee_mod
                drms, detail = [], {}
                if pm["charge"]["dist"] == 2:
                    drms.append(1)
                    detail["cavalry_2_hexes_away"] = 1
                if self._leader_here(u):
                    drms.append(-2)
                    detail["leader_in_hex"] = -2
                if u["formation"] == "column":
                    drms.append(-1)
                    detail["in_column"] = -1
                elif u["formation"] == "line":
                    drms.append(1)
                    detail["in_line"] = 1
                elif u["formation"] == "skirmish":
                    drms.append(4)
                    detail["in_skirmish"] = 4
                die = self.roll_d10()
                eff = melee_mod.form_square(die, u["morale"], drms)
                rec = {"unit": pid, "die": die, "drms": detail,
                       "vs": u["morale"], "result": eff["kind"],
                       "cite": "8.4.2#4"}
                out["form_square"] = rec
                if eff["kind"] == "square_formed":
                    u["formation"] = "square"
                    if u["facing"] % 2 == 0:
                        u["facing"] = (u["facing"] + 1) % fm.FACINGS
                else:
                    self._disorder(u)
                    pm["square_failed"] = True
                    if eff.get("levels"):
                        i = self._LADDER.index(u["morale_state"])
                        self._set_morale_state(
                            u, self._LADDER[min(3, i + eff["levels"])],
                            out)
            else:
                self._stand_check(u, pm, out)   # [8.4.2#4 Stand]
            pm["stage"] = "return_window"
            self._shock_run(pm, out)
            return out
        if t == "melee_return":
            pid = str(action["unit"])
            v = self.unit(pid)
            atk = self._top(self._stack(*pm["ahex"], side=pm["side"]))
            self.s["returned"].append(pid)
            rec, eff = self._resolve_shot(v, atk)
            out["melee_return"] = rec
            self._apply_effect(atk, eff, out)
            pm["returned_units"].append(pid)
            pm["entitled"].pop(pid, None)
            # the attack ends if the attacking stack is broken
            # [8.2.1#3: survives without becoming Unsteady or Routed]
            atk2 = [self.unit(p) for p in pm["attackers"]]
            alive = [a for a in atk2 if not a.get("dead")
                     and a["morale_state"] not in ("unsteady", "routed")
                     and (a["col"], a["row"]) == tuple(pm["ahex"])]
            if not alive:
                out["attack_broken"] = {"cite": "8.2.1#3/8.3.1#3"}
                return self._finish_from_window(pm, out) or out
            if not pm["entitled"]:
                self._advance_stage_after_return(pm, out)
            return out
        if t == "reaction_move":
            pid = str(action["unit"])
            v = self.unit(pid)
            dest = tuple(action["dest"])
            v["col"], v["row"] = dest
            out["skirmish_reaction_move"] = {
                "unit": pid, "dest": list(dest), "cite": "8.2.1#3"}
            # vacated: the attacker advances, sequence over [8.2.1#3]
            if not self._stack(*pm["dhex"], side=pm["dside"]):
                self._advance_attackers(pm, out)
                return self._finish_from_window(pm, out) or out
            pm["entitled"].pop(pid, None)
            if not pm["entitled"]:
                self._advance_stage_after_return(pm, out)
            return out
        if t == "melee_no_return":
            self._advance_stage_after_return(pm, out)
            return out
        if t in ("melee_stand", "melee_withdraw"):
            if t == "melee_withdraw":
                hexx = pm["dhex"] if pm["stage"] == "continue_def" \
                    else pm["ahex"]
                who = pm["dside"] if pm["stage"] == "continue_def" \
                    else pm["side"]
                for v in list(self._stack(*hexx, side=who)):
                    if v["arm"].startswith("artillery"):
                        continue
                    self._set_morale_state(v, "routed", out)
                out["voluntary_rout"] = {"side": who, "cite": "8.5.3"}
                adv = pm["stage"] == "continue_def"
                self._shock_finish(pm, out, advance=adv)
                return out
            if pm["stage"] == "continue_def":
                pm["stage"] = "continue_att"
            else:
                pm["stage"] = "melee_round"
            self._shock_run(pm, out)
            return out
        raise RuntimeError(f"unhandled melee window action {t}")

    def _advance_stage_after_return(self, pm, out):
        pm["stage"] = "defender_check" if pm["kind"] != "charge" \
            else "melee_round"
        self._shock_run(pm, out)

    def _finish_from_window(self, pm, out):
        self._shock_finish(pm, out)
        return None

    # ------------------------------------ phase 4: strategic movement
    def _propose_strategic(self, side):
        """Declare Strategic Movement for the activated division [5.2]:
        full activation, before anything else has acted."""
        act = self.s["act"]
        if act["atype"] != "full" or not act.get("div"):
            return self._v(False, "strategic movement requires a "
                                  "division Full Activation [5.2]")
        if act["div"] in self.s["strat"]:
            return self._v(False, "the division already carries a "
                                  "Strategic Movement marker [5.2]")
        if self.s["moved"] or act["stage"] != "move":
            return self._v(False, "strategic movement must be declared "
                                  "before the division acts [5.2.1: "
                                  "never both strategic and regular "
                                  "movement]")
        return self._v(True)

    def _apply_strategic(self, side):
        act = self.s["act"]
        dk = act["div"]
        self.s["strat"].append(dk)
        self.s["strat_turn"] = sorted(set(self.s["strat_turn"]) | {dk})
        act["strat"] = True
        for pid in act["incommand"]:
            u = self.unit(pid)
            if u["arm"] != "leader":
                act["budget"][pid] = float(int(u["ma"]) * 2)   # [5.2]
        return {"strategic_movement": {
            "div": dk, "budgets": dict(act["budget"]),
            "cite": "5.2: double MA; no combat or reactions; must keep "
                    "3 hexes from the enemy; road movement required "
                    "into village/woods/swamp and over stream/wall"}}

    def _strat_proximity_sweep(self, acted_side, out):
        """5.2.1: a marked division loses its marker once enemy combat
        units have finished an activation (combat included) within 3
        hexes of any of its units."""
        for dk in list(self.s.get("strat", [])):
            if self._divisions()[dk]["side"] == acted_side:
                continue        # only ENEMY activations strip it
            if self._enemies_within(dk, 3):
                self.s["strat"].remove(dk)
                out.setdefault("strategic_markers_lost", []).append(
                    {"div": dk, "cite": "5.2.1 (enemy finished an "
                     "activation within 3 hexes)"})

    def _strat_close_checks(self, out):
        """End-of-activation duties for a strat-moving division:
        must-move-as-far-as-possible [5.2.1#4, Fox's liberal reading]
        and the no-Line rule; violation = marker stripped (the LIM-
        removal penalty is moot under A15.1's voluntary pool)."""
        act = self.s.get("act")
        if not act or not act.get("strat"):
            return
        dk = act["div"]
        violated = None
        for pid in act["incommand"]:
            u = self.unit(pid)
            if u["arm"] == "leader" or u.get("dead"):
                continue
            if u["formation"] == "line":
                violated = f"{pid} remained in Line [5.2.1]"
                break
            left = act["budget"].get(pid, 0) - act["spent"].get(pid, 0)
            if left >= 1 and pid not in self.s["moved"]:
                if self.reachable(pid, budget=left, strat=True):
                    violated = f"{pid} did not move as far as " \
                               "possible [5.2.1#4]"
                    break
        if violated and dk in self.s["strat"]:
            self.s["strat"].remove(dk)
            out["strategic_violation"] = {
                "div": dk, "why": violated,
                "cite": "5.2.1#4 + Fox Q&A (liberal reading: only "
                        "unforced shortfalls are punished)"}

    # ------------------------------- phase 4: reaction windows [6.2]
    # The NON-active player acts during the active player's movement.
    # Movement executes hex by hex; each step computes who may react
    # BEFORE the step (MP expenditure inside a zone) and AFTER it
    # (entry into a zone). A non-empty window logs its entitlements
    # (the honesty record) and hands the flow to the reacting side
    # until every reactor has acted or declined; then the walk resumes.

    _ZONE_ALL = ("skirmish",)          # all-around zones [6.2.2]

    def _zone(self, e):
        """Reaction Zone hexes of enemy unit `e` [6.2 + 6.3 diagrams]:
        front-adjacent for formed units, all-around for skirmishers and
        lone leaders; limbered foot artillery has none [6.2.4]."""
        if e["arm"] == "leader":
            alone = len(self.occupants(e["col"], e["row"])) == 1
            if not alone:
                return set()
            return {tuple(h) for h in
                    self.game.neighbors(e["col"], e["row"])}
        if e["morale_state"] == "routed":
            return set()               # non-routed units only [6.2]
        if e["formation"] == "skirmish":
            return {tuple(h) for h in
                    self.game.neighbors(e["col"], e["row"])}
        if e["arm"].startswith("artillery"):
            if e["formation"] != "unlimbered" and \
                    not (e["arm"] == "artillery_horse"):
                return set()           # limbered foot: no zone [6.2.4]
        kind = self._kind(e)
        if kind == "all":
            return {tuple(h) for h in
                    self.game.neighbors(e["col"], e["row"])}
        return {tuple(h) for h in fm.front_hexes(
            self.game, e["col"], e["row"], e["facing"], kind)}

    def _flank_zone(self, e):
        """Cavalry Flank Zone [6.2.3]: extends from the flank
        hexsides."""
        if e["arm"] != "cavalry" or e["morale_state"] == "routed" \
                or e["formation"] == "disorder":
            return set()               # disordered cavalry has no
                                       # flank reaction zone [6.4.1]
        kind = self._kind(e)
        if kind == "all":
            return set()
        return {tuple(h) for h in fm.flank_hexes(
            self.game, e["col"], e["row"], e["facing"], kind)}

    def _react_kinds(self, e, mover, at_hex, phase, charge=False):
        """Which reactions may `e` take against `mover` at `at_hex`
        right now. phase: 'pre' = MP spent inside the zone, 'post' =
        entry into the zone."""
        if e.get("dead") or not self.on_map(e):
            return []
        if e["side"] == mover["side"]:
            return []
        if self._in_strat(e):
            return []                  # no reactions in strat move
        kinds = []
        zone = self._zone(e)
        in_zone = tuple(at_hex) in zone
        if e["arm"] == "leader":
            if in_zone and self._leader_alone(e) \
                    and self._reaction_moves(e):
                kinds.append("reaction_move")   # any number [6.2.7]
            return kinds
        if e["formation"] == "skirmish":
            if in_zone:                # entry OR expenditure [6.2.2]
                if e["pid"] not in self.s["reacted"] \
                        and self._fire_capable(e)[0]:
                    kinds.append("reaction_fire")
                if self._reaction_moves(e):
                    kinds.append("reaction_move")
            return kinds
        if e["arm"] == "infantry":
            # expenditure only - entry alone does NOT trigger [6.2.1];
            # charge moves trigger on any movement in the zone
            if in_zone and (phase == "pre" or charge) \
                    and e["pid"] not in self.s["reacted"] \
                    and self._fire_capable(e)[0]:
                kinds.append("reaction_fire")
            return kinds
        if e["arm"].startswith("artillery"):
            if not in_zone:
                return []
            horse = e["arm"] == "artillery_horse"
            if e["formation"] == "unlimbered":
                used = e["pid"] in self.s["reacted"] or \
                    e["pid"] in self.s["returned"]
                if not used and self._fire_capable(e)[0]:
                    kinds.append("reaction_fire")   # once [6.2.4/8.1.4]
                if horse and not used and mover["arm"] != "cavalry":
                    kinds.append("reaction_limber")  # [6.2.5]
            elif horse:               # limbered horse: reverse [6.2.5]
                if e["pid"] not in self.s.get("rev_blocked", []) \
                        and self._reverse_dest(e):
                    kinds.append("reaction_reverse")
            return kinds
        if e["arm"] == "cavalry":
            if e["morale_state"] == "unsteady":
                return []              # may not reaction charge [9.2.3]
            if mover["arm"] in ("infantry",) or \
                    mover["arm"].startswith("artillery"):
                if in_zone:
                    if self._reverse_dest(e):
                        kinds.append("reaction_reverse")   # [6.2.3]
                    okc, _ = self._may_initiate_melee(e)
                    if okc and not e.get("blown", 0) \
                            and e["pid"] not in \
                            self.s.get("cc_failed", []):
                        kinds.append("reaction_charge")    # [6.2.3]
            # cavalry movement never triggers reaction charges (Fox
            # Q&A); countercharge exists only against charges [8.4.2#3]
            if phase == "post" and tuple(at_hex) in self._flank_zone(e):
                kinds.append("reaction_face")              # [6.2.3]
            return kinds
        return kinds

    def _leader_alone(self, e):
        return len(self.occupants(e["col"], e["row"])) == 1

    def _reaction_moves(self, e):
        """Legal reaction-move destinations (skirmisher/leader): any
        adjacent stacking-legal hex not adjacent to an enemy [6.2.2/
        6.2.7]."""
        return self._skirmish_moves(e)

    def _reverse_dest(self, e):
        """Reverse Movement in Reaction [6.2.6]: one hex through a rear
        hexside, keeping facing; never into a prohibited hex, an
        enemy-adjacent hex or an occupied hex (Fox Q&A)."""
        kind = self._kind(e)
        if kind == "all":
            return None
        rears = fm.rear_hexes(self.game, e["col"], e["row"],
                              e["facing"], kind)
        for h in rears:
            h = tuple(h)
            if not self.in_area(*h) or self.hex_terrain(*h) == "water":
                continue
            cell = self.F.entry(e, self.hex_terrain(*h))
            if cell is None or cell.prohibited:
                continue
            if self.occupants(*h):
                continue
            if self._near_enemy(h, 1, e["side"]):
                continue
            return h
        return None

    def _collect_window(self, mover, at_hex, phase, charge=False,
                        exclude_hex=None):
        ent = {}
        for e in self.s["units"].values():
            if exclude_hex and (e["col"], e["row"]) == exclude_hex:
                continue        # the charge target reacts through the
                                # machine's own steps [8.4.2#3-5]
            ks = self._react_kinds(e, mover, at_hex, phase,
                                   charge=charge)
            if ks:
                ent[e["pid"]] = ks
        return ent

    def _open_react(self, mover, ent, phase, out, walk=None):
        pr = {"side": self._enemy(mover["side"]), "mover": mover["pid"],
              "mover_side": mover["side"],
              "at": [mover["col"], mover["row"]], "phase": phase,
              "entitled": ent, "declined": [], "walk": walk}
        self.s["pending_react"] = pr
        out.setdefault("reaction_windows", []).append(
            {"at": pr["at"], "phase": phase, "owner": pr["side"],
             "entitled": {k: list(v) for k, v in ent.items()},
             "cite": "6.2 (window logged = opportunity surfaced)"})

    # ------------------------------ the stepwise move walk (schema 4)
    def _facing_toward(self, frm, to, kind):
        fx, fy = self.game.grid.hex_to_pixel(*frm)
        tx, ty = self.game.grid.hex_to_pixel(*to)
        ang = math.degrees(math.atan2(tx - fx, -(ty - fy))) % 360
        f = int(round(ang / 30.0)) % 12
        if kind == "vertex" and f % 2 == 0:
            f = (f + 1) % fm.FACINGS
        if kind == "hexside" and f % 2 == 1:
            f = (f + 1) % fm.FACINGS
        return f

    def _walk_move(self, u, walk, out):
        """Execute the remaining steps of a move, opening reaction
        windows as triggers arise. walk = {path_left, facing, nmc,
        dis_left, cost, [charge], [pm]}. Returns True when the move is
        finished."""
        act = self.s.get("act")
        chg = bool(walk.get("charge"))
        excl = tuple(walk["pm"]["dhex"]) if walk.get("pm") else None
        while walk["path_left"]:
            frm = (u["col"], u["row"])
            nxt = tuple(walk["path_left"][0])
            # PRE window: spending MPs inside enemy zones [6.2.1]
            ent = self._collect_window(u, frm, "pre", charge=chg,
                                       exclude_hex=excl)
            ent = self._filter_declined(ent, walk)
            if ent:
                self._open_react(u, ent, "pre", out, walk=walk)
                return False
            if not chg:
                sc, dis, nmc = self.step_cost(u, frm, nxt, walk["nmc"])
                walk["nmc"] = nmc
                walk["cost"] += sc or 0
            u["col"], u["row"] = nxt
            kind = self._kind(u)
            u["facing"] = self._facing_toward(frm, nxt, kind)
            walk["path_left"] = walk["path_left"][1:]
            # movement-disorder events land at their recorded hexes
            walk["dis_left"], rolls = self._apply_dis_events(
                u, walk["dis_left"], nxt)
            if rolls:
                out.setdefault("disorder", []).extend(rolls)
            # POST window: entry into enemy zones [6.2.2/6.2.4/6.2.3]
            ent = self._collect_window(u, nxt, "post", charge=chg,
                                       exclude_hex=excl)
            ent = self._filter_declined(ent, walk)
            if ent:
                self._open_react(u, ent, "post", out, walk=walk)
                return False
        if walk.get("pm"):
            self._start_charge_machine(walk["pm"], out)
            return True
        u["facing"] = walk["final_facing"]
        if act is not None and "spent" in act:
            act["spent"][u["pid"]] = act["spent"].get(u["pid"], 0) + \
                max(walk["cost"], walk.get("full_cost", 0))
        out["move_complete"] = {"unit": u["pid"],
                                "at": [u["col"], u["row"]],
                                "facing": u["facing"]}
        return True

    def _filter_declined(self, ent, walk):
        """A reactor that declined once during this move is not
        re-prompted at later steps (its later opportunities are logged
        as declined-in-advance)."""
        dec = walk.get("declined_all", [])
        return {k: v for k, v in ent.items() if k not in dec}

    def _apply_dis_events(self, u, dis_left, at_hex):
        rolls = []
        keep = []
        for kind, c, r in dis_left:
            if (c, r) != tuple(at_hex):
                keep.append((kind, c, r))
                continue
            if u["formation"] == "disorder":
                continue
            if kind == "auto":
                self._disorder(u)
                rolls.append({"at": [c, r], "auto": True})
            else:
                v = self.roll_d10()
                failed = v > u["morale"]
                if failed:
                    self._disorder(u)
                rolls.append({"at": [c, r], "roll": v,
                              "vs_morale": u["morale"],
                              "disordered": failed})
        return keep, rolls

    # ------------------------------------- reaction window actions
    def _propose_react_window(self, side, action):
        pr = self.s["pending_react"]
        t = action.get("type")
        if side != pr["side"]:
            return self._v(False, f"the reaction window belongs to "
                                  f"{pr['side']} [6.2]")
        if t == "decline_reaction":
            return self._v(True)
        pid = str(action.get("unit"))
        if pid not in pr["entitled"]:
            return self._v(False, "that unit is not entitled to react "
                                  "in this window [6.2]")
        if t not in pr["entitled"][pid]:
            return self._v(False, f"{t} is not among that unit's "
                                  f"reactions here: "
                                  f"{pr['entitled'][pid]} [6.2]")
        if t == "reaction_move":
            dest = action.get("dest")
            if not dest or tuple(dest) not in \
                    self._reaction_moves(self.unit(pid)):
                return self._v(False, "illegal reaction-move "
                                      "destination [6.2.2/6.2.7]")
        if t == "reaction_face":
            df = int(action.get("turn", 2))
            if df not in (2, -2):
                return self._v(False, "reaction facing change is one "
                                      "hexside [6.2.3]")
        return self._v(True)

    def _apply_react_window(self, side, action):
        pr = self.s["pending_react"]
        t = action["type"]
        mover = self.unit(pr["mover"])
        out = {}
        walk = pr.get("walk")
        if t == "decline_reaction":
            if walk is not None:
                walk.setdefault("declined_all", []).extend(
                    pr["entitled"].keys())
            out["reactions_declined"] = list(pr["entitled"].keys())
            return self._close_react(pr, mover, out)
        pid = str(action["unit"])
        e = self.unit(pid)
        before = (mover["morale_state"], mover.get("dead", False),
                  mover["col"], mover["row"])
        if t == "reaction_fire":
            self.s["reacted"].append(pid)
            rec, eff = self._resolve_shot(e, mover)
            out["reaction_fire"] = rec
            self._apply_effect(mover, eff, out)
            pr["entitled"].pop(pid, None)
        elif t == "reaction_move":
            e["col"], e["row"] = tuple(action["dest"])
            out["reaction_move"] = {"unit": pid,
                                    "dest": [e["col"], e["row"]],
                                    "cite": "6.2.2/6.2.7"}
            pr["entitled"].pop(pid, None)
        elif t == "reaction_limber":
            self.s["reacted"].append(pid)   # counts as its reaction
            e["formation"] = "limbered"
            if e["facing"] % 2 == 1:
                e["facing"] = (e["facing"] + 1) % fm.FACINGS
            out["reaction_limber"] = {"unit": pid, "cite": "6.2.5"}
            pr["entitled"].pop(pid, None)
        elif t == "reaction_reverse":
            dest = self._reverse_dest(e)
            rec = {"unit": pid, "dest": dest and list(dest),
                   "cite": "6.2.6"}
            if e["arm"] == "artillery_horse" \
                    and e["formation"] != "unlimbered":
                die = self.roll_d10()
                rec["disorder_check"] = {"die": die,
                                         "vs": e["morale"]}
                if die > e["morale"]:   # artillery never disorders,
                    # but a failure ends its reverse moves [6.2.5]
                    self.s.setdefault("rev_blocked", []).append(pid)
                    rec["blocked"] = True
            if dest and not rec.get("blocked"):
                e["col"], e["row"] = dest
            out["reaction_reverse"] = rec
            pr["entitled"].pop(pid, None)
            if e.get("blown"):
                e["recovery"] = False   # reaction move strips it
                                        # [8.4.5]
        elif t == "reaction_face":
            df = int(action.get("turn", 2))
            e["facing"] = (e["facing"] + df) % fm.FACINGS
            out["reaction_face"] = {"unit": pid,
                                    "facing": e["facing"],
                                    "cite": "6.2.3 (free movement)"}
            pr["entitled"].pop(pid, None)
        elif t == "reaction_charge":
            pr["entitled"].pop(pid, None)
            drms, detail = self._preshock_drms(
                e, "attacker",
                {"kind": "reaction_charge", "supports": [],
                 "ahex": [e["col"], e["row"]],
                 "dhex": [mover["col"], mover["row"]],
                 "dside": mover["side"]})
            die = self.roll_d10()
            import melee as melee_mod
            eff = melee_mod.pre_shock_attacker(die, e["morale"], drms)
            rec = {"unit": pid, "die": die, "drms": detail,
                   "vs": e["morale"], "result": eff["kind"],
                   "cite": "6.2.3 (reaction charges DO take the "
                           "pre-melee check - Fox Q&A)"}
            out["reaction_charge_check"] = rec
            if eff["kind"] != "may_melee":
                # failure = immediately disordered, no charge [6.2.3]
                self._disorder(e)
                self.s.setdefault("cc_failed", []).append(pid)
                rec["disordered"] = True
            else:
                # the reacting cavalry becomes the ATTACKER [6.2.3];
                # the mover's movement is over whatever happens (Fox)
                self.s["pending_react"] = None
                if walk is not None:
                    out["movement_ended"] = {
                        "unit": mover["pid"],
                        "cite": "Fox Q&A: reaction-charged movement "
                                "ends"}
                pm = {"kind": "charge", "side": e["side"],
                      "dside": mover["side"],
                      "ahex": [e["col"], e["row"]],
                      "dhex": [mover["col"], mover["row"]],
                      "attackers": [pid], "supports": [],
                      "stage": "formation_check", "round": 0,
                      "returned_units": [],
                      "charge": {"dist": None,
                                 "ctype": self._cav_class(e),
                                 "from": [e["col"], e["row"]],
                                 "path": [], "reaction": True}}
                self.s["pending_melee"] = pm
                self._book_strat_strip(pm)
                out["reaction_charge"] = {
                    "unit": pid, "target_hex": pm["dhex"],
                    "cite": "6.2.3/8.4 (charge bonus applies; "
                            "may NOT be countercharged)"}
                self._shock_run(pm, out)
                return out
        # window continues while entitlements remain; else resume
        if pr["entitled"]:
            changed = (mover["morale_state"], mover.get("dead", False),
                       mover["col"], mover["row"]) != before
            if changed and walk is not None:
                out["movement_ended"] = {
                    "unit": mover["pid"],
                    "why": "state changed by the reaction"}
                self.s["pending_react"] = None
                return out
            return out
        return self._close_react(pr, mover, out)

    def _close_react(self, pr, mover, out):
        self.s["pending_react"] = None
        walk = pr.get("walk")
        if walk is None:
            return out
        if mover.get("dead") or mover["morale_state"] in ("unsteady",
                                                          "routed"):
            out["movement_ended"] = {
                "unit": mover["pid"],
                "why": f"mover is "
                       f"{'dead' if mover.get('dead') else mover['morale_state']}"}
            return out
        self._walk_move(mover, walk, out)
        return out

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
        if t in ("melee", "charge"):
            return self._apply_shock(side, action)
        if t in ("melee_return", "melee_no_return", "melee_stand",
                 "melee_withdraw", "square_choice") or \
                (t == "reaction_move" and self.s.get("pending_melee")):
            return self._apply_melee_window(side, action)
        if t in ("reaction_fire", "reaction_move", "reaction_reverse",
                 "reaction_face", "reaction_limber", "reaction_charge",
                 "decline_reaction"):
            return self._apply_react_window(side, action)
        if t == "declare_strategic":
            return self._apply_strategic(side)
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
        strat = bool(act and act.get("strat"))
        if t == "move":
            dest = action["dest"]
            reach = self.reachable(pid, budget=budget, avoid_adjacent=avoid,
                                   strat=strat)
            facing = action.get("facing")
            if facing is None:      # cheapest facing at the destination
                facing = min(((v[0], k[2]) for k, v in reach.items()
                              if (k[0], k[1]) == (int(dest[0]),
                                                  int(dest[1]))))[1]
            facing = int(facing)
            cost, path, dis_events = reach[
                (int(dest[0]), int(dest[1]), facing)]
            if self._p4:
                # schema 4: the move executes hex by hex, opening
                # reaction windows as it triggers them [6.2]
                result.update(cost=round(cost, 2),
                              path=[list(p) for p in path],
                              facing=facing)
                walk = {"path_left": [list(p) for p in path[1:]],
                        "final_facing": facing, "nmc": 0,
                        "dis_left": list(dis_events), "cost": 0.0,
                        "full_cost": cost}
                done = self._walk_move(u, walk, result)
                if not done:
                    result["interrupted"] = {
                        "at": [u["col"], u["row"]],
                        "cite": "6.2 reaction window"}
                self.s["moved"].append(pid)
                return result
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
        if self._p4 and act is not None and "spent" in act:
            # May Charge bookkeeping [5.1.2]: moves record their MP
            # cost; other actions their TEC cost (slide/reverse are
            # priced as the full budget - conservative, they end most
            # units' movement anyway)
            if t == "move":
                spent = result.get("cost", 0)
            elif t in ("about_face", "change_formation"):
                spent = self.F.action_cost(u, t, u["ma"]) or 0
            else:
                spent = float(u["ma"])
            act["spent"][pid] = act["spent"].get(pid, 0) + spent
        if self._p4 and t in ("about_face", "change_formation",
                              "slide", "reverse"):
            # spending MPs inside an enemy Reaction Zone triggers
            # reactions - including a formation change in an enemy
            # front hex (Fox Q&A) [6.2.1/6.2.2]
            ent = self._collect_window(u, (u["col"], u["row"]), "pre")
            if ent:
                self._open_react(u, ent, "pre", result, walk=None)
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
            if self._p4:
                self._p4_open_act(self.s["act"])
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
        if self._p4:
            # Blown Recovery [8.4.5]: Recovery markers come off and the
            # Blown level drops one in the Rally Phase
            rec = []
            for u in self.s["units"].values():
                if u.get("recovery") and not u.get("dead"):
                    u["blown"] = max(0, u.get("blown", 0) - 1)
                    u["recovery"] = False
                    rec.append({"unit": u["pid"], "blown": u["blown"]})
            if rec:
                out["blown_recovery"] = rec
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
        if self._p4:
            self.s["pending_melee"] = None
            self.s["pending_react"] = None
            self.s["reacted"] = []
            self.s["defended"] = []
            self.s["strat_turn"] = []
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
    def decider(self):
        """The side whose decision the game is waiting on RIGHT NOW.
        Open windows override the mover: shock windows [8.2-8.5],
        reaction windows [6.2], the return-fire decision [8.1.2];
        otherwise the mover (which the command flow keeps pointed at
        the acting side through every phase [3.0/4.0])."""
        pm = self.s.get("pending_melee")
        if pm and pm.get("window_owner"):
            return pm["window_owner"]
        pr = self.s.get("pending_react")
        if pr:
            return pr["side"]
        pf = self.s.get("pending_fire")
        if pf:
            return pf["defender_side"]
        return self.s["mover"]

    def flow(self):
        v = self.s.get("victory") or self._victory_state()
        out = {"mode": "napoleonic",
               "rules_scope": self.rules_scope(),
               "turn": self.s["turn"], "turn_label": self.turn_label(),
               "mover": self.s["mover"], "phase": self.s["phase"],
               "decider": self.decider(),
               "moved": list(self.s["moved"]),
               "fired": list(self.s.get("fired", [])),
               "pending_fire": self.s.get("pending_fire"),
               "victory": v,
               "napoleonic": {"units": {
                   u["pid"]: {"facing": u["facing"],
                              "formation": u["formation"],
                              "morale": u.get("morale_state", "good"),
                              "sp": u["sp"], "dead": u.get("dead", False),
                              "slot": u["slot"],
                              **({"blown": u["blown"]}
                                 if u.get("blown") else {})}
                   for u in self.s["units"].values()}},
               "over": bool(v.get("winner"))
               or self.s["turn"] > self.turns}
        if self._p4:
            pmelee = self.s.get("pending_melee")
            preact = self.s.get("pending_react")
            out["shock"] = pmelee and {
                "kind": pmelee["kind"], "stage": pmelee["stage"],
                "owner": pmelee.get("window_owner"),
                "entitled": pmelee.get("entitled", {}),
                "ahex": pmelee["ahex"], "dhex": pmelee["dhex"],
                "attackers": pmelee["attackers"]}
            out["reaction"] = preact and {
                "owner": preact["side"], "mover": preact["mover"],
                "at": preact["at"], "phase": preact["phase"],
                "entitled": preact["entitled"]}
            # legal reaction-move destinations for the client [6.2.2]
            if pmelee:
                md = {p: [list(h) for h in
                          self._skirmish_moves(self.unit(p))]
                      for p, ks in (pmelee.get("entitled") or {}).items()
                      if "reaction_move" in ks}
                if md:
                    out["shock"]["move_dests"] = md
            if preact:
                md = {p: [list(h) for h in
                          self._reaction_moves(self.unit(p))]
                      for p, ks in preact["entitled"].items()
                      if "reaction_move" in ks}
                if md:
                    out["reaction"]["move_dests"] = md
            out["strat_divs"] = list(self.s.get("strat", []))
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
        if self.s.get("pending_melee") or self.s.get("pending_react"):
            return {"can_act": False, "budget": 0, "dests": [],
                    "reasons": ["a shock combat / reaction window is "
                                "open [6.2/8.2-8.5]"]}
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
        act_s = self.s.get("act") if self._cmd else None
        reach = self.reachable(pid, budget=budget, avoid_adjacent=avoid,
                               strat=bool(act_s and act_s.get("strat")))
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
