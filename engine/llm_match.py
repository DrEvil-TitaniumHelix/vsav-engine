"""
llm_match.py - Head-to-head match driver: two commanders, N games,
sides alternating each game, every log verified before the result counts.

A commander is a provider spec:
    policy              the shipped policy AI (no LLM)
    mock                keyless dry-run transport (valid empty plan -> policy
                        plays the turn; exercises the whole LLM pipeline)
    claude[:model]      Anthropic API (default claude-fable-5), needs
                        ANTHROPIC_API_KEY
    openai[:model]      OpenAI API (default gpt-5.6), needs OPENAI_API_KEY

Example - GPT-5.6 vs Fable 5, two games, sides swapped between them:
    python engine/llm_match.py --game games/blue-and-gray-chickamauga \
        --out runs/gpt_vs_fable --a openai:gpt-5.6 --b claude:claude-fable-5 \
        --games 2

The gate treats both commanders exactly like humans: plans compile into
proposals, every proposal is validated, illegal ones are inert. After each
game the log is replayed through verify_game.verify; an unverifiable game
FAILS the match. The per-side orders logs (plans + commentary + token usage)
land next to each game log, ready for render_movie.py subtitles.

Families: bluegray (Chickamauga) - the family the Plan DSL pilots. Other
families join here as their compilers land in plans.py.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gamespec             # noqa: E402
import bluegray as bg_mod   # noqa: E402
import plans                # noqa: E402
import llm_planner          # noqa: E402
import verify_game          # noqa: E402

KEY_FOR = {"claude": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}


def make_planner(spec, effort, orders_log):
    prov, _, model = spec.partition(":")
    if prov == "policy":
        return None
    if prov == "mock":
        tr = llm_planner.mock_transport()
    elif prov == "claude":
        tr = llm_planner.claude_transport(model or llm_planner.DEFAULT_MODEL,
                                          effort)
    elif prov == "openai":
        tr = llm_planner.openai_transport(model or "gpt-5.6")
    else:
        raise SystemExit(f"unknown provider '{prov}' "
                         "(use policy | mock | claude[:model] | openai[:model])")
    return llm_planner.LLMPlanner(transport=tr, orders_log=orders_log)


def preflight(*specs):
    for s in specs:
        var = KEY_FOR.get(s.partition(":")[0])
        if var and not os.environ.get(var):
            raise SystemExit(
                f"{var} is not set. Refusing to start: an API failure would "
                "silently fall back to the policy AI and the 'match' would be "
                "meaningless. Set the key, or use provider policy/mock.")


def find_scenario(game_dir):
    for cand in sorted(os.listdir(game_dir)):
        if cand.startswith("scenario") and cand.endswith(".json"):
            return os.path.join(game_dir, cand)
    raise SystemExit(f"no scenario*.json in {game_dir}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--a", required=True, help="commander A provider spec")
    ap.add_argument("--b", required=True, help="commander B provider spec")
    ap.add_argument("--games", type=int, default=2)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--max-gts", type=int, default=None)
    ap.add_argument("--effort", default=llm_planner.DEFAULT_EFFORT,
                    help="reasoning effort for claude transports")
    a = ap.parse_args()

    preflight(a.a, a.b)
    game = gamespec.Game(a.game)
    scen = find_scenario(a.game)
    gkey = os.path.basename(os.path.normpath(game.dir))
    sides = game.side_order
    if len(sides) != 2:
        raise SystemExit("match driver needs a 2-side game")

    report = {"game": a.game, "a": a.a, "b": a.b, "seed": a.seed, "games": []}
    tally = {"A": 0, "B": 0, "draw": 0, "unfinished": 0}
    os.makedirs(a.out, exist_ok=True)

    for g in range(a.games):
        a_side = sides[g % 2]
        b_side = game.enemy(a_side)
        live = os.path.join(a.out, f"g{g + 1:02d}_A-{a_side.lower()}")
        os.makedirs(live, exist_ok=True)
        planners, stats = {}, {}
        for side, spec, tag in ((a_side, a.a, "A"), (b_side, a.b, "B")):
            pl = make_planner(spec, a.effort,
                              os.path.join(live, f"orders_{side.lower()}.jsonl"))
            if pl:
                planners[side] = pl
                stats[tag] = pl
        print(f"game {g + 1}/{a.games}: A={a.a} as {a_side}, "
              f"B={a.b} as {b_side}, seed {a.seed + g}")
        t0 = time.time()
        tg = bg_mod.BlueGrayGame(game, scen, live, seed=a.seed + g)
        turn, _ = plans.play_game(tg, planners, max_turns=a.max_gts)

        log_path = os.path.join(live, f"game_{gkey}.log.jsonl")
        ok, msg = verify_game.verify(a.game, log_path)
        winner = tg.s["winner"] if tg.s["over"] else None
        outcome = ("A" if winner == a_side else
                   "B" if winner == b_side else
                   "draw" if winner else "unfinished")
        tally[outcome] += 1
        entry = {"n": g + 1, "a_side": a_side, "seed": a.seed + g,
                 "turns": tg.s["turn"], "over": tg.s["over"],
                 "winner": winner, "outcome": outcome,
                 "vp": tg.s["vp"], "verified": bool(ok),
                 "verify_msg": str(msg)[:300],
                 "wall_s": round(time.time() - t0, 1),
                 "log": log_path}
        for tag, pl in stats.items():
            entry[f"{tag.lower()}_llm"] = {
                "calls": pl.calls, "fallbacks": pl.fallbacks,
                "usage": pl.usage_total}
        report["games"].append(entry)
        print(f"  -> {outcome} (winner={winner}, vp={tg.s['vp']}, "
              f"GT{tg.s['turn']}, verified={'PASS' if ok else 'FAIL: ' + str(msg)})")
        if not ok:
            report["verify_failure"] = entry
            break

    report["tally"] = tally
    rp = os.path.join(a.out, "match_report.json")
    with open(rp, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    print(f"\nMATCH: A({a.a}) {tally['A']} - {tally['B']} B({a.b})"
          + (f", {tally['draw']} draw" if tally["draw"] else "")
          + (f", {tally['unfinished']} unfinished" if tally["unfinished"] else ""))
    print(f"report: {rp}")
    sys.exit(0 if all(e["verified"] for e in report["games"]) else 1)


if __name__ == "__main__":
    main()
