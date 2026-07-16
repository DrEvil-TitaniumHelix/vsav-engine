# Engine design: the Napoleonic tactical families

**Status: DESIGN FOR REVIEW (Bruce + mastermind) — nothing here is built. 2026-07-16.**
**Trigger game: Austerlitz: Napoleon's Greatest Victory (GMT 2000, David Fox) — Great Battles of the Napoleonic Wars Vol. I. Ingested at Tier 0 as `games/austerlitz-gmt`.**

## Why this is engine work, not game work

Austerlitz fails pre-screen gate 3 (mechanics fit) on four counts. Per the standing
rule — capabilities are built ONCE at engine level so every qualifying game
inherits them — each gap is designed as a reusable engine family, not an
Austerlitz special. The same four families cover GMT's Triumph & Glory series
(Marengo, Wagram — same system, free living rules already downloaded), and
three of the four cover broad classes beyond Napoleonics (chit-pull activation,
morale/step ledgers, and reaction fire each unlock whole shelves of the module
library).

Everything below cites the Austerlitz rulebook (`literature/austerlitz/aus_rules.pdf`,
free from GMT) as the reference implementation target.

## What the engine already has (no work)

- Hex grid, terrain costs, hexside rules, roads, stacking — `gamespec.py` (TEC 5.0 fits the existing shape, but see Family B for the formation dimension)
- Facing with front/flank/rear aspects — proven in Tobruk's 3-question fire model (6.1's front/flank/rear is the same idea)
- Table-driven combat with cited cells — CRT (Arnhem/AK) and to-hit ladders (Tobruk); the Fire Table [8.1.8] and Melee Result Table [8.5] are ordinary table lookups
- Seeded, logged, engine-owned RNG — which is exactly what makes a **chit draw** replayable (a LIM draw is a dice roll over the pool contents)
- The gate/log/verifier trinity — unchanged; every new family routes through `submit()`

## Family A — Command pool & activation (`engine/command.py`)

**What the rules demand [3.0, 4.0]:** turn = Pool Placement → LIM Activation →
Non-LIM → Rally. LIMs (Leader Initiative Markers) sit in an opaque pool; players
add them via Command Change rolls [4.2] (corps LIM supersedes its division LIMs
[4.2.1]), an opposed initiative roll picks who seeds the turn [4.4], then LIMs are
drawn at random and the drawn leader rolls ≤ activation rating for Full Activation,
takes an automatic Limited Activation, or fails onto the Command Breakdown Table
whose column is the leader's personality (Aggressive/Normal/Cautious) [4.5, 4.7].
Only In-Command units (hex range to their division leader) act when their division
activates [4.3.3].

**Engine shape:**
- New spec block `command`: leader hierarchy (overall → corps → division), each
  leader's activation / personality / command-range ratings, LIM roster, the
  Command Change and Command Breakdown tables as cited data.
- Turn flow becomes a small state machine owned by the engine. The random draw
  is an engine RNG event — logged like a die roll, so replay/verify works unchanged.
- New gate actions: `command_change`, `choose_initiative_lim`, `activation_choice`
  (full/limited), then ordinary move/combat actions scoped to the active division.
- Legality: the gate rejects any action by a unit that is not In Command of the
  currently activated division — a pure hex-range check we already know how to do.

**Reuse beyond Napoleonics:** chit-pull/random-activation is one of the most common
wargame families in the library (many SPI/AH/GMT titles). This family is the
single biggest unlock of the four.

**Scenario data note:** initial LIMs per scenario are recoverable from the module's
own scenario saves (the LIM Board map carries the starting chits) — no playbook needed
for that part.

## Family B — Formation states (extension of facing/stats)

**What the rules demand [6.0, 7.0, TEC 5.0]:** every unit is always in a formation
(infantry: line/column/square/skirmish/disorder; cavalry: line/column/disorder;
artillery: limbered/unlimbered) — and formation determines movement cost column,
stacking limit [7.1], facing behavior, and combat modifiers. Formation change is
itself a priced move; disorder is an involuntary formation [6.4].

**Engine shape:**
- Unit state gains `formation` (persisted, hashed, logged — same contract as
  position/facing today).
- `terrain_mp` becomes keyed by (terrain, unit class, formation) — the TEC is
  literally printed that way, so the spec transcription stays cell-by-cell.
- Stacking limits keyed by (terrain type, formation) per Stacking Chart [7.1].
- New gate action `change_formation` with MP cost + disorder checks where the
  TEC says so.

This is the *least* novel family — it's a data-model widening of things the engine
already does (Tobruk facing, per-class movement). It is also the prerequisite for
everything else: fire/melee modifiers are mostly formation terms.

## Family C — Morale / rout / rally / fatigue ledger (`engine/morale.py`)

**What the rules demand [9.0–13.0]:** combat results are rarely "eliminated" —
they are SP losses plus morale checks (Morale Check Table 9.1), rout retreats
with a procedure [10.1], breakpoints at unit/division/corps level [11.0], a Rally
phase [12.0], and an army-level fatigue track with its own effects table [13.0].

**Engine shape:**
- Per-unit persistent ledger: current morale vs printed, SP strength, disorder,
  routed, fatigue contribution; division/corps rollups for breakpoint checks.
- **Effects interpreter:** a table cell resolves to a typed effect list —
  `[lose_sp 1, morale_check +2, retreat 3, disorder]` — executed by the engine
  with every roll logged. This formalizes what the Chickamauga retreat-chain code
  already does ad hoc (see `validate_retreat_chain.py`), and becomes the shared
  vocabulary for ANY game whose CRT outputs compound results.
- Rally/fatigue phases are ordinary phase actions through the gate.

**Reuse:** step-loss + morale systems cover most tactical games in the library;
the effects interpreter benefits even existing games (cleaner CRT encodings).

## Family D — Reaction windows (the novel one)

**What the rules demand [6.2, 8.4]:** the NON-active player acts during the active
player's movement: reaction fire when an enemy spends MPs in a unit's Reaction
Zone (entry alone does NOT trigger it [6.2.1]), skirmisher reaction moves,
cavalry free facing changes / countercharges / reaction charges, artillery
once-per-activation reaction fire budgets [6.2.4–6.2.5], infantry forming square
against a charge [8.4.2#4], pursuit after melee. Each reaction type has explicit
per-activation budgets.

**Engine shape (design center):**
- Every gate-applied action computes its **reaction windows**: the set of enemy
  units entitled to react, with the reaction types available and each unit's
  remaining budget. If non-empty, the game enters a `REACTION` state where ONLY
  the reacting side may submit (a reaction action or `decline`); then flow
  returns to the mover. This is a sub-turn inside an activation — same
  `submit()` door, no second code path.
- Budgets (e.g., "artillery reaction-fires once per enemy activation") are
  engine-tracked counters, reset on activation boundaries, all visible in the log.
- The audit log records window-open (who was entitled, to what) and every
  taken/declined reaction — so the verifier can prove not just that moves were
  legal but that every reaction *opportunity* was surfaced. That's a new,
  stronger honesty claim: the engine can't "forget" your defensive fire.
- Hotseat/PBM: reaction prompts are turns-within-turns; the PBM flow already
  supports multi-exchange turns. AI: the policy answers reaction prompts like
  any other decision node.

**Risk note:** this is the largest architectural change since the gate itself.
It should land LAST, after the other three families are validated, and behind a
per-game spec flag so no existing game's flow changes (frozen-contract rule:
existing HASH_KEYS/log dicts untouched; reaction records are new event types).

## Sequencing (proposal)

| Phase | Build | Earns | Validation source |
|---|---|---|---|
| 1 | Family B (formations) | Austerlitz **Tier 1** (movement gate) on "The Northern Flank" learning scenario | TEC + Stacking Chart transcribed cell-by-cell from embedded charts; errata applied; hex-label Chrome pass |
| 2 | Family C + Fire Table [8.1.8] + Artillery Range [8.1.6] | fire combat enforced | Fire/Morale/Fatigue tables from embedded charts; GMT errata as source-defect seeds |
| 3 | Family A (command pool) | full turn structure | Command tables p1 of charts; initial LIMs from scenario saves |
| 4 | Family D (reactions) + melee/charge procedures [8.2–8.5] | Austerlitz **Tier 2**, then Tier 3 per spec #22 pipeline | Melee/charge tables p4; worked examples — see open question 1 |

Honest scale estimate: phases 1–2 ≈ a Westwall-class encode each; phase 3
similar; phase 4 is bigger — it's new architecture plus the most intricate rules
in the book. This is a multi-week program, not an overnight encode.

## Source-defect register seeds (spec #21)

GMT's official errata (2000-07-20, `literature/austerlitz/aus_errata.html`) already
gives us: counter misprints (color bands, missing horse symbols, duplicate
"1/61 Ligne", wrong Austrian cavalry MA), a map clarification (only one Primary
Road), OOB units intentionally omitted, and six rules amendments (secret LIM pool
removal 3.0.C.3, concealed command change 4.2, multi-hex cavalry melee 6.5.6,
mandatory pre-melee morale checks 8.4, fatigue 13.3/A4.4.5.C, melee retreat
clarification 8.5). These go straight into `source_defects` with
authority = official errata when encoding starts.

## Open questions for Bruce

1. **The Playbook is not in GMT's free downloads** — scenario victory conditions,
   special-commander rules, and initiative modifiers live there. Initial LIMs and
   setups we can recover from the module; VCs we cannot. Options: Bruce owns/buys
   the printed game (BYO principle applies to us too), or we ask GMT/BGG for the
   scenario pages, or Tier 1 ships with movement only and VCs wait.
2. **Multi-hex counters [6.5]** (cavalry regiments spanning 2 hexes) — engine
   currently assumes 1 unit = 1 hex. Small but real data-model change; fold into
   Family B or defer?
3. **Priority vs the standing queue** — champion PBM wiring (both games) and the
   release bundle are still open from 7/14–16. This program is large; where does
   it sit?
