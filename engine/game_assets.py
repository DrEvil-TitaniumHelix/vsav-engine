"""
game_assets.py - LaunchBox-style art + reference assets per game, sourced
primarily from THE MODULE ITSELF (no scraping, no API walls):

  cover_vassal.<ext>       the module library's own cover (MediaWiki hashed URL)
  cover_module.<ext>       box/cover/title art found INSIDE the module, if any
  map_background.jpg       the main board, downscaled (LaunchBox fanart/bg)
  counters_composite.png   a sampled grid of counter art (per Bruce: a
                           composite, not one art per counter)
  assets.json              metadata: manual pointers (rule PDFs bundled in the
                           module + library page), how-to-play video SEARCH
                           links (labeled as searches), provenance

    python engine/game_assets.py --pilot                    # the 26 scorecard slugs
    python engine/game_assets.py <slug> [...]               # specific projects

Note: BGG's XML API now returns 401 (API-key program) — BGG metadata/videos
need a registered key; slot exists in assets.json when we get one.
"""
import hashlib, io, json, os, re, sys, time, urllib.parse, urllib.request, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import census

META = census.META
ASSETS = os.path.join(META, "assets")
MODULE_DIRS = [r"C:\VassalIngest\downloads", os.path.join(census.LIB, "modules")]
UA = {"User-Agent": "vsav-engine-assets/1.0 (boardgame art staging; "
                    "contact: DrEvil-TitaniumHelix on github)"}
PILOT_SLUGS = [
    "afrika_korps_stiglr", "PanzerBlitz", "The_Russian_Campaign",
    "napoleon_at_waterloo_cholmcc", "battle_for_moscow_gdw_cholm",
    "Panzergruppe_Guderian", "Squad_Leader", "Twilight_Struggle",
    "Paths_of_Glory", "Hannibal_Rome_vs._Carthage", "Washingtons_War",
    "Wilderness_War", "Victory_in_the_Pacific", "War_At_Sea", "Diplomacy",
    "Rise_and_Decline_of_the_Third_Reich", "Commands__Colors_Ancients",
    "A_House_Divided", "1960_The_Making_of_the_President", "Empire_of_the_Sun",
    "For_the_People", "The_Longest_Day", "World_in_Flames", "Julius_Caesar",
    "Ardennes_44", "Bitter_Woods_4th_Ed_wga",
]
BOXART_RE = re.compile(r"box|cover|title|splash|front", re.I)
IMG_EXT = (".png", ".gif", ".jpg", ".jpeg", ".bmp")


def wiki_image_url(filename):
    n = filename.replace(" ", "_")
    h = hashlib.md5(n.encode()).hexdigest()
    return f"https://obj.vassalengine.org/images/{h[0]}/{h[:2]}/{urllib.parse.quote(n)}"


def fetch(url, binary=False):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    return data if binary else data.decode("utf-8", errors="replace")


def find_vmod(slug, cat):
    m = census.main_vmod(cat.get(slug, {})) if "error" not in cat.get(slug, {}) else None
    if not m:
        return None
    for d in MODULE_DIRS:
        for p in (os.path.join(d, m["filename"]), os.path.join(d, slug, m["filename"])):
            if os.path.exists(p):
                return p
    return None


def load_img(z, name):
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(z.read(name)))
        im.load()
        return im.convert("RGBA") if im.mode != "RGBA" else im
    except Exception:
        return None


def module_art(vmod_path, out_dir, max_counters=40):
    """Box art, map background, counter composite — all from inside the zip."""
    from PIL import Image
    got = {}
    with zipfile.ZipFile(vmod_path) as z:
        imgs = [n for n in z.namelist() if n.lower().endswith(IMG_EXT)
                and not n.endswith("/")]
        infos = {n: z.getinfo(n).file_size for n in imgs}

        # --- box/cover art: name says so, and it's a real image
        for n in sorted((n for n in imgs if BOXART_RE.search(os.path.basename(n))),
                        key=lambda n: -infos[n]):
            im = load_img(z, n)
            if im and im.width >= 150 and im.height >= 150:
                ext = os.path.splitext(n)[1].lower()
                im.convert("RGB").save(os.path.join(out_dir, "cover_module.jpg"),
                                       quality=88)
                got["cover_module"] = os.path.basename(n)
                break

        # --- map background: biggest image by bytes = almost always the board
        for n in sorted(imgs, key=lambda n: -infos[n])[:3]:
            im = load_img(z, n)
            if im and im.width >= 800 and im.width > im.height * 0.3:
                if im.width > 1920:
                    im = im.resize((1920, int(im.height * 1920 / im.width)),
                                   Image.LANCZOS)
                im.convert("RGB").save(os.path.join(out_dir, "map_background.jpg"),
                                       quality=85)
                got["map_background"] = os.path.basename(n)
                break

        # --- counter composite: small squarish images, sampled evenly, gridded
        counters = []
        for n in imgs:
            s = infos[n]
            if not (300 < s < 400_000):
                continue
            bn = os.path.basename(n).lower()
            if BOXART_RE.search(bn) or "map" in bn or "board" in bn:
                continue
            counters.append(n)
        if counters:
            counters.sort()
            step = max(1, len(counters) // max_counters)
            sample, seen = [], set()
            for n in counters[::step]:
                im = load_img(z, n)
                if im is None or not (16 <= im.width <= 400) or \
                        not (0.5 <= im.width / max(1, im.height) <= 2.0):
                    continue
                key = (im.width, im.height, os.path.basename(n)[:4])
                if key in seen:      # skip runs of near-identical counters
                    continue
                seen.add(key)
                sample.append(im)
                if len(sample) >= max_counters:
                    break
            if len(sample) >= 4:
                cell = 96
                cols = 8
                rows = (len(sample) + cols - 1) // cols
                sheet = Image.new("RGBA", (cols * (cell + 8) + 8, rows * (cell + 8) + 8),
                                  (28, 28, 30, 255))
                for i, im in enumerate(sample):
                    im.thumbnail((cell, cell), Image.LANCZOS)
                    x = 8 + (i % cols) * (cell + 8) + (cell - im.width) // 2
                    y = 8 + (i // cols) * (cell + 8) + (cell - im.height) // 2
                    sheet.paste(im, (x, y), im)
                sheet.convert("RGB").save(os.path.join(out_dir, "counters_composite.png"))
                got["counters_composite"] = f"{len(sample)} counters sampled of {len(counters)}"
    return got


def gather(slug, cat):
    d = os.path.join(ASSETS, slug)
    os.makedirs(d, exist_ok=True)
    rec = dict(slug=slug, sources={})
    try:
        proj = json.loads(fetch(census.BASE + "/" + urllib.parse.quote(slug)))
    except Exception as e:
        rec["error"] = f"library API: {e}"
        return rec
    game = proj.get("game") or {}
    title = game.get("title") or proj.get("name") or slug
    rec.update(title=title, publisher=game.get("publisher"), year=game.get("year"),
               tags=proj.get("tags", []),
               library_page=f"https://vassalengine.org/library/projects/{slug}")
    # direct module download: with this in the shared XML, a user needs ONLY the
    # metadata file — they fetch just the modules they want from the library
    m = census.main_vmod(cat.get(slug, {})) if "error" not in cat.get(slug, {}) else None
    if m:
        rec["download"] = dict(url=m["url"], filename=m["filename"], size=m["size"],
                               sha256=m.get("sha256"), published=m.get("published_at"))

    # 1. library cover (MediaWiki hashed path)
    if proj.get("image"):
        try:
            data = fetch(wiki_image_url(proj["image"]), binary=True)
            ext = os.path.splitext(proj["image"])[1].lower() or ".jpg"
            open(os.path.join(d, "cover_vassal" + ext), "wb").write(data)
            rec["sources"]["cover_vassal"] = proj["image"]
        except Exception as e:
            rec["sources"]["cover_vassal_error"] = str(e)

    # 2. art from inside the module
    vmod = find_vmod(slug, cat)
    if vmod:
        try:
            rec["sources"].update(module_art(vmod, d))
        except Exception as e:
            rec["sources"]["module_art_error"] = str(e)
    else:
        rec["sources"]["module_art_error"] = "vmod not found locally"

    # 3. manuals: rule PDFs bundled in the module (indexed by harvest) + hubs
    hp = os.path.join(META, "harvest",
                      re.sub(r"[^a-zA-Z0-9._-]+", "_",
                             os.path.splitext(os.path.basename(vmod or ""))[0]) + ".json")
    if os.path.exists(hp):
        h = json.load(open(hp, encoding="utf-8"))
        rec["manuals_in_module"] = h.get("rules", {}).get("pdfs", [])
    # 4. how-to-play video SEARCH links (labeled as searches, not curated picks)
    q = urllib.parse.quote_plus(f"how to play {title} board game")
    rec["video_searches"] = [
        dict(label="YouTube: how to play", url=f"https://www.youtube.com/results?search_query={q}")]
    rec["bgg_note"] = "BGG XML API returns 401 (API-key program) — needs registered key"

    json.dump(rec, open(os.path.join(d, "assets.json"), "w", encoding="utf-8"), indent=1)
    return rec


def main(slugs, resume=False):
    cat = json.load(open(census.CATALOG, encoding="utf-8"))
    if resume:
        slugs = [s for s in slugs
                 if not os.path.exists(os.path.join(ASSETS, s, "assets.json"))]
        print(f"resume: {len(slugs)} games still need assets")
    hits = dict(cover_vassal=0, cover_module=0, map_background=0, counters_composite=0)
    for i, slug in enumerate(slugs):
        rec = gather(slug, cat)
        s = rec.get("sources", {})
        for k in hits:
            hits[k] += 1 if s.get(k) else 0
        flags = "".join(k[0].upper() if s.get(k) else "-" for k in
                        ("cover_vassal", "cover_module", "map_background", "counters_composite"))
        print(f"[{i + 1}/{len(slugs)}] {rec.get('title', slug):50} [{flags}] "
              + (s.get("counters_composite") or ""))
        time.sleep(1.0)
    n = len(slugs)
    print("\nhit rates: " + ", ".join(f"{k} {v}/{n}" for k, v in hits.items()))


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--all" in args:
        cat = json.load(open(census.CATALOG, encoding="utf-8"))
        slugs = sorted(s for s, e in cat.items()
                       if "error" not in e and census.main_vmod(e))
        main(slugs, resume=True)
    else:
        main(PILOT_SLUGS if "--pilot" in args else args)
