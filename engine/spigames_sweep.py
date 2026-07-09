"""
spigames_sweep.py - P4b acquisition sweep: spigames.net rules archive
(fan-maintained, discrete rules/charts per SPI title). Source supplied by
Bruce 2026-07-09; in scope under his looser retrieval rule of the same date
(any freely/publicly downloadable copy; provenance logged per file;
local-only, never redistributed, never committed).

    python engine/spigames_sweep.py --plan     # parse + match -> _meta/spigames_plan.json (review!)
    python engine/spigames_sweep.py --fetch    # download -> Manuals/VASSAL/<title>/ + _meta/spigames_log.json

Page structure: "<Rules|Charts|...> for <Game Title>" labels, each followed
by one or more download anchors. Targets: doc_gaps.json rows with publisher
Simulations Publications, rulebook MISSING.
"""
import argparse, hashlib, html, json, os, re, sys, time
import urllib.parse, urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import census

META = census.META
MANUALS = os.path.join(census.LIB, "launchbox", "Manuals", "VASSAL")
PLAN = os.path.join(META, "spigames_plan.json")
LOG = os.path.join(META, "spigames_log.json")
BASE = "https://www.spigames.net/"
PAGE = BASE + "rules_downloads.htm"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0"}
SLEEP = 1.5
MAX_MB = 100

LABEL = re.compile(r"(Rules|Charts?|Errata|Exclusive rules|Standard rules|"
                   r"Tables?|Map notes|Scenarios?)[^<>]{0,20}?\bfor\s+"
                   r"([^<*]{3,80})", re.I)
LINK = re.compile(r'href="((?:PDF|pdf)[^"]*\.(?:pdf|rtf))"', re.I)


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
    t = re.sub(r"\b(the|a|an)\b", " ", t)
    t = re.sub(r"[^a-z0-9']+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def clean_title(t):
    # trailing dots/spaces are stripped by Win32 at dir creation - mirror that
    return re.sub(r"\s+", " ", re.sub(r"[\\/:*?\"<>|']", "_", t or "")) \
        .strip().rstrip(". ")


def kind_of(label):
    l = label.lower()
    if "errata" in l:
        return "errata"
    if "chart" in l or "table" in l:
        return "chart"
    if "scenario" in l:
        return "playbook"
    if "rule" in l:
        return "rules"
    return "other"


def parse_page(page):
    """[(label_kind, game_label, url)] in document order."""
    events = []
    for m in LABEL.finditer(page):
        events.append((m.start(), "label", m.group(1), m.group(2)))
    for m in LINK.finditer(page):
        events.append((m.start(), "link", m.group(1), None))
    events.sort(key=lambda e: e[0])
    out, cur = [], None
    for pos, typ, a, b in events:
        if typ == "label":
            cur = (kind_of(a), re.sub(r"\s+", " ", html.unescape(b))
                   .strip(" * "))
        elif cur:
            out.append((cur[0], cur[1], BASE + a.replace(" ", "%20")))
    return out


# labels the page markup truncates mid-title, or fan expansions that are not
# the base game - never match on these
BAD_LABELS = {"First World War Module"}
DANGLING = ("of", "the", "for", "at", "in", "de", "and")


def targets():
    dg = json.load(open(os.path.join(META, "doc_gaps.json"), encoding="utf-8"))
    rows = [x for x in dg
            if "simulations publications" in (x.get("publisher") or "").lower()
            and x["rulebook"].startswith("MISSING")]
    rows.sort(key=lambda x: (-(x.get("score") or 0), x["title"]))
    return rows


def plan():
    rows = targets()
    entries = parse_page(fetch(PAGE))
    print(f"{len(rows)} SPI games missing rules; "
          f"{len(entries)} labeled downloads on spigames.net")
    out = []
    for x in rows:
        title = x["title"]
        gn, gm = norm(title), norm(title.split(":")[0])
        hits, seen = [], set()
        for kind, label, url in entries:
            ln = norm(label)
            if label in BAD_LABELS or not ln or \
                    ln.split()[-1] in DANGLING:
                continue
            s = 0
            if ln and ln in (gn, gm):
                s = 100
            elif ln and len(ln) >= 8 and (gn.startswith(ln + " ")
                                          or ln.startswith(gn + " ")):
                s = 85
            if s and url not in seen:
                seen.add(url)
                hits.append(dict(score=s, label=label, url=url, kind=kind))
        hits.sort(key=lambda h: -h["score"])
        has_rules = any(h["kind"] == "rules" and h["score"] >= 85
                        for h in hits)
        verdict = ("MATCH" if has_rules else
                   "AUX-ONLY" if hits else "NO-HIT")
        out.append(dict(game=title, style=x["style"],
                        tier_score=x.get("score"), verdict=verdict,
                        pdfs=hits[:10]))
        if hits:
            print(f'{verdict:<9} {title}: '
                  + "; ".join(f'{h["label"]}[{h["kind"]}]' for h in hits[:4]))
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
            if p["kind"] == "other" or (r["game"], p["url"]) in have:
                n_skip += 1
                continue
            fname = clean_title(urllib.parse.unquote(
                p["url"].split("/")[-1]))
            path = os.path.join(d, fname)
            if os.path.exists(path) and os.path.getsize(path) > 0:
                n_skip += 1
                continue
            try:
                data = fetch(p["url"], binary=True)
                if len(data) > MAX_MB * 1024 * 1024 or \
                        (data[:4] != b"%PDF" and data[:5] != b"{\\rtf"):
                    print(f"  SKIP not-pdf {p['url']}")
                    continue
                os.makedirs(d, exist_ok=True)
                open(path, "wb").write(data)
                log.append(dict(game=r["game"], label=p["label"],
                                url=p["url"], kind=p["kind"], file=fname,
                                bytes=len(data),
                                sha256=hashlib.sha256(data).hexdigest(),
                                channel="spigames.net fan archive "
                                        "(looser rule 2026-07-09)"))
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
