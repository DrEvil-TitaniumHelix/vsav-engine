import itertools
import math

DEFAULTS = {
    "sector": 0.62,
    "sector_width": 0.10,
    "second_sector": 0.0,
    "escalade_share": 0.35,
    "tower_commit": 1.0,
    "cav_flank": 0.5,
    "archer_stand": 2.0,
    "stage_dist": 3.0,
    "target_pref": 0.5,
    "protect_leader": 1.0,
    "jud_wall_share": 0.55,
    "jud_reserve_depth": 3.0,
    "jud_react": 2.0,
    "jud_react_size": 10.0,
    "sortie": 0.0,
}

HEAVY = ("RV1", "RL1", "RR1")


def _th(theta, key):
    if theta and key in theta:
        return theta[key]
    return DEFAULTS[key]


def _over(g):
    return bool(g.s["over"])


def _K(g, name):
    return g.name_hex.get(name, name)


def _N(g, key):
    return g.hex_name.get(key, key)


def _unit(g, pid):
    return g.s["units"][pid]


def _onmap(g, side=None, state=None):
    return [u for u in g.s["units"].values() if u["hex"] is not None
            and (side is None or u["side"] == side)
            and (state is None or u["state"] == state)]


def _cls(g, u):
    return g.utype(u)["cls"]


def _is_leader(g, u):
    return _cls(g, u) in ("leader", "hq") or u["pid"] in ("R01", "J01", "Y01", "E01")


def _elev(g, h):
    return g.hex_t0.get(h) in ("north_wall", "bastion", "fort", "fortress",
                               "wall", "gate_wall", "gate_north_wall")


def _perimeter(g):
    if hasattr(g, "_ai_perim"):
        return g._ai_perim
    walls = [h for h in g.playable
             if g.hex_t0.get(h) in ("north_wall", "bastion", "fort", "fortress")]
    cx = sum(g.px[h][0] for h in g.jud_zone) / max(1, len(g.jud_zone))
    cy = sum(g.px[h][1] for h in g.jud_zone) / max(1, len(g.jud_zone))
    rows = []
    for h in walls:
        outs = [n for n in g._nb(h) if n in g.playable and n not in g.jud_zone
                and not _elev(g, n) and n not in g.rom_prohibited]
        if not outs:
            continue
        ang = math.atan2(g.px[h][1] - cy, g.px[h][0] - cx)
        rows.append((ang, h, outs))
    rows.sort()
    g._ai_perim = rows
    return rows


def _plan(g, theta):
    key = tuple(sorted((k, round(float(v), 4)) for k, v in
                       ((k, _th(theta, k)) for k in DEFAULTS)))
    cache = getattr(g, "_ai_plans", None)
    if cache is None:
        cache = g._ai_plans = {}
    if key in cache:
        return cache[key]
    per = _perimeter(g)
    n = len(per)
    c = int(_th(theta, "sector") * n) % n
    w = max(3, int(round(_th(theta, "sector_width") * n)))
    idx = [(c + i - w // 2) % n for i in range(w)]
    sec = [per[i] for i in idx]
    plain = [r for r in sec if g.hex_t0.get(r[1]) == "north_wall"]
    strong = [r for r in sec if r not in plain]
    breach = []
    for r in plain[:2]:
        breach.append((r[1], r[2][0]))
    if not breach and sec:
        breach.append((sec[0][1], sec[0][2][0]))
    used = {p for _, p in breach}
    esc = []
    for r in plain[2:] + strong:
        for o in r[2]:
            if o not in used:
                esc.append((r[1], o))
                used.add(o)
                break
        if len(esc) >= 3:
            break
    towers = []
    for r in strong + plain:
        for o in r[2]:
            if o not in used:
                towers.append((r[1], o))
                used.add(o)
                break
        if len(towers) >= 3:
            break
    center = sec[len(sec) // 2][1] if sec else per[0][1]
    ramw, rampost = breach[0]
    lane = {rampost}
    for h in g.playable:
        if g._dist(h, rampost) <= 1 and not _elev(g, h) and h not in g.jud_zone:
            lane.add(h)
    sd = _th(theta, "stage_dist")
    stage = sorted((h for h in g.rom_zone
                    if sd <= min(g._dist(h, s[1]) for s in sec) <= sd + 1
                    and h not in lane),
                   key=lambda h: (min(g._dist(h, s[1]) for s in sec),
                                  g._dist(h, center)))
    flank = _th(theta, "cav_flank")
    lo, hi = per[idx[0]], per[idx[-1]]
    fl = lo if flank < 0.5 else hi
    cav = sorted((h for h in g.rom_zone
                  if g._dist(h, fl[1]) <= 8 and h not in lane),
                 key=lambda h: (g._dist(h, fl[1]), g._dist(h, center)))
    plan = {"sector": [r[1] for r in sec], "center": center,
            "breach": breach, "esc": esc, "towers": towers,
            "lane": lane, "stage": stage, "cav": cav,
            "outs": {r[1]: r[2] for r in sec}}
    cache[key] = plan
    return plan


def _roles(g, theta):
    plan = _plan(g, theta)
    if "roles" in plan:
        return plan["roles"]
    units = g.s["units"]
    heav = sorted((p for p in units if p.startswith(HEAVY)),
                  key=lambda p: (HEAVY.index(p[:3]), int(p.split("_")[1])))
    roles = {}
    ramw, rampost = plan["breach"][0]
    crews = {"RM1": heav[-2:]}
    left = heav[:-2]
    tw = [p for p in units if p.startswith("RT1")]
    tc = int(round(_th(theta, "tower_commit") * len(tw)))
    for i, t in enumerate(tw[:len(plan["towers"])]):
        if i < tc:
            crews[t] = left[-2:]
            left = left[:-2]
            roles[t] = ("tower", plan["towers"][i])
        else:
            roles[t] = ("park", None)
    for t in tw[len(plan["towers"]):]:
        roles[t] = ("park", None)
    for se, cr in crews.items():
        for p in cr:
            roles[p] = ("crew", se)
    ne = int(round(_th(theta, "escalade_share") * len(left)))
    esc_units = left[-ne:] if ne else []
    assault = left[:len(left) - ne] if ne else left
    for i, p in enumerate(esc_units):
        roles[p] = ("escalade", plan["esc"][i % len(plan["esc"])] if plan["esc"]
                    else plan["breach"][0])
    for i, p in enumerate(assault):
        roles[p] = ("assault", i)
    for p in units:
        if p in roles or units[p]["side"] != "Rom":
            continue
        if p.startswith("RE1"):
            roles[p] = ("light", None)
        elif p.startswith("RF1"):
            roles[p] = ("guard", None)
        elif p.startswith("RS1"):
            roles[p] = ("archer", None)
        elif p.startswith("RC1"):
            roles[p] = ("cav", None)
        elif p == "RM1":
            roles[p] = ("ram", plan["breach"][0])
        elif p == "R01":
            roles[p] = ("hq", None)
        else:
            roles[p] = ("artillery", None)
    plan["roles"] = roles
    plan["crews"] = crews
    return roles


def _dist_to_sector(g, plan, h):
    return min(g._dist(h, s) for s in plan["sector"])


def _rom_deploy_hex(g, plan, roles, pid, taken):
    role, arg = roles[pid]
    crews = plan["crews"]
    for se, cr in crews.items():
        if pid in cr or pid == se:
            if se in taken:
                return [taken[se]]
            break
    se_hexes = {u["hex"] for u in g.s["units"].values() if u["hex"] is not None and _cls(g, u) == "siege_engine"}
    art_hexes = {taken[q] for q, (r, _) in roles.items() if r == "artillery" and q in taken}
    if role == "artillery":
        return sorted((h for h in g.rom_zone if h not in art_hexes and h not in se_hexes),
                      key=lambda h: (abs(_dist_to_sector(g, plan, h) - 6),
                                     g._dist(h, plan["center"])))
    if role in ("ram", "tower"):
        post = arg[1]
        cands = sorted((h for h in g.rom_zone if not _elev(g, h)),
                       key=lambda h: (g._dist(h, post), g._dist(h, plan["center"])))
        return cands
    if role == "cav":
        return [h for h in plan["cav"] if h not in se_hexes] or sorted(
            (h for h in g.rom_zone if h not in se_hexes), key=lambda h: g._dist(h, plan["center"]))
    if role == "escalade":
        return sorted((h for h in g.rom_zone if h not in se_hexes), key=lambda h: (g._dist(h, arg[1]), h))
    if role == "park":
        return sorted((h for h in g.rom_zone if not g._occupants(h)),
                      key=lambda h: -_dist_to_sector(g, plan, h))
    if role in ("assault", "hq", "guard", "light", "archer", "crew"):
        return sorted((h for h in g.rom_zone if h not in plan["lane"] and h not in se_hexes),
                      key=lambda h: (_dist_to_sector(g, plan, h), g._dist(h, plan["center"])))
    return sorted(g.rom_zone, key=lambda h: g._dist(h, plan["center"]))


def _rom_deploy(g, theta):
    plan = _plan(g, theta)
    roles = _roles(g, theta)
    taken = {}
    order = sorted((u["pid"] for u in g.s["units"].values() if u["side"] == "Rom"
                    and u["hex"] is None and u["state"] not in ("eliminated", "exited")),
                   key=lambda p: (0 if roles[p][0] in ("ram", "tower") else
                                  1 if roles[p][0] == "crew" else 2, p))
    for pid in order:
        u = _unit(g, pid)
        if u["hex"] is not None:
            continue
        cands = _rom_deploy_hex(g, plan, roles, pid, taken)
        placed = False
        for h in cands[:80]:
            a = {"type": "deploy", "pid": pid, "hex": _N(g, h)}
            role, arg = roles[pid]
            if role in ("ram", "tower"):
                face = min(g._nb(h), key=lambda n: g._dist(n, arg[0]))
                a["facing"] = _N(g, face)
            ok = yield ("Rom", a, f"deploy {pid} {role}")
            if ok:
                taken[pid] = h
                placed = True
                break
        if not placed:
            for h in sorted(g.rom_zone, key=lambda h: g._dist(h, plan["center"]))[:200]:
                a = {"type": "deploy", "pid": pid, "hex": _N(g, h)}
                if roles[pid][0] in ("ram", "tower"):
                    a["facing"] = _N(g, g._nb(h)[0])
                if (yield ("Rom", a, f"deploy {pid} fallback")):
                    taken[pid] = h
                    break
    yield ("Rom", {"type": "deploy_done"}, "Roman deployment done")


def _jud_deploy(g, theta):
    mf = list(g.min_force)
    inner = [h for h in g.jud_zone if h in g.playable and not _elev(g, h)]
    walls = [h for h in g.jud_zone if h in g.playable and _elev(g, h)
             and g.hex_t0.get(h) in ("north_wall", "bastion", "fort", "fortress")]
    per = _perimeter(g)
    outer = [r[1] for r in per]
    depth = _th(theta, "jud_reserve_depth")
    reserve = sorted(inner, key=lambda h: (abs(min(g._dist(h, w) for w in outer) - depth),
                                          g._dist(h, outer[len(outer) // 2])))
    units = [u for u in g.s["units"].values() if u["side"] == "Jud"
             and u["hex"] is None and u["state"] not in ("eliminated", "exited")]
    militia = [u["pid"] for u in units if g.utype(u).get("cls") == "militia"
               or "militia" in u["type"]]
    others = [u["pid"] for u in units if u["pid"] not in militia]
    caul = [p for p in others if p.startswith("C01")]
    lead = [p for p in others if _is_leader(g, _unit(g, p))]
    rest = [p for p in others if p not in caul and p not in lead]
    share = _th(theta, "jud_wall_share")
    fill = militia + rest
    used = {}
    for i, h in enumerate(mf):
        if not fill:
            break
        pid = fill.pop(0)
        if (yield ("Jud", {"type": "deploy", "pid": pid, "hex": _N(g, h)}, f"deploy {pid} strongpoint")):
            used[h] = used.get(h, 0) + 1
        else:
            fill.insert(0, pid)
    for pid in caul:
        for h in sorted(outer, key=lambda h: (used.get(h, 0), h))[:20]:
            if (yield ("Jud", {"type": "deploy", "pid": pid, "hex": _N(g, h)}, f"deploy {pid} cauldron")):
                used[h] = used.get(h, 0) + 1
                break
    nwall = int(round(share * len(fill)))
    wall_units, res_units = fill[:nwall], fill[nwall:]
    wall_order = sorted(outer, key=lambda h: (used.get(h, 0), g.hex_t0.get(h) != "north_wall", h))
    for pid in wall_units:
        for h in sorted(wall_order, key=lambda h: used.get(h, 0))[:30]:
            if (yield ("Jud", {"type": "deploy", "pid": pid, "hex": _N(g, h)}, f"deploy {pid} wall")):
                used[h] = used.get(h, 0) + 1
                break
    for pid in res_units + lead:
        for h in sorted(reserve, key=lambda h: used.get(h, 0))[:40]:
            if (yield ("Jud", {"type": "deploy", "pid": pid, "hex": _N(g, h)}, f"deploy {pid} reserve")):
                used[h] = used.get(h, 0) + 1
                break
    for u in list(g.s["units"].values()):
        if u["side"] == "Jud" and u["hex"] is None and u["state"] not in ("eliminated", "exited") \
                and u["pid"] not in [q["pid"] for q in g.s.get("pool", [])]:
            for h in sorted(g.jud_zone, key=lambda h: used.get(h, 0))[:60]:
                if (yield ("Jud", {"type": "deploy", "pid": u["pid"], "hex": _N(g, h)}, "deploy fallback")):
                    used[h] = used.get(h, 0) + 1
                    break
    yield ("Jud", {"type": "deploy_done"}, "Judaean deployment done")


def _pending(g, side, theta):
    p = g.s["pending"]
    by = p["by"]
    k = p["kind"]
    if k == "loss":
        need = [c for c in p["letters"] if c != "B"]
        elig = [o["pid"] for o in g._loss_elig(p["hex"], by, p.get("lvl"))]
        prim = [q for q in (p.get("primary") or []) if q in elig]
        order = prim + [q for q in elig if q not in prim]
        if _th(theta, "protect_leader") > 0.5:
            order.sort(key=lambda q: _is_leader(g, _unit(g, q)))
        if not need:
            yield (by, {"type": "resolve_loss", "picks": []}, "loss B-only")
            return
        tries = 0
        combos = list(itertools.permutations(order, len(need))) if len(order) >= len(need) else []
        combos += [c for c in itertools.product(order, repeat=len(need)) if c not in set(combos)]
        for combo in combos:
            tries += 1
            if tries > 40:
                break
            if (yield (by, {"type": "resolve_loss", "picks": [{"pid": q} for q in combo]}, "loss picks")):
                return
        yield (by, {"type": "resolve_loss", "picks": []}, "loss forfeit")
    elif k == "retreat":
        pids = [q for q in (p.get("pids") or []) if _unit(g, q)["hex"] is not None]
        att = [_unit(g, q)["hex"] for q in (p.get("attackers") or [])
               if _unit(g, q)["hex"] is not None]

        def paths_for(pid, n):
            u = _unit(g, pid)
            res = []
            for nb1 in g._nb(u["hex"]):
                if nb1 not in g.playable or any(o["side"] != u["side"] for o in g._occupants(nb1)):
                    continue
                if n == 1:
                    res.append([u["hex"], nb1])
                    continue
                for nb2 in g._nb(nb1):
                    if nb2 == u["hex"] or nb2 not in g.playable or any(
                            o["side"] != u["side"] for o in g._occupants(nb2)):
                        continue
                    res.append([u["hex"], nb1, nb2])
            res.sort(key=lambda pv: -min([g._dist(pv[-1], a) for a in att] or [0]))
            return res

        for n in (2, 1):
            cands = {pid: paths_for(pid, n) for pid in pids}
            for i in range(10):
                if not all(cands[pid] for pid in pids):
                    break
                pathsd = {pid: [_N(g, h) for h in cands[pid][min(i, len(cands[pid]) - 1)]]
                          for pid in pids}
                if (yield (by, {"type": "resolve_retreat", "paths": pathsd, "eliminate": []}, "retreat")):
                    return
        if (yield (by, {"type": "resolve_retreat", "paths": {}, "eliminate": pids}, "retreat elim")):
            return
        yield (by, {"type": "resolve_retreat", "paths": {}, "eliminate": []}, "retreat none")
    elif k == "advance":
        cands = [q for q in (p.get("pids") or []) if _unit(g, q)["hex"] is not None]
        for cut in range(len(cands), -1, -1):
            if (yield (by, {"type": "resolve_advance", "pids": cands[:cut]}, "advance")):
                return
    elif k == "esc_up":
        opts = p.get("opts") or {}
        mv = {}
        used = set()
        for pid, hs in opts.items():
            for h in (hs if isinstance(hs, list) else [hs]):
                if h not in used:
                    mv[pid] = h
                    used.add(h)
                    break
        if (yield (by, {"type": "resolve_esc_up", "moves": mv}, "esc up")):
            return
        yield (by, {"type": "resolve_esc_up", "moves": {}}, "esc up none")
    elif k == "counterattack":
        cands = list(p.get("cands") or [])
        if cands and _th(theta, "sortie") >= 0.0 and (
                yield (by, {"type": "resolve_counterattack", "attackers": cands}, "counterattack")):
            return
        yield (by, {"type": "resolve_counterattack", "decline": True}, "counterattack decline")
    elif k == "errant":
        cands = list(p.get("cands") or [])
        if cands and (yield (by, {"type": "resolve_errant", "pid": cands[0]}, "errant")):
            return
        yield (by, {"type": "resolve_errant", "pid": None}, "errant none")
    else:
        yield (by, {"type": "end_phase"}, f"unknown pending {k}")


def _missile(g, u):
    return g.utype(u).get("missile")


def _max_range(g, u):
    m = _missile(g, u)
    if not m:
        return 0
    hi = 0
    for band in m:
        hi = max(hi, int(str(band).split("-")[-1]))
    return hi


def _best_target(g, u, theta, adj_only=False):
    pref = _th(theta, "target_pref")
    rng = 1 if adj_only else _max_range(g, u)
    fired = set(g.s.get("fired_hexes") or [])
    adj_enemy = any(o["side"] != u["side"] for n in g._nb(u["hex"]) for o in g._occupants(n))
    if adj_enemy:
        rng = 1
    best = None
    for k2 in g.playable:
        if k2 in fired:
            continue
        occ = g._occupants(k2)
        if not occ or occ[0]["side"] == u["side"]:
            continue
        if all(_cls(g, o) == "siege_engine" for o in occ):
            continue
        d = g._dist(u["hex"], k2)
        if d > rng or g._range_af(u, d) is None:
            continue
        if d > 1 and not g.in_cc(u):
            continue
        if not g._lof(u["hex"], k2)[0]:
            continue
        val = sum(1 for o in occ if o["state"] == "fresh") + 0.5 * len(occ)
        score = d - pref * val
        if best is None or score < best[0]:
            best = (score, _N(g, k2))
    return best[1] if best else None


def _fire_plans(g, side, theta):
    plans = {}
    for u in _onmap(g, side, "fresh"):
        if u["pid"] in g.s["fired"] or _cls(g, u) == "siege_engine" or not _missile(g, u):
            continue
        if not u.get("up") and any(_cls(g, o) == "siege_engine" for o in g._occupants(u["hex"])):
            continue
        if g._hi_mixed(u) or any(e["hex"] == u["hex"] for e in g.s["esc"]):
            continue
        tgt = _best_target(g, u, theta, adj_only=g.is_night())
        if tgt:
            plans.setdefault(tgt, []).append(u["pid"])
    return plans


def _fire_seg(g, side, theta):
    if side == "Rom":
        plan = _plan(g, theta)
        for wall, post in plan["breach"]:
            u = _unit(g, "RM1")
            manned = any(o["state"] == "fresh" and _cls(g, o) in ("heavy", "light") and not o.get("up")
                         for o in g._occupants(u["hex"])) if u["hex"] is not None else False
            if u["hex"] == post and u["state"] == "fresh" and manned and g.hex_t(wall) != "breach":
                yield ("Rom", {"type": "breach_attack", "target": _N(g, wall),
                               "attackers": ["RM1"]}, "ram breach attack")
                while g.s["pending"]:
                    yield from _pending(g, side, theta)
                break
    for tgt, firers in _fire_plans(g, side, theta).items():
        if _K(g, tgt) in set(g.s.get("fired_hexes") or []):
            continue
        ok = yield (side, {"type": "fire", "target": tgt, "firers": firers}, "fire")
        while g.s["pending"]:
            yield from _pending(g, side, theta)
        if not ok and len(firers) > 1:
            for q in firers:
                if _K(g, tgt) in set(g.s.get("fired_hexes") or []):
                    break
                yield (side, {"type": "fire", "target": tgt, "firers": [q]}, "fire single")
                while g.s["pending"]:
                    yield from _pending(g, side, theta)
    yield (side, {"type": "end_phase"}, "end fire segment")


def _move_toward(g, pid, goal, maxcost=99.0, stop_adj=False, avoid=(), stop_dist=0, up=False):
    ld = g.legal_dests(pid)
    u = _unit(g, pid)
    dests = [d for d in ld["dests"] if _K(g, d["hex"]) not in avoid]
    goal = _K(g, goal)
    stop = 1 if stop_adj else stop_dist
    if u["hex"] is None:
        best = None
        for d in dests:
            dd = g._dist(_K(g, d["hex"]), goal)
            if best is None or dd < best[0]:
                best = (dd, d)
        if not best:
            return None
        a = {"type": "move", "pid": pid, "path": best[1]["path"]}
        if ld["crew"]:
            a["crew"] = ld["crew"]
        return a
    d0 = g._dist(u["hex"], goal)
    if d0 <= stop:
        return None
    best = None
    for d in dests:
        if d["cost"] > maxcost:
            continue
        dd = g._dist(_K(g, d["hex"]), goal)
        if dd < stop or dd >= d0:
            continue
        if best is None or (dd, d["cost"]) < (best[0], best[1]["cost"]):
            best = (dd, d)
    if not best:
        return None
    a = {"type": "move", "pid": pid, "path": best[1]["path"]}
    if ld["crew"]:
        a["crew"] = ld["crew"]
    if up:
        a["up"] = True
    return a


def _face_toward(g, pid, goal):
    u = _unit(g, pid)
    gk = _K(g, goal)
    fh = g._facing_hex(u)
    if fh is not None and g._dist(fh, gk) <= g._dist(u["hex"], gk):
        return []
    nbs = sorted(g._nb(u["hex"]), key=lambda n: g._dist(n, gk))
    return [{"type": "change_facing", "pid": pid, "face": _N(g, n)} for n in nbs[:2]]


def _se_go(g, pid, post, wall):
    u = _unit(g, pid)
    if u["hex"] is None:
        return
    if u["hex"] == post:
        if g._facing_hex(u) != wall:
            yield ("Rom", {"type": "change_facing", "pid": pid, "face": _N(g, wall)}, "SE face wall")
        return
    for fa in _face_toward(g, pid, post):
        if (yield ("Rom", fa, "SE face")):
            break
    a = _move_toward(g, pid, post)
    ok = (yield ("Rom", a, "SE advance")) if a else False
    if not ok:
        for fa in _face_toward(g, pid, post):
            if (yield ("Rom", fa, "SE re-face")):
                break
        a = _move_toward(g, pid, post)
        if a:
            yield ("Rom", a, "SE advance retry")
    if _unit(g, pid)["hex"] == post:
        yield ("Rom", {"type": "change_facing", "pid": pid, "face": _N(g, wall)}, "SE at post face wall")


def _builtup_goal(g, u):
    best = None
    for h in g.playable:
        if g.hex_t0.get(h) != "builtup" or g.s["control"].get(_N(g, h), g.s["control"].get(h)) == "Rom":
            continue
        occ = g._occupants(h)
        if occ and occ[0]["side"] == "Jud" and len(occ) >= 2:
            continue
        d = g._dist(u["hex"], h)
        if best is None or d < best[0]:
            best = (d, h)
    return best[1] if best else None


def _rom_move(g, theta):
    plan = _plan(g, theta)
    roles = _roles(g, theta)
    opened = [w for w, _ in plan["breach"] if g.hex_t(w) == "breach"]
    for wall, post in plan["breach"]:
        u = _unit(g, "RM1")
        if u["hex"] is None:
            break
        if g.hex_t(wall) == "breach":
            continue
        yield from _se_go(g, "RM1", post, wall)
        break
    for pid, (role, arg) in roles.items():
        u = _unit(g, pid)
        if u["hex"] is None or u["state"] != "fresh":
            continue
        if role == "tower":
            yield from _se_go(g, pid, arg[1], arg[0])
        elif role == "hq":
            goal = opened[0] if opened else plan["breach"][0][1]
            a = _move_toward(g, pid, goal, avoid=plan["lane"], stop_dist=2)
            if a:
                yield ("Rom", a, "HQ forward")
        elif role == "guard":
            hq = _unit(g, "R01")
            if hq["hex"] is not None:
                a = _move_toward(g, pid, hq["hex"], avoid=plan["lane"], stop_adj=True)
                if a:
                    yield ("Rom", a, "guard HQ")
        elif role == "escalade":
            wall, spot = arg
            esc_here = any(e["hex"] == spot for e in g.s["esc"])
            here = u["hex"] == spot
            if not esc_here:
                if here:
                    yield ("Rom", {"type": "escalade", "pid": pid, "op": "place"}, "place escalade")
                elif not g._occupants(spot):
                    a = _move_toward(g, pid, spot)
                    if a:
                        yield ("Rom", a, "to escalade spot")
                else:
                    a = _move_toward(g, pid, spot, stop_adj=True)
                    if a:
                        yield ("Rom", a, "toward escalade spot")
            elif not here and not u.get("up"):
                ld = g.legal_dests(pid)
                d = next((d for d in ld["dests"] if _K(g, d["hex"]) == spot), None)
                if d:
                    yield ("Rom", {"type": "move", "pid": pid, "path": d["path"], "up": True}, "climb")
                else:
                    a = _move_toward(g, pid, spot, stop_adj=True)
                    if a:
                        yield ("Rom", a, "toward ladder")
        elif role == "cav":
            i = list(k for k, v in roles.items() if v[0] == "cav").index(pid)
            goal = plan["cav"][i % len(plan["cav"])] if plan["cav"] else plan["center"]
            a = _move_toward(g, pid, goal, stop_adj=True)
            if a:
                yield ("Rom", a, "cavalry flank")
        elif role == "archer" or role == "light":
            goal = plan["sector"][(hash(pid) % len(plan["sector"]))]
            a = _move_toward(g, pid, goal, stop_dist=int(_th(theta, "archer_stand")), avoid=plan["lane"])
            if a:
                yield ("Rom", a, "missile line")
        elif role == "assault":
            i = arg
            if opened:
                gb = opened[i % len(opened)]
                if u["hex"] in opened or u["hex"] in g.jud_zone:
                    goal = _builtup_goal(g, u)
                    if goal is not None:
                        a = _move_toward(g, pid, goal, avoid={plan["breach"][0][1]})
                        if a:
                            yield ("Rom", a, "into the city")
                elif not any(o["side"] == "Jud" for o in g._occupants(gb)) and len(g._occupants(gb)) < 3:
                    a = _move_toward(g, pid, gb, avoid={plan["breach"][0][1]})
                    if a:
                        yield ("Rom", a, "through breach")
                else:
                    a = _move_toward(g, pid, gb, stop_adj=True, avoid={plan["breach"][0][1]})
                    if a:
                        yield ("Rom", a, "to breach")
            else:
                st = plan["stage"]
                if st:
                    a = _move_toward(g, pid, st[i % len(st)], avoid=plan["lane"])
                    if a:
                        yield ("Rom", a, "stage")
    yield from _end_move(g, "Rom")


def _end_move(g, side):
    for _ in range(4):
        if (yield (side, {"type": "end_phase"}, "end movement")):
            return
        moved = False
        for pid in g._refuge_laggards(side):
            u = _unit(g, pid)
            ld = g.legal_dests(pid)
            dests = sorted(ld["dests"], key=lambda d: (g._refuge_dist(side, _K(g, d["hex"])), -d["cost"]))
            for d in dests[:4]:
                if (yield (side, {"type": "move", "pid": pid, "path": d["path"]}, "obligation")):
                    moved = True
                    break
        if not moved:
            break
    yield (side, {"type": "end_phase"}, "end movement final")


def _threat_hexes(g):
    out = set()
    for u in _onmap(g, "Rom"):
        for nb in g._nb(u["hex"]):
            if g.hex_t0.get(nb) in ("north_wall", "bastion", "fort", "fortress") or g.hex_t(nb) == "breach":
                out.add(nb)
    return sorted(out)


def _jud_move(g, theta):
    threat = sum(g.s["breach"].values()) if isinstance(g.s["breach"], dict) else 0
    opened = [h for h in g.playable if g.hex_t(h) == "breach"]
    th = _threat_hexes(g)
    rally = min(th, key=lambda t: t) if th else None
    for q in list(g.s["entry_queue"]):
        goal = rally if rally is not None else _K(g, "K47")
        a = _move_toward(g, q["pid"], goal)
        if a:
            yield ("Jud", a, "reinforcement enters")
    react = _th(theta, "jud_react")
    if th and (threat >= react or opened or len(th) >= 3):
        reserves = [u for u in _onmap(g, "Jud", "fresh")
                    if not _elev(g, u["hex"]) and _cls(g, u) not in ("cauldron",)
                    and min(g._dist(u["hex"], t) for t in th) > 2]
        reserves.sort(key=lambda u: min(g._dist(u["hex"], t) for t in th))
        for u in reserves[:int(_th(theta, "jud_react_size"))]:
            tgt = min(th, key=lambda t: g._dist(u["hex"], t))
            a = _move_toward(g, u["pid"], tgt, stop_adj=True)
            if a:
                yield ("Jud", a, "reserve reacts")
    for gb in opened:
        if not g._occupants(gb):
            for u in _onmap(g, "Jud", "fresh"):
                if g._dist(u["hex"], gb) == 1:
                    a = _move_toward(g, u["pid"], gb)
                    if a and (yield ("Jud", a, "plug breach")):
                        break
    inside = [u for u in _onmap(g, "Rom") if u["hex"] in g.jud_zone]
    if inside:
        for u in _onmap(g, "Jud", "fresh"):
            if _elev(g, u["hex"]) or _cls(g, u) == "cauldron":
                continue
            near = min(inside, key=lambda r: g._dist(u["hex"], r["hex"]))
            if g._dist(u["hex"], near["hex"]) <= 4:
                a = _move_toward(g, u["pid"], near["hex"], stop_adj=True)
                if a:
                    yield ("Jud", a, "contest intruder")
    yield from _end_move(g, "Jud")


def _melee(g, side, theta):
    foe = "Jud" if side == "Rom" else "Rom"
    targets = {}
    for u in _onmap(g, side, "fresh"):
        if u["pid"] in g.s.get("meleed", []):
            continue
        if _cls(g, u) in ("artillery", "siege_engine"):
            continue
        if any(_cls(g, o) == "siege_engine" for o in g._occupants(u["hex"])):
            continue
        if g._hi_mixed(u) or any(o["state"] == "panicked" for o in g._occupants(u["hex"])):
            continue
        for nb in g._nb(u["hex"]):
            occ = g._occupants(nb)
            if occ and occ[0]["side"] == foe and g._melee_approach(u, nb)[0] is not None:
                targets.setdefault(nb, []).append(u["pid"])
    breach_targets = set()
    if side == "Rom":
        breach_targets = {w for w, _ in _plan(g, theta)["breach"]}
    order = sorted(targets, key=lambda h: (h not in breach_targets, g.hex_t(h) != "breach", _N(g, h)))
    for h in order:
        pids = sorted(set(targets[h]))
        ok = yield (side, {"type": "melee", "target": _N(g, h), "attackers": pids}, "melee")
        while g.s["pending"]:
            yield from _pending(g, side, theta)
        if not ok and len(pids) > 1:
            for q in pids:
                if (yield (side, {"type": "melee", "target": _N(g, h), "attackers": [q]}, "melee single")):
                    while g.s["pending"]:
                        yield from _pending(g, side, theta)
                    break
    yield (side, {"type": "end_phase"}, "end melee")


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
        ph = g.s["phase"]
        if ph == "deploy_jud":
            yield from _jud_deploy(g, theta)
        elif ph == "deploy_rom":
            yield from _rom_deploy(g, theta)
        elif ph.endswith("_fire"):
            yield from _fire_seg(g, side, theta)
        elif ph == "rom_move":
            yield from _rom_move(g, theta)
        elif ph == "jud_move":
            yield from _jud_move(g, theta)
        elif ph.endswith("_melee"):
            yield from _melee(g, side, theta)
        else:
            yield (side, {"type": "end_phase"}, f"end {ph}")
        if g.s["n"] == n0 and g.side_to_move() == side and not g.s["pending"]:
            if not (yield (side, {"type": "end_phase"}, "end phase fallback")):
                return


def _log_entry(side, action, desc, r):
    return {"side": side, "action": action, "desc": desc,
            "legal": r["verdict"]["legal"], "reasons": r["verdict"]["reasons"]}


def _drive(gen, g):
    log = []
    try:
        item = gen.send(None)
        while True:
            side, action, desc = item
            r = g.submit(side, action)
            log.append(_log_entry(side, action, desc, r))
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


def play_game(g, max_turns=None, on_turn=None, thetas=None, max_actions=6000):
    full = []
    guard = 0
    while not _over(g) and guard < 2000:
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
