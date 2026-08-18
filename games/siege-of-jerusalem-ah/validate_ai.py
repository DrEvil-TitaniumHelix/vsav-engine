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

import subprocess
_XP = ("import sys,tempfile;sys.path.insert(0,%r);import gamespec,ai_soj;"
       "from soj import SoJGame;g=gamespec.Game(%r);t=SoJGame(g,%r,tempfile.mkdtemp(),seed=2,tier=2);"
       "ai_soj.play_game(t,max_turns=3);print(t.state_hash(),t.s['n'])"
       % (os.path.join(ROOT, "engine"), HERE, SCEN))
xp = []
for hs in ("11", "22"):
    env = dict(os.environ, PYTHONHASHSEED=hs)
    xp.append(subprocess.run([sys.executable, "-c", _XP], capture_output=True, text=True, env=env).stdout.strip())
check(xp[0] == xp[1] and xp[0],
      f"seed 2: three-turn policy game identical across processes with different PYTHONHASHSEED ({xp[0]} vs {xp[1]})")

tmp_r = tempfile.mkdtemp()
tr = SoJGame(G, SCEN, tmp_r, seed=1, tier=2)
_, log_r = ai.play_game(tr)
ret = [e for e in log_r if e["action"].get("type") == "resolve_retreat"]
ret_ok = sum(1 for e in ret if e.get("legal"))
check(ret and ret_ok == len(ret),
      f"seed 1: every AI retreat resolution legal on first submission ({ret_ok}/{len(ret)})")

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

import random
import families
import plans
import strategy_soj as strat
import optimize
import champion
fam = families.for_game(G)
check(fam["kind"] == "soj" and fam["strategy"] is strat and fam["ai"] is ai,
      "families.for_game registers the soj family (ai_soj + strategy_soj)")
lo = {n: a for n, a, _, _ in strat.GENES}
hi = {n: b for n, _, b, _ in strat.GENES}
check(all(n in ai.DEFAULTS for n in lo) and strat.baseline() == {n: ai.DEFAULTS[n] for n in lo},
      f"{len(strat.GENES)} genes all read from ai_soj.DEFAULTS; baseline == the shipped policy")
rng = random.Random(7)
pop = strat.corners() + [strat.random_theta(rng) for _ in range(5)]
pop += [strat.mutate(t, rng) for t in pop] + [strat.crossover(pop[0], pop[1], rng)]
check(all(lo[n] <= t[n] <= hi[n] for t in pop for n in lo) and len(strat.corners()) == 5,
      f"corners/random/mutate/crossover stay inside gene ranges ({len(pop)} thetas)")
tmp = tempfile.mkdtemp()
tp = SoJGame(G, SCEN, tmp, seed=2, tier=2)
plans.play_game(tp, {sd: strat.StrategyPlanner(strat.baseline()) for sd in ("Rom", "Jud")}, max_turns=2)
check(tp.state_hash() == hh[0],
      "plans.play_game + StrategyPlanner(baseline) reproduces the shipped-policy game hash")
t0 = time.time()
res = optimize.play_one((HERE, strat.corners()[0], None, 1, 2))
check(res["vp"]["Rom"]["need"] == 10 and res["margin_a"] < 0 and not res["over"],
      f"optimize.play_one 2 turns: margin_a {res['margin_a']:+.2f} ({time.time() - t0:.0f}s)")
mwin = fam["margin"]({"Rom": {"builtup": 10, "need": 10, "won": True, "lost": 20},
                      "Jud": {"lost": 5}}, G.side_order)
mloss = fam["margin"]({"Rom": {"builtup": 9, "need": 10, "won": False, "lost": 0},
                       "Jud": {"lost": 40}}, G.side_order)
check(mwin > 0 > mloss and abs(mloss + 1) < 0.5,
      f"margin fn: Roman win {mwin:+.2f} > 0 > 9-of-10 built-up {mloss:+.2f} (loss tiebreak never flips the sign)")
cp = champion.plan_for(tp)
check(cp is not None and champion.validated(HERE),
      "playbook present: champion.plan_for returns the graduated genome plan (elite_0, GRADUATION MET 2026-08-18) - the AI seat plays it")
tc = SoJGame(G, SCEN, tempfile.mkdtemp(), seed=970, tier=2)
cg = json.load(open(os.path.join(HERE, "playbook", "champion.json"), encoding="utf-8"))
ctheta = cg["portfolio"]["genomes"][cg["portfolio"]["weights"][0][0]] if cg["type"] == "portfolio" else cg["genome"]
ai.play_game(tc, thetas={"Rom": ctheta})
check(tc.s["over"] and tc.s["winner"] == "Rom" and tc._roman_builtup_count() == 20 and tc.s["n"] == 456,
      f"champion (Rom) vs baseline seed 970 reproduces the corpus game exactly: Rom win, built-up {tc._roman_builtup_count()}, {tc.s['n']} actions (corpus: 20 / 456)")

sys.path.insert(0, os.path.join(ROOT, "ui"))
import server
server.LIVE = tempfile.mkdtemp()
server.load_game(HERE)
r = server.route_post("/api/ai_step", {})
first = r["next"]
n = 0
while not r["done"] and n < 400:
    r = server.route_post("/api/ai_step", {})
    n += 1
check(first and first["action"]["type"] == "deploy" and r["flow"]["phase"] == "deploy_rom",
      f"server /api/ai_step: Judaean deployment stepped through the gate in {n} steps")
r = server.route_post("/api/sg_ai_turn", {"side": "Jud"})
check(r.get("error") == "it is not Jud's decision", "server refuses the AI for a seat not deciding")
r = server.route_post("/api/sg_ai_turn", {})
legal_n = sum(1 for e in r["steps"] if e["legal"])
check(r["flow"]["phase"] == "rom_fire" and legal_n == len(r["steps"]) and server.SJ.s["turn"] == 1,
      f"server /api/sg_ai_turn: Roman deployment {legal_n} legal / {len(r['steps'])} proposals, turn 1 opens")
info = server.route_get("/api/state", {})
check(info["game"]["tier"]["active"] == info["game"]["tier"]["earned"] == 3,
      "Full rules mode includes the AI seat (server plumbing value 3 = max)")

print("ALL PASS" if ok else "FAILURES ABOVE")
sys.exit(0 if ok else 1)
