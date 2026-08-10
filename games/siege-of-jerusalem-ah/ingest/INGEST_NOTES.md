# Siege of Jerusalem (AH 1989) — ingest working notes
**Status: INGEST IN PROGRESS (2026-08-07). No game.json yet — do not expect this dir to load.**

**AMENDED 2026-08-09 (A3+A4 code phase):** Gallus Built-up = **92** (42 flips applied per
`builtup_evidence.json` — the file is FROZEN as the pre-fix audit, do not regenerate; see
`build_builtup_verdicts.py` docstring). Battlefield hard-bounded: `southern_bound` diagonals in
scenario_gallus.json (cols A–O ≤ printed 50 anchored at O50; QQ–XX ≤ 32 at the QQ31/QQ32
junction) + Elevated hexes playable only where they border battlefield ground — playable
1925→1341, Old City fully off-battlefield. Side-finds: **V42 is a Second-Wall corner gate**
(overlay: Fort class, entrances U42+W41), encoded; **SS18/SS20/VV15** are the only flagged art
hexes inside the bound — adjudicated CLEAR (Kidron valley slope shading / printed "Valley of
Kidron" label; crops in `C:\VassalSoJ\desktop_packs\SoJ_A4\`). Regression:
`validate_deploy.py::bound_and_builtup_checks` + `validate_combat.py::gate_ring_checks`.
Target: introductory scenario "The Assault of Gallus 66 AD" first (Tier ladder from there).
Module: SOJ 3_0_0.vmod (Rob McRae / clanmacrae9, GitHub issue #2 funnel ticket), extracted at
`C:\VassalSoJ\extracted\`. Rules transcription (full, Gallus scope):
`literature/siege-of-jerusalem/RULES_TRANSCRIPTION.md` (gitignored, local).

## Grid — SOLVED + VALIDATED
Letter+number printed scheme (rulebook cites e.g. R51, W36 Damascus Gate, P51 Yafo Gate):
letters = columns (A..Z, AA.. doubled), numbers along diagonals [rule 2.14].
- Fit (from 3,096 named regions in module v2.3 RegionGrid; 3,071 inliers < 10 px):
  `x = 71.0749*L + 207.60 ; y = 82.2902*(N + L/2) - 1840.52`  (L: A=1..Z=26, AA=27..)
- Flat-top hexes, column-staggered; axial coords: (L,N) neighbors (L±1,N),(L,N±1),(L+1,N-1),(L-1,N+1).
- Engine mapping: col=L, row=N+floor(L/2), stagger odd cols +dy/2, odd_row_carry=0.
  NEEDS new naming style in gamespec.Grid: "colletter_diag": N = row - col//2.
- Validated: Damascus Gate W36, Yafo P51, Psephinus G39, ~40 named landmark markers in the
  Gallus .vsav all compute to their own hex (0-7 px). v3.0 numbered grid = same geometry
  (dx 71.0256/dy 82.3/x0 -4/y0 -70), numeric col = L+3.

## Terrain — PASS 2 DONE (auto), precision pass PENDING
`ingest/terrain_pass2.json`: 3,125 hexes {cls, ring{red,orange,blue}, gray, dark, rmg, v}.
Classes: clear / slope / builtup / edifice / bastion(blue ring) / fort(orange) / fortress+gate(red).
Calibration: clear v~130 sat 75-85; slope v<122 & r-g>38; builtup gray>=0.35; edifice +v<108.
`ingest/wall_candidates.json`: 214 wall-band hexes (gray band, sat<45, 100<v<195, frac>0.13).
Known misses fixed by eye: G41 (wall), X24 n/a (wall goes X25->Y24), GG17 = FORT (ring 0.076
under threshold; save's own GG17 marker dead-center on the fort art).

### North Wall (Agrippa's) arc — TRACED (Gallus battlefield; breach defense 6, North Wall missile row)
West leg (south->north): O50(fort) N50 M50(bastion) L50(bastion) K50 J50 I50 I49 I48 H48 H47
  G48 G47 G46 G45 G44 G43(fort) G42 G41 G40(fort) G39(FORTRESS, Psephinus Tower)
North leg (west->east): H39 I38 J37 K37 L37 M36(bastion) N35 O34 P33(bastion) P34(bastion?
  verify pair) Q32 R31 S30(bastion) T29 U28 V27(bastion) W26 X25 Y24(bastion)
  **Z23 = WOMEN'S GATE (red)** AA22(bastion) BB21 CC20 DD19(fort) EE19 FF18 GG17(fort)
  HH16/HH17 II15/II16/II17(bastion at II15? verify alignment) JJ17 KK17 LL17 MM17 NN17 OO17
  PP17(landmark tower/fort — verify)
East leg (north->south): PP18..PP25 QQ22 QQ23 QQ25(landmark) QQ26 QQ27 QQ28 QQ29(bastion)
  QQ30 QQ31(= card's east end). Junction strongpoints beyond scenario bounds: P50(fort, west)
  QQ32(fort, east) — card: "Romans may never enter P50 or QQ32" = garrison-area junctions.
Scenario minimum-force rule covers "each Bastion and Fortress of the North Wall O50..QQ29".

### Second Wall (inner arc = New City south boundary) — approx trace, VERIFY hex-by-hex
Q49(bastion, WEST REINFORCEMENT GATE) R49(fort) R48? R47? R46(bastion) R45(bastion) then NE:
S45? T44? U43? V42(fort) V41? V40(bastion) V39(bastion) V38 W37(fortress) **W36 = DAMASCUS
GATE (red)** X36(fortress) Y35? Z34(bastion) Z33(bastion) AA32? BB31? CC30(bastion) DD29?
EE28? FF28(bastion) GG28(bastion) HH27? II27(bastion) JJ27(bastion) KK27? LL27(bastion)
LL28(bastion) MM27(bastion) then SE down to: NN29? MM30(bastion) ... OO33 (**TADI GATE, EAST
REINFORCEMENT GATE**) OO34(fortress) PP33(fortress) joining east junction at QQ32/RR31/RR32.
NOTE second wall belongs to the battlefield boundary; Antonia complex (II33-JJ36 fortresses,
KK35/KK36 forts) + Temple north wall (MM30-33/NN31-33) lie beyond it (out of Gallus play).

### New City (deployment area) = crescent between the two arcs
Pass-2 candidates inside crescent: builtup x23: Q44 S37 V38 W29 W32 X28 X35 Y26 Y27 Y31 Y34
Z26 Z28 Z29 Z30 AA26 AA28 AA29 BB24 DD23 JJ22 JJ23 MM20; edifice x13: R37 S35 S36 T35 X31
Y30 AA25 CC23 EE20 KK20 MM21 NN20 OO28. (Edifice-vs-builtup split needs the visual pass —
edifice = dark-gray background hex.) Everything else in crescent: clear (+ some slope at edges).

## Remaining ingest work (next session)
1. PRECISION PASS on crescent + arcs: verify every wall/bastion/fort/gate hex + builtup/edifice
   split visually (zoom crops); resolve P33/P34 pair, II15-17 alignment, PP17/QQ25 types;
   staircase hexsides (visible marks on wall inner faces, e.g. Y24/AA22 flanks of Women's Gate);
   entrance hexsides at gates (brown rut marks [8.91]); roads INSIDE New City (outside = destroyed
   [8.94]); crest hexsides on approach (mostly clear plain — verify NE Kidron edge SS/TT cols).
2. game.json: grid + naming style (add "colletter_diag" to gamespec, validate vs 3071 regions),
   sides Romans/Judaeans, unit stats (2.41-2.46 transcribed), terrain MP table (TEC transcribed),
   Melee Table + Missile Table + Breach Table + Weapons Effect + LOF + Rally (all transcribed,
   game-card image legible), credits (printed p.15 + module credits), source_defects (4 known:
   QQ32 errata 2.15 [module art already applies it]; Q&A 7.311 rout-from-Heavy-ZOC — RETRACTED
   2026-08-09: decode-prep 6 re-read both scans, BOTH documents answer "No" (the contradiction
   claim was our transcription error); registered instead as citation mismatch 17.23-vs-17.3,
   ruling enforced unchanged; General 26-4
   interphase sequence wrong per Greenwood-reviewed aid [campaign scope, register on later
   touch]; card reinforcement "rolls the dice" 1d-vs-2d ambiguity — no official ruling found,
   resolution TBD [module behavior/Rob as expert review]).
3. Scenario spec: OOB decoded from module .vsav = EXACT match to printed card (79 Judaean +
   63 Roman + turn marker). Free deployment => gate-validated deployment phase: Judaeans first,
   in crescent (on/within outer walls), minimum-force strongpoints O50-QQ29; Giora faction
   (ben Giora + 9 Regulars + 14 Militia) + 2 Zealots held off-board as South Wall garrison,
   dice-rolled entry from turn 4 at OO33 (odd) / Q49 (even), blocked -> other gate; Romans
   second, anywhere outside city >= 5 hexes from any Elevated hex; Roman Fire Phase opens turn 1.
   Victory: Romans control 10 Built-up hexes at end of any Judaean Melee Phase; 10 turns;
   turns 8-10 night (card track shading; "only the first seven may be day turns").
4. Engine family: sequence Rally/Fire/Move/Melee per side (non-phasing fires first in Fire
   Phase), CC (HQ range 10), ZOC (ground/gate/elevated + hard/soft), disruption ladder
   Fresh->Disrupted->Routed->Panicked, rally table + drm, melee odds CRT + drm + continuous
   combat + advance, missile AF->multiple->result, breach damage accumulation, siege engines
   (Tower/Ram/Armored Tower + facing), escalade, testudo, cauldron rocks, retreat-toward-Refuge.
   SCOPE CALL (surface to Bruce): Refuge = Temple Quarter is off-battlefield; proposal = routed
   units exiting the bounded area via the south gates are removed from play (scenario's own
   "played only on the North Wall" bound); flag in validation worksheet for Rob's expert review.
5. Open module bugs for Rob's worksheet: "P51" Yafo Gate name-marker physically placed in P55;
   v2.3 region typos (GG671, NN112, P53@wrong, C44, V68, + ~20 more, list in fit script output).
