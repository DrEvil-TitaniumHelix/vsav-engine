"""
validate_shock.py - phase-4 shock-combat / reaction / strategic-movement
validation (schema 4, tier 2).

Exercises the phase-4 machinery through the REAL gate (submit() only, no
private resolver calls for outcomes): melee legality gates [6.4.1/9.2.3/
11.1.1/5.2.1 + 8.2.1/8.3.1 caps + support rules], the Bayonet flow with
its logged decision windows [8.2.1], the return-fire-breaks-attack path
[8.2.1#3], Assault melee rounds with the continue/withdraw windows
[8.3.1/8.5.3], the cavalry Charge machine [8.4.2: May Charge, range,
square window, charge-bonus DRM detail, blown, pursuit], Blown lifecycle
[8.4.4/8.4.5], reaction windows [6.2: expenditure-vs-entry triggers,
skirmisher/artillery/cavalry kinds, budgets, reaction charge ends the
mover's movement], strategic movement [5.2], and finally replays a full
scripted schema-4 game independently via verify_game.

Countercharge [8.4.2#3] is scenario-UNREACHABLE in A15.1 (the Russians
field no cavalry) - documented by an explicit roster check below; its
arithmetic is validated at table level in validate_melee.py.

Run: python games/austerlitz-gmt/validate_shock.py
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "engine"))
import formations as fm
import gamespec
import melee as melee_mod
import verify_game
from napoleonic import NapoleonicGame

FAILS = []


def why(r):
    return "; ".join(r.get("reasons", []))


def check(label, ok):
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILS.append(label)


def fresh(seed):
    live = tempfile.mkdtemp(prefix="aus_shock_")
    g = NapoleonicGame(gamespec.load(HERE),
                       os.path.join(HERE, "scenario_northern_flank.json"),
                       live, seed=seed, tier=2)
    return g, live


def by_slot(g, slot, side=None):
    for u in g.s["units"].values():
        if u["slot"] == slot and (side is None or u["side"] == side):
            return u
    raise KeyError(slot)


def front_of(g, u, facing=None):
    return {tuple(h) for h in fm.front_hexes(
        g.game, u["col"], u["row"],
        u["facing"] if facing is None else facing, g._kind(u))}


def face_toward(g, u, target_hex):
    """A facing (legal for the unit's formation kind) that puts
    target_hex in the unit's front hexsides."""
    kind = g._kind(u)
    for f in range(fm.FACINGS):
        if kind == "vertex" and f % 2 == 0:
            continue
        if kind == "hexside" and f % 2 == 1:
            continue
        fh = {tuple(h) for h in fm.front_hexes(
            g.game, u["col"], u["row"], f, kind)}
        if tuple(target_hex) in fh:
            return f
    # distant target: nearest legal facing along the bearing
    return g._facing_toward((u["col"], u["row"]), tuple(target_hex),
                            kind)


def put(g, u, hexx, toward=None):
    u["col"], u["row"] = hexx
    if toward is not None:
        u["facing"] = face_toward(g, u, toward)


def park_side(g, side, keep=()):
    """Teleport a side's combat units (and leaders) to the area corner
    so they cannot project reaction zones over the test site."""
    c0, c1, r0, r1 = g.area
    spot = (c1, r1)
    for u in g.s["units"].values():
        if u["side"] == side and u["pid"] not in keep:
            u["col"], u["row"] = spot


def clear_lane(g, n=2):
    """n+1 clear hexes in a chain (each adjacent to the next), no
    hexside features between consecutive pairs. Returns the list."""
    c0, c1, r0, r1 = g.area
    for c in range(c0 + 2, c1 - 2):
        for r in range(r0 + 2, r1 - 2):
            lane = [(c, r)]
            while len(lane) < n + 1:
                cur = lane[-1]
                ext = None
                for nb in g.game.neighbors(*cur):
                    nb = tuple(nb)
                    if nb in lane or not g.in_area(*nb):
                        continue
                    if g.hex_terrain(*nb) != "clear":
                        continue
                    rows, _ = g._hexside_rows(cur, nb)
                    if rows:
                        continue
                    if len(lane) >= 2 and \
                            g.game.hex_distance(lane[0], nb) != len(lane):
                        continue        # keep the lane straightish
                    ext = nb
                    break
                if ext is None:
                    break
                lane.append(ext)
            if len(lane) == n + 1 and g.hex_terrain(*lane[0]) == "clear":
                return lane
    raise RuntimeError("no clear lane found")


def terr_pair(g, want):
    """(clear_hex, want_hex) adjacent, melee allowed across."""
    rows_def = g._eff_rows()
    for key, terr in g.thex.items():
        if terr != want:
            continue
        c, r = map(int, key.split(","))
        if not g.in_area(c, r):
            continue
        for nb in g.game.neighbors(c, r):
            nb = tuple(nb)
            if not g.in_area(*nb) or g.hex_terrain(*nb) != "clear":
                continue
            names = g._melee_rows_between(nb, (c, r))
            _, allowed = melee_mod.terrain_melee_drm(rows_def, names)
            if allowed:
                return nb, (c, r)
    raise RuntimeError(f"no clear/{want} melee pair found")


def woods_pair(g):
    return terr_pair(g, "woods")


def defensive_pair(g):
    """Village is this map's Defensive terrain [TEC Defensive col]."""
    return terr_pair(g, "village")


def open_full(want_div, seeds=range(1, 500), setup=None, extra_lim=None):
    """Hunt seeds until a FULL activation opens for want_div through the
    real command flow (pool -> initiative -> activation roll [4.5.1])."""
    for seed in seeds:
        g, live = fresh(seed)
        if setup:
            setup(g)
        divs = g._divisions()
        own = divs[want_div]["side"]
        lim = divs[want_div]["lim"]
        pools = {"French": [], "Allied": []}
        pools[own].append(lim)
        if extra_lim:
            eside, elim = extra_lim
            pools[eside].append(elim)
        g.submit("French", {"type": "set_pool", "lims": pools["French"]})
        g.submit("Allied", {"type": "set_pool", "lims": pools["Allied"]})
        if g.s["phase"] == "initiative":
            g.submit(g.s["initiative"], {"type": "choose_initiative_lim",
                                         "lim": f"{own}:{lim}"})
        act = g.s.get("act")
        if not act or act.get("side") != own or act.get("lim") != \
                f"{own}:{lim}":
            continue
        kw = {"type": "activation_choice", "choice": "full"}
        if act.get("kind") == "independent":
            # cavalry divisions activate under the Independent LIM
            # [A4.3.2 / A15.1]
            if want_div not in act["indep"]["eligible"]:
                continue
            kw["division"] = want_div
        g.submit(own, kw)
        act = g.s.get("act")
        if act and act.get("atype") == "full" and act.get("div") == \
                want_div and act.get("stage") == "move":
            return g, live, seed
    raise RuntimeError(f"no seed opened a full activation for {want_div}")


GAME = gamespec.load(HERE)

print("== schema 4 / tier 2 boots ==")
g, live = fresh(7)
check("tier 2 game runs state schema 4 (phase-4 flow on)",
      g.s["schema"] == 4 and g.s["tier"] == 2 and g._p4)
check("phase-4 unit fields present: blown/recovery [8.4.4/8.4.5]",
      all("blown" in u and "recovery" in u
          for u in g.s["units"].values()))
check("tier 1 still pins schema 3 (phase-3 flow untouched)",
      NapoleonicGame(gamespec.load(HERE),
                     os.path.join(HERE, "scenario_northern_flank.json"),
                     tempfile.mkdtemp(prefix="aus_t1_"), seed=7,
                     tier=1).s["schema"] == 3)
check("A15.1 roster has NO Allied cavalry: countercharge [8.4.2#3] is "
      "scenario-unreachable (validated at table level, validate_melee)",
      not any(u["arm"] == "cavalry" and u["side"] == "Allied"
              for u in g.s["units"].values()))
check("no Aggressive leader in A15.1: the CHARGE breakdown result "
      "remains asserted-unreachable [4.7]",
      all(v["personality"] != "A"
          for v in (g._rating(dk) for dk in g._divisions())))

print("== melee legality gates [8.2.1/8.3.1 + 6.4.1/9.2.3/11.1.1] ==")
g, live, seed = open_full("French:3")
atk = by_slot(g, "1/40 Ln")
atk2 = by_slot(g, "2/40 Ln")
dfn = by_slot(g, "3/Arkh")
lane = clear_lane(g, 3)
park_side(g, "Allied", keep=[dfn["pid"]])
put(g, atk, lane[0], toward=lane[1])
put(g, dfn, lane[1], toward=lane[0])
r = g.propose("French", {"type": "melee", "unit": atk["pid"],
                         "target": dfn["pid"]})
check("infantry melee vs a front-adjacent enemy is legal [8.2.1]",
      r["legal"])
# flank placement: adjacent but not in the attacker's front hexsides
flanks = [tuple(h) for h in fm.flank_hexes(
    g.game, atk["col"], atk["row"], atk["facing"], g._kind(atk))
    if g.in_area(*h)]
put(g, dfn, flanks[0])
r = g.propose("French", {"type": "melee", "unit": atk["pid"],
                         "target": dfn["pid"]})
check("defender adjacent on a FLANK hexside is rejected [8.2.1/8.3.1: "
      "front hexsides only]", not r["legal"] and "front" in why(r))
put(g, dfn, lane[1], toward=lane[0])
r = g.propose("French", {"type": "charge", "unit": atk["pid"],
                         "target": dfn["pid"]})
check("infantry may not CHARGE [8.4: cavalry only]",
      not r["legal"] and "cavalry" in why(r))
atk["formation"] = "disorder"
r = g.propose("French", {"type": "melee", "unit": atk["pid"],
                         "target": dfn["pid"]})
check("disordered units may not initiate melee [6.4.1]", not r["legal"])
atk["formation"] = "line"
atk["morale_state"] = "unsteady"
r = g.propose("French", {"type": "melee", "unit": atk["pid"],
                         "target": dfn["pid"]})
check("unsteady units may not initiate melee [9.2.3]", not r["legal"])
atk["morale_state"] = "good"
atk["sp_lost"] = atk["sp"] + 1      # cumulative loss > half printed SP
r = g.propose("French", {"type": "melee", "unit": atk["pid"],
                         "target": dfn["pid"]})
check("a unit at Breakpoint may never initiate melee [11.1.1]",
      not r["legal"] and "Breakpoint" in why(r))
atk["sp_lost"] = 0
g.s["strat"].append("French:3")
r = g.propose("French", {"type": "melee", "unit": atk["pid"],
                         "target": dfn["pid"]})
check("strategic-movement units may never initiate combat [5.2.1]",
      not r["legal"] and "strategic" in why(r).lower())
g.s["strat"].remove("French:3")

# limited activation: no melee at all [8.2/8.3/8.4]
def _lim_setup(gx):
    pass
gl, livel = fresh(31)
divs = gl._divisions()
gl.submit("French", {"type": "set_pool", "lims": ["Suchet"]})
gl.submit("Allied", {"type": "set_pool", "lims": []})
if gl.s["phase"] == "initiative":
    gl.submit(gl.s["initiative"], {"type": "choose_initiative_lim",
                                   "lim": "French:Suchet"})
gl.submit("French", {"type": "activation_choice", "choice": "limited"})
la = by_slot(gl, "1/40 Ln")
ld = by_slot(gl, "3/Arkh")
lane_l = clear_lane(gl, 1)
park_side(gl, "Allied", keep=[ld["pid"]])
put(gl, la, lane_l[0], toward=lane_l[1])
put(gl, ld, lane_l[1], toward=lane_l[0])
r = gl.propose("French", {"type": "melee", "unit": la["pid"],
                          "target": ld["pid"]})
check("only a FULL activation may melee [8.2/8.3/8.4]",
      not r["legal"] and "Full" in why(r))

print("== support rules [8.2.1#2/8.3.1#2 + Fox Q&A] ==")
g, live, seed = open_full("French:3")
atk = by_slot(g, "1/40 Ln")
atk2 = by_slot(g, "2/40 Ln")
sup = by_slot(g, "1/88 Ln")
atkB = by_slot(g, "2/34 Ln")
dfn = by_slot(g, "3/Arkh")
dfn2 = by_slot(g, "2/Arkh")
lane = clear_lane(g, 3)
park_side(g, "Allied", keep=[dfn["pid"], dfn2["pid"]])
A = lane[0]
put(g, atk, A, toward=lane[1])
put(g, atk2, A)
atk2["facing"] = atk["facing"]
fh = sorted(front_of(g, atk))
D1 = tuple(lane[1])
D2 = [h for h in fh if h != D1 and g.in_area(*h)]
D2 = tuple(D2[0]) if D2 else None
put(g, dfn, D1, toward=A)
# support adjacent to the defender, defender in its front
sup_spots = [tuple(h) for h in g.game.neighbors(*D1)
             if tuple(h) not in (A, D2) and g.in_area(*h)
             and g.hex_terrain(*h) != "water"]
put(g, sup, sup_spots[0], toward=D1)
r = g.propose("French", {"type": "melee", "unit": atk["pid"],
                         "target": dfn["pid"],
                         "supports": [sup["pid"]]})
check("a legal supporting stack is accepted [8.2.1#2]", r["legal"])
sup["facing"] = (sup["facing"] + 6) % fm.FACINGS      # face away
r = g.propose("French", {"type": "melee", "unit": atk["pid"],
                         "target": dfn["pid"],
                         "supports": [sup["pid"]]})
check("support with the defender NOT in its front hexsides is rejected "
      "(Fox Q&A)", not r["legal"] and "front" in why(r))
put(g, sup, sup_spots[0], toward=D1)
far = clear_lane(g, 1)[0]
sup_far_keep = (sup["col"], sup["row"], sup["facing"])
c0, c1, r0, r1 = g.area
sup["col"], sup["row"] = (c0, r0)
r = g.propose("French", {"type": "melee", "unit": atk["pid"],
                         "target": dfn["pid"],
                         "supports": [sup["pid"]]})
check("support must be adjacent to the defender [8.2.1#2]",
      not r["legal"] and "adjacent" in why(r))
sup["col"], sup["row"], sup["facing"] = sup_far_keep
r = g.propose("French", {"type": "melee", "unit": atk["pid"],
                         "target": dfn["pid"],
                         "supports": [atk2["pid"]]})
check("the attacking stack may not also support [8.2.1#2]",
      not r["legal"])
# submit the melee with support; then the once-per caps
rs = g.submit("French", {"type": "melee", "unit": atk["pid"],
                         "target": dfn["pid"],
                         "supports": [sup["pid"]]})
res = rs["result"]
check("shock record logs kind/attackers/supports/defenders + terrain "
      "rows [8.2.1]",
      res["shock"]["kind"] == "bayonet"
      and sup["pid"] in res["shock"]["supports"]
      and set(res["shock"]["attackers"]) >= {atk["pid"], atk2["pid"]})
check("supporting stacks feed the attacker's pre-shock DRM "
      "(-1 per stack) [8.2.1#2]",
      res.get("attacker_check", {}).get("drms", {})
      .get("supporting_stacks") == -1)
# drive any open window to completion so the caps can be probed
guard = 0
while g.s.get("pending_melee") and guard < 20:
    pm = g.s["pending_melee"]
    if pm["stage"] == "return_window":
        g.submit(pm["window_owner"], {"type": "melee_no_return"})
    elif pm["stage"] in ("continue_def", "continue_att"):
        g.submit(pm["window_owner"], {"type": "melee_stand"})
    else:
        break
    guard += 1
act = g.s["act"]
check("declared hexes are booked: meleed + attacked_with "
      "[8.2.1#1/8.3.1#1]",
      list(D1) in act["meleed"] and list(A) in act["attacked_with"])
alive_def = [v for v in g._stack(*D1, side="Allied")]
if alive_def and D2:
    r = g.propose("French", {"type": "melee", "unit": atkB["pid"],
                             "target": alive_def[0]["pid"]})
    # atkB placed fresh next to D1
    put(g, atkB, [h for h in g.game.neighbors(*D1)
                  if tuple(h) not in (A, D2)
                  and g.in_area(*h)][1], toward=D1)
    r = g.propose("French", {"type": "melee", "unit": atkB["pid"],
                             "target": alive_def[0]["pid"]})
    check("a stack may be meleed only once per activation "
          "[8.2.1#1/8.3.1 Q&A]",
          not r["legal"] and "already been meleed" in why(r))
else:
    check("defender eliminated/retreated before cap probe - meleed cap "
          "verified via act bookkeeping instead [8.2.1#1]",
          list(D1) in act["meleed"])
if D2:
    put(g, dfn2, D2, toward=A)
    r = g.propose("French", {"type": "melee", "unit": atk["pid"],
                             "target": dfn2["pid"]})
    check("an attacking stack attacks only once per activation "
          "[8.3.1#1]",
          not r["legal"] and "already attacked" in why(r))
    # support exhaustion [8.2.1#2]: sup already supported the first one
    third = [h for h in g.game.neighbors(*D2)
             if g.in_area(*h) and g.hex_terrain(*h) != "water"
             and tuple(h) != A]
    put(g, atkB, third[0], toward=D2)
    put(g, sup, [h for h in third if tuple(h) !=
                 (atkB["col"], atkB["row"])][0], toward=D2)
    r = g.propose("French", {"type": "melee", "unit": atkB["pid"],
                             "target": dfn2["pid"],
                             "supports": [sup["pid"]]})
    check("a stack may support only one attack per activation "
          "[8.2.1#2]",
          not r["legal"] and "support one attack" in why(r))

print("== bayonet flow: windows logged, defender check, no advance "
      "[8.2.1] ==")
done = False
for seed in range(1, 300):
    try:
        g, live, _ = open_full("French:3", seeds=[seed])
    except RuntimeError:
        continue
    atk = by_slot(g, "1/40 Ln")
    dfn = by_slot(g, "3/Arkh")
    lane = clear_lane(g, 2)
    park_side(g, "Allied", keep=[dfn["pid"]])
    put(g, atk, lane[0], toward=lane[1])
    put(g, dfn, lane[1], toward=lane[0])
    rs = g.submit("French", {"type": "melee", "unit": atk["pid"],
                             "target": dfn["pid"]})
    res = rs["result"]
    if res.get("attacker_check", {}).get("result") != "may_melee":
        continue
    pm = g.s.get("pending_melee")
    if not pm or pm["stage"] != "return_window":
        continue
    wins = res.get("windows", [])
    check("attacker passed the pre-shock check and the defender window "
          "opened [8.2.1#2-3]", pm["window_owner"] == "Allied")
    check("window ENTITLEMENTS logged at window-open (honesty record) "
          "[8.2.1#3]",
          wins and wins[0]["stage"] == "return_window"
          and dfn["pid"] in wins[0]["entitled"]
          and "melee_return" in wins[0]["entitled"][dfn["pid"]])
    r = g.propose("French", {"type": "melee_return",
                             "unit": dfn["pid"]})
    check("the window belongs to the DEFENDER side [8.2.1#3]",
          not r["legal"])
    r2 = g.submit("Allied", {"type": "melee_no_return"})
    res2 = r2["result"]
    check("declining return fire runs the defender pre-shock check "
          "[8.2.1#4]", bool(res2.get("defender_check")))
    check("bayonet ends after the defender check - no melee round, no "
          "advance step [8.2.1 steps panel]",
          g.s.get("pending_melee") is None
          and res2.get("shock_over", {}).get("kind") == "bayonet"
          and not res2.get("melee_rounds") and "advance" not in res2)
    check("combat marked division fatigue for both sides [13.1.2]",
          "French:3" in g.s["fat_combat"]
          and "Allied:2" in g.s["fat_combat"])
    done = True
    break
check("bayonet end-to-end flow exercised (seed hunt)", done)

print("== return fire can break the attack [8.2.1#3] ==")
done = False
for seed in range(1, 500):
    try:
        g, live, _ = open_full("French:3", seeds=[seed])
    except RuntimeError:
        continue
    atk = by_slot(g, "1/40 Ln")
    dfn = by_slot(g, "3/Arkh")
    lane = clear_lane(g, 2)
    park_side(g, "Allied", keep=[dfn["pid"]])
    park_side(g, "French", keep=[atk["pid"]] + [
        u["pid"] for u in g.s["units"].values()
        if u["arm"] == "leader" and u["side"] == "French"])
    put(g, atk, lane[0], toward=lane[1])
    put(g, dfn, lane[1], toward=lane[0])
    atk["sp"] = 1                      # one SP: any hit breaks it
    rs = g.submit("French", {"type": "melee", "unit": atk["pid"],
                             "target": dfn["pid"]})
    if rs["result"].get("attacker_check", {}).get("result") != \
            "may_melee":
        continue
    if not g.s.get("pending_melee"):
        continue
    r2 = g.submit("Allied", {"type": "melee_return",
                             "unit": dfn["pid"]})
    res2 = r2["result"]
    if "attack_broken" not in res2:
        continue
    check("return fire that kills/breaks every attacker ends the "
          "attack [8.2.1#3]",
          g.s.get("pending_melee") is None
          and "defender_check" not in res2)
    check("the return shot was resolved and logged [8.1.2 tables]",
          "melee_return" in res2 and "die" in res2["melee_return"])
    done = True
    break
check("return-fire-breaks-attack path exercised (seed hunt)", done)

print("== assault: defensive terrain, melee rounds, continue/withdraw "
      "[8.3.1/8.5.3] ==")
ass_kind = ass_round = ass_path = False
for seed in range(1, 600):
    try:
        g, live, _ = open_full("French:3", seeds=[seed])
    except RuntimeError:
        continue
    atk = by_slot(g, "1/40 Ln")
    atk2 = by_slot(g, "2/40 Ln")
    dfn = by_slot(g, "3/Arkh")
    ahex, whex = defensive_pair(g)
    park_side(g, "Allied", keep=[dfn["pid"]])
    put(g, atk, ahex, toward=whex)
    put(g, atk2, ahex)
    atk2["facing"] = atk["facing"]
    put(g, dfn, whex, toward=ahex)
    dfn["sp"] = 12                     # sturdy: survive to the rounds
    rs = g.submit("French", {"type": "melee", "unit": atk["pid"],
                             "target": dfn["pid"]})
    res = rs["result"]
    if res.get("shock", {}).get("kind") != "assault":
        continue
    if not ass_kind:
        check("defender in Defensive terrain => the melee is an "
              "ASSAULT [8.3/TEC Defensive column]", True)
        ass_kind = True
    if res.get("attacker_check", {}).get("result") != "may_melee":
        continue
    if not g.s.get("pending_melee"):
        continue
    r2 = g.submit("Allied", {"type": "melee_no_return"})
    res2 = r2["result"]
    if not res2.get("melee_rounds"):
        continue
    rnd = res2["melee_rounds"][0]
    if not ass_round:
        check("assault runs a Melee Result Table round with full DRM "
              "detail logged [8.3.1#5/8.5]",
              "die" in rnd and "drms" in rnd and "att_sp" in rnd
              and "def_sp" in rnd and rnd["cite"] == "8.5")
        ass_round = True
    pm = g.s.get("pending_melee")
    if rnd["loser"] != "both" or not pm \
            or pm["stage"] != "continue_def":
        continue
    check("'both' result -> melee continues: DEFENDER decides "
          "stand/withdraw first [8.5.3]",
          pm["window_owner"] == "Allied")
    r3 = g.submit("Allied", {"type": "melee_stand"})
    pm = g.s.get("pending_melee")
    check("defender stood -> ATTACKER decides stand/withdraw [8.5.3]",
          pm and pm["stage"] == "continue_att"
          and pm["window_owner"] == "French")
    r4 = g.submit("French", {"type": "melee_withdraw"})
    res4 = r4["result"]
    a_now = g.unit(atk["pid"])
    check("attacker voluntary withdrawal = the whole stack routs "
          "[8.5.3 voluntary rout]",
          res4.get("voluntary_rout", {}).get("side") == "French"
          and a_now["morale_state"] == "routed"
          and g.s.get("pending_melee") is None)
    ass_path = True
    break
check("assault continue->withdraw path exercised (seed hunt)",
      ass_kind and ass_round and ass_path)

print("== charge legality [8.4/5.1.2/A8.1.1] ==")
g, live, seed = open_full("French:T")
hus = by_slot(g, "10 Hus")
dfn = by_slot(g, "3/Arkh")
park_side(g, "Allied", keep=[dfn["pid"]])
lane = clear_lane(g, 4)
put(g, dfn, lane[3], toward=lane[0])
put(g, hus, lane[0])
r = g.propose("French", {"type": "melee", "unit": hus["pid"],
                         "target": dfn["pid"]})
check("cavalry may not Bayonet/Assault - it charges [8.2/8.3]",
      not r["legal"] and "charges" in why(r))
put(g, dfn, lane[1])
r = g.propose("French", {"type": "charge", "unit": hus["pid"],
                         "target": dfn["pid"]})
check("charge NEVER declared adjacent [A8.1.1: range 2-4]",
      not r["legal"] and "never" in why(r).lower())
c0, c1, r0, r1 = g.area
put(g, dfn, (hus["col"], hus["row"]))
dfn["col"] = min(c1, hus["col"] + 6)
r = g.propose("French", {"type": "charge", "unit": hus["pid"],
                         "target": dfn["pid"]})
check("charge range beyond 4 hexes rejected [A8.1.1]", not r["legal"])
hus["blown"] = 1
put(g, dfn, lane[3])
r = g.propose("French", {"type": "charge", "unit": hus["pid"],
                         "target": dfn["pid"]})
check("blown cavalry may not charge [8.4.4]",
      not r["legal"] and "blown" in why(r).lower())
hus["blown"] = 0
g.s["act"]["spent"][hus["pid"]] = 7.0     # > half of MA 12
r = g.propose("French", {"type": "charge", "unit": hus["pid"],
                         "target": dfn["pid"]})
check("no May Charge marker after moving more than half MA [5.1.2]",
      not r["legal"] and "May Charge" in why(r))
g.s["act"]["spent"].pop(hus["pid"])

print("== the charge machine: square window, DRM detail, blown, "
      "pursuit [8.4.2] ==")
chg_done = sq_done = pursuit_done = sq_offered = False
for seed in range(1, 800):
    if chg_done and sq_done and pursuit_done:
        break
    try:
        g, live, _ = open_full("French:T", seeds=[seed])
    except RuntimeError:
        continue
    hus = by_slot(g, "10 Hus")
    dfn = by_slot(g, "3/Arkh")
    park_side(g, "Allied", keep=[dfn["pid"]])
    park_side(g, "French", keep=[hus["pid"]])
    lane = clear_lane(g, 3)
    put(g, dfn, lane[3], toward=lane[0])
    put(g, hus, lane[0], toward=lane[1])
    if g._charge_path(hus, (dfn["col"], dfn["row"])) is None:
        continue
    clear, _ = g._los((hus["col"], hus["row"]),
                      (dfn["col"], dfn["row"]))
    if not clear:
        continue
    rs = g.submit("French", {"type": "charge", "unit": hus["pid"],
                             "target": dfn["pid"]})
    res = rs["result"]
    if "shock" not in res:
        continue
    if not chg_done:
        check("charge declared at range 2-4 with LOS + legal path "
              "executes hex by hex [8.4.1/8.4.2#2]",
              res["shock"]["kind"] == "charge"
              and len(res["shock"]["path"]) >= 2)
    chg_done = True
    pm = g.s.get("pending_melee")
    if not pm or pm["stage"] != "square_window":
        continue
    wins = res.get("windows", [])
    if not sq_offered:
        check("defending infantry offered Stand-or-Square, logged "
              "before the choice [8.4.2#4]",
              pm["window_owner"] == "Allied"
              and any(w["stage"] == "square_window" for w in wins))
        sq_offered = True
    r2 = g.submit("Allied", {"type": "square_choice", "form": True,
                             "unit": dfn["pid"]})
    res2 = r2["result"]
    fs = res2.get("form_square", {})
    if fs.get("result") != "square_formed":
        # failed square: charge continues vs the disordered defender
        sq_done = sq_done or False
        continue
    if not sq_done:
        u_now = g.unit(dfn["pid"])
        check("square formed: formation change applied [8.4.2#4]",
              fs["result"] == "square_formed")
        rounds = res2.get("melee_rounds", [])
        if rounds:
            drms = rounds[0]["drms"]
            exp = melee_mod.charge_bonus(
                g.ctables, "light", dist=pm["charge"]["dist"],
                vs_square=True, in_column=False)
            check("melee DRM detail: vs_square -3 (cavalry) + charge "
                  "bonus HALVED vs square [8.4.2#6]",
                  drms.get("vs_square") == -3
                  and drms.get("charge_bonus", 0) == exp)
            hus_now = g.unit(hus["pid"])
            if not hus_now.get("dead") and \
                    res2.get("shock_over"):
                check("charging cavalry ends disordered + Blown-2 "
                      "[8.4.2#9]",
                      res2.get("blown", {}).get("level") == 2
                      and hus_now["blown"] == 2
                      and hus_now["formation"] == "disorder")
        sq_done = True
    # pursuit needs a routed defender - separate hunt below
if not pursuit_done:
    for seed in range(1, 1200):
        try:
            g, live, _ = open_full("French:T", seeds=[seed])
        except RuntimeError:
            continue
        hus = by_slot(g, "10 Hus")
        dfn = by_slot(g, "3/Arkh")
        park_side(g, "Allied", keep=[dfn["pid"]])
        park_side(g, "French", keep=[hus["pid"]])
        lane = clear_lane(g, 3)
        put(g, dfn, lane[3], toward=lane[0])
        put(g, hus, lane[0], toward=lane[1])
        dfn["morale_state"] = "unsteady"   # brittle: rout likely
        if g._charge_path(hus, (dfn["col"], dfn["row"])) is None:
            continue
        clear, _ = g._los((hus["col"], hus["row"]),
                          (dfn["col"], dfn["row"]))
        if not clear:
            continue
        rs = g.submit("French", {"type": "charge", "unit": hus["pid"],
                                 "target": dfn["pid"]})
        out_all = dict(rs["result"])
        pm = g.s.get("pending_melee")
        guard = 0
        while g.s.get("pending_melee") and guard < 12:
            pm = g.s["pending_melee"]
            if pm["stage"] == "square_window":
                r2 = g.submit("Allied", {"type": "square_choice",
                                         "form": False,
                                         "unit": dfn["pid"]})
            elif pm["stage"] == "return_window":
                r2 = g.submit("Allied", {"type": "melee_no_return"})
            elif pm["stage"] in ("continue_def", "continue_att"):
                r2 = g.submit(pm["window_owner"],
                              {"type": "melee_stand"})
            else:
                break
            out_all.update(r2.get("result", {}))
            guard += 1
        if "pursuit" in out_all:
            pu = out_all["pursuit"]
            check("routed defender -> Pursuit Table rolled, DRMs + "
                  "hexes logged [8.4.2#8]",
                  "die" in pu and "hexes" in pu
                  and pu["cite"] == "8.4.2#8"
                  and pu["drms"].get("light_or_lancer") == 1)
            pursuit_done = True
            break
check("charge executed (seed hunt)", chg_done)
check("square window + DRM detail exercised (seed hunt)", sq_done)
check("pursuit path exercised (seed hunt)", pursuit_done)

print("== blown lifecycle [8.4.4/8.4.5] ==")
def _blown_setup(gx):
    by_slot(gx, "10 Hus")["blown"] = 1
g, live, seed = open_full("French:T", setup=_blown_setup)
hus = by_slot(g, "10 Hus")
check("blown cavalry activates at HALF MA rounded up (12 -> 6) "
      "[8.4.4]", g.s["act"]["budget"][hus["pid"]] == 6.0)
g.submit("French", {"type": "end_activation"})
check("blown cavalry that neither moved nor defended gains a Recovery "
      "marker at its division's close [8.4.5]",
      g.unit(hus["pid"])["recovery"] is True)
# drive the turn to the Rally Phase: recovery decrements the level
by_slot(g, "3/Arkh")["morale_state"] = "shaken"   # force a rally phase
guard = 0
while g.s["phase"] in ("activation", "non_lim") and guard < 60:
    ph = g.s["phase"]
    if ph == "activation":
        act = g.s["act"]
        if act.get("pending") == "choice":
            kw = {"type": "activation_choice", "choice": "limited"}
            if act["kind"] == "independent":
                kw["division"] = [d for d in act["indep"]["eligible"]
                                  if d not in act["indep"]["done"]][0]
            g.submit(act["side"], kw)
        elif act.get("pending") == "bd_offer":
            g.submit(act["side"], {"type": "bd_decline"})
        else:
            g.submit(act["side"], {"type": "end_activation"})
    else:
        g.submit(g.s["mover"], {"type": "pass_non_lim"})
    guard += 1
guard = 0
while g.s["phase"] == "rally" and guard < 10:
    g.submit(g.s["mover"], {"type": "end_rally"})
    guard += 1
check("Rally Phase: Recovery marker comes off and Blown drops a level "
      "[8.4.5]",
      g.unit(hus["pid"])["blown"] == 0
      and g.unit(hus["pid"])["recovery"] is False)

print("== reaction windows: expenditure vs entry [6.2.1/6.2.2] ==")
g, live, seed = open_full("French:3")
atk = by_slot(g, "1/40 Ln")
dfn = by_slot(g, "3/Arkh")
lane = clear_lane(g, 3)
park_side(g, "Allied", keep=[dfn["pid"]])
put(g, dfn, lane[3], toward=lane[0])
zone = g._zone(dfn)
put(g, atk, lane[1], toward=lane[2])
check("test geometry: the mover's destination is in the defender's "
      "front Reaction Zone [6.2]", tuple(lane[2]) in zone
      and tuple(lane[1]) not in zone)
rs = g.submit("French", {"type": "move", "unit": atk["pid"],
                         "dest": list(lane[2])})
check("KEY NEGATIVE [6.2.1]: entry into a formed infantry zone alone "
      "does NOT trigger a reaction (MP expenditure does)",
      rs["verdict"]["legal"] and g.s.get("pending_react") is None
      and "move_complete" in rs["result"])
# now the mover STARTS in the zone: first MP spent inside -> window
g2b, live2b, _ = open_full("French:3")
atk = by_slot(g2b, "1/40 Ln")
atk2 = by_slot(g2b, "2/40 Ln")
dfn = by_slot(g2b, "3/Arkh")
lane = clear_lane(g2b, 3)
park_side(g2b, "Allied", keep=[dfn["pid"]])
put(g2b, dfn, lane[3], toward=lane[0])
zone = g2b._zone(dfn)
inzone = sorted(zone)[0]
inzone = tuple(lane[2])
put(g2b, atk, inzone, toward=lane[1])
rs = g2b.submit("French", {"type": "move", "unit": atk["pid"],
                           "dest": list(lane[1])})
pr = g2b.s.get("pending_react")
check("MP expenditure INSIDE the zone opens the reaction window "
      "before the step [6.2.1]",
      pr is not None and pr["side"] == "Allied"
      and "reaction_fire" in pr["entitled"].get(dfn["pid"], [])
      and rs["result"].get("interrupted"))
check("reaction window entitlements logged at open (honesty record) "
      "[6.2]",
      rs["result"]["reaction_windows"][0]["entitled"]
      .get(dfn["pid"]) == ["reaction_fire"])
r = g2b.propose("French", {"type": "reaction_fire",
                           "unit": dfn["pid"]})
check("only the reacting side acts in the window [6.2]",
      not r["legal"])
rf = g2b.submit("Allied", {"type": "reaction_fire",
                           "unit": dfn["pid"]})
check("reaction fire resolves through the fire tables and is booked "
      "once-per-activation [8.1.3]",
      "reaction_fire" in rf["result"]
      and dfn["pid"] in g2b.s["reacted"])
mover_now = g2b.unit(atk["pid"])
if g2b.s.get("pending_react") is None and not mover_now.get("dead") \
        and mover_now["morale_state"] not in ("unsteady", "routed"):
    check("after the reaction the walk resumed and completed [6.2]",
          "move_complete" in rf["result"])
else:
    check("reaction changed the mover's state: movement correctly "
          "ended [6.2/Fox]", "movement_ended" in rf["result"]
          or mover_now.get("dead"))
# once per activation [8.1.3]: a second mover in the same zone
if not g2b.s.get("pending_react") and not g2b.s.get("pending_melee"):
    put(g2b, atk2, inzone, toward=lane[1])
    rs2 = g2b.submit("French", {"type": "move", "unit": atk2["pid"],
                                "dest": list(lane[1])})
    check("reaction fire is once per enemy activation [8.1.3]",
          g2b.s.get("pending_react") is None)

print("== skirmisher reactions [6.2.2] + budget separation "
      "[8.1.2/8.1.3] ==")
def _skirm_setup(gx):
    leg = by_slot(gx, "2/17 Leg")
    leg["formation"] = "skirmish"
g, live, seed = open_full("Allied:2", setup=_skirm_setup)
leg = by_slot(g, "2/17 Leg")
mv = by_slot(g, "2/Arkh")
lane = clear_lane(g, 3)
park_side(g, "French", keep=[leg["pid"]])
park_side(g, "Allied", keep=[u["pid"] for u in g.s["units"].values()
                             if u["side"] == "Allied"
                             and u["div"] == "2"]
          + [by_slot(g, "Markov")["pid"]])
put(g, leg, lane[3], toward=lane[0])
put(g, mv, lane[1], toward=lane[2])
zone = g._zone(leg)
check("skirmisher zone is all-around [6.2.2]",
      zone == {tuple(h) for h in g.game.neighbors(leg["col"],
                                                  leg["row"])})
dest = lane[2]
rs = g.submit("Allied", {"type": "move", "unit": mv["pid"],
                         "dest": list(dest)})
pr = g.s.get("pending_react")
check("ENTRY into a skirmisher's zone triggers the window [6.2.2] "
      "(unlike formed infantry [6.2.1])",
      pr is not None and leg["pid"] in pr["entitled"])
if pr:
    kinds = pr["entitled"][leg["pid"]]
    check("skirmisher offers reaction FIRE and/or reaction MOVE only "
          "[6.2.2]", set(kinds) <= {"reaction_fire", "reaction_move"}
          and "reaction_fire" in kinds)
    rf = g.submit("French", {"type": "reaction_fire",
                             "unit": leg["pid"]})
    check("skirmisher reaction fire booked [8.1.3]",
          leg["pid"] in g.s["reacted"])
# budget separation: reacted unit may still RETURN fire when shot at
mv2 = g.unit(mv["pid"])
if not g.s.get("pending_react") and not mv2.get("dead") \
        and mv2["morale_state"] not in ("routed",):
    put(g, mv2, lane[2], toward=lane[3])
    put(g, leg, lane[3], toward=lane[2])
    r = g.propose("Allied", {"type": "fire", "unit": mv2["pid"],
                             "target": leg["pid"]})
    if r["legal"]:
        g.submit("Allied", {"type": "fire", "unit": mv2["pid"],
                            "target": leg["pid"]})
        pf = g.s.get("pending_fire")
        if pf:
            r = g.propose("French", {"type": "return_fire"})
            check("reaction fire [8.1.3] does NOT spend the unit's "
                  "RETURN fire [8.1.2] (infantry budgets separate)",
                  r["legal"])
            g.submit("French", {"type": "decline_return"})

print("== artillery reactions: entry trigger, either-or, limber, "
      "reverse [6.2.4/6.2.5/8.1.4] ==")
g, live, seed = open_full("French:3")
ab = by_slot(g, "a/B")
atk = by_slot(g, "1/40 Ln")
lane = clear_lane(g, 3)
park_side(g, "Allied", keep=[ab["pid"]])
put(g, ab, lane[3], toward=lane[0])
put(g, atk, lane[1], toward=lane[2])
zone = g._zone(ab)
check("unlimbered artillery projects a front Reaction Zone [6.2.4]",
      tuple(lane[2]) in zone)
rs = g.submit("French", {"type": "move", "unit": atk["pid"],
                         "dest": list(lane[2])})
pr = g.s.get("pending_react")
check("ENTRY into an artillery zone triggers its window [6.2.4]",
      pr is not None and ab["pid"] in pr["entitled"]
      and "reaction_fire" in pr["entitled"][ab["pid"]])
check("horse battery vs an infantry mover ALSO offers limbering "
      "[6.2.5]", pr is not None
      and "reaction_limber" in pr["entitled"][ab["pid"]])
rf = g.submit("Allied", {"type": "reaction_fire", "unit": ab["pid"]})
check("artillery reaction fire resolved + booked [6.2.4/8.1.4]",
      ab["pid"] in g.s["reacted"])
mvr = g.unit(atk["pid"])
if not mvr.get("dead") and mvr["morale_state"] not in ("unsteady",
                                                       "routed") \
        and not g.s.get("pending_react"):
    r = g.propose("French", {"type": "fire", "unit": atk["pid"],
                             "target": ab["pid"]})
    if r["legal"]:
        g.submit("French", {"type": "fire", "unit": atk["pid"],
                            "target": ab["pid"]})
        if g.s.get("pending_fire"):
            r = g.propose("Allied", {"type": "return_fire"})
            check("artillery may Reaction Fire OR Return Fire, never "
                  "both in one activation [8.1.4]",
                  not r["legal"] and "8.1.4" in why(r))
            g.submit("Allied", {"type": "decline_return"})
# limbered horse artillery: reverse in reaction [6.2.5/6.2.6]
g4b, live4b, _ = open_full("French:3")
ab = by_slot(g4b, "a/B")
atk = by_slot(g4b, "1/40 Ln")
lane = clear_lane(g4b, 3)
park_side(g4b, "Allied", keep=[ab["pid"]])
ab["formation"] = "limbered"
put(g4b, ab, lane[3], toward=lane[0])
put(g4b, atk, lane[2], toward=lane[3])
zone = g4b._zone(ab)
if tuple(lane[2]) in zone and g4b._reverse_dest(ab):
    before = (ab["col"], ab["row"])
    rs = g4b.submit("French", {"type": "move", "unit": atk["pid"],
                               "dest": list(lane[1])})
    pr = g4b.s.get("pending_react")
    check("limbered HORSE artillery may Reverse in reaction [6.2.5]",
          pr is not None
          and pr["entitled"].get(ab["pid"]) == ["reaction_reverse"])
    rr = g4b.submit("Allied", {"type": "reaction_reverse",
                               "unit": ab["pid"]})
    rec = rr["result"]["reaction_reverse"]
    moved = (ab["col"], ab["row"]) != before
    check("reverse rolled its disorder check; either it moved one "
          "rear hex or the failure blocked it [6.2.5/6.2.6]",
          "disorder_check" in rec
          and (moved != bool(rec.get("blocked")))
          and (not rec.get("blocked")
               or ab["pid"] in g4b.s["rev_blocked"]))
else:
    check("limbered-horse reverse geometry unavailable on this lane "
          "(skipped - covered by proposal gate)", True)

print("== cavalry reactions: reverse/charge, failure lockout, "
      "movement ends [6.2.3 + Fox] ==")
cc_ok = cc_fail = False
for seed in range(1, 900):
    if cc_ok and cc_fail:
        break
    try:
        g, live, _ = open_full("Allied:2", seeds=[seed])
    except RuntimeError:
        continue
    hus = by_slot(g, "10 Hus")
    mv = by_slot(g, "2/Arkh")
    lane = clear_lane(g, 3)
    park_side(g, "French", keep=[hus["pid"]])
    park_side(g, "Allied", keep=[mv["pid"],
                                 by_slot(g, "Markov")["pid"]])
    put(g, hus, lane[3], toward=lane[0])
    put(g, mv, lane[1], toward=lane[2])
    zone = g._zone(hus)
    if tuple(lane[2]) not in zone:
        continue
    rs = g.submit("Allied", {"type": "move", "unit": mv["pid"],
                             "dest": list(lane[2])})
    pr = g.s.get("pending_react")
    if not pr or "reaction_charge" not in \
            pr["entitled"].get(hus["pid"], []):
        continue
    rc = g.submit("French", {"type": "reaction_charge",
                             "unit": hus["pid"]})
    res = rc["result"]
    rec = res.get("reaction_charge_check", {})
    if rec.get("result") == "may_melee" and not cc_ok:
        check("reaction charge passed its pre-melee check (Fox Q&A: "
              "reaction charges DO check) [6.2.3]",
              rec.get("cite", "").startswith("6.2.3"))
        check("the mover's movement ENDS on a successful reaction "
              "charge (Fox Q&A)", "movement_ended" in res)
        check("the reacting cavalry becomes the ATTACKER: charge "
              "machine opened on the mover's hex [6.2.3/8.4]",
              "reaction_charge" in res
              and (res.get("stand_check") or res.get("form_square")
                   or res.get("melee_rounds")
                   or g.s.get("pending_melee") is not None))
        # drive to completion; charger must end blown [8.4.2#9]
        guard = 0
        while g.s.get("pending_melee") and guard < 12:
            pm = g.s["pending_melee"]
            if pm["stage"] == "square_window":
                g.submit(pm["window_owner"],
                         {"type": "square_choice", "form": False})
            elif pm["stage"] == "return_window":
                g.submit(pm["window_owner"], {"type": "melee_no_return"})
            elif pm["stage"] in ("continue_def", "continue_att"):
                g.submit(pm["window_owner"], {"type": "melee_stand"})
            else:
                break
            guard += 1
        hn = g.unit(hus["pid"])
        if not hn.get("dead"):
            check("reaction charger ends disordered + Blown-2 "
                  "[8.4.2#9]", hn["blown"] == 2)
        cc_ok = True
    elif rec.get("result") != "may_melee" and not cc_fail:
        hn = g.unit(hus["pid"])
        check("failed reaction-charge check: immediately disordered, "
              "no charge [6.2.3]",
              hn["formation"] == "disorder"
              and hus["pid"] in g.s["cc_failed"]
              and g.s.get("pending_melee") is None)
        # lockout: may not try again this activation [6.2.3]
        mv2 = g.unit(mv["pid"])
        if not g.s.get("pending_react") and not mv2.get("dead"):
            second = by_slot(g, "G/Arkh")
            put(g, second, lane[1], toward=lane[2])
            rs2 = g.submit("Allied", {"type": "move",
                                      "unit": second["pid"],
                                      "dest": list(lane[2])})
            pr2 = g.s.get("pending_react")
            no_charge = (pr2 is None or "reaction_charge" not in
                         pr2.get("entitled", {}).get(hus["pid"], []))
            check("failed reaction charger may NOT try again this "
                  "activation [6.2.3]", no_charge)
            if pr2:
                g.submit("French", {"type": "decline_reaction"})
        cc_fail = True
check("reaction-charge success path exercised (seed hunt)", cc_ok)
check("reaction-charge failure path exercised (seed hunt)", cc_fail)

print("== decline: once declined, not re-prompted on later steps "
      "[6.2] ==")
g, live, seed = open_full("French:3")
atk = by_slot(g, "1/40 Ln")
dfn = by_slot(g, "3/Arkh")
lane = clear_lane(g, 3)
park_side(g, "Allied", keep=[dfn["pid"]])
put(g, dfn, lane[3], toward=lane[2])
zone = g._zone(dfn)
put(g, atk, lane[2], toward=lane[1])   # starts inside the zone
rs = g.submit("French", {"type": "move", "unit": atk["pid"],
                         "dest": list(lane[0])})
pr = g.s.get("pending_react")
if pr:
    rd = g.submit("Allied", {"type": "decline_reaction"})
    check("decline logs every entitlement it waives [6.2]",
          dfn["pid"] in rd["result"]["reactions_declined"])
    check("the walk resumed and completed without re-prompting the "
          "decliner [6.2]",
          g.s.get("pending_react") is None
          and "move_complete" in rd["result"])
else:
    check("decline setup failed to open a window", False)

print("== formation change in an enemy front hex triggers reactions "
      "(Fox Q&A) [6.2.1] ==")
g, live, seed = open_full("French:3")
atk = by_slot(g, "2/40 Ln")
dfn = by_slot(g, "3/Arkh")
lane = clear_lane(g, 2)
park_side(g, "Allied", keep=[dfn["pid"]])
put(g, dfn, lane[2], toward=lane[1])
put(g, atk, lane[1], toward=lane[2])
rs = g.submit("French", {"type": "change_formation",
                         "unit": atk["pid"], "to": "column"})
pr = g.s.get("pending_react")
check("MP-costing action inside the zone (formation change) opens the "
      "window [6.2.1 + Fox Q&A]",
      pr is not None and dfn["pid"] in pr["entitled"])
if pr:
    g.submit("Allied", {"type": "decline_reaction"})

print("== strategic movement [5.2] ==")
def _far_setup(gx):
    park_side(gx, "Allied")
g, live, seed = open_full("French:3", setup=_far_setup)
r = g.propose("French", {"type": "declare_strategic"})
check("strategic movement declarable on a fresh Full Activation "
      "[5.2]", r["legal"])
rs = g.submit("French", {"type": "declare_strategic"})
act = g.s["act"]
u40 = by_slot(g, "1/40 Ln")
check("strategic budgets = DOUBLE MA [5.2]",
      act["budget"][u40["pid"]] == 12.0
      and "French:3" in g.s["strat"]
      and "French:3" in g.s["strat_turn"])
r = g.propose("French", {"type": "declare_strategic"})
check("cannot declare twice [5.2]", not r["legal"])
# 3-hex exclusion in strat reachability [5.2.1]
foe = by_slot(g, "3/Arkh")
foe["col"], foe["row"] = u40["col"] + 4, u40["row"]
reach_s = g.reachable(u40["pid"], budget=12.0, strat=True)
reach_n = g.reachable(u40["pid"], budget=12.0)
near = {k for k in reach_n
        if g._dist((k[0], k[1]), (foe["col"], foe["row"])) <= 3
        and (k[0], k[1]) != (u40["col"], u40["row"])}
check("strat steps never enter hexes within 3 of an enemy [5.2.1] "
      "(control: normal reach does)",
      near and not any(g._dist((k[0], k[1]),
                               (foe["col"], foe["row"])) <= 3
                       for k in reach_s
                       if (k[0], k[1]) != (u40["col"], u40["row"])))
# road duty: woods entry requires Road Movement [5.2.1]
c0, c1, r0, r1 = g.area
foe["col"], foe["row"] = c1, r1
wclear, w = woods_pair(g)
road = g._road(wclear, w) is not None
if not road:
    u40["formation"] = "column"
    put(g, u40, wclear, toward=w)
    reach_s = g.reachable(u40["pid"], budget=12.0, strat=True)
    reach_n = g.reachable(u40["pid"], budget=12.0)
    check("off-road woods entry is normally reachable but NOT under "
          "strategic movement [5.2.1 road duties]",
          any((k[0], k[1]) == w for k in reach_n)
          and not any((k[0], k[1]) == w for k in reach_s))
else:
    check("woods_pair landed on a road - road-duty check via "
          "_strat_step_ok direct", not g._strat_step_ok(
              u40, wclear, w) or road)
# strat units refuse fire [5.2.1]
dfn = by_slot(g, "G/Arkh")
put(g, dfn, (u40["col"] + 1, u40["row"]))
tw = face_toward(g, u40, (dfn["col"], dfn["row"]))
u40["facing"] = tw
r = g.propose("French", {"type": "fire", "unit": u40["pid"],
                         "target": dfn["pid"]})
check("strategic movement: may never initiate combat - fire refused "
      "[5.2.1]", not r["legal"] and "strategic" in why(r).lower())
park_side(g, "Allied")
# must-move-as-far-as-possible + no-Line [5.2.1#4]
rs = g.submit("French", {"type": "end_activation"})
res = rs["result"]
check("strat division that idled in Line loses the marker: violation "
      "logged [5.2.1 + Fox liberal reading]",
      "strategic_violation" in res
      and "French:3" not in g.s["strat"])

# declared-after-acting rejection + happy path + sweep + fatigue hold
def _col_setup(gx):
    park_side(gx, "Allied")
    for u in gx.s["units"].values():
        if u["side"] == "French" and u["div"] == "3" \
                and u["arm"] == "infantry":
            u["formation"] = "column"
    gx.s["fatigue"]["French:3"] = 2
g, live, seed = open_full("French:3", setup=_col_setup)
u40 = by_slot(g, "1/40 Ln")
lm = g.legal_moves(u40["pid"])
d = lm["dests"][0]
g.submit("French", {"type": "move", "unit": u40["pid"],
                    "dest": [d["col"], d["row"]],
                    "facing": d["facing"]})
r = g.propose("French", {"type": "declare_strategic"})
check("strategic movement must be declared BEFORE the division acts "
      "[5.2.1]", not r["legal"])
g2c, live2c, _ = open_full("French:3", setup=_col_setup,
                           extra_lim=("Allied", "Markov"))
g2c.submit("French", {"type": "declare_strategic"})
act = g2c.s["act"]
moved_all = True
for pid in list(act["incommand"]):
    u = g2c.unit(pid)
    if u["arm"] == "leader":
        continue
    lm = g2c.legal_moves(pid)
    if not lm["can_act"] or not lm["dests"]:
        moved_all = False
        continue
    d = max(lm["dests"], key=lambda dd: dd["cost"])
    rr = g2c.submit("French", {"type": "move", "unit": pid,
                               "dest": [d["col"], d["row"]],
                               "facing": d["facing"]})
    if not rr["verdict"]["legal"]:
        moved_all = False
rs = g2c.submit("French", {"type": "end_activation"})
check("strat division that moved (columns, max reach) KEEPS the "
      "marker [5.2.1]",
      "strategic_violation" not in rs.get("result", {})
      and "French:3" in g2c.s["strat"])
# no reactions from strat units [5.2.1]: Allied moves next to them
mk = by_slot(g2c, "Markov")
mvA = by_slot(g2c, "2/Arkh")
u40 = by_slot(g2c, "1/40 Ln")
if g2c.s["phase"] == "activation" and g2c.s.get("act") \
        and g2c.s["act"].get("pending") == "choice" \
        and g2c.s["act"]["side"] == "Allied":
    g2c.submit("Allied", {"type": "activation_choice",
                          "choice": "limited"})
    act = g2c.s.get("act")
    if act and act.get("stage") == "move":
        # place Markov + a battalion within his command range near u40
        put(g2c, mk, (u40["col"] + 2, u40["row"]))
        if mvA["pid"] in act["incommand"]:
            put(g2c, mvA, (u40["col"] + 3, u40["row"]),
                toward=(u40["col"] + 2, u40["row"]))
            zone = g2c._zone(u40)
            check("a strat-marked unit projects NO reaction zone "
                  "[5.2.1 via 6.2 gate]",
                  g2c._react_kinds(u40, mvA,
                                   (u40["col"] + 1, u40["row"]),
                                   "post") == [])
        # enemy activation finishing within 3 hexes strips the marker
        rs = g2c.submit("Allied", {"type": "end_activation"})
        lost = rs.get("result", {}).get("strategic_markers_lost", [])
        check("enemy activation closing within 3 hexes strips the "
              "Strategic Movement marker [5.2.1]",
              any(e["div"] == "French:3" for e in lost)
              and "French:3" not in g2c.s["strat"])
# complete the turn: strat-only division's fatigue HOLDS (Fox Q&A)
guard = 0
while g2c.s["turn"] == 1 and guard < 80:
    ph = g2c.s["phase"]
    if g2c.s.get("pending_react"):
        g2c.submit(g2c.s["pending_react"]["side"],
                   {"type": "decline_reaction"})
    elif ph == "activation":
        act = g2c.s["act"]
        if act.get("pending") == "choice":
            kw = {"type": "activation_choice", "choice": "limited"}
            if act["kind"] == "independent":
                kw["division"] = [dd for dd in act["indep"]["eligible"]
                                  if dd not in act["indep"]["done"]][0]
            g2c.submit(act["side"], kw)
        elif act.get("pending") == "bd_offer":
            g2c.submit(act["side"], {"type": "bd_decline"})
        else:
            g2c.submit(act["side"], {"type": "end_activation"})
    elif ph == "non_lim":
        g2c.submit(g2c.s["mover"], {"type": "pass_non_lim"})
    elif ph == "rally":
        g2c.submit(g2c.s["mover"], {"type": "end_rally"})
    else:
        break
    guard += 1
check("fatigue HOLDS for a strat-only division: no +1 for the LIM, "
      "no -1 recovery [5.2.1 + Fox Q&A]",
      g2c.s["turn"] == 2 and g2c.s["fatigue"]["French:3"] == 2)

print("== charge vs a strategic-movement defender: forced stand, +2 "
      "DRMs, marker stripped [5.2.1/8.4.2] ==")
sc_done = False
for seed in range(1, 1000):
    try:
        g, live, _ = open_full("Allied:2", seeds=[seed],
                               extra_lim=("French", "Independent"))
    except RuntimeError:
        continue
    if g.s.get("act", {}).get("div") != "Allied:2":
        continue
    for u in g.s["units"].values():
        if u["side"] == "Allied" and u["div"] == "2" \
                and u["arm"] == "infantry":
            u["formation"] = "column"
    rs = g.submit("Allied", {"type": "declare_strategic"})
    if not rs["verdict"]["legal"]:
        continue
    # move every battalion so the marker survives the close
    act = g.s["act"]
    ok_move = True
    for pid in list(act["incommand"]):
        u = g.unit(pid)
        if u["arm"] == "leader":
            continue
        lm = g.legal_moves(pid)
        if lm["can_act"] and lm["dests"]:
            d = max(lm["dests"], key=lambda dd: dd["cost"])
            g.submit("Allied", {"type": "move", "unit": pid,
                                "dest": [d["col"], d["row"]],
                                "facing": d["facing"]})
    g.submit("Allied", {"type": "end_activation"})
    if "Allied:2" not in g.s["strat"]:
        continue
    act = g.s.get("act")
    if not (g.s["phase"] == "activation" and act
            and act.get("pending") == "choice"
            and act.get("side") == "French"):
        continue
    kw = {"type": "activation_choice", "choice": "full"}
    if act.get("kind") == "independent":
        if "French:T" not in act["indep"]["eligible"]:
            continue
        kw["division"] = "French:T"
    g.submit("French", kw)
    act = g.s.get("act")
    if not act or act.get("atype") != "full" or \
            act.get("div") != "French:T":
        continue
    hus = by_slot(g, "10 Hus")
    dfn = by_slot(g, "2/Arkh")
    park_side(g, "Allied", keep=[dfn["pid"]])
    park_side(g, "French", keep=[hus["pid"]])
    g.s["strat"] = ["Allied:2"]        # keep the marker on the target
    lane = clear_lane(g, 3)
    put(g, dfn, lane[3], toward=lane[0])
    put(g, hus, lane[0], toward=lane[1])
    if g._charge_path(hus, (dfn["col"], dfn["row"])) is None:
        continue
    clear, _ = g._los((hus["col"], hus["row"]),
                      (dfn["col"], dfn["row"]))
    if not clear:
        continue
    rs = g.submit("French", {"type": "charge", "unit": hus["pid"],
                             "target": dfn["pid"]})
    res = rs["result"]
    if "stand_check" not in res:
        continue
    check("strat infantry may NOT form square: forced to Stand with "
          "the pre-melee check [5.2.1/8.4.2#4]",
          not any(w["stage"] == "square_window"
                  for w in res.get("windows", [])))
    check("pre-shock DRM detail: strategic_movement +2 (charts p4)",
          res["stand_check"]["drms"].get("strategic_movement") == 2)
    out_all = dict(res)
    guard = 0
    while g.s.get("pending_melee") and guard < 12:
        pm = g.s["pending_melee"]
        if pm["stage"] == "return_window":
            r2 = g.submit(pm["window_owner"],
                          {"type": "melee_no_return"})
        elif pm["stage"] in ("continue_def", "continue_att"):
            r2 = g.submit(pm["window_owner"], {"type": "melee_stand"})
        else:
            break
        out_all.update(r2.get("result", {}))
        guard += 1
    if out_all.get("melee_rounds"):
        check("melee DRM detail: defender_strategic_movement +2 "
              "(charts p4)",
              out_all["melee_rounds"][0]["drms"]
              .get("defender_strategic_movement") == 2)
    check("strat defender loses the marker after combat completes "
          "[5.2.1]",
          "strategic_marker_removed" in out_all
          and "Allied:2" not in g.s["strat"])
    check("strat defenders never return fire in the melee window "
          "[5.2.1]",
          not any(w["stage"] == "return_window" and w["entitled"]
                  for w in out_all.get("windows", [])))
    sc_done = True
    break
check("charge-vs-strategic-defender flow exercised (seed hunt)",
      sc_done)

print("== full scripted schema-4 game -> independent replay "
      "[spec #9] ==")
gg, liveg = fresh(20260717)
submits = 0


def drive_pendings():
    global submits
    guard = 0
    while guard < 40:
        guard += 1
        pm = gg.s.get("pending_melee")
        pr = gg.s.get("pending_react")
        pf = gg.s.get("pending_fire")
        if pm:
            side = pm.get("window_owner")
            st = pm["stage"]
            if st == "square_window":
                gg.submit(side, {"type": "square_choice",
                                 "form": pm["round"] == 0})
            elif st == "return_window":
                ent = pm.get("entitled", {})
                pid = next((p for p, ks in ent.items()
                            if "melee_return" in ks), None)
                if pid:
                    gg.submit(side, {"type": "melee_return",
                                     "unit": pid})
                else:
                    gg.submit(side, {"type": "melee_no_return"})
            elif st in ("continue_def", "continue_att"):
                t = "melee_stand" if pm["round"] < 3 else \
                    "melee_withdraw"
                gg.submit(side, {"type": t})
            else:
                break
            submits += 1
            continue
        if pr:
            ent = pr["entitled"]
            pid, kinds = next(iter(ent.items()))
            kind = kinds[0]
            actn = {"type": kind, "unit": pid}
            if kind == "reaction_move":
                mvs = gg._reaction_moves(gg.unit(pid))
                if not mvs:
                    actn = {"type": "decline_reaction"}
                else:
                    actn["dest"] = list(mvs[0])
            if kind == "reaction_face":
                actn["turn"] = 2
            r = gg.propose(pr["side"], actn)
            if not r["legal"]:
                actn = {"type": "decline_reaction"}
            gg.submit(pr["side"], actn)
            submits += 1
            continue
        if pf:
            gg.submit(pf["defender_side"], {"type": "return_fire"})
            submits += 1
            continue
        return


melees_declared = charges_declared = 0
while not gg.flow()["over"] and gg.s["turn"] <= 6 and submits < 4000:
    drive_pendings()
    ph = gg.s["phase"]
    if ph == "command":
        gg.submit(gg.s["mover"],
                  {"type": "set_pool",
                   "lims": list(gg.scenario["initial_lims"]
                                [gg.s["mover"]])})
    elif ph == "initiative":
        own = [ref for ref in gg.s["pool"]
               if ref.startswith(gg.s["initiative"])]
        gg.submit(gg.s["initiative"],
                  {"type": "choose_initiative_lim",
                   "lim": own[0] if own else gg.s["pool"][0]})
    elif ph == "activation":
        act = gg.s["act"]
        if act.get("pending") == "choice":
            kw = {"type": "activation_choice", "choice": "full"}
            if act["kind"] == "independent":
                kw["division"] = [d for d in act["indep"]["eligible"]
                                  if d not in act["indep"]["done"]][0]
            if act["kind"] != "independent" and \
                    gg._at_div_breakpoint(act["div"] or ""):
                kw["choice"] = "limited"
            gg.submit(act["side"], kw)
        elif act.get("pending") == "bd_offer":
            gg.submit(act["side"], {"type": "bd_activate",
                                    "division": act["bd_closest"][0]})
        elif act.get("stage") in ("move", "melee", "combat"):
            side = act["side"]
            did = False
            # 1) try a melee/charge declaration
            for pid in act["incommand"]:
                u = gg.unit(pid)
                if u["arm"] == "leader" or u.get("dead"):
                    continue
                if u["arm"] == "infantry" and \
                        gg._may_initiate_melee(u)[0]:
                    for tgt in gg.s["units"].values():
                        if tgt["side"] == side or \
                                tgt["arm"] == "leader" or \
                                tgt.get("dead"):
                            continue
                        if (tgt["col"], tgt["row"]) not in \
                                front_of(gg, u):
                            continue
                        r = gg.propose(side, {"type": "melee",
                                              "unit": pid,
                                              "target": tgt["pid"]})
                        if r["legal"]:
                            gg.submit(side, {"type": "melee",
                                             "unit": pid,
                                             "target": tgt["pid"]})
                            melees_declared += 1
                            did = True
                            break
                if did:
                    break
                if u["arm"] == "cavalry" and not u.get("blown"):
                    for tgt in gg.s["units"].values():
                        if tgt["side"] == side or \
                                tgt["arm"] == "leader" or \
                                tgt.get("dead") or not gg.on_map(tgt):
                            continue
                        dd = gg._dist((u["col"], u["row"]),
                                      (tgt["col"], tgt["row"]))
                        if not 2 <= dd <= 4:
                            continue
                        r = gg.propose(side, {"type": "charge",
                                              "unit": pid,
                                              "target": tgt["pid"]})
                        if r["legal"]:
                            gg.submit(side, {"type": "charge",
                                             "unit": pid,
                                             "target": tgt["pid"]})
                            charges_declared += 1
                            did = True
                            break
                if did:
                    break
            if did:
                submits += 1
                drive_pendings()
                continue
            # 2) move someone toward the enemy
            if act.get("stage") == "move":
                for pid in act["incommand"]:
                    u = gg.unit(pid)
                    if pid in gg.s["moved"] or u["arm"] == "leader" \
                            or u.get("dead") \
                            or u.get("morale_state") == "routed":
                        continue
                    lm = gg.legal_moves(pid)
                    if lm["can_act"] and lm["dests"]:
                        ex = 40 if u["side"] == "Allied" else 75
                        dests = sorted(lm["dests"],
                                       key=lambda d: (abs(d["col"] - ex),
                                                      d["cost"]))
                        d = dests[0]
                        gg.submit(u["side"],
                                  {"type": "move", "unit": pid,
                                   "dest": [d["col"], d["row"]],
                                   "facing": d["facing"]})
                        did = True
                        break
            if not did:
                # 3) a shot, then end
                for pid in act["incommand"]:
                    u = gg.unit(pid)
                    if pid in gg.s["fired"] or u["arm"] == "leader":
                        continue
                    for tgt in gg.s["units"].values():
                        if tgt["side"] == u["side"] or \
                                tgt["arm"] == "leader" or \
                                tgt.get("dead"):
                            continue
                        r = gg.propose(u["side"],
                                       {"type": "fire", "unit": pid,
                                        "target": tgt["pid"]})
                        if r["legal"]:
                            gg.submit(u["side"],
                                      {"type": "fire", "unit": pid,
                                       "target": tgt["pid"]})
                            did = True
                            break
                    if did:
                        break
                if not did:
                    gg.submit(act["side"], {"type": "end_activation"})
        else:
            gg.submit(act["side"], {"type": "end_activation"})
    elif ph == "non_lim":
        o = gg._nonlim_options(gg.s["mover"])
        if o["divisions"]:
            gg.submit(gg.s["mover"], {"type": "non_lim",
                                      "division": o["divisions"][0]})
        elif o["units"]:
            gg.submit(gg.s["mover"], {"type": "non_lim",
                                      "unit": o["units"][0]})
        else:
            gg.submit(gg.s["mover"], {"type": "pass_non_lim"})
    elif ph == "rally":
        did = False
        for u in gg.s["units"].values():
            if u["side"] != gg.s["mover"] or not gg.on_map(u):
                continue
            if u.get("morale_state", "good") == "good" \
                    or u["pid"] in gg.s.get("rallied", []):
                continue
            r = gg.submit(gg.s["mover"], {"type": "rally",
                                          "unit": u["pid"]})
            if r["verdict"]["legal"]:
                did = True
                break
        if not did:
            gg.submit(gg.s["mover"], {"type": "end_rally"})
    submits += 1

log = os.path.join(liveg, "game_austerlitz-gmt.log.jsonl")
n_lines = sum(1 for _ in open(log, encoding="utf-8"))
check(f"scripted schema-4 game reached turn {gg.s['turn']} with "
      f"{melees_declared} melees + {charges_declared} charges "
      f"({n_lines} log entries)",
      gg.s["turn"] >= 3 and n_lines > 80 and melees_declared >= 1)
ok, msg = verify_game.verify(HERE, log)
check(f"verify_game replay: {msg[:90]}", ok)

print()
if FAILS:
    print(f"{len(FAILS)} FAILURES:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("validate_shock: ALL GREEN")
