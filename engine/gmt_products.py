"""
gmt_products.py - P1 acquisition sweep: GMT's NEW-site product pages.
The legacy living-rules index (t-GMTLivingRules.aspx) was already swept;
product pages host the same publisher-posted PDFs (rules, playbooks, charts,
errata) on GMT's S3 bucket for games the index misses.

    python engine/gmt_products.py --plan     # search + match + parse PDF links
                                             #   -> _meta/gmt_products_plan.json (review it!)
    python engine/gmt_products.py --fetch    # download per reviewed plan
                                             #   -> Manuals/VASSAL/<title>/ + _meta/gmt_products_log.json

Targets: doc_gaps.json rows with publisher GMT and rulebook MISSING.
Matching is scored and conservative; anything not clearly unique lands in
AMBIGUOUS for human review. The DROP set below is the curated false-positive
list (same pattern as the living-rules sweep's hand-removals).

Provenance: every downloaded file is logged with product-page URL, PDF URL,
anchor text, bytes, sha256. Publisher-posted = sanctioned channel.
"""
import argparse, hashlib, html, json, os, re, sys, time, urllib.parse, urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import census

META = census.META
MANUALS = os.path.join(census.LIB, "launchbox", "Manuals", "VASSAL")
PLAN = os.path.join(META, "gmt_products_plan.json")
LOG = os.path.join(META, "gmt_products_log.json")
SITE = "https://www.gmtgames.com"
UA = {"User-Agent": "vsav-engine-doclinker/1.0 (rules-availability study; "
                    "contact: DrEvil-TitaniumHelix on github)"}
SLEEP = 1.5          # polite: sequential, throttled
MAX_MB = 100

# game title -> product slug fragment: curated false positives (never match)
DROP = set()

# game title -> product URL: curated hand-resolutions of AMBIGUOUS rows
OVERRIDE = {
    "Silver Bayonet: The First Team in Vietnam, 1965":
        SITE + "/p-1224-silver-bayonet-25th-anniversary-edition-2nd-printing.aspx",
    "Mr President":
        SITE + "/p-1056-mr-president-the-american-presidency-2001-2020-2nd-edition.aspx",
}

# languages we skip when they label a rules translation
LANG = re.compile(r"\b(russian|french|spanish|espanol|español|italian|german|"
                  r"deutsch|japanese|chinese|korean|polish|hungarian|czech|"
                  r"portuguese|dutch)\b", re.I)
KIND = [  # first match wins; anchor text checked before filename
    ("rules", re.compile(r"living rules|rule\s?book|rules", re.I)),
    ("playbook", re.compile(r"play\s?book|scenario book|battle book", re.I)),
    ("chart", re.compile(r"\bcrt\b|chart|table|player aid|\bpac\b|\btec\b|"
                         r"display|track sheet", re.I)),
    ("errata", re.compile(r"errata|update|living|clarification", re.I)),
    ("example", re.compile(r"example|tutorial|reference", re.I)),
]
EDITION = re.compile(r"[,\s]*((\d+(st|nd|rd|th)|second|third|fourth|fifth|"
                     r"sixth)\s+(printing|edition|ed\.?)|deluxe edition|"
                     r"reprint(ed)?( edition)?)\s*$", re.I)


def fetch(url, binary=False, retries=3):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=90) as r:
                data = r.read()
            time.sleep(SLEEP)
            return data if binary else data.decode("utf-8", "replace")
        except Exception as e:
            if i == retries - 1:
                raise
            time.sleep(3 * (i + 1))


def norm(t):
    t = html.unescape(t or "").lower().replace("’", "'").replace("–", "-")
    while True:
        t2 = EDITION.sub("", t).strip()
        if t2 == t:
            break
        t = t2
    t = re.sub(r"[^a-z0-9']+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def main_title(t):
    return t.split(":")[0].strip()


def clean_title(t):
    # trailing dots/spaces are stripped by Win32 at dir creation - mirror that
    return re.sub(r"\s+", " ", re.sub(r"[\\/:*?\"<>|']", "_", t or "")) \
        .strip().rstrip(". ")


def search_products(query):
    """xsearch -> [(url, product_title)]"""
    q = urllib.parse.quote_plus(query)
    page = fetch(f"{SITE}/xsearch?searchterm={q}")
    # exact-match searches 302 straight to the product page: results pages
    # are titled "GMT Games", product pages "GMT Games - <product>"
    t = re.search(r"<title>GMT Games - (.*?)</title>", page)
    if t:
        m = re.search(r'"(/p-(?!564-)\d+-[a-z0-9-]+\.aspx)"', page)
        if m:
            return [(SITE + m.group(1), html.unescape(t.group(1)).strip())]
    out, seen = [], set()
    # pair anchor+title strictly inside one <li> block: an anchor without its
    # own <h2> (the gift-certificate promo) must not steal the next title
    for li in page.split("<li>")[1:]:
        li = li.split("</li>")[0]
        m = re.search(r'<a href="(/p-\d+-[^"]+)"', li)
        h = re.search(r"<h2>(.*?)</h2>", li, re.S)
        if not (m and h):
            continue
        u, t = SITE + m.group(1), html.unescape(h.group(1)).strip()
        if t.lower() == "description":
            continue
        if u not in seen:
            seen.add(u)
            out.append((u, t))
    return out


def score(game_title, product_title):
    gn, pn = norm(game_title), norm(product_title)
    gm, pm = norm(main_title(game_title)), norm(main_title(product_title))
    if gn == pn:
        return 100
    if pn == gm or gn == pm:       # one side's full title = other's main title
        return 85
    if gm == pm:                   # main titles agree, subtitles differ
        return 60
    if len(gm) >= 10 and (pn.startswith(gm) or gn.startswith(pm)):
        return 55
    return 0


def product_pdfs(url):
    """[(pdf_url, anchor_text, kind)] - dedup'd, translations skipped."""
    page = fetch(url)
    out, seen = [], set()
    for m in re.finditer(r'<a[^>]+href="(https?://[^"]*\.pdf[^"]*)"[^>]*>(.*?)</a>',
                         page, re.S):
        u = html.unescape(m.group(1))
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(2))).strip()
        if u in seen:
            continue
        seen.add(u)
        fname = urllib.parse.unquote(u.split("/")[-1].split("?")[0])
        probe = text + " " + fname
        # translation? language word next to rules-ish wording, not factional
        # aids - check the filename too (FallingSkyRulebookSPANISH.pdf)
        if (LANG.search(text) or LANG.search(fname)) \
                and not re.search(r"player|aid|card|pac|chart", text, re.I):
            out.append((u, text, "skip:translation"))
            continue
        kind = next((k for k, rx in KIND if rx.search(probe)), "other")
        out.append((u, text, kind))
    return out


def targets():
    dg = json.load(open(os.path.join(META, "doc_gaps.json"), encoding="utf-8"))
    rows = [x for x in dg
            if (x.get("publisher") or "").upper().startswith("GMT")
            and x["rulebook"].startswith("MISSING")]
    rows.sort(key=lambda x: (-(x.get("score") or 0), x["title"]))
    return rows


def plan(retry_nohit=False):
    rows = targets()
    old = {}
    if retry_nohit:
        old = {r["game"]: r for r in json.load(open(PLAN, encoding="utf-8"))}
        rows = [x for x in rows if old.get(x["title"], {}).get("verdict")
                in (None, "NO-HIT", "ERROR")]
    print(f"{len(rows)} GMT games missing rules; searching product pages...")
    out = []
    for i, x in enumerate(rows):
        title = x["title"]
        if title in OVERRIDE:
            u = OVERRIDE[title]
            row = dict(game=title, style=x["style"], tier_score=x.get("score"),
                       query="(override)", verdict="MATCH", candidates=[],
                       product_url=u, product_title=title + " (override)")
            try:
                row["pdfs"] = [dict(url=a, text=b, kind=c)
                               for a, b, c in product_pdfs(u)]
                if not any(p["kind"] == "rules" for p in row["pdfs"]):
                    row["verdict"] = "MATCH-NO-RULES-PDF"
            except Exception as e:
                row["verdict"], row["error"] = "ERROR", str(e)[:200]
            print(f"[{i+1}/{len(rows)}] {row['verdict']:<18} {title} (override)")
            out.append(row)
            continue
        q = main_title(title)
        try:
            cands = search_products(q)
            if not cands and q != title:
                cands = search_products(title)
        except Exception as e:
            out.append(dict(game=title, verdict="ERROR", error=str(e)[:200]))
            print(f"[{i+1}/{len(rows)}] {title} -> ERROR {e}")
            continue
        scored = sorted(((score(title, t), u, t) for u, t in cands),
                        reverse=True)
        scored = [s for s in scored if s[0] > 0 and
                  not any(d in s[1] for d in DROP)]
        # collapse printings/editions of the same product (norm-equal titles)
        # so a 1st-vs-2nd-printing pair doesn't read as ambiguous
        by_norm, dedup = set(), []
        for s in scored:
            k = norm(s[2])
            if k not in by_norm:
                by_norm.add(k)
                dedup.append(s)
        scored = dedup
        row = dict(game=title, style=x["style"], tier_score=x.get("score"),
                   query=q, verdict="NO-HIT", candidates=[
                       dict(score=s, url=u, product=t) for s, u, t in scored[:5]])
        if scored:
            top = scored[0]
            unique = len(scored) == 1 or scored[1][0] < top[0]
            if top[0] >= 85 and unique:
                row["verdict"] = "MATCH"
            elif top[0] >= 55:
                row["verdict"] = "AMBIGUOUS"
        if row["verdict"] == "MATCH":
            u = scored[0][1]
            try:
                pdfs = product_pdfs(u)
                row["product_url"] = u
                row["product_title"] = scored[0][2]
                row["pdfs"] = [dict(url=a, text=b, kind=c) for a, b, c in pdfs]
                if not any(p["kind"] == "rules" for p in row["pdfs"]):
                    row["verdict"] = "MATCH-NO-RULES-PDF"
            except Exception as e:
                row["verdict"] = "ERROR"
                row["error"] = str(e)[:200]
        print(f"[{i+1}/{len(rows)}] {row['verdict']:<18} {title}"
              + (f"  => {row.get('product_title', '')}"
                 f" ({sum(1 for p in row.get('pdfs', []) if p['kind'] == 'rules')} rules pdf)"
                 if row["verdict"].startswith("MATCH") else ""))
        out.append(row)
    if retry_nohit:
        for r in out:
            old[r["game"]] = r
        out = list(old.values())
    json.dump(out, open(PLAN, "w", encoding="utf-8"), indent=1)
    c = {}
    for r in out:
        c[r["verdict"]] = c.get(r["verdict"], 0) + 1
    print("\nplan ->", PLAN, " ", c)


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
            if p["kind"].startswith("skip") or p["kind"] == "other":
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
                log.append(dict(game=r["game"], product_url=r["product_url"],
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
    ap.add_argument("--retry-nohit", action="store_true",
                    help="re-search only NO-HIT/ERROR rows, merge into plan")
    ap.add_argument("--fetch", action="store_true")
    a = ap.parse_args()
    if a.plan or a.retry_nohit:
        plan(retry_nohit=a.retry_nohit)
    elif a.fetch:
        do_fetch()
    else:
        ap.print_help()
