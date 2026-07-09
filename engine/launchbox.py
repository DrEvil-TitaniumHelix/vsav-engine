"""
launchbox.py - Generate a LaunchBox platform ("VASSAL") from the harvest/census
data: games XML + custom fields + per-game art, staged as a drop-in folder.

    python engine/launchbox.py --pilot          # the 26 scorecard games
    python engine/launchbox.py <slug> [...]

Output staging (copy into your LaunchBox folder while LaunchBox is CLOSED):
  C:\\VassalLibrary\\launchbox\\
    Data\\Platforms\\VASSAL.xml        games, custom fields, download links
    Emulators.snippet.xml              VASSAL-as-emulator entry (see INSTRUCTIONS)
    Images\\VASSAL\\Box - Front\\...     covers (library image, else module box art)
    Images\\VASSAL\\Fanart - Background\\...   map backgrounds
    Images\\VASSAL\\Screenshot - Gameplay\\... counter composite sheets
    INSTRUCTIONS.md

Every game record carries the module's direct download URL + sha256 as custom
fields — the XML is a DISTRIBUTABLE INDEX: share it and users fetch only the
modules they want from vassalengine.org (BYO, we never ship module content).
ApplicationPath points at the local mirror location; Installed=Yes/No is
stamped by checking the disk at generation time (regenerate to refresh).
"""
import html
import json, os, re, shutil, sys, uuid, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import census

OUT = os.path.join(census.LIB, "launchbox")
ASSETS = os.path.join(census.META, "assets")
HARVEST_DIR = os.path.join(census.META, "harvest")
PLATFORM = "VASSAL"
VASSAL_EXE = r"C:\Program Files\VASSAL-3.7.24\VASSAL.exe"
NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
EMU_ID = str(uuid.uuid5(NS, "vassal-engine-emulator"))
# where the .vmods live (Bruce: the ROM drive once moved) — override with
# --modules-root or the VASSAL_MODULES env var; first existing hit wins,
# missing modules get their ApplicationPath under the FIRST root
MODULE_DIRS = ([os.environ["VASSAL_MODULES"]] if os.environ.get("VASSAL_MODULES") else []) \
    + [os.path.join(census.LIB, "modules"), r"C:\VassalIngest\downloads"]


def gid(slug):
    return str(uuid.uuid5(NS, "vassal-game-" + slug))


# docs bundled inside modules: PDFs (rulebooks, charts, playbooks, hint cards).
# The one that names itself the rules becomes the LaunchBox manual; every other
# PDF becomes an "Additional App" so it's one click away on the game's page.
MANUAL_RE = re.compile(r"rule|manual|rulebook|livret|regle|regel", re.I)


def extract_bundled_docs(vmod_path, title):
    """Pull every PDF out of the module into Manuals/<PLATFORM>/<title>/."""
    try:
        with zipfile.ZipFile(vmod_path) as z:
            pdfs = [n for n in z.namelist()
                    if n.lower().endswith(".pdf") and not n.endswith("/")]
            if not pdfs:
                return
            outdir = os.path.join(OUT, "Manuals", PLATFORM, clean_title(title))
            os.makedirs(outdir, exist_ok=True)
            seen = set()
            for n in pdfs:
                bn = re.sub(r'[\\/:*?"<>|]', "_", os.path.basename(n)).strip() or "doc.pdf"
                if bn.lower() in seen:
                    bn = f"{len(seen)}_{bn}"
                seen.add(bn.lower())
                dest = os.path.join(outdir, bn)
                if not os.path.exists(dest) or os.path.getsize(dest) != z.getinfo(n).file_size:
                    with z.open(n) as src, open(dest, "wb") as f:
                        shutil.copyfileobj(src, f)
    except Exception:
        pass


def folder_docs(title):
    """Manual + extra docs from EVERYTHING on disk for this game - bundled
    extractions, library-package fetches, publisher living rules alike.
    Returns (manual_relpath, [(name, relpath), ...]) relative to LaunchBox root."""
    t = clean_title(title)
    reldir = os.path.join("Manuals", PLATFORM, t)
    d = os.path.join(OUT, reldir)
    if not os.path.isdir(d):
        return None, []
    pdfs = [(f, os.path.getsize(os.path.join(d, f)))
            for f in os.listdir(d) if f.lower().endswith(".pdf")]
    if not pdfs:
        return None, []
    ranked = sorted(pdfs, key=lambda r: (not MANUAL_RE.search(r[0]), -r[1]))
    manual = os.path.join(reldir, ranked[0][0])
    others = [(f, os.path.join(reldir, f)) for f, _ in ranked[1:]]
    return manual, others


def clean_title(t):
    return re.sub(r"\s+", " ", re.sub(r"[\\/:*?\"<>|']", "_", t)).strip()


def esc(s):
    return html.escape(str(s), quote=False) if s is not None else ""


def harvest_row(filename):
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "_", os.path.splitext(filename)[0])
    p = os.path.join(HARVEST_DIR, stem + ".json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


# slug -> pipeline enrichment (tier score, rules status, screen verdict,
# cross-linked carrier module). Loaded once in build(); every field optional
# so the generator still runs on a bare census.
ENRICH = {}


def load_enrichment():
    def jload(name):
        p = os.path.join(census.META, name)
        return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}

    games = jload("games.json")
    slug2gk = {m["slug"]: gk for gk, g in games.items()
               for m in g.get("modules", []) if m.get("slug")}
    gaps = {x["game"]: x for x in (jload("doc_gaps.json") or [])}
    screen = {x["game"]: x for x in (jload("rules_screen.json") or [])}
    links = jload("crosslinks.json")

    # filename -> on-disk path index (for cross-linked carrier modules)
    findex = {}
    for root in MODULE_DIRS:
        if not os.path.isdir(root):
            continue
        for dirpath, _, files in os.walk(root):
            for f in files:
                if f.lower().endswith(".vmod") and f not in findex:
                    findex[f] = os.path.join(dirpath, f)

    for slug, gk in slug2gk.items():
        e = {}
        d = gaps.get(gk)
        if d:
            e.update(TierScore=d.get("score"), RulesStatus=d.get("rulebook"),
                     CompleteDocSet="Yes" if d.get("complete") else "No",
                     pilot=bool(d.get("pilot")))
        s = screen.get(gk)
        if s:
            e["ScreenVerdict"] = s.get("screen")
            e["clean_fit_ready"] = (s.get("screen") == "CLEAN-FIT"
                                    and s.get("style") == "hex"
                                    and (s.get("setups") or 0) > 0)
        l = links.get(gk)
        if l and l.get("module") in findex:
            e["carrier_path"] = findex[l["module"]]
            e["carrier_module"] = l["module"]
        if e:
            ENRICH[slug] = e


def game_xml(slug, rec):
    dl = rec.get("download") or {}
    fname = dl.get("filename")
    app = ""
    installed = "No"
    if fname:
        for d in MODULE_DIRS:
            for p in (os.path.join(d, slug.rstrip(". ") or slug, fname),
                      os.path.join(d, fname)):
                if os.path.exists(p):
                    app, installed = p, "Yes"
                    break
            if app:
                break
        if not app:
            app = os.path.join(MODULE_DIRS[0], slug, fname)   # future home
    enr = ENRICH.get(slug, {})
    shared = None
    if installed == "No" and enr.get("carrier_path"):
        # stub project: the game lives inside another game's module
        app, installed = enr["carrier_path"], "Yes"
        fname = shared = enr["carrier_module"]
    h = harvest_row(fname) if fname else {}
    pieces = h.get("pieces", {})
    genres = [t.split(":", 1)[1] for t in rec.get("tags", []) if ":" in t
              and not t.split(":", 1)[1].lower().startswith("unknown")]
    year = rec.get("year")
    notes = []
    if h.get("description"):
        notes.append(h["description"])
    notes.append(f"Board style: {h.get('board_style', '?')}. "
                 f"{pieces.get('slots', '?')} piece slots, "
                 f"{len(h.get('setups', []))} bundled setups, "
                 f"{h.get('n_decks', 0)} card decks.")
    notes.append(f"Module library page: {rec.get('library_page')}")
    notes.append(f"Direct module download: {dl.get('url')}")
    if installed == "Yes" and not shared:
        extract_bundled_docs(app, rec.get("title", slug))
    manual, other_docs = folder_docs(rec.get("title", slug))
    g = gid(slug)
    x = ["  <Game>",
         f"    <ID>{g}</ID>",
         f"    <Title>{esc(rec.get('title', slug))}</Title>",
         f"    <ApplicationPath>{esc(app)}</ApplicationPath>",
         f"    <Platform>{PLATFORM}</Platform>",
         f"    <Emulator>{EMU_ID}</Emulator>",
         f"    <Genre>{esc('; '.join(dict.fromkeys(genres)))}</Genre>",
         f"    <Publisher>{esc(rec.get('publisher') or '')}</Publisher>",
         f"    <Notes>{esc(chr(10).join(notes))}</Notes>",
         f"    <Version>{esc(h.get('version') or '')}</Version>"]
    if manual:
        x.append(f"    <ManualPath>{esc(manual)}</ManualPath>")
    if year and str(year).isdigit():
        x.append(f"    <ReleaseDate>{year}-01-01T00:00:00</ReleaseDate>")
    x.append("  </Game>")
    cf = [("Installed", installed),
          ("SharedModule", shared),
          ("TierScore", enr.get("TierScore")),
          ("RulesStatus", enr.get("RulesStatus")),
          ("ScreenVerdict", enr.get("ScreenVerdict")),
          ("CompleteDocSet", enr.get("CompleteDocSet")),
          ("DownloadUrl", dl.get("url")),
          ("SHA256", dl.get("sha256")),
          ("ModuleFile", fname),
          ("ModuleSizeMB", round(dl.get("size", 0) / 1e6, 1) if dl.get("size") else None),
          ("BoardStyle", h.get("board_style")),
          ("PieceSlots", pieces.get("slots")),
          ("Setups", len(h.get("setups", [])) or None),
          ("Sides", ", ".join(h.get("sides", [])[:6]) or None),
          ("Dice", "/".join(f"{d['nDice']}d{d['nSides']}" for d in h.get("dice", [])[:4]) or None),
          ("LibraryPage", rec.get("library_page")),
          ("HowToPlaySearch", (rec.get("video_searches") or [{}])[0].get("url"))]
    for name, val in cf:
        if val not in (None, ""):
            x += ["  <CustomField>",
                  f"    <GameID>{g}</GameID>",
                  f"    <Name>{esc(name)}</Name>",
                  f"    <Value>{esc(val)}</Value>",
                  "  </CustomField>"]
    if dl.get("url"):
        x += ["  <AdditionalApplication>",
              f"    <Id>{str(uuid.uuid5(NS, 'dl-' + slug))}</Id>",
              f"    <GameID>{g}</GameID>",
              f"    <ApplicationPath>{esc(dl['url'])}</ApplicationPath>",
              "    <Name>Download module (opens browser)</Name>",
              "  </AdditionalApplication>"]
    for bn, rel in other_docs:
        x += ["  <AdditionalApplication>",
              f"    <Id>{str(uuid.uuid5(NS, 'doc-' + slug + '-' + bn))}</Id>",
              f"    <GameID>{g}</GameID>",
              f"    <ApplicationPath>{esc(rel)}</ApplicationPath>",
              f"    <Name>Doc: {esc(os.path.splitext(bn)[0])}</Name>",
              "  </AdditionalApplication>"]
    return "\n".join(x), rec.get("title", slug), installed


def copy_art(slug, title):
    src = os.path.join(ASSETS, slug.rstrip(". ") or slug)
    if not os.path.isdir(src):
        return 0
    t = clean_title(title)
    n = 0
    plans = [(("cover_vassal.jpg", "cover_vassal.png", "cover_vassal.gif",
               "cover_module.jpg"), "Box - Front", ".jpg"),
             (("map_background.jpg",), "Fanart - Background", ".jpg"),
             (("counters_composite.png",), "Screenshot - Gameplay", ".png")]
    for cands, folder, ext in plans:
        for c in cands:
            p = os.path.join(src, c)
            if os.path.exists(p):
                d = os.path.join(OUT, "Images", PLATFORM, folder)
                os.makedirs(d, exist_ok=True)
                shutil.copy(p, os.path.join(d, f"{t}-01{ext}"))
                n += 1
                break
    return n


PLAYLISTS = [
    ("VASSAL - Tier-Attempt Ready",
     "Hex games with setups whose rules screened CLEAN-FIT: the next-up "
     "candidates for movement/combat enforcement.",
     lambda e: e.get("clean_fit_ready")),
    ("VASSAL - Complete Document Set",
     "Readable rulebook on disk + bundled setup: everything needed to "
     "attempt the tier ladder.",
     lambda e: e.get("CompleteDocSet") == "Yes"),
    ("VASSAL - Pilot 26",
     "The 26-game ingest scorecard pilot.",
     lambda e: e.get("pilot")),
]


def write_playlists(members):
    d = os.path.join(OUT, "Data", "Playlists")
    os.makedirs(d, exist_ok=True)
    for name, notes, _ in PLAYLISTS:
        pid = str(uuid.uuid5(NS, "vassal-playlist-" + name))
        x = ['<?xml version="1.0" standalone="yes"?>', "<LaunchBox>",
             "  <Playlist>",
             f"    <PlaylistId>{pid}</PlaylistId>",
             f"    <Name>{esc(name)}</Name>",
             f"    <NestedName>{esc(name)}</NestedName>",
             f"    <SortBy>Title</SortBy>",
             f"    <Notes>{esc(notes)}</Notes>",
             "  </Playlist>"]
        for i, (slug, title) in enumerate(sorted(members.get(name, []),
                                                 key=lambda m: m[1]), 1):
            x += ["  <PlaylistGame>",
                  f"    <PlaylistId>{pid}</PlaylistId>",
                  f"    <GameId>{gid(slug)}</GameId>",
                  f"    <GameTitle>{esc(title)}</GameTitle>",
                  f"    <GamePlatform>{PLATFORM}</GamePlatform>",
                  f"    <ManualOrder>{i}</ManualOrder>",
                  "  </PlaylistGame>"]
        x.append("</LaunchBox>")
        fn = re.sub(r'[\\/:*?"<>|]', "_", name) + ".xml"
        with open(os.path.join(d, fn), "w", encoding="utf-8") as f:
            f.write("\n".join(x) + "\n")
    return {n: len(members.get(n, [])) for n, _, _ in PLAYLISTS}


def build(slugs):
    load_enrichment()
    games, arts, installed_n = [], 0, 0
    members = {}
    for slug in slugs:
        ap = os.path.join(ASSETS, slug.rstrip(". ") or slug, "assets.json")
        if not os.path.exists(ap):
            print(f"  ! no assets.json for {slug} — run game_assets.py first")
            continue
        rec = json.load(open(ap, encoding="utf-8"))
        xml, title, installed = game_xml(slug, rec)
        games.append(xml)
        installed_n += installed == "Yes"
        arts += copy_art(slug, title)
        e = ENRICH.get(slug, {})
        for name, _, want in PLAYLISTS:
            if want(e):
                members.setdefault(name, []).append((slug, title))
    os.makedirs(os.path.join(OUT, "Data", "Platforms"), exist_ok=True)
    doc = ('<?xml version="1.0" standalone="yes"?>\n<LaunchBox>\n'
           + "\n".join(games) + "\n</LaunchBox>\n")
    with open(os.path.join(OUT, "Data", "Platforms", PLATFORM + ".xml"), "w",
              encoding="utf-8") as f:
        f.write(doc)
    counts = write_playlists(members)
    with open(os.path.join(OUT, "Emulators.snippet.xml"), "w", encoding="utf-8") as f:
        f.write(f"""<!-- Merge into LaunchBox\\Data\\Emulators.xml (inside <LaunchBox>),
or add VASSAL via Tools > Manage Emulators and re-point games' emulator. -->
  <Emulator>
    <ID>{EMU_ID}</ID>
    <Title>VASSAL</Title>
    <ApplicationPath>{VASSAL_EXE}</ApplicationPath>
    <NoQuotes>false</NoQuotes>
    <NoSpace>false</NoSpace>
  </Emulator>
  <EmulatorPlatform>
    <Emulator>{EMU_ID}</Emulator>
    <Platform>{PLATFORM}</Platform>
    <Default>true</Default>
  </EmulatorPlatform>
""")
    with open(os.path.join(OUT, "INSTRUCTIONS.md"), "w", encoding="utf-8") as f:
        f.write(f"""# VASSAL platform for LaunchBox — install

1. CLOSE LaunchBox.
2. Copy `Data\\Platforms\\VASSAL.xml` into your `LaunchBox\\Data\\Platforms\\`.
3. Copy the `Images\\VASSAL` folder into `LaunchBox\\Images\\`.
3b. Copy the `Manuals\\VASSAL` folder into `LaunchBox\\Manuals\\` — rulebooks
   bundled inside modules appear as each game's Manual; extra PDFs (charts,
   playbooks, hint cards) appear under the game's Additional Apps as "Doc: ...".
3c. Copy the `Data\\Playlists` XMLs into `LaunchBox\\Data\\Playlists\\` —
   curated playlists (Tier-Attempt Ready, Complete Document Set, Pilot 26).
4. Emulator: open `Emulators.snippet.xml` and merge its two blocks into
   `LaunchBox\\Data\\Emulators.xml` (paste just inside `<LaunchBox>`).
   VASSAL executable expected at: {VASSAL_EXE}
5. Start LaunchBox — a "{PLATFORM}" platform appears; games launch VASSAL with
   the module. Games with custom field Installed=No aren't downloaded yet:
   use the game's "Download module" additional app / DownloadUrl custom field,
   save the .vmod to the path shown in ApplicationPath, and it launches.

Regenerating the XML re-checks the disk and refreshes Installed flags.
""")
    print(f"{len(games)} games ({installed_n} installed), {arts} art files -> {OUT}")
    print(f"playlists: {counts}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--modules-root" in args:
        i = args.index("--modules-root")
        MODULE_DIRS.insert(0, args[i + 1])
        del args[i:i + 2]
    args = [a for a in args if a != "--pilot"]
    slugs = args or sorted(os.listdir(ASSETS))
    build(slugs)
