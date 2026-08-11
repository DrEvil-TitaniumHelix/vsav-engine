"""
soj.py - The Siege of Jerusalem (AH 1989) legality gate.

The Assault of Gallus introductory scenario: free deployment, per-class TEC
movement, SoJ zones of control, stacking, hex control [18.3], the Giora
reinforcement, the Siege Engine locked pushing-crew stack with tracked
Directional-Arrow facing and the 2.45 white-side MA-0 flip, and the
validated combat systems: Missile Table fire (LOF, concentration,
mandatory targets, wall-attack bonus, rocks), Ram/Armored Tower Breach
attacks vs the Facing-arrow hex with cumulative damage and breached-wall state, Melee
Table combat with drm/strength modifiers, defender-choice loss pendings,
retreats toward Refuge, the disruption ladder (Fresh-Disrupted-Routed-
Panicked), the Rally Phase, Command Control, and night-turn effects.

Coverage-matrix regime (spec #13 as amended 2026-08-09): the scenario's
COVERAGE_MATRIX.md is the playability instrument. Open rows (the scenario
rules_scope `build_open` list) are defects that block playability - never
player-umpired corners; "umpired" is retired as a state. The gate ships
whole or not at all.

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

# The hex-grid direction ring in (d_col, d_N) axial deltas (N = row - col//2,
# the printed-map diagonal number). A Siege Engine's printed Directional
# Arrow [2.45/8.6/10.11] is stored as an index into DIRS (u["facing"]) so it
# survives movement and hashes with the unit.
DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, -1), (-1, 1))


class SoJGame(GateGame):
    HASH_KEYS = ("units", "turn", "phase", "seg", "seed", "rng_calls",
                 "control", "pool", "entry_queue", "deploy_done", "breach",
                 "fired", "fired_hexes", "meleed", "pending", "cc_hex",
                 "escaped", "markers", "melee_hexes", "esc", "testudo",
                 "pmoved")
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
        self.s.setdefault("markers", [])   # pre-B9/B10 in-flight saves
        self.s.setdefault("melee_hexes", [])
        self.s.setdefault("esc", [])
        self.s.setdefault("testudo", [])
        self.s.setdefault("pmoved", False)

    def rules_scope(self):
        """Matrix-regime composition (spec #13 as amended 2026-08-09),
        shadowing the tiered base: the scenario declares `enforced` /
        `enforced_tier2` (true claims only) and `build_open` — the open
        coverage-matrix rows, presented as not-enforced DEFECTS that block
        playability, never as umpired corners. Sandbox (tier < 2) makes no
        combat enforcement claims at all."""
        sc = self.scenario.get("rules_scope", {})
        rulings = sc.get("rulings", [])
        if self.tier >= 2:
            return {"enforced": (sc.get("enforced", []) +
                                 sc.get("enforced_tier2", [])),
                    "not_enforced": sc.get("build_open", []),
                    "rulings": rulings,
                    "banner": "BUILD IN PROGRESS - NOT PLAYABLE by the "
                              "coverage-matrix standard (open rows below)"}
        return {"enforced": sc.get("enforced", []),
                "not_enforced": (sc.get("enforced_tier2", []) +
                                 sc.get("build_open", [])),
                "rulings": rulings,
                "banner": "SANDBOX MODE - combat is not gated and no "
                          "enforcement claim is made for it"}

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
        self.crests = set()
        self.roads = set()
        for k, v in self.terr.get("sides", {}).items():
            if v.get("staircase"):
                self.stairs.add(tuple(sorted(k.split("|"))))
            if v.get("entrance"):
                self.entrances.add(tuple(sorted(k.split("|"))))
            if v.get("crest"):
                # [11.17] slope|clear boundary whose slope side is shaded
                # dark brown on the printed map (ingest/crest_hexsides.json)
                self.crests.add(tuple(sorted(k.split("|"))))
            if v.get("road"):
                # [8.94] interior roads (city hexsides only - outside roads
                # are destroyed; ingest/road_hexsides.json)
                self.roads.add(tuple(sorted(k.split("|"))))
        self._build_elevation_regions()
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
        for dc, dn in DIRS:
            c2, n2 = c + dc, N + dn
            k = f"{c2:02d}{n2 + c2 // 2:02d}"
            if k in self.hex_t0:
                out.append(k)
        return out

    def _dir_of(self, frm, to):
        """DIRS index from frm to an adjacent hex, else None."""
        c, r = int(frm[:2]), int(frm[2:])
        c2, r2 = int(to[:2]), int(to[2:])
        d = (c2 - c, (r2 - c2 // 2) - (r - c // 2))
        return DIRS.index(d) if d in DIRS else None

    def _facing_hex(self, u):
        """The hex a Siege Engine's Directional Arrow indicates [10.11];
        None off-map or while the facing is unset."""
        h, d = u.get("hex"), u.get("facing")
        if h is None or d is None:
            return None
        c = int(h[:2]) + DIRS[d][0]
        n = int(h[2:]) - int(h[:2]) // 2 + DIRS[d][1]
        k = f"{c:02d}{n + c // 2:02d}"
        return k if k in self.hex_t0 else None

    def _dist(self, a, b):
        ca, ra = int(a[:2]), int(a[2:])
        cb, rb = int(b[:2]), int(b[2:])
        na, nb_ = ra - ca // 2, rb - cb // 2
        dq, dr = cb - ca, nb_ - na
        return max(abs(dq), abs(dr), abs(dq + dr))

    def _build_elevation_regions(self):
        """[9.52] 'There are different elevations of Ground Level as
        distinguished by the Slopes.' Elevation regions = maximal connected
        areas of non-slope ground-level terrain (clear/builtup) on the STATIC
        map; slope bands and Elevated hexes separate them. Two hexes in the
        same region are at the same elevation; a slope hex (or a breached
        wall) belongs to no region and counts as an elevation transition."""
        self._elev = {}
        comp = 0
        for h, t in self.hex_t0.items():
            if t not in ("clear", "builtup") or h in self._elev:
                continue
            comp += 1
            stack = [h]
            self._elev[h] = comp
            while stack:
                cur = stack.pop()
                for n in self._nb(cur):
                    if n not in self._elev and \
                            self.hex_t0[n] in ("clear", "builtup"):
                        self._elev[n] = comp
                        stack.append(n)

    def _compute_playable(self, cfg):
        """A4 hard bound. The card plays Gallus 'only on the North Wall from
        O50 to Women's Gate to QQ31'; the Old City is off the battlefield and
        its terrain is deliberately unencoded. Two southern_bound diagonals
        (printed-number caps anchored on the arc ends O50 and QQ31/QQ32) stop
        the outside flood from wrapping around the wall ends, and the Elevated
        fabric counts as playable only where it borders battlefield ground —
        which drops the typed Old City strongpoints (P51/O53/Q50... cluster)
        from play and from the Judaean deployment zone."""
        caps = []
        for b in cfg["southern_bound"]:
            lo, hi = (self._col_num(c) for c in b["cols"].split("-"))
            caps.append((lo, hi, int(b["max_number"])))

        def bounded_out(h):
            col = int(h[:2])
            n = int(h[2:]) - col // 2
            return any(lo <= col <= hi and n > mx for lo, hi, mx in caps)

        elevated = {h for h, t in self.hex_t0.items() if t in ELEVATED}
        seed = self.name_hex[cfg["outside_seed"]]
        seen = set()
        stack = [seed]
        while stack:
            h = stack.pop()
            if (h in seen or h in elevated or h in self.new_city
                    or bounded_out(h)):
                continue
            seen.add(h)
            stack.extend(self._nb(h))
        self.outside = seen
        ground = seen | self.new_city
        barrier = {h for h in elevated
                   if any(n in ground for n in self._nb(h))}
        self.playable = ground | barrier

    @staticmethod
    def _col_num(letters):
        return ord(letters[0]) - 64 + (26 if len(letters) > 1 else 0)

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
            "pending": None, "cc_hex": None, "escaped": [], "markers": [],
            "melee_hexes": [], "esc": [], "testudo": [],
            "pmoved": False, "winner": None, "over": False,
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

    def _se_crewed(self, u):
        """2.45 crew condition: a Fresh pushing Heavy Infantry or Velitae
        unit that started this MPh beneath the engine (the crew0 snapshot)
        and is still beneath it. False = the counter's white side."""
        for p in u.get("crew0", []):
            x = self.s["units"].get(p)
            if x and self._fresh(x) and x["hex"] == u["hex"] \
                    and not x.get("up"):
                return True
        return False

    def _ma(self, u):
        t = self.utype(u)
        if t["cls"] == "siege_engine":
            # white side up = no crew at the start of its MPh, MA 0 [2.45]
            return float(t["ma"][0 if self._se_crewed(u) else 1])
        return float(t["ma"][0 if self._fresh(u) else 1])

    def _melee_val(self, u):
        t = self.utype(u)
        return t["melee"][0 if self._fresh(u) else 1]

    def _occupants(self, h):
        return [u for u in self.s["units"].values() if u["hex"] == h]

    def _enemy(self, side):
        return "Jud" if side == "Rom" else "Rom"

    # ------------------------------------------- markers [11.4/13.21/14.5]
    def _esc_at(self, h):
        for e in self.s["esc"]:
            if e["hex"] == h:
                return e
        return None

    def _esc_sweep(self):
        keep = []
        for e in self.s["esc"]:
            b = self.s["units"].get(e["base"])
            if b and b["hex"] == e["hex"] and self._fresh(b):
                keep.append(e)
                continue
            for o in self._occupants(e["hex"]):
                o.pop("up", None)
        self.s["esc"] = keep
        hexes = {e["hex"] for e in self.s["esc"]} | {
            u["hex"] for u in self.s["units"].values()
            if u["hex"] is not None and u["type"] in ("tower",
                                                      "armored_tower")}
        for x in self.s["units"].values():
            if x.get("up") and x["hex"] not in hexes:
                x.pop("up")

    def _se_at(self, h):
        for o in self._occupants(h):
            if self.utype(o)["cls"] == "siege_engine":
                return o
        return None

    def _pushers(self, h):
        return [o for o in self._occupants(h)
                if not o.get("up")
                and self.utype(o)["cls"] not in ("hq", "siege_engine")]

    def _riders(self, h):
        return [o for o in self._occupants(h)
                if o.get("up") and self.utype(o)["cls"] != "hq"]

    def _tower_fall(self, h):
        se = self._se_at(h)
        if se and se["type"] in ("tower", "armored_tower") and not any(
                o["side"] == "Rom" and self.utype(o)["cls"] != "siege_engine"
                for o in self._occupants(h)):
            self._eliminate(se)
            return se["pid"]
        return None

    def _tst_at(self, h, broken=None):
        for t in self.s["testudo"]:
            if t["hex"] == h and (broken is None
                                  or bool(t.get("broken")) == broken):
                return t
        return None

    def _tst_join_ok(self, u, t):
        if u["side"] != "Rom":
            return False, "Judaeans may not join a Testudo [6.6/6.61]"
        cls = self.utype(u)["cls"]
        occ = self._occupants(t["hex"])
        hv = sum(1 for o in occ if self.utype(o)["cls"] == "heavy")
        vl = sum(1 for o in occ if o["type"] == "velitae")
        hqn = sum(1 for o in occ if self.utype(o)["cls"] == "hq")
        if cls == "hq":
            if u["state"] == "panicked":
                return False, "a Panicked HQ may not join a Testudo [6.61/16.4]"
            if hqn >= 1:
                return False, "one HQ may stack within a Testudo formation [6.6]"
        elif u["type"] == "velitae":
            if u["state"] not in ("fresh", "disrupted"):
                return False, "only a Fresh or Disrupted Velitae may join a Testudo [6.61/16.4]"
            if vl >= 1 or hv > 2:
                return False, "a Testudo holds one Velitae with at most two Heavy Infantry - fully occupied [6.6/16.4]"
        elif cls == "heavy":
            if not self._fresh(u):
                return False, "only Fresh Heavy Infantry may join a Testudo [6.61/16.4]"
            if hv >= 3 or (vl and hv >= 2):
                return False, "a Testudo holds at most three Heavy Infantry (two with a Velitae) - fully occupied [6.6]"
        else:
            return False, "only Heavy Infantry, Velitae, and a HQ may join a Testudo [6.1/6.61]"
        if self.utype(u).get("hq") != "commander" \
                and u.get("faction") != t.get("legion"):
            return False, "units of different Legions may not form or join a Testudo [6.6]"
        return True, None

    def _tst_sweep(self):
        out = []
        for t in self.s["testudo"]:
            occ = self._occupants(t["hex"])
            if t.get("broken"):
                if any(o["pid"] in t["members"] for o in occ):
                    out.append(t)
                continue
            if not occ:
                continue
            fresh_hi = sum(1 for o in occ
                           if self.utype(o)["cls"] == "heavy"
                           and self._fresh(o))
            if fresh_hi < 2 or any(o["state"] == "panicked" for o in occ):
                out.append({"hex": t["hex"], "broken": True,
                            "members": sorted(o["pid"] for o in occ)})
                continue
            out.append(t)
        self.s["testudo"] = out

    def _melee_stay_ok(self, h):
        return (self.hex_t(h) == "fortress"
                or self._tst_at(h, broken=False) is not None
                or any(self.utype(o)["cls"] == "siege_engine"
                       for o in self._occupants(h)))

    def _breach_link(self, b):
        return any(self.hex_t(n) == "breach" for n in self._nb(b))

    def _markers_at(self, h, cat=None):
        """Wreck/Elim markers in hex h; cat filters on the marker's unit
        class ('siege_engine' = Wreck, 'artillery' = Elim)."""
        return [m for m in self.s["markers"]
                if m["hex"] == h and (cat is None or m["cls"] == cat)]

    def _eliminate(self, u):
        """The single elimination door - every path that kills a unit goes
        through here so the marker rules cannot be skipped. An eliminated
        Siege Engine leaves a WRECK in its hex [11.4/14.5]; eliminated
        non-Cauldron Artillery leaves the Elim marker [13.21]. The
        13.21-vs-14.5 marker-identity conflict for Artillery is registered
        in source_defects and proven outcome-equivalent inside Gallus (R7
        holds the campaign-scope question). Cauldrons are 'eliminated
        normally without leaving Elim markers behind' [13.21]; no other
        class leaves anything. Markers persist to the end of the Assault
        Period = the whole Gallus scenario (14.5's 'Assault Phase' removal
        wording is a registered dangling reference)."""
        cls = self.utype(u)["cls"]
        if u["hex"] is not None and cls in ("siege_engine", "artillery"):
            self.s["markers"].append(
                {"hex": u["hex"], "cls": cls, "type": u["type"],
                 "kind": "wreck" if cls == "siege_engine" else "elim",
                 "side": u["side"], "pid": u["pid"]})
        u["hex"], u["state"] = None, "eliminated"

    # ------------------------------------------------------------ stacking
    def _stack_limit(self, h, side):
        t = self.hex_t(h)
        lim = self.game.spec["movement"]["tec"]["stacking"].get(
            t, [3, 2] if t == "clear" else [2, 2])
        return lim[0] if side == "Rom" else lim[1]

    def _combat_count(self, occ):
        free_cls = {"artillery", "cauldron", "hq", "siege_engine"}
        return sum(1 for u in occ if self.utype(u)["cls"] not in free_cls)

    def _stack_check(self, h, side, adding, skip=()):
        add = adding if isinstance(adding, list) else [adding]
        occ = [o for o in self._occupants(h) if o["pid"] not in skip] + add
        if self._combat_count(occ) > self._stack_limit(h, side):
            return f"stacking limit exceeded in {self.hex_name[h]} [TEC/6.0]"
        for cls in ("artillery", "hq", "siege_engine"):
            n = sum(1 for u in occ if self.utype(u)["cls"] in
                    ({cls, "cauldron"} if cls == "artillery" else {cls}))
            # Wreck/Elim markers hold the dead unit's slot 'as if they were
            # not eliminated' [11.4/14.5/13.21]
            n += len(self._markers_at(h, cls))
            cap = 2 if (cls == "artillery" and self.hex_t(h) == "fortress") else 1
            if n > cap:
                return f"max one {cls.replace('_', ' ')} per hex [6.3/6.4/@]"
        has_cav = any(self.utype(u)["cls"] == "cavalry" for u in occ)
        has_inf = any(self.utype(u)["cls"] in ("heavy", "light") for u in occ)
        if has_cav and has_inf:
            return "Infantry may not stack with Cavalry [6.1/6.2]"
        return None

    # ------------------------------------------------------------ ZOC [7]
    def _unit_zoc(self, u):
        """The hexes over which u exerts ZOC [7.1x], ignoring night (the
        callers gate on is_night). Single source for both the map union and
        the per-unit 9.7 exerter test."""
        if u["hex"] is None or not self._fresh(u):
            return set()
        cls = self.utype(u)["cls"]
        if cls == "hq":
            return set()          # HQ exert none [2.4 exception / 7.321]
        if u["side"] == "Rom" and (
                self._esc_at(u["hex"]) is not None
                or any(self.utype(o)["cls"] == "siege_engine"
                       for o in self._occupants(u["hex"]))):
            return set()
        if self._tst_at(u["hex"], broken=False) is not None:
            return set()
        h = u["hex"]
        t = self.hex_t(h)
        out = set()
        if cls in ("heavy", "light") and (t in GROUND or t == "builtup"):
            out = {n for n in self._nb(h) if self.hex_t(n) in GROUND}
        elif cls in ("heavy", "light") and t in GATES:
            out = {n for n in self._nb(h)
                   if self.hex_t(n) in ELEVATED
                   or tuple(sorted((h, n))) in self.entrances}
        elif cls in ("heavy", "light") and t in ELEVATED:
            out = {n for n in self._nb(h) if self.hex_t(n) in ELEVATED}
        elif cls == "cavalry" and (t in GROUND or t == "builtup"):
            out = {n for n in self._nb(h) if self.hex_t(n) in GROUND}
        return out

    def _zoc_map(self, side):
        if self.is_night():
            return set()          # no ZOC at night [7.2]
        zoc = set()
        for u in self.s["units"].values():
            if u["side"] == side:
                zoc |= self._unit_zoc(u)
        return zoc

    def _heavy_ground_zoc(self, side):
        if self.is_night():
            return set()
        out = set()
        for u in self.s["units"].values():
            if (u["side"] == side and u["hex"] is not None
                    and self.utype(u)["cls"] == "heavy"
                    and self.hex_t(u["hex"]) in (GROUND | {"builtup"})):
                out |= {n for n in self._unit_zoc(u)
                        if self.hex_t(n) in GROUND}
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

        if t_to in ELEVATED and u.get("up") and cls in ("heavy", "light") \
                and self._fresh(u) and self._esc_at(frm) is not None \
                and to in self._nb(frm):
            return 2.0, None

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

        # ---- ground-to-ground [8.94/8.95 interior roads]
        road = key in self.roads
        if cls in ("cavalry", "artillery"):
            if t_frm == "builtup" and not road:
                return None, ("Cavalry and Artillery may exit Built-up hexes "
                              "only through road hexsides [8.95]")
            if t_to == "builtup":
                if not road:
                    return None, ("Cavalry and Artillery may enter Built-up "
                                  "hexes only through road hexsides [8.95]")
                return 0.5, None    # along the road [8.94/12.4]
        if t_to == "breach" and cls in ("cavalry", "artillery",
                                        "siege_engine") \
                and not self._breach_link(to):
            return None, ("Artillery, Testudos, Cavalry and Siege Engines "
                          "enter a Breach only if it is adjacent to a "
                          "connecting Breach of the same wall [8.96]")
        base = self._ground_cost(u, to, side)
        if base is None:
            return None, "class may not enter that terrain [TEC]"
        if road:
            return 0.5, None        # road movement rate [8.94/12.4, Gen 26-4]
        return base, None

    def _refuge_dist(self, side, h):
        """Distance to Refuge: Judaean = the south gates toward the Temple
        Quarter (exit = removed from play, Bruce-approved scope call);
        Roman = the nearest board edge, approximated by the north edge
        (lowest row) [15.4]."""
        if side == "Jud":
            return min(self._dist(h, g) for g in self.refuge_gates)
        return int(h[2:])

    def _road_ref_dist(self, side, zoc):
        if side != "Jud":
            return {}
        enemy = self._enemy(side)

        def blocked(h):
            return h in zoc or any(o["side"] == enemy
                                   for o in self._occupants(h))
        rd = {}
        frontier = []
        for g in self.refuge_gates:
            if blocked(g):
                continue
            for n in self._nb(g):
                if n not in rd and not blocked(n) and any(
                        tuple(sorted((n, m))) in self.roads
                        for m in self._nb(n)):
                    rd[n] = 0
                    frontier.append(n)
        while frontier:
            nxt = []
            for h in frontier:
                for n in self._nb(h):
                    if tuple(sorted((h, n))) in self.roads \
                            and n not in rd and not blocked(n):
                        rd[n] = rd[h] + 1
                        nxt.append(n)
            frontier = nxt
        return rd

    def _refuge_laggards(self, side, skip=None, states=("routed",
                                                        "panicked")):
        out = []
        for u in self.s["units"].values():
            if u["side"] != side or u["hex"] is None or u["pid"] == skip \
                    or u["state"] not in states:
                continue
            if any(self._move_verdict(side, u, [u["hex"], n])["legal"]
                   for n in sorted(self._nb(u["hex"]))):
                out.append(u["pid"])
        return sorted(out)

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

    def _move_verdict(self, side, u, path, crew=None, face=None, up=False,
                      tst=False):
        entry_gate = self.enterable_from(u["pid"])
        if u["hex"] is None and entry_gate is None:
            return self._v(False, "unit is not on the map")
        if u["side"] != side:
            return self._v(False, "not your unit")
        if u.get("pushed"):
            return self._v(False, "already moved as part of a Siege Engine stack this MPh [8.3]")
        if u.get("fin"):
            return self._v(False, "this unit's MPh ended when it entered a hex containing a Panicked unit [17.21]")
        if u["state"] == "panicked":
            lag = self._refuge_laggards(side, skip=u["pid"],
                                        states=("routed",))
            if lag:
                return self._v(False, f"Routed units must complete their mandatory move towards Refuge before Panicked units move [4.13/8.1/17.21]: {lag[0]}")
        elif self.s.get("pmoved"):
            return self._v(False, "Panicked units move only after all other units have finished movement - no further non-Panicked moves this MPh [8.1/17.21]")
        if any(e["base"] == u["pid"] for e in self.s["esc"]):
            return self._v(False, "a unit beneath an Escalade may not move - remove it first (4 MF) [8.7]")
        t0 = self._tst_at(u["hex"], broken=False) \
            if u["hex"] is not None else None
        if tst:
            if t0 is None:
                return self._v(False, "unit is not part of a Testudo formation [8.3/8.8]")
            return self._tst_move_verdict(side, u, t0, path)
        forfeit = 0.0
        if t0 is not None:
            if sum(1 for o in self._occupants(u["hex"])
                   if o["pid"] != u["pid"]
                   and self.utype(o)["cls"] == "heavy"
                   and self._fresh(o)) < 2:
                return self._v(False, "leaving would drop the Testudo below two Fresh Heavy Infantry - disband it instead (6 MF) [6.6/16.4/8.8]")
            forfeit = self._ma(u) / 2.0
        e0 = self._esc_at(u["hex"]) if u.get("up") else None
        if e0 and u["pid"] not in e0["used"] and len(e0["used"]) >= 2:
            return self._v(False, "no more than two units may use an Escalade per phase - Fully Occupied [8.7]")
        if up:
            eN = self._esc_at(path[-1]) if path else None
            sN = self._se_at(path[-1]) if path else None
            if eN is not None:
                if u.get("up") and u["hex"] != path[-1]:
                    return self._v(False, "Escalading units may not move laterally from Escalade to Escalade [8.7]")
                if not (self.utype(u)["cls"] in ("heavy", "hq")
                        or u["type"] == "velitae"):
                    return self._v(False, "only Heavy Infantry, Velitae, or a HQ may occupy an Escalade hex [6.5]")
                if not self._fresh(u):
                    return self._v(False, "a Disrupted unit cannot climb an Escalade [16.3]")
                if u["pid"] not in eN["used"] and len(eN["used"]) >= 2:
                    return self._v(False, "no more than two units may use an Escalade per phase - Fully Occupied [8.7]")
                if self.utype(u)["cls"] != "hq" and sum(
                        1 for o in self._occupants(path[-1])
                        if o.get("up") and self.utype(o)["cls"] != "hq") >= 2:
                    return self._v(False, "up to two units (plus a HQ) may be above an Escalade [6.5/8.7]")
            elif sN is None:
                return self._v(False, "no Escalade or Siege Tower in the destination hex [8.7/8.61]")
            elif sN["side"] != side:
                return self._v(False, "Judaeans may not move or climb Siege Engines - they may only wreck them [11.4]")
            else:
                if sN["type"] not in ("tower", "armored_tower"):
                    return self._v(False, "Rams may not carry passengers [6.41]")
                if self.utype(u)["cls"] not in ("heavy", "light", "hq"):
                    return self._v(False, "only one Infantry unit plus a HQ may be atop a Siege Tower [6.42]")
                if self.utype(u)["cls"] != "hq" and any(
                        o["pid"] != u["pid"]
                        for o in self._riders(path[-1])):
                    return self._v(False, "only one Infantry unit plus a HQ may be atop a Siege Tower at once [6.42]")
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
        rd_lock = (self._road_ref_dist(side, zoc)
                   if u["state"] in ("routed", "panicked") else None)
        picked = [str(p) for p in (crew or [])]
        if picked and cls != "siege_engine":
            return self._v(False, "only Siege Engines move with a pushing crew [8.3]")
        if face is not None and cls != "siege_engine":
            return self._v(False, "facing is a Siege Engine attribute [2.45]")
        if cls == "siege_engine":
            if not self._se_crewed(u):
                return self._v(False, "Siege Engine had no Fresh Heavy Infantry or Velitae pushing unit at the start of its MPh - white side up, MA 0 [8.6/2.45]")
            if not picked:
                return self._v(False, "Siege Engine and its pushing units move as one locked stack: name the crew in the move [8.3/8.6]")
            for p in picked:
                x = self.s["units"].get(p)
                if not x or x["side"] != side:
                    return self._v(False, "unknown/enemy pushing unit")
                if x.get("pushed"):
                    return self._v(False, f"{p} already pushed a Siege Engine this MPh [8.3]")
                if p not in (u.get("crew0") or []) or not self._fresh(x) \
                        or x["hex"] != u["hex"] or x.get("up"):
                    return self._v(False, f"{p} is not a Fresh pushing unit that started the MPh beneath the Siege Engine [8.6/10.11]")
            if face is not None and self._dir_of(path[-1], face) is None:
                return self._v(False, "facing must point at a hex adjacent to the Siege Engine [2.45/10.11]")
            if u.get("lk"):
                return self._v(False, "a unit crossed between the Tower and an Elevated Hex - the Tower may move no further nor change facing this MPh [8.61/10.11]")
        out_cc = not self.in_cc(u)
        budget = self._ma(u) - u.get("mv", 0.0) - forfeit
        soft = cls in ("hq", "cavalry")
        spent = 0.0
        prev = path[0]
        started_in_zoc = prev in zoc
        for i, h in enumerate(path[1:], 1):
            if h not in self._nb(prev):
                return self._v(False, f"{self.hex_name.get(h, h)} is not adjacent to {self.hex_name.get(prev, prev)}")
            if rd_lock is not None:
                if rd_lock.get(prev, 0) > 0:
                    if tuple(sorted((prev, h))) not in self.roads \
                            or rd_lock.get(h, 1 << 20) >= rd_lock[prev]:
                        return self._v(False, "on an unobstructed road to Refuge the unit must remain on that road, moving along it, until it reaches Refuge [15.3]")
                elif self._refuge_dist(side, h) >= \
                        self._refuge_dist(side, prev):
                    return self._v(False, "Routed/Panicked units must move towards Refuge - every hex entered must be closer [15.3/17.21]")
            enemy_occ = [o for o in self._occupants(h) if o["side"] == enemy]
            if enemy_occ:
                # 11.4 carve-out of 8.11: a Siege Engine 'not stacked with
                # friendly Combat units ... cannot prevent Judaean units
                # from entering its hex during the MPh'. Any other enemy
                # occupant (combat unit or HQ - conservative reading of
                # 'Combat units') keeps the hex closed. The entered engine
                # is wrecked in _apply [11.4].
                if not (side == "Jud" and all(
                        self.utype(o)["cls"] == "siege_engine"
                        for o in enemy_occ)):
                    return self._v(False, "may not enter an enemy-occupied hex [8.11]")
                if self.hex_t(prev) in ELEVATED:
                    return self._v(False, "Judaeans may enter a Siege Engine hex only from the Ground level [6.4/11.4]")
            if cls in ("siege_engine", "artillery", "cauldron"):
                cat = "siege_engine" if cls == "siege_engine" else "artillery"
                if self._markers_at(h, cat):
                    return self._v(False, "a Wreck/Elim marker blocks similar units from moving into/through that hex [11.4/13.21/14.5]")
            if cls == "siege_engine" and self._occupants(h):
                return self._v(False, "a Siege Engine may not enter a hex occupied by any unit [6.4]")
            sh = self._se_at(h)
            if sh is not None and sh["side"] == side:
                if cls not in ("heavy", "light", "hq"):
                    return self._v(False, "only Infantry may enter or pass through a Siege Engine hex [6.4]")
                if cls != "hq" and sum(
                        1 for o in self._pushers(h)
                        if o["pid"] != u["pid"]) >= 2:
                    return self._v(False, "a Siege Engine hex with two pushing units is filled to capacity [6.4]")
                if i == len(path) - 1 and not up and cls != "hq" \
                        and not (cls == "heavy" or u["type"] == "velitae"):
                    return self._v(False, "up to two Heavy Infantry and/or Velitae (plus a HQ) may be beneath a Siege Engine [6.4]")
            if any(o["side"] == side and o["state"] == "panicked"
                   for o in self._occupants(h)) and i < len(path) - 1:
                return self._v(False, "must stop on entering a hex with a Panicked unit [17.21]")
            eh = self._esc_at(h)
            if eh is not None:
                if side == "Jud":
                    return self._v(False, "Judaeans may never enter an Escalade hex [6.5]")
                if cls in ("artillery", "cauldron"):
                    return self._v(False, "Artillery may not enter an Escalade hex [6.3]")
                if sum(1 for o in self._occupants(h)
                       if self.utype(o)["cls"] != "hq") >= 3:
                    return self._v(False, "the Escalade hex is filled to capacity by units above and below [8.7]")
                if i == len(path) - 1 and not up and cls != "hq":
                    return self._v(False, "only one Fresh Heavy Infantry or Velitae (plus a HQ) may be beneath an Escalade - climb (up) or pass through [8.7]")
            th = self._tst_at(h, broken=False)
            se0 = self._se_at(path[0]) if i == 1 and u.get("up") else None
            if se0 is not None and se0["pid"] != u["pid"] \
                    and self.hex_t(h) in ELEVATED:
                if h != self._facing_hex(se0):
                    return self._v(False, "units atop a Tower move off only through the ramp (arrow) hexside [8.61/10.11]")
                cost, why = 2.0, None
            elif th is not None:
                if i < len(path) - 1:
                    return self._v(False, "units enter a Testudo hex only to join it - the move ends there [6.61]")
                ok_j, why_j = self._tst_join_ok(u, th)
                if not ok_j:
                    return self._v(False, why_j)
                cost, why = 6.0, None
            elif up and i == len(path) - 1 and self._esc_at(h) is not None:
                if self.hex_t(prev) in ELEVATED:
                    cost, why = 2.0, None
                else:
                    cost, why = self._entry_cost(u, prev, h, side)
                    if cost is not None:
                        cost += 4.0
            elif up and i == len(path) - 1:
                sN2 = self._se_at(h)
                sur = 2.0 * sN2.get("tmf", 0.0)
                if self.hex_t(prev) in ELEVATED:
                    if prev != self._facing_hex(sN2):
                        return self._v(False, "units board a Tower from an Elevated hex only via its ramp (arrow) hexside [8.61/10.11]")
                    cost, why = 2.0 + sur, None
                else:
                    cost, why = self._entry_cost(u, prev, h, side)
                    if cost is not None:
                        cost += sur
            else:
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
        movers = [u] + [self.s["units"][p] for p in picked]
        if cls == "siege_engine":
            movers += [o for o in self._occupants(path[0]) if o.get("up")]
        bad = self._stack_check(dest, side, movers)
        pstop = any(o["side"] == side and o["state"] == "panicked"
                    and o["pid"] != u["pid"] for o in self._occupants(dest))
        if bad:
            if not pstop:
                return self._v(False, bad)
            if u["state"] in ("routed", "panicked"):
                return self._v(False, "a mandatory Refuge move never ends in elimination - the unit remains in place instead [17.21/15.1]")
        fd = self._dir_of(dest, face) if face is not None else None
        return dict(self._v(True, f"cost {spent:g} of {budget:g} MF"),
                    crew=picked, face_dir=fd, spent=spent, up=bool(up),
                    forfeit=forfeit, pstop=pstop,
                    panic_elim=bool(bad and pstop))

    def _tst_move_verdict(self, side, u, t, path):
        if side != "Rom":
            return self._v(False, "Testudo is a Roman formation [6.6]")
        if t.get("hold"):
            return self._v(False, "a unit joined the Testudo before it moved - the Testudo may not move this MPh [8.8]")
        if not path or path[0] != t["hex"]:
            return self._v(False, f"path must start at {self.hex_name[t['hex']]}")
        if len(path) < 2:
            return self._v(False, "empty move")
        members = self._occupants(t["hex"])
        budget = 4.0 - t.get("mv", 0.0)
        for m in members:
            if self._fresh(m):
                budget = min(budget, self._ma(m) - m.get("mv", 0.0))
        zoc = self._zoc_map(self._enemy(side))
        spent = 0.0
        prev = path[0]
        started_in_zoc = prev in zoc
        for i, h in enumerate(path[1:], 1):
            if h not in self._nb(prev):
                return self._v(False, f"{self.hex_name.get(h, h)} is not adjacent to {self.hex_name.get(prev, prev)}")
            if h not in self.playable:
                return self._v(False, "off the Gallus battlefield (card scope statement)")
            key = tuple(sorted((prev, h)))
            if self.hex_t(prev) in GATES and key not in self.entrances:
                return self._v(False, "a Testudo leaves a Gate through its Entrance hexsides only [6.61/8.91]")
            t_h = self.hex_t(h)
            occ = self._occupants(h)
            if t_h in GATES:
                if key not in self.entrances:
                    return self._v(False, "a Testudo passes a Gate at ground level through its Entrance hexsides only [6.61/8.91]")
                if self.s["control"].get(h) != side and not (
                        occ and all(o["side"] == side for o in occ)):
                    return self._v(False, "a Testudo may pass only through a Gate occupied or controlled by the Romans [6.61]")
                if any(o["state"] == "panicked" for o in occ):
                    return self._v(False, "must stop on entering a hex with a Panicked unit - and a Testudo may not stop in a Gate [17.21/6.61]")
                if i == len(path) - 1:
                    return self._v(False, "a Testudo may not stop in a Gate hex [6.61]")
                cost = 1.0
            elif t_h in ELEVATED:
                return self._v(False, "a Testudo may not enter an Elevated hex [6.61]")
            elif t_h == "builtup":
                return self._v(False, "a Testudo may not enter a Built-up hex, even on a road [6.61]")
            else:
                if occ:
                    return self._v(False, "a Testudo may not enter a hex occupied by any unit [6.61]")
                if t_h == "breach" and not self._breach_link(h):
                    return self._v(False, "a Testudo enters a Breach only if it is adjacent to a connecting Breach of the same wall [8.96]")
                cost = 0.5 if key in self.roads else INF_COST.get(t_h)
                if cost is None:
                    return self._v(False, "class may not enter that terrain [TEC]")
            if i == 1 and started_in_zoc and h in zoc:
                return self._v(False, "leaving a hard ZOC: the first hex entered must be free of enemy ZOC [7.311]")
            spent += cost
            if spent > budget + 1e-9:
                return self._v(False, f"Testudo movement allowance exceeded: {spent:g} > {budget:g} MF [8.8/6.61]")
            if h in zoc and i < len(path) - 1:
                return self._v(False, "must stop on entering an enemy ZOC [7.31]")
            prev = h
        return dict(self._v(True, f"Testudo moves - cost {spent:g} of {budget:g} MF [8.8]"),
                    spent=spent, tst=True,
                    members=sorted(m["pid"] for m in members))

    # ------------------------------------------------------------ fire [9/13]
    def _lof(self, frm, to):
        """LOF check [9.5/9.51/9.52/9.9/game card]. Returns (ok, drm, why,
        info). Samples the center-to-center pixel line; obstacle classes per
        the LOF Determination Table (a hex bearing a siege Tower unit is
        "Fortress, Tower" group on both axes; closer-to tiebreaks bind B/W
        only). Exact 9.51: Elevated<->Ground fire blocked by Built-up
        adjacent to the ground end. 9.52: ground-level fire across an
        intervening Slope limited to one clear hex between elevations.
        Indirect fire [9.9]: ground-to-ground, or same-height-Elevated, may
        cross ONE combat-unit hex of the same height class for -1; more
        block the LOF. info carries the drm raw material for
        _resolve_missile: towers crossed [9.13], breach hexes crossed,
        indirect flag."""
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

        def has_tower(h):
            # the printed LOF table groups the siege Tower UNIT with Fortress
            # on both axes (its "Tower" - the map key has no tower terrain).
            # Armored Towers are NOT lifted: the card names them separately
            # wherever it means both (9.11/9.13), and its own Missile Table
            # rows Tower with North Wall but Armored Tower with Bastion, so
            # an armored-tower hex classifies by its terrain. A Tower WRECK
            # keeps the lift: 'affect LOF as if the Siege Engine were still
            # there' [11.4].
            return (any(o["type"] == "tower" for o in self._occupants(h))
                    or any(m["type"] == "tower"
                           for m in self._markers_at(h)))

        def grp_of(t):
            return ("FT" if t in ("fortress", "fort") else
                    "B" if t == "bastion" else
                    "WB" if t in ("wall", "north_wall", "gate", "gate_wall",
                                  "gate_north_wall") else "O")
        frm_grp = "FT" if has_tower(frm) else grp_of(t_frm)
        to_grp = "FT" if has_tower(to) else grp_of(t_to)
        MATRIX = {  # firing-from group -> target group -> blocking classes
            "FT": {"FT": "F", "B": "F", "WB": "FB*", "O": "FBW*"},
            "B":  {"FT": "F", "B": "FB", "WB": "FB", "O": "FBW"},
            "WB": {"FT": "FB@", "B": "FB", "WB": "FB", "O": "FBW"},
            "O":  {"FT": "FBW@", "B": "FBW", "WB": "FBW", "O": "FBWPC"},
        }
        spec = MATRIX[frm_grp][to_grp]
        # */@ are the card's closer-to tiebreaks and its key defines them for
        # B and W ONLY ("B*, W*" / "B@, W@") - F and P block unconditionally
        closer_tgt = spec.endswith("*")
        closer_frm = spec.endswith("@")
        classes = spec.rstrip("*@")
        same_grp = frm_grp == to_grp
        frm_elev = t_frm in ELEVATED
        to_elev = t_to in ELEVATED
        occ_cross = towers = breach_cross = slope_cross = clear_cross = 0
        for hk, dfrm, dto in crossed:
            t = self.hex_t(hk)
            bc = blocker_class(t)
            occ = self._occupants(hk)
            if bc and bc in classes:
                if closer_tgt and bc in "BW" and not (dto < dfrm):
                    continue
                if closer_frm and bc in "BW" and not (dfrm < dto):
                    continue
                return (False, 0,
                        f"LOF blocked by {self.hex_name[hk]} [game card LOF table]",
                        None)
            # [9.51] exact: Elevated->Ground fire is ALWAYS blocked by a
            # Built-up hex adjacent to the target it is traced through;
            # Ground->Elevated by one adjacent to the firer (Temple exception
            # 10.3 is outside the Gallus battlefield)
            if t == "builtup" and frm_elev != to_elev:
                low_end = "target" if frm_elev else "firer"
                if (dto if frm_elev else dfrm) == 1:
                    return (False, 0,
                            f"LOF blocked by Built-up {self.hex_name[hk]} "
                            f"adjacent to the {low_end} [9.51]",
                            None)
            # [9.13] -1 per Tower/Armored Tower hex traversed (through-hex);
            # a wrecked one still obstructs 'as if still there' [11.4]
            if any(o["type"] in ("tower", "armored_tower") for o in occ) or \
                    any(m["type"] in ("tower", "armored_tower")
                        for m in self._markers_at(hk)):
                towers += 1
            if t == "breach":
                breach_cross += 1
            if t == "slope":
                slope_cross += 1
            if t == "clear":
                clear_cross += 1
            # [9.9] Combat units (infantry/cavalry - equipment, artillery
            # and HQ do not screen; Towers have 9.13's own -1) obstruct only
            # ground-to-ground and Elevated-to-same-height fire, and only at
            # that same height
            if same_grp and grp_of(t) == frm_grp and \
                    any(self.utype(o)["cls"] in ("heavy", "light", "cavalry")
                        for o in occ):
                occ_cross += 1
        # [9.52] Ground-level fire across elevations: blocked if the LOF
        # passes through an intervening Slope hex and through/into more than
        # one clear hex (exclusive of the firing hex; the target counts).
        # Elevation regions per _build_elevation_regions; endpoints in the
        # same region are at the same elevation and exempt, a slope (or
        # breach) endpoint is an elevation transition and is not.
        if not frm_elev and not to_elev and slope_cross:
            n_clear = clear_cross + (1 if t_to == "clear" else 0)
            same_elev = (self._elev.get(frm) is not None and
                         self._elev.get(frm) == self._elev.get(to))
            if n_clear > 1 and not same_elev:
                return (False, 0,
                        "Ground-level LOF across an intervening Slope may pass "
                        "through/into at most one clear hex [9.52]",
                        None)
        if same_grp and occ_cross > 1:
            return (False, 0,
                    "indirect fire may cross only ONE combat-unit hex [9.9]",
                    None)
        indirect = same_grp and occ_cross == 1
        info = {"indirect": indirect, "towers": towers,
                "breach_cross": breach_cross}
        return True, (-1 if indirect else 0), None, info

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
        defenders = [o for o in self._occupants(tgt) if o["side"] == enemy
                     and self.utype(o)["cls"] != "siege_engine"]
        if not defenders:
            if self._se_at(tgt) is not None:
                return self._v(False, "Fire does not affect Siege Engines [9.1]")
            return self._v(False, "no enemy units in the target hex [9.1]")
        tse = self._se_at(tgt)
        lv = action.get("level")
        if lv not in (None, "above", "below", "both"):
            return self._v(False, "level must be 'above', 'below' or 'both' [9.11]")
        if lv in ("above", "below") and (
                tse is None or tse["type"] not in ("tower", "armored_tower")):
            return self._v(False, "the firer specifies pushing/riding units only vs a Tower hex [9.11]")
        lvl = lv if lv in ("above", "below") else None
        if lvl == "above" and not any(d.get("up") for d in defenders):
            return self._v(False, "no units riding atop the Tower [9.11]")
        if lvl == "below" and all(d.get("up") for d in defenders):
            return self._v(False, "no pushing units beneath the Tower [9.11]")
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
                   for o in self._occupants(f["hex"])) and not f.get("up"):
                return self._v(False, "Missile units may not fire if beneath a Siege Engine - units riding atop a Tower may [9.4/Q&A 11.1]")
            if self._esc_at(f["hex"]) is not None:
                return self._v(False, "Missile units may not fire while occupying an Escalade hex [9.4]")
            ut0 = self.utype(f)
            if tse is not None and tse["type"] in ("tower", "armored_tower") \
                    and lvl != "below" \
                    and (f["type"] == "cauldron"
                         or (ut0.get("rock") is not None
                             and ut0.get("missile") is None)):
                return self._v(False, "Cauldrons and rock-throwing units may not fire vs the riding units on a Tower - specify the pushing units (level 'below') [9.11]")
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
            if adj_enemy and d == 1 and not self.is_night():
                # may not ignore a ZOC-exerter for a non-exerter [9.7]
                exerters = [n for n in adj_enemy
                            if any(f["hex"] in self._unit_zoc(o)
                                   for o in self._occupants(n)
                                   if o["side"] == enemy)]
                if exerters and tgt not in exerters:
                    return self._v(False, "may not ignore an adjacent enemy "
                                          "exerting a ZOC over the firer to "
                                          "attack a non-exerter [9.7]")
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
                lof_ok, _drm, why, _info = self._lof(f["hex"], tgt)
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
                    af=af_total, row=row, cauldrons=cauldrons, lvl=lvl)

    def _wall_bonus(self, frm, tgt):
        """[9.8 + Q&A] Elevated firer, target in a Wall/Bridge hex, LOF
        straight down a path of connected Wall hexes, and NOT over
        intervening units (official Question Box: 'A. Yes. No.'). Gates are
        not Wall hexes for 9.8 - a gate resolves on its printed strongpoint
        ring class on every table (decode-prep 6), so all three gate types
        are excluded (settles the F.19 inconsistency)."""
        if self.hex_t(frm) not in ELEVATED:
            return False
        if self.hex_t(tgt) not in ("wall", "north_wall"):
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
            if self._occupants(hk):
                return False       # not over intervening units [9.8 Q&A]
        return True

    def _target_row(self, tgt, primary_class=None):
        tt = self._tst_at(tgt)
        if tt is not None:
            return ("breach_broken_testudo" if tt.get("broken")
                    else "testudo_artillery_ground")
        occ = self._occupants(tgt)
        se = next((o for o in occ
                   if self.utype(o)["cls"] == "siege_engine"), None)
        if se is not None:
            return {"tower": "builtup_northwall_tower",
                    "armored_tower": "bastion_armored_tower",
                    "ram": "wall_bridge_ram"}[se["type"]]
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
        # -1 Fresh Heavy Infantry in target hex; NA if Testudo (B13), Siege
        # Engine, Foederatti or Syrian Archers in the hex, or Artillery is
        # the Primary Target [13.3 + the card's ** footnote]
        art_primary = row == "testudo_artillery_ground" or \
            action.get("primary_class") in ("catapult", "ballista", "onager")
        if any(self._fresh(d) and self.utype(d)["cls"] == "heavy"
               for d in defenders) and \
           not any(d["type"] in ("foederatti", "syrian_archers")
                   for d in defenders) and \
           not any(self.utype(o)["cls"] == "siege_engine"
                   for o in self._occupants(tgt)) and \
           self._tst_at(tgt) is None and \
           not art_primary:
            drm -= 1
        if any(d["type"] == "judaean_militia" for d in defenders):
            drm += 1
        # the printed drm block, complete [game card / 9.x / B2]. A combined
        # attack rolls one die; per-firer trace penalties apply at the WORST
        # single firer (the convention the old indirect handling set).
        lof_drm = 0
        ground = GROUND | {"builtup"}
        for f in firers:
            u = self.s["units"][f]
            if not self.utype(u).get("missile"):
                continue
            ok, _ld, _w, info = self._lof(u["hex"], tgt)
            if not ok:
                continue
            fd = -info["towers"]              # -1 per Tower hex [9.13]
            if self.hex_t(u["hex"]) == "breach":
                fd -= 1                       # firing from a Breach [card]
            gb = (info["breach_cross"] > 0
                  and self.hex_t(u["hex"]) in ground
                  and self.hex_t(tgt) in ground)
            # * footnote: indirect -1 and ground-through-Breach -1 are not
            # cumulative with each other [9.9/card]
            if info["indirect"] or gb:
                fd -= 1
            lof_drm = min(lof_drm, fd)
        # -1 Judaean Artillery outside Primary Range: UNREACHABLE in Gallus
        # (the only Judaean artillery in the card OOB is Cauldrons - counter
        # census; units-only evidence). Build with the campaign scenarios.
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
        # errant artillery fire [9.31 + Q&A]: natural 1, artillery firing at
        # a higher-elevation target, friendly units adjacent to the target
        # (ground or elevated) outside the firing hexes
        errant = None
        if die == 1:
            fire_hexes = {self.s["units"][f]["hex"] for f in firers}
            art_up = any(self.utype(self.s["units"][f])["cls"] == "artillery"
                         and self.hex_t(self.s["units"][f]["hex"])
                         not in ELEVATED
                         for f in firers) and self.hex_t(tgt) in ELEVATED
            if art_up:
                cands = [o["pid"] for n in self._nb(tgt)
                         for o in self._occupants(n)
                         if o["side"] == side and o["hex"] not in fire_hexes]
                if cands:
                    errant = {"kind": "errant", "hex": tgt, "by": enemy,
                              "cands": cands}
        if result != "-":
            self._queue_losses(tgt, list(result), enemy, source="fire",
                               primary=self._primary_pids(tgt, action, row),
                               lvl=verdict.get("lvl"))
        if errant:
            if self.s["pending"] is None:
                detail["errant"] = self._install_errant(errant)
            else:
                self.s["pending"]["then_errant"] = errant
                detail["errant"] = "pending"
        detail["pending"] = self.s["pending"] is not None
        return detail

    def _primary_pids(self, tgt, action, row):
        occ = self._occupants(tgt)
        if row == "testudo_artillery_ground":
            return [o["pid"] for o in occ
                    if self.utype(o)["cls"] == "artillery"]
        return None

    def _install_errant(self, spec):
        """Errant fire pending [9.31]: the DEFENDER picks which
        attacker-side unit adjacent to the target is disrupted. Auto-applies
        when only one candidate exists."""
        cands = [p for p in spec["cands"]
                 if self.s["units"][p]["hex"] is not None
                 and not (any(e["base"] == p for e in self.s["esc"])
                          and any(o.get("up") for o in self._occupants(
                              self.s["units"][p]["hex"])))]
        if not cands:
            return "no eligible unit"
        if len(cands) == 1:
            return self._apply_errant(cands[0])
        self.s["pending"] = dict(spec, cands=cands)
        return "pending"

    def _apply_errant(self, pid):
        """[9.31] 'must be disrupted': Fresh -> Disrupted. The rule says
        'disrupted', not a ladder step, so a non-Fresh unit takes no
        further effect."""
        u = self.s["units"][pid]
        if self._fresh(u):
            u["state"] = "disrupted"
            return f"{pid} disrupted by errant fire [9.31]"
        return f"{pid} already Disrupted - no further effect [9.31]"

    def _resolve_errant_verdict(self, side, action):
        p = self.s.get("pending")
        if not p or p["kind"] != "errant":
            return self._v(False, "no errant fire to resolve")
        if side != p["by"]:
            return self._v(False, "the defender chooses the errant victim [9.31]")
        pid = str(action.get("pid"))
        if pid not in p["cands"]:
            return self._v(False, f"pick one of {p['cands']} [9.31]")
        return self._v(True, "errant victim chosen")

    # ------------------------------------------------------------ losses
    def _queue_losses(self, tgt, letters, defender, source, primary=None,
                      lvl=None):
        """Create the defender-choice pending, auto-resolving forced cases.
        `primary` = pids the most severe result must fall on [13.2 Q&A]."""
        letters = [c for c in letters if c in ("B", "D", "E")]
        self.s["pending"] = {"kind": "loss", "hex": tgt, "letters": letters,
                             "by": defender, "source": source,
                             "primary": primary, "lvl": lvl}
        self._auto_resolve_pending()

    def _apply_letter(self, u, letter, source):
        """Apply one D/E to a unit [13.21/14.3/14.4]. Returns event str."""
        cls = self.utype(u)["cls"]
        if letter == "E":
            self._eliminate(u)     # 'An E result always eliminates Artillery' [13.21/14.4]
            return "eliminated"
        # D
        if cls in ("artillery",) and source == "fire":
            # artillery ladder [13.21]; equipment shrugs off first hits
            if self._fresh(u):
                return "no effect (Fresh Artillery ignores D from fire) [13.21]"
            u["state"] = DISR_LADDER[min(3, DISR_LADDER.index(u["state"]) + 1)] \
                if u["state"] in DISR_LADDER else u["state"]
            if u["state"] == "panicked":
                self._eliminate(u)
                return "eliminated [13.21]"
            return u["state"]
        if self._fresh(u):
            u["state"] = "disrupted"
            return "disrupted"
        self._eliminate(u)
        return "eliminated (Disrupted absorbed a D) [14.3]"

    def _loss_elig(self, h, by, lvl=None):
        d = [o for o in self._occupants(h) if o["side"] == by
             and self.utype(o)["cls"] != "siege_engine"]
        e = self._esc_at(h)
        if e and lvl == "above":
            return [o for o in d if o.get("up")]
        if e and len(d) > 1:
            d = [o for o in d if o["pid"] != e["base"]]
        elif e is None and self._se_at(h) is not None:
            if lvl == "above":
                return [o for o in d if o.get("up")]
            if lvl == "below":
                return [o for o in d if not o.get("up")]
            if lvl == "ground":
                up = [o for o in d if o.get("up")]
                return up if up else d
        return d

    def _auto_resolve_pending(self):
        p = self.s["pending"]
        if not p or p["kind"] != "loss" or "B" in p["letters"]:
            return
        if len(self._loss_elig(p["hex"], p["by"], p.get("lvl"))) != 1:
            return
        letters = [c for c in p["letters"] if c != "B"]
        if letters.count("D") >= 2:
            letters = ["E"] + [c for c in letters if c == "E"]
            p["auto_note"] = "DD vs a lone eligible target eliminates it [14.33/9.12]"
        events, u, done = [], None, []
        for c in letters:
            el = self._loss_elig(p["hex"], p["by"], p.get("lvl"))
            if not el:
                break
            u = el[0]
            done.append(c)
            events.append(self._apply_letter(u, c, p["source"]))
        self.s["pending"] = None
        p["auto"] = events
        p["xe"] = letters.count("E") - done.count("E")
        if p["source"] == "melee" and "disrupted" in events and u \
                and u["state"] == "disrupted":
            self.s["pending"] = {"kind": "retreat", "hex": p["hex"],
                                 "pids": [u["pid"]], "by": p["by"],
                                 "rkind": "disrupt", "lvl": p.get("lvl"),
                                 "attackers": p.get("attacker_pids") or [],
                                 "mk": p.get("mk"), "xe": p["xe"],
                                 "optional": self._melee_stay_ok(p["hex"])}

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
        e = self._esc_at(p["hex"])
        tse = self._se_at(p["hex"]) if e is None else None
        lvl = p.get("lvl")
        sim = {o["pid"]: o["state"] for o in self._occupants(p["hex"])
               if o["side"] == side
               and self.utype(o)["cls"] != "siege_engine"}

        def elig():
            liv = [q for q in sim if sim[q] != "eliminated"]
            if (e or tse) and lvl == "above":
                return [q for q in liv if self.s["units"][q].get("up")]
            if tse and lvl == "below":
                return [q for q in liv
                        if not self.s["units"][q].get("up")]
            if tse and lvl == "ground":
                up = [q for q in liv if self.s["units"][q].get("up")]
                return up if up else liv
            if e and e["base"] in liv and len(liv) > 1:
                liv = [q for q in liv if q != e["base"]]
            return liv

        if any(str(pk.get("pid")) not in sim for pk in picks):
            return self._v(False, "pick units in the affected hex")
        prev_d = None
        for pk, letter in zip(picks, need):
            pid = str(pk.get("pid"))
            el = elig()
            if not el:
                break
            if pid not in el:
                if e and lvl == "above" \
                        and not self.s["units"][pid].get("up"):
                    return self._v(False, "units beneath an Escalade cannot be attacked in Melee from above [11.61]")
                if e and pid == e["base"]:
                    return self._v(False, "the Base unit is not affected "
                                          "unless it is the only unit left "
                                          "in the hex [9.12]")
                if tse and lvl in ("above", "below"):
                    return self._v(False, "units at the other level of the "
                                          "Tower are immune to this attack "
                                          "[9.11/11.21]")
                if tse and lvl == "ground" \
                        and not self.s["units"][pid].get("up"):
                    return self._v(False, "Romans riding atop are affected "
                                          "by the combat results before the "
                                          "pushing units [11.22]")
                return self._v(False, f"{pid} cannot absorb a further "
                                      "result while another eligible "
                                      "target remains [14.33/14.4]")
            if letter == "D":
                if prev_d == pid and len(el) > 1:
                    return self._v(False, "one unit cannot voluntarily "
                                          "suffer the entire DD while "
                                          "another eligible target "
                                          "remains [14.33]")
                prev_d = pid
            cls = self.utype(self.s["units"][pid])["cls"]
            if letter == "E":
                sim[pid] = "eliminated"
            elif cls == "artillery" and p["source"] == "fire":
                if sim[pid] != "fresh":
                    j = DISR_LADDER.index(sim[pid]) \
                        if sim[pid] in DISR_LADDER else 3
                    sim[pid] = "eliminated" if j >= 2 else DISR_LADDER[j + 1]
            elif sim[pid] == "fresh":
                sim[pid] = "disrupted"
            else:
                sim[pid] = "eliminated"
        # the most severe result must fall on the Primary Target [13.2 Q&A]
        prim = [pid for pid in (p.get("primary") or [])
                if self.s["units"].get(pid, {}).get("hex") == p["hex"]]
        if prim and need:
            sev = min(need, key=lambda c: {"E": 0, "D": 1}.get(c, 2))
            if not any(need[i] == sev and str(pk.get("pid")) in prim
                       for i, pk in enumerate(picks)):
                return self._v(False, "the most severe result must be taken "
                                      "against the Primary Target [13.2 Q&A]")
        sub = action.get("substitute_d")
        if sub is not None:
            if "B" not in p["letters"] or p["source"] != "melee":
                return self._v(False, "no B result to substitute [14.2]")
            u = self.s["units"].get(str(sub))
            if not u or u["hex"] != p["hex"] or u["side"] != side:
                return self._v(False, "the substituted D must fall on a "
                                      "single unit in the affected hex [14.2]")
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
            if self._facing_hex(u) != tgt:
                return self._v(False, "Rams/Armored Towers may attack only the Elevated hex indicated by their Facing arrow [10.11]")
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
                self._eliminate(o)
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
        if key in self.crests and self.hex_t(tgt) != "slope":
            # [11.17] attacker halved across a Crest hexside vs a defender
            # at Ground level on a non-Slope hex (crest sides are slope|clear,
            # so the attacker is on the slope side and the defender's clear
            # hex is the higher ground)
            mult *= 0.5
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
        esc = self._esc_at(tgt)
        tt = self._tst_at(tgt, broken=False)
        atk_units = []
        for pid in action.get("attackers", []):
            u = self.s["units"].get(str(pid))
            if not u or u["side"] != side:
                return self._v(False, "unknown/enemy attacker")
            if not self._fresh(u):
                return self._v(False, f"{u['pid']} is not Fresh [11.1/16.2]")
            if self.utype(u)["cls"] in ("artillery", "siege_engine"):
                return self._v(False, "Artillery/Siege Engines may not melee [2.46/11.x]")
            if u["type"] == "cauldron":
                return self._v(False, "Cauldrons melee only defensively in this scenario scope")
            if self._tst_at(u["hex"], broken=False) is not None:
                return self._v(False, "units in a Testudo may not Melee attack [11.5]")
            if tt is not None and self.hex_t(u["hex"]) not in \
                    (GROUND | GATES | {"builtup"}):
                return self._v(False, "Judaean Combat units occupying Ground, Gate and Built-up hexes may Melee adjacent Testudos [11.5]")
            if any(o["state"] == "panicked" and o["side"] == side
                   for o in self._occupants(u["hex"])):
                return self._v(False, "no attacks from a hex containing a Panicked unit [17.22]")
            if self._dist(u["hex"], tgt) != 1:
                return self._v(False, "melee attacks adjacent hexes [11.1]")
            if self._esc_at(u["hex"]) is not None:
                if any(e["base"] == u["pid"] for e in self.s["esc"]):
                    return self._v(False, "Base units may not attack [11.6]")
                if not u.get("up"):
                    return self._v(False, "only units atop the Escalade may Melee [11.6/11.61]")
                if self.hex_t(tgt) not in ELEVATED:
                    return self._v(False, "Escalading units may Melee only adjacent units in Elevated Hexes [11.6]")
            sa = self._se_at(u["hex"])
            if sa is not None:
                if not u.get("up"):
                    return self._v(False, "Romans in a Tower or Ram hex may not Melee, whether atop or beneath [11.2/11.3]")
                if tgt != self._facing_hex(sa):
                    return self._v(False, "units mounted in a Tower may Melee only through the hexside indicated by the Facing arrow [10.11/11.2]")
                if self.hex_t(tgt) not in ELEVATED:
                    return self._v(False, "Romans in a Tower hex may not Melee Ground or Built-up hexes [11.2]")
            atk_units.append(u)
        if not atk_units:
            return self._v(False, "no attackers")
        tse = self._se_at(tgt) if esc is None else None
        dcombat = [d for d in defenders
                   if self.utype(d)["cls"] != "siege_engine"]
        lvl = None
        wreck = False
        if esc is not None:
            lvs = {"above" if self.hex_t(u["hex"]) in ELEVATED
                   and self.hex_t(u["hex"]) not in GATES else "ground"
                   for u in atk_units}
            if len(lvs) > 1:
                return self._v(False, "an Escalade hex may not be attacked from both an Elevated and Ground hex in a combined attack - each attack is a separate battle [11.6]")
            lvl = lvs.pop()
            if lvl == "above" and not any(d.get("up") for d in defenders):
                return self._v(False, "Roman units beneath an Escalade cannot be attacked in Melee from above [11.61]")
        elif tse is not None:
            lvs = {"above" if self.hex_t(u["hex"]) in ELEVATED
                   and self.hex_t(u["hex"]) not in GATES else "ground"
                   for u in atk_units}
            if len(lvs) > 1:
                return self._v(False, "a Tower may not be attacked from both an Elevated and a Ground hex in a combined attack - each attack is resolved separately [11.2]")
            lvl = lvs.pop()
            if lvl == "above":
                fh = self._facing_hex(tse)
                if any(u["hex"] != fh for u in atk_units):
                    return self._v(False, "units riding atop a Tower (or a vacant Tower) are attacked from an Elevated hex only through that Tower's ramp hexside [11.21]")
                if not dcombat:
                    wreck = True
                elif not any(d.get("up") for d in dcombat):
                    return self._v(False, "units beneath the Tower cannot be affected by this attack [11.21/11.3]")
            elif not dcombat:
                return self._v(False, "a Siege Engine has no Melee Strength - wreck an unescorted engine by entering its hex in the MPh [11.4/11.22]")
        marked = any(u.get("mk") for u in atk_units)
        cc = self.s.get("cc_hex")
        cc_same = (isinstance(cc, dict) and tgt == cc["hex"]
                   and {u["pid"] for u in atk_units} == set(cc["pids"]))
        if (isinstance(cc, dict) and tgt == cc["hex"]
                and not cc_same and not marked):
            return self._v(False, "Continuous Combat re-attacks the same hex with the same units [11.87]")
        for u in atk_units:
            if u["pid"] in self.s["meleed"] and not (cc_same or marked):
                return self._v(False, f"{u['pid']} already attacked this Melee Phase [11.1/11.87/11.9]")
        mh = self.s["melee_hexes"]
        split = esc is not None or tse is not None
        hit = (tgt in mh or [tgt, lvl] in mh) if split else \
            any(x == tgt or (isinstance(x, list) and x[0] == tgt)
                for x in mh)
        if hit and not (cc_same or marked):
            return self._v(False, "hex already attacked this Melee Phase"
                           + (" from that level [11.2/11.6]" if split
                              else "")
                           + " - needs Continuous Combat or a Multiple Attack marker [11.81]")
        if not self.is_night():
            for u in atk_units:
                if u.get("mk"):
                    zhexes = {h for h in self._unit_zoc(u)
                              if any(o["side"] == enemy
                                     for o in self._occupants(h))}
                    if zhexes and tgt not in zhexes:
                        return self._v(False, f"{u['pid']} advanced after combat and must Melee a unit in its ZOC [11.9]")
        att = 0.0
        factions = set()
        for u in atk_units:
            if (esc is not None or tse is not None) and lvl == "above":
                mult = 1.0
            elif self._se_at(u["hex"]) is not None and u.get("up"):
                mult = 2.0
            else:
                mult, why = self._melee_approach(u, tgt)
                if mult is None:
                    return self._v(False, f"no legal approach: {why} [11.1]")
            if u.get("up") and self._esc_at(u["hex"]) is not None:
                mult *= 0.5
            att += self._melee_val(u) * mult
            factions.add(u.get("faction"))
        return dict(self._v(True, "melee set"),
                    att=att, factions=len(factions - {None}) or 1, lvl=lvl,
                    wreck=wreck)

    def _resolve_melee(self, side, action, verdict):
        tgt = self.name_hex.get(action["target"], action["target"])
        enemy = self._enemy(side)
        atk_units = [self.s["units"][str(p)] for p in action["attackers"]]
        if verdict.get("wreck"):
            tse0 = self._se_at(tgt)
            self._eliminate(tse0)
            for a in atk_units:
                self.s["meleed"].append(a["pid"])
            self.s["melee_hexes"].append([tgt, "above"])
            return {"wrecked": tse0["pid"], "lvl": "above",
                    "note": "unescorted Siege Engine attacked in Melee "
                            "through its Ramp hexside from an Elevated Hex "
                            "is eliminated - Wreck placed [11.4/11.21]"}
        defenders = [o for o in self._occupants(tgt) if o["side"] == enemy
                     and self.utype(o)["cls"] != "siege_engine"]
        att = verdict["att"]
        t = self.hex_t(tgt)
        esc = self._esc_at(tgt)
        tse = self._se_at(tgt) if esc is None else None
        lvl = verdict.get("lvl")
        if esc is not None and lvl == "above":
            dunits = [d for d in defenders if d.get("up")]
            deff = sum(self._melee_val(d) for d in dunits) * 0.5
        elif esc is not None:
            dunits = [d for d in defenders if d["pid"] == esc["base"]]
            deff = sum(self._melee_val(d) for d in dunits) * 0.5
        elif tse is not None and lvl == "above":
            dunits = [d for d in defenders if d.get("up")]
            deff = sum(self._melee_val(d) for d in dunits)
        elif tse is not None:
            push = [d for d in defenders if not d.get("up")]
            if push:
                dunits = push
                deff = sum(self._melee_val(d) for d in push)
            else:
                dunits = [d for d in defenders if d.get("up")]
                deff = sum(self._melee_val(d) for d in dunits) * 0.5
        else:
            dunits = defenders
            dmult = 3.0 if t == "fortress" else (2.0 if t in ELEVATED else 1.0)
            deff = sum(self._melee_val(d) for d in dunits) * dmult
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
               for d in dunits):
            drm -= 1
        if any(self.utype(a).get("hq") == "commander" for a in atk_units):
            drm += 1
        if any(self.utype(d).get("hq") == "commander" for d in dunits):
            drm -= 1
        drm += self._cohort_drm(atk_units, +1) + self._cohort_drm(dunits, -1)
        if side == "Jud" and self.is_night():
            drm += 1                          # [18.25]
        if any(d["state"] == "routed" for d in dunits):
            drm += 1                          # [17.23]
        if any(o["state"] == "panicked" and o["side"] == enemy
               for h2 in [tgt] + self._nb(tgt) for o in self._occupants(h2)):
            drm += 2                          # [17.23]
        dfacs = {d.get("faction") for d in dunits} - {None}
        if len(dfacs) > 1:
            drm += 2 * (len(dfacs) - 1)       # [11.842]
        afacs = verdict["factions"]
        if afacs > 1:
            drm -= (afacs - 1)                # [11.842]
        die = self.roll_die()
        adj = die + drm
        key = str(max(-1, min(8, adj)))
        result = self.melee_t["rows"][key][cols.index(col)]
        mks = [a["mk"] for a in atk_units if a.get("mk")]
        stage = max(mks, key="ABC".index) if mks else None
        if stage is None:
            for x in self.s["units"].values():
                x.pop("mk", None)
        else:
            if stage == "B":
                for x in self.s["units"].values():
                    if x.get("mk") == "A":
                        x.pop("mk")
            for a in atk_units:
                a.pop("mk", None)
        nxt = {"A": "B", "B": "C", "C": "A"}.get(stage, "A")
        for a in atk_units:
            self.s["meleed"].append(a["pid"])
        self.s["melee_hexes"].append(
            [tgt, lvl] if (esc is not None or tse is not None) else tgt)
        detail = {"att": att, "def": deff, "col": col, "die": die,
                  "drm": drm, "result": result, "mk_stage": stage}
        if lvl:
            detail["lvl"] = lvl
        # continuous combat [11.87]: die >= 6 before or after drm
        self.s["cc_hex"] = ({"hex": tgt,
                             "pids": sorted(a["pid"] for a in atk_units)}
                            if (die >= 6 or adj >= 6) else None)
        if result == "-":
            return detail
        letters = list(result)
        self._queue_melee_result(tgt, letters, enemy, side,
                                 [a["pid"] for a in atk_units], nxt, lvl)
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

    def _queue_melee_result(self, tgt, letters, defender, attacker,
                            attacker_pids=None, mk=None, lvl=None):
        p = {"kind": "loss", "hex": tgt, "letters": letters,
             "by": defender, "source": "melee",
             "attacker": attacker,
             "attacker_pids": attacker_pids or [], "mk": mk,
             "lvl": lvl}
        self.s["pending"] = p
        self._auto_resolve_pending()
        xe = p.get("xe", 0)
        if self.s["pending"] is None:
            # auto-resolved: any survivor with B retreats via its own pending
            if "B" in letters:
                self._queue_retreat(tgt, defender, attacker_pids, mk, lvl, xe)
            if self.s["pending"] is None and lvl == "above":
                self._tower_fall(tgt)
            if self.s["pending"] is None and mk and lvl != "above":
                self._open_adv(tgt, attacker, attacker_pids, mk, xe)

    def _queue_retreat(self, tgt, defender, attacker_pids=None, mk=None,
                       lvl=None, xe=0):
        movers = [o["pid"] for o in self._occupants(tgt)
                  if o["side"] == defender
                  and self.utype(o)["cls"] != "siege_engine"
                  and (lvl != "above" or o.get("up"))]
        if movers:
            self.s["pending"] = {"kind": "retreat", "hex": tgt,
                                 "pids": movers, "by": defender,
                                 "rkind": "b", "lvl": lvl,
                                 "attackers": attacker_pids or [], "mk": mk,
                                 "xe": xe}

    def _open_adv(self, h, side, apids, mk, xe=0):
        if any(o["side"] == self._enemy(side) for o in self._occupants(h)):
            return
        pids = [str(p) for p in (apids or [])
                if self.s["units"].get(str(p), {}).get("hex") is not None]
        if pids:
            self.s["pending"] = {"kind": "advance", "hex": h, "by": side,
                                 "pids": pids, "mk": mk, "xe": xe}

    def _resolve_esc_up_verdict(self, side, action):
        p = self.s.get("pending")
        if not p or p["kind"] != "esc_up":
            return self._v(False, "no Escalade move-up to resolve")
        if side != p["by"]:
            return self._v(False, "the Roman player moves escalading units up at the end of his Melee Phase [11.6]")
        moves = action.get("moves") or {}
        by_dest = {}
        for pid, hn in moves.items():
            pid = str(pid)
            if pid not in p["opts"]:
                return self._v(False, f"{pid} is not an escalading unit or Tower rider adjacent to a vacant Elevated hex [11.6/11.2]")
            if hn not in p["opts"][pid]:
                return self._v(False, f"{pid} may move only onto an adjacent vacant Elevated hex: {p['opts'][pid]} [11.6/11.2]")
            by_dest.setdefault(self.name_hex[hn], []).append(
                self.s["units"][pid])
        for h, movers in by_dest.items():
            bad = self._stack_check(h, "Rom", movers)
            if bad:
                return self._v(False, f"move up within the stacking limit [11.6/6.0]: {bad}")
        return self._v(True, ("escalade move-up set" if moves
                              else "escalade move-up declined") + " [11.6]")

    def _adv_step(self, u, frm, to, side, zoc, last):
        if to not in self._nb(frm):
            return f"{self.hex_name.get(to, to)} is not adjacent to {self.hex_name.get(frm, frm)}"
        enemy = self._enemy(side)
        if any(o["side"] == enemy for o in self._occupants(to)):
            return "may not advance into an enemy-occupied hex [8.11/11.86]"
        c, why = self._entry_cost(u, frm, to, side)
        if c is None:
            return f"{why} [11.86]"
        cls = self.utype(u)["cls"]
        if cls in ("siege_engine", "artillery", "cauldron") and \
                self._markers_at(to, "siege_engine" if cls == "siege_engine"
                                 else "artillery"):
            return "a Wreck/Elim marker blocks similar units from moving into/through that hex [11.4/13.21/14.5]"
        if to in zoc and u["state"] != "fresh" \
                and not (side == "Jud" and self.is_night()):
            return "Disrupted units may not enter an enemy ZOC [16.51]"
        if not last and any(o["side"] == side and o["state"] == "panicked"
                            for o in self._occupants(to)):
            return "must stop on entering a hex with a Panicked unit [17.21]"
        if self._tst_at(to, broken=False) is not None:
            return "may not advance into a Testudo hex - joining is a Movement Phase action [6.61/8.8]"
        if self._esc_at(to) is not None:
            if cls in ("artillery", "cauldron"):
                return "Artillery may not enter an Escalade hex [6.3]"
            if sum(1 for o in self._occupants(to)
                   if self.utype(o)["cls"] != "hq") >= 3:
                return "the Escalade hex is filled to capacity by units above and below [8.7]"
            if last and cls != "hq":
                return "only one Fresh Heavy Infantry or Velitae (plus a HQ) may be beneath an Escalade - the advance may not end there [8.7]"
        se = self._se_at(to)
        if se is not None and se["side"] == side:
            if cls not in ("heavy", "light", "hq"):
                return "only Infantry may enter or pass through a Siege Engine hex [6.4]"
            if cls != "hq" and sum(
                    1 for o in self._pushers(to)
                    if o["pid"] != u["pid"]) >= 2:
                return "a Siege Engine hex with two pushing units is filled to capacity [6.4]"
            if last and cls != "hq" \
                    and not (cls == "heavy" or u["type"] == "velitae"):
                return "up to two Heavy Infantry and/or Velitae (plus a HQ) may be beneath a Siege Engine [6.4]"
        return None

    def _resolve_advance_verdict(self, side, action):
        p = self.s.get("pending")
        if not p or p["kind"] != "advance":
            return self._v(False, "no advance to resolve")
        if side != p["by"]:
            return self._v(False, "the victorious attacker chooses the advance [11.9]")
        pids = [str(x) for x in (action.get("pids") or [])]
        if len(set(pids)) != len(pids):
            return self._v(False, "duplicate advancing unit")
        beyond = {str(k): [str(n) for n in (v or [])]
                  for k, v in (action.get("beyond") or {}).items()}
        xe = p.get("xe") or 0
        units = []
        for pid in pids:
            if pid not in p["pids"]:
                return self._v(False, f"{pid} did not attack the vacated hex [11.9]")
            u = self.s["units"][pid]
            c, why = self._entry_cost(u, u["hex"], p["hex"], side)
            if c is None:
                return self._v(False, f"illegal advance terrain: {why} [11.9/11.86]")
            units.append(u)
        if units:
            bad = self._stack_check(p["hex"], side, units, skip=set(pids))
            if bad:
                return self._v(False, f"advance up to the stacking limit [11.9]: {bad}")
        if beyond and not xe:
            return self._v(False, "no bonus advance: the number of 'E' results did not exceed the number of defending units [11.86]")
        ends = {}
        zoc = self._zoc_map(self._enemy(side))
        for pid, names in beyond.items():
            if pid not in pids:
                return self._v(False, f"{pid} is not advancing into the vacated hex [11.86]")
            if not 1 <= len(names) <= xe:
                return self._v(False, f"the excess-'E' bonus allows at most {xe} hex(es) beyond the vacated hex [11.86]")
            u = self.s["units"][pid]
            if not self.in_cc(u):
                return self._v(False, "lack of Command Control prevents any advance beyond the vacated hex [11.9/5.3]")
            prev = p["hex"]
            path = [self.name_hex.get(n, n) for n in names]
            for i, h in enumerate(path):
                if prev in zoc:
                    return self._v(False, "enemy ZOC prevents any advance beyond that hex [11.9/7.311]")
                why = self._adv_step(u, prev, h, side, zoc,
                                     i == len(path) - 1)
                if why:
                    return self._v(False, why)
                prev = h
            ends.setdefault(prev, []).append(u)
        for h, us in ends.items():
            if h == p["hex"]:
                continue
            bad = self._stack_check(h, side, us, skip=set(pids))
            if bad:
                return self._v(False, f"the bonus advance must respect stacking [11.86/6.0]: {bad}")
        return self._v(True, ("advance set" if pids else "advance declined")
                       + " [11.9]")

    def _apply_advance(self, action):
        p = self.s["pending"]
        pids = [str(x) for x in (action.get("pids") or [])]
        beyond = {str(k): [str(n) for n in (v or [])]
                  for k, v in (action.get("beyond") or {}).items()}
        for pid in pids:
            u = self.s["units"][pid]
            u["hex"] = p["hex"]
            u["mk"] = p["mk"]
            self.s["control"][p["hex"]] = p["by"]
            for hn in beyond.get(pid, []):
                h = self.name_hex.get(hn, hn)
                u["hex"] = h
                self.s["control"][h] = p["by"]
        self.s["pending"] = None
        out = {"advanced": pids, "mk": p["mk"] if pids else None,
               "hex": self.hex_name[p["hex"]]}
        if beyond:
            out["beyond"] = {pid: v for pid, v in beyond.items() if v}
        return out

    # ------------------------------------------------ retreats [14.2/15.x]
    # The 15.1/15.3 retreat is a constrained search, not a step count: an MF
    # budget (melee-Disrupt retreats only), a mandatory preference for routes
    # that avoid Rout/Panic/elimination, per-hex movement towards Refuge
    # whenever possible, three absolute prohibitions, forced continuation
    # while fully stacked, and elimination as the failure case (never a
    # deadlock). The printed 15.3 EXAMPLE (rulebook p.12) is reproduced by
    # validate_combat's retreat_engine_checks.
    _FREE_CLS = {"artillery", "cauldron", "hq", "siege_engine"}

    def _retreat_occ(self, h, overlay, skip=None):
        """Occupants of h with this action's earlier retreats applied
        (overlay: pid -> virtual hex, None = eliminated), excluding the
        moving unit itself."""
        out = []
        for u in self.s["units"].values():
            if u["pid"] == skip:
                continue
            if u["pid"] in overlay:
                if overlay[u["pid"]] == h:
                    out.append(u)
            elif u["hex"] == h:
                out.append(u)
        return out

    def _retreat_full(self, u, h, side, overlay):
        """Is h fully stacked to retreating unit u [8.13/15.3]? Entering
        such a hex costs one disorganization level; a retreat may not END
        in one. Free-stack classes use the one-each caps [6.3/6.4] as their
        'full to them' test (8.13's carve-out, mirrored)."""
        occ = self._retreat_occ(h, overlay, skip=u["pid"])
        cls = self.utype(u)["cls"]
        if cls in self._FREE_CLS:
            grp = ({"artillery", "cauldron"} if cls in ("artillery",
                                                        "cauldron")
                   else {cls})
            cap = (2 if cls in ("artillery", "cauldron")
                   and self.hex_t(h) == "fortress" else 1)
            n = sum(1 for o in occ if self.utype(o)["cls"] in grp)
            # markers hold their slot during retreats too, as 'full to
            # them' [14.5 'as if they were not eliminated'] - the 15.3
            # overstack ladder governs retreats, not the MPh into/through
            # prohibition, so a marker hex costs a level and may not be
            # the retreat's end, exactly like a live one-each occupant
            n += sum(1 for m in self.s["markers"]
                     if m["hex"] == h and m["cls"] in grp)
            return n >= cap
        return self._combat_count(occ) >= self._stack_limit(h, side)

    def _retreat_step(self, u, frm, to, side, zoc, overlay):
        """One retreat step: the three 15.1 prohibitions + 7.5 + 8.11 +
        15.2's Infantry/Cavalry interlock. Returns (cost, why).
        (15.2's SE-with-two-pushers and Testudo-join gates land with
        B13/B14 - no such states exist yet.)"""
        if to not in self._nb(frm):
            return None, "retreat path not adjacent"
        if to in zoc:
            return None, "may not retreat into an enemy ZOC [7.5/15.1]"
        occ = self._retreat_occ(to, overlay, skip=u["pid"])
        enemy = self._enemy(side)
        if any(o["side"] == enemy for o in occ):
            return None, "may not retreat into an enemy-occupied hex [8.11/15.1]"
        if any(o["side"] == side and o["state"] == "panicked" for o in occ):
            return None, "may not retreat into a hex with a Panicked unit [15.1]"
        cls = self.utype(u)["cls"]
        e = self._esc_at(to)
        if e is not None:
            if side == "Jud":
                return None, "Judaeans may never enter an Escalade hex [6.5]"
            if cls in ("artillery", "cauldron"):
                return None, "Artillery may not enter an Escalade hex [6.3]"
        tt = self._tst_at(to, broken=False)
        if tt is not None:
            ok_j, why_j = self._tst_join_ok(u, tt)
            if not ok_j:
                return None, why_j + " [15.2]"
            return 6.0, None
        if cls in ("heavy", "light") and \
                any(self.utype(o)["cls"] == "cavalry" for o in occ):
            return None, "Infantry may not retreat into a Cavalry hex [15.2]"
        if cls in ("heavy", "light") and \
                any(self.utype(o)["cls"] == "siege_engine" for o in occ) and \
                sum(1 for o in occ if not o.get("up") and
                    self.utype(o)["cls"] not in ("hq", "siege_engine")) >= 2:
            return None, "Infantry may not retreat into or through a Siege Engine hex with two pushing units [15.2]"
        if cls == "cavalry" and \
                any(self.utype(o)["cls"] in ("heavy", "light") for o in occ):
            return None, "Cavalry may not retreat into an Infantry hex [15.2]"
        c, why = self._entry_cost(u, frm, to, side)
        if c is None:
            return None, f"illegal retreat terrain: {why} [15.1]"
        return c, None

    def _retreat_capped(self, u, p):
        """14.21: a Judaean unit in the Ground-level ZOC of an attacking
        Roman Heavy Infantry retreats exactly one hex; a forced overstack
        eliminates it."""
        if u["side"] != "Jud" or self.is_night() or \
                self.hex_t(u["hex"]) not in GROUND:
            return False
        for apid in p.get("attackers", []):
            a = self.s["units"].get(str(apid))
            if (a and a["hex"] is not None and a["side"] == "Rom"
                    and self._fresh(a)
                    and self.utype(a)["cls"] == "heavy"
                    and self.hex_t(a["hex"]) in (GROUND | {"builtup"})
                    and u["hex"] in self._nb(a["hex"])):
                return True
        return False

    def _retreat_can_finish(self, u, side, ctx, pos, mf_left, levels, steps,
                            clean, overlay, memo):
        """Feasibility: can this retreat still end alive in a non-full hex?
        rkind 'b' [14.2]: 1-2 hexes at the defender's option regardless of
        MF, then forced continuation only while fully stacked. rkind
        'disrupt' [15.1]: any length within the Disrupted-MA MF budget.
        `clean` = no further fully-stacked entries allowed (the mandatory
        avoid-Rout/Panic/elimination preference); `levels` = disorganization
        levels the unit can still absorb before dying."""
        full_here = steps >= 1 and self._retreat_full(u, pos, side, overlay)
        if steps >= 1 and not full_here:
            return True
        if ctx["rkind"] == "b" and steps >= 2 and not full_here:
            return False                       # window spent, not forced
        key = (pos, None if mf_left is None else round(mf_left * 2),
               levels, min(steps, 2), clean)
        if key in memo:
            return memo[key]
        memo[key] = False                      # revisits cannot help
        for n in self._nb(pos):
            c, _ = self._retreat_step(u, pos, n, side, ctx["zoc"], overlay)
            if c is None:
                continue
            if mf_left is not None and c > mf_left + 1e-9:
                continue
            lv = levels
            if self._retreat_full(u, n, side, overlay):
                if clean or lv <= 0:
                    continue
                lv -= 1
            if self._retreat_can_finish(
                    u, side, ctx, n,
                    None if mf_left is None else mf_left - c,
                    lv, steps + 1, clean, overlay, memo):
                memo[key] = True
                return True
        return False

    def _retreat_levels(self, u):
        i = DISR_LADDER.index(u["state"]) if u["state"] in DISR_LADDER else 3
        return 3 - i

    def _retreat_survivable(self, u, side, ctx, p, overlay):
        """Does ANY legal retreat end alive? False => the unit is eliminated
        [15.1/14.21/7.5] - the gate never deadlocks (B17)."""
        if self._retreat_capped(u, p):
            for n in self._nb(u["hex"]):
                c, _ = self._retreat_step(u, u["hex"], n, side, ctx["zoc"],
                                          overlay)
                if c is not None and \
                        not self._retreat_full(u, n, side, overlay):
                    return True
            return False
        mf = self._ma(u) if ctx["rkind"] == "disrupt" else None
        return self._retreat_can_finish(u, side, ctx, u["hex"], mf,
                                        self._retreat_levels(u), 0, False,
                                        overlay, {})

    def _retreat_path_verdict(self, u, side, ctx, p, names, overlay):
        """Validate one unit's submitted retreat path. Returns a refusal
        string or None."""
        path = [self.name_hex.get(n, n) for n in names]
        if not path or path[0] != u["hex"]:
            return "retreat path must start at the unit's hex"
        if len(path) < 2:
            return "must retreat at least one hex [14.2/15.1]"
        if self._retreat_capped(u, p):
            if len(path) != 2:
                return ("in the attacking Roman Heavy Infantry's ground "
                        "ZOC: retreat exactly one hex [14.21]")
            c, why = self._retreat_step(u, path[0], path[1], side,
                                        ctx["zoc"], overlay)
            if c is None:
                return why
            if self._retreat_full(u, path[1], side, overlay):
                return ("a forced overstack under 14.21 eliminates the "
                        "unit - declare it in `eliminate` instead")
            return None
        rk = ctx["rkind"]
        mf = self._ma(u) if rk == "disrupt" else None
        levels = self._retreat_levels(u)
        pos = path[0]
        for i, n in enumerate(path[1:]):
            steps = i                          # steps already taken
            full_pos = steps >= 1 and self._retreat_full(u, pos, side,
                                                         overlay)
            forced = full_pos
            if rk == "b" and steps >= 2 and not forced:
                return ("14.2 retreats extend beyond two hexes only while "
                        "fully stacked [14.2/15.3]")
            c, why = self._retreat_step(u, pos, n, side, ctx["zoc"], overlay)
            if c is None:
                return why
            if self._tst_at(n, broken=False) is not None and n != path[-1]:
                return "joining a Testudo ends the retreat [15.2/6.61]"
            if mf is not None:
                if c > mf + 1e-9:
                    return ("may not expend more MF than the Disrupted "
                            "movement allowance [15.1]")
                mf -= c
            constrained = rk == "disrupt" or forced
            clean_possible = constrained and self._retreat_can_finish(
                u, side, ctx, pos, None if mf is None else mf + c, levels,
                steps, True, overlay, {})
            n_full = self._retreat_full(u, n, side, overlay)
            if n_full:
                if clean_possible:
                    return ("must avoid the Rout/Panic/elimination hex - a "
                            "safe route exists [15.1/15.3]")
                if levels <= 0:
                    return ("this route eliminates the unit; declare it in "
                            "`eliminate` if no survivable retreat exists")
                levels -= 1
            if constrained:
                # each hex towards Refuge whenever possible [15.1/15.3]
                d0 = self._refuge_dist(side, pos)
                if self._refuge_dist(side, n) >= d0:
                    for m in self._nb(pos):
                        if self._refuge_dist(side, m) >= d0:
                            continue
                        cm, _ = self._retreat_step(u, pos, m, side,
                                                   ctx["zoc"], overlay)
                        if cm is None or (mf is not None
                                          and cm > mf + c + 1e-9):
                            continue
                        lvm = levels + (1 if n_full else 0)
                        if self._retreat_full(u, m, side, overlay):
                            if clean_possible or lvm <= 0:
                                continue
                            lvm -= 1
                        if self._retreat_can_finish(
                                u, side, ctx, m,
                                None if mf is None else mf + c - cm,
                                lvm, steps + 1, clean_possible, overlay,
                                {}):
                            return ("each hex of a retreat must be towards "
                                    "Refuge whenever possible [15.1/15.3]")
            pos = n
        if self._retreat_full(u, pos, side, overlay):
            return ("a retreat may not end fully stacked - continue it or "
                    "declare the unit in `eliminate` [15.1/15.3]")
        return None

    def _resolve_retreat_verdict(self, side, action):
        p = self.s.get("pending")
        if not p or p["kind"] != "retreat":
            return self._v(False, "no retreat to resolve")
        if side != p["by"]:
            return self._v(False, "the owning player routes retreats [15.1]")
        paths = action.get("paths", {}) or {}
        elim = [str(x) for x in action.get("eliminate", [])]
        named = set(paths) | set(elim)
        if p.get("optional"):
            if elim:
                return self._v(False, "the unit may remain in place instead [14.31] - no forced elimination")
            if not named <= set(p["pids"]):
                return self._v(False, f"only these units may retreat: {p['pids']} [14.31]")
        elif named != set(p["pids"]) or set(paths) & set(elim):
            return self._v(False, "route or eliminate each of: "
                                  f"{p['pids']} exactly once")
        ctx = {"rkind": p.get("rkind", "b"),
               "zoc": self._zoc_map(self._enemy(side))}
        overlay = {}
        for pid, names in paths.items():
            u = self.s["units"][pid]
            why = self._retreat_path_verdict(u, side, ctx, p, names, overlay)
            if why:
                return self._v(False, why)
            overlay[pid] = self.name_hex.get(names[-1], names[-1])
        for pid in elim:
            if self._retreat_survivable(self.s["units"][pid], side, ctx, p,
                                        overlay):
                return self._v(False, f"{pid} has a survivable retreat and "
                                      "must take it [15.1]")
            overlay[pid] = None
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
                self._eliminate(u)
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
            ok, _d, _w, _i = self._lof(e["hex"], u["hex"])
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
            if a == "resolve_errant":
                return self._resolve_errant_verdict(side, action)
            if a == "resolve_advance":
                return self._resolve_advance_verdict(side, action)
            if a == "resolve_esc_up":
                return self._resolve_esc_up_verdict(side, action)
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
            face = action.get("facing")
            if face is not None:
                face = self.name_hex.get(face, face)
                if face not in self.hex_t0:
                    return self._v(False, "unknown facing hex")
            return self._move_verdict(side, u, path,
                                      crew=action.get("crew"), face=face,
                                      up=bool(action.get("up")),
                                      tst=bool(action.get("testudo")))
        if a == "escalade":
            return self._escalade_verdict(side, action)
        if a == "testudo":
            return self._testudo_verdict(side, action)
        if a == "change_facing":
            return self._change_facing_verdict(side, action)
        if a == "fire":
            if self.tier < 2:
                return self._v(False, "combat is not gated in sandbox mode")
            return self._fire_verdict(side, action)
        if a == "breach_attack":
            if self.tier < 2:
                return self._v(False, "combat is not gated in sandbox mode")
            return self._breach_verdict(side, action)
        if a == "melee":
            if self.tier < 2:
                return self._v(False, "combat is not gated in sandbox mode")
            return self._melee_verdict(side, action)
        if a == "end_phase":
            if phase in ("deploy_jud", "deploy_rom"):
                return self._v(False, "finish deployment with deploy_done")
            if side != self.side_to_move():
                return self._v(False, "not your phase")
            if phase.endswith("_move") and self.tier >= 2:
                lag = self._refuge_laggards(side)
                if lag:
                    return self._v(False, "Routed/Panicked units must move towards Refuge using all available MF before the phase ends [15.3/17.21/8.1]: " + ", ".join(lag))
            return self._v(True, f"end of {phase}"
                           + (f" ({self.s['seg']} segment)" if self.s.get("seg") else ""))
        return self._v(False, f"unknown action type {a!r}")

    def _escalade_verdict(self, side, action):
        if self.s["phase"] != f"{'rom' if side == 'Rom' else 'jud'}_move":
            return self._v(False, "Escalades are placed and removed in the owning Movement Phase [6.5/8.7]")
        if side != "Rom":
            return self._v(False, "Judaeans may never enter an Escalade hex [6.5]")
        u = self.s["units"].get(str(action.get("pid")))
        if not u or u["side"] != side:
            return self._v(False, "not your unit")
        if u["hex"] is None:
            return self._v(False, "unit is not on the map")
        if not self._fresh(u):
            return self._v(False, "a Disrupted unit cannot place, maintain, or climb an Escalade [16.3]")
        if u.get("pushed"):
            return self._v(False, "already moved as part of a Siege Engine stack this MPh [8.3]")
        if u.get("fin"):
            return self._v(False, "this unit's MPh ended when it entered a hex containing a Panicked unit [17.21]")
        if self._ma(u) - u.get("mv", 0.0) < 4.0 - 1e-9:
            return self._v(False, "placing or removing an Escalade costs four MF [6.5/8.7]")
        h = u["hex"]
        e = self._esc_at(h)
        op = action.get("op")
        if op == "place":
            if e is not None:
                return self._v(False, "only one Base unit may be designated per hex [8.7]")
            if self._tst_at(h, broken=False) is not None:
                return self._v(False, "an Escalade may not be placed if a Testudo occupies the hex [6.5]")
            if not (self.utype(u)["cls"] == "heavy" or u["type"] == "velitae"):
                return self._v(False, "the Base unit must be Fresh Heavy Infantry or Velitae [6.5/8.7]")
            if u.get("up"):
                return self._v(False, "a scaling unit cannot become the Base unit [8.7]")
            if not any(self.hex_t(n) in ELEVATED for n in self._nb(h)):
                return self._v(False, "an Escalade is placed adjacent to an Elevated hex [8.7]")
            if any(not (self.utype(o)["cls"] in ("heavy", "hq")
                        or o["type"] == "velitae")
                   for o in self._occupants(h)):
                return self._v(False, "an Escalade may not be placed if a Testudo or units other than Heavy Infantry, Velitae, or HQ occupy the hex [6.5]")
            if not self.in_cc(u):
                return self._v(False, "out of Command Control: may not place Escalades [5.3]")
            return self._v(True, "place Escalade - 4 MF [6.5/8.7]")
        if op == "remove":
            if e is None or e["base"] != u["pid"]:
                return self._v(False, "only the Fresh Base unit removes its own Escalade [8.7]")
            if any(o.get("up") for o in self._occupants(h)):
                return self._v(False, "an Escalade may not be removed while units are on top of it [8.7]")
            return self._v(True, "remove Escalade - 4 MF [8.7]")
        return self._v(False, "escalade op must be 'place' or 'remove'")

    def _testudo_verdict(self, side, action):
        op = action.get("op")
        phase = self.s["phase"]
        setup = phase == "deploy_rom"
        if side != "Rom":
            return self._v(False, "Testudo is a Roman formation [6.6/2.6]")
        if not setup and phase != "rom_move":
            return self._v(False, "Testudo is assembled/disassembled in the Roman Movement Phase, or at setup [3.4/6.6/8.8]")
        if op == "form":
            pids = [str(p) for p in (action.get("pids") or [])]
            if not pids or len(set(pids)) != len(pids):
                return self._v(False, "name the forming units")
            us = []
            for p in pids:
                x = self.s["units"].get(p)
                if not x or x["side"] != side:
                    return self._v(False, "not your unit")
                if x["hex"] is None:
                    return self._v(False, f"{p} is not on the map")
                us.append(x)
            h = us[0]["hex"]
            if any(x["hex"] != h for x in us):
                return self._v(False, "forming units must share one hex [6.6]")
            if self.hex_t(h) in ELEVATED:
                return self._v(False, "a Testudo may not stand on an Elevated hex [6.61]")
            if self._tst_at(h) is not None:
                return self._v(False, "the hex already holds a Testudo or its Broken marker [6.6/16.4]")
            if self._esc_at(h) is not None:
                return self._v(False, "an Escalade may not share a hex with a Testudo [6.5]")
            if any(o["pid"] not in pids for o in self._occupants(h)):
                return self._v(False, "every unit in the hex must be part of the formation [6.1/6.61]")
            hv = [x for x in us if self.utype(x)["cls"] == "heavy"]
            vl = [x for x in us if x["type"] == "velitae"]
            hq = [x for x in us if self.utype(x)["cls"] == "hq"]
            if len(hv) + len(vl) + len(hq) != len(us):
                return self._v(False, "only Heavy Infantry, Velitae, and a HQ may form a Testudo [6.1/6.6]")
            if not (len(hv) in (2, 3) and len(vl) <= 1 and len(hq) <= 1
                    and not (vl and len(hv) > 2)):
                return self._v(False, "a Testudo is two or three Fresh Heavy Infantry, or two with one Fresh Velitae, plus at most one HQ [6.6]")
            if any(not self._fresh(x) for x in hv + vl):
                return self._v(False, "forming units must be Fresh [6.6]")
            if any(x["state"] == "panicked" for x in hq):
                return self._v(False, "a Panicked unit immediately disbands a Testudo [16.4]")
            fac = {x.get("faction") for x in hv + vl}
            if len(fac) > 1:
                return self._v(False, "units of different Legions may not form Testudo [6.6]")
            for x in hq:
                if self.utype(x).get("hq") != "commander" \
                        and x.get("faction") not in fac:
                    return self._v(False, "the HQ must belong to the forming Legion [5.4/6.6]")
            if not setup:
                for x in hv + vl:
                    if x.get("pushed"):
                        return self._v(False, f"{x['pid']} already moved as part of a Siege Engine stack this MPh [8.3]")
                    if self._ma(x) - x.get("mv", 0.0) < 6.0 - 1e-9:
                        return self._v(False, "forming Testudo costs six MF per forming unit [2.6/8.8]")
                    if not self.in_cc(x):
                        return self._v(False, "out of Command Control: may not assemble Testudo [5.3]")
            return dict(self._v(True, "form Testudo - 6 MF per forming unit [6.6/8.8]"),
                        hex=h, legion=next(iter(fac)))
        if op == "disband":
            if setup:
                return self._v(False, "disband during the Roman Movement Phase [8.8]")
            h = self.name_hex.get(action.get("hex"), action.get("hex"))
            t = self._tst_at(h, broken=False) if h in self.hex_t0 else None
            if t is None:
                return self._v(False, "no Testudo formation in that hex")
            if t.get("mv", 0.0) > 0:
                return self._v(False, "only a Testudo that has not yet moved this MPh may be disbanded [8.8]")
            for x in self._occupants(h):
                if self._fresh(x) and \
                        self._ma(x) - x.get("mv", 0.0) < 6.0 - 1e-9:
                    return self._v(False, "disbanding costs six MF to each Fresh occupant [8.8]")
                if self.utype(x)["cls"] != "hq" and not self.in_cc(x):
                    return self._v(False, "out of Command Control: may not disassemble Testudo [5.3]")
            return dict(self._v(True, "disband Testudo - 6 MF to each Fresh occupant, Disrupted not penalized [8.8]"),
                        hex=h)
        return self._v(False, "testudo op must be 'form' or 'disband'")

    def _change_facing_verdict(self, side, action):
        """[10.11/8.6] Free pivot within the hex, own Movement Phase only,
        by a Fresh pushing unit that started that MPh beneath the engine.
        (The 8.61/10.11 pivot lock after a unit crosses to/from an Elevated
        hex lands with tower boarding, B14 - no crossing action exists yet.)"""
        if self.s["phase"] != f"{'rom' if side == 'Rom' else 'jud'}_move":
            return self._v(False, "facing changes only during the owning Movement Phase [10.11]")
        u = self.s["units"].get(str(action.get("pid")))
        if not u or u["side"] != side:
            return self._v(False, "not your unit")
        if self.utype(u)["cls"] != "siege_engine":
            return self._v(False, "facing is a Siege Engine attribute [2.45]")
        if u["hex"] is None:
            return self._v(False, "unit is not on the map")
        fh = self.name_hex.get(action.get("face"), action.get("face"))
        if fh not in self.hex_t0:
            return self._v(False, "unknown facing hex")
        d = self._dir_of(u["hex"], fh)
        if d is None:
            return self._v(False, "facing must point at an adjacent hex [2.45/10.11]")
        if not self._se_crewed(u):
            return self._v(False, "facing change needs a Fresh pushing unit that started this MPh beneath the Siege Engine - white side up [10.11/8.6/2.45]")
        if u.get("lk"):
            return self._v(False, "a unit crossed between the Tower and an Elevated Hex - the Tower may not change facing again this MPh [8.61/10.11]")
        return dict(self._v(True,
                            f"face {self.hex_name[fh]} (free) [8.6/10.11]"),
                    face_dir=d)

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
        if self._tst_at(h, broken=False) is not None:
            return self._v(False, "the hex holds a Testudo - only its formed members may stack there [6.61]")
        sh = self._se_at(h)
        if sh is not None:
            if cls not in ("heavy", "light", "hq"):
                return self._v(False, "only Infantry may share a Siege Engine hex [6.4]")
            if cls != "hq":
                if not (cls == "heavy" or u["type"] == "velitae"):
                    return self._v(False, "up to two Heavy Infantry and/or Velitae (plus a HQ) may be beneath a Siege Engine [6.4]")
                if len(self._pushers(h)) >= 2:
                    return self._v(False, "a Siege Engine hex with two pushing units is filled to capacity [6.4]")
        if cls == "siege_engine":
            occ0 = self._occupants(h)
            if any(not (self.utype(o)["cls"] in ("heavy", "hq")
                        or o["type"] == "velitae") for o in occ0) \
                    or len(self._pushers(h)) > 2:
                return self._v(False, "up to two Heavy Infantry and/or Velitae (plus a HQ) may be beneath a Siege Engine [6.4]")
        bad = self._stack_check(h, side, u)
        if bad:
            return self._v(False, bad)
        fd = None
        face = action.get("facing")
        if face is not None:
            if cls != "siege_engine":
                return self._v(False, "facing is a Siege Engine attribute [2.45]")
            fh = self.name_hex.get(face, face)
            fd = self._dir_of(h, fh) if fh in self.hex_t0 else None
            if fd is None:
                return self._v(False, "facing must point at a hex adjacent to the deployment hex [2.45]")
        return dict(self._v(True, "deploy"), face_dir=fd)

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
        out = self._apply_act(side, action, verdict)
        self._esc_sweep()
        self._tst_sweep()
        return out

    def _apply_act(self, side, action, verdict):
        a = action["type"]
        if a == "deploy":
            u = self.s["units"][str(action["pid"])]
            h = self.name_hex.get(action["hex"], action["hex"])
            u["hex"] = h
            self.s["control"][h] = side
            out = {"placed": self.hex_name[h]}
            if self.utype(u)["cls"] == "siege_engine":
                # the counter always has an arrow [2.45]; default direction
                # 0 until pivoted (free, crewed, MPh [10.11])
                fd = verdict.get("face_dir")
                u["facing"] = fd if fd is not None else 0
                out["facing"] = self.hex_name.get(self._facing_hex(u))
            return out
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
            self._mph_bookkeeping()
            return {"next": self.s["phase"], "turn": 1,
                    "seg": self.s.get("seg")}
        if a == "move":
            u = self.s["units"][str(action["pid"])]
            path = [self.name_hex.get(h, h) for h in action["path"]]
            if verdict.get("tst"):
                dest = path[-1]
                t = self._tst_at(path[0])
                for pid_ in verdict["members"]:
                    m = self.s["units"][pid_]
                    m["hex"] = dest
                    m["mv"] = m.get("mv", 0.0) + verdict["spent"]
                t["hex"] = dest
                t["mv"] = t.get("mv", 0.0) + verdict["spent"]
                for h in path[1:]:
                    self.s["control"][h] = side
                return {"testudo_to": self.hex_name[dest],
                        "members": verdict["members"]}
            entering = u["hex"] is None
            was_up = bool(u.get("up"))
            se0 = self._se_at(u["hex"]) if u["hex"] is not None else None
            e0 = self._esc_at(u["hex"]) if u.get("up") else None
            if e0 and u["pid"] not in e0["used"]:
                e0["used"].append(u["pid"])
            u["hex"] = path[-1]
            u["mv"] = u.get("mv", 0.0) + verdict.get("spent", 0.0) \
                + verdict.get("forfeit", 0.0)
            tj = self._tst_at(path[-1], broken=False)
            if tj is not None and not tj.get("mv"):
                tj["hold"] = True
            if verdict.get("up"):
                u["up"] = True
                eN = self._esc_at(path[-1])
                if eN and u["pid"] not in eN["used"]:
                    eN["used"].append(u["pid"])
            else:
                u.pop("up", None)
            for h in (path if entering else path[1:]):
                self.s["control"][h] = side
            if entering:
                self.s["entry_queue"] = [q for q in self.s["entry_queue"]
                                         if q["pid"] != u["pid"]]
            out = {"to": self.hex_name[path[-1]]}
            crew = verdict.get("crew") or []
            for p in crew:
                x = self.s["units"][p]
                x["hex"] = path[-1]           # locked stack [8.3]
                x["pushed"] = True
            if crew:
                u["pushed"] = True
                out["crew"] = crew
                spent = verdict.get("spent", 0.0)
                u["tmf"] = u.get("tmf", 0.0) + spent
                rid = [o for o in self._occupants(path[0]) if o.get("up")]
                for o in rid:
                    o["hex"] = path[-1]
                    o["mv"] = o.get("mv", 0.0) + 2.0 * spent
                if rid:
                    out["riders"] = sorted(o["pid"] for o in rid)
            if was_up and se0 is not None and len(path) > 1 \
                    and self.hex_t(path[1]) in ELEVATED:
                se0["lk"] = True
            if verdict.get("up"):
                sN = self._se_at(path[-1])
                if sN is not None and sN["pid"] != u["pid"] \
                        and self.hex_t(path[-2]) in ELEVATED:
                    sN["lk"] = True
            if verdict.get("face_dir") is not None:
                u["facing"] = verdict["face_dir"]
                out["facing"] = self.hex_name.get(self._facing_hex(u))
            if side == "Jud":
                # any unescorted Siege Engine whose hex was entered 'is
                # eliminated and removed' and leaves a Wreck [11.4] - the
                # verdict only admits SE-only enemy hexes onto the path
                wrecked = [o["pid"]
                           for h2 in (path if entering else path[1:])
                           for o in self._occupants(h2)
                           if o["side"] == "Rom"
                           and self.utype(o)["cls"] == "siege_engine"]
                for pid_ in wrecked:
                    self._eliminate(self.s["units"][pid_])
                if wrecked:
                    out["wrecked"] = wrecked
            if u["state"] == "panicked":
                self.s["pmoved"] = True
            if verdict.get("pstop"):
                u["fin"] = True
                out["fin"] = True
                if verdict.get("panic_elim"):
                    self._eliminate(u)
                    out["eliminated"] = ("the forced stop overstacked the "
                                         "hex [17.21]")
            return out
        if a == "escalade":
            u = self.s["units"][str(action["pid"])]
            u["mv"] = u.get("mv", 0.0) + 4.0
            if action.get("op") == "place":
                self.s["esc"].append({"hex": u["hex"], "base": u["pid"],
                                      "used": []})
                return {"escalade": self.hex_name[u["hex"]], "op": "place"}
            self.s["esc"] = [e for e in self.s["esc"] if e["hex"] != u["hex"]]
            return {"escalade": self.hex_name[u["hex"]], "op": "remove"}
        if a == "testudo":
            h = verdict["hex"]
            if action.get("op") == "form":
                if self.s["phase"] != "deploy_rom":
                    for o in self._occupants(h):
                        if self.utype(o)["cls"] != "hq":
                            o["mv"] = o.get("mv", 0.0) + 6.0
                self.s["testudo"].append({"hex": h, "mv": 0.0,
                                          "legion": verdict.get("legion")})
                return {"testudo": self.hex_name[h], "op": "form"}
            for o in self._occupants(h):
                if self._fresh(o):
                    o["mv"] = o.get("mv", 0.0) + 6.0
            self.s["testudo"] = [t for t in self.s["testudo"]
                                 if t["hex"] != h]
            return {"testudo": self.hex_name[h], "op": "disband"}
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
        if a == "resolve_advance":
            return self._apply_advance(action)
        if a == "resolve_esc_up":
            moved = []
            for pid, hn in sorted((action.get("moves") or {}).items()):
                u = self.s["units"][str(pid)]
                h = self.name_hex[hn]
                u["hex"] = h
                u.pop("up", None)
                self.s["control"][h] = "Rom"
                moved.append({"pid": str(pid), "to": hn})
            self.s["pending"] = None
            out = self._advance_phase({"esc_up_done": True})
            out["esc_up"] = moved
            return out
        if a == "change_facing":
            u = self.s["units"][str(action["pid"])]
            u["facing"] = verdict["face_dir"]
            return {"facing": self.hex_name.get(self._facing_hex(u))}
        if a == "resolve_errant":
            out = self._apply_errant(str(action["pid"]))
            self.s["pending"] = None
            return {"errant": out}
        if a == "end_phase":
            return self._advance_phase(action)
        raise AssertionError(f"apply fell through for {a!r}")

    def _apply_loss(self, side, action):
        p = self.s["pending"]
        need = [c for c in p["letters"] if c != "B"]
        events = []
        xe = 0
        for pk, letter in zip(action["picks"], need):
            u = self.s["units"][str(pk["pid"])]
            el = {o["pid"] for o in
                  self._loss_elig(p["hex"], p["by"], p.get("lvl"))}
            if u["state"] == "eliminated" or u["pid"] not in el:
                xe += letter == "E"
                events.append({"pid": u["pid"], "event":
                               "forfeit - excess loss with no eligible "
                               "target [14.33/11.82]"})
                continue
            events.append({"pid": u["pid"],
                           "event": self._apply_letter(u, letter, p["source"])})
        self.s["pending"] = None
        sub = action.get("substitute_d")
        if "B" in p["letters"] and p["source"] == "melee":
            if sub is not None:
                # the defender substitutes a D (to a single unit) [14.2]
                u = self.s["units"][str(sub)]
                if u["state"] != "eliminated":
                    events.append({"pid": u["pid"], "event":
                                   self._apply_letter(u, "D", p["source"])
                                   + " (substituted for B) [14.2]"})
                movers = [e for e in events
                          if e["event"].startswith("disrupted")]
                if movers:
                    self.s["pending"] = {
                        "kind": "retreat", "hex": p["hex"],
                        "pids": [e["pid"] for e in movers], "by": side,
                        "rkind": "disrupt", "lvl": p.get("lvl"),
                        "attackers": p.get("attacker_pids") or [],
                        "mk": p.get("mk"), "xe": xe,
                        "optional": self._melee_stay_ok(p["hex"])}
            else:
                self._queue_retreat(p["hex"], side,
                                    p.get("attacker_pids"), p.get("mk"),
                                    p.get("lvl"), xe)
        elif p["source"] == "melee":
            movers = [e for e in events if e["event"] == "disrupted"]
            if movers:
                self.s["pending"] = {"kind": "retreat", "hex": p["hex"],
                                     "pids": [e["pid"] for e in movers],
                                     "by": side, "rkind": "disrupt",
                                     "lvl": p.get("lvl"),
                                     "attackers": p.get("attacker_pids")
                                     or [], "mk": p.get("mk"), "xe": xe,
                                     "optional":
                                     self._melee_stay_ok(p["hex"])}
        if self.s["pending"] is None and p["source"] == "melee" \
                and p.get("lvl") == "above":
            fell = self._tower_fall(p["hex"])
            if fell:
                events.append({"pid": fell, "event":
                               "Tower eliminated - no pushing units and the "
                               "Melee removed all Roman units atop [11.21]"})
        if self.s["pending"] is None and p.get("mk") \
                and p["source"] == "melee" and p.get("lvl") != "above":
            self._open_adv(p["hex"], p["attacker"],
                           p.get("attacker_pids"), p["mk"], xe)
        if self.s["pending"] is None and p.get("then_errant"):
            events.append({"errant": self._install_errant(p["then_errant"])})
        return {"events": events,
                "retreat_pending": self.s["pending"] is not None}

    def _apply_retreat(self, side, action):
        p = self.s["pending"]
        out = []
        for pid, names in (action.get("paths", {}) or {}).items():
            path = [self.name_hex.get(n, n) for n in names]
            u = self.s["units"][pid]
            bumps = 0
            for h in path[1:]:
                if self._retreat_full(u, h, side, {}):
                    bumps += 1                # [15.3] +1 level per such hex
            u["hex"] = path[-1]
            if self._esc_at(path[-1]) is not None \
                    and self.hex_t(path[-2]) in ELEVATED:
                u["up"] = True    # the card's escalade-as-retreat route [8.7]
            elif u.get("up"):
                u.pop("up")
            for _ in range(bumps):
                i = DISR_LADDER.index(u["state"]) \
                    if u["state"] in DISR_LADDER else 3
                if i >= 3:
                    self._eliminate(u)
                    break
                u["state"] = DISR_LADDER[i + 1]
            out.append({"pid": pid, "to": self.hex_name.get(u["hex"], None),
                        "state": u["state"]})
        for pid in [str(x) for x in action.get("eliminate", [])]:
            u = self.s["units"][pid]
            self._eliminate(u)
            out.append({"pid": pid, "to": None, "state": "eliminated",
                        "why": "no survivable retreat [15.1/14.21/7.5]"})
        self.s["pending"] = None
        if p.get("lvl") == "above":
            fell = self._tower_fall(p["hex"])
            if fell:
                out.append({"pid": fell, "to": None, "state": "eliminated",
                            "why": "Tower eliminated - no pushing units and "
                                   "the Melee removed all Roman units atop "
                                   "[11.21]"})
        if p.get("mk") and p.get("lvl") != "above":
            self._open_adv(p["hex"], self._enemy(p["by"]),
                           p.get("attackers"), p["mk"], p.get("xe", 0))
        return {"retreated": out}

    def _esc_up_opts(self):
        opts = {}
        zoc = self._zoc_map("Jud")
        for u in self.s["units"].values():
            if not (u.get("up") and u["hex"] is not None):
                continue
            if self._esc_at(u["hex"]) is not None:
                if not self._fresh(u):
                    continue
                hs = [self.hex_name[n] for n in self._nb(u["hex"])
                      if n in self.playable and self.hex_t(n) in ELEVATED
                      and not self._occupants(n)]
            else:
                se = self._se_at(u["hex"])
                if se is None or se["type"] not in ("tower",
                                                    "armored_tower") \
                        or self.utype(u)["cls"] == "hq":
                    continue
                fh = self._facing_hex(se)
                hs = [self.hex_name[fh]] if (
                    fh is not None and fh in self.playable
                    and self.hex_t(fh) in ELEVATED
                    and not self._occupants(fh)
                    and (self._fresh(u) or fh not in zoc)) else []
            if hs:
                opts[u["pid"]] = sorted(hs)
        return opts

    def _advance_phase(self, action=None):
        p = self.s["phase"]
        if p == "rom_melee" and not (action or {}).get("esc_up_done"):
            opts = self._esc_up_opts()
            if opts:
                self.s["pending"] = {"kind": "esc_up", "by": "Rom",
                                     "opts": opts}
                return {"pending": "esc_up", "next": p}
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
        if p == "rom_move":
            self.s["testudo"] = [t for t in self.s["testudo"]
                                 if not (t.get("broken") and t.get("armed"))]
        i = self.PHASES.index(p)
        self.s["fired"] = []
        self.s["fired_hexes"] = []
        self.s["cc_hex"] = None
        self.s["pmoved"] = False
        if p == "jud_melee":
            self.s["meleed"] = []
            self.s["melee_hexes"] = []
            for x in self.s["units"].values():
                x.pop("mk", None)
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
                self.s["melee_hexes"] = []
                for x in self.s["units"].values():
                    x.pop("mk", None)
            self.s["phase"] = self.PHASES[i + 1]
        if self.s["phase"].endswith("_fire"):
            phasing = "Rom" if self.s["phase"].startswith("rom_") else "Jud"
            self.s["seg"] = self._enemy(phasing)   # non-phasing fires first
            result["seg"] = self.s["seg"]
        if self.s["phase"] == "jud_move" and self.s["turn"] >= \
                self.scenario["reinforcement"]["from_turn"] and self.s["pool"]:
            result["reinforcement"] = self._roll_reinforcements()
        self._mph_bookkeeping()
        result["next"] = self.s["phase"]
        return result

    def _mph_bookkeeping(self):
        """Phase-boundary bookkeeping for the locked Siege Engine stack:
        clear the spent-pusher flags, and on entering a Movement Phase
        snapshot each engine's eligible pushing units (crew0) - the 8.6/
        2.45/10.11 'at the start of its MPh' condition that movement,
        facing changes and the white-side MA 0 all read."""
        for u in self.s["units"].values():
            u.pop("pushed", None)
            u.pop("crew0", None)
            u.pop("mv", None)
            u.pop("tmf", None)
            u.pop("lk", None)
            u.pop("fin", None)
        for e in self.s.get("esc", []):
            e["used"] = []
        for t in self.s.get("testudo", []):
            t.pop("hold", None)
            if not t.get("broken"):
                t["mv"] = 0.0
        if self.s["phase"] == "rom_move":
            for t in self.s["testudo"]:
                if t.get("broken"):
                    t["armed"] = True
                    for p_ in t["members"]:
                        x = self.s["units"].get(p_)
                        if x and x["hex"] == t["hex"] and self._fresh(x):
                            x["mv"] = 6.0
        if not self.s["phase"].endswith("_move"):
            return
        for se in self.s["units"].values():
            if self.utype(se)["cls"] == "siege_engine" and se["hex"]:
                se["crew0"] = sorted(
                    o["pid"] for o in self._occupants(se["hex"])
                    if self._fresh(o) and o["pid"] != se["pid"]
                    and not o.get("up")
                    and (self.utype(o)["cls"] == "heavy"
                         or o["type"] == "velitae"))

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
