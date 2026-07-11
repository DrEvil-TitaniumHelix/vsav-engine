# Blue & Gray: Chickamauga — validation evidence chain

Encoded overnight 2026-07-10→11 (Bruce's directive: Chickamauga, original SPI
rules, Tier 3 target). Everything below ran green before the tier claim.

## Sources (all local, gitignored under literature/blue-and-gray/)
1. **1975 SPI folio scan** (`BGChickamauga.pdf`, spigames.net): Standard Rules
   4pp + Chickamauga Exclusive Rules + counter sheet + the CRT/TEC page +
   original map sheet. PRIMARY for "what does the original say".
2. **Decision Games Blue & Gray Deluxe rulebook** (clean text layer):
   "the original SPI rules, reformatted and including official errata and
   clarifications" — primary transcription source; every divergence from the
   1975 printing treated as errata evidence.
3. **The VASSAL module** (`Blue and Gray Complete.vmod` 1.0): map art,
   counters, grids, per-battle setup saves.
4. **Stafford 2018 revised rules** (Bruce's Scribd source): a fan REVISION
   (leaders, disruption, 2d6 CRT) — used only as a tie-break clarification
   aid, never as the encoded ruleset. Community evidence (DG's own reprint
   intent, the module's counter mix, the revision's ~111 views) says the
   original IS what people play.

## Rules transcription (rules_transcription.json)
- CRT: all **60 cells** transcribed twice (1975 scan p8 vs deluxe p5) —
  identical; re-cross-checked against game.json on every validate_combat run.
- TEC, movement/ZOC/combat/artillery/night/train rules: 1975 text vs deluxe
  compared clause by clause; deluxe matched the original on every enforced
  rule (MA 6 all units, stacking 2, no-exit-from-EZOC, road 1 MP, trail 2/1,
  creek/bridge/ford, mandatory combat, 1-hex owner retreats, one advance).
- Deployment (46 units) + reinforcement schedule (40 units, GT2/5/6/7/8) from
  the 1975 charts.

## Module cross-validation (validate_grid.py — ALL PASS)
- Grid formula from the module buildFile resolves **46/46** chart positions
  (45 at-start pieces in `Chickamauga Start.vsav` + roundtrip 728/728 hexes).
- **Module deviations found** (worksheet in rules_transcription.json, both
  corrected to the printed chart in our scenario):
  - Wilder parked at 0822 (chart: 1022);
  - 2/4/XIV omitted from the module setup entirely (the counter exists in
    the module palette; chart hex 0822).

## Terrain (build_terrain.py — 38 anchors ALL PASS)
- 674 playable hexes classified from the module map art (clear 241 / forest
  300 / rough 12 / forest+rough 121), spot-verified against the 1975 map scan.
- Creek hexsides by edge-band coverage; **every creek crossing enumerated by
  eye at 3× zoom**: 4 bridges (all four match the map's own name labels —
  Alexander's 1922|2022, Reed's 2216|2316, Dyer's 2311|2411, Ringgold
  2403|2503) + 6 hatch-marked fords (2112|2212, 2218|2318, 2320|2420,
  2408|2508, 1527|1627, 1926|2026), pinned with ink-scored candidates.
- Roads/trails by both-sides ink density + connected-component size (solid vs
  dashed), validated on known road chains, the trail at 2123|2223, and
  plain-side negatives.

## Movement gate (validate_movement.py — ALL PASS)
TEC costs (incl. road-override into forest, trail cap, ford surcharge, the
5.25 composition), creek prohibition, ZOC stop/lock/creek-block/bridge-cross,
stacking 2 + free pass-through, MA-6 reach.

## Combat gate (validate_gate.py + validate_combat.py — ALL PASS)
- 60+ staged-session checks: turn sequence, reinforcement columns (15.0
  costs, occupied/both-blocked entries), exits + final VP scoring, night GT
  (no combat, no EZOC entry), mandatory-combat closure (7.11/7.12), CRT
  determinism, odds clamps (7-1→6-1) + voluntary reduction, terrain and
  all-across-ford doubling, printed-strength exchange under doubling,
  pure-bombardment immunity (8.15), LOS blocking + 8.41, trapped-retreat
  elimination, 7.74 no-contribution, single-unit advance (7.76), the Train
  (road/trail moves, hex blocking, auto-retreat).
- **Every session replayed byte-exact through engine/verify_game.py.**

## Tier 3 AI (validate_ai.py — ALL PASS)
- 5 seeds × full 15-GT AI-vs-AI campaigns: complete, no stalls, 45–78
  battles each, **byte-exact verifier replays** (every verdict, die, hash).
- Tier-1 (no combat) game clean; TurnStepper stream identical to take_turn.
- Outcomes Confederate-favored across seeds — consistent with the historical
  result and the printed VP schedule; both seats run the same policy.
  Declared-weak: no voluntary odds reduction, no diversionary-attack search.

## Source-defect register (spec #21) — 3 entries in game.json
1. **exit-hex-0110-vs-0111** (map_errata): the 1975 rules say exit hexes
   "0101 and 0110" three times; the 1975 map's road exits through **0111**
   (0110 is roadless clear). Resolution 0101/0111; authority = the original
   map + the deluxe's official correction.
2. **ford-trail-cost-composition** (ambiguity): every ford lies on a printed
   trail; encoded compositionally (trail cap + 1 MP), declared.
3. **csa-exit-vp-asymmetry** (ambiguity): 10 VP per exited CSA CSP enforced
   verbatim; designer's notes confirm the Chattanooga exit as the objective.

## Browser verification (Chrome, :8646)
Map + 46 counters at chart positions render; unit select shows gate-computed
legal hexes with costs; a move submits through the gate and mirrors to the
work .vsav; end-movement → combat → next player; the stepped AI reveals then
executes one action per /api/ai_step (engine-level spacebar/animated play);
Rules panel renders the tier, the full cited rules scope, the source-defect
register and the SPI credits — all engine-level, no game-specific client
code beyond the Blue & Gray reinforcement/exit/train panel branches.

## Regressions after every engine-touching change
Arnhem baseline SHA fe2a652f6f9c byte-identical (gamespec "cap" hexside
effect is inert without a spec rule using it); Tobruk verify; all AK
validators; all game loads. Final sweep results in the session notes.
