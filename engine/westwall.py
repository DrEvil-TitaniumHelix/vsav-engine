"""
westwall.py - The legality gate for the SPI Westwall quad family (Arnhem
first). Same anti-cheat trinity as bluegray.py/strategic.py: EVERY action
enters through propose()/submit(); submit() logs EVERY proposal (including
rejections) with rulebook-cited reasons, engine-owned seeded dice and state
hashes to an append-only JSONL log that engine/verify_game.py replays.

Turn structure (Standard Rules 4.1): each GT = First Player-Turn (Movement
Phase then Combat Phase) then Second Player-Turn, then the GT marker advances.
Allied is the First Player [18.17]. 10 GTs.

Actions:
  {"type":"move", "unit":pid, "dest":[c,r]}
  {"type":"reinforce", "unit":pid, "hex":[c,r]}      (15.x column/edge/airborne)
  {"type":"exit", "unit":pid, "edge":"west"|"east"}  (15.4, German only)
  {"type":"demolition", "attempt":{side_key:bool}}   (12.x, German pending)
  {"type":"end_movement"}
  {"type":"battle", "attackers":[pid..], "defenders":[pid..], "gsp":n}
  {"type":"fpf", "allocations":[[arty_pid, def_pid]..], "gsp":n}  (8.4 pending)
  {"type":"retreat", "unit":pid, "path":[[c,r]..], "eliminate":bool,
   "city_reduce":bool}                               (7.7/11.1)
  {"type":"advance", "unit":pid, "dest":[c,r]} / {"type":"advance","decline":1}
  {"type":"end_phase"}
"""
import heapq
from collections import deque

try:
    from .gate import GateGame      # imported as engine.westwall
except ImportError:
    from gate import GateGame       # imported with engine/ on sys.path

ARTY = {"artillery", "sp_artillery", "ab_artillery"}
VEHICLE = {"armor", "recon", "mech", "sp_artillery"}      # 5.24
ROW_RANK = ["rough", "broken", "grove", "clear"]          # 7.61, defender-best first


class WestwallGame(GateGame):
    # Frozen log contract — see gate.GateGame.HASH_KEYS.
    HASH_KEYS = ("turn", "phase", "mover", "over", "winner", "rng_calls", "units",
                 "moved", "done", "arrived", "entered", "drops", "pool", "exited",
                 "dead", "vp", "gsp_left", "demolished", "repaired", "offered",
                 "fought", "defended", "advanced", "fpf_used", "adverse",
                 "displaced_arty", "eng_lock", "eng_start", "assault",
                 "battle_no", "pending")
    TURN_NOUN = "GT"

    def __init__(self, game, scenario_path, live_dir, seed=None, tier=None):
        super().__init__(game, scenario_path, live_dir)
        cfg = self.scenario["game"]
        self.gsp_sched = {int(k): v for k, v in
                          (cfg.get("gsp", {}).get("All") or {}).items()}
        self.vp_cfg = self.scenario.get("vp", {})
        self.loc_cfg = self.scenario.get("loc", {})
        self.waal_zone = set(self.vp_cfg.get("waal_zone", []))
        self.rijn_zone = set(self.vp_cfg.get("rijn_zone", []))
        self.reserve = {u["id"]: u for u in self.scenario.get("reserve", [])}
        self.catalog = {u["id"]: u for u in
                        self.scenario.get("units", []) + self.scenario.get("reserve", [])}
        self._resolve_tier(tier)
        # pristine copies of demolishable/repairable sides (runtime mutation).
        # Captured ONCE per Game object - later gates on the same Game must
        # see the ORIGINAL terrain, not a previous game's demolitions.
        pris = getattr(game, "_westwall_pristine", None)
        if pris is None:
            pris = {k: dict(v) for k, v in game.terrain["sides"].items()
                    if v.get("bridge_type") in ("canal", "rail")}
            game._westwall_pristine = pris
        self._pristine = pris
        self._resume_or_new(seed, required=("demolished",))
        self._apply_bridge_state()

    # ------------------------------------------------------------ lifecycle
    def new_game(self, seed=None):
        seed = self._fresh_seed(seed)
        units = self._scenario_units()
        self.s = {
            "seed": seed, "rng_calls": 0, "n": 0, "tier": self.tier,
            "turn": 1, "phase": "movement", "mover": self.first_player,
            "over": False, "winner": None, "level": None,
            "units": units,
            "moved": {},          # pid -> MP spent this movement phase
            "done": [],           # pids finished moving (5.15: one move each)
            "arrived": {},        # pid -> GT of airborne arrival (15.32 MA 3)
            "entered": {},        # entry hexkey -> column count this player turn
            "drops": [],          # hexes used by airborne arrivals this turn (15.31)
            "pool": {pid: e["due"] for pid, e in self.reserve.items()},
            "exited": {},         # pid -> edge name (15.42 re-entry pool)
            "dead": [],
            "vp": {s: 0 for s in self.game.side_order},
            "gsp_left": self.gsp_sched.get(1, 0),
            "demolished": [], "repaired": [], "offered": [],   # bridge side keys
            "fought": [], "defended": [], "advanced": [],
            "fpf_used": [],       # arty pids that used FPF this GT (8.46)
            "adverse": {},        # arty pid -> [turn, mover] of last adverse result (8.41)
            "displaced_arty": [],  # arty displaced this combat phase (8.41/7.82)
            "eng_lock": None,     # "moved"|"crossed" - 13.21 exclusivity this player turn
            "eng_start": None,    # engineer [c,r] at the start of the German turn (13.1)
            "assault": [],        # pids stacked with the Engineer owing a 13.24 assault
            "battle_no": 0,
            "pending": None,
        }
        self._reset_log()
        self._log({"event": "init", "mode": "westwall",
                   "scenario": self.scenario["name"], "tier": self.tier,
                   "rules_scope": self.rules_scope(), "seed": seed,
                   "turns": self.turns, "first_player": self.first_player,
                   "units": self._units_for_log(units)})
        self.save()

    # ------------------------------------------------------------ bridges
    def _apply_bridge_state(self):
        """Runtime hexside truth: demolished bridges lose crossing/bridge/road
        [12.13]; repaired canal bridges get them back [13.1]."""
        sides = self.game.terrain["sides"]
        for k, pristine in self._pristine.items():
            sides[k] = dict(pristine)
            if k in self.s["demolished"] and k not in self.s["repaired"]:
                sides[k].pop("bridge", None)
                sides[k].pop("bridge_type", None)
                sides[k].pop("crossing", None)
                sides[k].pop("road", None)

    def _bridge_hexes(self, key):
        a, b = key.split("|")
        return [(int(a[:2]), int(a[2:])), (int(b[:2]), int(b[2:]))]

    def _live_bridges(self):
        """Demolishable bridges not yet offered/demolished [12.11/12.14]."""
        return [k for k in self._pristine
                if k not in self.s["offered"] and k not in self.s["demolished"]]

    def _demolition_triggers(self, hexes):
        """Bridges whose offer triggers when an Allied unit stands in `hexes`
        [12.11: the FIRST Allied unit into any hex of which the bridge forms
        a side, no matter what the phase]."""
        out = []
        hs = {tuple(h) for h in hexes}
        for k in self._live_bridges():
            if hs & set(self._bridge_hexes(k)):
                out.append(k)
        return sorted(out)

    def _offer_demolition(self, moved_hexes, ev):
        trig = self._demolition_triggers(moved_hexes)
        if trig:
            self.s["offered"].extend(trig)
            self.s["pending"] = {"awaiting": "demolition", "by": "Ger",
                                 "bridges": trig, "resume": self.s["pending"]}
            ev.append({"demolition_offer": trig})
        return ev

    # ------------------------------------------------------------ helpers
    def cat(self, pid):
        return self.catalog[str(pid)]

    def cls(self, pid):
        return self.cat(pid).get("cls", "infantry")

    def stats(self, pid):
        return self.cat(pid)["stats"]

    def is_arty(self, pid):
        return self.cls(pid) in ARTY

    def is_vehicle(self, pid):
        return self.cls(pid) in VEHICLE

    def is_airborne(self, pid):
        return bool(self.cat(pid).get("airborne"))

    def _live(self, side=None, dz=None):
        for u in self.s["units"].values():
            if self.cls(u["pid"]) == "dz" and not dz:
                continue
            if side is None or u["side"] == side:
                yield u

    def rules_board(self, exclude_pid=None):
        """Combat units as the movement board. DZ counters are invisible to
        movement/ZOC entirely [15.35]."""
        return [dict(id=u["pid"], name=u["slot"], side=u["side"],
                     col=u["col"], row=u["row"])
                for u in self._live() if u["pid"] != exclude_pid]

    def _positions(self, side=None, dz=None):
        return {(u["col"], u["row"]) for u in self._live(side, dz=dz)}

    def side_feat(self, a, b):
        return self.game.side_features(a, b)

    def _river_side(self, a, b):
        return self.side_feat(a, b).get("water") == "river"

    def _river_no_bridge(self, a, b):
        f = self.side_feat(a, b)
        return f.get("water") == "river" and not f.get("bridge")

    def _engineer(self):
        for u in self._live("All"):
            if self.cls(u["pid"]) == "engineer":
                return u
        return None

    def budget(self, pid):
        u = self.unit(pid)
        ma = self.stats(pid)["ma"]
        if self.s["arrived"].get(str(pid)) == self.s["turn"]:
            ma = min(ma, 3)     # 15.32 airborne arrival turn
        return ma - self.s["moved"].get(str(pid), 0)

    # ------------------------------------------------------------ movement
    def _step_ok(self, pid, cur, nb, board_ctx):
        """One movement step legality beyond move_cost: 5.24 vehicle classes,
        the Engineer river-crossing arcs [13.2]."""
        cost = self.game.move_cost(cur, nb)
        f = self.side_feat(cur, nb)
        eng = board_ctx.get("eng_cross")
        crossing_arc = False
        if cost is None:
            # 13.22: airborne/glider units may cross a river hexside through
            # the Engineer's hex (or out of it) at no river charge
            if eng and self._river_side(cur, nb) and (cur == eng or nb == eng) \
               and board_ctx["is_ab_inf"]:
                t = self.game.hex_terrain(*nb)
                cost = float(self.game.terrain_mp.get(t, self.game.default_mp))
                crossing_arc = True
            else:
                return None, False
        if self.is_vehicle(pid):
            water = f.get("water")
            roady = f.get("road") in ("road", "trail")
            if water in ("river", "stream") and not roady:
                return None, False           # 5.24 hexside bar (rail bridges/ferries too)
            if f.get("ferry"):
                return None, False           # ferries carry no road [5.24]
            t = self.game.hex_terrain(*nb)
            if t in ("rough", "broken", "woods") and not roady:
                return None, False           # 5.24 hex bar except via road/trail
        return cost, crossing_arc

    def dests(self, pid):
        """Legal destinations {(c,r): mp} - full Westwall step semantics."""
        pid = str(pid)
        u = self.unit(pid)
        if self.cls(pid) == "dz":
            return {}
        board = self.rules_board(exclude_pid=pid)
        enemy = self.game.enemy(u["side"])
        epos = {(b["col"], b["row"]) for b in board if b["side"] == enemy}
        fpos = {(b["col"], b["row"]) for b in board if b["side"] != enemy}
        ezoc = self.game.zoc_hexes(board, enemy)
        start = (u["col"], u["row"])
        if start in ezoc:
            return {}                        # 5.14/6.13 locked in EZOC
        ma = self.budget(pid)
        if ma <= 0:
            return {}
        # Engineer crossing context (13.21): available to airborne/glider
        # (not airborne artillery, 13.23) while the Engineer has spent no MP
        # this Allied player-turn and is free of EZOC
        ctx = {"eng_cross": None,
               "is_ab_inf": self.cls(pid) in ("para", "glider", "polish")
               or (self.is_airborne(pid) and self.cls(pid) not in ARTY)}
        eng = self._engineer()
        if eng and u["side"] == "All" and pid != eng["pid"] \
           and self.s["eng_lock"] != "moved" \
           and (eng["col"], eng["row"]) not in ezoc:
            ctx["eng_cross"] = (eng["col"], eng["row"])
        # 13.24: one airborne/glider unit may END stacked with the Engineer
        # (assault stack) when an enemy sits across an adjacent river hexside
        assault_hex = None
        if ctx["eng_cross"] and ctx["is_ab_inf"] and not self.s["assault"]:
            eh = ctx["eng_cross"]
            for nb in self.game.neighbors(*eh):
                if nb in epos and self._river_side(eh, nb):
                    assault_hex = eh
                    break
        best = {start: 0.0}
        pq = [(0.0, start)]
        while pq:
            cost, cur = heapq.heappop(pq)
            if cost > best.get(cur, 1e9):
                continue
            if cur != start and cur in ezoc:
                continue                      # 6.0 stop on entering EZOC
            for nb in self.game.neighbors(*cur):
                if nb in epos or not self.game.on_map(*nb):
                    continue                  # 5.12
                c, _ = self._step_ok(pid, cur, nb, ctx)
                if c is None:
                    continue
                nc = cost + c
                if nc > ma + 1e-9 or nc >= best.get(nb, 1e9):
                    continue
                best[nb] = nc
                heapq.heappush(pq, (nc, nb))
        best.pop(start, None)
        out = {}
        for h, c in best.items():
            if h in fpos:
                if assault_hex and h == assault_hex:
                    out[h] = c                # 13.24 stack with the Engineer
                continue                      # 5.31 stacking prohibited
            out[h] = c
        return out

    # ------------------------------------------------------------ engagement
    def _engage_adjacent(self, ua, ub):
        """Ground-combat contact: adjacency across a hexside that is not a
        non-bridge river hexside [6.33; ferries are non-bridge]."""
        pa, pb = (ua["col"], ua["row"]), (ub["col"], ub["row"])
        return pb in self.game.neighbors(*pa) and not self._river_no_bridge(pa, pb)

    def _contacts(self, side):
        """(must_attack_pids, must_be_attacked_pids) [7.11/7.12], with the
        13.24 assault obligation folded in. Advanced units are out [7.96];
        artillery adjacent only across rivers is exempt [8.34]."""
        adv = set(self.s["advanced"])
        mine, theirs = set(), set()
        enemies = [u for u in self._live(self.game.enemy(side)) if u["pid"] not in adv]
        for u in self._live(side):
            if u["pid"] in adv:
                continue
            for e in enemies:
                if self._engage_adjacent(u, e):
                    mine.add(u["pid"])
                    theirs.add(e["pid"])
        for pid in self.s["assault"]:
            if str(pid) in self.s["units"]:
                mine.add(str(pid))
        return mine, theirs

    # ------------------------------------------------------------ propose
    def propose(self, side, action):
        s = self.s
        t = action.get("type")
        if s["over"]:
            return self._v(False, "game is over [17.0]")
        if s["pending"]:
            p = s["pending"]
            if t != p["awaiting"]:
                return self._v(False, f"pending {p['awaiting']} must be resolved first")
            if side != p["by"]:
                return self._v(False, f"the {p['by']} player owns the pending {p['awaiting']}")
        elif side != s["mover"]:
            return self._v(False, f"not {side}'s player-turn [4.1]")
        fn = {"move": self._propose_move, "reinforce": self._propose_reinforce,
              "exit": self._propose_exit, "demolition": self._propose_demolition,
              "battle": self._propose_battle, "fpf": self._propose_fpf,
              "retreat": self._propose_retreat, "advance": self._propose_advance,
              }.get(t)
        if fn:
            return fn(side, action)
        if t == "end_movement":
            if s["phase"] != "movement":
                return self._v(False, "not the movement phase [4.1]")
            return self._v(True, "movement phase complete [4.1]")
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
            return self._v(False, "movement only in the own Movement Phase [5.11]")
        u, err = self._gate_unit(side, action)
        if err:
            return err
        pid = u["pid"]
        if pid in s["done"]:
            return self._v(False, f"{u['slot']} has already moved this phase [5.15]")
        if self.cls(pid) == "dz":
            return self._v(False, "DZ counters are not units and never move [15.35]")
        if self.cls(pid) == "engineer" and s["eng_lock"] == "crossed":
            return self._v(False,
                           "the Engineer enabled river crossings this player-turn - "
                           "it may expend no MP [13.21]")
        dest = tuple(action.get("dest", ()))
        dd = self.dests(pid)
        if dest not in dd:
            return self._v(False,
                           f"{dest} is not a legal destination for {u['slot']} "
                           f"[5.x/6.x movement, 5.24 vehicle classes, 5.31 stacking]")
        return self._v(True, f"move {u['slot']} to {dest} for {dd[dest]:g} MP")

    def _entry_cost(self, e, h, count_before):
        """Column entry MP [15.11-15.13]: the entry hex per the Terrain Key
        (road rate when a road leads off the map through it), later units in
        the same hex pay one more column step each."""
        has_road = any(self.side_feat(h, nb).get("road") == "road"
                       for nb in self.game.neighbors(*h))
        t = self.game.hex_terrain(*h)
        base = float(self.game.terrain_mp.get(t, self.game.default_mp))
        step = 0.5 if has_road else base
        return step * (count_before + 1) if has_road else base + count_before * step

    def _propose_reinforce(self, side, action):
        s = self.s
        if s["phase"] != "movement":
            return self._v(False, "reinforcements enter during the Movement Phase [15.0]")
        pid = str(action.get("unit"))
        if pid not in self.reserve or pid in s["units"] \
           or (pid in s["dead"] and self.cls(pid) != "engineer"):
            return self._v(False, f"{pid} is not an available reinforcement")
        e = self.reserve[pid]
        if e["side"] != side:
            return self._v(False, f"{e['slot']} is not a {side} reinforcement")
        if s["pool"].get(pid, 99) > s["turn"]:
            return self._v(False, f"{e['slot']} is due GT {s['pool'].get(pid)}, "
                                  f"not GT {s['turn']} [15.0/15.23]")
        h = tuple(action.get("hex", ()))
        if len(h) != 2:
            return self._v(False, "reinforce needs a hex [c,r]")
        board = self.rules_board()
        enemy = self.game.enemy(side)
        epos = {(b["col"], b["row"]) for b in board if b["side"] == enemy}
        fpos = {(b["col"], b["row"]) for b in board if b["side"] == side}
        ezoc = self.game.zoc_hexes(board, enemy)
        arrival = e.get("arrival")
        if arrival == "airborne":
            tgt = tuple(e["target"])
            legal = {tgt} | set(self.game.neighbors(*tgt))
            legal = {x for x in legal if self.game.on_map(*x)}
            if h not in legal:
                return self._v(False, f"airborne arrival within one hex of "
                                      f"{tgt} [15.31/18.13]")
            if h in epos or h in fpos or h in self._positions(dz=False):
                return self._v(False, "airborne units may not land in occupied "
                                      "hexes [15.31/15.33]")
            if list(h) in s["drops"]:
                return self._v(False, "only one airborne unit per hex [15.31]")
            return self._v(True, f"{e['slot']} drops at {h} [15.31] "
                                 f"(MA 3 this turn [15.32])")
        # ground entries (column / edge)
        entry = [tuple(x) for x in e["entry"]]
        if h not in entry:
            return self._v(False, f"entry hexes for {e['slot']}: "
                                  f"{[list(x) for x in entry[:6]]}... [15.22/18.14/18.15]")
        if h in epos:
            alt = self._entry_alternate(e, entry, epos, fpos, ezoc)
            return self._v(False, f"entry hex {h} is enemy-occupied - nearest "
                                  f"unblocked alternate: {alt} [15.22]")
        if h in fpos and h in ezoc:
            return self._v(False, f"entry hex {h} holds a friendly unit in an "
                                  f"EZOC [15.22]")
        if h in fpos:
            return self._v(False, f"entry hex {h} is occupied - stacking is "
                                  f"prohibited [5.31]")
        cost = self._entry_cost(e, h, s["entered"].get(f"{h[0]:02d}{h[1]:02d}", 0))
        if cost > self.stats(pid)["ma"] + 1e-9:
            return self._v(False, f"column position costs {cost:g} MP > MA [15.13]")
        return self._v(True, f"{e['slot']} enters at {h} for {cost:g} MP [15.1]")

    def _entry_alternate(self, e, entry, epos, fpos, ezoc):
        return [list(h) for h in entry if h not in epos
                and not (h in fpos and h in ezoc)][:3]

    def _propose_exit(self, side, action):
        s = self.s
        if side != "Ger":
            return self._v(False, "only the German player may exit the map [15.4]")
        if s["phase"] != "movement":
            return self._v(False, "exit only during the German Movement Phase [15.43]")
        u, err = self._gate_unit(side, action)
        if err:
            return err
        pid = u["pid"]
        # exiting is the last step of a move [15.4: the unit expends MP to
        # enter the imaginary off-map hex] - a unit that already moved may
        # still exit on remaining MP; the budget check below governs
        pos = (u["col"], u["row"])
        edges = self.game.spec.get("exit", {}).get("german_edges", {})
        edge = None
        for name, (a, b) in edges.items():
            hexes = self._edge_hexes(a, b)
            if pos in hexes:
                edge = name
        if edge is None:
            return self._v(False, f"{u['slot']} is not on an exit edge hex "
                                  f"(west 0601-2301 / east 0126-2726) [15.41]")
        t = self.game.hex_terrain(*pos)
        cost = float(self.game.terrain_mp.get(t, self.game.default_mp))
        if self.budget(pid) < cost - 1e-9:
            return self._v(False, f"exiting costs the imaginary-hex terrain "
                                  f"cost {cost:g} MP [15.4]")
        board = self.rules_board(exclude_pid=pid)
        if pos in self.game.zoc_hexes(board, self.game.enemy(side)):
            return self._v(False, "a unit in an EZOC may not move (or exit) [5.14]")
        return self._v(True, f"{u['slot']} exits the {edge} edge [15.41]")

    def _edge_hexes(self, a, b):
        (ca, ra), (cb, rb) = (int(a[:2]), int(a[2:])), (int(b[:2]), int(b[2:]))
        out = set()
        if ca == cb:
            for r in range(min(ra, rb), max(ra, rb) + 1):
                if self.game.on_map(ca, r):
                    out.add((ca, r))
            return out
        top = min(ra, rb) <= 2
        for c in range(min(ca, cb), max(ca, cb) + 1):
            rows = [r for r in range(0, 28) if self.game.on_map(c, r)]
            if rows:
                out.add((c, min(rows) if top else max(rows)))
        return out

    def _propose_demolition(self, side, action):
        p = self.s["pending"]
        if not p or p["awaiting"] != "demolition":
            return self._v(False, "no demolition offer pending [12.11]")
        att = action.get("attempt", {})
        if not isinstance(att, dict) or set(att) - set(p["bridges"]):
            return self._v(False, f"attempt map over the offered bridges only: "
                                  f"{p['bridges']}")
        return self._v(True, "demolition decision [12.12: die 1-2 demolishes; "
                             "declining forfeits the one-time chance 12.11/12.14]")

    # ---------------------------------------------------------------- combat
    def _terrain_row(self, def_units, melee_atk):
        """The defender's CRT row [7.4x]: best of each defender's hex terrain,
        plus the bridge-hexside row when ALL melee attackers attack across
        bridge hexsides [7.61 Grove/Bridge], with the 7.42 stream condition
        folded into the shared Broken/Town/Woods/Stream row. Pure barrage:
        hex terrain only [8.62]."""
        alias = self.combat["crt"]["terrain_alias"]
        rows = []
        for d in def_units:
            t = self.game.hex_terrain(d["col"], d["row"]) or "clear"
            rows.append(alias.get(t, t if t in ROW_RANK else "clear"))
        best = min(rows, key=ROW_RANK.index)
        if melee_atk:
            dpos = {(d["col"], d["row"]) for d in def_units}
            all_bridge = all(
                any(self.side_feat((a["col"], a["row"]), dp).get("bridge")
                    for dp in dpos if dp in self.game.neighbors(a["col"], a["row"]))
                for a in melee_atk)
            if all_bridge and ROW_RANK.index("grove") < ROW_RANK.index(best):
                best = "grove"
        return best

    def _column_pos(self, row, diff):
        cols = self.combat["crt"]["terrain_columns"][row]
        def parse(br):
            b = br.replace("+", "")
            if "," in b:
                lo, hi = b.split(",")
                lo = int(lo)
                hi = int(hi) if not b.startswith("-") else -int(hi)
                return (min(lo, hi), max(lo, hi))
            if "-" in b[1:]:
                lo, hi = b.rsplit("-", 1)
                return (int(lo), int(hi))
            return (int(b), int(b))
        lo0 = parse(cols[0])[0]
        if diff <= lo0:
            return 1
        if diff >= 12:
            return len(cols)
        for i, br in enumerate(cols):
            lo, hi = parse(br)
            if lo <= diff <= hi:
                return i + 1
        return len(cols)

    def crt_result(self, row, diff, die):
        pos = self._column_pos(row, diff)
        return self.combat["crt"]["die_rows"][str(die)][pos - 1], pos

    def _gsp_ok_hexes(self, hexes):
        """14.11: GSP applies only within 3 hexes of an Allied NON-airborne
        unit (every affected hex must qualify)."""
        anchors = [(u["col"], u["row"]) for u in self._live("All")
                   if not self.is_airborne(u["pid"])]
        for h in hexes:
            if not any(self.game.hex_distance(h, a) <= 3 for a in anchors):
                return False
        return True

    def _propose_battle(self, side, action):
        s = self.s
        if not self.combat:
            return self._v(False, f"combat is not enforced at tier {self.tier}")
        if s["phase"] != "combat":
            return self._v(False, "battles happen in the Combat Phase [4.1]")
        atk_ids = [str(p) for p in action.get("attackers", [])]
        def_ids = [str(p) for p in action.get("defenders", [])]
        if not atk_ids or not def_ids:
            return self._v(False, "battle needs attackers and defenders [7.0]")
        for pid in atk_ids + def_ids:
            if pid not in s["units"]:
                return self._v(False, f"unit {pid} is not on the map")
        atk = [self.unit(p) for p in atk_ids]
        dfd = [self.unit(p) for p in def_ids]
        if any(u["side"] != side for u in atk):
            return self._v(False, "attackers must be the phasing player's units [7.0]")
        if any(u["side"] == side for u in dfd):
            return self._v(False, "defenders must be enemy units [7.0]")
        if any(self.cls(p) == "dz" for p in atk_ids + def_ids):
            return self._v(False, "DZ counters have no combat strength [15.35]")
        if any(p in s["fought"] for p in atk_ids):
            return self._v(False, "a unit attacks once per Combat Phase [7.14]")
        if any(p in s["defended"] for p in def_ids):
            return self._v(False, "a unit is attacked once per Combat Phase [7.14]")
        if any(p in s["advanced"] for p in atk_ids + def_ids):
            return self._v(False, "advanced units neither attack nor are attacked [7.96]")
        melee, barrage = self._split_attackers(atk_ids, dfd)
        # non-artillery must be adjacent [7.15]; never across non-bridge rivers [6.33]
        for p in melee:
            u = self.unit(p)
            if not self.is_arty(p) or True:
                pass
            for d in dfd:
                if not self._engage_adjacent(u, d) and not self._assault_pair(p, d):
                    return self._v(False,
                                   f"{u['slot']} is not adjacent to {d['slot']} across a "
                                   f"crossable hexside - all attackers adjacent to all "
                                   f"defenders [7.23/6.33]")
        for p in barrage:
            if not self.is_arty(p):
                return self._v(False,
                               f"{self.unit(p)['slot']} is not artillery and not "
                               f"adjacent - non-artillery attack only adjacent [7.15]")
            u = self.unit(p)
            rng = self.stats(p).get("range", 0)
            if not any(self.game.hex_distance((u["col"], u["row"]),
                                              (d["col"], d["row"])) <= rng for d in dfd):
                return self._v(False, f"{u['slot']} has no defender within barrage "
                                      f"range {rng} [8.11/8.22]")
        # 14.12: max two artillery per combat for the attacker
        n_arty = sum(1 for p in atk_ids if self.is_arty(p))
        if n_arty > 2:
            return self._v(False, "no more than two artillery units per combat [14.12]")
        # pure bombardment hits a single hex [8.13]
        dhexes = {(d["col"], d["row"]) for d in dfd}
        if not melee and len(dhexes) > 1:
            return self._v(False, "a pure barrage attacks a single hex [8.13]")
        # full stacks fight together: Westwall has no stacks (5.31), except the
        # 13.24 assault stack: Engineer+assault unit - the Engineer need not join
        # GSP allocation [9.x/14.11]
        gsp = int(action.get("gsp", 0) or 0)
        if gsp:
            if side != "All":
                return self._v(False, "only the Allied player has GSP [14.11]")
            if gsp > s["gsp_left"]:
                return self._v(False, f"only {s['gsp_left']} GSP left this GT [18.16/9.14]")
            if not self._gsp_ok_hexes(dhexes):
                return self._v(False, "GSP applies only within 3 hexes of an Allied "
                                      "non-airborne unit [14.11]")
        # 7.12/8.31: all adjacent friendlies participate - a battle must take
        # every unfought friendly whose obligations it covers
        missing = self._mandatory_joiners(side, atk_ids, def_ids)
        if missing:
            names = ", ".join(self.cat(p)["desig"] for p in missing[:4])
            return self._v(False,
                           f"all adjacent friendly units participate in an attack - "
                           f"{names} must join this battle [7.12/8.31]")
        return self._v(True, f"battle declared ({len(atk_ids)} vs {len(def_ids)}"
                             + (f", {gsp} GSP" if gsp else "") + ") [7.0]")

    def _mandatory_joiners(self, side, atk_ids, def_ids):
        """Unfought friendlies adjacent (crossable) to ALL of the battle's
        defender hexes, whose own un-attacked adjacent enemies all lie inside
        this battle - they must join [7.12/8.31]. A unit 7.23 bars from the
        multi-hex battle is excused; the 14.12 artillery cap wins over 8.31
        (declared in rules_scope)."""
        s = self.s
        dfd = [self.unit(p) for p in def_ids if p in s["units"]]
        dhexes = {(d["col"], d["row"]) for d in dfd}
        n_arty = sum(1 for p in atk_ids if self.is_arty(p))
        missing = []
        for u in self._live(side):
            p = u["pid"]
            if p in atk_ids or p in s["fought"] or p in s["advanced"] \
               or self.cls(p) == "dz":
                continue
            targets = [e for e in self._live(self.game.enemy(side))
                       if e["pid"] not in s["defended"]
                       and e["pid"] not in s["advanced"]
                       and self._engage_adjacent(u, e)]
            if not targets:
                continue
            if not all(e["pid"] in def_ids for e in targets):
                continue               # obligations outside this battle
            if not all(dh in self.game.neighbors(u["col"], u["row"])
                       and not self._river_no_bridge((u["col"], u["row"]), dh)
                       for dh in dhexes):
                continue               # 7.23 bars it - excused
            if self.is_arty(p) and n_arty >= 2:
                continue               # 14.12
            missing.append(p)
            if self.is_arty(p):
                n_arty += 1
        return missing

    def _assault_pair(self, pid, d):
        """13.24: the assault-stacked unit engages across the adjacent river
        hexside."""
        if pid not in self.s["assault"]:
            return False
        u = self.unit(pid)
        pa, pb = (u["col"], u["row"]), (d["col"], d["row"])
        return pb in self.game.neighbors(*pa) and self._river_side(pa, pb)

    def _split_attackers(self, atk_ids, dfd):
        """(melee, barraging): artillery not adjacent (crossable) to any
        defender barrages [8.0/8.31]; everything adjacent fights as melee -
        adjacent artillery contributes its Barrage strength and suffers
        results [8.31/8.33]."""
        melee, barrage = [], []
        for p in atk_ids:
            u = self.unit(p)
            adj = any(self._engage_adjacent(u, d) or self._assault_pair(p, d)
                      for d in dfd)
            if adj:
                melee.append(p)
            elif self.is_arty(p):
                barrage.append(p)
            else:
                melee.append(p)     # rejected upstream (not adjacent)
        return melee, barrage

    def _fpf_eligible(self, def_side, dfd):
        """Artillery that may add FPF [8.41/8.42/8.46] + GSP eligibility."""
        s = self.s
        out = []
        board = self.rules_board()
        for u in self._live(def_side):
            p = u["pid"]
            if not self.is_arty(p) or p in s["fpf_used"]:
                continue
            if p in s["displaced_arty"]:
                continue
            adv = s["adverse"].get(p)
            if adv and (adv[0], adv[1]) in self._recent_phases():
                continue
            # adjacent to an enemy (except across a river) bars FPF [8.41]
            enemy = self.game.enemy(def_side)
            adjacent = False
            for e in self._live(enemy):
                pa, pb = (u["col"], u["row"]), (e["col"], e["row"])
                if pb in self.game.neighbors(*pa) and not self._river_side(pa, pb):
                    adjacent = True
                    break
            if adjacent:
                continue
            rng = self.stats(p).get("range", 0)
            targets = [d["pid"] for d in dfd
                       if self.game.hex_distance((u["col"], u["row"]),
                                                 (d["col"], d["row"])) <= rng]
            if targets:
                out.append({"pid": p, "slot": u["slot"], "fpf": self.stats(p)["fpf"],
                            "targets": targets})
        return out

    def _recent_phases(self):
        """(turn, mover) stamps counting as 'current or previous Combat Phase'
        for 8.41."""
        s = self.s
        cur = (s["turn"], s["mover"])
        order = self.game.side_order
        if s["mover"] == order[0]:
            prev = (s["turn"] - 1, order[1])
        else:
            prev = (s["turn"], order[0])
        return {tuple(cur), tuple(prev)}

    def _propose_fpf(self, side, action):
        p = self.s["pending"]
        if not p or p["awaiting"] != "fpf":
            return self._v(False, "no FPF allocation pending [8.4]")
        alloc = [(str(a), str(b)) for a, b in action.get("allocations", [])]
        elig = {e["pid"]: e for e in p["eligible"]}
        seen = set()
        for arty, target in alloc:
            if arty not in elig:
                return self._v(False, f"{arty} may not provide FPF [8.41/8.46]")
            if arty in seen:
                return self._v(False, "each artillery unit FPFs once [8.46]")
            seen.add(arty)
            if target not in elig[arty]["targets"]:
                return self._v(False, f"{target} is out of range for {arty} [8.42]")
        n_arty_def = len(alloc)
        if n_arty_def > 2:
            return self._v(False, "no more than two artillery per combat [14.12]")
        gsp = int(action.get("gsp", 0) or 0)
        if gsp:
            if side != "All":
                return self._v(False, "only the Allied player has GSP [14.11]")
            if gsp > self.s["gsp_left"]:
                return self._v(False, f"only {self.s['gsp_left']} GSP left [18.16]")
            dhexes = [ (self.unit(d)["col"], self.unit(d)["row"])
                       for d in p["def_ids"] if d in self.s["units"] ]
            if not self._gsp_ok_hexes(dhexes):
                return self._v(False, "GSP only within 3 hexes of an Allied "
                                      "non-airborne unit [14.11]")
        if p.get("pure_barrage") and (alloc or gsp):
            return self._v(False, "no FPF against an attack made solely by "
                                  "artillery/GSP [8.45]")
        return self._v(True, f"FPF: {len(alloc)} artillery + {gsp} GSP [8.4]")

    # ------------------------------------------------- retreats & advances
    def _surrounded(self, u):
        """11.2: all six adjacent hexes enemy-occupied or enemy-controlled."""
        board = self.rules_board(exclude_pid=u["pid"])
        enemy = self.game.enemy(u["side"])
        epos = {(b["col"], b["row"]) for b in board if b["side"] == enemy}
        ezoc = self.game.zoc_hexes(board, enemy)
        for nb in self.game.neighbors(u["col"], u["row"]):
            if not self.game.on_map(*nb):
                continue
            if nb not in epos and nb not in ezoc:
                return False
        return True

    def _city_benefit(self, pid, at_hex):
        """11.1/11.2: retreat reduction available? (occupying/entering a City;
        never airborne artillery; when surrounded only Allied airborne/glider)."""
        if self.cls(pid) == "ab_artillery":
            return False
        if self.game.hex_terrain(*at_hex) != "city":
            return False
        u = self.unit(pid)
        if self._surrounded(u):
            return u["side"] == "All" and self.is_airborne(pid) \
                and self.cls(pid) in ("para", "glider", "polish")
        return True

    def _retreat_distance_options(self, pid, n):
        """Legal total retreat distances for a unit under 11.1 (in-city at the
        start). Entering a city mid-path is handled in path validation."""
        u = self.unit(pid)
        opts = {n}
        if self._city_benefit(pid, (u["col"], u["row"])):
            mn = {3: 1, 4: 2}.get(n, 0)
            opts.add(max(n - 2, mn))
        return opts

    def _retreat_step_ok(self, pid, side, cur, nb, epos, ezoc):
        """One retreat step [7.71/7.72/5.24/13.25]."""
        if not self.game.on_map(*nb):
            return False
        if nb in epos or nb in ezoc:
            return False                       # 7.71 (friends do not negate)
        f = self.side_feat(cur, nb)
        if f.get("water") == "river" and side == "All":
            return False                       # 13.25: Allied never retreat across rivers
        if self.game.hexside_prohibited(cur, nb):
            return False                       # 7.72
        if self.is_vehicle(pid):
            water = f.get("water")
            roady = f.get("road") in ("road", "trail")
            if water in ("river", "stream") and not roady:
                return False                   # 5.24 (eliminated instead)
            if f.get("ferry") and not roady:
                return False
            if self.game.hex_terrain(*nb) in ("rough", "broken", "woods") and not roady:
                return False
        eng = self._engineer()
        if eng and side == "All" and cur == (eng["col"], eng["row"]) and pid != eng["pid"]:
            return False                       # 13.25: never retreat out of the Engineer hex
        return True

    def _retreat_paths_exist(self, pid, n, allow_friends):
        """Is any legal retreat path of exact length n with final distance n
        available? (BFS over (hex, steps); friends displace only when
        allow_friends.)"""
        u = self.unit(pid)
        side = u["side"]
        board = self.rules_board(exclude_pid=pid)
        enemy = self.game.enemy(side)
        epos = {(b["col"], b["row"]) for b in board if b["side"] == enemy}
        fpos = {(b["col"], b["row"]) for b in board if b["side"] == side}
        ezoc = self.game.zoc_hexes(board, enemy)
        start = (u["col"], u["row"])
        q = deque([(start, 0, (start,))])
        while q:
            cur, k, path = q.popleft()
            if k == n:
                if self.game.hex_distance(start, cur) == n and cur not in fpos:
                    return True
                continue
            for nb in self.game.neighbors(*cur):
                if nb in path:
                    continue
                if not self._retreat_step_ok(pid, side, cur, nb, epos, ezoc):
                    continue
                if nb in fpos and not allow_friends:
                    continue
                q.append((nb, k + 1, path + (nb,)))
        return False

    def _propose_retreat(self, side, action):
        s = self.s
        p = s["pending"]
        if not p or p["awaiting"] != "retreat":
            return self._v(False, "no retreat pending [7.7]")
        pid = str(action.get("unit"))
        if pid not in p["units"]:
            return self._v(False, f"{pid} is not among the retreating units")
        u = self.unit(pid)
        n = (p.get("distance_by") or {}).get(pid, p["distance"])   # displaced: 1 [7.81]
        opts = self._retreat_distance_options(pid, n)
        if action.get("eliminate"):
            mn = min(opts)
            if mn == 0:
                return self._v(False, "the city benefit reduces this retreat to "
                                      "no-effect - elimination needs no retreat [11.1]")
            if self._retreat_paths_exist(pid, mn, allow_friends=True):
                return self._v(False, f"a legal retreat of {mn} exists - elimination "
                                      f"only when none does [7.74]")
            return self._v(True, f"{u['slot']} cannot complete the retreat - "
                                 f"eliminated [7.74]"
                           + (" (vehicle class violation 5.24)" if self.is_vehicle(pid) else ""))
        path = [tuple(x) for x in action.get("path", [])]
        want = len(path)
        if action.get("city_reduce"):
            if want not in opts or want == n:
                return self._v(False, f"city reduction gives distances {sorted(opts)} [11.1]")
        elif want != n and want not in opts:
            return self._v(False, f"retreat must cover {n} hexes (city option: "
                                  f"{sorted(opts)}) [7.7/11.1]")
        if want == 0:
            if 0 not in opts:
                return self._v(False, "a zero retreat needs the city no-effect option [11.1]")
            return self._v(True, f"{u['slot']} stands - city benefit [11.1]")
        board = self.rules_board(exclude_pid=pid)
        enemy = self.game.enemy(u["side"])
        epos = {(b["col"], b["row"]) for b in board if b["side"] == enemy}
        fpos = {(b["col"], b["row"]) for b in board if b["side"] == u["side"]}
        ezoc = self.game.zoc_hexes(board, enemy)
        cur = (u["col"], u["row"])
        seen = {cur}
        uses_friends = False
        for i, nb in enumerate(path):
            if nb in seen:
                return self._v(False, "retreat may not revisit a hex [7.7]")
            if nb not in self.game.neighbors(*cur):
                return self._v(False, f"step {i + 1}: {nb} is not adjacent")
            if not self._retreat_step_ok(pid, u["side"], cur, nb, epos, ezoc):
                return self._v(False, f"step {i + 1}: illegal retreat step "
                                      f"[7.71/7.72/5.24/13.25]")
            if nb in fpos:
                uses_friends = True
            seen.add(nb)
            cur = nb
        if self.game.hex_distance((u["col"], u["row"]), cur) != want:
            return self._v(False, f"retreat must END {want} hexes away from the "
                                  f"combat position [7.74]")
        if uses_friends and self._retreat_paths_exist(pid, want, allow_friends=False):
            return self._v(False, "displacement only when no vacant route exists [7.73]")
        if want > 0 and path and action.get("city_reduce"):
            pass                               # already validated via opts
        return self._v(True, f"{u['slot']} retreats {want} to {cur}"
                             + (" displacing" if uses_friends else "") + " [7.7]")

    def _propose_advance(self, side, action):
        s = self.s
        p = s["pending"]
        if not p or p["awaiting"] != "advance":
            return self._v(False, "no advance pending [7.9]")
        if action.get("decline") or action.get("unit") is None:
            return self._v(True, "advance declined [7.96: never forced]")
        pid = str(action.get("unit"))
        if pid not in p["units"]:
            return self._v(False, "only victorious adjacent participants advance "
                                  "[7.91/7.94]")
        if pid in s["advanced"]:
            return self._v(False, f"{pid} already advanced")
        dest = tuple(action.get("dest") or action.get("hex") or ())
        path = [tuple(h) for h in p["path"]]
        if dest not in path:
            return self._v(False, f"advance only along the Path of Retreat {p['path']} "
                                  f"[7.95]")
        u = self.unit(pid)
        occupied = self._positions(dz=False)
        cur = (u["col"], u["row"])
        # walk the path from its head to dest; every hex en route must be
        # empty; hexside legality per this unit (5.24/13.25)
        for h in path:
            if h in occupied and h != dest:
                return self._v(False, f"path hex {h} is occupied [5.31]")
            step_from = cur
            if h not in self.game.neighbors(*step_from):
                return self._v(False, f"{u['slot']} cannot reach {h} along the path")
            f = self.side_feat(step_from, h)
            if u["side"] == "Ger" and f.get("water") == "river":
                return self._v(False, "German units never advance across a river "
                                      "hexside [13.25]")
            if self.game.hexside_prohibited(step_from, h) and pid not in s["assault"]:
                return self._v(False, "no advance across a prohibited hexside")
            if self.is_vehicle(pid):
                water = f.get("water")
                roady = f.get("road") in ("road", "trail")
                if (water in ("river", "stream") and not roady) or \
                   (self.game.hex_terrain(*h) in ("rough", "broken", "woods") and not roady):
                    return self._v(False, f"vehicle class cannot advance into/across "
                                          f"{h} [5.24]")
            if h == dest:
                if dest in occupied:
                    return self._v(False, f"{dest} is occupied [5.31]")
                return self._v(True, f"{u['slot']} advances to {dest} [7.9]")
            cur = h
        return self._v(False, "destination beyond the path")

    def _retreat_path_options(self, pid, n):
        """Legal retreat paths of exact length n, one per distinct endpoint
        (vacant routes first; displacement routes only when no vacant route
        reaches any endpoint, 7.73). UI surface."""
        u = self.unit(pid)
        side = u["side"]
        board = self.rules_board(exclude_pid=pid)
        enemy = self.game.enemy(side)
        epos = {(b["col"], b["row"]) for b in board if b["side"] == enemy}
        fpos = {(b["col"], b["row"]) for b in board if b["side"] == side}
        ezoc = self.game.zoc_hexes(board, enemy)
        origin = (u["col"], u["row"])

        def search(allow_friends):
            found = {}
            stack = [(origin, ())]
            while stack:
                cur, path = stack.pop()
                if len(path) == n:
                    if cur not in fpos and cur not in found \
                       and self.game.hex_distance(origin, cur) == n:
                        found[cur] = list(path)
                    continue
                for nb in sorted(self.game.neighbors(*cur)):
                    if nb in path or nb == origin:
                        continue
                    if not self._retreat_step_ok(pid, side, cur, nb, epos, ezoc):
                        continue
                    if nb in fpos and not allow_friends:
                        continue
                    stack.append((nb, path + (nb,)))
            return found

        found = search(False)
        if not found:
            found = search(True)
        return [found[k] for k in sorted(found)]

    def _propose_end_phase(self, side):
        s = self.s
        if s["phase"] != "combat":
            return self._v(False, "end_phase ends the Combat Phase - use end_movement")
        if s["pending"]:
            return self._v(False, "resolve the pending step first")
        if self.combat:
            mine, theirs = self._contacts(side)
            un_att = [p for p in sorted(theirs) if p not in s["defended"]]
            if un_att:
                names = ", ".join(self.unit(p)["slot"] for p in un_att[:4])
                return self._v(False, f"every enemy unit in contact must be attacked: "
                                      f"{names} [7.11]")
            un_assault = [p for p in s["assault"]
                          if p in s["units"] and p not in s["fought"]
                          and self.unit(p)["side"] == side]
            if un_assault:
                names = ", ".join(self.cat(p)["desig"] for p in un_assault)
                return self._v(False, f"the Engineer assault stack must attack "
                                      f"across the river: {names} [13.24]")
            # 7.12's "all adjacent friendly units participate" is enforced at
            # battle time (_mandatory_joiners): a battle must include every
            # unfought friendly whose obligations it covers. At closure every
            # contacted ENEMY is attacked (7.11 above); an unfought friendly
            # left here has only already-attacked neighbors - 7.14 (one attack
            # per enemy per phase) makes attacking impossible, so it is excused.
        return self._v(True, "combat phase complete [4.1]")

    # ------------------------------------------------------------ submit
    def submit(self, side, action):
        verdict = self.propose(side, action)
        entry = {"event": "action", "turn": self.s["turn"], "phase": self.s["phase"],
                 "side": side, "action": action, "verdict": verdict}
        if not verdict["legal"]:
            self._log(entry)
            self.save()
            return {"verdict": verdict}
        result = self._apply(side, action)
        entry["result"] = result
        self._log(entry)
        self.save()
        return {"verdict": verdict, "result": result}

    # ------------------------------------------------------------ apply
    def _apply(self, side, action):
        s = self.s
        t = action["type"]
        ev = []
        if t == "move":
            pid = str(action["unit"])
            u = self.unit(pid)
            dest = tuple(action["dest"])
            dd = self.dests(pid)
            u["col"], u["row"] = dest
            s["moved"][pid] = s["moved"].get(pid, 0) + dd[dest]
            s["done"].append(pid)
            if self.cls(pid) == "engineer":
                s["eng_lock"] = "moved"
            eng = self._engineer()
            if eng and pid != eng["pid"] and dest == (eng["col"], eng["row"]):
                s["assault"].append(pid)       # 13.24 assault stack formed
                s["eng_lock"] = "crossed"
                ev.append({"assault_stack": u["slot"], "note": "must attack across "
                           "the river this Combat Phase [13.24]"})
            # crossing through the Engineer's hex locks it [13.21] - detect by
            # river-arc use: conservative: any Allied airborne/glider move that
            # ends across a river from where a plain path could not go is rare;
            # the lock is set whenever the move used a crossing arc:
            ev.append({"move": u["slot"], "to": list(dest), "mp": dd[dest]})
            if side == "All":
                ev = self._offer_demolition([dest], ev)
        elif t == "reinforce":
            pid = str(action["unit"])
            e = self.reserve[pid]
            h = tuple(action["hex"])
            s["units"][pid] = {"pid": pid, "slot": e["slot"], "side": side,
                               "col": h[0], "row": h[1]}
            s["pool"].pop(pid, None)
            if e.get("arrival") == "airborne":
                s["arrived"][pid] = s["turn"]
                s["drops"].append(list(h))
                ev.append({"drop": e["slot"], "at": list(h), "ma": 3})
            else:
                key = f"{h[0]:02d}{h[1]:02d}"
                cost = self._entry_cost(e, h, s["entered"].get(key, 0))
                s["entered"][key] = s["entered"].get(key, 0) + 1
                s["moved"][pid] = cost
                ev.append({"reinforce": e["slot"], "at": list(h), "column_mp": cost})
            if side == "All":
                ev = self._offer_demolition([h], ev)
        elif t == "exit":
            pid = str(action["unit"])
            u = self.unit(pid)
            edges = self.game.spec["exit"]["german_edges"]
            pos = (u["col"], u["row"])
            edge = next(nm for nm, (a, b) in edges.items()
                        if pos in self._edge_hexes(a, b))
            s["exited"][pid] = edge
            # 15.42: available again on any subsequent GT on the same edge
            self.reserve[pid] = dict(self.cat(pid), arrival="edge",
                                     entry=[list(h) for h in sorted(self._edge_hexes(
                                         *edges[edge]))])
            s["pool"][pid] = s["turn"] + 1
            del s["units"][pid]
            ev.append({"exit": u["slot"], "edge": edge, "reenter_from": s["turn"] + 1})
        elif t == "demolition":
            ev += self._apply_demolition(action)
        elif t == "end_movement":
            ev += self._begin_combat_phase(side)
        elif t == "battle":
            ev += self._apply_battle(side, action)
        elif t == "fpf":
            ev += self._apply_fpf(side, action)
        elif t == "retreat":
            ev += self._apply_retreat(side, action)
        elif t == "advance":
            ev += self._apply_advance(side, action)
        elif t == "end_phase":
            ev += self._end_player_turn(side)
        return ev

    def _apply_demolition(self, action):
        s = self.s
        p = s["pending"]
        ev = []
        for key in p["bridges"]:
            if action.get("attempt", {}).get(key):
                die = self.roll_die()
                if die <= 2:
                    s["demolished"].append(key)
                    ev.append({"demolition": key, "die": die, "result": "DEMOLISHED",
                               "cite": "[12.12]"})
                else:
                    ev.append({"demolition": key, "die": die,
                               "result": "intact for the rest of the game [12.14]"})
            else:
                ev.append({"demolition": key, "result": "declined - chance forfeited "
                           "[12.11]"})
        s["pending"] = p.get("resume")
        self._apply_bridge_state()
        return ev

    def _begin_combat_phase(self, side):
        s = self.s
        s["phase"] = "combat"
        s["fought"], s["defended"], s["advanced"] = [], [], []
        s["displaced_arty"] = []
        return [{"combat_phase": side}]

    # ------------------------------------------------------------ battles
    def _apply_battle(self, side, action):
        s = self.s
        atk_ids = [str(p) for p in action["attackers"]]
        def_ids = [str(p) for p in action["defenders"]]
        gsp = int(action.get("gsp", 0) or 0)
        dfd = [self.unit(p) for p in def_ids]
        melee, barrage = self._split_attackers(atk_ids, dfd)
        pure = not melee
        def_side = self.game.enemy(side)
        elig = [] if pure else self._fpf_eligible(def_side, dfd)
        gsp_def_possible = (def_side == "All" and s["gsp_left"] > 0 and not pure)
        s["battle_no"] += 1
        battle = {"no": s["battle_no"], "attackers": atk_ids, "defenders": def_ids,
                  "melee": melee, "barrage": barrage, "gsp_att": gsp,
                  "pure_barrage": pure}
        if gsp:
            s["gsp_left"] -= gsp
        if elig or gsp_def_possible:
            s["pending"] = {"awaiting": "fpf", "by": def_side, "battle": battle,
                            "eligible": elig, "def_ids": def_ids,
                            "pure_barrage": pure}
            return [{"battle_declared": s["battle_no"],
                     "fpf_offer": [e["slot"] for e in elig],
                     "gsp_available": s["gsp_left"] if gsp_def_possible else 0}]
        return self._resolve_battle(side, battle, [], 0)

    def _apply_fpf(self, side, action):
        s = self.s
        p = s["pending"]
        alloc = [(str(a), str(b)) for a, b in action.get("allocations", [])]
        gsp = int(action.get("gsp", 0) or 0)
        if gsp:
            s["gsp_left"] -= gsp
        for arty, _tgt in alloc:
            s["fpf_used"].append(arty)
        battle = p["battle"]
        s["pending"] = None
        att_side = self.game.enemy(side)
        return self._resolve_battle(att_side, battle, alloc, gsp)

    def _resolve_battle(self, side, battle, fpf_alloc, gsp_def):
        s = self.s
        atk_ids, def_ids = battle["attackers"], battle["defenders"]
        melee, barrage = battle["melee"], battle["barrage"]
        atk = [self.unit(p) for p in atk_ids if p in s["units"]]
        dfd = [self.unit(p) for p in def_ids if p in s["units"]]
        a_str = 0
        for p in atk_ids:
            st = self.stats(p)
            a_str += st.get("barrage", st["att"]) if self.is_arty(p) else st["att"]
        a_str += battle["gsp_att"]
        d_str = sum(self.stats(p)["def"] for p in def_ids)
        d_str += sum(self.stats(a)["fpf"] for a, _t in fpf_alloc) + gsp_def
        diff = a_str - d_str
        # terrain row: 13.24 assault resolves on the Stream line [13.24]
        melee_units = [self.unit(p) for p in melee if p in s["units"]]
        if any(p in s["assault"] for p in melee):
            row = "broken"                     # Stream shares the Broken row [7.61]
        else:
            row = self._terrain_row(dfd, melee_units)
        die = self.roll_die()
        res, col = self.crt_result(row, diff, die)
        bno = battle["no"]
        for p in atk_ids:
            s["fought"].append(p)
        for p in def_ids:
            s["defended"].append(p)
        ev = [{"battle": bno, "differential": diff, "row": row, "column": col,
               "die": die, "result": res,
               "attackers": [self.cat(p)["desig"] for p in atk_ids],
               "defenders": [self.cat(p)["desig"] for p in def_ids],
               "barraging": [self.cat(p)["desig"] for p in barrage],
               "fpf": [[self.cat(a)["desig"], self.cat(t)["desig"]] for a, t in fpf_alloc],
               "gsp": [battle["gsp_att"], gsp_def]}]
        # 8.15: solely artillery/GSP - only D2/D3/D4/De affect the defender
        if battle["pure_barrage"] and res not in ("D2", "D3", "D4", "De"):
            ev.append({"no_effect": res, "cite": "[8.15] pure barrage: only "
                       "D2/D3/D4/De apply"})
            self._after_battle_assault_check(ev, battle, advanced_into=None)
            return ev
        d_hexes = sorted({(d["col"], d["row"]) for d in dfd})
        a_hexes = sorted({(self.unit(p)["col"], self.unit(p)["row"])
                          for p in melee if p in s["units"]})
        if res == "De":
            ev += self._eliminate(def_ids, f"De [7.62] battle {bno}")
            ev += self._offer_advance(side, [p for p in melee], d_hexes, bno,
                                      battle)
        elif res == "Ae":
            victims = list(melee)              # 8.14 barraging artillery immune
            ev += self._eliminate(victims, f"Ae [7.62] battle {bno}")
            ev += self._offer_advance(self.game.enemy(side), def_ids, a_hexes, bno,
                                      battle)
            self._mark_adverse(melee + def_ids, attackers_only=melee)
        elif res in ("D1", "D2", "D3", "D4"):
            n = int(res[1])
            self._mark_adverse(def_ids, attackers_only=[])
            s["pending"] = {"awaiting": "retreat", "by": self.game.enemy(side),
                            "units": [p for p in def_ids if p in s["units"]],
                            "distance": n, "battle": bno, "adv_by": side,
                            "adv_units": list(melee), "paths": {}, "battle_ctx": battle}
            ev.append({"defender_retreats": n})
        elif res in ("A1", "A2"):
            n = int(res[1])
            self._mark_adverse(melee, attackers_only=[])
            live_melee = [p for p in melee if p in s["units"]]
            if live_melee:
                s["pending"] = {"awaiting": "retreat", "by": side,
                                "units": live_melee, "distance": n, "battle": bno,
                                "adv_by": None, "adv_units": [], "paths": {},
                                "battle_ctx": battle}
                ev.append({"attacker_retreats": n})
            else:
                ev.append({"attacker_retreats": 0, "note": "barrage only [8.14]"})
        elif res == "Br":
            self._mark_adverse(def_ids + melee, attackers_only=[])
            # defender first [7.62]; then the attackers; no advances (all
            # involved units are themselves retreating)
            s["pending"] = {"awaiting": "retreat", "by": self.game.enemy(side),
                            "units": [p for p in def_ids if p in s["units"]],
                            "distance": 1, "battle": bno, "adv_by": None,
                            "adv_units": [], "paths": {},
                            "then_attacker": [p for p in melee if p in s["units"]],
                            "then_by": side, "battle_ctx": battle}
            ev.append({"both_retreat": 1, "defender_first": True})
        if res in ("De", "D1", "D2", "D3", "D4") or res in ("Ae",):
            pass
        return ev

    def _mark_adverse(self, pids, attackers_only):
        """8.41 bookkeeping: artillery that suffered an adverse result."""
        stamp = [self.s["turn"], self.s["mover"]]
        for p in pids:
            if self.is_arty(p):
                self.s["adverse"][p] = stamp

    def _eliminate(self, pids, why):
        s = self.s
        ev = []
        for p in pids:
            if p not in s["units"]:
                continue
            u = self.unit(p)
            enemy = self.game.enemy(u["side"])
            if u["side"] == "All":
                s["vp"]["Ger"] += self.vp_cfg.get("german_per_allied_unit_destroyed", 5)
            else:
                s["vp"]["All"] += self.vp_cfg.get("allied_per_german_unit_eliminated", 1)
            s["dead"].append(p)
            if p in s["assault"]:
                s["assault"].remove(p)
            del s["units"][p]
            ev.append({"eliminated": self.cat(p)["desig"], "why": why,
                       "vp_to": enemy})
            # 13.3: the Engineer is replaced - re-enters at 0105/0106 next turn
            if self.cls(p) == "engineer":
                s["dead"].remove(p)
                self.reserve[p] = dict(self.cat(p), arrival="column",
                                       entry=[[1, 5], [1, 6]])
                s["pool"][p] = s["turn"] + 1
                ev.append({"engineer_replacement": s["turn"] + 1, "cite": "[13.3]"})
        return ev

    def _offer_advance(self, by, unit_ids, path_hexes, bno, battle):
        """7.9x: victorious adjacent participants may advance along the Path
        of Retreat (here: the vacated hexes, ordered nearest-first)."""
        s = self.s
        cands = [p for p in unit_ids if p in s["units"] and p not in s["advanced"]]
        if not cands or not path_hexes:
            self._after_battle_assault_check([], battle, advanced_into=None)
            return []
        s["pending"] = {"awaiting": "advance", "by": by, "units": cands,
                        "path": [list(h) for h in path_hexes], "battle": bno,
                        "battle_ctx": battle}
        return [{"advance_offered": by, "path": [list(h) for h in path_hexes]}]

    def _after_battle_assault_check(self, ev, battle, advanced_into):
        """13.24: an assault unit unable to advance across the river hexside
        after its combat is immediately eliminated."""
        s = self.s
        for p in list(s["assault"]):
            if p in battle.get("melee", []) and p in s["units"]:
                u = self.unit(p)
                eng = self._engineer()
                still_stacked = eng and (u["col"], u["row"]) == (eng["col"], eng["row"])
                if still_stacked:
                    ev += self._eliminate([p], "13.24: unable to advance across "
                                               "the river after the assault")
                else:
                    s["assault"].remove(p)
        return ev

    def _apply_retreat(self, side, action):
        s = self.s
        p = s["pending"]
        pid = str(action["unit"])
        u = self.unit(pid)
        ev = []
        origin = (u["col"], u["row"])
        if action.get("eliminate"):
            ev += self._eliminate([pid], "no legal retreat [7.74]")
            vacated = [origin]
        else:
            path = [tuple(x) for x in action.get("path", [])]
            fpos = {(v["col"], v["row"]): v for v in self.s["units"].values()
                    if v["pid"] != pid and v["side"] == u["side"]
                    and self.cls(v["pid"]) != "dz"}
            # displacement [7.8]: each friend on the path retreats one hex
            for h in path:
                friend = fpos.get(h)
                if friend:
                    ev.append({"displaced": friend["slot"], "by": u["slot"]})
                    if self.is_arty(friend["pid"]):
                        s["displaced_arty"].append(friend["pid"])
                    p.setdefault("displace_queue", []).append(friend["pid"])
            if path:
                u["col"], u["row"] = path[-1]
            vacated = [origin] + [h for h in path[:-1]]
            ev.append({"retreat": u["slot"], "to": list(path[-1]) if path else
                       list(origin), "hexes": len(path)})
            if u["side"] == "All":
                ev = self._offer_demolition(path, ev)
        p["units"].remove(pid)
        p.setdefault("vacated", []).extend([list(h) for h in vacated])
        # displaced friends retreat 1 as pendings of the same owner [7.81]
        dq = p.get("displace_queue") or []
        if dq:
            p["units"].extend([x for x in dq if x in s["units"] and x not in p["units"]])
            p["displace_queue"] = []
            p["distance_by"] = p.get("distance_by", {})
            for x in dq:
                p["distance_by"][x] = 1
        if pid in (p.get("distance_by") or {}):
            del p["distance_by"][pid]
        if not p["units"]:
            then_atk = p.get("then_attacker")
            if then_atk:
                live = [x for x in then_atk if x in s["units"]]
                if live:
                    s["pending"] = {"awaiting": "retreat", "by": p["then_by"],
                                    "units": live, "distance": 1,
                                    "battle": p["battle"], "adv_by": None,
                                    "adv_units": [], "paths": {},
                                    "battle_ctx": p.get("battle_ctx", {})}
                    ev.append({"attacker_retreats": 1, "after": "defender [7.62 Br]"})
                    return ev
            adv_by, adv_units = p.get("adv_by"), p.get("adv_units", [])
            battle = p.get("battle_ctx", {})
            s["pending"] = None
            occupied = self._positions(dz=False)
            vac = [h for h in p.get("vacated", []) if tuple(h) not in occupied]
            if adv_by and vac:
                ev += self._offer_advance(adv_by, adv_units, [tuple(h) for h in vac],
                                          p["battle"], battle)
            else:
                self._after_battle_assault_check(ev, battle, advanced_into=None)
        return ev

    def _apply_advance(self, side, action):
        s = self.s
        p = s["pending"]
        ev = []
        battle = p.get("battle_ctx", {})
        if action.get("decline") or action.get("unit") is None:
            ev.append({"advance": "declined"})
            s["pending"] = None
            self._after_battle_assault_check(ev, battle, advanced_into=None)
            return ev
        pid = str(action["unit"])
        u = self.unit(pid)
        dest = tuple(action.get("dest") or action.get("hex"))
        u["col"], u["row"] = dest
        s["advanced"].append(pid)
        if pid in s["assault"]:
            s["assault"].remove(pid)           # 13.24 satisfied by the advance
        ev.append({"advance": u["slot"], "to": list(dest)})
        if u["side"] == "All":
            ev = self._offer_demolition([dest], ev)
        # further advances may follow along the remaining path [7.97]
        remaining = [x for x in p["units"] if x != pid and x in s["units"]
                     and x not in s["advanced"]]
        occupied = self._positions(dz=False)
        open_path = [h for h in p["path"] if tuple(h) not in occupied]
        if remaining and open_path and not s["pending"]:
            s["pending"] = {"awaiting": "advance", "by": p["by"], "units": remaining,
                            "path": open_path, "battle": p["battle"],
                            "battle_ctx": battle}
        elif not s["pending"]:
            s["pending"] = None
            self._after_battle_assault_check(ev, battle, advanced_into=dest)
        return ev

    # ------------------------------------------------------------ turn flow
    def _end_player_turn(self, side):
        s = self.s
        ev = []
        # 13.24: assault units that never attacked are handled by the 7.12
        # closure (they were forced to attack); clear stray flags
        if side == "Ger":
            ev += self._german_turn_end_scoring()
        order = self.game.side_order
        s["phase"] = "movement"
        s["moved"], s["done"] = {}, []
        s["entered"], s["drops"] = {}, []
        s["fought"], s["defended"], s["advanced"] = [], [], []
        s["displaced_arty"] = []
        s["eng_lock"] = None
        s["pending"] = None
        if s["mover"] == order[0]:
            s["mover"] = order[1]
            eng = self._engineer()
            s["eng_start"] = [eng["col"], eng["row"]] if eng else None
            ev.append({"player_turn": s["mover"]})
        else:
            s["turn"] += 1
            s["mover"] = order[0]
            s["fpf_used"] = []
            if s["turn"] > self.turns:
                ev += self._final_scoring()
            else:
                s["gsp_left"] = self.gsp_sched.get(s["turn"], 0)
                ev.append({"game_turn": s["turn"], "label": self.turn_label(),
                           "gsp": s["gsp_left"]})
        return ev

    def _german_turn_end_scoring(self):
        """End of the German player-turn = end of the GT for scoring: LOC
        checks [17.35], Waal-zone VP [17.11], Engineer canal repair [13.1]."""
        s = self.s
        ev = []
        # Engineer repair: stationary through the German player-turn, adjacent
        # to a demolished canal bridge, EZOC-free at both ends [13.1]
        eng = self._engineer()
        if eng and s.get("eng_start") == [eng["col"], eng["row"]]:
            board = self.rules_board(exclude_pid=eng["pid"])
            if (eng["col"], eng["row"]) not in self.game.zoc_hexes(board, "Ger"):
                pos = (eng["col"], eng["row"])
                for key in list(s["demolished"]):
                    if key in s["repaired"]:
                        continue
                    if self._pristine[key].get("bridge_type") != "canal":
                        continue                # 12.16: railroad bridges never repaired
                    hexes = self._bridge_hexes(key)
                    if pos in hexes or any(h in self.game.neighbors(*pos)
                                           for h in hexes):
                        s["repaired"].append(key)
                        ev.append({"bridge_repaired": key, "cite": "[13.1]"})
                self._apply_bridge_state()
        # LOC + zone VP
        loc = self._loc_status()
        fails = [p for p, ok in loc.items() if not ok]
        if fails:
            pts = len(fails) * self.vp_cfg.get("german_per_loc_fail_per_turn", 3)
            s["vp"]["Ger"] += pts
            ev.append({"loc_failures": [self.cat(p)["desig"] for p in fails],
                       "german_vp": pts, "cite": "[17.35]"})
        waal = [u["pid"] for u in self._live("All")
                if not self.is_airborne(u["pid"])
                and f"{u['col']:02d}{u['row']:02d}" in self.waal_zone
                and loc.get(u["pid"], False)]
        if waal:
            pts = len(waal) * self.vp_cfg.get("waal_per_unit_per_turn", 5)
            s["vp"]["All"] += pts
            ev.append({"north_of_waal": [self.cat(p)["desig"] for p in waal],
                       "allied_vp": pts, "cite": "[17.11]"})
        return ev

    def _loc_status(self):
        """pid -> LOC ok, for every Allied unit subject to 17.3 (Polish and
        DZ excluded [17.36])."""
        out = {}
        board = self.rules_board()
        gzoc = self.game.zoc_hexes(board, "Ger")
        apos = self._positions("All")
        gpos = self._positions("Ger")
        blocked = {h for h in gzoc if h not in apos} | gpos   # 17.33
        dz_pos = {self.cat(u["pid"]).get("desig", "").split()[0]: (u["col"], u["row"])
                  for u in self._live("All", dz=True) if self.cls(u["pid"]) == "dz"}
        exits = {tuple(h) for h in self.loc_cfg.get("ground_exit", [[1, 5], [1, 6]])}
        ground_ok = self._ground_loc_set(blocked, exits)
        for u in self._live("All"):
            pid = u["pid"]
            if self.cls(pid) in ("polish",):
                continue                        # 17.36
            pos = (u["col"], u["row"])
            if self.is_airborne(pid):
                div = self.cat(pid).get("division")
                tgt = dz_pos.get(div)
                out[pid] = bool(tgt) and self._airborne_loc(pos, tgt, blocked)
            else:
                out[pid] = pos in ground_ok
        return out

    def _side_water_block(self, a, b):
        f = self.side_feat(a, b)
        return f.get("water") in ("river", "stream") and not f.get("bridge")

    def _ground_loc_set(self, blocked, exits):
        """Hexes with a ground LOC to 0105/0106 [17.31]: BFS from the exit
        hexes with the road-locking automaton run in reverse (from the edge
        toward the units the mode can only tighten: road -> road hexsides
        only; trail -> road/trail hexsides; free until a road/trail hex is
        entered). 17.34 bars unbridged river/stream hexsides throughout."""
        def hex_mode(h):
            for nb in self.game.neighbors(*h):
                f = self.side_feat(h, nb)
                if f.get("road") == "road":
                    return "road"
            for nb in self.game.neighbors(*h):
                if self.side_feat(h, nb).get("road") == "trail":
                    return "trail"
            return "free"
        ok = set()
        seen = set()
        q = deque()
        for e in exits:
            if e in blocked:
                continue
            m = hex_mode(e)
            q.append((e, m))
            seen.add((e, m))
        while q:
            cur, mode = q.popleft()
            ok.add(cur)
            for nb in self.game.neighbors(*cur):
                if not self.game.on_map(*nb) or nb in blocked:
                    continue
                if self._side_water_block(cur, nb):
                    continue                    # 17.34
                f = self.side_feat(cur, nb)
                if mode == "road" and f.get("road") != "road":
                    continue
                if mode == "trail" and f.get("road") not in ("road", "trail"):
                    continue
                nm = hex_mode(nb)
                # once on the road net, stay on it toward the unit as well
                nmode = mode if mode != "free" else ("road" if nm == "road" else
                                                     ("trail" if nm == "trail" else "free"))
                if (nb, nmode) not in seen:
                    seen.add((nb, nmode))
                    q.append((nb, nmode))
        return ok

    def _airborne_loc(self, pos, tgt, blocked):
        """<=7 hexes to the divisional DZ, any terrain, 17.33/17.34 blocks."""
        if pos == tgt:
            return True
        seen = {pos}
        q = deque([(pos, 0)])
        while q:
            cur, d = q.popleft()
            if d >= self.loc_cfg.get("airborne_max", 7):
                continue
            for nb in self.game.neighbors(*cur):
                if nb in seen or not self.game.on_map(*nb):
                    continue
                if self._side_water_block(cur, nb):
                    continue
                if nb == tgt:
                    return True
                if nb in blocked:
                    continue
                seen.add(nb)
                q.append((nb, d + 1))
        return False

    def _final_scoring(self):
        s = self.s
        ev = [{"game_end": self.turns}]
        loc = self._loc_status()
        rijn = [u["pid"] for u in self._live("All")
                if not self.is_airborne(u["pid"])
                and f"{u['col']:02d}{u['row']:02d}" in self.rijn_zone
                and loc.get(u["pid"], False)]
        if rijn:
            pts = len(rijn) * self.vp_cfg.get("rijn_per_unit_end", 10)
            s["vp"]["All"] += pts
            ev.append({"north_of_rijn": [self.cat(p)["desig"] for p in rijn],
                       "allied_vp": pts, "cite": "[17.11]"})
        g, a = s["vp"]["Ger"], s["vp"]["All"]
        if a == 0 and g == 0:
            level = "Draw"
        elif a == 0:
            level = "German Strategic"
        else:
            r = g / a
            level = ("German Strategic" if r >= 3.0 else
                     "German Tactical" if r > 2.0 else
                     "Draw" if abs(r - 2.0) < 1e-9 else
                     "Allied Tactical" if r > 1.0 else "Allied Strategic")
        s["over"] = True
        s["level"] = level
        s["winner"] = ("Ger" if level.startswith("German")
                       else "All" if level.startswith("Allied") else "draw")
        ev.append({"final_vp": dict(s["vp"]), "ratio_german_to_allied":
                   None if a == 0 else round(g / a, 2), "level": level,
                   "winner": s["winner"], "cite": "[17.4]"})
        return ev

    # ------------------------------------------------------------ UI surface
    @property
    def schedule(self):
        return self.reserve

    def dests_map(self, u):
        return self.dests(u["pid"] if isinstance(u, dict) else u)

    def legal_moves(self, pid):
        pid = str(pid)
        if pid not in self.s["units"]:
            return {"can_act": False, "reasons": ["unit is not on the map"], "dests": []}
        u = self.unit(pid)
        s = self.s
        if s["over"]:
            return {"can_act": False, "reasons": ["game is over [17.0]"], "dests": []}
        if s["phase"] != "movement":
            return {"can_act": False,
                    "reasons": ["movement only in the Movement Phase [5.11]"], "dests": []}
        if u["side"] != s["mover"]:
            return {"can_act": False,
                    "reasons": [f"not {u['side']}'s player-turn [4.1]"], "dests": []}
        if pid in s["done"]:
            return {"can_act": False,
                    "reasons": [f"{u['slot']} has already moved this phase [5.15]"],
                    "dests": []}
        out = {"can_act": True, "reasons": [], "budget": self.budget(pid), "dests": []}
        for (c, r), cost in sorted(self.dests(pid).items()):
            x, y = self.game.grid.hex_to_pixel(c, r)
            out["dests"].append(dict(col=c, row=r, x=x, y=y, cost=round(cost, 1),
                                     hexnum=self.game.grid.hexnum(c, r),
                                     terrain=self.game.hex_terrain(c, r)))
        return out

    def battle_preview(self, side, atk_ids, def_ids, bomb_ids=None):
        atk_ids = [str(p) for p in atk_ids]
        def_ids = [str(p) for p in def_ids]
        chk = self.propose(side, {"type": "battle", "attackers": atk_ids,
                                  "defenders": def_ids})
        try:
            dfd = [self.unit(p) for p in def_ids]
            melee, barrage = self._split_attackers(atk_ids, dfd)
            a = 0
            for p in atk_ids:
                st = self.stats(p)
                a += st.get("barrage", st["att"]) if self.is_arty(p) else st["att"]
            d = sum(self.stats(p)["def"] for p in def_ids)
            melee_units = [self.unit(p) for p in melee]
            row = self._terrain_row(dfd, melee_units)
            return {"odds": f"{a - d:+d} ({row})", "differential": a - d, "row": row,
                    "column": self._column_pos(row, a - d),
                    "factors": [a, d], "legal": chk["legal"], "reasons": chk["reasons"],
                    "needs_supply": False, "bombarding": barrage}
        except KeyError:
            return {"odds": None, "legal": False, "reasons": chk["reasons"],
                    "needs_supply": False}

    def _pending_view(self):
        p = self.s["pending"]
        if not p:
            return None
        if p["awaiting"] == "demolition":
            return {"kind": "demolition", "chooser": p["by"],
                    "bridges": p["bridges"],
                    "note": "die 1-2 demolishes; declining forfeits the attempt [12.1]"}
        if p["awaiting"] == "fpf":
            return {"kind": "fpf", "chooser": p["by"],
                    "eligible": p["eligible"],
                    "gsp_left": self.s["gsp_left"] if p["by"] == "All" else 0,
                    "pure_barrage": p.get("pure_barrage", False)}
        if p["awaiting"] == "retreat":
            units = []
            for pid in p["units"]:
                if pid not in self.s["units"]:
                    continue
                n = (p.get("distance_by") or {}).get(pid, p["distance"])
                opts = self._retreat_distance_options(pid, n)
                options = []
                for want in sorted(opts, reverse=True):
                    if want == 0:
                        options.append({"path": [], "city_reduce": True,
                                        "name": "stand (city) [11.1]"})
                        continue
                    for path in self._retreat_path_options(pid, want)[:6]:
                        o = {"path": [list(h) for h in path],
                             "name": self.game.grid.hexnum(*path[-1])
                             + (f" ({want})" if want != n else "")}
                        if want != n:
                            o["city_reduce"] = True
                        options.append(o)
                units.append({"pid": pid, "slot": self.unit(pid)["slot"],
                              "distance": n, "city_options": sorted(opts),
                              "options": options})
            return {"kind": "retreat", "chooser": p["by"], "units": units}
        if p["awaiting"] == "advance":
            return {"kind": "advance", "chooser": p["by"], "can_decline": True,
                    "advancers": [{"pid": x, "slot": self.unit(x)["slot"]}
                                  for x in p["units"] if x in self.s["units"]],
                    "hexes": p["path"],
                    "hex_names": [self.game.grid.hexnum(*h) for h in p["path"]]}
        return dict(p)

    def flow(self):
        s = self.s
        due = sorted([{"pid": pid, "slot": self.reserve[pid]["slot"],
                       "side": self.reserve[pid]["side"], "due": d,
                       "arrival": self.reserve[pid].get("arrival"),
                       "entry": self.reserve[pid].get("entry"),
                       "target": self.reserve[pid].get("target")}
                      for pid, d in s["pool"].items() if d <= s["turn"]
                      and self.reserve[pid]["side"] == s["mover"]],
                     key=lambda e: e["pid"])
        must_attack, must_be = [], []
        if self.combat and not s["over"] and s["phase"] == "combat":
            mine, theirs = self._contacts(s["mover"])
            must_attack = [{"pid": p, "slot": self.unit(p)["slot"]}
                           for p in sorted(mine) if p not in s["fought"]]
            must_be = [{"pid": p, "slot": self.unit(p)["slot"]}
                       for p in sorted(theirs) if p not in s["defended"]]
        combat = None
        if self.combat:
            combat = {"phase": s["phase"], "must_attack": must_attack,
                      "must_be_attacked": must_be, "pending": self._pending_view(),
                      "battles_fought": s["battle_no"]}
        return {
            "mode": "westwall", "turn": s["turn"], "turns": self.turns,
            "turn_label": self.turn_label(), "night": False,
            "phase": s["phase"], "mover": s["mover"],
            "over": s["over"], "winner": s["winner"], "level": s.get("level"),
            "vp": s["vp"], "moved": s["moved"], "combat": combat,
            "westwall": {"due": due, "gsp_left": s["gsp_left"],
                         "demolished": s["demolished"], "repaired": s["repaired"],
                         "pending": self._pending_view(),
                         "assault": s["assault"]},
            "exited": dict(s["exited"]),
            "scenario": self.scenario["name"],
            "tier": self.tier, "tier_earned": self.tier_earned,
            "rules_scope": self.rules_scope(),
        }
