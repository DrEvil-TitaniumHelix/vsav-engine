# Encoding your own game — the "do this for Blue and Gray" guide

This engine **encodes a printed wargame whole**: the map, the counters, the
rules, the combat tables — everything — and turns it into a computerized
version that enforces the game's own rules. The two shipped games (Afrika
Korps, Tobruk) were built exactly this way, and the process is repeatable for
yours.

## The prompt

Clone this repo, open it in your IDE, launch **Claude Code (Fable model)**,
and say, for example:

> *"I have SPI's Blue and Gray. Do the same thing for my game — put Blue and
> Gray in the engine."*

Claude reads this guide, studies the reference game, and drives the encoding
with you. Expect a collaboration over multiple sessions, not a one-button
import — the payoff is a game whose every enforced rule cites its rulebook
section.

## What you must bring

The repo ships no third-party game content beyond the two release games. For
your own game you supply:

1. **The VASSAL module** (`.vmod`) — download it yourself from its
   vassalengine.org module page. It provides the scanned map, the grid
   geometry (`buildFile`), every counter's art and definition, and usually the
   charts and player aids.
2. **The rulebook** — many modules ship the full scanned rulebook inside the
   `.vmod`; if yours doesn't, bring a copy. No rulebook, no rules encoding
   (the module still ingests to a bare board — the starting point for
   encoding, not a playable game).
3. **A starting position** — a setup save or the printed setup instructions,
   so a scenario can be built (`engine/make_save.py` builds `.vsav` files from
   the module's own pieces).

## What gets encoded

- **The map** — grid geometry from the module's `buildFile` (hex/offset/pixel
  math), terrain per hex (`terrain.json`), plus map errata.
- **The counters** — every unit as data: side, type, combat factors, movement
  allowance, linked to the module's art.
- **The rules** — turn sequence, movement, zones of control, stacking,
  supply… as gate procedures, each carrying its rulebook citation. Illegal
  moves are rejected with the rule that forbids them.
- **The combat** — the CRT / to-hit tables transcribed **cell by cell** into
  data (never trusted as images), each cell citing its source chart.
- **The scenario** — starting forces, reinforcement schedules, victory
  conditions.
- **The credits** — the printed game's designers and publisher, and the
  VASSAL module's authors, rendered in the in-game Rules panel.

## Can my game be encoded? — the five-point pre-screen

All five must pass for a game to ship with an **enforced** rules gate:

1. **Rules present** — embedded in the module or freely/legitimately obtainable.
2. **Rules transcribe cleanly** — clear procedures, ideally with worked
   examples in the rulebook to validate against.
3. **Mechanics fit the engine** — hex *or* named-region movement substrate,
   plus (behind a rules gate) ZOC/terrain and one combat flavor already built
   (odds/differential CRT, or to-hit/damage). Region / area / point-to-point
   maps are **in-engine** as ingest space (`space.kind=region`; see
   `AREA_MAP_DESIGN.md`; War Room gap G1) — per-game
   folders still need ingest + authored edges; region *rules* gates are later.
   Not yet in the engine: card-driven systems, hidden movement, air/naval
   subsystems — each is a future engine expansion, not a per-game hack.
4. **Complete playable scope exists** — a defined scenario with victory
   conditions, not the whole game system at once.
5. **Every encoded table is validatable** — worked examples, a second printed
   source, or expert review. No way to check the transcription = no
   enforcement.

Failing the screen means the game is not offered. The module still ingests
to a bare board (VASSAL-parity piece pushing) that you can encode on top of,
but unenforced play is not a VALOR game — that is what VASSAL already does.

## The coverage matrix — a game ships whole or not at all

The old Tier 0–3 ladder is retired. Playability is binary and strict:

- Build a **coverage matrix** for the game: every rule, in every phase of the
  turn sequence, per scenario, is a cell (`COVERAGE_MATRIX.md`; see
  `games/siege-of-jerusalem-ah/` and `games/napoleon-at-waterloo/`).
- A cell is closed only when it is **enforced** by the gate or **unreachable,
  with evidence**. There is no "umpired" state: an action the gate cannot
  check is a defect.
- The game is offered when every cell is closed. Until then it is work in
  progress, however much of it is enforced. You still build incrementally —
  movement, then combat, then the rest — but those are build stages, not
  shippable ratings.
- What a player chooses is **seats**, not a rules level: Human, Basic AI,
  Champion/Advanced AI or Harness in each seat, gate always on.

**The iron rule: a wrong gate is worse than no gate.** Every table and
procedure must be validated against the rulebook's *own worked examples* (or
expert review) before the engine may enforce it. If a table can't be
validated, its cell stays open and the game is not offered until it is.

## The process (follow the reference game)

`games/afrika-korps-classic-ah/` is the complete worked example — every step
below has a concrete artifact there to copy the shape of:

1. **Ingest the module** — extract the `.vmod`, read `buildFile` for grid
   geometry and PieceSlots (see `engine/ingest.py`, `engine/setup_module.py`;
   AK's `INGEST_REPORT.md` / `ingest_summary.json` show the output).
2. **Write `game.json`** — grid, sides, counters, assets. This
   file IS the game; the engine is generic.
3. **Terrain** — per-hex terrain data (`build_terrain.py`, `terrain.json`).
4. **Scenario** — starting position + arrivals (`make_scenario.py`,
   `scenario_campaign.json`, a `.vsav` via `engine/make_save.py`).
5. **Transcribe the tables** — CRT, terrain effects, whatever the game
   resolves on — into cited data (Tobruk's `combat.json` is the pattern).
6. **Validate everything** — AK has seven validators
   (`validate_grid/movement/full_scope/combat/completion/arrivals/ai.py`) run against
   the rulebook's printed examples, with the evidence chain in
   `VALIDATION.md`. Your game needs its equivalent before it is offered.
7. **Register the original game's defects** — encoding always surfaces bugs
   in the *printed* game (contradictions, undefined cases, broken
   cross-references, map errata). They go in `game.json` `source_defects`
   with quoted evidence, the resolution enforced, and the resolution's
   authority (official errata > tournament ruling > proven equivalence >
   declared umpired). AK ships eight entries; the Rules panel renders them.
8. **Credits** — fill the `credits` section from the printed credits and the
   module's credits page.

## Non-negotiables (the engine's constitution)

- **Citations**: every enforced rule names its rulebook section.
- **Engine-owned dice**: seeded, logged, replayable — no client-side rolls.
- **Everything logged**: every proposal (legal or rejected) goes to an
  append-only log; `engine/verify_game.py` must replay it byte-exact.
- **No unvalidated enforcement**: see the iron rule above.
- **Bring your own module**: your game's assets come from your download of
  its sanctioned module, and stay out of the public repo.
