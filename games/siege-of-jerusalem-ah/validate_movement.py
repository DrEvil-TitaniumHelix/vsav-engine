"""validate_movement.py - SoJ TEC movement gate, worked cases.

Two layers:
  A. GATE-DRIVEN: a deployed Gallus game (via validate_deploy's deployment)
     with submitted moves - Roman march budgets on clear terrain, wall entry
     denials, staircase costs, gate ground-passage closure [8.91], cauldron
     movement, stacking at move end, hex-control flips [18.3], phase cycle +
     seeded Giora reinforcement at turn 4. Log must replay through
     verify_game at the end.
  B. VERDICT PROBES (no submit): _move_verdict on crafted positions for the
     rules tier-1 play cannot physically reach yet (walls insulate ground
     ZOC until combat opens a breach - itself asserted here): hard-ZOC
     stop/exit [7.31/7.311], the Judaean freeze in Roman Heavy-Infantry
     ground ZOC (official Q&A 1/6/1992 - see source_defects), soft-ZOC +3
     [7.32], slope costs, cavalry prohibitions, SE pusher requirement [8.6].
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ENG = os.path.join(HERE, "..", "..", "engine")
sys.path.insert(0, ENG)
sys.path.insert(0, HERE)
import gamespec         # noqa: E402
import soj              # noqa: E402
from validate_deploy import deploy_all, submit_ok, submit_no  # noqa: E402


def hexes_path(tg, names):
    return [n for n in names]


def ok_move(tg, side, pid, names):
    return submit_ok(tg, side, {"type": "move", "pid": pid, "path": names})


def no_move(tg, side, pid, names, frag=""):
    return submit_no(tg, side, {"type": "move", "pid": pid, "path": names}, frag)


def clear_chain(tg, start, length):
    """A simple path of `length` clear, empty outside hexes from `start`
    (engine keys) - depth-first with backtracking."""
    def dfs(chain, seen):
        if len(chain) == length + 1:
            return chain
        for n in tg._nb(chain[-1]):
            if (n not in seen and n in tg.outside
                    and tg.hex_t0[n] == "clear" and not tg._occupants(n)):
                r = dfs(chain + [n], seen | {n})
                if r:
                    return r
        return None
    chain = dfs([start], {start})
    assert chain, f"no clear chain of {length} from {tg.hex_name[start]}"
    return [tg.hex_name[h] for h in chain]


def cycle_to(tg, phase, turn=None):
    """End phases (as whichever side owns the moment) until the target
    phase (and turn) is reached; returns the last end_phase result."""
    r = None
    for _ in range(200):
        if tg.s["phase"] == phase and (turn is None or tg.s["turn"] == turn):
            return r
        r = submit_ok(tg, tg.side_to_move(), {"type": "end_phase"})
    raise AssertionError(f"never reached {phase} turn {turn}")


def main():
    live = tempfile.mkdtemp(prefix="soj_mov_")
    try:
        g = gamespec.Game(HERE)
        tg = soj.SoJGame(g, os.path.join(HERE, "scenario_gallus.json"),
                         live, seed=11)
        deploy_all(tg)
        assert tg.s["phase"] == "rom_fire"

        # -------- phase discipline
        # any veteran with an open 9-hex chain: the A4-bounded west flank
        # packs the deployment densely enough that corner units (A25) are
        # walled in by their own camp
        heavy = chain9 = None
        for u in tg.s["units"].values():
            if u["type"] != "roman_veteran":
                continue
            try:
                chain9 = clear_chain(tg, u["hex"], 9)
                heavy = u
                break
            except AssertionError:
                continue
        assert chain9, "no roman_veteran with an open 9-hex clear chain"
        no_move(tg, "Rom", heavy["pid"], chain9[:3], "not the Rom Movement Phase")
        # fire phase: NON-phasing side's segment comes first [4.12]
        assert tg.side_to_move() == "Jud"
        submit_no(tg, "Rom", {"type": "end_phase"}, "not your phase")
        submit_ok(tg, "Jud", {"type": "end_phase"})   # end Judaean segment
        submit_ok(tg, "Rom", {"type": "end_phase"})   # end Roman segment
        assert tg.s["phase"] == "rom_move"

        # -------- Roman march budgets: heavy MA 8, clear = 1 each [TEC]
        no_move(tg, "Rom", heavy["pid"], chain9, "allowance exceeded")   # 9 MF
        ok_move(tg, "Rom", heavy["pid"], chain9[:9])                     # 8 MF
        assert tg.s["units"][heavy["pid"]]["hex"] == tg.name_hex[chain9[8]]
        # control flipped along the way [18.3]
        assert all(tg.s["control"][tg.name_hex[n]] == "Rom" for n in chain9[:9])

        # cavalry MA 15 on clear; may not enter Elevated [6.2]
        cav = next(u for u in tg.s["units"].values()
                   if u["type"] == "roman_cavalry")
        cchain = clear_chain(tg, cav["hex"], 15)
        ok_move(tg, "Rom", cav["pid"], cchain)
        # artillery: fresh MA is 0 in this scenario model [8.4 - see notes]
        art = next(u for u in tg.s["units"].values()
                   if u["type"] == "roman_ballista")
        achain = clear_chain(tg, art["hex"], 2)
        no_move(tg, "Rom", art["pid"], achain[:2], "allowance exceeded")

        # -------- Roman cannot pass a Judaean-held gate at ground level [8.91]
        # (find the Roman unit nearest Women's Gate approach is overkill -
        #  verdict probe below covers the geometry; here assert the terrain)
        z23 = tg.name_hex["Z23"]
        assert tg.s["control"][z23] == "Jud"

        cycle_to(tg, "jud_move")
        assert tg.s["phase"] == "jud_move"

        # -------- Judaean wall work: climb a staircase through the gate
        # find a (ground unit, staircase, strongpoint) trio from the actual
        # deployment (deterministic under the fixed seed)
        climb = None
        for pair in sorted(tg.stairs):
            gnd, wall = ((pair[0], pair[1])
                         if tg.hex_t0[pair[1]] in soj.ELEVATED else (pair[1], pair[0]))
            if tg.hex_t0[gnd] in soj.ELEVATED:
                continue
            unit = next((u for u in tg._occupants(gnd)
                         if u["side"] == "Jud" and u["type"] in
                         ("judaean_regular", "judaean_militia", "zealot")), None)
            if unit is None:
                continue
            v = tg._move_verdict("Jud", unit,
                                 [gnd, wall])
            if v["legal"]:
                climb = (unit, gnd, wall, v)
                break
        assert climb, "no staircase climb available from the deployment"
        unit, gnd, wall, v = climb
        assert "2 of" in v["reasons"][0], \
            f"staircase climb should cost 2 MF [8.93]: {v['reasons']}"
        ok_move(tg, "Jud", unit["pid"],
                [tg.hex_name[gnd], tg.hex_name[wall]])
        assert tg.s["units"][unit["pid"]]["hex"] == wall
        submit_ok(tg, "Jud", {"type": "end_phase"})       # -> jud_melee
        # jud_melee end -> VC check (0 Roman builtup) -> turn 2
        r = submit_ok(tg, "Jud", {"type": "end_phase"})
        assert r["result"]["roman_builtup"] == 0
        assert tg.s["turn"] == 2 and tg.s["phase"] == "rom_rally"

        # advance to the turn-4 Judaean MPh for the Giora reinforcement roll
        pool_before = len(tg.s["pool"])
        r = cycle_to(tg, "jud_move", turn=4)
        rr = r["result"].get("reinforcement")
        assert rr, "Giora reinforcement roll expected at turn-4 jud_move"
        assert rr["gate"] in ("OO33", "Q49")
        assert 2 <= rr["rolled"] <= 12, rr
        drawn = rr["entered"]
        assert drawn and drawn[0] == "S01", "Giora leader accompanies first draw"
        assert len(tg.s["pool"]) == pool_before - len(drawn)
        # queued units enter with a move whose path starts at the gate
        q0 = tg.s["entry_queue"][0]
        gate_name = tg.hex_name[q0["gate"]]
        inside = next(tg.hex_name[n] for n in tg._nb(q0["gate"])
                      if tuple(sorted((q0["gate"], n))) in tg.entrances
                      and n in tg.new_city and not tg._occupants(n))
        ok_move(tg, "Jud", q0["pid"], [gate_name, inside])
        assert tg.s["units"][q0["pid"]]["hex"] == tg.name_hex[inside]
        assert all(q["pid"] != q0["pid"] for q in tg.s["entry_queue"])

        print("gate-driven cases: PASS")

        # ---------------- B. verdict probes (no state mutation)
        probes(tg)

        # ---------------- C. interior roads [8.94/8.95/12.4] - B8
        road_checks(tg)

        # ---------------- D. rout/panic movement obligations - B16
        rout_obligation_checks(g)

        # ---------------- E. artillery flip-to-move [8.4] - B19
        artillery_flip_checks(g)

        # ---------------- log replays end-to-end
        r = subprocess.run(
            [sys.executable, os.path.join(ENG, "verify_game.py"),
             "--game", HERE,
             os.path.join(live, "game_siege-of-jerusalem-ah.log.jsonl")],
            capture_output=True, text=True)
        assert "VERIFIED" in r.stdout, r.stdout + r.stderr
        print(r.stdout.strip().splitlines()[-1])
        print("validate_movement: PASS")
    finally:
        shutil.rmtree(live, ignore_errors=True)


def walk(tg, u, dest):
    """Greedy legal-path walk toward dest across open crescent ground for
    test setup; returns a display-name path or None if already there."""
    if u["hex"] == dest:
        return None
    frontier = [(0, [u["hex"]])]
    seen = {u["hex"]}
    import heapq
    while frontier:
        cost, path = heapq.heappop(frontier)
        if path[-1] == dest:
            names = [tg.hex_name[h] for h in path]
            v = tg._move_verdict(u["side"], u, path)
            assert v["legal"], (names, v["reasons"])
            return names
        for n in tg._nb(path[-1]):
            if (n in seen or n not in tg.new_city
                    or tg.hex_t0[n] not in ("clear", "builtup")
                    or tg._occupants(n)):
                continue
            seen.add(n)
            heapq.heappush(frontier, (cost + 1, path + [n]))
    raise AssertionError("no open path to target")


def probes(tg):
    """Crafted-position verdict probes. State is snapshotted and restored;
    propose() never mutates, so the log stays clean."""
    import copy
    snap = copy.deepcopy(tg.s["units"])
    U = tg.s["units"]
    try:
        # stage: a Roman heavy at U20-equivalent open ground + Judaean nearby
        f = lambda name: tg.name_hex[name]
        rom = next(u for u in U.values() if u["type"] == "roman_veteran")
        jud = next(u for u in U.values() if u["type"] == "judaean_militia"
                   and u["hex"] is not None)
        cav = next(u for u in U.values() if u["type"] == "roman_cavalry")
        hq = next(u for u in U.values() if u["type"] == "gallus")
        # find a clear outside pocket: three empty hexes in a row (the pocket
        # must be empty of the camp, whatever shape deploy_rom gave it)
        a = next(h for h in sorted(tg.outside)
                 if tg.hex_t0[h] == "clear" and not tg._occupants(h)
                 and sum(1 for n in tg._nb(h) if n in tg.outside
                         and tg.hex_t0[n] == "clear"
                         and not tg._occupants(n)) >= 4)
        nbs = [n for n in tg._nb(a) if n in tg.outside
               and tg.hex_t0[n] == "clear" and not tg._occupants(n)]
        b, c = next((x, y) for x in nbs for y in nbs if y in tg._nb(x))
        rom["hex"], jud["hex"] = a, b        # adjacent ground units
        hq["hex"] = a                        # commander keeps the probe in CC
        # ground ZOC: Judaean moving out of Roman heavy ground ZOC = frozen
        # [7.311 + official Q&A 1/6/1992]
        v = tg._move_verdict("Jud", jud, [b, c])
        assert not v["legal"] and "7.311" in " ".join(v["reasons"]), v
        # the same Judaean as HQ-class is exempt (soft ZOC)
        jl = next(u for u in U.values() if u["type"] == "judaean_leader")
        jl["hex"] = b                        # HQ: soft ZOC, and covers CC
        v = tg._move_verdict("Jud", jl, [b, c])
        assert v["legal"], v["reasons"]      # HQ may leave, +3 MF [7.32]
        # hard-ZOC stop on entry [7.31]: Roman moving through Judaean zoc...
        # Judaean militia at b exerts zoc into adjacent ground hexes
        zoc_t = [n for n in tg._nb(b) if tg.hex_t0[n] in ("clear", "slope")
                 and n != a and n in tg._nb(a)]
        if zoc_t:
            t0 = zoc_t[0]
            far = next((n for n in tg._nb(t0)
                        if tg.hex_t0[n] == "clear" and n not in tg._nb(b)
                        and n != a), None)
            if far:
                v = tg._move_verdict("Rom", rom, [a, t0, far])
                assert not v["legal"] and "7.31" in " ".join(v["reasons"]), v
        k = lambda names: [tg.name_hex[n] for n in names]
        # cavalry may not enter Elevated [6.2]
        cav["hex"] = f("Z22")
        v = tg._move_verdict("Rom", cav, k(["Z22", "Z23"]))
        assert not v["legal"] and "6.2" in " ".join(v["reasons"]), v
        # Roman ground entry through an enemy gate is closed [8.91]
        rom2 = next(u for u in U.values() if u["type"] == "roman_line")
        rom2["hex"] = f("Z22")
        v = tg._move_verdict("Rom", rom2, k(["Z22", "Z23"]))
        assert not v["legal"] and "8.91" in " ".join(v["reasons"]), v
        # wall entry from ground without staircase/entrance [8.91-8.93]
        jud2 = next(u for u in U.values() if u["type"] == "judaean_regular")
        jud2["hex"] = f("X26")
        v = tg._move_verdict("Jud", jud2, k(["X26", "X25"]))
        assert not v["legal"] and "8.9" in " ".join(v["reasons"]), v
        # connected elevated = 1/2 MF each [TEC C]: Y24 -> X25 -> W26 -> V27
        jud2["hex"] = f("Y24")
        v = tg._move_verdict("Jud", jud2, k(["Y24", "X25", "W26", "V27"]))
        assert v["legal"], v["reasons"]
        assert "1.5" in v["reasons"][0], v["reasons"]
        # slope costs 3 for infantry, 7 cavalry [TEC]
        hz = tg._zoc_map("Rom") | tg._heavy_ground_zoc("Rom")
        s = next(h for h in sorted(tg.playable)
                 if tg.hex_t0[h] == "slope" and h not in hz
                 and not tg._occupants(h)
                 and any(tg.hex_t0[n] == "clear" and n not in hz
                         and not tg._occupants(n) for n in tg._nb(h)))
        cl = next(n for n in tg._nb(s)
                  if tg.hex_t0[n] == "clear" and n not in hz
                  and not tg._occupants(n))
        jud2["hex"] = cl
        jl["hex"] = cl                       # leader holds the probe in CC
        v = tg._move_verdict("Jud", jud2, [cl, s])
        assert v["legal"] and "3" in v["reasons"][0], v
        # siege engine without a pushing crew may not move [8.6]
        se = next(u for u in U.values() if u["type"] == "tower")
        se["hex"] = c
        crewless = tg._move_verdict("Rom", se,
                                    [c, next(n for n in tg._nb(c)
                                             if tg.hex_t0[n] == "clear")])
        assert not crewless["legal"] and "8.6" in " ".join(crewless["reasons"])
        # cauldron: elevated-to-elevated at 1/2, ground prohibited [8.5]
        cd = next(u for u in U.values() if u["type"] == "cauldron")
        cd["hex"] = f("Y24")
        v = tg._move_verdict("Jud", cd, k(["Y24", "X25"]))
        assert v["legal"] and "0.5" in v["reasons"][0], v
        v = tg._move_verdict("Jud", cd, k(["Y24", "Y25"]))
        assert not v["legal"] and "8.5" in " ".join(v["reasons"]), v
        print("verdict probes: PASS")
    finally:
        tg.s["units"] = snap


def road_checks(tg):
    """[8.94/8.95/12.4 + The General 26-4 p.13] interior roads - B8.
    Data structure, the 1/2-MF rate, and the Cavalry/Artillery Built-up
    road-hexside gate, on crafted positions (snapshot/restore)."""
    import copy
    snap = copy.deepcopy(tg.s["units"])
    U = tg.s["units"]
    f = lambda name: tg.name_hex[name]
    k = lambda names: [tg.name_hex[n] for n in names]
    try:
        # ---- data structure [8.94]: 105 art-derived city-interior sides,
        # every one joining two ground hexes inside the walls
        assert len(tg.roads) == 105, len(tg.roads)
        for a, b in tg.roads:
            assert tg.hex_t0[a] in ("clear", "builtup"), (a, tg.hex_t0[a])
            assert tg.hex_t0[b] in ("clear", "builtup"), (b, tg.hex_t0[b])
            assert a in tg.new_city and b in tg.new_city, (a, b)
        side = lambda x, y: tuple(sorted((f(x), f(y))))
        # calibration anchors (ingest/road_hexsides.json)
        for x, y in (("Z24", "Z25"), ("W28", "X27"), ("Q45", "R44"),
                     ("Y26", "Z25"), ("Q36", "R36")):
            assert side(x, y) in tg.roads, (x, y)
        # adjudication rejects: wash false-positives and non-crossings stay out
        for x, y in (("Q42", "R42"), ("AA23", "AA24"), ("W27", "X27"),
                     ("KK25", "KK26")):
            assert side(x, y) not in tg.roads, (x, y)

        # ---- stage a cleared corridor along the Womens-Gate road + NE artery
        route = ["U30", "V29", "W28", "X27", "Y26", "Z25", "Z26", "Z27",
                 "Z28", "Z29", "Z30", "Y31", "Y32", "X33"]
        bubble = set()
        for n in route + ["W27"]:
            bubble.add(f(n))
            bubble |= set(tg._nb(f(n)))
        parking = iter(sorted(h for h in tg.outside
                              if tg.hex_t0[h] == "clear"
                              and not tg._occupants(h) and h not in bubble))
        for u in U.values():
            if u["hex"] in bubble:
                u["hex"] = next(parking)

        # ---- 1/2 MF along the road [8.94/12.4]: militia MA 6 marches 12 road
        # hexsides for exactly 6.0 MF; 13 exceeds the allowance
        mil = next(u for u in U.values() if u["type"] == "judaean_militia")
        jl = next(u for u in U.values() if u["type"] == "judaean_leader")
        mil["hex"] = f("V29")
        jl["hex"] = f("V29")             # leader keeps the probe in CC
        assert tg._ma(mil) == 6
        v = tg._move_verdict("Jud", mil, k(route[1:]))       # 12 crossings
        assert v["legal"], v["reasons"]
        assert "6" in v["reasons"][0], v["reasons"]
        mil["hex"] = f("U30")
        jl["hex"] = f("U30")
        v = tg._move_verdict("Jud", mil, k(route))           # 13 crossings
        assert not v["legal"] and "exceeded" in " ".join(v["reasons"]), v
        # off-road the same 12-hex march would cost >= 12 MF - the road halves it
        cost, why = tg._entry_cost(mil, f("W27"), f("X26"), "Jud")
        assert cost == 1.0, (cost, why)  # clear, no road side

        # ---- Built-up entry costs: road rate replaces the TEC figure
        rom = next(u for u in U.values() if u["type"] == "roman_veteran")
        assert tg._entry_cost(rom, f("W28"), f("X27"), "Rom")[0] == 0.5
        assert tg._entry_cost(rom, f("W27"), f("X27"), "Rom")[0] == 3.0
        assert tg._entry_cost(mil, f("W27"), f("X27"), "Jud")[0] == 2.0

        # ---- 8.95: Cavalry and Artillery enter/exit Built-up only through
        # road hexsides
        cav = next(u for u in U.values() if u["type"] == "roman_cavalry")
        art = next(u for u in U.values() if u["type"] == "roman_ballista")
        for u in (cav, art):
            c, why = tg._entry_cost(u, f("W27"), f("X27"), "Rom")
            assert c is None and "8.95" in why, (u["type"], why)
            c, why = tg._entry_cost(u, f("W28"), f("X27"), "Rom")
            assert c == 0.5, (u["type"], c, why)
            c, why = tg._entry_cost(u, f("X27"), f("W27"), "Rom")   # exit
            assert c is None and "8.95" in why, (u["type"], why)
            c, why = tg._entry_cost(u, f("X27"), f("W28"), "Rom")
            assert c == 0.5, (u["type"], c, why)
        # gate-driven: cavalry commits the road-side Built-up entry
        hq = next(u for u in U.values() if u["type"] == "gallus")
        cav["hex"] = f("W28")
        hq["hex"] = f("W28")
        v = tg._move_verdict("Rom", cav, k(["W28", "X27"]))
        assert v["legal"], v["reasons"]
        assert "0.5" in v["reasons"][0], v["reasons"]

        # ---- a road hexside never unlocks terrain a class may not enter:
        # Siege Engines stay barred from Built-up [TEC]
        se = next(u for u in U.values() if u["type"] == "tower")
        c, why = tg._entry_cost(se, f("W28"), f("X27"), "Rom")
        assert c is None and "TEC" in why, (c, why)

        print("road checks [8.94/8.95/12.4]: PASS")
    finally:
        tg.s["units"] = snap


def rout_obligation_checks(g):
    live = tempfile.mkdtemp(prefix="soj_rout_")
    try:
        tg = soj.SoJGame(g, os.path.join(HERE, "scenario_gallus.json"),
                         live, seed=31)
        U = tg.s["units"]
        tg.s["deploy_done"] = {"Jud": True, "Rom": True}
        tg.s["turn"] = 1
        N = tg.hex_name

        def take(t, n):
            out = [u for u in U.values()
                   if u["type"] == t and u["hex"] is None
                   and u["state"] == "fresh"][:n]
            assert len(out) == n, f"need {n} {t}"
            return out

        def clear1(h):
            return (h in tg.playable and h in tg.outside
                    and tg.hex_t0[h] == "clear"
                    and len(tg._nb(h)) == 6 and not tg._occupants(h))

        def chain_n(h, length):
            def dfs(c):
                if len(c) == length + 1:
                    return c
                for n in tg._nb(c[-1]):
                    if n not in c and clear1(n) and \
                            tg._refuge_dist("Rom", n) < \
                            tg._refuge_dist("Rom", c[-1]):
                        r = dfs(c + [n])
                        if r:
                            return r
                return None
            return dfs([h])

        def pocket(avoid=()):
            return next(h for h in sorted(tg.hex_t0)
                        if clear1(h)
                        and all(clear1(n) for n in tg._nb(h))
                        and all(clear1(m) for n in tg._nb(h)
                                for m in tg._nb(n))
                        and all(tg._dist(h, a) > 5 for a in avoid)
                        and chain_n(h, 5))

        def mph(phase):
            tg.s["phase"] = phase
            tg.s["pmoved"] = False
            tg._mph_bookkeeping()

        def toward(h):
            d0 = tg._refuge_dist("Rom", h)
            return [n for n in tg._nb(h)
                    if tg._refuge_dist("Rom", n) < d0]

        def lateral(h):
            d0 = tg._refuge_dist("Rom", h)
            return [n for n in tg._nb(h)
                    if tg._refuge_dist("Rom", n) == d0]

        def park(*us):
            for x in us:
                x["hex"] = None
                x["state"] = "fresh"
                x.pop("fin", None)

        # ---- full-MF obligation + per-hex direction + end_phase gate
        mph("rom_move")
        h0 = pocket()
        vr = take("roman_veteran", 1)[0]
        vr["hex"], vr["state"] = h0, "routed"
        away = next(n for n in tg._nb(h0)
                    if tg._refuge_dist("Rom", n) > tg._refuge_dist("Rom", h0))
        no_move(tg, "Rom", vr["pid"], [N[h0], N[away]], "must be closer")
        no_move(tg, "Rom", vr["pid"], [N[h0], N[lateral(h0)[0]]],
                "must be closer")
        submit_no(tg, "Rom", {"type": "end_phase"},
                  "using all available MF")
        assert abs(tg._ma(vr) - 5.0) < 1e-9
        steps = chain_n(h0, 5)
        ok_move(tg, "Rom", vr["pid"], [N[steps[0]], N[steps[1]]])
        submit_no(tg, "Rom", {"type": "end_phase"},
                  "using all available MF")
        ok_move(tg, "Rom", vr["pid"], [N[h] for h in steps[1:]])
        assert vr["hex"] == steps[5] and abs(vr["mv"] - 5.0) < 1e-9
        submit_ok(tg, "Rom", {"type": "end_phase"})
        assert tg.s["phase"] == "rom_melee"
        print("rout obligations: away/lateral steps refused, end_phase "
              "gated until the routed unit spends its full Disrupted MA "
              "towards Refuge OK [15.3/17.21/8.1]")

        # ---- unable to move (enemy ZOC over every closer hex) = stay
        park(vr)
        mph("rom_move")
        h1 = pocket()
        vr2 = take("roman_veteran", 1)[0]
        vr2["hex"], vr2["state"] = h1, "routed"
        tw1 = toward(h1)
        zs = take("zealot", len(tw1))
        for z, t1 in zip(zs, tw1):
            z["hex"] = t1
        for t1 in tw1:
            no_move(tg, "Rom", vr2["pid"], [N[h1], N[t1]],
                    "may not enter an enemy-occupied hex")
        submit_ok(tg, "Rom", {"type": "end_phase"})
        print("rout obligations: a Routed unit unable to move (every "
              "closer hex enemy-held) remains in place - phase may end "
              "OK [17.21]")

        # ---- Panicked move last; a Panicked move ends all other movement
        park(vr2, *zs)
        mph("rom_move")
        h2 = pocket()
        h3 = pocket(avoid=(h2,))
        h4 = pocket(avoid=(h2, h3))
        vp, vr3, vn = take("roman_veteran", 3)
        vp["hex"], vp["state"] = h2, "panicked"
        vr3["hex"], vr3["state"] = h3, "routed"
        vn["hex"] = h4
        c2 = chain_n(h2, 5)
        t2 = c2[1]
        no_move(tg, "Rom", vp["pid"], [N[h2], N[t2]],
                "before Panicked units move")
        s3 = chain_n(h3, 5)
        ok_move(tg, "Rom", vr3["pid"], [N[h] for h in s3])
        v4 = next(n for n in tg._nb(h4) if clear1(n))
        ok_move(tg, "Rom", vn["pid"], [N[h4], N[v4]])
        ok_move(tg, "Rom", vp["pid"], [N[h2], N[t2]])
        assert tg.s["pmoved"] is True
        no_move(tg, "Rom", vn["pid"], [N[v4], N[h4]],
                "after all other units have finished")
        ok_move(tg, "Rom", vp["pid"], [N[h] for h in c2[1:]])
        submit_ok(tg, "Rom", {"type": "end_phase"})
        assert tg.s["pmoved"] is False
        print("rout obligations: Panicked units move only after Routed "
              "obligations are met, and their move ends all other "
              "movement OK [4.13/8.1/17.21]")

        # ---- entering a Panicked hex ends the mover's MPh [17.21]
        park(vp, vr3, vn)
        mph("rom_move")
        h5 = pocket()
        vp2, vn2 = take("roman_veteran", 2)
        vp2["hex"], vp2["state"] = h5, "panicked"
        e5 = next(n for n in tg._nb(h5) if clear1(n))
        e6 = next(n for n in tg._nb(h5) if clear1(n) and n != e5)
        vn2["hex"] = e5
        no_move(tg, "Rom", vn2["pid"], [N[e5], N[h5], N[e6]],
                "must stop on entering a hex with a Panicked unit")
        r = ok_move(tg, "Rom", vn2["pid"], [N[e5], N[h5]])
        assert r["result"].get("fin") and vn2.get("fin")
        no_move(tg, "Rom", vn2["pid"], [N[h5], N[e6]],
                "MPh ended when it entered a hex containing a Panicked")
        submit_no(tg, "Rom", {"type": "escalade", "pid": vn2["pid"],
                              "op": "place"},
                  "MPh ended when it entered a hex containing a Panicked")
        mph("rom_move")
        assert not vn2.get("fin"), "fin clears at the phase boundary"
        print("rout obligations: the forced stop in a Panicked hex ends "
              "that unit's MPh - further moves and MF-spending refused, "
              "flag clears at phase change OK [17.21]")

        # ---- forced stop that overstacks eliminates the enterer [17.21]
        park(vn2)
        vf = take("roman_veteran", 2)
        vf[0]["hex"] = vf[1]["hex"] = h5
        vn3 = take("roman_veteran", 1)[0]
        vn3["hex"] = e6
        assert tg._combat_count(tg._occupants(h5)) == 3
        r = ok_move(tg, "Rom", vn3["pid"], [N[e6], N[h5]])
        assert "overstacked" in r["result"].get("eliminated", ""), r
        assert vn3["state"] == "eliminated" and vn3["hex"] is None
        assert all(x["state"] != "eliminated"
                   for x in (vp2, vn2, *vf))
        vr4 = take("roman_veteran", 1)[0]
        s5 = next(n for n in tg._nb(h5)
                  if tg._refuge_dist("Rom", n) >
                  tg._refuge_dist("Rom", h5) and clear1(n))
        vr4["hex"], vr4["state"] = s5, "routed"
        if tg._refuge_dist("Rom", h5) < tg._refuge_dist("Rom", s5):
            no_move(tg, "Rom", vr4["pid"], [N[s5], N[h5]],
                    "never ends in elimination")
        print("rout obligations: a voluntary entry that overstacks the "
              "Panicked hex is legal but eliminates the entering unit; "
              "a mandatory Refuge move may never do so OK [17.21]")

        # ---- 15.3 road lock (Judaean routed unit on the city roads)
        park(vp2, vn2, vr4, *vf)
        mph("jud_move")
        rd0 = tg._road_ref_dist("Jud", set())
        jm = take("judaean_militia", 1)[0]
        cavs = [u for u in U.values() if u["type"] == "roman_cavalry"
                and u["hex"] is None]

        def unblock():
            for b in cavs:
                b["hex"] = None

        R = off = on = off2 = None
        for h, d in sorted(rd0.items(), key=lambda kv: kv[1]):
            if d < 2 or tg._occupants(h):
                continue
            offs = [n for n in tg._nb(h)
                    if tg._refuge_dist("Jud", n) < tg._refuge_dist("Jud", h)
                    and tuple(sorted((h, n))) not in tg.roads
                    and not tg._occupants(n)
                    and tg._entry_cost(jm, h, n, "Jud")[0] is not None]
            ons = [n for n in tg._nb(h)
                   if tuple(sorted((h, n))) in tg.roads
                   and rd0.get(n, 99) < d and not tg._occupants(n)]
            rnb = [n for n in tg._nb(h)
                   if tuple(sorted((h, n))) in tg.roads]
            if not (offs and ons) or len(rnb) > len(cavs):
                continue
            for b, n in zip(cavs, rnb):
                b["hex"] = n
            zocR = tg._zoc_map("Rom")
            o2 = [n for n in offs if n not in zocR
                  and not tg._occupants(n)]
            if h not in tg._road_ref_dist("Jud", zocR) \
                    and h not in tg._heavy_ground_zoc("Rom") and o2:
                R, off, on, off2 = h, offs[0], ons[0], o2[0]
                unblock()
                break
            unblock()
        assert R is not None, "test geometry: no suitable locked road hex"
        jm["hex"], jm["state"] = R, "routed"
        no_move(tg, "Jud", jm["pid"], [N[R], N[off]],
                "must remain on that road")
        v = tg._move_verdict("Jud", jm, [R, on])
        assert v["legal"], v["reasons"]
        for b, n in zip(cavs, [n for n in tg._nb(R)
                               if tuple(sorted((R, n))) in tg.roads]):
            b["hex"] = n
        assert R not in tg._road_ref_dist("Jud", tg._zoc_map("Rom"))
        v = tg._move_verdict("Jud", jm, [R, off2])
        assert v["legal"], \
            ("an obstructed road frees the unit to leave it towards "
             "Refuge [15.3]", v["reasons"])
        unblock()
        print("road lock: on an unobstructed road to Refuge the unit must "
              "keep to it; obstruction frees it to leave towards Refuge "
              "OK [15.3]")

        print("rout obligation checks: PASS (B16 15.3/17.21/8.1/4.13)")
    finally:
        shutil.rmtree(live, ignore_errors=True)


def artillery_flip_checks(g):
    live = tempfile.mkdtemp(prefix="soj_flip_")
    try:
        tg = soj.SoJGame(g, os.path.join(HERE, "scenario_gallus.json"),
                         live, seed=41)
        U = tg.s["units"]
        tg.s["deploy_done"] = {"Jud": True, "Rom": True}
        tg.s["turn"] = 1
        tg.s["phase"] = "rom_move"
        tg._mph_bookkeeping()
        N = tg.hex_name

        assert all(tg.hex_t0[h] not in soj.ELEVATED for h in tg.rom_zone), \
            ("the Roman deployment zone holds no Elevated hex - 8.4's "
             "Elevated-start clause cannot arise in Gallus")

        def clear1(h):
            return (h in tg.playable and h in tg.outside
                    and tg.hex_t0[h] == "clear"
                    and len(tg._nb(h)) == 6 and not tg._occupants(h))

        bal = next(u for u in U.values() if u["type"] == "roman_ballista")
        h0 = next(h for h in sorted(tg.hex_t0)
                  if clear1(h) and all(clear1(n) for n in tg._nb(h))
                  and all(clear1(m) for n in tg._nb(h) for m in tg._nb(n)))
        bal["hex"] = h0
        no_move(tg, "Rom", bal["pid"], [N[h0], N[tg._nb(h0)[0]]],
                "allowance exceeded")
        tg.s["phase"] = "rom_fire"
        submit_no(tg, "Rom", {"type": "flip", "pid": bal["pid"]},
                  "owning Movement Phase")
        tg.s["phase"] = "rom_move"
        vet = next(u for u in U.values() if u["type"] == "roman_veteran"
                   and u["hex"] is None)
        submit_no(tg, "Rom", {"type": "flip", "pid": vet["pid"]},
                  "unit is not on the map")
        vet["hex"] = tg._nb(h0)[1]
        submit_no(tg, "Rom", {"type": "flip", "pid": vet["pid"]},
                  "only Artillery flips")
        r = submit_ok(tg, "Rom", {"type": "flip", "pid": bal["pid"]})
        assert r["result"]["state"] == "disrupted" \
            and bal["state"] == "disrupted"
        submit_no(tg, "Rom", {"type": "flip", "pid": bal["pid"]},
                  "only Fresh Artillery")
        assert abs(tg._ma(bal) - 4.0) < 1e-9
        chain = clear_chain(tg, h0, 5)
        no_move(tg, "Rom", bal["pid"], chain[:6], "allowance exceeded")
        ok_move(tg, "Rom", bal["pid"], chain[:5])
        assert bal["hex"] == tg.name_hex[chain[4]]
        print("artillery flip: Fresh Roman Artillery cannot move (MA 0); "
              "the voluntary flip turns it Disrupted (MA 4) and it "
              "marches; phase/side/class/state refusals OK [8.4]")

        jm = next(u for u in U.values()
                  if u["type"] == "judaean_militia" and u["hex"] is None)
        tgt = tg.name_hex[clear_chain(tg, bal["hex"], 2)[2]]
        jm["hex"] = tgt
        tg.s["phase"] = "rom_fire"
        tg.s["seg"] = "Rom"
        v = tg.propose("Rom", {"type": "fire", "target": N[tgt],
                               "firers": [bal["pid"]]})
        assert not v["legal"] \
            and "not Fresh" in " ".join(v["reasons"]), v["reasons"]
        print("artillery flip: the flipped (Disrupted, moving) Artillery "
              "may not fire until rallied OK [8.4/9.1/16.2]")

        tg.s["phase"] = "jud_move"
        tg._mph_bookkeeping()
        cld = next(u for u in U.values() if u["type"] == "cauldron")
        wall = next(h for h in sorted(tg.hex_t0)
                    if tg.hex_t0[h] == "wall" and h in tg.playable
                    and not tg._occupants(h))
        cld["hex"] = wall
        submit_no(tg, "Jud", {"type": "flip", "pid": bal["pid"]},
                  "not your unit")
        submit_no(tg, "Jud", {"type": "flip", "pid": cld["pid"]},
                  "no flip needed")
        print("artillery flip: Cauldrons never flip - they move Fresh or "
              "Disrupted OK [8.5]")

        print("artillery flip checks: PASS (B19 8.4)")
    finally:
        shutil.rmtree(live, ignore_errors=True)


if __name__ == "__main__":
    main()
