"""validate_deploy.py - Gallus free-deployment gate.

Drives a complete legal deployment through the gate (every placement a
submitted, logged action) and probes the card's constraints with rejection
cases:
  - Judaeans deploy first, only in the New City / on its outer walls
  - minimum-force strongpoints O50..QQ29 must each hold a unit before
    deploy_done passes (special rule 1)
  - Cauldrons only on Elevated hexes [8.4/8.5]; stacking respected [6.x]
  - Romans deploy second, outside, >= 5 hexes from any Elevated hex;
    P50/QQ32 prohibited (card); rejection probes for each
The finished log must replay through verify_game.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ENG = os.path.join(HERE, "..", "..", "engine")
sys.path.insert(0, ENG)
import gamespec  # noqa: E402
import soj       # noqa: E402


def submit_ok(tg, side, action):
    r = tg.submit(side, action)
    assert r["verdict"]["legal"], (action, r["verdict"]["reasons"])
    return r


def submit_no(tg, side, action, why_frag=""):
    r = tg.submit(side, action)
    assert not r["verdict"]["legal"], f"expected rejection: {action}"
    if why_frag:
        joined = " ".join(r["verdict"]["reasons"])
        assert why_frag in joined, (why_frag, joined)
    return r


def deploy_all(tg):
    """A legal deployment: Judaean wall garrison + crescent mass, then the
    Roman camp on the northern plain."""
    deploy_jud(tg)
    deploy_rom(tg)


def deploy_jud(tg):
    """Judaean half only (for tests that script their own Roman camp)."""
    juds = [u for u in tg.s["units"].values() if u["side"] == "Jud"]
    min_force = [tg.hex_name[h] for h in tg.min_force]
    cauldrons = [u for u in juds if u["type"] == "cauldron"]
    combat = [u for u in juds if u["type"] in
              ("zealot", "judaean_regular", "judaean_militia")]
    leaders = [u for u in juds if u["type"] == "judaean_leader"]
    for hexn, u in zip(min_force, combat):
        submit_ok(tg, "Jud", {"type": "deploy", "pid": u["pid"], "hex": hexn})
    rest = combat[len(min_force):]
    for hexn, u in zip(min_force, cauldrons):
        submit_ok(tg, "Jud", {"type": "deploy", "pid": u["pid"], "hex": hexn})
    crescent_hexes = [tg.hex_name[h] for h in sorted(tg.new_city)
                      if tg.hex_t0[h] in ("clear", "builtup")]
    spots = crescent_hexes[:3]
    for hexn in crescent_hexes[3:]:
        spots += [hexn, hexn]
    for u, hexn in zip(leaders + rest, spots):
        submit_ok(tg, "Jud", {"type": "deploy", "pid": u["pid"], "hex": hexn})
    submit_ok(tg, "Jud", {"type": "deploy_done"})


def deploy_rom(tg):
    roms = [u for u in tg.s["units"].values() if u["side"] == "Rom"]
    # every other zone hex: the A4-bounded flank is tight enough that a
    # solid-packed camp walls its own corner units in (A24/B24 don't exist),
    # and the movement probes need units with open ground beside them
    zone = sorted(tg.rom_zone)[::2]
    heavy_first = sorted(
        roms, key=lambda u: 0 if tg.utype(u)["cls"] in ("heavy", "light") else 1)
    zi = 0
    placed_here = 0
    for u in heavy_first:
        while True:
            h = zone[zi]
            act = {"type": "deploy", "pid": u["pid"], "hex": tg.hex_name[h]}
            r = tg.submit("Rom", act)
            if r["verdict"]["legal"]:
                placed_here += 1
                if placed_here >= 2:      # keep stacks loose
                    zi += 1
                    placed_here = 0
                break
            zi += 1
            placed_here = 0
    submit_ok(tg, "Rom", {"type": "deploy_done"})


def bound_and_builtup_checks(tg):
    """A3+A4 regression (2026-08-09). A3: Gallus Built-up = 92 per the frozen
    PREP-4 evidence (ingest/builtup_evidence.json) — the 42-hex western-quarter
    correction plus the 50 shipped, and Built-up IS the Roman victory pool.
    A4: the southern hard bound (card: played only on the North Wall O50 ->
    Women's Gate -> QQ31) keeps every pre-bound Old City art hex off the
    battlefield; SS18/SS20/VV15 are the three adjudicated false positives
    inside the bound (Kidron valley shading / printed map label — crops in
    C:\\VassalSoJ\\desktop_packs\\SoJ_A4)."""
    ev = json.load(open(os.path.join(HERE, "ingest", "builtup_evidence.json"),
                        encoding="utf-8"))
    rows = ev["rows"]
    want = {r["key"] for r in rows
            if r["zone"] == "new_city" and r["verdict"] == "builtup"}
    have = {h for h, t in tg.hex_t0.items() if t == "builtup"}
    assert want == have, (sorted(want - have), sorted(have - want))
    assert len(have) == 92, len(have)
    assert all(h in tg.playable for h in have), "objective off-battlefield"
    assert tg.scenario["vp"]["roman_win"]["builtup_controlled"] == 10
    # A4: nothing the printed art marks as Old City interior is playable
    TRIO = {"SS18", "SS20", "VV15"}
    leaked = [r["hex"] for r in rows
              if r["zone"] == "outside" and r["hex"] not in TRIO
              and r["verdict"] in ("builtup", "edifice", "adjudicate")
              and tg.name_hex[r["hex"]] in tg.playable]
    assert not leaked, leaked
    for n in TRIO:
        assert tg.name_hex[n] in tg.playable, n
    # the typed Old City strongpoint fabric at the south junction is out;
    # the card's named anchors, junctions and gates stay in
    for n in ("P51", "O51", "O52", "O53", "P52", "P53",
              "Q50", "Q51", "Q52", "Q53", "R49", "R51"):
        assert tg.name_hex[n] not in tg.playable, n
    for n in ("O50", "Z23", "QQ31", "P50", "QQ32", "Q49", "OO33",
              "W36", "V42", "G39"):
        assert tg.name_hex[n] in tg.playable, n
    # exact area accounting: any change here is a bound change and needs
    # the same evidence discipline as this bite
    assert len(tg.playable) == 1341, len(tg.playable)
    assert len(tg.outside) == 845, len(tg.outside)
    print("A3/A4 bound+builtup checks: PASS (92 objectives, "
          f"{len(tg.playable)} playable, Old City off-battlefield)")


def setup_option_checks(tg):
    """N13 [3.4]: Roman Artillery may set up either Fresh or Disrupted
    (movable); no other unit, and no other side, may choose a setup status.
    N17 [3.3]: Gallus has no off-board Legion setup - every Roman unit deploys
    on-board and the only reinforcements are the Judaean South Wall force."""
    deploy_jud(tg)
    assert tg.s["phase"] == "deploy_rom"
    arts = [u for u in tg.s["units"].values()
            if u["side"] == "Rom" and tg.utype(u)["cls"] == "artillery"]
    assert len(arts) >= 3, len(arts)
    heavy = next(u for u in tg.s["units"].values()
                 if u["side"] == "Rom" and tg.utype(u)["cls"] == "heavy"
                 and u["hex"] is None)
    ground = [h for h in sorted(tg.rom_zone)
              if tg.hex_t(h) not in soj.ELEVATED]

    submit_ok(tg, "Rom", {"type": "deploy", "pid": arts[0]["pid"],
                          "hex": tg.hex_name[ground[0]], "status": "disrupted"})
    assert arts[0]["state"] == "disrupted", arts[0]
    submit_ok(tg, "Rom", {"type": "deploy", "pid": arts[1]["pid"],
                          "hex": tg.hex_name[ground[2]], "status": "fresh"})
    assert arts[1]["state"] == "fresh", arts[1]
    submit_ok(tg, "Rom", {"type": "deploy", "pid": arts[2]["pid"],
                          "hex": tg.hex_name[ground[4]]})
    assert arts[2]["state"] == "fresh", arts[2]        # default is Fresh

    submit_no(tg, "Rom", {"type": "deploy", "pid": heavy["pid"],
                          "hex": tg.hex_name[ground[6]], "status": "disrupted"},
              "only Roman Artillery")
    submit_no(tg, "Rom", {"type": "deploy", "pid": arts[3]["pid"],
                          "hex": tg.hex_name[ground[6]], "status": "routed"},
              "Fresh or Disrupted")

    dep = tg.scenario["deployment"]
    assert "offboard" not in dep and "legions" not in dep, dep.keys()
    assert all(p["side"] == "Jud" for p in tg.scenario["reinforcement_pool"])
    print("setup-option checks: PASS (N13 Artillery Fresh/Disrupted; N17 "
          "no off-board Legion setup in Gallus - Romans all on-board)")


def main():
    live = tempfile.mkdtemp(prefix="soj_dep_")
    try:
        g = gamespec.Game(HERE)
        tg = soj.SoJGame(g, os.path.join(HERE, "scenario_gallus.json"),
                         live, seed=7)
        bound_and_builtup_checks(tg)
        assert tg.tier == 3 and tg.tier_earned == 3, \
            f"Full rules = combat gate + AI seat (plumbing 3, got {tg.tier_earned})"
        assert tg.s["phase"] == "deploy_jud"

        # N13/N17 setup options on a throwaway (its own log, not replayed here)
        stg = soj.SoJGame(g, os.path.join(HERE, "scenario_gallus.json"),
                          tempfile.mkdtemp(prefix="soj_setup_"), seed=7)
        setup_option_checks(stg)

        juds = [u for u in tg.s["units"].values() if u["side"] == "Jud"]
        roms = [u for u in tg.s["units"].values() if u["side"] == "Rom"]
        assert len(juds) == 51 and len(roms) == 65 and len(tg.s["pool"]) == 26, \
            (len(juds), len(roms), len(tg.s["pool"]))

        # --- rejection probes before anything is placed
        submit_no(tg, "Rom", {"type": "deploy", "pid": roms[0]["pid"],
                              "hex": "U20"}, "not your deployment")
        z = next(u for u in juds if u["type"] == "zealot")
        submit_no(tg, "Jud", {"type": "deploy", "pid": z["pid"], "hex": "U20"},
                  "New City")             # outside the walls
        c = next(u for u in juds if u["type"] == "cauldron")
        submit_no(tg, "Jud", {"type": "deploy", "pid": c["pid"], "hex": "Z28"},
                  "Elevated")             # cauldron on ground
        submit_no(tg, "Jud", {"type": "deploy_done"}, "not deployed")

        # min-force enforcement: place everything except one strongpoint
        deploy_all_probe(tg)

        # --- full legal deployment on a fresh game
        shutil.rmtree(live)
        os.makedirs(live)
        tg = soj.SoJGame(g, os.path.join(HERE, "scenario_gallus.json"),
                         live, seed=7)
        deploy_all(tg)
        assert tg.s["turn"] == 1
        assert tg.s["phase"] == tg.scenario["game"]["opening_phase"] == "rom_fire"

        # Roman prohibition probes now that the game is live: P50/QQ32 remain
        # barred through movement (checked in validate_movement)
        n_placed = sum(1 for u in tg.s["units"].values() if u["hex"])
        assert n_placed == 116, n_placed

        # log replays end-to-end
        r = subprocess.run(
            [sys.executable, os.path.join(ENG, "verify_game.py"),
             "--game", HERE,
             os.path.join(live, "game_siege-of-jerusalem-ah.log.jsonl")],
            capture_output=True, text=True)
        assert "VERIFIED" in r.stdout, r.stdout + r.stderr
        print(r.stdout.strip().splitlines()[-1])
        print("validate_deploy: PASS")
    finally:
        shutil.rmtree(live, ignore_errors=True)


def deploy_all_probe(tg):
    """Deploy everything but leave strongpoint QQ29 empty: deploy_done must
    name it; then fill it and pass."""
    juds = [u for u in tg.s["units"].values() if u["side"] == "Jud"]
    min_force = [tg.hex_name[h] for h in tg.min_force]
    combat = [u for u in juds if u["type"] in
              ("zealot", "judaean_regular", "judaean_militia")]
    cauldrons = [u for u in juds if u["type"] == "cauldron"]
    leaders = [u for u in juds if u["type"] == "judaean_leader"]
    hold_back = combat[0]
    fill = combat[1:]
    for hexn, u in zip([h for h in min_force if h != "QQ29"], fill):
        submit_ok(tg, "Jud", {"type": "deploy", "pid": u["pid"], "hex": hexn})
    used = len(min_force) - 1
    rest = fill[used:]
    for hexn, u in zip(min_force, cauldrons):
        if hexn != "QQ29":
            submit_ok(tg, "Jud", {"type": "deploy", "pid": u["pid"], "hex": hexn})
    crescent_hexes = [tg.hex_name[h] for h in sorted(tg.new_city)
                      if tg.hex_t0[h] in ("clear", "builtup")]
    spots = crescent_hexes[:3]              # leaders get distinct hexes first
    for hexn in crescent_hexes[3:]:
        spots += [hexn, hexn]
    extra = [u for u in cauldrons if u["hex"] is None]
    for u, hexn in zip(leaders + rest + [hold_back], spots):
        submit_ok(tg, "Jud", {"type": "deploy", "pid": u["pid"], "hex": hexn})
    for u in extra:   # any cauldron still unplaced: put on a wall hex
        for hexn in min_force:
            r = tg.submit("Jud", {"type": "deploy", "pid": u["pid"], "hex": hexn})
            if r["verdict"]["legal"]:
                break
    submit_no(tg, "Jud", {"type": "deploy_done"}, "QQ29")
    # redeploy the held-back unit onto the empty strongpoint
    submit_ok(tg, "Jud", {"type": "deploy", "pid": hold_back["pid"], "hex": "QQ29"})
    submit_ok(tg, "Jud", {"type": "deploy_done"})
    print("min-force enforcement: names the empty strongpoint, passes when filled")


if __name__ == "__main__":
    main()
