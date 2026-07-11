"""
ai_bluegray.py - the AI opponent's policy for Blue & Gray quad games
(any BlueGrayGame).

Doctrine identical to ai_strategic.py: the policy READS public state and
SUBMITS every proposal through the one legality gate (BlueGrayGame.submit).
Rejections are logged as proof-of-enforcement. The policy is a GENERATOR of
single gate actions - take_turn drains it, TurnStepper steps it - so stepped
play is byte-identical to whole-turn play and the engine-level spacebar /
animated stepping works unchanged.

Policy (honest, not clever - a beta opponent playing a legal, complete,
replayable game):
  reinforcements - enter every due unit, alternating entry hexes, until the
    column cost exhausts the schedule (15.0).
  movement - combat units drive toward the nearest enemy-held VP objective
    (falling back to the nearest enemy unit); a unit never voluntarily ends
    adjacent to the enemy unless the units already in contact with that stack
    would attack at 1-1 or better (combat is mandatory, 7.0 - walking into a
    hopeless battle is suicide). Artillery keeps a 2-3 hex bombardment
    standoff (8.1) and avoids EZOCs (8.41). The Train runs for the exit
    hexes along roads/trails (18.23) and exits when able (16.x, the 10-VP
    stake of 17.11).
  combat - discharge every 7.11/7.12 obligation: each contacted friendly unit
    attacks ALL of its adjacent not-yet-defended stacks in ONE battle (7.23 -
    combining hexes per 7.25), pulling in co-attackers adjacent to every
    defender; then free bombardments against un-defended stacks in range.
    Own retreats maximize distance from the enemy; advances are taken onto VP
    hexes or safe ground, declined otherwise; exchanges pay with the smallest
    sufficient units (7.6).
Known-weak, declared: no voluntary odds reduction (7.9), no diversionary
attack search (7.5), no coordinated multi-turn plans. All optional - skipping
them is legal.
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


def _pix_d2(game, a, b):
    ax, ay = game.grid.hex_to_pixel(*a)
    bx, by = game.grid.hex_to_pixel(*b)
    return (ax - bx) ** 2 + (ay - by) ** 2


def _stacks(bg, side):
    """hex -> [units] for a side (train excluded from combat stacks)."""
    out = {}
    for u in bg.s["units"].values():
        if u["side"] == side and bg.cls(u) != "train":
            out.setdefault((u["col"], u["row"]), []).append(u)
    return out


def _vp_targets(bg, side):
    """Enemy-credited or uncontrolled VP hexes, as (col,row)."""
    occ = bg.s["occ"]
    out = []
    for owner_key, hexes in (bg.vp_cfg.get("occupation") or {}).items():
        owner = {"union": "Union", "confederate": "Confederate",
                 "either": None}.get(owner_key.lower(), owner_key)
        for hx in hexes:
            if owner not in (None, side):
                continue
            if occ.get(hx) != side:
                out.append((int(hx[:2]), int(hx[2:])))
    return out


def _objective(bg, u):
    side = u["side"]
    here = (u["col"], u["row"])
    foes = [(e["col"], e["row"]) for e in bg._live(bg.game.enemy(side))
            if bg.cls(e) != "train"]
    vps = _vp_targets(bg, side)
    cands = vps + foes
    if not cands:
        return here
    return min(cands, key=lambda h: _pix_d2(bg.game, here, h))


def _local_odds_ok(bg, u, dest, efoes):
    """Would ending on `dest` put u adjacent to enemies it (plus friends
    already adjacent) cannot fight at >= 1-1? Mandatory combat (7.0) makes
    hopeless adjacency suicide."""
    adj_stacks = {}
    for (h, stack) in efoes.items():
        if dest in bg.game.neighbors(*h) and bg._crossable(dest, h):
            adj_stacks[h] = stack
    if not adj_stacks:
        return True
    my = bg.strength(u)
    friends = _stacks(bg, u["side"])
    d_total = 0
    for h, stack in adj_stacks.items():
        base = sum(bg.strength(d) for d in stack)
        dbl = bg.game.hex_terrain(*h) in set(
            (bg.combat or {}).get("defense_double_terrain", []))
        d_total += base * 2 if dbl else base
        for fh, fstack in friends.items():
            if fh != dest and h in bg.game.neighbors(*fh) \
               and bg._crossable(fh, h):
                my += sum(bg.strength(f) for f in fstack
                          if f["pid"] not in bg.s["moved"] or True)
    return my >= d_total


def _movement_actions(bg, side):
    dist = _Dist(bg.game)
    # 1. reinforcements (15.0) - alternate hexes, stop when the column cost bites
    due = sorted([pid for pid, d in bg.s["pool"].items() if d <= bg.s["turn"]
                  and bg.reserve[pid]["side"] == side])
    flip = 0
    for pid in due:
        e = bg.reserve[pid]
        hexes = [tuple(h) for h in e["entry"]]
        placed = False
        for k in range(len(hexes)):
            h = hexes[(flip + k) % len(hexes)]
            okv = yield (side, {"type": "reinforce", "unit": pid, "hex": list(h)},
                         f"reinforcement {e['slot']} enters at {h} [15.0]")
            if okv:
                placed = True
                flip += 1
                break
        if not placed:
            break                      # column exhausted or hexes blocked (15.3/15.5)

    # 2. unit moves
    efoes = _stacks(bg, bg.game.enemy(side))
    pids = sorted(u["pid"] for u in bg._live(side))
    for pid in pids:
        if pid not in bg.s["units"] or pid in bg.s["moved"]:
            continue
        u = bg.unit(pid)
        here = (u["col"], u["row"])
        dd = bg.legal_moves(pid)
        # Train: run for the nearest exit hex, exit when standing on one
        if bg.cls(u) == "train":
            if here in bg.exit_hexes:
                yield (side, {"type": "exit", "unit": pid},
                       "the Train exits the map [16.1/17.11]")
                continue
            if dd:
                tgt = min(bg.exit_hexes, key=lambda h: dist(here, h))
                best = min(dd, key=lambda h: (dist(h, tgt), h))
                if dist(best, tgt) < dist(here, tgt):
                    yield (side, {"type": "move", "unit": pid, "dest": list(best)},
                           f"the Train rolls toward the exit {tgt} [18.23]")
            continue
        if not dd:
            continue                   # ZOC-locked (5.13) or boxed in
        obj = _objective(bg, u)
        if bg.cls(u) == "artillery":
            # standoff: prefer hexes 2-3 from the nearest enemy, never adjacent
            def standoff(h):
                dmin = min((dist(h, eh) for eh in efoes), default=9)
                return (0 if 2 <= dmin <= 3 else 1, dist(h, obj), h)
            cands = [h for h in dd
                     if min((dist(h, eh) for eh in efoes), default=9) >= 2]
            if not cands:
                continue
            best = min(cands, key=standoff)
            if standoff(best) < standoff(here):
                yield (side, {"type": "move", "unit": pid, "dest": list(best)},
                       "artillery takes a bombardment standoff [8.1/8.41]")
            continue
        scored = []
        for h in dd:
            if not _local_odds_ok(bg, u, h, efoes):
                continue
            scored.append((dist(h, obj), h))
        if not scored:
            continue
        scored.sort()
        best = scored[0][1]
        if dist(here, obj) <= scored[0][0]:
            continue                   # no progress - hold
        yield (side, {"type": "move", "unit": pid, "dest": list(best)},
               f"{u['slot']} advances toward {obj}")

    yield (side, {"type": "end_movement"}, "movement phase complete [4.1]")


def _pick_battles(bg, side, tried=frozenset()):
    """Greedy 7.11/7.12/7.23 partition: for each unfought contacted friendly
    unit (most-constrained first), one battle against ALL its adjacent
    un-defended stacks, with every co-attacker adjacent to all of them.
    `tried` = (attackers,defenders) frozenset pairs already rejected."""
    mine, theirs = bg._contacts(side)
    unfought = [p for p in sorted(mine) if p not in bg.s["fought"]]
    if not unfought:
        return None
    efoes = _stacks(bg, bg.game.enemy(side))

    def adj_stacks(pid):
        u = bg.unit(pid)
        out = []
        for h, stack in sorted(efoes.items()):
            if any(d["pid"] in bg.s["defended"] for d in stack):
                continue
            if h in bg.game.neighbors(u["col"], u["row"]) \
               and bg._crossable((u["col"], u["row"]), h):
                out.append((h, stack))
        return out

    unfought.sort(key=lambda p: len(adj_stacks(p)))
    for pid in unfought:
        stacks = adj_stacks(pid)
        if not stacks:
            continue
        dhexes = [h for h, _ in stacks]
        def_ids = [d["pid"] for _, st in stacks for d in st]
        atk_ids = [pid]
        for q in unfought:
            if q == pid or q in atk_ids:
                continue
            uq = bg.unit(q)
            # a co-attacker must be adjacent to ALL defenders (7.25) AND have
            # no un-defended obligations outside this battle - otherwise
            # joining strands its own 7.11/7.23 duty (each unit fights once,
            # 7.14)
            if all(h in bg.game.neighbors(uq["col"], uq["row"])
                   and bg._crossable((uq["col"], uq["row"]), h)
                   for h in dhexes) \
               and all(h in dhexes for h, _ in adj_stacks(q)):
                atk_ids.append(q)
        # 7.22: pull in co-stacked unfought mates (they must fight as one)
        for q in list(atk_ids):
            uq = bg.unit(q)
            for v in bg._live(side):
                if v["pid"] not in atk_ids and v["pid"] in unfought \
                   and (v["col"], v["row"]) == (uq["col"], uq["row"]):
                    atk_ids.append(v["pid"])
        key = (frozenset(atk_ids), frozenset(def_ids))
        if key in tried:
            continue
        return {"type": "battle", "attackers": sorted(atk_ids),
                "defenders": sorted(def_ids)}
    return None


def _resolve_pending(bg):
    """One gate action resolving the current pending, from its owning side."""
    p = bg.s["pending"]
    if not p:
        return None
    dist = _Dist(bg.game)
    by = p["by"]
    if p["awaiting"] == "retreat":
        pid = p["units"][0]
        u = bg.unit(pid)
        open_h, disp_h = bg._retreat_hexes(u)
        cands = open_h or disp_h
        if not cands:
            return (by, {"type": "retreat", "unit": pid, "dest": None},
                    f"{u['slot']} has no retreat - eliminated [7.72]")
        efoes = _stacks(bg, bg.game.enemy(u["side"]))
        best = max(sorted(cands),
                   key=lambda h: min((dist(h, eh) for eh in efoes), default=9))
        return (by, {"type": "retreat", "unit": pid, "dest": list(best)},
                f"{u['slot']} retreats to {best} [7.71]")
    if p["awaiting"] == "advance":
        vp_hexes = set()
        for d in (bg.vp_cfg.get("occupation") or {}).values():
            vp_hexes |= {(int(k[:2]), int(k[2:])) for k in d}
        for h in p["hexes"]:
            h = tuple(h)
            for pid in p["units"]:
                u = bg.unit(pid)
                if h in bg.game.neighbors(u["col"], u["row"]) \
                   and bg._crossable((u["col"], u["row"]), h):
                    efoes = _stacks(bg, bg.game.enemy(u["side"]))
                    adj_enemy = sum(
                        sum(bg.strength(d) for d in st)
                        for eh, st in efoes.items()
                        if h in bg.game.neighbors(*eh) and bg._crossable(h, eh))
                    if h in vp_hexes or adj_enemy == 0:
                        return (by, {"type": "advance", "unit": pid,
                                     "dest": list(h)},
                                f"{u['slot']} advances into {h} [7.75]")
        return (by, {"type": "advance"}, "advance declined [7.75]")
    if p["awaiting"] == "exchange_loss":
        owe = p["owe"]
        units = sorted(p["units"], key=lambda x: bg.printed(bg.unit(x)))
        # smallest single unit covering the debt, else accumulate smallest-first
        for x in units:
            if bg.printed(bg.unit(x)) >= owe:
                return (by, {"type": "exchange_loss", "units": [x]},
                        f"exchange paid with {bg.unit(x)['slot']} [7.6]")
        chosen, tot = [], 0
        for x in units:
            chosen.append(x)
            tot += bg.printed(bg.unit(x))
            if tot >= owe:
                break
        return (by, {"type": "exchange_loss", "units": chosen},
                "exchange paid smallest-first [7.6]")
    if p["awaiting"] == "train_retreat":
        u = bg.unit(p["unit"])
        open_h, _ = bg._retreat_hexes(u)
        if not open_h:
            return (by, {"type": "train_retreat", "dest": None},
                    "the Train has no road/trail retreat - destroyed [18.23]")
        efoes = _stacks(bg, "Confederate")
        best = max(sorted(open_h),
                   key=lambda h: min((dist(h, eh) for eh in efoes), default=9))
        return (by, {"type": "train_retreat", "dest": list(best)},
                f"the Train falls back to {best} [18.11]")
    return None


def turn_actions(bg, resolve_for=None):
    """Generator of (side, action, desc) for the current mover's player turn.
    resolve_for: sides whose pending resolutions this generator may answer
    (default: both - AI-vs-AI; pass {side} for human-vs-AI so the human's own
    retreat choices are left to the human)."""
    side = bg.s["mover"]
    resolve_for = resolve_for if resolve_for is not None \
        else set(bg.game.side_order)
    start = (bg.s["turn"], side)

    def live():
        return not bg.s["over"] and (bg.s["turn"], bg.s["mover"]) == start

    # ---------------- movement phase
    if bg.s["phase"] == "movement" and live():
        gen = _movement_actions(bg, side)
        okv = None
        while True:
            try:
                item = gen.send(okv)
            except StopIteration:
                break
            okv = yield item
            if not live():
                return

    # ---------------- combat phase
    guard = 0
    tried = set()          # rejected proposals this phase - never re-propose
    while live() and bg.s["phase"] == "combat" and guard < 400:
        guard += 1
        p = bg.s["pending"]
        if p:
            if p["by"] not in resolve_for:
                return                 # the human owns this choice
            item = _resolve_pending(bg)
            if item is None:
                return
            yield item
            continue
        battle = _pick_battles(bg, side, tried)
        if battle:
            key = (frozenset(battle["attackers"]), frozenset(battle["defenders"]))
            okv = yield (side, battle,
                         f"obligated battle: {len(battle['attackers'])} vs "
                         f"{len(battle['defenders'])} [7.11/7.12/7.23]")
            if not okv:
                tried.add(key)
            continue
        # free bombardments once obligations are clear: STACKED batteries
        # fire together at one hex (8.14/7.22)
        fired = False
        rng = (bg.combat or {}).get("artillery", {}).get("range") or [2, 3]
        board = bg.rules_board(mover_side=side)
        ezoc = bg.game.zoc_hexes(board, bg.game.enemy(side))
        efoes = _stacks(bg, bg.game.enemy(side))
        arty_by_hex = {}
        for u in sorted(bg._live(side), key=lambda x: x["pid"]):
            if bg.cls(u) != "artillery" or u["pid"] in bg.s["fought"]:
                continue
            src = (u["col"], u["row"])
            if src in ezoc:
                continue
            arty_by_hex.setdefault(src, []).append(u["pid"])
        for src, gunners in sorted(arty_by_hex.items()):
            best = None
            for h, stack in sorted(efoes.items()):
                if any(d["pid"] in bg.s["defended"] for d in stack):
                    continue
                d = bg.game.hex_distance(src, h)
                if not (rng[0] <= d <= rng[1]) or not bg._los_clear(src, h):
                    continue
                dstr = sum(bg.strength(x) for x in stack)
                if best is None or dstr < best[1]:
                    best = ([x["pid"] for x in stack], dstr)
            if not best:
                continue
            key = (frozenset(gunners), frozenset(best[0]))
            if key in tried:
                continue
            okv = yield (side, {"type": "battle", "attackers": sorted(gunners),
                                "defenders": sorted(best[0]),
                                "bombarding": sorted(gunners)},
                         f"battery at {src} bombards {best[0]} [8.1/8.14]")
            if not okv:
                tried.add(key)
            fired = True
            break
        if fired:
            continue
        yield (side, {"type": "end_phase"}, "combat phase complete [4.1]")
        return


# ----------------------------------------------------------------- drivers
def _log_entry(side, action, desc, r):
    return {"side": side, "action": action, "desc": desc,
            "legal": r["verdict"]["legal"],
            "reasons": r["verdict"]["reasons"],
            "result": r.get("result")}


def _drive(gen, bg):
    log = []
    try:
        side, action, desc = gen.send(None)
        while True:
            r = bg.submit(side, action)
            log.append(_log_entry(side, action, desc, r))
            side, action, desc = gen.send(r["verdict"]["legal"])
    except StopIteration:
        pass
    return log


def take_turn(bg, resolve_for=None):
    """Play the current mover's whole player turn through the gate."""
    if bg.s["over"]:
        return []
    return _drive(turn_actions(bg, resolve_for), bg)


class TurnStepper:
    """One gate action at a time - the engine hook for spacebar / animated
    stepping. Identical action stream to take_turn."""

    def __init__(self, bg, resolve_for=None):
        self.bg = bg
        self.gen = turn_actions(bg, resolve_for)
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


def play_game(bg, max_turns=None, on_turn=None):
    """Drive a full AI-vs-AI game. Returns (turns_played, log)."""
    full = []
    guard = 0
    limit = (max_turns or bg.turns) * 2 + 6
    while not bg.s["over"] and guard < limit:
        before = (bg.s["turn"], bg.s["mover"])
        log = take_turn(bg)
        full.extend(log)
        if on_turn:
            on_turn(bg, log)
        after = (bg.s["turn"], bg.s["mover"])
        if before == after and not bg.s["over"]:
            full.append({"desc": "AI could not end its turn - stopping",
                         "error": True})
            break
        guard += 1
        if max_turns and bg.s["turn"] > max_turns:
            break
    return bg.s["turn"], full
