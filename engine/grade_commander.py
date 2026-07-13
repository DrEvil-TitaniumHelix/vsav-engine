"""
grade_commander.py - Complexity-of-thinking scorecard for a played game.

Grades the ARTIFACTS each commander produced (plans + commentary from the
orders_<side>.jsonl sidecars), two layers:

1. STRUCTURAL metrics - objective, engine-computed, per turn:
   units explicitly commanded (vs left to standing doctrine), distinct
   verbs, distinct objectives, plan size, commentary length, enemy
   references, conditional-reasoning markers, advisor engagement
   (declared adopt/modify/override), turn-to-turn plan change rate.

2. BLIND RUBRIC judge (optional, --judge <transport>) - each turn's
   briefing+plan+commentary with commander identity stripped, scored 1-5
   against a fixed rubric: lookahead, enemy modeling, contingency,
   specificity, coherence. Run it once per judge model; judging all turns
   blind means a model also grades its own work without knowing it.

  python engine/grade_commander.py --live runs/match1 [--out grades.json]
      [--judge mock|claude[:model]|openai[:model]]

Honest limit: this measures thinking-as-expressed in the written orders,
not either model's hidden internal reasoning.
"""
import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import llm_planner          # noqa: E402

COND_RE = re.compile(r"\b(if|unless|in case|should the|contingen|whether|"
                     r"otherwise|fallback|risk)\b", re.I)
ENEMY_RE = re.compile(r"\b(enemy|opponent|their|counter-?attack|threat|"
                      r"he will|they will)\b", re.I)
ADVISOR_RE = re.compile(r"\b(adopt|modif|overrid|advisor|champion)\w*\b", re.I)
HEX_RE = re.compile(r"\b\d{4}\b")

RUBRIC_SCHEMA = {
    "type": "object",
    "properties": {
        "lookahead": {"type": "integer", "minimum": 1, "maximum": 5},
        "enemy_modeling": {"type": "integer", "minimum": 1, "maximum": 5},
        "contingency": {"type": "integer", "minimum": 1, "maximum": 5},
        "specificity": {"type": "integer", "minimum": 1, "maximum": 5},
        "coherence": {"type": "integer", "minimum": 1, "maximum": 5},
        "rationale": {"type": "string"},
    },
    "required": ["lookahead", "enemy_modeling", "contingency",
                 "specificity", "coherence", "rationale"],
    "additionalProperties": False,
}
JUDGE_SYSTEM = """You are grading ONE turn of command work in a hex-and-counter \
wargame. You see the briefing the commander received and the plan + commentary \
they wrote. You do NOT know who or what wrote it. Grade 1-5 on each axis:
lookahead (plans beyond this turn / victory schedule), enemy_modeling (reasons \
about what the opponent is doing or will do), contingency (conditional \
thinking, hedges, fallbacks), specificity (concrete hexes, units, geometry vs \
vague intent), coherence (orders actually implement the stated intent).
Judge only what is written. Answer with JSON only."""


def assignment(plan):
    out = {}
    for o in plan.get("orders", []):
        tgt = o.get("objective") or o.get("at") or ""
        for u in o.get("units", []):
            out[u] = (o.get("verb"), str(tgt))
    return out


def structural(entries):
    rows, prev = [], None
    for e in entries:
        plan, com = e.get("plan") or {}, e.get("commentary") or ""
        orders = plan.get("orders", [])
        asg = assignment(plan)
        changed = None
        if prev is not None:
            keys = set(asg) | set(prev)
            changed = round(sum(1 for k in keys
                                if asg.get(k) != prev.get(k)) / len(keys), 3) \
                if keys else 0.0
        rows.append({
            "turn": e["turn"], "side": e["side"],
            "orders": len(orders),
            "units_commanded": len(asg),
            "distinct_verbs": len({o.get("verb") for o in orders}),
            "distinct_targets": len({v[1] for v in asg.values() if v[1]}),
            "commentary_words": len(com.split()),
            "hex_refs": len(HEX_RE.findall(com)),
            "enemy_refs": len(ENEMY_RE.findall(com)),
            "conditional_markers": len(COND_RE.findall(com)),
            "advisor_engagement": bool(ADVISOR_RE.search(com)),
            "plan_change_rate": changed,
        })
        prev = asg
    return rows


def thinking_score(row, rubric=None):
    """One rough 0-1000 'how much did it have to think' number per move.
    Structural half (0-400): written reasoning volume + conditional thinking
    + enemy analysis + geometric specificity + breadth of explicit command.
    Rubric half (0-600, when a blind judge ran): mean of the five 1-5 axes.
    Without a judge the structural half is scaled to the full 0-1000."""
    s = (min(row["commentary_words"], 120) / 120 * 100
         + min(row["conditional_markers"], 5) * 20
         + min(row["enemy_refs"], 5) * 20
         + min(row["hex_refs"], 5) * 10
         + min(row["distinct_targets"], 5) * 10)
    if rubric is None:
        return round(s * 2.5)
    axes = ["lookahead", "enemy_modeling", "contingency", "specificity",
            "coherence"]
    r = sum(rubric[k] for k in axes) / len(axes)          # 1..5
    return round(s + (r - 1) / 4 * 600)


def summarize(rows):
    if not rows:
        return {}
    keys = ["orders", "units_commanded", "distinct_verbs", "distinct_targets",
            "commentary_words", "hex_refs", "enemy_refs",
            "conditional_markers"]
    out = {k: round(sum(r[k] for r in rows) / len(rows), 2) for k in keys}
    out["advisor_engagement_rate"] = round(
        sum(1 for r in rows if r["advisor_engagement"]) / len(rows), 2)
    chg = [r["plan_change_rate"] for r in rows
           if r["plan_change_rate"] is not None]
    out["mean_plan_change_rate"] = round(sum(chg) / len(chg), 3) if chg else None
    out["turns"] = len(rows)
    return out


def make_judge(spec, effort):
    prov, _, model = spec.partition(":")
    if prov == "mock":
        def tr(system, user, schema):
            return (json.dumps({k: 3 for k in
                                ("lookahead", "enemy_modeling", "contingency",
                                 "specificity", "coherence")}
                               | {"rationale": "mock"}), {})
        return tr
    if prov == "claude":
        return llm_planner.claude_transport(
            model or llm_planner.DEFAULT_MODEL, effort)
    if prov == "openai":
        return llm_planner.openai_transport(model or "gpt-5.6")
    raise SystemExit(f"unknown judge '{spec}'")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--judge", default=None,
                    help="mock | claude[:model] | openai[:model]")
    ap.add_argument("--effort", default=llm_planner.DEFAULT_EFFORT)
    a = ap.parse_args()

    report = {"live": a.live, "commanders": {}}
    sides = {}
    for path in sorted(glob.glob(os.path.join(a.live, "orders_*.jsonl"))):
        entries = [json.loads(l) for l in open(path, encoding="utf-8")]
        if not entries:
            continue
        name = entries[0].get("commander") or entries[0]["side"]
        sides[entries[0]["side"]] = (name, entries)
    for side, (name, entries) in sorted(sides.items()):
        rows = structural(entries)
        for r in rows:
            r["thinking_score"] = thinking_score(r)
        summ = summarize(rows)
        summ["mean_thinking_score"] = round(
            sum(r["thinking_score"] for r in rows) / len(rows)) if rows else 0
        report["commanders"][name] = {"side": side,
                                      "per_turn": rows,
                                      "summary": summ}
    if a.judge:
        judge = make_judge(a.judge, a.effort)
        for side, (name, entries) in sorted(sides.items()):
            grades = []
            for e in entries:
                bfile = os.path.join(
                    a.live, f"briefing_gt{e['turn']}_{side.lower()}.txt")
                briefing = open(bfile, encoding="utf-8").read() \
                    if os.path.exists(bfile) else "(briefing unavailable)"
                user = (f"BRIEFING:\n{briefing}\n\nTHE COMMANDER'S PLAN:\n"
                        + json.dumps(e.get("plan"))
                        + f"\n\nTHE COMMANDER'S COMMENTARY:\n"
                        + (e.get("commentary") or "(none)"))
                raw, _ = judge(JUDGE_SYSTEM, user, RUBRIC_SCHEMA)
                g = json.loads(raw)
                g["turn"] = e["turn"]
                grades.append(g)
                print(f"  judged {name} gt{e['turn']}")
            axes = ["lookahead", "enemy_modeling", "contingency",
                    "specificity", "coherence"]
            rows = report["commanders"][name]["per_turn"]
            by_turn = {g["turn"]: g for g in grades}
            for r in rows:
                if r["turn"] in by_turn:
                    r["thinking_score"] = thinking_score(r, by_turn[r["turn"]])
            report["commanders"][name]["summary"]["mean_thinking_score"] = \
                round(sum(r["thinking_score"] for r in rows) / len(rows))
            report["commanders"][name]["rubric"] = {
                "judge": a.judge, "per_turn": grades,
                "means": {k: round(sum(g[k] for g in grades) / len(grades), 2)
                          for k in axes} if grades else {}}
    out = a.out or os.path.join(a.live, "command_grades.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    print(f"\nCOMMAND SCORECARD")
    for name, c in report["commanders"].items():
        print(f"  {name} ({c['side']}): {json.dumps(c['summary'])}")
        if "rubric" in c:
            print(f"    rubric means ({c['rubric']['judge']}): "
                  f"{json.dumps(c['rubric']['means'])}")
    print(f"report: {out}")


if __name__ == "__main__":
    main()
