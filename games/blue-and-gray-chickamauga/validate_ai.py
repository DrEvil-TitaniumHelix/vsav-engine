"""Tier-3 evidence: AI-vs-AI Chickamauga campaigns through the gate.

For each seed: the full 15-GT campaign (or --smoke: 4 GTs) must COMPLETE with
no stalls, produce battles, and the whole log must replay BYTE-EXACT through
engine/verify_game.py (every verdict, every die, every state hash). A Tier-1
game (no combat) must also complete.

Run:  python games/blue-and-gray-chickamauga/validate_ai.py [--smoke]
"""
import json, os, sys, tempfile, time

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..")))
from engine import gamespec, bluegray, ai_bluegray, verify_game

HERE = os.path.dirname(os.path.abspath(__file__))
G = gamespec.load(HERE)
SCEN = os.path.join(HERE, "scenario_chickamauga.json")
SMOKE = "--smoke" in sys.argv
SEEDS = [1] if SMOKE else [1, 7, 42, 100, 2718]
MAXT = 4 if SMOKE else None

fails = []
def check(cond, what):
    if not cond:
        fails.append(what)
    print(("PASS " if cond else "FAIL ") + what)

for seed in SEEDS:
    t0 = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        bg = bluegray.BlueGrayGame(G, SCEN, tmp, seed=seed)
        turns, log = ai_bluegray.play_game(bg, max_turns=MAXT)
        dt = time.time() - t0
        stalled = any(e.get("error") for e in log)
        n_batt = bg.s["battle_no"]
        n_rej = sum(1 for e in log if not e.get("legal", True))
        done = bg.s["over"] or (MAXT and bg.s["turn"] > MAXT)
        print(f"  seed {seed}: {bg.s['turn'] - 1} GTs, {n_batt} battles, "
              f"{len(log)} actions ({n_rej} rejected), vp={bg.s['vp']}, "
              f"winner={bg.s['winner']}, {dt:.0f}s")
        check(not stalled, f"seed {seed}: no stalls")
        check(done, f"seed {seed}: game ran to completion")
        check(n_batt >= 1, f"seed {seed}: at least one battle fought ({n_batt})")
        gkey = os.path.basename(os.path.normpath(G.dir))
        okv, msg = verify_game.verify(HERE, os.path.join(tmp, f"game_{gkey}.log.jsonl"))
        check(okv, f"seed {seed}: verify_game byte-exact replay"
                   + ("" if okv else f" - {msg}"))

# Tier-1 game (no combat gate): must also complete
with tempfile.TemporaryDirectory() as tmp:
    bg = bluegray.BlueGrayGame(G, SCEN, tmp, seed=5, tier=1)
    turns, log = ai_bluegray.play_game(bg, max_turns=3 if SMOKE else 6)
    check(not any(e.get("error") for e in log), "tier-1 game: no stalls")
    gkey = os.path.basename(os.path.normpath(G.dir))
    okv, msg = verify_game.verify(HERE, os.path.join(tmp, f"game_{gkey}.log.jsonl"))
    check(okv, "tier-1 game: verify_game byte-exact replay"
               + ("" if okv else f" - {msg}"))

# TurnStepper == take_turn: identical action stream
with tempfile.TemporaryDirectory() as tA, tempfile.TemporaryDirectory() as tB:
    a = bluegray.BlueGrayGame(G, SCEN, tA, seed=9)
    b = bluegray.BlueGrayGame(G, SCEN, tB, seed=9)
    la = ai_bluegray.take_turn(a)
    st = ai_bluegray.TurnStepper(b)
    lb = []
    while not st.done():
        lb.append(st.step())
    same = [e["action"] for e in la] == [e["action"] for e in lb]
    check(same and a.state_hash() == b.state_hash(),
          f"TurnStepper action stream identical to take_turn ({len(la)}=={len(lb)})")

print()
if fails:
    print(f"{len(fails)} FAILURES")
    sys.exit(1)
print("ALL PASS")
