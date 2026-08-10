"""validate_combat.py - SoJ combat tables + resolution engine, worked cases.

Spec #12: enforcement ships only where validated. This validator holds the
transcribed tables and the resolution engine to the rulebook's own worked
examples and the official Q&A:

  TABLES
  - Melee 2-1 column, adjusted die 7 = "DE"  [11.82 printed example]
  - both tables' diagonal structure (each row shifts one column)
  - Missile thresholds are row-increment multiples (game card structure)
  - Breach table rows + defenses (North Wall 6 ... Fortress 15) [12.1/card]

  ENGINE
  - odds rounding in defender's favor: 16v9=1-1, 14v6=2-1, 6v8=1-2 [11.81]
  - extreme odds: 10-1 -> 7-1 col +3 drm; 1-6 -> 1-4 col -2 drm [11.83]
  - missile attack multiples: 24 AF vs Testudo row = col 8 + 1 drm;
    45 AF vs Wall/Ram row = col 8 + 2 drm [13.4 printed examples]
  - gate-driven end-to-end: Roman artillery fire (LOF, concentration,
    once-per-hex), ram breach attacks accumulating damage until the North
    Wall breaches (occupants eliminated [12.2], hex becomes a Breach),
    assault through the breach, melee with defender-choice pendings and
    retreat routing, the rally ladder, and a byte-exact replay of the log.
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
from validate_deploy import deploy_jud, submit_ok, submit_no  # noqa: E402


def table_checks(g):
    cd = g.spec["combat"]
    melee, missile, breach = cd["melee"], cd["missile"], cd["breach"]
    # 11.82: 2-1 column, adjusted die 7 -> DE
    cols = melee["odds_columns"]
    assert melee["rows"]["7"][cols.index("2-1")] == "DE", \
        "11.82 worked example broken"
    # diagonal structure: row r+1 equals row r shifted one column left
    keys = ["-1"] + [str(i) for i in range(0, 9)]
    for a, b in zip(keys, keys[1:]):
        assert melee["rows"][b][:-1] == melee["rows"][a][1:], (a, b)
        assert missile["result_rows"][b][:-1] == missile["result_rows"][a][1:]
    # missile thresholds: cols 2..8 are increment multiples 1..7
    for row, th in missile["target_rows"].items():
        inc = th[-1] - th[-2]
        for i in range(1, 8):
            assert th[i] == inc * i, (row, th)
    assert missile["target_rows"]["fortress"][-1] == 56
    assert missile["target_rows"]["clear_slope_ramp_escalade"][1] == 1
    # breach: strictly non-decreasing rows; defenses per the card
    for bf, row in breach["table"].items():
        assert row == sorted(row), (bf, row)
    assert breach["defenses"]["north_wall"] == 6
    assert breach["defenses"]["fortress"] == 15
    assert breach["defenses"]["bridge"] == 5
    print("table checks: PASS (incl. the 11.82 printed example)")


def engine_math(tg):
    # odds rounding [11.81] + extreme odds [11.83] via the melee resolver's
    # arithmetic, isolated
    import math
    cols = tg.melee_t["odds_columns"]

    def oddsy(att, deff):
        if att >= deff:
            r = int(att // deff)
            return cols[min(r, 7) + 2], max(0, r - 7)
        r = math.ceil(deff / att)
        return cols[max(4 - r, 0)], -max(0, r - 4)
    assert oddsy(16, 9) == ("1-1", 0), oddsy(16, 9)
    assert oddsy(14, 6) == ("2-1", 0)
    assert oddsy(6, 8) == ("1-2", 0)
    assert oddsy(70, 7) == ("7-1", 3)        # 10-1 -> +3 [11.83]
    assert oddsy(7, 42) == ("1-4", -2)       # 1-6 -> -2 [11.83]
    # missile attack multiples [13.4 printed examples]
    def missile_col(af, row):
        th = tg.missile_t["target_rows"][row]
        col = 0
        for i, t in enumerate(th):
            if t is not None and af >= t:
                col = i + 1
        inc = th[-1] - th[-2]
        return col, ((af - th[-1]) // inc if col == 8 else 0)
    assert missile_col(24, "testudo_artillery_ground") == (8, 1)
    assert missile_col(45, "wall_bridge_ram") == (8, 2)
    assert missile_col(7, "clear_slope_ramp_escalade") == (8, 0)
    print("engine math: PASS (11.81/11.83/13.4 worked examples)")


def retreat_engine_checks(g):
    """B17/N10/N23: the 14.2/14.21/15.1/15.2/15.3 retreat engine on
    engineered boards (direct state surgery on a throwaway game whose log
    is never replayed; every check still goes through submit()). The
    fully-stacked arithmetic reproduces the printed 15.3 EXAMPLE's two
    bracketed sub-cases (rulebook p.12): a Militia fills a Wall hex
    (limit 1), a lone Cauldron does not."""
    live = tempfile.mkdtemp(prefix="soj_ret_")
    try:
        tg = soj.SoJGame(g, os.path.join(HERE, "scenario_gallus.json"),
                         live, seed=99)
        U = tg.s["units"]
        tg.s["phase"], tg.s["deploy_done"] = "rom_melee", True

        def take(t, n):
            out = [u for u in U.values()
                   if u["type"] == t and u["hex"] is None][:n]
            assert len(out) == n, f"need {n} {t}"
            return out

        def place(u, h, state="fresh"):
            u["hex"], u["state"] = h, state

        def d(h):
            return tg._refuge_dist("Jud", h)

        def pend_b(pids, hex_, by="Jud", attackers=()):
            tg.s["pending"] = {"kind": "retreat", "hex": hex_,
                               "pids": [p_ for p_ in pids], "by": by,
                               "rkind": "b", "attackers": list(attackers)}

        # ---- an open two-ring clear field patch per case
        def clear1(h):
            return (h in tg.playable and tg.hex_t(h) == "clear"
                    and len(tg._nb(h)) == 6)
        field = [h for h in sorted(tg.hex_t0)
                 if clear1(h) and all(clear1(n) for n in tg._nb(h))
                 and all(clear1(m) for n in tg._nb(h) for m in tg._nb(n))]
        spots = []
        for h in field:
            if all(tg._dist(h, s) > 5 for s in spots):
                spots.append(h)
        assert len(spots) >= 6, f"only {len(spots)} isolated field spots"

        # ---- 15.3 EXAMPLE arithmetic: Wall limit 1; Cauldron doesn't count
        wall = next(h for h in sorted(tg.hex_t0)
                    if tg.hex_t(h) == "wall" and h in tg.playable)
        reg, reg2 = take("judaean_regular", 2)
        mil = take("judaean_militia", 12)
        cau = take("cauldron", 1)[0]
        place(mil[0], wall)
        assert tg._retreat_full(reg, wall, "Jud", {}), \
            "a Militia must fill a Wall hex (limit 1) [15.3 EXAMPLE]"
        mil[0]["hex"] = None
        place(cau, wall)
        assert not tg._retreat_full(reg, wall, "Jud", {}), \
            "a lone Cauldron must NOT fill the hex [15.3 EXAMPLE/6.x]"
        cau["hex"] = None

        # ---- case 1: 14.2 B retreat - free 1-2 window, forced continuation
        # while fully stacked, mandatory clean route, towards-Refuge, ladder
        h0 = spots[0]
        place(reg, h0)
        n1 = min(tg._nb(h0), key=d)
        place(mil[0], n1)
        place(mil[1], n1)              # n1 full (clear Jud limit 2)
        n2 = min((x for x in tg._nb(n1) if x != h0), key=d)
        n_away = max(tg._nb(n1), key=d)
        pend_b([reg["pid"]], h0)
        submit_no(tg, "Jud", {"type": "resolve_retreat",
                              "paths": {reg["pid"]: [h0, n1]}},
                  "end fully stacked")           # cannot stop overstacked
        pend_b([reg["pid"]], h0)
        submit_no(tg, "Jud", {"type": "resolve_retreat",
                              "paths": {reg["pid"]: [h0, n1, n_away]}},
                  "towards Refuge")              # forced step must close
        pend_b([reg["pid"]], h0)
        submit_no(tg, "Jud", {"type": "resolve_retreat",
                              "eliminate": [reg["pid"]]},
                  "survivable")                  # B17: no false eliminations
        pend_b([reg["pid"]], h0)
        r = submit_ok(tg, "Jud", {"type": "resolve_retreat",
                                  "paths": {reg["pid"]: [h0, n1, n2]}})
        ev = r["result"]["retreated"][0]
        assert reg["hex"] == n2 and reg["state"] == "disrupted", ev
        print("retreat: 14.2 window + forced continuation + ladder bump OK")

        # beyond two hexes while NOT fully stacked: refused
        h0b = spots[1]
        place(reg2, h0b)
        c1 = min(tg._nb(h0b), key=d)
        c2 = min((x for x in tg._nb(c1) if x != h0b), key=d)
        c3 = min((x for x in tg._nb(c2) if x != c1), key=d)
        pend_b([reg2["pid"]], h0b)
        submit_no(tg, "Jud", {"type": "resolve_retreat",
                              "paths": {reg2["pid"]: [h0b, c1, c2, c3]}},
                  "only while fully stacked")

        # ---- case 2: 15.1 melee-Disrupt retreat - MF budget, per-hex
        # towards-Refuge, mandatory avoidance of the fully-stacked hex
        z = take("zealot", 1)[0]       # disrupted MA 5
        rest = iter(spots[2:])

        def build_chain():
            """A 6-step all-clear unoccupied min-towards-Refuge walk."""
            for start in spots[2:]:
                ch, cur, prev = [start], start, None
                for _ in range(6):
                    cand = [x for x in tg._nb(cur)
                            if x != prev and clear1(x)
                            and not tg._occupants(x)]
                    if not cand:
                        break
                    nxt = min(cand, key=d)
                    ch.append(nxt)
                    prev, cur = cur, nxt
                if len(ch) == 7:
                    return ch
            raise AssertionError("no clear 6-step chain found")
        chain = build_chain()
        h0c = chain[0]
        rest = iter([s for s in spots[2:] if s != h0c])
        place(z, h0c, "disrupted")
        def pend_d(pids, hex_):
            tg.s["pending"] = {"kind": "retreat", "hex": hex_,
                               "pids": pids, "by": "Jud",
                               "rkind": "disrupt", "attackers": []}
        pend_d([z["pid"]], h0c)
        submit_no(tg, "Jud", {"type": "resolve_retreat",
                              "paths": {z["pid"]: chain}},
                  "movement allowance")          # 6 MF > MA 5
        away = max(tg._nb(h0c), key=d)
        pend_d([z["pid"]], h0c)
        submit_no(tg, "Jud", {"type": "resolve_retreat",
                              "paths": {z["pid"]: [h0c, away]}},
                  "towards Refuge")              # every 15.1 hex closes
        t1 = min(tg._nb(h0c), key=d)
        place(mil[2], t1)
        place(mil[3], t1)              # the towards hex is now full
        t_alt = min((x for x in tg._nb(h0c) if x != t1 and d(x) < d(h0c)),
                    key=d, default=None)
        pend_d([z["pid"]], h0c)
        submit_no(tg, "Jud", {"type": "resolve_retreat",
                              "paths": {z["pid"]: [h0c, t1, chain[2]]}},
                  "safe route exists")           # mandatory avoidance
        if t_alt is not None:
            pend_d([z["pid"]], h0c)
            submit_ok(tg, "Jud", {"type": "resolve_retreat",
                                  "paths": {z["pid"]: [h0c, t_alt]}})
            assert z["hex"] == t_alt and z["state"] == "disrupted"
        print("retreat: 15.1 MF budget + direction + safe-route OK")

        # ---- case 3: B17 - ringed unit is eliminated, never deadlocked
        h0d = next(rest)
        vets = take("roman_veteran", 3)
        z2 = take("zealot", 1)[0]
        place(z2, h0d)
        ring = sorted(tg._nb(h0d))
        opp = next(x for x in ring if x != ring[0]
                   and x not in tg._nb(ring[0])
                   and not (set(tg._nb(x)) & set(tg._nb(ring[0]))
                            & set(ring)))    # the true geometric opposite
        place(vets[0], ring[0])
        pend_b([z2["pid"]], h0d)
        submit_no(tg, "Jud", {"type": "resolve_retreat",
                              "eliminate": [z2["pid"]]},
                  "survivable")                  # half-ringed: must retreat
        place(vets[1], opp)            # two opposed HI: all 6 blocked
        probe = next(x for x in ring if x not in (ring[0], opp))
        submit_no(tg, "Jud", {"type": "resolve_retreat",
                              "paths": {z2["pid"]: [h0d, probe]}},
                  "ZOC")
        r = submit_ok(tg, "Jud", {"type": "resolve_retreat",
                                  "eliminate": [z2["pid"]]})
        assert z2["state"] == "eliminated" and z2["hex"] is None
        print("retreat: B17 ringed unit eliminated through the gate OK")

        # ---- case 4: 14.21 - one hex only; forced overstack eliminates
        h0e = next(rest)
        z3, z4 = take("judaean_regular", 2)
        place(z3, h0e)
        atk = vets[2]
        a_hex = sorted(tg._nb(h0e))[0]
        place(atk, a_hex)              # fresh HI adjacent on ground
        legal = [n for n in tg._nb(h0e)
                 if n not in tg._nb(a_hex) and n != a_hex]
        pend_b([z3["pid"]], h0e, attackers=[atk["pid"]])
        two = [h0e, legal[0],
               next(x for x in tg._nb(legal[0]) if x not in (h0e, a_hex))]
        submit_no(tg, "Jud", {"type": "resolve_retreat",
                              "paths": {z3["pid"]: two}},
                  "exactly one hex")             # 14.21 cap
        fillers = mil[4:4 + 2 * len(legal)]
        for i, n in enumerate(legal):
            place(fillers[2 * i], n)
            place(fillers[2 * i + 1], n)         # every legal dest full
        submit_no(tg, "Jud", {"type": "resolve_retreat",
                              "paths": {z3["pid"]: [h0e, legal[0]]}},
                  "eliminate")                   # forced overstack
        r = submit_ok(tg, "Jud", {"type": "resolve_retreat",
                                  "eliminate": [z3["pid"]]})
        assert z3["state"] == "eliminated"
        # reopen one destination: the capped 1-hex retreat works again
        fillers[0]["hex"] = fillers[1]["hex"] = None
        place(z4, h0e)
        pend_b([z4["pid"]], h0e, attackers=[atk["pid"]])
        submit_ok(tg, "Jud", {"type": "resolve_retreat",
                              "paths": {z4["pid"]: [h0e, legal[0]]}})
        assert z4["hex"] == legal[0] and z4["state"] == "fresh"
        print("retreat: 14.21 cap + forced-overstack elimination OK")

        # ---- case 5: N23 - substitute a D for the B [14.2]
        h0f = next(rest)
        j1, j2 = take("judaean_regular", 2)
        place(j1, h0f)
        place(j2, h0f)
        tg.s["pending"] = {"kind": "loss", "hex": h0f, "letters": ["D"],
                           "by": "Jud", "source": "melee",
                           "attacker": "Rom", "attacker_pids": []}
        submit_no(tg, "Jud", {"type": "resolve_loss",
                              "picks": [{"pid": j1["pid"]}],
                              "substitute_d": j2["pid"]},
                  "no B result")                 # substitution needs a B
        tg.s["pending"] = {"kind": "loss", "hex": h0f, "letters": ["B"],
                           "by": "Jud", "source": "melee",
                           "attacker": "Rom", "attacker_pids": []}
        submit_ok(tg, "Jud", {"type": "resolve_loss", "picks": [],
                              "substitute_d": j2["pid"]})
        assert j2["state"] == "disrupted" and j1["state"] == "fresh", \
            "substituted D falls on the single chosen unit [14.2]"
        p = tg.s["pending"]
        assert p and p["kind"] == "retreat" and p["rkind"] == "disrupt" \
            and p["pids"] == [j2["pid"]], \
            "the substituted Disrupt retreats immediately [14.3]"
        dst = min(tg._nb(h0f), key=d)
        submit_ok(tg, "Jud", {"type": "resolve_retreat",
                              "paths": {j2["pid"]: [h0f, dst]}})
        assert j1["hex"] == h0f and j1["state"] == "fresh", \
            "the other defender neither retreats nor suffers [14.2]"
        print("retreat: N23 substitute-D honoured, B retreat waived OK")

        # ---- 15.2: Infantry may not retreat into a Cavalry hex
        reg["hex"] = mil[0]["hex"] = mil[1]["hex"] = None   # clear spot 0
        cav = take("roman_cavalry", 1)[0]
        vet = take("roman_veteran", 1)[0]
        place(vet, h0)                 # reuse spot 0's field
        cav_hex = max(tg._nb(h0), key=d)
        place(cav, cav_hex)
        pend_b([vet["pid"]], h0, by="Rom")
        submit_no(tg, "Rom", {"type": "resolve_retreat",
                              "paths": {vet["pid"]: [h0, cav_hex]}},
                  "[15.2]")
        open_n = next(n for n in tg._nb(h0)
                      if n != cav_hex and not tg._occupants(n))
        submit_ok(tg, "Rom", {"type": "resolve_retreat",
                              "paths": {vet["pid"]: [h0, open_n]}})
        print("retreat: 15.2 Infantry/Cavalry interlock OK")
        print("retreat engine checks: PASS (B17/N10/N23; 15.3 EXAMPLE "
              "arithmetic reproduced)")
    finally:
        shutil.rmtree(live, ignore_errors=True)


def fire_drm_checks(g):
    """B2/B3/B4/B5 + N3/N4: the complete printed Missile Table drm block,
    errant fire, primary-target allocation, wall-bonus denial, ZOC-exerter
    preference, and 9.9's one-hex indirect limit - engineered boards through
    submit() (throwaway game, log never replayed). The one exception: the
    errant case pins the die to a natural 1 by overriding the throwaway's
    roll_die - resolution logic given a die, like the table checks."""
    live = tempfile.mkdtemp(prefix="soj_drm_")
    try:
        tg = soj.SoJGame(g, os.path.join(HERE, "scenario_gallus.json"),
                         live, seed=41)
        U = tg.s["units"]
        tg.s["phase"], tg.s["deploy_done"] = "rom_fire", True
        tg.s["seg"] = "Rom"

        def take(t, n):
            out = [u for u in U.values()
                   if u["type"] == t and u["hex"] is None][:n]
            assert len(out) == n, f"need {n} {t}"
            return out

        def place(u, h, state="fresh"):
            u["hex"], u["state"] = h, state

        cmdR = next(u for u in U.values() if u["type"] == "gallus")
        jleads = {u.get("faction"): u for u in U.values()
                  if u["type"] == "judaean_leader"}

        def with_hq(u):
            """CC for the engineered firer [5.x]: its commander/leader
            shares the hex (HQs free-stack). All other leaders park off-map
            so a leftover HQ never becomes a stray mandatory target."""
            for h_ in [cmdR] + list(jleads.values()):
                h_["hex"] = None
            hq = cmdR if u["side"] == "Rom" else jleads[u["faction"]]
            hq["hex"], hq["state"] = u["hex"], "fresh"

        def reset_fire(seg):
            tg.s["fired"], tg.s["fired_hexes"] = [], []
            tg.s["phase"] = "rom_fire" if seg == "Rom" else "jud_fire"
            tg.s["seg"] = seg
            tg.s["pending"] = None

        def axis(h, dq, dr, k):
            c, r = int(h[:2]), int(h[2:])
            n = r - c // 2
            c2, n2 = c + dq * k, n + dr * k
            return f"{c2:02d}{n2 + c2 // 2:02d}"

        AXES = [(1, 0), (0, 1), (1, -1)]

        def clear1(h):
            return (h in tg.playable and tg.hex_t(h) == "clear"
                    and not tg._occupants(h))

        def clear_line(k):
            """k colinear clear unoccupied playable hexes, isolated."""
            for h in sorted(tg.hex_t0):
                for dq, dr in AXES:
                    for sign in (1, -1):
                        L = [axis(h, dq * sign, dr * sign, i)
                             for i in range(k)]
                        if all(clear1(x) and
                               all(m in tg.playable for m in tg._nb(x))
                               for x in L):
                            return L
            raise AssertionError(f"no clear {k}-line")

        # ---- A: 9.13 -1 per Tower hex fired through + Fresh-HI -1
        L = clear_line(3)
        jr = take("judaean_regular", 3)
        tower = take("tower", 1)[0]
        vet = take("roman_veteran", 4)
        place(jr[0], L[0])
        with_hq(jr[0])
        place(tower, L[1])
        place(vet[0], L[2])
        reset_fire("Jud")
        r = submit_ok(tg, "Jud", {"type": "fire", "firers": [jr[0]["pid"]],
                                  "target": tg.hex_name[L[2]]})
        det = r["result"]
        assert det["drm"] == -2, det   # -1 tower [9.13], -1 Fresh HI [13.3]
        print(f"fire drm: 9.13 tower -1 + Fresh-HI -1 -> drm {det['drm']} OK")
        tower["hex"] = None
        reset_fire("Jud")
        r = submit_ok(tg, "Jud", {"type": "fire", "firers": [jr[0]["pid"]],
                                  "target": tg.hex_name[L[2]]})
        assert r["result"]["drm"] == -1     # tower gone: only Fresh-HI
        tg.s["pending"] = None
        # SE in the target hex suppresses the Fresh-HI -1 [13.3 ** footnote]
        ram = take("ram", 1)[0]
        place(ram, L[2])
        reset_fire("Jud")
        r = submit_ok(tg, "Jud", {"type": "fire", "firers": [jr[0]["pid"]],
                                  "target": tg.hex_name[L[2]]})
        assert r["result"]["drm"] == 0, r["result"]
        print("fire drm: Fresh-HI -1 suppressed by SE in target hex OK")
        for u in (jr[0], vet[0], ram):
            u["hex"] = None

        # ---- B/C: breach drm - find a wall with colinear ground on both
        # sides: g0 -> w1(breached) -> g2 [-> g3]
        found = None
        for w in sorted(tg.hex_t0):
            if tg.hex_t(w) not in ("wall", "north_wall"):
                continue
            for dq, dr in AXES:
                for sign in (1, -1):
                    a, b = dq * sign, dr * sign
                    g0, g2 = axis(w, a, b, -1), axis(w, a, b, 1)
                    g3 = axis(w, a, b, 2)
                    if clear1(g0) and clear1(g2) and clear1(g3):
                        found = (g0, w, g2, g3)
                        break
                if found:
                    break
            if found:
                break
        assert found, "no ground-wall-ground axis line"
        g0, w1, g2, g3 = found
        tg.s["breach"][w1] = 99            # the wall is now a Breach
        assert tg.hex_t(w1) == "breach"
        vel = take("velitae", 2)
        # firing FROM a Breach: -1 [game card]
        place(vel[0], w1)
        with_hq(vel[0])
        place(jr[1], g2)
        reset_fire("Rom")
        r = submit_ok(tg, "Rom", {"type": "fire", "firers": [vel[0]["pid"]],
                                  "target": tg.hex_name[g2]})
        assert r["result"]["drm"] == -1, r["result"]
        print("fire drm: firing from a Breach -1 OK")
        vel[0]["hex"] = None
        tg.s["pending"] = None
        # ground-through-Breach + indirect together = -1, not -2 [* footnote]
        place(vel[1], g0)
        with_hq(vel[1])
        place(jr[2], g2)                   # occupied crossing (indirect)
        jr[1]["hex"] = g3                  # the target beyond
        reset_fire("Rom")
        r = submit_ok(tg, "Rom", {"type": "fire", "firers": [vel[1]["pid"]],
                                  "target": tg.hex_name[g3]})
        det = r["result"]
        assert det["drm"] == -1, det       # breach-cross + indirect = -1
        print("fire drm: *-pair (indirect + through-Breach) not cumulative OK")
        for u in (vel[1], jr[1], jr[2]):
            u["hex"] = None
        del tg.s["breach"][w1]
        tg.s["pending"] = None

        # ---- E: 9.8 wall bonus - denied over intervening units; gates are
        # never Wall hexes (F.19 ruling)
        wline = None
        for w in sorted(tg.hex_t0):
            if tg.hex_t(w) not in ("wall", "north_wall"):
                continue
            for dq, dr in AXES:
                for sign in (1, -1):
                    W = [axis(w, dq * sign, dr * sign, i) for i in range(4)]
                    if all(x in tg.hex_t0 and
                           tg.hex_t(x) in ("wall", "north_wall")
                           and not tg._occupants(x) for x in W):
                        wline = W
                        break
                if wline:
                    break
            if wline:
                break
        assert wline, "no colinear wall 4-line"
        w0, w1b, w2, w3 = wline            # blocker NOT adjacent to w0
        jr2 = take("judaean_regular", 1)[0]
        jr2b = next(u for u in U.values()
                    if u["type"] == "judaean_regular" and u["hex"] is None
                    and u["faction"] == jr2["faction"])
        place(jr2, w0)
        place(jr2b, w1b)                   # wall limit 1: one per hex
        with_hq(jr2)                       # same faction: one leader covers
        place(vet[1], w3)
        reset_fire("Jud")
        r = submit_ok(tg, "Jud", {"type": "fire",
                                  "firers": [jr2["pid"], jr2b["pid"]],
                                  "target": tg.hex_name[w3]})
        af2 = r["result"]["af"]
        tg.s["pending"] = None
        # intervening unit: artillery, so it is never a mandatory target
        # [9.7] and exerts no ZOC - only the 9.8 denial is in play
        blk = take("roman_ballista", 1)[0]
        place(blk, w2)
        reset_fire("Jud")
        r = submit_ok(tg, "Jud", {"type": "fire",
                                  "firers": [jr2["pid"], jr2b["pid"]],
                                  "target": tg.hex_name[w3]})
        af1 = r["result"]["af"]
        assert af2 == 2 * af1, (af2, af1)  # bonus doubled, then denied
        print(f"fire drm: 9.8 wall bonus {af1}->{af2} doubled, denied over "
              "intervening units OK")
        for u in (jr2, jr2b, vet[1], blk):
            u["hex"] = None
        tg.s["pending"] = None

        # ---- F: 13.2 the most severe result falls on the Primary Target
        spot = clear_line(1)[0]
        ball = take("roman_ballista", 1)[0]
        place(ball, spot)
        place(vet[3], spot)
        tg.s["pending"] = {"kind": "loss", "hex": spot, "letters": ["D", "E"],
                           "by": "Rom", "source": "fire",
                           "primary": [ball["pid"]]}
        submit_no(tg, "Rom", {"type": "resolve_loss",
                              "picks": [{"pid": ball["pid"]},
                                        {"pid": vet[3]["pid"]}]},
                  "Primary Target")        # E (severest) on the non-primary
        submit_ok(tg, "Rom", {"type": "resolve_loss",
                              "picks": [{"pid": vet[3]["pid"]},
                                        {"pid": ball["pid"]}]})
        assert ball["state"] == "eliminated", ball
        print("fire drm: 13.2 severest result forced onto Primary Target OK")
        vet[3]["hex"] = None

        # ---- G: 9.7 may not ignore a ZOC-exerter for a non-exerter
        fhex = None
        for w in sorted(tg.hex_t0):
            if tg.hex_t(w) in ("wall", "north_wall"):
                for n in tg._nb(w):
                    if clear1(n) and any(clear1(m) for m in tg._nb(n)):
                        fhex, whex = n, w
                        break
            if fhex:
                break
        gnd = next(m for m in tg._nb(fhex) if clear1(m))
        jr3 = take("judaean_regular", 1)[0]
        vets2 = take("roman_veteran", 2)
        place(jr3, fhex)
        with_hq(jr3)
        place(vets2[0], gnd)               # ground HI: exerts ZOC over jr3
        place(vets2[1], whex)              # elevated: exerts none on ground
        reset_fire("Jud")
        submit_no(tg, "Jud", {"type": "fire", "firers": [jr3["pid"]],
                              "target": tg.hex_name[whex]}, "[9.7]")
        submit_ok(tg, "Jud", {"type": "fire", "firers": [jr3["pid"]],
                              "target": tg.hex_name[gnd]})
        tg.s["pending"] = None
        for u in (jr3, vets2[0], vets2[1]):
            u["hex"] = None

        # ---- H: 9.31 errant fire on a natural 1 (die pinned)
        wt = next(h for h in sorted(tg.hex_t0)
                  if tg.hex_t(h) in ("wall", "north_wall")
                  and not tg._occupants(h)
                  and sum(1 for n in tg._nb(h) if clear1(n)) >= 3)
        mil = take("judaean_militia", 1)[0]
        place(mil, wt)
        gs = [n for n in tg._nb(wt) if clear1(n)]
        ball2 = take("roman_ballista", 1)[0]
        place(ball2, gs[0])                # the firing hex
        with_hq(ball2)
        va, vb = take("roman_veteran", 2)
        place(va, gs[1])
        place(vb, gs[2])                   # two friendly errant candidates
        reset_fire("Rom")
        tg.roll_die = lambda: 1            # pin the natural 1 [9.31]
        r = submit_ok(tg, "Rom", {"type": "fire", "firers": [ball2["pid"]],
                                  "target": tg.hex_name[wt]})
        del tg.roll_die
        assert r["result"]["die"] == 1
        assert r["result"].get("errant") == "pending", r["result"]
        # any hit letters resolve first, then the errant choice is the
        # DEFENDER's [9.31]
        while tg.s.get("pending") and tg.s["pending"]["kind"] == "loss":
            p = tg.s["pending"]
            need = [c for c in p["letters"] if c != "B"]
            submit_ok(tg, "Jud", {"type": "resolve_loss",
                                  "picks": [{"pid": mil["pid"]}
                                            for _ in need]})
        p = tg.s.get("pending")
        assert p and p["kind"] == "errant" and p["by"] == "Jud", p
        assert set(p["cands"]) == {va["pid"], vb["pid"]}, p
        submit_no(tg, "Rom", {"type": "resolve_errant", "pid": va["pid"]},
                  "defender")
        submit_ok(tg, "Jud", {"type": "resolve_errant", "pid": va["pid"]})
        assert va["state"] == "disrupted" and vb["state"] == "fresh"
        print("fire drm: 9.31 errant fire - defender disrupts an attacker "
              "unit adjacent to the target OK")
        print("fire drm checks: PASS (B2/B3/B4/B5 + N3/N4)")
    finally:
        shutil.rmtree(live, ignore_errors=True)


def gate_ring_checks(tg):
    """A5/A6 regression. Decode-prep 6: neither printed table has a Gate
    row, so a gate's breach defense and missile row resolve on its printed
    strongpoint ring class (red=Fortress orange=Fort blue=Bastion).
    Entrance hexsides per the module's own gate overlay (PREP-2, 53 arrows
    incl. the 8.91 printed example QQ36); staircase set per the PREP-3
    art-confirmation pass."""
    import json
    exp = {"G40": (12, "fort"), "R49": (12, "fort"),
           "LL30": (10, "bastion_armored_tower"),
           "MM32": (10, "bastion_armored_tower"),
           "P51": (15, "fortress"), "W36": (15, "fortress"),
           "Z23": (15, "fortress"), "Q49": (10, "bastion_armored_tower"),
           "OO33": (15, "fortress"),
           "V42": (12, "fort")}    # A4 side-find: Second-Wall corner gate
    for name, (deff, row) in exp.items():
        h = tg.name_hex[name]
        assert tg.hex_t0[h].startswith("gate"), (name, tg.hex_t0[h])
        assert tg._breach_def(h) == deff, (name, tg._breach_def(h))
        assert tg._target_row(h) == row, (name, tg._target_row(h))
    E = tg.entrances
    # the two overlay-contradicted entrance sides are corrected
    assert ("2346", "2347") not in E and ("2247", "2347") in E, \
        "W36 Damascus entrance must be V36, not W35"
    assert ("4153", "4253") not in E and ("4153", "4154") in E, \
        "OO33 Tadi entrance must be OO34, not PP32"
    for k in ("0643|0743", "0743|0844", "1758|1858", "1858|1957",
              "3748|3849", "3849|3949", "3852|3951", "3951|4051",
              "1559|1659", "1659|1758"):
        assert tuple(k.split("|")) in E, f"missing entrance side {k}"
    # sweep: every overlay gate inside the playable area must be
    # gate-typed with a ring and at least one entrance side. Pre-A4 the
    # Old City leak exposed 13 printed gates that failed this; the A4
    # hard bound dropped 12 of them off the battlefield (asserted below)
    # and the 13th, V42, turned out to be Second-Wall fabric bordering
    # the crescent (entrance U42) - it is now encoded and must PASS.
    OLD_CITY_GATES = {"N55", "P54", "Q52", "U50", "X48", "FF47",
                      "II34", "JJ43", "KK41", "NN42", "OO38", "QQ36"}
    for n in OLD_CITY_GATES:
        assert tg.name_hex[n] not in tg.playable, \
            f"Old City gate {n} is inside the A4-bounded battlefield"
    assert tg.name_hex["V42"] in tg.playable, "V42 must stay playable"
    ov = json.load(open(os.path.join(HERE, "ingest", "gates_overlay.json"),
                        encoding="utf-8"))
    failing = set()
    for gt in ov["gates"]:
        h = tg.name_hex.get(gt["gate"])
        if h is None or h not in tg.playable:
            continue
        if (not tg.hex_t0[h].startswith("gate") or h not in tg.hex_ring
                or not any(h in pair for pair in E)):
            failing.add(gt["gate"])
    assert not failing, \
        f"overlay-gate sweep: unencoded playable gates {sorted(failing)}"
    # staircases: the ten non-adjacent phantoms are gone; Z33|Z34 is in
    for k in ("0742|0844 1854|1955 1858|1959 2253|2354 2646|2747 3244|3345 "
              "3544|3646 3635|3736 3846|3947 3936|4038").split():
        assert tuple(k.split("|")) not in tg.stairs, f"phantom stair {k} back"
    assert ("2646", "2647") in tg.stairs, "Z33|Z34 staircase missing"
    print("gate ring/entrance/staircase checks: PASS "
          "(10 gates incl. V42, overlay sweep clean, 12 Old City gates "
          "off-battlefield, 10 phantoms out, Z33|Z34 in)")


def walk_phase(tg, pid, dest, max_turns=8):
    """Move a unit toward dest across successive own Movement Phases."""
    u = tg.s["units"][pid]
    side = u["side"]
    for _ in range(max_turns):
        cycle_to_phase(tg, f"{'rom' if side == 'Rom' else 'jud'}_move")
        path = greedy_path(tg, u, dest)
        if path and len(path) > 1:
            submit_ok(tg, side, {"type": "move", "pid": pid,
                                 "path": [tg.hex_name[h] for h in path]})
        if u["hex"] == dest:
            return
    raise AssertionError(f"{pid} never reached {tg.hex_name[dest]}")


def greedy_path(tg, u, dest):
    """Longest legal prefix of a shortest clear-ground path toward dest."""
    import heapq
    frontier = [(0, [u["hex"]])]
    seen = {u["hex"]}
    best = None
    while frontier:
        d, path = heapq.heappop(frontier)
        if path[-1] == dest:
            best = path
            break
        for n in tg._nb(path[-1]):
            if n in seen or n not in tg.playable:
                continue
            if tg.hex_t(n) not in ("clear", "slope", "breach"):
                continue
            if any(o["side"] != u["side"] for o in tg._occupants(n)):
                continue
            seen.add(n)
            heapq.heappush(frontier, (d + 1, path + [n]))
    if not best:
        return None
    # longest prefix the gate accepts
    for cut in range(len(best), 1, -1):
        v = tg._move_verdict(u["side"], u, best[:cut])
        if v["legal"]:
            return best[:cut]
    return None


def cycle_to_phase(tg, phase, turn=None):
    r = None
    for _ in range(400):
        if tg.s["phase"] == phase and (turn is None or tg.s["turn"] == turn):
            return r
        assert not tg.s.get("pending"), tg.s["pending"]
        r = submit_ok(tg, tg.side_to_move(), {"type": "end_phase"})
        if tg.s.get("over"):
            return r
    raise AssertionError(f"never reached {phase}")


def main():
    live = tempfile.mkdtemp(prefix="soj_cbt_")
    try:
        g = gamespec.Game(HERE)
        table_checks(g)
        tg = soj.SoJGame(g, os.path.join(HERE, "scenario_gallus.json"),
                         live, seed=23)
        assert tg.tier == 2 and tg.tier_earned == 2, \
            f"combat validated => tier 2 earned (got {tg.tier_earned})"
        engine_math(tg)
        gate_ring_checks(tg)
        retreat_engine_checks(g)
        fire_drm_checks(g)

        # ---- deployment engineered for the assault: Judaean garrison as
        # usual, Roman camp scripted (ram + crew forward, ballista in range)
        deploy_jud(tg)

        tgt = tg.name_hex["T29"]              # plain North Wall hex, def 6
        s30 = tg.name_hex["S30"]
        ram = next(u for u in tg.s["units"].values() if u["type"] == "ram")
        crew = [u for u in tg.s["units"].values()
                if u["type"] == "roman_veteran"][:2]
        ball = next(u for u in tg.s["units"].values()
                    if u["type"] == "roman_ballista")
        approach = next(h for h in tg._nb(tgt)
                        if h in tg.outside and tg.hex_t(h) == "clear")
        camp = min((h for h in tg.rom_zone),
                   key=lambda h: tg._dist(h, approach))
        # artillery targets a DIFFERENT garrisoned strongpoint so the S30
        # militia stays Fresh for the rock test
        art_tgt = next(tg.name_hex[n] for n in
                       ("V27", "Y24", "P33", "M36")
                       if any(h2 == tg.name_hex[n] and tg._occupants(h2)
                              for h2 in [tg.name_hex[n]]))
        ball_camp = next(h for h in sorted(tg.rom_zone)
                         if 7 <= tg._dist(h, art_tgt) <= 9
                         and tg._dist(h, camp) <= 8
                         and tg._lof(h, art_tgt)[0] and h != camp)
        gallus = next(u for u in tg.s["units"].values()
                      if u["type"] == "gallus")
        for u_ in (ram, crew[0], crew[1], gallus):
            submit_ok(tg, "Rom", {"type": "deploy", "pid": u_["pid"],
                                  "hex": tg.hex_name[camp]})
        submit_ok(tg, "Rom", {"type": "deploy", "pid": ball["pid"],
                              "hex": tg.hex_name[ball_camp]})
        # bulk the rest of the army far back
        zone = sorted(tg.rom_zone,
                      key=lambda h: -tg._dist(h, approach))
        zi = 0
        for u_ in tg.s["units"].values():
            if u_["side"] != "Rom" or u_["hex"] is not None:
                continue
            while True:
                r = tg.submit("Rom", {"type": "deploy", "pid": u_["pid"],
                                      "hex": tg.hex_name[zone[zi]]})
                if r["verdict"]["legal"]:
                    break
                zi += 1
        submit_ok(tg, "Rom", {"type": "deploy_done"})

        # ---- Roman artillery fire at S30's garrison (fire segment order)
        cycle_to_phase(tg, "rom_fire")
        assert tg.side_to_move() == "Jud"     # non-phasing fires first [4.12]
        submit_ok(tg, "Jud", {"type": "end_phase"})
        art_tgt_name = tg.hex_name[art_tgt]
        r = submit_ok(tg, "Rom", {"type": "fire", "firers": [ball["pid"]],
                                  "target": art_tgt_name})
        det = r["result"]
        assert det["row"] == "bastion_armored_tower", det
        assert det["col"] >= 1 and "die" in det
        submit_no(tg, "Rom", {"type": "fire", "firers": [ball["pid"]],
                              "target": art_tgt_name}, "already")   # [13.1]
        print(f"artillery fire: AF {det['af']} vs bastion, col {det['col']}, "
              f"die {det['die']} -> {det['result']}")
        drain_pendings(tg)

        # ---- march ram + crew together to the approach hex (crew must be
        # in the engine's hex at the start of each of its moves [8.6])
        for _ in range(10):
            if ram["hex"] == approach:
                break
            cycle_to_phase(tg, "rom_move")
            path = greedy_path(tg, ram, approach)
            if path and len(path) > 1:
                submit_ok(tg, "Rom", {"type": "move", "pid": ram["pid"],
                                      "path": [tg.hex_name[h] for h in path]})
            for c_ in crew:
                if c_["hex"] != ram["hex"]:
                    p2 = greedy_path(tg, c_, ram["hex"])
                    if p2 and len(p2) > 1:
                        submit_ok(tg, "Rom",
                                  {"type": "move", "pid": c_["pid"],
                                   "path": [tg.hex_name[h] for h in p2]})
        assert ram["hex"] == approach, "ram never reached the wall"

        # ---- breach attacks until T29 falls (defense 6)
        breached = False
        for _turn in range(12):
            if tg.s["phase"] == "rom_fire":   # leave this turn's fire phase
                submit_ok(tg, tg.side_to_move(), {"type": "end_phase"})
                if tg.s["phase"] == "rom_fire":
                    submit_ok(tg, tg.side_to_move(), {"type": "end_phase"})
            cycle_to_phase(tg, "rom_fire")
            submit_ok(tg, "Jud", {"type": "end_phase"})
            r = submit_ok(tg, "Rom", {"type": "breach_attack",
                                      "attackers": [ram["pid"]],
                                      "target": "T29"})
            det = r["result"]
            assert det["defense"] == 6        # North Wall [card/12.1]
            if det.get("breached"):
                breached = True
                break
        assert breached, "ram never breached the North Wall"
        assert tg.hex_t(tgt) == "breach", "breached hex must become a Breach [12.2]"
        print(f"breach: T29 fell after cumulative damage {det['total']} >= 6; "
              "hex is now a Breach")

        # ---- assault: heavy infantry climbs through the breach and melees
        # the bastion S30 garrison from the breach (approach mult 1/2 [11.13])
        cycle_to_phase(tg, "rom_move")
        v = submit_ok(tg, "Rom", {"type": "move", "pid": crew[0]["pid"],
                                  "path": [tg.hex_name[approach], "T29"]})
        assert tg.s["units"][crew[0]["pid"]]["hex"] == tgt
        cycle_to_phase(tg, "rom_melee")
        defenders = [o for o in tg._occupants(s30)]
        assert defenders, "S30 garrison expected"
        r = submit_ok(tg, "Rom", {"type": "melee",
                                  "attackers": [crew[0]["pid"]],
                                  "target": "S30"})
        det = r["result"]
        # 7 attack halved (breach->elevated 11.13) vs doubled defense [11.7]
        assert det["att"] == 3.5, det
        print(f"melee from breach: att {det['att']} vs def {det['def']}, "
              f"col {det['col']}, die {det['die']} -> {det['result']}")
        # resolve any pendings honestly through the gate
        drain_pendings(tg)

        # ---- rally ladder: disrupt a Roman by Judaean rocks, then rally it
        rock_test(tg)

        # ---- the log replays end-to-end
        r = subprocess.run(
            [sys.executable, os.path.join(ENG, "verify_game.py"),
             "--game", HERE,
             os.path.join(live, "game_siege-of-jerusalem-ah.log.jsonl")],
            capture_output=True, text=True)
        assert "VERIFIED" in r.stdout, r.stdout + r.stderr
        print(r.stdout.strip().splitlines()[-1])
        print("validate_combat: PASS")
    finally:
        shutil.rmtree(live, ignore_errors=True)


def drain_pendings(tg):
    while tg.s.get("pending"):
        p = tg.s["pending"]
        if p["kind"] == "loss":
            need = [c for c in p["letters"] if c != "B"]
            occ = [o for o in tg._occupants(p["hex"]) if o["side"] == p["by"]]
            picks = [{"pid": occ[min(i, len(occ) - 1)]["pid"]}
                     for i in range(len(need))]
            submit_ok(tg, p["by"], {"type": "resolve_loss", "picks": picks})
        elif p["kind"] == "retreat":
            paths, elim = {}, []
            enemy = tg._enemy(p["by"])
            zoc = tg._zoc_map(enemy)
            virt = {}                     # combat units this action added
            for pid in p["pids"]:
                u = tg.s["units"][pid]
                cands = []
                for n in tg._nb(u["hex"]):
                    if n in zoc:
                        continue
                    occ = [o for o in tg._occupants(n) if o["pid"] != pid]
                    if any(o["side"] == enemy for o in occ):
                        continue
                    if any(o["state"] == "panicked" for o in occ):
                        continue
                    if tg._entry_cost(u, u["hex"], n, p["by"])[0] is None:
                        continue
                    if tg._combat_count(occ) + virt.get(n, 0) >= \
                            tg._stack_limit(n, p["by"]):
                        continue          # full - the driver stops clean
                    cands.append(n)
                if cands:
                    dest = min(cands,
                               key=lambda h: tg._refuge_dist(p["by"], h))
                    paths[pid] = [tg.hex_name[u["hex"]], tg.hex_name[dest]]
                    if tg.utype(u)["cls"] not in tg._FREE_CLS:
                        virt[dest] = virt.get(dest, 0) + 1
                else:
                    elim.append(pid)      # no clean 1-hex stop: eliminate
            act = {"type": "resolve_retreat", "paths": paths}
            if elim:
                act["eliminate"] = elim
            submit_ok(tg, p["by"], act)


def rock_test(tg):
    """The S30 garrison drops rocks on the breach party in T29 below
    [10.2/Weapons Chart]; a disruption then rides the rally ladder."""
    s30 = tg.name_hex["S30"]
    t29 = tg.name_hex["T29"]
    z = next((u for u in tg._occupants(s30)
              if u["side"] == "Jud" and u["state"] == "fresh"
              and tg.utype(u).get("rock") is not None), None)
    if z is None:
        print("rock test skipped: S30 garrison not Fresh")
        return
    if not any(o["side"] == "Rom" for o in tg._occupants(t29)):
        print("rock test skipped: no Romans in the breach")
        return
    victim_hex = t29
    cycle_to_phase(tg, "jud_fire")
    if tg.side_to_move() == "Rom":
        submit_ok(tg, "Rom", {"type": "end_phase"})
    r = submit_ok(tg, "Jud", {"type": "fire", "firers": [z["pid"]],
                              "target": tg.hex_name[victim_hex]})
    det = r["result"]
    print(f"rocks: AF {det['af']} vs {det['row']}, die {det['die']} -> "
          f"{det['result']}")
    drain_pendings(tg)
    # ride the rally phase: any disrupted Roman gets its mandatory roll
    disrupted = [u["pid"] for u in tg.s["units"].values()
                 if u["side"] == "Rom" and u["state"] != "fresh"
                 and u["hex"] is not None]
    r = cycle_to_phase(tg, "rom_fire")      # passes through rom_rally
    if disrupted and r and "rally" in (r.get("result") or {}):
        ev = r["result"]["rally"]
        assert any(e["pid"] in disrupted for e in ev), ev
        print(f"rally rolls: {ev}")


if __name__ == "__main__":
    main()
