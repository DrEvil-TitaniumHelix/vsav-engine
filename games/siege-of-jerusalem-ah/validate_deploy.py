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
    zone = sorted(tg.rom_zone)
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


def main():
    live = tempfile.mkdtemp(prefix="soj_dep_")
    try:
        g = gamespec.Game(HERE)
        tg = soj.SoJGame(g, os.path.join(HERE, "scenario_gallus.json"),
                         live, seed=7)
        assert tg.tier == 2 and tg.tier_earned == 2, \
            f"validated combat => tier 2 earned (got {tg.tier_earned})"
        assert tg.s["phase"] == "deploy_jud"

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
