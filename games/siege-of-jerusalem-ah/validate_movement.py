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
        # find a (ground unit, staircase, strongpoint) trio: walk a deployed
        # Judaean to the ground end of a surviving art-confirmed staircase
        # (the R4 exclusion removed the session-1 stairs that used to sit
        # under the deployment), then climb it [8.93]
        climb = None
        juds = sorted((u for u in tg.s["units"].values()
                       if u["side"] == "Jud" and u["hex"] is not None
                       and u["type"] in ("judaean_regular",
                                         "judaean_militia", "zealot")
                       and tg.hex_t0[u["hex"]] in ("clear", "builtup")),
                      key=lambda x: x["pid"])
        for pair in sorted(tg.stairs):
            gnd, wall = ((pair[0], pair[1])
                         if tg.hex_t0[pair[1]] in soj.ELEVATED else (pair[1], pair[0]))
            if tg.hex_t0[gnd] in soj.ELEVATED or gnd not in tg.playable \
                    or wall not in tg.playable:
                continue
            for unit in juds:
                if unit["hex"] != gnd and tg._occupants(gnd):
                    continue
                try:
                    names = walk(tg, unit, gnd)
                except AssertionError:
                    continue
                cost = sum(2.0 if tg.hex_t0[tg.name_hex[n]] == "builtup"
                           else 1.0 for n in (names or [])[1:])
                if tg._ma(unit) - cost < 2.0:
                    continue
                if names:
                    ok_move(tg, "Jud", unit["pid"], names)
                v = tg._move_verdict("Jud", unit, [gnd, wall])
                if v["legal"]:
                    climb = (unit, gnd, wall, v)
                break
            if climb:
                break
        assert climb, "no staircase climb reachable from the deployment"
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
        q0u = tg.s["units"][q0["pid"]]
        assert q0u["hex"] == tg.name_hex[inside]
        assert all(q["pid"] != q0["pid"] for q in tg.s["entry_queue"])
        assert tg.in_cc(q0u) == tg._cc_unit(q0u, tg._cc_map("Jud")), \
            "an entrant's CC is determined at entry [5.1 ruling]"

        print("gate-driven cases: PASS")

        # ---------------- B. verdict probes (no state mutation)
        probes(tg)

        # ---------------- C. interior roads [8.94/8.95/12.4] - B8
        road_checks(tg)

        # ---------------- D. rout/panic movement obligations - B16
        rout_obligation_checks(g)

        # ---------------- E. artillery flip-to-move [8.4] - B19
        artillery_flip_checks(g)

        # ---------------- F. Command Control exact tracing [5.1/5.2] - B18
        cc_trace_checks(g)

        # ---------------- G. MPh doors: 8.2/7.321/8.13/gates/6.x - Bite 21
        mph_door_checks(g)

        # ---------------- H. offboard exit [8.14/15.5] - Bite 24 (N12)
        offboard_exit_checks(g)

        # ---------------- I. Garrison Areas declared ruling - Bite 25 (R1)
        garrison_checks(g)

        # ---------------- J. doubtful-staircase exclusion - Bite 25 (R4)
        stair_exclusion_checks(g)

        # ---------------- 5-bastion evidence pass (2026-08-13)
        north_wall_strongpoint_checks(g)

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
        tg._cc_snapshot()
        # ground ZOC: Judaean moving out of Roman heavy ground ZOC = frozen
        # [7.311 + official Q&A 1/6/1992]
        v = tg._move_verdict("Jud", jud, [b, c])
        assert not v["legal"] and "7.311" in " ".join(v["reasons"]), v
        # the same Judaean as HQ-class is exempt (soft ZOC)
        jl = next(u for u in U.values() if u["type"] == "judaean_leader")
        jl["hex"] = b                        # HQ: soft ZOC, and covers CC
        tg._cc_snapshot()
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
        tg._cc_snapshot()
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
        tg._cc_snapshot()


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


def cc_trace_checks(g):
    live = tempfile.mkdtemp(prefix="soj_cc_")
    try:
        tg = soj.SoJGame(g, os.path.join(HERE, "scenario_gallus.json"),
                         live, seed=51)
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
                    and h not in tg.rom_prohibited
                    and len(tg._nb(h)) == 6 and not tg._occupants(h))

        def mph(phase):
            tg.s["phase"] = phase
            tg.s["pmoved"] = False
            tg._mph_bookkeeping()

        def park(*us):
            for x in us:
                x["hex"] = None
                x["state"] = "fresh"
                x.pop("up", None)
                x.pop("fin", None)

        def axis_line(k):
            for h in sorted(tg.hex_t0):
                for dq, dr in ((1, 0), (0, 1), (1, -1)):
                    for sign in (1, -1):
                        L = []
                        c, r = int(h[:2]), int(h[2:])
                        n0 = r - c // 2
                        for i in range(k):
                            c2 = c + dq * sign * i
                            n2 = n0 + dr * sign * i
                            L.append(f"{c2:02d}{n2 + c2 // 2:02d}")
                        if all(x in tg.hex_t0 and clear1(x) for x in L):
                            return L
            raise AssertionError(f"no clear axis {k}-line")

        # ---- the printed 5.2 EXAMPLE: a flanked Wall traces no CC at all
        wall = mil = jl = None
        for w in sorted(tg.hex_t0):
            if tg.hex_t0[w] != "wall" or w not in tg.playable \
                    or tg._occupants(w):
                continue
            elev = [n for n in tg._nb(w) if tg.hex_t(n) in soj.ELEVATED]
            ground = [n for n in tg._nb(w)
                      if n in tg.playable and n not in tg.rom_prohibited
                      and tg.hex_t(n) not in soj.ELEVATED
                      and tg.hex_t(n) in ("clear", "slope")
                      and not tg._occupants(n)]
            if elev and ground and len(elev) <= 3:
                wall, E, G = w, elev, ground[0]
                break
        assert wall, "no flanked-wall topology"
        mil = take("judaean_militia", 1)[0]
        mil["hex"] = wall
        jl = next(u for u in U.values() if u["type"] == "judaean_leader"
                  and u.get("faction") == mil.get("faction")
                  and u["hex"] is None)
        jl["hex"] = G
        roms = take("roman_veteran", len(E))
        for x, e in zip(roms, E):
            x["hex"] = e
        mph("jud_move")
        assert not tg.in_cc(mil), \
            "flanked Wall unit may not trace CC even one hex [5.2 EXAMPLE]"
        park(roms[0])
        jl["hex"] = E[0]
        mph("jud_move")
        assert tg.in_cc(mil), "open Elevated route restores the trace [5.2]"
        park(mil, jl, *roms)
        print("cc trace: the printed 5.2 EXAMPLE reproduced - Romans on the "
              "connected Elevated hexes cut CC to the Wall entirely (ground "
              "hexes do not connect to a Wall), reopened route traces OK")

        # ---- unique axis path: radius pin + through-vs-terminal doors
        L = axis_line(11)
        K = [tg.name_hex.get(x, x) for x in L]
        gal = next(u for u in U.values() if u["type"] == "gallus")
        vet = take("roman_veteran", 1)[0]
        gal["hex"], vet["hex"] = L[0], L[10]
        mph("rom_move")
        assert tg.in_cc(vet), "10 hexes = in range [5.1]"

        va, vb = take("roman_veteran", 2)
        va["hex"] = vb["hex"] = L[5]
        tg.s["testudo"].append({"hex": L[5], "legion": va.get("faction"),
                                "mv": 0.0})
        mph("rom_move")
        assert not tg.in_cc(vet), \
            "an intact Testudo hex is enterable only to JOIN - the trace " \
            "may not pass through [5.2/6.61]"
        assert tg.in_cc(va), "the Testudo hex itself still receives CC"
        tg.s["testudo"] = []
        mph("rom_move")
        assert tg.in_cc(vet)
        park(va, vb)

        pan = take("roman_line", 1)[0]
        pan["hex"], pan["state"] = L[5], "panicked"
        mph("rom_move")
        assert not tg.in_cc(vet), \
            "the HQ must stop on entering a Panicked hex - no through-trace " \
            "[5.2/17.21]"
        assert tg.in_cc(pan), "the Panicked hex itself still receives CC"
        park(pan)

        z = take("zealot", 1)[0]
        z["hex"] = next(n for n in tg._nb(L[5]) if clear1(n))
        gal["state"] = "disrupted"
        vet["hex"] = L[8]
        mph("rom_move")
        assert not tg.in_cc(vet), \
            "a Disrupted HQ may not enter enemy ZOC - the trace obeys " \
            "16.51 [5.2/16.51]"
        gal["state"] = "fresh"
        mph("rom_move")
        assert tg.in_cc(vet), \
            "a Fresh HQ is never stopped by ZOC (soft) - trace passes [7.32]"
        park(z)

        base = take("roman_line", 1)[0]
        c1, c2 = take("velitae", 2)
        vet["hex"] = L[10]
        base["hex"] = c1["hex"] = c2["hex"] = L[5]
        c1["up"] = c2["up"] = True
        tg.s["esc"].append({"hex": L[5], "base": base["pid"], "used": []})
        mph("rom_move")
        assert not tg.in_cc(vet), \
            "an Escalade hex filled to capacity blocks the trace [5.2/8.7]"
        park(c2)
        mph("rom_move")
        assert tg.in_cc(vet), "below capacity the HQ may pass through [8.7]"
        tg.s["esc"] = []
        park(base, c1, vet)
        gal["hex"] = None

        jz = take("zealot", 1)[0]
        jl2 = next(u for u in U.values() if u["type"] == "judaean_leader"
                   and u["hex"] is None)
        ram = take("ram", 1)[0]
        jl2["hex"], jz["hex"], ram["hex"] = L[0], L[10], L[5]
        mph("jud_move")
        assert tg.in_cc(jz), \
            "an unescorted enemy Siege Engine cannot prevent the trace - " \
            "the HQ could enter (and wreck) its hex [5.2/11.4]"
        esc = take("roman_line", 1)[0]
        esc["hex"] = L[5]
        mph("jud_move")
        assert not tg.in_cc(jz), "an escorted engine hex stays closed [8.11]"
        park(jz, jl2, ram, esc)
        print("cc trace: exact-tracing doors - Testudo join-only, Panicked "
              "stop, 16.51 Disrupted-HQ ZOC bar (Fresh HQ soft-passes), "
              "Escalade capacity, unescorted-enemy-SE passage OK "
              "[5.2/6.61/17.21/16.51/8.7/11.4]")

        # ---- 5.1: CC is a phase-start determination, both directions
        z2 = take("zealot", 1)[0]
        gal["hex"], vet["hex"], z2["hex"] = L[0], L[1], L[3]
        mph("rom_move")
        assert tg.in_cc(vet)
        gal["hex"] = None
        assert tg.in_cc(vet), \
            "begins the phase in CC = not penalized this phase [5.1]"
        ok_move(tg, "Rom", vet["pid"], [K[1], K[2]])
        submit_ok(tg, "Rom", {"type": "end_phase"})
        assert tg.s["phase"] == "rom_melee" and not tg.in_cc(vet), \
            "the next phase re-determines CC [5.1]"
        park(vet)

        vet2 = take("roman_veteran", 1)[0]
        vet2["hex"] = L[1]
        mph("rom_move")
        assert not tg.in_cc(vet2)
        gal["hex"] = L[0]
        assert not tg.in_cc(vet2), \
            "CC gained mid-phase waits for the next determination [5.1]"
        no_move(tg, "Rom", vet2["pid"], [K[1], K[2]], "[5.3]")
        submit_ok(tg, "Rom", {"type": "end_phase"})
        assert tg.in_cc(vet2), "the new phase sees the HQ [5.1]"
        park(vet2, z2)
        gal["hex"] = None

        print("cc trace: 5.1 phase-start snapshot - begins-in-CC protected "
              "through a real ZOC-entry move, mid-phase CC gain denied "
              "([5.3] refusal witnessed), both re-determined at the next "
              "phase OK [5.1/5.3]")
        print("cc trace checks: PASS (B18 5.1/5.2)")
    finally:
        shutil.rmtree(live, ignore_errors=True)


def mph_door_checks(g):
    live = tempfile.mkdtemp(prefix="soj_mdoor_")
    try:
        tg = soj.SoJGame(g, os.path.join(HERE, "scenario_gallus.json"),
                         live, seed=37)
        U = tg.s["units"]
        tg.s["deploy_done"] = {"Jud": True, "Rom": True}
        tg.s["turn"] = 1
        N = tg.hex_name
        gal = next(u for u in U.values() if u["type"] == "gallus")

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

        def pocket(avoid=()):
            return next(h for h in sorted(tg.hex_t0)
                        if clear1(h)
                        and all(clear1(n) for n in tg._nb(h))
                        and all(clear1(m) for n in tg._nb(h)
                                for m in tg._nb(n))
                        and all(tg._dist(h, a) > 6 for a in avoid))

        def mph(phase):
            tg.s["phase"] = phase
            tg._mph_bookkeeping()

        def park(*us):
            for x in us:
                x["hex"] = None
                x["state"] = "fresh"
                x.pop("up", None)

        # ---- 8.2 movement finality [M.21/N11]
        h0 = pocket()
        h1 = pocket(avoid=(h0,))
        v1, v2 = take("roman_veteran", 2)
        v1["hex"], v2["hex"] = h0, h1
        mph("rom_move")
        a0 = next(n for n in tg._nb(h0) if clear1(n))
        ok_move(tg, "Rom", v1["pid"], [N[h0], N[a0]])
        b0 = next(n for n in tg._nb(a0) if clear1(n) and n != h0)
        ok_move(tg, "Rom", v1["pid"], [N[a0], N[b0]])
        a1 = next(n for n in tg._nb(h1) if clear1(n))
        ok_move(tg, "Rom", v2["pid"], [N[h1], N[a1]])
        no_move(tg, "Rom", v1["pid"], [N[b0], N[a0]], "[8.2]")
        b1 = next(n for n in tg._nb(a1) if clear1(n) and n != h1)
        ok_move(tg, "Rom", v2["pid"], [N[a1], N[b1]])
        mph("rom_move")
        ok_move(tg, "Rom", v1["pid"], [N[b0], N[a0]])
        print("mph doors: a unit moves in multiple legs until another "
              "begins, then its movement is completed; cleared at the "
              "phase boundary OK [8.2]")
        park(v1, v2)

        # ---- 7.321 free soft-ZOC first-step exit [M.10/N6]
        h2 = pocket(avoid=(h0, h1))
        cav = take("roman_cavalry", 1)[0]
        z1 = take("zealot", 1)[0]
        cav["hex"] = h2
        zn = next(n for n in tg._nb(h2) if clear1(n))
        z1["hex"] = zn
        gal["hex"] = next(n for n in tg._nb(h2)
                          if clear1(n) and n not in tg._nb(zn))
        mph("rom_move")
        zoc = tg._zoc_map("Jud")
        assert h2 in zoc
        free = next(n for n in tg._nb(h2)
                    if clear1(n) and n not in zoc)
        both = next(n for n in tg._nb(h2)
                    if n in tg._nb(zn) and clear1(n))
        v = tg._move_verdict("Rom", cav, [h2, free])
        assert v["legal"] and abs(v["spent"] - 1.0) < 1e-9, v
        v = tg._move_verdict("Rom", cav, [h2, both])
        assert v["legal"] and abs(v["spent"] - 4.0) < 1e-9, v
        cav["hex"] = free
        mph("rom_move")
        out2 = next(n for n in tg._nb(h2)
                    if clear1(n) and n not in zoc and n != free)
        v = tg._move_verdict("Rom", cav, [free, h2, out2])
        assert v["legal"] and abs(v["spent"] - 5.0) < 1e-9, v
        print("mph doors: soft-ZOC exit is FREE when the first hex entered "
              "is ZOC-free; +3 ZOC-to-ZOC and +3 on later exits stand "
              "OK [7.321/7.32]")
        park(cav, z1, gal)

        # ---- 8.13 fully-stacked carve-out [M.20/N20]
        h3 = pocket(avoid=(h0, h1, h2))
        m1, m2, m3 = take("judaean_militia", 3)
        jh1 = take("judaean_leader", 2)
        m1["hex"] = m2["hex"] = h3
        s3 = next(n for n in tg._nb(h3) if clear1(n))
        t3 = next(n for n in tg._nb(h3) if clear1(n) and n != s3)
        jh1[0]["hex"] = s3
        mph("jud_move")
        assert tg._stack_limit(h3, "Jud") == 2
        v = tg._move_verdict("Jud", jh1[0], [s3, h3, t3])
        assert v["legal"] and abs(v["spent"] - 2.0) < 1e-9, v
        m3["hex"] = s3
        v = tg._move_verdict("Jud", m3, [s3, h3, t3])
        assert v["legal"] and abs(v["spent"] - 3.0) < 1e-9, v
        jh1[1]["hex"] = h3
        v = tg._move_verdict("Jud", jh1[0], [s3, h3, t3])
        assert v["legal"] and abs(v["spent"] - 3.0) < 1e-9, v
        print("mph doors: a combat-full hex is not fully stacked to an "
              "entering HQ (no transit doubling) until its own slot is "
              "taken; other entrants still pay double OK [8.13]")
        park(m1, m2, m3, *jh1)

        # ---- 6.3 one-Cauldron doors
        fort = next(h for h in sorted(tg.hex_t0)
                    if tg.hex_t0[h] == "fortress" and h in tg.playable
                    and not tg._occupants(h)
                    and any(tg.hex_t0[n] in soj.ELEVATED
                            and n in tg.playable and not tg._occupants(n)
                            for n in tg._nb(h)))
        e1 = next(n for n in tg._nb(fort)
                  if tg.hex_t0[n] in soj.ELEVATED and n in tg.playable
                  and not tg._occupants(n))
        c1, c2 = take("cauldron", 2)
        c1["hex"], c2["hex"] = fort, e1
        mph("jud_move")
        no_move(tg, "Jud", c2["pid"], [N[e1], N[fort]],
                "not already containing a Cauldron")
        bad = tg._stack_check(fort, "Jud", c2)
        assert bad and "only one is a Cauldron" in bad, bad
        print("mph doors: a Cauldron may not enter (nor stack in) a "
              "Fortress already containing a Cauldron OK [6.3]")
        park(c1, c2)

        # ---- N16: Cavalry/Artillery/Ram pass through controlled Gates
        gate = e_in = e_out = None
        for G in sorted(tg.hex_t0):
            if tg.hex_t0[G] not in soj.GATES or G not in tg.playable:
                continue
            gr = [x for p in tg.entrances if G in p
                  for x in p if x != G and x in tg.playable
                  and tg.hex_t0[x] == "clear" and not tg._occupants(x)]
            if len(gr) >= 2:
                gate, e_in, e_out = G, gr[0], gr[1]
                break
        assert gate, "no gate with two clear entrance-side ground hexes"
        tg.s["control"][gate] = "Rom"
        cav2 = take("roman_cavalry", 1)[0]
        cav2["hex"] = e_in
        mph("rom_move")
        no_move(tg, "Rom", cav2["pid"], [N[e_in], N[gate]],
                "may not stop there")
        ok_move(tg, "Rom", cav2["pid"], [N[e_in], N[gate], N[e_out]])
        assert cav2["hex"] == e_out
        park(cav2)
        tg.s["control"][gate] = "Jud"
        cav3 = take("roman_cavalry", 1)[0]
        cav3["hex"] = e_in
        mph("rom_move")
        no_move(tg, "Rom", cav3["pid"], [N[e_in], N[gate], N[e_out]],
                "[6.2]")
        park(cav3)
        tg.s["control"][gate] = "Rom"
        art = take("roman_ballista", 1)[0]
        art["hex"], art["state"] = e_in, "disrupted"
        mph("rom_move")
        no_move(tg, "Rom", art["pid"], [N[e_in], N[gate]],
                "may not stop there")
        ok_move(tg, "Rom", art["pid"], [N[e_in], N[gate], N[e_out]])
        park(art)
        ram = take("ram", 1)[0]
        cr1, cr2 = take("roman_veteran", 2)
        ram["hex"] = cr1["hex"] = cr2["hex"] = e_in
        vg = take("roman_veteran", 1)[0]
        vg["hex"] = gate
        mph("rom_move")
        crew = sorted([cr1["pid"], cr2["pid"]])
        r = {"type": "move", "pid": ram["pid"], "crew": crew}
        submit_no(tg, "Rom", dict(r, path=[N[e_in], N[gate]]),
                  "may not stop there")
        submit_ok(tg, "Rom", dict(r, path=[N[e_in], N[gate], N[e_out]]))
        assert ram["hex"] == e_out and cr1["hex"] == e_out
        park(ram, cr1, cr2)
        vg["hex"] = None
        twr = take("tower", 1)[0]
        cr3, cr4 = take("roman_veteran", 2)
        twr["hex"] = cr3["hex"] = cr4["hex"] = e_in
        mph("rom_move")
        submit_no(tg, "Rom", {"type": "move", "pid": twr["pid"],
                              "crew": sorted([cr3["pid"], cr4["pid"]]),
                              "path": [N[e_in], N[gate], N[e_out]]},
                  "only a Ram may pass through")
        park(twr, cr3, cr4)
        vg["hex"], vg["state"] = gate, "panicked"
        cav4 = take("roman_cavalry", 1)[0]
        cav4["hex"] = e_in
        mph("rom_move")
        no_move(tg, "Rom", cav4["pid"], [N[e_in], N[gate], N[e_out]],
                "Panicked")
        park(cav4, vg)
        print("mph doors: Cavalry/flipped-Artillery/crewed Ram pass through "
              "a Roman Gate via its Entrance hexsides but may not stop; "
              "uncontrolled Gate, Tower, and a Panicked occupant refuse "
              "OK [6.2/6.4/8.4/M.29]")

        # ---- 6.1/6.2/6.3 entry prohibitions bind on ENTRY, not stacking
        h5 = pocket(avoid=(h0, h1, h2, h3))
        vx = take("roman_veteran", 1)[0]
        cv = take("roman_cavalry", 1)[0]
        s5 = next(n for n in tg._nb(h5) if clear1(n))
        t5 = next(n for n in tg._nb(h5)
                  if clear1(n) and n != s5 and n in tg._nb(s5))
        vx["hex"] = h5
        cv["hex"] = s5
        mph("rom_move")
        v = tg._move_verdict("Rom", cv, [s5, h5, t5])
        assert not v["legal"] and any("6.2" in r for r in v["reasons"]), v
        gal["hex"] = h5
        vx["hex"] = t5
        v = tg._move_verdict("Rom", cv, [s5, h5])
        assert v["legal"], v
        v = tg._move_verdict("Rom", vx, [t5, s5])
        assert not v["legal"] and any("6.1" in r for r in v["reasons"]), v
        v = tg._move_verdict("Rom", gal, [h5, s5])
        assert v["legal"], v
        cv2 = take("roman_cavalry", 1)[0]
        cv2["hex"] = t5
        vx["hex"] = None
        v = tg._move_verdict("Rom", cv2, [t5, s5])
        assert v["legal"], v
        a1_, a2_ = take("roman_catapult", 2)
        a1_["hex"], a1_["state"] = h5, "disrupted"
        a2_["hex"], a2_["state"] = t5, "disrupted"
        gal["hex"] = None
        park(cv, cv2)
        mph("rom_move")
        v = tg._move_verdict("Rom", a2_, [t5, h5, s5])
        assert not v["legal"] and any("6.3" in r for r in v["reasons"]), v
        cv["hex"] = h5
        a1_["hex"] = None
        v = tg._move_verdict("Rom", a2_, [t5, h5, s5])
        assert not v["legal"] and any("6.3" in r for r in v["reasons"]), v
        cv["hex"] = None
        v = tg._move_verdict("Rom", a2_, [t5, h5, s5])
        assert v["legal"], v
        print("mph doors: 6.1/6.2/6.3 are ENTRY prohibitions - Cavalry "
              "into a non-HQ hex, Infantry into a Cavalry hex, Artillery "
              "into an Artillery/Cavalry hex all refused mid-path; "
              "HQ-with-Cavalry and Cavalry-with-Cavalry legal OK")
        print("mph door checks: PASS (Bite 21 N6/N11/N16/N20 + 6.x entry "
              "doors)")
    finally:
        shutil.rmtree(live, ignore_errors=True)


def offboard_exit_checks(g):
    live = tempfile.mkdtemp(prefix="soj_off_")
    try:
        tg = soj.SoJGame(g, os.path.join(HERE, "scenario_gallus.json"),
                         live, seed=41)
        U = tg.s["units"]
        tg.s["deploy_done"] = {"Jud": True, "Rom": True}
        tg.s["turn"] = 1
        N = tg.hex_name
        gal = next(u for u in U.values() if u["type"] == "gallus")

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

        def edge1(h):
            return (h in tg.playable and h in tg.outside
                    and tg.hex_t0[h] == "clear"
                    and len(tg._nb(h)) < 6 and not tg._occupants(h))

        def epick(avoid=()):
            return next(h for h in sorted(tg.hex_t0)
                        if edge1(h) and any(clear1(n) for n in tg._nb(h))
                        and all(tg._dist(h, a) > 6 for a in avoid))

        def pocket(avoid=()):
            return next(h for h in sorted(tg.hex_t0)
                        if clear1(h)
                        and all(clear1(n) for n in tg._nb(h))
                        and all(tg._dist(h, a) > 6 for a in avoid))

        def mph(phase):
            tg.s["phase"] = phase
            tg._mph_bookkeeping()

        def park(*us):
            for x in us:
                x["hex"] = None
                x["state"] = "fresh"
                x.pop("mv", None)

        # ---- exit as-if-Clear: cost, removal, no-return, control flip
        e0 = epick()
        s0 = next(n for n in tg._nb(e0) if clear1(n))
        vA = take("roman_veteran", 1)[0]
        vA["hex"] = s0
        tg.s["phase"] = "rom_fire"
        r = tg.submit("Rom", {"type": "exit", "pid": vA["pid"],
                              "path": [N[s0], N[e0]]})
        assert not r["verdict"]["legal"] and \
            "Movement Phase" in " ".join(r["verdict"]["reasons"])
        mph("rom_move")
        r = submit_ok(tg, "Rom", {"type": "exit", "pid": vA["pid"],
                                  "path": [N[s0], N[e0]]})
        assert abs(r["verdict"]["spent"] - 2.0) < 1e-9, r["verdict"]
        assert vA["hex"] is None and vA["state"] == "exited"
        assert vA["pid"] in tg.s["escaped"]
        assert tg.s["control"][e0] == "Rom"
        submit_no(tg, "Rom", {"type": "move", "pid": vA["pid"],
                              "path": [N[e0], N[s0]]}, "not on the map")
        vC = take("roman_veteran", 1)[0]
        vC["hex"] = e0
        mph("rom_move")
        vC["mv"] = 7.5
        submit_no(tg, "Rom", {"type": "exit", "pid": vC["pid"],
                              "path": [N[e0]]}, "allowance exceeded")
        vC.pop("mv")
        submit_no(tg, "Rom", {"type": "exit", "pid": vC["pid"],
                              "path": [N[e0], N[s0]]}, "mapsheet-edge")
        submit_ok(tg, "Rom", {"type": "exit", "pid": vC["pid"],
                              "path": [N[e0]]})
        print("offboard exit: leaves as if entering a Clear hex (1 MF over "
              "TEC path), unit removed from play and barred from return, "
              "hex control flips en route; non-edge hexes and exhausted "
              "allowance refused OK [8.14/15.5/18.3]")

        # ---- 8.2 finality ledger includes exits
        p0 = pocket(avoid=(e0,))
        vB = take("roman_veteran", 1)[0]
        vB["hex"] = p0
        vE = take("roman_veteran", 1)[0]
        vE["hex"] = e0
        mph("rom_move")
        a0 = next(n for n in tg._nb(p0) if clear1(n))
        ok_move(tg, "Rom", vB["pid"], [N[p0], N[a0]])
        submit_ok(tg, "Rom", {"type": "exit", "pid": vE["pid"],
                              "path": [N[e0]]})
        no_move(tg, "Rom", vB["pid"], [N[a0], N[p0]], "[8.2]")
        park(vB)
        print("offboard exit: an exit enters the 8.2 finality ledger - the "
              "previous mover's movement is completed OK [8.2/8.14]")

        # ---- Judaean arm: fresh may leave forever; routed must head for
        # the Temple Quarter, not the map edge
        eJ = epick(avoid=(e0, p0))
        z1, z2 = take("zealot", 2)
        z1["hex"] = eJ
        mph("jud_move")
        submit_ok(tg, "Jud", {"type": "exit", "pid": z1["pid"],
                              "path": [N[eJ]]})
        assert z1["state"] == "exited" and z1["pid"] in tg.s["escaped"]
        z2["hex"], z2["state"] = eJ, "routed"
        mph("jud_move")
        r = tg.submit("Jud", {"type": "exit", "pid": z2["pid"],
                              "path": [N[eJ]]})
        assert not r["verdict"]["legal"] and \
            "Temple Quarter" in " ".join(r["verdict"]["reasons"])
        park(z2)
        vR = take("roman_veteran", 1)[0]
        vR["hex"], vR["state"] = e0, "routed"
        mph("rom_move")
        submit_ok(tg, "Rom", {"type": "exit", "pid": vR["pid"],
                              "path": [N[e0]]})
        assert vR["state"] == "exited"
        print("offboard exit: Judaean escape legal for Fresh units and "
              "refused for Routed (Refuge = Temple Quarter); a Routed Roman "
              "may leave - his Refuge is the board edge OK "
              "[8.14/15.3/15.4/15.5/18.92]")

        # ---- ZOC arms on the off-map step
        e4 = zn = x0 = None
        for h in sorted(tg.hex_t0):
            if not (edge1(h)
                    and all(tg._dist(h, a) > 6 for a in (e0, p0, eJ))):
                continue
            nbs = [n for n in tg._nb(h) if clear1(n)]
            pair = next(((a, b) for a in nbs for b in nbs
                         if b != a and b not in tg._nb(a)), None)
            if pair:
                e4, (zn, x0) = h, pair
                break
        assert e4, "no edge hex with a non-adjacent clear neighbor pair"
        z3 = take("zealot", 1)[0]
        z3["hex"] = zn
        cav = take("roman_cavalry", 1)[0]
        cav["hex"] = e4
        gal["hex"] = next(h for h in sorted(tg.hex_t0)
                          if clear1(h) and 2 <= tg._dist(h, x0) <= 5
                          and h not in tg._nb(zn) and h != e4)
        mph("rom_move")
        zoc = tg._zoc_map("Jud")
        assert e4 in zoc and x0 not in zoc
        v = tg._move_verdict("Rom", cav, [e4, soj.OFF])
        assert v["legal"] and abs(v["spent"] - 1.0) < 1e-9, v
        cav["hex"] = x0
        mph("rom_move")
        v = tg._move_verdict("Rom", cav, [x0, e4, soj.OFF])
        assert v["legal"] and abs(v["spent"] - 5.0) < 1e-9, v
        vH = take("roman_veteran", 1)[0]
        vH["hex"] = e4
        mph("rom_move")
        v = tg._move_verdict("Rom", vH, [e4, soj.OFF])
        assert v["legal"] and abs(v["spent"] - 1.0) < 1e-9, v
        park(cav, vH, z3, gal)
        print("offboard exit: leaving a ZOC straight off-map is a ZOC-free "
              "first hex (free soft exit, hard exit legal); +3 soft "
              "surcharge stands on a later-leg exit OK [7.31/7.311/7.321]")

        # ---- class doors: Cauldron never; a crewed Ram leaves with its crew
        cd = take("cauldron", 1)[0]
        cd["hex"] = e4
        mph("jud_move")
        v = tg._move_verdict("Jud", cd, [e4, soj.OFF])
        assert not v["legal"] and any("8.5" in x for x in v["reasons"]), v
        park(cd)
        rm = take("ram", 1)[0]
        c1, c2 = take("roman_veteran", 2)
        rm["hex"] = c1["hex"] = c2["hex"] = e4
        mph("rom_move")
        r = submit_ok(tg, "Rom", {"type": "exit", "pid": rm["pid"],
                                  "crew": sorted([c1["pid"], c2["pid"]]),
                                  "path": [N[e4]]})
        assert sorted(r["result"]["exited"]) == \
            sorted([rm["pid"], c1["pid"], c2["pid"]])
        assert all(x["state"] == "exited" and x["pid"] in tg.s["escaped"]
                   for x in (rm, c1, c2))
        assert not tg.s["markers"]
        print("offboard exit: Cauldrons refused (Elevated-only movers); a "
              "crewed Ram exits as the locked stack, crew removed with it, "
              "no Wreck marker - the engine left alive OK [8.5/8.3/8.14]")

        # ---- Testudo formation exits whole
        e6 = epick(avoid=(e0, p0, eJ, e4))
        t1, t2, t3 = take("roman_veteran", 3)
        t1["hex"] = t2["hex"] = t3["hex"] = e6
        tg.s["testudo"].append({"hex": e6, "mv": 0.0,
                                "legion": t1.get("cohort")})
        mph("rom_move")
        r = submit_ok(tg, "Rom", {"type": "exit", "pid": t1["pid"],
                                  "testudo": True, "path": [N[e6]]})
        assert sorted(r["result"]["exited"]) == \
            sorted([t1["pid"], t2["pid"], t3["pid"]])
        assert tg._tst_at(e6) is None
        assert all(x["state"] == "exited" for x in (t1, t2, t3))
        print("offboard exit: an intact Testudo marches off whole - "
              "members removed, formation dissolved OK [8.14/8.8]")
        print("offboard exit checks: PASS (Bite 24 N12 - M.33 whole)")
    finally:
        shutil.rmtree(live, ignore_errors=True)


def north_wall_strongpoint_checks(g):
    """5-bastion evidence pass (2026-08-13): the session-1 terrain
    auto-classifier typed five North Wall strongpoints as plain
    'north_wall'. Re-read from the printed control-map rings + tower/fort
    structures (ring-fraction census cross-validated vs all 22 shipped
    Bastions / 10 Forts): G45/G47/H48/J37 are Bastions, I50 is a Fort;
    the four bleed-only marginals G48/H47/I48/NN17 stay plain wall. The
    fix raises their breach defense (north_wall 6 -> Bastion 10 / Fort 12
    [12.1/game card]), enrols them in STRONGPOINTS, and (card SR1: each
    Bastion and Fortress of the North Wall O50..QQ29) adds them to the
    minimum-force garrison, closing P0.2's under-enforcement."""
    live = tempfile.mkdtemp(prefix="soj_nws_")
    try:
        tg = soj.SoJGame(g, os.path.join(HERE, "scenario_gallus.json"),
                         live, seed=53)
        BAST = ["G45", "G47", "H48", "J37"]
        FORT = ["I50"]
        BLEED = ["G48", "H47", "I48", "NN17"]
        for n in BAST:
            h = tg.name_hex[n]
            assert tg.hex_t0[h] == "bastion", (n, tg.hex_t0[h])
            assert tg.hex_t(h) in soj.STRONGPOINTS
            assert tg._breach_def(h) == 10, (n, tg._breach_def(h))
        for n in FORT:
            h = tg.name_hex[n]
            assert tg.hex_t0[h] == "fort", (n, tg.hex_t0[h])
            assert tg.hex_t(h) in soj.STRONGPOINTS
            assert tg._breach_def(h) == 12, (n, tg._breach_def(h))
        for n in BLEED:
            h = tg.name_hex[n]
            assert tg.hex_t0[h] == "north_wall", (n, tg.hex_t0[h])
            assert tg._breach_def(h) == 6, (n, tg._breach_def(h))
        mf = {tg.hex_name[h] for h in tg.min_force}
        assert set(BAST + FORT) <= mf, sorted(set(BAST + FORT) - mf)
        assert not (set(BLEED) & mf), sorted(set(BLEED) & mf)
        assert len(tg.min_force) == 26, len(tg.min_force)
        print("north-wall strongpoints: G45/G47/H48/J37=Bastion(def10), "
              "I50=Fort(def12) re-typed + garrisoned; 4 bleed marginals "
              "stay plain wall; min-force = 26 [card SR1 / 12.1]")
    finally:
        shutil.rmtree(live, ignore_errors=True)


def stair_exclusion_checks(g):
    """R4 declared ruling (Bruce 2026-08-12): the 20 doubtful session-1
    staircase hexsides are EXCLUDED (source_defects
    'staircase-doubtful-hexsides'); the 28 art-confirmed sides stand.
    Pin the exclusion set, prove the loud consequence (a stair-less fort
    refuses ground entry and ground melee with the printed-law citation),
    and prove a confirmed staircase still opens its wall."""
    EXCLUDED = [
        "0743|0844", "0746|0846", "0746|0847", "1355|1356", "1356|1456",
        "3950|4051", "1556|1557", "4138|4238", "4254|4255", "2253|2353",
        "3034|3035", "3544|3545", "3635|3636", "1256|1355", "3749|3849",
        "3951|4052", "1557|1657", "4247|4346", "1255|1256", "3952|3953",
        "3949|4050",
    ]
    live = tempfile.mkdtemp(prefix="soj_stex_")
    try:
        tg = soj.SoJGame(g, os.path.join(HERE, "scenario_gallus.json"),
                         live, seed=41)
        U = tg.s["units"]
        tg.s["deploy_done"] = {"Jud": True, "Rom": True}
        tg.s["turn"] = 1
        N = tg.hex_name
        assert len(tg.stairs) == 28, len(tg.stairs)
        for k in EXCLUDED:
            assert tuple(sorted(k.split("|"))) not in tg.stairs, k
        print("stair exclusion: 21 doubtful hexsides absent (20 by the R4 "
              "ruling + MM30's with its typing fix), 28 art-confirmed "
              "staircases stand OK [8.93/11.11; source_defects "
              "staircase-doubtful-hexsides]")

        g43 = tg.name_hex["G43"]
        h42 = tg.name_hex["H42"]
        vet = next(u for u in U.values() if u["type"] == "roman_veteran"
                   and u["hex"] is None)
        vet["hex"] = h42
        tg.s["phase"] = "rom_move"
        tg._mph_bookkeeping()
        r = tg.submit("Rom", {"type": "move", "pid": vet["pid"],
                              "path": [N[h42], N[g43]]})
        assert not r["verdict"]["legal"] and \
            "Staircase" in " ".join(r["verdict"]["reasons"])
        zea = next(u for u in U.values() if u["type"] == "zealot"
                   and u["hex"] is None)
        zea["hex"], zea["state"] = g43, "fresh"
        mult, why = tg._melee_approach(vet, g43)
        assert mult is None and "Staircase" in why, (mult, why)
        vet["hex"], zea["hex"] = None, None
        print("stair exclusion: the stair-less fort G43 refuses ground "
              "entry and ground melee with the 8.91-8.93 citation - the "
              "excluded-stair error mode is LOUD OK [8.93/11.11]")
    finally:
        shutil.rmtree(live, ignore_errors=True)


def garrison_checks(g):
    """R1 declared ruling (Bruce 2026-08-12): Roman entry of Garrison Areas
    is barred on the nine battlefield-reachable perimeter hexes of the three
    18.4 areas (see source_defects 'gallus-garrison-extent'). Battery: the
    data list is pinned; every hex refuses Roman movement with the garrison
    verdict; Judaean entry through both Giora doors stays legal; the
    advance-into-vacated-gate carve-out no longer lifts the bar; 11.1 melee
    eligibility inherits it; missile fire INTO a garrison hex stays legal;
    the end-of-melee climb-up offer filters garrison destinations."""
    live = tempfile.mkdtemp(prefix="soj_garr_")
    try:
        tg = soj.SoJGame(g, os.path.join(HERE, "scenario_gallus.json"),
                         live, seed=41)
        U = tg.s["units"]
        tg.s["deploy_done"] = {"Jud": True, "Rom": True}
        tg.s["turn"] = 1
        N = tg.hex_name
        RULING = ["P50", "Q49", "MM31", "MM32", "MM33",
                  "NN33", "OO33", "PP33", "QQ32"]
        assert sorted(N[h] for h in tg.rom_prohibited) == sorted(RULING), \
            sorted(N[h] for h in tg.rom_prohibited)
        assert tg.hex_t0[tg.name_hex["MM30"]] == "clear" and \
            tg.name_hex["MM30"] in tg.new_city
        print("garrison: 9-hex declared ruling list pinned; MM30 typing "
              "defect fixed (clear, New City) OK [card/18.4/18.3]")

        def take(t, n):
            out = [u for u in U.values()
                   if u["type"] == t and u["hex"] is None
                   and u["state"] == "fresh"][:n]
            assert len(out) == n, f"need {n} {t}"
            return out

        def mph(phase):
            tg.s["phase"] = phase
            tg._mph_bookkeeping()

        def park(*us):
            for x in us:
                x["hex"] = None
                x["state"] = "fresh"
                x.pop("mv", None)
                x.pop("up", None)

        # ---- A: Roman movement refused into every ruled hex
        vet = take("roman_veteran", 1)[0]
        for name in RULING:
            tgt = tg.name_hex[name]
            adj = next(n for n in tg._nb(tgt)
                       if n in tg.playable and not tg._occupants(n))
            vet["hex"] = adj
            vet.pop("mv", None)
            mph("rom_move")
            no_move(tg, "Rom", vet["pid"], [N[adj], name], "Garrison")
        park(vet)
        print("garrison: Roman movement refused into all 9 perimeter hexes "
              "with the garrison verdict OK [card]")

        # ---- B: Judaean entry through both Giora doors; deploy zone keeps
        # the garrison walls
        zea = take("zealot", 1)[0]
        for gate, ent in (("OO33", "OO32"), ("Q49", "Q48")):
            zea["hex"] = tg.name_hex[ent]
            zea.pop("mv", None)
            mph("jud_move")
            ok_move(tg, "Jud", zea["pid"], [ent, gate])
            assert zea["hex"] == tg.name_hex[gate]
            park(zea)
        assert all(tg.name_hex[n] in tg.jud_zone
                   for n in ("P50", "QQ32", "MM31", "OO33"))
        print("garrison: Judaean entry legal through both Giora doors "
              "(OO33 Tadi, Q49); garrison walls stay in the Judaean "
              "deployment zone OK [18.4]")

        # ---- C: the advance-into-vacated-gate carve-out no longer lifts
        # the bar (the pre-fix hole: entrance-hexside gate advance flipped a
        # refused entry to 1 MF flat)
        q49 = tg.name_hex["Q49"]
        q48 = tg.name_hex["Q48"]
        vet["hex"] = q48
        tg.s["phase"] = "rom_melee"
        tg.s["pending"] = {"kind": "advance", "by": "Rom",
                           "pids": [vet["pid"]], "hex": q49, "xe": 0}
        submit_no(tg, "Rom", {"type": "resolve_advance",
                              "pids": [vet["pid"]]}, "Garrison")
        submit_ok(tg, "Rom", {"type": "resolve_advance", "pids": []})
        assert tg.s["pending"] is None
        print("garrison: advance into a vacated garrison Gate across its "
              "Entrance hexside refused; decline still clean OK "
              "[11.86/11.9/card]")

        # ---- D: 11.1 melee eligibility inherits the bar (the reading the
        # two printed example hexes have always had)
        zea["hex"], zea["state"] = q49, "fresh"
        vet["hex"] = q48
        mult, why = tg._melee_approach(vet, q49)
        assert mult is None and "Garrison" in why, (mult, why)
        print("garrison: Roman melee against an occupied garrison hex "
              "ineligible via 11.1 could-enter test OK [11.1/card]")

        # ---- E: missile fire INTO a garrison hex stays legal (entry is
        # barred, bombardment is not)
        park(vet)
        syr = take("syrian_archers", 1)[0]
        syr["hex"] = q48
        cmdR = next(u for u in U.values() if u["type"] == "gallus")
        cmdR["hex"], cmdR["state"] = q48, "fresh"
        tg.s["phase"], tg.s["seg"] = "rom_fire", "Rom"
        tg.s["fired"], tg.s["fired_hexes"] = [], []
        tg.s["pending"] = None
        tg._cc_snapshot()
        r = tg.propose("Rom", {"type": "fire", "firers": [syr["pid"]],
                               "target": "Q49"})
        assert r["legal"], r
        park(zea, syr, cmdR)
        print("garrison: missile fire into a garrison hex remains legal "
              "OK [9.x/card]")

        # ---- F: end-of-melee climb-up offer filters garrison Elevated
        # (MM30 ground base: MM31 = garrison fortress, LL30 = battlefield
        # gate - only the battlefield hex may be offered)
        mm30 = tg.name_hex["MM30"]
        base, climber = take("roman_veteran", 2)
        base["hex"] = mm30
        climber["hex"], climber["up"] = mm30, True
        tg.s["esc"].append({"hex": mm30, "base": base["pid"], "used": []})
        opts = tg._esc_up_opts()
        assert climber["pid"] in opts, opts
        assert "MM31" not in opts[climber["pid"]] and \
            "LL30" in opts[climber["pid"]], opts
        tg.s["esc"] = [e for e in tg.s["esc"] if e["hex"] != mm30]
        park(base, climber)
        print("garrison: climb-up offer excludes garrison Elevated hexes, "
              "battlefield Elevated still offered OK [11.6/card]")
        print("garrison checks: PASS (Bite 25 R1 - P0.4 whole, declared "
              "ruling, module-author review pending)")
    finally:
        shutil.rmtree(live, ignore_errors=True)


if __name__ == "__main__":
    main()
