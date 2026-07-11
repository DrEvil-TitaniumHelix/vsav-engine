# Westwall: Arnhem — validation evidence chain

Encoded 2026-07-11 (Bruce's directive: "do for Westwall what you did for Blue
and Gray" — mastermind's factor→image binding brief of 2026-07-09 consumed).
Everything below ran green before the tier claim. Earned tier: **3**.

## Sources
1. **Westwall Standard Rules** (SPI 1976) — OCR sidecar
   `C:/VassalLibrary/_meta/ocr/Westwall_ Four Battles to Germany__WestWallStdRules.txt`
   (complete, 1.0–9.14); scanned PDFs alongside.
2. **Arnhem Exclusive Rules** (same folder, `__WestWallQuad.txt`) — complete
   10.0–18.26 + design credits + the printed Integrated CRT.
3. **`C:/VassalIngest/westwall/`** — mastermind's decode: `counter_stats.json`
   (374 units), `counter_stats_by_image.json` (AK-parity binding),
   `map_tables_transcription.json` (independent image-only CRT + Terrain Key).
4. **Westwall Quad.vmod** (extracted) — buildFile grids, 469 piece images,
   `Arnhem Historical.vsav` setup, save key 0xA3.

## Counter stats (three-source agreement, asserted per unit)
- All **95 Arnhem front-state counters read by eye** (contact sheets, 2026-07-11)
  against mastermind's binding AND the printed 18.12–18.15 schedule;
  `make_scenario.py` asserts factor equality for every one of the 96 units
  (95 images + the marker-bound Engineer).
- **13 binding corrections** recorded in `rules_transcription.json`
  (`binding_corrections`): the 1/1Lt & 2/1Lt airborne artillery (bound as
  infantry), 1/2 German 1-2-7 (bound as British 2/1), 2107 M 4-4-10,
  1/6PT & 2/6PT 2-3-7, side identities of 1/1PT & 2/1PT, the Engineer
  3-3-10 (bound as a factorless marker), 55 = 4-2-7/3-10, 15/19's dropped
  top line. Every ambiguous_bind flag from the brief resolved.

## Grid + module cross-validation (validate_grid.py — ALL PASS)
- buildFile HexGrid dx=96 dy=119 x0=60 y0=60 == the legacy hand-validated
  values; the formula resolves **18/18 printed anchors** in the module's own
  setup save (7 German 18.12 hexes, 3 DZ 18.11 hexes, 8 GT1 18.13 drop
  targets) + pixel↔hex roundtrip on all 930 on-map hexes.
- **Module deviation recorded**: the module pre-places the GT1 airborne
  stacked on their drop targets; the printed rules drop them one-per-hex
  [15.31] — our scenario holds them as GT1 reinforcements.

## Terrain (build_terrain.py — ALL PASS)
Base = the validated legacy extraction (ref/terrain.json); corrections all
eye-verified on annotated 2× map crops:
- **11 City hexes** (block-color census: city >1400 brown-block px, towns
  grey): Eindhoven 0203/0204/0304, Nijmegen 2520/2521/2620/2621, Arnhem
  3423/3523/3524, Oosterbeek 3521.
- **23 bridges TYPED** (12.15 demolition classes): 9 canal (Son 0505|0605,
  Best 0503|0603, Veghel 1207|1308, Waal-Maas 2518|2519 / 2319|2419 /
  2219|2220 / 2120|2121 / 2619|2720, Wilhelmina 0710|0711), 6 rail (all
  R-R-marked: Veghel 1206|1307, Gennep 1523|1524, Mook 1920|2020,
  Ravenstein 2413|2513, Rhenen 3411|3512, Arnhem 3422|3522), 8 highway/
  never-demolishable (incl. Grave 2216|2316, Nijmegen 2621|2721, Arnhem
  3323|3423 — the corridor's objectives).
- **3 ferries** (white-arrow symbols; +3 MP, non-bridge per 6.33):
  Driel/Heveadorp 3420|3520, Renkum 3608|3709, Huissen 3124|3125.
- **5 legacy false-positive bridges removed** (no symbol at 2× zoom).
- Canals measured to be drawn in STREAM ink → the canal-hexside undefined
  case resolved as stream (source_defects `canal-hexside-undefined`), which
  reproduces the historical Son situation: infantry wade at +3, vehicles
  wait for the Engineer [5.24/12.13/13.1].
- Declared limitation (rules_scope): railway LINES are decorative; the
  legacy road/trail layer may carry railway ink as trail on listed sides.

## Movement gate (validate_movement.py — ALL PASS)
Terrain Key costs, road ½ / trail 1 [5.22/5.23], river prohibition +
bridge/ferry crossings, stream +3, the full 5.24 vehicle-class bars
(step-level: woods/rough/broken entry, stream/ferry/rail-bridge crossings,
road-bridge allowed), rigid ZOC + 6.33 river blocking (both directions),
no-stacking, airborne arrival MA 3 [15.32], column entry ½/1/1½ [15.13],
Engineer river crossing incl. the 13.23 artillery bar, demolition's
movement effect + repair [12.13/13.1].

## Tier-1 gate (validate_gate.py — ALL PASS, sessions replay byte-exact)
Three multi-turn sessions through submit() only, each replayed byte-exact by
engine/verify_game.py: sequencing [4.1], the full GT1 drop, schedule
enforcement + withholding [15.0/15.23], drop-triggered demolition offers
[12.11] (paratroopers landing at Veghel trigger the German option — the gate
found this itself), the demolition die [12.12] + one-attempt-ever [12.14],
German exit + same-edge re-entry [15.4x], GSP schedule + expiry [18.16/9.14],
LOC scoring [17.3x]. Staged probes: airborne/ground LOC pass & fail cases,
Engineer canal repair [13.1], rail bridges never repaired [12.16].

## Tier-2 combat (validate_combat.py — ALL PASS)
- **CRT three-way cross-check on every run**: game.json == the printed
  table's OCR == mastermind's image transcription (12×6 cells, all terrain-row
  brackets, bounds), AND == engine/rules.py (the legacy CRT validated
  2026-07-03) across 4 rows × 23 differentials × 6 dice.
- The rulebook's own worked example [7.0] live through the gate: 13 vs 4 in
  a Town hex = +9 on the Town line, die 5 → D1 (seed-searched engine die).
- Staged sessions (byte-exact replays): mandatory-combat closure [7.11/7.12
  + the battle-time mandatory-joiners rule], FPF window + differential
  arithmetic 5−(3+2+4)=−4 [8.4x], GSP spend/decrement [9.14], city = Town
  line [11.2], city retreat-reduction to no-effect [11.1], rough row [7.44],
  pure-barrage 8.15 both branches, no-FPF-vs-pure-barrage [8.45], the 14.12
  two-artillery cap, De + advance along the vacated hex + no-second-attack
  [7.9x], Br defender-first [7.62], the 13.24 Engineer assault (stream line,
  mandatory attack).

## Tier-3 AI (validate_ai.py — ALL PASS)
- **5 seeds × full 10-GT AI-vs-AI campaigns**: all complete, 96–121 battles
  each, no stalls, ~1000 actions per game, **byte-exact verifier replays**
  (every verdict, die, state hash; 73–80 rejected proposals per game logged
  as proof of enforcement).
- Tier-1 (no combat) game clean; TurnStepper stream identical to take_turn.
- Outcomes are strongly German-favored across seeds (German Strategic,
  ~500:20 VP): the printed VP schedule (3 VP per Allied LOC failure per
  turn, 5 VP per Allied unit destroyed vs 1 per German) punishes the simple
  Allied corridor policy hard; the historical battle was also a German win.
  Both seats run the same policy — beta-fine per the AK/B&G precedent,
  declared in game.json policy_ai.

## Source-defect register (spec #21) — 3 entries in game.json
1. **canal-hexside-undefined** (undefined_case): 12.13 treats a demolished
   canal bridge as "a normal Canal or River hexside" but no rule or Terrain
   Key entry defines a Canal hexside; resolved as STREAM from map-ink
   measurement + CRT/TEC structure. Declared interpretation.
2. **german-east-reentry-0726-vs-2726** (editing_error): 15.42's east-edge
   re-entry span "0126–0726" contradicts 15.41's exit span "0126–2726";
   resolved as the symmetric 2726 (typo).
3. **rules-counters-designation-drift** (editing_error): 1/6PT vs printed
   1/6P, Hber vs Hbr, the 2/235 typo — matched by designation+factors
   together, asserted in make_scenario.py.

## Integration (API-verified end to end, 2026-07-11)
Fourth menu game (AK · B&G · **Westwall: Arnhem** · Tobruk), index.html
client with westwall panel branches (airborne drops, edge/column entries,
GSP, demolition decisions, FPF allocation, multi-hex retreat options with
the city no-effect button, advances), engine-level guidance/sole-next wiring,
stepped/animated AI via the same /api/ai_step. Verified against the live
server: drop → gate-computed legal hexes (MA 3) → gated move → phase flow →
AI stepper plays the whole German turn → menu switching in all directions →
state persists across switches → tier 1/3 selection → fresh reset.
games_bundled/westwall-arnhem self-contained (9.5 MB, loads 99 pieces +
boots the gate from the bundle alone).
**Pending: an in-Chrome visual pass** (the browser extension was not
connected during the run; every client code path was exercised at the API
level).

## Regressions after every engine-touching change
gamespec zoc.blocked_by_side_features is spec-gated (Arnhem baseline
byte-identical); westwall.py/ai_westwall.py are new modules. Final sweep
results in the session notes and the commit message.
