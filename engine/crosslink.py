"""
crosslink.py - Match stub games (library project hosts no module file) to the
CARRIER module that actually contains them: companion games in combined
modules (Panzer Leader inside "PanzerBlitz/Panzer Leader"), system pages
whose content lives in a sibling project.

    python engine/crosslink.py

Evidence, conservative-first:
  name:   harvest row's module display name contains the stub title
  desc:   module description contains the stub title
  setup:  >=2 bundled setup names contain the stub title (or its initials
          prefix like "PZL #")
Writes _meta/crosslinks.json  {game_key: {module, slug, evidence, matched}}
Every match carries its evidence string - review the log before trusting.
"""
import json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import census

META = census.META


def norm(t):
    t = re.sub(r"\(.*?\)", " ", (t or "").lower())
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    t = re.sub(r"\b(the|a|of|de|game|games)\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# hand-reviewed 2026-07-09: auto-matches that are DIFFERENT GAMES sharing a
# name fragment - never link these (the auto matcher's evidence looked
# plausible but the games are unrelated)
DROP = {
    "blood bowl",            # != Blood Bowl: Team Manager (card game)
    "napoleon",              # != Commands & Colors: Napoleonics
    "dauntless",             # != Operation Dauntless (GMT ground combat)
    "east & west",           # != Blocks in the East/West
    "intruder",              # != Flight of the Intruder
    "banzai",                # != Mississippi Banzai
    "raider!",               # != Rebel Raiders
    "star trek: the game",   # != Star Trek: Ascendancy
    "goblin",                # != Goblin Supremacy
    "testing",               # junk stub
}


def main():
    games = json.load(open(os.path.join(META, "games.json"), encoding="utf-8"))
    db = json.load(open(os.path.join(META, "harvest_db.json"), encoding="utf-8"))
    cat = json.load(open(os.path.join(META, "catalog.json"), encoding="utf-8"))

    # slug -> module filename, for reverse lookup of carrier's game entry
    stubs = {k: g for k, g in games.items()
             if all(m.get("vmod") is None for m in g.get("modules", []))}
    print(f"stub games: {len(stubs)}")

    # preload setup names per harvest row (from the full per-module harvest)
    hdir = os.path.join(META, "harvest")
    links, log = {}, []
    for gk, g in sorted(stubs.items()):
        if gk in DROP:
            continue
        nt = norm(g.get("title"))
        if len(nt) < 6:            # too generic to match safely
            continue
        best = None
        for stem, r in db.items():
            if not r.get("ok"):
                continue
            ev = []
            if nt in norm(r.get("name")):
                ev.append(f"module name: {r.get('name')!r}")
            hp = os.path.join(hdir, stem + ".json")
            if not ev and os.path.exists(hp):
                h = json.load(open(hp, encoding="utf-8"))
                if nt in norm(h.get("description")):
                    ev.append("module description")
                else:
                    hits = [s.get("name") for s in h.get("setups", [])
                            if nt in norm(s.get("name"))]
                    if len(hits) >= 2:
                        ev.append(f"{len(hits)} setups: {hits[0]!r}...")
            if ev:
                cand = dict(module=r["file"], evidence=ev,
                            setups=r.get("n_setups"), style=r.get("board_style"))
                # prefer name-evidence, then more setups
                key = (ev[0].startswith("module name"), r.get("n_setups") or 0)
                if best is None or key > best[0]:
                    best = (key, cand)
        if best:
            links[gk] = best[1]
            log.append(f"{g['title'][:44]:46} -> {best[1]['module'][:40]:42} "
                       f"[{best[1]['evidence'][0][:60]}]")

    json.dump(links, open(os.path.join(META, "crosslinks.json"), "w",
                          encoding="utf-8"), indent=1)
    print(f"cross-linked: {len(links)} of {len(stubs)} stubs")
    for line in log:
        print(" ", line)


if __name__ == "__main__":
    main()
