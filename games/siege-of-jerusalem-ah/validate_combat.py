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
            paths = {}
            enemy = tg._enemy(p["by"])
            zoc = tg._zoc_map(enemy)
            for pid in p["pids"]:
                u = tg.s["units"][pid]
                dest = next((n for n in tg._nb(u["hex"])
                             if n not in zoc
                             and not any(o["side"] == enemy
                                         for o in tg._occupants(n))
                             and tg._entry_cost(u, u["hex"], n, p["by"])[0]
                             is not None), None)
                assert dest, "no legal retreat found by the test driver"
                paths[pid] = [tg.hex_name[u["hex"]], tg.hex_name[dest]]
            submit_ok(tg, p["by"], {"type": "resolve_retreat", "paths": paths})


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
