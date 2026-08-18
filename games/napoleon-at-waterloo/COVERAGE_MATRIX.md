# COVERAGE MATRIX — Napoleon at Waterloo, SECOND EDITION (SPI, 1971)

**The instrument defined by PLATFORM_SPEC #13 (amended 2026-08-09): this matrix IS the playability
rating.** The game is **playable** exactly when every row below is `ENFORCED` or `UNREACHABLE`.
There is no third acceptable state; an `OPEN` row is a named defect that blocks playability, and
nothing may be left to a human umpire — *"umpired" is a failure point, not a disclosure*
(Bruce 2026-08-08). Internal report — builder + testers, never player-facing.

**This is the SKELETON.** Nothing is encoded: there is no engine code, no validator and no
`game.json` for this game. Every cell that is not evidenced-unreachable therefore starts `OPEN`.
The matrix's job right now is to enumerate **exhaustively what must be closed**, so the encoder
can work down it and so nothing is silently skipped.

Scope: **2nd Edition only**, and the 2nd Edition prints exactly one game — ten Game-Turns
(1 pm .. 10 pm), one at-start setup read off the map art, one reinforcement event. The
per-scenario scope of this file is therefore the whole edition. **No 3rd Edition rule, and no
module redraw, may ever be used to fill a gap here** (authority_ladder: a non-primary asset may
be cited only for a claim a primary witness independently covers).

**Status values**

| status | meaning | must carry |
|---|---|---|
| `ENFORCED` | the gate checks it | code location + the validator that proves it against a printed table or worked example |
| `UNREACHABLE` | cannot arise in this game | the evidence |
| `OPEN` | reachable, not (fully) enforced | the work that closes it |

**Discipline observed in building this file**

- ENFORCED cells carry the code location and the validator line that proves them (ENFORCED overlay in naw_coverage_matrix.py); the overlay grows one bite at a time
- an UNREACHABLE claim with no evidence is exactly the silent gap this standard exists to prevent, so unreachability is claimed only from printed rules that close their own state space or from enumerated printed components
- where enforceability is uncertain the cell says so rather than choosing the optimistic answer - an over-optimistic call becomes a silent incorrectness, the worst failure class in this project

Every cell traces to one or more rule ids in `ingest/rules_2nd_ed.json`. Machine-verified
coverage of that index is reported in §8; the file that generates this document and its JSON
twin is `ingest/naw_coverage_matrix.py`.

---

## §1 PHASE SPINE

2nd Edition turn structure (SEQ-02/03/04): **French Movement → French Combat → Allied Movement →
Allied Combat → advance the Time Record**, ten times. Setup is one-off and is not a phase
(SET-04). Zones of Control, victory and demoralization are **continuous** — they are read and
written inside other phases, so they carry their own sections rather than sitting in one.

### P0 — SETUP

*one-off, before Game-Turn 1; not a phase; p.1 col.3 SETTING UP THE GAME; SET-04*

| cell | rules | requirement | status |
|---|---|---|---|
| **S.1** | `SET-01`, `SET-03`, `PCS-06` | at-start placement is read off the printed map art: a setup is legal iff every printed position holds a unit of the printed strength AND type; historical designation is free <br>**data:** ingest/oob_2nd_ed.json (44 at-start units, hex/side/factors/type, three independent witnesses, module_factor_disagreements = 0) <br>**evidence:** scenario_2nd_ed.json units (44) built by build_data.py from oob_2nd_ed.json; engine/naw.py new_game \|\| games/napoleon-at-waterloo/validate_data.py: at-start roster (hex, side, CS, MA, type, designation) == oob 44/44; no two units share a hex; strengths 89/73/34 <br>*note:* the data exists and is triple-witnessed; what is missing is the encoding and a validator asserting all 44 printed positions | `ENFORCED` |
| **S.2** | `SET-01`, `PCS-05` | side is decided by the printed Front Line: North of it Allied, South of it French; French = blue, Allied = red (British) + green (Prussian) <br>**data:** ingest/oob_2nd_ed.json side field, 44/44 agreement with the module save <br>**evidence:** scenario units carry side Fr/Al; game.json sides.detect_tokens \|\| games/napoleon-at-waterloo/validate_data.py: every counter image resolves to its printed side; 26 French / 18 British at start | `ENFORCED` |
| **S.3** | `SET-02`, `REI-01` | "Place the Prussian units on the East side" - staging of the nine Prussian counters before play <br>**HARD.** AMBIGUOUS AS PRINTED. Off-map staging vs literal on-map East-edge placement. The literal reading contradicts REI-01 (Prussians ENTER at the start of the Allied player-turn of Game-Turn 2) and would put nine units on the map from Game-Turn 1. Not enforceable until a ruling picks a reading. <br>**evidence:** engine/naw.py: the nine Prussians are an OFF-MAP reserve pool due Game-Turn 2 (SPI 1979 7.0: reinforcements ENTER during a Movement Phase - NAW2-OR-1 A) \|\| games/napoleon-at-waterloo/validate_victory.py: nine Prussians staged OFF the map, due Game-Turn 2 <br>*note:* the engine stages the Prussians OFF-MAP (reserve pool, due Game-Turn 2) - the reading consistent with REI-01; NAW2-OR-1 stays open <br>*source:* rules_2nd_ed.json unenforceable_as_written (SET-02); printed_defect_candidates kind=ambiguity <br>*open ruling:* `NAW2-OR-1` | `ENFORCED` |
| **S.4** | `SET-04`, `SEQ-04` | placement is not a turn or a phase; the game opens with the French Player's first Movement Phase <br>**evidence:** engine/naw.py new_game: turn 1, French mover, Movement Phase; no setup phase exists \|\| validate_movement.py: game opens with the French Movement Phase of Game-Turn 1 | `ENFORCED` |
| **S.5** | `SET-03` | "Players set up their units simultaneously" <br>**evidence:** scenario_2nd_ed.json fixes both sides' setup at once; no setup action exists in the gate (simultaneity is trivial) \|\| validate_data.py: at-start roster 44/44 <br>*note:* both setups are fully printed on the map art, so neither side learns anything from the other's placement and simultaneity has no informational content. That argument must be WRITTEN DOWN and asserted by a validator, not assumed - a phased setup that admits any deviation from the printed positions would make simultaneity load-bearing again | `ENFORCED` |
| **S.6** | `PCS-01`, `PCS-02`, `PCS-03`, `PCS-04`, `PCS-07` | a unit carries exactly three game-relevant attributes: Combat Strength (one number, attack and defence alike), Movement Allowance (a hex count), type in {infantry, cavalry, artillery} <br>**evidence:** scenario units carry cls + stats{att,def,ma}; nothing else is read by any verdict \|\| validate_data.py: Combat Strength serves attack and defence alike; classes partition every piece <br>*note:* NO printed rule in the 127-row index keys on infantry-vs-cavalry. Only artillery carries type-specific rules (ART-01..ART-18). An encoder must model the type field but must NOT invent a cavalry behaviour; a validator should assert that no verdict path branches on infantry vs cavalry | `ENFORCED` |
| **S.7** | `MAP-01` | position and movement are expressed on the hex grid; 27 columns x 22 rows = 594 hexes, six-way adjacency <br>**data:** ingest/hexgraph_2nd_ed.json (594 hexes, 0 mutual-adjacency violations, parity proven against two independently fitted pixel grids) <br>**evidence:** terrain.json 594 hexes; gamespec grid adjacency == the proved hexgraph \|\| validate_data.py: engine adjacency == PROVED hexgraph 594/594 <br>*note:* the 2nd Edition puts ODD columns half a hex LOWER - the OPPOSITE parity to the 3rd Edition. A shared hex-id helper across editions would silently mis-stagger one of them | `ENFORCED` |
| **S.8** | `MAP-02`, `MAP-03`, `MAP-04`, `MAP-05`, `TEC-01` | terrain vocabulary is exactly {Wood, Town, Road}; a hex is that terrain if ANY part of it carries the symbol; no other map feature may carry a rule <br>**data:** ingest/hexgraph_2nd_ed.json terrain_counts: clear 503, town 30, woods 56, woods_road 5 <br>**evidence:** terrain.json kinds {clear, town, woods, woods_road}; hexside features road/woods_edge; nothing else carries a rule \|\| validate_data.py: terrain counts 503/30/56/5; sides = exactly the Woods/Road hexsides <br>*note:* the TEC's own footnote states the any-part rule for Woods a second time. map_grid.json rejected three woods_road candidates (1918, 2401, 2604) - the accept/reject boundary is a validator case | `ENFORCED` |
| **S.9** | `SCA-01`, `SCA-02`, `SCA-03` | scale: one turn = one hour, one hex = 400 m, one counter = one division <br>**evidence:** scenario turn_labels 1 pm..10 pm; scale is descriptive only (no rule keys on it) \|\| validate_data.py: turn labels = the printed Time Record <br>*note:* no gate obligation beyond the turn count (T.1) and the display; recorded so the spine is complete | `ENFORCED` |

### T — TURN STRUCTURE (the spine itself)

*every Game-Turn; p.1 col.3 TURNS OF PLAY*

| cell | rules | requirement | status |
|---|---|---|---|
| **T.1** | `SEQ-01`, `SEQ-05`, `SEQ-04` | exactly ten Game-Turns (1 pm .. 10 pm); step 5 of each turn advances the Time Record; the game ends on a victory condition or at the end of Game-Turn 10, whichever comes first <br>**data:** ingest/timerecord_oob.json time_record: 10 slots, read individually <br>**evidence:** engine/naw.py _end_player_turn/_game_end: 10 Game-Turns then over (victory-halt = T.6, bite 6) \|\| games/napoleon-at-waterloo/validate_movement.py: ten Game-Turns then the game ends; no action after | `ENFORCED` |
| **T.2** | `SEQ-02`, `SEQ-03`, `SEQ-04` | Game-Turn = French Player-Turn then Allied Player-Turn; each Player-Turn = Movement Phase then Combat Phase; the printed five-step order <br>**evidence:** engine/naw.py propose/end_movement/end_phase: French then Allied, Movement then Combat \|\| games/napoleon-at-waterloo/validate_movement.py: turn structure block | `ENFORCED` |
| **T.3** | `SEQ-06`, `MOV-04` | no combat of any kind during a Movement Phase - an attack submission in a movement phase is refused | `OPEN` |
| **T.4** | `SEQ-07` | no movement during a Combat Phase except as directed by the CRT: the only position changes are retreat, disruption displacement and advance <br>*note:* the advance (X.15) is OPTIONAL, not directed. Whether an optional advance falls inside SEQ-07's 'except as directed by the Combat Resolution Table' carve-out is the hinge of N7 \|\| movement refusal in the Combat Phase is enforced (validate_movement: movement refused in the Combat Phase [SEQ-07]); the retreat/disruption/advance half lands with bite 5 | `OPEN` |
| **T.5** | `SEQ-08`, `MOV-03`, `ART-15` | no non-phasing action of any kind: no enemy movement during friendly movement, no reaction, no defensive fire, no defensive use of artillery range <br>*note:* this is the rule the advance-after-Ar case collides with - see N7 \|\| non-phasing movement is refused (validate_movement: Allied move during the French Player-Turn refused [SEQ-08]); the combat-side clauses land with bites 3-5 | `OPEN` |
| **T.6** | `VIC-07` | the game halts the INSTANT a victory condition is met, mid-phase if necessary <br>**evidence:** engine/naw.py _check_victory runs after every elimination and every exit and sets over/winner at once \|\| games/napoleon-at-waterloo/validate_victory.py: Allied win immediately on the fortieth French point; French win the instant the seventh exit follows demoralization <br>*note:* combined with CBT-04 (results applied immediately, one attack at a time) the check runs between two attacks of the same combat phase | `ENFORCED` |

### P1/P3 — MOVEMENT PHASE (French / Allied)

*step 1 and step 3 of every Game-Turn; p.1 col.4 MOVEMENT*

| cell | rules | requirement | status |
|---|---|---|---|
| **M.1** | `MOV-01`, `MOV-14` | movement is never compulsory and never directionally constrained; a player may move none, some or all of his units <br>**evidence:** engine/naw.py: no obligation to move; end_movement legal with unmoved units \|\| games/napoleon-at-waterloo/validate_movement.py: random walk ends phases with unmoved units; end_movement always legal | `ENFORCED` |
| **M.2** | `MOV-02`, `MOV-05`, `MOV-15`, `MOV-20`, `PCS-03` | flat 1 MP per hex entered in every terrain; hexes entered this Player-Turn <= printed Movement Allowance; unspent points are lost; no pooling between units, no carry-over between turns <br>**evidence:** engine/naw.py dests(): 1 MP per hex (gamespec.move_cost, TEC costs), MA cap, per-Player-Turn reset \|\| games/napoleon-at-waterloo/validate_movement.py: open field costs == hex distance, none beyond MA; gate == independent hexgraph oracle on >1500 positions <br>*note:* the TEC agrees: every enterable terrain costs exactly one MP per hex, and the road itself costs nothing and grants nothing (combat_charts O6). An engine that builds its movement predicate from the TEC alone will miss MOV-17 | `ENFORCED` |
| **M.3** | `MOV-06` | a move is a path of consecutively adjacent hexes; no hex may be skipped <br>**evidence:** engine/naw.py dests(): Dijkstra over adjacent hexes only \|\| games/napoleon-at-waterloo/validate_movement.py: oracle BFS agreement | `ENFORCED` |
| **M.4** | `MOV-07` | friendly-occupied hexes may be moved THROUGH <br>**evidence:** engine/naw.py dests(): friendly hexes traversable \|\| games/napoleon-at-waterloo/validate_movement.py: moves THROUGH the friendly hex | `ENFORCED` |
| **M.5** | `MOV-08` | enemy-occupied hexes may be neither entered nor passed through <br>**evidence:** engine/naw.py dests(): enemy hexes never entered or traversed \|\| games/napoleon-at-waterloo/validate_movement.py: enemy-occupied hex never entered | `ENFORCED` |
| **M.6** | `MOV-09`, `MOV-07` | one unit per hex <br>**HARD.** TWO PRINTED SENTENCES, TWO SCOPES. Sentence 1 bars finishing the MOVEMENT PHASE stacked; sentence 2 says 'Players may NOT place more than one unit in a given hex' with no time qualifier. Under reading A a unit may end its own move stacked with a friend and be moved off later in the same phase; under reading B it may not. MOV-07 grants pass-through, which reading B makes the only legal co-occupancy. Different legal move sets. Not on any prior list - see N1 <br>**evidence:** engine/naw.py dests(): friendly-occupied destinations excluded (reading B - one unit per hex at all times); NAW2-OR-2 stays open, reading A is a one-line switch \|\| games/napoleon-at-waterloo/validate_movement.py: may not end the move on a friendly unit; gate refuses with MOV-09 <br>*open ruling:* `NAW2-OR-2` | `ENFORCED` |
| **M.7** | `MOV-10`, `ZOC-04` | a unit entering any hex in an enemy Zone of Control MUST STOP there; entering is legal, continuing is not <br>**evidence:** engine/naw.py dests(): a hex in enemy ZOC is a terminal destination \|\| games/napoleon-at-waterloo/validate_movement.py: may move INTO the enemy ZOC / must STOP on entering it | `ENFORCED` |
| **M.8** | `MOV-11`, `ZOC-04` | no unit may travel THROUGH an enemy-controlled hex <br>**evidence:** engine/naw.py dests(): no expansion from an EZOC hex \|\| games/napoleon-at-waterloo/validate_movement.py: hexes beyond the ZOC ring unreachable through it | `ENFORCED` |
| **M.9** | `MOV-11`, `MOV-12`, `ZOC-05`, `ZOC-08` | a unit in an enemy-controlled hex may not leave it by movement; the lock releases on exactly three events - the exerting enemy destroyed, the exerting enemy retreated, or the unit itself forced to retreat by combat <br>**evidence:** engine/naw.py in_ezoc(): a unit in enemy ZOC has no destinations; the lock is a live read of enemy positions so it releases exactly when the exerting enemy is gone (combat removal = bite 5) \|\| games/napoleon-at-waterloo/validate_movement.py: unit adjacent to an enemy may not move at all | `ENFORCED` |
| **M.10** | `MOV-13` | a unit that BEGINS its Movement Phase in an enemy ZOC may not move at all that phase <br>**evidence:** engine/naw.py in_ezoc() at proposal time (only the phasing player moves, so live == phase-start) \|\| games/napoleon-at-waterloo/validate_movement.py: MOV-13 refusal with citation <br>*note:* phase-start snapshot, not a live read. A unit that becomes ZOC-free mid-phase (impossible by movement alone, since only the phasing player moves) is still frozen; a unit whose enemy died in the previous combat phase is free | `ENFORCED` |
| **M.11** | `MOV-16`, `MOV-18`, `TEC-01` | Woods entry is PROHIBITED; the only Woods hexes any unit may enter are those traversed by a Road <br>**data:** ingest/hexgraph_2nd_ed.json: 56 woods, 5 woods_road <br>**evidence:** terrain.json woods = 99 MP (never affordable) + gate reads terrain; MOV-18 \|\| games/napoleon-at-waterloo/validate_movement.py: no Woods hex is ever a destination | `ENFORCED` |
| **M.12** | `MOV-17` | a Woods/Road hex must be ENTERED and EXITED along the road: both hexsides used must be road hexsides <br>**data:** ingest/hexgraph_2nd_ed.json road_sides on the 5 woods_road hexes: 1014 [NW], 1101 [N,S], 1603 [NE,SW], 1701 [NE,S], 1702 [N,SW] <br>**HARD.** DATA VERIFICATION REQUIRED BEFORE ENCODING. Hex 1014 carries exactly ONE road hexside, which makes it a cul-de-sac under MOV-17: the only legal exit is back through the entry side. Either the printed road genuinely dead-ends there or the road_sides extraction is incomplete for that hex. Must be re-read off the print before this cell can close - see N2 <br>**evidence:** terrain.json sides: road / woods_edge on the 5 Woods/Road hexes; gamespec.move_cost prohibit; N2 CLOSED 2026-08-17 - hex 1014 is a genuine printed cul-de-sac (road ends at Hougoumont), verified on Oliver's map scan \|\| games/napoleon-at-waterloo/validate_movement.py: 1014 only via 0913; 1503-1603-1702-1701-1801 = 1,2,3,4 MP; 1101 only from 1102 | `ENFORCED` |
| **M.13** | `MOV-19`, `MOV-01` | "Once a unit has been moved, and the Player's hand is taken from the piece, it may not be moved any further during that Player-Turn, not may it change its move without the consent of the opposing Player." <br>**HARD.** PLATFORM-LEVEL QUESTION, NOT A GAME-LEVEL ONE. The trigger is physical (a hand leaving a piece) and the escape is social (opponent's consent); no gate can evaluate either from game state. Its subject matter is exactly what the platform's UNDO feature does - an undo IS 'changing a move'. That makes MOV-19 a question about the ENGINE's shipped feature set across ALL games, not a NAW encoding detail: either UNDO is a platform affordance that stands outside the printed rules (and is declared as such), or it is gated on an opponent-consent step. Bruce's call. Escalate before Fable touches undo semantics anywhere <br>*note:* the first clause IS enforced: once moved, a unit may not be moved again that Player-Turn (validate_movement: MOV-19 refusal); the consent-to-change clause remains the platform UNDO question <br>*source:* rules_2nd_ed.json unenforceable_as_written (MOV-19); the row is absent from RULEBOOK_VERIFIED entirely <br>*open ruling:* `NAW2-OR-3` | `OPEN` |
| **M.14** | `MOV-01`, `MOV-19` | there is NO one-mover-at-a-time finality rule in this edition beyond MOV-19 <br>**evidence:** engine/naw.py: no finality rule beyond MOV-19; any order, interleaving allowed \|\| games/napoleon-at-waterloo/validate_movement.py: random walk interleaves units freely <br>*note:* recorded as an explicit ABSENCE so no one imports Siege of Jerusalem's 8.2 by habit. Units may be moved in any order and a player may interleave partial moves, subject only to MOV-19 and to M.6's unresolved reading. If M.6 resolves to reading B, interleaving is constrained by stacking rather than by any movement-finality rule | `ENFORCED` |

### P3r — REINFORCEMENT (Prussian entry - a sub-step of the Allied Movement Phase, Game-Turn 2)

*beginning of the Allied Player-Turn of Game-Turn 2, once only; p.1 col.3/col.4 SETTING UP THE GAME case (B.); printed Time Record 2 pm slot*

| cell | rules | requirement | status |
|---|---|---|---|
| **R.1** | `REI-01`, `SEQ-02` | the nine Prussian units enter at the beginning of the Allied Player-Turn of Game-Turn 2 <br>**data:** ingest/timerecord_oob.json: all nine units printed in the single 2 pm slot; no other slot carries a unit; ingest/oob_2nd_ed.json reinforcements (9 units, 34 CSP) <br>**evidence:** engine/naw.py _propose_reinforce: pool due Game-Turn 2, Allied Movement Phase only, refused before \|\| games/napoleon-at-waterloo/validate_victory.py: Game-Turn 1 refused [REI-01]; Game-Turn 2 accepted <br>*note:* exactly ONE reinforcement event exists in this edition - see the unreachable register for the staggered-arrival and 3 pm entry claims | `ENFORCED` |
| **R.2** | `REI-02` | entry anywhere along the East edge, at as many different points as desired <br>**HARD.** DATA GAP. hexgraph_2nd_ed.json flags the NORTH-edge exit hexes but carries no East-edge flag. The East-edge hex set must be derived from the grid extent (column 27) and CONFIRMED against the printed map before this cell can close; the jagged north and south edges make an off-by-one at the corners a live risk <br>**evidence:** engine/naw.py entry_hexes: column 27 = the East edge (all 22 hexes of the last column of the 594-hex graph; 4 are Woods), any number of entry points \|\| games/napoleon-at-waterloo/validate_victory.py: entry hexes = column 27 minus the 4 Woods hexes = 18; column 26 refused | `ENFORCED` |
| **R.3** | `REI-03`, `MOV-05` | the act of placing a Prussian unit on the map expends one Movement Point of that unit's allowance <br>**evidence:** engine/naw.py _apply reinforce: moved[pid] = 1 MP (game.json reinforcements.entry_cost_mp; NAW2-SD-1 'extends' = expends) \|\| games/napoleon-at-waterloo/validate_victory.py: Prussian enters at 2705 for 1 MP <br>*note:* printed 'extends'; registered as NAW2-SD-1, resolved on proven outcome-equivalence (the same page prints 'expends' for the mirror-image exit action). RULEBOOK_VERIFIED had silently normalised it - the normalisation, not the typo, is the lesson | `ENFORCED` |
| **R.4** | `REI-04` | Prussians may move and fight on their turn of entry like any other Allied unit; no arrival penalty beyond the 1 MP <br>**evidence:** engine/naw.py budget = MA - moved: an entered unit may still move MA-1 and fight (no done flag on entry) \|\| games/napoleon-at-waterloo/validate_victory.py: it may still move with MA-1 this turn | `ENFORCED` |
| **R.5** | `REI-06` | entry may not be deliberately delayed <br>**HARD.** UNDEFINED CASE. The print states no relief for a position where entry is physically impossible - every East-edge hex enemy-occupied (MOV-08 bars entry into them), or enough of them in enemy ZOC that arriving units must stop on arrival (MOV-10). A gate that enforces a non-delayable entry must decide what it does when the obligation cannot be met. Ranked MATERIAL in rules_2nd_ed.json printed_defect_candidates <br>**evidence:** engine/naw.py end_movement refused while any due unit has a legal entry hex; no legal hex -> the unit waits (NAW2-OR-4 A, logged) \|\| games/napoleon-at-waterloo/validate_victory.py: end_movement REFUSED while due Prussians can still enter; entry physically impossible -> accepted, Prussians wait <br>*open ruling:* `NAW2-OR-4` | `ENFORCED` |
| **R.6** | `REI-07`, `VIC-12` | Prussians may not leave the map once brought on; no Allied unit may ever exit <br>**evidence:** engine/naw.py _propose_exit: exit_side Fr only \|\| games/napoleon-at-waterloo/validate_victory.py: Prussians may never leave the map [REI-07/VIC-12] | `ENFORCED` |
| **R.7** | `REI-05`, `DEM-01`, `VIC-01` | Prussian losses count as Allied losses - ONE loss ledger for British + Prussian against the 40-point threshold <br>**evidence:** engine/naw.py _eliminate: losses[unit side]; Prussians carry side Al \|\| games/napoleon-at-waterloo/validate_victory.py: Prussian losses count as Allied losses | `ENFORCED` |

### Z — ZONES OF CONTROL (continuous, both players' turns)

*always; p.1 col.5 ZONES OF CONTROL*

| cell | rules | requirement | status |
|---|---|---|---|
| **Z.1** | `ZOC-01`, `ZOC-02` | every unit of every type controls the six hexes directly adjacent to it, at all times, whether or not it is that player's turn; there is no negated or inactive ZOC state <br>**evidence:** gamespec.zoc_hexes: every unit, all six neighbours, always \|\| games/napoleon-at-waterloo/validate_movement.py: an enemy unit controls exactly its six adjacent hexes | `ENFORCED` |
| **Z.2** | `ZOC-03` | friendly ZOCs never inhibit friendly units <br>**evidence:** engine/naw.py _board_sets: only enemy ZOC is computed \|\| games/napoleon-at-waterloo/validate_movement.py: friendly ZOC never inhibits friendly movement | `ENFORCED` |
| **Z.3** | `ZOC-06` | ZOC does not stack or intensify; more than one unit may control the same hex and the test is set membership <br>**evidence:** gamespec.zoc_hexes returns a set \|\| games/napoleon-at-waterloo/validate_movement.py: set membership (ZOC-06) | `ENFORCED` |
| **Z.4** | `ZOC-07` | the ZOC rule triggers on unit-to-unit adjacency, never on hex-to-hex ZOC overlap between non-adjacent opposing units <br>**evidence:** engine/naw.py in_ezoc(): tests the unit's own hex against enemy ZOC only \|\| games/napoleon-at-waterloo/validate_movement.py: ZOC tests are unit-hex membership <br>*note:* absent from RULEBOOK_VERIFIED's ZOC summary; carried here so it is not lost | `ENFORCED` |
| **Z.5** | `ZOC-01`, `MOV-16` | ZOC is projected into all six adjacent hexes with NO terrain exception - including non-Road Woods hexes that no unit could legally enter <br>**HARD.** NAMED TRAP. Enforceable exactly as written, but an encoder who 'reasonably' exempts impassable hexes is silently wrong, and the error is invisible in movement (nobody can enter those hexes anyway) while being decisive in RETREAT: X.4 bars retreating into an enemy ZOC, so a phantom-free woods hex would create retreat destinations the printed rules forbid. Flagged in rules_2nd_ed.json unenforceable_as_written <br>**evidence:** gamespec.zoc_hexes projects into every neighbour incl. Woods (no terrain exception) \|\| games/napoleon-at-waterloo/validate_movement.py: ZOC is projected into adjacent Woods hexes too | `ENFORCED` |
| **Z.6** | `ZOC-08`, `ZOC-05` | the lock is MUTUAL: neither of two adjacent opposing units may leave the other's presence until one is destroyed or retreated by combat <br>**evidence:** engine/naw.py in_ezoc(): symmetric by construction (adjacency) \|\| games/napoleon-at-waterloo/validate_movement.py: mutual lock - unit adjacent to enemy may not move | `ENFORCED` |

### P2/P4 — COMBAT PHASE - declaration and assignment

*step 2 and step 4 of every Game-Turn; p.1 col.5/col.6 COMBAT*

| cell | rules | requirement | status |
|---|---|---|---|
| **C.1** | `CBT-01`, `PCS-02` | one attack = the summed Combat Strength of the attacking unit(s) compared to the summed Combat Strength of the adjacent defending unit(s), stated as a ratio <br>**evidence:** engine/naw.py attack_strength/defense_strength/battle_check: summed strengths, ratio \|\| games/napoleon-at-waterloo/validate_combat.py: 27/27 printed examples through battle_check | `ENFORCED` |
| **C.2** | `CBT-02`, `CBT-EX-01`, `CRT-01` | the ratio is simplified to a printed column, ALWAYS rounded in favour of the defender; attacks worse than 1:5 are treated as 1:5 and better than 6:1 as 6:1 <br>**data:** ingest/crt_2nd_ed.json (10 columns, 6 rows, 60 cells, four independent readings, clamp footnote verbatim) <br>**evidence:** engine/naw.py odds_column: floor(a/d):1 else 1:ceil(d/a), clamped to the printed columns \|\| games/napoleon-at-waterloo/validate_combat.py: rounding pairs incl. EX-13 (2 vs 3 = 1:2), clamp 1 vs 40 = 1:5 / 30 vs 1 = 6:1, the 8-vs-3 rules example <br>*note:* the arithmetic expression that reproduces all 27 printed examples is OURS, not printed: floor(a/d):1 when a>=d, else 1:ceil(d/a). EX-13 (2 vs 3 -> 1:2) is the ONLY printed witness that the adverse side rounds by ceil rather than floor. A single witness - treat accordingly and write the validator against the whole 27-example corpus | `ENFORCED` |
| **C.3** | `CBT-03`, `CRT-01` | one six-sided die per attack, rolled by the attacking player, read against the odds column <br>*note:* engine-owned dice: seeded, logged, replayable (spec #11). No client-side rolls \|\| roll_die (gate.py) is seeded/counted/replayable (validate_combat: 300 rolls 1..6, same seed same rolls); the per-attack roll lands with the battle action (bite 5) | `OPEN` |
| **C.4** | `CBT-04` | the indicated action is taken IMMEDIATELY, and applied to the board, before any other attack in that Combat Phase is resolved | `OPEN` |
| **C.5** | `CBT-05`, `ART-01` | attacking units must be adjacent to the enemy unit attacked, during the attacker's own Combat Phase; the sole exception is artillery bombardment at exactly two hexes <br>*note:* predicate BUILT + validated (battle_check: adjacent legal, non-adjacent infantry refused, artillery at exactly two hexes) - flips to ENFORCED when the battle action makes battle_check the door (bite 5) | `OPEN` |
| **C.6** | `CBT-06`, `CBT-07`, `CBT-10` | EVERY enemy unit adjacent to any phasing unit must be attacked this phase; EVERY phasing unit adjacent to any enemy must participate in an attack this phase; no unit may appear in more than one attack, on either side <br>**HARD.** THE COMBAT PHASE IS A GLOBAL ASSIGNMENT PROBLEM, NOT A PER-ACTION CHECK. Taken together these three rules require a PARTITION of the contact graph: every adjacent enemy covered exactly once as a defender, every adjacent friendly used exactly once as an attacker, subject to the adjacency constraints of CBT-11 (all attackers adjacent to the defender) and CBT-12 (all defenders adjacent to the attacker). A gate that validates one attack at a time CANNOT enforce this: an individually legal first attack can strand a later unit with no legal partner, and the illegality only becomes visible at the end of the phase. Deciding legality means searching for a COMPLETE assignment before admitting the first attack. Worse, the sheet prints NO RELIEF CLAUSE for a position in which no complete assignment exists, and no tie-break for choosing among several. The engine must either solve the assignment (and refuse a first attack that provably strands the phase) or declare the position undefined - and 'declare undefined' is an umpire, which spec #13 forbids. The printed examples confirm the shape rather than relieving it: both partitions of the 16-unit battle line use all 9 attackers exactly once and cover all 7 defenders exactly once. ART-07 widens the search space rather than narrowing it: an artillery unit standing adjacent to an enemy may discharge its obligation by bombarding a DIFFERENT enemy two hexes away, provided some other friendly covers the adjacent one. This is the single largest engineering item in the encoding <br>*source:* rules_2nd_ed.json unenforceable_as_written (CBT-06 + CBT-07 + CBT-10) <br>*open ruling:* `NAW2-OR-5` | `OPEN` |
| **C.7** | `CBT-04`, `CBT-06`, `CBT-07` | when the mandatory-attack obligations are evaluated: at the start of the Combat Phase, or re-evaluated after every applied result <br>**HARD.** OPEN RULING, NOT A CODING CHOICE. CBT-04 applies each result to the board before the next attack is declared, so the set of 'enemy units to which there are friendly units adjacent' CHANGES DURING THE PHASE - a Dr moves a defender away, a DE removes it, an advance (X.15) moves a victor into new contact. The sheet never says whether CBT-06/07 are fixed at phase start or re-read after each result. Reading A (fixed at phase start) makes the assignment computable once, but can oblige an attack on a unit that has since retreated out of contact. Reading B (live re-evaluation) makes the obligation set a moving target and can CREATE new obligations mid-phase that no unit is left to satisfy, because CBT-10 has already spent the neighbours. The two readings give different legal move sets from the same board position. Must be ruled before any combat code is written; it is the precondition for C.6, not a detail of it <br>*source:* rules_2nd_ed.json unenforceable_as_written (CBT-04 vs CBT-06) <br>*open ruling:* `NAW2-OR-6` | `OPEN` |
| **C.8** | `CBT-08` | the attacking player resolves his attacks in any order he wishes <br>*note:* absent from RULEBOOK_VERIFIED; distinct from CBT-09's choice of pairings. Free order plus immediate results (C.4) is what makes C.7's timing question decisive | `OPEN` |
| **C.9** | `CBT-09` | the attacking player chooses which attacking units attack which defending units | `OPEN` |
| **C.10** | `CBT-11` | many attackers may combine against one defender, provided every attacker is adjacent to that defender (artillery bombardment excepted); their strengths total into one figure <br>*note:* predicate built + validated (several attackers vs one defender, all adjacent) - flips with the battle action | `OPEN` |
| **C.11** | `CBT-12` | one attacker may attack two or more defenders it is adjacent to; the defenders' strengths total into one figure <br>*note:* predicate built + validated (one attacker vs several adjacent defenders; several-on-several EX-14 under the every-attacker-adjacent-to-every-defender reading) - flips with the battle action | `OPEN` |
| **C.12** | `CBT-13` | deliberately poor-odds ('diversionary') attacks are legal; the gate must never require odds maximisation or refuse a suicidal attack <br>*note:* a real refusal risk: an engine that helpfully rejects a 1:5 attack breaks the printed permission. EX-16 prints a 1:4 attack \|\| validated: a 1:4 attack is legal, battle_check never refuses on odds - flips with the battle action | `OPEN` |
| **C.13** | `CBT-17` | Combat Strength is used as an integral whole and may never be split across two attacks <br>**evidence:** engine/naw.py battle_check: a unit named twice is refused; strengths enter whole \|\| games/napoleon-at-waterloo/validate_combat.py: a unit named twice is refused [CBT-17] | `ENFORCED` |
| **C.14** | `CBT-18`, `TEC-01` | a DEFENDING unit in a Town hex or a Woods/Road hex doubles its Combat Strength; attacking FROM such terrain confers nothing <br>**evidence:** engine/naw.py defense_strength: x2 when the DEFENDER's hex kind is town or woods_road (game.json combat.terrain_effects, ruling NAW2-D4); attackers never doubled \|\| games/napoleon-at-waterloo/validate_combat.py: Town defender 6->12, Woods/Road 1014 defender 6->12, clear 6, attacker in Town 6 vs 6 = 1:1 (EX-03/EX-04) <br>*note:* NAW2-D4 RULED (Bruce, 2026-08-14): follow the chart, which prints 'Towns & Woods/Roads' as one row. The rules text case (J.) names Towns only. Both are printed components of the same 1971 folio and no documentary ladder separates them; the 27 printed examples are silent (no example places a defender in a Woods/Road hex). Blast radius 5 hexes of 594. The predicate keys on the DEFENDER's hex only - EX-03 proves an attacker in a Town is NOT doubled, EX-04 proves the Town defender IS. Escalation to the game/module creator remains outstanding per spec #21 as amended <br>*open ruling:* `NAW2-D4 (ruled; escalation outstanding)` | `ENFORCED` |
| **C.15** | `CBT-10` | no defending unit may be attacked more than once per turn, nor any attacking unit attack more than once per turn <br>*note:* the print says 'per turn' where the neighbouring cases say Combat Phase. A unit can only be attacked in its enemy's Combat Phase and there is exactly one of those per Game-Turn, so the two readings coincide in play; the wording is loose, not defective. Recorded so no one re-derives it \|\| predicate built + validated via the fought/defended flags - the flags are set by the battle action (bite 5) | `OPEN` |
| **C.16** | `CBT-EX-01`, `CRT-01` | the validation corpus: 27 printed worked examples (folio p.2) plus the 8-vs-3 example printed inside the COMBAT column must all reproduce under the encoded odds arithmetic <br>**data:** ingest/worked_examples.json (27 examples); ingest/example_check.json (27/27 odds reproduced under both readings of D4) <br>**HARD.** VALIDATION COVERAGE IS PARTIAL AND MUST BE STATED, NOT ASSUMED (hard rule #1). What the corpus does NOT exercise: the CRT itself (no example states a die roll or a result code, so AE/Ar/EX/Dr/DE are validated only by the printed table); CRT columns 1:5, 1:3, 5:1 and 6:1; the clamp footnote (most extreme printed odds are 1:4 and 4:1); Zones of Control (never drawn); a Woods/Road defender (D4 is untouched by the corpus); nationality (attacker/defender is coded by grey tint, so no example constrains which side attacks); and terrain of any hex other than the two Town hexes. Enforcement of anything on that list ships on the printed table alone, not on a worked example <br>**evidence:** engine/naw.py battle_check + odds_column + crt_result \|\| games/napoleon-at-waterloo/validate_combat.py: 27/27 printed examples reproduce their odds; 60/60 CRT cells == crt_2nd_ed.json; corpus gaps stated (no die/result printed, columns 1:5/1:3/5:1/6:1 and the clamp untested by print) | `ENFORCED` |

### P2a/P4a — COMBAT PHASE - artillery

*inside every Combat Phase; p.1 col.6/col.7 ARTILLERY*

| cell | rules | requirement | status |
|---|---|---|---|
| **A.1** | `ART-01` | artillery may attack by bombarding from EXACTLY two hexes' distance, as well as adjacently <br>*note:* predicate built + validated: distance exactly 2 legal, 3 refused - flips with the battle action | `OPEN` |
| **A.2** | `ART-02`, `CBT-07` | artillery adjacent to an enemy unit is bound by the mandatory-participation rule like any other unit | `OPEN` |
| **A.3** | `ART-06`, `CBT-06` | bombardment is never mandatory; an enemy within two hexes creates NO obligation <br>*note:* this is the scope limit that stops CBT-06 from generating range-2 obligations. Absent from RULEBOOK_VERIFIED; without it the assignment problem of C.6 would be strictly larger | `OPEN` |
| **A.4** | `ART-07` | an artillery unit adjacent to an enemy may discharge its participation obligation by bombarding a DIFFERENT enemy two hexes away, provided some other friendly unit attacks the adjacent enemy <br>**HARD.** feeds directly into C.6: the assignment search must consider range-2 substitutions for adjacent artillery, which enlarges the space of complete assignments and means an assignment solver that only pairs adjacent units will refuse legal phases | `OPEN` |
| **A.5** | `ART-03`, `ART-04`, `ART-09` | a unit that attacked from range 2 is never destroyed or retreated by the result: AE and Ar do not touch it, and its strength still counts in the odds | `OPEN` |
| **A.6** | `ART-10` | artillery attacking from an adjacent position suffers all combat results like any other unit | `OPEN` |
| **A.7** | `ART-12`, `ART-05` | artillery immunity never propagates: non-artillery partners always suffer all results, whatever the distance of the artillery <br>*note:* absent from RULEBOOK_VERIFIED | `OPEN` |
| **A.8** | `ART-05`, `EXR-01` | on an EX result, the attacker's loss is made up only from units directly involved in that attack; bombarding artillery contributes strength and pays nothing <br>**HARD.** UNDEFINED CASE WITH A REAL EXPLOIT. If EVERY attacker in the attack is bombarding artillery, an EX eliminates the defender AT NO COST - the print names no one to pay the exchange, and ART-03/ART-09 explicitly exempt the only participants. The 3rd Edition [6.3] closes this; the 2nd Edition never does. It is reachable in play: 4 French and 3 Allied artillery units are in the OOB, and the 2:1/4:1/5:1 columns carry EX on a 5, 3:1 and 4:1/5:1 on a 6. A gate must decide - defender eliminated free, or the attack refused, or the EX read as a DE - and each choice changes the 40-point victory race (V.2). This is exactly the class spec #21 as amended sends to the game creator and which BLOCKS playability until resolved <br>*source:* rules_2nd_ed.json printed_defect_candidates kind=undefined case (ART-05) <br>*open ruling:* `NAW2-OR-7` | `OPEN` |
| **A.9** | `ART-11`, `RET-01` | a bombarding artillery unit may VOLUNTARILY elect to suffer an 'Attacker Retreat' result it is otherwise immune to <br>**HARD.** the print gives no purpose, no restriction and no chooser for the direction of a VOLUNTARY retreat. X.3 gives retreat direction to the VICTORIOUS player - which on an Ar is the defender - so a voluntary Ar would hand the enemy the right to move the electing unit. Whether the electing player instead picks his own direction is undefined. Not on any prior list - see N5 <br>*open ruling:* `NAW2-OR-8` | `OPEN` |
| **A.10** | `ART-13`, `ART-14` | a BOMBARDING artillery unit may attack only a single unit (never part of a one-to-many attack); an ADJACENT artillery unit may attack as many units as it is adjacent to <br>*note:* the bar is on the bombarding unit's participation, so it also constrains mixed attacks (A.11): a combined attack that includes a bombarding gun cannot have two defenders \|\| predicate built + validated: bombarding gun vs two defenders refused (ART-13); adjacent gun vs two adjacent defenders legal (ART-14) | `OPEN` |
| **A.11** | `ART-08` | artillery may attack alone, with other artillery, or with infantry/cavalry, combining adjacent attackers and range-2 bombardment in ONE combined strength <br>**data:** worked_examples.json: EX-09 and EX-24 print exactly this combination <br>*note:* predicate built + validated: adjacent cavalry 1 + bombarding artillery 3 = 4:1 (EX-09/EX-24) | `OPEN` |
| **A.12** | `ART-15`, `SEQ-08` | artillery under attack suffers all results like any other unit and may NOT use its two-hex range defensively; there is no defensive fire <br>*note:* closes as structurally impossible if the engine has no non-phasing action at all (T.5) - but that argument must be asserted by a validator, not assumed | `OPEN` |
| **A.13** | `ART-16` | bombardment may fire over intervening units (enemy or friendly) and over Town hexes <br>*note:* predicate built + validated: fires over an intervening enemy unit and over a Town hex | `OPEN` |
| **A.14** | `ART-17`, `TEC-01` | artillery may not fire over a Woods hex to attack a unit two hexes away <br>**HARD.** AMBIGUOUS AT THE GEOMETRY. On a hex grid two hexes apart there are either one or two intervening hexes depending on the axis. The print never says whether ONE Woods hex among two candidate paths blocks the shot, or whether every path must be blocked. The two readings give different legal bombardment sets, and 56 of 594 hexes are Woods, so the difference is not marginal. Flagged MATERIAL in rules_2nd_ed.json; listed in unenforceable_as_written. Note also that the TEC states the same bar on its Woods row, so both printed sources agree on the rule and disagree with neither - the ambiguity is in the geometry, not between components <br>*note:* predicate built under the STRICT reading (any candidate intervening Woods hex blocks) - NAW2-OR-9 open; validated on a real Woods pair <br>*open ruling:* `NAW2-OR-9` | `OPEN` |
| **A.15** | `ART-18`, `CBT-14` | artillery that is not adjacent to the defender may never take the post-combat advance | `OPEN` |
| **A.16** | `DIS-01`, `ART-02` | a disrupted artillery unit may NOT fire in the Combat Phase in which it was disrupted <br>**HARD.** two undefined edges (disruption_verified U6): whether the ban applies to a gun that had ALREADY fired earlier in the same Combat Phase (the ban is stated forward-looking), and whether a disrupted gun still counts as an adjacent participant for the CBT-07 obligation - if it does not, a disruption can make an otherwise complete assignment (C.6) impossible mid-phase, which is C.7's timing question in its sharpest form <br>*open ruling:* `NAW2-OR-10` | `OPEN` |

### P2b/P4b — COMBAT PHASE - result application (retreat, disruption, advance)

*immediately after every resolved attack; map sheet p.5 EXPLANATION OF RESULTS + RETREAT AND ADVANCE AS A RESULT OF COMBAT (both printed on the British/Prussian half only)*

| cell | rules | requirement | status |
|---|---|---|---|
| **X.1** | `EXR-01`, `CRT-01` | the five printed result codes and their meanings: AE Attacker Eliminated, Ar Attacker Retreats one hex, EX Exchange, Dr Defender Retreats one hex, DE Defender Eliminated <br>*note:* the 3rd Edition renames these Ae/Ee/De - a RENAME, not a rules change. Map them; never branch on them | `OPEN` |
| **X.2** | `EXR-01`, `RET-01` | retreat distance is ONE hex (stated in the Explanation of Results for both Ar and Dr; the Retreat and Advance block never restates a distance) | `OPEN` |
| **X.3** | `RET-01` | the VICTORIOUS player decides the retreat direction - for Ar as well as Dr, because the paragraph is headed 'When units are forced to retreat' and is not scoped to defenders <br>*note:* consequence the chart never states in so many words (combat_charts O2): on an Ar the victorious player is the DEFENDER, so the NON-PHASING player makes a decision inside the phasing player's Combat Phase. That is a decisional pending the engine must present to the non-phasing seat | `OPEN` |
| **X.4** | `RET-01` | four printed bars: a retreat may not go into an enemy Zone of Control, off the map, into non-Road Woods, or into an enemy-occupied hex <br>*note:* reads directly off Z.1/Z.5: because every unit projects ZOC into all six adjacent hexes with no terrain exception, a unit adjacent to two or more enemies will frequently have NO legal retreat hex and be eliminated by X.6. That is the printed consequence, not a bug - and it makes Z.5's phantom-ZOC trap decisive | `OPEN` |
| **X.5** | `RET-01` | nothing requires a retreat to move the unit AWAY from the attacker; within the four bars, sideways and forward retreats are legal <br>*note:* combat_charts O4. A gate that computes 'directly away' will be silently wrong and will eliminate units the rules would have saved | `OPEN` |
| **X.6** | `RET-01` | if no path of retreat is open aside from the forbidden hexes, the retreating unit is ELIMINATED and removed immediately | `OPEN` |
| **X.7** | `DIS-01` | DISRUPTION: if the only safe hex is occupied by another, uninvolved FRIENDLY unit, that unit is pushed out by the retreating unit; the victorious player moves it back as if it were retreating, and the retreating unit takes its place <br>*note:* printed exactly once in the whole folio, on the map sheet, on the British/Prussian half only. A French player reading only his own half of the sheet is never shown it (NAW2-SD-2) | `OPEN` |
| **X.8** | `DIS-01` | the disrupted unit may not be forced into enemy units, Zones of Control, or 'woods' <br>**HARD.** NAW2-SD-3, OPEN, BLOCKS PLAYABILITY. The retreat bar two paragraphs earlier prints 'non-Road Woods'; the disruption bar prints bare lower-case 'woods'. Reading A treats the shorthand as elision (disruption is barred exactly where retreat is barred); reading B takes it literally (disruption is barred from ALL woods, a HARSHER constraint than retreat). The same sentence also OMITS 'off the map', which the retreat bar includes (U1) - so the disruption bar is either deliberately narrower on one axis and wider on another, or loosely drafted. Blast radius 5 Woods/Road hexes in the displacement branch only, and it interacts with C.14: under Bruce's D4 ruling a Woods/Road hex is defensively FAVOURABLE, which sharpens whether a unit may be shoved into one. Awaiting Bruce <br>*open ruling:* `NAW2-SD-3` | `OPEN` |
| **X.9** | `DIS-01` | the disrupted unit is 'moved back ... as if it were retreating' <br>**HARD.** UNDEFINED (U3): back relative to WHAT? The disrupted unit fought no combat, so it has no attacker to be pushed away from. The print names the victorious player as the chooser but gives no direction rule at all. Combined with X.5 (retreats need not move away) the practical reading is 'any hex passing the X.8 bars, chosen by the victorious player' - but that is a reading, not the print <br>*open ruling:* `NAW2-OR-11` | `OPEN` |
| **X.10** | `DIS-01` | if the push cannot be made legally, the uninvolved unit is NOT disrupted, stays put, and the ORIGINAL retreating unit is eliminated instead | `OPEN` |
| **X.11** | `DIS-01` | chain-reaction disruption: a disrupted unit may itself disrupt a further friendly unit when that is the only safe path open to it <br>**HARD.** UNDEFINED AT DEPTH (U4, U7). The print does not say whether each link of the chain is subject to the same X.8 bar and the same X.10 fallback, nor - if the chain fails at depth N - WHICH unit is eliminated: X.10's subject is 'the unit which was forced to retreat as a result of combat', which in a chain has no unique referent. And S5 says a disrupted unit CAN disrupt others, which reads permissive inside an otherwise mandatory procedure - is the chain compulsory when it is the only option, or may the victorious player decline it and eliminate instead? A recursive displacement engine cannot be written until this is ruled <br>*open ruling:* `NAW2-OR-12` | `OPEN` |
| **X.12** | `DIS-01` | 'uninvolved' friendly unit <br>**HARD.** NEVER DEFINED (U5). Uninvolved in the combat just resolved, or in any combat this Combat Phase - a unit that has already attacked, or that is a defender in a battle not yet resolved? Under CBT-06/CBT-07 nearly every unit in contact is 'involved' in something, so the narrow reading can leave no eligible disruptee at all <br>*open ruling:* `NAW2-OR-13` | `OPEN` |
| **X.13** | `DIS-01` | how disruption ENDS <br>**HARD.** NO PRINTED END CONDITION. The rule states no removal step, no duration and no end-of-phase clause. The only durable consequence it names is bounded by its own wording - artillery may not fire 'in the Combat Phase in which they were disrupted' (A.16). The punched set contains exactly ONE marker (the turn marker), so there is no physical disrupted-unit counter and no component evidence for a persistent state. The conservative encoding is a per-Combat-Phase flag with no other effect - but it is a reading <br>*open ruling:* `NAW2-OR-14` | `OPEN` |
| **X.14** | `EXR-01` | EX: the defender is eliminated and the attacker suffers a loss AT LEAST equal in Strength Points, made up ONLY from units directly involved in that attack; the attacker will sometimes be forced to lose more than the defender; both sides' losses are removed immediately; a surviving attacker may then advance <br>**HARD.** DECISIONAL OBLIGATION WITH NO PRINTED MINIMALITY RULE. 'AT LEAST equal' states a floor and no ceiling, and the print never says who selects the units nor that he must pick the cheapest sufficient subset. A player could deliberately over-pay - which is not idle, because both 40-point ledgers (V.1/V.2/V.3) are the victory condition, so over-paying can hand the opponent the race or trigger demoralization. The gate must present the selection as a constrained pending and must decide whether over-payment is legal. Not on any prior list - see N4 <br>*open ruling:* `NAW2-OR-15` | `OPEN` |
| **X.15** | `CBT-14`, `CBT-16`, `RET-01` | OPTIONAL ADVANCE: whenever a hex is vacated as a result of combat, the victorious unit responsible may advance into it; the option must be exercised IMMEDIATELY; a unit is never forced to advance; never more than one hex; advances are not regular Movement and expend no Movement Points | `OPEN` |
| **X.16** | `CBT-15`, `RET-01` | the advance is legal even if the advancing unit is still in an enemy ZOC AND/OR the vacated hex is in an enemy ZOC <br>*note:* SOURCE-LOCATION CORRECTION. rules_2nd_ed.json flagged the second clause as an unsourced extension in RULEBOOK_VERIFIED, because the page-1 text (CBT-15) grants the permission only for the advancing unit's own ZOC situation. The page-5 chart DOES print 'and/or if the vacated hex is in an Enemy Zone of Control' verbatim. So the clause is printed, on the other sheet - not an invention, but it must be cited to p.5 and never to p.1. Also note the advance is the ONE way a unit may enter a hex in an enemy ZOC and later act, which is why it interacts so hard with X.17 | `OPEN` |
| **X.17** | `RET-01`, `CBT-06`, `CBT-07` | an advancing unit may not participate in another attack OR defense in the Combat Phase in which it advanced, even if the advance places it next to enemy units whose battles are yet to be resolved <br>**HARD.** DIRECT COLLISION WITH THE MANDATORY-ATTACK CLUSTER (combat_charts O5). CBT-07 says every friendly unit adjacent to an enemy MUST participate in an attack this phase; this paragraph says an advanced unit MUST NOT. An advance can also drop the advancing unit next to an as-yet-unattacked enemy, which under a live reading of CBT-06 (see C.7) creates an obligation that the advanced unit is forbidden to satisfy and that its neighbours may already have spent themselves on (CBT-10). The folio never reconciles the two. The bar on 'defense' is stranger still: a unit cannot decline to be a defender, so under an Ar-advance (X.15 applied to the non-phasing victor) the sentence forbids something the rules do not let a player choose. Which of C.7's two readings is adopted decides whether this is a contradiction or merely a sequencing constraint <br>*open ruling:* `NAW2-OR-16` | `OPEN` |
| **X.18** | `RET-01`, `SEQ-08`, `SEQ-07`, `CBT-14` | who may advance after an Ar result <br>**HARD.** NEW FINDING - see N7. RET-01 grants the advance to 'the victorious unit responsible for the Enemy elimination or retreat' whenever a hex is vacated as a result of combat. On an Ar the vacated hex is the ATTACKER's, and the victorious unit is the DEFENDER - a NON-PHASING unit. SEQ-08 states flatly that no Allied movement takes place during the French Player-Turn and vice-versa, and SEQ-07 permits movement in a Combat Phase only 'as directed by the Combat Resolution Table' - an optional advance is permitted, not directed. So either (a) the non-phasing player advances, contradicting SEQ-08 on its face, or (b) the advance is phasing-player-only, which the Retreat and Advance block's own wording does not say and which would make ART-11 (a bombarding gun VOLUNTARILY electing an Ar) pointless as a tactical device. A printed contradiction between page 1 and page 5 that no prior bite named; it must be ruled before the advance pending is built, and it decides which SEAT the engine prompts <br>*open ruling:* `NAW2-OR-17` | `OPEN` |
| **X.19** | `VIC-13`, `RET-01` | a unit forced to retreat off the map counts as DESTROYED, never as an exiting unit, for either side <br>*note:* candidate proven-outcome-equivalence: X.4 already bars retreating off the map and X.6 eliminates a unit with no legal retreat, so the state VIC-13 describes cannot be entered and its accounting consequence (counted as destroyed) is exactly what X.6 produces anyway. If that argument survives review the cell closes vacuously - but it is an argument, not an encoding, and it stays OPEN until a validator asserts that no code path can retreat a unit off the map | `OPEN` |

### V — VICTORY AND EXIT (continuous; checked immediately)

*continuously, mid-phase; p.1 col.7/col.8 HOW THE GAME IS WON + Cases*

| cell | rules | requirement | status |
|---|---|---|---|
| **V.1** | `VIC-05` | both players keep a running total of Combat Strength Points lost by BOTH sides - two ledgers are part of game state <br>**data:** ingest/oob_2nd_ed.json totals: French 89 CSP at start, Allied 73 + 34 Prussian = 107 <br>**evidence:** engine/naw.py s.losses {Fr, Al} incremented by printed Combat Strength in _eliminate \|\| games/napoleon-at-waterloo/validate_victory.py: eliminating an Allied unit adds its points to the Allied ledger <br>*note:* the printed Demoralization Scale is a 1..40 track; the punched set has exactly ONE marker (the turn marker), so the scale's own instruction is to use a destroyed counter. No component evidence constrains the engine here | `ENFORCED` |
| **V.2** | `VIC-01`, `VIC-02` | FRENCH VICTORY: destroy 40 Allied Combat Strength Points AND exit seven French units off the North edge, on or before Game-Turn 10, with the 40 reached BEFORE the Allies destroy 40 French points <br>**evidence:** engine/naw.py _check_victory: first_forty == Fr and exited >= 7 -> French win \|\| games/napoleon-at-waterloo/validate_victory.py: forty Allied points with seven already exited -> French win; seventh exit after demoralization wins | `ENFORCED` |
| **V.3** | `VIC-03` | ALLIED VICTORY: destroy 40 French Combat Strength Points before the enemy destroys 40 Allied points; no exit requirement <br>**evidence:** engine/naw.py _check_victory: first_forty == Al -> Allied win \|\| games/napoleon-at-waterloo/validate_victory.py: forty French points destroyed first -> Allied win, immediately | `ENFORCED` |
| **V.4** | `VIC-04` | DRAW: neither side reaches 40, or the French reach 40 but fail to exit seven units <br>**evidence:** engine/naw.py _game_end after Game-Turn 10: draw unless already over \|\| games/napoleon-at-waterloo/validate_victory.py: end of Game-Turn 10 while demoralized and under seven exits -> DRAW; validate_movement: no losses -> draw | `ENFORCED` |
| **V.5** | `VIC-08` | French units may exit ONLY from the arrow-marked North-edge hexes <br>**data:** ingest/map_grid.json editions.2nd.exit_hexes: 11 hexes, 0101..1101, read off the folio arrows; columns 12+ of row 01 carry no arrow; ingest/timerecord_oob.json exit_arrows_corroboration: 11 arrows counted independently <br>**evidence:** engine/naw.py exit_options(): only game.json exit.hexes (11 arrowed hexes) \|\| games/napoleon-at-waterloo/validate_movement.py: exit from a non-arrowed hex refused; column 12+ not an exit hex <br>*note:* E41 is closed for the 2nd Edition with an enumerated set - do NOT reuse the 3rd Edition's 9 exit hexes | `ENFORCED` |
| **V.6** | `VIC-09`, `MOV-05` | the act of exiting expends one Movement Point <br>**evidence:** engine/naw.py exit_options(): +1 MP, must fit within MA \|\| games/napoleon-at-waterloo/validate_movement.py: exit costs 3 hexes + 1; unit at 0305 cannot exit | `ENFORCED` |
| **V.7** | `VIC-10` | exited units may not return to the game <br>**evidence:** engine/naw.py _apply exit: unit deleted, exited ledger \|\| games/napoleon-at-waterloo/validate_movement.py: an exited unit is gone for good | `ENFORCED` |
| **V.8** | `VIC-11` | exits are unconstrained in timing and grouping - not all in one turn, not all from one hex, before and/or after the 40-point mark <br>**evidence:** engine/naw.py: exit legal in any own Movement Phase, any arrowed hex, no grouping \|\| games/napoleon-at-waterloo/validate_movement.py: exits at any time in the random walk | `ENFORCED` |
| **V.9** | `VIC-12`, `REI-07` | Allied units may NEVER exit the map, even to avoid destruction <br>**evidence:** engine/naw.py _propose_exit: exit_side Fr only (VIC-12; REI-07) \|\| games/napoleon-at-waterloo/validate_movement.py: Allied units may never exit | `ENFORCED` |
| **V.10** | `VIC-06`, `VIC-13` | EXITED is a third unit state, neither on-map nor lost: exited French units are not counted in French losses and are kept on display off the map <br>**evidence:** engine/naw.py s.exited (separate from s.dead); _eliminate never touches exited units; losses unchanged by exit \|\| games/napoleon-at-waterloo/validate_victory.py: an exited French unit is not a French loss <br>*note:* absent from RULEBOOK_VERIFIED. The printed Exited French Units box has exactly seven blank cells - a physical mirror of the victory requirement \|\| the exited ledger exists (engine/naw.py s.exited, separate from s.dead); the loss ledger and its exclusion of exited units land with bite 6 | `ENFORCED` |
| **V.11** | `VIC-14`, `EXR-01` | if BOTH sides reach the 40-point level at exactly the same moment (only possible on an EX), the French win if seven units are already exited, otherwise the Allies win <br>**evidence:** engine/naw.py _check_victory: both ledgers crossing forty in one elimination step -> first_forty 'both' -> French if seven exited else Allied \|\| games/napoleon-at-waterloo/validate_victory.py: both ledgers cross forty in one step -> Allied win / French win with seven exited [VIC-14] <br>*note:* the only simultaneity the print admits, and it exists precisely because EX removes both sides' losses at one instant (X.14) | `ENFORCED` |
| **V.12** | `MOV-17`, `VIC-08`, `VIC-09` | exit hex 1101 is a Woods/Road hex whose road hexsides are N (off the north edge) and S <br>**HARD.** INTERACTION, NEW - see N3. Under M.12 a Woods/Road hex must be entered and exited along the road, so the eleventh exit hex is enterable ONLY from the south along the road and exitable only northwards off the map. The other ten exit hexes are clear terrain and carry no such constraint. Whether the off-map step counts as an 'exit along the road' for MOV-17 is not stated anywhere; the reading is natural but unprinted, and it decides whether one of the seven required French exits can be made through 1101 at all <br>**evidence:** engine/naw.py: 1101 enterable only from 1102 along the road (terrain.json sides), exit crosses the N road hexside - LEGAL; NAW2-OR-18 kept open for Bruce's confirmation (the exit arrow is printed inside the hex) \|\| games/napoleon-at-waterloo/validate_movement.py: exit through 1101 from 1102 = 2 MP; from 1002 = 3 MP via 1102 <br>*open ruling:* `NAW2-OR-18` | `ENFORCED` |

### D — ALLIED DEMORALIZATION (continuous latch)

*the instant the trigger is met, mid-phase; p.1 col.8 ALLIED DEMORALIZATION*

| cell | rules | requirement | status |
|---|---|---|---|
| **D.1** | `DEM-01`, `REI-05` | trigger: the French destroy 40 Allied Combat Strength Points FIRST but have not yet exited seven units; the game continues and ALL Allied units, Prussians included, are DEMORALIZED <br>**evidence:** engine/naw.py _check_victory: first_forty == Fr and exited < 7 -> demoralized latch, game continues \|\| games/napoleon-at-waterloo/validate_victory.py: forty Allied points with no exits -> game continues, Allies DEMORALIZED | `ENFORCED` |
| **D.2** | `DEM-02`, `DEM-08`, `CBT-04` | demoralization takes effect IMMEDIATELY, even in the middle of a Player-Turn - between two attacks of the same Combat Phase if necessary; no delay <br>**evidence:** engine/naw.py: the latch is set inside _eliminate, i.e. at the instant of the loss, mid-phase \|\| games/napoleon-at-waterloo/validate_victory.py: latch set by the eliminating call itself | `ENFORCED` |
| **D.3** | `DEM-03`, `DEM-08` | a one-way latch: once demoralized the Allies stay demoralized for the rest of the game <br>**evidence:** engine/naw.py: s.demoralized is never cleared \|\| games/napoleon-at-waterloo/validate_victory.py: demoralization stands after forty French points | `ENFORCED` |
| **D.4** | `DEM-04`, `DEM-09`, `VIC-04` | after the latch the Allied victory branch is closed: destroying 40 French points is no longer an Allied victory, does not demoralize the French, and does not relieve the effects; the best Allied outcome is a Draw <br>**evidence:** engine/naw.py _check_victory: once first_forty == Fr, forty French points later never sets an Allied win; the French are never demoralized (D.5) \|\| games/napoleon-at-waterloo/validate_victory.py: forty French points AFTER demoralization: no Allied win, demoralization stands [DEM-09] <br>*note:* DEM-04 is a DERIVED state (a consequence of DEM-05 + VIC-04), never an independent gate check - flagged in rules_2nd_ed.json unenforceable_as_written. Encoding it as a check would be a fabricated rule | `ENFORCED` |
| **D.5** | `DEM-05`, `VIC-03` | there is no French demoralized state <br>**evidence:** printed, twice, in the 2nd Edition itself. DEM-05: 'The French army is never demoralized (for the point at which they would be demoralized, fulfills the Allied Victory Condition).' And the one board state that could otherwise reach it - the Allies passing 40 French points AFTER their own latch - is closed by DEM-09 in the same column: that achievement 'does not ... Demoralize the French or in any way relieve the effects of Allied Demoralization.' Both citations are verbatim from rules_2nd_ed.json rows DEM-05 and DEM-09; no board position, victory branch or demoralization path in this edition produces a demoralized French army. Evidence kind: printed rule closing its own state space, with the single bypass explicitly foreclosed by an adjacent printed rule <br>*note:* the engine must therefore have NO French demoralization code path at all, and a validator must assert its absence - an unreachable cell is a claim about the engine as much as about the rules | `UNREACHABLE` |
| **D.6** | `DEM-06`, `DEM-07`, `CRT-01` | while demoralized: every Allied attack is resolved one odds-column LOWER and every French attack one odds-column HIGHER than the computed odds <br>**HARD.** UNDEFINED AT BOTH ENDS OF THE TABLE. The printed columns run 1:5 .. 6:1. An Allied attack already at 1:5 has no column below it and a French attack already at 6:1 has none above it, and the print states nothing for either case. The CRT's clamp footnote does NOT obviously cover it: it is worded 'attacks EXECUTED AT worse than 1 to 5 are treated as 1 to 5', which speaks to the raw ratio a player computes, not to a column produced by a shift applied afterwards. So there are at least three readings - clamp at the printed end, treat the shift as impossible (refuse or leave unshifted), or extrapolate a column the table does not have - and they give different combat outcomes in exactly the situations demoralization is meant to punish. Ranked MATERIAL for a gate in rules_2nd_ed.json printed_defect_candidates and listed in unenforceable_as_written. Reachable: demoralization is a normal course of this game and the 1:5 and 6:1 columns are both printed <br>**evidence:** engine/naw.py demoralization_shift inside battle_check: Al -1 / Fr +1 column, clamped at the printed ends (NAW2-OR-19 A; SPI 1979 6.2) \|\| games/napoleon-at-waterloo/validate_victory.py: 2:1 -> 1:1 Allied / 3:1 French; 1:5 and 6:1 stay put; battle_check reports the shift <br>*open ruling:* `NAW2-OR-19` | `ENFORCED` |

---

## §2 STATE LEDGER

Persistent state the gate must keep: which cells WRITE it, which READ it. This is where the
movement↔combat interplay lives; a phase-only view never tests that combat rewrote the map
movement runs on. In this game the Combat Phase writes unit positions through **three** distinct
doors (retreat, disruption displacement, advance), two of which are driven by the player who does
not own the unit.

| state | written by | read by | status |
|---|---|---|---|
| unit hex | setup (S.1), movement (M.*), reinforcement entry (R.1-R.3), retreat (X.2-X.6), disruption displacement (X.7-X.11), advance (X.15-X.18) | everything <br>*note:* three distinct writers inside the Combat Phase alone, two of them driven by the NON-owning player (X.3 retreat direction, X.7 disruption push) | `OPEN` |
| movement points spent, per unit, per Player-Turn | movement (M.2), map entry (R.3), map exit (V.6) | movement legality (M.2), exit legality (V.6) <br>*note:* explicitly NOT written by retreat or advance - CBT-16 puts both outside regular Movement | `OPEN` |
| ZOC map (derived, continuous) | any change of unit hex, by any writer, including mid-Combat-Phase results | movement stop/lock (M.7-M.10), retreat bars (X.4), disruption bars (X.8), advance permission (X.16) <br>*note:* must be recomputed after EVERY applied result, because CBT-04 applies results one at a time; a ZOC map cached at phase start would be wrong for the second attack onward | `OPEN` |
| phase-start ZOC snapshot (movement freeze) | start of each Movement Phase | MOV-13 freeze (M.10) <br>*note:* MOV-13 keys on the situation at the BEGINNING of the phase, so this is a separate snapshot from the live ZOC map above. Conflating them is a silent-incorrectness risk of exactly the class B18 closed in Siege of Jerusalem | `OPEN` |
| units that have attacked / been attacked this Combat Phase | attack resolution (C.4) | the once-per-turn bar (C.15), the mandatory-assignment check (C.6) | `OPEN` |
| mandatory-attack obligation set | phase start and/or every applied result - UNDECIDED, this is C.7 | every attack verdict, and the end-of-phase completion check (C.6) <br>*note:* the single most consequential undecided piece of state in the encoding. Its write schedule is an open ruling, not an implementation detail | `OPEN` |
| units that have advanced this Combat Phase | advance (X.15) | the no-further-participation bar (X.17), which the assignment check (C.6) must also honour | `OPEN` |
| disrupted-this-Combat-Phase flag | disruption displacement (X.7, X.11) | artillery firing ban (A.16) <br>*note:* no printed end condition (X.13) and NO physical counterpart - the punched set has exactly one marker, the turn marker | `OPEN` |
| loss ledgers, one per side, in Combat Strength Points | eliminations and EX losses (X.1, X.6, X.10, X.14) | victory (V.2, V.3, V.4, V.11), demoralization trigger (D.1) <br>*note:* Prussian losses write the ALLIED ledger (R.7). Exited French units do NOT write the French ledger (V.10) | `OPEN` |
| exited French units (count and identity) | exit (V.5, V.6) | victory (V.2), the draw branch (V.4), the demoralization trigger (D.1), the tie-break (V.11) | `OPEN` |
| Allied demoralization latch | the trigger test after every loss (D.1, D.2) | every odds computation thereafter (D.6), the victory branches (D.4) <br>*note:* one-way; must be tested between attacks, not at end of phase (D.2) | `OPEN` |
| Prussian reinforcement pool | setup staging (S.3 - reading undecided), entry (R.1) | entry legality (R.1-R.5), the non-delay obligation (R.5) | `OPEN` |
| turn and phase counter | the five-step sequence (T.1, T.2) | everything phase-gated; the turn-10 stop (T.1); the Game-Turn 2 entry window (R.1) | `OPEN` |
| pendings (retreat direction, disruption push, EX loss selection, advance decision) | combat resolution (X.3, X.7, X.14, X.15) | the propose/submit router <br>*note:* at least two of these are prompted to the NON-phasing seat (X.3 on an Ar, X.7 whenever the victor is the defender). Per the standing GUI rule every mid-phase pending is a modal | `OPEN` |

## §3 OBLIGATION FLAGS

| class | cells | status |
|---|---|---|
| **automatic (engine does it, no player input)** | T.1 turn advance, T.6 immediate victory check, C.3 die roll, D.1/D.2 demoralization latch, X.6 elimination when no retreat is open, X.10 elimination when the push fails, V.1 loss ledgers | all OPEN |
| **obligatory-decisional (the player MUST act and the gate must refuse everything else)** | C.6 the assignment itself, X.3 retreat direction (victorious player, either seat), X.7/X.9 disruption push direction, X.11 chain continuation, X.14 EX loss selection, A.9 voluntary Ar election | all OPEN; three of them (X.9, X.11, X.14) have no printed decision rule at all |
| **optional-decisional (the gate must permit and must never require)** | M.1 movement, C.12 poor-odds attacks, A.3 bombardment, X.15 the advance, V.8 exit timing | all OPEN. C.12 and X.15 are the two most likely to be broken by a helpful engine that refuses a bad choice |
| **ordered / quantified** | T.2 the five-step sequence, C.4 one attack at a time, results applied immediately, C.8 free attack order, R.1 entry at the beginning of the Allied Player-Turn of Game-Turn 2, M.14 NO movement-finality rule exists | all OPEN |
| **prohibitive (the gate refuses the action)** | T.3, T.4, T.5, M.5, M.8, M.9, M.10, M.11, M.12, C.13, C.15, A.10, A.12, A.14, A.15, A.16, X.4, X.8, X.17, V.7, V.9 | all OPEN |

## §4 UNREACHABLE REGISTER

Every claim carries its evidence. **One phase-spine cell** is marked `UNREACHABLE` (D.5); the
remaining entries are scope facts that keep out-of-edition and non-primary material from ever
becoming cells at all.

| subject | evidence | kind |
|---|---|---|
| French demoralization (the only phase-spine cell marked UNREACHABLE: D.5) | DEM-05 verbatim: 'The French army is never demoralized (for the point at which they would be demoralized, fulfills the Allied Victory Condition).' The single bypass - the Allies passing 40 French points after their own latch - is foreclosed verbatim by DEM-09 in the same column. Two printed rules of this edition close the state space between them | printed rule closing its own state space |
| the Grouchy variant in its entirety (variant counters '5v', the variant arrival schedule, and every rule the sheet carries) | edition_diff.json module defect M3: 'the Grouchy variant does not exist in the Second Edition at all. A module labelled 2nd Ed ships a variant board for a subsystem that edition never had.' The sheet both modules ship is a retimed edit of the printed 3rd Edition [9.2]-[9.4] text (M2), with every turn number shifted one turn earlier and the counters relabelled 'Var' where printed [9.1] specifies '5v'. NOT CITABLE for anything, and out of edition scope entirely | out-of-edition component; module scope error |
| staggered or later Prussian arrivals; any reinforcement event other than the single Game-Turn 2 entry | ingest/timerecord_oob.json: all ten Time Record slots were read individually off the native scan; all nine Prussian units are printed in the single 2 pm slot and NO unit is printed in any other slot. Corroborated on the Oliver module map. The 2nd Edition has exactly one reinforcement event | printed component enumeration (Time Record), two witnesses |
| Prussian entry on Game-Turn 3 (3 pm) | edition_diff.json M4: the davejm 3rd Edition module's map Time Record marks Prussian entry at 3 pm while its own bundled Grouchy sheet says Game-Turn Two. That is a 3rd Edition module contradicting itself; the 2nd Edition folio prints 2 pm on the Time Record and 'the beginning of the Allied Player's second turn' in the rules. Out of edition and not citable here | out-of-edition; module self-contradiction |
| every 3rd Edition mechanic that has no 2nd Edition counterpart - including [6.3]'s closure of the all-bombardment Exchange (A.8), [5.6]'s no-bombarding-from-an-enemy-ZOC restriction (diff row D9), and [6.5] displacement | edition_diff.json, 41 diff rows over both printed editions; the 2nd Edition is encoded from its own printed folio only. A 3rd Edition rule may NEVER be used to fill a 2nd Edition gap - that is precisely the gap-fill the authority ladder forbids ('a non-primary asset may be cited only for a claim a primary witness independently covers') | edition scope |
| the 3rd Edition map, its 380 hexes, its 9 exit hexes and its opposite column parity | ingest/map_grid.json edition_comparison: '2nd Ed 27x22 = 594 hexes; 3rd Ed 23x(17/16) = 380 hexes. The 3rd Ed map is a SMALLER battlefield, not a renumbering of the same field.' The two editions' column parities are OPPOSITE | edition scope; measured |
| any additional scenario, campaign game or optional rule | the 2nd Edition folio prints exactly one game: ten Game-Turns, 1 pm to 10 pm, one at-start setup read off the map art, one reinforcement event. The 127-row rules index contains no scenario, campaign or optional-rule section, and the Time Record has exactly ten slots. This matrix's per-scenario scope is therefore the whole edition | printed component enumeration |
| the 2020 Sabin house rules ('Double Defence / Except Cavalry with 2020 Rules') and every other third-party redraw content | edition_diff.json M1: the davejm module's TEC.png is a redraw that bakes in Philip Sabin's April 2020 tweaks, omits the 2nd Edition's Woods/Road doubling and asserts a Woods/Road LOS block. 'must not be used as the source for E14 or E15.' authority_ladder.json tier T3c, flagged contaminated | contaminated non-primary asset; never citable |

## §5 THE HARD CELLS

These are not ordinary rows. Each names a difficulty that a straightforward per-action legality
gate cannot absorb, and several must be **ruled before code is written**, not during it.

### S.3 — SETUP · SET-02, REI-01

**"Place the Prussian units on the East side" - staging of the nine Prussian counters before play**

AMBIGUOUS AS PRINTED. Off-map staging vs literal on-map East-edge placement. The literal reading contradicts REI-01 (Prussians ENTER at the start of the Allied player-turn of Game-Turn 2) and would put nine units on the map from Game-Turn 1. Not enforceable until a ruling picks a reading.

*Open ruling:* `NAW2-OR-1`

### M.6 — MOVEMENT PHASE · MOV-09, MOV-07

**one unit per hex**

TWO PRINTED SENTENCES, TWO SCOPES. Sentence 1 bars finishing the MOVEMENT PHASE stacked; sentence 2 says 'Players may NOT place more than one unit in a given hex' with no time qualifier. Under reading A a unit may end its own move stacked with a friend and be moved off later in the same phase; under reading B it may not. MOV-07 grants pass-through, which reading B makes the only legal co-occupancy. Different legal move sets. Not on any prior list - see N1

*Open ruling:* `NAW2-OR-2`

### M.12 — MOVEMENT PHASE · MOV-17

**a Woods/Road hex must be ENTERED and EXITED along the road: both hexsides used must be road hexsides**

DATA VERIFICATION REQUIRED BEFORE ENCODING. Hex 1014 carries exactly ONE road hexside, which makes it a cul-de-sac under MOV-17: the only legal exit is back through the entry side. Either the printed road genuinely dead-ends there or the road_sides extraction is incomplete for that hex. Must be re-read off the print before this cell can close - see N2

### M.13 — MOVEMENT PHASE · MOV-19, MOV-01

**"Once a unit has been moved, and the Player's hand is taken from the piece, it may not be moved any further during that Player-Turn, not may it change its move without the consent of the opposing Player."**

PLATFORM-LEVEL QUESTION, NOT A GAME-LEVEL ONE. The trigger is physical (a hand leaving a piece) and the escape is social (opponent's consent); no gate can evaluate either from game state. Its subject matter is exactly what the platform's UNDO feature does - an undo IS 'changing a move'. That makes MOV-19 a question about the ENGINE's shipped feature set across ALL games, not a NAW encoding detail: either UNDO is a platform affordance that stands outside the printed rules (and is declared as such), or it is gated on an opponent-consent step. Bruce's call. Escalate before Fable touches undo semantics anywhere

*Open ruling:* `NAW2-OR-3`

### R.2 — REINFORCEMENT · REI-02

**entry anywhere along the East edge, at as many different points as desired**

DATA GAP. hexgraph_2nd_ed.json flags the NORTH-edge exit hexes but carries no East-edge flag. The East-edge hex set must be derived from the grid extent (column 27) and CONFIRMED against the printed map before this cell can close; the jagged north and south edges make an off-by-one at the corners a live risk

### R.5 — REINFORCEMENT · REI-06

**entry may not be deliberately delayed**

UNDEFINED CASE. The print states no relief for a position where entry is physically impossible - every East-edge hex enemy-occupied (MOV-08 bars entry into them), or enough of them in enemy ZOC that arriving units must stop on arrival (MOV-10). A gate that enforces a non-delayable entry must decide what it does when the obligation cannot be met. Ranked MATERIAL in rules_2nd_ed.json printed_defect_candidates

*Open ruling:* `NAW2-OR-4`

### Z.5 — ZONES OF CONTROL · ZOC-01, MOV-16

**ZOC is projected into all six adjacent hexes with NO terrain exception - including non-Road Woods hexes that no unit could legally enter**

NAMED TRAP. Enforceable exactly as written, but an encoder who 'reasonably' exempts impassable hexes is silently wrong, and the error is invisible in movement (nobody can enter those hexes anyway) while being decisive in RETREAT: X.4 bars retreating into an enemy ZOC, so a phantom-free woods hex would create retreat destinations the printed rules forbid. Flagged in rules_2nd_ed.json unenforceable_as_written

### C.6 — COMBAT PHASE - declaration and assignment · CBT-06, CBT-07, CBT-10

**EVERY enemy unit adjacent to any phasing unit must be attacked this phase; EVERY phasing unit adjacent to any enemy must participate in an attack this phase; no unit may appear in more than one attack, on either side**

THE COMBAT PHASE IS A GLOBAL ASSIGNMENT PROBLEM, NOT A PER-ACTION CHECK. Taken together these three rules require a PARTITION of the contact graph: every adjacent enemy covered exactly once as a defender, every adjacent friendly used exactly once as an attacker, subject to the adjacency constraints of CBT-11 (all attackers adjacent to the defender) and CBT-12 (all defenders adjacent to the attacker). A gate that validates one attack at a time CANNOT enforce this: an individually legal first attack can strand a later unit with no legal partner, and the illegality only becomes visible at the end of the phase. Deciding legality means searching for a COMPLETE assignment before admitting the first attack. Worse, the sheet prints NO RELIEF CLAUSE for a position in which no complete assignment exists, and no tie-break for choosing among several. The engine must either solve the assignment (and refuse a first attack that provably strands the phase) or declare the position undefined - and 'declare undefined' is an umpire, which spec #13 forbids. The printed examples confirm the shape rather than relieving it: both partitions of the 16-unit battle line use all 9 attackers exactly once and cover all 7 defenders exactly once. ART-07 widens the search space rather than narrowing it: an artillery unit standing adjacent to an enemy may discharge its obligation by bombarding a DIFFERENT enemy two hexes away, provided some other friendly covers the adjacent one. This is the single largest engineering item in the encoding

*Open ruling:* `NAW2-OR-5`

### C.7 — COMBAT PHASE - declaration and assignment · CBT-04, CBT-06, CBT-07

**when the mandatory-attack obligations are evaluated: at the start of the Combat Phase, or re-evaluated after every applied result**

OPEN RULING, NOT A CODING CHOICE. CBT-04 applies each result to the board before the next attack is declared, so the set of 'enemy units to which there are friendly units adjacent' CHANGES DURING THE PHASE - a Dr moves a defender away, a DE removes it, an advance (X.15) moves a victor into new contact. The sheet never says whether CBT-06/07 are fixed at phase start or re-read after each result. Reading A (fixed at phase start) makes the assignment computable once, but can oblige an attack on a unit that has since retreated out of contact. Reading B (live re-evaluation) makes the obligation set a moving target and can CREATE new obligations mid-phase that no unit is left to satisfy, because CBT-10 has already spent the neighbours. The two readings give different legal move sets from the same board position. Must be ruled before any combat code is written; it is the precondition for C.6, not a detail of it

*Open ruling:* `NAW2-OR-6`

### C.16 — COMBAT PHASE - declaration and assignment · CBT-EX-01, CRT-01

**the validation corpus: 27 printed worked examples (folio p.2) plus the 8-vs-3 example printed inside the COMBAT column must all reproduce under the encoded odds arithmetic**

VALIDATION COVERAGE IS PARTIAL AND MUST BE STATED, NOT ASSUMED (hard rule #1). What the corpus does NOT exercise: the CRT itself (no example states a die roll or a result code, so AE/Ar/EX/Dr/DE are validated only by the printed table); CRT columns 1:5, 1:3, 5:1 and 6:1; the clamp footnote (most extreme printed odds are 1:4 and 4:1); Zones of Control (never drawn); a Woods/Road defender (D4 is untouched by the corpus); nationality (attacker/defender is coded by grey tint, so no example constrains which side attacks); and terrain of any hex other than the two Town hexes. Enforcement of anything on that list ships on the printed table alone, not on a worked example

### A.4 — COMBAT PHASE - artillery · ART-07

**an artillery unit adjacent to an enemy may discharge its participation obligation by bombarding a DIFFERENT enemy two hexes away, provided some other friendly unit attacks the adjacent enemy**

feeds directly into C.6: the assignment search must consider range-2 substitutions for adjacent artillery, which enlarges the space of complete assignments and means an assignment solver that only pairs adjacent units will refuse legal phases

### A.8 — COMBAT PHASE - artillery · ART-05, EXR-01

**on an EX result, the attacker's loss is made up only from units directly involved in that attack; bombarding artillery contributes strength and pays nothing**

UNDEFINED CASE WITH A REAL EXPLOIT. If EVERY attacker in the attack is bombarding artillery, an EX eliminates the defender AT NO COST - the print names no one to pay the exchange, and ART-03/ART-09 explicitly exempt the only participants. The 3rd Edition [6.3] closes this; the 2nd Edition never does. It is reachable in play: 4 French and 3 Allied artillery units are in the OOB, and the 2:1/4:1/5:1 columns carry EX on a 5, 3:1 and 4:1/5:1 on a 6. A gate must decide - defender eliminated free, or the attack refused, or the EX read as a DE - and each choice changes the 40-point victory race (V.2). This is exactly the class spec #21 as amended sends to the game creator and which BLOCKS playability until resolved

*Open ruling:* `NAW2-OR-7`

### A.9 — COMBAT PHASE - artillery · ART-11, RET-01

**a bombarding artillery unit may VOLUNTARILY elect to suffer an 'Attacker Retreat' result it is otherwise immune to**

the print gives no purpose, no restriction and no chooser for the direction of a VOLUNTARY retreat. X.3 gives retreat direction to the VICTORIOUS player - which on an Ar is the defender - so a voluntary Ar would hand the enemy the right to move the electing unit. Whether the electing player instead picks his own direction is undefined. Not on any prior list - see N5

*Open ruling:* `NAW2-OR-8`

### A.14 — COMBAT PHASE - artillery · ART-17, TEC-01

**artillery may not fire over a Woods hex to attack a unit two hexes away**

AMBIGUOUS AT THE GEOMETRY. On a hex grid two hexes apart there are either one or two intervening hexes depending on the axis. The print never says whether ONE Woods hex among two candidate paths blocks the shot, or whether every path must be blocked. The two readings give different legal bombardment sets, and 56 of 594 hexes are Woods, so the difference is not marginal. Flagged MATERIAL in rules_2nd_ed.json; listed in unenforceable_as_written. Note also that the TEC states the same bar on its Woods row, so both printed sources agree on the rule and disagree with neither - the ambiguity is in the geometry, not between components

*Open ruling:* `NAW2-OR-9`

### A.16 — COMBAT PHASE - artillery · DIS-01, ART-02

**a disrupted artillery unit may NOT fire in the Combat Phase in which it was disrupted**

two undefined edges (disruption_verified U6): whether the ban applies to a gun that had ALREADY fired earlier in the same Combat Phase (the ban is stated forward-looking), and whether a disrupted gun still counts as an adjacent participant for the CBT-07 obligation - if it does not, a disruption can make an otherwise complete assignment (C.6) impossible mid-phase, which is C.7's timing question in its sharpest form

*Open ruling:* `NAW2-OR-10`

### X.8 — COMBAT PHASE - result application · DIS-01

**the disrupted unit may not be forced into enemy units, Zones of Control, or 'woods'**

NAW2-SD-3, OPEN, BLOCKS PLAYABILITY. The retreat bar two paragraphs earlier prints 'non-Road Woods'; the disruption bar prints bare lower-case 'woods'. Reading A treats the shorthand as elision (disruption is barred exactly where retreat is barred); reading B takes it literally (disruption is barred from ALL woods, a HARSHER constraint than retreat). The same sentence also OMITS 'off the map', which the retreat bar includes (U1) - so the disruption bar is either deliberately narrower on one axis and wider on another, or loosely drafted. Blast radius 5 Woods/Road hexes in the displacement branch only, and it interacts with C.14: under Bruce's D4 ruling a Woods/Road hex is defensively FAVOURABLE, which sharpens whether a unit may be shoved into one. Awaiting Bruce

*Open ruling:* `NAW2-SD-3`

### X.9 — COMBAT PHASE - result application · DIS-01

**the disrupted unit is 'moved back ... as if it were retreating'**

UNDEFINED (U3): back relative to WHAT? The disrupted unit fought no combat, so it has no attacker to be pushed away from. The print names the victorious player as the chooser but gives no direction rule at all. Combined with X.5 (retreats need not move away) the practical reading is 'any hex passing the X.8 bars, chosen by the victorious player' - but that is a reading, not the print

*Open ruling:* `NAW2-OR-11`

### X.11 — COMBAT PHASE - result application · DIS-01

**chain-reaction disruption: a disrupted unit may itself disrupt a further friendly unit when that is the only safe path open to it**

UNDEFINED AT DEPTH (U4, U7). The print does not say whether each link of the chain is subject to the same X.8 bar and the same X.10 fallback, nor - if the chain fails at depth N - WHICH unit is eliminated: X.10's subject is 'the unit which was forced to retreat as a result of combat', which in a chain has no unique referent. And S5 says a disrupted unit CAN disrupt others, which reads permissive inside an otherwise mandatory procedure - is the chain compulsory when it is the only option, or may the victorious player decline it and eliminate instead? A recursive displacement engine cannot be written until this is ruled

*Open ruling:* `NAW2-OR-12`

### X.12 — COMBAT PHASE - result application · DIS-01

**'uninvolved' friendly unit**

NEVER DEFINED (U5). Uninvolved in the combat just resolved, or in any combat this Combat Phase - a unit that has already attacked, or that is a defender in a battle not yet resolved? Under CBT-06/CBT-07 nearly every unit in contact is 'involved' in something, so the narrow reading can leave no eligible disruptee at all

*Open ruling:* `NAW2-OR-13`

### X.13 — COMBAT PHASE - result application · DIS-01

**how disruption ENDS**

NO PRINTED END CONDITION. The rule states no removal step, no duration and no end-of-phase clause. The only durable consequence it names is bounded by its own wording - artillery may not fire 'in the Combat Phase in which they were disrupted' (A.16). The punched set contains exactly ONE marker (the turn marker), so there is no physical disrupted-unit counter and no component evidence for a persistent state. The conservative encoding is a per-Combat-Phase flag with no other effect - but it is a reading

*Open ruling:* `NAW2-OR-14`

### X.14 — COMBAT PHASE - result application · EXR-01

**EX: the defender is eliminated and the attacker suffers a loss AT LEAST equal in Strength Points, made up ONLY from units directly involved in that attack; the attacker will sometimes be forced to lose more than the defender; both sides' losses are removed immediately; a surviving attacker may then advance**

DECISIONAL OBLIGATION WITH NO PRINTED MINIMALITY RULE. 'AT LEAST equal' states a floor and no ceiling, and the print never says who selects the units nor that he must pick the cheapest sufficient subset. A player could deliberately over-pay - which is not idle, because both 40-point ledgers (V.1/V.2/V.3) are the victory condition, so over-paying can hand the opponent the race or trigger demoralization. The gate must present the selection as a constrained pending and must decide whether over-payment is legal. Not on any prior list - see N4

*Open ruling:* `NAW2-OR-15`

### X.17 — COMBAT PHASE - result application · RET-01, CBT-06, CBT-07

**an advancing unit may not participate in another attack OR defense in the Combat Phase in which it advanced, even if the advance places it next to enemy units whose battles are yet to be resolved**

DIRECT COLLISION WITH THE MANDATORY-ATTACK CLUSTER (combat_charts O5). CBT-07 says every friendly unit adjacent to an enemy MUST participate in an attack this phase; this paragraph says an advanced unit MUST NOT. An advance can also drop the advancing unit next to an as-yet-unattacked enemy, which under a live reading of CBT-06 (see C.7) creates an obligation that the advanced unit is forbidden to satisfy and that its neighbours may already have spent themselves on (CBT-10). The folio never reconciles the two. The bar on 'defense' is stranger still: a unit cannot decline to be a defender, so under an Ar-advance (X.15 applied to the non-phasing victor) the sentence forbids something the rules do not let a player choose. Which of C.7's two readings is adopted decides whether this is a contradiction or merely a sequencing constraint

*Open ruling:* `NAW2-OR-16`

### X.18 — COMBAT PHASE - result application · RET-01, SEQ-08, SEQ-07, CBT-14

**who may advance after an Ar result**

NEW FINDING - see N7. RET-01 grants the advance to 'the victorious unit responsible for the Enemy elimination or retreat' whenever a hex is vacated as a result of combat. On an Ar the vacated hex is the ATTACKER's, and the victorious unit is the DEFENDER - a NON-PHASING unit. SEQ-08 states flatly that no Allied movement takes place during the French Player-Turn and vice-versa, and SEQ-07 permits movement in a Combat Phase only 'as directed by the Combat Resolution Table' - an optional advance is permitted, not directed. So either (a) the non-phasing player advances, contradicting SEQ-08 on its face, or (b) the advance is phasing-player-only, which the Retreat and Advance block's own wording does not say and which would make ART-11 (a bombarding gun VOLUNTARILY electing an Ar) pointless as a tactical device. A printed contradiction between page 1 and page 5 that no prior bite named; it must be ruled before the advance pending is built, and it decides which SEAT the engine prompts

*Open ruling:* `NAW2-OR-17`

### V.12 — VICTORY AND EXIT · MOV-17, VIC-08, VIC-09

**exit hex 1101 is a Woods/Road hex whose road hexsides are N (off the north edge) and S**

INTERACTION, NEW - see N3. Under M.12 a Woods/Road hex must be entered and exited along the road, so the eleventh exit hex is enterable ONLY from the south along the road and exitable only northwards off the map. The other ten exit hexes are clear terrain and carry no such constraint. Whether the off-map step counts as an 'exit along the road' for MOV-17 is not stated anywhere; the reading is natural but unprinted, and it decides whether one of the seven required French exits can be made through 1101 at all

*Open ruling:* `NAW2-OR-18`

### D.6 — ALLIED DEMORALIZATION · DEM-06, DEM-07, CRT-01

**while demoralized: every Allied attack is resolved one odds-column LOWER and every French attack one odds-column HIGHER than the computed odds**

UNDEFINED AT BOTH ENDS OF THE TABLE. The printed columns run 1:5 .. 6:1. An Allied attack already at 1:5 has no column below it and a French attack already at 6:1 has none above it, and the print states nothing for either case. The CRT's clamp footnote does NOT obviously cover it: it is worded 'attacks EXECUTED AT worse than 1 to 5 are treated as 1 to 5', which speaks to the raw ratio a player computes, not to a column produced by a shift applied afterwards. So there are at least three readings - clamp at the printed end, treat the shift as impossible (refuse or leave unshifted), or extrapolate a column the table does not have - and they give different combat outcomes in exactly the situations demoralization is meant to punish. Ranked MATERIAL for a gate in rules_2nd_ed.json printed_defect_candidates and listed in unenforceable_as_written. Reachable: demoralization is a normal course of this game and the 1:5 and 6:1 columns are both printed

*Open ruling:* `NAW2-OR-19`

## §6 OPEN RULINGS

Per spec #21 as amended 2026-08-09, *declared-umpired was removed from the authority ladder*: a
defect we cannot derive, validate or resolve to a binary answer is registered with quoted
evidence, escalated to the game/module creator, and **blocks playability** until resolved. Every
row below is an input to `game.json` `source_defects`; none of them is a coding choice.

> **A CONFLICT WITH THE AMENDED SPEC, SURFACED NOT WORKED AROUND.** #21 as amended routes an
> unresolvable defect to *the game/module creator* and blocks playability until **resolved by
> authority**. For this game that route does not exist: SPI ceased trading in 1982 and the folio's
> designer is dead. The module authors (PREP-7 job B's register) can answer questions about their
> *modules*; not one of the rulings below is a module question — every one is a defect in the 1971
> print. So the only authorities actually available for these 20 open items are (a) official errata,
> if any is ever found, (b) proven outcome-equivalence, and (c) a declared ruling by Bruce — which
> is the rung the 2026-08-09 amendment removed. Siege of Jerusalem could lean on a living module
> author; Napoleon at Waterloo cannot. **Bruce must decide how a dead-publisher game reaches
> playable at all before the encoding is worth starting** — otherwise the work terminates in 20
> permanently-open cells and a game that can never ship. This is a direction call, not a build
> problem, and it is prior to every item in the table.

| id | cell | question | status |
|---|---|---|---|
| `NAW2-SD-3` | X.8 | disruption bar says 'woods', retreat bar says 'non-Road Woods'; and 'off the map' is absent from the disruption bar | carried from rulings_2nd_ed.json, status OPEN, authority PENDING - Bruce |
| `NAW2-D4` | C.14 | TEC vs rules text on Woods/Road defence doubling | RULED - Bruce 2026-08-14, follow the chart; escalation to the game/module creator still outstanding per spec #21 as amended |
| `NAW2-OR-1` | S.3 | SET-02 Prussian staging: off-map or literal East-edge placement | new, needs a ruling |
| `NAW2-OR-2` | M.6 | MOV-09's two stacking sentences, two scopes | new, needs a ruling |
| `NAW2-OR-3` | M.13 | MOV-19 touch-move - PLATFORM-LEVEL: whether the engine's UNDO is legal under the printed rules, in this game and every other | new, Bruce's call, blocks undo semantics platform-wide |
| `NAW2-OR-4` | R.5 | REI-06 non-delayable entry when entry is physically impossible | new, needs a ruling |
| `NAW2-OR-5` | C.6 | the mandatory-assignment problem: no printed relief when no complete assignment exists, no tie-break when several do | new, and the largest single item in the encoding |
| `NAW2-OR-6` | C.7 | are the CBT-06/07 obligations fixed at phase start or re-evaluated after each result | new, precondition for C.6 |
| `NAW2-OR-7` | A.8 | ART-05: EX with only bombarding attackers kills the defender at no cost | carried from printed_defect_candidates, needs a ruling |
| `NAW2-OR-8` | A.9 | ART-11 voluntary Ar: who chooses the direction | new |
| `NAW2-OR-9` | A.14 | ART-17: does one Woods hex among two candidate intervening hexes block the shot | carried from printed_defect_candidates, needs a ruling |
| `NAW2-OR-10` | A.16 | disrupted artillery: already-fired case, and whether it still counts as an adjacent participant for CBT-07 | carried from disruption_verified U6 |
| `NAW2-OR-11` | X.9 | disruption direction - 'moved back' relative to what | carried from disruption_verified U3 |
| `NAW2-OR-12` | X.11 | chain-reaction disruption: per-link bars, who dies when the chain fails at depth N, and whether the chain is compulsory | carried from disruption_verified U4/U7 |
| `NAW2-OR-13` | X.12 | 'uninvolved' is never defined | carried from disruption_verified U5 |
| `NAW2-OR-14` | X.13 | disruption has no printed end condition | carried from disruption_verified |
| `NAW2-OR-15` | X.14 | EX loss selection: who chooses, and is over-payment legal | new |
| `NAW2-OR-16` | X.17 | advance bar vs mandatory participation | carried from combat_charts O5 |
| `NAW2-OR-17` | X.18 | advance after an Ar vs SEQ-08's no-non-phasing-action rule | new |
| `NAW2-OR-18` | V.12 | does an off-map step from exit hex 1101 satisfy MOV-17's along-the-road exit | new |
| `NAW2-OR-19` | D.6 | the demoralization odds shift at the ends of the printed table, and whether the CRT clamp footnote governs a shifted column | carried from printed_defect_candidates, needs a ruling |

## §7 NEW GAPS FOUND BY THIS MATRIX (N-list)

Found 2026-08-14 by reading the 127-row rules index against the page-5 charts, the disruption
paragraph, the hexgraph and the worked-example corpus. **Five (N1–N5) appear on no prior list at
all**; a sixth (N7) sharpens a prior observation into a named page-1-vs-page-5 contradiction; N6 is
carried unchanged and is listed only so it has a cell that can be closed.

| # | cell | rules | finding | class |
|---|---|---|---|---|
| N1 | M.6 | `MOV-09`, `MOV-07` | MOV-09 is two sentences with two different scopes - 'may not finish their Movement Phase in the same hex' and the unqualified 'Players may NOT place more than one unit in a given hex'. Whether a unit may END ITS OWN MOVE stacked with a friendly and be moved off later in the same phase is undecided, and the two readings give different legal move sets <br>*prior lists:* none - not in printed_defect_candidates, not in unenforceable_as_written | ambiguity in the original published game |
| N2 | M.12 | `MOV-17` | Woods/Road hex 1014 carries exactly ONE road hexside (NW) in hexgraph_2nd_ed.json. Under MOV-17's enter-and-exit-along-the-road rule that makes it a cul-de-sac whose only legal exit is the entry side. Either the printed road dead-ends there or the road_sides extraction is incomplete for that hex <br>*prior lists:* none | data verification item (possible ingest gap, possible printed map fact) |
| N3 | V.12 | `MOV-17`, `VIC-08`, `VIC-09` | the eleventh exit hex, 1101, is the only Woods/Road exit hex; its road hexsides are N (off the map) and S. MOV-17 therefore constrains entry to the southern road hexside, and nothing printed says whether the off-map step counts as exiting 'along the road'. One of the seven required French exits may or may not be makeable through it <br>*prior lists:* none | unstated interaction between the movement rules and the victory conditions |
| N4 | X.14 | `EXR-01` | the EX loss is 'AT LEAST equal' with no ceiling and no printed minimality requirement, and the print never names who selects which attacking units pay. Deliberate over-payment is therefore arguably legal, and it is not idle - both 40-point ledgers ARE the victory condition, so over-paying can hand the opponent the race or trip demoralization <br>*prior lists:* none | undefined case in the original published game |
| N5 | A.9 | `ART-11`, `RET-01` | ART-11 lets a bombarding gun VOLUNTARILY elect an Ar it is immune to, but RET-01 gives retreat direction to the VICTORIOUS player - who on an Ar is the defender. So a voluntary election hands the enemy the right to move the electing unit, unless the election also carries the direction. Undefined <br>*prior lists:* none | undefined case in the original published game |
| N6 | X.17 | `RET-01`, `CBT-06`, `CBT-07` | the advance bar on further participation collides with the mandatory-attack cluster - CARRIED, not new: recorded as combat_charts.json observation O5. Restated here as a matrix cell because O5 is an observation in an ingest file and would otherwise never be closed by anything <br>*prior lists:* combat_charts.json O5 | carried |
| N7 | X.18 | `RET-01`, `SEQ-08`, `SEQ-07`, `CBT-14` | ADVANCE AFTER AN Ar IS A PAGE-1 vs PAGE-5 CONTRADICTION. RET-01 grants the advance to the victorious unit whenever a hex is vacated by combat; on an Ar the vacated hex is the attacker's and the victor is the non-phasing defender. SEQ-08 states flatly that no non-phasing movement occurs, and SEQ-07 admits only movement DIRECTED by the CRT, which an optional advance is not. Either the non-phasing player advances (contradicting SEQ-08 on its face) or the advance is phasing-only (which the chart does not say, and which would make ART-11 pointless). It decides which seat the engine prompts <br>*prior lists:* adjacent to combat_charts.json O5, which notes the Ar/Dr asymmetry but does not name the SEQ-08 contradiction | contradiction between two printed components of the same edition |

## §8 COVERAGE AND VERDICT

| phase | cells | OPEN | UNREACHABLE | ENFORCED | hard |
|---|---|---|---|---|---|
| P0 SETUP | 9 | 0 | 0 | 9 | 1 |
| T TURN STRUCTURE (the spine itself) | 6 | 3 | 0 | 3 | 0 |
| P1/P3 MOVEMENT PHASE (French / Allied) | 14 | 1 | 0 | 13 | 3 |
| P3r REINFORCEMENT (Prussian entry - a sub-step of the Allied Movement Phase, Game-Turn 2) | 7 | 0 | 0 | 7 | 2 |
| Z ZONES OF CONTROL (continuous, both players' turns) | 6 | 0 | 0 | 6 | 1 |
| P2/P4 COMBAT PHASE - declaration and assignment | 16 | 11 | 0 | 5 | 3 |
| P2a/P4a COMBAT PHASE - artillery | 16 | 16 | 0 | 0 | 5 |
| P2b/P4b COMBAT PHASE - result application (retreat, disruption, advance) | 19 | 19 | 0 | 0 | 8 |
| V VICTORY AND EXIT (continuous; checked immediately) | 12 | 0 | 0 | 12 | 1 |
| D ALLIED DEMORALIZATION (continuous latch) | 6 | 0 | 1 | 5 | 1 |
| **TOTAL** | **111** | **50** | **1** | **60** | **25** |

**Rule-index coverage (machine-verified by `naw_coverage_matrix.py`):** 127 of 127 rows in
`rules_2nd_ed.json` are cited by at least one cell. Rows cited by no cell: **none**.
Cell citations not present in the index: **none**.

### PLAYABILITY VERDICT

**NOT PLAYABLE** — encoding in progress (bites 1-3 + 6 of 7 done: data layer, movement/ZOC/exit, combat arithmetic, reinforcement/victory/demoralization; bites 4-5 wait on rulings OR-5/OR-6/OR-16). 50 of 111 cells OPEN, 1 UNREACHABLE-with-evidence, 60 ENFORCED. 21 registered rulings (NAW2-D4 ruled; NAW2-OR-2 and NAW2-OR-18 enforced under a declared reading pending Bruce; the rest open), of which NAW2-SD-3 / OR-5 / OR-6 block bites 4-5.

The gating work, in the order it must happen:

1. **Rule the blockers first.** `NAW2-SD-3` (X.8), `NAW2-OR-6` (C.7 obligation timing) and
   `NAW2-OR-7` (A.8 costless Exchange) each decide the shape of code rather than a detail of it;
   `NAW2-OR-3` (M.13 touch-move vs UNDO) is a **platform-wide** question that reaches every
   shipped game and belongs to Bruce before Fable touches undo semantics anywhere.
2. **Then solve C.6.** The mandatory-assignment problem is the single largest engineering item;
   it cannot be started until C.7 is ruled, and A.4 widens its search space.
3. **Then the retreat/disruption engine** (X.2–X.13), which has five undefined edges of its own
   and no printed procedure on page 1 at all — the whole procedure lives on the map sheet, on the
   British/Prussian half only.
4. **Then everything else**, against the 27-example corpus for odds and against the printed CRT
   for results — with C.16's coverage gaps stated in the shipped register rather than glossed.

