"""Stage-3 LIVE evaluation: Claude (claude-fable-5) as plan-proposer vs the
shipped policy AI, full Chickamauga campaigns, seeded and verifiable.

COSTS MONEY and needs Anthropic API credentials (ANTHROPIC_API_KEY).
NOT part of the CI suite - run it deliberately:

  python games/blue-and-gray-chickamauga/eval_llm.py --smoke          # 1 short game
  python games/blue-and-gray-chickamauga/eval_llm.py --seeds 1,7      # full matches, both seatings

Outputs per game (under --out, default eval_llm_out/):
  game_<tag>.log.jsonl    the verified gate log
  orders_<tag>.jsonl      the LLM's plan + commentary per turn
plus a summary table with VP margins vs the same-seed policy-vs-policy
baseline, fallback counts, token usage and a cost estimate.
"""
import argparse
import json
import os
import shutil
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
PRICE_IN, PRICE_OUT = 10.0, 50.0          # claude-fable-5 $/MTok


def margin(bg, side):
    e = bg.game.enemy(side)
    return bg.s["vp"][side] - bg.s["vp"][e]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="1")
    ap.add_argument("--sides", default="Union,Confederate",
                    help="seatings for the LLM")
    ap.add_argument("--model", default=llm_planner.DEFAULT_MODEL)
    ap.add_argument("--effort", default=llm_planner.DEFAULT_EFFORT)
    ap.add_argument("--max-gts", type=int, default=None)
    ap.add_argument("--smoke", action="store_true",
                    help="1 seed, LLM as Union, 4 GTs")
    ap.add_argument("--out", default=os.path.join(HERE, "eval_llm_out"))
    a = ap.parse_args()
    if a.smoke:
        a.seeds, a.sides, a.max_gts = "1", "Union", 4

    if not (os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise SystemExit(
            "No Anthropic credentials found (ANTHROPIC_API_KEY / "
            "ANTHROPIC_AUTH_TOKEN). This evaluation makes real, billed API "
            "calls - set a key and re-run. Rough cost: ~$1-2 per full game "
            f"at {a.model} prices.")

    os.makedirs(a.out, exist_ok=True)
    seeds = [int(x) for x in a.seeds.split(",")]
    sides = a.sides.split(",")
    rows, tok_in, tok_out = [], 0, 0

    for seed in seeds:
        with tempfile.TemporaryDirectory() as tmp:      # policy baseline
            ref = bluegray.BlueGrayGame(G, SCEN, tmp, seed=seed)
            ai_bluegray.play_game(ref, max_turns=a.max_gts)
            base_vp = dict(ref.s["vp"])
        for side in sides:
            tag = f"s{seed}_{side.lower()}"
            olog = os.path.join(a.out, f"orders_{tag}.jsonl")
            if os.path.exists(olog):
                os.remove(olog)
            pl = llm_planner.LLMPlanner(orders_log=olog, model=a.model,
                                        effort=a.effort)
            tmp = tempfile.mkdtemp(prefix="eval_")
            bg = bluegray.BlueGrayGame(G, SCEN, tmp, seed=seed)
            print(f"== seed {seed}: {a.model} commands {side} ==")
            plans.play_game(bg, {side: pl}, max_turns=a.max_gts)
            lp = os.path.join(tmp, f"game_{GKEY}.log.jsonl")
            okv, msg = verify_game.verify(HERE, lp)
            shutil.copy(lp, os.path.join(a.out, f"game_{tag}.log.jsonl"))
            tok_in += pl.usage_total["in"]
            tok_out += pl.usage_total["out"]
            rows.append(dict(
                seed=seed, side=side, vp=dict(bg.s["vp"]),
                winner=bg.s["winner"], verified=okv,
                margin_llm=margin(bg, side),
                margin_policy_baseline=base_vp[side] -
                base_vp[bg.game.enemy(side)],
                calls=pl.calls, fallbacks=pl.fallbacks,
                cache_read=pl.usage_total["cache_read"]))
            print(f"   vp={bg.s['vp']} winner={bg.s['winner']} "
                  f"verified={okv} calls={pl.calls} "
                  f"fallbacks={pl.fallbacks}")
            if not okv:
                print(f"   VERIFY FAILED: {msg}")

    print("\n=== SUMMARY (margin = own VP - enemy VP for the LLM's side) ===")
    print(f"{'seed':>4} {'LLM side':<12} {'LLM margin':>10} "
          f"{'policy baseline':>15} {'delta':>6} {'winner':<12} "
          f"{'fallbacks':>9} verified")
    for r in rows:
        d = r["margin_llm"] - r["margin_policy_baseline"]
        print(f"{r['seed']:>4} {r['side']:<12} {r['margin_llm']:>10} "
              f"{r['margin_policy_baseline']:>15} {d:>+6} "
              f"{str(r['winner']):<12} {r['fallbacks']:>9} {r['verified']}")
    cost = tok_in / 1e6 * PRICE_IN + tok_out / 1e6 * PRICE_OUT
    print(f"\ntokens: {tok_in} in / {tok_out} out; "
          f"estimated spend ${cost:.2f} "
          f"(cache-read tokens billed lower; treat as upper bound)")
    with open(os.path.join(a.out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1)
    print(f"logs + orders + summary -> {a.out}")


if __name__ == "__main__":
    main()
