"""validate_ai.py - Austerlitz (GBoNW) Tier-3 evidence.

AI-vs-AI campaigns at multiple seeds through the REAL gate (submit()
only): every game must COMPLETE (an A15.1 victory or the turn limit),
fight with fire AND shock, answer every window it owns, never stall,
and REPLAY BYTE-EXACT through engine/verify_game.py (every verdict,
die and state hash). Plus: the decider contract (the policy only ever
submits for the side whose decision the game is waiting on - the
honesty property that lets a human keep every decision of their own),
a tier-1 (phase-3 flow) game, tier selection, and TurnStepper /
take_turn equivalence.

Usage: python validate_ai.py [--smoke]
"""
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "engine"))
import gamespec                                 # noqa: E402
from napoleonic import NapoleonicGame           # noqa: E402
import ai_napoleonic as ai                      # noqa: E402
import verify_game                              # noqa: E402

G = gamespec.load(HERE)
SCEN = os.path.join(HERE, "scenario_northern_flank.json")
SMOKE = "--smoke" in sys.argv
SEEDS = [1] if SMOKE else [1, 7, 42, 100, 2718]
ok = True


def check(cond, msg):
    global ok
    print(("PASS  " if cond else "FAIL  ") + msg)
    ok = ok and cond


def fresh(seed, tier=None):
    tmp = tempfile.mkdtemp(prefix="aus_ai_")
    return NapoleonicGame(G, SCEN, tmp, seed=seed, tier=tier), tmp


check(NapoleonicGame(G, SCEN, tempfile.mkdtemp(), seed=0).tier_earned == 3,
      "policy_ai declared in game.json => earned tier 3 [spec #13]")

tot = {"fire": 0, "shock": 0, "windows": 0, "rej": 0}
for seed in SEEDS:
    t0 = time.time()
    g, tmp = fresh(seed)
    check(g.tier == 3 and g.s["schema"] == 4 and g._p4,
          f"seed {seed}: tier-3 game runs the full schema-4 gate")
    # drive the game burst by burst, checking the decider contract on
    # every burst: the policy submits ONLY for the side the game was
    # waiting on when the burst began
    contract = True
    full = []
    guard = 0
    while guard < 5000:
        # exactly flow()'s game-over formula (victory recomputes live
        # until the first turn end stores it)
        v = g.s.get("victory") or g._victory_state()
        if v.get("winner") or g.s["turn"] > g.turns:
            break
        who = g.decider()
        burst = ai.take_turn(g, who)
        if not burst:
            break
        if any(e["side"] != who for e in burst):
            contract = False
        full.extend(burst)
        guard += 1
    errors = [e for e in full if e.get("error")]
    rej = sum(1 for e in full if not e.get("legal", True))
    by_type = {}
    sides = set()
    for e in full:
        if e.get("legal"):
            by_type[e["action"]["type"]] = \
                by_type.get(e["action"]["type"], 0) + 1
            sides.add(e["side"])
    fires = by_type.get("fire", 0)
    shocks = by_type.get("melee", 0) + by_type.get("charge", 0)
    windows = sum(by_type.get(k, 0) for k in (
        "square_choice", "melee_return", "melee_no_return", "melee_stand",
        "return_fire", "decline_return", "reaction_fire", "reaction_move",
        "reaction_charge", "reaction_face", "reaction_reverse",
        "decline_reaction"))
    tot["fire"] += fires
    tot["shock"] += shocks
    tot["windows"] += windows
    tot["rej"] += rej
    v = g.s.get("victory") or g._victory_state()
    done = bool(v.get("winner")) or g.s["turn"] > g.turns
    check(not errors and done,
          f"seed {seed}: game complete (turn {g.s['turn']}, "
          f"{len(full)} actions, {rej} rejections, {fires} fires, "
          f"{shocks} shocks, {windows} window answers, "
          f"{time.time() - t0:.0f}s) -> "
          f"{v.get('winner') or 'turn limit'} {v['counts']}")
    check(contract, f"seed {seed}: decider contract held - every action "
                    "was submitted by the side whose decision it was")
    check(len(sides) == 2, f"seed {seed}: both sides fought "
                           f"({sorted(sides)})")
    okv, msg = verify_game.verify(
        HERE, os.path.join(tmp, "game_austerlitz-gmt.log.jsonl"))
    check(okv, f"seed {seed}: {msg}")

check(tot["fire"] > 0 and tot["shock"] > 0 and tot["windows"] > 0,
      f"across seeds: fire ({tot['fire']}), shock ({tot['shock']}) and "
      f"window decisions ({tot['windows']}) all exercised")

# ------------------------------------------------ tier selection [spec #13]
g1, tmp1 = fresh(5, tier=1)
check(g1.tier == 1 and g1.s["schema"] == 3,
      "tier-1 selection still pins the phase-3 flow (schema 3)")
turns, log = ai.play_game(g1, max_turns=2)
check(not any(e.get("error") for e in log),
      f"tier-1 game runs without stalls ({len(log)} actions to "
      f"turn {g1.s['turn']})")
okv, msg = verify_game.verify(
    HERE, os.path.join(tmp1, "game_austerlitz-gmt.log.jsonl"))
check(okv, f"tier-1 replay: {msg}")

g2, tmp2 = fresh(5, tier=2)
check(g2.tier == 2 and g2.s["schema"] == 4,
      "tier-2 selection keeps the schema-4 gate (AI is an overlay, "
      "the gate is identical [spec #13])")

# ------------------------------------- TurnStepper == take_turn (seed 9)
# 25 decision bursts (both sides, both drivers) must produce identical
# action streams and identical state hashes
ga, tmp_a = fresh(9)
gb, tmp_b = fresh(9)
log_a, log_b = [], []
for _ in range(25):
    if ai._over(ga):
        break
    log_a.extend(ai.take_turn(ga, ga.decider()))
for _ in range(25):
    if ai._over(gb):
        break
    stepper = ai.TurnStepper(gb)
    while not stepper.done():
        e = stepper.step()
        if e:
            log_b.append(e)
sa = [(e["side"], json.dumps(e["action"], sort_keys=True)) for e in log_a]
sb = [(e["side"], json.dumps(e["action"], sort_keys=True)) for e in log_b]
check(sa == sb and len(sa) > 20,
      f"TurnStepper action stream identical to take_turn over 25 bursts "
      f"({len(sa)} == {len(sb)})")
check(ga.state_hash() == gb.state_hash(),
      "state hashes identical after the stepped bursts")

# ------------------- strategy family: baseline genome == shipped policy
# (spec #22: strategy_nap gene baselines are read from
# ai_napoleonic.DOCTRINE; theta=baseline() must reproduce the shipped
# policy's action stream exactly - the optimizer's zero point)
import strategy_nap as sn                       # noqa: E402
gc, _ = fresh(1)
gd, _ = fresh(1)
log_c, log_d = [], []
for _ in range(25):
    if ai._over(gc):
        break
    log_c.extend(ai.take_turn(gc, gc.decider()))
for _ in range(25):
    if ai._over(gd):
        break
    log_d.extend(ai.take_turn(gd, gd.decider(), theta=sn.baseline()))
sc = [(e["side"], json.dumps(e["action"], sort_keys=True)) for e in log_c]
sd = [(e["side"], json.dumps(e["action"], sort_keys=True)) for e in log_d]
check(sc == sd and len(sc) > 20,
      f"strategy_nap.baseline() plays the shipped policy exactly "
      f"({len(sc)} == {len(sd)} actions) [spec #22]")
check(gc.state_hash() == gd.state_hash(),
      "state hashes identical under the baseline genome")

print("ALL PASS" if ok else "FAILURES ABOVE")
sys.exit(0 if ok else 1)
