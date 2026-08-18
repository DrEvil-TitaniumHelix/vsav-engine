import random


def resolve_pending(g, rng=None, prefer=None):
    rng = rng or random.Random(0)
    n = 0
    while g.s["pending"] and not g.s["over"]:
        p = g.s["pending"]
        view = g._pending_view()
        by = p["by"]
        if p["awaiting"] == "retreat":
            if view["voluntary"] and (prefer or {}).get("stand", True):
                r = g.submit(by, {"type": "retreat", "decline": True})
            else:
                us = [u for u in view["units"] if u["options"]]
                if not us:
                    raise RuntimeError(f"retreat pending with no options: {view}")
                u = rng.choice(us)
                o = rng.choice(u["options"])
                r = g.submit(by, {"type": "retreat", "unit": u["pid"], "path": o["path"]})
        elif p["awaiting"] == "exchange_loss":
            inv = sorted(view["involved"], key=lambda x: x["factor"])
            pick, tot = [], 0
            for u in inv:
                if tot >= view["owe"]:
                    break
                pick.append(u["pid"])
                tot += u["factor"]
            r = g.submit(by, {"type": "exchange_loss", "units": pick})
        elif p["awaiting"] == "advance":
            if view["pairs"] and rng.random() < (prefer or {}).get("advance", 0.5):
                pr = rng.choice(view["pairs"])
                r = g.submit(by, {"type": "advance", "unit": pr["pid"], "hex": pr["hex"]})
            else:
                r = g.submit(by, {"type": "advance", "decline": True})
        else:
            raise RuntimeError(f"unknown pending {p['awaiting']}")
        if not r["verdict"]["legal"]:
            raise RuntimeError(f"pending resolution refused: {r['verdict']}")
        n += 1
    return n


def discharge_combat(g, rng=None, extra=0.0):
    rng = rng or random.Random(0)
    side = g.s["mover"]
    fought = 0
    while not g.s["over"]:
        resolve_pending(g, rng)
        if g.s["over"]:
            break
        plan = g.complete_assignment()
        if not plan:
            break
        atk, dfd = plan[0] if rng.random() > 0.5 else rng.choice(plan)
        r = g.submit(side, {"type": "battle", "attackers": atk, "defenders": dfd})
        if not r["verdict"]["legal"]:
            raise RuntimeError(f"complete_assignment attack refused: {r['verdict']} plan={plan}")
        fought += 1
    if extra and not g.s["over"]:
        resolve_pending(g, rng)
    return fought


def bring_prussians(g):
    n = 0
    for pid in g.due_reserve(g.s["mover"]):
        eh = g.entry_hexes(pid)
        if eh:
            r = g.submit(g.s["mover"], {"type": "reinforce", "unit": pid, "hex": list(sorted(eh)[0])})
            n += r["verdict"]["legal"]
    return n


def unstack(g):
    side = g.s["mover"]
    for h, ps in list(g.stacked_hexes(side).items()):
        for pp in ps:
            if pp not in g.s["done"]:
                occ = {(v["col"], v["row"]) for v in g.s["units"].values()}
                free = [dd for dd in g.dests(pp) if dd not in occ]
                if free:
                    g.submit(side, {"type": "move", "unit": pp, "dest": list(sorted(free)[0])})
                    break


def end_player_turn(g, rng=None):
    rng = rng or random.Random(0)
    side = g.s["mover"]
    if g.s["phase"] == "movement":
        bring_prussians(g)
        r = g.submit(side, {"type": "end_movement"})
        if not r["verdict"]["legal"]:
            unstack(g)
            r = g.submit(side, {"type": "end_movement"})
        if not r["verdict"]["legal"]:
            raise RuntimeError(f"end_movement refused: {r['verdict']}")
    discharge_combat(g, rng)
    if g.s["over"]:
        return
    resolve_pending(g, rng)
    r = g.submit(side, {"type": "end_phase"})
    if not r["verdict"]["legal"]:
        raise RuntimeError(f"end_phase refused: {r['verdict']}")


def random_movement(g, rng, aggression=0.5, exits=0.3):
    side = g.s["mover"]
    enemy = g.game.enemy(side)
    mine = [p for p in g.s["units"] if g.unit(p)["side"] == side]
    rng.shuffle(mine)
    epos = [(v["col"], v["row"]) for v in g.s["units"].values() if v["side"] == enemy]
    for pid in mine:
        if pid in g.s["done"] or g.s["over"]:
            continue
        lm = g.legal_moves(pid)
        if not lm["can_act"]:
            continue
        if lm["exits"] and rng.random() < exits:
            e = rng.choice(lm["exits"])
            g.submit(side, {"type": "exit", "unit": pid, "via": [e["col"], e["row"]]})
            continue
        if not lm["dests"] or rng.random() < 0.15:
            continue
        if epos and rng.random() < aggression:
            def dist(d):
                return min(g.game.hex_distance((d["col"], d["row"]), e) for e in epos)
            d = min(lm["dests"], key=lambda d: (dist(d), rng.random()))
        else:
            d = rng.choice(lm["dests"])
        g.submit(side, {"type": "move", "unit": pid, "dest": [d["col"], d["row"]]})


def play_game(g, seed=1, aggression=0.6, max_actions=6000):
    rng = random.Random(seed)
    while not g.s["over"] and g.s["n"] < max_actions:
        random_movement(g, rng, aggression=aggression)
        end_player_turn(g, rng)
    return g
