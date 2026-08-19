import json
import os
import random
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "engine"))
import gamespec  # noqa: E402
from naw import NawGame  # noqa: E402
import ai_naw as ai  # noqa: E402
import verify_game  # noqa: E402

G = gamespec.Game(HERE)
SCEN = os.path.join(HERE, "scenario_2nd_ed.json")
SMOKE = "--smoke" in sys.argv or "--fast" in sys.argv
SEEDS = [1, 8] if SMOKE else [1, 5, 8, 11, 14]
ok = True


def check(cond, msg):
    global ok
    print(("PASS  " if cond else "FAIL  ") + msg)
    ok = ok and bool(cond)


results = {}
alllogs = []
for seed in SEEDS:
    t0 = time.time()
    tmp = tempfile.mkdtemp()
    tg = NawGame(G, SCEN, tmp, seed=seed)
    turns, log = ai.play_game(tg)
    errors = [e for e in log if e.get("error")]
    rejected = sum(1 for e in log if not e.get("legal", True))
    legal = sum(1 for e in log if e.get("legal"))
    kinds = {e["action"]["type"] for e in log if e.get("legal")}
    alllogs += log
    s = tg.s
    check(not errors and s["over"] and s["winner"] in ("Fr", "Al", "draw"),
          f"seed {seed}: game complete (turn {turns}, winner {s['winner']}, losses {s['losses']}, "
          f"exited {len(s['exited'])}, demoralized {s['demoralized']}, {legal} legal / {rejected} rejected, "
          f"{time.time() - t0:.0f}s)")
    check({"move", "end_movement", "battle", "end_phase", "reinforce"} <= kinds,
          f"seed {seed}: action families exercised {sorted(kinds)}")
    check(rejected == 0, f"seed {seed}: zero refusals - every proposal legal on first submission")
    okv, msg = verify_game.verify(HERE, tg.log_path)
    check(okv, f"seed {seed}: {msg}")
    results[seed] = (s["winner"], dict(s["losses"]), len(s["exited"]), s["battle_no"])

winners = {r[0] for r in results.values()}
check(len(winners) >= 2 and all(r[3] >= 8 for r in results.values()),
      f"AI vs AI games are contested: winners {sorted(winners)}, battles per game {[r[3] for r in results.values()]}")
check(all(r[1]["Fr"] + r[1]["Al"] >= 30 for r in results.values()),
      f"AI vs AI games are bloody (>= 30 CS destroyed each): {[r[1] for r in results.values()]}")
if 8 in results:
    check(results[8][0] == "Fr" and results[8][2] >= 7,
          f"seed 8: French win by demoralization + seven exits ({results[8]})")

hh = []
for _ in range(2):
    tg2 = NawGame(G, SCEN, tempfile.mkdtemp(), seed=2)
    ai.play_game(tg2, max_turns=2)
    hh.append(tg2.state_hash())
check(hh[0] == hh[1] and tg2.s["turn"] >= 2,
      f"seed 2: two-turn policy replay is deterministic ({hh[0]}, n={tg2.s['n']})")

_XP = ("import sys,tempfile;sys.path.insert(0,%r);import gamespec,ai_naw;"
       "from naw import NawGame;g=gamespec.Game(%r);t=NawGame(g,%r,tempfile.mkdtemp(),seed=2);"
       "ai_naw.play_game(t,max_turns=3);print(t.state_hash(),t.s['n'])"
       % (os.path.join(ROOT, "engine"), HERE, SCEN))
xp = []
for hs in ("11", "22"):
    env = dict(os.environ, PYTHONHASHSEED=hs)
    xp.append(subprocess.run([sys.executable, "-c", _XP], capture_output=True, text=True, env=env).stdout.strip())
check(xp[0] == xp[1] and xp[0],
      f"seed 2: three-turn policy game identical across processes with different PYTHONHASHSEED ({xp[0]} vs {xp[1]})")

wa = NawGame(G, SCEN, tempfile.mkdtemp(), seed=9)
wb = NawGame(G, SCEN, tempfile.mkdtemp(), seed=9)
log_a = ai.take_turn(wa)
stepper = ai.TurnStepper(wb)
log_b = []
while not stepper.done():
    e = stepper.step()
    if e:
        log_b.append(e)
sa = [(e["side"], json.dumps(e["action"], sort_keys=True)) for e in log_a]
sb = [(e["side"], json.dumps(e["action"], sort_keys=True)) for e in log_b]
check(sa == sb and sa, f"TurnStepper action stream identical to take_turn ({len(sa)} == {len(sb)})")
check(wa.state_hash() == wb.state_hash() and wa.s["mover"] == "Al",
      "state hashes identical after the French Player-Turn; the Allied Player-Turn is next")

pend = NawGame(G, SCEN, tempfile.mkdtemp(), seed=1)
_, plog = ai.play_game(pend)
pk = {}
for e in plog:
    t = e["action"]["type"]
    if t in ("retreat", "exchange_loss", "advance"):
        pk[t] = pk.get(t, 0) + 1
check(pk.get("retreat", 0) > 0 and pk.get("advance", 0) > 0,
      f"seed 1: pending decisions answered by the AI {pk}")
by = {}
for e in alllogs:
    by.setdefault(e["side"], set()).add(e["action"]["type"])
check("retreat" in by.get("Al", set()) and "retreat" in by.get("Fr", set()),
      "both seats choose retreats (victor decides direction, defender after Ar)")

theta = dict(ai.DEFAULTS, aggression=0.25, risk=1.2, north_drive=1.5, exit_turn=3.0, exit_weak=7.0)
tg3 = NawGame(G, SCEN, tempfile.mkdtemp(), seed=1)
turns, log = ai.play_game(tg3, max_turns=5, thetas={"Fr": theta})
check(not any(e.get("error") for e in log) and (turns >= 5 or tg3.s["over"]),
      f"theta-driven game runs 5 turns without stalls (n={tg3.s['n']}, exited {len(tg3.s['exited'])})")
tg4 = NawGame(G, SCEN, tempfile.mkdtemp(), seed=1)
ai.play_game(tg4, max_turns=5)
check(tg3.state_hash() != tg4.state_hash() and len(tg3.s["exited"]) > len(tg4.s["exited"]),
      f"theta changes play: runner theta exited {len(tg3.s['exited'])} by turn 5 vs baseline {len(tg4.s['exited'])}")
okv, msg = verify_game.verify(HERE, tg3.log_path)
check(okv, f"theta game: {msg}")

import families  # noqa: E402
import plans  # noqa: E402
import strategy_naw as strat  # noqa: E402
import optimize  # noqa: E402
import champion  # noqa: E402
fam = families.for_game(G)
check(fam["kind"] == "naw" and fam["strategy"] is strat and fam["ai"] is ai and fam["game_cls"] is NawGame,
      "families.for_game registers the naw family (ai_naw + strategy_naw + NawGame)")
lo = {n: a for n, a, _, _ in strat.GENES}
hi = {n: b for n, _, b, _ in strat.GENES}
check(all(n in ai.DEFAULTS for n in lo) and strat.baseline() == {n: ai.DEFAULTS[n] for n in lo}
      and set(lo) == set(ai.DEFAULTS),
      f"{len(strat.GENES)} genes == ai_naw.DEFAULTS; baseline == the shipped policy")
check(all(lo[n] <= ai.DEFAULTS[n] <= hi[n] for n in lo), "every default lies inside its gene range")
check(set(strat.GENE_PROSE) == set(lo), "GENE_PROSE covers every gene")
rng = random.Random(7)
pop = strat.corners() + [strat.random_theta(rng) for _ in range(5)]
pop += [strat.mutate(t, rng) for t in pop] + [strat.crossover(pop[0], pop[1], rng)]
check(all(lo[n] <= t[n] <= hi[n] for t in pop for n in lo) and len(strat.corners()) == 8,
      f"corners/random/mutate/crossover stay inside gene ranges ({len(pop)} thetas)")
tp = NawGame(G, SCEN, tempfile.mkdtemp(), seed=2)
plans.play_game(tp, {sd: strat.StrategyPlanner(strat.baseline()) for sd in ("Fr", "Al")}, max_turns=2)
check(tp.state_hash() == hh[0],
      "plans.play_game + StrategyPlanner(baseline) reproduces the shipped-policy game hash")
t0 = time.time()
res = optimize.play_one((HERE, strat.corners()[0], None, 8, None))
check(res["over"] and "Fr" in res["vp"] and "cs" in res["vp"]["Fr"] and isinstance(res["margin_a"], float),
      f"optimize.play_one full game (hammer vs baseline, seed 8): winner {res['winner']} margin_a {res['margin_a']:+.1f} "
      f"vp {res['vp']} ({time.time() - t0:.0f}s)")
mwin = fam["margin"]({"Fr": {"cs": 45, "exited": 7, "won": True}, "Al": {"cs": 20, "won": False}}, G.side_order)
mloss = fam["margin"]({"Fr": {"cs": 10, "exited": 0, "won": False}, "Al": {"cs": 41, "won": True}}, G.side_order)
mdraw = fam["margin"]({"Fr": {"cs": 30, "exited": 2, "won": False}, "Al": {"cs": 30, "won": False}}, G.side_order)
check(mwin > 100 > mdraw > 0 > -100 > mloss,
      f"margin fn: French win {mwin:+.1f}, even race with exits {mdraw:+.1f}, Allied win {mloss:+.1f}")
check(champion.validated(HERE) and champion.genome(HERE) is None and champion.plan_for(tp) is None,
      "playbook present, baseline retained: champion.genome None, plan_for None -> the AI seat plays the shipped policy")
_man = json.load(open(os.path.join(HERE, "playbook", "manifest.json"), encoding="utf-8"))
_bar = _man["earned_by"]["graduation_bar"]
check("NOT MET" in _bar["result"] and champion.graduated(HERE) is None,
      f"graduation bar on record as NOT MET and graduated() refuses it: {_bar['result'][:60]}")
_gs = champion.generalship(HERE)
check(_gs["rung"] == 3 and "graduation bar NOT MET" in _gs["evidence"],
      f"generalship 3/10 with the bar verdict in the evidence: {_gs['evidence'][:90]}...")
_cg = json.load(open(os.path.join(HERE, "playbook", "champion.json"), encoding="utf-8"))["portfolio"]
check(_cg["weights"] == [["baseline", 1.0]] and _cg["equilibrium"]["weights"][0][0] == "elite_0"
      and all(not v["met"] for k, v in _cg["graduation_bar"].items() if k.startswith("elite")),
      "champion.json: shipped weights = baseline 1.0, the run's equilibrium + both failed bar candidates recorded inside")
_cm = json.load(open(os.path.join(HERE, "playbook", "corpus", "corpus_manifest.json"), encoding="utf-8"))
_rep = [g for g in _cm["games"] if g["label"] == "baseline_selfplay" and g["seed"] == 970][0]
tc = NawGame(G, SCEN, tempfile.mkdtemp(), seed=970)
ai.play_game(tc)
check(tc.s["n"] == _rep["actions"] and tc.s["winner"] == _rep["winner"] and dict(tc.s["losses"]) == _rep["losses"],
      f"baseline self-play seed 970 reproduces the corpus game exactly: {tc.s['winner']}, {tc.s['n']} actions, losses {dict(tc.s['losses'])}")
_okc, _mc = verify_game.verify(HERE, os.path.join(HERE, "playbook", "corpus", "baseline_selfplay_s970.log.jsonl"))
check(_okc, f"corpus log replays byte-exact through verify_game: {_mc[:70]}")

sys.path.insert(0, os.path.join(ROOT, "ui"))
import server  # noqa: E402
server.LIVE = tempfile.mkdtemp()
server.load_game(HERE)
info = server.route_get("/api/state", {})
avail = set(info["game"]["seats"]["available"])
check(info["game"]["tier"] is None and {"human", "basic"} <= avail and "harness" not in avail,
      f"seat model: NaW offers {sorted(avail)}, no tier field ({info['game']['seats']['pairing']})")
check(info["game"]["seats"]["current"] == {"Fr": "human", "Al": ("champion" if "champion" in avail else "basic")},
      f"default seats: Human French vs the computer Allies ({info['game']['seats']['current']})")
check(info["flow"]["mode"] == "naw" and "tier" not in info["flow"] and info["flow"]["rules_scope"]["banner"].startswith("PLAYABLE"),
      f"flow carries no tier; rules_scope banner: {info['flow']['rules_scope']['banner'][:60]}...")
r = server.route_post("/api/sg_ai_turn", {"side": "Al"})
check(r.get("error") == "it is not Al's decision", f"server refuses the AI for a seat not deciding: {r.get('error')}")
r = server.route_post("/api/sg_ai_turn", {})
check("seat is Human" in (r.get("error") or ""), f"server refuses to play a Human seat: {r.get('error')}")
r = server.route_post("/api/seats", {"seats": {"Fr": "harness"}})
check("not available" in (r.get("error") or ""), f"seat picker refuses a seat the game lacks: {r.get('error')}")
r = server.route_post("/api/seats", {"seats": {"Fr": "basic", "Al": "basic"}})
check(r.get("ok") and r["seats"]["pairing"] == "Computer (Basic AI) vs Computer (Basic AI)",
      f"seats set: {r.get('seats', {}).get('pairing')}")
r = server.route_post("/api/ai_step", {})
first = r["next"]
n = 0
while not r["done"] and n < 400:
    r = server.route_post("/api/ai_step", {})
    n += 1
check(first and first["action"]["type"] in ("move", "exit") and r["flow"]["mover"] == "Al" and r["flow"]["phase"] == "movement",
      f"server /api/ai_step: the French Player-Turn stepped through the gate in {n} steps; Allied Player-Turn next")
r = server.route_post("/api/sg_ai_turn", {})
legal_n = sum(1 for e in r["steps"] if e["legal"])
check(r["flow"]["turn"] == 2 and r["flow"]["mover"] == "Fr" and legal_n == len(r["steps"]),
      f"server /api/sg_ai_turn: Allied Player-Turn {legal_n} legal / {len(r['steps'])} proposals, Game-Turn 2 opens")
r = server.route_post("/api/reset", {"tier": 0})
st = server.route_get("/api/state", {})
check(r.get("ok") and server.SG is not None and st["flow"]["turn"] == 1,
      "reset ignores any tier request: the gate is always on, a fresh game starts at Game-Turn 1")

print("ALL PASS" if ok else "FAILURES ABOVE")
sys.exit(0 if ok else 1)
