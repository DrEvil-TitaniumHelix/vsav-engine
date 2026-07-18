# VALOR Engine — VASSAL-Adjudicated Legality Of Rules

[![tests](https://github.com/DrEvil-TitaniumHelix/vsav-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/DrEvil-TitaniumHelix/vsav-engine/actions/workflows/ci.yml)

**▶ Play it in your browser — nothing to install:** https://vassal-test.pages.dev

*(Formerly "Dr Evil's Game Legality Engine for VASSAL". The repo keeps its
`vsav-engine` slug; the system is the **VALOR Engine**.)*

**This system encodes a printed wargame whole — the map, the counters, the
rules, the combat tables — and makes it a computerized version of the game.**
Not a digital tabletop where you push pieces and consult the rulebook
yourself: the game itself, encoded. The map becomes grid geometry and per-hex
terrain; every counter becomes data with its factors and its art; every rule
becomes an enforced procedure citing its rulebook section; every combat table
is transcribed cell by cell and rolled on by the engine. The result plays like
the printed game because it *is* the printed game, executable.

And **neither side is capable of cheating**: every action either player (human
or AI) proposes passes through the same deterministic legality gate, every die
is rolled by the gate from a seeded stream, and the whole game is recorded in
an append-only log that **anyone can independently re-verify**. That is the
name: **V**ASSAL-**A**djudicated **L**egality **O**f **R**ules.

Want your own game encoded the same way? See **ENCODING_GUIDE.md** — clone the
repo, bring your game's VASSAL module and rulebook, and ask Claude (Fable) to
"do the same thing for my game."

This is the working answer to *"an AI opponent will cheat and won't even know it's
cheating."* The AI never adjudicates anything. It proposes; the gate disposes; the log
remembers; the verifier proves.

```
python engine/verify_game.py live/game_tobruk.log.jsonl
VERIFIED: 85/85 entries: every verdict, every die, every state hash reproduced
          (0 illegal proposals ever touched the game state)
```

**Play in the browser:** https://vassal-test.pages.dev · **Watch it play:**
https://www.youtube.com/watch?v=Afomvk0LjU8 · **Windows download:**
https://drive.google.com/file/d/1FuJlt54Mb2FIAunbKrEXBKCpHCOngCpH/view

**Four complete games ship in this repo, playable out of the box:** Avalon
Hill's **Afrika Korps** (the flagship — the full strategic campaign), SPI's
**Blue & Gray: Chickamauga** (the classic 1975 Civil War hex battle, encoded
overnight as the platform's second full Tier-3 game), SPI's **Westwall:
Arnhem** (the 1976 Market-Garden operational battle — airborne drops, bridge
demolition, engineers) and Avalon Hill's **Tobruk** (a tactical tank
firefight). A fifth, GMT's **Austerlitz** (2000, Great Battles of the
Napoleonic Wars — the chit-pull command system, reaction windows, cavalry
charges, at full enforcement with an AI opponent), plays in the hosted
browser demo bring-your-own-module. v1 (movement legality for ASL) is still
here and still works. By **DrEvil / Titanium Helix**. MIT licensed.

---

## Game 1: Afrika Korps (Avalon Hill, 1964) — the flagship

The **entire campaign game, encoded**: the full North Africa map (playable
Qattara edges and all its printed map errata), every unit counter with its
factors, the complete 3rd-edition rules as an enforced, cited gate —
movement, zones of control, stacking, the supply system (landing, capture,
isolation, army collapse), fortresses, Automatic Victory, replacements,
substitutes, Rommel — and the CRT transcribed cell by cell and validated
66/66 against two independent sources plus the rulebook's own worked
examples.

- **Tier system** — play it your way: Tier 0 free play (you're the umpire),
  Tier 1 movement enforced, Tier 2 full combat gate, **Tier 3 with an AI
  opponent** that plays whole campaign turns — stepped action-by-action with
  the spacebar or animated auto-play.
- **Seven validators** (`games/afrika-korps-classic-ah/validate_*.py`) are the
  evidence chain: grid, movement, tier 1, combat, tier 2, arrivals, AI —
  every one green before any tier badge. `VALIDATION.md` documents it.
- **A source-defect register**: encoding surfaced eight defects in the
  *printed* game — editing errors, contradictions, undefined cases, a broken
  cross-reference, map errata — each recorded in `game.json` with quoted
  evidence, the enforced resolution, and its authority. The in-game Rules
  panel renders the register.

## Game 2: Blue & Gray — Chickamauga (SPI, 1975) — Tier 3

**The Last Victory, 20 September 1863** — the complete campaign game from
SPI's classic quad: the full battlefield map (creek crossings, the four named
bridges and six fords read off the map art), all 86 counters on the printed
deployment and reinforcement schedules, and the original rules as an
enforced, cited gate — movement and terrain costs, rigid ZOCs, mandatory
combat, the 1d6 CRT (validated cell-by-cell against two independent
printings), one-hex retreats with displacement chains, advance after combat,
artillery bombardment with line of sight, night turns, map exits, the Union
Train, and the full Victory Point schedule with both lines-of-communication
checks.

- **Tier 3**: policy AI opponent through the same gate — five AI-vs-AI
  campaigns complete all 15 game turns and replay byte-exact.
- **Five validators** (`games/blue-and-gray-chickamauga/validate_*.py`):
  grid, movement, gate, combat, AI — the same evidence chain as Afrika Korps.
- **The register works**: encoding found the 1975 rules citing an exit hex
  (0110) that contradicts the game's own map (the road exits at 0111) — the
  defect, the map evidence and the official correction are recorded in
  `game.json` and rendered in the Rules panel.

## Game 3: Westwall — Arnhem (SPI, 1976) — Tier 3

**The Historical Scenario** from SPI's *Westwall* quadrigame — Operation
Market-Garden at the Arnhem end of the corridor: the full operational map with
the Rijn and Waal, the canals (drawn in stream ink), the road/rail bridges and
ferries read off the map art; every counter on the printed reinforcement and
airborne-drop schedules; and the original rules as an enforced, cited gate —
the **terrain-differential CRT** [7.61] (four terrain rows, best-of favorability),
rigid ZOCs that lock at start and don't reach across non-bridge river hexsides
[6.33], the five **vehicle movement classes** [5.24], stacking prohibited [5.31]
except the Engineer assault stack, **airborne drops** with arrival movement
[15.3x], **bridge demolition** (canal and rail, one die-roll chance ever) [12.x],
engineers (canal repair, river crossing) [13.x], the Allied ground-supply pool
[14.11] and lines-of-communication trace [17.3x], and the full Victory-Point
schedule with the Waal and Rijn zones and the German:Allied victory ratio.

- **Tier 3**: policy AI opponent through the same gate — five AI-vs-AI
  campaigns run to term and replay byte-exact.
- **Five validators** (`games/westwall-arnhem/validate_*.py`): grid (18/18
  printed anchors), movement (the vehicle classes and river-ZOC step rules),
  gate, combat (CRT cross-checked three ways), AI — the same evidence chain.
- **The register works**: three defects in the printed game are recorded in
  `game.json` with quoted evidence and the enforced resolution, rendered in the
  Rules panel. (Encoding also corrected the old "stacking allowed" lore —
  Arnhem stacking is *prohibited* by 5.31.)

## Game 4: Tobruk (Avalon Hill, 1975) — the tactical proof game

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

## Code tour — where the rules live, where a move is checked

Three questions every code reader asks, answered up front:

**1. Where are the rules encoded?** In two layers — there is deliberately no
`<game>_rules.py`:

- **Data:** `games/<game>/game.json` is the game. For Afrika Korps that file
  holds the complete CRT (`combat.crt` — all 66 cells, with a `provenance`
  field naming the two independent transcriptions it was cross-checked
  against), the movement and terrain-cost config, unit types and factors,
  the credits, and the source-defect register. Rulebook section numbers are
  carried in the data entries themselves. `terrain.json` holds per-hex
  terrain; `scenario_*.json` holds setup and reinforcement schedules.
- **Procedure:** one gate module per game family interprets that data and
  enforces the rules that don't reduce to a table — ZOC, stacking, mandatory
  attacks, supply tracing, turn sequence. Rule numbers are cited inline in
  the code where each rule is enforced.

The point of the split: adding a game is mostly writing a new data file, not
new engine code.

**2. Where is a move checked?** Each game has exactly one door, a
`submit(side, action)` method. Every proposal — human click or AI decision —
goes through it; illegal ones are rejected with the rule citation, legal ones
are applied and appended to the JSONL log.

| Game | Gate (`submit()` lives in) |
|---|---|
| Afrika Korps | `engine/strategic.py` (`StrategicGame`) |
| Blue & Gray: Chickamauga | `engine/bluegray.py` |
| Westwall: Arnhem | `engine/westwall.py` |
| Tobruk (tactical) | `engine/gamestate.py` |

`engine/verify_game.py` replays any log through a fresh engine and re-derives
every verdict, die and state hash.

**3. What is `VALIDATION.md`?** Each game directory's `VALIDATION.md` is the
evidence worksheet — working notes recorded *as the validation was done*
(what was checked, against which source, what broke, how it was fixed). It's
an audit trail, not an introduction; start with this section and
`ENCODING_GUIDE.md` instead, then use `VALIDATION.md` to audit any specific
claim.

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

## Quickstart

**Recommended path (testers):** download the repo, open the folder in PyCharm
(or your preferred IDE), launch **Claude Code with the Fable model** in it, and
ask: *"Read GETTING_STARTED.md and get me started."* Claude sets everything up,
starts the game, and answers rules questions while you play.

**Manual path** — Python 3.10+, the engine itself is stdlib-only:

```
git clone https://github.com/DrEvil-TitaniumHelix/vsav-engine
pip install -r requirements.txt     # just pywebview, for the native window
python app.py                       # window opens → pick a game → play
```

or in a plain browser with zero dependencies: `python ui/server.py` and open
the printed URL. The release games (**Afrika Korps**, **Blue & Gray:
Chickamauga**, **Westwall: Arnhem**, **Tobruk**) are
self-contained in `games_bundled/` — a fresh clone plays out of the box.

**No-Python path:** download the prebuilt Windows exe from the
[Releases page](https://github.com/DrEvil-TitaniumHelix/vsav-engine/releases/latest)
(also mirrored on Google Drive:
https://drive.google.com/file/d/1FuJlt54Mb2FIAunbKrEXBKCpHCOngCpH/view).
Double-click it — see RELEASE_README.md for the SmartScreen first-run warning
and the Mac build.

Verify any finished (or in-progress) game:

```
python engine/verify_game.py live/game_tobruk.log.jsonl -v
```

Other games (ASL) remain bring-your-own-module:

```
# download Tobruk_v1.1.vmod from https://vassalengine.org/wiki/Module:Tobruk
python engine/setup_module.py tobruk "path/to/Tobruk_v1.1.vmod"
python ui/server.py --game games/tobruk
```

## Testing

One command runs the whole suite:

```
python run_all.py             # every game's validators, one PASS/FAIL summary
python run_all.py --fast      # skip the slow multi-seed AI campaigns
python run_all.py --ai-smoke  # AI validators in 1-seed smoke mode (what CI runs)
python run_all.py --game westwall-arnhem   # one game only
```

The suite *is* the validators: each `games/<name>/validate_*.py` is a standalone
evidence script (grid, movement, gate, combat, AI) that exits non-zero on any
discrepancy — the same checks that gate a game's tier badge, documented per game
in its `VALIDATION.md`. The engine is stdlib-only, so no install step is needed
to run them. A few validators cross-check against private decode material that
isn't in this public repo; those **skip cleanly** when it's absent (as in CI),
and never fail the run. This is exactly what runs on every push (see the badge
above). To audit a specific finished game, replay its log independently:

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
games_bundled/             the four release games, SELF-CONTAINED (map, counters,
                           scenario) — a fresh clone plays out of the box
games/afrika-korps-classic-ah/  the flagship as data: game.json (rules config,
                           credits, source-defect register), terrain.json,
                           scenario_campaign.json, seven validators, VALIDATION.md
games/tobruk/game.json     the game as data: grid, facing, sides, MAs
games/tobruk/combat.json   to-hit tables, Area Impacted, damage cards — every cell
                           cites its source chart image in the module
games/tobruk/scenario_firefight_b.json   the scenario as data
engine/ai_strategic.py     the strategic AI (Afrika Korps campaign turns)
ui/server.py               HTTP API: state/legal_moves/legal_targets/action/ai_plan/log
ui/tactical.html           the playable browser client (v2)
ui/index.html              the v1 movement-legality client
web/                       v1 serverless browser build (movement only)
```

## What ships in the repo vs bring-your-own

The four **release games** ship self-contained in `games_bundled/` for the closed
tester group: exactly the map and the counters their scenario uses (sourced from
the games' VASSAL modules, hosted with permission at vassalengine.org), no
rulebook scans, no unused art. The combat tables are **our transcriptions** with
rulebook citations — data, not scans. Full credits for each game's designers,
publisher, and module authors are in its `game.json` and rendered in the in-game
Rules panel.

Everything else stays **bring-your-own-module**: other games' folders hold only
our spec/rules data, and `setup_module.py` ingests the module you download from
vassalengine.org yourself.

## Legal

Code is MIT. *Tobruk* © its rights-holders (originally Avalon Hill, 1975); *Arnhem* /
*Westwall* © Decision Games; ASL/VASL content © MMP / the VASL project. This project
ships none of their material. Not affiliated with or endorsed by VASSAL, Decision
Games, or MMP.
