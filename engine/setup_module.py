"""
setup_module.py - One-command setup: turn a downloaded VASSAL .vmod into the
asset layout this engine expects, then build the scenario save.

The repo ships ZERO game assets (see README "Legal"). You download the module
yourself from the sanctioned vassalengine.org page, then:

    python engine/setup_module.py tobruk "C:/Downloads/Tobruk_v1.1.vmod"

which creates, NEXT TO your clone of this repo:

    ../VassalTobruk/extracted/   buildFile, moduledata, images/* (from the vmod zip)
    ../VassalTobruk/assets/      map.png (converted from the module's board BMP)

and builds games/tobruk/scenario_firefight_b.vsav from the module's own
PieceSlot definitions. After that:  python ui/server.py --game games/tobruk

Requires Pillow for the one-time BMP->PNG map conversion: pip install pillow
(the engine itself is pure stdlib).
"""
import json
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

MODULES = {
    "tobruk": {
        "dir_name": "VassalTobruk",
        "map_image": "images/Board_ADBECF.bmp",
        "scenario": "scenario_firefight_b.json",
        "download": "https://vassalengine.org/wiki/Module:Tobruk",
    },
    "austerlitz-gmt": {
        # game.json references ../../../VassalIngest/austerlitz-gmt/*
        "dir_name": os.path.join("VassalIngest", "austerlitz-gmt"),
        "map_image": "images/Austerlitz.jpg",
        "scenario": None,          # scenario JSON ships in the repo; the
        "setups_from_module": True,  # setup .vsavs come from the module
        "download": "https://vassalengine.org/library/projects/"
                    "Austerlitz_clanmacrae",
    },
}


def setup(game_key, vmod_path):
    cfg = MODULES[game_key]
    game_dir = os.path.join(ROOT, "games", game_key)
    target = os.path.normpath(os.path.join(ROOT, "..", cfg["dir_name"]))
    extracted = os.path.join(target, "extracted")
    assets = os.path.join(target, "assets")
    os.makedirs(extracted, exist_ok=True)
    os.makedirs(assets, exist_ok=True)

    print(f"extracting {vmod_path} -> {extracted}")
    with zipfile.ZipFile(vmod_path) as z:
        z.extractall(extracted)

    map_src = os.path.join(extracted, *cfg["map_image"].split("/"))
    map_dst = os.path.join(assets, "map.png")
    if not os.path.exists(map_dst):
        print(f"converting map {os.path.basename(map_src)} -> map.png (one-time, ~1 min)")
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = None
        Image.open(map_src).convert("RGB").save(map_dst, optimize=True)

    if cfg.get("setups_from_module"):
        # the module embeds its scenario saves at the zip root; the game
        # spec's setup_save points into setups/
        import shutil
        setups = os.path.join(target, "setups")
        os.makedirs(setups, exist_ok=True)
        n = 0
        for f in os.listdir(extracted):
            if f.lower().endswith(".vsav"):
                shutil.copy(os.path.join(extracted, f),
                            os.path.join(setups, f))
                n += 1
        print(f"staged {n} scenario saves -> {setups}")

    if cfg.get("scenario"):
        scen = os.path.join(game_dir, cfg["scenario"])
        out = os.path.join(game_dir,
                           os.path.splitext(cfg["scenario"])[0] + ".vsav")
        print(f"building scenario save {os.path.basename(out)} "
              "from the module's PieceSlots")
        sys.path.insert(0, HERE)
        import gamespec
        import make_save
        game = gamespec.Game(game_dir)
        make_save.build(game, json.load(open(scen, encoding="utf-8")), out)
    print(f"\ndone. run:  python ui/server.py --game games/{game_key}")


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in MODULES:
        names = ", ".join(MODULES)
        print(f"usage: python engine/setup_module.py <{names}> <path-to-.vmod>")
        for k, c in MODULES.items():
            print(f"  {k}: download the module at {c['download']}")
        sys.exit(1)
    setup(sys.argv[1], sys.argv[2])
