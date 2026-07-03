"""
build_web.py - Bake the three games into a fully static, serverless web demo:
"Dr Evil's Move Legality Engine for VASSAL".

Each game page = the standard board UI (ui/index.html) + data.js (board state,
terrain, movement spec baked from the engine) + shared/local.js (the JS port of
the legality engine + a fetch shim answering /api/* locally). Works from a
file:// double-click or any static host. No Python, no server, no install.

Usage: python web/build_web.py   ->  dist/legality-web/
"""
import json, os, re, shutil, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
import board as board_mod  # noqa: E402
import gamespec  # noqa: E402

OUT = os.path.join(ROOT, "dist", "legality-web")
BRAND = "Dr Evil's Move Legality Engine for VASSAL"


def img_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return struct.unpack("<HH", head[6:10])
    return struct.unpack(">II", head[16:24])


def bake(game_key):
    g = gamespec.Game(os.path.join(ROOT, "games", game_key))
    b = board_mod.Board(g.setup_save, g)
    gd = os.path.join(OUT, game_key)
    ad = os.path.join(gd, "assets", "counters")
    os.makedirs(ad, exist_ok=True)

    # units in the same shape server.py's unit_view returns
    units, missing = [], []
    for u in b.units():
        a, d, m = g.stats(u["name"])
        img = u["img"].replace("/", "_")     # flatten: %2F breaks file:// URLs
        src = os.path.join(g.assets["counters_dir"], u["img"])
        if os.path.exists(src):
            shutil.copy(src, os.path.join(ad, img))
        else:
            missing.append(u["img"])
        units.append(dict(u, img=img, att=a, dfn=d, ma=m,
                          onmap=g.on_map(u["col"], u["row"]),
                          terrain=g.hex_terrain(u["col"], u["row"]),
                          status=None,
                          facing=0 if g.facing else None))

    mext = os.path.splitext(g.assets["map"])[1]
    shutil.copy(g.assets["map"], os.path.join(gd, "assets", "map" + mext))
    w, h = img_size(g.assets["map"])

    descriptor = dict(
        name=g.name,
        map_url="assets/map" + mext, map_w=w, map_h=h,
        counters_url="assets/counters/",
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

    # game page = board UI + data + local engine, rebranded
    # (the brand has an apostrophe: escape it inside the JS string literal)
    html = open(os.path.join(ROOT, "ui", "index.html"), encoding="utf-8").read()
    html = html.replace("' — Claude Plays VASSAL'",
                        "' — " + BRAND.replace("'", "\\'") + "'")
    html = html.replace("Claude Plays VASSAL", BRAND)
    html = html.replace("<script>",
                        '<script src="data.js"></script>\n'
                        '<script src="../shared/local.js"></script>\n<script>', 1)
    open(os.path.join(gd, "index.html"), "w", encoding="utf-8").write(html)
    n = sum(len(fs) for _, _, fs in os.walk(gd))
    print(f"{game_key}: {len(units)} units, {n} files"
          + (f", missing art {missing}" if missing else ""))


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(os.path.join(OUT, "shared"))
    shutil.copy(os.path.join(ROOT, "web", "shared", "local.js"),
                os.path.join(OUT, "shared", "local.js"))
    shutil.copy(os.path.join(ROOT, "web", "START_HERE.html"),
                os.path.join(OUT, "START_HERE.html"))
    for k in ("arnhem", "tobruk", "asl"):
        bake(k)
    print("->", OUT)


if __name__ == "__main__":
    main()
