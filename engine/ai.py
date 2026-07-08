"""
ai.py - The AI opponent's tactical policy for Tobruk Scenario One firefights.

Deliberately transparent: the AI READS the same state every player sees and
SUBMITS proposals through the same legality gate (gamestate.submit) that the
human's moves pass through. It has no other door into the game. If it ever
proposes something illegal, the gate rejects it, the rejection is logged as
proof-of-enforcement, and the AI picks a different action.

Policy (simple, honest desert tactics):
  movement — keep the front armor toward the nearest live enemy; close to
  effective gun range (HPN <= 8 unlocks fire initiation) but no closer than
  it must; stationary units pivot to face threats so they can still fire.
  combat  — prefer the acquired target (better ROF), then the best kill odds
  (lowest adjusted HPN, flank/rear bonus targets first).
"""


def _nearest_enemy(tg, u):
    best, bd = None, 999
    for e in tg.s["units"].values():
        if e["side"] == u["side"] or e["K"]:
            continue
        d = tg.range_between(u, e)
        if d is not None and d < bd:
            best, bd = e, d
    return best, bd


def _desired_range(tg, u):
    """Close until fire can be initiated (HPN <= 8), then hold."""
    weapon = tg.cd.weapon_of(u["afv"])
    tbl = tg.cd.weapons[weapon]["hpn_by_range"]
    for r in range(len(tbl), 0, -1):
        if tbl[r - 1] <= tg.cd.init_max_hpn:
            return r
    return 1


def movement_actions(tg, side):
    """Yield (description, action) proposals for the movement segment."""
    acts = []
    for u in sorted(tg.s["units"].values(), key=lambda x: x["pid"]):
        if u["side"] != side or u["K"] or u["M"]:
            continue
        if u["pid"] in tg.s["moved"] or u["pid"] in tg.s["pivoted"]:
            continue
        enemy, dist = _nearest_enemy(tg, u)
        if enemy is None:
            continue
        want = _desired_range(tg, u)
        lm = tg.legal_moves(u["pid"])
        if not lm["can_act"]:
            continue
        if dist > want and lm["dests"]:
            # close the distance: pick the reachable hex nearest the enemy,
            # facing the step direction (free) so the front stays toward him
            scored = []
            for d in lm["dests"]:
                nd = tg.range_between({"col": d["col"], "row": d["row"]}, enemy)
                scored.append((nd, d["cost"], d))
            scored.sort(key=lambda t: (t[0], t[1]))
            nd, _, dest = scored[0]
            if nd < dist:
                face = tg.facing_of_step((dest["col"], dest["row"]),
                                         (enemy["col"], enemy["row"]))
                f = face if face in dest["free_facings"] or dest["any_facing"] else dest["free_facings"][0]
                acts.append((f"{u['slot']} {u['pid'][-2:]} advances to {dest['hexnum']} (range {dist}->{nd})",
                             {"type": "move", "unit": u["pid"],
                              "dest": [dest["col"], dest["row"]], "facing": f}))
                continue
        # in range (or can't improve): pivot the front toward the threat, keep the gun
        face = tg.facing_of_step((u["col"], u["row"]), (enemy["col"], enemy["row"]))
        if face != u["facing"]:
            acts.append((f"{u['slot']} {u['pid'][-2:]} pivots to face {enemy['slot']}",
                         {"type": "pivot", "unit": u["pid"], "facing": face}))
    return acts


def pick_fire(tg, side):
    """Best single fire proposal for the combat segment, or None."""
    cands = []
    for u in tg.s["units"].values():
        if u["side"] != side or u["K"] or u["F"]:
            continue
        if u["pid"] in tg.s["moved"] or u["pid"] in tg.s["fired"]:
            continue
        for t in tg.legal_targets(u["pid"]):
            if not t["legal"]:
                continue
            score = (0 if t["acquired"] else 1,          # keep acquired targets
                     t["hpn_adjusted"] or 99,            # best odds first
                     -t["rounds"], t["range"])
            cands.append((score, u, t))
    if not cands:
        return None
    cands.sort(key=lambda c: c[0])
    _, u, t = cands[0]
    tgt = tg.unit(t["target"])
    return (f"{u['slot']} {u['pid'][-2:]} fires at {tgt['slot']} {t['target'][-2:]} "
            f"(range {t['range']}, needs {t['hpn_adjusted']}+, {t['rounds']} rounds"
            + (", ACQUIRED" if t["acquired"] else "") + ")",
            {"type": "fire", "unit": u["pid"], "target": t["target"]})


def take_movement_segment(tg, side):
    """Run the AI's whole movement segment through the gate; returns log."""
    out = []
    for desc, act in movement_actions(tg, side):
        r = tg.submit(side, act)
        out.append({"desc": desc, "action": act, "verdict": r["verdict"],
                    "result": r.get("result")})
    r = tg.submit(side, {"type": "end_movement"})
    out.append({"desc": f"{side} ends movement", "action": {"type": "end_movement"},
                "verdict": r["verdict"], "result": r.get("result")})
    return out


def take_one_fire(tg, side):
    """One alternating-fire slot: fire the best shot or pass. Returns log."""
    pick = pick_fire(tg, side)
    if pick is None:
        r = tg.submit(side, {"type": "pass_fire"})
        return [{"desc": f"{side} has no shot — passes", "action": {"type": "pass_fire"},
                 "verdict": r["verdict"], "result": r.get("result")}]
    desc, act = pick
    r = tg.submit(side, act)
    out = [{"desc": desc, "action": act, "verdict": r["verdict"], "result": r.get("result")}]
    if not r["verdict"]["legal"]:
        # the gate said no — prove the loop: log it and pass this slot
        r2 = tg.submit(side, {"type": "pass_fire"})
        out.append({"desc": f"{side} proposal rejected by the gate — passes",
                    "action": {"type": "pass_fire"}, "verdict": r2["verdict"],
                    "result": r2.get("result")})
    return out
