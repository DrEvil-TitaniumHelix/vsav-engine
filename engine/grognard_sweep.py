"""
grognard_sweep.py - P6 backbone: grognard.com's per-title link hub. One <li>
per game across EVERY publisher: rules translations, official rules PDFs,
errata, charts - hosted on grognard.com itself or linked out (incl.
web.archive.org mirrors). Cross-publisher: targets ALL games still missing a
rulebook. Looser-rule channel (Bruce 2026-07-09); provenance logged per file.

    python engine/grognard_sweep.py --plan    # parse a-z indexes + match
                                              #   -> _meta/grognard_plan.json (review!)
    python engine/grognard_sweep.py --fetch   # download -> Manuals/VASSAL/<title>/
                                              #   + _meta/grognard_log.json

Skipped link classes: boardgamegeek (login-gated), reviews/replays/previews,
magazine page scans (.gif), non-English translations, zips (contents unknown).
"""
import argparse, hashlib, html, json, os, re, string, sys, time
import urllib.parse, urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import census

META = census.META
MANUALS = os.path.join(census.LIB, "launchbox", "Manuals", "VASSAL")
PLAN = os.path.join(META, "grognard_plan.json")
LOG = os.path.join(META, "grognard_log.json")
SITE = "https://grognard.com/"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0 "
                    "vsav-engine-doclinker/1.0 (rules-availability study)"}
SLEEP = 1.5
MAX_MB = 100
EXTS = (".pdf", ".rtf", ".txt", ".doc")

LANG = re.compile(r"\b(french|german|italian|spanish|japanese|russian|polish|"
                  r"hungarian|dutch|portuguese|czech|korean|chinese)\b", re.I)
RULESISH = re.compile(r"\brules?\b|rule\s?book|living rules", re.I)
AUXISH = re.compile(r"errata|chart|table|player aid|crt|tec|setup|scenario", re.I)
SKIP_TEXT = re.compile(r"review|replay|preview|variant|counters|box art|"
                       r"unboxing|video|interview|analysis|strategy|session",
                       re.I)
# "rules summary/guide/PBM/solitaire..." is an aid, not the rulebook - a game
# whose only hit is one of these must not claim a fetched rulebook
DEMOTE = re.compile(r"summar|guide|difference|variant|pb[em]m?|solitaire|"
                    r"simplified|revision|update|addend", re.I)
# curated: same headline title, different game entirely
DROP = {("Conflict", "Conflict"),          # ours != Parker Brothers party game
        }


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


def parse_index(page_html):
    """[(game_title, pub_tag, [(url, text)])] - one entry per <li>."""
    out = []
    for li in re.split(r"<li>", page_html)[1:]:
        li = li.split("</li>")[0]
        head = re.search(r'<a id="[^"]*">(.*?)</a>\s*(?:\(([^)]*)\))?', li,
                         re.S)
        if not head:
            continue
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "",
                                           html.unescape(head.group(1)))).strip()
        pub = (head.group(2) or "").strip()
        links = []
        for a in re.finditer(r'<a href="([^"]+)"[^>]*>(.*?)</a>', li, re.S):
            u = html.unescape(a.group(1))
            text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "",
                                              html.unescape(a.group(2)))).strip()
            links.append((u, text))
        if title:
            out.append((title, pub, links))
    return out


def link_kind(url, text):
    low = url.lower().split("?")[0]
    if "boardgamegeek.com" in low or not low.endswith(EXTS):
        return None
    if LANG.search(text) and "english" not in text.lower():
        return None
    if SKIP_TEXT.search(text) and not RULESISH.search(text):
        return None
    if RULESISH.search(text):
        return "aux" if DEMOTE.search(text) or SKIP_TEXT.search(text) \
            else "rules"
    if AUXISH.search(text):
        return "aux"
    return None


def targets():
    dg = json.load(open(os.path.join(META, "doc_gaps.json"), encoding="utf-8"))
    rows = [x for x in dg if x["rulebook"].startswith("MISSING")]
    rows.sort(key=lambda x: (-(x.get("score") or 0), x["title"]))
    return rows


def plan():
    rows = targets()
    entries = []
    pages = [f"title{c}.html" for c in string.ascii_lowercase] \
        + ["titlenum.html", "title0.html"]
    for p in pages:
        try:
            got = parse_index(fetch(SITE + p))
            entries += got
            print(f"  {p}: {len(got)} game entries")
        except Exception as e:
            print(f"  {p}: skip ({str(e)[:60]})")
    by_norm = {}
    for title, pub, links in entries:
        by_norm.setdefault(norm(title), []).append((title, pub, links))
    print(f"{len(entries)} grognard entries; matching {len(rows)} "
          "missing-rules games...")

    out = []
    for x in rows:
        title = x["title"]
        gn, gm = norm(title), norm(title.split(":")[0])
        cands = by_norm.get(gn, []) + ([] if gn == gm else
                                       by_norm.get(gm, []))
        row = dict(game=title, publisher=x.get("publisher"),
                   style=x["style"], tier_score=x.get("score"),
                   verdict="NO-HIT", pdfs=[])
        withrules = []
        for t, pub, links in cands:
            if (title, t) in DROP:
                continue
            typed = [(u, txt, link_kind(u, txt)) for u, txt in links]
            typed = [(u, txt, k) for u, txt, k in typed if k]
            if any(k == "rules" for _, _, k in typed):
                withrules.append((t, pub, typed))
        if len(withrules) > 1:
            # disambiguate by publisher: grognard tags entries like
            # (Columbia Games), (The Gamers/MMP), (AH/Hasbro)
            mypub = (x.get("publisher") or "").lower()
            aliases = {"avalon hill": "ah", "multi-man": "gamers",
                       "simulations publications": "spi",
                       "game designers": "gdw", "victory games": "vg",
                       "milton bradley": "mb"}
            keys = {w for w in re.split(r"[^a-z]+", mypub) if len(w) > 1}
            for full, ab in aliases.items():
                if full in mypub:
                    keys.add(ab)
            hits2 = [wr for wr in withrules
                     if keys & {w for w in
                                re.split(r"[^a-z]+", wr[1].lower())
                                if len(w) > 1}]
            if len(hits2) == 1:
                withrules = hits2
        if len(withrules) > 1:
            row["verdict"] = "AMBIGUOUS"
            row["candidates"] = [dict(entry=t, pub=p) for t, p, _ in withrules]
        elif len(withrules) == 1:
            t, pub, typed = withrules[0]
            row["verdict"] = "MATCH"
            row["entry"], row["entry_pub"] = t, pub
            seen = set()
            for u, txt, k in typed:
                full = u if u.startswith("http") else SITE + u
                if full not in seen:
                    seen.add(full)
                    row["pdfs"].append(dict(url=full, text=txt, kind=k))
        elif cands:
            row["verdict"] = "AUX-ONLY"
        out.append(row)
        if row["verdict"] != "NO-HIT":
            print(f'{row["verdict"]:<9} {title[:52]:<54} '
                  + (f'<- {row.get("entry")} ({row.get("entry_pub")}) '
                     f'{[p["text"][:28] for p in row["pdfs"][:3]]}'
                     if row["verdict"] == "MATCH" else ""))
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
        t = clean_title(r["game"])
        d = os.path.join(MANUALS, t)
        for p in r["pdfs"]:
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
                low = fname.lower()
                ok = (low.endswith(".pdf") and data[:4] == b"%PDF") or \
                     (low.endswith(".rtf") and data[:5] == b"{\\rtf") or \
                     low.endswith((".txt", ".doc"))
                if not ok or len(data) > MAX_MB * 1024 * 1024:
                    print(f"  SKIP bad content {p['url']}")
                    continue
                os.makedirs(d, exist_ok=True)
                open(path, "wb").write(data)
                # native-text rules: sidecar so rules_screen can read it
                txt = None
                if low.endswith(".txt"):
                    txt = data.decode("utf-8", "replace")
                elif low.endswith(".rtf"):
                    s = data.decode("latin-1", "replace")
                    s = re.sub(r"\\'[0-9a-f]{2}", " ", s)
                    s = re.sub(r"\\[a-z]+-?\d* ?", " ", s)
                    txt = re.sub(r"\s+", " ", re.sub(r"[{}]", " ", s)).strip()
                if txt and len(txt) > 1500:
                    ocr_dir = os.path.join(META, "ocr")
                    os.makedirs(ocr_dir, exist_ok=True)
                    open(os.path.join(
                        ocr_dir,
                        f"{t}__{os.path.splitext(fname)[0].replace(' ', '_')}.txt"),
                        "w", encoding="utf-8").write(txt)
                log.append(dict(game=r["game"], entry=r.get("entry"),
                                url=p["url"], text=p["text"], kind=p["kind"],
                                file=fname, bytes=len(data),
                                sha256=hashlib.sha256(data).hexdigest(),
                                channel="grognard.com link hub "
                                        "(looser rule 2026-07-09)"))
                n_dl += 1
                print(f"{r['game']}: {fname} ({len(data)//1024} KB, {p['kind']})")
            except Exception as e:
                n_err += 1
                print(f"  ERROR {r['game']} {p['url']}: {str(e)[:100]}")
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
