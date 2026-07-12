"""
session_play.py - Interactive commander driver: a human OR an interactive
LLM session (e.g. Claude Code) plays one side through the Plan DSL, the
shipped policy AI plays the other. State resumes from disk, so each
invocation advances the game until it next needs a plan:

  python engine/session_play.py --game games/<dir> --live <dir> \
         --side Union [--seed 1]

  exit 0  game over (result printed)
  exit 2  a plan is needed: the briefing was written to
          <live>/briefing_gt<N>_<side>.txt and printed; write the plan to
          <live>/plan_gt<N>_<side>.json  ({"commentary": ..., "orders": [...]})
          and re-run
  exit 3  the submitted plan failed compile-check (problems printed; the
          bad file was renamed *.rejected so the next run re-prompts)

Every compiled order passes the legality gate; the game log accumulates in
<live>/ and replays byte-exact through verify_game.py. Commander plans and
commentary are appended to <live>/orders_<side>.jsonl.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gamespec            # noqa: E402
import bluegray as bg_mod   # noqa: E402
import plans               # noqa: E402
import llm_planner         # noqa: E402
import strategy_bg          # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", required=True)
    ap.add_argument("--live", required=True)
    ap.add_argument("--side", required=True)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--max-gts", type=int, default=None)
    ap.add_argument("--opponent-theta", default=None,
                    help="JSON file holding a strategy_bg genome (e.g. an "
                    "optimizer status.json 'champion' block); the enemy side "
                    "then plays that strategy instead of the baseline policy")
    a = ap.parse_args()

    opp_theta = None
    if a.opponent_theta:
        blob = json.load(open(a.opponent_theta, encoding="utf-8"))
        opp_theta = blob.get("champion", blob)   # status.json or bare genome

    game = gamespec.Game(a.game)
    scen = None
    for cand in sorted(os.listdir(a.game)):
        if cand.startswith("scenario") and cand.endswith(".json"):
            scen = os.path.join(a.game, cand)
            break
    os.makedirs(a.live, exist_ok=True)
    tg = bg_mod.BlueGrayGame(game, scen, a.live, seed=a.seed)
    orders_log = os.path.join(a.live, f"orders_{a.side.lower()}.jsonl")

    guard = 0
    while not tg.s["over"] and guard < (a.max_gts or tg.turns) * 2 + 6:
        guard += 1
        turn, mover = tg.s["turn"], tg.s["mover"]
        if a.max_gts and turn > a.max_gts:
            break
        if mover != a.side:
            if opp_theta is not None:                # champion plays the enemy
                plans.take_turn(tg, strategy_bg.make_plan(tg, mover, opp_theta))
            else:
                plans.take_turn(tg)                  # policy plays the enemy
            continue
        pfile = os.path.join(a.live, f"plan_gt{turn}_{a.side.lower()}.json")
        bfile = os.path.join(a.live, f"briefing_gt{turn}_{a.side.lower()}.txt")
        if not os.path.exists(pfile):
            briefing = llm_planner._bg_briefing(tg, a.side)
            with open(bfile, "w", encoding="utf-8") as f:
                f.write(briefing)
            print(briefing)
            print(f"\n>>> write your plan to {pfile} and re-run")
            sys.exit(2)
        plan_data = json.load(open(pfile, encoding="utf-8"))
        plan = {"orders": [{k: v for k, v in o.items() if v not in ("", [])}
                           for o in plan_data.get("orders", [])]}
        problems = plans.validate_plan(tg, a.side, plan)
        if problems:
            os.replace(pfile, pfile + ".rejected")
            print("PLAN REJECTED by compile-check:")
            for p in problems:
                print("  -", p)
            sys.exit(3)
        with open(orders_log, "a", encoding="utf-8") as f:
            f.write(json.dumps({"turn": turn, "side": a.side,
                                "commentary": plan_data.get("commentary", ""),
                                "plan": plan}) + "\n")
        log = plans.take_turn(tg, plan)
        rej = [e for e in log if not e.get("legal", True)]
        print(f"GT{turn} {a.side}: {len(log)} actions submitted "
              f"({len(rej)} rejected by the gate), vp={tg.s['vp']}")

    print(f"\nGAME {'OVER' if tg.s['over'] else 'PAUSED'}: turn {tg.s['turn']}, "
          f"vp={tg.s['vp']}, winner={tg.s['winner']}")
    gkey = os.path.basename(os.path.normpath(game.dir))
    print(f"log: {os.path.join(a.live, f'game_{gkey}.log.jsonl')}")
    sys.exit(0)


if __name__ == "__main__":
    main()
