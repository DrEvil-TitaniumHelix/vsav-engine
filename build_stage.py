"""build_stage.py — stage self-contained game folders for the packaged build.

The games' heavy assets (map, counters, starting-position save) live OUTSIDE the
game folder; game.json points at them with paths that only resolve on a build
machine. A frozen one-file .exe can't reach those, so before packaging we copy
each release game's real assets INTO a staging folder and rewrite game.json to
reference them relatively (assets/...). PyInstaller then bundles the staging
folders, producing an .exe that runs on a machine that has none of the source
assets.

Run:  python build_stage.py     (build.ps1 / build.sh run this before PyInstaller)
"""
import os
import sys
import json
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "engine"))
import gamespec  # noqa: E402
import board as board_mod  # noqa: E402


def needed_counter_stems(g):
    """Image name-stems the game can actually draw: every piece in the starting
    position (the UI only renders a counter from a board piece's img/name).
    Lets us stage just the counters a scenario uses instead of a module's whole
    art set (+ its rulebook page scans, board tiles, to-hit tables — none of
    which the engine serves; the CRT/to-hit tables are transcribed engine data
    rendered in the UI, not scans)."""
    try:
        b = board_mod.Board(g.setup_save, g)
    except Exception:
        return None                      # can't tell -> caller keeps everything
    stems = set()
    for u in b.units():
        if u.get("img"):
            stems.add(os.path.splitext(u["img"])[0])
        if u.get("name"):
            stems.add(u["name"])
    return stems

RELEASE_GAMES = ["afrika-korps-classic-ah", "blue-and-gray-chickamauga",
                 "westwall-arnhem", "tobruk"]
STAGE = os.path.join(HERE, "build", "stage")


def stage_game(slug):
    src = os.path.join(HERE, "games", slug)
    bundled = os.path.join(HERE, "games_bundled", slug)
    spec_probe = json.load(open(os.path.join(src, "game.json"), encoding="utf-8"))
    m = (spec_probe.get("assets") or {}).get("map")
    if m and not os.path.exists(m if os.path.isabs(m) else os.path.join(src, m)) \
            and os.path.isdir(bundled):
        # a clone has no module extracts — the in-repo bundle IS already the
        # self-contained staged form, so ship it verbatim
        dst = os.path.join(STAGE, "games", slug)
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(bundled, dst)
        size = sum(os.path.getsize(os.path.join(dp, f))
                   for dp, _, fs in os.walk(dst) for f in fs)
        print(f"  staged {slug} from games_bundled/ (clone build), {size/1e6:.1f} MB")
        return dst
    g = gamespec.Game(src)                 # resolves every asset to an abs path
    dst = os.path.join(STAGE, "games", slug)
    assets = os.path.join(dst, "assets")
    if os.path.exists(dst):
        shutil.rmtree(dst)
    os.makedirs(assets, exist_ok=True)

    # in-repo runtime data (scenario json, terrain.json, any in-repo .vsav)
    for f in os.listdir(src):
        if f.endswith((".json", ".vsav")) and os.path.isfile(os.path.join(src, f)):
            shutil.copy(os.path.join(src, f), os.path.join(dst, f))

    spec = json.load(open(os.path.join(src, "game.json"), encoding="utf-8"))

    # starting-position save: if it wasn't an in-repo file (already copied
    # above), pull it in from wherever game.json pointed.
    if g.setup_save and os.path.isfile(g.setup_save):
        rel = spec.get("setup_save", "")
        if not os.path.isfile(os.path.join(dst, rel)):
            base = os.path.basename(g.setup_save)
            shutil.copy(g.setup_save, os.path.join(assets, base))
            spec["setup_save"] = f"assets/{base}"

    # map / counters_dir / map_thumb → copy in, rewrite to assets/...
    stems = needed_counter_stems(g)
    new_assets = dict(spec.get("assets", {}))
    for key, absp in g.assets.items():
        if not absp or not os.path.exists(absp):
            continue
        if os.path.isdir(absp):
            # A module's image folder holds its ENTIRE art set — every scenario's
            # counters, board tiles (.bmp), rulebook page scans, to-hit tables.
            # The engine only ever serves counters the board references, so stage
            # exactly those (match a file whose stem is / starts with a board
            # stem). Everything else — including the table scans, which are
            # transcribed engine data rendered in the UI — is dropped.
            outdir = os.path.join(assets, key)
            os.makedirs(outdir, exist_ok=True)
            for f in os.listdir(absp):
                fp = os.path.join(absp, f)
                if not os.path.isfile(fp):
                    continue
                if f.lower().endswith(".bmp") or os.path.getsize(fp) >= 1_000_000:
                    continue
                if stems is not None:
                    fstem = os.path.splitext(f)[0]
                    if not any(fstem == s or fstem.startswith(s + "_") or
                               fstem.startswith(s) for s in stems):
                        continue
                shutil.copy(fp, os.path.join(outdir, f))
            new_assets[key] = f"assets/{key}"
        else:
            base = os.path.basename(absp)
            shutil.copy(absp, os.path.join(assets, base))
            new_assets[key] = f"assets/{base}"
    spec["assets"] = new_assets

    # ingest-only keys point outside the bundle and are never read at runtime
    for k in ("buildfile", "moduledata"):
        spec.pop(k, None)

    json.dump(spec, open(os.path.join(dst, "game.json"), "w", encoding="utf-8"),
              indent=1)
    n_counters = len(os.listdir(os.path.join(assets, "counters_dir"))) \
        if os.path.isdir(os.path.join(assets, "counters_dir")) else 0
    size = sum(os.path.getsize(os.path.join(dp, f))
               for dp, _, fs in os.walk(dst) for f in fs)
    print(f"  staged {slug}: {n_counters} counter images, {size/1e6:.1f} MB")
    return dst


def main():
    if os.path.exists(STAGE):
        shutil.rmtree(STAGE)
    os.makedirs(STAGE, exist_ok=True)
    print(f"Staging {len(RELEASE_GAMES)} games -> {STAGE}")
    for slug in RELEASE_GAMES:
        stage_game(slug)
    print("Staging complete.")


if __name__ == "__main__":
    main()
