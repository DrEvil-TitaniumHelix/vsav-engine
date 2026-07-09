"""
mechanics_report.py - Classify the harvested library by machine-readable
mechanics signals and rank a preliminary tier-target queue.

    python engine/mechanics_report.py

Reads  _meta/games.json (dedup'd games) + _meta/harvest_db.json (per-module
buildFile signals). Writes:
    MECHANICS_REPORT.md          (repo root, committed - stats only, no module content)
    _meta/tier_targets.json      (full scored list, local)

HONESTY NOTES (also stamped into the report):
- Scores are MODULE-DERIVED SIGNALS ONLY: what the buildFile/zip reveals
  (grid, setups, bundled rules PDFs, chart windows, dice, decks). Movement/
  combat RULES SEMANTICS live in rulebooks, not modules - a high score means
  "cheap to attempt + validatable-looking", never "rules verified".
- The rules dimension is graded bundled > html-help > unknown; "unknown"
  means the acquisition sweep / BGG must fill it in, not that rules don't exist.
- This is the pre-BGG cut: mechanics taxonomy (towing, supply, hidden
  movement...) needs BGG tags + rulebook reading, slotted in later.
"""
import json, os, re, sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import census
from game_assets import PILOT_SLUGS

META = census.META
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def stem_key(vmod):
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", os.path.splitext(vmod)[0])


def score_row(r):
    """(score 0-100, dict of component scores) from one harvest row."""
    style = r.get("board_style") or "none"
    fit = {"hex": 40, "square": 22, "point-to-point": 18, "region-snap": 18,
           "gridless-board": 8, "none": 0}.get(style, 0)
    decks = r.get("n_decks") or 0
    fit = max(0, fit - (12 if decks >= 3 else 4 if decks >= 1 else 0))
    scenario = 20 if (r.get("n_setups") or 0) > 0 else \
        10 if (r.get("n_atstart") or 0) > 0 else 0
    rules = 25 if (r.get("rules_pdfs") or 0) > 0 else \
        12 if (r.get("ruleish") or 0) > 0 else 0
    valid = (8 if (r.get("charts") or 0) > 0 else 0) + (7 if r.get("dice") else 0)
    parts = dict(mechanics_fit=fit, scenario=scenario, rules=rules,
                 validation_signals=valid)
    return sum(parts.values()), parts


def pick_module(game, db):
    """Best harvest row among a game's modules: prefer setups, then bundled
    rules, then piece count (the most convertible version of the game)."""
    best, best_k = None, None
    for m in game.get("modules", []):
        r = db.get(stem_key(m.get("vmod") or ""))
        if not r or not r.get("ok"):
            continue
        k = ((r.get("n_setups") or 0) > 0, (r.get("rules_pdfs") or 0) > 0,
             r.get("n_slots") or 0)
        if best is None or k > best_k:
            best, best_k = r, k
    return best


def main():
    games = json.load(open(os.path.join(META, "games.json"), encoding="utf-8"))
    db = json.load(open(os.path.join(META, "harvest_db.json"), encoding="utf-8"))
    pilot = set(PILOT_SLUGS)

    rows, unharvested = [], 0
    for gk, g in games.items():
        r = pick_module(g, db)
        if r is None:
            unharvested += 1
            continue
        score, parts = score_row(r)
        scale = next((t.split(":", 1)[1] for t in g.get("tags", [])
                      if t.startswith("scale:")), "?")
        era = next((t.split(":", 1)[1] for t in g.get("tags", [])
                    if t.startswith("era:")), "?")
        rows.append(dict(
            game=gk, title=g.get("title"), publisher=g.get("publisher"),
            year=g.get("year"), scale=scale, era=era,
            module=r["file"], style=r.get("board_style"),
            slots=r.get("n_slots"), setups=r.get("n_setups"),
            decks=r.get("n_decks"), dice=r.get("dice"),
            charts=r.get("charts"), rules_pdfs=r.get("rules_pdfs"),
            ruleish=r.get("ruleish"),
            rules_grade=("bundled" if r.get("rules_pdfs") else
                         "html-help" if r.get("ruleish") else "unknown"),
            pilot=any(m.get("slug") in pilot for m in g.get("modules", [])),
            score=score, parts=parts))
    rows.sort(key=lambda x: (-x["score"], -(x["rules_pdfs"] or 0),
                             -(x["setups"] or 0), x["title"] or ""))

    json.dump(rows, open(os.path.join(META, "tier_targets.json"), "w",
                         encoding="utf-8"), indent=1)

    # ---- report ----
    n = len(rows)
    style_c = Counter(x["style"] for x in rows)
    hexes = [x for x in rows if x["style"] == "hex"]

    def pct(k, whole=n):
        return f"{k} ({k * 100 // max(1, whole)}%)"

    funnel = [("hex grid", hexes)]
    for label, f in [("+ bundled setup(s)", lambda x: (x["setups"] or 0) > 0),
                     ("+ dice button(s)", lambda x: bool(x["dice"])),
                     ("+ chart window(s) (CRT candidates)", lambda x: (x["charts"] or 0) > 0),
                     ("+ bundled rules PDF (gate 1 free)", lambda x: (x["rules_pdfs"] or 0) > 0)]:
        funnel.append((label, [x for x in funnel[-1][1] if f(x)]))

    scale_x = Counter((x["style"], x["scale"]) for x in rows)
    scales = [s for s, _ in Counter(x["scale"] for x in rows).most_common(8)]
    styles = [s for s, _ in style_c.most_common()]

    L = ["# Mechanics classification - full library (module-derived signals)",
         "",
         f"Scope: {n} dedup'd games with a harvested module "
         f"({unharvested} games had no readable module). "
         "Signals come from module buildFiles/zips ONLY - rules semantics live "
         "in rulebooks; scores mean \"cheap to attempt + validatable-looking\", "
         "never \"rules verified\" (spec #12). BGG mechanics taxonomy slots in "
         "when the API key arrives.",
         "",
         "## Board-style families",
         "",
         "| style | games |", "|---|---|"]
    L += [f"| {s} | {pct(style_c[s])} |" for s in styles]
    L += ["",
          "## The hex conversion funnel (engine-today lane)",
          "",
          "| stage | games | % of hex |", "|---|---|---|"]
    L += [f"| {lab} | {len(v)} | {len(v) * 100 // max(1, len(hexes))}% |"
          for lab, v in funnel]
    L += ["",
          "## Rules availability (pre-screen gate 1, pre-acquisition-sweep)",
          ""]
    rg = Counter(x["rules_grade"] for x in rows)
    L += ["| grade | games | note |", "|---|---|---|",
          f"| bundled PDF | {pct(rg['bundled'])} | gate 1 passes for free |",
          f"| html help in module | {pct(rg['html-help'])} | often full rules, needs eyeballing |",
          f"| unknown | {pct(rg['unknown'])} | acquisition sweep / BGG to grade: "
          "publisher-free > obtainable > unobtainable |",
          "",
          "## Style x scale (top scales)",
          "",
          "| style | " + " | ".join(scales) + " |",
          "|" + "---|" * (len(scales) + 1)]
    for s in styles:
        L.append(f"| {s} | " + " | ".join(str(scale_x.get((s, sc), 0))
                                          for sc in scales) + " |")
    card = Counter("3+ decks (card-driven?)" if (x["decks"] or 0) >= 3 else
                   "1-2 decks" if (x["decks"] or 0) >= 1 else "no decks"
                   for x in rows)
    L += ["",
          "## Card usage (gate 3: cards = future engine expansion)",
          "",
          "| decks in module | games |", "|---|---|"]
    L += [f"| {k} | {pct(v)} |" for k, v in card.most_common()]
    L += ["",
          "## Preliminary tier-target queue (top 60 by score)",
          "",
          "Score = mechanics fit (40) + scenario (20) + rules (25) + validation "
          "signals (15). Full ranked list: `_meta/tier_targets.json` (local).",
          "",
          "| # | title | score | style | setups | dice | charts | rules | scale | pilot |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for i, x in enumerate(rows[:60], 1):
        L.append(f"| {i} | {x['title']} | {x['score']} | {x['style']} | "
                 f"{x['setups']} | {x['dice'] or '-'} | {x['charts']} | "
                 f"{x['rules_grade']} | {x['scale']} | "
                 f"{'YES' if x['pilot'] else ''} |")
    npilot = sum(1 for x in rows if x["pilot"])
    top100 = sum(1 for x in rows[:100] if x["pilot"])
    L += ["",
          f"Pilot coverage check: {npilot} of the 26 pilot games matched in the "
          f"dedup'd set; {top100} of them land in the top 100 - the pilot is "
          "calibration for exactly this queue.",
          ""]
    out = os.path.join(REPO, "MECHANICS_REPORT.md")
    open(out, "w", encoding="utf-8").write("\n".join(L))
    print(f"{n} games scored ({unharvested} unharvested) -> {out}")
    print(f"full list -> {os.path.join(META, 'tier_targets.json')}")
    print("top 10:", ", ".join(f"{x['title']}({x['score']})" for x in rows[:10]))


if __name__ == "__main__":
    main()
