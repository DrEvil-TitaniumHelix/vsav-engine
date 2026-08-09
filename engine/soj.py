"""
soj.py - The Siege of Jerusalem (AH 1989) legality gate. Tier-2 scope.

The Assault of Gallus introductory scenario: free deployment, per-class TEC
movement, SoJ zones of control, stacking, hex control [18.3], the Giora
reinforcement, and the validated combat systems: Missile Table fire (LOF,
concentration, mandatory targets, wall-attack bonus, rocks), Ram/Armored
Tower Breach attacks with cumulative damage and breached-wall state, Melee
Table combat with drm/strength modifiers, defender-choice loss pendings,
retreats toward Refuge, the disruption ladder (Fresh-Disrupted-Routed-
Panicked), the Rally Phase, Command Control, and night-turn effects.

Enforced-with-simplifications (declared in scenario rules_scope, module-
author review pending): siege-engine facing is not enforced (breach attacks
allowed vs any adjacent Elevated hex); Escalades and Testudo are not
available in v1; multi-hex advance after combat is limited to the vacated
hex; CC tracing and Refuge routing use documented approximations.

Authority: official Q&A > rulebook; the two official Q&A documents agree
everywhere (decode-prep 6) - their one citation mismatch (17.23 vs 17.3)
is registered in game.json source_defects. Every enforcement carries its
citation.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gate import GateGame  # noqa: E402

ELEVATED = {"north_wall", "wall", "bastion", "fort", "fortress",
            "gate", "gate_north_wall", "gate_wall"}
GATES = {"gate", "gate_north_wall", "gate_wall"}
STRONGPOINTS = {"bastion", "fort", "fortress"}
GROUND = {"clear", "slope", "breach"}          # [2.12]; builtup separate [2.13]

INF_COST = {"clear": 1.0, "slope": 3.0, "breach": 3.0}
CAV_COST = {"clear": 1.0, "slope": 7.0, "breach": 7.0}
SE_COST = {"clear": 1.0, "slope": 3.0, "breach": 3.0}

# missile target rows: terrain class -> row key in combat tables.
# Gates are absent by design: neither printed table has a Gate row, so a
# gate resolves on its printed strongpoint ring class (decode-prep 6) -
# see _breach_def / _target_row, which read the hex's "ring".
ROW_OF_TERRAIN = {
    "fortress": "fortress", "fort": "fort",
    "bastion": "bastion_armored_tower",
    "wall": "wall_bridge_ram",
    "north_wall": "builtup_northwall_tower",
    "builtup": "builtup_northwall_tower",
    "breach": "breach_broken_testudo",
    "clear": "clear_slope_ramp_escalade", "slope": "clear_slope_ramp_escalade",
}
# breach defense by hex class [12.1 / game card]; gates via ring, as above
BREACH_DEF = {"fortress": 15, "fort": 12, "bastion": 10, "wall": 8,
              "north_wall": 6}

DISR_LADDER = ["fresh", "disrupted", "routed", "panicked"]


class SoJGame(GateGame):
    HASH_KEYS = ("units", "turn", "phase", "seg", "seed", "rng_calls",
                 "control", "pool", "entry_queue", "deploy_done", "breach",
                 "fired", "fired_hexes", "meleed", "pending", "cc_hex",
                 "escaped")
    TURN_NOUN = "turn"
    PHASE_FIELD = "phase"

    PHASES = ["rom_rally", "rom_fire", "rom_move", "rom_melee",
              "jud_rally", "jud_fire", "jud_move", "jud_melee"]

    def __init__(self, game, scenario_path, live_dir, seed=None, tier=None):
        super().__init__(game, scenario_path, live_dir)
        self._resolve_tier(tier)
        self.types = game.spec["unit_types"]
        self.terr = game.terrain
        self._index_terrain()
        self._resume_or_new(self._fresh_seed(seed),
                            required=("units", "phase", "control", "pool",
                                      "breach", "pending"))

    # ------------------------------------------------------------ terrain
    def _index_terrain(self):
        th = self.terr["hexes"]
        self.hex_t0 = {k: v["t"] for k, v in th.items()}
        self.hex_name = {k: v.get("name", k) for k, v in th.items()}
        self.name_hex = {v: k for k, v in self.hex_name.items()}
        self.px = {}
        g = self.game.grid
        for k in th:
            self.px[k] = g.hex_to_pixel(int(k[:2]), int(k[2:]))
        self.hex_ring = {k: v["ring"] for k, v in th.items() if "ring" in v}
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
                         {h for h, t in self.hex_t0.items()
                          if t in ELEVATED and h in self.playable})
        self.rom_zone = self._roman_zone()
        self.refuge_gates = [self.name_hex[n] for n in
                             (self.scenario["reinforcement"]["entry_die"]["odd"],
                              self.scenario["reinforcement"]["entry_die"]["even"])]
        cd = self.game.spec.get("combat") or {}
        self.melee_t = cd.get("melee")
        self.missile_t = cd.get("missile")
        self.breach_t = cd.get("breach")
        self.rally_t = cd.get("rally")

    def _breach_def(self, h):
        """[12.1] Breach Defense of a hex. A gate resolves on its printed
        strongpoint ring class (decode-prep 6); a gate without a recorded
        ring is a data bug and fails loudly here."""
        t = self.hex_t0[h]
        if t in GATES:
            return BREACH_DEF[self.hex_ring[h]]
        return BREACH_DEF.get(t, 99)

    def hex_t(self, h):
        """Dynamic terrain: a breached Elevated hex is a Breach [12.2]."""
        t = self.hex_t0[h]
        if t in ELEVATED and self.s.get("breach", {}).get(h, 0) >= \
                self._breach_def(h):
            return "breach"
        return t

    def _nb(self, h):
        c, r = int(h[:2]), int(h[2:])
        N = r - c // 2
        out = []
        for dc, dn in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, -1), (-1, 1)):
            c2, n2 = c + dc, N + dn
            k = f"{c2:02d}{n2 + c2 // 2:02d}"
            if k in self.hex_t0:
                out.append(k)
        return out

    def _dist(self, a, b):
        ca, ra = int(a[:2]), int(a[2:])
        cb, rb = int(b[:2]), int(b[2:])
        na, nb_ = ra - ca // 2, rb - cb // 2
        dq, dr = cb - ca, nb_ - na
        return max(abs(dq), abs(dr), abs(dq + dr))

    def _compute_playable(self, cfg):
        barrier = {h for h, t in self.hex_t0.items() if t in ELEVATED}
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
        elev = [(int(h[:2]), int(h[2:]) - int(h[:2]) // 2)
                for h, t in self.hex_t0.items() if t in ELEVATED]

        def dist_ok(h):
            c, r = int(h[:2]), int(h[2:])
            n = r - c // 2
            for ec, en in elev:
                dq, dr = ec - c, en - n
                if max(abs(dq), abs(dr), abs(dq + dr)) < 5:
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
                units[pid] = {"pid": pid, "slot": spec["slot"],
                              "side": spec["side"], "type": spec["type"],
                              "faction": spec.get("faction"), "hex": None,
                              "state": "fresh"}
                if spec.get("cohorts"):
                    units[pid]["cohort"] = spec["cohorts"][i]
        pool = []
        for spec in self.scenario["reinforcement_pool"]:
            for i in range(spec.get("count", 1)):
                pid = spec["id"] if spec.get("count", 1) == 1 \
                    else f"{spec['id']}_{i + 1}"
                pool.append({"pid": pid, "slot": spec["slot"],
                             "side": spec["side"], "type": spec["type"],
                             "faction": spec.get("faction"),
                             "leader_first": bool(spec.get("leader_enters_with_first_draw"))})
        control = {}
        for h in self.playable:
            control[h] = "Rom" if h in self.outside else "Jud"
        self.s = {
            "schema": 2, "tier": self.tier, "seed": seed, "rng_calls": 0,
            "n": 0, "turn": 0, "phase": "deploy_jud", "seg": None,
            "units": units, "pool": pool, "entry_queue": [],
            "control": control, "deploy_done": {"Jud": False, "Rom": False},
            "breach": {}, "fired": [], "fired_hexes": [], "meleed": [],
            "pending": None, "cc_hex": None, "escaped": [],
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
        if self.s.get("pending"):
            return self.s["pending"]["by"]
        if p == "deploy_jud":
            return "Jud"
        if p == "deploy_rom":
            return "Rom"
        if p.endswith("_fire") and self.s.get("seg"):
            return self.s["seg"]
        return "Rom" if p.startswith("rom_") else "Jud"

    def is_night(self):
        return self.s["turn"] in self.scenario["game"].get("night_turns", [])

    def utype(self, u):
        return self.types[u["type"]]

    def _fresh(self, u):
        return u["state"] == "fresh"

    def _ma(self, u):
        t = self.utype(u)
        return float(t["ma"][0 if self._fresh(u) else 1])

    def _melee_val(self, u):
        t = self.utype(u)
        return t["melee"][0 if self._fresh(u) else 1]

    def _occupants(self, h):
        return [u for u in self.s["units"].values() if u["hex"] == h]

    def _enemy(self, side):
        return "Jud" if side == "Rom" else "Rom"

    # ------------------------------------------------------------ stacking
    def _stack_limit(self, h, side):
        t = self.hex_t(h)
        lim = self.game.spec["movement"]["tec"]["stacking"].get(
            t, [3, 2] if t == "clear" else [2, 2])
        return lim[0] if side == "Rom" else lim[1]

    def _combat_count(self, occ):
        free_cls = {"artillery", "cauldron", "hq", "siege_engine"}
        return sum(1 for u in occ if self.utype(u)["cls"] not in free_cls)

    def _stack_check(self, h, side, adding):
        occ = self._occupants(h) + [adding]
        if self._combat_count(occ) > self._stack_limit(h, side):
            return f"stacking limit exceeded in {self.hex_name[h]} [TEC/6.0]"
        for cls in ("artillery", "hq", "siege_engine"):
            n = sum(1 for u in occ if self.utype(u)["cls"] in
                    ({cls, "cauldron"} if cls == "artillery" else {cls}))
            cap = 2 if (cls == "artillery" and self.hex_t(h) == "fortress") else 1
            if n > cap:
                return f"max one {cls.replace('_', ' ')} per hex [6.3/6.4/@]"
        has_cav = any(self.utype(u)["cls"] == "cavalry" for u in occ)
        has_inf = any(self.utype(u)["cls"] in ("heavy", "light") for u in occ)
        if has_cav and has_inf:
            return "Infantry may not stack with Cavalry [6.1/6.2]"
        return None

    # ------------------------------------------------------------ ZOC [7]
    def _zoc_map(self, side):
        if self.is_night():
            return set()          # no ZOC at night [7.2]
        zoc = set()
        for u in self.s["units"].values():
            if u["side"] != side or u["hex"] is None or not self._fresh(u):
                continue
            cls = self.utype(u)["cls"]
            if cls == "hq":
                continue          # HQ exert none [2.4 exception / 7.321]
            h = u["hex"]
            t = self.hex_t(h)
            if cls in ("heavy", "light") and (t in GROUND or t == "builtup"):
                for n in self._nb(h):
                    if self.hex_t(n) in GROUND:
                        zoc.add(n)
            elif cls in ("heavy", "light") and t in GATES:
                for n in self._nb(h):
                    key = tuple(sorted((h, n)))
                    if self.hex_t(n) in ELEVATED or key in self.entrances:
                        zoc.add(n)
            elif cls in ("heavy", "light") and t in ELEVATED:
                for n in self._nb(h):
                    if self.hex_t(n) in ELEVATED:
                        zoc.add(n)
            elif cls == "cavalry" and (t in GROUND or t == "builtup"):
                for n in self._nb(h):
                    if self.hex_t(n) in GROUND:
                        zoc.add(n)
        return zoc

    def _heavy_ground_zoc(self, side):
        if self.is_night():
            return set()
        out = set()
        for u in self.s["units"].values():
            if (u["side"] == side and u["hex"] is not None and self._fresh(u)
                    and self.utype(u)["cls"] == "heavy"
                    and self.hex_t(u["hex"]) in (GROUND | {"builtup"})):
                for n in self._nb(u["hex"]):
                    if self.hex_t(n) in GROUND:
                        out.add(n)
        return out

    # ------------------------------------------------------------ CC [5]
    def _cc_map(self, side):
        """Hexes in command for `side` this moment. BFS from each HQ through
        hexes the HQ could move through [5.2 - passability approximation,
        module-author review note]; radius 10, -2 night [5.11], -2 HQ not
        Fresh [16.1]. Judaean auto-CC [5.6] handled in in_cc()."""
        cover = {}
        for hq in self.s["units"].values():
            if hq["side"] != side or hq["hex"] is None \
                    or self.utype(hq)["cls"] != "hq":
                continue
            rad = 10 - (2 if self.is_night() else 0) \
                     - (0 if self._fresh(hq) else 2)
            if rad <= 0:
                continue
            scope = ("all" if self.utype(hq).get("hq") == "commander"
                     else hq.get("faction"))
            seen = {hq["hex"]: 0}
            frontier = [hq["hex"]]
            enemy = self._enemy(side)
            while frontier:
                nxt = []
                for h in frontier:
                    d = seen[h]
                    if d >= rad:
                        continue
                    for n in self._nb(h):
                        if n in seen or n not in self.playable:
                            continue
                        if any(o["side"] == enemy for o in self._occupants(n)):
                            continue
                        c, _w = self._entry_cost(hq, h, n, side)
                        if c is None:
                            continue
                        seen[n] = d + 1
                        nxt.append(n)
                frontier = nxt
            for h in seen:
                cover.setdefault(h, set()).add(scope)
        return cover

    def in_cc(self, u, cc=None):
        """[5.1-5.6]. Judaean auto-CC: in an unbreached Fortress/Fort, or on
        Elevated tracing a Roman-free unbreached Elevated path to a
        Judaean-controlled Fortress/Fort [5.6]."""
        if self.utype(u)["cls"] == "hq":
            return True                      # 17.3: disrupted HQ always in CC
        if u["side"] == "Jud":
            t = self.hex_t(u["hex"])
            if t in ("fort", "fortress"):
                return True
            if t in ELEVATED and self._elevated_path_to_fortress(u["hex"]):
                return True
        cover = cc if cc is not None else self._cc_map(u["side"])
        scopes = cover.get(u["hex"], set())
        if "all" in scopes:
            return True
        # zealots/cauldrons/artillery: any Judaean HQ controls [5.4 exc]
        if u["side"] == "Jud" and u["type"] in ("zealot", "cauldron") \
                and scopes:
            return True
        if self.utype(u)["cls"] in ("artillery", "cauldron") and scopes:
            return True
        return u.get("faction") in scopes

    def _elevated_path_to_fortress(self, start):
        seen = {start}
        frontier = [start]
        while frontier:
            h = frontier.pop()
            t = self.hex_t(h)
            if t in ("fort", "fortress") and \
                    self.s["control"].get(h) == "Jud":
                return True
            for n in self._nb(h):
                if n in seen or self.hex_t(n) not in ELEVATED:
                    continue
                if any(o["side"] == "Rom" for o in self._occupants(n)):
                    continue
                seen.add(n)
                frontier.append(n)
        return False

    # ------------------------------------------------------------ movement
    def _entry_cost(self, u, frm, to, side):
        t_to = self.hex_t(to)
        t_frm = self.hex_t(frm)
        cls = self.utype(u)["cls"]
        key = tuple(sorted((frm, to)))
        both_elev = t_frm in ELEVATED and t_to in ELEVATED

        if to not in self.playable:
            return None, "off the Gallus battlefield (card scope statement)"
        if side == "Rom" and to in self.rom_prohibited:
            return None, "Romans may never enter Garrison hexes P50/QQ32 (card)"

        if cls == "cauldron":
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
                return None, "Siege Engines may not enter Elevated hexes [6.4]"
            if cls == "artillery":
                return None, "Roman Artillery on the ground may not enter Elevated hexes [8.4]"
            if both_elev:
                half = 1.0 if self._half_damaged(to) else 0.5   # [12.4]
                return half, None
            if t_frm == "breach":
                return 2.0, None   # a Breach gives Ground<->Elevated access [8.93]
            if key in self.stairs:
                return 2.0, None
            if key in self.entrances:
                if self.s["control"].get(to) != side:
                    return None, "Gate is closed to enemy units at ground level [8.91]"
                return 1.0, None
            return None, "Elevated hex entered only from connected Elevated, a Staircase hexside or a Gate entrance [8.91-8.93]"

        if t_frm in ELEVATED and t_to not in ELEVATED:
            if key in self.stairs:
                return 2.0, None
            if key in self.entrances:
                base = self._ground_cost(u, to, side)
                if base is None:
                    return None, "class may not enter that terrain [TEC]"
                return base, None
            if t_to == "breach":
                return 3.0, None       # down through the rubble [8.93/8.96]
            return None, "Elevated hex left only via Staircase hexside or Gate entrance [8.91-8.93]"

        base = self._ground_cost(u, to, side)
        if base is None:
            return None, "class may not enter that terrain [TEC]"
        return base, None

    def _refuge_dist(self, side, h):
        """Distance to Refuge: Judaean = the south gates toward the Temple
        Quarter (exit = removed from play, Bruce-approved scope call);
        Roman = the nearest board edge, approximated by the north edge
        (lowest row) [15.4]."""
        if side == "Jud":
            return min(self._dist(h, g) for g in self.refuge_gates)
        return int(h[2:])

    def _half_damaged(self, h):
        t = self.hex_t0[h]
        d = self.s.get("breach", {}).get(h, 0)
        return t in ELEVATED and d * 2 >= self._breach_def(h)

    def _ground_cost(self, u, to, side):
        t = self.hex_t(to)
        cls = self.utype(u)["cls"]
        if cls in ("heavy", "light", "hq"):
            if t == "builtup":
                return 2.0 if side == "Jud" else 3.0
            return INF_COST.get(t)
        if cls == "cavalry":
            if t == "builtup":
                return None
            return CAV_COST.get(t)
        if cls in ("siege_engine", "artillery"):
            if t == "builtup":
                return None
            return SE_COST.get(t)
        return None

    def _move_verdict(self, side, u, path):
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
        enemy = self._enemy(side)
        zoc = self._zoc_map(enemy)
        heavy_zoc = self._heavy_ground_zoc("Rom") if side == "Jud" else set()

        if (side == "Jud" and cls != "hq" and u["hex"] in heavy_zoc
                and not self.is_night()):
            # night lifts the freeze [18.23]
            return self._v(False,
                           "Judaean unit in Roman Heavy Infantry ground-level "
                           "ZOC may not move [7.311; official Q&A 1/6/1992]")
        if u["state"] in ("routed", "panicked"):
            # must head for Refuge [15.3/17.21]; v1 enforces direction
            # (full-MF obligation is advisory - see rules_scope)
            if self._refuge_dist(side, path[-1]) >= \
                    self._refuge_dist(side, path[0]):
                return self._v(False, "Routed/Panicked units must move towards Refuge [15.3/17.21]")
        if cls == "siege_engine":
            crew = [o for o in self._occupants(u["hex"])
                    if self._fresh(o) and o["pid"] != u["pid"]
                    and (self.utype(o)["cls"] == "heavy"
                         or o["type"] == "velitae")]
            if not crew:
                return self._v(False, "Siege Engine needs a Fresh Heavy Infantry or Velitae pushing unit in its hex at the start of the MPh [8.6/2.45]")
        out_cc = not self.in_cc(u)
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
            if any(o["side"] == side and o["state"] == "panicked"
                   for o in self._occupants(h)) and i < len(path) - 1:
                return self._v(False, "must stop on entering a hex with a Panicked unit [17.21]")
            cost, why = self._entry_cost(u, prev, h, side)
            if cost is None:
                return self._v(False, why)
            if h in zoc:
                if u["state"] != "fresh" and not (side == "Jud" and self.is_night()):
                    return self._v(False, "Disrupted units may not enter an enemy ZOC [16.51]")
                if out_cc:
                    return self._v(False, "out of Command Control: may not enter an enemy ZOC [5.3]")
            if out_cc and any(
                    self.hex_t(n2) in ELEVATED and
                    any(o["side"] == enemy for o in self._occupants(n2))
                    for n2 in self._nb(h)) and \
                    not any(self.hex_t(n2) in ELEVATED and
                            any(o["side"] == enemy
                                for o in self._occupants(n2))
                            for n2 in self._nb(path[0])):
                return self._v(False, "out of Command Control: may not move adjacent to an enemy unit on an Elevated hex [5.3]")
            if i == 1 and started_in_zoc and not soft and h in zoc:
                return self._v(False, "leaving a hard ZOC: the first hex entered must be free of enemy ZOC [7.311]")
            if soft and prev in zoc:
                cost += 3.0                   # [7.32/7.4]
            occ = self._occupants(h)
            if self._combat_count(occ) >= self._stack_limit(h, side) \
                    and i < len(path) - 1:
                cost *= 2.0                   # [8.13]
            # leaving a hex with a Panicked friend doubles the next cost [17.21]
            if any(o["side"] == side and o["state"] == "panicked"
                   and o["pid"] != u["pid"] for o in self._occupants(prev)):
                cost *= 2.0
            spent += cost
            if spent > budget + 1e-9:
                return self._v(False, f"movement allowance exceeded: {spent:g} > {budget:g} MF [8.11/TEC]")
            if not soft and h in zoc and i < len(path) - 1:
                return self._v(False, "must stop on entering an enemy ZOC [7.31]")
            prev = h
        dest = path[-1]
        if self.hex_t(dest) in GATES and self.hex_t(path[-2]) not in ELEVATED \
                and tuple(sorted((path[-2], dest))) in self.entrances:
            spent += 2.0
            if spent > budget + 1e-9:
                return self._v(False, "may not stop in a Gate at ground level - +2 MF Interior Staircase exceeds allowance [8.91]")
        bad = self._stack_check(dest, side, u)
        if bad:
            return self._v(False, bad)
        return self._v(True, f"cost {spent:g} of {budget:g} MF")

    # ------------------------------------------------------------ fire [9/13]
    def _lof(self, frm, to):
        """LOF check [9.5/game card]. Returns (ok, drm, why). Samples the
        center-to-center pixel line; obstacle classes per the LOF
        Determination Table with closer-to tiebreaks; friendly/intervening
        combat units force Indirect Fire (-1, artillery only)."""
        (x1, y1), (x2, y2) = self.px[frm], self.px[to]
        import math
        L = math.hypot(x2 - x1, y2 - y1)
        crossed = []
        steps = max(int(L / 6), 2)
        for k in range(1, steps):
            t = k / steps
            x, y = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
            g = self.game.grid
            col, row, _ = g.pixel_to_hex(x, y)
            hk = f"{col:02d}{row:02d}"
            # exclude near-hexside samples (within 6px of two centers tie)
            if hk in (frm, to) or hk not in self.hex_t0:
                continue
            cx, cy = self.px[hk]
            if math.hypot(x - cx, y - cy) > 40.0:
                continue          # touching only the rim: hexside graze
            if hk not in [c[0] for c in crossed]:
                crossed.append((hk, self._dist(hk, frm), self._dist(hk, to)))
        t_frm, t_to = self.hex_t(frm), self.hex_t(to)

        def blocker_class(t):
            if t in ("fortress", "fort"):
                return "F"
            if t == "bastion":
                return "B"
            if t in ("wall", "north_wall", "gate", "gate_wall",
                     "gate_north_wall"):
                return "W"
            if t == "builtup":
                return "P"
            return None
        frm_grp = ("FT" if t_frm in ("fortress", "fort") else
                   "B" if t_frm == "bastion" else
                   "WB" if t_frm in ("wall", "north_wall", "gate",
                                     "gate_wall", "gate_north_wall") else "O")
        to_grp = ("FT" if t_to in ("fortress", "fort") else
                  "B" if t_to == "bastion" else
                  "WB" if t_to in ("wall", "north_wall", "gate",
                                   "gate_wall", "gate_north_wall") else "O")
        MATRIX = {  # firing-from group -> target group -> blocking classes
            "FT": {"FT": "F", "B": "F", "WB": "FB*", "O": "FBW*"},
            "B":  {"FT": "F", "B": "FB", "WB": "FB", "O": "FBW"},
            "WB": {"FT": "FB@", "B": "FB", "WB": "FB", "O": "FBW"},
            "O":  {"FT": "FBW@", "B": "FBW", "WB": "FBW", "O": "FBWPC"},
        }
        spec = MATRIX[frm_grp][to_grp]
        closer_tgt = spec.endswith("*")
        closer_frm = spec.endswith("@")
        classes = spec.rstrip("*@")
        indirect = False
        for hk, dfrm, dto in crossed:
            t = self.hex_t(hk)
            bc = blocker_class(t)
            occ_combat = any(self.utype(o)["cls"] not in ("hq",)
                             for o in self._occupants(hk))
            if bc and bc in classes:
                if closer_tgt and not (dto < dfrm):
                    continue
                if closer_frm and not (dfrm < dto):
                    continue
                return False, 0, f"LOF blocked by {self.hex_name[hk]} [game card LOF table]"
            if "C" in classes and occ_combat:
                indirect = True
        # [9.51] elevation-adjacency Built-up blocks are approximated by the
        # crossed-hex P rule above (declared in rules_scope; author review)
        return True, (-1 if indirect else 0), None

    def _range_af(self, u, dist):
        t = self.utype(u)
        for band, af in (t.get("missile") or {}).items():
            lo, _, hi = band.partition("-")
            if int(lo) <= dist <= int(hi or lo):
                return af
        return None

    def _fire_verdict(self, side, action):
        p = self.s["phase"]
        if not p.endswith("_fire"):
            return self._v(False, "not a Fire Phase")
        if side != self.s.get("seg"):
            return self._v(False, f"the {self.s.get('seg')} fire segment is in progress [4.12/4.22]")
        tgt = self.name_hex.get(action.get("target"), action.get("target"))
        if tgt not in self.hex_t0:
            return self._v(False, "unknown target hex")
        if tgt in self.s["fired_hexes"]:
            return self._v(False, "that hex was already missile-attacked this phase [13.1/9.6]")
        enemy = self._enemy(side)
        defenders = [o for o in self._occupants(tgt) if o["side"] == enemy]
        if not defenders:
            return self._v(False, "no enemy units in the target hex [9.1]")
        firers = [self.s["units"].get(str(p_)) for p_ in action.get("firers", [])]
        if not firers or any(f is None for f in firers):
            return self._v(False, "unknown firer")
        af_total = 0
        cauldrons = 0
        for f in firers:
            if f["side"] != side:
                return self._v(False, "not your unit")
            if not self._fresh(f):
                return self._v(False, f"{f['pid']} is not Fresh [9.1/16.2]")
            if f["pid"] in self.s["fired"]:
                return self._v(False, f"{f['pid']} already fired this phase [9.1]")
            if any(self.utype(o)["cls"] == "siege_engine"
                   for o in self._occupants(f["hex"])):
                return self._v(False, "units stacked with a Siege Engine may not fire [9.4]")
            d = self._dist(f["hex"], tgt)
            if self.is_night() and d > 1:
                return self._v(False, "night: fire is limited to adjacent targets [18.21]")
            cls = self.utype(f)["cls"]
            ut = self.utype(f)
            if cls in ("artillery",) and self.hex_t(f["hex"]) in ("builtup", "breach"):
                return self._v(False, "Artillery may never fire from a Built-up or Breach hex [9.3]")
            if not self.in_cc(f) and d > 1:
                return self._v(False, "out of Command Control: may fire only at adjacent targets [5.3]")
            # mandatory targets [9.7]
            adj_enemy = [n for n in self._nb(f["hex"])
                         if any(o["side"] == enemy and
                                self.utype(o)["cls"] not in ("artillery", "siege_engine", "cauldron")
                                for o in self._occupants(n))]
            if adj_enemy and d > 1:
                return self._v(False, "adjacent enemy units are mandatory targets [9.7]")
            if ut.get("rock") is not None and ut.get("missile") is None:
                # rocks: from Elevated at lower adjacent units [10.2/2.523]
                if self.hex_t(f["hex"]) not in ELEVATED:
                    return self._v(False, "rock attacks only from Elevated hexes [10.2]")
                if d != 1 or self.hex_t(tgt) in ELEVATED:
                    return self._v(False, "rock attacks hit lower, adjacent units [10.2/Weapons Chart]")
                af = ut["rock"]
            else:
                af = self._range_af(f, d)
                if af is None:
                    return self._v(False, f"{f['pid']} out of range [Weapons Effect Chart]")
                lof_ok, _drm, why = self._lof(f["hex"], tgt)
                if not lof_ok:
                    return self._v(False, why)
            if f["type"] == "cauldron":
                cauldrons += 1
            # wall attack bonus [9.8]
            if self._wall_bonus(f["hex"], tgt):
                af *= 2
            af_total += af
        row = self._target_row(tgt, action.get("primary_class"))
        thresholds = self.missile_t["target_rows"][row]
        minimum = thresholds[0] if thresholds[0] is not None else thresholds[1]
        if af_total < minimum:
            return self._v(False, f"{af_total} AF below the minimum vs {row} [Missile Table]")
        return dict(self._v(True, f"{af_total} AF vs {row}"),
                    af=af_total, row=row, cauldrons=cauldrons)

    def _wall_bonus(self, frm, tgt):
        """[9.8] Elevated firer, target in Wall/Bridge hex, LOF straight
        down a path of connected Wall hexes."""
        if self.hex_t(frm) not in ELEVATED:
            return False
        if self.hex_t(tgt) not in ("wall", "north_wall", "gate_wall",
                                   "gate_north_wall"):
            return False
        c1, r1 = int(frm[:2]), int(frm[2:])
        c2, r2 = int(tgt[:2]), int(tgt[2:])
        n1, n2 = r1 - c1 // 2, r2 - c2 // 2
        dq, dr = c2 - c1, n2 - n1
        d = max(abs(dq), abs(dr), abs(dq + dr))
        if d == 0:
            return False
        # colinear on one of the three hex axes
        if not (dq == 0 or dr == 0 or dq + dr == 0):
            return False
        sq, sr = (dq // d), (dr // d)
        c, n = c1, n1
        for _ in range(d - 1):
            c, n = c + sq, n + sr
            hk = f"{c:02d}{n + c // 2:02d}"
            if self.hex_t(hk) not in ELEVATED:
                return False
        return True

    def _target_row(self, tgt, primary_class=None):
        occ = self._occupants(tgt)
        if primary_class == "tower" and any(o["type"] == "tower" for o in occ):
            return "builtup_northwall_tower"
        if primary_class == "armored_tower" and \
                any(o["type"] == "armored_tower" for o in occ):
            return "bastion_armored_tower"
        if primary_class == "ram" and any(o["type"] == "ram" for o in occ):
            return "wall_bridge_ram"
        t = self.hex_t(tgt)
        if t in GROUND and any(self.utype(o)["cls"] in ("artillery",)
                               for o in occ):
            return "testudo_artillery_ground"
        if t in GATES:
            return ROW_OF_TERRAIN[self.hex_ring[tgt]]
        return ROW_OF_TERRAIN[t]

    def _resolve_missile(self, side, action, verdict):
        tgt = self.name_hex.get(action["target"], action["target"])
        firers = [str(p) for p in action["firers"]]
        af, row, cauldrons = verdict["af"], verdict["row"], verdict["cauldrons"]
        thresholds = self.missile_t["target_rows"][row]
        col = 0
        for i, th in enumerate(thresholds):
            if th is not None and af >= th:
                col = i + 1
        extreme = 0
        if col == 8:
            inc = thresholds[-1] - thresholds[-2]
            extreme = (af - thresholds[-1]) // inc
        drm = extreme + cauldrons
        enemy = self._enemy(side)
        defenders = [o for o in self._occupants(tgt) if o["side"] == enemy]
        if any(self._fresh(d) and self.utype(d)["cls"] == "heavy"
               for d in defenders) and \
           not any(d["type"] in ("foederatti", "syrian_archers")
                   for d in defenders):
            drm -= 1                          # [13.3 + ** note]
        if any(d["type"] == "judaean_militia" for d in defenders):
            drm += 1
        lof_drm = 0
        for f in firers:
            u = self.s["units"][f]
            if (self.utype(u).get("missile")):
                ok, ld, _ = self._lof(u["hex"], tgt)
                lof_drm = min(lof_drm, ld)    # indirect applies to the attack
        # towers fired through [9.13]
        drm += lof_drm
        die = self.roll_die()
        adj = die + drm
        rows = self.missile_t["result_rows"]
        key = str(max(-1, min(8, adj)))
        result = rows[key][col - 1]
        self.s["fired"].extend(firers)
        self.s["fired_hexes"].append(tgt)
        detail = {"af": af, "row": row, "col": col, "die": die, "drm": drm,
                  "result": result}
        if result == "-":
            return detail
        letters = list(result)
        self._queue_losses(tgt, letters, enemy, source="fire")
        detail["pending"] = self.s["pending"] is not None
        return detail

    # ------------------------------------------------------------ losses
    def _queue_losses(self, tgt, letters, defender, source):
        """Create the defender-choice pending, auto-resolving forced cases."""
        letters = [c for c in letters if c in ("B", "D", "E")]
        self.s["pending"] = {"kind": "loss", "hex": tgt, "letters": letters,
                             "by": defender, "source": source}
        self._auto_resolve_pending()

    def _apply_letter(self, u, letter, source):
        """Apply one D/E to a unit [13.21/14.3/14.4]. Returns event str."""
        cls = self.utype(u)["cls"]
        if letter == "E":
            u["hex"], u["state"] = None, "eliminated"
            return "eliminated"
        # D
        if cls in ("artillery",) and source == "fire":
            # artillery ladder [13.21]; equipment shrugs off first hits
            if self._fresh(u):
                return "no effect (Fresh Artillery ignores D from fire) [13.21]"
            u["state"] = DISR_LADDER[min(3, DISR_LADDER.index(u["state"]) + 1)] \
                if u["state"] in DISR_LADDER else u["state"]
            if u["state"] == "panicked":
                u["hex"], u["state"] = None, "eliminated"
                return "eliminated [13.21]"
            return u["state"]
        if self._fresh(u):
            u["state"] = "disrupted"
            return "disrupted"
        u["hex"], u["state"] = None, "eliminated"
        return "eliminated (Disrupted absorbed a D) [14.3]"

    def _auto_resolve_pending(self):
        """Resolve the loss pending automatically only when no real choice
        exists: a single defender and no B (B always offers the defender the
        substitute-D choice [14.2])."""
        p = self.s["pending"]
        if not p or p["kind"] != "loss" or "B" in p["letters"]:
            return
        defenders = [o for o in self._occupants(p["hex"])
                     if o["side"] == p["by"]]
        if len(defenders) != 1:
            return
        u = defenders[0]
        events = []
        letters = [c for c in p["letters"] if c != "B"]
        if letters.count("D") >= 2:
            # DD striking a lone defender twice eliminates it [14.33]
            letters = ["E"] + [c for c in letters if c == "E"]
        for c in letters:
            if u["state"] == "eliminated":
                break
            events.append(self._apply_letter(u, c, p["source"]))
        self.s["pending"] = None
        p["auto"] = events

    def _resolve_loss_verdict(self, side, action):
        p = self.s.get("pending")
        if not p or p["kind"] != "loss":
            return self._v(False, "no loss to resolve")
        if side != p["by"]:
            return self._v(False, "defender chooses losses [14.x]")
        picks = action.get("picks", [])
        need = [c for c in p["letters"] if c != "B"]
        if len(picks) != len(need):
            return self._v(False, f"{len(need)} results to allocate: {need}")
        for pk, letter in zip(picks, need):
            u = self.s["units"].get(str(pk.get("pid")))
            if not u or u["hex"] != p["hex"] or u["side"] != side:
                return self._v(False, "pick units in the affected hex")
        return self._v(True, "losses allocated")

    # ------------------------------------------------------------ breach [10/12]
    def _breach_verdict(self, side, action):
        p = self.s["phase"]
        if not p.endswith("_fire") or side != "Rom" or self.s.get("seg") != "Rom":
            return self._v(False, "Breach attacks: Roman fire segment only [4.12/4.22/10.1]")
        tgt = self.name_hex.get(action.get("target"), action.get("target"))
        if tgt not in self.hex_t0 or self.hex_t0[tgt] not in ELEVATED:
            return self._v(False, "Breach attacks target Elevated hexes [10.11]")
        if self.hex_t(tgt) == "breach":
            return self._v(False, "already breached")
        bf = 0
        for pid in action.get("attackers", []):
            u = self.s["units"].get(str(pid))
            if not u or u["side"] != "Rom":
                return self._v(False, "unknown/enemy attacker")
            if self.utype(u).get("breach_af") is None:
                return self._v(False, f"{u['pid']} cannot conduct Breach attacks [2.45]")
            if u["pid"] in self.s["fired"]:
                return self._v(False, f"{u['pid']} already attacked this phase")
            if self._dist(u["hex"], tgt) != 1:
                return self._v(False, "Rams/Armored Towers attack adjacent hexes [10.11]")
            crew = [o for o in self._occupants(u["hex"])
                    if self._fresh(o) and (self.utype(o)["cls"] == "heavy"
                                           or o["type"] == "velitae")]
            if not crew:
                return self._v(False, "Breach attack needs a Fresh manning unit [6.41/10.11]")
            bf += self.utype(u)["breach_af"]
        if bf == 0:
            return self._v(False, "no breach factors")
        return dict(self._v(True, f"BF {bf} vs {self.hex_name[tgt]}"), bf=bf)

    def _resolve_breach(self, side, action, verdict):
        tgt = self.name_hex.get(action["target"], action["target"])
        bf = verdict["bf"]
        # gate attacked through its Entrance hexside doubles AF [10.1]
        doubled = False
        if self.hex_t0[tgt] in GATES:
            for pid in action["attackers"]:
                u = self.s["units"][str(pid)]
                if tuple(sorted((u["hex"], tgt))) in self.entrances:
                    doubled = True
        if doubled:
            bf *= 2
        col = str(min(4, bf)) if bf < 4 else "4"
        die = self.roll_die()
        dmg = self.breach_t["table"][col][die - 1]
        self.s["breach"][tgt] = self.s["breach"].get(tgt, 0) + dmg
        for pid in action["attackers"]:
            self.s["fired"].append(str(pid))
        total = self.s["breach"][tgt]
        defense = self._breach_def(tgt)
        detail = {"bf": bf, "die": die, "damage": dmg, "total": total,
                  "defense": defense}
        if total >= defense:
            killed = [o["pid"] for o in self._occupants(tgt)]
            for o in self._occupants(tgt):
                o["hex"], o["state"] = None, "eliminated"
            detail["breached"] = True
            detail["occupants_eliminated"] = killed   # [12.2]
        return detail

    # ------------------------------------------------------------ melee [11/14]
    def _melee_approach(self, u, tgt):
        """(mult, why): how u attacks tgt hex [11.11-11.14]; None = cannot.
        Eligibility = could conceivably enter if vacated [11.1]."""
        frm = u["hex"]
        cost, why = self._entry_cost(u, frm, tgt, u["side"])
        if cost is None:
            return None, why
        mult = 1.0
        key = tuple(sorted((frm, tgt)))
        if key in self.stairs:
            mult = 0.5                        # [11.11/11.12]
        if self.hex_t(frm) == "breach" and self.hex_t(tgt) not in GROUND:
            mult = 0.5                        # [11.13]
        cls = self.utype(u)["cls"]
        if cls == "cavalry":
            if self.hex_t(frm) == "clear" and self.hex_t(tgt) == "clear":
                mult *= 2.0                   # [11.88]
            if self.hex_t(tgt) == "builtup":
                mult *= 0.5                   # [TEC]
        return mult, None

    def _melee_verdict(self, side, action):
        p = self.s["phase"]
        if p != f"{'rom' if side == 'Rom' else 'jud'}_melee":
            return self._v(False, f"not the {side} Melee Phase")
        tgt = self.name_hex.get(action.get("target"), action.get("target"))
        if tgt not in self.hex_t0:
            return self._v(False, "unknown target hex")
        enemy = self._enemy(side)
        defenders = [o for o in self._occupants(tgt) if o["side"] == enemy]
        if not defenders:
            return self._v(False, "no enemy units in the target hex")
        att = 0.0
        factions = set()
        atk_units = []
        for pid in action.get("attackers", []):
            u = self.s["units"].get(str(pid))
            if not u or u["side"] != side:
                return self._v(False, "unknown/enemy attacker")
            if not self._fresh(u):
                return self._v(False, f"{u['pid']} is not Fresh [11.1/16.2]")
            if u["pid"] in self.s["meleed"] and self.s.get("cc_hex") != tgt:
                return self._v(False, f"{u['pid']} already attacked this Melee Phase [11.1]")
            if self.utype(u)["cls"] in ("artillery", "siege_engine"):
                return self._v(False, "Artillery/Siege Engines may not melee [2.46/11.x]")
            if u["type"] == "cauldron":
                return self._v(False, "Cauldrons melee only defensively in this scenario scope")
            if any(o["state"] == "panicked" and o["side"] == side
                   for o in self._occupants(u["hex"])):
                return self._v(False, "no attacks from a hex containing a Panicked unit [17.22]")
            if self._dist(u["hex"], tgt) != 1:
                return self._v(False, "melee attacks adjacent hexes [11.1]")
            mult, why = self._melee_approach(u, tgt)
            if mult is None:
                return self._v(False, f"no legal approach: {why} [11.1]")
            att += self._melee_val(u) * mult
            factions.add(u.get("faction"))
            atk_units.append(u)
        if not atk_units:
            return self._v(False, "no attackers")
        return dict(self._v(True, "melee set"),
                    att=att, factions=len(factions - {None}) or 1)

    def _resolve_melee(self, side, action, verdict):
        tgt = self.name_hex.get(action["target"], action["target"])
        enemy = self._enemy(side)
        defenders = [o for o in self._occupants(tgt) if o["side"] == enemy]
        att = verdict["att"]
        t = self.hex_t(tgt)
        dmult = 3.0 if t == "fortress" else (2.0 if t in ELEVATED else 1.0)
        deff = sum(self._melee_val(d) for d in defenders
                   if self.utype(d)["cls"] != "siege_engine") * dmult
        deff = max(deff, 0.5)
        # flank [11.85]: every hex around defender enemy/impassable/enemy-ZOC
        zoc = self._zoc_map(side)
        ring = self._nb(tgt)
        if len(ring) == 6 and all(
                any(o["side"] == side for o in self._occupants(n))
                or n not in self.playable or n in zoc
                for n in ring):
            att *= 2.0
        # odds column: round in the defender's favor [11.81]
        import math
        cols = self.melee_t["odds_columns"]
        if att >= deff:
            ratio = int(att // deff)          # 16v9 -> 1-1; 14v6 -> 2-1
            idx = min(ratio, 7) + 2           # 1-1 at index 3 ... 7-1 at 9
            extreme = max(0, ratio - 7)       # +1 per multiple over 7-1 [11.83]
        else:
            ratio = math.ceil(deff / att)     # 6v8 -> 1-2
            idx = max(4 - ratio, 0)           # 1-2 at index 2 ... 1-4 at 0
            extreme = -max(0, ratio - 4)      # -1 per multiple under 1-4 [11.83]
        col = cols[min(idx, 9)]
        drm = extreme
        # defender in built-up (not edifice) [11.19]
        if t == "builtup":
            drm -= 1
        if any(self._fresh(d) and self.utype(d)["cls"] == "heavy"
               for d in defenders):
            drm -= 1
        atk_units = [self.s["units"][str(p)] for p in action["attackers"]]
        if any(self.utype(a).get("hq") == "commander" for a in atk_units):
            drm += 1
        if any(self.utype(d).get("hq") == "commander" for d in defenders):
            drm -= 1
        drm += self._cohort_drm(atk_units, +1) + self._cohort_drm(defenders, -1)
        if side == "Jud" and self.is_night():
            drm += 1                          # [18.25]
        if any(d["state"] == "routed" for d in defenders):
            drm += 1                          # [17.23]
        if any(o["state"] == "panicked" and o["side"] == enemy
               for h2 in [tgt] + self._nb(tgt) for o in self._occupants(h2)):
            drm += 2                          # [17.23]
        dfacs = {d.get("faction") for d in defenders} - {None}
        if len(dfacs) > 1:
            drm += 2 * (len(dfacs) - 1)       # [11.842]
        afacs = verdict["factions"]
        if afacs > 1:
            drm -= (afacs - 1)                # [11.842]
        die = self.roll_die()
        adj = die + drm
        key = str(max(-1, min(8, adj)))
        result = self.melee_t["rows"][key][cols.index(col)]
        for a in atk_units:
            self.s["meleed"].append(a["pid"])
        detail = {"att": att, "def": deff, "col": col, "die": die,
                  "drm": drm, "result": result}
        # continuous combat [11.87]: die >= 6 before or after drm
        self.s["cc_hex"] = tgt if (die >= 6 or adj >= 6) else None
        if result == "-":
            return detail
        letters = list(result)
        self._queue_melee_result(tgt, letters, enemy, side)
        detail["pending"] = self.s["pending"] is not None
        return detail

    def _cohort_drm(self, units, sign):
        by_cohort = {}
        for u in units:
            if u.get("cohort") and self._fresh(u):
                by_cohort.setdefault(u["cohort"], set()).add(u["type"])
        for _c, kinds in by_cohort.items():
            if kinds >= {"roman_veteran", "roman_line", "roman_recruit"}:
                return sign                   # [11.841] max one per attack
        return 0

    def _queue_melee_result(self, tgt, letters, defender, attacker):
        self.s["pending"] = {"kind": "loss", "hex": tgt, "letters": letters,
                             "by": defender, "source": "melee",
                             "attacker": attacker}
        self._auto_resolve_pending()
        if self.s["pending"] is None:
            # auto-resolved: any survivor with B retreats via its own pending
            if "B" in letters:
                self._queue_retreat(tgt, defender)

    def _queue_retreat(self, tgt, defender):
        movers = [o["pid"] for o in self._occupants(tgt)
                  if o["side"] == defender]
        if movers:
            self.s["pending"] = {"kind": "retreat", "hex": tgt,
                                 "pids": movers, "by": defender,
                                 "dist": [1, 2]}

    def _resolve_retreat_verdict(self, side, action):
        p = self.s.get("pending")
        if not p or p["kind"] != "retreat":
            return self._v(False, "no retreat to resolve")
        if side != p["by"]:
            return self._v(False, "the owning player routes retreats [15.1]")
        paths = action.get("paths", {})
        if set(paths.keys()) != set(p["pids"]):
            return self._v(False, f"retreat paths required for: {p['pids']}")
        enemy = self._enemy(side)
        zoc = self._zoc_map(enemy)
        heavy_zoc = self._heavy_ground_zoc(enemy)
        for pid, names in paths.items():
            u = self.s["units"][pid]
            path = [self.name_hex.get(n, n) for n in names]
            if not path or path[0] != u["hex"]:
                return self._v(False, "retreat path must start at the unit's hex")
            lo, hi = p["dist"]
            steps = len(path) - 1
            maxd = hi
            if u["hex"] in heavy_zoc:
                maxd = 1                      # [14.21]
            if not (lo <= steps <= maxd):
                return self._v(False, f"retreat {lo}-{maxd} hexes [14.2/14.21]")
            prev = path[0]
            for h in path[1:]:
                if h not in self._nb(prev):
                    return self._v(False, "retreat path not adjacent")
                if h in zoc:
                    return self._v(False, "may not retreat into an enemy ZOC [7.5/15.1]")
                if any(o["side"] == enemy for o in self._occupants(h)):
                    return self._v(False, "may not retreat into an enemy-occupied hex")
                if any(o["state"] == "panicked" for o in self._occupants(h)):
                    return self._v(False, "may not retreat into a hex with a Panicked unit [15.1]")
                c, why = self._entry_cost(u, prev, h, side)
                if c is None:
                    return self._v(False, f"illegal retreat terrain: {why} [15.1]")
                prev = h
        return self._v(True, "retreat routed")

    # ------------------------------------------------------------ rally [17]
    def _rally_side(self, side, artillery_pids):
        """Auto-resolve the mandatory Rally Phase [17.1]: HQ first, then the
        board sweep in alpha-numerical order (row A before row B; A1 before
        A2 [17.1]). Returns per-unit events for the log."""
        cc = self._cc_map(side)
        enemy = self._enemy(side)
        zoc = self._zoc_map(enemy)
        units = [u for u in self.s["units"].values()
                 if u["side"] == side and u["hex"] is not None
                 and u["state"] in ("disrupted", "routed", "panicked")]
        def order_key(u):
            hq = 0 if self.utype(u)["cls"] == "hq" else 1
            name = self.hex_name[u["hex"]]
            letters = "".join(c for c in name if c.isalpha())
            num = int(name[len(letters):])
            return (hq, len(letters), letters, num, u["pid"])
        events = []
        for u in sorted(units, key=order_key):
            cls = self.utype(u)["cls"]
            if cls in ("artillery", "cauldron") and \
                    u["pid"] not in artillery_pids:
                continue                      # artillery rally optional [17.1]
            drm = 0
            occ = self._occupants(u["hex"])
            nbs = [o for n in self._nb(u["hex"]) for o in self._occupants(n)]
            own_hq_ok = self._hq_affects(u)
            best = 0
            for o in occ:
                if o["side"] == side and self.utype(o)["cls"] == "hq" \
                        and self._fresh(o) and own_hq_ok(o):
                    best = min(best, -3 if self.utype(o).get("hq") == "commander" else -2)
            for o in nbs:
                if o["side"] == side and self.utype(o)["cls"] == "hq" \
                        and self._fresh(o) and own_hq_ok(o):
                    best = min(best, -2 if self.utype(o).get("hq") == "commander" else -1)
            drm += best
            if not self.in_cc(u, cc):
                drm += 1                      # [5.12]
            if self._enemy_missile_threat(u):
                drm += 1                      # [17.24]
            if self.is_night():
                drm += 1                      # [18.22]
            if u["hex"] in zoc:
                drm += 1
            if any(o["side"] == enemy and self.utype(o)["cls"] not in
                   ("artillery", "siege_engine") for o in nbs):
                drm += 1
            if u["state"] == "routed" or any(
                    o["side"] == side and o["state"] == "routed" for o in occ):
                drm += 1                      # max +1
            if u["state"] == "panicked" or any(
                    o["side"] == side and o["state"] == "panicked"
                    for o in occ + nbs):
                drm += 2                      # max +2
            for hq in self.s["units"].values():
                if hq["side"] == side and self.utype(hq)["cls"] == "hq" \
                        and own_hq_ok(hq):
                    if hq["state"] == "routed":
                        drm += 1              # [17.3]
                    elif hq["state"] == "panicked":
                        drm += 2
            die = self.roll_die()
            adj = die + drm
            rn = self.utype(u).get("rally") or 0
            before = u["state"]
            if adj <= rn:
                u["state"] = {"disrupted": "fresh", "routed": "disrupted",
                              "panicked": "routed"}[u["state"]]
            elif adj >= 9:
                u["hex"], u["state"] = None, "eliminated"
            elif adj == 8 and u["state"] in ("disrupted", "routed"):
                u["state"] = "panicked"
            elif adj == 7 and u["state"] == "disrupted":
                u["state"] = "routed"
            events.append({"pid": u["pid"], "die": die, "drm": drm,
                           "was": before, "now": u["state"]})
        return events

    def _hq_affects(self, u):
        side = u["side"]
        def ok(hq):
            kind = self.utype(hq).get("hq")
            if kind == "commander":
                return True
            if side == "Jud" and (u["type"] in ("zealot", "cauldron")
                                  or self.utype(u)["cls"] == "artillery"):
                return False                  # only the Commander [17.3]
            return hq.get("faction") == u.get("faction")
        return ok

    def _enemy_missile_threat(self, u):
        enemy = self._enemy(u["side"])
        for e in self.s["units"].values():
            if e["side"] != enemy or e["hex"] is None or not self._fresh(e):
                continue
            if not self.utype(e).get("missile"):
                continue                      # rocks/artillery don't count [17.24]
            if self.utype(e)["cls"] == "artillery":
                continue
            d = self._dist(e["hex"], u["hex"])
            if self.is_night() and d > 1:
                continue                      # [18.22]
            if self._range_af(e, d) is None:
                continue
            ok, _d, _w = self._lof(e["hex"], u["hex"])
            if ok:
                return True
        return False

    # ------------------------------------------------------------ propose
    def propose(self, side, action):
        if self.s.get("over"):
            return self._v(False, "game over")
        a = action.get("type")
        if self.s.get("pending"):
            if a == "resolve_loss":
                return self._resolve_loss_verdict(side, action)
            if a == "resolve_retreat":
                return self._resolve_retreat_verdict(side, action)
            return self._v(False, f"a {self.s['pending']['kind']} pending must be resolved first")
        phase = self.s["phase"]
        if a == "deploy":
            return self._deploy_verdict(side, action)
        if a == "deploy_done":
            return self._deploy_done_verdict(side)
        if a == "move":
            if phase != f"{'rom' if side == 'Rom' else 'jud'}_move":
                return self._v(False, f"not the {side} Movement Phase")
            u = self.s["units"].get(str(action.get("pid")))
            if not u:
                return self._v(False, "unknown unit")
            path = [self.name_hex.get(h, h) for h in action.get("path", [])]
            if any(p not in self.hex_t0 for p in path):
                return self._v(False, "path contains unknown hexes")
            return self._move_verdict(side, u, path)
        if a == "fire":
            if self.tier < 2:
                return self._v(False, "combat is umpired at tier 1")
            return self._fire_verdict(side, action)
        if a == "breach_attack":
            if self.tier < 2:
                return self._v(False, "combat is umpired at tier 1")
            return self._breach_verdict(side, action)
        if a == "melee":
            if self.tier < 2:
                return self._v(False, "combat is umpired at tier 1")
            return self._melee_verdict(side, action)
        if a == "end_phase":
            if phase in ("deploy_jud", "deploy_rom"):
                return self._v(False, "finish deployment with deploy_done")
            if side != self.side_to_move():
                return self._v(False, "not your phase")
            return self._v(True, f"end of {phase}"
                           + (f" ({self.s['seg']} segment)" if self.s.get("seg") else ""))
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
        if h not in self.hex_t0:
            return self._v(False, "unknown hex")
        zone = self.jud_zone if side == "Jud" else self.rom_zone
        if h not in zone:
            why = ("inside the New City on or within its outer walls (card)"
                   if side == "Jud" else
                   "outside Jerusalem, >= 5 hexes from any Elevated hex (card)")
            return self._v(False, f"deployment must be {why}")
        cls = self.utype(u)["cls"]
        if cls == "cavalry" and self.hex_t(h) in ELEVATED:
            return self._v(False, "Cavalry may never enter Elevated hexes [6.2]")
        if cls in ("siege_engine", "artillery") and self.hex_t(h) in ELEVATED:
            return self._v(False, "Siege Engines/Artillery do not deploy on Elevated hexes [6.4/8.4]")
        if cls == "cauldron" and self.hex_t(h) not in ELEVATED:
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
            self.s["control"][h] = side
            return {"placed": self.hex_name[h]}
        if a == "deploy_done":
            if self.s["phase"] == "deploy_jud":
                self.s["deploy_done"]["Jud"] = True
                self.s["phase"] = "deploy_rom"
                return {"next": "deploy_rom"}
            self.s["deploy_done"]["Rom"] = True
            self.s["turn"] = 1
            self.s["phase"] = self.scenario["game"].get("opening_phase", "rom_rally")
            if self.s["phase"].endswith("_fire"):
                self.s["seg"] = self._enemy(
                    "Rom" if self.s["phase"].startswith("rom_") else "Jud")
            return {"next": self.s["phase"], "turn": 1,
                    "seg": self.s.get("seg")}
        if a == "move":
            u = self.s["units"][str(action["pid"])]
            path = [self.name_hex.get(h, h) for h in action["path"]]
            entering = u["hex"] is None
            u["hex"] = path[-1]
            for h in (path if entering else path[1:]):
                self.s["control"][h] = side
            if entering:
                self.s["entry_queue"] = [q for q in self.s["entry_queue"]
                                         if q["pid"] != u["pid"]]
            return {"to": self.hex_name[path[-1]]}
        if a == "fire":
            return self._resolve_missile(side, action, verdict)
        if a == "breach_attack":
            return self._resolve_breach(side, action, verdict)
        if a == "melee":
            return self._resolve_melee(side, action, verdict)
        if a == "resolve_loss":
            return self._apply_loss(side, action)
        if a == "resolve_retreat":
            return self._apply_retreat(side, action)
        if a == "end_phase":
            return self._advance_phase(action)
        raise AssertionError(f"apply fell through for {a!r}")

    def _apply_loss(self, side, action):
        p = self.s["pending"]
        need = [c for c in p["letters"] if c != "B"]
        events = []
        for pk, letter in zip(action["picks"], need):
            u = self.s["units"][str(pk["pid"])]
            if u["state"] == "eliminated":
                continue
            events.append({"pid": u["pid"],
                           "event": self._apply_letter(u, letter, p["source"])})
        self.s["pending"] = None
        if "B" in p["letters"] and p["source"] == "melee":
            self._queue_retreat(p["hex"], side)
        elif p["source"] == "melee":
            movers = [e for e in events if e["event"] == "disrupted"]
            if movers and self.hex_t(p["hex"]) not in ("fortress",):
                # melee-disrupted units retreat immediately [14.3/14.31]
                self.s["pending"] = {"kind": "retreat", "hex": p["hex"],
                                     "pids": [e["pid"] for e in movers],
                                     "by": side, "dist": [1, 2]}
        return {"events": events,
                "retreat_pending": self.s["pending"] is not None}

    def _apply_retreat(self, side, action):
        p = self.s["pending"]
        out = []
        for pid in p["pids"]:
            path = [self.name_hex.get(n, n) for n in action["paths"][pid]]
            u = self.s["units"][pid]
            crowded = 0
            for h in path[1:]:
                if self._combat_count(self._occupants(h)) >= \
                        self._stack_limit(h, side):
                    crowded += 1              # [15.3] +1 level per such hex
            u["hex"] = path[-1]
            for _ in range(crowded):
                i = DISR_LADDER.index(u["state"]) if u["state"] in DISR_LADDER else 3
                if i >= 3:
                    u["hex"], u["state"] = None, "eliminated"
                    break
                u["state"] = DISR_LADDER[i + 1]
            out.append({"pid": pid, "to": self.hex_name.get(u["hex"], None),
                        "state": u["state"]})
        self.s["pending"] = None
        return {"retreated": out}

    def _advance_phase(self, action=None):
        p = self.s["phase"]
        result = {"ended": p}
        if p.endswith("_fire") and self.s.get("seg"):
            phasing = "Rom" if p.startswith("rom_") else "Jud"
            if self.s["seg"] != phasing:
                self.s["seg"] = phasing       # phasing side fires last
                result["next"] = p
                result["seg"] = phasing
                return result
            self.s["seg"] = None
        if p.endswith("_rally") and self.tier >= 2:
            side = "Rom" if p.startswith("rom_") else "Jud"
            result["rally"] = self._rally_side(
                side, [str(x) for x in ((action or {}).get("artillery") or [])])
        i = self.PHASES.index(p)
        self.s["fired"] = []
        self.s["fired_hexes"] = []
        self.s["cc_hex"] = None
        if p == "jud_melee":
            self.s["meleed"] = []
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
            if p.endswith("_melee"):
                self.s["meleed"] = []
            self.s["phase"] = self.PHASES[i + 1]
        if self.s["phase"].endswith("_fire"):
            phasing = "Rom" if self.s["phase"].startswith("rom_") else "Jud"
            self.s["seg"] = self._enemy(phasing)   # non-phasing fires first
            result["seg"] = self.s["seg"]
        if self.s["phase"] == "jud_move" and self.s["turn"] >= \
                self.scenario["reinforcement"]["from_turn"] and self.s["pool"]:
            result["reinforcement"] = self._roll_reinforcements()
        result["next"] = self.s["phase"]
        return result

    def _roman_builtup_count(self):
        return sum(1 for h, s in self.s["control"].items()
                   if s == "Rom" and self.hex_t0.get(h) == "builtup")

    def _roll_reinforcements(self):
        cfg = self.scenario["reinforcement"]
        count = sum(self.roll_die() for _ in range(int(cfg["count_dice"])))
        entry = self.roll_die()
        gate_name = cfg["entry_die"]["odd" if entry % 2 else "even"]
        gate = self.name_hex[gate_name]
        alt = self.name_hex[cfg["entry_die"]["even" if entry % 2 else "odd"]]

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
        leader = next((p_ for p_ in pool if p_.get("leader_first")), None)
        if leader:
            draw.append(leader)
        r = self._rng()
        others = [p_ for p_ in pool if not p_.get("leader_first")]
        for _ in range(min(count, len(others))):
            k = int(r.random() * len(others))
            self.s["rng_calls"] += 1
            draw.append(others.pop(k))
        placed = []
        for p_ in draw:
            self.s["units"][p_["pid"]] = {
                "pid": p_["pid"], "slot": p_["slot"], "side": "Jud",
                "type": p_["type"], "faction": p_.get("faction"),
                "hex": None, "state": "fresh"}
            self.s["entry_queue"].append({"pid": p_["pid"], "gate": gate})
            placed.append(p_["pid"])
        self.s["pool"] = [p_ for p_ in pool if p_["pid"] not in placed]
        return {"rolled": count, "entry_die": entry,
                "gate": self.hex_name[gate], "entered": placed}

    def enterable_from(self, pid):
        for q in self.s["entry_queue"]:
            if q["pid"] == pid:
                return q["gate"]
        return None
