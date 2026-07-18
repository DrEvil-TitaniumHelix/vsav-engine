"""
ai_westwall.py - the AI opponent's policy for Westwall quad games
(any WestwallGame).

Doctrine identical to ai_bluegray.py/ai_strategic.py: the policy READS public
state and SUBMITS every proposal through the one legality gate
(WestwallGame.submit). Rejections are logged as proof-of-enforcement. The
policy is a GENERATOR of single gate actions - take_turn drains it,
TurnStepper steps it - so stepped play is byte-identical to whole-turn play.

Policy (honest, not clever - a beta opponent playing a legal, complete,
replayable game):
  arrivals - every due reinforcement enters: airborne spread one-per-hex
    around the printed target [15.31]; ground columns enter at 0105/0106 and
    immediately drive on (clearing the entry hex for the next unit [15.12]);
    German edge groups spread along their printed segments.
  movement - Allied ground units drive up the corridor toward the Arnhem
    road bridge; airborne units stay within LOC range of their divisional DZ
    [17.32] while closing on the nearest enemy; German units close on the
    nearest Allied unit. Nobody voluntarily ends adjacent to enemies the
    local force cannot fight at a non-negative differential (combat is
    mandatory [7.0]). Artillery keeps a barrage standoff [8.11/8.41].
  demolition - the German player attempts every offered bridge [12.11]
    (the historical doctrine).
  combat - discharge every 7.11/7.12 obligation, most-constrained unit
    first, each battle taking ALL of the unit's adjacent un-attacked
    enemies with every legal co-attacker [7.23]; barrage support joins
    within the 14.12 two-artillery cap; the Allied player spends GSP to
    lift poor differentials [9.0/14.11] and burns leftover GSP as FPF in
    the German turn [8.4]. Retreat paths maximize distance from the enemy;
    the city no-effect option is taken whenever legal [11.1]; advances are
    taken onto empty ground, declined otherwise.
Known-weak, declared: no exit play [15.4], no Engineer assault stack
[13.24], no deliberate bridge-line attacks, no diversionary attacks [7.51],
no multi-turn plans. All optional - skipping them is legal.
"""


class _Dist:
    def __init__(self, game):
        self.g = game
        self.c = {}

    def __call__(self, a, b):
        a, b = tuple(a), tuple(b)
        if a == b:
            return 0
        key = (a, b) if a <= b else (b, a)
        v = self.c.get(key)
        if v is None:
            v = self.g.hex_distance(key[0], key[1])
            self.c[key] = v
        return 999 if v is None else v


def _foes(ww, side):
    return {(u["col"], u["row"]): u for u in ww._live(ww.game.enemy(side))}


def _objective(ww, u, dist):
    side = u["side"]
    here = (u["col"], u["row"])
    foes = list(_foes(ww, side))
    pid = u["pid"]
    if side == "All":
        if ww.is_airborne(pid):
            div = ww.cat(pid).get("division")
            dz = next(((x["col"], x["row"]) for x in ww._live("All", dz=True)
                       if ww.cls(x["pid"]) == "dz"
                       and ww.cat(x["pid"])["desig"].startswith(str(div))), here)
            near = [f for f in foes if dist(f, dz) <= 6]
            if near:
                return min(near, key=lambda h: (dist(here, h), h))
            return dz
        return (34, 23)                 # the Arnhem road bridge approach
    if foes:
        return min(foes, key=lambda h: (dist(here, h), h))
    return here


def _local_diff_ok(ww, u, dest, caution=-2):
    """Ending on dest must not create a hopeless mandatory battle [7.0]:
    combined printed attack of us + friends already adjacent to the enemies
    we would touch must be >= their combined defense - 2. caution raises
    (or keeps, at the -2 default) that acceptable-differential floor - the
    plans.py DSL exposes it per order; the policy always plays -2."""
    touch = []
    for h, e in _foes(ww, u["side"]).items():
        if h in ww.game.neighbors(*dest) and not ww._river_no_bridge(dest, h):
            touch.append((h, e))
    if not touch:
        return True
    my = ww.stats(u["pid"]).get("att", 0)
    d_total = 0
    friends = [(x["col"], x["row"], x) for x in ww._live(u["side"])
               if x["pid"] != u["pid"]]
    for h, e in touch:
        d_total += ww.stats(e["pid"])["def"]
        for fc, fr, f in friends:
            if h in ww.game.neighbors(fc, fr) \
               and not ww._river_no_bridge((fc, fr), h):
                my += ww.stats(f["pid"]).get("att", 0)
    return my >= d_total + caution


def _movement_actions(ww, side):
    dist = _Dist(ww.game)
    s = ww.s
    # 1. reinforcements
    due = sorted(pid for pid, d in s["pool"].items() if d <= s["turn"]
                 and ww.reserve[pid]["side"] == side)
    for pid in due:
        e = ww.reserve[pid]
        if e.get("arrival") == "airborne":
            tgt = tuple(e["target"])
            ring = [tgt] + sorted(ww.game.neighbors(*tgt))
            for h in ring:
                if not ww.game.on_map(*h):
                    continue
                okv = yield (side, {"type": "reinforce", "unit": pid,
                                    "hex": list(h)},
                             f"{e['slot']} drops near {tgt} [15.31]")
                if okv:
                    break
        else:
            entry = [tuple(h) for h in e["entry"]]
            placed = False
            for h in entry:
                okv = yield (side, {"type": "reinforce", "unit": pid,
                                    "hex": list(h)},
                             f"{e['slot']} enters at {h} [15.1]")
                if okv:
                    placed = True
                    # clear the entry hex for the column mates [15.12]
                    if pid in s["units"]:
                        u = ww.unit(pid)
                        dd = ww.dests(pid)
                        if dd:
                            obj = _objective(ww, u, dist)
                            cands = [h2 for h2 in dd if _local_diff_ok(ww, u, h2)]
                            if cands:
                                best = min(cands,
                                           key=lambda h2: (dist(h2, obj), h2))
                                yield (side, {"type": "move", "unit": pid,
                                              "dest": list(best)},
                                       f"{e['slot']} drives on [15.14]")
                    break
            if not placed:
                continue

    # 2. unit moves
    for pid in sorted(s["units"]):
        if pid not in s["units"] or pid in s["done"]:
            continue
        u = ww.unit(pid)
        if u["side"] != side or ww.cls(pid) == "dz":
            continue
        dd = ww.dests(pid)
        if not dd:
            continue
        here = (u["col"], u["row"])
        obj = _objective(ww, u, dist)
        if ww.is_arty(pid):
            rng = ww.stats(pid).get("range", 4)
            foes = _foes(ww, side)

            def standoff(h):
                dmin = min((dist(h, eh) for eh in foes), default=99)
                return (0 if 2 <= dmin <= rng else 1, dist(h, obj), h)
            cands = [h for h in dd
                     if min((dist(h, eh) for eh in foes), default=99) >= 2]
            if cands:
                best = min(cands, key=standoff)
                if standoff(best) < standoff(here):
                    yield (side, {"type": "move", "unit": pid, "dest": list(best)},
                           "artillery takes a barrage standoff [8.11/8.41]")
            continue
        scored = [(dist(h, obj), h) for h in sorted(dd)
                  if _local_diff_ok(ww, u, h)]
        if not scored:
            continue
        scored.sort()
        if dist(here, obj) <= scored[0][0]:
            continue
        yield (side, {"type": "move", "unit": pid, "dest": list(scored[0][1])},
               f"{ww.cat(pid)['desig']} advances toward {obj}")

    yield (side, {"type": "end_movement"}, "movement phase complete [4.1]")


def _retreat_path(ww, pid, n):
    """A legal retreat path of exact length n, endpoint farthest from the
    enemy; vacant routes preferred, displacement through friends only when
    no vacant route exists [7.73]; None when nothing works (eliminate 7.74)."""
    u = ww.unit(pid)
    side = u["side"]
    board = ww.rules_board(exclude_pid=pid)
    enemy = ww.game.enemy(side)
    epos = {(b["col"], b["row"]) for b in board if b["side"] == enemy}
    fpos = {(b["col"], b["row"]) for b in board if b["side"] == side}
    ezoc = ww.game.zoc_hexes(board, enemy)
    origin = (u["col"], u["row"])
    dist = _Dist(ww.game)

    def search(allow_friends):
        best = None
        stack = [(origin, ())]
        seen = set()
        while stack:
            cur, path = stack.pop()
            if len(path) == n:
                if cur in fpos or ww.game.hex_distance(origin, cur) != n:
                    continue
                score = min((dist(cur, eh) for eh in epos), default=0)
                if best is None or score > best[0]:
                    best = (score, path)
                continue
            for nb in sorted(ww.game.neighbors(*cur)):
                if nb in path or nb == origin:
                    continue
                if not ww._retreat_step_ok(pid, side, cur, nb, epos, ezoc):
                    continue
                if nb in fpos and not allow_friends:
                    continue
                key = (nb, len(path) + 1)
                if key in seen and len(path) + 1 < n:
                    continue
                seen.add(key)
                stack.append((nb, path + (nb,)))
        return best

    best = search(False) or search(True)
    return list(best[1]) if best else None


def _resolve_pending(ww):
    p = ww.s["pending"]
    if not p:
        return None
    by = p["by"]
    if p["awaiting"] == "demolition":
        return (by, {"type": "demolition",
                     "attempt": {k: True for k in p["bridges"]}},
                "the German player fires every charge [12.11/12.12]")
    if p["awaiting"] == "fpf":
        elig = p["eligible"]
        allocs = []
        for e in elig[:2]:              # 14.12
            allocs.append([e["pid"], e["targets"][0]])
        gsp = 0
        if by == "All" and not p.get("pure_barrage") and ww.s["gsp_left"] > 0:
            dhexes = {(ww.unit(d)["col"], ww.unit(d)["row"])
                      for d in p["def_ids"] if d in ww.s["units"]}
            if ww._gsp_ok_hexes(dhexes):    # 14.11 pre-check
                gsp = ww.s["gsp_left"]
        act = {"type": "fpf", "allocations": allocs}
        if gsp:
            act["gsp"] = gsp
        return (by, act, f"FPF: {len(allocs)} batteries + {gsp} GSP [8.4/9.0]")
    if p["awaiting"] == "retreat":
        pid = next((x for x in p["units"] if x in ww.s["units"]), None)
        if pid is None:
            return None
        n = (p.get("distance_by") or {}).get(pid, p["distance"])
        opts = ww._retreat_distance_options(pid, n)
        if 0 in opts:
            return (by, {"type": "retreat", "unit": pid, "path": [],
                         "city_reduce": True},
                    "city benefit: the retreat becomes no-effect [11.1]")
        path = _retreat_path(ww, pid, min(opts))
        if path is None and min(opts) != n:
            path = _retreat_path(ww, pid, n)
        if path is None:
            return (by, {"type": "retreat", "unit": pid, "eliminate": True},
                    "no legal retreat - eliminated [7.74]")
        act = {"type": "retreat", "unit": pid,
               "path": [list(h) for h in path]}
        if len(path) != n and len(path) in opts:
            act["city_reduce"] = True
        return (by, act, f"retreats {len(path)} away [7.7]")
    if p["awaiting"] == "advance":
        occupied = ww._positions(dz=False)
        for h in p["path"]:
            h = tuple(h)
            if h in occupied:
                continue
            for pid in p["units"]:
                if pid not in ww.s["units"] or pid in ww.s["advanced"]:
                    continue
                chk = ww.propose(by, {"type": "advance", "unit": pid,
                                      "dest": list(h)})
                if chk["legal"]:
                    return (by, {"type": "advance", "unit": pid, "dest": list(h)},
                            f"advances into {h} [7.9]")
        return (by, {"type": "advance", "decline": True},
                "advance declined [7.96]")
    return None


def _pick_battle(ww, side, tried):
    mine, theirs = ww._contacts(side)
    unfought = [p for p in sorted(mine) if p not in ww.s["fought"]]
    if not unfought:
        return None
    foes = _foes(ww, side)

    def adj_enemies(pid):
        u = ww.unit(pid)
        out = []
        for h, e in sorted(foes.items()):
            if e["pid"] in ww.s["defended"] or e["pid"] in ww.s["advanced"]:
                continue
            if h in ww.game.neighbors(u["col"], u["row"]) \
               and (not ww._river_no_bridge((u["col"], u["row"]), h)
                    or ww._assault_pair(pid, e)):
                out.append(e["pid"])
        return out

    unfought.sort(key=lambda p: (len(adj_enemies(p)), p))
    for pid in unfought:
        defs = adj_enemies(pid)
        if not defs:
            continue
        atk = [pid]
        dhexes = {(ww.unit(d)["col"], ww.unit(d)["row"]) for d in defs}
        for q in unfought:
            if q in atk:
                continue
            uq = ww.unit(q)
            if all(h in ww.game.neighbors(uq["col"], uq["row"])
                   and not ww._river_no_bridge((uq["col"], uq["row"]), h)
                   for h in dhexes) \
               and set(adj_enemies(q)) <= set(defs):
                if ww.is_arty(q) and sum(1 for x in atk if ww.is_arty(x)) >= 2:
                    continue           # 14.12
                atk.append(q)
        # barrage support within the 14.12 cap
        n_arty = sum(1 for x in atk if ww.is_arty(x))
        if n_arty < 2:
            for u in sorted(ww._live(side), key=lambda x: x["pid"]):
                q = u["pid"]
                if q in atk or not ww.is_arty(q) or q in ww.s["fought"]:
                    continue
                if q in [x for x in unfought if adj_enemies(x)]:
                    continue           # it has its own melee obligation
                rng = ww.stats(q).get("range", 0)
                src = (u["col"], u["row"])
                if any(ww.game.hex_distance(src, h) <= rng
                       and ww.game.hex_distance(src, h) >= 2 for h in dhexes):
                    atk.append(q)
                    n_arty += 1
                    if n_arty >= 2:
                        break
        # the gate demands every covered friendly join [7.12/8.31]
        atk += [x for x in ww._mandatory_joiners(side, atk, defs)
                if x not in atk]
        action = {"type": "battle", "attackers": sorted(atk),
                  "defenders": sorted(defs)}
        # Allied GSP: lift the differential toward +6 [9.0/14.11]
        if side == "All" and ww.s["gsp_left"] > 0:
            a = 0
            for x in atk:
                st = ww.stats(x)
                a += st.get("barrage", st["att"]) if ww.is_arty(x) else st["att"]
            d = sum(ww.stats(x)["def"] for x in defs)
            want = max(0, min(ww.s["gsp_left"], 6 - (a - d)))
            if want and ww._gsp_ok_hexes({(ww.unit(x)["col"], ww.unit(x)["row"])
                                          for x in defs}):
                action["gsp"] = want
        key = (frozenset(action["attackers"]), frozenset(action["defenders"]),
               action.get("gsp", 0))
        if key in tried:
            continue
        return action, key
    return None


def turn_actions(ww, resolve_for=None, movement_gen=None):
    """Generator of (side, action, desc) for the current mover's player turn.
    resolve_for: sides whose pending choices this generator may answer.
    movement_gen: optional replacement movement-phase generator (the plans.py
    compiler injects planned movement here); None = the policy's own
    _movement_actions, byte-identical to the shipped behavior. Pendings and
    the combat phase always stay the policy's - 7.x is mandatory."""
    side = ww.s["mover"]
    resolve_for = resolve_for if resolve_for is not None \
        else set(ww.game.side_order)
    start = (ww.s["turn"], side)

    def live():
        return not ww.s["over"] and (ww.s["turn"], ww.s["mover"]) == start

    guard = 0
    pend_fail = [0]

    def pending_action():
        """Resolve the current pending with a degradation ladder: the policy
        pick, then the minimal legal fallback (empty FPF / decline / eliminate)
        - a rejected resolution can never loop."""
        item = _resolve_pending(ww)
        if item is None:
            return None
        if pend_fail[0] >= 1:
            by, act, _ = item
            p = ww.s["pending"]
            if p["awaiting"] == "fpf":
                return (by, {"type": "fpf", "allocations": []},
                        "FPF declined (fallback)")
            if p["awaiting"] == "advance":
                return (by, {"type": "advance", "decline": True},
                        "advance declined (fallback)")
            if p["awaiting"] == "retreat":
                pid = next((x for x in p["units"] if x in ww.s["units"]), None)
                if pid:
                    return (by, {"type": "retreat", "unit": pid,
                                 "eliminate": True}, "retreat fallback")
        return item

    # ---------------- movement phase (pendings may interrupt: demolition)
    if ww.s["phase"] == "movement" and live():
        gen = movement_gen if movement_gen is not None \
            else _movement_actions(ww, side)
        okv = None
        while live():
            if ww.s["pending"]:
                if ww.s["pending"]["by"] not in resolve_for:
                    return
                item = pending_action()
                if item is None:
                    return
                pok = yield item
                pend_fail[0] = 0 if pok else pend_fail[0] + 1
                if pend_fail[0] > 3:
                    return
                continue
            try:
                item = gen.send(okv)
            except StopIteration:
                break
            okv = yield item
    # ---------------- combat phase
    tried = set()
    while live() and ww.s["phase"] == "combat" and guard < 500:
        guard += 1
        if ww.s["pending"]:
            if ww.s["pending"]["by"] not in resolve_for:
                return
            item = pending_action()
            if item is None:
                return
            pok = yield item
            pend_fail[0] = 0 if pok else pend_fail[0] + 1
            if pend_fail[0] > 3:
                return
            continue
        pick = _pick_battle(ww, side, tried)
        if pick:
            action, key = pick
            okv = yield (side, action,
                         f"obligated battle {len(action['attackers'])} vs "
                         f"{len(action['defenders'])} [7.11/7.12]")
            if not okv:
                tried.add(key)
            continue
        okv = yield (side, {"type": "end_phase"}, "combat phase complete [4.1]")
        if not okv:
            return                     # closure refused and no battle found
        return


# ----------------------------------------------------------------- drivers
def _log_entry(side, action, desc, r):
    return {"side": side, "action": action, "desc": desc,
            "legal": r["verdict"]["legal"],
            "reasons": r["verdict"]["reasons"],
            "result": r.get("result")}


def _drive(gen, ww):
    log = []
    try:
        side, action, desc = gen.send(None)
        while True:
            r = ww.submit(side, action)
            log.append(_log_entry(side, action, desc, r))
            side, action, desc = gen.send(r["verdict"]["legal"])
    except StopIteration:
        pass
    return log


def take_turn(ww, resolve_for=None):
    if ww.s["over"]:
        return []
    return _drive(turn_actions(ww, resolve_for), ww)


class TurnStepper:
    """One gate action at a time - the engine hook for spacebar / animated
    stepping. Identical action stream to take_turn."""

    def __init__(self, ww, resolve_for=None, gen=None):
        self.bg = ww
        self.sg = ww
        # gen: a pre-built action generator (champion plan via
        # plans.COMPILERS) - absent, the policy's own stream
        self.gen = gen if gen is not None else turn_actions(ww, resolve_for)
        self._next = None
        try:
            self._next = self.gen.send(None)
        except StopIteration:
            self._next = None

    def done(self):
        return self._next is None

    def peek(self):
        if self._next is None:
            return None
        side, action, desc = self._next
        return {"side": side, "action": action, "desc": desc}

    def step(self):
        if self._next is None:
            return None
        side, action, desc = self._next
        r = self.bg.submit(side, action)
        entry = _log_entry(side, action, desc, r)
        try:
            self._next = self.gen.send(r["verdict"]["legal"])
        except StopIteration:
            self._next = None
        return entry


def play_game(ww, max_turns=None, on_turn=None):
    full = []
    guard = 0
    limit = (max_turns or ww.turns) * 2 + 6
    while not ww.s["over"] and guard < limit:
        before = (ww.s["turn"], ww.s["mover"], ww.s["n"])
        log = take_turn(ww)
        full.extend(log)
        if on_turn:
            on_turn(ww, log)
        after = (ww.s["turn"], ww.s["mover"], ww.s["n"])
        if before[:2] == after[:2] and not ww.s["over"]:
            full.append({"desc": "AI could not end its turn - stopping",
                         "error": True})
            break
        guard += 1
        if max_turns and ww.s["turn"] > max_turns:
            break
    return ww.s["turn"], full
