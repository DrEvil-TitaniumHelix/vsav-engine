# VALOR Engine (Legality Engine for VASSAL)

A portable Windows app. It contains no game art: you supply each game's VASSAL module yourself, once per game.

## Getting started

1. Download the latest `LegalityEngine-<version>-win64.zip` from https://github.com/DrEvil-TitaniumHelix/vsav-engine/releases/latest and unzip it into an empty folder. (Quiver Launcher does this step for you.)
2. Double-click `Legality Engine for VASSAL.exe`.
3. In the menu, find the game you want. A game you have not set up shows **Needs your module**, with its library link and the exact file name and size.
4. Download that exact `.vmod` file from the link in the table below.
5. Choose the file when the app asks. A wrong file is rejected with a hint.
6. The card now shows **Ready**. Later launches need nothing more.

## Modules

Each game needs this exact file. The app checks its size and SHA-256.

| Game | Library page | Exact file name | Size (bytes) |
|---|---|---|---|
| Tobruk: Tank Battles in North Africa 1942 | https://vassalengine.org/library/projects/Tobruk_Tank_Battles_in_North_Africa_1942 | `Tobruk_v1.1.vmod` | 95539764 |
| Blue & Gray: Chickamauga | https://vassalengine.org/library/projects/Blue__Gray_Four_American_Civil_War_Battles | `Blue and Gray Complete.vmod` | 49428841 |
| Westwall: Arnhem | https://vassalengine.org/library/projects/Westwall_Four_Battles_to_Germany | `Westwall Quad.vmod` | 32527773 |
| Afrika Korps Classic (Avalon Hill) | https://vassalengine.org/library/projects/Afrika_Korps_Classic_Avalon_Hill | `Afrika Korps Classic AH 3.0.1.vmod` | 11083018 |
| Austerlitz: Napoleon's Greatest Victory (GMT) | https://vassalengine.org/library/projects/Austerlitz_clanmacrae | `Austerlitz1_0_0.vmod` | 26051623 |
| The Siege of Jerusalem (Avalon Hill, 1989) | https://vassalengine.org/library/projects/The_Siege_of_Jerusalem | `SOJ 2_5_0.vmod` | 30014120 |
| Napoleon at Waterloo 2nd Edition (Stephen Oliver, v2.2.0) | https://vassalengine.org/library/projects/napoleon_at_waterloo_2nd_ed_stephen_oliver | `Napoleon at Waterloo 2nd Ed Vers 2.2.vmod` | 12439999 |

## Windows will probably warn you the first time

This app is not code-signed, so Windows SmartScreen or your antivirus may flag it (for example "Windows protected your PC", or a quarantine notice).

- **SmartScreen:** click **More info**, then **Run anyway**.
- **Antivirus quarantine:** restore the file or allow it, or add an exception.

If you are not comfortable doing that, don't force it.

## If the app will not start

Version 0.2.0 could fail at launch with `Failed to resolve Python.Runtime.Loader.Initialize`. Fixed in 0.2.1: download the latest release.

## Your data

- Game state and logs: `%LOCALAPPDATA%\TheVassal\live\`
- Your imported module files: `%LOCALAPPDATA%\TheVassal\byo\`

## Reporting a bug

Every game is deterministic and fully logged, so your log replays your exact game on our end.

Note the version shown in the menu footer and send the game log (`game_<name>.log.jsonl`) from the folder above.

## Building from source (developers)

```
pip install pywebview pyinstaller
powershell -ExecutionPolicy Bypass -File build.ps1
```

Produces `dist\LegalityEngine\` (one-dir PyInstaller build, no game art inside) and `dist\LegalityEngine-<version>-win64.zip`. The build fails if any image, save or module file lands in the output. Which games ship: `RELEASE_GAMES` in `ui/server.py` and the `GAMES` table in `thevassal.spec`. Version: `VERSION` in `ui/server.py`. Run from source without packaging: `python app.py` (native window) or `python ui/server.py --port 8641` (browser).

macOS: `./build.sh` on a Mac (untested since v0.2.0; Gatekeeper needs right-click, Open the first time).

## Quiver Launcher

VALOR is in the Quiver Launcher catalog: https://quiverlauncher.com/apps/valor-engine-for-vassal-games. Quiver downloads the release zip, checks it and launches the exe; later releases update in place.
