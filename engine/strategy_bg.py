"""
strategy_bg.py - A parameterized strategy family for Blue & Gray games
(spec #22: the expertise standard).

A STRATEGY is a numeric genome (theta) that turns game state into ONE plan
per player turn in the plans.py DSL - it never touches the gate directly,
so every order it produces is compiled and legality-checked exactly like a
human's. The family spans the space the first played campaigns explored:
occupation-economy garrisons, concentrated field forces with odds
discipline, endgame hex-grabbing, exit discipline, artillery standoff.
theta == BASELINE approximates the shipped policy AI (everyone pushes the
nearest enemy-credited VP hex); other corners of the space produce
fortress play, mass attacks, or pure occupation racing.

Used by engine/optimize.py for tournament evolution. Deterministic given
(theta, game state); no LLM, no randomness of its own.
"""
import random

GENES = [
    # name, min, max, baseline
    ("garrison_per_10vp", 0.0, 12.0, 0.0),   # strength posted per 10 VP of own-scoring hex
    ("garrison_range", 2.0, 30.0, 8.0),      # only garrison hexes within this distance
    ("hold_factor", 0.0, 1.5, 0.5),          # demand multiplier for hexes already credited to us
    ("deny_weight", 0.0, 2.0, 1.0),          # weight on denying enemy-scoring hexes vs taking ours
    ("mass_min", 0.0, 40.0, 0.0),            # field force advances only above this total strength
    ("focus_value_w", 0.0, 3.0, 1.0),        # objective choice: VP weight
    ("focus_dist_w", 0.0, 3.0, 1.0),         # objective choice: distance penalty
    ("endgame_turn", 8.0, 16.0, 16.0),       # from this GT, spread-grab nearest uncredited hexes
    ("exit_turn", 8.0, 16.0, 16.0),          # from this GT, units on exit hexes exit (1 VP/CSP)
    ("reinf_to_field", 0.0, 1.0, 1.0),       # 1 = reinforcements join field force, 0 = garrisons
    ("arty_standoff", 0.0, 1.0, 1.0),        # 1 = artillery uses standoff, 0 = fights as infantry
    ("night_freeze", 0.0, 1.0, 0.0),         # 1 = hold everything on night turns
]


def baseline():
    return {n: b for n, _, _, b in GENES}


def random_theta(rng):
    return {n: rng.uniform(lo, hi) for n, lo, hi, _ in GENES}


def mutate(theta, rng, rate=0.35, scale=0.25):
    out = dict(theta)
    for n, lo, hi, _ in GENES:
        if rng.random() < rate:
            out[n] = min(hi, max(lo, out[n] + rng.gauss(0, (hi - lo) * scale)))
    return out


def crossover(a, b, rng):
    return {n: (a if rng.random() < 0.5 else b)[n] for n, _, _, _ in GENES}


# ------------------------------------------------------------ plan builder
def _hexnum(h):
    return f"{h[0]:02d}{h[1]:02d}"


def _dist(bg, a, b):
    ax, ay = bg.game.grid.hex_to_pixel(*a)
    bx, by = bg.game.grid.hex_to_pixel(*b)
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5 / max(bg.game.grid.dx, 1)


def _vp_hexes(bg, side):
    """[(hex, pts, mine_scoring, credited_to)] for all occupation hexes."""
    out = []
    key = side.lower()
    for owner_key, hexes in (bg.vp_cfg.get("occupation") or {}).items():
        for hx, pts in hexes.items():
            h = (int(hx[:2]), int(hx[2:]))
            mine = owner_key.lower() in (key, "either")
            theirs = owner_key.lower() != key
            out.append((h, pts, mine, theirs, bg.s["occ"].get(hx)))
    return out


def make_plan(bg, side, theta):
    s = bg.s
    turn = s["turn"]
    units = sorted(bg._live(side), key=lambda u: u["pid"])
    field, orders, assigned = [], [], set()

    # trains and (optionally) artillery keep their doctrine
    for u in units:
        cls = bg.cls(u)
        if cls == "train":
            orders.append({"verb": "run_exit", "units": [u["pid"]]})
            assigned.add(u["pid"])
        elif cls == "artillery" and theta["arty_standoff"] >= 0.5:
            orders.append({"verb": "standoff", "units": [u["pid"]]})
            assigned.add(u["pid"])

    if theta["night_freeze"] >= 0.5 and bg.is_night():
        rest = [u["pid"] for u in units if u["pid"] not in assigned]
        if rest:
            orders.append({"verb": "hold", "units": rest})
        return {"orders": orders}

    # exit discipline: standing on an exit hex late enough -> take the VP
    if turn >= theta["exit_turn"]:
        for u in units:
            if u["pid"] in assigned:
                continue
            if (u["col"], u["row"]) in bg.exit_hexes:
                orders.append({"verb": "run_exit", "units": [u["pid"]]})
                assigned.add(u["pid"])

    pool = [u for u in units if u["pid"] not in assigned]
    vps = _vp_hexes(bg, side)

    # garrison demand: own-scoring (and deny-weighted enemy-scoring) hexes
    demands = []
    for h, pts, mine, theirs, holder in vps:
        w = pts * (1.0 if mine else 0.0)
        if theirs:
            w = max(w, pts * theta["deny_weight"])
        if holder == side:
            w *= theta["hold_factor"]
        need = theta["garrison_per_10vp"] * w / 10.0
        if need >= 1.0:
            demands.append((need, h))
    demands.sort(key=lambda d: -d[0])
    for need, h in demands:
        got = 0.0
        for u in sorted(pool, key=lambda u: _dist(bg, (u["col"], u["row"]), h)):
            if u["pid"] in assigned or got >= need:
                continue
            if _dist(bg, (u["col"], u["row"]), h) > theta["garrison_range"]:
                break
            if (u["col"], u["row"]) == h:
                orders.append({"verb": "hold", "units": [u["pid"]]})
            else:
                orders.append({"verb": "hold", "units": [u["pid"]],
                               "at": _hexnum(h)})
            assigned.add(u["pid"])
            got += bg.strength(u) or 0

    field = [u for u in pool if u["pid"] not in assigned]

    # endgame: spread-grab the nearest uncredited hexes, one unit each
    if turn >= theta["endgame_turn"] and field:
        taken = set()
        for u in list(field):
            cands = [(h, pts) for h, pts, mine, theirs, holder in vps
                     if holder != side and h not in taken]
            if not cands:
                break
            h, _ = min(cands, key=lambda c: _dist(bg, (u["col"], u["row"]), c[0]))
            orders.append({"verb": "push", "units": [u["pid"]],
                           "objective": _hexnum(h)})
            assigned.add(u["pid"])
            taken.add(h)
            field.remove(u)

    # field force: concentrate on ONE focus objective, odds-disciplined
    if field:
        strength = sum(bg.strength(u) or 0 for u in field)
        cx = sum(bg.game.grid.hex_to_pixel(u["col"], u["row"])[0]
                 for u in field) / len(field)
        cy = sum(bg.game.grid.hex_to_pixel(u["col"], u["row"])[1]
                 for u in field) / len(field)

        def center_dist(h):
            hx, hy = bg.game.grid.hex_to_pixel(*h)
            return ((hx - cx) ** 2 + (hy - cy) ** 2) ** 0.5 / max(bg.game.grid.dx, 1)

        targets = [(h, pts) for h, pts, mine, theirs, holder in vps
                   if holder != side and (mine or theta["deny_weight"] > 0.2)]
        pids = [u["pid"] for u in field]
        if targets and strength >= theta["mass_min"]:
            focus = max(targets, key=lambda t: t[1] * theta["focus_value_w"]
                        - center_dist(t[0]) * theta["focus_dist_w"])[0]
            orders.append({"verb": "push", "units": pids,
                           "objective": _hexnum(focus)})
        else:
            orders.append({"verb": "hold", "units": pids})

    return {"orders": orders}


class StrategyPlanner:
    """planner callable for plans.play_game: planner(bg, side) -> plan."""

    def __init__(self, theta):
        self.theta = dict(theta)

    def __call__(self, bg, side):
        return make_plan(bg, side, self.theta)
