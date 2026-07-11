"""Stage-2 evidence: the Plan DSL compiler plays complete, verifiable,
plan-obedient Chickamauga campaigns through the gate.

Checks:
  1. policy-mirror plans (every unit explicitly ordered every turn) play a
     full campaign: no stalls, battles happen, log replays BYTE-EXACT
     through engine/verify_game.py;
  2. determinism: the same planned game twice = identical final state hash;
  3. plans control behavior: a Union hold-fast doctrine cuts Union
     voluntary movement by more than half vs the mirror game, and the game
     still completes and verifies (the gate, not the plan, stays boss);
  4. compile-time validation catches garbage plans;
  5. strength report: mirror-plan final VPs vs the pure-policy game.

Run:  python games/blue-and-gray-chickamauga/validate_plans.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "engine")))
from engine import gamespec, bluegray, ai_bluegray, verify_game  # noqa: E402
import plans  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
G = gamespec.load(HERE)
SCEN = os.path.join(HERE, "scenario_chickamauga.json")
GKEY = os.path.basename(os.path.normpath(G.dir))

fails = []


def check(cond, what):
    if not cond:
        fails.append(what)
    print(("PASS " if cond else "FAIL ") + what)


def run_game(seed, planners):
    tmp = tempfile.mkdtemp(prefix="plans_")
    bg = bluegray.BlueGrayGame(G, SCEN, tmp, seed=seed)
    turns, log = plans.play_game(bg, planners)
    return bg, log, os.path.join(tmp, f"game_{GKEY}.log.jsonl")


def union_moves(log):
    return sum(1 for e in log
               if e.get("legal") and e["action"].get("type") == "move"
               and e["side"] == "Union")


# 1. policy-mirror plans, both sides, full campaign
mirror = {"Union": plans.policy_mirror_planner,
          "Confederate": plans.policy_mirror_planner}
bg1, log1, lp1 = run_game(1, mirror)
n_rej = sum(1 for e in log1 if not e.get("legal", True))
print(f"  mirror game: {bg1.s['turn'] - 1} GTs, {bg1.s['battle_no']} battles, "
      f"{len(log1)} actions ({n_rej} rejected), vp={bg1.s['vp']}, "
      f"winner={bg1.s['winner']}")
check(bg1.s["over"] and not any(e.get("error") for e in log1),
      "mirror-plan campaign ran to completion, no stalls")
check(bg1.s["battle_no"] >= 1, "mirror-plan campaign fought battles")
okv, msg = verify_game.verify(HERE, lp1)
check(okv, "mirror-plan log replays byte-exact through verify_game"
      + ("" if okv else f" - {msg}"))

# 2. determinism
bg2, log2, _ = run_game(1, mirror)
check(bg1.state_hash() == bg2.state_hash(),
      "same seed + same plans = identical final state hash")

# 3. hold-fast doctrine controls behavior
def union_hold(tg, side):
    return {"orders": [{"verb": "hold", "units": [u["pid"]]}
                       for u in sorted(tg._live(side), key=lambda x: x["pid"])
                       if tg.cls(u) not in ("train", "artillery")]}


bgh, logh, lph = run_game(1, {"Union": union_hold})
mv_mirror, mv_hold = union_moves(log1), union_moves(logh)
print(f"  hold-fast game: vp={bgh.s['vp']}, winner={bgh.s['winner']}; "
      f"Union voluntary moves {mv_hold} vs {mv_mirror} in the mirror game")
check(bgh.s["over"] and not any(e.get("error") for e in logh),
      "hold-fast campaign ran to completion")
okv, msg = verify_game.verify(HERE, lph)
check(okv, "hold-fast log replays byte-exact"
      + ("" if okv else f" - {msg}"))
check(mv_hold < mv_mirror * 0.5,
      f"hold-fast doctrine cut Union voluntary movement by >50% "
      f"({mv_hold} < {mv_mirror}/2)")

# 4. compile-time validation
with tempfile.TemporaryDirectory() as tmp:
    bgv = bluegray.BlueGrayGame(G, SCEN, tmp, seed=1)
    bad = {"orders": [{"verb": "teleport", "units": ["u1"]},
                      {"verb": "push", "units": ["No Such Brigade"],
                       "objective": "1520"},
                      {"verb": "hold", "units": []}]}
    probs = plans.validate_plan(bgv, "Union", bad)
    check(len(probs) == 3, f"validate_plan flags all 3 planted defects ({len(probs)})")
    good = plans.policy_mirror_planner(bgv, "Union")
    check(plans.validate_plan(bgv, "Union", good) == [],
          "policy-mirror plan validates clean")

# 5. strength report (pure-policy reference, same seed)
with tempfile.TemporaryDirectory() as tmp:
    bgp = bluegray.BlueGrayGame(G, SCEN, tmp, seed=1)
    ai_bluegray.play_game(bgp)
    print(f"  strength: mirror-plan vp={bg1.s['vp']} vs pure-policy "
          f"vp={bgp.s['vp']} (seed 1; report only - plans must be "
          f"comparable, not identical)")

print()
if fails:
    print(f"{len(fails)} FAILURES")
    sys.exit(1)
print("ALL PASS")
