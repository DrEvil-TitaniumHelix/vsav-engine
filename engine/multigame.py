"""
multigame.py - P8: multi-game module sweep. Modules whose display name joins
several games ("PanzerBlitz/Panzer Leader", "Anzio / Cassino", quads) carry
"invisible games" - titles with no own catalog module, playable only through
the carrier.

    python engine/multigame.py

Detection: "/"-joined display names (high precision; "&" joins are almost
always ONE game - Axis & Allies). Each component only counts when it
independently matches a catalog game title; unmatched components are
REPORTED for review, never auto-created.

Writes:
  _meta/multigame_report.json - carriers, components, match status
  extends _meta/crosslinks.json - stub components gain their carrier
    (existing crosslink entries are never overwritten)
"""
import json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import census

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

META = census.META

# name fragments that look like joins but are one game / junk - never split
SKIP_NAMES = re.compile(
    r"axis & allies|commands & colors|1918/1919|and/or|w/|"
    r"tcs_|scenario|expansion|starter kit", re.I)


def norm(t):
    t = re.sub(r"\(.*?\)", " ", (t or "").lower())
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    t = re.sub(r"\b(the|a|of|de|game|games)\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def main():
    games = json.load(open(os.path.join(META, "games.json"), encoding="utf-8"))
    db = json.load(open(os.path.join(META, "harvest_db.json"),
                        encoding="utf-8"))
    xpath = os.path.join(META, "crosslinks.json")
    links = json.load(open(xpath, encoding="utf-8")) \
        if os.path.exists(xpath) else {}

    by_norm = {}
    for gk, g in games.items():
        by_norm.setdefault(norm(g.get("title")), []).append(gk)

    report, n_new = [], 0
    for stem, r in sorted(db.items()):
        name = r.get("name") or ""
        # publisher tags like "(Gamers/MMP)" are not game joins
        bare = re.sub(r"\(.*?\)", " ", name).strip()
        if "/" not in bare or SKIP_NAMES.search(bare):
            continue
        parts = [p.strip() for p in bare.split("/") if p.strip()]
        if len(parts) < 2:
            continue
        # the whole slashed name may itself be ONE game (Red Star/White Star)
        if by_norm.get(norm(bare)):
            continue
        # shared-suffix joins: "Skies/Storm Above the Reich" ->
        # "Skies Above the Reich" + "Storm Above the Reich"
        tailwords = parts[-1].split()
        if len(tailwords) > 1 and all(len(p.split()) == 1
                                      for p in parts[:-1]):
            tail = " ".join(tailwords[1:])
            expanded = [f"{p} {tail}" for p in parts[:-1]] + [parts[-1]]
            if sum(1 for e in expanded if by_norm.get(norm(e))) \
                    > sum(1 for p in parts if by_norm.get(norm(p))):
                parts = expanded
        comps = []
        compact = {k.replace(" ", ""): v for k, v in by_norm.items()}
        for p in parts:
            pn = norm(p)
            hit = by_norm.get(pn) or compact.get(pn.replace(" ", ""))
            if not hit and len(pn) >= 6:
                # main-title match: "Cassino" vs "Cassino: The Gustav Line"
                hit = [gk for gk, g in games.items()
                       if norm(g.get("title", "").split(":")[0]) == pn]
            status = "no-match"
            if hit:
                gk = hit[0]
                g = games[gk]
                has_own = any(m.get("vmod") for m in g.get("modules", []))
                if has_own:
                    status = "has-own-module"
                elif gk in links:
                    status = f"already-linked({links[gk]['module'][:30]})"
                else:
                    links[gk] = dict(module=r["file"],
                                     evidence=[f"P8 name-join: {name!r}"],
                                     setups=r.get("n_setups"),
                                     style=r.get("board_style"))
                    status = "NEW-CROSSLINK"
                    n_new += 1
            comps.append(dict(part=p, status=status))
        report.append(dict(module=r["file"], name=name, components=comps))

    json.dump(report, open(os.path.join(META, "multigame_report.json"), "w",
                           encoding="utf-8"), indent=1)
    json.dump(links, open(xpath, "w", encoding="utf-8"), indent=1)
    print(f"{len(report)} '/'-joined modules; {n_new} new crosslinks; "
          f"crosslinks.json now {len(links)} entries")
    print("\ncomponents with NO catalog match (review - potential invisible "
          "games):")
    for row in report:
        for c in row["components"]:
            if c["status"] == "no-match" and len(c["part"]) >= 5:
                print(f'  {c["part"][:44]:<46} (in {row["name"][:40]})')
    print("\nnew crosslinks:")
    for row in report:
        for c in row["components"]:
            if c["status"] == "NEW-CROSSLINK":
                print(f'  {c["part"][:44]:<46} -> {row["module"][:44]}')


if __name__ == "__main__":
    main()
