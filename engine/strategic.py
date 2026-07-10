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
    def __init__(self, game, scenario_path, live_dir, seed=None, tier=None):
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
        # id -> (slot, side) for every piece the scenario knows (replacements
        # resurrect from the dead list; breakdowns from the exchanged stock)
        self.catalog = {u["id"]: (u["slot"], u["side"])
                        for u in self.scenario.get("units", [])}
        self.catalog.update({u["id"]: (u["slot"], u["side"])
                             for u in self.scenario.get("reserve", [])})
        self.supply_table = (self.scenario.get("supply_table") or {}).get("windows", [])
        self.supply_max = self.scenario.get("supply_max_on_board", {})
        p = (game.spec.get("ports") or {}).get("list", [])
        self.ports = {tuple(e["hex"]): e for e in p}
        self.combat = game.spec.get("combat")
        # Tier selection (spec #13): a game may be RUN below the tier it has
        # earned. Tier 1 = movement/arrivals gate only — the entire combat
        # ruleset (and everything keyed on it: capture, isolation,
        # replacements, substitutes, AV, victory) is switched off, which is
        # exactly the validated Tier-1 configuration. Tier 0 never reaches
        # this class (no gate at all — the server serves free play).
        # Earned tier: 1 = movement/arrivals only; 2 = full combat gate;
        # 3 = combat gate + a validated policy AI (declared in game.json
        # `policy_ai`). Tier 3's gate is identical to tier 2 — the AI is an
        # opponent offered on top, it submits through the same door.
        self.tier_earned = (
            (3 if game.spec.get("policy_ai") else 2) if self.combat else 1)
        self.tier = self.tier_earned if tier is None \
            else max(1, min(int(tier), self.tier_earned))
        if self.tier < 2:
            self.combat = None
        self.repl_cfg = self.scenario.get("replacements")
        self.sub_cfg = self.scenario.get("substitutes")
        # 4.1/4.2 control-victory objectives: every fortress + home base hex
        self.victory_hexes = []
        if self.combat and game.terrain:
            for key, v in game.terrain["hexes"].items():
                if v["t"] in ("fortress", "homebase"):
                    self.victory_hexes.append((int(key[:2]), int(key[2:])))
            self.victory_hexes.sort()
        if os.path.exists(self.state_path):
            self.s = json.load(open(self.state_path, encoding="utf-8"))
            if "pool" not in self.s or "attacked" not in self.s \
               or "cap_pool" not in self.s:
                self.new_game(seed)       # older-schema state file: reset
            elif self.s.get("tier", self.tier_earned) != self.tier:
                self.new_game(seed)       # state was played at another tier
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
            "seed": seed, "rng_calls": 0, "n": 0, "tier": self.tier,
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
            # combat phase (3.2/3.4): battle bookkeeping, all verifier-replayed
            "attacked": {}, "defended": {}, "fought": [],
            "supplies_used": [], "pending": None, "pending_rommel": None,
            "vic_start_ok": False, "vic_streak": {}, "dead": [],
            # Tier-2 completion: supply capture 15, isolation 24,
            # replacements 20, substitutes 21, Automatic Victory 9
            "cap_pool": {}, "no_sustain": [], "cap_attacks": [],
            "cap_move": {},
            "iso": {}, "iso_start": {}, "nosup": {}, "nosup_start": False,
            "repl": {}, "av": [], "sub_stock": [], "sub_comp": {},
        }
        for side in self.game.side_order:
            self.s["cap_pool"][side] = sorted(
                pid for pid, e in self.reserve.items()
                if e.get("cls") == "supply" and "Captured" in e["slot"]
                and e["side"] == side)
            self.s["repl"][side] = 0
            self.s["nosup"][side] = 0
        self.s["ports"] = self._controlled_ports(self.first_player)
        self.s["vic_start_ok"] = self._controls_objectives(self.first_player)
        self.s["iso_start"] = self._iso_snapshot(self.first_player)
        self.s["nosup_start"] = not self._supply_hexes(self.first_player) \
            and self.combat is not None
        if os.path.exists(self.log_path):
            os.remove(self.log_path)
        self._log({"event": "init", "mode": "strategic",
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
                ("turn", "phase", "mover", "moved", "over", "winner",
                 "rng_calls", "units", "pool", "supply_pool", "supply_rolled",
                 "supply_pending", "allied_supply_done", "paths", "bonus",
                 "landed_sea", "ports",
                 "attacked", "defended", "fought", "supplies_used",
                 "pending", "pending_rommel", "vic_start_ok", "vic_streak",
                 "dead", "cap_pool", "no_sustain", "cap_attacks",
                 "cap_move",
                 "iso", "iso_start", "nosup", "nosup_start",
                 "repl", "av", "sub_stock", "sub_comp")}
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
        pieces and units at sea are not on the map and never block).
        AV'd defenders (9.1) carry zoc_negated: they exert no ZOC and may
        be moved through, though never ended upon."""
        neg = self._av_negated() if self.s.get("av") else set()
        return [dict(id=u["pid"], name=u["slot"], side=u["side"],
                     col=u["col"], row=u["row"],
                     **({"zoc_negated": True} if u["pid"] in neg else {}))
                for u in self.s["units"].values()
                if u["pid"] != exclude_pid and self.on_map(u)]

    def budget(self, u):
        return self.game.stats(u["slot"])[2]

    def dests(self, u):
        """Legal destinations for a gate unit via the validated spec engine
        (terrain, roads/escarpments 17/18, ZOC 7/8 incl. fortress immunity
        19.5, stacking 6, enemy hexes 5.4). An hq unit may not voluntarily
        end alone in an enemy ZOC (22.41: staying put is always an
        alternative)."""
        me = dict(id=u["pid"], name=u["slot"], side=u["side"],
                  col=u["col"], row=u["row"])
        dd = self.game.legal_destinations_t(
            me, self.budget(u), self.rules_board(exclude_pid=u["pid"]))
        if self.combat and self.game.unit_class(u["slot"]) == "hq":
            board = self.rules_board(exclude_pid=u["pid"])
            ezoc = self.game.zoc_hexes(board, self.game.enemy(u["side"]))
            friends = {(f["col"], f["row"]) for f in self._combat_units(u["side"])}
            dd = {h: c for h, c in dd.items()
                  if h not in ezoc or h in friends}
        return dd

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
        if self.combat and self.game.unit_class(u["slot"]) == "hq":
            end = tuple(path[-1])
            board = self.rules_board(exclude_pid=u["pid"])
            ezoc = self.game.zoc_hexes(board, self.game.enemy(u["side"]))
            friends = {(f["col"], f["row"]) for f in self._combat_units(u["side"])}
            if end in ezoc and end not in friends:
                return self._v(False, "the headquarters unit may not be "
                                      "purposefully moved into an enemy ZOC "
                                      "without an accompanying friendly combat "
                                      "unit [22.41]")
        v = self._v(True)
        v["path_check"] = why
        return v

    # ------------------------------------------------------------ combat helpers
    def _is_combat(self, u):
        """A combat unit: on the map and not a marker/supply/hq (5.4)."""
        return self.on_map(u) and self.game.unit_class(u["slot"]) is None

    def _combat_units(self, side):
        return [u for u in self.s["units"].values()
                if u["side"] == side and self._is_combat(u)]

    def _engageable(self, a, b):
        """Hexes a and b may engage each other: adjacent and not across a
        prohibited hexside (5.7: units on the E18-F19 / W62-X62 adjoining
        hexes may not engage each other in battle)."""
        return b in self.game.neighbors(*a) \
            and not self.game.hexside_prohibited(a, b)

    def _ezoc_for(self, side, ignore_pids=()):
        """Enemy ZOC hexes threatening `side`, optionally ignoring the ZOC
        of specific enemy units (14.2 supply routes ignore the ZOC of the
        very units being attacked — 13.2 + clarifications fig. 15)."""
        board = self.rules_board()
        z = self.game.zoc_by_unit(board, self.game.enemy(side))
        out = set()
        for pid, hexes in z.items():
            if pid not in ignore_pids:
                out |= hexes
        return out

    def _trace_blocked(self, side):
        """Hexes a supply/isolation trace may never pass: enemy hexes whose
        occupants include a combat unit (5.4 — lone supply/Rommel do not
        block, they are not combat units)."""
        board = self.rules_board()
        eblock, _, _ = self.game._enemy_hexes(board, self.game.enemy(side))
        return eblock

    def _trace_reaches(self, from_hex, side, targets, radius=None,
                       ignore_zoc_of=(), target_zoc_exempt=False):
        """BFS trace from from_hex (exclusive) toward any hex in `targets`
        (inclusive): every route hex must be on playable terrain, free of
        enemy ZOC and enemy combat units, and no step may cross a
        prohibited hexside (14.2, 24.1). Returns True if some target is
        within `radius` route hexes (None = unlimited).
        target_zoc_exempt: the target hex itself may sit in enemy ZOC —
        used for the 24.1 isolation trace, where the line runs TO the
        supply unit (a wrong auto-elimination is worse than a lenient
        one); the 14.2 attack-supply route keeps the strict inclusive
        test and instead carves out the attacked units' own ZOC
        (ignore_zoc_of — 13.2 + clarifications figs. 12/15)."""
        targets = {tuple(t) for t in targets}
        if tuple(from_hex) in targets:
            return True                # stacked with the supply: route length 0
        ezoc = self._ezoc_for(side, ignore_pids=ignore_zoc_of)
        blocked = self._trace_blocked(side)
        seen = {tuple(from_hex)}
        frontier = [tuple(from_hex)]
        depth = 0
        while frontier and (radius is None or depth < radius):
            depth += 1
            nxt = []
            for cur in frontier:
                for nb in self.game.neighbors(*cur):
                    if nb in seen:
                        continue
                    if self.game.hexside_prohibited(cur, nb):
                        continue
                    if not self.game.on_map(*nb):
                        continue
                    if nb in targets and target_zoc_exempt and nb not in blocked:
                        return True
                    if nb in ezoc or nb in blocked:
                        continue
                    seen.add(nb)
                    if nb in targets:
                        return True
                    nxt.append(nb)
            frontier = nxt
        return False

    def _supply_hexes(self, side):
        """Hexes of side's on-map supply units (own or captured)."""
        return [(u["col"], u["row"]) for u in self.s["units"].values()
                if u["side"] == side and self.on_map(u)
                and self.game.unit_class(u["slot"]) == "supply"]

    def _isolated(self, u):
        """24.1: no trace of any length free of enemy ZOC / sea / Qattara /
        board edge / prohibited hexsides to a friendly supply unit."""
        sup = self._supply_hexes(u["side"])
        if not sup:
            return True
        return not self._trace_reaches((u["col"], u["row"]), u["side"], sup,
                                       target_zoc_exempt=True)

    def _adjacent_enemy_combat(self, u):
        """Enemy combat units this unit could engage (adjacent, engageable)."""
        enemy = self.game.enemy(u["side"])
        out = []
        for e in self._combat_units(enemy):
            if self._engageable((u["col"], u["row"]), (e["col"], e["row"])):
                out.append(e)
        return out

    def _battle_factors(self, attackers, defenders):
        """(attack total, defense total): attack factors are never terrain
        affected (8.7); defense doubles on fortress/escarpment (10.2)."""
        att = sum(self.game.stats(a["slot"])[0] for a in attackers)
        deff = sum(self.game.defense_factor(d["slot"], (d["col"], d["row"]))
                   for d in defenders)
        return att, deff

    def _supply_free_attack_exists(self, u, pool=None):
        """Can `u`, ALONE, make its forced attack with no supply (rounded odds
        1-3 .. 1-6, 14.3/7.4)? A lone unit must attack every adjacent enemy
        combat unit COMBINED into one battle — one unit attacking several
        totals their defense (11.2), and a single unit may not divide a stack
        (11.4). Used for the 11.9 trapped-unit sweep (clarifications sec. 5)
        and the forced-elimination test."""
        adj = pool if pool is not None else self._adjacent_enemy_combat(u)
        if not adj:
            return False
        att = self.game.stats(u["slot"])[0]
        deff = sum(self.game.defense_factor(e["slot"], (e["col"], e["row"]))
                   for e in adj)
        n, d = self.game.odds(att, deff)
        return n == 1 and 3 <= d <= 6

    def _solo_attack_exists(self, u):
        """Any legal attack `u` can make ALONE. Its forced attack is against
        EVERY adjacent enemy combat unit combined into one battle (11.2/11.4:
        one unit may not split a stack, and totals the defense of all units it
        attacks; 11.33: it must attack every enemy in whose ZOC it sits).
        Legal at supply-free odds (1-3..1-6) or at 1-2/better with a supply
        unit actually in range (14.2). The 11.6 multi-unit-support option is
        NOT searched — declared in the scenario's rules_scope."""
        adj = self._adjacent_enemy_combat(u)
        if not adj:
            return False
        if self._supply_free_attack_exists(u, adj):
            return True
        att = self.game.stats(u["slot"])[0]
        deff = sum(self.game.defense_factor(e["slot"], (e["col"], e["row"]))
                   for e in adj)
        n, d = self.game.odds(att, deff)
        if self.game.odds_column(n, d) is None:
            return False                       # worse than 1-6: no legal attack
        if d > 2:                              # supply-free (already covered)
            return True
        sup = self._supply_hexes(u["side"])
        rad = self.combat["attack_supply"]["radius"]
        ids = tuple(e["pid"] for e in adj)
        return self._trace_reaches((u["col"], u["row"]), u["side"], sup,
                                   radius=rad, ignore_zoc_of=ids)

    def _obligations(self, side):
        """8.4 both directions: (my combat units in enemy ZOC that have not
        attacked, enemy combat units whose ZOC covers my combat units and
        have not been attacked)."""
        board = self.rules_board()
        enemy = self.game.enemy(side)
        mine = [((u["col"], u["row"]), u["pid"]) for u in self._combat_units(side)]
        my_hexes = {h for h, _ in mine}
        must_attack, must_be_attacked = [], []
        zby = self.game.zoc_by_unit(board, enemy)
        for epid, hexes in zby.items():
            if my_hexes & hexes:
                epid_unit = self.s["units"].get(epid)
                if epid_unit is not None and self._is_combat(epid_unit) \
                   and epid not in self.s["defended"]:
                    must_be_attacked.append(epid)
        allz = set().union(*zby.values()) if zby else set()
        for h, pid in mine:
            if h in allz and pid not in self.s["attacked"]:
                must_attack.append(pid)
        return sorted(must_attack), sorted(must_be_attacked)

    # ------------------------------------------------------------ retreats
    def _retreat_env(self, side):
        board = self.rules_board()
        enemy = self.game.enemy(side)
        ezoc = self.game.zoc_hexes(board, enemy)
        eblock, _, _ = self.game._enemy_hexes(board, enemy)
        return board, ezoc, eblock

    def _retreat_step_ok(self, cur, nb, ezoc, eblock):
        """One retreat step: playable terrain (escarpments allowed, no stop
        — 7.6), never across a prohibited hexside, never into enemy ZOC or
        an enemy combat unit's hex (7.61)."""
        if not self.game.on_map(*nb):
            return False
        if self.game.hexside_prohibited(cur, nb):
            return False
        if nb in ezoc or nb in eblock:
            return False
        return True

    def _retreat_paths(self, u, ezoc, eblock, board):
        """All legal 2-hex retreat paths for u: zigzag allowed, may not
        re-enter its own hex nor any hex twice (7.6 + clarifications 9);
        intermediate hex ignores stacking (7.6), final hex must respect it
        (7.61). Returns {end_hex: [path, ...]}."""
        start = (u["col"], u["row"])
        me = dict(id=u["pid"], name=u["slot"], side=u["side"],
                  col=u["col"], row=u["row"])
        out = {}
        for h1 in self.game.neighbors(*start):
            if not self._retreat_step_ok(start, h1, ezoc, eblock):
                continue
            for h2 in self.game.neighbors(*h1):
                if h2 == start or h2 == h1:
                    continue
                if not self._retreat_step_ok(h1, h2, ezoc, eblock):
                    continue
                if not self.game._stack_ok(me, h2, board):
                    continue
                out.setdefault(h2, []).append([list(h1), list(h2)])
        return out

    def _stack_room(self, side, h, board):
        """Free combat-unit slots at hex h for `side` (6.1)."""
        st = self.game.stacking
        if not st:
            return 99
        exempt = set(st.get("exempt_classes", []))
        n = sum(1 for b in board
                if b["side"] == side and (b["col"], b["row"]) == tuple(h)
                and self.game.unit_class(b["name"]) not in exempt)
        return max(0, int(st["max"]) - n)

    def _survival_assignment_exists(self, pids, extra_used=None):
        """Is there an assignment of legal retreat end-hexes to every unit
        in pids such that all survive (joint stacking capacity respected)?
        7.62 + clarifications 7: the winner may not cause an immediate
        elimination when routes exist that let all retreating units live."""
        if not pids:
            return True
        units = [self.unit(p) for p in pids]
        side = units[0]["side"]
        board, ezoc, eblock = self._retreat_env(side)
        opts = []
        for u in units:
            ends = list(self._retreat_paths(u, ezoc, eblock, board))
            if not ends:
                return False
            opts.append(ends)
        room = {}
        for ends in opts:
            for h in ends:
                if h not in room:
                    room[h] = self._stack_room(side, h, board)
        if extra_used:
            for h in extra_used:
                if tuple(h) in room:
                    room[tuple(h)] -= 1

        def rec(i, used):
            if i == len(opts):
                return True
            for h in opts[i]:
                if used.get(h, 0) < room.get(h, 0):
                    used[h] = used.get(h, 0) + 1
                    if rec(i + 1, used):
                        return True
                    used[h] -= 1
            return False
        return rec(0, {})

    # ------------------------------------------------------------ Rommel 22.4
    def _rommel_displacement(self, events):
        """22.4: an hq alone in an enemy ZOC is placed with the closest
        friendly combat unit (22.42: not counting untraversable or
        enemy-ZOC hexes unless there is no other way; ties are the owner's
        choice). Fortress hexes are never in enemy ZOC (19.5), so Rommel
        alone in Tobruch stays (clarifications 6)."""
        if self.s["pending_rommel"]:
            return
        board = self.rules_board()
        for u in list(self.s["units"].values()):
            if not self.on_map(u) or self.game.unit_class(u["slot"]) != "hq":
                continue
            here = (u["col"], u["row"])
            if any(b["side"] == u["side"] and (b["col"], b["row"]) == here
                   and self.game.unit_class(b["name"]) is None for b in board):
                continue
            ezoc = self.game.zoc_hexes(board, self.game.enemy(u["side"]))
            if here not in ezoc:
                continue
            friends = {(f["col"], f["row"]) for f in self._combat_units(u["side"])}
            if not friends:
                continue
            eblock, _, _ = self.game._enemy_hexes(board, self.game.enemy(u["side"]))
            choices = self._closest_hexes(here, friends, ezoc, eblock)
            if not choices:
                choices = self._closest_hexes(here, friends, set(), eblock)
            if not choices:
                continue
            if len(choices) == 1:
                u["col"], u["row"] = choices[0]
                events.append(f"'{u['slot']}' was alone in an enemy ZOC — "
                              f"placed with the closest friendly combat unit "
                              f"at {self.game.grid.display_name(*choices[0])} "
                              f"[22.4]")
            else:
                self.s["pending_rommel"] = {"unit": u["pid"],
                                            "choices": [list(c) for c in choices]}
                events.append(f"'{u['slot']}' is alone in an enemy ZOC with "
                              f"equidistant friendly combat units — the owner "
                              f"must choose a placement [22.4, 22.42]")

    def _closest_hexes(self, start, targets, ezoc, eblock):
        """Hexes in `targets` at minimum BFS distance from start, tracing
        over playable terrain, avoiding enemy ZOC/combat hexes (22.42)."""
        seen = {start}
        frontier = [start]
        while frontier:
            found = sorted(h for h in frontier if h in targets and h != start)
            if found:
                return found
            nxt = []
            for cur in frontier:
                for nb in self.game.neighbors(*cur):
                    if nb in seen or not self.game.on_map(*nb):
                        continue
                    if self.game.hexside_prohibited(cur, nb):
                        continue
                    if nb not in targets and (nb in ezoc or nb in eblock):
                        continue
                    seen.add(nb)
                    nxt.append(nb)
            frontier = nxt
        return []

    # ------------------------------------------------------------ victory 4.1-4.3
    def _controls_objectives(self, side):
        """4.3 control of every fortress + home base hex: occupied by a
        combat/supply/Rommel unit; home bases additionally free of enemy
        ZOC."""
        if not self.victory_hexes:
            return False
        board = self.rules_board()
        ezoc = self.game.zoc_hexes(board, self.game.enemy(side))
        for hx in self.victory_hexes:
            occ = any(u["side"] == side and self.on_map(u)
                      and (u["col"], u["row"]) == hx
                      and self.game.unit_class(u["slot"]) != "markers"
                      for u in self.s["units"].values())
            if not occ:
                return False
            if self.game.hex_terrain(*hx) == "homebase" and hx in ezoc:
                return False
        return True

    def _check_elimination_victory(self, events):
        """4.1/4.2: a side with no combat units on the board loses ('on the
        board' excludes units at sea, clarifications 13)."""
        if self.s["over"] or not self.combat:
            return
        a, b = self.game.side_order
        alive = {s: len(self._combat_units(s)) for s in (a, b)}
        dead = [s for s in (a, b) if alive[s] == 0]
        if not dead:
            return
        self.s["over"] = True
        if len(dead) == 2:
            self.s["winner"] = None
            events.append("both sides have lost every combat unit on the "
                          "board — no winner adjudicated [4.1/4.2]")
        else:
            w = self.game.enemy(dead[0])
            self.s["winner"] = w
            events.append(f"all {dead[0]} combat units on the board are "
                          f"eliminated — {w} wins [4.1/4.2, clarifications 13]")

    def _remove_units(self, pids, events, why):
        for pid in pids:
            u = self.s["units"].pop(str(pid), None)
            if u:
                self.s["dead"].append(str(pid))
                events.append(f"'{u['slot']}' eliminated — {why}")

    # ------------------------------------------------------------ supply capture 15
    def _recycle_supply(self, pid, events, why):
        """A supply unit leaves the board: the physical counter returns to
        the owner's off-board pool for possible re-entry under the normal
        generation rules (12.1/12.2 imply counter recycling — the maxima
        are counter counts; 15.21 says captured originals are 'returned to
        the opponent for possible reentry')."""
        u = self.s["units"].pop(str(pid), None)
        if not u:
            return
        pool = "cap_pool" if "Captured" in u["slot"] else "supply_pool"
        self.s[pool].setdefault(u["side"], []).append(str(pid))
        if str(pid) in self.s["supplies_used"]:
            self.s["supplies_used"].remove(str(pid))
        events.append(f"'{u['slot']}' {why}")

    def _capture_sweep(self, events, capturer, context="movement",
                       near_hexes=None):
        """15.21/15.22/15.321: an UNACCOMPANIED enemy supply adjacent to (or
        under) one of `capturer`'s combat units is captured the instant that
        adjacency ARISES — the trigger is the capturer's units moving/
        retreating/advancing/remaining after battle, never static enemy
        adjacency (15.21 'moves adjacent', 15.211). One-directional per
        event, so a freshly captured supply is never ping-ponged back by
        units that merely stand next to it. Exceptions: fortress hexes
        shield adjacency capture (15.23 — same-hex capture still applies),
        anomalous hexsides never create adjacency (5.7), and a supply
        currently sustaining attacks is neither captured nor stopped when
        overrun (15.22). near_hexes: optionally also capture supplies
        adjacent to intermediate path hexes (15.22 'during its retreat')."""
        if not self.combat:
            return
        mine = self._combat_units(capturer)
        enemy = self.game.enemy(capturer)
        changed = True
        while changed:
            changed = False
            for u in list(self.s["units"].values()):
                if u["side"] != enemy or not self.on_map(u) \
                   or self.game.unit_class(u["slot"]) != "supply":
                    continue
                if context != "movement" and u["pid"] in self.s["supplies_used"]:
                    continue                     # 15.22 sustaining exception
                here = (u["col"], u["row"])
                if any(b["side"] == enemy and self.on_map(b)
                       and (b["col"], b["row"]) == here and self._is_combat(b)
                       for b in self.s["units"].values()):
                    continue                     # accompanied (Rommel doesn't count, 15.1)
                on_top = any((e["col"], e["row"]) == here for e in mine)
                adjacent = any(self._engageable(here, (e["col"], e["row"]))
                               for e in mine)
                if near_hexes and not (on_top or adjacent):
                    adjacent = any(self._engageable(here, tuple(h))
                                   or tuple(h) == here for h in near_hexes)
                in_fortress = self.game.hex_terrain(*here) == "fortress"
                if not (on_top or (adjacent and not in_fortress)):
                    continue                     # 15.23: fortress blocks adjacency capture
                self._apply_capture(u, capturer, events, context)
                changed = True
                break

    def _escorts_of(self, here, capturer):
        """Enemy combat units stacked on the captured supply's hex — the
        'previously accompanying' units of 15.34."""
        enemy = self.game.enemy(capturer)
        return [b["pid"] for b in self._combat_units(enemy)
                if (b["col"], b["row"]) == tuple(here)]

    def _apply_capture(self, u, capturer, events, context):
        """Flip an unaccompanied supply to the capturing side (15.21).
        Post-capture rights depend on HOW it was captured:
          movement (15.21, AV fig 2): moves and sustains freely this turn;
          battle/capture-attack (15.32x): may move its full MF — even out of
          the old escort's ZOC (15.33/15.34) — but never sustains this turn;
          fortress capture-attack (15.23): neither moves nor sustains;
          retreat/advance (15.22/15.31): accompanies only — no move, no
          sustain."""
        here = (u["col"], u["row"])
        events_note = (f"'{u['slot']}' at {self.game.grid.display_name(*here)} "
                       f"CAPTURED by {capturer}")
        self._recycle_supply(u["pid"], [],
                             "returned to the opponent's pool [15.21]")
        pool = self.s["cap_pool"].get(capturer, [])
        if pool:
            new_pid = pool.pop(0)
            slot = self.reserve[new_pid]["slot"]
            self.s["units"][new_pid] = {"pid": new_pid, "slot": slot,
                                        "side": capturer,
                                        "col": here[0], "row": here[1]}
        else:                        # no physical captured counter left:
            new_pid = u["pid"]       # flip the original in place
            self.s["units"][new_pid] = dict(u, side=capturer)
            self.s["supply_pool"][u["side"]].remove(new_pid)
        if context == "movement":
            events.append(events_note + " — it may move and sustain attacks "
                          "this turn [15.21, clarifications figs 1-2]")
            return
        if new_pid not in self.s["no_sustain"]:
            self.s["no_sustain"].append(new_pid)
        if context == "battle":
            self.s["cap_move"][new_pid] = list(self._escorts_of(here, capturer))
            events.append(events_note + " — it may be moved its full MF, "
                          "even out of the old escort's ZOC, but cannot "
                          "sustain attacks this turn [15.33, 15.34]")
        else:                        # fortress attack / retreat / advance
            self.s["moved"][new_pid] = {"captured": True}
            events.append(events_note + " — it may not move further nor "
                          "sustain attacks this turn [15.22, 15.23]")

    # ------------------------------------------------------------ isolation 24
    def _iso_snapshot(self, side):
        """Isolation status of every friendly combat unit (24.1; at-sea
        units are isolated unless a friendly supply is also at sea, 24.4)."""
        if not self.combat:
            return {}
        out = {}
        supply_at_sea = any(
            u["side"] == side and not self.on_map(u)
            and self.game.unit_class(u["slot"]) == "supply"
            for u in self.s["units"].values())
        for u in self.s["units"].values():
            if u["side"] != side or self.game.unit_class(u["slot"]) is not None:
                continue
            if not self.on_map(u):
                out[u["pid"]] = not supply_at_sea
            else:
                out[u["pid"]] = self._isolated(u)
        return out

    def _isolation_end_of_turn(self, side, notes):
        """24.2: isolated at the start AND end of two consecutive own
        player turns -> eliminated (clarifications 8: supply at start OR
        end breaks the count). 24.5: a side with no supply units on board
        at start and end of two consecutive own turns loses everything."""
        if not self.combat:
            return
        end = self._iso_snapshot(side)
        iso = self.s["iso"]
        for pid, isolated_now in end.items():
            if isolated_now and self.s["iso_start"].get(pid):
                iso[pid] = iso.get(pid, 0) + 1
            else:
                iso.pop(pid, None)
        doomed = sorted(p for p, n in iso.items() if n >= 2)
        for pid in doomed:
            iso.pop(pid, None)
            self._remove_units([pid], notes,
                               "isolated at the start and end of two "
                               "consecutive friendly player turns [24.1, 24.2]")
        for pid in list(iso):
            if pid not in self.s["units"]:
                iso.pop(pid)
        nosup_end = not self._supply_hexes(side)
        if nosup_end and self.s["nosup_start"]:
            self.s["nosup"][side] = self.s["nosup"].get(side, 0) + 1
        else:
            self.s["nosup"][side] = 0
        if self.s["nosup"][side] >= 2 and not self.s["over"]:
            gone = [u["pid"] for u in self.s["units"].values()
                    if u["side"] == side]
            self._remove_units(gone, notes,
                               "no supply units for two consecutive player "
                               "turns — all units lost [24.5]")
            self.s["over"] = True
            self.s["winner"] = self.game.enemy(side)
            notes.append(f"{side} had no supply units on board at the start "
                         f"and end of two consecutive player turns — "
                         f"{self.s['winner']} WINS [24.5]")

    # ------------------------------------------------------------ replacements 20
    def _repl_accrue(self, side, notes):
        """20.2/20.3: earn replacement attack factors at the start of the
        own player turn for each controlled home base / Tobruch (4.3)."""
        cfg = self.repl_cfg
        if not cfg or not self.combat or self.s["turn"] < cfg["start_turn"]:
            return
        board = self.rules_board()
        ezoc = self.game.zoc_hexes(board, self.game.enemy(side))
        earned = 0
        rates = cfg["rates"][side]
        for hx in self.victory_hexes:
            terr = self.game.hex_terrain(*hx)
            occ = any(u["side"] == side and self.on_map(u)
                      and (u["col"], u["row"]) == hx
                      and self.game.unit_class(u["slot"]) != "markers"
                      for u in self.s["units"].values())
            if not occ:
                continue
            if terr == "homebase":
                if hx in ezoc:
                    continue
                # only the OWN home base earns (20.2/20.3)
                port = self.ports.get(hx)
                if not port or side not in port["usable_by"]:
                    continue
                earned += rates.get("homebase", 0)
            elif terr == "fortress" and tuple(hx) in self.ports:
                earned += rates.get("fortress_port", 0)   # Tobruch, not Bengasi
        if earned:
            self.s["repl"][side] = self.s["repl"].get(side, 0) + earned
            notes.append(f"{side} earns {earned} replacement factor(s) "
                         f"[20.2/20.3, from 1 March 1942; accumulated: "
                         f"{self.s['repl'][side]} (20.5)]")

    # ------------------------------------------------------------ AV 9 plumbing
    def _av_negated(self):
        return {p for e in self.s["av"] for p in e["defenders"]}

    # ------------------------------------------------------------ verdicts
    def _v(self, ok, *reasons):
        return {"legal": ok, "reasons": list(reasons)}

    def propose(self, side, action):
        t = action.get("type")
        if self.s["over"]:
            return self._v(False, "game is over")
        if side not in self.game.side_order:
            return self._v(False, f"unknown side '{side}'")
        # combat sub-actions may belong to the NON-moving player (7.5: the
        # winner retreats the loser's units / pays exchange losses)
        if t == "place_rommel":
            return self._propose_place_rommel(side, action)
        if self.s["pending_rommel"]:
            return self._v(False, "the displaced headquarters unit must be "
                                  "placed first [22.4, 22.42]")
        if t == "retreat":
            return self._propose_retreat(side, action)
        if t == "exchange_loss":
            return self._propose_exchange_loss(side, action)
        pend = self.s["pending"]
        if pend and pend["kind"] in ("retreat", "exchange"):
            return self._v(False, "a battle is being settled — its retreat/"
                                  "exchange losses must be executed before "
                                  "anything else [8.6]")
        if side != self.s["mover"]:
            return self._v(False, f"it is the {self.s['mover']} player turn — "
                                  f"no {side} movement is allowed [3.1/3.3]")
        if t == "end_phase":
            return self._propose_end_phase(side)
        if t == "end_movement":
            return self._propose_end_movement(side)
        if t == "battle":
            return self._propose_battle(side, action)
        if t == "advance":
            return self._propose_advance(side, action)
        if t == "forced_elim":
            return self._propose_forced_elim(side, action)
        if t == "destroy_supply":
            return self._propose_destroy_supply(side, action)
        if t == "capture_supply":
            return self._propose_capture_supply(side, action)
        if t == "replace":
            return self._propose_replace(side, action)
        if t == "declare_av":
            return self._propose_declare_av(side, action)
        if t == "substitute":
            return self._propose_substitute(side, action)
        if t == "breakdown":
            return self._propose_breakdown(side, action)
        if t == "move" and self.s["phase"] == "combat" \
           and str(action.get("unit")) in self.s["cap_move"]:
            return self._propose_move(side, action)
        if t in ("move", "rommel_extend", "roll_supply", "land_supply",
                 "land_reinforcement", "embark", "debark") \
           and self.s["phase"] != "movement":
            return self._v(False, "the movement portion of the turn is over — "
                                  "all movement precedes combat resolution "
                                  "[3.1/3.2, 5.3]")
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

    # ------------------------------------------------------------ combat proposals
    def _propose_end_movement(self, side):
        if not self.combat:
            return self._v(False, "no combat rules encoded for this game")
        if self.s["phase"] != "movement":
            return self._v(False, "movement is already over this player turn")
        over = self.overstacked_hexes(side)
        if over:
            names = ", ".join(self.game.grid.display_name(*h) for h in over)
            return self._v(False, f"stacking limit exceeded at {names} — limits "
                                  "bind at the end of movement [6.1, 6.3]")
        # 9.2/14.5: every AV must still have a supply within 5 hexes of all
        # its attackers at the END of the movement portion (the AVed unit's
        # ZOC is negated by now); a different supply than the declared one
        # means BOTH are expended
        rad = (self.combat.get("attack_supply") or {}).get("radius", 5)
        av_supplies = []
        for e in self.s["av"]:
            atk_hexes = [(self.unit(p)["col"], self.unit(p)["row"])
                         for p in e["attackers"] if p in self.s["units"]]

            def in_range(spid):
                su = self.s["units"].get(spid)
                if not su or not self.on_map(su) \
                   or self.game.unit_class(su["slot"]) != "supply" \
                   or su["side"] != side or spid in self.s["no_sustain"]:
                    return False
                return all(self._trace_reaches(h, side,
                                               [(su["col"], su["row"])],
                                               radius=rad)
                           for h in atk_hexes)
            if in_range(e["supply"]):
                av_supplies.append([e["supply"]])
                continue
            alt = next((u["pid"] for u in self.s["units"].values()
                        if u["side"] == side and in_range(u["pid"])), None)
            if alt is None:
                names = ", ".join(self.unit(p)["slot"] for p in e["defenders"]
                                  if p in self.s["units"])
                return self._v(False,
                    f"the AV against {names or 'the negated unit'} has no "
                    f"supply within {rad} hexes of its attackers at the end "
                    f"of movement — move one into range [9.2, 14.5]")
            av_supplies.append([e["supply"], alt])
        v = self._v(True)
        v["av_supplies"] = av_supplies
        return v

    def _propose_end_phase(self, side):
        over = self.overstacked_hexes(side)
        if over:
            names = ", ".join(self.game.grid.display_name(*h) for h in over)
            return self._v(False, f"stacking limit exceeded at {names} — limits "
                                  "must be adhered to at the conclusion of each "
                                  "player's movement [2.3, 6.1, 6.3]")
        if not self.combat:
            return self._v(True)
        must_attack, must_be = self._obligations(side)
        if self.s["phase"] == "movement":
            if must_attack or must_be:
                return self._v(False, "moving into an enemy ZOC causes combat "
                                      "— all battles must be resolved before "
                                      "the player turn ends (submit "
                                      "end_movement, then the battles) "
                                      "[3.2/3.4, 7.2, 8.4]")
            return self._v(True)
        # combat phase: every obligation must be discharged
        if must_attack:
            names = ", ".join(self.unit(p)["slot"] for p in must_attack)
            return self._v(False, f"units in enemy ZOC have not attacked: "
                                  f"{names} — every combat unit in the ZOC of "
                                  f"an enemy unit must attack [8.4]")
        if must_be:
            names = ", ".join(self.unit(p)["slot"] for p in must_be)
            return self._v(False, f"enemy units with your units in their ZOC "
                                  f"were not attacked: {names} [8.4]")
        err = self._fortress_sortie_unmet(side)
        if err:
            return err
        for e in self.s["av"]:
            for dpid in e["defenders"]:
                if dpid in self.s["units"] and dpid not in self.s["defended"]:
                    return self._v(False,
                        f"the declared AV against "
                        f"'{self.unit(dpid)['slot']}' has not been resolved — "
                        f"the AVed unit is removed when the attacker resolves "
                        f"his attacks [9.1, 9.6]")
        for ca in self.s["cap_attacks"]:
            for apid in ca["accomp"]:
                if apid in self.s["units"] and apid not in self.s["defended"]:
                    return self._v(False,
                        f"one unit is 'attacking' the supply, so all other "
                        f"units in the defender's ZOC must attack "
                        f"'{self.unit(apid)['slot']}' at legal odds [15.322, "
                        f"clarifications figs 7/11]")
        return self._v(True)

    def _fortress_sortie_unmet(self, side):
        """23.2: if units in a fortress attacked this turn, they must attack
        ALL adjacent enemy combat units."""
        for f in self.s["fought"]:
            fort_hexes = {tuple(h) for h in f["ahex"].values()
                          if self.game.hex_terrain(*h) == "fortress"}
            for fh in fort_hexes:
                for e in self._combat_units(self.game.enemy(side)):
                    if self._engageable(fh, (e["col"], e["row"])) \
                       and e["pid"] not in self.s["defended"]:
                        return self._v(False,
                            f"units attacking out of the fortress at "
                            f"{self.game.grid.display_name(*fh)} must attack "
                            f"ALL adjacent enemy units — '{e['slot']}' was "
                            f"not attacked [23.2]")
        return None

    def _propose_battle(self, side, action):
        if not self.combat:
            return self._v(False, "no combat rules encoded for this game")
        if self.s["phase"] != "combat":
            return self._v(False, "battles are resolved after all movement — "
                                  "end movement first [3.2, 5.3, 8.6]")
        atk_ids = [str(p) for p in (action.get("attackers") or [])]
        def_ids = [str(p) for p in (action.get("defenders") or [])]
        if not atk_ids or not def_ids:
            return self._v(False, "a battle names attackers and defenders")
        if len(set(atk_ids)) != len(atk_ids) or len(set(def_ids)) != len(def_ids):
            return self._v(False, "duplicate unit in battle declaration")
        attackers, defenders = [], []
        for pid in atk_ids:
            u = self.s["units"].get(pid)
            if not u or u["side"] != side or not self._is_combat(u):
                return self._v(False, f"attacker '{pid}' is not one of your "
                                      f"combat units on the map [5.4, 7.2]")
            if pid in self.s["attacked"]:
                return self._v(False, f"'{u['slot']}' has already fought — no "
                                      f"attacking unit may fight more than one "
                                      f"battle per turn [11.8]")
            attackers.append(u)
        enemy = self.game.enemy(side)
        for pid in def_ids:
            u = self.s["units"].get(pid)
            if not u or u["side"] != enemy or not self._is_combat(u):
                return self._v(False, f"defender '{pid}' is not an enemy "
                                      f"combat unit on the map")
            if pid in self.s["defended"]:
                return self._v(False, f"'{u['slot']}' has already been attacked "
                                      f"— no defending unit may be attacked "
                                      f"more than once per turn [11.7]")
            defenders.append(u)
        for a in attackers:
            for d in defenders:
                if not self._engageable((a["col"], a["row"]),
                                        (d["col"], d["row"])):
                    return self._v(False,
                        f"'{a['slot']}' is not adjacent to '{d['slot']}' — "
                        f"each attacking unit must be adjacent to every "
                        f"defending unit in its attack [8.5] (5.7: anomalous "
                        f"hexsides never allow engagement)")
        # 11.2/11.4: a SINGLE attacking unit may not divide a stacked hex —
        # one unit attacking several totals their defense into one combined
        # factor (dividing a stack across battles requires more than one
        # attacking unit). It must engage every combat unit on each hex it
        # attacks.
        if len(attackers) == 1:
            for d in defenders:
                for other in self._combat_units(enemy):
                    if (other["col"], other["row"]) == (d["col"], d["row"]) \
                       and other["pid"] not in def_ids:
                        return self._v(False,
                            f"a single attacking unit may not split the stack "
                            f"at {self.game.grid.display_name(d['col'], d['row'])}"
                            f" — one unit attacking several totals their defense "
                            f"into one combined factor [11.2, 11.4]")
        # 23.1: attacking into a fortress engages every unit in it
        for d in defenders:
            if self.game.hex_terrain(d["col"], d["row"]) == "fortress":
                for other in self._combat_units(enemy):
                    if (other["col"], other["row"]) == (d["col"], d["row"]) \
                       and other["pid"] not in def_ids:
                        return self._v(False,
                            f"attacks into a fortress must engage ALL units "
                            f"in it — '{other['slot']}' is also in "
                            f"{self.game.grid.display_name(d['col'], d['row'])} "
                            f"[23.1]")
        att, deff = self._battle_factors(attackers, defenders)
        n, d = self.game.odds(att, deff)
        col = self.game.odds_column(n, d)
        if col is None:
            return self._v(False, f"odds {att}:{deff} round to {n}-{d} — no "
                                  f"unit may voluntarily attack at worse than "
                                  f"1-6 [7.4, 11.6]")
        # 11.31/11.33: the battle partition must let EVERY unit in an enemy
        # ZOC attack — this battle may not consume the last un-attacked
        # defender adjacent to some other friendly unit (append-only log
        # has no takebacks; an orphaned unit would dead-lock the turn)
        defended2 = set(self.s["defended"]) | set(def_ids)
        attacked2 = set(self.s["attacked"]) | set(atk_ids)
        ezoc = self.game.zoc_hexes(self.rules_board(), enemy)
        for f in self._combat_units(side):
            if f["pid"] in attacked2 or (f["col"], f["row"]) not in ezoc:
                continue
            if not any(e["pid"] not in defended2
                       for e in self._adjacent_enemy_combat(f)):
                return self._v(False,
                    f"this battle would leave '{f['slot']}' in an enemy ZOC "
                    f"with every adjacent enemy already attacked — every "
                    f"combat unit in an enemy ZOC must attack, so the battle "
                    f"partition must include it [8.4, 11.31-11.33]")
        v = self._v(True)
        v["odds"] = f"{n}-{d}"
        v["column"] = col
        v["factors"] = [att, deff]
        # 14.1/14.2: supply for attacks at 1-2 or better
        if d <= 2:
            spid = str(action.get("supply") or "")
            su = self.s["units"].get(spid)
            if not su or su["side"] != side or not self.on_map(su) \
               or self.game.unit_class(su["slot"]) != "supply":
                vv = self._v(False,
                    f"odds {n}-{d} are 1-2 or better — the attack must state "
                    f"a friendly supply unit sustaining it [14.1, 14.6]")
                vv.update(odds=f"{n}-{d}", column=col, factors=[att, deff])
                return vv
            if spid in self.s["no_sustain"]:
                return self._v(False, "a supply captured this turn during "
                                      "combat/retreat/advance cannot sustain "
                                      "attacks [15.22, 15.33]")
            rad = self.combat["attack_supply"]["radius"]
            for a in attackers:
                if not self._trace_reaches(
                        (a["col"], a["row"]), side,
                        [(su["col"], su["row"])], radius=rad,
                        ignore_zoc_of=tuple(def_ids)):
                    return self._v(False,
                        f"'{a['slot']}' has no {rad}-hex route free of enemy "
                        f"ZOC and blocking terrain to supply '{su['slot']}' — "
                        f"ALL units attacking at 1-2 or better must be within "
                        f"{rad} hexes of the sustaining supply [14.2]")
            v["supply"] = spid
        elif action.get("supply"):
            v["reasons"].append("odds worse than 1-2: no supply needed [14.3]")
        return v

    def _propose_forced_elim(self, side, action):
        if not self.combat or self.s["phase"] != "combat":
            return self._v(False, "forced eliminations happen in the combat "
                                  "portion of the turn [7.4]")
        if self.s["fought"]:
            return self._v(False, "a unit forced to attack at worse than 1-6 "
                                  "is eliminated BEFORE any other battle is "
                                  "resolved [7.4]")
        u, err = self._gate_unit(side, action)
        if err:
            return err
        if not self._is_combat(u):
            return self._v(False, "only combat units are forced to attack [8.4]")
        board = self.rules_board()
        ezoc = self.game.zoc_hexes(board, self.game.enemy(side))
        if (u["col"], u["row"]) not in ezoc:
            return self._v(False, "unit is not in an enemy ZOC — it is not "
                                  "forced to attack [7.2, 8.4]")
        if self._solo_attack_exists(u):
            return self._v(False, "this unit can still make a legal attack — "
                                  "every combat unit in an enemy ZOC must "
                                  "attack [8.4, 7.4] (note: bringing other "
                                  "units in support may also fix the odds, "
                                  "11.6)")
        return self._v(True)

    # ------------------------------------------------ supply capture/destroy 15
    def _cap_move_dests(self, u):
        """Destinations for a combat-captured supply's special move: full MF
        (15.33), ignoring the ZOC of the units that previously accompanied
        it (15.34) — every other rule still applies."""
        ignore = set(self.s["cap_move"].get(u["pid"], []))
        board = []
        for b in self.rules_board(exclude_pid=u["pid"]):
            if b["id"] in ignore:
                b = dict(b, zoc_negated=True)
            board.append(b)
        me = dict(id=u["pid"], name=u["slot"], side=u["side"],
                  col=u["col"], row=u["row"])
        return self.game.legal_destinations_t(me, self.budget(u), board)

    def _fig3_guard(self, u, dest):
        """Clarifications fig 3: a combat unit may not voluntarily move to
        capture an unaccompanied supply when the move leaves it in an enemy
        ZOC with no legal attack — 7.4 supersedes the automatic capture of
        15.21/15.22. (Fig 4: with support adjacent to the covering
        defenders the move is legal — the support test here is presence,
        the exact joint odds stay with the battle gate.)"""
        if not self.combat or not self._is_combat(u):
            return None
        enemy = self.game.enemy(u["side"])
        dest = tuple(dest)
        would_capture = False
        for su in self.s["units"].values():
            if su["side"] != enemy or not self.on_map(su) \
               or self.game.unit_class(su["slot"]) != "supply":
                continue
            sh = (su["col"], su["row"])
            if any((b["col"], b["row"]) == sh for b in self._combat_units(enemy)):
                continue
            if dest == sh or (self._engageable(dest, sh)
                              and self.game.hex_terrain(*sh) != "fortress"):
                would_capture = True
                break
        if not would_capture:
            return None
        board = self.rules_board(exclude_pid=u["pid"])
        ezoc = self.game.zoc_hexes(board, enemy)
        if dest not in ezoc:
            return None
        fake = dict(u, col=dest[0], row=dest[1])
        if self._solo_attack_exists(fake):
            return None
        covering = [e for e in self._combat_units(enemy)
                    if self._engageable(dest, (e["col"], e["row"]))]
        support = any(f["pid"] != u["pid"]
                      and self._engageable((f["col"], f["row"]),
                                           (e["col"], e["row"]))
                      for f in self._combat_units(u["side"])
                      for e in covering)
        if support:
            return None
        return self._v(False,
            "this move would capture the supply while leaving the unit in an "
            "enemy ZOC with no legal attack — a unit cannot voluntarily place "
            "itself in a forbidden attack position; 7.4 supersedes the "
            "automatic capture [clarifications sec 3 fig 3]")

    def _propose_destroy_supply(self, side, action):
        u, err = self._gate_unit(side, action)
        if err:
            return err
        if self.game.unit_class(u["slot"]) != "supply":
            return self._v(False, "only supply units may be voluntarily "
                                  "destroyed [15.4]")
        return self._v(True)

    def _apply_destroy_supply(self, side, action):
        events = []
        self._recycle_supply(str(action["unit"]), events,
                             "voluntarily destroyed by its owner — the counter "
                             "returns to the off-board pool [15.4]")
        return {"events": events}

    def _propose_capture_supply(self, side, action):
        if not self.combat or self.s["phase"] != "combat":
            return self._v(False, "capturing a defended or fortress supply is "
                                  "an 'attack' — combat portion only [15.23, "
                                  "15.322]")
        u, err = self._gate_unit(side, action)
        if err:
            return err
        if not self._is_combat(u):
            return self._v(False, "only a combat unit can attack a supply "
                                  "[15.322]")
        if u["pid"] in self.s["attacked"]:
            return self._v(False, "this unit already fought — the capture "
                                  "'attack' is its battle for the turn [11.8, "
                                  "15.322, clarifications fig 7]")
        spid = str(action.get("supply"))
        su = self.s["units"].get(spid)
        enemy = self.game.enemy(side)
        if not su or su["side"] != enemy or not self.on_map(su) \
           or self.game.unit_class(su["slot"]) != "supply":
            return self._v(False, "target is not an enemy supply unit on the "
                                  "map [15.2]")
        sh = (su["col"], su["row"])
        if not self._engageable((u["col"], u["row"]), sh):
            return self._v(False, "the capturing unit must be adjacent [15.23, "
                                  "15.322, 5.7]")
        accomp = [b["pid"] for b in self._combat_units(enemy)
                  if (b["col"], b["row"]) == sh]
        in_fortress = self.game.hex_terrain(*sh) == "fortress"
        if accomp and in_fortress:
            return self._v(False, "the one-unit supply 'attack' cannot be used "
                                  "against a defended fortress — attack the "
                                  "garrison itself [15.322 NOTE, 23.1]")
        if not accomp and not in_fortress:
            return self._v(False, "an unaccompanied supply outside a fortress "
                                  "is captured automatically by adjacency "
                                  "during movement — no attack needed [15.21]")
        if any(ca["supply"] == spid for ca in self.s["cap_attacks"]):
            return self._v(False, "one attacking unit at most may be used to "
                                  "capture a supply [15.322]")
        v = self._v(True)
        v["accomp"] = accomp
        return v

    def _apply_capture_supply(self, side, action, verdict):
        s = self.s
        pid, spid = str(action["unit"]), str(action["supply"])
        su = self.unit(spid)
        sh = (su["col"], su["row"])
        in_fortress = self.game.hex_terrain(*sh) == "fortress"
        events = []
        s["attacked"][pid] = "capture"
        s["cap_attacks"].append({"unit": pid, "supply": spid,
                                 "accomp": verdict["accomp"]})
        s["pending"] = None
        self._apply_capture(su, side, events,
                            "battle" if verdict["accomp"] else "fortress")
        if in_fortress and not verdict["accomp"]:
            self.s["pending"] = {"kind": "advance", "battle": "capture",
                                 "hexes": [list(sh)], "advancers": [pid]}
            events.append("the capturing unit may advance into the fortress "
                          "even though no combat unit defended it [16.3]")
        self._rommel_displacement(events)
        return {"captured": spid, "events": events,
                "note": "supply captured by attack — it may not move or "
                        "sustain attacks this turn [15.23/15.33]"}

    # ------------------------------------------------------------ replacements 20
    def _propose_replace(self, side, action):
        cfg = self.repl_cfg
        if not cfg or not self.combat:
            return self._v(False, "no replacement rules in this scenario")
        if self.s["turn"] < cfg["start_turn"]:
            return self._v(False, f"replacements begin "
                                  f"{self.turn_label(cfg['start_turn'])} [20.1]")
        err = self._no_moves_yet("replacement placement", "3.1/3.3, 20.4")
        if err:
            return err
        if self.s["phase"] != "movement":
            return self._v(False, "placements precede movement [20.4, 19.2]")
        pid = str(action.get("unit"))
        if pid not in self.s["dead"]:
            return self._v(False, "replacements are taken only from units "
                                  "already eliminated [20.1]")
        slot, uside = self.catalog.get(pid, (None, None))
        if uside != side:
            return self._v(False, "you may replace only your own units [20.1]")
        if self.game.unit_class(slot) is not None:
            return self._v(False, "supply and headquarters units are not "
                                  "replacements — supply arrives under rule 12 "
                                  "[20.1]")
        if self._unit_type(slot) is not None and slot in (
                (self.game.spec.get("unit_types") or {}).get("substitute_slots") or {}):
            return self._v(False, "substitute units may not be brought onto "
                                  "the board as replacements [21.6]")
        cost = self.game.stats(slot)[0]
        have = self.s["repl"].get(side, 0)
        if cost > have:
            return self._v(False, f"'{slot}' costs {cost} replacement "
                                  f"factor(s); {side} has {have} accumulated "
                                  f"[20.2/20.3, 20.5]")
        port = tuple(action.get("port") or ())
        if not self._port_ok(side, port):
            return self._v(False, "replacements enter like reinforcements: "
                                  "Tobruch or your own home base, controlled "
                                  "at the start of the player turn [20.4, "
                                  "19.2, 4.3]")
        v = self._v(True)
        v["cost"] = cost
        v["slot"] = slot
        return v

    def _apply_replace(self, side, action, verdict):
        s = self.s
        pid = str(action["unit"])
        s["repl"][side] -= verdict["cost"]
        s["dead"].remove(pid)
        s["units"][pid] = {"pid": pid, "slot": verdict["slot"], "side": side,
                           "col": action["port"][0], "row": action["port"][1]}
        events = []
        self._capture_sweep(events, side, "movement")
        return {"placed": pid, "slot": verdict["slot"],
                "at": list(action["port"]), "cost": verdict["cost"],
                "remaining": s["repl"][side], "events": events,
                "note": "replacement enters per the reinforcement rules; it "
                        "may move and fight this turn [20.4, 19.2]"}

    # ------------------------------------------------------------ AV 9
    def _propose_declare_av(self, side, action):
        if not self.combat:
            return self._v(False, "no combat rules encoded for this game")
        if self.s["phase"] != "movement":
            return self._v(False, "Automatic Victory is achieved during the "
                                  "movement portion of the turn [9.1/9.2]")
        dpid = str(action.get("defender"))
        du = self.s["units"].get(dpid)
        enemy = self.game.enemy(side)
        if not du or du["side"] != enemy or not self._is_combat(du):
            return self._v(False, "the AV target must be an enemy combat unit "
                                  "on the map [9.1]")
        dh = (du["col"], du["row"])
        defenders = [b["pid"] for b in self._combat_units(enemy)
                     if (b["col"], b["row"]) == dh]
        if any(p in self._av_negated() for p in defenders):
            return self._v(False, "that unit's ZOC is already negated [9.1]")
        atk_ids = [str(p) for p in (action.get("attackers") or [])]
        if not atk_ids:
            return self._v(False, "name the attacking units in position [9.1]")
        attackers = []
        frozen = {p for e in self.s["av"] for p in e["attackers"] + e["blockers"]}
        for pid in atk_ids:
            u = self.s["units"].get(pid)
            if not u or u["side"] != side or not self._is_combat(u):
                return self._v(False, f"attacker '{pid}' is not one of your "
                                      f"combat units on the map")
            if pid in frozen:
                return self._v(False, f"'{u['slot']}' is already committed to "
                                      f"an AV this turn [9.2/9.3]")
            if not self._engageable((u["col"], u["row"]), dh):
                return self._v(False, f"'{u['slot']}' is not adjacent to the "
                                      f"AV target [9.1, 8.5]")
            attackers.append(u)
        blk_ids = [str(p) for p in (action.get("blockers") or [])]
        for pid in blk_ids:
            u = self.s["units"].get(pid)
            if not u or u["side"] != side or not self._is_combat(u):
                return self._v(False, f"blocker '{pid}' is not one of your "
                                      f"combat units on the map [9.3]")
        dus = [self.unit(p) for p in defenders]
        att, deff = self._battle_factors(attackers, dus)
        n, d = self.game.odds(att, deff)
        col = self.game.odds_column(n, d)
        if col != "auto_elim":
            if not (d == 1 and n >= 5):
                return self._v(False, f"odds {att}:{deff} = {n}-{d} — an AV "
                                      f"needs 7-1, or 5-1 with the defender "
                                      f"surrounded [9.1]")
            if self._survival_assignment_exists(defenders):
                return self._v(False, f"odds are {n}-1 but the defender could "
                                      f"survive a 'back 2' result — no AV "
                                      f"below 7-1 unless surrounded [9.1]")
        spid = str(action.get("supply") or "")
        su = self.s["units"].get(spid)
        if not su or su["side"] != side or not self.on_map(su) \
           or self.game.unit_class(su["slot"]) != "supply":
            return self._v(False, "an AV must be sustained by a named supply "
                                  "unit at the instant it is achieved [9.2, "
                                  "9.6, 14.6]")
        if spid in self.s["no_sustain"]:
            return self._v(False, "a supply captured this turn during combat/"
                                  "retreat/advance cannot sustain attacks "
                                  "[15.33]")
        rad = self.combat["attack_supply"]["radius"]
        for a in attackers:
            # 9.2 + clarifications sec 10: at the DECLARATION instant the
            # defender's ZOC still blocks the supply route — no carve-out
            if not self._trace_reaches((a["col"], a["row"]), side,
                                       [(su["col"], su["row"])], radius=rad):
                return self._v(False,
                    f"'{a['slot']}' cannot trace {rad} ZOC-free hexes to "
                    f"'{su['slot']}' at the instant of the AV — the target's "
                    f"own ZOC still blocks until the AV is achieved [9.2, "
                    f"clarifications sec 10]")
        v = self._v(True)
        v["defenders"] = defenders
        v["odds"] = f"{n}-{d}"
        return v

    def _apply_declare_av(self, side, action, verdict):
        s = self.s
        atk = [str(p) for p in action["attackers"]]
        blk = [str(p) for p in (action.get("blockers") or [])]
        entry = {"defenders": verdict["defenders"], "attackers": atk,
                 "blockers": blk, "supply": str(action["supply"])}
        s["av"].append(entry)
        events = []
        for pid in atk + blk:
            if pid not in s["moved"]:
                s["moved"][pid] = {"av_frozen": True}
        names = ", ".join(self.unit(p)["slot"] for p in verdict["defenders"])
        events.append(f"AUTOMATIC VICTORY declared at {verdict['odds']} — the "
                      f"ZOC of {names} is negated for the rest of this turn; "
                      f"units may move through its hexes and over the unit "
                      f"itself, but not end on it; the AVing units are frozen "
                      f"until the combat portion [9.1-9.3]")
        self._capture_sweep(events, side, "movement")
        return {"defenders": verdict["defenders"], "odds": verdict["odds"],
                "events": events}

    # ------------------------------------------------------------ substitutes 21
    def _unit_type(self, slot):
        ut = self.game.spec.get("unit_types")
        if not ut:
            return None
        for t in ("armor", "armored_infantry", "recce"):
            if slot in ut.get(t, []):
                return t
        return ut.get("default", "infantry")

    def _sub_window(self, side):
        cfg = self.sub_cfg
        if not cfg or not self.combat:
            return self._v(False, "no substitute rules in this scenario")
        if side != cfg["side"]:
            return self._v(False, f"only the {cfg['side']} player has "
                                  f"substitute counters [21.1]")
        if self.s["turn"] < cfg["start_turn"]:
            return self._v(False, f"substitutes become available "
                                  f"{self.turn_label(cfg['start_turn'])} [21.1]")
        if self.s["phase"] != "combat" or self.s["fought"] \
           or self.s["pending"]:
            return self._v(False, "substitution occurs at the end of the "
                                  "movement portion, before battles are "
                                  "resolved [21.2]")
        return None

    def _propose_substitute(self, side, action):
        err = self._sub_window(side)
        if err:
            return err
        pids = [str(p) for p in (action.get("units") or [])]
        if not pids or len(set(pids)) != len(pids):
            return self._v(False, "name the on-board units being exchanged "
                                  "[21.1]")
        units = []
        for pid in pids:
            u = self.s["units"].get(pid)
            if not u or u["side"] != side or not self._is_combat(u):
                return self._v(False, f"'{pid}' is not one of your combat "
                                      f"units on the map — substitution may "
                                      f"not take place at sea or off-board "
                                      f"[21.6]")
            units.append(u)
        hexes = {(u["col"], u["row"]) for u in units}
        if len(hexes) != 1:
            return self._v(False, "all units involved in the substitution "
                                  "must end the movement portion in the same "
                                  "hex [21.2]")
        sub_pid = str(action.get("sub"))
        ut = self.game.spec.get("unit_types") or {}
        subs = ut.get("substitute_slots") or {}
        e = self.reserve.get(sub_pid)
        if not e or e["slot"] not in subs:
            return self._v(False, "not a substitute counter — only the units "
                                  "provided specifically as substitutes can "
                                  "be used [21.7]")
        if sub_pid in self.s["units"] or sub_pid in self.s["dead"]:
            return self._v(False, "that substitute counter is not available")
        stype = subs[e["slot"]]
        allowed = ut["exchange_classes"][stype]
        for u in units:
            if self._unit_type(u["slot"]) not in allowed:
                return self._v(False,
                    f"'{u['slot']}' is {self._unit_type(u['slot'])} — a "
                    f"{stype} substitute exchanges only for "
                    f"{' or '.join(allowed)} (counter-face symbols) [21.1]")
        total = sum(self.game.stats(u["slot"])[0] for u in units)
        sub_att = self.game.stats(e["slot"])[0]
        if total != sub_att:
            return self._v(False, f"exchanged units total {total} attack "
                                  f"factors; the substitute is {sub_att} — "
                                  f"totals must be the same [21.1]")
        v = self._v(True)
        v["hex"] = list(hexes.pop())
        v["slot"] = e["slot"]
        return v

    def _apply_substitute(self, side, action, verdict):
        s = self.s
        pids = [str(p) for p in action["units"]]
        mfs = [self.game.stats(self.unit(p)["slot"])[2] for p in pids]
        for pid in pids:
            del s["units"][pid]
            s["sub_stock"].append(pid)
        sub_pid = str(action["sub"])
        s["units"][sub_pid] = {"pid": sub_pid, "slot": verdict["slot"],
                               "side": side,
                               "col": verdict["hex"][0],
                               "row": verdict["hex"][1]}
        s["moved"][sub_pid] = {"substituted": True}
        s["sub_comp"][sub_pid] = {"units": pids, "max_mf": max(mfs)}
        return {"formed": verdict["slot"], "at": verdict["hex"],
                "from": pids,
                "note": "the substitute may not move this turn but may "
                        "attack [21.2]"}

    def _propose_breakdown(self, side, action):
        err = self._sub_window(side)
        if err:
            return err
        sub_pid = str(action.get("sub"))
        u = self.s["units"].get(sub_pid)
        ut = self.game.spec.get("unit_types") or {}
        subs = ut.get("substitute_slots") or {}
        if not u or u["side"] != side or u["slot"] not in subs:
            return self._v(False, "only a substitute counter on the map can "
                                  "be broken down [21.3]")
        pids = [str(p) for p in (action.get("into") or [])]
        if not pids or len(set(pids)) != len(pids):
            return self._v(False, "name the component units [21.3]")
        stype = subs[u["slot"]]
        allowed = ut["exchange_classes"][stype]
        comp = self.s["sub_comp"].get(sub_pid, {})
        total = 0
        for pid in pids:
            if pid not in self.s["sub_stock"]:
                return self._v(False, "components come from units previously "
                                      "exchanged away by substitution [21.3]")
            slot, uside = self.catalog[pid]
            if uside != side or self._unit_type(slot) not in allowed:
                return self._v(False, f"'{slot}' is not of the same type "
                                      f"[21.1, 21.3]")
            if self.game.stats(slot)[2] > self.game.stats(u["slot"])[2] \
               and pid not in comp.get("units", []):
                return self._v(False,
                    f"'{slot}' moves faster than the substitute — a breakdown "
                    f"may not generate a faster unit unless it originally "
                    f"formed this substitute [21.4]")
            total += self.game.stats(slot)[0]
        if total > self.game.stats(u["slot"])[0]:
            return self._v(False, f"components total {total} attack factors — "
                                  f"more than the substitute's "
                                  f"{self.game.stats(u['slot'])[0]} [21.4]")
        if len(pids) > int((self.game.stacking or {}).get("max", 3)):
            return self._v(False, "the components would exceed the stacking "
                                  "limit [21.5, 6.1]")
        return self._v(True)

    def _apply_breakdown(self, side, action):
        s = self.s
        sub_pid = str(action["sub"])
        u = self.unit(sub_pid)
        hx = [u["col"], u["row"]]
        del s["units"][sub_pid]
        s["sub_comp"].pop(sub_pid, None)
        placed = []
        for pid in [str(p) for p in action["into"]]:
            s["sub_stock"].remove(pid)
            slot, _ = self.catalog[pid]
            s["units"][pid] = {"pid": pid, "slot": slot, "side": side,
                               "col": hx[0], "row": hx[1]}
            s["moved"][pid] = {"breakdown": True}
            placed.append(slot)
        return {"broke": u["slot"], "into": placed, "at": hx,
                "note": "components placed in the substitute's hex [21.3]"}

    def _propose_advance(self, side, action):
        pend = self.s["pending"]
        if not pend or pend["kind"] != "advance":
            return self._v(False, "no advance after combat is available — the "
                                  "option lapses when the next battle is "
                                  "resolved [16.1, 8.6]")
        pid = str(action.get("unit"))
        if pid not in pend["advancers"]:
            return self._v(False, "only surviving attacking units of that "
                                  "battle may advance [16.1]")
        u = self.s["units"].get(pid)
        if not u:
            return self._v(False, "unit no longer on the board")
        hx = tuple(action.get("hex") or ())
        if list(hx) not in pend["hexes"]:
            return self._v(False, "advance is only into the fortress or "
                                  "escarpment hex vacated by the defender "
                                  "[16.1]")
        if not self._engageable((u["col"], u["row"]), hx):
            return self._v(False, "advancing unit must be adjacent to the "
                                  "vacated hex [16.1, 8.5]")
        me = dict(id=u["pid"], name=u["slot"], side=u["side"],
                  col=u["col"], row=u["row"])
        if not self.game._stack_ok(me, hx, self.rules_board()):
            return self._v(False, "advance may not exceed stacking limits "
                                  "[16.1, 6.1]")
        return self._v(True)

    def _propose_retreat(self, side, action):
        pend = self.s["pending"]
        if not pend or pend["kind"] != "retreat":
            return self._v(False, "no retreat is pending")
        if side != pend["chooser"]:
            return self._v(False, f"the {pend['chooser']} player retreats the "
                                  f"losing units — the winner chooses the "
                                  f"route [7.5, 7.6]")
        pid = str(action.get("unit"))
        if pid not in pend["units"]:
            return self._v(False, "that unit is not awaiting retreat from "
                                  "this battle")
        u = self.s["units"].get(pid)
        board, ezoc, eblock = self._retreat_env(u["side"])
        paths = self._retreat_paths(u, ezoc, eblock, board)
        remaining = [p for p in pend["units"] if p != pid]
        if action.get("eliminate"):
            if self._survival_assignment_exists(pend["units"]):
                return self._v(False,
                    "routes exist that let every retreating unit survive — "
                    "the winner may not choose eliminations while they do "
                    "[7.61, 7.62 + clarifications 7]")
            return self._v(True)
        path = [tuple(h) for h in (action.get("path") or [])]
        dist = self.combat["retreat"]["distance"]
        if len(path) != dist:
            return self._v(False, f"a retreat is exactly {dist} hexes — zigzag "
                                  f"allowed, ending one hex away is legal "
                                  f"[7.5, 7.6]")
        legal = [list(h) for h in path] in paths.get(path[-1], [])
        if not legal:
            return self._v(False,
                "illegal retreat route — each hex must be playable terrain "
                "free of enemy ZOC and enemy units, no prohibited hexside, "
                "no hex entered twice, never back into the battle hex, and "
                "the final hex must respect stacking [7.6, 7.61, "
                "clarifications 9]")
        if self._survival_assignment_exists(pend["units"]) and remaining:
            if not self._survival_assignment_exists(remaining,
                                                    extra_used=[path[-1]]):
                return self._v(False,
                    "this route would force another retreating unit into "
                    "elimination — the winner must choose routes that let "
                    "ALL retreating units live when possible [7.62 + "
                    "clarifications 7]")
        return self._v(True)

    def _propose_exchange_loss(self, side, action):
        pend = self.s["pending"]
        if not pend or pend["kind"] != "exchange":
            return self._v(False, "no exchange is being settled")
        if side != pend["winner"]:
            return self._v(False, f"the {pend['winner']} player owes the "
                                  f"exchange losses [7.5]")
        pids = [str(p) for p in (action.get("units") or [])]
        if not pids or len(set(pids)) != len(pids):
            return self._v(False, "name the units removed to satisfy the "
                                  "exchange [7.5]")
        for pid in pids:
            if pid not in pend["involved"]:
                return self._v(False, "exchange losses come only from units "
                                      "actually involved in that battle [7.5]")
        total = 0
        for pid in pids:
            u = self.unit(pid)
            total += self._exchange_factor(u, pend["winner_is_attacker"])
        owe = pend["owe"]
        if total < owe:
            return self._v(False, f"removed factors {total} do not reach the "
                                  f"opponent's {owe} — the exchange removes "
                                  f"units totaling AT LEAST that [7.5]")
        for pid in pids:
            u = self.unit(pid)
            if total - self._exchange_factor(u, pend["winner_is_attacker"]) >= owe:
                return self._v(False, f"'{u['slot']}' is not needed to reach "
                                      f"{owe} — the exchange removes the "
                                      f"number of units whose factors total "
                                      f"at least the opponent's, no more "
                                      f"[7.5]")
        return self._v(True)

    def _exchange_factor(self, u, as_attacker):
        """7.5: attacker counts attack factors (never terrain-affected,
        8.7); defender counts defense at basic or double value per terrain."""
        if as_attacker:
            return self.game.stats(u["slot"])[0]
        return self.game.defense_factor(u["slot"], (u["col"], u["row"]))

    def _propose_place_rommel(self, side, action):
        pr = self.s["pending_rommel"]
        if not pr:
            return self._v(False, "no headquarters placement is pending")
        u = self.unit(pr["unit"])
        if u["side"] != side:
            return self._v(False, f"the {u['side']} player places his own "
                                  f"headquarters unit [22.42]")
        hx = list(action.get("hex") or ())
        if hx not in pr["choices"]:
            names = ", ".join(self.game.grid.display_name(*h)
                              for h in pr["choices"])
            return self._v(False, f"placement must be with one of the closest "
                                  f"friendly combat units: {names} [22.4, 22.42]")
        return self._v(True)

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
        if self.s["phase"] == "combat" and u["pid"] in self.s["cap_move"]:
            dest = tuple(action.get("dest") or ())
            dd = self._cap_move_dests(u)
            if dest not in dd:
                return self._v(False, "not a legal destination for the "
                                      "captured supply [15.33, 15.34]")
            v = self._v(True)
            v["cost"] = dd[dest]
            v["cap_move"] = True
            return v
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
                err = self._fig3_guard(u, dest)
                if err:
                    return err
                v["cost"] = len(path) - 1
            return v
        dd = self.dests(u)
        if dest not in dd:
            ma = self.budget(u)
            return self._v(False, f"not a legal destination for this unit "
                                  f"(MF {ma}) — movement 5.2/5.4, stacking 6.1, "
                                  f"ZOC 7.1/8.1/8.3, roads 17, escarpments 18")
        err = self._fig3_guard(u, dest)
        if err:
            return err
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
            if verdict.get("cap_move"):
                s["cap_move"].pop(u["pid"], None)
            if action.get("path"):
                s["paths"][u["pid"]] = [list(h) for h in action["path"]]
            if action.get("rommel_bonus"):
                s["bonus"][u["pid"]] = int(action["rommel_bonus"])
            events = []
            if self.combat:
                self._capture_sweep(events, side, "movement")
                self._rommel_displacement(events)
            return {"from": old, "to": [u["col"], u["row"]],
                    "cost": verdict.get("cost"), "events": events}
        if t == "end_movement":
            return self._apply_end_movement(side, verdict)
        if t == "battle":
            return self._apply_battle(side, action, verdict)
        if t == "retreat":
            return self._apply_retreat(side, action)
        if t == "exchange_loss":
            return self._apply_exchange_loss(side, action)
        if t == "advance":
            return self._apply_advance(side, action)
        if t == "forced_elim":
            return self._apply_forced_elim(side, action)
        if t == "destroy_supply":
            return self._apply_destroy_supply(side, action)
        if t == "capture_supply":
            return self._apply_capture_supply(side, action, verdict)
        if t == "replace":
            return self._apply_replace(side, action, verdict)
        if t == "declare_av":
            return self._apply_declare_av(side, action, verdict)
        if t == "substitute":
            return self._apply_substitute(side, action, verdict)
        if t == "breakdown":
            return self._apply_breakdown(side, action)
        if t == "place_rommel":
            u = self.unit(s["pending_rommel"]["unit"])
            u["col"], u["row"] = action["hex"]
            s["pending_rommel"] = None
            return {"placed": u["pid"], "at": list(action["hex"]),
                    "note": "headquarters placed with the chosen closest "
                            "friendly combat unit [22.4, 22.42]"}
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
            # the pool holds recycled supply too (14.1 consumed / 15 captured),
            # whose ids are scenario-deployed units, not reserve entries — so
            # resolve the counter from the full catalog, not just the reserve
            slot = self.catalog[pid][0]
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
            events = []
            if self.combat:
                self._capture_sweep(events, side, "movement")
            return {"placed": pid, "slot": e["slot"], "at": list(action["port"]),
                    "due": self.turn_label(e["due"]), "events": events,
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
            events = []
            if self.combat:
                self._capture_sweep(events, side, "movement")
            return {"landed": u["pid"], "at": list(action["port"]),
                    "events": events,
                    "note": "may move inland this turn; may not go back out "
                            "to sea [23.4, 23.42]"}
        # end_phase
        notes = []
        if self.combat:
            # 24.2/24.5 end-of-turn isolation checks run while consumed
            # supplies are still on the board (they are removed AT the end,
            # 14.1 — a wrong auto-elimination is worse than a lenient order)
            self._isolation_end_of_turn(side, notes)
            for spid in sorted(set(s["supplies_used"])):
                self._recycle_supply(spid, notes,
                                     "used to sustain attacks — removed at "
                                     "the end of the player turn, the counter "
                                     "returns to the off-board pool [14.1]")
            self._check_elimination_victory(notes)
            # 4.1/4.2 control victory: both fortresses + both home bases at
            # the start AND end of two consecutive own player turns
            end_ok = self._controls_objectives(side)
            streak = s["vic_streak"].get(side, 0)
            streak = streak + 1 if (s["vic_start_ok"] and end_ok) else 0
            s["vic_streak"][side] = streak
            if streak >= 2 and not s["over"]:
                s["over"] = True
                s["winner"] = side
                notes.append(f"{side} has controlled both fortresses and both "
                             f"home bases at the start and end of two "
                             f"consecutive player turns — {side} WINS "
                             f"[4.1/4.2, 4.3]")
        if side == "Axis" and s["supply_pending"]:
            s["supply_pending"] = False
            notes.append("arrived Axis supply unit was not landed — forfeited; "
                         "supply may not accumulate off board [12.4]")
        lost_at_sea = [u for u in s["units"].values()
                       if u["side"] == side and not self.on_map(u)
                       and u.get("embark_turn", s["turn"]) < s["turn"]]
        for u in lost_at_sea:
            del s["units"][u["pid"]]
            s["dead"].append(u["pid"])
            notes.append(f"'{u['slot']}' failed to return to a port on the turn "
                         f"following its removal from the board — ELIMINATED [23.42]")
        s["moved"] = {}
        s["paths"] = {}
        s["bonus"] = {}
        s["landed_sea"] = []
        s["phase"] = "movement"
        s["attacked"] = {}
        s["defended"] = {}
        s["fought"] = []
        s["supplies_used"] = []
        s["pending"] = None
        s["av"] = []
        s["cap_attacks"] = []
        s["no_sustain"] = []
        s["cap_move"] = {}
        if s["over"]:
            return {"note": f"GAME OVER — {s['winner']} wins." if s["winner"]
                            else "GAME OVER.",
                    "over": True, "winner": s["winner"], "events": notes}
        other = self.game.enemy(side)
        if side == self.first_player:
            s["mover"] = other
            s["allied_supply_done"] = False
            s["ports"] = self._controlled_ports(other)
            if self.combat:
                s["vic_start_ok"] = self._controls_objectives(other)
                s["iso_start"] = self._iso_snapshot(other)
                s["nosup_start"] = not self._supply_hexes(other)
                self._repl_accrue(other, notes)
            return {"note": f"{side} player turn over — {other} moves now [3.3]",
                    "events": notes}
        s["turn"] += 1
        s["mover"] = self.first_player
        s["supply_rolled"] = False
        s["ports"] = self._controlled_ports(self.first_player)
        if self.combat:
            s["vic_start_ok"] = self._controls_objectives(self.first_player)
            s["iso_start"] = self._iso_snapshot(self.first_player)
            s["nosup_start"] = not self._supply_hexes(self.first_player)
            self._repl_accrue(self.first_player, notes)
        if s["turn"] > self.turns:
            s["over"] = True
            unlanded = sorted(self.schedule[pid]["slot"] for pid in s["pool"])
            s["pool"] = {}
            if unlanded:
                notes.append("reinforcements not in play by the last October "
                             "1942 turn are eliminated [19.8]: "
                             + ", ".join(unlanded))
            if self.combat:
                s["winner"] = "Allied" if "Allied" in self.game.side_order else None
                note = ("GAME OVER — final turn complete. The Allied player "
                        "wins by avoiding the Axis victory conditions through "
                        "the last October 1942 turn [4.2].")
            else:
                note = ("GAME OVER — final turn complete. Victory conditions "
                        "(4.1/4.2) require combat resolution: not in Tier-1 "
                        "scope, no winner adjudicated.")
            return {"note": note, "turn": s["turn"], "over": True,
                    "winner": s.get("winner"), "events": notes}
        return {"note": f"game turn complete — {self.turn_label()} begins, "
                        f"{self.first_player} moves first [3.5]",
                "turn": s["turn"], "over": False, "events": notes}

    # ------------------------------------------------------------ combat apply
    def _apply_end_movement(self, side, verdict=None):
        s = self.s
        s["phase"] = "combat"
        events = []
        for e, sups in zip(s["av"], (verdict or {}).get("av_supplies", [])):
            for spid in sups:
                if spid not in s["supplies_used"]:
                    s["supplies_used"].append(spid)
            if len(sups) > 1:
                events.append("the supply sustaining an AV changed during "
                              "movement — BOTH supplies are expended [14.5]")
        # 11.9: attacking units isolated in enemy ZOC with no supply-free
        # attack are eliminated before combat (clarifications sec. 5)
        board = self.rules_board()
        ezoc = self.game.zoc_hexes(board, self.game.enemy(side))
        for u in list(self._combat_units(side)):
            if (u["col"], u["row"]) not in ezoc:
                continue
            if self._isolated(u) and not self._supply_free_attack_exists(u):
                self._remove_units([u["pid"]], events,
                                   "isolated in enemy ZOC with no legal "
                                   "supply-free attack — eliminated before "
                                   "the combat phase [11.9, 24.1, 14.3]")
        self._rommel_displacement(events)
        self._check_elimination_victory(events)
        must_attack, must_be = self._obligations(side)
        return {"note": "movement portion over — all battles caused by "
                        "movement are now resolved one at a time [3.2/3.4, 8.6]",
                "events": events,
                "must_attack": must_attack, "must_be_attacked": must_be}

    def _battle_no(self):
        return len(self.s["fought"])

    def _apply_battle(self, side, action, verdict):
        s = self.s
        atk_ids = [str(p) for p in action["attackers"]]
        def_ids = [str(p) for p in action["defenders"]]
        attackers = [self.unit(p) for p in atk_ids]
        defenders = [self.unit(p) for p in def_ids]
        n = self._battle_no()
        for pid in atk_ids:
            s["attacked"][pid] = n
        for pid in def_ids:
            s["defended"][pid] = n
        s["fought"].append({
            "attackers": atk_ids, "defenders": def_ids,
            "ahex": {p: [self.unit(p)["col"], self.unit(p)["row"]]
                     for p in atk_ids},
            "dhex": {p: [self.unit(p)["col"], self.unit(p)["row"]]
                     for p in def_ids}})
        s["pending"] = None                     # a lapsed advance option
        if verdict.get("supply"):
            if verdict["supply"] not in s["supplies_used"]:
                s["supplies_used"].append(verdict["supply"])
        col = verdict["column"]
        events = []
        if col == "auto_elim":
            roll = None
            code = "DE"
            events.append(f"odds {verdict['odds']} are greater than 6-1 — "
                          f"automatic elimination, no die is rolled [7.4, "
                          f"9.1, printed CRT note]")
        else:
            roll = self.roll_die()
            code = self.game.crt_result(col, roll)
        res = {"odds": verdict["odds"], "factors": verdict["factors"],
               "column": col, "roll": roll, "result": code,
               "meaning": self.combat["crt"]["results"][code],
               "battle": n, "events": events}
        dbl_def_hexes = [list(h) for h in
                         {tuple(hh) for hh in s["fought"][n]["dhex"].values()
                          if self.game.hex_terrain(*hh)
                          in self.combat["advance"]["into_terrain"]}]
        if code == "AE":
            self._remove_units(atk_ids, events, "A Elim [7.5]")
        elif code == "DE":
            self._remove_units(def_ids, events, "D Elim [7.5]")
            self._offer_advance(n, atk_ids, dbl_def_hexes, events)
        elif code == "EX":
            att, deff = verdict["factors"]
            if att == deff:
                self._remove_units(atk_ids + def_ids, events,
                                   "Exchange with equal factors — both sides "
                                   "remove all involved units [7.5]")
                self._offer_advance(n, [], dbl_def_hexes, events)
            elif att < deff:
                self._remove_units(atk_ids, events,
                                   "Exchange — the attacker had fewer "
                                   "involved factors [7.5]")
                s["pending"] = {"kind": "exchange", "battle": n,
                                "winner": self.game.enemy(side),
                                "winner_is_attacker": False,
                                "owe": att, "involved": def_ids,
                                "vac_hexes": [], "advancers": []}
                events.append(f"the defender removes involved units totaling "
                              f"at least {att} defense factors [7.5]")
            else:
                self._remove_units(def_ids, events,
                                   "Exchange — the defender had fewer "
                                   "involved factors [7.5]")
                s["pending"] = {"kind": "exchange", "battle": n,
                                "winner": side, "winner_is_attacker": True,
                                "owe": deff, "involved": atk_ids,
                                "vac_hexes": dbl_def_hexes,
                                "advancers": atk_ids}
                events.append(f"the attacker removes involved units totaling "
                              f"at least {deff} attack factors [7.5]")
        elif code in ("AB2", "DB2"):
            losers = atk_ids if code == "AB2" else def_ids
            chooser = self.game.enemy(side) if code == "AB2" else side
            s["pending"] = {"kind": "retreat", "battle": n,
                            "units": list(losers), "chooser": chooser,
                            "advance_after": code == "DB2",
                            "vac_hexes": dbl_def_hexes if code == "DB2" else [],
                            "advancers": atk_ids if code == "DB2" else []}
            events.append(f"the {chooser} player (the winner) now retreats "
                          f"each losing unit two hexes [7.5, 7.6]")
        self._capture_sweep(events, side, "battle")
        self._rommel_displacement(events)
        self._check_elimination_victory(events)
        return res

    def _offer_advance(self, battle, advancer_ids, candidate_hexes, events):
        """16.1: advance is available into vacated fortress/escarpment hexes."""
        alive = [p for p in advancer_ids if p in self.s["units"]]
        vac = []
        for h in candidate_hexes:
            occ = any(self._is_combat(u) and [u["col"], u["row"]] == list(h)
                      for u in self.s["units"].values())
            if not occ:
                vac.append(list(h))
        if alive and vac:
            self.s["pending"] = {"kind": "advance", "battle": battle,
                                 "hexes": vac, "advancers": alive}
            names = ", ".join(self.game.grid.display_name(*h) for h in vac)
            events.append(f"surviving attackers may advance into the vacated "
                          f"{names} before the next battle [16.1]")

    def _apply_retreat(self, side, action):
        s = self.s
        pend = s["pending"]
        pid = str(action["unit"])
        events = []
        u = self.unit(pid)
        if action.get("eliminate"):
            self._remove_units([pid], events,
                               "no retreat route lets it survive — eliminated "
                               "instead of retreating [7.61]")
            res = {"eliminated": pid, "events": events}
        else:
            old = [u["col"], u["row"]]
            path = [list(h) for h in action["path"]]
            u["col"], u["row"] = path[-1]
            res = {"from": old, "path": path, "events": events,
                   "note": "retreated two hexes by the winner [7.5, 7.6]"}
        pend["units"] = [p for p in pend["units"] if p != pid]
        if not pend["units"]:
            s["pending"] = None
            if pend.get("advance_after"):
                self._offer_advance(pend["battle"], pend["advancers"],
                                    pend["vac_hexes"], events)
        if u["pid"] in s["units"]:       # 15.22: capture along the route too
            self._capture_sweep(events, u["side"], "retreat",
                                near_hexes=action.get("path") or [])
        self._rommel_displacement(events)
        self._check_elimination_victory(events)
        return res

    def _apply_exchange_loss(self, side, action):
        s = self.s
        pend = s["pending"]
        pids = [str(p) for p in action["units"]]
        events = []
        self._remove_units(pids, events, "removed to satisfy the exchange [7.5]")
        s["pending"] = None
        if pend["winner_is_attacker"]:
            survivors = [p for p in pend["involved"] if p in s["units"]]
            self._offer_advance(pend["battle"], survivors,
                                pend["vac_hexes"], events)
        self._capture_sweep(events, side, "battle")
        self._rommel_displacement(events)
        self._check_elimination_victory(events)
        return {"removed": pids, "events": events}

    def _apply_advance(self, side, action):
        s = self.s
        pend = s["pending"]
        pid = str(action["unit"])
        u = self.unit(pid)
        old = [u["col"], u["row"]]
        u["col"], u["row"] = action["hex"]
        pend["advancers"] = [p for p in pend["advancers"] if p != pid]
        if not pend["advancers"]:
            s["pending"] = None
        events = []
        self._capture_sweep(events, side, "advance")
        self._rommel_displacement(events)
        return {"from": old, "to": list(action["hex"]), "events": events,
                "note": "advance after combat into the vacated hex [16.1, 16.2]"}

    def _apply_forced_elim(self, side, action):
        s = self.s
        pid = str(action["unit"])
        events = []
        self._remove_units([pid], events,
                           "forced to attack at odds worse than 1-6 — "
                           "eliminated before any battle, no soak-off, no "
                           "blocking ZOC [7.4]")
        s["pending"] = None
        self._capture_sweep(events, side, "battle")
        self._rommel_displacement(events)
        self._check_elimination_victory(events)
        return {"eliminated": pid, "events": events}

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
        dd = self._cap_move_dests(u) \
            if self.s["phase"] == "combat" and pid in self.s["cap_move"] \
            else self.dests(u)
        for (c, r), cost in sorted(dd.items()):
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
        repl = None
        if self.repl_cfg and self.combat and s["turn"] >= self.repl_cfg["start_turn"]:
            dead = []
            for pid in s["dead"]:
                slot, uside = self.catalog.get(pid, (None, None))
                if uside != side or self.game.unit_class(slot) is not None:
                    continue
                if slot in ((self.game.spec.get("unit_types") or {})
                            .get("substitute_slots") or {}):
                    continue
                dead.append(dict(pid=pid, slot=slot,
                                 cost=self.game.stats(slot)[0]))
            repl = dict(points=s["repl"].get(side, 0),
                        dead=sorted(dead, key=lambda d: d["cost"]))
        return dict(due=due, at_sea=at_sea, ports=ports, supply=supply,
                    replacements=repl,
                    placements_open=not s["moved"])

    def combat_panel(self):
        """Everything the UI needs to drive the combat phase."""
        if not self.combat:
            return None
        s = self.s
        side = s["mover"]
        must_attack, must_be = self._obligations(side)
        pend = s["pending"]
        pinfo = None
        if pend:
            pinfo = dict(kind=pend["kind"], battle=pend.get("battle"))
            if pend["kind"] == "retreat":
                pinfo["chooser"] = pend["chooser"]
                pinfo["units"] = []
                for p in pend["units"]:
                    u = self.unit(p)
                    board, ezoc, eblock = self._retreat_env(u["side"])
                    paths = self._retreat_paths(u, ezoc, eblock, board)
                    opts = [dict(end=list(h),
                                 name=self.game.grid.display_name(*h),
                                 path=pp[0])
                            for h, pp in sorted(paths.items())]
                    pinfo["units"].append(dict(pid=p, slot=u["slot"],
                                               options=opts))
            elif pend["kind"] == "exchange":
                pinfo["winner"] = pend["winner"]
                pinfo["owe"] = pend["owe"]
                pinfo["involved"] = [dict(pid=p, slot=self.unit(p)["slot"],
                                          factor=self._exchange_factor(
                                              self.unit(p),
                                              pend["winner_is_attacker"]))
                                     for p in pend["involved"]
                                     if p in s["units"]]
            elif pend["kind"] == "advance":
                pinfo["hexes"] = pend["hexes"]
                pinfo["hex_names"] = [self.game.grid.display_name(*h)
                                      for h in pend["hexes"]]
                pinfo["advancers"] = [dict(pid=p, slot=self.unit(p)["slot"])
                                      for p in pend["advancers"]
                                      if p in s["units"]]
        av_offers = []
        if s["phase"] == "movement":
            frozen = {p for e in s["av"] for p in e["attackers"] + e["blockers"]}
            for du in self._combat_units(self.game.enemy(side)):
                if du["pid"] in self._av_negated():
                    continue
                dh = (du["col"], du["row"])
                defenders = [b for b in self._combat_units(self.game.enemy(side))
                             if (b["col"], b["row"]) == dh]
                attackers = [a for a in self._combat_units(side)
                             if a["pid"] not in frozen
                             and self._engageable((a["col"], a["row"]), dh)]
                if not attackers:
                    continue
                att, deff = self._battle_factors(attackers, defenders)
                n, d = self.game.odds(att, deff)
                if self.game.odds_column(n, d) != "auto_elim":
                    continue                     # panel offers 7-1 only
                rad = self.combat["attack_supply"]["radius"]
                sup = next((u["pid"] for u in self.s["units"].values()
                            if u["side"] == side and self.on_map(u)
                            and self.game.unit_class(u["slot"]) == "supply"
                            and u["pid"] not in s["no_sustain"]
                            and all(self._trace_reaches(
                                (a["col"], a["row"]), side,
                                [(u["col"], u["row"])], radius=rad)
                                for a in attackers)), None)
                if not sup:
                    continue
                av_offers.append(dict(
                    defender=du["pid"], slot=du["slot"],
                    hexname=self.game.grid.display_name(*dh),
                    odds=f"{n}-{d}",
                    attackers=[a["pid"] for a in attackers],
                    supply=sup))
        subs = None
        if self.sub_cfg and self.combat and side == self.sub_cfg["side"] \
           and s["turn"] >= self.sub_cfg["start_turn"] \
           and s["phase"] == "combat" and not s["fought"] and not pinfo:
            slots = ((self.game.spec.get("unit_types") or {})
                     .get("substitute_slots") or {})
            avail = [dict(pid=pid, slot=e["slot"],
                          att=self.game.stats(e["slot"])[0])
                     for pid, e in self.reserve.items()
                     if e["slot"] in slots and pid not in s["units"]
                     and pid not in s["dead"]]
            subs = dict(available=sorted(avail, key=lambda a: a["slot"]),
                        stock=len(s["sub_stock"]))
        return dict(
            phase=s["phase"],
            must_attack=[dict(pid=p, slot=self.unit(p)["slot"])
                         for p in must_attack],
            must_be_attacked=[dict(pid=p, slot=self.unit(p)["slot"])
                              for p in must_be],
            battles_fought=len(s["fought"]),
            supplies_used=[dict(pid=p, slot=self.unit(p)["slot"])
                           for p in sorted(set(s["supplies_used"]))
                           if p in s["units"]],
            pending=pinfo,
            pending_rommel=s["pending_rommel"],
            av=[dict(defenders=[dict(pid=p, slot=self.unit(p)["slot"])
                                for p in e["defenders"] if p in s["units"]])
                for e in s["av"]],
            av_offers=av_offers,
            substitutes=subs,
            replacements_from=self.repl_cfg and self.turn_label(
                self.repl_cfg["start_turn"]))

    def battle_preview(self, side, atk_ids, def_ids):
        """Odds/column/supply-need preview for a prospective battle (UI
        helper: read-only, computed by the same code that gates it)."""
        v = self._propose_battle(side, {"type": "battle",
                                        "attackers": atk_ids,
                                        "defenders": def_ids,
                                        "supply": None})
        out = dict(legal=v["legal"], reasons=v["reasons"])
        if "odds" in v:
            out.update(odds=v["odds"], column=v["column"],
                       factors=v["factors"])
        if v["legal"]:
            out["needs_supply"] = False
        elif v["reasons"] and "supply unit sustaining" in v["reasons"][0]:
            # legal except for the supply declaration
            out["needs_supply"] = True
        return out

    def rules_scope(self):
        """The scenario's declared scope, composed for the ACTIVE tier.
        Scenarios may split their enforced list into `enforced` (tier-1
        systems) + `enforced_tier2` (combat systems); at tier 1 the tier-2
        items are presented honestly as not-enforced-in-this-mode."""
        rs = self.scenario.get("rules_scope")
        if not rs:
            return None
        t2 = rs.get("enforced_tier2", [])
        if self.tier >= 2:
            return dict(rs, enforced=rs.get("enforced", []) + t2,
                        enforced_tier2=None)
        note = ("TIER 1 MODE selected (this game has earned Tier "
                f"{self.tier_earned}) — the validated combat systems below "
                "are switched OFF; resolve combat yourself, umpire-style:")
        return dict(rs,
                    enforced=rs.get("enforced", []),
                    enforced_tier2=None,
                    not_enforced=([note] + t2 if t2 else [])
                    + rs.get("not_enforced", []))

    def flow(self):
        s = self.s
        return dict(turn=s["turn"], turns=self.turns,
                    turn_label=self.turn_label(),
                    phase=s["phase"], mover=s["mover"],
                    moved=len(s["moved"]), over=s["over"], winner=s["winner"],
                    overstacked=[self.game.grid.display_name(*h)
                                 for h in self.overstacked_hexes(s["mover"])],
                    seed=s["seed"], n=s["n"],
                    tier=self.tier, tier_earned=self.tier_earned,
                    first_player=self.first_player,
                    scenario=self.scenario["name"],
                    rules_scope=self.rules_scope(),
                    arrivals=self.arrivals_panel(),
                    combat=self.combat_panel())
