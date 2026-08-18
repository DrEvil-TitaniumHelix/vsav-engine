import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
import gamespec
import soj

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME = os.path.join(ROOT, "games", "siege-of-jerusalem-ah")
OLDLOG = os.path.join(GAME, "ref_gallus.log.jsonl")
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 20260813
WORK = sys.argv[1]
os.makedirs(WORK, exist_ok=True)
for fn in os.listdir(WORK):
    if fn.startswith("game_") or fn.endswith((".jsonl", ".state.json")):
        os.remove(os.path.join(WORK, fn))

BREACH_PLAN = [("G44", "F44"), ("G46", "F46")]
ESC_SPOTS = ["F48"]
ASSAULT = ["RV1_1", "RV1_2", "RV1_3", "RV1_4", "RV1_5", "RV1_6", "RV1_7",
           "RV1_8", "RL1_1", "RL1_2", "RL1_3", "RL1_4", "RL1_5", "RL1_6",
           "RL1_7", "RL1_8", "RL1_9", "RL1_10"]
RAM_CREW = ["RV1_9", "RV1_10"]
DEPLOY_OVERRIDE = {"RM1": "B45", "RV1_9": "B45", "RV1_10": "B45",
                   "RV1_5": "F33", "RC1_5": "G32",
                   "RE1_1": "D34", "RE1_2": "D34",
                   "RE1_3": "J31", "RE1_4": "J31",
                   "RE1_5": "N30", "RE1_6": "N30"}
RAM_LANE = {"B45", "C45", "D45", "E45", "F44", "F45", "F46"}
STAGE_SPOTS = ["E43", "D43", "E46", "D46", "E47", "D47", "C43", "C46",
               "E48", "D48", "E42", "D42"]
SB_WAVES = [(["I37", "K36", "L36"],
             [f"RR1_{i}" for i in range(1, 11)])]
GUARD_GOALS = {"RF1_1": "N33", "RF1_2": "O32", "RF1_3": "M33",
               "RF1_4": "N32", "RF1_5": "L34", "RF1_6": "M34"}
TOWER_POSTS = {"RT1_1": ("H38", "H39"), "RT1_2": ("M35", "M36"),
               "RT1_3": ("N34", "N35")}
CAV_GOALS = {f"RC1_{i}": g for i, g in
             enumerate(["P32", "Q31", "P34", "R32", "P30", "Q33"], 1)}
ARCHER_GOALS = {"RS1_1": "K37", "RS1_2": "I38", "RS1_3": "M36"}

stats = {"ok": 0, "ref": 0, "reasons": {}}


def main():
    game = gamespec.Game(GAME)
    scen = None
    for c in sorted(os.listdir(GAME)):
        if c.startswith("scenario") and c.endswith(".json"):
            s = json.load(open(os.path.join(GAME, c), encoding="utf-8"))
            if "Gallus" in s.get("name", ""):
                scen = os.path.join(GAME, c)
    tg = soj.SoJGame(game, scen, WORK, seed=SEED)

    def sub(side, action, quiet=False):
        r = tg.submit(side, action)
        if r["verdict"]["legal"]:
            stats["ok"] += 1
        else:
            stats["ref"] += 1
            why = "; ".join(r["verdict"]["reasons"])[:110]
            stats["reasons"][why] = stats["reasons"].get(why, 0) + 1
            if not quiet:
                print(f"  REF {action.get('type')} {action.get('pid', '')}: {why}")
        return r

    def K(name):
        return tg.name_hex.get(name, name)

    def N(key):
        return tg.hex_name.get(key, key)

    def dist(a, b):
        return tg._dist(K(a) if isinstance(a, str) and a in tg.name_hex else a,
                        K(b) if isinstance(b, str) and b in tg.name_hex else b)

    def enemies_at(name):
        return [o for o in tg._occupants(K(name))]

    def unit(pid):
        return tg.s["units"][pid]

    def onmap(side=None, state=None):
        return [u for u in tg.s["units"].values() if u["hex"] is not None
                and (side is None or u["side"] == side)
                and (state is None or u["state"] == state)]

    def move_toward(pid, goal, maxcost=99.0, stop_adj=False, avoid=(),
                    stop_dist=0):
        ld = tg.legal_dests(pid)
        u = unit(pid)
        if avoid:
            ld = dict(ld, dests=[d for d in ld["dests"]
                                 if d["hex"] not in avoid])

        def go(d):
            a = {"type": "move", "pid": pid, "path": d["path"]}
            if ld["crew"]:
                a["crew"] = ld["crew"]
            return sub(u["side"], a)

        if u["hex"] is None:
            best = None
            for d in ld["dests"]:
                dd = dist(K(d["hex"]), K(goal))
                if best is None or dd < best[0]:
                    best = (dd, d)
            return go(best[1]) if best else None
        stop = 1 if stop_adj else stop_dist
        d0 = dist(u["hex"], K(goal))
        if d0 <= stop:
            return None
        best = None
        for d in ld["dests"]:
            if d["cost"] > maxcost:
                continue
            dd = dist(K(d["hex"]), K(goal))
            if dd < stop or dd >= d0:
                continue
            if best is None or (dd, d["cost"]) < (best[0], best[1]["cost"]):
                best = (dd, d)
        return go(best[1]) if best else None

    def handle_pending():
        import itertools
        p = tg.s["pending"]
        by = p["by"]
        k = p["kind"]
        if k == "loss":
            need = [c for c in p["letters"] if c != "B"]
            elig = [o["pid"] for o in
                    tg._loss_elig(p["hex"], by, p.get("lvl"))]
            prim = [q for q in (p.get("primary") or []) if q in elig]
            order = prim + [q for q in elig if q not in prim]
            if not need:
                sub(by, {"type": "resolve_loss", "picks": []}, quiet=True)
                return
            tries = 0
            for combo in itertools.product(order, repeat=len(need)):
                tries += 1
                if tries > 40:
                    break
                if sub(by, {"type": "resolve_loss",
                            "picks": [{"pid": q} for q in combo]},
                       quiet=True)["verdict"]["legal"]:
                    return
            sub(by, {"type": "resolve_loss", "picks": []})
        elif k == "retreat":
            pids = [q for q in (p.get("pids") or [])
                    if unit(q)["hex"] is not None]
            att = [unit(q)["hex"] for q in (p.get("attackers") or [])
                   if unit(q)["hex"] is not None]

            def paths_for(pid, n):
                u = unit(pid)
                res = []
                for nb1 in tg._nb(u["hex"]):
                    if nb1 not in tg.playable or any(
                            o["side"] != u["side"]
                            for o in tg._occupants(nb1)):
                        continue
                    if n == 1:
                        res.append([u["hex"], nb1])
                        continue
                    for nb2 in tg._nb(nb1):
                        if nb2 == u["hex"] or nb2 not in tg.playable or any(
                                o["side"] != u["side"]
                                for o in tg._occupants(nb2)):
                            continue
                        res.append([u["hex"], nb1, nb2])
                res.sort(key=lambda pv: -min(
                    [tg._dist(pv[-1], a) for a in att] or [0]))
                return res

            fails = []
            for n in (2, 1):
                cands = {pid: paths_for(pid, n) for pid in pids}
                for i in range(10):
                    if not all(cands[pid] for pid in pids):
                        break
                    pathsd = {pid: [N(h) for h in
                                    cands[pid][min(i, len(cands[pid]) - 1)]]
                              for pid in pids}
                    r = sub(by, {"type": "resolve_retreat", "paths": pathsd,
                                 "eliminate": []}, quiet=True)
                    if r["verdict"]["legal"]:
                        return
                    fails.append((pathsd,
                                  "; ".join(r["verdict"]["reasons"])[:90]))
            r = sub(by, {"type": "resolve_retreat", "paths": {},
                         "eliminate": pids}, quiet=True)
            if r["verdict"]["legal"]:
                return
            fails.append(("elim", "; ".join(r["verdict"]["reasons"])[:90]))
            for f in fails[-6:]:
                print("  retreat try:", f)
            sub(by, {"type": "resolve_retreat", "paths": {}, "eliminate": []})
        elif k == "advance":
            cands = [q for q in (p.get("pids") or [])
                     if unit(q)["hex"] is not None]
            for cut in range(len(cands), -1, -1):
                if sub(by, {"type": "resolve_advance", "pids": cands[:cut]},
                       quiet=True)["verdict"]["legal"]:
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
            if sub(by, {"type": "resolve_esc_up", "moves": mv},
                   quiet=True)["verdict"]["legal"]:
                if mv:
                    print(f"  ESC-UP: {mv}")
                return
            sub(by, {"type": "resolve_esc_up", "moves": {}})
        elif k == "counterattack":
            cands = list(p.get("cands") or [])
            if cands and sub(by, {"type": "resolve_counterattack",
                                  "attackers": cands},
                             quiet=True)["verdict"]["legal"]:
                print("  COUNTERATTACK!")
                return
            sub(by, {"type": "resolve_counterattack", "decline": True})
        elif k == "errant":
            cands = list(p.get("cands") or [])
            if not cands or not sub(by, {"type": "resolve_errant",
                                         "pid": cands[0]},
                                    quiet=True)["verdict"]["legal"]:
                sub(by, {"type": "resolve_errant", "pid": None})
        else:
            print(f"  UNKNOWN PENDING {k}: {json.dumps(p)[:200]}")
            raise SystemExit(1)
        if tg.s["pending"] is p:
            print(f"  STUCK PENDING {k}: {json.dumps(p)[:300]}")
            raise SystemExit(1)

    def deploy_all():
        old = [json.loads(x) for x in open(OLDLOG, encoding="utf-8")]
        for e in old[1:]:
            if e.get("event") != "action" or not e["verdict"]["legal"]:
                continue
            a = e["action"]
            if a["type"] == "deploy":
                hx = DEPLOY_OVERRIDE.get(a["pid"], a["hex"])
                a2 = dict(a, hex=hx)
                if a["pid"] == "RM1":
                    a2["facing"] = "C45"
                r = sub(e["side"], a2, quiet=True)
                if not r["verdict"]["legal"] and hx != a["hex"]:
                    r = sub(e["side"], a, quiet=True)
                if not r["verdict"]["legal"]:
                    print(f"  DEPLOY FAIL {a['pid']}: "
                          + "; ".join(r["verdict"]["reasons"])[:120])
            elif a["type"] == "deploy_done":
                sub(e["side"], a)
            if tg.s["phase"] not in ("deploy_jud", "deploy_rom"):
                break

    def cur_plan():
        for tgt, post in BREACH_PLAN:
            if tg.hex_t(K(tgt)) != "breach":
                return tgt, post
        return None, None

    def open_breaches():
        return [tgt for tgt, _ in BREACH_PLAN
                if tg.hex_t(K(tgt)) == "breach"]

    def ram_ready():
        tgt, post = cur_plan()
        u = unit("RM1")
        return post is not None and u["hex"] is not None \
            and N(u["hex"]) == post

    def drain():
        while tg.s["pending"]:
            handle_pending()

    def fire_plans(side):
        plans = {}
        for u in onmap(side, "fresh"):
            if u["pid"] in tg.s["fired"] or u["pid"] == "RM1" \
                    or not self_missile(u):
                continue
            if not u.get("up") and any(
                    tg.utype(o)["cls"] == "siege_engine"
                    for o in tg._occupants(u["hex"])):
                continue
            tgt = best_target(u, adj_only=tg.is_night())
            if tgt:
                plans.setdefault(tgt, []).append(u["pid"])
        return plans

    def rom_fire_seg():
        tgt, post = cur_plan()
        if tgt and ram_ready() and unit("RM1")["state"] == "fresh":
            r = sub("Rom", {"type": "breach_attack", "target": tgt,
                            "attackers": ["RM1"]}, quiet=True)
            if r["verdict"]["legal"]:
                res = r.get("result") or {}
                print(f"  BREACH ATTACK {tgt}: dmg {res.get('damage')}"
                      f" total {res.get('total')}/{res.get('defense')}"
                      + (" *** WALL DOWN ***" if res.get("breached") else ""))
            else:
                print(f"  breach refused: "
                      + "; ".join(r["verdict"]["reasons"])[:100])
            drain()
        elif tgt:
            u = unit("RM1")
            occ = [o["pid"] for o in tg._occupants(K(post))] if post else []
            print(f"  no breach try: ram={N(u['hex']) if u['hex'] else 'dead'}"
                  f" state={u['state']} post={post} occ={occ}")
        for ftgt, firers in fire_plans("Rom").items():
            r = sub("Rom", {"type": "fire", "target": ftgt,
                            "firers": firers}, quiet=True)
            if not r["verdict"]["legal"] and len(firers) > 1:
                for q in firers:
                    sub("Rom", {"type": "fire", "target": ftgt,
                                "firers": [q]}, quiet=True)
                    drain()
            drain()
        sub("Rom", {"type": "end_phase"}, quiet=True)

    def self_missile(u):
        return tg.utype(u).get("missile")

    def best_target(u, adj_only=False):
        cand = None
        rng = 1 if adj_only else max_range(u)
        for k2, o in ((k2, o) for k2 in tg.playable
                      for o in tg._occupants(k2)):
            if o["side"] == u["side"]:
                continue
            d = tg._dist(u["hex"], k2)
            if d > rng:
                continue
            if cand is None or d < cand[0]:
                cand = (d, N(k2))
        return cand[1] if cand else None

    def max_range(u):
        m = self_missile(u)
        if not m:
            return 0
        hi = 0
        for band in m:
            hi = max(hi, int(str(band).split("-")[-1]))
        return hi

    def jud_fire_seg():
        for ftgt, firers in fire_plans("Jud").items():
            r = sub("Jud", {"type": "fire", "target": ftgt,
                            "firers": firers}, quiet=True)
            if not r["verdict"]["legal"] and len(firers) > 1:
                for q in firers:
                    sub("Jud", {"type": "fire", "target": ftgt,
                                "firers": [q]}, quiet=True)
                    drain()
            drain()
        sub("Jud", {"type": "end_phase"}, quiet=True)

    def face_toward(pid, goal):
        u = unit(pid)
        gk = K(goal)
        if tg._facing_hex(u) is not None \
                and tg._dist(tg._facing_hex(u), gk) <= tg._dist(u["hex"], gk):
            return
        nbs = sorted(tg._nb(u["hex"]), key=lambda n: tg._dist(n, gk))
        for nb in nbs[:2]:
            if sub("Rom", {"type": "change_facing", "pid": pid,
                           "face": N(nb)}, quiet=True)["verdict"]["legal"]:
                return

    def rom_move_phase():
        tgt, post = cur_plan()
        opened = open_breaches()
        breach_open = bool(opened)
        if tgt and not ram_ready() and unit("RM1")["hex"] is not None:
            face_toward("RM1", post)
            r = move_toward("RM1", post)
            if r is None or not r["verdict"]["legal"]:
                face_toward("RM1", post)
                move_toward("RM1", post)
            if ram_ready():
                sub("Rom", {"type": "change_facing", "pid": "RM1",
                            "face": tgt}, quiet=True)
                print(f"  RAM IN POSITION at {post} facing {tgt}")
        move_toward("R01", "H36" if K("H36") != "H36" else "D44",
                    avoid=RAM_LANE)
        for pid, goal in GUARD_GOALS.items():
            u = unit(pid)
            if goal in tg.name_hex and u["hex"] is not None \
                    and u["state"] == "fresh":
                move_toward(pid, goal, avoid=RAM_LANE)
        for spots, wave in SB_WAVES:
          for i, pid in enumerate(wave):
            u = unit(pid)
            if u["hex"] is None or u["state"] != "fresh":
                continue
            spot = spots[i % len(spots)]
            esc_here = any(N(e["hex"]) == spot for e in tg.s["esc"])
            here = N(u["hex"]) == spot
            if not esc_here:
                if here:
                    sub("Rom", {"type": "escalade", "pid": pid,
                                "op": "place"}, quiet=True)
                elif not tg._occupants(K(spot)):
                    move_toward(pid, spot)
                else:
                    move_toward(pid, spot, stop_adj=True)
            elif not here and not u.get("up"):
                ld = tg.legal_dests(pid)
                d = next((d for d in ld["dests"] if d["hex"] == spot), None)
                if d:
                    sub("Rom", {"type": "move", "pid": pid,
                                "path": d["path"], "up": True}, quiet=True)
                else:
                    move_toward(pid, spot, stop_adj=True)
        for tp, (post, wall) in TOWER_POSTS.items():
            u = unit(tp)
            if u["hex"] is None:
                continue
            if N(u["hex"]) != post:
                face_toward(tp, post)
                r = move_toward(tp, post)
                if r is None or not r["verdict"]["legal"]:
                    face_toward(tp, post)
                    move_toward(tp, post)
                if N(unit(tp)["hex"]) == post:
                    sub("Rom", {"type": "change_facing", "pid": tp,
                                "face": wall}, quiet=True)
                    print(f"  TOWER {tp} AT THE WALL {post}")
        for pid, goal in CAV_GOALS.items():
            u = unit(pid)
            if goal in tg.name_hex and u["hex"] is not None \
                    and u["state"] == "fresh":
                move_toward(pid, goal, stop_adj=True)
        for pid, goal in ARCHER_GOALS.items():
            u = unit(pid)
            if goal in tg.name_hex and u["hex"] is not None \
                    and u["state"] == "fresh":
                move_toward(pid, goal, stop_dist=2)
        for i, spot in enumerate(ESC_SPOTS):
            holder = [o for o in tg._occupants(K(spot)) if o["side"] == "Rom"]
            esc_here = any(e["hex"] == K(spot) for e in tg.s["esc"])
            pid = ASSAULT[i]
            u = unit(pid)
            if u["hex"] is None or u["state"] != "fresh":
                continue
            if not holder and N(u["hex"]) != spot:
                move_toward(pid, spot)
            if N(unit(pid)["hex"]) == spot and not esc_here:
                sub("Rom", {"type": "escalade", "pid": pid, "op": "place"},
                    quiet=True)
        keep_clear = {post} if tgt else set()
        for i, pid in enumerate(ASSAULT[len(ESC_SPOTS):]):
            u = unit(pid)
            if u["hex"] is None or u["state"] != "fresh":
                continue
            if breach_open:
                gb = opened[i % len(opened)]
                if N(u["hex"]) in opened:
                    move_toward(pid, "H45", avoid=keep_clear)
                elif not any(o for o in tg._occupants(K(gb))
                             if o["side"] == "Jud") \
                        and len(tg._occupants(K(gb))) < 3:
                    move_toward(pid, gb, avoid=keep_clear)
                else:
                    move_toward(pid, gb, stop_adj=True, avoid=keep_clear)
            else:
                move_toward(pid, STAGE_SPOTS[ASSAULT.index(pid)
                                             % len(STAGE_SPOTS)],
                            avoid=RAM_LANE)
        while True:
            r = sub("Rom", {"type": "end_phase"}, quiet=True)
            if r["verdict"]["legal"]:
                break
            if not force_obligations("Rom"):
                sub("Rom", {"type": "end_phase"})
                break

    def threat_hexes():
        out = set()
        for u in onmap("Rom"):
            for nb in tg._nb(u["hex"]):
                if tg.hex_t0.get(nb) in ("north_wall", "bastion", "fort") \
                        or tg.hex_t(nb) == "breach":
                    out.add(nb)
        return sorted(out)

    def jud_move_phase():
        threat = sum(tg.s["breach"].values())
        opened = open_breaches()
        for q in list(tg.s["entry_queue"]):
            move_toward(q["pid"], "K47")
        th = threat_hexes()
        if th and (threat >= 2 or opened or len(th) >= 3):
            reserves = [u for u in onmap("Jud", "fresh")
                        if u["pid"].startswith(("Y02", "Y10", "S02", "S11"))
                        and min(dist(u["hex"], t) for t in th) > 2]
            reserves.sort(key=lambda u:
                          min(dist(u["hex"], t) for t in th))
            for u in reserves[:10]:
                tgt = min(th, key=lambda t: dist(u["hex"], t))
                move_toward(u["pid"], N(tgt), stop_adj=True)
        for gb in opened:
            occ = tg._occupants(K(gb))
            if not occ:
                for u in onmap("Jud", "fresh"):
                    if dist(u["hex"], K(gb)) == 1:
                        move_toward(u["pid"], gb)
                        break
        while True:
            r = sub("Jud", {"type": "end_phase"}, quiet=True)
            if r["verdict"]["legal"]:
                break
            if not force_obligations("Jud"):
                sub("Jud", {"type": "end_phase"})
                break

    def force_obligations(side):
        moved = False
        for u in onmap(side):
            if u["state"] in ("routed", "panicked"):
                ld = tg.legal_dests(u["pid"])
                if ld["dests"]:
                    d = ld["dests"][0]
                    if sub(side, {"type": "move", "pid": u["pid"],
                                  "path": d["path"]},
                           quiet=True)["verdict"]["legal"]:
                        moved = True
        return moved

    def melee_phase(side):
        foe = "Jud" if side == "Rom" else "Rom"
        targets = {}
        for u in onmap(side, "fresh"):
            if u["pid"] in tg.s.get("meleed", []):
                continue
            if tg.utype(u)["cls"] in ("artillery", "siege_engine"):
                continue
            if any(tg.utype(o)["cls"] == "siege_engine"
                   for o in tg._occupants(u["hex"])):
                continue
            for nb in tg._nb(u["hex"]):
                occ = tg._occupants(nb)
                if occ and occ[0]["side"] == foe:
                    targets.setdefault(nb, []).append(u["pid"])
        order = sorted(targets, key=lambda h: (N(h) not in
                                               [t for t, _ in BREACH_PLAN],
                                               N(h)))
        for h in order:
            pids = sorted(set(targets[h]))
            r = sub(side, {"type": "melee", "target": N(h),
                           "attackers": pids}, quiet=True)
            drain()
            if not r["verdict"]["legal"] and len(pids) > 1:
                for q in pids:
                    r2 = sub(side, {"type": "melee", "target": N(h),
                                    "attackers": [q]}, quiet=True)
                    drain()
                    if r2["verdict"]["legal"]:
                        break
        sub(side, {"type": "end_phase"}, quiet=True)

    deploy_all()
    print(f"deployed, phase={tg.s['phase']} n={tg.s['n']}")
    guard = 0
    while not tg.s["over"] and guard < 3000:
        guard += 1
        if tg.s["pending"]:
            handle_pending()
            continue
        ph = tg.s["phase"]
        seg = tg.s.get("seg")
        if ph.endswith("_fire"):
            if seg == "Rom":
                rom_fire_seg()
            else:
                jud_fire_seg()
        elif ph == "rom_move":
            rom_move_phase()
        elif ph == "jud_move":
            jud_move_phase()
        elif ph == "rom_melee":
            melee_phase("Rom")
        elif ph == "jud_melee":
            melee_phase("Jud")
        elif ph.endswith("_rally"):
            sub("Rom" if ph.startswith("rom") else "Jud",
                {"type": "end_phase"})
        else:
            print(f"  unhandled phase {ph}")
            break
        if tg.s["phase"] == "rom_fire" and ph != "rom_fire":
            ram = unit("RM1")
            spots = {p: (N(unit(p)["hex"]) if unit(p)["hex"] else unit(p)["state"])
                     for p in ["RV1_1", "RV1_2", "RL1_3", "RL1_6"]}
            print(f"TURN {tg.s['turn']} ram={N(ram['hex']) if ram['hex'] else 'gone'}"
                  f" face={ram.get('facing')}"
                  f" breach={ {N(h): d for h, d in tg.s['breach'].items()} }"
                  f" assault={spots} n={tg.s['n']}")
    print(f"OVER={tg.s['over']} winner={tg.s['winner']} turn={tg.s['turn']}")
    print(f"actions ok={stats['ok']} refused={stats['ref']}")
    for why, c in sorted(stats["reasons"].items(), key=lambda t: -t[1])[:15]:
        print(f"  {c:3d}x {why}")
    print("log:", tg.log_path)


if __name__ == "__main__":
    main()
