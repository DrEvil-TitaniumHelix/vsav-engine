"""
ai_strategic.py - the AI opponent's policy for the strategic games (Afrika
Korps campaign; any StrategicGame).

Same doctrine as the tactical ai.py: the AI READS the same public state a
human sees and SUBMITS every proposal through the one legality gate
(StrategicGame.submit).  It has no other door.  When it proposes something
illegal the gate rejects it, the rejection is logged as proof-of-enforcement,
and the AI moves on.  Reading engine internals is fine (ai.py reads tg.s the
same way); only writes go through submit().

Policy (honest, not clever — a beta opponent that plays a legal, complete,
replayable game; it is not a strong player):
  arrivals — Axis rolls for supply and lands it; both sides land due
    reinforcements and debark sea units at the controlled port nearest the
    front.
  supply   — supply units are kept ALIVE and well clear of the enemy: losing
    the last one collapses the whole army (24.5), and the isolation trace has
    no length limit, so a safe rear supply still keeps units un-isolated. They
    trail the army only as far as they can stay >= 6 hexes from any enemy.
  movement — combat units drive toward the nearest contested victory hex (a
    fortress or home base not held; AK is won by controlling ground, 4.1) but
    NEVER advance into a hex from which they could not trace supply (24.1); an
    already-isolated unit falls back to regain the trace (24.2). A unit never
    voluntarily ends in an enemy ZOC — a forced attack, 8.4 — UNLESS it, with
    friends already adjacent, can attack that stack at 2-1 or better AND a
    supply unit is in range to sustain it (a strong attack needs supply, 14.1;
    without it the unit would be trapped and eliminated, 11.6).
  combat  — discharge every 8.4 obligation: each ZOC-locked unit attacks every
    adjacent enemy combined (11.2/11.4), pulling in co-adjacent friends for
    better odds, most-constrained unit first (11.7/11.31); sustain with a
    supply unit when the odds need it; resolve the winner's retreat / exchange
    / advance choices; eliminate a unit that is forced to attack but can make
    no legal attack (7.4/11.6).
Known-weak, declared: no 11.6 soak-off search, no replacements/substitutes,
no Rommel escort bonus — all optional; skipping them is legal, never wrong.
"""


# --------------------------------------------------------------------------- utils
def _submit(sg, side, action, log, desc):
    r = sg.submit(side, action)
    log.append({"side": side, "desc": desc, "action": action,
                "verdict": r["verdict"], "result": r.get("result")})
    return r["verdict"]["legal"]


class _Dist:
    """Memoized hex distance — hex_distance BFSes the whole board per call."""
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


def _pix(game, hx):
    return game.grid.hex_to_pixel(*hx)


def _pix_d2(game, a, b):
    ax, ay = _pix(game, a); bx, by = _pix(game, b)
    return (ax - bx) ** 2 + (ay - by) ** 2


def _objective(sg, u, dist):
    """The hex this unit is driving toward. Territorial, not a lunge at the
    nearest enemy: head for the nearest contested victory hex (a fortress or
    home base not currently held by us). Combat is incidental to the advance
    and only initiated at strong odds (see _do_movement). Falls back to the
    nearest enemy unit, then the enemy home base."""
    side = u["side"]
    enemy = sg.game.enemy(side)
    ehex = (u["col"], u["row"])
    mine = {(f["col"], f["row"]) for f in sg._combat_units(side)}
    targets = [h for h in sg.victory_hexes if h not in mine]
    if targets:
        return min(targets, key=lambda h: _pix_d2(sg.game, ehex, h))
    foes = [(e["col"], e["row"]) for e in sg._combat_units(enemy)]
    if foes:
        return min(foes, key=lambda h: _pix_d2(sg.game, ehex, h))
    return ehex


def _def_factor(sg, epid):
    e = sg.unit(epid)
    return sg.game.defense_factor(e["slot"], (e["col"], e["row"]))


def _supply_hex_list(sg, side):
    """Board positions of this side's usable supply units."""
    return [(u["col"], u["row"]) for u in sg.s["units"].values()
            if u["side"] == side and sg.on_map(u)
            and sg.game.unit_class(u["slot"]) == "supply"
            and u["pid"] not in sg.s["no_sustain"]]


def _supply_connected(sg, side):
    """Every hex from which a friendly supply unit can be traced (24.1): the
    supply hexes plus all hexes reachable from them by a path free of enemy
    ZOC, enemy combat units, the board edge and prohibited hexsides. Computed
    once per turn (reverse of the engine's own isolation trace) so isolation
    can be tested in O(1) per candidate destination. Returns (connected, sup).
    A hex X is NON-isolated iff X is a supply hex, X is in `connected`, or X has
    a neighbour in `connected` across a legal hexside (the unit itself may sit
    in an enemy ZOC and still trace out — the from-hex is exclusive)."""
    sup = set(sg._supply_hexes(side))
    connected = set(sup)
    if not sup:
        return connected, sup
    g = sg.game
    ezoc = sg._ezoc_for(side)
    blocked = sg._trace_blocked(side)
    frontier = list(sup)
    while frontier:
        nxt = []
        for cur in frontier:
            for nb in g.neighbors(*cur):
                if nb in connected or g.hexside_prohibited(cur, nb) \
                   or not g.on_map(*nb) or nb in ezoc or nb in blocked:
                    continue
                connected.add(nb)
                nxt.append(nb)
        frontier = nxt
    return connected, sup


def _nonisolated(sg, hx, connected, sup):
    """Would a combat unit at hx be able to trace supply (24.1)? See
    _supply_connected. Empty supply set → everything is isolated."""
    if not sup:
        return False
    if hx in connected:
        return True
    g = sg.game
    return any(nb in connected and not g.hexside_prohibited(hx, nb)
               for nb in g.neighbors(*hx))


def _supply_in_range(sg, side, hx, sup_hexes, rad, dist):
    """Roughly, is a supply unit within sustaining range of hx (14.1/14.2)?
    A fast, permissive hex-distance test (ZOC-blocking is ignored here) — the
    AI uses it only to decide whether to SEEK contact; the actual attack is
    validated for supply by the gate when the battle is declared, so an
    over-optimistic 'yes' just falls back to the gate, never a wrong result."""
    return any(dist(hx, s) <= rad for s in sup_hexes)


def _stack_def(sg, side, fh):
    """Combined defense of the whole enemy stack on hex fh — a lone attacker
    totals the defense of every unit it engages (11.2/11.4), so the AI must
    weigh the whole stack, not one counter."""
    enemy = sg.game.enemy(side)
    return sum(sg.game.defense_factor(e["slot"], fh)
               for e in sg._combat_units(enemy)
               if (e["col"], e["row"]) == fh)


def _atk_factor(sg, pid):
    return sg.game.stats(sg.unit(pid)["slot"])[0]


# --------------------------------------------------------------------------- arrivals
def _do_arrivals(sg, side, log):
    ap = sg.arrivals_panel()
    # Axis: roll for supply, then land it; Allied: land its granted supply
    if ap["supply"]["can_roll"]:
        _submit(sg, side, {"type": "roll_supply"}, log, "rolls for sea supply")
        ap = sg.arrivals_panel()
    if ap["supply"]["pending"] and ap["ports"]:
        port = _front_port(sg, side, ap["ports"])
        _submit(sg, side, {"type": "land_supply", "port": port}, log,
                "lands the supply unit at a controlled port")
    # debark sea units that must land this turn (land at the nearest port)
    for su in sg.arrivals_panel()["at_sea"]:
        if not su["must_land"]:
            continue
        ports = sg.arrivals_panel()["ports"]
        if not ports:
            break
        port = _front_port(sg, side, ports)
        _submit(sg, side, {"type": "debark", "unit": su["pid"], "port": port},
                log, f"lands {su['slot']} from the sea")
    # land every due reinforcement at the port nearest the front
    for due in sg.arrivals_panel()["due"]:
        ports = sg.arrivals_panel()["ports"]
        if not ports:
            break
        port = _front_port(sg, side, ports)
        _submit(sg, side,
                {"type": "land_reinforcement", "unit": due["pid"], "port": port},
                log, f"brings up {due['slot']}")


def _front_port(sg, side, ports):
    """The controlled port closest to the enemy — reinforcements enter where
    they are needed."""
    enemy = sg.game.enemy(side)
    foes = [(e["col"], e["row"]) for e in sg._combat_units(enemy)]
    if not foes:
        foes = [h for h in sg.victory_hexes]
    if not foes:
        return ports[0]["hex"] if isinstance(ports[0], dict) else ports[0]
    def hx(p):
        return p["hex"] if isinstance(p, dict) else p
    return hx(min(ports,
                  key=lambda p: min(_pix_d2(sg.game, tuple(hx(p)), f)
                                    for f in foes)))


# --------------------------------------------------------------------------- movement
def _do_movement(sg, side, log, dist):
    enemy = sg.game.enemy(side)
    rad = (sg.combat.get("attack_supply") or {}).get("radius", 5) if sg.combat else 0
    sup_hexes = _supply_hex_list(sg, side) if sg.combat else []
    # supply-connectivity (24.1): never advance a unit into isolation, and pull
    # an already-isolated unit back to a hex that can trace supply
    connected, supset = _supply_connected(sg, side) if sg.combat else (set(), set())
    # stacking (6.1): reinforcements pile up on the home-base port when they
    # land; a hex over the limit at end of movement is illegal, so a unit on an
    # over-stacked hex is dispersed even if it means not advancing. Live counts
    # of my combat units per hex, decremented as they move off.
    stack_max = ((sg.game.spec.get("movement") or {}).get("stacking") or {}).get("max", 3)
    counts = {}
    for u in sg._combat_units(side):
        h = (u["col"], u["row"])
        counts[h] = counts.get(h, 0) + 1
    # committed attack factor already promised against each enemy hex this turn
    committed = {}
    for e in sg._combat_units(side):     # units already adjacent count as committed
        for f in sg._combat_units(enemy):
            fh = (f["col"], f["row"])
            if sg._engageable((e["col"], e["row"]), fh):
                committed[fh] = committed.get(fh, 0) + _atk_factor(sg, e["pid"])
    movers = sorted((u for u in sg._combat_units(side)), key=lambda u: u["pid"])
    for u in movers:
        if u["pid"] in sg.s["moved"]:
            continue
        lm = sg.legal_moves(u["pid"])
        if not lm["can_act"] or not lm["dests"]:
            continue
        obj = _objective(sg, u, dist)
        cur = (u["col"], u["row"])
        cur_d = dist(cur, obj)
        cur_iso = sg.combat and not _nonisolated(sg, cur, connected, supset)
        cur_over = counts.get(cur, 0) > stack_max
        foes = [(f["col"], f["row"]) for f in sg._combat_units(enemy)]
        best_adv = None      # advance (no contact): (dist, cost, dest)
        best_atk = None      # deliberate contact: (dist, cost, dest, foe_hex, myfactor)
        for d in lm["dests"]:
            dh = (d["col"], d["row"])
            # never advance a unit into a hex it could not trace supply from
            # (24.1) — but a unit that MUST vacate an over-stacked hex (6.1) may
            # go anywhere legal (an immediate stall is worse than an isolation
            # risk it can recover from), and if the side has no supply at all
            # every hex is isolated, so the gate would just freeze the army
            if sg.combat and supset and not cur_over \
               and not _nonisolated(sg, dh, connected, supset):
                continue
            touch = [fh for fh in foes if sg._engageable(dh, fh)]
            dd = dist(dh, obj)
            if not touch or not sg.combat:
                # no adjacent enemy — or no combat gate at all (Tier 1): the AI
                # never voluntarily ends in a ZOC it would be forced to attack
                if not touch:
                    cand = (dd, d["cost"], dh)
                    if best_adv is None or cand < best_adv:
                        best_adv = cand
            else:
                # will I (plus friends already committed) reach a STRONG attack
                # (2-1 or better) on some foe hex? weigh the WHOLE enemy stack
                # there (11.2/11.4). The AI only initiates combat when it
                # clearly wins — it never volunteers weak units into a losing
                # forced attack (7.4/11.6).
                mf = _atk_factor(sg, u["pid"])
                for fh in touch:
                    have = committed.get(fh, 0) + mf
                    if have >= 2 * _stack_def(sg, side, fh) \
                       and _supply_in_range(sg, side, dh, sup_hexes, rad, dist):
                        cand = (dd, d["cost"], dh, fh, mf)
                        if best_atk is None or cand < best_atk:
                            best_atk = cand
                        break
        if best_atk is not None:
            _, _, dh, fh, mf = best_atk
            if _submit(sg, side, {"type": "move", "unit": u["pid"],
                                  "dest": list(dh)}, log,
                       f"{u['slot']} closes to attack"):
                committed[fh] = committed.get(fh, 0) + mf
                counts[cur] = counts.get(cur, 0) - 1
                counts[dh] = counts.get(dh, 0) + 1
                _place_rommel_if_pending(sg, log)
            continue
        if best_adv is not None and (best_adv[0] < cur_d or cur_iso or cur_over):
            # advance toward the objective — or, if currently cut off from
            # supply, fall back to the nearest supplied hex to break isolation
            # (24.2) even if it means giving ground
            dh = best_adv[2]
            if cur_over and best_adv[0] >= cur_d and not cur_iso:
                desc = f"{u['slot']} disperses from the overstacked hex"
            elif cur_iso and best_adv[0] >= cur_d:
                desc = f"{u['slot']} falls back to regain supply"
            else:
                desc = f"{u['slot']} advances toward the front"
            if _submit(sg, side, {"type": "move", "unit": u["pid"],
                                  "dest": list(dh)}, log, desc):
                counts[cur] = counts.get(cur, 0) - 1
                counts[dh] = counts.get(dh, 0) + 1
                _place_rommel_if_pending(sg, log)
        # else: holding position (connected, no improving safe destination)


def _do_supply_movement(sg, side, log, dist):
    """Keep supply units alive and connected. Losing the last supply unit
    collapses the whole army (24.5), so supply trails the army only as far as
    it can stay well clear of the enemy (capture, 15.x); the isolation trace
    has no length limit, so a safe rear supply still keeps the army supplied."""
    combat = sg._combat_units(side)
    if not combat:
        return
    xs = [sg.game.grid.hex_to_pixel(u["col"], u["row"]) for u in combat]
    cx = sum(p[0] for p in xs) / len(xs)
    cy = sum(p[1] for p in xs) / len(xs)
    enemy = sg.game.enemy(side)
    foes = [(e["col"], e["row"]) for e in sg._combat_units(enemy)]
    # SAFE = the supply must stay this many hexes from every enemy. Losing the
    # only supply unit isolates the WHOLE army (24.5 = instant collapse), and
    # the isolation trace has no length limit — so supply keeps its distance and
    # follows the army only as far as safety allows. It never needs to be near
    # the front to keep units un-isolated; it only needs to be reachable.
    SAFE = 6

    def enemy_gap(hx):
        return min((dist(hx, f) for f in foes), default=99)

    def to_army(hx):
        x, y = sg.game.grid.hex_to_pixel(*hx)
        return (x - cx) ** 2 + (y - cy) ** 2

    sups = sorted((u for u in sg.s["units"].values()
                   if u["side"] == side and sg.on_map(u)
                   and sg.game.unit_class(u["slot"]) == "supply"),
                  key=lambda u: u["pid"])
    for su in sups:
        if su["pid"] in sg.s["moved"]:
            continue
        lm = sg.legal_moves(su["pid"])
        if not lm["can_act"]:
            continue
        cur = (su["col"], su["row"])
        cands = [cur] + [(d["col"], d["row"]) for d in lm["dests"]]
        safe = [h for h in cands if enemy_gap(h) >= SAFE]
        if safe:
            tgt = min(safe, key=to_army)     # closest to the army while staying safe
            note = f"{su['slot']} closes up behind the line"
        else:
            tgt = max(cands, key=enemy_gap)  # trapped — flee to the safest hex
            note = f"{su['slot']} pulls back from the enemy"
        if tgt != cur:
            _submit(sg, side, {"type": "move", "unit": su["pid"],
                               "dest": list(tgt)}, log, note)


def _place_rommel_if_pending(sg, log):
    pr = sg.s.get("pending_rommel")
    if not pr:
        return
    owner = sg.unit(pr["unit"])["side"]
    choices = pr.get("choices") or []
    if choices:
        _submit(sg, owner, {"type": "place_rommel", "hex": choices[0]}, log,
                "places the displaced headquarters with its nearest unit")


# --------------------------------------------------------------------------- combat
def _resolve_retreat(sg, panel, log):
    pend = panel["pending"]
    chooser = pend["chooser"]
    for unit in pend["units"]:
        opts = unit["options"]
        if opts:
            return _submit(sg, chooser,
                           {"type": "retreat", "unit": unit["pid"],
                            "path": opts[0]["path"]}, log,
                           f"retreats {unit['slot']}")
        return _submit(sg, chooser,
                       {"type": "retreat", "unit": unit["pid"],
                        "eliminate": True}, log,
                       f"{unit['slot']} has no retreat route — eliminated")
    return False


def _minimal_exchange(involved, owe):
    """Smallest set of involved units whose factors total >= owe with no
    removable member (7.5)."""
    best = None
    n = len(involved)
    for mask in range(1, 1 << n):
        pick = [involved[i] for i in range(n) if mask & (1 << i)]
        tot = sum(p["factor"] for p in pick)
        if tot < owe:
            continue
        if any(tot - p["factor"] >= owe for p in pick):
            continue                    # a member is unnecessary
        cand = (len(pick), tot, [p["pid"] for p in pick])
        if best is None or cand < best:
            best = cand
    return best[2] if best else [p["pid"] for p in involved]


def _resolve_exchange(sg, panel, log):
    pend = panel["pending"]
    pids = _minimal_exchange(pend["involved"], pend["owe"])
    return _submit(sg, pend["winner"],
                   {"type": "exchange_loss", "units": pids}, log,
                   f"pays the exchange ({pend['owe']} factors)")


def _do_advances(sg, side, log, dist):
    """Optionally advance into vacated fortress/escarpment hexes (16.1).
    Advance a unit when it moves the unit toward its objective."""
    for _ in range(8):
        panel = sg.combat_panel()
        pend = panel["pending"]
        if not pend or pend["kind"] != "advance":
            return
        advancers = pend["advancers"]
        hexes = [tuple(h) for h in pend["hexes"]]
        if not advancers or not hexes:
            return
        moved = False
        for a in advancers:
            u = sg.unit(a["pid"])
            obj = _objective(sg, u, dist)
            for hx in hexes:
                if not sg._engageable((u["col"], u["row"]), hx):
                    continue
                if dist(hx, obj) <= dist((u["col"], u["row"]), obj):
                    if _submit(sg, side, {"type": "advance", "unit": a["pid"],
                                          "hex": list(hx)}, log,
                               f"advances {u['slot']} onto the vacated hex"):
                        moved = True
                        break
            if moved:
                break
        if not moved:
            return


def _find_supply(sg, side, attackers, defenders):
    """A supply unit that can legally sustain this attack (13.2/14.2 trace)."""
    for su in sg.s["units"].values():
        if su["side"] != side or not sg.on_map(su):
            continue
        if sg.game.unit_class(su["slot"]) != "supply":
            continue
        if su["pid"] in sg.s["no_sustain"]:
            continue
        v = sg.propose(side, {"type": "battle", "attackers": attackers,
                              "defenders": defenders, "supply": su["pid"]})
        if v["legal"]:
            return su["pid"]
    return None


def _adjacent_enemies(sg, side, hx, undefended_only=True):
    enemy = sg.game.enemy(side)
    return [e["pid"] for e in sg._combat_units(enemy)
            if sg._engageable(hx, (e["col"], e["row"]))
            and (not undefended_only or e["pid"] not in sg.s["defended"])]


def _declare_battles(sg, side, must_attack, log):
    """Discharge 8.4: each of my ZOC-locked units attacks EVERY enemy adjacent
    to it, combined (11.2/11.33) — a lone unit may not split a stack (11.4).
    Co-attackers that are adjacent to every defender join to improve the odds
    (11.1/11.32). Most-constrained unit first so a shared defender is fought by
    a battle that includes all the units obliged to attack it (11.7/11.31)."""
    made = False
    pend = [p for p in must_attack
            if p in sg.s["units"] and p not in sg.s["attacked"]]
    # fewest available targets first
    pend.sort(key=lambda p: len(_adjacent_enemies(
        sg, side, (sg.unit(p)["col"], sg.unit(p)["row"]))))
    for p in pend:
        if p in sg.s["attacked"]:
            continue
        u = sg.unit(p)
        uh = (u["col"], u["row"])
        defs = _adjacent_enemies(sg, side, uh)
        if not defs:
            continue                   # its targets were already attacked
        dhexes = [(sg.unit(dp)["col"], sg.unit(dp)["row"]) for dp in defs]
        allies = [f["pid"] for f in sg._combat_units(side)
                  if f["pid"] not in sg.s["attacked"] and f["pid"] != p
                  and all(sg._engageable((f["col"], f["row"]), dh)
                          for dh in dhexes)]
        attackers = [p] + allies
        v = sg.propose(sg.s["mover"],
                       {"type": "battle", "attackers": attackers,
                        "defenders": defs, "supply": None})
        supply = None
        if not v["legal"]:
            supply = _find_supply(sg, sg.s["mover"], attackers, defs)
            if supply is None:
                continue               # no legal attack — forced_elim handles it
        names = "/".join(sorted({sg.game.grid.display_name(*dh)
                                 for dh in dhexes}))
        if _submit(sg, sg.s["mover"],
                   {"type": "battle", "attackers": attackers,
                    "defenders": defs, "supply": supply}, log,
                   f"attacks {names}"
                   + (" (sustained by supply)" if supply else "")):
            made = True
    return made


def _forced_elims(sg, side, must_attack, log):
    """7.4: a unit forced to attack that can make no legal attack is removed
    before any battle is resolved."""
    if sg.s["fought"]:
        return False
    made = False
    for pid in must_attack:
        if pid not in sg.s["units"]:
            continue
        v = sg.propose(side, {"type": "forced_elim", "unit": pid})
        if v["legal"]:
            _submit(sg, side, {"type": "forced_elim", "unit": pid}, log,
                    f"{sg.unit(pid)['slot']} cannot attack at legal odds — "
                    f"eliminated [7.4]")
            made = True
    return made


def _do_combat(sg, side, log, dist):
    # 7.4 forced eliminations run first, while no battle has been fought
    ma, mb = sg._obligations(side)
    _forced_elims(sg, side, ma, log)
    for _ in range(500):
        if sg.s["over"]:
            return
        _place_rommel_if_pending(sg, log)
        panel = sg.combat_panel()
        pend = panel["pending"]
        if pend and pend["kind"] == "retreat":
            if not _resolve_retreat(sg, panel, log):
                return
            continue
        if pend and pend["kind"] == "exchange":
            if not _resolve_exchange(sg, panel, log):
                return
            continue
        if pend and pend["kind"] == "advance":
            _do_advances(sg, side, log, dist)
        ma, mb = sg._obligations(side)
        if ma or mb:
            if _declare_battles(sg, side, ma, log):
                continue
            if _forced_elims(sg, side, ma, log):
                continue
            # nothing legal discharges the obligation — surface it via the gate
            _submit(sg, side, {"type": "end_phase"}, log,
                    "ends the combat phase")
            return
        _submit(sg, side, {"type": "end_phase"}, log, "ends the player turn")
        return


# --------------------------------------------------------------------------- turn
def take_turn(sg):
    """Play the current mover's whole player turn through the gate.  Returns a
    list of log entries (proposal + verdict + result each)."""
    side = sg.s["mover"]
    log = []
    if sg.s["over"] or sg.s["phase"] != "movement":
        return log
    dist = _Dist(sg.game)
    _do_arrivals(sg, side, log)
    _do_supply_movement(sg, side, log, dist)
    _do_movement(sg, side, log, dist)
    _do_supply_movement(sg, side, log, dist)   # close up behind the new front
    _place_rommel_if_pending(sg, log)
    if not sg.combat:
        _submit(sg, side, {"type": "end_phase"}, log, "ends the player turn")
        return log
    # close movement, then fight
    if _submit(sg, side, {"type": "end_movement"}, log, "ends movement"):
        _do_combat(sg, side, log, dist)
    else:
        # end_movement refused (e.g. an AV needs supply) — end the turn cleanly
        _submit(sg, side, {"type": "end_phase"}, log, "ends the player turn")
    return log


def play_game(sg, max_turns=None, on_turn=None):
    """Drive a full AI-vs-AI game.  Returns (turns_played, log)."""
    full = []
    guard = 0
    limit = (max_turns or sg.turns) * 2 + 4
    while not sg.s["over"] and guard < limit:
        before = (sg.s["turn"], sg.s["mover"])
        log = take_turn(sg)
        full.extend(log)
        if on_turn:
            on_turn(sg, log)
        after = (sg.s["turn"], sg.s["mover"])
        if before == after and not sg.s["over"]:
            # a full player turn ran without ending the phase (an obligation
            # the policy could not legally discharge) — surface it, don't spin
            full.append({"desc": "AI could not end its turn — stopping",
                         "error": True})
            break
        guard += 1
    return sg.s["turn"], full
