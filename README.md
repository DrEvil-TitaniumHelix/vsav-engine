# vsav-engine

**A game-state API for VASSAL 3 — no VASSAL modifications, no GUI automation.**

Read the board, rule-check moves, and write new positions directly into VASSAL's own
`.vsav` save files. VASSAL, a browser UI, and an AI opponent become three interchangeable
clients sharing one file.

Reference implementation: **SPI's *Arnhem*** (from the *Westwall* quad, 1976), played on the
sanctioned [Westwall: Four Battles to Germany VASSAL module](https://vassalengine.org/wiki/Module:Westwall:_Four_Battles_to_Germany).
The method — save codec, hex math, terrain extraction — generalizes to other modules.

By **DrEvil / Titanium Helix**. MIT licensed.

---

## How it works

1. **Save-file codec** — a `.vsav` is a ZIP; the `savedGame` entry is obfuscated with a
   `!VCSK` header + one-byte XOR cipher (`0xA3` for this module). We decode to plain text
   and re-encode byte-perfectly, so VASSAL can't tell our saves from its own.
2. **Board parser** — game state is a list of records: one per counter (pixel position)
   plus separate *stack* records that control rendering. A unit's position lives in BOTH;
   edit them together or nothing moves. Parses all 99 Arnhem counters.
3. **Hex math** — grid geometry from the module's `buildFile` (dx=96, dy=119, origin 60,60,
   staggered) gives pixel↔hex formulas, validated against the module's player-aid setup cards.
4. **Terrain + rules engine** — terrain for all 1,128 hexes is extracted **from the map
   image itself** by color-classifying hexes and hexsides (towns, woods, rivers, roads,
   all 14 bridges). Legal movement is Dijkstra pathfinding with road bonuses, river/bridge
   logic, and zone-of-control stops, per the published rules.
5. **Move writer + clients** — edit the decoded save, re-encode, and VASSAL just reloads
   the file. A local web UI serves the real map with legal-move highlighting and drag-to-move;
   a watcher diffs saves to detect (and legality-judge) moves a human made in VASSAL.

## What's in the repo

```
engine/arnhem.py           save codec (XOR/zip), hex math, v1 CLI: dump / move
engine/board.py            v2 full-fidelity mover: batch moves, stack split/join
engine/rules.py            movement + ZOC + CRT rules engine (Dijkstra legal-move search)
engine/extract_terrain.py  builds terrain.json by color-classifying the module's map image
engine/play.py             AI turn driver: analyze side, generate moves, resolve combat
engine/watch.py            human-move watcher: diff saves, judge legality
engine/inspect_build.py    dump grid geometry from a module's buildFile
engine/extract_pdf.py      helpers for rendering rules PDFs to images
engine/render_pdf.py
ui/server.py               local HTTP API over the .vsav (state / legal / move / pass / reset)
ui/index.html              browser client: real map, pan/zoom, legal-hex highlights, drag to move
ahk/arnhem_sync.ahk        optional AutoHotkey v2 reload macro for the VASSAL window
```

## What's NOT in the repo (bring your own)

**No game assets are included or will ever be.** The module, map, counter art, and rules
are the property of Decision Games (SPI's successor) — the module is hosted **with
permission** at vassalengine.org, so get it there:

1. Install [VASSAL 3.7+](https://vassalengine.org) and download the
   *Westwall: Four Battles to Germany* module via the in-app Module Manager.
2. Open the Arnhem historical setup and save a game → `game.vsav`.
3. Extract the map image from the `.vmod` (it's a ZIP) and run
   `python engine/extract_terrain.py` to regenerate `terrain.json` locally.

## Quickstart

Python 3.10+; `pip install pillow` (only needed for terrain extraction).

```
python engine/board.py dump game.vsav                 # board state: 99 counters w/ hex + side
python engine/board.py move game.vsav out.vsav "9SSRcn=2822"   # write a move, load out.vsav in VASSAL
python ui/server.py                                   # browser client on http://localhost:8641
python engine/watch.py game.vsav                      # watch for + legality-judge human moves
```

## Why this matters

The VASSAL team has said a programmatic game-state interface arrives "in V4."
This gets that behavior **today, on V3, without touching VASSAL's code** — because
the save file *is* the game state.

## Legal

Code is MIT. *Arnhem*, *Westwall*, and all game content, artwork, and rules are the
property of their respective rights-holders (Decision Games). This project ships **zero**
of their material and requires you to obtain the module through the sanctioned channel.
Not affiliated with or endorsed by VASSAL or Decision Games.
