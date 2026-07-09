"""
ia_sweep.py - Internet Archive sweep: per-game search of archive.org's texts
collection for rulebook scans/uploads. Uses the public advancedsearch +
metadata APIs (Bruce endorsed the API route 2026-07-09; looser-rule channel,
provenance logged per file).

    python engine/ia_sweep.py --plan [--all]   # search per game -> _meta/ia_plan.json (review!)
    python engine/ia_sweep.py --fetch          # download -> Manuals/VASSAL/<title>/ + _meta/ia_log.json

Default target cohort: canon-publisher hex games missing rules (the grognard
core Bruce's success metric tracks); --all widens to every missing-rules game.
Matching is deliberately strict: the item title must contain the game's full
main title AND a rules-ish word must appear in the item title, or the PDF
filename must be rules-ish. Everything else lands in REVIEW.
"""
import argparse, hashlib, html, json, os, re, sys, time
import urllib.parse, urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import census

META = census.META
MANUALS = os.path.join(census.LIB, "launchbox", "Manuals", "VASSAL")
PLAN = os.path.join(META, "ia_plan.json")
LOG = os.path.join(META, "ia_log.json")
UA = {"User-Agent": "vsav-engine-doclinker/1.0 (rules-availability study; "
                    "contact: DrEvil-TitaniumHelix on github)"}
SLEEP = 1.5
MAX_MB = 150
RULESISH = re.compile(r"rule|manual|instructions", re.I)

CANON = ("gmt", "simulations publications", "avalon hill", "multi-man",
         "the gamers", "game designers", "victory games", "decision games",
         "compass", "columbia", "clash of arms", "hexasim", "legion wargames",
         "west end", "world wide wargames", "spi")

# hand-culled wrong matches from the 2026-07-09 plan review (video-game
# manuals, LEGO instructions, ship-classification rules...)
DROP_ITEMS = {
    "brothers-in-arms-hells-highway-pc-windows-english-manual",
    "roadrunnersnesgermanmanual", "DontDisarm",
    "lloyds-register-rules-and-regulations-for-the-classification-of-ships"
    "-using-gase_20231019",
    "lego-building-instructions-76151",
    "vgmuseum_sir-tech_trophycase-druid-manual", "DTIC_ADA272982",
    "gulf-strike-avalon-hill",       # map scan only, not rules
}
WARGAMEY = ("combat results", "zone of control", "movement allowance",
            "hexes", "die roll", "terrain effects", "counters", "scenario")


def verify_pdf(data, game_title):
    """The file must prove itself: game title in the text, or it reads
    like boardgame rules (>=2 wargame phrases). Textless scans get their
    first pages OCR'd before judgment. Spec-#12 spirit: a wrong rulebook
    in the tree is worse than none."""
    import fitz
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        text = " ".join(doc[i].get_text()
                        for i in range(min(6, doc.page_count))).lower()
        if len(text) < 500:        # scan: OCR the first two pages to judge
            import subprocess, tempfile
            with tempfile.TemporaryDirectory() as td:
                for i in range(min(2, doc.page_count)):
                    png = os.path.join(td, f"v{i}.png")
                    doc[i].get_pixmap(dpi=200).save(png)
                    r = subprocess.run(
                        ["tesseract", png, "stdout", "--psm", "3"],
                        capture_output=True, text=True,
                        encoding="utf-8", errors="replace")
                    text += " " + (r.stdout or "").lower()
        doc.close()
    except Exception:
        return False, "unreadable"
    main = re.sub(r"[^a-z0-9']+", " ",
                  game_title.split(":")[0].lower()).strip()
    if main and main in re.sub(r"[^a-z0-9']+", " ", text):
        return True, "title-in-text"
    hits = sum(1 for w in WARGAMEY if w in text)
    if hits >= 2:
        return True, f"wargamey({hits})"
    return False, f"no evidence (title absent, {hits} wargame phrases)"


def fetch(url, binary=False, retries=3):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=90) as r:
                data = r.read()
            time.sleep(SLEEP)
            return data if binary else data.decode("utf-8", "replace")
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(5 * (i + 1))


def norm(t):
    t = html.unescape(t or "").lower().replace("’", "'")
    t = re.sub(r"\b(the|a|an)\b", " ", t)
    t = re.sub(r"[^a-z0-9']+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def clean_title(t):
    # trailing dots/spaces are stripped by Win32 at dir creation - mirror that
    return re.sub(r"\s+", " ", re.sub(r"[\\/:*?\"<>|']", "_", t or "")) \
        .strip().rstrip(". ")


def search(title):
    q = urllib.parse.quote(f'title:("{title}") AND mediatype:(texts)')
    url = (f"https://archive.org/advancedsearch.php?q={q}"
           "&fl[]=identifier&fl[]=title&rows=10&page=1&output=json")
    j = json.loads(fetch(url))
    return [(d["identifier"], d.get("title", ""))
            for d in j.get("response", {}).get("docs", [])]


def item_pdfs(identifier):
    j = json.loads(fetch(f"https://archive.org/metadata/{identifier}"))
    out = []
    for f in j.get("files", []):
        name = f.get("name", "")
        if name.lower().endswith(".pdf") and f.get("source") == "original":
            out.append(dict(name=name, size=int(f.get("size", 0) or 0)))
    return out


def targets(all_games):
    dg = json.load(open(os.path.join(META, "doc_gaps.json"), encoding="utf-8"))
    rows = [x for x in dg if x["rulebook"].startswith("MISSING")]
    if not all_games:
        rows = [x for x in rows if x["style"] == "hex" and
                any(c in (x.get("publisher") or "").lower() for c in CANON)]
    rows.sort(key=lambda x: (-(x.get("score") or 0), x["title"]))
    return rows


def plan(all_games=False):
    rows = targets(all_games)
    print(f"{len(rows)} target games; searching archive.org...")
    out = []
    for i, x in enumerate(rows):
        title = x["title"]
        main = title.split(":")[0].strip()
        gm = norm(main)
        row = dict(game=title, publisher=x.get("publisher"),
                   style=x["style"], tier_score=x.get("score"),
                   verdict="NO-HIT", items=[])
        try:
            docs = search(main)
        except Exception as e:
            row["verdict"], row["error"] = "ERROR", str(e)[:150]
            out.append(row)
            print(f"[{i+1}/{len(rows)}] ERROR {title}: {str(e)[:60]}")
            continue
        for ident, ititle in docs:
            it = norm(ititle)
            if gm and gm in it:
                strong = bool(RULESISH.search(ititle))
                row["items"].append(dict(id=ident, title=ititle,
                                         strong=strong))
        if any(it["strong"] for it in row["items"]):
            row["verdict"] = "MATCH"
        elif row["items"]:
            row["verdict"] = "REVIEW"
        if row["verdict"] == "MATCH":
            best = next(it for it in row["items"] if it["strong"])
            try:
                pdfs = item_pdfs(best["id"])
                row["item"] = best["id"]
                row["pdfs"] = [p for p in pdfs
                               if p["size"] < MAX_MB * 1024 * 1024][:4]
                if not row["pdfs"]:
                    row["verdict"] = "MATCH-NO-PDF"
            except Exception as e:
                row["verdict"], row["error"] = "ERROR", str(e)[:150]
        if row["verdict"] != "NO-HIT":
            print(f'[{i+1}/{len(rows)}] {row["verdict"]:<12} {title[:46]:<48}'
                  + (f' <- {row.get("item")}' if row["verdict"] == "MATCH"
                     else f' ?? {[it["title"][:40] for it in row["items"][:2]]}'))
        out.append(row)
    json.dump(out, open(PLAN, "w", encoding="utf-8"), indent=1)
    from collections import Counter
    print("\nplan ->", PLAN, " ", Counter(r["verdict"] for r in out))


def do_fetch():
    rows = json.load(open(PLAN, encoding="utf-8"))
    log = json.load(open(LOG, encoding="utf-8")) if os.path.exists(LOG) else []
    have = {(e["game"], e["url"]) for e in log}
    n_dl = n_skip = n_err = 0
    for r in rows:
        if r["verdict"] != "MATCH" or r.get("item") in DROP_ITEMS:
            continue
        t = clean_title(r["game"])
        d = os.path.join(MANUALS, t)
        for p in r["pdfs"]:
            url = (f"https://archive.org/download/{r['item']}/"
                   + urllib.parse.quote(p["name"]))
            if (r["game"], url) in have:
                n_skip += 1
                continue
            fname = clean_title(p["name"].split("/")[-1])
            path = os.path.join(d, fname)
            if os.path.exists(path) and os.path.getsize(path) > 0:
                n_skip += 1
                continue
            try:
                data = fetch(url, binary=True)
                if data[:4] != b"%PDF":
                    print(f"  SKIP not-pdf {url}")
                    continue
                ok, why = verify_pdf(data, r["game"])
                if not ok:
                    print(f"  QUARANTINE {r['game']} <- {p['name']}: {why}")
                    continue
                os.makedirs(d, exist_ok=True)
                open(path, "wb").write(data)
                log.append(dict(game=r["game"], item=r["item"], url=url,
                                file=fname, bytes=len(data), verified=why,
                                sha256=hashlib.sha256(data).hexdigest(),
                                channel="archive.org texts "
                                        "(looser rule 2026-07-09)"))
                n_dl += 1
                print(f"{r['game']}: {fname} ({len(data)//1024} KB)")
            except Exception as e:
                n_err += 1
                print(f"  ERROR {r['game']} {url}: {str(e)[:100]}")
    json.dump(log, open(LOG, "w", encoding="utf-8"), indent=1)
    print(f"\ndownloaded {n_dl}, skipped {n_skip}, errors {n_err} -> {LOG}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--fetch", action="store_true")
    a = ap.parse_args()
    if a.plan:
        plan(all_games=a.all)
    elif a.fetch:
        do_fetch()
    else:
        ap.print_help()
