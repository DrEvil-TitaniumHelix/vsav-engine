"""
strategy_ww.py - A parameterized strategy family for Westwall quad games
(spec #22: the expertise standard), Westwall: Arnhem first.

A STRATEGY is a numeric genome (theta) that turns game state into ONE plan
per player turn in the plans.py DSL - it never touches the gate directly,
so every order it produces is compiled and legality-checked exactly like a
human's. The genes span the decision space the shipped policy declares
itself weak in, plus the levers the 17.x VP schedule actually pays:

  Allied - WHEN to stop driving blindly at the Arnhem bridge and start
  banking geography (Waal zone = 5 VP/unit/GT [17.11], Rijn zone = 10
  VP/unit at the end), how far airborne battalions stray from their DZ
  (LOC is <= 7 hexes [17.32]), how much of the column stays behind as
  corridor pickets (each LOC failure pays the German 3 VP/GT [17.35]),
  and how bad a mandatory battle a unit will voluntarily accept (each
  Allied loss pays the German 5 VP [17.1]).

  German - how strongly units steer for the corridor road to cut the
  ground LOC [17.31/17.33] and for the airborne pockets, versus the
  policy's plain nearest-enemy attraction.

theta == BASELINE approximates the shipped ai_westwall policy; other
corners produce zone-banking Allied play or corridor-scissors German play.

Used by engine/optimize.py for tournament evolution via families.py.
Deterministic given (theta, game state); no LLM, no randomness of its own.
"""

GENES = [
    # name, min, max, baseline (baseline ~= shipped policy AI)
    ("all_waal_turn", 1.0, 11.0, 11.0),      # from this GT ground units bank Waal-zone VP [17.11]
    ("all_rijn_turn", 1.0, 11.0, 11.0),      # from this GT ground units head north of the Rijn [17.11]
    ("all_airborne_reach", 0.0, 12.0, 6.0),  # airborne engage foes within this range of their DZ [17.32]
    ("all_mass_min", 0.0, 30.0, 0.0),        # ground column advances only above this combined attack
    ("all_loc_guard", 0.0, 1.0, 0.0),        # fraction of ground units held back as corridor pickets [17.35]
    ("all_caution", -2.0, 6.0, -2.0),        # min acceptable local differential when closing [7.0]
    ("ger_loc_cut_w", 0.0, 3.0, 0.0),        # German pull toward corridor-road LOC hexes [17.31/17.33]
    ("ger_dz_w", 0.0, 3.0, 0.0),             # German pull toward airborne pockets
    ("ger_mass_min", 0.0, 30.0, 0.0),        # German field force advances only above this combined attack
    ("arty_standoff", 0.0, 1.0, 1.0),        # 1 = barrage standoff [8.11], 0 = artillery fights in the line
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


def corners():
    """Doctrine-seeded corners of the space (spec #22: the LLM seeds the
    population from knowledge; these encode the 17.x VP arithmetic the
    baseline ignores)."""
    dash = baseline()
    dash.update(all_waal_turn=2.0, all_rijn_turn=8.0, all_airborne_reach=4.0,
                all_mass_min=8.0, all_loc_guard=0.2, all_caution=0.0)
    scissors = baseline()
    scissors.update(ger_loc_cut_w=2.5, ger_dz_w=1.0, ger_mass_min=8.0)
    return [dash, scissors]


GENE_PROSE = {
    "all_waal_turn": "from GT {v:.0f}, Allied ground units break off the "
                     "bridge drive and bank Waal-zone VP (5/unit/GT, 17.11)",
    "all_rijn_turn": "from GT {v:.0f}, Allied ground units head north of "
                     "the Rijn for the 10 VP/unit end bonus (17.11)",
    "all_airborne_reach": "airborne battalions engage enemies up to "
                          "{v:.0f} hexes from their DZ (LOC limit is 7, "
                          "17.32)",
    "all_mass_min": "the Allied column advances only above {v:.0f} "
                    "combined attack strength - below that it stands",
    "all_loc_guard": "{v:.0%} of Allied ground units (rearmost first) "
                     "stand as corridor pickets against LOC cuts (17.35)",
    "all_caution": "Allied units accept a mandatory battle only at a "
                   "local differential of {v:.0f} or better (policy "
                   "floor is -2, 7.0)",
    "ger_loc_cut_w": "German units weight corridor-road LOC hexes at "
                     "{v:.2f} (0 = ignore the corridor, chase units)",
    "ger_dz_w": "German units weight the airborne pockets at {v:.2f}",
    "ger_mass_min": "the German field force advances only above {v:.0f} "
                    "combined attack strength",
    "arty_standoff": "artillery {alt} (1 = 8.11 barrage standoff, "
                     "0 = fights in the line)",
}


# ------------------------------------------------------------ plan builder
def _hexnum(h):
    return f"{h[0]:02d}{h[1]:02d}"


def _parse_zone(zone):
    return [(int(k[:2]), int(k[2:])) for k in zone]


def _att(ww, pid):
    return ww.stats(pid).get("att", 0) or 0


def _corridor_targets(ww):
    """Hexes that currently carry the Allied ground LOC AND sit on the road
    net - cutting one severs everything forward of it [17.31/17.33]."""
    board = ww.rules_board()
    gzoc = ww.game.zoc_hexes(board, "Ger")
    apos = ww._positions("All")
    gpos = ww._positions("Ger")
    blocked = {h for h in gzoc if h not in apos} | gpos
    exits = {tuple(h) for h in ww.loc_cfg.get("ground_exit", [[1, 5], [1, 6]])}
    ok = ww._ground_loc_set(blocked, exits)
    road = set()
    for h in ok:
        for nb in ww.game.neighbors(*h):
            if ww.side_feat(h, nb).get("road") == "road":
                road.add(h)
                break
    return road


def make_plan(ww, side, theta):
    s = ww.s
    turn = s["turn"]
    hd = ww.game.hex_distance

    def d(a, b):
        v = hd(tuple(a), tuple(b))
        return 999 if v is None else v

    units = [u for u in ww._live(side) if ww.cls(u["pid"]) != "dz"]
    orders, assigned = [], set()

    # artillery doctrine
    for u in units:
        if ww.is_arty(u["pid"]) and theta["arty_standoff"] >= 0.5:
            orders.append({"verb": "standoff", "units": [u["pid"]]})
            assigned.add(u["pid"])

    foes = {(x["col"], x["row"]): x for x in ww._live(ww.game.enemy(side))}

    if side == "All":
        caution = int(round(theta["all_caution"]))

        def push(pids, obj):
            o = {"verb": "push", "units": pids, "objective": _hexnum(obj)}
            if caution != -2:
                o["caution"] = caution
            orders.append(o)

        # airborne: engage within reach of the divisional DZ, else hold it
        dzpos = {ww.cat(x["pid"])["desig"].split()[0]: (x["col"], x["row"])
                 for x in ww._live("All", dz=True) if ww.cls(x["pid"]) == "dz"}
        reach = theta["all_airborne_reach"]
        airborne = [u for u in units if u["pid"] not in assigned
                    and ww.is_airborne(u["pid"])]
        for u in airborne:
            here = (u["col"], u["row"])
            div = str(ww.cat(u["pid"]).get("division", ""))
            dz = dzpos.get(div, here)
            near = [f for f in foes if d(f, dz) <= reach]
            obj = min(near, key=lambda h: (d(here, h), h)) if near else dz
            push([u["pid"]], obj)
            assigned.add(u["pid"])

        # ground column: pickets, then the era's objective
        ground = [u for u in units if u["pid"] not in assigned]
        entry = tuple((ww.loc_cfg.get("ground_exit") or [[1, 5]])[0])
        ground.sort(key=lambda u: (d((u["col"], u["row"]), entry), u["pid"]))
        n_guard = int(round(theta["all_loc_guard"] * len(ground)))
        for u in ground[:n_guard]:
            orders.append({"verb": "hold", "units": [u["pid"]]})
            assigned.add(u["pid"])
        column = ground[n_guard:]
        if not column:
            return {"orders": orders}

        zone = None
        if turn >= theta["all_rijn_turn"]:
            zone = _parse_zone(ww.rijn_zone)
        elif turn >= theta["all_waal_turn"]:
            zone = _parse_zone(ww.waal_zone)
        if zone:
            # spread-claim: each unit its own nearest unclaimed zone hex
            taken = set()
            for u in column:
                here = (u["col"], u["row"])
                cands = [h for h in zone if h not in taken]
                if not cands:
                    break
                h = min(cands, key=lambda z: (d(here, z), z))
                taken.add(h)
                push([u["pid"]], h)
                assigned.add(u["pid"])
        else:
            strength = sum(_att(ww, u["pid"]) for u in column)
            pids = [u["pid"] for u in column]
            if strength >= theta["all_mass_min"]:
                push(pids, (34, 23))          # the Arnhem road bridge approach
            else:
                orders.append({"verb": "hold", "units": pids})
            assigned.update(pids)
        return {"orders": orders}

    # ---------------- German
    field = [u for u in units if u["pid"] not in assigned]
    if not field:
        return {"orders": orders}
    strength = sum(_att(ww, u["pid"]) for u in field)
    if strength < theta["ger_mass_min"]:
        orders.append({"verb": "hold", "units": [u["pid"] for u in field]})
        return {"orders": orders}

    corridor = _corridor_targets(ww) if theta["ger_loc_cut_w"] > 0.05 else set()
    airborne_pos = [h for h, x in foes.items() if ww.is_airborne(x["pid"])]
    for u in field:
        here = (u["col"], u["row"])
        cands = []
        if foes:
            cands.append((min(foes, key=lambda h: (d(here, h), h)), 0.0))
        if corridor:
            cands.append((min(corridor, key=lambda h: (d(here, h), h)),
                          theta["ger_loc_cut_w"]))
        if airborne_pos and theta["ger_dz_w"] > 0.05:
            cands.append((min(airborne_pos, key=lambda h: (d(here, h), h)),
                          theta["ger_dz_w"]))
        if not cands:
            continue
        obj = min(cands, key=lambda c: (d(here, c[0]) - 3.0 * c[1], c[0]))[0]
        orders.append({"verb": "push", "units": [u["pid"]],
                       "objective": _hexnum(obj)})
    return {"orders": orders}


class StrategyPlanner:
    """planner callable for plans.play_game: planner(ww, side) -> plan."""

    def __init__(self, theta):
        self.theta = dict(theta)

    def __call__(self, ww, side):
        return make_plan(ww, side, self.theta)
