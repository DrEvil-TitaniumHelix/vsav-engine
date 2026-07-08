"""
ingest.py - Generalized VASSAL .vmod ingest: one command, structured output.

    python engine/ingest.py <path-to.vmod> [--out games/<name>] [--staging <dir>] [--name <slug>]
    python engine/ingest.py --batch <dir-with-vmods> [--scorecard SCORECARD.md]

Tier-0 conversion only (spec #1): extract the module, detect the board grid,
parse the piece definitions, find bundled setups, and emit a game.json
skeleton plus an honest per-module INGEST_REPORT.md of what worked, what
didn't, and why. NO rules are learned and NO enforcement is claimed here —
stats/movement in the skeleton are placeholders marked UNVERIFIED.

Grid detection strategies, in order:
  1. HexGrid element in the buildFile (possibly inside ZonedGrid zones) —
     dx/dy/x0/y0 read directly; sideways=false -> flat-top (Arnhem-style).
  2. RegionGrid snap points -> robust lattice fit, both orientations tried
     (the Tobruk method, generalized); few named regions -> point-to-point
     board, reported as such (no lattice).
  3. SquareGrid -> recorded, but the engine has no square-grid support yet.
  4. Nothing -> placeholder grid, loudly flagged (pieces still pushable).

Assets (map, counters, setup saves) stay in the staging directory OUTSIDE
the repo — game.json references them relatively, nothing is committed.
"""
import argparse, html, json, os, re, statistics, sys, zipfile
from collections import Counter, defaultdict
from xml.etree import ElementTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vsav

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ESC = "\x1b"
if hasattr(sys.stdout, "reconfigure"):     # Windows console: don't die on em-dashes
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PIECE_RE = re.compile(r"^\+/(\d+)/(\w+);")
STACK_RE = re.compile(r"^\+/(\d+)/stack/([^;]+);(-?\d+);(-?\d+)((?:;\d+)*)\\*$")
POS32_RE = re.compile(r"false;[^;]*;1;(-?\d+),(-?\d+)")
SLOT_RE = re.compile(
    r'<VASSAL\.build\.widget\.(?:Piece|Card)Slot[^>]*?entryName="([^"]*)"[^>]*?gpid="([^"]*)"[^>]*>'
    r'(.*?)</VASSAL\.build\.widget\.(?:Piece|Card)Slot>', re.S)


def slugify(name):
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "module"


def local(tag):
    return tag.rsplit(".", 1)[-1]


def attrs_f(el, *names, default=None):
    for n in names:
        v = el.get(n)
        if v is not None:
            try:
                return float(v)
            except ValueError:
                return default
    return default


# ---------------------------------------------------------------- extraction
def extract_vmod(vmod_path, staging):
    extracted = os.path.join(staging, "extracted")
    os.makedirs(extracted, exist_ok=True)
    with zipfile.ZipFile(vmod_path) as z:
        z.extractall(extracted)
        names = z.namelist()
    bf = next((os.path.join(extracted, n) for n in ("buildFile", "buildFile.xml")
               if os.path.exists(os.path.join(extracted, n))), None)
    return extracted, bf, names


def parse_moduledata(extracted):
    p = os.path.join(extracted, "moduledata")
    out = {"name": None, "version": None}
    if os.path.exists(p):
        txt = open(p, encoding="utf-8", errors="replace").read()
        for k in out:
            m = re.search(rf"<{k}>([^<]*)</{k}>", txt)
            if m:
                out[k] = html.unescape(m.group(1)).strip()
    return out


# ---------------------------------------------------------------- buildFile
def parse_buildfile(bf_path):
    """Walk the buildFile: maps, boards, grids, sides, setups, decks, pieces."""
    raw = open(bf_path, "rb").read()
    txt = raw.decode("utf-8", errors="replace")
    root = ElementTree.fromstring(raw)

    mod = dict(maps=[], sides=[], predefined_setups=[], decks=0, cards=0,
               charts=[], prototypes=0, slots=[], parse="elementtree")

    for el in root.iter():
        lt = local(el.tag)
        if lt == "PlayerRoster":
            mod["sides"] = [e.text.strip() for e in el if local(e.tag) == "entry" and e.text]
        elif lt == "PredefinedSetup":
            if el.get("useFile", "false") == "true" and el.get("file"):
                mod["predefined_setups"].append(
                    dict(name=el.get("name", ""), file=el.get("file")))
        elif lt == "DrawPile":
            mod["decks"] += 1
        elif lt == "CardSlot":
            mod["cards"] += 1
        elif lt == "PrototypeDefinition":
            mod["prototypes"] += 1
        elif lt in ("ChartWindow", "BrowserHelpFile", "PDFHelpFile", "HelpFile"):
            n = el.get("name") or el.get("title") or el.get("fileName") or lt
            mod["charts"].append(n)

    for mp in root.iter():
        lt = local(mp.tag)
        # stock Map/PrivateMap plus custom subclasses (VASL's ASLMap etc.)
        if not (lt in ("Map", "PrivateMap")
                or (lt.endswith("Map") and mp.get("mapName") is not None)):
            continue
        m = dict(name=mp.get("mapName", ""), private=lt == "PrivateMap",
                 boards=[], setup_stacks=0, at_start=[])
        for el in mp.iter():
            lt = local(el.tag)
            if lt == "Board":
                m["boards"].append(parse_board(el))
            elif lt in ("SetupStack", "AtStartStack"):
                m["setup_stacks"] += 1
                x, y = attrs_f(el, "x", default=0), attrs_f(el, "y", default=0)
                for ps in el.iter():
                    if local(ps.tag) in ("PieceSlot", "CardSlot"):
                        m["at_start"].append(dict(gpid=ps.get("gpid", ""),
                                                  name=ps.get("entryName", ""),
                                                  x=int(x or 0), y=int(y or 0)))
        mod["maps"].append(m)

    # piece slots from the raw text (same regex family make_save.py uses)
    for name, gpid, body in SLOT_RE.findall(txt):
        b = html.unescape(body)
        has_img = bool(re.search(r"piece;[^;]*;[^;]*;[^;]+?\.(?:png|gif|svg|jpg);", b))
        mod["slots"].append(dict(name=html.unescape(name), gpid=gpid,
                                 has_img=has_img, layered="emb2;" in b))
    return mod


def parse_board(el):
    b = dict(name=el.get("name", ""), image=el.get("image"),
             width=el.get("width"), height=el.get("height"), grids=[])
    for g in el.iter():
        lt = local(g.tag)
        if lt == "HexGrid":
            num = next((dict(n.attrib) for n in g if local(n.tag).endswith("GridNumbering")), None)
            b["grids"].append(dict(kind="hex", dx=attrs_f(g, "dx"), dy=attrs_f(g, "dy"),
                                   x0=attrs_f(g, "x0", default=0), y0=attrs_f(g, "y0", default=0),
                                   sideways=g.get("sideways", "false") == "true",
                                   numbering=num))
        elif lt == "SquareGrid":
            b["grids"].append(dict(kind="square", dx=attrs_f(g, "dx"), dy=attrs_f(g, "dy"),
                                   x0=attrs_f(g, "x0", default=0), y0=attrs_f(g, "y0", default=0)))
        elif lt == "RegionGrid":
            pts, names = [], set()
            for r in g.iter():
                if local(r.tag) == "Region":
                    pts.append((int(float(r.get("originx", 0))), int(float(r.get("originy", 0)))))
                    names.add(r.get("name", ""))
            b["grids"].append(dict(kind="region", points=pts,
                                   named=len(names - {"New Region", ""})))
    return b


# ---------------------------------------------------------------- region fit
def fit_region_lattice(points):
    """Robust-fit a staggered hex lattice to RegionGrid snap points (the
    Tobruk method, generalized: both orientations tried, thresholds scaled
    to the fitted spacing, quality reported honestly)."""
    best = None
    for orient in ("pointy", "flat"):
        fit = _fit_axis(points, orient)
        if fit and (best is None or fit["bad"] < best["bad"]):
            best = fit
    return best


def _fit_axis(points, orient):
    # pointy: cluster by y (rows), stagger in x. flat: cluster by x (cols), stagger in y.
    a = 1 if orient == "pointy" else 0     # clustered axis
    b = 1 - a                              # staggered axis
    vals = sorted(p[a] for p in points)
    if len(vals) < 20:
        return None
    clusters = [[vals[0]]]
    for v in vals[1:]:
        if v - clusters[-1][-1] > 30:
            clusters.append([])
        clusters[-1].append(v)
    keep = [(statistics.median(c), len(c)) for c in clusters if len(c) >= 5]
    if len(keep) < 4:
        return None
    centers = [c for c, _ in keep]
    gaps = [q - p for p, q in zip(centers, centers[1:])]
    da = statistics.median(gaps)
    if da < 20:
        return None
    byc = defaultdict(list)
    for p in points:
        ci = min(range(len(centers)), key=lambda i: abs(centers[i] - p[a]))
        if abs(centers[ci] - p[a]) < da * 0.25:
            byc[ci].append(p[b])
    bgaps = []
    for xs in byc.values():
        xs = sorted(xs)
        bgaps += [q - p for p, q in zip(xs, xs[1:]) if p != q]
    if not bgaps:
        return None
    d0 = statistics.median(bgaps)
    inb = [g for g in bgaps if 0.7 * d0 < g < 1.3 * d0]
    if len(inb) < 10:
        return None
    db = statistics.median(inb)
    phases = {ci: statistics.median(x % db for x in xs) for ci, xs in byc.items() if xs}
    even = [ph for ci, ph in phases.items() if ci % 2 == 0]
    odd = [ph for ci, ph in phases.items() if ci % 2 == 1]
    if not even or not odd:
        return None
    pe, po = statistics.median(even), statistics.median(odd)
    diff = abs(pe - po)
    stagger = abs(diff - db / 2) < db * 0.15
    b0, a0 = pe, centers[0] % da
    tol = 0.2 * min(da, db)
    bad = 0
    for p in points:
        ci = round((p[a] - a0) / da)
        if abs(a0 + ci * da - p[a]) > tol:
            bad += 1
            continue
        off = (db / 2) if (stagger and ci % 2 == 1) else 0.0
        cj = round((p[b] - b0 - off) / db)
        if abs(b0 + cj * db + off - p[b]) > tol:
            bad += 1
    n = len(points)
    if orient == "pointy":
        cfg = dict(orient="pointy", dx=round(db, 2), dy=round(da, 2),
                   x0=round(b0, 1), y0=round(a0, 1), stagger=stagger, offset_parity=1)
    else:
        cfg = dict(orient="flat", dx=round(da, 2), dy=round(db, 2),
                   x0=round(a0, 1), y0=round(b0, 1), stagger=stagger, stagger_sign=1)
    cfg.update(bad=bad, n=n, bad_pct=round(100.0 * bad / n, 1))
    return cfg


# ---------------------------------------------------------------- external boards
def load_external_board(boards_dir, want, staging):
    """VASL-pattern modules ship NO boards — players download board archives
    separately (e.g. github vasl-developers bdFiles). A board archive is a dir
    or zip holding BoardMetadata.xml + the board image; the metadata declares
    the board's size IN HEXES, so the grid is computed from the board's own
    data (dx = imageW/(cols-1), dy = imageH/rows — VASL geoboard convention:
    A1 top-left, odd letter-columns shifted up half a hex).
    Returns (board_dict, err_msg): exactly one is None."""
    cands = []
    for entry in sorted(os.listdir(boards_dir)):
        p = os.path.join(boards_dir, entry)
        try:
            if os.path.isdir(p) and os.path.exists(os.path.join(p, "BoardMetadata.xml")):
                cands.append((entry, p, False))
            elif os.path.isfile(p) and zipfile.is_zipfile(p):
                with zipfile.ZipFile(p) as z:
                    if any(n.endswith("BoardMetadata.xml") for n in z.namelist()):
                        cands.append((entry, p, True))
        except OSError:
            continue
    if not cands:
        return None, f"no board archives (BoardMetadata.xml) found in {boards_dir}"
    pick = None
    if want:
        pick = next((c for c in cands if want.lower() in c[0].lower()), None)
        if pick is None:
            return None, f"--board {want!r} not among {[c[0] for c in cands]}"
    entry, path, is_zip = pick or cands[0]
    if is_zip:
        dst = os.path.join(staging, "boards", os.path.splitext(entry)[0])
        os.makedirs(dst, exist_ok=True)
        with zipfile.ZipFile(path) as z:
            z.extractall(dst)
        path = dst
    meta_path = os.path.join(path, "BoardMetadata.xml")
    if not os.path.exists(meta_path):
        for base, _, files in os.walk(path):
            if "BoardMetadata.xml" in files:
                meta_path = os.path.join(base, "BoardMetadata.xml")
                break
    md = ElementTree.parse(meta_path).getroot().attrib
    cols, rows = int(md.get("width", 0)), int(md.get("height", 0))
    img = os.path.join(os.path.dirname(meta_path), md.get("boardImageFileName", ""))
    if not (cols > 1 and rows and os.path.exists(img)):
        return None, f"board {entry!r}: metadata incomplete (width={md.get('width')} " \
                     f"height={md.get('height')} image={md.get('boardImageFileName')!r})"
    dims = img_size(img)
    if not dims:
        return None, f"board {entry!r}: image {os.path.basename(img)} unreadable"
    dx, dy = dims[0] / (cols - 1), dims[1] / rows
    grid = dict(orient="flat", dx=round(dx, 3), dy=round(dy, 3), x0=0.0, y0=round(-dy / 2, 3),
                stagger=True, stagger_sign=-1, odd_row_carry=0, hexnum_digits=2,
                naming={"style": "colletter"},
                provenance=(f"computed from the board's own metadata: {cols}x{rows} hexes "
                            f"declared, image {dims[0]}x{dims[1]} px -> dx={round(dx, 3)} "
                            f"dy={round(dy, 3)}; VASL geoboard convention (A1 top-left, "
                            "odd letter-columns shifted up)"))
    name = md.get("name", entry)
    return dict(entry=entry, name=name.lstrip("0") or name, image=img, grid=grid,
                cols=cols, rows=rows, n_candidates=len(cands),
                terrain_meta=os.path.exists(os.path.join(os.path.dirname(meta_path), "LOSData"))), None


# ---------------------------------------------------------------- grids -> engine
def hexgrid_to_engine(g):
    """Map a VASSAL HexGrid to our Grid config. sideways=false (flat-top,
    staggered columns) is validated against Arnhem; sideways=true swaps axes
    in VASSAL's renderer — mapped best-effort, flagged unverified."""
    if not g["sideways"]:
        cfg = dict(orient="flat", dx=g["dx"], dy=g["dy"], x0=g["x0"], y0=g["y0"],
                   stagger=True, stagger_sign=1, odd_row_carry=1)
        conf = "hexgrid-direct (flat-top mapping validated on Westwall/Arnhem)"
    else:
        cfg = dict(orient="pointy", dx=g["dy"], dy=g["dx"], x0=g["y0"], y0=g["x0"],
                   stagger=True, offset_parity=1)
        conf = "hexgrid-sideways (axis-swap mapping UNVERIFIED — validate vs a printed hex before trusting)"
    num = g.get("numbering")
    if num:
        cfg["provenance"] = (f"{conf}; module numbering: first={num.get('first')} "
                             f"hType={num.get('hType')} vType={num.get('vType')} "
                             f"hOff={num.get('hOff')} vOff={num.get('vOff')} "
                             f"stagger={num.get('stagger')} — hex LABELS unverified, geometry is what matters for Tier 0")
    else:
        cfg["provenance"] = conf + "; no grid numbering in module"
    cfg["hexnum_digits"] = 2
    return cfg


# ---------------------------------------------------------------- saves
def read_any_save(path):
    """Decode any VASSAL save generation: modern 3-entry zip, zip missing
    moduledata/savedata (some modules strip them), or the pre-3.x form — a
    bare obfuscated '!VCSK' stream, no zip at all. Returns (plain, key)."""
    try:
        with zipfile.ZipFile(path) as z:
            raw = z.read("savedGame").decode("latin-1")
    except zipfile.BadZipFile:
        raw = open(path, "rb").read().decode("latin-1")
    if not raw.startswith("!VCSK"):
        raise ValueError("not an obfuscated VASSAL save (no !VCSK header)")
    return vsav.decode_saved(raw), int(raw[5:7], 16)


def inspect_save(path, key_hint=None):
    """Decode a save (any generation) and count what our parsers can resolve."""
    plain, key = read_any_save(path)
    cmds = plain.split(ESC)
    kinds = Counter()
    pieces, positioned, in_stacks = 0, 0, 0
    stack_members = set()
    for c in cmds:
        m = STACK_RE.match(c.rstrip())
        if m:
            stack_members.update(s for s in m.group(5).split(";") if s)
            continue
        m = PIECE_RE.match(c)
        if m:
            pieces += 1
            kinds[m.group(2)] += 1
            if POS32_RE.search(c) or re.search(r"[;\t][^;\t]+;(-?\d+);(-?\d+);\d*(?:[\t\\]|$)", c):
                positioned += 1
    for c in cmds:
        m = PIECE_RE.match(c)
        if m and m.group(1) in stack_members:
            in_stacks += 1
    return dict(pieces=pieces, positioned=positioned, in_stacks=in_stacks,
                kinds=dict(kinds), key=f"{key:02x}")


# ---------------------------------------------------------------- images
def img_size(path):
    try:
        with open(path, "rb") as f:
            head = f.read(32)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            import struct
            return struct.unpack(">II", head[16:24])
        if head[:6] in (b"GIF87a", b"GIF89a"):
            import struct
            return struct.unpack("<HH", head[6:10])
        if head[:2] == b"BM":
            import struct
            w, h = struct.unpack("<ii", head[18:26])
            return abs(w), abs(h)
    except OSError:
        return None
    try:
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = None
        with Image.open(path) as im:
            return im.size
    except Exception:
        return None


def find_image(extracted, image_name):
    if not image_name:
        return None
    p = os.path.join(extracted, "images", image_name)
    if os.path.exists(p):
        return p
    for base, _, files in os.walk(extracted):
        if image_name in files:
            return os.path.join(base, image_name)
    return None


def stage_map(img_path, staging):
    """Board image -> a UI-servable asset (PNG/GIF as-is; else convert)."""
    ext = os.path.splitext(img_path)[1].lower()
    if ext in (".png", ".gif"):
        return img_path, None
    out = os.path.join(staging, "assets", "map.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if os.path.exists(out):
        return out, None
    try:
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = None
        Image.open(img_path).convert("RGB").save(out, optimize=True)
        return out, None
    except ImportError:
        return None, f"map is {ext} — needs Pillow to convert (pip install pillow)"
    except Exception as e:
        return None, f"map conversion failed: {e}"


# ---------------------------------------------------------------- ingest
def ingest(vmod_path, out_dir=None, staging_root=None, name=None,
           boards_dir=None, board_pick=None):
    rep = dict(vmod=os.path.abspath(vmod_path), steps=[], problems=[], verdict=None)

    def ok(msg):
        rep["steps"].append(msg)
        print("  +", msg)

    def bad(msg):
        rep["problems"].append(msg)
        print("  !", msg)

    print(f"ingest: {vmod_path}")
    try:
        with zipfile.ZipFile(vmod_path) as z:
            z.testzip()
    except Exception as e:
        bad(f"not a readable zip: {e}")
        rep["verdict"] = "FAIL"
        return rep

    # --- extract
    tmp_staging = staging_root or os.path.join(ROOT, "..", "VassalIngest", "_tmp")
    mdname = None
    with zipfile.ZipFile(vmod_path) as z:
        if "moduledata" in z.namelist():
            mdname = re.search(rb"<name>([^<]*)</name>", z.read("moduledata"))
    modname = html.unescape(mdname.group(1).decode("utf-8", "replace")) if mdname else \
        os.path.splitext(os.path.basename(vmod_path))[0]
    slug = name or slugify(modname)
    staging = os.path.normpath(staging_root or os.path.join(ROOT, "..", "VassalIngest", slug))
    out_dir = os.path.normpath(out_dir or os.path.join(ROOT, "games", slug))

    extracted, bf_path, zip_names = extract_vmod(vmod_path, staging)
    md = parse_moduledata(extracted)
    rep.update(module=md["name"] or modname, version=md["version"], slug=slug,
               staging=staging, out=out_dir)
    ok(f"extracted {len(zip_names)} entries -> {extracted}")
    n_images = sum(1 for n in zip_names if n.startswith("images/") and not n.endswith("/"))
    ok(f"module: {rep['module']!r} v{md['version']}; {n_images} images staged")
    pdfs = [n for n in zip_names if n.lower().endswith(".pdf")]
    if pdfs:
        ok(f"{len(pdfs)} PDF(s) bundled (rules material?): {', '.join(pdfs[:5])}")
    rep["pdfs"] = pdfs

    if not bf_path:
        bad("no buildFile in module")
        rep["verdict"] = "FAIL"
        return rep

    # --- buildFile
    try:
        mod = parse_buildfile(bf_path)
    except ElementTree.ParseError as e:
        bad(f"buildFile is not parseable XML: {e}")
        rep["verdict"] = "FAIL"
        return rep
    rep["buildfile"] = mod
    n_slots = len(mod["slots"])
    n_img = sum(1 for s in mod["slots"] if s["has_img"])
    n_layered = sum(1 for s in mod["slots"] if s["layered"] and not s["has_img"])
    ok(f"{n_slots} piece/card slots ({n_img} with BasicPiece art, "
       f"{n_layered} blank-image layer pieces VASL-style); {mod['prototypes']} prototypes")
    if mod["sides"]:
        ok(f"declared sides: {mod['sides']}")
    if mod["decks"] or mod["cards"]:
        ok(f"{mod['decks']} card deck(s) / {mod['cards']} card slot(s) — cards NOT converted (engine future)")

    # --- choose main map/board
    def board_weight(b):
        img = find_image(extracted, b["image"])
        return os.path.getsize(img) if img else 0

    cands = [(m, b) for m in mod["maps"] for b in m["boards"] if not m["private"]]
    if not cands:
        cands = [(m, b) for m in mod["maps"] for b in m["boards"]]
    if not cands:
        bad("no Map/Board elements found")
        rep["verdict"] = "FAIL"
        return rep
    gridded = [(m, b) for m, b in cands if b["grids"]]
    main_map, main_board = max(gridded or cands, key=lambda mb: board_weight(mb[1]))
    rep["main_map"], rep["main_board"] = main_map["name"], main_board["name"]
    if not board_weight(main_board) and not main_board["grids"]:
        bad(f"no playable board bundled: {len(cands)} board entries but none has both an "
            "image in the module and a grid (external-boards pattern — VASL downloads "
            "boards separately; conversion needs the board files too)")
    others = [f"{b['name'] or b['image']} (map {m['name']!r})"
              for m, b in cands if b is not main_board]
    ok(f"main board: {main_board['name']!r} on map {main_map['name']!r}"
       + (f"; {len(others)} other board(s) not converted: {', '.join(others[:6])}" if others else ""))

    # --- external board files (--boards): the VASL pattern
    ext = None
    if boards_dir and not (main_board["grids"] and find_image(extracted, main_board["image"])):
        ext, err = load_external_board(boards_dir, board_pick, staging)
        if err:
            bad(err)
        else:
            ok(f"external board {ext['entry']!r} (board name {ext['name']!r}, "
               f"{ext['cols']}x{ext['rows']} hexes, {ext['n_candidates']} archive(s) available"
               + (", LOSData present" if ext["terrain_meta"] else "") + ")")
            # the map that TAKES external boards is the one shipping without any
            boardless = [m for m in mod["maps"] if not m["private"] and not m["boards"]]
            tgt = next((m for m in boardless if m["name"] == "Main Map"),
                       boardless[0] if boardless else None)
            if tgt:
                main_map = tgt
                rep["main_map"] = tgt["name"]
                ok(f"targeting map window {tgt['name']!r} (ships boardless — takes external boards)")

    # --- grid
    grid_cfg, grid_how = None, None
    hexes = [g for g in main_board["grids"] if g["kind"] == "hex" and g["dx"]]
    regions = [g for g in main_board["grids"] if g["kind"] == "region"]
    squares = [g for g in main_board["grids"] if g["kind"] == "square"]
    if ext:
        grid_cfg, grid_how = ext["grid"], "board-file-metadata"
        ok(f"grid from board metadata: flat dx={grid_cfg['dx']} dy={grid_cfg['dy']} "
           f"origin=({grid_cfg['x0']},{grid_cfg['y0']})")
    elif hexes:
        g = next((h for h in hexes if h.get("numbering")), hexes[0])
        grid_cfg, grid_how = hexgrid_to_engine(g), "hexgrid"
        ok(f"hex grid from buildFile: {grid_cfg['orient']} dx={grid_cfg['dx']} dy={grid_cfg['dy']} "
           f"origin=({grid_cfg['x0']},{grid_cfg['y0']})" + (" [SIDEWAYS — unverified mapping]" if g["sideways"] else ""))
    elif regions and len(regions[0]["points"]) >= 30 and not regions[0]["named"]:
        fit = fit_region_lattice(regions[0]["points"])
        if fit and fit["bad_pct"] <= 5.0:
            q = dict(fit)
            bad_pct = q.pop("bad_pct"); q.pop("bad"); q.pop("n")
            grid_cfg, grid_how = q, "region-fit"
            grid_cfg["hexnum_digits"] = 2
            grid_cfg["provenance"] = (f"lattice fitted from {fit['n']} RegionGrid snap points, "
                                      f"{fit['bad']} outliers ({bad_pct}%) — Tobruk method")
            ok(f"grid FITTED from {fit['n']} region snap points: {fit['orient']} "
               f"dx={fit['dx']} dy={fit['dy']} origin=({fit['x0']},{fit['y0']}) [{bad_pct}% outliers]")
        else:
            bad(f"region lattice fit failed ({len(regions[0]['points'])} points"
                + (f", {fit['bad_pct']}% outliers" if fit else ", no consistent spacing") + ")")
    elif regions and regions[0]["named"]:
        bad(f"board uses {regions[0]['named']} NAMED regions (point-to-point/area map) — "
            "engine has no region-space support yet")
        rep["region_names"] = regions[0]["named"]
    elif squares:
        bad(f"board uses a SQUARE grid (dx={squares[0]['dx']}) — engine has no square-grid support yet")
    else:
        bad("no grid of any kind on the main board")
    rep["grid"], rep["grid_how"] = grid_cfg, grid_how

    # --- map asset
    img_path = ext["image"] if ext else find_image(extracted, main_board["image"])
    map_asset, map_dims = None, None
    if not img_path:
        bad("main board has no bundled image" if not main_board["image"] else
            f"board image {main_board['image']!r} not found in module")
    else:
        map_asset, err = stage_map(img_path, staging)
        if err:
            bad(err)
        else:
            map_dims = img_size(map_asset)
            ok(f"map asset: {os.path.basename(map_asset)}"
               + (f" ({map_dims[0]}x{map_dims[1]} px)" if map_dims else ""))
    rep["map_asset"] = map_asset

    # --- setups
    setups = []
    setup_dir = os.path.join(staging, "setups")
    for ps in mod["predefined_setups"]:
        src = os.path.join(extracted, *ps["file"].split("/"))
        if not os.path.exists(src):
            bad(f"setup {ps['name']!r}: file {ps['file']!r} missing from module")
            continue
        try:
            info = inspect_save(src)
            os.makedirs(setup_dir, exist_ok=True)
            base = os.path.basename(ps["file"])
            dst = os.path.join(setup_dir, base if base.lower().endswith(".vsav") else base + ".vsav")
            if not os.path.exists(dst):
                try:
                    vsav.read_vsav(src)          # already a modern 3-entry zip?
                    import shutil
                    shutil.copy(src, dst)
                    legacy = ""
                except Exception:
                    # legacy form: normalize to a modern .vsav (same key, module's
                    # own moduledata) so board.py / the UI load it unchanged
                    plain, key = read_any_save(src)
                    moduledata = open(os.path.join(extracted, "moduledata"), "rb").read() \
                        if os.path.exists(os.path.join(extracted, "moduledata")) else b"<data/>"
                    savedata = (b'<?xml version="1.0" encoding="UTF-8"?>\n<data version="1">\n'
                                b'  <version></version>\n  <VassalVersion>3.2.17</VassalVersion>\n'
                                b'  <dateSaved>0</dateSaved>\n</data>')
                    vsav.write_vsav(dst, plain, moduledata, savedata, key=key)
                    legacy = ", LEGACY save normalized to modern .vsav"
            else:
                legacy = ""
            setups.append(dict(name=ps["name"], path=dst, **info))
            ok(f"setup {ps['name']!r}: {info['pieces']} pieces "
               f"({info['positioned']} self-positioned, {info['in_stacks']} in stacks), "
               f"key 0x{info['key']}{legacy}")
        except Exception as e:
            bad(f"setup {ps['name']!r} ({ps['file']}): undecodable — {e}")
    at_start = [u for m in mod["maps"] if m is main_map for u in m["at_start"]]
    rep["setups"], rep["at_start_count"] = setups, len(at_start)
    if not setups and at_start:
        ok(f"no bundled .vsav setups, but {len(at_start)} at-start pieces on the main map "
           "(SetupStack) — convertible")
    elif not setups and not at_start:
        bad("no setups of any kind: no bundled saves, no at-start stacks — board starts empty")

    # --- terrain metadata
    terr = [n for n in zip_names if re.search(r"(BoardMetadata|SharedBoardMetadata)\.xml$", n)]
    if terr:
        ok(f"terrain metadata present ({', '.join(terr[:3])}) — extractable later (VASL method)")
    else:
        ok("no terrain metadata (normal — terrain is not a Tier-0 item)")
    rep["terrain_meta"] = terr

    # --- game.json skeleton
    save_key = setups[0]["key"] if setups else "a3"
    placeholder = grid_cfg is None
    if placeholder:
        grid_cfg = dict(orient="flat", dx=100.0, dy=100.0, x0=50.0, y0=50.0,
                        stagger=False, hexnum_digits=2,
                        provenance="PLACEHOLDER — no grid detected; snapping is arbitrary, replace before use")
    bounds = None
    if ext:
        bounds = dict(cols=[0, ext["cols"] - 1], rows=[1, ext["rows"]])
    elif map_dims:
        bounds = dict(cols=[0, max(1, int((map_dims[0] - grid_cfg["x0"]) / grid_cfg["dx"]))],
                      rows=[0, max(1, int((map_dims[1] - grid_cfg["y0"]) / grid_cfg["dy"]))])
    unit_kinds = sorted(setups[0]["kinds"]) if setups else ["piece", "prototype", "mark", "hideCmd"]
    sides = [s for s in mod["sides"] if s.lower() not in ("solitaire", "solo", "referee", "observer")]
    if len(sides) < 2:
        sides = (sides + ["Side A", "Side B"])[:2]
    rel = lambda p: os.path.relpath(p, out_dir).replace("\\", "/")
    spec = {
        "name": f"{rep['module']} — INGESTED Tier-0 skeleton (free play only, nothing verified)",
        "map_name": main_map["name"] or "Main Map",
        "board_name": (ext["name"] if ext else main_board["name"]) or main_map["name"] or "Main Map",
        "save_key": save_key,
        "grid": grid_cfg,
        "buildfile": rel(bf_path),
        "moduledata": rel(os.path.join(extracted, "moduledata")),
        "assets": {"map": rel(map_asset) if map_asset else None,
                   "counters_dir": rel(os.path.join(extracted, "images"))},
        "ui": {"counter_px": 75},
        "unit_kinds": unit_kinds,
        "sides": {"order": sides[:2], "labels": {s: s for s in sides[:2]},
                  "default": sides[1] if len(sides) > 1 else sides[0],
                  "detect_tokens": {},
                  "note": "TODO detect_tokens empty — every piece shows as the default side until filled in"},
        "stats": {"patterns": [], "default": [0, 0, 6],
                  "provenance": "UNVERIFIED placeholder MA for free-play highlighting only — no rules learned (Tier 0)"},
        "movement": {"impassable_terrain": [], "terrain_mp": {}, "default_mp": 1.0,
                     "hexside_rules": [], "zoc": {"exerts": False},
                     "enter_enemy_hex": True, "pass_through_friendly": True,
                     **({"bounds": bounds} if bounds else {}),
                     "note": "Tier 0: uniform 1 MP, no ZOC, no terrain — piece pushing, not rules"},
        "ingest": {"tool": "engine/ingest.py", "grid_how": grid_how or "placeholder",
                   "module_version": md["version"]},
    }
    if setups:
        spec["setup_save"] = rel(setups[0]["path"])
    os.makedirs(out_dir, exist_ok=True)
    spec_path = os.path.join(out_dir, "game.json")
    if os.path.exists(spec_path):
        spec_path = os.path.join(out_dir, "game.ingest.json")
        bad(f"game.json already exists in {out_dir} — wrote {os.path.basename(spec_path)} instead (NOT clobbering a curated spec)")
    with open(spec_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=1)
    ok(f"spec skeleton -> {spec_path}")
    rep["spec_path"] = spec_path

    # --- at-start scenario (only when it's the only setup source)
    if not setups and at_start and not placeholder:
        usable = [u for u in at_start if u["gpid"]]
        scen = dict(name=f"{rep['module']} at-start setup (from module SetupStacks)",
                    units=[dict(gpid=u["gpid"], xy=[u["x"], u["y"]]) for u in usable])
        scen_path = os.path.join(out_dir, "scenario_atstart.json")
        json.dump(scen, open(scen_path, "w", encoding="utf-8"), indent=1)
        try:
            import gamespec, make_save
            game = gamespec.Game(out_dir)
            sav = os.path.join(setup_dir, "atstart.vsav")
            os.makedirs(setup_dir, exist_ok=True)
            make_save.build(game, scen, sav)
            spec["setup_save"] = rel(sav)
            json.dump(spec, open(spec_path, "w", encoding="utf-8"), indent=1)
            setups.append(dict(name="at-start (built)", path=sav, **inspect_save(sav)))
            ok(f"built setup save from {len(usable)} at-start pieces -> {sav}"
               + (f" ({len(at_start) - len(usable)} skipped, no gpid)" if len(usable) < len(at_start) else ""))
        except Exception as e:
            bad(f"at-start save build failed: {e}")

    # --- verdict
    best_setup = max((s["pieces"] for s in setups), default=0)
    if setups and best_setup < 10:
        bad(f"best setup has only {best_setup} piece(s) — likely markers, not a scenario; "
            "real setups need authoring (the make_save scenario-JSON path)")
    if grid_how and setups and best_setup >= 10 and map_asset and n_slots:
        rep["verdict"] = "FULL"
    elif map_asset and n_slots:
        rep["verdict"] = "PARTIAL"
    else:
        rep["verdict"] = "FAIL"
    write_report(rep, out_dir)
    json.dump({k: v for k, v in rep.items() if k != "buildfile"},
              open(os.path.join(out_dir, "ingest_summary.json"), "w", encoding="utf-8"),
              indent=1, default=str)
    print(f"  = verdict: {rep['verdict']}  (report: {os.path.join(out_dir, 'INGEST_REPORT.md')})")
    return rep


# ---------------------------------------------------------------- report
def write_report(rep, out_dir):
    L = [f"# Ingest report — {rep.get('module', os.path.basename(rep['vmod']))}"
         + (f" v{rep.get('version')}" if rep.get("version") else ""),
         "",
         f"**Verdict: {rep['verdict']}** (Tier-0 conversion — free piece pushing; "
         "no rules learned, no enforcement claimed)",
         "",
         f"- module file: `{os.path.basename(rep['vmod'])}`",
         f"- staged at: `{rep.get('staging', '-')}` (assets stay OUT of the repo)",
         ""]
    if rep["verdict"] == "FULL":
        L += [f"Play it:  `python ui/server.py --game {os.path.relpath(out_dir, ROOT)}`", ""]
    L += ["## What worked", ""] + [f"- {s}" for s in rep["steps"]] + [""]
    if rep["problems"]:
        L += ["## What didn't (and why)", ""] + [f"- {p}" for p in rep["problems"]] + [""]
    grid = rep.get("grid")
    if grid:
        L += ["## Grid", "", "```json", json.dumps(grid, indent=1), "```",
              f"- detection: **{rep.get('grid_how') or 'placeholder'}**",
              "- hex geometry is what Tier-0 needs; printed hex LABELS are unverified "
              "until checked against a map anchor.", ""]
    if rep.get("setups"):
        L += ["## Setups", ""]
        for s in rep["setups"]:
            L.append(f"- {s['name']!r}: {s['pieces']} pieces, {s['in_stacks']} in stacks, "
                     f"kinds {s['kinds']}")
        L.append("")
    L += ["---", "*Generated by engine/ingest.py — every claim above was produced by running "
          "the tool against the module, not by hand.*"]
    with open(os.path.join(out_dir, "INGEST_REPORT.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))


# ---------------------------------------------------------------- scorecard
def batch(vmod_dir, scorecard_path):
    reps = []
    vmods = sorted(f for f in os.listdir(vmod_dir) if f.lower().endswith(".vmod"))
    if not vmods:
        print(f"no .vmod files in {vmod_dir}")
        return
    for f in vmods:
        try:
            reps.append(ingest(os.path.join(vmod_dir, f)))
        except Exception as e:
            reps.append(dict(vmod=f, module=f, verdict="FAIL",
                             problems=[f"ingest crashed: {e}"], steps=[]))
            print(f"  ! ingest crashed on {f}: {e}")
    counts = Counter(r["verdict"] for r in reps)
    L = ["# Ingest scorecard — VASSAL .vmod → Tier-0 conversion",
         "",
         f"{len(reps)} modules: **{counts.get('FULL', 0)} full / "
         f"{counts.get('PARTIAL', 0)} partial / {counts.get('FAIL', 0)} fail**. "
         "Tier-0 = board + grid + pieces + a starting setup, playable in the browser "
         "as free piece-pushing (VASSAL-parity, zero rules enforcement). "
         "Failures are data: each row says exactly what's missing.",
         "",
         "| Module | Verdict | Grid | Pieces | Setup | Why not full |",
         "|---|---|---|---|---|---|"]
    for r in reps:
        bf = r.get("buildfile") or {}
        slots = len(bf.get("slots", [])) if bf else "-"
        grid = r.get("grid_how") or "—"
        setups = ", ".join(s["name"] or "unnamed" for s in r.get("setups", [])) or \
            (f"{r.get('at_start_count', 0)} at-start" if r.get("at_start_count") else "—")
        why = "; ".join(r.get("problems", [])[:3]) or "—"
        L.append(f"| {r.get('module', '?')} | {r['verdict']} | {grid} | {slots} | {setups} | {why} |")
    L += ["", "*Every row generated by `engine/ingest.py`; per-module detail in each "
          "game directory's `INGEST_REPORT.md`.*"]
    with open(scorecard_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"\nscorecard -> {scorecard_path}  ({dict(counts)})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="VASSAL .vmod -> Tier-0 game skeleton")
    ap.add_argument("vmod", nargs="?", help="path to a .vmod")
    ap.add_argument("--out", help="output game dir (default games/<slug>)")
    ap.add_argument("--staging", help="asset staging dir (default ../VassalIngest/<slug>)")
    ap.add_argument("--name", help="slug override")
    ap.add_argument("--boards", help="dir of external board archives (VASL pattern)")
    ap.add_argument("--board", help="which external board to use (name fragment)")
    ap.add_argument("--batch", help="ingest every .vmod in this directory")
    ap.add_argument("--scorecard", default=os.path.join(ROOT, "SCORECARD.md"))
    a = ap.parse_args()
    if a.batch:
        batch(a.batch, a.scorecard)
    elif a.vmod:
        ingest(a.vmod, a.out, a.staging, a.name, a.boards, a.board)
    else:
        ap.print_help()
