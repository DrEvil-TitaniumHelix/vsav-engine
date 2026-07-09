"""
compass_sweep.py - P3 acquisition sweep: Compass Games' Support Library
(compassgames.com/support-library/), a single page of publisher-posted S3
PDFs organized as <strong>Game Title</strong> headings with download links
beneath each.

    python engine/compass_sweep.py --plan     # parse + match -> _meta/compass_sweep_plan.json (review!)
    python engine/compass_sweep.py --fetch    # download -> Manuals/VASSAL/<title>/ + _meta/compass_sweep_log.json

Targets: doc_gaps.json rows with publisher Compass Games, rulebook MISSING.
"""
import argparse, hashlib, html, json, os, re, sys, time
import urllib.parse, urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import census

META = census.META
MANUALS = os.path.join(census.LIB, "launchbox", "Manuals", "VASSAL")
PLAN = os.path.join(META, "compass_sweep_plan.json")
LOG = os.path.join(META, "compass_sweep_log.json")
URL = "https://www.compassgames.com/support-library/"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0 "
                    "vsav-engine-doclinker/1.0 (rules-availability study)"}
SLEEP = 1.5
MAX_MB = 100

# game title -> support-library heading: curated hand-resolutions of
# AMBIGUOUS rows (same game, different punctuation/edition naming)
OVERRIDE = {
    "Battle Hymn Vol.1: Gettysburg and Pea Ridge":
        "Battle Hymn Vol. 1 – Gettysburg & Pea Ridge",
    "Yalu (2nd edition)": "Yalu",
    "A las Barricadas! (2nd Edition)": "A las Barricadas!",
    "Crusade and Revolution: The Spanish Civil War, 1936-1939":
        "Crusade and Revolution: The Spanish Civil War, 1936-1939 DELUXE EDITION",
    "Interceptor Ace: Daylight Air Defense Over Germany, 1943-44":
        "Interceptor Ace, Vol. 1",
    "Nine Years: The War of the Grand Alliance 1688-1697":
        "Nine Years: War of the Grand Alliance 1688-1697",
}

LANG = re.compile(r"\b(spanish|espanol|español|japanese|french|german|italian|"
                  r"russian|chinese|korean|polish|hungarian|portuguese|dutch)\b",
                  re.I)
KIND = [
    ("rules", re.compile(r"living rules|rule\s?book|rules", re.I)),
    ("playbook", re.compile(r"play\s?book|scenario", re.I)),
    ("chart", re.compile(r"chart|table|player aid|\bcrt\b|\btec\b|display", re.I)),
    ("errata", re.compile(r"errata|clarification|update|faq", re.I)),
]


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


def sections(page):
    """[(heading, [(url, text)])] - one section per <strong> heading."""
    out = []
    parts = re.split(r"<strong>", page)
    for seg in parts[1:]:
        m = re.match(r"(.*?)</strong>(.*)", seg, re.S)
        if not m:
            continue
        head = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "",
                                          html.unescape(m.group(1)))).strip()
        body = m.group(2)
        anchors = []
        for a in re.finditer(r'<a[^>]+href="([^"]*\.pdf[^"]*)"[^>]*>(.*?)</a>',
                             body, re.S):
            u = html.unescape(a.group(1))
            text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "",
                                              html.unescape(a.group(2)))).strip()
            anchors.append((u, text))
        if head and anchors:
            out.append((head, anchors))
    return out


def score(game_title, heading):
    gn, hn = norm(game_title), norm(heading)
    gm, hm = norm(game_title.split(":")[0]), norm(heading.split(":")[0])
    if gn == hn:
        return 100
    if hn == gm or gn == hm:
        return 85
    if gm == hm:
        return 60
    if len(gm) >= 10 and (hn.startswith(gm) or gn.startswith(hm)):
        return 55
    return 0


def targets():
    dg = json.load(open(os.path.join(META, "doc_gaps.json"), encoding="utf-8"))
    rows = [x for x in dg
            if "compass" in (x.get("publisher") or "").lower()
            and x["rulebook"].startswith("MISSING")]
    rows.sort(key=lambda x: (-(x.get("score") or 0), x["title"]))
    return rows


def plan():
    rows = targets()
    secs = sections(fetch(URL))
    print(f"{len(rows)} Compass games missing rules; "
          f"{len(secs)} support-library sections")
    out = []
    for x in rows:
        title = x["title"]
        if title in OVERRIDE:
            hit = next(((h, a) for h, a in secs if h == OVERRIDE[title]), None)
            best = (100, hit[0], hit[1]) if hit else (0, None, [])
        else:
            best = max(((score(title, h), h, a) for h, a in secs),
                       key=lambda s: s[0], default=(0, None, []))
        row = dict(game=title, style=x["style"], tier_score=x.get("score"),
                   verdict="NO-HIT", pdfs=[])
        if best[0] >= 85:
            ties = [h for h, a in secs
                    if score(title, h) == best[0] and h != best[1]]
            if ties:
                row["verdict"] = "AMBIGUOUS"
                row["candidates"] = [best[1]] + ties
            else:
                row["heading"] = best[1]
                for u, text in best[2]:
                    if LANG.search(text) or LANG.search(u.split("/")[-1]):
                        continue
                    fname = urllib.parse.unquote(u.split("/")[-1].split("?")[0])
                    kind = next((k for k, rx in KIND
                                 if rx.search(text + " " + fname)), "other")
                    row["pdfs"].append(dict(url=u, text=text, kind=kind))
                row["verdict"] = ("MATCH" if any(p["kind"] == "rules"
                                                 for p in row["pdfs"])
                                  else "MATCH-NO-RULES-PDF")
        elif best[0] >= 55:
            row["verdict"] = "AMBIGUOUS"
            row["candidates"] = [best[1]]
        if row["verdict"] != "NO-HIT":
            print(f'{row["verdict"]:<18} {title}'
                  + (f'  => {row.get("heading")} '
                     f'({[p["kind"] for p in row["pdfs"]]})'
                     if row["verdict"].startswith("MATCH") else
                     f'  ?? {row.get("candidates")}'))
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
        if r["verdict"] != "MATCH":
            continue
        d = os.path.join(MANUALS, clean_title(r["game"]))
        for p in r["pdfs"]:
            if p["kind"] == "other":
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
                log.append(dict(game=r["game"], heading=r.get("heading"),
                                url=p["url"], text=p["text"], kind=p["kind"],
                                file=fname, bytes=len(data),
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
