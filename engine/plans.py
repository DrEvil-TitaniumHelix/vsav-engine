"""
plans.py - The Plan DSL and plan compiler (expert-AI stage 2).

A PLAN is operational intent for ONE player turn, written in the hobby's
own vocabulary; the COMPILER expands it into individual proposals through
the legality gate. Plans have no authority: every emitted action still
enters via submit() and can be rejected. A plan can only choose among
legal options - it cannot bend a rule, and combat OBLIGATIONS (B&G
7.11/7.12) are never plan territory: the combat phase is always played by
the validated policy, which discharges what the rules mandate.

Plan format (JSON-friendly; designed so a future LLM planner can emit it):

  {"orders": [
     {"verb": "push",     "units": ["u12", "Wilder c"], "objective": "1520"},
     {"verb": "hold",     "units": ["u3"], "at": "1014"},
     {"verb": "standoff", "units": ["u7"]},
     {"verb": "run_exit", "units": ["u30"]}
  ]}

  - units: pids or exact slot names, this side's units only
  - objective/at: "CCRR" string or [col,row]; hold defaults to the unit's
    current hex
  - any unit NOT named in an order behaves exactly as the shipped policy
    AI would (the plan overrides targeting, never invents capabilities)

Verbs (movement phase only):
  push     - advance toward the objective; keeps the policy's local-odds
             sanity (never voluntarily end adjacent to enemies the units
             in contact cannot fight at 1-1, combat being mandatory 7.0)
  hold     - stand at / move toward a hex, same safety rule
  standoff - keep a 2-3 hex bombardment distance (artillery doctrine 8.1)
  run_exit - road-march for the exit hexes and exit when able

Families: Blue & Gray (the stage-2 pilot) and Westwall. The compiler
surface (take_turn / play_game / validate_plan) is family-generic; register
other families in COMPILERS as their adapters land.

Westwall additions: orders may carry an optional "caution" integer (the
minimum acceptable local combat differential a moving unit will accept when
ending adjacent to the enemy; the policy default is -2 [7.0]). run_exit
(German 15.4 map exit) is not compiled yet - plans naming it are rejected
at validation.

The default-unit blocks mirror ai_bluegray._movement_actions /
ai_westwall._movement_actions and must stay behavior-compatible with them;
consolidate when the next family adapter lands rather than fork further.
"""
import ai_bluegray as abg
import ai_napoleonic as anp
import ai_westwall as aww


# ------------------------------------------------------------ plan parsing
VERBS = ("push", "hold", "standoff", "run_exit")
VERBS_BY_MODE = {"bluegray": VERBS,
                 "westwall": ("push", "hold", "standoff")}


def parse_hex(v):
    """"0312" or [3,12] -> (3,12); None if unparseable."""
    if isinstance(v, str) and len(v) == 4 and v.isdigit():
        return int(v[:2]), int(v[2:])
    if isinstance(v, (list, tuple)) and len(v) == 2:
        return int(v[0]), int(v[1])
    return None


def _unit_ref(bg, side, ref):
    """Resolve a pid or exact slot name to a pid of `side`, else None."""
    u = bg.s["units"].get(str(ref))
    if u and u["side"] == side:
        return u["pid"]
    hits = [u["pid"] for u in bg.s["units"].values()
            if u["side"] == side and u["slot"] == ref]
    return hits[0] if len(hits) == 1 else None


def validate_plan(bg, side, plan):
    """Compile-check a plan: list of problems (empty = clean). The gate
    still has the last word on every emitted action."""
    probs = []
    verbs = VERBS_BY_MODE.get(_mode_of(bg), VERBS)
    if not isinstance(plan, dict) or not isinstance(plan.get("orders", []), list):
        return ["plan must be {'orders': [...]}"]
    for i, o in enumerate(plan.get("orders", [])):
        tag = f"order {i}"
        if o.get("verb") not in verbs:
            probs.append(f"{tag}: unknown verb {o.get('verb')!r} (know {verbs})")
            continue
        if "caution" in o and not isinstance(o["caution"], (int, float)):
            probs.append(f"{tag}: caution must be a number")
            continue
        refs = o.get("units") or []
        if not refs:
            probs.append(f"{tag}: no units")
        for r in refs:
            if _unit_ref(bg, side, r) is None:
                probs.append(f"{tag}: unit {r!r} not found on side {side} "
                             "(pid or exact slot name, ambiguous names need pids)")
        if o["verb"] == "push" and parse_hex(o.get("objective")) is None:
            probs.append(f"{tag}: push needs objective 'CCRR' or [col,row]")
        if o["verb"] == "hold" and "at" in o and parse_hex(o["at"]) is None:
            probs.append(f"{tag}: hold 'at' unparseable")
    return probs


def _assignments(bg, side, plan):
    out = {}
    for o in plan.get("orders", []):
        if o.get("verb") not in VERBS:
            continue
        for r in o.get("units") or []:
            pid = _unit_ref(bg, side, r)
            if pid:
                out[pid] = o
    return out


# ------------------------------------------------------------ B&G compiler
def _bg_planned_movement(bg, side, plan):
    """Movement-phase generator: plan verbs for assigned units, the policy's
    own behavior for everyone else. Yields (side, action, desc); receives
    the gate's legality verdict."""
    dist = abg._Dist(bg.game)
    assign = _assignments(bg, side, plan)

    # reinforcements (15.0) - policy behavior, mirrors ai_bluegray
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
            break

    efoes = abg._stacks(bg, bg.game.enemy(side))

    def near_enemy(h):
        return min((dist(h, eh) for eh in efoes), default=9)

    def move_toward(u, target, desc):
        """Shared push/hold march step with the policy's odds sanity."""
        here = (u["col"], u["row"])
        dd = bg.dests(u)
        if not dd:
            return None
        scored = [(dist(h, target), h) for h in dd
                  if abg._local_odds_ok(bg, u, h, efoes)]
        if not scored:
            return None
        scored.sort()
        if dist(here, target) <= scored[0][0]:
            return None                       # no progress - stand
        return (side, {"type": "move", "unit": u["pid"],
                       "dest": list(scored[0][1])}, desc)

    for pid in sorted(u["pid"] for u in bg._live(side)):
        if pid not in bg.s["units"] or pid in bg.s["moved"]:
            continue
        u = bg.unit(pid)
        here = (u["col"], u["row"])
        order = assign.get(pid)
        verb = order["verb"] if order else None

        if verb == "run_exit" or (verb is None and bg.cls(u) == "train"):
            if here in bg.exit_hexes:
                yield (side, {"type": "exit", "unit": pid},
                       "the Train exits the map [16.1/17.11]")
                continue
            dd = bg.dests(u)
            if dd:
                tgt = min(bg.exit_hexes, key=lambda h: dist(here, h))
                best = min(dd, key=lambda h: (dist(h, tgt), h))
                if dist(best, tgt) < dist(here, tgt):
                    yield (side, {"type": "move", "unit": pid, "dest": list(best)},
                           f"rolls for the exit {tgt} [18.23]")
            continue

        if verb == "standoff" or (verb is None and bg.cls(u) == "artillery"):
            obj = parse_hex((order or {}).get("objective")) or abg._objective(bg, u)

            def standoff(h):
                dmin = near_enemy(h)
                return (0 if 2 <= dmin <= 3 else 1, dist(h, obj), h)
            cands = [h for h in bg.dests(u) if near_enemy(h) >= 2]
            if not cands:
                continue
            best = min(cands, key=standoff)
            if standoff(best) < standoff(here):
                yield (side, {"type": "move", "unit": pid, "dest": list(best)},
                       "takes a bombardment standoff [8.1/8.41]")
            continue

        if verb == "push":
            item = move_toward(u, parse_hex(order["objective"]),
                               f"{u['slot']} pushes on "
                               f"{parse_hex(order['objective'])} [plan]")
            if item:
                yield item
            continue

        if verb == "hold":
            at = parse_hex(order.get("at")) or here
            if at != here:
                item = move_toward(u, at, f"{u['slot']} falls in at {at} [plan]")
                if item:
                    yield item
            continue                          # standing fast IS the order

        # no order: the policy's own doctrine
        obj = abg._objective(bg, u)
        item = move_toward(u, obj, f"{u['slot']} advances toward {obj}")
        if item:
            yield item

    yield (side, {"type": "end_movement"}, "movement phase complete [4.1]")


def _bg_turn_actions(bg, plan, resolve_for=None):
    """One planned player turn: planned movement, then the COMBAT PHASE IS
    THE POLICY'S (obligated battles, retreats, advances, bombardments -
    7.x is mandatory, not plan territory)."""
    side = bg.s["mover"]
    start = (bg.s["turn"], side)
    if bg.s["phase"] == "movement" and not bg.s["over"]:
        gen = _bg_planned_movement(bg, side, plan or {})
        okv = None
        while True:
            try:
                item = gen.send(okv)
            except StopIteration:
                break
            okv = yield item
            if bg.s["over"] or (bg.s["turn"], bg.s["mover"]) != start:
                return
    if not bg.s["over"] and bg.s["phase"] == "combat" \
       and (bg.s["turn"], bg.s["mover"]) == start:
        yield from abg.turn_actions(bg, resolve_for)


# ------------------------------------------------------------ WW compiler
def _ww_planned_movement(ww, side, plan):
    """Westwall movement-phase generator: plan verbs for assigned units, the
    policy's own behavior for everyone else. Mirrors
    ai_westwall._movement_actions exactly for unassigned units."""
    dist = aww._Dist(ww.game)
    s = ww.s
    assign = _assignments(ww, side, plan)

    # reinforcements [15.x] - policy behavior, mirrors ai_westwall; a plan
    # order on an arriving unit steers its 15.14 drive-on objective
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
                            order = assign.get(pid)
                            obj = parse_hex((order or {}).get("objective")) \
                                or aww._objective(ww, u, dist)
                            cands = [h2 for h2 in dd
                                     if aww._local_diff_ok(ww, u, h2)]
                            if cands:
                                best = min(cands,
                                           key=lambda h2: (dist(h2, obj), h2))
                                yield (side, {"type": "move", "unit": pid,
                                              "dest": list(best)},
                                       f"{e['slot']} drives on [15.14]")
                    break
            if not placed:
                continue

    # unit moves: plan verbs override targeting, never capabilities
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
        order = assign.get(pid)
        verb = order["verb"] if order else None
        caution = int(order.get("caution", -2)) if order else -2

        if verb == "standoff" or (verb is None and ww.is_arty(pid)):
            rng = ww.stats(pid).get("range", 4)
            foes = aww._foes(ww, side)
            obj = parse_hex((order or {}).get("objective")) \
                or aww._objective(ww, u, dist)

            def standoff(h):
                dmin = min((dist(h, eh) for eh in foes), default=99)
                return (0 if 2 <= dmin <= rng else 1, dist(h, obj), h)
            cands = [h for h in dd
                     if min((dist(h, eh) for eh in foes), default=99) >= 2]
            if cands:
                best = min(cands, key=standoff)
                if standoff(best) < standoff(here):
                    yield (side, {"type": "move", "unit": pid,
                                  "dest": list(best)},
                           "artillery takes a barrage standoff [8.11/8.41]")
            continue

        if verb == "push":
            target = parse_hex(order["objective"])
            desc = f"{ww.cat(pid)['desig']} pushes on {target} [plan]"
        elif verb == "hold":
            target = parse_hex(order.get("at")) or here
            if target == here:
                continue                      # standing fast IS the order
            desc = f"{ww.cat(pid)['desig']} falls in at {target} [plan]"
        else:
            target = aww._objective(ww, u, dist)
            desc = f"{ww.cat(pid)['desig']} advances toward {target}"
        scored = [(dist(h, target), h) for h in sorted(dd)
                  if aww._local_diff_ok(ww, u, h, caution)]
        if not scored:
            continue
        scored.sort()
        if dist(here, target) <= scored[0][0]:
            continue                          # no progress - stand
        yield (side, {"type": "move", "unit": pid,
                      "dest": list(scored[0][1])}, desc)

    yield (side, {"type": "end_movement"}, "movement phase complete [4.1]")


def _ww_turn_actions(ww, plan, resolve_for=None):
    """One planned Westwall player turn: planned movement injected into the
    policy's turn loop - pendings (demolition/FPF/retreat/advance) and the
    whole combat phase stay the validated policy's (7.x is mandatory)."""
    side = ww.s["mover"]
    return aww.turn_actions(ww, resolve_for,
                            movement_gen=_ww_planned_movement(ww, side,
                                                              plan or {}))


COMPILERS = {"bluegray": _bg_turn_actions, "westwall": _ww_turn_actions}


# ------------------------------------------------------------ drivers
def _mode_of(tg):
    # class-name dispatch: engine modules are importable both as `bluegray`
    # and `engine.bluegray`, so isinstance would see two different classes
    return {"BlueGrayGame": "bluegray",
            "WestwallGame": "westwall",
            "NapoleonicGame": "napoleonic"}.get(type(tg).__name__)


def _policy_of(tg):
    return {"bluegray": abg, "westwall": aww,
            "napoleonic": anp}.get(_mode_of(tg), abg)


def take_turn(tg, plan=None, resolve_for=None):
    """Play the current mover's whole player turn from a plan. No plan (or
    no orders) = the shipped policy AI unchanged.

    Napoleonic family: decisions interleave between the sides, so there
    is no turn-plan DSL - the 'plan' IS a strategy_nap doctrine genome
    (theta), handed to ai_napoleonic, and one call plays every decision
    the current decider owns (napoleonic keeps game-over in flow, not
    state, so ai_napoleonic._over is the stop test)."""
    if _mode_of(tg) == "napoleonic":
        return anp.take_turn(tg, theta=plan)
    if tg.s["over"]:
        return []
    comp = COMPILERS.get(_mode_of(tg))
    if comp is None:
        raise NotImplementedError(
            "no plan compiler for this game family yet - register it in "
            "plans.COMPILERS")
    pol = _policy_of(tg)
    if not plan or not plan.get("orders"):
        return pol.take_turn(tg, resolve_for)
    return pol._drive(comp(tg, plan, resolve_for), tg)


def play_game(tg, planners=None, max_turns=None):
    """AI-vs-AI driver where each side may have a planner. planners maps
    side -> plan dict, or side -> callable(tg, side) returning a fresh plan
    each player turn; absent sides play pure policy. Returns (turn, log).

    Napoleonic family: the 'plan' is a static doctrine genome, so each
    side's planner is resolved once and ai_napoleonic.play_game drives
    the interleaved decider flow."""
    planners = planners or {}
    if _mode_of(tg) == "napoleonic":
        thetas = {sd: (pl(tg, sd) if callable(pl) else pl)
                  for sd, pl in planners.items()}
        return anp.play_game(tg, max_turns=max_turns, thetas=thetas)
    full = []
    guard = 0
    limit = (max_turns or tg.turns) * 2 + 6
    while not tg.s["over"] and guard < limit:
        side = tg.s["mover"]
        before = (tg.s["turn"], side)
        pl = planners.get(side)
        plan = pl(tg, side) if callable(pl) else pl
        full.extend(take_turn(tg, plan))
        if before == (tg.s["turn"], tg.s["mover"]) and not tg.s["over"]:
            full.append({"desc": "planned play could not end the turn - stopping",
                         "error": True})
            break
        guard += 1
        if max_turns and tg.s["turn"] > max_turns:
            break
    return tg.s["turn"], full


def policy_mirror_planner(tg, side):
    """A plan that spells out, as explicit orders, what the policy would do:
    every combat unit pushes on its policy objective, artillery stands off,
    the train runs for the exit. Exercises the whole DSL every turn - the
    stage-2 plumbing proof."""
    orders = []
    for u in sorted(tg._live(side), key=lambda x: x["pid"]):
        cls = tg.cls(u)
        if cls == "train":
            orders.append({"verb": "run_exit", "units": [u["pid"]]})
        elif cls == "artillery":
            orders.append({"verb": "standoff", "units": [u["pid"]]})
        else:
            obj = abg._objective(tg, u)
            orders.append({"verb": "push", "units": [u["pid"]],
                           "objective": [obj[0], obj[1]]})
    return {"orders": orders}
