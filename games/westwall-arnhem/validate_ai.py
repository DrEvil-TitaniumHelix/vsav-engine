"""validate_ai.py - Westwall: Arnhem Tier-3 evidence.

AI-vs-AI campaigns at multiple seeds: every game must COMPLETE (all 10 GTs
or an early end), fight battles, never stall, and REPLAY BYTE-EXACT through
engine/verify_game.py (every verdict, die and state hash). Plus: a Tier-1
(no combat) game, and TurnStepper/take_turn equivalence.

Usage: python validate_ai.py [--smoke]
"""
import json, os, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "engine"))
import gamespec                                 # noqa: E402
from westwall import WestwallGame              # noqa: E402
import ai_westwall as ai                        # noqa: E402
import verify_game                              # noqa: E402

G = gamespec.Game(HERE)
SCEN = os.path.join(HERE, "scenario_historical.json")
SMOKE = "--smoke" in sys.argv
SEEDS = [1] if SMOKE else [1, 7, 42, 100, 2718]
ok = True


def check(cond, msg):
    global ok
    print(("PASS  " if cond else "FAIL  ") + msg)
    ok = ok and cond


for seed in SEEDS:
    t0 = time.time()
    tmp = tempfile.mkdtemp()
    ww = WestwallGame(G, SCEN, tmp, seed=seed)
    turns, log = ai.play_game(ww)
    errors = [e for e in log if e.get("error")]
    battles = ww.s["battle_no"]
    rejected = sum(1 for e in log if not e.get("legal", True))
    check(not errors and ww.s["over"],
          f"seed {seed}: game complete ({turns} GTs, {battles} battles, "
          f"{len(log)} actions, {rejected} rejections, "
          f"{time.time() - t0:.0f}s) VP {ww.s['vp']} -> {ww.s.get('level')}")
    check(battles >= 3, f"seed {seed}: battles were fought ({battles})")
    okv, msg = verify_game.verify(HERE, os.path.join(tmp, "game_westwall-arnhem.log.jsonl"))
    check(okv, f"seed {seed}: {msg}")

# Tier-1 game (no combat enforced)
tmp = tempfile.mkdtemp()
ww1 = WestwallGame(G, SCEN, tmp, seed=5, tier=1)
turns, log = ai.play_game(ww1, max_turns=4)
check(not any(e.get("error") for e in log),
      f"tier-1 game runs without stalls ({turns} GTs reached)")
okv, msg = verify_game.verify(HERE, os.path.join(tmp, "game_westwall-arnhem.log.jsonl"))
check(okv, f"tier-1 replay: {msg}")

# TurnStepper == take_turn (identical action stream)
tmp_a = tempfile.mkdtemp()
tmp_b = tempfile.mkdtemp()
wa = WestwallGame(G, SCEN, tmp_a, seed=9)
wb = WestwallGame(G, SCEN, tmp_b, seed=9)
log_a = ai.take_turn(wa)
stepper = ai.TurnStepper(wb)
log_b = []
while not stepper.done():
    e = stepper.step()
    if e:
        log_b.append(e)
sa = [(e["side"], json.dumps(e["action"], sort_keys=True)) for e in log_a]
sb = [(e["side"], json.dumps(e["action"], sort_keys=True)) for e in log_b]
check(sa == sb, f"TurnStepper action stream identical to take_turn "
                f"({len(sa)} == {len(sb)})")
check(wa.state_hash() == wb.state_hash(), "state hashes identical after the turn")

print("ALL PASS" if ok else "FAILURES ABOVE")
sys.exit(0 if ok else 1)
