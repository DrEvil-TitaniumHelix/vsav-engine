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


if __name__ == "__main__":
    main()
