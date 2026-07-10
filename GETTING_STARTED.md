# Getting started (read this first — or better, let Claude read it for you)

Welcome, tester. The recommended way to run this project:

1. **Download the repo** (clone it, or GitHub → Code → Download ZIP and unzip).
2. **Open the folder in PyCharm** or your preferred IDE (any Python 3.10+).
3. **Launch Claude Code in the folder, using the Fable model** — then simply ask:
   *"Read GETTING_STARTED.md and get me started."*
   Claude will check your Python, install what's missing, start the right game,
   and explain anything you ask mid-game — rules questions included.

No Claude? The manual path is two commands:

```
pip install -r requirements.txt      # only needed for the native window
python app.py                        # opens the game window, pick a game, play
```

Prefer a plain browser? `python ui/server.py` then open the printed URL.

Don't want to touch Python at all? Use the prebuilt Windows exe — it's in
`dist/Legality Engine for VASSAL.exe` in this repo, and also downloadable from
Bruce's Google Drive link (ask Bruce). Double-click, no install. Windows
SmartScreen will warn the first time (unsigned new app — click **More info →
Run anyway**); details in RELEASE_README.md.

---

## Co-developers: encode YOUR game

The engine encodes a printed game whole — map, counters, rules, combat tables —
into a computerized version. To do it for your own game, bring its VASSAL
module (from vassalengine.org) and its rulebook, then ask Claude:

> *"I have SPI's Blue and Gray. Do the same thing for my game — put Blue and
> Gray in the engine."*

Claude follows **ENCODING_GUIDE.md** (the full process, with
`games/afrika-korps-classic-ah/` as the worked reference: ingest → game.json →
terrain → scenario → cited table transcription → validation → tier badge).

---

## Notes for the assistant (Claude) helping a new tester

- This is a rules-enforcing wargame engine. The games in the tester menu are
  **Afrika Korps** (strategic, full campaign + AI opponent) and **Tobruk**
  (tactical tank firefight). Both are self-contained in `games_bundled/`.
- Start the app with `python app.py` (native window; needs `pip install
  pywebview`) or `python ui/server.py` (browser, zero dependencies, port 8641).
- The in-game **guidance banner** always says what to do next, and when only
  one button can advance the game it pulses with a **red border**. The
  **Rules** and **Tables** buttons show exactly what the engine enforces, with
  rulebook citations. Encourage the tester to just click around — illegal moves
  are simply rejected with the rule that forbids them; nothing can be broken.
- Every game is deterministic, seeded, and logged (`live/` from source,
  `%LOCALAPPDATA%\TheVassal\live` from the exe). If the tester hits a bug, that
  log reproduces it exactly — have them send the `game_<name>.log.jsonl` and
  `.vsav` to Bruce, with the version from the menu footer.
- `python engine/verify_game.py <log.jsonl>` independently re-verifies any game.
- Full architecture background is in README.md; tester-facing run/build notes
  are in RELEASE_README.md.
