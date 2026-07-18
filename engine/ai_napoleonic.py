"""
ai_napoleonic.py - the AI opponent's policy for GBoNW-family games
(any NapoleonicGame, schema 3/4).

Doctrine identical to ai_westwall.py/ai_bluegray.py: the policy READS
public state and SUBMITS every proposal through the one legality gate
(NapoleonicGame.submit). Rejections are logged as proof-of-enforcement.

Napoleonic decisions INTERLEAVE between the sides (LIM draws, reaction
windows, shock windows, return fire), so unlike the strategic-family AIs
this policy is STATELESS per action: `turn_actions` re-reads the game
state before every pick and keeps yielding while the game is waiting on
its side (`NapoleonicGame.decider()`); it stops the moment a decision
belongs to the other side (a human answers their own windows). Resuming
later continues cleanly because every pick derives from state, never
from generator position.

Policy (honest, not clever - a beta opponent playing a legal, complete,
replayable game):
  pool - commit a division's LIM while its fatigue is under 6, or
    whenever the enemy is within 3 hexes (it will fight anyway)
    [13.1/13.2]; initiative picks an own-side LIM first [4.4].
  activations - attempt the Full Activation when the division has an
    enemy within 8 hexes (melee needs Full) or its leader's rating
    makes the roll safe; otherwise take the roll-free Limited half-MA
    march [4.5.1/4.6] rather than gamble on the Breakdown Table [4.7];
    breakdown ENEMY/REACTIVATE offers are taken [4.7 - a free
    activation].
  movement - one action per unit [4.6.1]: disordered units reform,
    limbered guns unlimber inside range, unlimbered guns rotate onto
    targets, cavalry preserves May Charge (never spends over half MA
    while enemies are near [5.1.2]), infantry closes on the nearest
    enemy preferring destinations that keep the enemy in the front arc,
    leaders stay in command range of their division [4.3.3].
  fire - every capable unit fires at the best legal target (the gate's
    8.1.1 hierarchy/arc/LOS decide legality).
  shock (tier 2+) - infantry melees an adjacent front-hex enemy stack
    when its own stack has at least equal SP; cavalry in good morale
    charges non-square targets at 2-4 hexes [8.4].
  windows - infantry tries to form square against a charge [8.4.2#4];
    melee defenders return fire, skirmishers evade [8.2.1#3]; melee
    continues are always STOOD (voluntary rout is never taken [8.5.3]);
    reaction windows fire when entitled, cavalry in good morale
    reaction-charges, lone leaders and skirmishers evade adjacent
    movers, everything else declines [6.2]; offensive fire is always
    returned [8.1.2].
  rally - every eligible unit attempts its rally [12.0].
Known-weak, declared: no melee supports [8.2.1#2], no strategic
movement declarations [5.2], no reaction_limber [6.2.5], no
countercharge play, no multi-turn plans, no square-vs-cavalry
formation play outside the charge window. All optional - skipping
them is legal.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import formations as fm             # noqa: E402


# Doctrine knobs (spec #22): the shipped policy's constants, exposed so a
# strategy genome (engine/strategy_nap.py) can vary them. theta=None (or a
# missing key) plays the shipped baseline EXACTLY - the values here ARE the
# policy documented above, and strategy_nap reads its gene baselines from
# this dict (single source of the shipped constants).
DOCTRINE = {
    "pool_fatigue_max": 6.0,    # commit a LIM below this fatigue [13.1/13.2]
    "pool_enemy_near": 3.0,     # ...or with an enemy this close [13.2]
    "init_own_first": 1.0,      # initiative picks an own-side LIM first [4.4]
    "full_enemy_dist": 8.0,     # Full Activation with enemy within this [4.6]
    "full_rating_min": 7.0,     # ...or leader activation rating >= this [4.5.1]
    "bd_take": 1.0,             # take breakdown Enemy/Reactivate offers [4.7]
    "hold_dist": 0.0,           # stand-off: never close inside this range [5.1]
    "cav_preserve_slack": 4.0,  # May-Charge cap while enemy <= MA+this [5.1.2]
    "charge_accept": 1.0,       # cavalry declares charges at all [8.4]
    "melee_sp_ratio": 1.0,      # melee only at own SP >= this x theirs [8.2]
    "square_form": 1.0,         # form square against a charge [8.4.2#4]
    "unlimber_slack": 0.0,      # unlimber at fire range + this [6.3.7]
    # v2 maneuver/targeting doctrine (all 0 = the shipped nearest-foe /
    # front-arc-first behavior EXACTLY - zero weights take the legacy
    # code paths). Only units that are destroyed/routed/unsteady count
    # toward the A15.1 thresholds, so target choice is where strategy
    # lives: press the nearly-broken, lock the already-broken, mass
    # effort instead of spreading it.
    "tgt_weak_w": 0.0,          # movement objective: pull toward damaged/
                                # shaken enemies (finish them) [9.x/A15.1]
    "tgt_arty_w": 0.0,          # movement objective: pull toward enemy guns
    "mass_w": 0.0,              # movement objective: pull toward enemies
                                # own units already converge on (mass)
    "fire_finish_w": 0.0,       # fire target: prefer worse-morale/damaged
    "shock_finish_w": 0.0,      # melee/charge target: prefer worse-morale
}


def _th(theta, key):
    return DOCTRINE[key] if theta is None else theta.get(key, DOCTRINE[key])


# ----------------------------------------------------------------- helpers
def _over(g):
    """Game over, exactly as flow() computes it: a victory [A15.1] or
    the scenario turn limit."""
    v = g.s.get("victory") or g._victory_state()
    return bool(v.get("winner")) or g.s["turn"] > g.turns


def _live_foes(g, side):
    return [v for v in g.s["units"].values()
            if v["side"] != side and g.on_map(v) and v["arm"] != "leader"]


def _nearest_foe(g, side, at):
    foes = _live_foes(g, side)
    if not foes:
        return None
    return min(foes, key=lambda v: (g._dist(at, (v["col"], v["row"])),
                                    v["pid"]))


_STATE_I = {"good": 0, "shaken": 1, "unsteady": 2, "routed": 3}


def _finish_score(v):
    """How close a unit is to feeding the A15.1 count: morale ladder
    position plus a step for SP already lost [9.x/11.1]."""
    return _STATE_I.get(v.get("morale_state", "good"), 0) \
        + (1 if v.get("sp_lost") else 0)


def _pick_foe(g, side, at, theta=None):
    """The unit's movement objective. Zero weights (the shipped
    doctrine) = _nearest_foe exactly; v2 weights re-score the pick:
    closer is still better, but damaged/shaken enemies (tgt_weak_w),
    enemy artillery (tgt_arty_w) and enemies own units already
    converge on (mass_w - friends within 3 hexes) pull the objective
    [A15.1 threshold arithmetic]."""
    tw = _th(theta, "tgt_weak_w")
    aw = _th(theta, "tgt_arty_w")
    mw = _th(theta, "mass_w")
    if tw == 0 and aw == 0 and mw == 0:
        return _nearest_foe(g, side, at)
    foes = _live_foes(g, side)
    if not foes:
        return None
    own = [(u["col"], u["row"]) for u in g.s["units"].values()
           if u["side"] == side and g.on_map(u) and u["arm"] != "leader"]

    def key(v):
        vhex = (v["col"], v["row"])
        d = g._dist(at, vhex)
        s = float(d) - tw * _finish_score(v) \
            - aw * (1.0 if v["arm"].startswith("artillery") else 0.0)
        if mw:
            s -= mw * sum(1 for h in own if g._dist(h, vhex) <= 3)
        return (round(s, 6), d, v["pid"])
    return min(foes, key=key)


def _front_set(g, u, c=None, r=None, f=None):
    c = u["col"] if c is None else c
    r = u["row"] if r is None else r
    f = u["facing"] if f is None else f
    return {tuple(h) for h in fm.front_hexes(g.game, c, r, f, g._kind(u))}


def _stack_sp(stack):
    """Rough shock strength of a stack: troops at face SP, artillery at
    half (it dies alone and never counts in the odds [8.2.1#4/8.5.1])."""
    sp = 0.0
    for v in stack:
        sp += v["sp"] * (0.5 if v["arm"].startswith("artillery") else 1.0)
    return sp


def _has_target(g, u):
    """A fire target inside range, arc and LOS exists right now."""
    rng = g._fire_range(u)
    here = (u["col"], u["row"])
    for v in _live_foes(g, u["side"]):
        if g._dist(here, (v["col"], v["row"])) > rng:
            continue
        if not g._in_fire_arc(u, v["col"], v["row"]):
            continue
        if g._los(here, (v["col"], v["row"]))[0]:
            return True
    return False


# ----------------------------------------------------- movement decisions
def _move_pick(g, u, budget, avoid, strat, cap=None, theta=None):
    """Best single move action for `u` (or None to hold): closes on the
    nearest enemy, prefers keeping it in the front arc and avoiding
    movement-disorder risk. `cap` limits spent MPs (cavalry May Charge
    preservation [5.1.2]); `hold_dist` doctrine keeps a stand-off
    distance (never voluntarily closing inside it)."""
    obj = _pick_foe(g, u["side"], (u["col"], u["row"]), theta)
    if obj is None:
        return None
    ohex = (obj["col"], obj["row"])
    here = (u["col"], u["row"])
    d_now = g._dist(here, ohex)
    faced_now = ohex in _front_set(g, u) or d_now > 1
    hold = _th(theta, "hold_dist")
    try:
        reach = g.reachable(u["pid"], budget=budget,
                            avoid_adjacent=avoid, strat=strat)
    except Exception:
        return None
    best = None
    for (c, r, f), (cost, path, dis) in reach.items():
        if cap is not None and cost > cap + 1e-9:
            continue
        d = g._dist((c, r), ohex)
        # stand-off doctrine: gate the approach, never force a retreat -
        # a unit already inside the hold range may still fight/refit
        if hold > 0 and (c, r) != here and d < min(hold, d_now):
            continue
        front = {tuple(h) for h in fm.front_hexes(
            g.game, c, r, f, g._kind(u))}
        # facing quality: adjacent must hold the enemy in the front
        # (melee/fire need it); at distance prefer roughly facing it
        face_pen = 0 if (ohex in front or
                         (d > 1 and g._dist(min(front, key=lambda h:
                          g._dist(h, ohex)), ohex) < d)) else 1
        risk = 1 if dis else 0
        key = (d, face_pen, risk, round(cost, 2), c, r, f)
        if best is None or key < best[0]:
            best = (key, (c, r, f))
    if best is None:
        return None
    (d, face_pen, risk, cost, *_), (c, r, f) = best
    stay = (c, r) == here
    if stay and f == u["facing"]:
        return None
    # only act when it improves the approach (or fixes the facing)
    if not stay and d >= d_now and (faced_now or face_pen):
        return None
    if stay and faced_now:
        return None
    what = "wheels toward" if stay else "advances on"
    return ({"type": "move", "unit": u["pid"], "dest": [c, r],
             "facing": f},
            f"{u['slot']} {what} {obj['slot']} [5.1/6.1]")


def _unit_action(g, u, budget, avoid, strat, theta=None):
    """The unit's one action this activation [4.6.1], or None."""
    pid = u["pid"]
    # reform out of disorder before anything else [6.4.1]
    if u["formation"] == "disorder":
        for form in ("column", "line", "unlimbered"):
            if form in g.F.defs and g._formation_change_ok(u, form)[0]:
                cost = g.F.action_cost(u, "change_formation", u["ma"])
                if cost is None or cost <= budget + 1e-9:
                    return ({"type": "change_formation", "unit": pid,
                             "to": form},
                            f"{u['slot']} reforms from disorder [6.4.1]")
        return None
    obj = _pick_foe(g, u["side"], (u["col"], u["row"]), theta)
    if obj is None:
        return None
    d = g._dist((u["col"], u["row"]), (obj["col"], obj["row"]))
    if u["arm"].startswith("artillery"):
        rng = g._fire_range(u)
        if u["formation"] == "unlimbered":
            if _has_target(g, u):
                return None                    # hold and fire
            # rotate onto the nearest enemy if that alone finds a shot
            return _move_pick(g, u, budget, avoid, strat, theta=theta)
        # limbered: unlimber inside range, else keep rolling forward
        if d <= rng + _th(theta, "unlimber_slack") \
                and g._formation_change_ok(u, "unlimbered")[0]:
            cost = g.F.action_cost(u, "change_formation", u["ma"])
            if cost is None or cost <= budget + 1e-9:
                return ({"type": "change_formation", "unit": pid,
                         "to": "unlimbered"},
                        f"{u['slot']} unlimbers in range [6.3.7]")
        return _move_pick(g, u, budget, avoid, strat, theta=theta)
    if u["arm"] == "cavalry":
        # May Charge preservation: never spend over half MA while a
        # charge could develop [5.1.2/8.4]; moot doctrine when this
        # genome never declares charges
        chg = _th(theta, "charge_accept") >= 0.5
        cap = int(u["ma"]) // 2 \
            if chg and d <= int(u["ma"]) + _th(theta, "cav_preserve_slack") \
            else None
        if chg and 2 <= d <= 4:
            return None                        # charge range already
        return _move_pick(g, u, budget, avoid, strat, cap=cap, theta=theta)
    return _move_pick(g, u, budget, avoid, strat, theta=theta)


def _leader_action(g, u, act, budget):
    """Leaders hold the division together: stay within command range of
    the division's combat units [4.3.3], keep out of enemy reach."""
    members = [g.unit(p) for p in act["incommand"]
               if p != u["pid"] and not g.unit(p).get("dead")]
    members = [m for m in members if m["arm"] != "leader"]
    if not members:
        return None
    here = (u["col"], u["row"])

    def spread(h):
        return max(g._dist(h, (m["col"], m["row"])) for m in members)

    def danger(h):
        foe = _nearest_foe(g, u["side"], h)
        return -min(3, g._dist(h, (foe["col"], foe["row"]))) if foe else 0
    if spread(here) <= 2 and danger(here) >= -1:
        return None
    try:
        reach = g.reachable(u["pid"], budget=budget)
    except Exception:
        return None
    cands = sorted(((spread((c, r)), danger((c, r)), cost, c, r, f)
                    for (c, r, f), (cost, _p, _d) in reach.items()),
                   key=lambda t: t[:3])
    if not cands:
        return None
    s0, d0, _, c, r, f = cands[0]
    if (c, r) == here or (s0, d0) >= (spread(here), danger(here)):
        return None
    return ({"type": "move", "unit": u["pid"], "dest": [c, r],
             "facing": f},
            f"{u['slot']} keeps the division in command [4.3.3]")


# ------------------------------------------------------- combat decisions
def _fire_pick(g, side, pids, theta=None):
    """First legal (proposed) fire action among `pids`. fire_finish_w=0
    keeps the shipped front-arc-first nearest scan (with its early
    break) byte-for-byte; a positive weight re-scores targets toward
    the damaged/shaken (the A15.1 count is morale states [9.x])."""
    fw = _th(theta, "fire_finish_w")
    for pid in sorted(pids):
        u = g.unit(pid)
        if u.get("dead") or pid in g.s["fired"]:
            continue
        if not g._fire_capable(u)[0]:
            continue
        here = (u["col"], u["row"])
        rng = g._fire_range(u)
        front = _front_set(g, u)
        if fw == 0:
            foes = sorted(_live_foes(g, side),
                          key=lambda v: (0 if (v["col"], v["row"]) in front
                                         else 1,
                                         g._dist(here, (v["col"], v["row"])),
                                         v["pid"]))
            for v in foes:
                if g._dist(here, (v["col"], v["row"])) > rng:
                    break
                a = {"type": "fire", "unit": pid, "target": v["pid"]}
                if g.propose(side, a)["legal"]:
                    return (a, f"{u['slot']} fires on {v['slot']} [8.1]")
            continue
        foes = sorted(_live_foes(g, side),
                      key=lambda v: (0 if (v["col"], v["row"]) in front
                                     else 1,
                                     round(g._dist(here, (v["col"],
                                                          v["row"]))
                                           - fw * _finish_score(v), 6),
                                     g._dist(here, (v["col"], v["row"])),
                                     v["pid"]))
        for v in foes:
            if g._dist(here, (v["col"], v["row"])) > rng:
                continue
            a = {"type": "fire", "unit": pid, "target": v["pid"]}
            if g.propose(side, a)["legal"]:
                return (a, f"{u['slot']} fires on {v['slot']} [8.1]")
    return None


def _shock_pick(g, side, act, theta=None):
    """Melee / charge declarations for a Full Activation (tier 2+)."""
    if not getattr(g, "_p4", False) or act.get("atype") != "full":
        return None
    for pid in sorted(act["incommand"]):
        u = g.unit(pid)
        if u.get("dead") or u["arm"] not in ("infantry", "cavalry"):
            continue
        if not g._may_initiate_melee(u)[0]:
            continue
        here = (u["col"], u["row"])
        sw = _th(theta, "shock_finish_w")
        if u["arm"] == "infantry":
            front = _front_set(g, u)
            for v in sorted(_live_foes(g, side),
                            key=lambda x: (round(-sw * _finish_score(x),
                                                 6), x["pid"])):
                dhex = (v["col"], v["row"])
                if dhex not in front or g._dist(here, dhex) != 1:
                    continue
                mine = _stack_sp([w for w in g._stack(*here, side=side)
                                  if w["arm"] == "infantry"
                                  and g._may_initiate_melee(w)[0]])
                theirs = _stack_sp(g._stack(*dhex, side=v["side"]))
                if mine < _th(theta, "melee_sp_ratio") * theirs:
                    continue           # no hopeless shocks
                a = {"type": "melee", "unit": pid, "target": v["pid"]}
                if g.propose(side, a)["legal"]:
                    return (a, f"{u['slot']} melees {v['slot']} "
                               "[8.2/8.3]")
            continue
        # cavalry charge [8.4]
        if _th(theta, "charge_accept") < 0.5:
            continue
        if u.get("blown", 0) or u["morale_state"] != "good" \
                or u["formation"] == "disorder":
            continue
        for v in sorted(_live_foes(g, side),
                        key=lambda x: (round(g._dist(here, (x["col"],
                                                            x["row"]))
                                             - sw * _finish_score(x), 6),
                                       g._dist(here, (x["col"],
                                                      x["row"])),
                                       x["pid"])):
            d = g._dist(here, (v["col"], v["row"]))
            if d < 2 or d > 4:
                continue
            if v["formation"] == "square":
                continue               # never charge a formed square
            a = {"type": "charge", "unit": pid, "target": v["pid"]}
            if g.propose(side, a)["legal"]:
                return (a, f"{u['slot']} charges {v['slot']} [8.4]")
    return None


# ------------------------------------------------------- window decisions
def _melee_window_action(g, side, theta=None):
    pm = g.s["pending_melee"]
    stage = pm["stage"]
    ent = pm.get("entitled") or {}
    if stage == "square_window":
        pid = next(iter(ent))
        form = _th(theta, "square_form") >= 0.5
        return ({"type": "square_choice", "form": form, "unit": pid},
                "infantry tries to form square [8.4.2#4]" if form else
                "declines the square - stands in formation [8.4.2#4]")
    if stage == "return_window":
        for pid, kinds in sorted(ent.items()):
            if "reaction_move" in kinds:
                dests = g._skirmish_moves(g.unit(pid))
                if dests:
                    a = tuple(pm["ahex"])
                    best = max(sorted(dests),
                               key=lambda h: g._dist(h, a))
                    return ({"type": "reaction_move", "unit": pid,
                             "dest": list(best)},
                            "skirmishers slip away [8.2.1#3]")
            if "melee_return" in kinds:
                return ({"type": "melee_return", "unit": pid},
                        "defenders return fire [8.2.1#3]")
        return ({"type": "melee_no_return"},
                "no return fire - resolve the shock")
    if stage in ("continue_def", "continue_att"):
        return ({"type": "melee_stand"},
                "stands for another melee round [8.5.3]")
    return None


def _react_window_action(g, side):
    pr = g.s["pending_react"]
    mover = g.unit(pr["mover"])
    mhex = (mover["col"], mover["row"])
    for pid, kinds in sorted(pr["entitled"].items()):
        e = g.unit(pid)
        if "reaction_fire" in kinds:
            return ({"type": "reaction_fire", "unit": pid},
                    f"{e['slot']} reaction fires [6.2]")
        if "reaction_charge" in kinds and e["morale_state"] == "good" \
                and mover["formation"] != "square":
            return ({"type": "reaction_charge", "unit": pid},
                    f"{e['slot']} reaction charges [6.2.3]")
        if "reaction_face" in kinds:
            want = g._facing_toward((e["col"], e["row"]), mhex,
                                    g._kind(e))
            turn = 2 if (want - e["facing"]) % fm.FACINGS <= 6 else -2
            return ({"type": "reaction_face", "unit": pid,
                     "turn": turn},
                    f"{e['slot']} wheels to face the threat [6.2.3]")
        if "reaction_reverse" in kinds and \
                g._dist((e["col"], e["row"]), mhex) <= 2:
            return ({"type": "reaction_reverse", "unit": pid},
                    f"{e['slot']} reverses away [6.2.5/6.2.6]")
        if "reaction_move" in kinds and \
                g._dist((e["col"], e["row"]), mhex) <= 2:
            dests = g._reaction_moves(e)
            if dests:
                best = max(sorted(dests),
                           key=lambda h: g._dist(h, mhex))
                return ({"type": "reaction_move", "unit": pid,
                         "dest": list(best)},
                        f"{e['slot']} evades [6.2.2/6.2.7]")
    return ({"type": "decline_reaction"}, "reactions declined [6.2]")


# ------------------------------------------------------ command decisions
def _pool_pick(g, side, theta=None):
    lims = []
    near = int(round(_th(theta, "pool_enemy_near")))
    for lim in g._available_lims(side):
        dk = g._div_by_lim(side, lim)
        if dk is None:
            lims.append(lim)
            continue
        fat = g.s["fatigue"].get(dk, 0)
        if fat < _th(theta, "pool_fatigue_max") or g._enemies_within(dk, near):
            lims.append(lim)
    return ({"type": "set_pool", "lims": lims},
            f"commits {len(lims)} LIM(s) - fatigued divisions rest "
            "[13.1/13.2 + A15.1]")


def _initiative_pick(g, side, theta=None):
    pool = g.s["pool"]
    own = [ref for ref in pool if ref.startswith(side + ":")]
    if _th(theta, "init_own_first") < 0.5:
        foreign = [ref for ref in pool if not ref.startswith(side + ":")]
        ref = (foreign or pool)[0]
    else:
        ref = (own or pool)[0]
    return ({"type": "choose_initiative_lim", "lim": ref},
            f"initiative opens with {ref} [4.4]")


def _want_full(g, dk, theta=None):
    """Attempt the Full Activation when the division needs to fight
    (enemy within 8 hexes - melee/charge and free adjacency need Full
    [4.6/8.2-8.4]) or when the leader's rating makes the roll safe;
    otherwise the roll-free Limited half-MA march [4.5.1/4.6.2] beats
    gambling the whole activation on the Breakdown Table [4.7]."""
    if g._at_div_breakpoint(dk):
        return False                   # gate forbids Full [11.2.1]
    if g._enemies_within(dk, int(round(_th(theta, "full_enemy_dist")))):
        return True
    return int(g._rating(dk)["activation"]) >= _th(theta, "full_rating_min")


def _choice_pick(g, side, act, tried, theta=None):
    if act["kind"] == "independent":
        ind = act["indep"]
        cands = [dk for dk in ind["eligible"] if dk not in ind["done"]]
        if not cands or len(ind["done"]) >= ind["allowed"]:
            return ({"type": "end_activation"},
                    "remaining independents decline [A4.3.2]")
        dk = cands[0]
        base = {"type": "activation_choice", "division": dk}
    else:
        dk = act["div"]
        base = {"type": "activation_choice"}
    order = ("full", "limited") if _want_full(g, dk, theta) \
        else ("limited", "full")
    for choice in order:
        if choice == "full" and g._at_div_breakpoint(dk):
            continue
        a = dict(base, choice=choice)
        if json.dumps(a, sort_keys=True) not in tried:
            return (a, f"{dk} attempts the {choice} activation "
                       "[4.5.1/4.6]")
    return ({"type": "end_activation"}, "activation declined [4.5.1]")


def _bd_pick(g, act, theta=None):
    if _th(theta, "bd_take") >= 0.5:
        for dk in act["bd_closest"]:
            if g.s["act_count"].get(dk, 0) < 2:
                return ({"type": "bd_activate", "division": dk},
                        f"takes the breakdown activation with {dk} [4.7]")
    return ({"type": "bd_decline"}, "breakdown offer declined [4.7]")


def _activation_pick(g, side, act, tried, theta=None):
    """One action inside an open activation: moves, then fire, then
    shock, then close [4.6.1/8.1.1]."""
    strat = bool(act.get("strat"))
    avoid = act["atype"] == "limited"
    if act["stage"] == "move":
        for pid in sorted(act["incommand"]):
            u = g.unit(pid)
            if pid in g.s["moved"] or u.get("dead") \
                    or u.get("morale_state") == "routed":
                continue
            item = _leader_action(g, u, act, act["budget"].get(pid)) \
                if u["arm"] == "leader" else \
                _unit_action(g, u, act["budget"].get(pid, 0.0),
                             avoid, strat, theta)
            if item and json.dumps(item[0], sort_keys=True) not in tried:
                return item
    if not strat:
        item = _fire_pick(g, side, act["incommand"], theta)
        if item and json.dumps(item[0], sort_keys=True) not in tried:
            return item
        item = _shock_pick(g, side, act, theta)
        if item and json.dumps(item[0], sort_keys=True) not in tried:
            return item
    return ({"type": "end_activation"}, "activation complete [4.6]")


def _nonlim_pick(g, side):
    o = g._nonlim_options(side)
    if o["divisions"]:
        dk = sorted(o["divisions"])[0]
        return ({"type": "non_lim", "division": dk},
                f"{dk} takes its Non-LIM limited activation [3.0.C.1]")
    if o["units"]:
        pid = sorted(o["units"])[0]
        return ({"type": "non_lim", "unit": pid},
                f"Out of Command unit {pid} moves [4.6.2.b]")
    return ({"type": "pass_non_lim"}, "Non-LIM pass [3.0.C]")


def _rally_pick(g, side):
    for u in sorted(g.s["units"].values(), key=lambda x: x["pid"]):
        if u["side"] != side or not g.on_map(u):
            continue
        if u.get("morale_state", "good") == "good":
            continue
        if u["pid"] in g.s.get("rallied", []):
            continue
        a = {"type": "rally", "unit": u["pid"]}
        if g.propose(side, a)["legal"]:
            return (a, f"{u['slot']} attempts to rally [12.0]")
    return ({"type": "end_rally"}, "rally phase complete [12.0]")


# ------------------------------------------------------------ the picker
def _next_action(g, side, tried, theta=None):
    """The policy's next (action, desc) for `side` given the current
    state, or None to stop. Every branch ends in a guaranteed-legal
    closer so a rejected pick can never loop. `theta` = optional
    strategy_nap doctrine genome; None plays the shipped baseline."""
    s = g.s
    if s.get("pending_melee") and \
            s["pending_melee"].get("window_owner") == side:
        item = _melee_window_action(g, side, theta)
        if item and json.dumps(item[0], sort_keys=True) in tried:
            # degradation ladder: the minimal legal answer
            pm = s["pending_melee"]
            item = ({"type": "melee_no_return"}, "fallback") \
                if pm["stage"] == "return_window" else \
                ({"type": "square_choice", "form": False}, "fallback") \
                if pm["stage"] == "square_window" else \
                ({"type": "melee_withdraw"}, "fallback")
            if json.dumps(item[0], sort_keys=True) in tried:
                return None
        return item
    if s.get("pending_react") and s["pending_react"]["side"] == side:
        item = _react_window_action(g, side)
        if json.dumps(item[0], sort_keys=True) in tried:
            item = ({"type": "decline_reaction"}, "fallback")
            if json.dumps(item[0], sort_keys=True) in tried:
                return None
        return item
    if s.get("pending_fire") and \
            s["pending_fire"]["defender_side"] == side:
        a = {"type": "return_fire"}
        if g.propose(side, a)["legal"] and \
                json.dumps(a, sort_keys=True) not in tried:
            return (a, "returns fire - simultaneous [8.1.2]")
        a = {"type": "decline_return"}
        return None if json.dumps(a, sort_keys=True) in tried \
            else (a, "declines the return fire [8.1.2]")
    ph = s["phase"]
    if ph == "rally":
        item = _rally_pick(g, side)
    elif getattr(g, "_cmd", False):
        if ph == "command":
            item = _pool_pick(g, side, theta)
        elif ph == "initiative":
            item = _initiative_pick(g, side, theta)
        elif ph == "activation":
            act = s.get("act")
            if act is None:
                return None
            if act["pending"] == "bd_offer":
                item = _bd_pick(g, act, theta)
            elif act["pending"] == "choice":
                item = _choice_pick(g, side, act, tried, theta)
            else:
                item = _activation_pick(g, side, act, tried, theta)
        elif ph == "non_lim":
            item = _nonlim_pick(g, side)
        else:
            return None
    else:
        # pre-command schema-2 flow (mechanics harnesses)
        moved = set(s["moved"])
        item = None
        for u in sorted(s["units"].values(), key=lambda x: x["pid"]):
            if u["side"] != side or u["pid"] in moved \
                    or u.get("dead") \
                    or u.get("morale_state") == "routed":
                continue
            it = _leader_action(
                g, u, {"incommand": [v["pid"] for v in
                                     s["units"].values()
                                     if v["side"] == side]},
                float(u["ma"])) if u["arm"] == "leader" else \
                _unit_action(g, u, float(u["ma"]), False, False, theta)
            if it and json.dumps(it[0], sort_keys=True) not in tried:
                item = it
                break
        if item is None:
            item = _fire_pick(g, side,
                              [u["pid"] for u in s["units"].values()
                               if u["side"] == side], theta)
        if item is None or json.dumps(item[0], sort_keys=True) in tried:
            item = ({"type": "end_turn"}, "player turn complete")
    if item and json.dumps(item[0], sort_keys=True) in tried:
        return None
    return item


# ---------------------------------------------------------------- drivers
def turn_actions(g, side=None, theta=None):
    """Generator of (side, action, desc) while the game is waiting on
    `side` (default: the current decider). Stops as soon as a decision
    belongs to the other side - a human opponent answers their own
    windows and the policy resumes afterwards from state. `theta` =
    optional strategy_nap doctrine genome (spec #22); None plays the
    shipped baseline exactly."""
    side = side or g.decider()
    tried = set()
    guard = 0
    while not _over(g) and g.decider() == side and guard < 4000:
        guard += 1
        item = _next_action(g, side, tried, theta)
        if item is None:
            return
        action, desc = item
        ok = yield (side, action, desc)
        if ok:
            tried.clear()
        else:
            tried.add(json.dumps(action, sort_keys=True))


def _log_entry(side, action, desc, r):
    return {"side": side, "action": action, "desc": desc,
            "legal": r["verdict"]["legal"],
            "reasons": r["verdict"]["reasons"],
            "result": r.get("result")}


def _drive(gen, g):
    log = []
    try:
        side, action, desc = gen.send(None)
        while True:
            r = g.submit(side, action)
            log.append(_log_entry(side, action, desc, r))
            side, action, desc = gen.send(r["verdict"]["legal"])
    except StopIteration:
        pass
    return log


def take_turn(g, side=None, theta=None):
    """Play every decision belonging to `side` (default: the current
    decider) until the flow passes to the other side or the game ends."""
    if _over(g):
        return []
    return _drive(turn_actions(g, side, theta), g)


class TurnStepper:
    """One gate action at a time - the engine hook for spacebar /
    animated stepping. Identical action stream to take_turn."""

    def __init__(self, g, side=None, theta=None):
        self.sg = g
        self.side = side or g.decider()
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


def play_game(g, max_turns=None, on_turn=None, thetas=None):
    """AI-vs-AI: whichever side the game waits on plays, until the game
    ends (victory [A15.1] or the turn limit). `thetas` = optional
    side -> strategy_nap genome; absent sides play the shipped
    baseline."""
    full = []
    guard = 0
    limit = (max_turns or g.turns) * 400 + 100
    while not _over(g) and guard < limit:
        before = (g.s["turn"], g.decider(), g.s["n"])
        who = g.decider()
        log = take_turn(g, who, (thetas or {}).get(who))
        full.extend(log)
        if on_turn:
            on_turn(g, log)
        after = (g.s["turn"], g.decider(), g.s["n"])
        if before == after and not _over(g):
            full.append({"desc": "AI could not advance the game - "
                                 "stopping", "error": True})
            break
        guard += 1
        if max_turns and g.s["turn"] > max_turns:
            break
    return g.s["turn"], full
