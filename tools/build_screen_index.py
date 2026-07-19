"""
build_screen_index.py - Bake the module-screener search index from the local
library census (C:/VassalLibrary/_meta, the 2026-07-08 full mirror of
vassalengine.org). Output: web/screener/index.json - COMMITTED, because the
census is a local-only asset (same rule as BYO boards: CI and clean clones
never see C:/VassalLibrary).

The index is metadata only - titles, publishers, years, tags, structural
counts from the module buildFile, and our five-gate screen signals. No art,
no rules text, no module content. Everything in it is either what
vassalengine.org already publishes about a module or a number we derived.

Per game record (compact keys - the page expands them):
  t/p/y/slug/tags/players  identity (from games.json + projects.json)
  mods                     how many module packages the game has
  style slots setups atstart decks dice charts rpdf ruleish
                           structural harvest of the chosen .vmod
  grade score parts screen text
                           deep rules-screen results (904 modules)
  skim                     hand-review verdict + reason (the top-20 skims)
  enc                      our slug, when the game is encoded on this site
  cov                      coverage: deep | struct | listed

Usage: python tools/build_screen_index.py  ->  web/screener/index.json
"""
import json
import os

META = os.environ.get("VASSAL_CENSUS", r"C:\VassalLibrary\_meta")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "web", "screener", "index.json")
SNAPSHOT = "2026-07-08"          # date the library census was taken

# our released encodings -> the library game entry they implement
ENCODED = {
    "tobruk: tank battles in north africa 1942": "tobruk",
    "blue & gray: four american civil war battles": "blue-and-gray-chickamauga",
    "westwall: four battles to germany": "westwall-arnhem",
    "afrika korps classic avalon hill": "afrika-korps-classic-ah",
    "austerlitz: napoleon's greatest victory": "austerlitz-gmt",
}

HARVEST_FIELDS = {          # harvest_db key -> index key
    "board_style": "style", "n_slots": "slots", "n_setups": "setups",
    "n_atstart": "atstart", "n_decks": "decks", "dice": "dice",
    "charts": "charts", "rules_pdfs": "rpdf", "ruleish": "ruleish",
}


def load(name):
    with open(os.path.join(META, name), encoding="utf-8") as f:
        return json.load(f)


def main():
    games = load("games.json")
    harvest = load("harvest_db.json")
    screens = load("rules_screen.json")
    projects = load("projects.json")
    skims = load("skim_verdicts.json")

    h_by_file = {v["file"]: v for v in harvest.values() if v.get("ok")}
    rs_by_file = {r["module"]: r for r in screens}
    players = {p["game"]["title_sort_key"]: p["game"]["players"]
               for p in projects}

    out, n_deep, n_struct = [], 0, 0
    for key, g in sorted(games.items()):
        mods = [m for m in g["modules"] if m.get("vmod")]
        rec = {
            "t": g["title"], "p": g.get("publisher") or "",
            "y": g.get("year") or "", "tags": g.get("tags") or [],
            "slug": mods[0]["slug"] if mods else None,
            "mods": len(g["modules"]),
        }
        pl = players.get(key)
        if pl and pl.get("min"):
            rec["players"] = [pl["min"], pl.get("max") or pl["min"]]

        # choose the module we report on: the deep-screened one when there is
        # one, else the most recently published harvested package
        screened = [m for m in mods if m["vmod"] in rs_by_file]
        harvested = [m for m in mods if m["vmod"] in h_by_file]
        pick = (screened or sorted(harvested,
                                   key=lambda m: m.get("published") or "",
                                   reverse=True) or [None])[0]
        if pick:
            h = h_by_file.get(pick["vmod"])
            if h:
                for hk, ik in HARVEST_FIELDS.items():
                    v = h.get(hk)
                    if v not in (None, "", 0):
                        rec[ik] = v
            rs = rs_by_file.get(pick["vmod"])
            if rs:
                rec["cov"] = "deep"
                rec["grade"] = rs["rules_grade"]
                rec["score"] = rs["score"]
                rec["parts"] = rs["parts"]
                rec["screen"] = rs["screen"]
                rec["text"] = rs.get("text_chars", 0)
                n_deep += 1
            elif h:
                rec["cov"] = "struct"
                n_struct += 1
            else:
                rec["cov"] = "listed"
        else:
            rec["cov"] = "listed"

        sk = skims.get(g["title"])
        if sk:
            rec["skim"] = {"v": sk["verdict"], "why": sk["reason"]}
        if key in ENCODED:
            rec["enc"] = ENCODED[key]
        out.append(rec)

    missing = [k for k in ENCODED if k not in games]
    if missing:
        raise SystemExit(f"encoded-game titles not found in census: {missing}")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    doc = {"snapshot": SNAPSHOT, "count": len(out), "games": out}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    kb = os.path.getsize(OUT) / 1024
    print(f"{len(out)} games ({n_deep} deep-screened, {n_struct} structural) "
          f"-> {OUT} ({kb:.0f} KB)")


if __name__ == "__main__":
    main()
