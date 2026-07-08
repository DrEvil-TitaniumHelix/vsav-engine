# vsav-engine — Dr Evil's Game Legality Engine for VASSAL (v2)

**v2: from move legality to full gameplay.** A complete, playable wargame scenario —
Avalon Hill's *Tobruk* (1975), Firefight B — where a human plays against an AI opponent
in the browser and **neither side is capable of cheating**: every action either player
proposes passes through the same deterministic legality gate, every die is rolled by the
gate from a seeded stream, and the whole game is recorded in an append-only log that
**anyone can independently re-verify**.

This is the working answer to *"an AI opponent will cheat and won't even know it's
cheating."* The AI never adjudicates anything. It proposes; the gate disposes; the log
remembers; the verifier proves.

```
python engine/verify_game.py live/game_tobruk.log.jsonl
VERIFIED: 85/85 entries: every verdict, every die, every state hash reproduced
          (0 illegal proposals ever touched the game state)
```

v1 (movement legality for Arnhem / Tobruk / ASL) is still here and still works.
By **DrEvil / Titanium Helix**. MIT licensed.

---

## What v2 adds — the playable proof game

**Firefight B — "An Even Encounter"** (*Tobruk* rulebook p.24, an official scenario):
6 British Stuart Mk.III vs 15 Italian M13/40, 10 turns, open desert, official victory
point table. Rules scope is Scenario One ("The Clash of Armor," pp.4-5) — declared,
complete, and enforced:

- **Turn sequence** — movement segment (side by side) then combat segment with
  **alternating single-unit fire**, exactly per I.B; damage applies immediately.
- **Movement** — MP budgets, facing (move through the front hexside), free pivots,
  +1 MP final-facing pivots, one-hex reverse with its facing constraints, move-OR-fire.
- **Gunnery** — the full three-question procedure: Hit Probability Numbers by range
  (2d6, +1 vs moved targets), rate of fire with **target acquisition** (fired at the
  same target last turn = more rounds), the **fire initiation doctrine** (no opening
  fire past HPN 8 unless flanked/answered), aspect determination (front/flank/rear by
  the hexside the shot crosses), per-vehicle **Area Impacted** charts, range-gated
  damage codes (K / M / F / possibility-kills / ricochets).
- **Every number transcribed from the module's own charts** (the .vmod ships the
  scanned rulebook and all tables) and validated against the rulebook's printed worked
  examples before use.

**The browser client** (`ui/tactical.html`): legal-move highlighting with MP costs, a
facing wheel, fire rings showing to-hit odds on every target, range rings, on-map shot
results (MISS / RICOCHET / K-KILL), synthesized sound, an in-game rules **Guide**, a
live audit-log panel where rejected proposals show up in red — and an AI opponent you
can run **auto-paced or stepped with the spacebar** (watch it select a unit, declare
intent, then act).

## The anti-cheat architecture

1. **One gate for everyone.** `engine/gamestate.py` exposes exactly one door,
   `submit(side, action)`. Human clicks and AI decisions become identical proposals.
   Illegal ones are rejected with the rule citation ("no weapon or vehicle which has
   been MOVED may fire in the combat segment of the same turn [I.E.4]").
2. **The AI owns nothing.** `engine/ai.py` reads the same public state you see and
   submits proposals like anyone else. It cannot roll dice, cannot apply damage,
   cannot move a counter — it can only ask.
3. **Append-only log.** Every proposal — legal or rejected — is written to
   `live/game_tobruk.log.jsonl` with the verdict, the dice, and a state hash.
4. **Independent verification.** `engine/verify_game.py` replays the log through a
   fresh engine: every verdict re-validated, every die re-rolled from the logged seed,
   every state hash re-derived. If any illegal action had ever been applied, or a die
   fudged, or a counter teleported, the replay cannot reproduce the log.

## Where the rules came from — and why this generalizes

Nothing here required owning the physical game. The Tobruk module **ships its own
source material**: the complete scanned 1975 rulebook (36 pages), the Hit Probability
Tables, the per-vehicle Target & Damage cards, the Turn Sequence chart — all as images
inside the `.vmod`. The build pipeline was:

1. **Read the scanned rulebook** out of the module → the rules scope (Scenario One)
   and every procedure, with section numbers.
2. **Transcribe the charts** into data files (`games/tobruk/combat.json`) — every
   table cell cites the exact chart image it came from.
3. **Validate against the rulebook's own worked examples** before trusting anything
   (the book says a 2-pounder needs 6+ at 8 hexes and a 47mm M37 needs 11+ at 12-13
   hexes — the transcribed tables must reproduce both, and do).
4. **Encode the procedures** as the gate, citing rule sections in its rejections.

That recipe is repeatable for **any module that packages its reference material** —
and most serious VASSAL modules do (rulebooks, charts, player aids are standard
contents). Grid geometry comes from the module's `buildFile`, counters from its
PieceSlots, scenarios can be built from data (`make_save.py`), and the rules layer is
JSON plus one procedure module. Game #2 of this engine (Arnhem) and game #3 (ASL)
were driven from their modules the same way.

## How this relates to VASSAL (it is not a fork — but VASSAL made it feasible)

Credit where it belongs: **this project exists because the VASSAL ecosystem did the
digitizing.** Thirty years of volunteer module authors produced exactly the data this
engine consumes — maps scanned and grid-calibrated, every counter as art, the charts,
and often the entire rulebook, packaged in one `.vmod` and hosted with the publishers'
permission. Building the same thing from a physical copy would have been possible;
the module ecosystem made it an afternoon instead of a month, and it's why the
approach can scale to the thousands of other modules. This is built **on VASSAL's
shoulders, without touching VASSAL's code** — a complement to the module ecosystem,
not a competitor to the engine.

Technically, the project contains **zero lines of VASSAL code**. It is an independent
engine (pure-stdlib Python) that is **file-format compatible** with VASSAL 3:

- It reads and writes VASSAL's own `.vsav` saves (the `!VCSK` + XOR-obfuscated zip),
  byte-perfectly — real VASSAL opens our saves and vice versa.
- It reads the **module** (`.vmod`) as data: grid geometry from the `buildFile`,
  counters from PieceSlot definitions, map art, and the charts the rules were
  transcribed from. A VASSAL module is a data package, and this engine is another
  consumer of that data — the way a spreadsheet other than Excel can open an .xlsx.
- VASSAL never needs to run. The save file *is* the game state; VASSAL, this browser
  UI, and the AI are three interchangeable clients of the same file. (The VASSAL team
  has said a programmatic game-state API arrives in V4 — this is that behavior on V3
  files, today, without touching their code.)

## Quickstart (bring your own module)

Python 3.10+. The engine is stdlib-only; `pip install pillow` once for setup's
map conversion.

```
git clone https://github.com/DrEvil-TitaniumHelix/vsav-engine
# download Tobruk_v1.1.vmod from https://vassalengine.org/wiki/Module:Tobruk
python engine/setup_module.py tobruk "path/to/Tobruk_v1.1.vmod"
python ui/server.py --game games/tobruk
# open http://localhost:8642 — you're British; the AI plays the Italians
```

Verify any finished (or in-progress) game:

```
python engine/verify_game.py live/game_tobruk.log.jsonl -v
```

## What's in the repo

```
engine/gamestate.py        THE LEGALITY GATE: turn flow, movement/fire validation with
                           rule citations, seeded dice, damage, VP, append-only log
engine/combat.py           the three-question gunnery procedure (data-driven)
engine/verify_game.py      standalone auditor: replays a game log, re-checks everything
engine/ai.py               the AI opponent's policy — proposes through the same gate
engine/gamespec.py         one engine, many games: grids, sides, terrain, movement
engine/vsav.py             .vsav codec (zip + !VCSK/XOR), byte-perfect round-trip
engine/board.py            full-fidelity save parser/mover (pieces + stacks)
engine/make_save.py        builds scenario .vsav files from the module's own PieceSlots
engine/setup_module.py     one-command setup from a downloaded .vmod
engine/rules.py            v1 Arnhem CRT · engine/watch.py  human-move watcher
engine/extract_terrain.py  terrain from map art (v1) · capture_baseline.py  regression
games/tobruk/game.json     the game as data: grid, facing, sides, MAs
games/tobruk/combat.json   to-hit tables, Area Impacted, damage cards — every cell
                           cites its source chart image in the module
games/tobruk/scenario_firefight_b.json   the scenario as data
ui/server.py               HTTP API: state/legal_moves/legal_targets/action/ai_plan/log
ui/tactical.html           the playable browser client (v2)
ui/index.html              the v1 movement-legality client
web/                       v1 serverless browser build (movement only)
```

## What's NOT in the repo (bring your own)

**No game assets are included or ever will be.** Maps, counter art, charts, and rules
are the property of their rights-holders; the modules are hosted **with permission** at
vassalengine.org — get them there (`setup_module.py` does the rest). This repo is code
plus data *derived by us from the rules* (tables transcribed and cited, like any rules
reference), under the same bring-your-own-module guardrail as v1.

## Legal

Code is MIT. *Tobruk* © its rights-holders (originally Avalon Hill, 1975); *Arnhem* /
*Westwall* © Decision Games; ASL/VASL content © MMP / the VASL project. This project
ships none of their material. Not affiliated with or endorsed by VASSAL, Decision
Games, or MMP.
