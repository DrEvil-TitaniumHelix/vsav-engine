"""
harvest.py - Extract EVERYTHING machine-readable from a .vmod, in place (no
extraction to disk — members are read straight out of the zip).

    python engine/harvest.py <path.vmod>              # one module -> summary + json
    python engine/harvest.py --sweep <dir> [...]      # every .vmod under dirs (resumable)

Per module -> C:\\VassalLibrary\\_meta\\harvest\\<stem>.json, plus an aggregate
C:\\VassalLibrary\\_meta\\harvest_db.json (one summary row per module).

What's harvested (the full parameterization, of which LaunchBox is one
projection):
  identity   moduledata name/version/description, VASSAL version
  boards     every map/board, dimensions, grid type + geometry + numbering
  regions    named point-to-point spaces WITH pixel coordinates (future
             region-space support data, captured now)
  pieces     slot/prototype counts, art style (ext/none/layered), trait
             histogram (rotate=facing, obs=hidden info, deck/cards, emb2=layers)
  setups     predefined saves + at-start stacks
  play aids  dice buttons (which dice the game rolls), turn tracker, chart
             windows, global properties
  inventory  file census by type; rules PDFs/HTML by name (pre-screen gate 1);
             chart-like images (CRT candidates, gate 5 signals)
  derived    board-style class (the conversion predictor), complexity metrics
"""
import argparse, html, json, os, re, sys, time, zipfile
from collections import Counter
from xml.etree import ElementTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ingest  # local(), attrs_f(), SLOT_RE — one parser family, not two

META = r"C:\VassalLibrary\_meta"
HARVEST_DIR = os.path.join(META, "harvest")
DB = os.path.join(META, "harvest_db.json")

TRAIT_RE = re.compile(r"(?:^|\t)((?:\\+)?)([a-zA-Z][a-zA-Z0-9_]*);")
RULEISH = re.compile(r"rule|manual|book|charts?|player.?aid|reference|crt|tables?", re.I)


def read_member(z, *names):
    for n in names:
        try:
            return z.read(n)
        except KeyError:
            continue
    return None


def harvest(vmod_path):
    h = dict(file=os.path.basename(vmod_path), path=os.path.abspath(vmod_path),
             size=os.path.getsize(vmod_path), ok=False)
    try:
        z = zipfile.ZipFile(vmod_path)
    except Exception as e:
        h["error"] = f"unreadable zip: {e}"
        return h
    with z:
        names = z.namelist()
        md = read_member(z, "moduledata")
        if md:
            txt = md.decode("utf-8", errors="replace")
            for k in ("name", "version", "description", "VassalVersion"):
                m = re.search(rf"<{k}>([^<]*)</{k}>", txt)
                if m:
                    h[k.lower()] = html.unescape(m.group(1)).strip()
        raw = read_member(z, "buildFile", "buildFile.xml")
        if raw is None:
            h["error"] = "no buildFile"
            return h
        try:
            root = ElementTree.fromstring(raw)
        except ElementTree.ParseError as e:
            h["error"] = f"buildFile XML: {e}"
            return h

        # ---- boards & grids & regions ----
        maps, dice, charts, sides = [], [], [], []
        n_setup_stacks = n_atstart = n_decks = n_cards = n_turntrack = 0
        regions_named = []
        for el in root.iter():
            lt = ingest.local(el.tag)
            if lt in ("Map", "PrivateMap") or (lt.endswith("Map") and el.get("mapName") is not None):
                m = dict(name=el.get("mapName", ""), private=lt == "PrivateMap", boards=[],
                         # appearance: how THIS window draws in VASSAL (colors,
                         # edges, move-highlighting) + stack/zoom settings below
                         appearance={k: v for k, v in el.attrib.items()
                                     if k in ("backgroundcolor", "color", "edgeHeight",
                                              "edgeWidth", "markMoved", "markUnmovedIcon",
                                              "buttonName", "allowMultiple", "launch")})
                for b in el.iter():
                    blt = ingest.local(b.tag)
                    if blt == "Board":
                        bd = ingest.parse_board(b)
                        for g in bd["grids"]:
                            g.pop("points", None)   # keep harvest json small
                        m["boards"].append(bd)
                    elif blt in ("SetupStack", "AtStartStack"):
                        n_setup_stacks += 1
                        n_atstart += sum(1 for ps in b.iter()
                                         if ingest.local(ps.tag) in ("PieceSlot", "CardSlot"))
                    elif blt == "StackMetrics":
                        m["stacking"] = dict(b.attrib)
                    elif blt == "Zoomer":
                        m["zoom"] = b.get("zoomLevels") or b.get("zoomFactor")
                    elif blt in ("LayeredPieceCollection", "GamePieceLayers"):
                        m["piece_layers"] = True
                maps.append(m)
            elif lt == "Region":
                nm = el.get("name", "")
                if nm and nm != "New Region":
                    regions_named.append(dict(name=nm, x=int(float(el.get("originx", 0))),
                                              y=int(float(el.get("originy", 0)))))
            elif lt == "DiceButton":
                dice.append(dict(name=el.get("name") or el.get("text", ""),
                                 nDice=el.get("nDice"), nSides=el.get("nSides")))
            elif lt == "ChartWindow":
                charts.append(el.get("name") or "")
            elif lt == "TurnTracker":
                n_turntrack += 1
            elif lt == "DrawPile":
                n_decks += 1
            elif lt == "CardSlot":
                n_cards += 1
            elif lt == "PlayerRoster":
                sides = [e.text.strip() for e in el if ingest.local(e.tag) == "entry" and e.text]

        # ---- piece palette tree: how the module ORGANIZES its counters for the
        # player (PieceWindow -> tabs -> panels/lists); names only, 3 levels ----
        def widget_tree(el, depth=0):
            out = []
            if depth > 3:
                return out
            for ch in el:
                clt = ingest.local(ch.tag)
                if clt in ("TabWidget", "PanelWidget", "BoxWidget", "ListWidget", "MapWidget"):
                    nm = ch.get("entryName") or ch.get("name") or clt
                    kids = widget_tree(ch, depth + 1)
                    out.append({nm: kids} if kids else nm)
            return out
        palette = []
        for el in root.iter():
            if ingest.local(el.tag) == "PieceWindow":
                palette.append({el.get("name", "Pieces"): widget_tree(el)})

        # ---- pieces: slots, art style, trait histogram ----
        txt = raw.decode("utf-8", errors="replace")
        traits = Counter()
        n_slots = n_img = n_noext = n_blank = n_layered = 0
        slot_names = []
        for name, gpid, body in ingest.SLOT_RE.findall(txt):
            n_slots += 1
            if len(slot_names) < 40:
                slot_names.append(html.unescape(name))
            b = html.unescape(body)
            if re.search(r"piece;[^;]*;[^;]*;[^;]+?\.(?:png|gif|svg|jpg|jpeg|bmp);", b):
                n_img += 1
            elif re.search(r"piece;[^;]*;[^;]*;(?:\\.|[^;/])+;", b):
                n_noext += 1
            else:
                n_blank += 1
            if "emb2;" in b:
                n_layered += 1
            for m in TRAIT_RE.finditer(b):
                t = m.group(2)
                if t not in ("piece", "null", "true", "false"):
                    traits[t] += 1
        n_protos = sum(1 for el in root.iter()
                       if ingest.local(el.tag) == "PrototypeDefinition")
        setups = [dict(name=el.get("name", ""), file=el.get("file"))
                  for el in root.iter()
                  if ingest.local(el.tag) == "PredefinedSetup"
                  and el.get("useFile", "false") == "true" and el.get("file")]

        # ---- file inventory ----
        by_ext = Counter()
        bytes_by_ext = Counter()
        for n in names:
            if n.endswith("/"):
                continue
            ext = os.path.splitext(n)[1].lower() or "(none)"
            by_ext[ext] += 1
            bytes_by_ext[ext] += z.getinfo(n).file_size
        pdfs = [n for n in names if n.lower().endswith(".pdf")]
        html_help = [n for n in names if n.lower().endswith((".htm", ".html"))]
        ruleish_files = [n for n in pdfs + html_help if RULEISH.search(os.path.basename(n))]
        chartish_imgs = [n for n in names
                         if n.lower().endswith((".png", ".gif", ".jpg", ".bmp"))
                         and RULEISH.search(os.path.basename(n))][:40]

    # ---- derived: board style + complexity ----
    style = "none"
    pub_boards = [b for m in maps for b in m["boards"] if not m["private"]]
    kinds = [g["kind"] for b in pub_boards for g in b["grids"]]
    if "hex" in kinds:
        style = "hex"
    elif regions_named:
        style = "point-to-point"
    elif "region" in kinds:
        style = "region-snap"
    elif "square" in kinds:
        style = "square"
    elif pub_boards:
        style = "gridless-board"
    h.update(
        ok=True,
        maps=maps, sides=sides, palette=palette,
        regions_named=regions_named[:600], n_regions_named=len(regions_named),
        dice=dice, charts=charts, turn_tracker=bool(n_turntrack),
        n_decks=n_decks, n_cards=n_cards,
        pieces=dict(slots=n_slots, with_art=n_img, art_noext=n_noext, blank=n_blank,
                    layered=n_layered, prototypes=n_protos,
                    traits=dict(traits.most_common(25)), sample_names=slot_names),
        setups=setups, n_setup_stacks=n_setup_stacks, n_atstart_pieces=n_atstart,
        inventory=dict(files=sum(by_ext.values()), by_ext=dict(by_ext.most_common(12)),
                       mb_by_ext={k: round(v / 1e6, 1) for k, v in bytes_by_ext.most_common(8)}),
        rules=dict(pdfs=pdfs[:30], html_help=len(html_help), ruleish=ruleish_files[:30],
                   chartish_images=chartish_imgs),
        board_style=style,
        complexity=dict(slots=n_slots, traits_per_slot=round(sum(traits.values()) / n_slots, 1)
                        if n_slots else 0),
    )
    return h


def stem(vmod_path):
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", os.path.splitext(os.path.basename(vmod_path))[0])


def db_row(h):
    """One aggregate row per module (the DB the LaunchBox generator reads)."""
    p = h.get("pieces", {})
    return dict(file=h["file"], path=h["path"], size=h["size"], ok=h["ok"],
                error=h.get("error"), name=h.get("name"), version=h.get("version"),
                board_style=h.get("board_style"),
                n_slots=p.get("slots"), n_layered=p.get("layered"),
                n_decks=h.get("n_decks"), n_setups=len(h.get("setups", [])),
                n_atstart=h.get("n_atstart_pieces"), n_regions=h.get("n_regions_named"),
                dice="/".join(f"{d['nDice']}d{d['nSides']}" for d in h.get("dice", [])[:4]),
                rules_pdfs=len(h.get("rules", {}).get("pdfs", [])),
                ruleish=len(h.get("rules", {}).get("ruleish", [])),
                charts=len(h.get("charts", [])), sides=h.get("sides", []))


def sweep(dirs):
    os.makedirs(HARVEST_DIR, exist_ok=True)
    db = json.load(open(DB, encoding="utf-8")) if os.path.exists(DB) else {}
    vmods = []
    for d in dirs:
        for base, _, files in os.walk(d):
            vmods += [os.path.join(base, f) for f in files if f.lower().endswith(".vmod")]
    todo = [p for p in vmods if stem(p) not in db]
    print(f"{len(vmods)} vmods found, {len(db)} already harvested, {len(todo)} to do")
    t0 = time.time()
    for i, p in enumerate(todo):
        try:
            h = harvest(p)
        except Exception as e:
            h = dict(file=os.path.basename(p), path=p, size=0, ok=False,
                     error=f"harvester crashed: {e}")
        json.dump(h, open(os.path.join(HARVEST_DIR, stem(p) + ".json"), "w",
                          encoding="utf-8"))
        db[stem(p)] = db_row(h)
        if (i + 1) % 100 == 0 or i == len(todo) - 1:
            json.dump(db, open(DB + ".tmp", "w", encoding="utf-8"))
            os.replace(DB + ".tmp", DB)
            rate = (i + 1) / (time.time() - t0)
            print(f"  {len(db)}/{len(vmods)} ({rate:.1f}/s)")
    ok = sum(1 for r in db.values() if r["ok"])
    styles = Counter(r["board_style"] for r in db.values() if r["ok"])
    print(f"done: {ok}/{len(db)} ok; board styles: {dict(styles.most_common())}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("vmod", nargs="?")
    ap.add_argument("--sweep", nargs="+", help="harvest every .vmod under these dirs")
    a = ap.parse_args()
    if a.sweep:
        sweep(a.sweep)
    elif a.vmod:
        h = harvest(a.vmod)
        os.makedirs(HARVEST_DIR, exist_ok=True)
        out = os.path.join(HARVEST_DIR, stem(a.vmod) + ".json")
        json.dump(h, open(out, "w", encoding="utf-8"), indent=1)
        print(json.dumps(db_row(h), indent=1))
        print(f"full harvest -> {out}")
    else:
        ap.print_help()
