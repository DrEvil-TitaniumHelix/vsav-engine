"""
dg_sweep.py - P4 acquisition sweep: Decision Games' public E-Rules Google
Drive folder (linked from decisiongames.com "E-Rules"). DG owns the SPI
catalog, so this is the sanctioned channel for both DG and SPI titles.

    python engine/dg_sweep.py --walk     # recurse the Drive tree -> _meta/dg_drive_tree.json
    python engine/dg_sweep.py --plan     # match files to games   -> _meta/dg_sweep_plan.json (review!)
    python engine/dg_sweep.py --fetch    # download               -> Manuals/VASSAL/<title>/ + _meta/dg_sweep_log.json

Targets: doc_gaps.json rows with publisher Decision Games or Simulations
Publications, rulebook MISSING. Files are matched on filename and parent-
folder name (both carry game titles in this archive).
"""
import argparse, hashlib, html, json, os, re, sys, time
import urllib.parse, urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import census

META = census.META
MANUALS = os.path.join(census.LIB, "launchbox", "Manuals", "VASSAL")
TREE = os.path.join(META, "dg_drive_tree.json")
PLAN = os.path.join(META, "dg_sweep_plan.json")
LOG = os.path.join(META, "dg_sweep_log.json")
ROOT = "1dB9qq80ZecyDvibEnbP0zbAHfBK8Yvhi"   # E-Rules root folder id
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0"}
SLEEP = 1.2
MAX_MB = 200
PUBS = ("decision games", "simulations publications")


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
    t = re.sub(r"\.pdf$", "", t)
    t = re.sub(r"\b(rules?|manual|rulebook|e-?rules|charts?|tables?|errata|"
               r"v?\d+(\.\d+)*|final|web(site)?|update[ds]?)\b", " ", t)
    t = re.sub(r"[^a-z0-9']+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def clean_title(t):
    # trailing dots/spaces are stripped by Win32 at dir creation - mirror that
    return re.sub(r"\s+", " ", re.sub(r"[\\/:*?\"<>|']", "_", t or "")) \
        .strip().rstrip(". ")


def list_folder(fid):
    """(subfolders [(id, name)], files [(id, name)])"""
    page = fetch(f"https://drive.google.com/embeddedfolderview?id={fid}#list")
    folders, files = [], []
    for chunk in page.split('<div class="flip-entry"')[1:]:
        eid = re.search(r'id="entry-([\w-]+)"', chunk)
        name = re.search(r'flip-entry-title">(.*?)</div>', chunk, re.S)
        if not (eid and name):
            continue
        entry = (eid.group(1), html.unescape(name.group(1)).strip())
        if "/drive/folders/" in chunk.split("flip-entry-title")[0]:
            folders.append(entry)
        else:
            files.append(entry)
    return folders, files


def walk():
    tree, queue, seen = [], [(ROOT, "")], set()
    while queue:
        fid, path = queue.pop(0)
        if fid in seen:
            continue
        seen.add(fid)
        try:
            folders, files = list_folder(fid)
        except Exception as e:
            print(f"ERROR {path or '(root)'}: {e}")
            continue
        print(f"{path or '(root)'}: {len(folders)} folders, {len(files)} files")
        for eid, name in files:
            tree.append(dict(id=eid, name=name, path=path))
        for eid, name in folders:
            queue.append((eid, f"{path}/{name}" if path else name))
    json.dump(tree, open(TREE, "w", encoding="utf-8"), indent=1)
    print(f"\n{len(tree)} files -> {TREE}")


def targets():
    dg = json.load(open(os.path.join(META, "doc_gaps.json"), encoding="utf-8"))
    rows = [x for x in dg
            if any(p in (x.get("publisher") or "").lower() for p in PUBS)
            and x["rulebook"].startswith("MISSING")]
    rows.sort(key=lambda x: (-(x.get("score") or 0), x["title"]))
    return rows


def plan():
    rows = targets()
    tree = json.load(open(TREE, encoding="utf-8"))
    print(f"{len(rows)} DG/SPI games missing rules; {len(tree)} Drive files")
    for f in tree:
        f["n_name"] = norm(f["name"])
        f["n_dir"] = norm(f["path"].split("/")[-1]) if f["path"] else ""
        f["is_pdf"] = f["name"].lower().endswith(".pdf")
    out = []
    for x in rows:
        title = x["title"]
        gn, gm = norm(title), norm(title.split(":")[0])
        hits = []
        for f in tree:
            if not f["is_pdf"]:
                continue
            fn, dn = f["n_name"], f["n_dir"]
            s = 0
            if fn and fn in (gn, gm):
                s = 100
            elif dn and dn in (gn, gm):
                s = 90
            elif fn and len(fn) >= 12 and (gn.startswith(fn) or fn.startswith(gn)):
                s = 60
            if s:
                hits.append(dict(score=s, id=f["id"], name=f["name"],
                                 path=f["path"]))
        hits.sort(key=lambda h: -h["score"])
        best = hits[0]["score"] if hits else 0
        verdict = ("MATCH" if best >= 90 else
                   "REVIEW" if best else "NO-HIT")
        out.append(dict(game=title, style=x["style"],
                        tier_score=x.get("score"), verdict=verdict,
                        files=[h for h in hits if h["score"] >= 60][:8]))
        if hits:
            print(f'{verdict:<8} {title}: '
                  + "; ".join(f'{h["path"]}/{h["name"]}[{h["score"]}]'
                              for h in hits[:3]))
    json.dump(out, open(PLAN, "w", encoding="utf-8"), indent=1)
    from collections import Counter
    print("\nplan ->", PLAN, " ", Counter(r["verdict"] for r in out))


def download_drive(fid):
    """uc?export=download, following the >25MB virus-scan confirm form."""
    url = f"https://drive.google.com/uc?export=download&id={fid}"
    data = fetch(url, binary=True)
    if data[:4] == b"%PDF":
        return data
    page = data.decode("utf-8", "replace")
    m = re.search(r'action="([^"]*)"[^>]*>(.*?)</form>', page, re.S)
    if not m:
        raise RuntimeError("no direct pdf and no confirm form")
    action = html.unescape(m.group(1))
    params = dict(re.findall(
        r'name="([^"]+)"\s+value="([^"]*)"', m.group(2)))
    q = urllib.parse.urlencode(params)
    data = fetch(f"{action}?{q}", binary=True)
    if data[:4] != b"%PDF":
        raise RuntimeError("confirm flow did not yield a pdf")
    return data


def do_fetch():
    rows = json.load(open(PLAN, encoding="utf-8"))
    log = json.load(open(LOG, encoding="utf-8")) if os.path.exists(LOG) else []
    have = {(e["game"], e["id"]) for e in log}
    n_dl = n_skip = n_err = 0
    for r in rows:
        if r["verdict"] != "MATCH":
            continue
        d = os.path.join(MANUALS, clean_title(r["game"]))
        for f in r["files"]:
            if f["score"] < 90 or (r["game"], f["id"]) in have:
                n_skip += 1
                continue
            fname = clean_title(f["name"])
            path = os.path.join(d, fname)
            if os.path.exists(path) and os.path.getsize(path) > 0:
                n_skip += 1
                continue
            try:
                data = download_drive(f["id"])
                if len(data) > MAX_MB * 1024 * 1024:
                    print(f"  SKIP oversize {f['name']}")
                    continue
                os.makedirs(d, exist_ok=True)
                open(path, "wb").write(data)
                log.append(dict(game=r["game"], id=f["id"], name=f["name"],
                                drive_path=f["path"], file=fname,
                                url=f"https://drive.google.com/file/d/{f['id']}",
                                bytes=len(data),
                                sha256=hashlib.sha256(data).hexdigest()))
                n_dl += 1
                print(f"{r['game']}: {fname} ({len(data)//1024} KB)")
            except Exception as e:
                n_err += 1
                print(f"  ERROR {r['game']} {f['name']}: {e}")
    json.dump(log, open(LOG, "w", encoding="utf-8"), indent=1)
    print(f"\ndownloaded {n_dl}, skipped {n_skip}, errors {n_err} -> {LOG}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--walk", action="store_true")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--fetch", action="store_true")
    a = ap.parse_args()
    if a.walk:
        walk()
    elif a.plan:
        plan()
    elif a.fetch:
        do_fetch()
    else:
        ap.print_help()
