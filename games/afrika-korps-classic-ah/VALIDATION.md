# Afrika Korps — grid & rules validation worksheet

Spec #12 discipline: nothing ships until validated. This file records the
evidence chain for the sideways-grid mapping and, later, the CRT encoding.

## GRID: VERIFIED 2026-07-09 (re-run `python validate_grid.py` — ALL PASS)

**Geometry** (buildFile sideways HexGrid, axis-swap conversion): pointy-top,
dx=101.8, dy=88.1256, origin (0, 32), stagger, offset_parity=1.
Independently confirmed from the printed map grid itself:
- edge-energy autocorrelation over open desert (x 2000–5000, y 1500–2300):
  x period 51/102 px (dx with stagger halving), y period 89 px (dy)
- row-center phase from slant-edge band model: y ≡ 31.4 (mod 88.126) vs
  buildFile 32.0 — sub-pixel agreement
- per-row column phase: even rows x ≡ 0, odd rows x ≡ 50.9 (mod 101.8) —
  exactly buildFile x0=0 / parity 1
- overlay renders (lattice dots on map crops): every dot dead-center in a
  printed hex (desert, Tobruch, Agheila, Bengasi, Alamein crops)

**Naming** (encoded in game.json `grid.naming`): style `letter_diag`,
row0=5, num0=−10. Semantics: letter = chr('A' + row − 5) (letters increase
southward; printed alone on the map's EAST edge — I/J/K/L visually confirmed
at rows 13–16); number = col + (row−5)//2 − 9, constant along SW→NE
diagonals exactly as rulebook 1.1 describes ("numbers diagonally from
southwest to northeast"). Matches module numbering hOff=−5 (letters) with
vOff=−12 up to VASSAL's off-by-convention.

**Anchors — all exact (validate_grid.py):**
| Anchor | Source | (col,row) | Evidence |
|---|---|---|---|
| W3 German home base | rules 1.1 | (1,27) | gray palm/flag hex located on map image |
| W6 El Agheila | rules 1.1 | (4,27) | town circle on image |
| H2 Bengasi fortress | rules 1.1 | (8,12) | cross-hatch hex on image — even-row discriminator that killed the first formula candidate |
| G25 Tobruch fortress | rules 1.1 | (31,11) | cross-hatch hex on image |
| L59 El Alamein | rules 1.1 | (63,16) | town circle on image |
| J62 Allied home base | rules 1.1 | (67,14) | Union Jack hex on image (center within 5px of node) |
| I63 K64 M65 O66 Q67 S68 U69 | rules 5.8 playable east edge | all col 68 | seven hexes, one column — exactly the easternmost odd-row column |
| R68 forbidden partial | rules 5.8 | col 69 | the partial column east of it |

**Adjacency** — every consecutive pair in the rule-18 movement examples is
adjacent under the engine's neighbor math: G25-H26-I27-J27-J28,
H24-I25-I26-J27-I27-I28-H28-H29-I30, G22-H23-H24-H25-H26-H27, I26-J27-I26;
plus the anomalous hexsides E18-F19 and W62-X62 (rules 5/14/22 references).

**South-edge printed labels** ("-3", "-4", … near the Agheila corner) are
dash+number: the dash is the letter placeholder — rule 5.8 says "neither 70
nor Y are grid coordinates", i.e. the bottom partial row has no letter; the
numbers label the SW→NE diagonals and their magnitudes (3,4,5…) match the
mapping at those columns. NOT negative coordinates (earlier note wrong).

**Dead ends recorded** (don't retry): fitting the lattice from setup-piece
positions fails — pieces are hand-placed off-center and contaminated by
turn-track/holding-box rows (phase-coherence peak at dy≈67.45 is the track
spacing, not the grid). The printed map grid is the ground truth.

## TIER-1 SUBMIT GATE: LIVE + VALIDATED 2026-07-09 (re-run `python validate_gate.py`)
The anti-cheat trinity (spec #9) is wired for the campaign scenario:
- **engine/strategic.py StrategicGame** — submit() is the only door; player-turn
  alternation Axis-first (3.1-3.5); per-unit once-per-turn (5.2/5.5); destination
  legality via the validated movement engine; end_phase blocked while overstacked
  (2.3/6.1/6.3); every proposal (incl. rejections) logged to JSONL with state hashes.
- **scenario_campaign.json** (make_scenario.py, assertion-guarded): 23 deployed
  units (12 Allied / 11 Axis incl. the El Agheila stack) = the March 1941 Situation
  placement (2.3); 102 reserve pieces on the printed OOA track (2.2) are
  gate-rejected; 38 half-month turns 1 Apr 1941 - 15 Oct 1942.
- **verify_game.py** dispatches on log mode; validate_gate.py = 18/18 replay with
  9 illegal proposals provably inert. ui/server.py hard-rejects over HTTP
  (/api/move, /api/end_phase) with cited reasons; index.html shows flow banner +
  gate toasts. Confirmed in-browser (drag-move through gate, overstack rejection).

**Engine additions this pass (spec-gated, legacy SHA-identical):** enemy_hex
pass_classes (5.4: combat blocks on-top/through; lone supply/Rommel enterable,
22.3/15.22) replacing the wrong blanket enter_enemy_hex:true; stacking max 3
combat at end-of-move, exempt classes above the limit (6.1-6.3). validate_movement
36/36 (24 original + 12 new cited cases).

**TERRAIN DEFECT FOUND+FIXED:** printed decorations (Turn Record strip, CRT,
holding boxes, legend art incl. printed counter pictures) classified as clear —
156 hexes flipped to offmap by decoration color masks + sea/decor combination
rule. All 38 art checks still pass, 99 road hexsides intact, plus NEW module-zone
cross-check: every enterable hex inside the buildFile "Hexes" polygon and outside
all decoration zones (exceptions T57/W61: qattara_partial per printed art, 5.6 —
the module's Unplayable trail-zone is coarser than the rules).

**HONESTY LINE — what Tier 1 does NOT yet cover (declared in rules_scope, UI-visible):**
reinforcement/supply arrivals (3.1/3.3, 12, 19 — OOA data transcribed, needs
Time-Record validation), Rommel two-hex companion bonus (22.1 — ambiguous text,
no worked example found; do NOT encode a guess), sea movement (23.3-23.44 —
crisp text, needs port-control + off-board state), replacements/substitutes
(20/21), all combat (Tier 2). The gate is intentionally STRICTER than the full
rules on arrivals/22.1/23.4: banner + scenario declare it. Bruce decides whether
scoped Tier 1 is claimable or whether 22.1+23.4+arrivals must land first.
Web build (web/) still runs the legacy JS engine — AK gate is Python/HTTP only.

## SUPERSEDED: movement rules (Tier 1 gate)
1. Read rules sections: movement (5), stacking (6), supply-for-movement,
   coast road (10?), escarpment, Qattara — encode MFs + terrain with
   citations into game.json.
2. Terrain classification from map art (escarpment brown splash, coast road
   red line, sea, fortress, home bases) — validate on rulebook examples
   (G24 escarpment, T29 NOT a pass, R60 Qattara, K61 coast road).
3. Movement gate + regressions (Arnhem SHA baseline, Tobruk byte-identical,
   ASL board 3, verify_game on existing logs).
4. AK has a SUPPLY subsystem (sunk convoys etc.) — read before claiming
   Tier-2 scope; may cap the tier or need engine expansion.

## CRT (Tier 2, later)
The full CRT is printed on the map image (center-top) AND in the rulebook
text — transcribe from text, cross-check against the map image, validate
resolution against the rulebook's worked combat examples (H25/H26/I26...).
Classic AH odds-ratio CRT with A elim / A back 2 / Exchange / D back 2 /
D elim and soak-off rules.

## TERRAIN: VERIFIED 2026-07-09 (re-run `python build_terrain.py` — 38/38 PASS)
Full-map classification from the module map art (posterized colors make it
crisp): 1071 clear / 266 sea / 138 offmap (partial + non-coordinate incl.
W70/X70 per 5.8) / 133 escarpment / 35 partial-Qattara (play clear, 5.6) /
33 full-Qattara (impassable) / fortresses H2+G25 / home bases W3+J62.
Hexsides: 99 coast-road crossings (17.2 red-line test, "Afrika Korps" red
title text excluded), 30 all-water prohibitions (5.7), 25 Qattara
prohibitions (5.7) found by center-to-center connectivity severing against
the flood-filled depression — W62-X62 severed exactly as 5.7 says, W62-X63
crossable (boundary hook tip ends inside X63). Validated on every rulebook
terrain/hexside example incl. the full rule-17/18 road/non-road hexside
table. game.json now carries terrain_file + prohibit rules with citations.

## MOVEMENT RULES — extracted with citations (encoding next)
- 5.2 MF = hexes moved, any direction; 5.5 no transfer/accumulation
- 5.4/8.1/8.3: stop on entering enemy ZOC; never through ZOC; no
  ZOC-to-same-unit's-ZOC first step; supply/Rommel are not combat units
- 6.1-6.3 stacking 3 combat units, check at end of movement; stack moves
  at slowest MF
- 17.1-17.2 coast road: +10 bonus hexes/turn, only through road-bisected
  hexsides, freely combinable with normal movement; 17.3 I26 two-road hex
- 18.1-18.5 escarpment: enter=stop, 1 hex/turn through, EXCEPT along road
  hexsides; one non-road on/off move per turn (worked examples encoded in
  validate_grid.py chains)
- ENGINE GAP for Tier 1: per-terrain stop-on-enter, road bonus budget
  (2D state Dijkstra), per-enemy-unit ZOC first-step rule. Unit MFs blocked
  on counter transcription (mastermind OCR job 1).
