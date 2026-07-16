# thevassal.spec — PyInstaller build recipe for The Vassal (one-file).
#
# Build (Windows):  powershell -File build.ps1     (or: pyinstaller thevassal.spec)
# Build (macOS):    ./build.sh                      (must run ON a Mac)
#
# Produces a single executable in dist/ that a non-technical tester runs by
# double-click — no Python, no browser, no command line. The same spec builds
# the Windows .exe and the macOS .app; only the host OS differs.
import os
import sys
from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(SPECPATH)

# Keep in sync with server.RELEASE_GAMES — only the tester-facing games ship.
RELEASE_GAMES = ["afrika-korps-classic-ah", "blue-and-gray-chickamauga",
                 "westwall-arnhem", "tobruk"]

# Read-only assets the engine loads at runtime, bundled at the frozen root so
# server._base_dir() (sys._MEIPASS when frozen) resolves games/ and ui/.
# Games come from build/stage (build_stage.py copies each game's real assets in
# and rewrites game.json to reference them relatively) — a plain games/<slug>
# only holds JSON + text, its map/counters/setup live outside the folder.
STAGE = os.path.join(ROOT, "build", "stage")
datas = [(os.path.join(ROOT, "ui"), "ui")]
for slug in RELEASE_GAMES:
    staged = os.path.join(STAGE, "games", slug)
    if not os.path.isdir(staged):
        raise SystemExit(f"missing staged game {slug!r} — run build_stage.py first")
    datas.append((staged, os.path.join("games", slug)))

# pywebview's native backend (WebView2/pythonnet on Windows, WebKit on macOS).
wv_datas, wv_binaries, wv_hidden = collect_all("webview")
datas += wv_datas

a = Analysis(
    ["app.py"],
    pathex=[ROOT, os.path.join(ROOT, "ui"), os.path.join(ROOT, "engine")],
    binaries=wv_binaries,
    datas=datas,
    # Engine modules are imported after a runtime sys.path.insert, so name them
    # explicitly; PyInstaller pulls in their dependencies (combat, rules, vsav…).
    hiddenimports=[
        "server", "board", "gamespec", "gate", "gamestate",
        "strategic", "ai", "ai_strategic",
        "bluegray", "ai_bluegray", "westwall", "ai_westwall",
    ] + wv_hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="Legality Engine for VASSAL",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                 # UPX-packed one-files trip AV more often; skip it
    runtime_tmpdir=None,
    console=False,             # native window app — no console window
    disable_windowed_traceback=False,
    icon=None,
)
