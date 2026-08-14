import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EX = os.path.join(HERE, "worked_examples.json")
CRT = os.path.join(HERE, "crt_2nd_ed.json")
OUT = os.path.join(HERE, "example_check.json")

COLS = ["1:5", "1:4", "1:3", "1:2", "1:1", "2:1", "3:1", "4:1", "5:1", "6:1"]

DOUBLING = {
    "towns_only": {"town"},
    "chart_as_printed": {"town", "woods_road"},
}


def odds_column(a, d):
    if d <= 0:
        return "6:1"
    if a >= d:
        n = min(6, int(math.floor(a / d)))
        return f"{max(1, n)}:1"
    n = min(5, int(math.ceil(d / a))) if a > 0 else 5
    return f"1:{max(1, n)}"


WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
         "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def norm_odds(s):
    if not s:
        return None
    t = str(s).strip().lower().replace("–", "-").replace("—", "-")
    m = re.search(r"(\d+)\s*(?:to|:|-)\s*(\d+)", t)
    if m:
        return f"{int(m.group(1))}:{int(m.group(2))}"
    w = "|".join(WORDS)
    m = re.search(rf"({w})\s*(?:to|:|-)\s*({w})", t)
    return f"{WORDS[m.group(1)]}:{WORDS[m.group(2)]}" if m else None


def classify(v):
    t = str(v or "").lower()
    if "woods" in t and "road" in t:
        return "woods_road"
    if "town" in t:
        return "town"
    if "woods" in t:
        return "woods"
    return "clear"


def side_terrain(units):
    for u in units or []:
        c = classify(u.get("in_terrain"))
        if c != "clear":
            return c
    return "clear"


def side_total(units):
    tot = 0
    for u in units or []:
        v = to_int(u.get("combat_strength") or u.get("factors"))
        if v is None:
            return None
        tot += v
    return tot if units else None


def pick(row, *names):
    for n in names:
        if n in row and row[n] not in (None, ""):
            return row[n]
    return None


def to_int(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    m = re.search(r"\d+", str(v))
    return int(m.group()) if m else None


def rows_of(doc):
    for k in ("examples", "worked_examples", "rows", "attacks"):
        if isinstance(doc.get(k), list):
            return doc[k]
    for v in doc.values():
        if isinstance(v, list) and v and isinstance(v[0], dict):
            return v
    return []


def main():
    if not os.path.exists(EX):
        print("worked_examples.json not present yet - nothing to check.")
        return 2
    doc = json.load(open(EX, encoding="utf-8"))
    crt = json.load(open(CRT, encoding="utf-8"))["table"]
    rows = rows_of(doc)
    print(f"loaded {len(rows)} example rows")
    if rows:
        print("field names on row 0:", sorted(rows[0]))

    results = []
    for i, r in enumerate(rows):
        att = side_total(r.get("attackers"))
        dfn = side_total(r.get("defenders"))
        printed = norm_odds(pick(r, "stated_odds", "printed_odds", "odds", "odds_printed"))
        terr = side_terrain(r.get("defenders"))
        rec = {
            "index": i,
            "id": pick(r, "id", "number", "label", "example"),
            "attackers": len(r.get("attackers") or []),
            "defenders": len(r.get("defenders") or []),
            "attack_strength": att,
            "defense_strength_printed_units": dfn,
            "defender_terrain": terr,
            "attacker_terrain": side_terrain(r.get("attackers")),
            "printed_odds": printed,
        }
        if att is None or dfn is None or printed is None:
            rec["status"] = "INCOMPLETE - cannot check"
            rec["missing"] = [n for n, v in
                              (("attack", att), ("defense", dfn), ("odds", printed)) if v is None]
            results.append(rec)
            continue
        for name, dbl in DOUBLING.items():
            eff = dfn * 2 if terr in dbl else dfn
            comp = odds_column(att, eff)
            rec[name] = {"effective_defense": eff, "computed_odds": comp,
                         "matches_printed": comp == printed}
        rec["status"] = "checked"
        rec["discriminates_d4"] = (
            terr == "woods_road"
            and rec["towns_only"]["matches_printed"] != rec["chart_as_printed"]["matches_printed"]
        )
        results.append(rec)

    checked = [r for r in results if r.get("status") == "checked"]
    summary = {}
    for name in DOUBLING:
        ok = sum(1 for r in checked if r[name]["matches_printed"])
        summary[name] = {"matched": ok, "of": len(checked)}

    d4 = [r for r in checked if r.get("discriminates_d4")]
    wr = [r for r in checked if r["defender_terrain"] == "woods_road"]

    out = {
        "produced_by": "PREP-5 collation, games/napoleon-at-waterloo/ingest/naw_example_check.py",
        "read_on": "2026-08-14",
        "what_this_is": "Replays every printed worked example (folio p.2) against the machine-"
        "readable CRT and the odds rules, under BOTH readings of the D4 contradiction. The printed "
        "examples are the 1971 game's own statement of how its arithmetic resolves, so they are the "
        "validation corpus the encoding must satisfy - the same bar Siege of Jerusalem's combat "
        "tables had to clear before enforcement was allowed to ship.",
        "odds_rule": "ratio rounded off IN FAVOUR OF THE DEFENDER, then clamped to 1:5 .. 6:1",
        "d4_question": "The Terrain Effects Chart prints 'Towns & Woods/Roads' as one row granting "
        "the defender double strength; the page-1 rules text says only 'Towns'. If a printed "
        "example doubles a defender in a Woods/Road hex, the chart wins on the game's own evidence "
        "and no arbitration is needed.",
        "summary": summary,
        "woods_road_examples_found": len(wr),
        "examples_that_discriminate_d4": len(d4),
        "d4_verdict": (
            "UNDECIDED - no printed example places a defender in a Woods/Road hex, so the examples "
            "cannot settle it; the authority call is Bruce's"
            if not d4 else
            "DECIDED BY THE PRINTED EXAMPLES - see discriminating rows"
        ),
        "results": results,
    }
    json.dump(out, open(OUT, "w"), indent=1)

    print()
    for name, s in summary.items():
        print(f"{name:20s} {s['matched']}/{s['of']} printed odds reproduced")
    print(f"woods/road defender examples: {len(wr)}   discriminating: {len(d4)}")
    print("D4:", out["d4_verdict"])
    bad = [r for r in checked if not r["chart_as_printed"]["matches_printed"]
           and not r["towns_only"]["matches_printed"]]
    if bad:
        print(f"\n{len(bad)} example(s) reproduced by NEITHER reading - investigate:")
        for r in bad[:10]:
            print("  ", r["id"], r["attack_strength"], "vs", r["defense_strength_printed_units"],
                  r["defender_terrain"], "printed", r["printed_odds"],
                  "computed", r["chart_as_printed"]["computed_odds"])
    inc = [r for r in results if r.get("status") != "checked"]
    if inc:
        print(f"\n{len(inc)} row(s) incomplete: {[r['missing'] for r in inc][:5]}")
    print("->", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
