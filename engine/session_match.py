"""
session_match.py - Head-to-head driver: TWO interactive commanders (e.g.
Claude Code as one, Codex CLI or another IDE agent as the other) play one
game against each other through the file protocol. Nobody's side is played
by the policy AI; every turn is a real commander's plan.

  python engine/session_match.py --game games/blue-and-gray-chickamauga \
      --live runs/match1 --a fable5=Union --b opus48=Confederate [--seed 1]

  exit 0  game over (result printed)
  exit 2  a plan is needed; the exit message names WHICH commander. The
          briefing (with champion advisor - maximum knowledge, always) is at
          <live>/briefing_gt<N>_<side>.txt; that commander writes
          <live>/plan_gt<N>_<side>.json and this script is re-run.
  exit 3  the submitted plan failed compile-check (renamed *.rejected)

State resumes from <live> on every invocation, so the two commanders simply
alternate: run script -> if it's your side, answer and re-run; if it's the
opponent's, hand over. Plans + commentary land in orders_<name>.jsonl
sidecars (fuel for render_movie subtitles and grade_commander.py).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gamespec             # noqa: E402
import bluegray as bg_mod   # noqa: E402
import plans                # noqa: E402
import llm_planner          # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", required=True)
    ap.add_argument("--live", required=True)
    ap.add_argument("--a", required=True, help="name=Side, e.g. fable5=Union")
    ap.add_argument("--b", required=True, help="name=Side")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--max-gts", type=int, default=None)
    ap.add_argument("--no-advisor", action="store_true")
    a = ap.parse_args()

    who = {}
    for spec in (a.a, a.b):
        name, _, side = spec.partition("=")
        who[side] = name
    game = gamespec.Game(a.game)
    if set(who) != set(game.side_order):
        raise SystemExit(f"sides must be exactly {game.side_order}, "
                         f"got {sorted(who)}")
    scen = None
    for cand in sorted(os.listdir(a.game)):
        if cand.startswith("scenario") and cand.endswith(".json"):
            scen = os.path.join(a.game, cand)
            break
    os.makedirs(a.live, exist_ok=True)
    tg = bg_mod.BlueGrayGame(game, scen, a.live, seed=a.seed)
    advisor = None if a.no_advisor else llm_planner.load_champion(a.game)

    guard = 0
    while not tg.s["over"] and guard < tg.turns * 2 + 6:
        guard += 1
        turn, side = tg.s["turn"], tg.s["mover"]
        name = who[side]
        if a.max_gts and turn > a.max_gts:
            break
        pfile = os.path.join(a.live, f"plan_gt{turn}_{side.lower()}.json")
        bfile = os.path.join(a.live, f"briefing_gt{turn}_{side.lower()}.txt")
        if not os.path.exists(pfile):
            briefing = llm_planner._bg_briefing(tg, side, advisor=advisor)
            with open(bfile, "w", encoding="utf-8") as f:
                f.write(briefing)
            print(briefing)
            print(f"\n>>> {name.upper()} ({side}) to move, GT {turn}: "
                  f"write your plan to {pfile} and re-run")
            sys.exit(2)
        plan_data = json.load(open(pfile, encoding="utf-8"))
        plan = {"orders": [{k: v for k, v in o.items() if v not in ("", [])}
                           for o in plan_data.get("orders", [])]}
        problems = plans.validate_plan(tg, side, plan)
        if problems:
            os.replace(pfile, pfile + ".rejected")
            print(f"PLAN REJECTED ({name}, {side}, GT {turn}):")
            for p in problems:
                print("  -", p)
            sys.exit(3)
        with open(os.path.join(a.live, f"orders_{side.lower()}.jsonl"),
                  "a", encoding="utf-8") as f:
            f.write(json.dumps({"turn": turn, "side": side,
                                "commander": name,
                                "commentary": plan_data.get("commentary", ""),
                                "plan": plan}) + "\n")
        log = plans.take_turn(tg, plan)
        rej = [e for e in log if not e.get("legal", True)]
        print(f"GT{turn} {side} ({name}): {len(log)} actions "
              f"({len(rej)} rejected by the gate), vp={tg.s['vp']}")

    print(f"\nGAME {'OVER' if tg.s['over'] else 'PAUSED'}: turn {tg.s['turn']}, "
          f"vp={tg.s['vp']}, winner={tg.s['winner']}"
          + (f" ({who.get(tg.s['winner'], 'draw')})"
             if tg.s.get("winner") in who else ""))
    gkey = os.path.basename(os.path.normpath(game.dir))
    print(f"log: {os.path.join(a.live, f'game_{gkey}.log.jsonl')}")
    sys.exit(0)


if __name__ == "__main__":
    main()
