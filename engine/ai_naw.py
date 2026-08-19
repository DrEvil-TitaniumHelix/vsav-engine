import itertools

DEFAULTS = {
    "aggression": 0.6,
    "risk": 0.7,
    "terrain": 0.5,
    "cohesion": 0.4,
    "exit_turn": 6.0,
    "exit_weak": 3.0,
    "north_drive": 0.5,
    "hold_row": 8.0,
    "block": 0.7,
    "advance": 0.5,
    "art_stand": 0.8,
    "bombard_min": 5.0,
    "prussian_target": 0.6,
    "concentrate": 1.0,
}

RES_W = {"Dr": 0.15, "Ar": -0.15}


def _th(theta, key):
    if theta and key in theta:
        return float(theta[key])
    return float(DEFAULTS[key])


def _over(g):
    return bool(g.s["over"])


def _live(g, side=None):
    return [u for u in g.s["units"].values() if side is None or u["side"] == side]


def _crt(g):
    c = getattr(g, "_ai_crt", None)
    if c is None:
        crt = g._cbt()["crt"]
        c = {}
        for i, col in enumerate(crt["odds_columns"]):
            d = {}
            for die, row in crt["die_rows"].items():
                d[row[i]] = d.get(row[i], 0) + 1
            c[col] = {k: v / len(crt["die_rows"]) for k, v in d.items()}
        g._ai_crt = c
    return c


def _col_index(g, col):
    return g._cbt()["crt"]["odds_columns"].index(col)


def _ev(g, side, a, d, a_melee=None):
    if d <= 0 or a <= 0:
        return 0.0
    col, _ = g.demoralization_shift(side, g.odds_column(a, d))
    p = _crt(g)[col]
    am = a if a_melee is None else a_melee
    return (p.get("DE", 0) * d + p.get("Dr", 0) * RES_W["Dr"] * d
            + p.get("Ar", 0) * RES_W["Ar"] * am - p.get("AE", 0) * am
            - p.get("EX", 0) * 0.15 * am)


def _mult(g, h):
    dbl = g._cbt()["terrain_effects"]["defender_doubles_in"]
    return 2 if g.game.hex_terrain(*h) in dbl else 1


def _exit_dist(g, h):
    m = getattr(g, "_ai_exd", None)
    if m is None:
        m = g._ai_exd = {}
    if h not in m:
        m[h] = min(g.game.hex_distance(h, x) for x in g.exit_hexes)
    return m[h]


def _centroid(units):
    if not units:
        return None
    return (sum(u["col"] for u in units) / len(units), sum(u["row"] for u in units) / len(units))


def _adj(g, h, pos):
    nb = g.game.neighbors(*h)
    return [p for p, ph in pos.items() if ph in nb]


class _Ctx:
    def __init__(self, g, side, theta):
        self.g, self.side, self.theta = g, side, theta
        self.enemy = g.game.enemy(side)
        self.epos = {u["pid"]: (u["col"], u["row"]) for u in _live(g, self.enemy)}
        self.fpos = {u["pid"]: (u["col"], u["row"]) for u in _live(g, side)}
        self.ecent = _centroid(_live(g, self.enemy))
        self.fcent = _centroid(_live(g, side))
        self._threat = {}

    def att(self, pid):
        return self.g.stats(pid)["att"]

    def dfn(self, pid):
        return self.g.stats(pid)["def"]

    def threat_at(self, h):
        if h in self._threat:
            return self._threat[h]
        g = self.g
        tot = 0
        for p, ph in self.epos.items():
            st = g.stats(p)
            if g.game.hex_distance(ph, h) <= st["ma"] + 1:
                tot += st["att"]
        self._threat[h] = tot
        return tot


def _hex_score(cx, pid, h, moving=True, targets=None):
    g, th, side = cx.g, cx.theta, cx.side
    st = g.stats(pid)
    mult = _mult(g, h)
    score = 0.0
    adj_e = _adj(g, h, cx.epos)
    fpos = {p: q for p, q in cx.fpos.items() if p != pid}
    if adj_e:
        tg = targets or {}
        best = -99.0
        for e in adj_e:
            eh = cx.epos[e]
            friends = _adj(g, eh, fpos)
            a = st["att"] + sum(cx.att(f) for f in friends)
            if e in tg:
                a += tg[e] * _th(th, "concentrate")
            d = cx.dfn(e) * _mult(g, eh)
            best = max(best, _ev(g, side, a, d))
        if len(adj_e) > 1:
            best -= 0.5 * (len(adj_e) - 1)
        score += _th(th, "aggression") * 2.0 * best - (0.0 if targets is None else 2.0)
    thr = cx.threat_at(h)
    if thr:
        score -= _th(th, "risk") * max(0.0, _ev(g, cx.enemy, thr, st["def"] * mult))
    if mult > 1:
        score += _th(th, "terrain") * st["def"] * 0.5
    friends_adj = len(_adj(g, h, fpos))
    score += _th(th, "cohesion") * 0.4 * min(friends_adj, 3)
    if h in fpos.values():
        score -= 6.0
    if side == g.exit_side:
        drive = _th(th, "north_drive") * (2.5 if g.s["demoralized"] else 1.0)
        score -= drive * 0.35 * _exit_dist(g, h)
    else:
        score -= _th(th, "block") * 0.35 * g.game.hex_distance(h, _allied_target(cx))
    return score


def _allied_target(cx):
    g, th = cx.g, cx.theta
    fc = cx.ecent if cx.side != g.exit_side else cx.fcent
    row = int(round(_th(th, "hold_row")))
    if fc is None:
        return (6, max(1, min(22, row)))
    col = int(round(6.0 + (fc[0] - 6.0) * 0.5))
    return (max(1, min(27, col)), max(1, min(22, row)))


def _want_exit(cx, pid):
    g, th = cx.g, cx.theta
    s = g.s
    if cx.side != g.exit_side:
        return False
    need = g.game.spec["victory"]["french_exit_required"]
    if len(s["exited"]) >= need:
        return False
    if s["demoralized"] or s["turn"] >= g.turns - 1:
        return True
    st = g.stats(pid)
    late = s["turn"] >= _th(th, "exit_turn")
    weak = st["att"] <= _th(th, "exit_weak")
    return (late and weak) or (s["losses"][cx.enemy] >= 30 and weak)


def _min_col(g, theta):
    n = len(g._cbt()["crt"]["odds_columns"])
    return max(0, min(n - 1, int(round(8 - 4 * _th(theta, "aggression")))))


def _plan_attacks(cx, lms):
    g, side, th = cx.g, cx.side, cx.theta
    reach = {}
    for pid, lm in lms.items():
        cur = cx.fpos[pid]
        reach[pid] = ({(d["col"], d["row"]) for d in lm["dests"]} | {cur}) if lm["can_act"] else {cur}
    locked = {pid for pid, lm in lms.items() if not lm["can_act"] and pid in cx.fpos}
    committed = {}
    taken = set()
    targets = {}
    fixed_att = {}
    for pid in locked:
        for e in _adj(g, cx.fpos[pid], cx.epos):
            fixed_att[e] = fixed_att.get(e, 0) + cx.att(pid)
    min_col = _min_col(g, th)
    order = sorted(cx.epos, key=lambda e: (cx.dfn(e) * _mult(g, cx.epos[e]), e))
    for e in order:
        eh = cx.epos[e]
        d = cx.dfn(e) * _mult(g, eh)
        hexes = []
        for h in g.game.neighbors(*eh):
            if not g.game.on_map(*h) or h in cx.epos.values() or h in taken:
                continue
            if g.game.hex_terrain(*h) == "woods":
                continue
            others = [x for x in _adj(g, h, cx.epos) if x != e and x not in targets]
            if others:
                continue
            hexes.append(h)
        if not hexes:
            continue
        pool = sorted((p for p in reach if p not in committed and p not in locked and g.cls(p) != "artillery"),
                      key=lambda p: -cx.att(p))
        a = fixed_att.get(e, 0)
        assign = {}
        free = list(hexes)
        for p in pool:
            if not free:
                break
            opts = [h for h in free if h in reach[p]]
            if not opts:
                continue
            h = min(opts, key=lambda x: (len(_adj(g, x, cx.epos)), -_mult(g, x), x))
            assign[p] = h
            free.remove(h)
            a += cx.att(p)
            col = g.odds_column(a, d)
            if _col_index(g, col) >= min_col + 1:
                break
        bombers = {}
        for p in reach:
            if p in committed or p in assign or p in locked or g.cls(p) != "artillery":
                continue
            posts = [h for h in reach[p] if h not in taken and g.game.hex_distance(h, eh) == 2
                     and not _adj(g, h, cx.epos)
                     and g._bombard_los({"col": h[0], "row": h[1]}, {"col": eh[0], "row": eh[1]})[0]]
            if posts:
                bombers[p] = min(posts, key=lambda x: (cx.threat_at(x), x))
                a += cx.att(p)
                col = g.odds_column(a, d)
                if _col_index(g, col) >= min_col + 1:
                    break
        if not assign and not bombers:
            continue
        col, _ = g.demoralization_shift(side, g.odds_column(a, d))
        ev = _ev(g, side, a, d, a_melee=sum(cx.att(p) for p in assign) + fixed_att.get(e, 0))
        if _col_index(g, col) < min_col and ev <= 0.5:
            continue
        for p, h in list(assign.items()) + list(bombers.items()):
            committed[p] = h
            taken.add(h)
        targets[e] = a - fixed_att.get(e, 0)
    return committed, targets


def _movement(g, side, theta):
    cx = _Ctx(g, side, theta)
    for pid in g.due_reserve(side):
        eh = g.entry_hexes(pid)
        if not eh:
            continue
        pt = _th(theta, "prussian_target")
        best = min(eh, key=lambda h: pt * min([g.game.hex_distance(h, q) for q in cx.epos.values()] or [0])
                   + (1 - pt) * h[1] * 0.5)
        yield (side, {"type": "reinforce", "unit": pid, "hex": list(best)},
               f"Prussian {g._nm_cat(pid)} enters at {g._hn(best)}")
        cx = _Ctx(g, side, theta)
    lms = {pid: g.legal_moves(pid) for pid in cx.fpos}
    exiting = []
    if side == g.exit_side:
        for pid, lm in lms.items():
            if lm["can_act"] and lm["exits"] and _want_exit(cx, pid):
                exiting.append(pid)
    for pid in exiting:
        lms.pop(pid, None)
    if side == g.exit_side and g.s["demoralized"]:
        committed, targets = {}, {}
    else:
        committed, targets = _plan_attacks(cx, lms)
    for pid in exiting:
        if _over(g):
            return
        lm = g.legal_moves(pid)
        if lm["can_act"] and lm["exits"]:
            e = lm["exits"][0]
            yield (side, {"type": "exit", "unit": pid, "via": [e["col"], e["row"]]},
                   f"{g._nm(pid)} exits via {e['hexnum']}")
    todo = [p for p, h in committed.items() if h != cx.fpos[p]]
    for _ in range(3):
        left = []
        for pid in todo:
            if pid not in g.s["units"] or pid in g.s["done"] or _over(g):
                continue
            h = committed[pid]
            occ = {(v["col"], v["row"]) for v in g.s["units"].values()}
            if h in occ or h not in g.dests(pid):
                left.append(pid)
                continue
            ok = yield (side, {"type": "move", "unit": pid, "dest": list(h)},
                        f"{g._nm(pid)} to {g._hn(h)} (attack post)")
            if not ok:
                left.append(pid)
        if not left or left == todo:
            todo = left
            break
        todo = left
    order = sorted(cx.fpos, key=lambda p: (g.cls(p) == "artillery", -g.stats(p)["ma"], p))
    for pid in order:
        if _over(g) or pid not in g.s["units"] or pid in g.s["done"] or (pid in committed and pid not in todo):
            continue
        lm = g.legal_moves(pid)
        if not lm["can_act"]:
            continue
        cx = _Ctx(g, side, theta)
        cur = cx.fpos[pid]
        best_h, best_s = None, _hex_score(cx, pid, cur, targets=targets)
        for d in lm["dests"]:
            h = (d["col"], d["row"])
            sc = _hex_score(cx, pid, h, targets=targets)
            if sc > best_s + 1e-9:
                best_h, best_s = h, sc
        if best_h is None:
            continue
        ok = yield (side, {"type": "move", "unit": pid, "dest": list(best_h)}, f"{g._nm(pid)} to {g._hn(best_h)}")
    for _ in range(6):
        if _over(g):
            return
        ok = yield (side, {"type": "end_movement"}, "end Movement Phase")
        if ok or _over(g):
            return
        moved = False
        for h, ps in list(g.stacked_hexes(side).items()):
            for pp in ps:
                if pp in g.s["done"]:
                    continue
                occ = {(v["col"], v["row"]) for v in g.s["units"].values()}
                dd = [d for d in g.dests(pp) if d not in occ]
                if dd:
                    cx = _Ctx(g, side, theta)
                    h2 = max(dd, key=lambda x: _hex_score(cx, pp, x, targets=targets))
                    ok = yield (side, {"type": "move", "unit": pp, "dest": list(h2)},
                                f"un-stack {g._nm(pp)} to {g._hn(h2)}")
                    moved = moved or ok
                    break
        for pid in g.due_reserve(side):
            eh = g.entry_hexes(pid)
            if eh:
                ok = yield (side, {"type": "reinforce", "unit": pid, "hex": list(sorted(eh)[0])},
                            f"{g._nm_cat(pid)} enters")
                moved = moved or ok
        if not moved:
            return


def _attack_candidates(g, side):
    s = g.s
    enemy = g.game.enemy(side)
    fs, es = g.obligations()
    mine = [u for u in _live(g, side) if u["pid"] not in s["fought"] and u["pid"] not in s["advanced"]]
    theirs = [u for u in _live(g, enemy) if u["pid"] not in s["defended"] and u["pid"] not in s["advanced"]]
    out = []
    for e in theirs:
        eh = (e["col"], e["row"])
        melee = [u["pid"] for u in mine if g._adjacent(u, e)]
        bomb = []
        for u in mine:
            if g.cls(u["pid"]) != "artillery" or u["pid"] in s["disrupted"]:
                continue
            if any(g._adjacent(u, x) for x in _live(g, enemy)):
                continue
            if g.game.hex_distance((u["col"], u["row"]), eh) == 2 and g._bombard_los(u, e)[0]:
                bomb.append(u["pid"])
        if not melee and not bomb:
            continue
        atk = melee + bomb
        d = g.defense_strength([e["pid"]])
        a = g.attack_strength(atk)
        ev = _ev(g, side, a, d, a_melee=g.attack_strength(melee))
        obl = e["pid"] in es or any(p in fs for p in melee)
        out.append((ev, obl, atk, [e["pid"]], melee, bomb))
    out.sort(key=lambda x: (-x[0], x[3]))
    return out, fs, es


def _combat(g, side, theta):
    guard = 0
    while not _over(g) and guard < 80:
        guard += 1
        if g.s["pending"]:
            return
        cands, fs, es = _attack_candidates(g, side)
        if not fs and not es:
            bmin = int(round(_th(theta, "bombard_min")))
            fired = False
            for ev, obl, atk, dfd, melee, bomb in cands:
                if melee or not bomb:
                    continue
                col, _ = g.demoralization_shift(side, g.odds_column(g.attack_strength(atk), g.defense_strength(dfd)))
                if _col_index(g, col) >= bmin and ev > 0:
                    ok = yield (side, {"type": "battle", "attackers": bomb, "defenders": dfd},
                                f"bombard {g._nm(dfd[0])}")
                    if ok:
                        fired = True
                        break
            if fired:
                continue
            return
        done_one = False
        for ev, obl, atk, dfd, melee, bomb in cands:
            if not obl:
                continue
            ok, why, meta = g.battle_check(side, atk, dfd)
            if not ok and bomb and melee:
                ok, why, meta = g.battle_check(side, melee, dfd)
                if ok:
                    atk = melee
            if not ok:
                continue
            ok2 = yield (side, {"type": "battle", "attackers": atk, "defenders": dfd},
                         f"attack {g._nm(dfd[0])} at {meta['column']}")
            if ok2:
                done_one = True
                break
        if done_one:
            continue
        plan = g.complete_assignment()
        if not plan:
            return
        atk, dfd = plan[0]
        ok = yield (side, {"type": "battle", "attackers": atk, "defenders": dfd}, "mandatory attack (assignment)")
        if not ok:
            return


def _pending(g, side, theta):
    p = g.s["pending"]
    view = g._pending_view()
    if p["awaiting"] == "retreat":
        if view["voluntary"] and _th(theta, "art_stand") > 0.5:
            yield (side, {"type": "retreat", "decline": True}, "bombarding artillery stands fast")
            return
        us = [u for u in view["units"] if u["options"]]
        if not us:
            return
        u = us[0]
        owner = g.unit(u["pid"])["side"]
        cx = _Ctx(g, side, theta)
        fc = (int(cx.fcent[0]), int(cx.fcent[1])) if cx.fcent else None

        def sc(o):
            h = tuple(o["path"][-1])
            disr = 1.0 if "disrupts" in o["name"] else 0.0
            if owner == side:
                return _hex_score(cx, u["pid"], h, moving=False) - 3.0 * disr
            if owner == g.exit_side:
                return h[1] * 1.0 + 2.0 * disr
            return (g.game.hex_distance(h, fc) if fc else 0) + 2.0 * disr
        best = max(u["options"], key=sc)
        yield (side, {"type": "retreat", "unit": u["pid"], "path": best["path"]},
               f"{u['slot']} retreats to {best['name']}")
    elif p["awaiting"] == "exchange_loss":
        inv = view["involved"]
        owe = view["owe"]
        best = None
        for r in range(1, len(inv) + 1):
            for combo in itertools.combinations(inv, r):
                pay = sum(x["factor"] for x in combo)
                if pay < owe:
                    continue
                key = (pay - owe, sum(g.stats(x["pid"])["ma"] for x in combo), len(combo))
                if best is None or key < best[0]:
                    best = (key, [x["pid"] for x in combo])
            if best is not None:
                break
        if best is None:
            best = (None, [x["pid"] for x in inv])
        yield (side, {"type": "exchange_loss", "units": best[1]}, f"exchange paid with {len(best[1])} unit(s)")
    elif p["awaiting"] == "advance":
        cx = _Ctx(g, side, theta)
        best, best_gain = None, 0.0
        for pr in view["pairs"]:
            pid, h = pr["pid"], tuple(pr["hex"])
            cur = (g.unit(pid)["col"], g.unit(pid)["row"])
            gain = _hex_score(cx, pid, h, moving=False) - _hex_score(cx, pid, cur, moving=False)
            gain += (_th(theta, "advance") - 0.5) * 2.0
            if gain > best_gain:
                best, best_gain = pr, gain
        if best:
            yield (side, {"type": "advance", "unit": best["pid"], "hex": best["hex"]},
                   f"{best['slot']} advances to {best['name']}")
        else:
            yield (side, {"type": "advance", "decline": True}, "no advance")


def turn_actions(g, side=None, theta=None):
    side = side or g.side_to_move()
    guard = 0
    while not _over(g) and g.side_to_move() == side and guard < 400:
        guard += 1
        n0 = g.s["n"]
        if g.s["pending"]:
            yield from _pending(g, side, theta)
            if g.s["pending"] and g.s["n"] == n0:
                return
            continue
        if g.s["phase"] == "movement":
            yield from _movement(g, side, theta)
            if g.s["phase"] == "movement" and not _over(g):
                return
        elif g.s["phase"] == "combat":
            yield from _combat(g, side, theta)
            if g.s["pending"] or _over(g):
                continue
            ok = yield (side, {"type": "end_phase"}, "end Combat Phase")
            if not ok:
                return
        if g.s["n"] == n0 and g.side_to_move() == side and not g.s["pending"]:
            return


def _log_entry(side, action, desc, r):
    return {"side": side, "action": action, "desc": desc,
            "legal": r["verdict"]["legal"], "reasons": r["verdict"]["reasons"]}


TURN_SUBMIT_CAP = 600


def _drive(gen, g, cap=None):
    log = []
    cap = TURN_SUBMIT_CAP if cap is None else cap
    try:
        item = gen.send(None)
        while True:
            side, action, desc = item
            r = g.submit(side, action)
            log.append(_log_entry(side, action, desc, r))
            if len(log) >= cap:
                log.append({"desc": f"turn submission cap {cap} reached - AI stalled", "error": True})
                gen.close()
                break
            item = gen.send(r["verdict"]["legal"])
    except StopIteration:
        pass
    return log


def take_turn(g, side=None, theta=None):
    if _over(g):
        return []
    return _drive(turn_actions(g, side, theta), g)


class TurnStepper:
    def __init__(self, g, side=None, theta=None):
        self.sg = g
        self.side = side or g.side_to_move()
        self.gen = turn_actions(g, self.side, theta)
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
        r = self.sg.submit(side, action)
        entry = _log_entry(side, action, desc, r)
        try:
            self._next = self.gen.send(r["verdict"]["legal"])
        except StopIteration:
            self._next = None
        return entry


def play_game(g, max_turns=None, on_turn=None, thetas=None, max_actions=4000):
    full = []
    guard = 0
    while not _over(g) and guard < 400:
        before = (g.s["turn"], g.s["phase"], g.side_to_move(), g.s["n"])
        who = g.side_to_move()
        log = take_turn(g, who, (thetas or {}).get(who))
        full.extend(log)
        if on_turn:
            on_turn(g, log)
        after = (g.s["turn"], g.s["phase"], g.side_to_move(), g.s["n"])
        if before == after and not _over(g):
            full.append({"desc": "AI could not advance the game - stopping", "error": True})
            break
        guard += 1
        if max_turns and g.s["turn"] > max_turns:
            break
        if g.s["n"] >= max_actions:
            full.append({"desc": "action cap reached", "error": True})
            break
    return g.s["turn"], full
