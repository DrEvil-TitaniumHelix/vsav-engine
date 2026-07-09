"""
mmp_sweep.py - P2 acquisition sweep: MMP's download/support index pages
(mmpgamers.com), including the Gamers Archive per-series pages. Publisher-
posted PDFs; anchor text = "<Game Title> Rulebook/Rules/..." plus per-series
rules that apply to every matched game on that series page.

    python engine/mmp_sweep.py --plan     # parse indexes + match titles
                                          #   -> _meta/mmp_sweep_plan.json (review!)
    python engine/mmp_sweep.py --fetch    # download per reviewed plan
                                          #   -> Manuals/VASSAL/<title>/ + _meta/mmp_sweep_log.json

Targets: doc_gaps.json rows with publisher Multi-Man Publishing / The Gamers
and rulebook MISSING. A game matched on a series page also receives that
page's series rules + charts (game rules alone are incomplete there).
"""
import argparse, hashlib, html, json, os, re, sys, time
import urllib.parse, urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import census

META = census.META
MANUALS = os.path.join(census.LIB, "launchbox", "Manuals", "VASSAL")
PLAN = os.path.join(META, "mmp_sweep_plan.json")
LOG = os.path.join(META, "mmp_sweep_log.json")
SITE = "https://mmpgamers.com"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0 "
                    "vsav-engine-doclinker/1.0 (rules-availability study)"}
SLEEP = 1.5
MAX_MB = 100
PUBS = ("multi-man", "the gamers")

# every download index; series pages get their series rules fanned out
PAGES = {
    "asl-downloads-ezp-3": None,
    "aslsk-downloads-ezp-6": None,
    "gcacw-downloads-ezp-8": "GCACW",
    "gts-downloads-ezp-7": "GTS",
    "igs-downloadserrata-ezp-4": None,
    "other-games-ezp-9": None,
    "battalion-combat-series-support-ezp-13": "BCS",
    "civil-war-brigade-series-support-ezp-17": "CWB",
    "line-of-battle-series-support-ezp-15": "LoB",
    "napoleonic-battle-series-support-ezp-18": "NBS",
    "operational-combat-series-support-ezp-14": "OCS",
    "standard-combat-series-support-ezp-12": "SCS",
    "tactical-combat-series-support-ezp-16": "TCS",
    "the-gamers-general-items-ezp-19": None,
}

LANG = re.compile(r"\b(spanish|japanese|french|german|italian|russian|chinese|"
                  r"korean|polish|hungarian|portuguese|dutch)\b", re.I)
SERIESRX = re.compile(r"(series|basic|standard) (rules|charts)|charts? & tables",
                      re.I)
KIND = [
    ("rules", re.compile(r"rule\s?book|rules", re.I)),
    ("playbook", re.compile(r"play\s?book|scenario", re.I)),
    ("chart", re.compile(r"chart|table|player aid|\bcrt\b|\btec\b|display", re.I)),
    ("errata", re.compile(r"errata|clarification|update|faq", re.I)),
]
# suffix words to strip from anchor text to recover the game title
TAIL = re.compile(r"[\s,]*(rule\s?book|rules?( w/errata)?|play\s?book|"
                  r"scenarios?( book)?|errata( & clarifications)?|charts?"
                  r"( & tables)?|player aids?|v?\d+(\.\d+)*)\s*$", re.I)


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
            time.sleep(3 * (i + 1))


def norm(t):
    t = html.unescape(t or "").lower().replace("’", "'")
    t = re.sub(r"[^a-z0-9']+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def clean_title(t):
    # trailing dots/spaces are stripped by Win32 at dir creation - mirror that
    return re.sub(r"\s+", " ", re.sub(r"[\\/:*?\"<>|']", "_", t or "")) \
        .strip().rstrip(". ")


def page_anchors(page_html):
    """[(url, text)] for every PDF anchor, dedup'd by url."""
    out, seen = [], set()
    for m in re.finditer(r'<a[^>]+href="([^"]*\.pdf[^"]*)"[^>]*>(.*?)</a>',
                         page_html, re.S):
        u = html.unescape(m.group(1))
        if u.startswith("/"):
            u = SITE + u
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "",
                                          html.unescape(m.group(2)))).strip()
        if u not in seen:
            seen.add(u)
            out.append((u, text))
    return out


def anchor_game(text):
    """Strip rules/errata/version tail words -> the game-name part."""
    t = text
    while True:
        t2 = TAIL.sub("", t).strip()
        if t2 == t:
            return t
        t = t2


def kind_of(text, fname):
    probe = text + " " + fname
    return next((k for k, rx in KIND if rx.search(probe)), "other")


def targets():
    dg = json.load(open(os.path.join(META, "doc_gaps.json"), encoding="utf-8"))
    rows = [x for x in dg
            if any(p in (x.get("publisher") or "").lower() for p in PUBS)
            and x["rulebook"].startswith("MISSING")]
    rows.sort(key=lambda x: (-(x.get("score") or 0), x["title"]))
    return rows


def plan():
    rows = targets()
    print(f"{len(rows)} MMP/Gamers games missing rules")
    pages = {}
    for slug in PAGES:
        try:
            pages[slug] = page_anchors(fetch(f"{SITE}/{slug}"))
            print(f"  index {slug}: {len(pages[slug])} pdf anchors")
        except Exception as e:
            print(f"  index {slug}: ERROR {e}")
            pages[slug] = []

    out = []
    for x in rows:
        title = x["title"]
        gn, gm = norm(title), norm(title.split(":")[0])
        hits, series_pages = [], set()
        for slug, anchors in pages.items():
            for u, text in anchors:
                if LANG.search(text):
                    continue
                an = norm(anchor_game(text))
                if not an or SERIESRX.search(text):
                    continue
                if an == gn or an == gm or (len(an) >= 10 and
                                            (gn.startswith(an) or an.startswith(gn))):
                    fname = u.split("/")[-1].split("?")[0]
                    hits.append(dict(page=slug, url=u, text=text,
                                     kind=kind_of(text, fname)))
                    if PAGES[slug]:
                        series_pages.add(slug)
        # an exact-title rules hit outranks prefix hits from a longer name
        # (game "Ardennes" must not also take "Ardennes II Specific Rules")
        if any(norm(anchor_game(h["text"])) in (gn, gm) for h in hits):
            hits = [h for h in hits
                    if norm(anchor_game(h["text"])) in (gn, gm)
                    or not norm(anchor_game(h["text"])).startswith((gn, gm))]
        # fan in the series rules/charts for any series page that matched
        for slug in series_pages:
            seen_kind = set()
            for u, text in pages[slug]:
                if LANG.search(text) or not SERIESRX.search(text):
                    continue
                fname = u.split("/")[-1].split("?")[0]
                k = kind_of(text, fname)
                if k in seen_kind:      # newest listed first - keep one per kind
                    continue
                seen_kind.add(k)
                hits.append(dict(page=slug, url=u, text=text,
                                 kind="series-" + k))
        verdict = ("MATCH" if any(h["kind"].endswith("rules") for h in hits)
                   else "AUX-ONLY" if hits else "NO-HIT")
        out.append(dict(game=title, style=x["style"],
                        tier_score=x.get("score"), verdict=verdict, pdfs=hits))
        if hits:
            print(f"{verdict:<9} {title}: "
                  + "; ".join(f'{h["text"]}[{h["kind"]}]' for h in hits[:6]))
    json.dump(out, open(PLAN, "w", encoding="utf-8"), indent=1)
    from collections import Counter
    print("\nplan ->", PLAN, " ", Counter(r["verdict"] for r in out))


def do_fetch():
    rows = json.load(open(PLAN, encoding="utf-8"))
    log = json.load(open(LOG, encoding="utf-8")) if os.path.exists(LOG) else []
    have = {(e["game"], e["url"]) for e in log}
    n_dl = n_skip = n_err = 0
    for r in rows:
        if r["verdict"] != "MATCH":
            continue
        d = os.path.join(MANUALS, clean_title(r["game"]))
        for p in r["pdfs"]:
            if p["kind"] in ("other", "series-other"):
                continue
            if (r["game"], p["url"]) in have:
                n_skip += 1
                continue
            fname = clean_title(urllib.parse.unquote(
                p["url"].split("/")[-1].split("?")[0]))
            path = os.path.join(d, fname)
            if os.path.exists(path) and os.path.getsize(path) > 0:
                n_skip += 1
                continue
            try:
                data = fetch(p["url"], binary=True)
                if len(data) > MAX_MB * 1024 * 1024 or not data.startswith(b"%PDF"):
                    print(f"  SKIP not-pdf/oversize {p['url']}")
                    continue
                os.makedirs(d, exist_ok=True)
                open(path, "wb").write(data)
                log.append(dict(game=r["game"], page=p["page"], url=p["url"],
                                text=p["text"], kind=p["kind"], file=fname,
                                bytes=len(data),
                                sha256=hashlib.sha256(data).hexdigest()))
                n_dl += 1
                print(f"{r['game']}: {fname} ({len(data)//1024} KB, {p['kind']})")
            except Exception as e:
                n_err += 1
                print(f"  ERROR {r['game']} {p['url']}: {e}")
    json.dump(log, open(LOG, "w", encoding="utf-8"), indent=1)
    print(f"\ndownloaded {n_dl}, skipped {n_skip}, errors {n_err} -> {LOG}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--fetch", action="store_true")
    a = ap.parse_args()
    if a.plan:
        plan()
    elif a.fetch:
        do_fetch()
    else:
        ap.print_help()
