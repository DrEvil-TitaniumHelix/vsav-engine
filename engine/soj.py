"""
soj.py - The Siege of Jerusalem (AH 1989) legality gate. Tier-1 scope.

The Assault of Gallus introductory scenario: free deployment (Judaeans in the
New City crescent / on the North Wall, minimum-force strongpoints; Romans
outside, >= 5 hexes from any Elevated hex), per-class TEC movement with
wall/staircase/gate entry rules, SoJ zones of control, stacking, hex control
[18.3] and the ten-Built-up-hex Roman victory check, Giora-faction dice
reinforcement. Combat/rally systems are transcribed in game.json
`combat_draft` but NOT enforced here yet (tier 1): the Fire, Melee and Rally
phases pass through as umpired phases. Spec #12: the melee/missile/breach
tables ship as an enforcing gate only after validate_combat.py holds them to
worked examples + the official Q&A.

Every rule enforced below carries its rulebook citation. Authority note: the
two official Q&A documents contradict each other once (rout out of Roman
Heavy-Infantry ground ZOC: Question Box "Yes", 1/6/1992 typescript "No");
the later ruling is enforced - see game.json source_defects.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gate import GateGame  # noqa: E402

ELEVATED = {"north_wall", "wall", "bastion", "fort", "fortress",
            "gate", "gate_north_wall", "gate_wall"}
GATES = {"gate", "gate_north_wall", "gate_wall"}
STRONGPOINTS = {"bastion", "fort", "fortress"}
GROUND = {"clear", "slope", "breach"}          # [2.12]; builtup is its own class [2.13]

# TEC infantry ground costs [TEC]; builtup is side-dependent [8.95]
INF_COST = {"clear": 1.0, "slope": 3.0}
CAV_COST = {"clear": 1.0, "slope": 7.0}
SE_COST = {"clear": 1.0, "slope": 3.0}


class SoJGame(GateGame):
    HASH_KEYS = ("units", "turn", "phase", "seed", "rng_calls", "control",
                 "pool", "entry_queue", "deploy_done")
    TURN_NOUN = "turn"
    PHASE_FIELD = "phase"

    # phase cycle after deployment (turn advances after jud_melee) [4.x]
    PHASES = ["rom_rally", "rom_fire", "rom_move", "rom_melee",
              "jud_rally", "jud_fire", "jud_move", "jud_melee"]

    def __init__(self, game, scenario_path, live_dir, seed=None, tier=None):
        super().__init__(game, scenario_path, live_dir)
        self._resolve_tier(tier)
        self.types = game.spec["unit_types"]
        self.terr = game.terrain          # gamespec loads terrain.json
        self._index_terrain()
        self._resume_or_new(self._fresh_seed(seed),
                            required=("units", "phase", "control", "pool"))

    # ------------------------------------------------------------ terrain
    def _index_terrain(self):
        """Hex classes, staircase/entrance hexsides, the playable area and
        the deployment zones - all derived from terrain.json + scenario."""
        th = self.terr["hexes"]
        self.hex_t = {k: v["t"] for k, v in th.items()}
        self.hex_name = {k: v.get("name", k) for k, v in th.items()}
        self.name_hex = {v: k for k, v in self.hex_name.items()}
        self.stairs = set()
        self.entrances = set()
        for k, v in self.terr.get("sides", {}).items():
            if v.get("staircase"):
                self.stairs.add(tuple(sorted(k.split("|"))))
            if v.get("entrance"):
                self.entrances.add(tuple(sorted(k.split("|"))))
        self.new_city = set(self.terr["areas"]["new_city"])
        dep = self.scenario["deployment"]
        self.min_force = [self.name_hex[n] for n in dep["min_force_hexes"]]
        self.rom_prohibited = {self.name_hex[n]
                               for n in dep["roman_prohibited_hexes"]}
        self._compute_playable(dep["playable_area"])
        self.jud_zone = (self.new_city |
                         {h for h, t in self.hex_t.items()
                          if t in ELEVATED and h in self.playable})
        # Roman deployment: outside the city, >= 5 hexes from any Elevated hex
        self.rom_zone = self._roman_zone()

    def _nb(self, h):
        """Axial neighbors (col=L, row=N+L//2 storage; axial in (L,N))."""
        c, r = int(h[:2]), int(h[2:])
        N = r - c // 2
        out = []
        for dc, dn in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, -1), (-1, 1)):
            c2, n2 = c + dc, N + dn
            k = f"{c2:02d}{n2 + c2 // 2:02d}"
            if k in self.hex_t:
                out.append(k)
        return out

    def _compute_playable(self, cfg):
        """Playable battlefield = outside flood fill (barred by every wall/
        strongpoint/garrison hex, cut at row_max) + New City + wall rings.
        The old city beyond the Second Wall is off the Gallus battlefield
        (scenario scope statement on the card)."""
        barrier = {h for h, t in self.hex_t.items() if t in ELEVATED}
        row_max = int(cfg["row_max"])
        seed = self.name_hex[cfg["outside_seed"]]
        seen = set()
        stack = [seed]
        while stack:
            h = stack.pop()
            if h in seen or h in barrier or h in self.new_city:
                continue
            if int(h[2:]) > row_max:
                continue
            seen.add(h)
            stack.extend(self._nb(h))
        self.outside = seen
        self.playable = seen | self.new_city | barrier

    def _roman_zone(self):
        """Outside hexes >= 5 hexes from every Elevated hex (card). Axial
        distance on (L,N) coordinates."""
        elev = [(int(h[:2]), int(h[2:]) - int(h[:2]) // 2)
                for h, t in self.hex_t.items() if t in ELEVATED]

        def dist_ok(h):
            c, r = int(h[:2]), int(h[2:])
            n = r - c // 2
            for ec, en in elev:
                dq, dr = ec - c, en - n
                d = max(abs(dq), abs(dr), abs(dq + dr))
                if d < 5:
                    return False
            return True
        return {h for h in self.outside if dist_ok(h)}

    # ------------------------------------------------------------ lifecycle
    def new_game(self, seed):
        units = {}
        for spec in self.scenario["units"]:
            for i in range(spec.get("count", 1)):
                pid = spec["id"] if spec.get("count", 1) == 1 \
                    else f"{spec['id']}_{i + 1}"
                units[pid] = {
                    "pid": pid, "slot": spec["slot"], "side": spec["side"],
                    "type": spec["type"], "faction": spec.get("faction"),
                    "hex": None, "state": "fresh", "used_mf": 0.0,
                }
                if spec.get("cohorts"):
                    units[pid]["cohort"] = spec["cohorts"][i]
        pool = []
        for spec in self.scenario["reinforcement_pool"]:
            for i in range(spec.get("count", 1)):
                pid = spec["id"] if spec.get("count", 1) == 1 \
                    else f"{spec['id']}_{i + 1}"
                pool.append({
                    "pid": pid, "slot": spec["slot"], "side": spec["side"],
                    "type": spec["type"], "faction": spec.get("faction"),
                    "leader_first": bool(spec.get("leader_enters_with_first_draw")),
                })
        # hex control [18.3]: city hexes Judaean, everything outside Roman
        control = {}
        for h in self.playable:
            control[h] = "Rom" if h in self.outside else "Jud"
        self.s = {
            "schema": 1, "tier": self.tier, "seed": seed, "rng_calls": 0,
            "n": 0, "turn": 0, "phase": "deploy_jud",
            "units": units, "pool": pool, "entry_queue": [],
            "control": control, "deploy_done": {"Jud": False, "Rom": False},
            "winner": None, "over": False,
        }
        self._reset_log()
        self._log({"event": "init", "mode": "soj",
                   "scenario": self.scenario["name"], "tier": self.tier,
                   "seed": seed,
                   "units": [{"pid": u["pid"], "slot": u["slot"],
                              "side": u["side"], "hex": u["hex"]}
                             for u in units.values()],
                   "pool": [p["pid"] for p in pool]})
        self.save()

    # ------------------------------------------------------------ queries
    def side_to_move(self):
        p = self.s["phase"]
        if p == "deploy_jud":
            return "Jud"
        if p == "deploy_rom":
            return "Rom"
        return "Rom" if p.startswith("rom_") else "Jud"

    def is_night(self):
        return self.s["turn"] in self.scenario["game"].get("night_turns", [])

    def utype(self, u):
        return self.types[u["type"]]

    def _ma(self, u):
        t = self.utype(u)
        return float(t["ma"][0 if u["state"] == "fresh" else 1])

    def _occupants(self, h):
        return [u for u in self.s["units"].values() if u["hex"] == h]

    # ------------------------------------------------------------ stacking
    def _stack_limit(self, h, side):
        """TEC STACKING@ [Roman, Judaean]; combat units only - Artillery,
        HQ and Siege Engines are free but max one of each per hex [6.0]."""
        t = self.hex_t[h]
        lim = self.game.spec["movement"]["tec"]["stacking"].get(
            t, [3, 2] if t == "clear" else [2, 2])
        return lim[0] if side == "Rom" else lim[1]

    def _stack_check(self, h, side, adding):
        """Would `adding` (a unit dict) overstack hex h? [6.0-6.3]"""
        occ = self._occupants(h) + [adding]
        free_cls = {"artillery", "cauldron", "hq", "siege_engine"}
        combat = [u for u in occ if self.utype(u)["cls"] not in free_cls]
        if len(combat) > self._stack_limit(h, side):
            return f"stacking limit exceeded in {self.hex_name[h]} [TEC/6.0]"
        for cls in ("artillery", "hq", "siege_engine"):
            n = sum(1 for u in occ if self.utype(u)["cls"] in
                    ({cls, "cauldron"} if cls == "artillery" else {cls}))
            cap = 1
            if cls == "artillery" and self.hex_t[h] == "fortress":
                cap = 2  # one may be a Cauldron [6.3]
            if n > cap:
                return f"max one {cls.replace('_', ' ')} per hex [6.3/6.4/@]"
        # infantry never stacks with cavalry [6.1]
        has_cav = any(self.utype(u)["cls"] == "cavalry" for u in occ)
        has_inf = any(self.utype(u)["cls"] in ("heavy", "light") for u in occ)
        if has_cav and has_inf:
            return "Infantry may not stack with Cavalry [6.1/6.2]"
        return None

    # ------------------------------------------------------------ ZOC [7]
    def _zoc_map(self, side):
        """Set of hexes under `side`'s ZOC, split hard/soft is by the MOVING
        unit's class, so this returns {hex: True}. No ZOC at night [7.2]."""
        if self.is_night():
            return set()
        zoc = set()
        for u in self.s["units"].values():
            if u["side"] != side or u["hex"] is None or u["state"] != "fresh":
                continue
            cls = self.utype(u)["cls"]
            if cls == "hq":
                # HQ are Infantry "[Exception: ZOC, 7.321]" [2.4] - the
                # exception removes them from the infantry ZOC rules; no
                # clause grants HQ a ZOC of their own, so they exert none.
                continue
            h = u["hex"]
            t = self.hex_t[h]
            if cls in ("heavy", "light") and (t in GROUND or t == "builtup"):
                # ground ZOC into adjacent GROUND hexes only [7.11]
                for n in self._nb(h):
                    if self.hex_t[n] in GROUND:
                        zoc.add(n)
            elif cls in ("heavy", "light") and t in GATES:
                # gate ZOC: connected Elevated + entrance-connected ground [7.12]
                for n in self._nb(h):
                    key = tuple(sorted((h, n)))
                    if self.hex_t[n] in ELEVATED or key in self.entrances:
                        zoc.add(n)
            elif cls in ("heavy", "light") and t in ELEVATED:
                # elevated ZOC into connected Elevated [7.13]
                for n in self._nb(h):
                    if self.hex_t[n] in ELEVATED:
                        zoc.add(n)
            elif cls == "cavalry" and (t in GROUND or t == "builtup"):
                for n in self._nb(h):                     # [7.11]
                    if self.hex_t[n] in GROUND:
                        zoc.add(n)
        return zoc

    def _heavy_ground_zoc(self, side):
        """Hexes in ground-level ZOC of side's Fresh HEAVY infantry - the
        7.311 Judaean freeze + 14.21 retreat limit key off this set."""
        if self.is_night():
            return set()
        out = set()
        for u in self.s["units"].values():
            if (u["side"] == side and u["hex"] is not None
                    and u["state"] == "fresh"
                    and self.utype(u)["cls"] == "heavy"
                    and self.hex_t[u["hex"]] in (GROUND | {"builtup"})):
                for n in self._nb(u["hex"]):
                    if self.hex_t[n] in GROUND:
                        out.add(n)
        return out

    # ------------------------------------------------------------ movement
    def _entry_cost(self, u, frm, to, side):
        """MF cost for `u` to enter `to` from `frm`, or (None, reason).
        Implements the TEC per unit class + wall/staircase/gate entry
        [8.91-8.95, TEC]. Returns (cost, None) or (None, why-not)."""
        t_to = self.hex_t[to]
        t_frm = self.hex_t[frm]
        cls = self.utype(u)["cls"]
        key = tuple(sorted((frm, to)))
        both_elev = t_frm in ELEVATED and t_to in ELEVATED

        if to not in self.playable:
            return None, "off the Gallus battlefield (card scope statement)"
        if side == "Rom" and to in self.rom_prohibited:
            return None, "Romans may never enter Garrison hexes P50/QQ32 (card)"

        if cls == "cauldron":
            # Cauldrons: elevated-to-connected-elevated at 1/2 each, never
            # Ground, never a non-Fortress hex holding other artillery [8.5]
            if not both_elev:
                return None, "Cauldrons move only between connected Elevated hexes [8.5/TEC**]"
            other_art = any(self.utype(o)["cls"] in ("artillery", "cauldron")
                            for o in self._occupants(to))
            if other_art and t_to != "fortress":
                return None, "Cauldron may not join Artillery outside a Fortress [6.3/8.5]"
            return 0.5, None

        if t_to in ELEVATED:
            if cls == "cavalry":
                return None, "Cavalry may never enter Elevated hexes [6.2]"
            if cls == "siege_engine":
                return None, "Siege Engines may not enter Elevated hexes (Ram-through-Gate is tier-2 scope) [6.4]"
            if cls == "artillery":
                return None, "Roman Artillery that begins the Assault Period on the ground may not enter Elevated hexes [8.4]"
            if both_elev:
                return 0.5, None              # connected Elevated [TEC C]
            if key in self.stairs:
                return 2.0, None              # staircase level change [8.93]
            if key in self.entrances:
                # ground-level entrance: gate must be controlled by mover's
                # side [8.91 'A Gate whether occupied or not is closed to all
                # enemy units']; stopping costs +2 up the Interior Staircase
                # (charged at path end in _move_verdict)
                if self.s["control"].get(to) != side:
                    return None, "Gate is closed to enemy units at ground level [8.91]"
                return 1.0, None
            return None, "Elevated hex entered only from connected Elevated, a Staircase hexside or a Gate entrance [8.91-8.93]"

        # ground-side classes into ground/builtup
        if t_frm in ELEVATED and t_to not in ELEVATED:
            # leaving elevation: staircase/entrance only [8.91/8.93]
            if key in self.stairs:
                return 2.0, None
            if key in self.entrances:
                base = self._ground_cost(u, to, side)
                if base is None:
                    return None, "class may not enter that terrain [TEC]"
                return base, None
            return None, "Elevated hex left only via Staircase hexside or Gate entrance [8.91-8.93]"

        base = self._ground_cost(u, to, side)
        if base is None:
            return None, "class may not enter that terrain [TEC]"
        return base, None

    def _ground_cost(self, u, to, side):
        t = self.hex_t[to]
        cls = self.utype(u)["cls"]
        if cls in ("heavy", "light", "hq"):
            if t == "builtup":
                return 2.0 if side == "Jud" else 3.0     # [8.95]
            return INF_COST.get(t)
        if cls == "cavalry":
            if t == "builtup":
                return None   # road-only [8.95]; interior roads not encoded in v1
            return CAV_COST.get(t)
        if cls in ("siege_engine", "artillery"):
            if t == "builtup":
                return None   # artillery: road hexsides only [8.95]; SE: X [TEC]
            return SE_COST.get(t)
        return None

    def _move_verdict(self, side, u, path):
        """Full path legality: cost budget, ZOC, stacking at destination.
        path = [hexkey...] starting at the unit's hex."""
        entry_gate = self.enterable_from(u["pid"])
        if u["hex"] is None and entry_gate is None:
            return self._v(False, "unit is not on the map")
        if u["side"] != side:
            return self._v(False, "not your unit")
        start = entry_gate if u["hex"] is None else u["hex"]
        if path[0] != start:
            where = self.hex_name.get(start, start)
            return self._v(False, f"path must start at {where}"
                           + (" (entry gate)" if entry_gate else ""))
        if len(path) < 2:
            return self._v(False, "empty move")
        cls = self.utype(u)["cls"]
        enemy = "Jud" if side == "Rom" else "Rom"
        zoc = self._zoc_map(enemy)
        heavy_zoc = self._heavy_ground_zoc("Rom") if side == "Jud" else set()

        # 7.311 + 1/6/1992 Q&A: non-HQ Judaean starting its MPh in Roman
        # Heavy-Infantry ground-level ZOC may not move at all
        if (side == "Jud" and cls != "hq" and u["hex"] in heavy_zoc):
            return self._v(False,
                           "Judaean unit in Roman Heavy Infantry ground-level "
                           "ZOC may not move [7.311; official Q&A 1/6/1992]")
        # siege engines need a Fresh pushing Heavy/Velitae in the hex [8.6]
        if cls == "siege_engine":
            crew = [o for o in self._occupants(u["hex"])
                    if o["state"] == "fresh" and o["pid"] != u["pid"]
                    and (self.utype(o)["cls"] == "heavy"
                         or o["type"] == "velitae")]
            if not crew:
                return self._v(False, "Siege Engine needs a Fresh Heavy Infantry or Velitae pushing unit in its hex at the start of the MPh [8.6/2.45]")

        budget = self._ma(u)
        soft = cls in ("hq", "cavalry")
        spent = 0.0
        prev = path[0]
        started_in_zoc = prev in zoc
        for i, h in enumerate(path[1:], 1):
            if h not in self._nb(prev):
                return self._v(False, f"{self.hex_name.get(h, h)} is not adjacent to {self.hex_name.get(prev, prev)}")
            if any(o["side"] == enemy for o in self._occupants(h)):
                return self._v(False, "may not enter an enemy-occupied hex [8.11]")
            cost, why = self._entry_cost(u, prev, h, side)
            if cost is None:
                return self._v(False, why)
            # hard-ZOC exit: first hex must be ZOC-free [7.311]
            if i == 1 and started_in_zoc and not soft and h in zoc:
                return self._v(False, "leaving a hard ZOC: the first hex entered must be free of enemy ZOC [7.311]")
            # soft ZOC (HQ/Cavalry): +3 MF each time a ZOC hex is left [7.32/7.4]
            if soft and prev in zoc:
                cost += 3.0
            # pass-through of a fully stacked hex doubles cost [8.13]
            occ = self._occupants(h)
            free_cls = {"artillery", "cauldron", "hq", "siege_engine"}
            combat_n = sum(1 for o in occ if self.utype(o)["cls"] not in free_cls)
            if combat_n >= self._stack_limit(h, side) and i < len(path) - 1:
                cost *= 2.0
            spent += cost
            if spent > budget + 1e-9:
                return self._v(False, f"movement allowance exceeded: {spent:g} > {budget:g} MF [8.11/TEC]")
            # hard ZOC: stop on entry [7.31]
            if not soft and h in zoc and i < len(path) - 1:
                return self._v(False, "must stop on entering an enemy ZOC [7.31]")
            prev = h
        dest = path[-1]
        # stopping in a gate hex costs +2 up the Interior Staircase [8.91]
        if self.hex_t[dest] in GATES and self.hex_t[path[-2]] not in ELEVATED \
                and tuple(sorted((path[-2], dest))) in self.entrances:
            spent += 2.0
            if spent > budget + 1e-9:
                return self._v(False, "may not stop in a Gate at ground level - +2 MF Interior Staircase exceeds allowance [8.91]")
        bad = self._stack_check(dest, side, u)
        if bad:
            return self._v(False, bad)
        return self._v(True, f"cost {spent:g} of {budget:g} MF")

    # ------------------------------------------------------------ propose
    def propose(self, side, action):
        if self.s.get("over"):
            return self._v(False, "game over")
        a = action.get("type")
        phase = self.s["phase"]
        if a == "deploy":
            return self._deploy_verdict(side, action)
        if a == "deploy_done":
            return self._deploy_done_verdict(side)
        if a == "move":
            if phase != f"{'rom' if side == 'Rom' else 'jud'}_move":
                return self._v(False, f"not the {side} Movement Phase")
            if side != self.side_to_move():
                return self._v(False, "not your phase")
            u = self.s["units"].get(str(action.get("pid")))
            if not u:
                return self._v(False, "unknown unit")
            path = [self.name_hex.get(h, h) for h in action.get("path", [])]
            if any(p not in self.hex_t for p in path):
                return self._v(False, "path contains unknown hexes")
            return self._move_verdict(side, u, path)
        if a == "end_phase":
            if phase in ("deploy_jud", "deploy_rom"):
                return self._v(False, "finish deployment with deploy_done")
            if side != self.side_to_move():
                return self._v(False, "not your phase")
            return self._v(True, f"end of {phase}")
        return self._v(False, f"unknown action type {a!r}")

    def _deploy_verdict(self, side, action):
        phase = self.s["phase"]
        if phase not in ("deploy_jud", "deploy_rom"):
            return self._v(False, "deployment is over")
        if side != self.side_to_move():
            return self._v(False, "not your deployment")
        u = self.s["units"].get(str(action.get("pid")))
        if not u or u["side"] != side:
            return self._v(False, "not your unit")
        h = self.name_hex.get(action.get("hex"), action.get("hex"))
        if h not in self.hex_t:
            return self._v(False, "unknown hex")
        zone = self.jud_zone if side == "Jud" else self.rom_zone
        if h not in zone:
            why = ("inside the New City on or within its outer walls (card)"
                   if side == "Jud" else
                   "outside Jerusalem, >= 5 hexes from any Elevated hex (card)")
            return self._v(False, f"deployment must be {why}")
        cls = self.utype(u)["cls"]
        if cls == "cavalry" and self.hex_t[h] in ELEVATED:
            return self._v(False, "Cavalry may never enter Elevated hexes [6.2]")
        if cls in ("siege_engine", "artillery") and self.hex_t[h] in ELEVATED:
            return self._v(False, "Siege Engines/Artillery do not deploy on Elevated hexes [6.4/8.4]")
        if cls == "cauldron" and self.hex_t[h] not in ELEVATED:
            return self._v(False, "Cauldrons occupy Elevated hexes [8.4/8.5]")
        bad = self._stack_check(h, side, u)
        if bad:
            return self._v(False, bad)
        return self._v(True, "deploy")

    def _deploy_done_verdict(self, side):
        phase = self.s["phase"]
        if phase == "deploy_jud":
            if side != "Jud":
                return self._v(False, "Judaean deployment first (card)")
            unplaced = [u["pid"] for u in self.s["units"].values()
                        if u["side"] == "Jud" and u["hex"] is None]
            if unplaced:
                return self._v(False, f"{len(unplaced)} Judaean units not deployed")
            empty = [self.hex_name[h] for h in self.min_force
                     if not self._occupants(h)]
            if empty:
                return self._v(False,
                               "minimum force: each Bastion/Fortress of the North "
                               f"Wall O50..QQ29 needs a unit; empty: {', '.join(sorted(empty))} (card special rule 1)")
            return self._v(True, "Judaean deployment complete")
        if phase == "deploy_rom":
            if side != "Rom":
                return self._v(False, "Roman deployment phase")
            unplaced = [u["pid"] for u in self.s["units"].values()
                        if u["side"] == "Rom" and u["hex"] is None]
            if unplaced:
                return self._v(False, f"{len(unplaced)} Roman units not deployed")
            return self._v(True, "Roman deployment complete - the assault begins")
        return self._v(False, "deployment is over")

    # ------------------------------------------------------------ apply
    def _apply(self, side, action, verdict):
        a = action["type"]
        if a == "deploy":
            u = self.s["units"][str(action["pid"])]
            h = self.name_hex.get(action["hex"], action["hex"])
            u["hex"] = h
            self.s["control"][h] = side          # occupation = control [18.3]
            return {"placed": self.hex_name[h]}
        if a == "deploy_done":
            if self.s["phase"] == "deploy_jud":
                self.s["deploy_done"]["Jud"] = True
                self.s["phase"] = "deploy_rom"
                return {"next": "deploy_rom"}
            self.s["deploy_done"]["Rom"] = True
            self.s["turn"] = 1
            self.s["phase"] = self.scenario["game"].get("opening_phase", "rom_rally")
            return {"next": self.s["phase"], "turn": 1}
        if a == "move":
            u = self.s["units"][str(action["pid"])]
            path = [self.name_hex.get(h, h) for h in action["path"]]
            entering = u["hex"] is None
            u["hex"] = path[-1]
            for h in (path if entering else path[1:]):
                self.s["control"][h] = side      # last occupant controls [18.3]
            if entering:
                self.s["entry_queue"] = [q for q in self.s["entry_queue"]
                                         if q["pid"] != u["pid"]]
            return {"to": self.hex_name[path[-1]]}
        if a == "end_phase":
            return self._advance_phase()
        raise AssertionError(f"apply fell through for {a!r}")

    def _advance_phase(self):
        p = self.s["phase"]
        i = self.PHASES.index(p)
        result = {"ended": p}
        # Roman victory check at the end of each Judaean Melee Phase (card)
        if p == "jud_melee":
            n = self._roman_builtup_count()
            result["roman_builtup"] = n
            need = self.scenario["vp"]["roman_win"]["builtup_controlled"]
            if n >= need:
                self.s["winner"] = "Rom"
                self.s["over"] = True
                result["winner"] = "Rom"
                return result
            if self.s["turn"] >= self.turns:
                self.s["winner"] = "Jud"
                self.s["over"] = True
                result["winner"] = "Jud"
                return result
            self.s["turn"] += 1
            self.s["phase"] = self.PHASES[0]
        else:
            self.s["phase"] = self.PHASES[i + 1]
        # Giora reinforcement rolls at the START of the Judaean MPh, turn 4+
        if self.s["phase"] == "jud_move" and self.s["turn"] >= \
                self.scenario["reinforcement"]["from_turn"] and self.s["pool"]:
            result["reinforcement"] = self._roll_reinforcements()
        result["next"] = self.s["phase"]
        return result

    def _roman_builtup_count(self):
        return sum(1 for h, s in self.s["control"].items()
                   if s == "Rom" and self.hex_t.get(h) == "builtup")

    def _roll_reinforcements(self):
        """Card special rule 2 (count = two dice per the declared
        interpretation in source_defects; entry die odd=OO33 even=Q49;
        blocked -> other gate; leader accompanies the first draw)."""
        cfg = self.scenario["reinforcement"]
        count = sum(self.roll_die() for _ in range(int(cfg["count_dice"])))
        entry = self.roll_die()
        gate_name = cfg["entry_die"]["odd" if entry % 2 else "even"]
        gate = self.name_hex[gate_name]
        alt = self.name_hex[cfg["entry_die"]["even" if entry % 2 else "odd"]]
        # blocked = enemy-occupied or enemy-controlled gate [8.91]
        def blocked(g):
            return (any(o["side"] == "Rom" for o in self._occupants(g))
                    or self.s["control"].get(g) != "Jud")
        if blocked(gate):
            gate, alt = alt, gate
        if blocked(gate):
            return {"rolled": count, "entry_die": entry,
                    "note": "both gates blocked - no entry this turn"}
        pool = self.s["pool"]
        draw = []
        leader = next((p for p in pool if p.get("leader_first")), None)
        if leader:
            draw.append(leader)
        r = self._rng()
        others = [p for p in pool if not p.get("leader_first")]
        for _ in range(min(count, len(others))):
            k = int(r.random() * len(others))
            self.s["rng_calls"] += 1
            draw.append(others.pop(k))
        placed = []
        for p in draw:
            self.s["units"][p["pid"]] = {
                "pid": p["pid"], "slot": p["slot"], "side": "Jud",
                "type": p["type"], "faction": p.get("faction"),
                "hex": None, "state": "fresh", "used_mf": 0.0,
            }
            self.s["entry_queue"].append({"pid": p["pid"], "gate": gate})
            placed.append(p["pid"])
        self.s["pool"] = [p for p in pool if p["pid"] not in placed]
        return {"rolled": count, "entry_die": entry,
                "gate": self.hex_name[gate], "entered": placed}

    # entry-queue units move onto the map with a move whose path starts at
    # the gate hex; _move_verdict path[0] check is bypassed via this hook
    def enterable_from(self, pid):
        for q in self.s["entry_queue"]:
            if q["pid"] == pid:
                return q["gate"]
        return None
