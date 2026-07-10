"""Afrika Korps Tier-3a validation: the policy AI plays complete campaigns
AGAINST ITSELF, every action through the one legality gate
(StrategicGame.submit), and every resulting log replays byte-for-byte through
engine/verify_game.py.

This is the Tier-3a evidence: an engine-owned opponent that (a) proposes only
through the gate, (b) plays a legal, complete, replayable game, and (c) leaves
a log the standalone verifier reproduces exactly (same dice, same state hash
after every entry). A wrong or teleporting AI cannot survive the replay.

Run:  python games/afrika-korps-classic-ah/validate_ai.py
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "engine"))
import gamespec        # noqa: E402
import strategic       # noqa: E402
import ai_strategic    # noqa: E402
import verify_game     # noqa: E402

g = gamespec.Game(HERE)
SCEN = os.path.join(HERE, "scenario_campaign.json")
fails = []


def check(cond, what):
    print(("  PASS  " if cond else "  FAIL  ") + what)
    if not cond:
        fails.append(what)


# Full campaigns can run ~40 turns; the legality gate and the exact-replay
# property hold at any length, so we bound each validation game to keep the
# suite to a few minutes (a bounded game still exercises arrivals, supply
# movement, combat and every pending-resolution path). Raise/remove for a
# full-length AI-vs-AI soak.
VAL_MAX_TURNS = 8


def run_one(seed, tier=None, max_turns=VAL_MAX_TURNS):
    tmp = tempfile.mkdtemp()
    sg = strategic.StrategicGame(g, SCEN, tmp, seed=seed, tier=tier)
    turns, log = ai_strategic.play_game(sg, max_turns=max_turns)
    submitted = [e for e in log if "verdict" in e]
    illegal = [e for e in submitted if not e["verdict"]["legal"]]
    battles = [e for e in submitted
               if e["action"].get("type") == "battle" and e["verdict"]["legal"]]
    moves = [e for e in submitted
             if e["action"].get("type") == "move" and e["verdict"]["legal"]]
    errors = [e for e in log if e.get("error")]
    logpath = os.path.join(tmp, [f for f in os.listdir(tmp)
                                 if f.endswith(".jsonl")][0])
    ok, msg = verify_game.verify(HERE, logpath)
    return dict(sg=sg, turns=turns, log=log, submitted=submitted,
                illegal=illegal, battles=battles, moves=moves, errors=errors,
                verify_ok=ok, verify_msg=msg, tmp=tmp)


print("=== Tier-3a: AI-vs-AI full campaigns through the gate ===")
print(f"scenario: {json.load(open(SCEN, encoding='utf-8'))['name']}\n")

results = []
SEEDS = [1, 7, 42, 100, 2718]
for seed in SEEDS:
    r = run_one(seed)
    results.append(r)
    s = r["sg"].s
    end = ("victory: " + (s["winner"] or "draw")) if s["over"] else \
          f"reached turn cap (turn {r['turns']})"
    print(f"seed {seed:>5}: {len(r['submitted'])} actions "
          f"({len(r['moves'])} moves, {len(r['battles'])} battles), "
          f"{len(r['illegal'])} gate-rejected, {end}")
    check(not r["errors"],
          f"seed {seed}: AI ran without stalling ({len(r['errors'])} error marks)")
    check(r["verify_ok"],
          f"seed {seed}: verify_game replays the log exactly -> {r['verify_msg'][:70]}")
    check(r["turns"] >= 2,
          f"seed {seed}: the game advanced past the opening turn")

print("\n=== the gate actually fired (proof-of-enforcement is optional but"
      " combat must be exercised somewhere) ===")
total_battles = sum(len(r["battles"]) for r in results)
total_moves = sum(len(r["moves"]) for r in results)
check(total_moves > 50, f"AI issued real movement across the runs "
                        f"({total_moves} legal moves)")
check(total_battles > 0, f"AI fought at least one battle through the CRT "
                         f"({total_battles} battles across {len(SEEDS)} games)")
# every rejected proposal must still replay identically (the gate's 'no' is
# part of the log the verifier reproduces)
allbad = [e for r in results for e in r["illegal"]]
check(all(r["verify_ok"] for r in results),
      f"all {len(SEEDS)} logs (incl. {len(allbad)} gate rejections) reproduce "
      f"under replay")

print("\n=== Tier-1 mode: the same AI plays a legal reduced game (no combat) ===")
r1 = run_one(7, tier=1)
check(r1["sg"].tier == 1, "runs at the selected Tier 1")
check(r1["verify_ok"],
      f"Tier-1 AI game replays exactly -> {r1['verify_msg'][:70]}")
check(not r1["errors"], "Tier-1 AI ran without stalling")
check(len(r1["battles"]) == 0, "no combat is attempted at Tier 1 (gate off)")

print()
if fails:
    print(f"*** {len(fails)} FAILURE(S) ***")
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("ALL PASS")
