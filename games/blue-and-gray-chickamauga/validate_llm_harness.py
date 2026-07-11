"""Stage-3 evidence (CI-safe, no network, no API key): the LLM-planner
harness turns model output into gate-checked play, and every failure mode
falls back to the policy AI without breaking the game.

Checks (all with FAKE transports - determinism is the point here; live
model strength is measured separately by eval_llm.py):
  1. a canned hold-fast plan from the "model" controls Union movement,
     the game completes, and the log replays BYTE-EXACT;
  2. a transport that always raises (no key / API down / refusal) means
     pure-policy fallback: the game is identical to a policy game;
  3. an invalid plan on the first call is repaired via the corrective
     retry (transport called twice, second plan used);
  4. the orders log records plans, commentary, and fallbacks.

Run:  python games/blue-and-gray-chickamauga/validate_llm_harness.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "engine")))
from engine import gamespec, bluegray, ai_bluegray, verify_game  # noqa: E402
import plans  # noqa: E402
import llm_planner  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
G = gamespec.load(HERE)
SCEN = os.path.join(HERE, "scenario_chickamauga.json")
GKEY = os.path.basename(os.path.normpath(G.dir))
MAXT = 4

fails = []


def check(cond, what):
    if not cond:
        fails.append(what)
    print(("PASS " if cond else "FAIL ") + what)


def hold_all_json(tg, side):
    orders = [{"verb": "hold", "units": [u["pid"]], "objective": "", "at": ""}
              for u in sorted(tg._live(side), key=lambda x: x["pid"])
              if tg.cls(u) not in ("train", "artillery")]
    return json.dumps({"commentary": "Stand fast on the start line.",
                       "orders": orders})


def run(planner_union, seed=1):
    tmp = tempfile.mkdtemp(prefix="llmh_")
    bg = bluegray.BlueGrayGame(G, SCEN, tmp, seed=seed)
    plans.play_game(bg, {"Union": planner_union}, max_turns=MAXT)
    return bg, os.path.join(tmp, f"game_{GKEY}.log.jsonl")


# 1. canned plan controls behavior + byte-exact replay
calls = {"n": 0}


class CannedTransport:
    def __call__(self, system_text, user_text, schema):
        calls["n"] += 1
        assert "DOCTRINE" in system_text and "GAME TURN" in user_text
        return self._json, {"in": 1000, "out": 100, "cache_read": 0,
                            "cache_write": 0, "model": "fake"}


canned = CannedTransport()
olog = os.path.join(tempfile.mkdtemp(prefix="llmh_"), "orders.jsonl")
pl = llm_planner.LLMPlanner(transport=canned, orders_log=olog)


def union_planner(tg, side):
    canned._json = hold_all_json(tg, side)
    return pl(tg, side)


bg1, lp1 = run(union_planner)
okv, msg = verify_game.verify(HERE, lp1)
umoves = sum(1 for l in open(lp1, encoding="utf-8") for e in [json.loads(l)]
             if e.get("event") == "action" and e["side"] == "Union"
             and e["action"].get("type") == "move" and e["verdict"]["legal"])
check(okv, "canned-plan game replays byte-exact through verify_game"
      + ("" if okv else f" - {msg}"))
check(umoves == 0, f"hold-fast plan from the fake model froze Union movement "
      f"({umoves} voluntary moves)")
check(calls["n"] == MAXT, f"one model call per Union turn ({calls['n']}=={MAXT})")
check(pl.fallbacks == 0, "no fallbacks on the clean path")

# 2. transport failure -> pure policy fallback, identical to a policy game
def broken(system_text, user_text, schema):
    raise RuntimeError("simulated API failure / missing key")


plb = llm_planner.LLMPlanner(transport=broken)
bg2, lp2 = run(lambda tg, side: plb(tg, side))
with tempfile.TemporaryDirectory() as tmp:
    ref = bluegray.BlueGrayGame(G, SCEN, tmp, seed=1)
    ai_bluegray.play_game(ref, max_turns=MAXT)
check(plb.fallbacks == MAXT and bg2.state_hash() == ref.state_hash(),
      "broken transport falls back to policy every turn; game state "
      "identical to a pure-policy game")

# 3. corrective retry: invalid plan first, valid on second call
class FlakyTransport:
    def __init__(self):
        self.n = 0

    def __call__(self, system_text, user_text, schema):
        self.n += 1
        if self.n == 1:
            bad = json.dumps({"commentary": "bad", "orders":
                              [{"verb": "push", "units": ["No Such Unit"],
                                "objective": "1520", "at": ""}]})
            return bad, {}
        assert "rejected by the compiler" in user_text
        return self._json, {}


flaky = FlakyTransport()
plf = llm_planner.LLMPlanner(transport=flaky)


def flaky_planner(tg, side):
    flaky._json = hold_all_json(tg, side)
    return plf(tg, side)


with tempfile.TemporaryDirectory() as tmp:
    bg3 = bluegray.BlueGrayGame(G, SCEN, tmp, seed=1)
    plan = flaky_planner(bg3, "Union")
check(plan is not None and flaky.n == 2 and plf.fallbacks == 0,
      f"invalid first plan repaired via corrective retry "
      f"(transport calls: {flaky.n}, plan accepted: {plan is not None})")

# 4. orders log content
entries = [json.loads(l) for l in open(olog, encoding="utf-8")]
check(len(entries) == MAXT and all(not e["fallback"] for e in entries)
      and all(e.get("commentary") for e in entries)
      and all(e.get("plan", {}).get("orders") for e in entries),
      f"orders log carries plan+commentary for all {MAXT} turns")

print()
if fails:
    print(f"{len(fails)} FAILURES")
    sys.exit(1)
print("ALL PASS")
