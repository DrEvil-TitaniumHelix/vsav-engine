"""
build_web.py - Bake the games into a fully static, serverless web release:
"Dr Evil's Move Legality Engine for VASSAL".

BYO-module build (the release pattern, Bruce 2026-07-17): the output contains
ONLY our engine + our transcribed game data. No map, no counters — the page
opens with a drop-zone gate (web/shared/byo.js) that takes the user's own
.vmod, verifies its SHA-256 against web/manifests/<game>.json, extracts the
art browser-side, and caches it in IndexedDB. Nothing is ever uploaded; the
static host has nothing to upload to.

Each game page = the standard board UI (ui/index.html) + data.js (board state,
terrain, movement spec baked from the engine) + manifest.js (module identity)
+ shared/local.js (JS engine port + fetch shim) + shared/byo.js (the gate).
Works from a file:// double-click or any static host.

Usage: python web/build_web.py   ->  dist/legality-web/
"""
import json, os, shutil, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
import board as board_mod  # noqa: E402
import gamespec  # noqa: E402

OUT = os.path.join(ROOT, "dist", "legality-web")
BRAND = "Dr Evil's Move Legality Engine for VASSAL"

# The two places ui/index.html builds a counter image URL; in the BYO build
# both route through BYO.counter(u) (blob URLs from the user's own module).
COUNTER_SRC = "GAME.counters_url + encodeURIComponent(u.img || (u.name + '.png'))"
COUNTER_TPL = "${GAME.counters_url}${encodeURIComponent(u.img || (u.name + '.png'))}"
BYO_EXPR = "(window.BYO ? BYO.counter(u) : %s)" % COUNTER_SRC


def img_size(path):
    with open(path, "rb") as f:
        head = f.read(26)
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return struct.unpack("<HH", head[6:10])
    if head[:2] == b"BM":
        return struct.unpack("<ii", head[18:26])
    return struct.unpack(">II", head[16:24])


def replace_counted(html, old, new, n, what):
    if html.count(old) != n:
        raise SystemExit(f"index.html: expected {n}x {what!r}, "
                         f"found {html.count(old)} - UI changed, update build")
    return html.replace(old, new)


def bake(game_key):
    g = gamespec.Game(os.path.join(ROOT, "games", game_key))
    b = board_mod.Board(g.setup_save, g)
    gd = os.path.join(OUT, game_key)
    os.makedirs(gd, exist_ok=True)

    manifest_path = os.path.join(ROOT, "web", "manifests", game_key + ".json")
    manifest = json.load(open(manifest_path, encoding="utf-8"))

    # units in the same shape server.py's unit_view returns. u["img"] keeps the
    # ORIGINAL module image path — byo.js resolves it against the module zip
    # (manifest assets.counters.prefix + img); nothing is copied to disk.
    units = []
    for u in b.units():
        a, d, m = g.stats(u["name"])
        units.append(dict(u, att=a, dfn=d, ma=m,
                          onmap=g.on_map(u["col"], u["row"]),
                          terrain=g.hex_terrain(u["col"], u["row"]),
                          status=None,
                          facing=0 if g.facing else None))

    # map geometry still comes from the local dev copy (byo.js swaps in the
    # user's module image at the same pixel dimensions - verified per game)
    w, h = img_size(g.assets["map"])

    descriptor = dict(
        name=g.name,
        map_url="", map_w=w, map_h=h,     # map_url is set by byo.js at runtime
        counters_url="",
        # movement IS enforced in this build (JS legality port) — tier 1 keeps
        # the guide banner honest; single choice hides the tier switcher
        tier=dict(active=1, earned=1, choices=[1]),
        counter_px=g.spec.get("ui", {}).get("counter_px", 75),
        grid=dict(dx=g.grid.dx, dy=g.grid.dy, orient=g.grid.orient),
        sides=[dict(id=s, label=g.spec["sides"].get("labels", {}).get(s, s))
               for s in g.side_order],
        facing=g.facing,
    )
    data = dict(
        game=descriptor,
        notes=f"{g.name} — move legality engine (browser demo)",
        units=units,
        terrain=g.terrain,
        spec=dict(grid=g.spec["grid"], movement=g.spec["movement"],
                  sides=dict(order=g.side_order)),
    )
    with open(os.path.join(gd, "data.js"), "w", encoding="utf-8") as f:
        f.write("window.GAME_DATA = ")
        json.dump(data, f, separators=(",", ":"))
        f.write(";\n")
    with open(os.path.join(gd, "manifest.js"), "w", encoding="utf-8") as f:
        f.write("window.BYO_MANIFEST = ")
        json.dump(manifest, f, separators=(",", ":"))
        f.write(";\n")

    # game page = board UI + data + module manifest + local engine + BYO gate
    # (the brand has an apostrophe: escape it inside the JS string literal)
    html = open(os.path.join(ROOT, "ui", "index.html"), encoding="utf-8").read()
    html = html.replace("' — Claude Plays VASSAL'",
                        "' — " + BRAND.replace("'", "\\'") + "'")
    html = html.replace("Claude Plays VASSAL", BRAND)
    # plain-concat site first: the template rewrite below INSERTS the plain
    # expression (inside the ternary), so doing it second would double-wrap
    html = replace_counted(html, COUNTER_SRC, BYO_EXPR, 1, "counter src URL")
    html = replace_counted(html, COUNTER_TPL, "${%s}" % BYO_EXPR, 1,
                           "counter template URL")
    html = html.replace("<script>",
                        '<script src="data.js"></script>\n'
                        '<script src="../shared/local.js"></script>\n'
                        '<script src="manifest.js"></script>\n'
                        '<script src="../shared/byo.js"></script>\n<script>', 1)
    open(os.path.join(gd, "index.html"), "w", encoding="utf-8").write(html)
    shutil.copy(os.path.join(ROOT, "ui", "frame.js"),
                os.path.join(gd, "frame.js"))   # index.html loads frame.js?v=…
    n = sum(len(fs) for _, _, fs in os.walk(gd))
    print(f"{game_key}: {len(units)} units, {n} files, "
          f"{len(manifest['requirements'])} module requirement(s), no art baked")


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(os.path.join(OUT, "shared"))
    for f in ("local.js", "byo.js"):
        shutil.copy(os.path.join(ROOT, "web", "shared", f),
                    os.path.join(OUT, "shared", f))
    shutil.copy(os.path.join(ROOT, "web", "START_HERE.html"),
                os.path.join(OUT, "START_HERE.html"))
    for k in ("tobruk", "arnhem", "asl"):
        bake(k)
    print("->", OUT)


if __name__ == "__main__":
    main()
