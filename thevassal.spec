import os
from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(SPECPATH)
PB = ["playbook/champion.json", "playbook/manifest.json", "playbook/doctrine.md"]
GAMES = {
    "tobruk": ["scenario_firefight_b.json", "scenario_meeting.json", "combat.json", "setup_units.json"],
    "blue-and-gray-chickamauga": ["scenario_chickamauga.json", "terrain.json", "setup_units.json"] + PB,
    "westwall-arnhem": ["scenario_historical.json", "terrain.json", "setup_units.json"] + PB,
    "afrika-korps-classic-ah": ["scenario_campaign.json", "terrain.json"],
    "austerlitz-gmt": ["scenario_northern_flank.json", "terrain_nf.json"] + PB,
    "siege-of-jerusalem-ah": ["scenario_gallus.json", "terrain.json"] + PB,
    "napoleon-at-waterloo": ["scenario_2nd_ed.json", "terrain.json", "setup_units.json"] + PB,
}
UI = ["menu.html", "index.html", "tactical.html", "soj.html", "frame.js", "salvo.js"]
ENGINE = ["server", "byo", "board", "gamespec", "gate", "gamestate", "strategic", "ai", "ai_strategic",
          "bluegray", "ai_bluegray", "westwall", "ai_westwall", "vsav", "combat", "naw", "napoleonic", "soj",
          "ai_napoleonic", "ai_soj", "ai_naw", "pbm", "plans", "champion", "salvo", "harness", "undo", "replay",
          "command", "fire", "formations", "melee", "families", "strategy_bg", "strategy_ww", "strategy_nap",
          "strategy_soj", "strategy_naw", "make_save"]

datas = [(os.path.join(ROOT, "ui", f), "ui") for f in UI]
for slug, files in GAMES.items():
    for f in ["game.json"] + files:
        src = os.path.join(ROOT, "games", slug, f)
        assert os.path.isfile(src), src
        datas.append((src, os.path.join("games", slug, os.path.dirname(f))))
    datas.append((os.path.join(ROOT, "web", "manifests", slug + ".json"), os.path.join("web", "manifests")))
assert not any(d[0].lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif", ".vsav", ".vmod", ".pdf")) for d in datas)

wv_datas, wv_binaries, wv_hidden = collect_all("webview")
a = Analysis(["app.py"], pathex=[ROOT, os.path.join(ROOT, "ui"), os.path.join(ROOT, "engine")],
             binaries=wv_binaries, datas=datas + wv_datas, hiddenimports=ENGINE + wv_hidden,
             hookspath=[], runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Legality Engine for VASSAL", debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          disable_windowed_traceback=False, icon=None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="LegalityEngine")
