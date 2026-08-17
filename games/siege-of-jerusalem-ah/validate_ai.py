import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "engine"))
import gamespec
from soj import SoJGame
import ai_soj as ai
import verify_game

G = gamespec.Game(HERE)
SCEN = os.path.join(HERE, "scenario_gallus.json")
SMOKE = "--smoke" in sys.argv
SEEDS = [1]
LOG = "game_siege-of-jerusalem-ah.log.jsonl"
ok = True


def check(cond, msg):
    global ok
    print(("PASS  " if cond else "FAIL  ") + msg)
    ok = ok and cond


hashes = {}
for seed in SEEDS:
    t0 = time.time()
    tmp = tempfile.mkdtemp()
    tg = SoJGame(G, SCEN, tmp, seed=seed, tier=2)
    turns, log = ai.play_game(tg)
    errors = [e for e in log if e.get("error")]
    rejected = sum(1 for e in log if not e.get("legal", True))
    legal = sum(1 for e in log if e.get("legal"))
    kinds = {e["action"]["type"] for e in log if e.get("legal")}
    check(not errors and tg.s["over"] and tg.s["winner"] in ("Rom", "Jud"),
          f"seed {seed}: game complete (turn {turns}, winner {tg.s['winner']}, "
          f"{legal} legal / {rejected} rejected, built-up {tg._roman_builtup_count()}, "
          f"breach {tg.s['breach']}, {time.time() - t0:.0f}s)")
    check({"deploy", "deploy_done", "fire", "move", "melee", "end_phase"} <= kinds,
          f"seed {seed}: action families exercised {sorted(kinds)}")
    check(rejected < legal, f"seed {seed}: legal actions outnumber refusals")
    okv, msg = verify_game.verify(HERE, os.path.join(tmp, LOG))
    check(okv, f"seed {seed}: {msg}")
    hashes[seed] = tg.state_hash()

hh = []
for _ in range(2):
    tmp = tempfile.mkdtemp()
    tg2 = SoJGame(G, SCEN, tmp, seed=2, tier=2)
    ai.play_game(tg2, max_turns=2)
    hh.append(tg2.state_hash())
check(hh[0] == hh[1] and tg2.s["turn"] >= 2,
      f"seed 2: two-turn policy replay is deterministic ({hh[0]}, n={tg2.s['n']})")

tmp_a = tempfile.mkdtemp()
tmp_b = tempfile.mkdtemp()
wa = SoJGame(G, SCEN, tmp_a, seed=9, tier=2)
wb = SoJGame(G, SCEN, tmp_b, seed=9, tier=2)
log_a = ai.take_turn(wa)
stepper = ai.TurnStepper(wb)
log_b = []
while not stepper.done():
    e = stepper.step()
    if e:
        log_b.append(e)
sa = [(e["side"], json.dumps(e["action"], sort_keys=True)) for e in log_a]
sb = [(e["side"], json.dumps(e["action"], sort_keys=True)) for e in log_b]
check(sa == sb, f"TurnStepper action stream identical to take_turn ({len(sa)} == {len(sb)})")
check(wa.state_hash() == wb.state_hash(), "state hashes identical after the deployment turn")

theta = dict(ai.DEFAULTS, sector=0.15, escalade_share=0.6, tower_commit=0.34)
tmp = tempfile.mkdtemp()
tg3 = SoJGame(G, SCEN, tmp, seed=1, tier=2)
plan = ai._plan(tg3, theta)
plan0 = ai._plan(tg3, None)
check(plan["sector"] != plan0["sector"], "theta moves the assault sector")
turns, log = ai.play_game(tg3, max_turns=2, thetas={"Rom": theta, "Jud": theta})
check(not any(e.get("error") for e in log) and turns >= 2,
      f"theta-driven game runs 2 turns without stalls (n={tg3.s['n']})")
okv, msg = verify_game.verify(HERE, os.path.join(tmp, LOG))
check(okv, f"theta game: {msg}")

print("ALL PASS" if ok else "FAILURES ABOVE")
sys.exit(0 if ok else 1)
