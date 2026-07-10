# Legality Engine for VASSAL — beta

A rules-enforcing engine for classic wargames. Pick a game from the menu and
play; the engine enforces the rules, owns the dice (seeded and logged), and
records every move so a whole game replays exactly. Ships with **Afrika Korps**
(full campaign, combat, AI opponent) and **Tobruk** (tactical firefight).

## Running it (testers)

**Windows:** double-click **`Legality Engine for VASSAL.exe`**. No install, no
Python, no browser — it opens as its own window.

> ### ⚠️ Windows will probably warn you the first time
> Because this is a brand-new one-file program that isn't code-signed, Windows
> SmartScreen and/or your antivirus may flag it (e.g. "Windows protected your
> PC", or a quarantine notice). **This is a false positive** — a known nuisance
> for freshly built one-file apps, not a sign of a virus.
> - **SmartScreen:** click **More info → Run anyway**.
> - **Antivirus quarantine:** restore the file / allow it, or add an exception.
>
> If you're not comfortable doing that, don't force it — tell Bruce and he'll
> sort it out. We warned you it would happen so it's not a surprise.

**Mac:** double-click **`Legality Engine for VASSAL.app`**. Gatekeeper blocks
unsigned apps, so the first time: **right-click the app → Open → Open**. After
that it launches normally.

## Playing

- **Menu** — pick a game. **Rules** and **Tables** buttons show exactly what the
  engine enforces and the transcribed combat tables (the same data the engine
  rolls on — not scanned images), each with rulebook citations.
- **Tiers** — some games can run at a lower tier (less enforced, more free-play).
  Switching tiers starts a fresh game.
- Your game state is saved automatically to your user folder, so closing and
  reopening picks up where you left off.

## Reporting a bug

Because every game is deterministic and fully logged, we can reproduce a bug
exactly from your session. If something goes wrong, note the **version** (shown
in the menu footer, e.g. `v0.1.0-beta`) and send Bruce the game log — it lives in:

- **Windows:** `%LOCALAPPDATA%\TheVassal\live\`
- (the `game_<name>.log.jsonl` and `game_<name>.vsav` files)

That log replays your exact game on our end, so we can find and fix the issue.

---

## Building from source (developers)

The repository is the factory for both builds. One-time setup:

```
pip install pywebview pyinstaller
```

Then:

- **Windows:** `powershell -ExecutionPolicy Bypass -File build.ps1`
  → `dist\Legality Engine for VASSAL.exe`
- **macOS:** `./build.sh` (must be run **on a Mac** — no cross-compile)
  → `dist/Legality Engine for VASSAL.app`

Both run `build_stage.py` (copies each release game's real assets into a
self-contained bundle) and then PyInstaller against `thevassal.spec`.

- Which games ship: edit `RELEASE_GAMES` in `build_stage.py` **and**
  `thevassal.spec` (keep them in sync with `server.RELEASE_GAMES`).
- The version stamp is `VERSION` in `ui/server.py`.
- To run from source without packaging: `python app.py` (native window) or
  `python ui/server.py --game games/<slug> --port 8641` (in a browser).
