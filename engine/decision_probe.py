"""
decision_probe.py - Test 1 of the frontier-model program: do two models,
given the SAME game state and the SAME maximum knowledge (playbook doctrine
+ champion advisor + rules briefing), make DIFFERENT decisions?

The probe replays a fixed REFERENCE game (one neither commander has seen)
and freezes every player-turn decision point. Each commander answers every
decision point independently; answers are directly comparable because the
positions are identical for everyone.

  emit     replay the reference log; write briefing_gt<T>_<side>.txt for
           every decision point (advisor plan included) + COMMANDER.md
           (identical instructions for every commander)
  collect  answer all briefings with an API transport
           (--transport mock|claude[:model]|openai[:model])
           -> answers_<name>/plan_gt<T>_<side>.json
           (interactive commanders - a Claude Code or Codex CLI session -
           write the same files by hand per COMMANDER.md; no collect needed)
  compare  re-replay, compile-check every answer at its exact state, and
           report divergence: per-unit agreement between commanders,
           advisor adoption, invalid-plan counts -> comparison.json

Usage:
  python engine/decision_probe.py emit --game games/blue-and-gray-chickamauga \
      --ref-log runs/ref_game/game_....log.jsonl --out runs/probe1
  python engine/decision_probe.py collect --out runs/probe1 --game ... \
      --ref-log ... --commander mock1 --transport mock
  python engine/decision_probe.py compare --game ... --ref-log ... \
      --out runs/probe1 --answers fable5,opus48

Families: bluegray. Zero API keys needed for emit/compare/file-mode.
"""
import argparse
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gamespec             # noqa: E402
import bluegray as bg_mod   # noqa: E402
import plans                # noqa: E402
import llm_planner          # noqa: E402

COMMANDER_MD = """# Commander instructions (identical for every model under test)

You are a commander being probed: for every decision point of a reference
game of {name} you write the plan YOU would issue for the side to move.

## Knowledge - use all of it
1. Read the playbook: {playbook} (manifest, doctrine.md, champion.json,
   corpus/). This is the accumulated expertise for this game.
2. Each briefing already contains the CHAMPION ADVISOR's proposed plan for
   that turn. Adopt, modify, or override it - say which, and why, in your
   commentary.

## The plan language (schema-enforced for API models; follow it exactly)
{plan_language}

## Procedure
- Briefings are in {briefdir}, one per decision point, named
  briefing_gt<TURN>_<side>.txt, in game order. Work through ALL of them.
- For each briefing write answers_<YOURNAME>/plan_gt<TURN>_<side>.json:
  {{"commentary": "<2-4 sentences: intent + advisor verdict>",
    "orders": [{{"verb": "push|hold|standoff|run_exit", "units": ["u12"],
                 "objective": "CCRR or \\"\\"", "at": "CCRR or \\"\\""}}]}}
- Decide each briefing on its own merits from the briefing + playbook only.
  Do NOT read other commanders' answer directories.
- The briefings come from one continuous game: both sides' decision points
  are included and you answer them ALL (you play both seats; so does every
  other commander - that is what makes the answers comparable).
"""


def find_scenario(game_dir, name):
    for cand in sorted(os.listdir(game_dir)):
        if cand.startswith("scenario") and cand.endswith(".json"):
            s = json.load(open(os.path.join(game_dir, cand), encoding="utf-8"))
            if s.get("name") == name:
                return os.path.join(game_dir, cand)
    raise SystemExit(f"scenario '{name}' not found in {game_dir}")


def replay(game_dir, ref_log, visit):
    """Replay the reference log; call visit(tg, turn, side) at every
    decision point (first movement-phase entry of each player turn), BEFORE
    that entry is applied. Returns the list of (turn, side) points."""
    lines = [json.loads(l) for l in open(ref_log, encoding="utf-8")
             if l.strip()]
    init = lines[0]
    if init.get("mode") != "bluegray":
        raise SystemExit("decision_probe supports bluegray logs only for now")
    game = gamespec.Game(game_dir)
    scen = find_scenario(game_dir, init["scenario"])
    points = []
    with tempfile.TemporaryDirectory() as tmp:
        tg = bg_mod.BlueGrayGame(game, scen, tmp, seed=init["seed"],
                                 tier=init.get("tier"))
        seen = set()
        for e in lines[1:]:
            if e.get("event") != "action":
                continue
            key = (e["turn"], e["side"])
            if e.get("phase") == "movement" and key not in seen:
                seen.add(key)
                points.append(key)
                visit(tg, e["turn"], e["side"])
            tg.submit(e["side"], e["action"])
    return points


def canon(tg, side, plan):
    """unit pid -> (verb, target) for every live unit; unassigned units
    follow standing doctrine and count as ('doctrine', '')."""
    out = {u["pid"]: ("doctrine", "") for u in tg._live(side)}
    for o in plan.get("orders", []):
        tgt = o.get("objective") or o.get("at") or ""
        if isinstance(tgt, list):
            tgt = f"{tgt[0]:02d}{tgt[1]:02d}"
        for pid in o.get("units", []):
            if pid in out:
                out[pid] = (o["verb"], str(tgt))
    return out


def cmd_emit(a):
    game = gamespec.Game(a.game)
    champion = llm_planner.load_champion(a.game)
    if champion is None:
        raise SystemExit("no playbook champion found - the probe requires "
                         "maximum knowledge (Bruce's rule #1)")
    bdir = os.path.join(a.out, "briefings")
    os.makedirs(bdir, exist_ok=True)

    def visit(tg, turn, side):
        text = llm_planner._bg_briefing(tg, side, advisor=champion)
        with open(os.path.join(bdir, f"briefing_gt{turn}_{side.lower()}.txt"),
                  "w", encoding="utf-8") as f:
            f.write(text)

    points = replay(a.game, a.ref_log, visit)
    doctrine_path = os.path.join(a.game, "playbook", "doctrine.md")
    if not os.path.exists(doctrine_path):
        doctrine_path = os.path.join(a.game, "doctrine.md")
    scen_name = json.loads(open(a.ref_log, encoding="utf-8")
                           .readline())["scenario"]
    plan_language = llm_planner.build_system(
        f"(read it yourself at {os.path.abspath(doctrine_path)})",
        scen_name, game.side_order)
    with open(os.path.join(a.out, "COMMANDER.md"), "w", encoding="utf-8") as f:
        f.write(COMMANDER_MD.format(
            name=scen_name,
            playbook=os.path.abspath(os.path.join(a.game, "playbook")),
            plan_language=plan_language,
            briefdir=os.path.abspath(bdir)))
    with open(os.path.join(a.out, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"ref_log": os.path.abspath(a.ref_log), "game": a.game,
                   "points": points}, f, indent=1)
    print(f"{len(points)} decision points -> {bdir}")
    print(f"instructions -> {os.path.join(a.out, 'COMMANDER.md')}")


def cmd_collect(a):
    prov, _, model = a.transport.partition(":")
    if prov == "mock":
        tr = llm_planner.mock_transport()
    elif prov == "claude":
        tr = llm_planner.claude_transport(model or llm_planner.DEFAULT_MODEL,
                                          a.effort)
    elif prov == "openai":
        tr = llm_planner.openai_transport(model or "gpt-5.6")
    else:
        raise SystemExit(f"unknown transport '{prov}'")
    game = gamespec.Game(a.game)
    champion = llm_planner.load_champion(a.game)
    adir = os.path.join(a.out, f"answers_{a.commander}")
    os.makedirs(adir, exist_ok=True)
    doctrine_path = os.path.join(a.game, "playbook", "doctrine.md")
    doctrine = open(doctrine_path, encoding="utf-8").read() \
        if os.path.exists(doctrine_path) else "(no doctrine)"
    init = json.loads(open(a.ref_log, encoding="utf-8").readline())
    system = llm_planner.build_system(doctrine, init["scenario"],
                                      game.side_order)

    def visit(tg, turn, side):
        user = llm_planner._bg_briefing(tg, side, advisor=champion)
        raw, usage = tr(system, user, llm_planner.PLAN_SCHEMA)
        with open(os.path.join(adir, f"plan_gt{turn}_{side.lower()}.json"),
                  "w", encoding="utf-8") as f:
            f.write(raw)
        print(f"  gt{turn} {side}: answered "
              f"({(usage or {}).get('out', 0)} out-tokens)")

    replay(a.game, a.ref_log, visit)
    print(f"answers -> {adir}")


def cmd_compare(a):
    names = a.answers.split(",")
    champion = llm_planner.load_champion(a.game)
    rows = []

    def visit(tg, turn, side):
        advisor_plan = None
        if champion is not None:
            import strategy_bg
            advisor_plan = canon(tg, side,
                                 strategy_bg.make_plan(tg, side, champion))
        row = {"turn": turn, "side": side, "plans": {}, "invalid": {}}
        for name in names:
            path = os.path.join(a.out, f"answers_{name}",
                                f"plan_gt{turn}_{side.lower()}.json")
            if not os.path.exists(path):
                row["plans"][name] = None
                continue
            data = json.load(open(path, encoding="utf-8"))
            plan = {"orders": [
                {k: v for k, v in o.items() if v not in ("", [])}
                for o in data.get("orders", [])]}
            problems = plans.validate_plan(tg, side, plan)
            if problems:
                row["invalid"][name] = problems
            row["plans"][name] = canon(tg, side, plan)
        if advisor_plan is not None:
            row["plans"]["_advisor"] = advisor_plan
        rows.append(row)

    replay(a.game, a.ref_log, visit)

    # pairwise per-unit agreement + advisor adoption
    all_names = names + (["_advisor"] if champion is not None else [])
    pair_stats = {}
    for i, n1 in enumerate(all_names):
        for n2 in all_names[i + 1:]:
            agree = total = ident = answered = 0
            for row in rows:
                p1, p2 = row["plans"].get(n1), row["plans"].get(n2)
                if p1 is None or p2 is None:
                    continue
                answered += 1
                units = set(p1) | set(p2)
                same = sum(1 for u in units
                           if p1.get(u) == p2.get(u))
                agree += same
                total += len(units)
                ident += (p1 == p2)
            pair_stats[f"{n1} vs {n2}"] = {
                "decision_points": answered,
                "identical_plans": ident,
                "unit_agreement": round(agree / total, 3) if total else None}
    invalid = {n: sum(1 for r in rows if n in r["invalid"]) for n in names}
    missing = {n: sum(1 for r in rows if r["plans"].get(n) is None)
               for n in names}
    report = {"pairs": pair_stats, "invalid_plans": invalid,
              "missing_answers": missing, "decisions": rows}
    rp = os.path.join(a.out, "comparison.json")
    with open(rp, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    print(f"\nDIVERGENCE REPORT ({len(rows)} decision points)")
    for pair, st in pair_stats.items():
        print(f"  {pair}: identical plans {st['identical_plans']}/"
              f"{st['decision_points']}, per-unit agreement "
              f"{st['unit_agreement']}")
    for n in names:
        if invalid[n] or missing[n]:
            print(f"  {n}: {invalid[n]} invalid, {missing[n]} missing")
    print(f"report: {rp}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("emit", cmd_emit), ("collect", cmd_collect),
                     ("compare", cmd_compare)):
        p = sub.add_parser(name)
        p.add_argument("--game", required=True)
        p.add_argument("--ref-log", required=True)
        p.add_argument("--out", required=True)
        if name == "collect":
            p.add_argument("--commander", required=True)
            p.add_argument("--transport", required=True)
            p.add_argument("--effort", default=llm_planner.DEFAULT_EFFORT)
        if name == "compare":
            p.add_argument("--answers", required=True,
                           help="comma-separated commander names")
        p.set_defaults(fn=fn)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
