"""
doc_gaps.py - Per-game DOCUMENT GAP inventory + acquisition plan: what each
game still needs (rulebook, charts, setups, art) to attempt the tier ladder,
and the cheapest sanctioned channel to get it.

    python engine/doc_gaps.py

Joins: _meta/tier_targets.json (scored games) + _meta/games.json +
_meta/catalog.json (library-hosted package PDFs) + _meta/manual_textcheck.json
(text layer of extracted bundled PDFs) + _meta/assets/<slug>/ (art on disk).

Writes DOCUMENT_GAPS.md (repo, stats only) + _meta/doc_gaps.json (full rows).

Channel grading for missing rulebooks (Bruce 2026-07-09): bundled >
library-package (vassalengine.org-hosted, fetchable) > publisher-free >
obtainable > unobtainable. Only sanctioned sources, ever.
"""
import json, os, re, sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import census

META = census.META
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULESISH = re.compile(r"rule|manual|rulebook|livret|regla|regel|playbook|"
                      r"scenario|example|chart|crt|terrain", re.I)


def clean_title(t):
    # trailing dots/spaces are stripped by Win32 at dir creation - mirror that
    return re.sub(r"\s+", " ", re.sub(r"[\\/:*?\"<>|']", "_", t or "")) \
        .strip().rstrip(". ")


def main():
    rows = json.load(open(os.path.join(META, "tier_targets.json"), encoding="utf-8"))
    games = json.load(open(os.path.join(META, "games.json"), encoding="utf-8"))
    cat = json.load(open(os.path.join(META, "catalog.json"), encoding="utf-8"))
    textcheck = json.load(open(os.path.join(META, "manual_textcheck.json"),
                               encoding="utf-8"))
    assets_dir = os.path.join(META, "assets")
    ocr_dir = os.path.join(META, "ocr")

    out = []
    for x in rows:
        g = games.get(x["game"], {})
        slugs = [m.get("slug") for m in g.get("modules", []) if m.get("slug")]

        # rulebook channel - graded from what is ON DISK (Manuals tree +
        # OCR sidecars), so acquisition runs move games automatically
        t = clean_title(x["title"])
        tc = textcheck.get(t, [])
        has_text = any(e.get("text") for e in tc)
        has_pdf = bool(tc)
        has_ocr = os.path.isdir(ocr_dir) and any(
            f.startswith(t + "__") and f.endswith(".txt")
            and os.path.getsize(os.path.join(ocr_dir, f)) > 1500
            for f in os.listdir(ocr_dir))
        pkg_pdfs = []
        for s in slugs:
            r = cat.get(s) or {}
            for p in (r.get("packages") or []):
                for f in p.get("files", []):
                    fn = str(f.get("filename", ""))
                    if fn.lower().endswith(".pdf") and RULESISH.search(fn) \
                            and "readme" not in fn.lower():
                        pkg_pdfs.append(dict(slug=s, filename=fn,
                                             url=f.get("url")))
        if has_text:
            rulebook = ("bundled-text" if x["rules_grade"] == "bundled"
                        else "fetched-text")
        elif has_ocr:
            rulebook = "ocr-text"
        elif has_pdf:
            rulebook = "bundled-scanned(OCR)"
        elif pkg_pdfs:
            rulebook = "library-package"
        elif x["rules_grade"] == "html-help":
            rulebook = "html-help"
        else:
            rulebook = "MISSING(external sweep)"

        charts = "in-module" if (x["charts"] or 0) > 0 else "unknown(in rulebook?)"
        setups = ("in-module" if (x["setups"] or 0) > 0 else
                  "MISSING(author scenario)")
        art = "none"
        for s in slugs:
            d = os.path.join(assets_dir, s.rstrip(". ") or s)
            if os.path.isdir(d) and any(f.startswith(("cover", "map"))
                                        for f in os.listdir(d)):
                art = "have"
                break
        gaps = [k for k, v in [("rulebook", rulebook), ("setups", setups)]
                if v.startswith(("MISSING", "bundled-scanned",
                                 "library-package"))]
        out.append(dict(x, rulebook=rulebook, charts=charts,
                        setups_status=setups, art=art,
                        package_pdfs=pkg_pdfs, gaps=gaps,
                        complete=not gaps))

    json.dump(out, open(os.path.join(META, "doc_gaps.json"), "w",
                        encoding="utf-8"), indent=1)

    n = len(out)
    hexlane = [x for x in out if x["style"] == "hex"]
    rb = Counter(x["rulebook"] for x in out)
    rb_hex = Counter(x["rulebook"] for x in hexlane)

    def row(k):
        return f"| {k} | {rb[k]} | {rb_hex[k]} |"

    ocr_q = [x for x in out if x["rulebook"] == "bundled-scanned(OCR)"]
    pkg_q = [x for x in out if x["rulebook"] == "library-package"]
    ext_q = [x for x in out if x["rulebook"].startswith("MISSING")]
    ext_hex = [x for x in ext_q if x["style"] == "hex" and (x["setups"] or 0) > 0]
    pubs = Counter(x["publisher"] or "?" for x in ext_hex).most_common(15)
    noscn = [x for x in hexlane if x["setups_status"].startswith("MISSING")]

    L = ["# Document gaps - what each game still needs, and where to get it",
         "",
         f"Scope: {n} scored games (see MECHANICS_REPORT.md). A game's document "
         "set = rulebook (gates 1-2) + charts/tables (gate 5) + scenario/setup "
         "(gate 4) + art (LaunchBox). Channels, best-first: bundled > "
         "library-package (hosted on vassalengine.org, fetchable) > "
         "publisher-free > obtainable > unobtainable. Sanctioned sources only.",
         "",
         "## Rulebook status",
         "",
         "| status | all games | hex lane |", "|---|---|---|"]
    for k in ("bundled-text", "fetched-text", "ocr-text",
              "bundled-scanned(OCR)", "library-package", "html-help",
              "MISSING(external sweep)"):
        L.append(row(k))
    L += ["",
          "## Action queues (by descending tier-target score)",
          "",
          f"1. **OCR queue - {len(ocr_q)} games**: bundled rulebook is a scan "
          "with no text layer. Local OCR pass makes them screenable. Top: "
          + "; ".join(x["title"] for x in ocr_q[:8]) + ".",
          f"2. **Library-package fetch - {len(pkg_q)} games**: rules-named PDFs "
          "hosted on the module's own vassalengine.org project page (URLs in "
          "doc_gaps.json) - politely downloadable, zero copyright question.",
          f"3. **External sweep - {len(ext_q)} games missing any rulebook** "
          f"({len(ext_hex)} in the hex+setups lane). Sweep by publisher "
          "(living-rules pages), then BGG once keyed. Top publishers in the "
          "hex+setups lane:",
          ""]
    L += ["| publisher | games missing rules |", "|---|---|"]
    L += [f"| {p} | {c} |" for p, c in pubs]
    L += ["",
          f"4. **Scenario authoring - {len(noscn)} hex games** have no bundled "
          "setup (gate 4): needs a hand-authored scenario each (the Firefight "
          "B pattern) - cost scales per game, do only for wanted titles.",
          "",
          "## Complete-set snapshot",
          "",
          f"- Games with NO document gaps (rulebook readable + setup in module): "
          f"**{sum(1 for x in out if x['complete'])}**",
          f"- ...of which hex: **{sum(1 for x in hexlane if x['complete'])}**",
          f"- Art present (LaunchBox): {sum(1 for x in out if x['art'] == 'have')}/{n}",
          "",
          "Full per-game rows incl. package-PDF URLs: `_meta/doc_gaps.json` (local).",
          ""]
    open(os.path.join(REPO, "DOCUMENT_GAPS.md"), "w", encoding="utf-8") \
        .write("\n".join(L))
    print(f"{n} games -> DOCUMENT_GAPS.md; queues: OCR {len(ocr_q)}, "
          f"library-package {len(pkg_q)}, external {len(ext_q)} "
          f"(hex+setups {len(ext_hex)}), scenario-authoring {len(noscn)}")


if __name__ == "__main__":
    main()
