"""
census.py - vassalengine.org library census: enumerate every project, catalog
every file (sizes, dates, sha256), then optionally download the library.

    python engine/census.py enumerate                  # ~36 paged API calls -> projects.json
    python engine/census.py files                      # 1 call/project (resumable) -> catalog.json
    python engine/census.py stats                      # totals + tag/size breakdowns from the catalog
    python engine/census.py download [--limit N]       # main .vmod per project, resumable, sha256-checked

Data lives OUTSIDE the repo in C:\\VassalLibrary (metadata in _meta\\, modules
in modules\\<slug>\\). Deliberately polite to the API: sequential requests,
identifying User-Agent, sleep between calls. Every phase is resumable — kill
it anytime, rerun, it continues where it stopped.

Purpose (Bruce, 2026-07-08): coverage statistics for the platform — what share
of the real library the ingest tool converts, and which engine expansions buy
what coverage. The API's own tags (era/scale/topic) do part of the
categorization; the rest comes from running ingest over the downloads.
"""
import argparse, hashlib, json, os, sys, time, urllib.parse, urllib.request

if hasattr(sys.stdout, "reconfigure"):     # Windows console: don't die on unicode filenames
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "https://vassalengine.org/api/gls/v1/projects"
UA = {"User-Agent": "vsav-engine-census/1.0 (library conversion-coverage study; "
                    "contact: DrEvil-TitaniumHelix on github)"}
LIB = r"C:\VassalLibrary"
META = os.path.join(LIB, "_meta")
PROJECTS = os.path.join(META, "projects.json")
CATALOG = os.path.join(META, "catalog.json")


def get_json(url, retries=3):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(5 * (i + 1))


def load(path, default):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else default


def save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    json.dump(obj, open(tmp, "w", encoding="utf-8"))
    os.replace(tmp, path)


# ---------------------------------------------------------------- enumerate
def enumerate_projects():
    projects, url, page = [], BASE + "?limit=100", 0
    while url:
        d = get_json(url)
        projects += d["projects"]
        page += 1
        nxt = d.get("meta", {}).get("next_page")
        url = BASE + nxt if nxt else None
        print(f"page {page}: {len(projects)} / {d.get('meta', {}).get('total', '?')}")
        time.sleep(0.5)
    save(PROJECTS, projects)
    print(f"{len(projects)} projects -> {PROJECTS}")


# ---------------------------------------------------------------- files
def fetch_files():
    projects = load(PROJECTS, None)
    if projects is None:
        sys.exit("run `enumerate` first")
    catalog = load(CATALOG, {})
    todo = [p for p in projects if p["slug"] not in catalog]
    print(f"{len(catalog)} cataloged, {len(todo)} to fetch")
    for i, p in enumerate(todo):
        slug = p["slug"]
        try:
            proj = get_json(BASE + "/" + urllib.parse.quote(slug))
            catalog[slug] = dict(
                title=(proj.get("game") or {}).get("title") or proj.get("name"),
                publisher=(proj.get("game") or {}).get("publisher"),
                year=(proj.get("game") or {}).get("year"),
                tags=proj.get("tags", []),
                packages=[dict(name=k.get("name"), sort_key=k.get("sort_key"),
                               files=[dict(filename=f["filename"], url=f["url"],
                                           size=f["size"], sha256=f.get("sha256"),
                                           published_at=f.get("published_at"))
                                      for rel in k.get("releases", [])
                                      for f in rel.get("files", [])])
                          for k in proj.get("packages", [])])
        except Exception as e:
            catalog[slug] = dict(error=str(e))
            print(f"  ! {slug}: {e}")
        if (i + 1) % 50 == 0 or i == len(todo) - 1:
            save(CATALOG, catalog)
            print(f"  {len(catalog)}/{len(projects)} cataloged (saved)")
        time.sleep(0.6)
    save(CATALOG, catalog)
    print(f"done: {len(catalog)} projects -> {CATALOG}")


# ---------------------------------------------------------------- selection
def main_vmod(entry):
    """Newest .vmod from the lowest-sort_key package that has one."""
    for pkg in sorted(entry.get("packages", []), key=lambda p: p.get("sort_key") or 99):
        vmods = [f for f in pkg["files"] if f["filename"].lower().endswith(".vmod")]
        if vmods:
            return max(vmods, key=lambda f: f.get("published_at") or "")
    return None


# ---------------------------------------------------------------- stats
def stats():
    catalog = load(CATALOG, None)
    if catalog is None:
        sys.exit("run `files` first")
    n = len(catalog)
    errs = sum(1 for e in catalog.values() if "error" in e)
    mains, all_bytes, main_bytes = 0, 0, 0
    tagcount = {}
    for e in catalog.values():
        if "error" in e:
            continue
        for pkg in e["packages"]:
            all_bytes += sum(f["size"] or 0 for f in pkg["files"])
        m = main_vmod(e)
        if m:
            mains += 1
            main_bytes += m["size"] or 0
        for t in e.get("tags", []):
            tagcount[t] = tagcount.get(t, 0) + 1
    print(f"projects:            {n}  ({errs} API errors)")
    print(f"with a .vmod:        {mains}")
    print(f"main .vmod total:    {main_bytes / 1e9:.1f} GB")
    print(f"ALL files total:     {all_bytes / 1e9:.1f} GB (incl. extensions, maps, PDFs, old versions)")
    for prefix in ("era:", "scale:", "topic:"):
        top = sorted(((k, v) for k, v in tagcount.items() if k.startswith(prefix)),
                     key=lambda kv: -kv[1])[:12]
        print(f"\ntop {prefix[:-1]} tags: " + ", ".join(f"{k.split(':', 1)[1]} {v}" for k, v in top))


# ---------------------------------------------------------------- download
def download(limit=None, gap=2.0):
    catalog = load(CATALOG, None)
    if catalog is None:
        sys.exit("run `files` first")
    picks = [(slug, main_vmod(e)) for slug, e in sorted(catalog.items()) if "error" not in e]
    picks = [(s, m) for s, m in picks if m]
    done = got = fail = 0
    for slug, m in picks:
        # Windows silently strips trailing dots/spaces in dir names — sanitize
        dst_dir = os.path.join(LIB, "modules", slug.rstrip(". ") or slug.strip("."))
        dst = os.path.join(dst_dir, m["filename"])
        if os.path.exists(dst) and os.path.getsize(dst) == m["size"]:
            done += 1
            continue
        if limit is not None and got >= limit:
            break
        os.makedirs(dst_dir, exist_ok=True)
        url = m["url"]
        if " " in url or any(ord(c) > 127 for c in url):
            url = urllib.parse.quote(url, safe="/:?&=%")
        # some entries carry a bucket-subdomain host whose cert only covers the
        # bare object store — rewrite to path-style
        url = url.replace("https://obj.vassalengine.org.us-east-1.linodeobjects.com/",
                          "https://us-east-1.linodeobjects.com/obj.vassalengine.org/")
        try:
            req = urllib.request.Request(url, headers=UA)
            h = hashlib.sha256()
            with urllib.request.urlopen(req, timeout=900) as r, open(dst + ".part", "wb") as out:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    h.update(chunk)
                    out.write(chunk)
            if m.get("sha256") and h.hexdigest() != m["sha256"]:
                os.remove(dst + ".part")
                raise ValueError("sha256 mismatch")
            os.replace(dst + ".part", dst)
            got += 1
            print(f"[{done + got}/{len(picks)}] {slug}: {m['filename']} ({(m['size'] or 0) / 1e6:.1f} MB)")
        except Exception as e:
            fail += 1
            print(f"  ! {slug}: {e}")
        time.sleep(gap)
    print(f"present {done + got}/{len(picks)} (this run: {got} new, {fail} failed)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["enumerate", "files", "stats", "download"])
    ap.add_argument("--limit", type=int, help="download: stop after N new files")
    ap.add_argument("--gap", type=float, default=2.0, help="download: seconds between files")
    a = ap.parse_args()
    if a.cmd == "enumerate":
        enumerate_projects()
    elif a.cmd == "files":
        fetch_files()
    elif a.cmd == "stats":
        stats()
    else:
        download(a.limit, a.gap)
