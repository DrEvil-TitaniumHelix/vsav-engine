"""
build_demo.py - Bake the FULL-FUNCTION browser demo: every release game at its
earned tier, played by THE actual Python engine running in the browser
(Pyodide/WASM). One link, one selection page (box art from the user's own
module), BYO-module gate in front of every game. Ships zero third-party art
and zero module-provided saves — those come out of the user's .vmod at
runtime, in the browser, never uploaded.

Output layout (dist/demo — serve statically, e.g. python -m http.server):
  index.html            the selection page (graphics + tier badges)
  shared/byo.js         the module gate (verify sha256, cache, extract)
  shared/bridge.js      Pyodide host: /api/* -> server.route_get/route_post
  py/pyodide/*          vendored Pyodide runtime (web/vendor/pyodide)
  py/app.zip            engine/*.py + ui/server.py + games/<slug>/ data
  g/<slug>/index.html   loader (picks board/tactical client by session tier)
  g/<slug>/board.html   baked ui/index.html      (all games)
  g/<slug>/tactical.html baked ui/tactical.html  (tactical family only)
  g/<slug>/manifest.js  module identity (sha256 + download link + asset map)
  g/<slug>/frame.js     shared client frame

Usage: python web/build_demo.py   ->  dist/demo/
"""
import io, json, os, shutil, struct, sys, time, zipfile

BUILD_STAMP = int(time.time())

# Cloudflare Web Analytics (cookieless visit counting on the hosted demo
# only - the local app never carries it)
BEACON = ("<script type='module' src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{\"token\": \"3c920f185374403bba59be2195c3700e\"}'></script>")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ui"))
import server as srv  # noqa: E402  (game_meta/game_dir only — no HTTP)

OUT = os.path.join(ROOT, "dist", "demo")
VENDOR = os.path.join(ROOT, "web", "vendor", "pyodide")
GAMES = list(srv.RELEASE_GAMES)

# same two counter-src sites build_web.py patches (board client), one in the
# tactical client — art must come from the user's module via BYO.counter(u)
COUNTER_SRC = "GAME.counters_url + encodeURIComponent(u.img || (u.name + '.png'))"
COUNTER_TPL = "${GAME.counters_url}${encodeURIComponent(u.img || (u.name + '.png'))}"
COUNTER_SRC_T = "GAME.counters_url+encodeURIComponent(u.img||(u.name+'.png'))"
BYO_EXPR = "(window.BYO ? BYO.counter(u) : %s)"


def replace_counted(html, old, new, n, what):
    if html.count(old) != n:
        raise SystemExit(f"client: expected {n}x {what!r}, found {html.count(old)}"
                         f" - UI changed, update build_demo")
    return html.replace(old, new)


def img_size(path):
    with open(path, "rb") as f:
        head = f.read(26)
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return struct.unpack("<HH", head[6:10])
    if head[:2] == b"BM":
        w, h = struct.unpack("<ii", head[18:26])
        return w, abs(h)
    return struct.unpack(">II", head[16:24])


def png_stub(w, h):
    """Minimal PNG whose IHDR carries the real map dimensions — the engine
    only ever reads the header (art itself comes from the user's module)."""
    ihdr = struct.pack(">II", w, h) + b"\x08\x02\x00\x00\x00"
    return (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + ihdr
            + b"\x00\x00\x00\x00")


def load_manifest(slug):
    p = os.path.join(ROOT, "web", "manifests", slug + ".json")
    if not os.path.isfile(p):
        raise SystemExit(f"no module manifest for {slug} (web/manifests/{slug}.json)")
    return json.load(open(p, encoding="utf-8"))


def game_payload(zf, slug, manifest):
    """Write games/<slug> into the app zip: our own data only. game.json is
    rewritten so nothing points outside the browser FS: art becomes a dims
    stub; a module-provided setup save becomes the engine_files fs_path that
    bridge.js extracts from the user's module at runtime."""
    gdir = srv.game_dir(slug)
    spec = json.load(open(os.path.join(gdir, "game.json"), encoding="utf-8"))

    map_path = spec["assets"]["map"]
    map_path = map_path if os.path.isabs(map_path) else os.path.join(gdir, map_path)
    w, h = img_size(map_path)
    spec["assets"] = {"map": "map_dims.png"}
    zf.writestr(f"games/{slug}/map_dims.png", png_stub(w, h))

    setup = spec.get("setup_save")
    written = set()
    if setup:
        full = os.path.normpath(os.path.join(gdir, setup))
        inside = full.startswith(os.path.abspath(gdir))
        if inside and os.path.isfile(full):
            zf.write(full, f"games/{slug}/{os.path.basename(full)}")
            written.add(os.path.basename(full))
            spec["setup_save"] = os.path.basename(full)
        else:                          # module-provided — runtime extraction
            ef = (manifest.get("engine_files") or [None])[0]
            if not ef:
                raise SystemExit(f"{slug}: setup save is outside the game dir and "
                                 f"the manifest declares no engine_files")
            spec["setup_save"] = ef["fs_path"]
    zf.writestr(f"games/{slug}/game.json",
                json.dumps(spec, ensure_ascii=False, indent=1))

    for fn in sorted(os.listdir(gdir)):
        full = os.path.join(gdir, fn)
        if not os.path.isfile(full) or fn == "game.json" or fn in written:
            continue
        if fn.endswith((".json", ".vsav")):     # our data + our generated saves
            zf.write(full, f"games/{slug}/{fn}")

    # the trained champion (spec #22): engine/champion.py reads
    # champion.json so the in-browser AI seat plays the same champion as
    # the native app; doctrine.md feeds the SALVO challenger payload. The
    # heavy corpus stays out.
    for fn in ("champion.json", "doctrine.md"):
        p = os.path.join(gdir, "playbook", fn)
        if os.path.isfile(p):
            zf.write(p, f"games/{slug}/playbook/{fn}")


def bake_client(src_name, slug, name, manifest, menu_href="../../index.html"):
    html = open(os.path.join(ROOT, "ui", src_name), encoding="utf-8").read()
    if src_name == "index.html":
        html = replace_counted(html, COUNTER_SRC, BYO_EXPR % COUNTER_SRC, 1,
                               "counter src URL")
        html = replace_counted(html, COUNTER_TPL, "${%s}" % (BYO_EXPR % COUNTER_SRC),
                               1, "counter template URL")
    else:
        html = replace_counted(html, COUNTER_SRC_T, BYO_EXPR % COUNTER_SRC_T, 1,
                               "tactical counter src URL")
    html = replace_counted(html, "location.href='/menu'",
                           f"location.href='{menu_href}'", 1, "games menu link")
    inject = (f'<script>window.DEMO_SLUG={json.dumps(slug)};'
              f'window.DEMO_NAME={json.dumps(name)};'
              f'window.DEMO_BUILD={BUILD_STAMP};</script>\n'
              '<script src="manifest.js"></script>\n'
              '<script src="../../shared/byo.js"></script>\n'
              '<script src="../../py/pyodide/pyodide.js"></script>\n'
              '<script src="../../shared/bridge.js"></script>\n'
              + BEACON + '\n<script>')
    return html.replace("<script>", inject, 1)


LOADER = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>%(name)s</title></head><body
style="background:#1a1c20"><script>
var t = localStorage.getItem('tier:%(slug)s');
var tactical = %(tactical)s && !(t !== null && +t === 0);
location.replace(tactical ? 'tactical.html' : 'board.html');
</script></body></html>
"""


def menu_page(metas):
    cards = json.dumps([dict(slug=m["slug"], name=m["name"], tier=m["tier"],
                             tags=m.get("tags") or [],
                             blurb=m.get("blurb") or "",
                             needs=[r["filename"] for r in m["manifest"]["requirements"]],
                             manifest=m["manifest"]) for m in metas],
                       ensure_ascii=False)
    return """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>VALOR Engine — choose a game</title>
<style>
  html,body { margin:0; min-height:100%; background:#1a1c20; color:#dde3ea;
              font-family:Segoe UI,sans-serif; }
  header { padding:34px 40px 10px; }
  header h1 { margin:0; font-size:26px; color:#fff; font-weight:600; letter-spacing:.3px; }
  header .sub { color:#8a8f98; font-size:14px; margin-top:6px; max-width:860px; line-height:1.5; }
  #cards { display:flex; flex-wrap:wrap; gap:20px; padding:18px 40px 40px; }
  .card { width:320px; background:#23262c; border:1px solid #3a3f47; border-radius:12px;
          padding:20px 22px; box-shadow:0 4px 18px rgba(0,0,0,.45);
          display:flex; flex-direction:column; gap:10px; cursor:pointer; }
  .card:hover { border-color:#3a6ea5; }
  .card .art { width:100%; height:190px; object-fit:contain; border-radius:8px;
               background:#1a1c20; }
  .card .noart { width:100%; height:190px; border-radius:8px; background:#1a1c20;
                 display:flex; align-items:center; justify-content:center;
                 color:#4a4f57; font-size:44px; }
  .card h2 { margin:0; font-size:19px; color:#fff; }
  .meta { display:flex; gap:8px; flex-wrap:wrap; }
  .tag { font-size:11px; padding:2px 9px; border-radius:20px; background:#2c2f36;
         border:1px solid #4a4f57; color:#b9c2cc; }
  .tag.tier { background:#243447; border-color:#3a6ea5; color:#9cc4ee; }
  .tag.ai   { background:#2f2740; border-color:#7a5aa5; color:#c9aef0; }
  .tag.soon { background:#2c2f36; border-color:#4a4f57; color:#98a0a8; }
  .tag.feature { background:#243d33; border-color:#3a7a5f; color:#8fd8b4; }
  .blurb { color:#9aa3ad; font-size:13px; line-height:1.5; flex:1; min-height:20px; }
  .needs { color:#98a0a8; font-size:11.5px; }
  .card button { margin-top:6px; padding:10px 0; border:0; border-radius:7px; cursor:pointer;
                 background:#3a6ea5; color:#fff; font-size:15px; font-weight:600; }
  .card button:hover { background:#4880bd; }
  footer { padding:14px 40px 22px; color:#98a0a8; font-size:12px; border-top:1px solid #2a2d33;
           line-height:1.6; }
  footer b { color:#9aa3ad; font-weight:600; }
</style>
</head>
<body>
<header>
  <h1>VALOR Engine <span style="color:#8a8f98;font-weight:400">— VASSAL-Adjudicated Legality Of Rules. Full rules, in your browser.</span></h1>
  <div class="sub">Choose a game. Every game runs at its full earned tier — the complete
  validated rules engine (the same Python engine, running in your browser) with tier
  selection, seeded dice and a replayable log. The first time you open a game it asks
  once for your own copy of its VASSAL module: the file is verified and read locally,
  never uploaded, and remembered on this device — that's also where the box art below
  comes from.</div>
</header>
<div id="cards"></div>
<footer>
  <b>DrEvil / Titanium Helix</b> &nbsp;·&nbsp; <a href="https://github.com/DrEvil-TitaniumHelix/vsav-engine/issues" target="_blank" rel="noopener" style="color:#9cc4ee">contact the developer / report a bug</a> &nbsp;·&nbsp; engine + rules data only — all game art
  belongs to its publishers and module authors and comes from your own module &nbsp;·&nbsp;
  games save in this browser, on this device &nbsp;&middot;&nbsp; anonymous visit counting via Cloudflare (no cookies, no personal data)
</footer>
<script src="shared/byo.js"></script>
<script>
const GAMES = """ + cards + """;
const TIER_LABEL = {0:"Free play", 1:"Movement enforced", 2:"Combat enforced", 3:"Full rules + AI"};
async function coverUrl(g){
  const m = g.manifest;
  if (!m.assets || !m.assets.cover) return null;
  try {
    const db = await BYO.util.idb();
    const blobs = {};
    for (const r of m.requirements){
      const v = await BYO.util.idbGet(db, r.sha256);
      if (!v || !v.blob) return null;         // module not dropped yet
      blobs[r.id] = v.blob;
    }
    const c = m.assets.cover;
    const idx = await BYO.util.zipIndex(blobs[c.req]);
    const e = idx.get(c.entry);
    if (!e) return null;
    return BYO.util.urlFor(await BYO.util.unzipEntry(blobs[c.req], e), c.entry);
  } catch(err){ console.warn('cover', g.slug, err); return null; }
}
const cards = document.getElementById('cards');
for (const g of GAMES){
  const card = document.createElement('div');
  card.className = 'card';
  const tags = (g.tags || []).map(t =>
    `<span class="tag ${t.kind}">${t.label}</span>`).join('');
  card.innerHTML =
    `<div class="noart">🎲</div>
     <h2>${g.name}</h2>
     <div class="meta">${tags}</div>
     <div class="blurb">${g.blurb}</div>
     <div class="needs">needs your module: ${g.needs.join(' + ')}</div>
     <button>Play</button>`;
  card.onclick = () => location.href = 'g/' + g.slug + '/';
  cards.appendChild(card);
  coverUrl(g).then(u => {
    if (!u) return;
    const img = document.createElement('img');
    img.className = 'art'; img.src = u; img.alt = '';
    card.querySelector('.noart').replaceWith(img);
  });
}
</script>
""" + BEACON + """
</body>
</html>
"""


def main():
    if not os.path.isfile(os.path.join(VENDOR, "pyodide.asm.wasm")):
        raise SystemExit(
            "Pyodide runtime missing. Fetch it once:\n"
            "  cd web/vendor/pyodide && for f in pyodide.js pyodide.mjs "
            "pyodide.asm.js pyodide.asm.wasm python_stdlib.zip pyodide-lock.json;"
            " do curl -sLO https://cdn.jsdelivr.net/pyodide/v0.27.2/full/$f; done")
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(os.path.join(OUT, "shared"))
    for f in ("byo.js", "bridge.js"):
        shutil.copy(os.path.join(ROOT, "web", "shared", f),
                    os.path.join(OUT, "shared", f))
    shutil.copytree(VENDOR, os.path.join(OUT, "py", "pyodide"))

    # ---- the engine payload -------------------------------------------------
    metas = []
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fn in sorted(os.listdir(os.path.join(ROOT, "engine"))):
            if fn.endswith(".py"):
                zf.write(os.path.join(ROOT, "engine", fn), "engine/" + fn)
        zf.write(os.path.join(ROOT, "ui", "server.py"), "ui/server.py")
        for slug in GAMES:
            manifest = load_manifest(slug)
            meta = srv.game_meta(slug)
            meta["manifest"] = manifest
            metas.append(meta)
            game_payload(zf, slug, manifest)
    open(os.path.join(OUT, "py", "app.zip"), "wb").write(buf.getvalue())

    # ---- game pages ---------------------------------------------------------
    for meta in metas:
        slug, name, manifest = meta["slug"], meta["name"], meta["manifest"]
        gd = os.path.join(OUT, "g", slug)
        os.makedirs(gd)
        tactical = meta["client"] == "tactical.html"
        with open(os.path.join(gd, "manifest.js"), "w", encoding="utf-8") as f:
            f.write("window.BYO_MANIFEST = ")
            json.dump(manifest, f, separators=(",", ":"))
            f.write(";\n")
        open(os.path.join(gd, "board.html"), "w", encoding="utf-8").write(
            bake_client("index.html", slug, name, manifest))
        if tactical:
            open(os.path.join(gd, "tactical.html"), "w", encoding="utf-8").write(
                bake_client("tactical.html", slug, name, manifest))
        open(os.path.join(gd, "index.html"), "w", encoding="utf-8").write(
            LOADER % dict(slug=slug, name=name,
                          tactical="true" if tactical else "false"))
        shutil.copy(os.path.join(ROOT, "ui", "frame.js"),
                    os.path.join(gd, "frame.js"))
        shutil.copy(os.path.join(ROOT, "ui", "salvo.js"),
                    os.path.join(gd, "salvo.js"))
        n_req = len(manifest["requirements"])
        print(f"{slug}: client={'tactical+board' if tactical else 'board'}, "
              f"earned tier {meta['tier']['earned']}, {n_req} module req(s)")

    open(os.path.join(OUT, "index.html"), "w", encoding="utf-8").write(
        menu_page(metas))
    total = sum(os.path.getsize(os.path.join(dp, f))
                for dp, _, fs in os.walk(OUT) for f in fs)
    print(f"-> {OUT}  ({total / 1048576:.1f} MB incl. Pyodide runtime)")


if __name__ == "__main__":
    main()
