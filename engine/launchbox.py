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
import json, os, re, shutil, sys, uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import census

OUT = os.path.join(census.LIB, "launchbox")
ASSETS = os.path.join(census.META, "assets")
HARVEST_DIR = os.path.join(census.META, "harvest")
PLATFORM = "VASSAL"
VASSAL_EXE = r"C:\Program Files\VASSAL-3.7.24\VASSAL.exe"
NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
EMU_ID = str(uuid.uuid5(NS, "vassal-engine-emulator"))
MODULE_DIRS = [os.path.join(census.LIB, "modules"), r"C:\VassalIngest\downloads"]


def gid(slug):
    return str(uuid.uuid5(NS, "vassal-game-" + slug))


def clean_title(t):
    return re.sub(r"\s+", " ", re.sub(r"[\\/:*?\"<>|']", "_", t)).strip()


def esc(s):
    return html.escape(str(s), quote=False) if s is not None else ""


def harvest_row(filename):
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "_", os.path.splitext(filename)[0])
    p = os.path.join(HARVEST_DIR, stem + ".json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def game_xml(slug, rec):
    dl = rec.get("download") or {}
    fname = dl.get("filename")
    app = ""
    installed = "No"
    if fname:
        for d in MODULE_DIRS:
            for p in (os.path.join(d, slug, fname), os.path.join(d, fname)):
                if os.path.exists(p):
                    app, installed = p, "Yes"
                    break
            if app:
                break
        if not app:
            app = os.path.join(census.LIB, "modules", slug, fname)   # future home
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
    if year and str(year).isdigit():
        x.append(f"    <ReleaseDate>{year}-01-01T00:00:00</ReleaseDate>")
    x.append("  </Game>")
    cf = [("Installed", installed),
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
    return "\n".join(x), rec.get("title", slug), installed


def copy_art(slug, title):
    src = os.path.join(ASSETS, slug)
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


def build(slugs):
    games, arts, installed_n = [], 0, 0
    for slug in slugs:
        ap = os.path.join(ASSETS, slug, "assets.json")
        if not os.path.exists(ap):
            print(f"  ! no assets.json for {slug} — run game_assets.py first")
            continue
        rec = json.load(open(ap, encoding="utf-8"))
        xml, title, installed = game_xml(slug, rec)
        games.append(xml)
        installed_n += installed == "Yes"
        arts += copy_art(slug, title)
    os.makedirs(os.path.join(OUT, "Data", "Platforms"), exist_ok=True)
    doc = ('<?xml version="1.0" standalone="yes"?>\n<LaunchBox>\n'
           + "\n".join(games) + "\n</LaunchBox>\n")
    with open(os.path.join(OUT, "Data", "Platforms", PLATFORM + ".xml"), "w",
              encoding="utf-8") as f:
        f.write(doc)
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


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--pilot"]
    slugs = args or sorted(os.listdir(ASSETS))
    build(slugs)
