import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.dirname(HERE)

SPINE = [
    {
        "phase": "P0",
        "name": "SETUP",
        "when": "one-off, before Game-Turn 1; not a phase",
        "citation": "p.1 col.3 SETTING UP THE GAME; SET-04",
        "cells": [
            {
                "id": "S.1",
                "rules": ["SET-01", "SET-03", "PCS-06"],
                "obligation": "MUST",
                "requirement": "at-start placement is read off the printed map art: a setup is legal iff every printed position holds a unit of the printed strength AND type; historical designation is free",
                "status": "OPEN",
                "data": ["ingest/oob_2nd_ed.json (44 at-start units, hex/side/factors/type, three independent witnesses, module_factor_disagreements = 0)"],
                "note": "the data exists and is triple-witnessed; what is missing is the encoding and a validator asserting all 44 printed positions",
            },
            {
                "id": "S.2",
                "rules": ["SET-01", "PCS-05"],
                "obligation": "DEFINES",
                "requirement": "side is decided by the printed Front Line: North of it Allied, South of it French; French = blue, Allied = red (British) + green (Prussian)",
                "status": "OPEN",
                "data": ["ingest/oob_2nd_ed.json side field, 44/44 agreement with the module save"],
            },
            {
                "id": "S.3",
                "rules": ["SET-02", "REI-01"],
                "obligation": "PROCEDURE",
                "requirement": "\"Place the Prussian units on the East side\" - staging of the nine Prussian counters before play",
                "status": "OPEN",
                "difficulty": "AMBIGUOUS AS PRINTED. Off-map staging vs literal on-map East-edge placement. The literal reading contradicts REI-01 (Prussians ENTER at the start of the Allied player-turn of Game-Turn 2) and would put nine units on the map from Game-Turn 1. Not enforceable until a ruling picks a reading.",
                "open_ruling": "NAW2-OR-1",
                "source": "rules_2nd_ed.json unenforceable_as_written (SET-02); printed_defect_candidates kind=ambiguity",
            },
            {
                "id": "S.4",
                "rules": ["SET-04", "SEQ-04"],
                "obligation": "PROCEDURE",
                "requirement": "placement is not a turn or a phase; the game opens with the French Player's first Movement Phase",
                "status": "OPEN",
            },
            {
                "id": "S.5",
                "rules": ["SET-03"],
                "obligation": "PROCEDURE",
                "requirement": "\"Players set up their units simultaneously\"",
                "status": "OPEN",
                "note": "both setups are fully printed on the map art, so neither side learns anything from the other's placement and simultaneity has no informational content. That argument must be WRITTEN DOWN and asserted by a validator, not assumed - a phased setup that admits any deviation from the printed positions would make simultaneity load-bearing again",
            },
            {
                "id": "S.6",
                "rules": ["PCS-01", "PCS-02", "PCS-03", "PCS-04", "PCS-07"],
                "obligation": "DEFINES",
                "requirement": "a unit carries exactly three game-relevant attributes: Combat Strength (one number, attack and defence alike), Movement Allowance (a hex count), type in {infantry, cavalry, artillery}",
                "status": "OPEN",
                "note": "NO printed rule in the 127-row index keys on infantry-vs-cavalry. Only artillery carries type-specific rules (ART-01..ART-18). An encoder must model the type field but must NOT invent a cavalry behaviour; a validator should assert that no verdict path branches on infantry vs cavalry",
            },
            {
                "id": "S.7",
                "rules": ["MAP-01"],
                "obligation": "DEFINES",
                "requirement": "position and movement are expressed on the hex grid; 27 columns x 22 rows = 594 hexes, six-way adjacency",
                "status": "OPEN",
                "data": ["ingest/hexgraph_2nd_ed.json (594 hexes, 0 mutual-adjacency violations, parity proven against two independently fitted pixel grids)"],
                "note": "the 2nd Edition puts ODD columns half a hex LOWER - the OPPOSITE parity to the 3rd Edition. A shared hex-id helper across editions would silently mis-stagger one of them",
            },
            {
                "id": "S.8",
                "rules": ["MAP-02", "MAP-03", "MAP-04", "MAP-05", "TEC-01"],
                "obligation": "DEFINES",
                "requirement": "terrain vocabulary is exactly {Wood, Town, Road}; a hex is that terrain if ANY part of it carries the symbol; no other map feature may carry a rule",
                "status": "OPEN",
                "data": ["ingest/hexgraph_2nd_ed.json terrain_counts: clear 503, town 30, woods 56, woods_road 5"],
                "note": "the TEC's own footnote states the any-part rule for Woods a second time. map_grid.json rejected three woods_road candidates (1918, 2401, 2604) - the accept/reject boundary is a validator case",
            },
            {
                "id": "S.9",
                "rules": ["SCA-01", "SCA-02", "SCA-03"],
                "obligation": "DEFINES",
                "requirement": "scale: one turn = one hour, one hex = 400 m, one counter = one division",
                "status": "OPEN",
                "note": "no gate obligation beyond the turn count (T.1) and the display; recorded so the spine is complete",
            },
        ],
    },
    {
        "phase": "T",
        "name": "TURN STRUCTURE (the spine itself)",
        "when": "every Game-Turn",
        "citation": "p.1 col.3 TURNS OF PLAY",
        "cells": [
            {
                "id": "T.1",
                "rules": ["SEQ-01", "SEQ-05", "SEQ-04"],
                "obligation": "PROCEDURE",
                "requirement": "exactly ten Game-Turns (1 pm .. 10 pm); step 5 of each turn advances the Time Record; the game ends on a victory condition or at the end of Game-Turn 10, whichever comes first",
                "status": "OPEN",
                "data": ["ingest/timerecord_oob.json time_record: 10 slots, read individually"],
            },
            {
                "id": "T.2",
                "rules": ["SEQ-02", "SEQ-03", "SEQ-04"],
                "obligation": "PROCEDURE",
                "requirement": "Game-Turn = French Player-Turn then Allied Player-Turn; each Player-Turn = Movement Phase then Combat Phase; the printed five-step order",
                "status": "OPEN",
            },
            {
                "id": "T.3",
                "rules": ["SEQ-06", "MOV-04"],
                "obligation": "MUST NOT",
                "requirement": "no combat of any kind during a Movement Phase - an attack submission in a movement phase is refused",
                "status": "OPEN",
            },
            {
                "id": "T.4",
                "rules": ["SEQ-07"],
                "obligation": "MUST NOT",
                "requirement": "no movement during a Combat Phase except as directed by the CRT: the only position changes are retreat, disruption displacement and advance",
                "status": "OPEN",
                "note": "the advance (X.15) is OPTIONAL, not directed. Whether an optional advance falls inside SEQ-07's 'except as directed by the Combat Resolution Table' carve-out is the hinge of N7",
            },
            {
                "id": "T.5",
                "rules": ["SEQ-08", "MOV-03", "ART-15"],
                "obligation": "MUST NOT",
                "requirement": "no non-phasing action of any kind: no enemy movement during friendly movement, no reaction, no defensive fire, no defensive use of artillery range",
                "status": "OPEN",
                "note": "this is the rule the advance-after-Ar case collides with - see N7",
            },
            {
                "id": "T.6",
                "rules": ["VIC-07"],
                "obligation": "PROCEDURE",
                "requirement": "the game halts the INSTANT a victory condition is met, mid-phase if necessary",
                "status": "OPEN",
                "note": "combined with CBT-04 (results applied immediately, one attack at a time) the check runs between two attacks of the same combat phase",
            },
        ],
    },
    {
        "phase": "P1/P3",
        "name": "MOVEMENT PHASE (French / Allied)",
        "when": "step 1 and step 3 of every Game-Turn",
        "citation": "p.1 col.4 MOVEMENT",
        "cells": [
            {
                "id": "M.1",
                "rules": ["MOV-01", "MOV-14"],
                "obligation": "MAY",
                "requirement": "movement is never compulsory and never directionally constrained; a player may move none, some or all of his units",
                "status": "OPEN",
            },
            {
                "id": "M.2",
                "rules": ["MOV-02", "MOV-05", "MOV-15", "MOV-20", "PCS-03"],
                "obligation": "MUST NOT",
                "requirement": "flat 1 MP per hex entered in every terrain; hexes entered this Player-Turn <= printed Movement Allowance; unspent points are lost; no pooling between units, no carry-over between turns",
                "status": "OPEN",
                "note": "the TEC agrees: every enterable terrain costs exactly one MP per hex, and the road itself costs nothing and grants nothing (combat_charts O6). An engine that builds its movement predicate from the TEC alone will miss MOV-17",
            },
            {
                "id": "M.3",
                "rules": ["MOV-06"],
                "obligation": "MUST",
                "requirement": "a move is a path of consecutively adjacent hexes; no hex may be skipped",
                "status": "OPEN",
            },
            {
                "id": "M.4",
                "rules": ["MOV-07"],
                "obligation": "MAY",
                "requirement": "friendly-occupied hexes may be moved THROUGH",
                "status": "OPEN",
            },
            {
                "id": "M.5",
                "rules": ["MOV-08"],
                "obligation": "MUST NOT",
                "requirement": "enemy-occupied hexes may be neither entered nor passed through",
                "status": "OPEN",
            },
            {
                "id": "M.6",
                "rules": ["MOV-09", "MOV-07"],
                "obligation": "MUST NOT",
                "requirement": "one unit per hex",
                "status": "OPEN",
                "difficulty": "TWO PRINTED SENTENCES, TWO SCOPES. Sentence 1 bars finishing the MOVEMENT PHASE stacked; sentence 2 says 'Players may NOT place more than one unit in a given hex' with no time qualifier. Under reading A a unit may end its own move stacked with a friend and be moved off later in the same phase; under reading B it may not. MOV-07 grants pass-through, which reading B makes the only legal co-occupancy. Different legal move sets. Not on any prior list - see N1",
                "open_ruling": "NAW2-OR-2",
            },
            {
                "id": "M.7",
                "rules": ["MOV-10", "ZOC-04"],
                "obligation": "MUST",
                "requirement": "a unit entering any hex in an enemy Zone of Control MUST STOP there; entering is legal, continuing is not",
                "status": "OPEN",
            },
            {
                "id": "M.8",
                "rules": ["MOV-11", "ZOC-04"],
                "obligation": "MUST NOT",
                "requirement": "no unit may travel THROUGH an enemy-controlled hex",
                "status": "OPEN",
            },
            {
                "id": "M.9",
                "rules": ["MOV-11", "MOV-12", "ZOC-05", "ZOC-08"],
                "obligation": "MUST NOT",
                "requirement": "a unit in an enemy-controlled hex may not leave it by movement; the lock releases on exactly three events - the exerting enemy destroyed, the exerting enemy retreated, or the unit itself forced to retreat by combat",
                "status": "OPEN",
            },
            {
                "id": "M.10",
                "rules": ["MOV-13"],
                "obligation": "MUST NOT",
                "requirement": "a unit that BEGINS its Movement Phase in an enemy ZOC may not move at all that phase",
                "status": "OPEN",
                "note": "phase-start snapshot, not a live read. A unit that becomes ZOC-free mid-phase (impossible by movement alone, since only the phasing player moves) is still frozen; a unit whose enemy died in the previous combat phase is free",
            },
            {
                "id": "M.11",
                "rules": ["MOV-16", "MOV-18", "TEC-01"],
                "obligation": "MUST NOT",
                "requirement": "Woods entry is PROHIBITED; the only Woods hexes any unit may enter are those traversed by a Road",
                "status": "OPEN",
                "data": ["ingest/hexgraph_2nd_ed.json: 56 woods, 5 woods_road"],
            },
            {
                "id": "M.12",
                "rules": ["MOV-17"],
                "obligation": "MUST",
                "requirement": "a Woods/Road hex must be ENTERED and EXITED along the road: both hexsides used must be road hexsides",
                "status": "OPEN",
                "data": ["ingest/hexgraph_2nd_ed.json road_sides on the 5 woods_road hexes: 1014 [NW], 1101 [N,S], 1603 [NE,SW], 1701 [NE,S], 1702 [N,SW]"],
                "difficulty": "DATA VERIFICATION REQUIRED BEFORE ENCODING. Hex 1014 carries exactly ONE road hexside, which makes it a cul-de-sac under MOV-17: the only legal exit is back through the entry side. Either the printed road genuinely dead-ends there or the road_sides extraction is incomplete for that hex. Must be re-read off the print before this cell can close - see N2",
            },
            {
                "id": "M.13",
                "rules": ["MOV-19", "MOV-01"],
                "obligation": "MUST NOT",
                "requirement": "\"Once a unit has been moved, and the Player's hand is taken from the piece, it may not be moved any further during that Player-Turn, not may it change its move without the consent of the opposing Player.\"",
                "status": "OPEN",
                "difficulty": "PLATFORM-LEVEL QUESTION, NOT A GAME-LEVEL ONE. The trigger is physical (a hand leaving a piece) and the escape is social (opponent's consent); no gate can evaluate either from game state. Its subject matter is exactly what the platform's UNDO feature does - an undo IS 'changing a move'. That makes MOV-19 a question about the ENGINE's shipped feature set across ALL games, not a NAW encoding detail: either UNDO is a platform affordance that stands outside the printed rules (and is declared as such), or it is gated on an opponent-consent step. Bruce's call. Escalate before Fable touches undo semantics anywhere",
                "open_ruling": "NAW2-OR-3",
                "source": "rules_2nd_ed.json unenforceable_as_written (MOV-19); the row is absent from RULEBOOK_VERIFIED entirely",
            },
            {
                "id": "M.14",
                "rules": ["MOV-01", "MOV-19"],
                "obligation": "MAY",
                "requirement": "there is NO one-mover-at-a-time finality rule in this edition beyond MOV-19",
                "status": "OPEN",
                "note": "recorded as an explicit ABSENCE so no one imports Siege of Jerusalem's 8.2 by habit. Units may be moved in any order and a player may interleave partial moves, subject only to MOV-19 and to M.6's unresolved reading. If M.6 resolves to reading B, interleaving is constrained by stacking rather than by any movement-finality rule",
            },
        ],
    },
    {
        "phase": "P3r",
        "name": "REINFORCEMENT (Prussian entry - a sub-step of the Allied Movement Phase, Game-Turn 2)",
        "when": "beginning of the Allied Player-Turn of Game-Turn 2, once only",
        "citation": "p.1 col.3/col.4 SETTING UP THE GAME case (B.); printed Time Record 2 pm slot",
        "cells": [
            {
                "id": "R.1",
                "rules": ["REI-01", "SEQ-02"],
                "obligation": "PROCEDURE",
                "requirement": "the nine Prussian units enter at the beginning of the Allied Player-Turn of Game-Turn 2",
                "status": "OPEN",
                "data": ["ingest/timerecord_oob.json: all nine units printed in the single 2 pm slot; no other slot carries a unit", "ingest/oob_2nd_ed.json reinforcements (9 units, 34 CSP)"],
                "note": "exactly ONE reinforcement event exists in this edition - see the unreachable register for the staggered-arrival and 3 pm entry claims",
            },
            {
                "id": "R.2",
                "rules": ["REI-02"],
                "obligation": "MAY",
                "requirement": "entry anywhere along the East edge, at as many different points as desired",
                "status": "OPEN",
                "difficulty": "DATA GAP. hexgraph_2nd_ed.json flags the NORTH-edge exit hexes but carries no East-edge flag. The East-edge hex set must be derived from the grid extent (column 27) and CONFIRMED against the printed map before this cell can close; the jagged north and south edges make an off-by-one at the corners a live risk",
            },
            {
                "id": "R.3",
                "rules": ["REI-03", "MOV-05"],
                "obligation": "MUST",
                "requirement": "the act of placing a Prussian unit on the map expends one Movement Point of that unit's allowance",
                "status": "OPEN",
                "note": "printed 'extends'; registered as NAW2-SD-1, resolved on proven outcome-equivalence (the same page prints 'expends' for the mirror-image exit action). RULEBOOK_VERIFIED had silently normalised it - the normalisation, not the typo, is the lesson",
            },
            {
                "id": "R.4",
                "rules": ["REI-04"],
                "obligation": "MAY",
                "requirement": "Prussians may move and fight on their turn of entry like any other Allied unit; no arrival penalty beyond the 1 MP",
                "status": "OPEN",
            },
            {
                "id": "R.5",
                "rules": ["REI-06"],
                "obligation": "MUST NOT",
                "requirement": "entry may not be deliberately delayed",
                "status": "OPEN",
                "difficulty": "UNDEFINED CASE. The print states no relief for a position where entry is physically impossible - every East-edge hex enemy-occupied (MOV-08 bars entry into them), or enough of them in enemy ZOC that arriving units must stop on arrival (MOV-10). A gate that enforces a non-delayable entry must decide what it does when the obligation cannot be met. Ranked MATERIAL in rules_2nd_ed.json printed_defect_candidates",
                "open_ruling": "NAW2-OR-4",
            },
            {
                "id": "R.6",
                "rules": ["REI-07", "VIC-12"],
                "obligation": "MUST NOT",
                "requirement": "Prussians may not leave the map once brought on; no Allied unit may ever exit",
                "status": "OPEN",
            },
            {
                "id": "R.7",
                "rules": ["REI-05", "DEM-01", "VIC-01"],
                "obligation": "DEFINES",
                "requirement": "Prussian losses count as Allied losses - ONE loss ledger for British + Prussian against the 40-point threshold",
                "status": "OPEN",
            },
        ],
    },
    {
        "phase": "Z",
        "name": "ZONES OF CONTROL (continuous, both players' turns)",
        "when": "always",
        "citation": "p.1 col.5 ZONES OF CONTROL",
        "cells": [
            {
                "id": "Z.1",
                "rules": ["ZOC-01", "ZOC-02"],
                "obligation": "DEFINES",
                "requirement": "every unit of every type controls the six hexes directly adjacent to it, at all times, whether or not it is that player's turn; there is no negated or inactive ZOC state",
                "status": "OPEN",
            },
            {
                "id": "Z.2",
                "rules": ["ZOC-03"],
                "obligation": "DEFINES",
                "requirement": "friendly ZOCs never inhibit friendly units",
                "status": "OPEN",
            },
            {
                "id": "Z.3",
                "rules": ["ZOC-06"],
                "obligation": "DEFINES",
                "requirement": "ZOC does not stack or intensify; more than one unit may control the same hex and the test is set membership",
                "status": "OPEN",
            },
            {
                "id": "Z.4",
                "rules": ["ZOC-07"],
                "obligation": "DEFINES",
                "requirement": "the ZOC rule triggers on unit-to-unit adjacency, never on hex-to-hex ZOC overlap between non-adjacent opposing units",
                "status": "OPEN",
                "note": "absent from RULEBOOK_VERIFIED's ZOC summary; carried here so it is not lost",
            },
            {
                "id": "Z.5",
                "rules": ["ZOC-01", "MOV-16"],
                "obligation": "DEFINES",
                "requirement": "ZOC is projected into all six adjacent hexes with NO terrain exception - including non-Road Woods hexes that no unit could legally enter",
                "status": "OPEN",
                "difficulty": "NAMED TRAP. Enforceable exactly as written, but an encoder who 'reasonably' exempts impassable hexes is silently wrong, and the error is invisible in movement (nobody can enter those hexes anyway) while being decisive in RETREAT: X.4 bars retreating into an enemy ZOC, so a phantom-free woods hex would create retreat destinations the printed rules forbid. Flagged in rules_2nd_ed.json unenforceable_as_written",
            },
            {
                "id": "Z.6",
                "rules": ["ZOC-08", "ZOC-05"],
                "obligation": "MUST NOT",
                "requirement": "the lock is MUTUAL: neither of two adjacent opposing units may leave the other's presence until one is destroyed or retreated by combat",
                "status": "OPEN",
            },
        ],
    },
    {
        "phase": "P2/P4",
        "name": "COMBAT PHASE - declaration and assignment",
        "when": "step 2 and step 4 of every Game-Turn",
        "citation": "p.1 col.5/col.6 COMBAT",
        "cells": [
            {
                "id": "C.1",
                "rules": ["CBT-01", "PCS-02"],
                "obligation": "PROCEDURE",
                "requirement": "one attack = the summed Combat Strength of the attacking unit(s) compared to the summed Combat Strength of the adjacent defending unit(s), stated as a ratio",
                "status": "OPEN",
            },
            {
                "id": "C.2",
                "rules": ["CBT-02", "CBT-EX-01", "CRT-01"],
                "obligation": "PROCEDURE",
                "requirement": "the ratio is simplified to a printed column, ALWAYS rounded in favour of the defender; attacks worse than 1:5 are treated as 1:5 and better than 6:1 as 6:1",
                "status": "OPEN",
                "data": ["ingest/crt_2nd_ed.json (10 columns, 6 rows, 60 cells, four independent readings, clamp footnote verbatim)"],
                "note": "the arithmetic expression that reproduces all 27 printed examples is OURS, not printed: floor(a/d):1 when a>=d, else 1:ceil(d/a). EX-13 (2 vs 3 -> 1:2) is the ONLY printed witness that the adverse side rounds by ceil rather than floor. A single witness - treat accordingly and write the validator against the whole 27-example corpus",
            },
            {
                "id": "C.3",
                "rules": ["CBT-03", "CRT-01"],
                "obligation": "PROCEDURE",
                "requirement": "one six-sided die per attack, rolled by the attacking player, read against the odds column",
                "status": "OPEN",
                "note": "engine-owned dice: seeded, logged, replayable (spec #11). No client-side rolls",
            },
            {
                "id": "C.4",
                "rules": ["CBT-04"],
                "obligation": "MUST",
                "requirement": "the indicated action is taken IMMEDIATELY, and applied to the board, before any other attack in that Combat Phase is resolved",
                "status": "OPEN",
            },
            {
                "id": "C.5",
                "rules": ["CBT-05", "ART-01"],
                "obligation": "MUST",
                "requirement": "attacking units must be adjacent to the enemy unit attacked, during the attacker's own Combat Phase; the sole exception is artillery bombardment at exactly two hexes",
                "status": "OPEN",
            },
            {
                "id": "C.6",
                "rules": ["CBT-06", "CBT-07", "CBT-10"],
                "obligation": "MUST",
                "requirement": "EVERY enemy unit adjacent to any phasing unit must be attacked this phase; EVERY phasing unit adjacent to any enemy must participate in an attack this phase; no unit may appear in more than one attack, on either side",
                "status": "OPEN",
                "difficulty": "THE COMBAT PHASE IS A GLOBAL ASSIGNMENT PROBLEM, NOT A PER-ACTION CHECK. Taken together these three rules require a PARTITION of the contact graph: every adjacent enemy covered exactly once as a defender, every adjacent friendly used exactly once as an attacker, subject to the adjacency constraints of CBT-11 (all attackers adjacent to the defender) and CBT-12 (all defenders adjacent to the attacker). A gate that validates one attack at a time CANNOT enforce this: an individually legal first attack can strand a later unit with no legal partner, and the illegality only becomes visible at the end of the phase. Deciding legality means searching for a COMPLETE assignment before admitting the first attack. Worse, the sheet prints NO RELIEF CLAUSE for a position in which no complete assignment exists, and no tie-break for choosing among several. The engine must either solve the assignment (and refuse a first attack that provably strands the phase) or declare the position undefined - and 'declare undefined' is an umpire, which spec #13 forbids. The printed examples confirm the shape rather than relieving it: both partitions of the 16-unit battle line use all 9 attackers exactly once and cover all 7 defenders exactly once. ART-07 widens the search space rather than narrowing it: an artillery unit standing adjacent to an enemy may discharge its obligation by bombarding a DIFFERENT enemy two hexes away, provided some other friendly covers the adjacent one. This is the single largest engineering item in the encoding",
                "open_ruling": "NAW2-OR-5",
                "source": "rules_2nd_ed.json unenforceable_as_written (CBT-06 + CBT-07 + CBT-10)",
            },
            {
                "id": "C.7",
                "rules": ["CBT-04", "CBT-06", "CBT-07"],
                "obligation": "MUST",
                "requirement": "when the mandatory-attack obligations are evaluated: at the start of the Combat Phase, or re-evaluated after every applied result",
                "status": "OPEN",
                "difficulty": "OPEN RULING, NOT A CODING CHOICE. CBT-04 applies each result to the board before the next attack is declared, so the set of 'enemy units to which there are friendly units adjacent' CHANGES DURING THE PHASE - a Dr moves a defender away, a DE removes it, an advance (X.15) moves a victor into new contact. The sheet never says whether CBT-06/07 are fixed at phase start or re-read after each result. Reading A (fixed at phase start) makes the assignment computable once, but can oblige an attack on a unit that has since retreated out of contact. Reading B (live re-evaluation) makes the obligation set a moving target and can CREATE new obligations mid-phase that no unit is left to satisfy, because CBT-10 has already spent the neighbours. The two readings give different legal move sets from the same board position. Must be ruled before any combat code is written; it is the precondition for C.6, not a detail of it",
                "open_ruling": "NAW2-OR-6",
                "source": "rules_2nd_ed.json unenforceable_as_written (CBT-04 vs CBT-06)",
            },
            {
                "id": "C.8",
                "rules": ["CBT-08"],
                "obligation": "MAY",
                "requirement": "the attacking player resolves his attacks in any order he wishes",
                "status": "OPEN",
                "note": "absent from RULEBOOK_VERIFIED; distinct from CBT-09's choice of pairings. Free order plus immediate results (C.4) is what makes C.7's timing question decisive",
            },
            {
                "id": "C.9",
                "rules": ["CBT-09"],
                "obligation": "MAY",
                "requirement": "the attacking player chooses which attacking units attack which defending units",
                "status": "OPEN",
            },
            {
                "id": "C.10",
                "rules": ["CBT-11"],
                "obligation": "MAY",
                "requirement": "many attackers may combine against one defender, provided every attacker is adjacent to that defender (artillery bombardment excepted); their strengths total into one figure",
                "status": "OPEN",
            },
            {
                "id": "C.11",
                "rules": ["CBT-12"],
                "obligation": "MAY",
                "requirement": "one attacker may attack two or more defenders it is adjacent to; the defenders' strengths total into one figure",
                "status": "OPEN",
            },
            {
                "id": "C.12",
                "rules": ["CBT-13"],
                "obligation": "MAY",
                "requirement": "deliberately poor-odds ('diversionary') attacks are legal; the gate must never require odds maximisation or refuse a suicidal attack",
                "status": "OPEN",
                "note": "a real refusal risk: an engine that helpfully rejects a 1:5 attack breaks the printed permission. EX-16 prints a 1:4 attack",
            },
            {
                "id": "C.13",
                "rules": ["CBT-17"],
                "obligation": "MUST NOT",
                "requirement": "Combat Strength is used as an integral whole and may never be split across two attacks",
                "status": "OPEN",
            },
            {
                "id": "C.14",
                "rules": ["CBT-18", "TEC-01"],
                "obligation": "PROCEDURE",
                "requirement": "a DEFENDING unit in a Town hex or a Woods/Road hex doubles its Combat Strength; attacking FROM such terrain confers nothing",
                "status": "OPEN",
                "note": "NAW2-D4 RULED (Bruce, 2026-08-14): follow the chart, which prints 'Towns & Woods/Roads' as one row. The rules text case (J.) names Towns only. Both are printed components of the same 1971 folio and no documentary ladder separates them; the 27 printed examples are silent (no example places a defender in a Woods/Road hex). Blast radius 5 hexes of 594. The predicate keys on the DEFENDER's hex only - EX-03 proves an attacker in a Town is NOT doubled, EX-04 proves the Town defender IS. Escalation to the game/module creator remains outstanding per spec #21 as amended",
                "open_ruling": "NAW2-D4 (ruled; escalation outstanding)",
            },
            {
                "id": "C.15",
                "rules": ["CBT-10"],
                "obligation": "MUST NOT",
                "requirement": "no defending unit may be attacked more than once per turn, nor any attacking unit attack more than once per turn",
                "status": "OPEN",
                "note": "the print says 'per turn' where the neighbouring cases say Combat Phase. A unit can only be attacked in its enemy's Combat Phase and there is exactly one of those per Game-Turn, so the two readings coincide in play; the wording is loose, not defective. Recorded so no one re-derives it",
            },
            {
                "id": "C.16",
                "rules": ["CBT-EX-01", "CRT-01"],
                "obligation": "PROCEDURE",
                "requirement": "the validation corpus: 27 printed worked examples (folio p.2) plus the 8-vs-3 example printed inside the COMBAT column must all reproduce under the encoded odds arithmetic",
                "status": "OPEN",
                "data": ["ingest/worked_examples.json (27 examples)", "ingest/example_check.json (27/27 odds reproduced under both readings of D4)"],
                "difficulty": "VALIDATION COVERAGE IS PARTIAL AND MUST BE STATED, NOT ASSUMED (hard rule #1). What the corpus does NOT exercise: the CRT itself (no example states a die roll or a result code, so AE/Ar/EX/Dr/DE are validated only by the printed table); CRT columns 1:5, 1:3, 5:1 and 6:1; the clamp footnote (most extreme printed odds are 1:4 and 4:1); Zones of Control (never drawn); a Woods/Road defender (D4 is untouched by the corpus); nationality (attacker/defender is coded by grey tint, so no example constrains which side attacks); and terrain of any hex other than the two Town hexes. Enforcement of anything on that list ships on the printed table alone, not on a worked example",
            },
        ],
    },
    {
        "phase": "P2a/P4a",
        "name": "COMBAT PHASE - artillery",
        "when": "inside every Combat Phase",
        "citation": "p.1 col.6/col.7 ARTILLERY",
        "cells": [
            {
                "id": "A.1",
                "rules": ["ART-01"],
                "obligation": "MAY",
                "requirement": "artillery may attack by bombarding from EXACTLY two hexes' distance, as well as adjacently",
                "status": "OPEN",
            },
            {
                "id": "A.2",
                "rules": ["ART-02", "CBT-07"],
                "obligation": "MUST",
                "requirement": "artillery adjacent to an enemy unit is bound by the mandatory-participation rule like any other unit",
                "status": "OPEN",
            },
            {
                "id": "A.3",
                "rules": ["ART-06", "CBT-06"],
                "obligation": "MAY",
                "requirement": "bombardment is never mandatory; an enemy within two hexes creates NO obligation",
                "status": "OPEN",
                "note": "this is the scope limit that stops CBT-06 from generating range-2 obligations. Absent from RULEBOOK_VERIFIED; without it the assignment problem of C.6 would be strictly larger",
            },
            {
                "id": "A.4",
                "rules": ["ART-07"],
                "obligation": "MAY",
                "requirement": "an artillery unit adjacent to an enemy may discharge its participation obligation by bombarding a DIFFERENT enemy two hexes away, provided some other friendly unit attacks the adjacent enemy",
                "status": "OPEN",
                "difficulty": "feeds directly into C.6: the assignment search must consider range-2 substitutions for adjacent artillery, which enlarges the space of complete assignments and means an assignment solver that only pairs adjacent units will refuse legal phases",
            },
            {
                "id": "A.5",
                "rules": ["ART-03", "ART-04", "ART-09"],
                "obligation": "DEFINES",
                "requirement": "a unit that attacked from range 2 is never destroyed or retreated by the result: AE and Ar do not touch it, and its strength still counts in the odds",
                "status": "OPEN",
            },
            {
                "id": "A.6",
                "rules": ["ART-10"],
                "obligation": "MUST",
                "requirement": "artillery attacking from an adjacent position suffers all combat results like any other unit",
                "status": "OPEN",
            },
            {
                "id": "A.7",
                "rules": ["ART-12", "ART-05"],
                "obligation": "MUST",
                "requirement": "artillery immunity never propagates: non-artillery partners always suffer all results, whatever the distance of the artillery",
                "status": "OPEN",
                "note": "absent from RULEBOOK_VERIFIED",
            },
            {
                "id": "A.8",
                "rules": ["ART-05", "EXR-01"],
                "obligation": "PROCEDURE",
                "requirement": "on an EX result, the attacker's loss is made up only from units directly involved in that attack; bombarding artillery contributes strength and pays nothing",
                "status": "OPEN",
                "difficulty": "UNDEFINED CASE WITH A REAL EXPLOIT. If EVERY attacker in the attack is bombarding artillery, an EX eliminates the defender AT NO COST - the print names no one to pay the exchange, and ART-03/ART-09 explicitly exempt the only participants. The 3rd Edition [6.3] closes this; the 2nd Edition never does. It is reachable in play: 4 French and 3 Allied artillery units are in the OOB, and the 2:1/4:1/5:1 columns carry EX on a 5, 3:1 and 4:1/5:1 on a 6. A gate must decide - defender eliminated free, or the attack refused, or the EX read as a DE - and each choice changes the 40-point victory race (V.2). This is exactly the class spec #21 as amended sends to the game creator and which BLOCKS playability until resolved",
                "open_ruling": "NAW2-OR-7",
                "source": "rules_2nd_ed.json printed_defect_candidates kind=undefined case (ART-05)",
            },
            {
                "id": "A.9",
                "rules": ["ART-11", "RET-01"],
                "obligation": "MAY",
                "requirement": "a bombarding artillery unit may VOLUNTARILY elect to suffer an 'Attacker Retreat' result it is otherwise immune to",
                "status": "OPEN",
                "difficulty": "the print gives no purpose, no restriction and no chooser for the direction of a VOLUNTARY retreat. X.3 gives retreat direction to the VICTORIOUS player - which on an Ar is the defender - so a voluntary Ar would hand the enemy the right to move the electing unit. Whether the electing player instead picks his own direction is undefined. Not on any prior list - see N5",
                "open_ruling": "NAW2-OR-8",
            },
            {
                "id": "A.10",
                "rules": ["ART-13", "ART-14"],
                "obligation": "MUST NOT",
                "requirement": "a BOMBARDING artillery unit may attack only a single unit (never part of a one-to-many attack); an ADJACENT artillery unit may attack as many units as it is adjacent to",
                "status": "OPEN",
                "note": "the bar is on the bombarding unit's participation, so it also constrains mixed attacks (A.11): a combined attack that includes a bombarding gun cannot have two defenders",
            },
            {
                "id": "A.11",
                "rules": ["ART-08"],
                "obligation": "MAY",
                "requirement": "artillery may attack alone, with other artillery, or with infantry/cavalry, combining adjacent attackers and range-2 bombardment in ONE combined strength",
                "status": "OPEN",
                "data": ["worked_examples.json: EX-09 and EX-24 print exactly this combination"],
            },
            {
                "id": "A.12",
                "rules": ["ART-15", "SEQ-08"],
                "obligation": "MUST NOT",
                "requirement": "artillery under attack suffers all results like any other unit and may NOT use its two-hex range defensively; there is no defensive fire",
                "status": "OPEN",
                "note": "closes as structurally impossible if the engine has no non-phasing action at all (T.5) - but that argument must be asserted by a validator, not assumed",
            },
            {
                "id": "A.13",
                "rules": ["ART-16"],
                "obligation": "MAY",
                "requirement": "bombardment may fire over intervening units (enemy or friendly) and over Town hexes",
                "status": "OPEN",
            },
            {
                "id": "A.14",
                "rules": ["ART-17", "TEC-01"],
                "obligation": "MUST NOT",
                "requirement": "artillery may not fire over a Woods hex to attack a unit two hexes away",
                "status": "OPEN",
                "difficulty": "AMBIGUOUS AT THE GEOMETRY. On a hex grid two hexes apart there are either one or two intervening hexes depending on the axis. The print never says whether ONE Woods hex among two candidate paths blocks the shot, or whether every path must be blocked. The two readings give different legal bombardment sets, and 56 of 594 hexes are Woods, so the difference is not marginal. Flagged MATERIAL in rules_2nd_ed.json; listed in unenforceable_as_written. Note also that the TEC states the same bar on its Woods row, so both printed sources agree on the rule and disagree with neither - the ambiguity is in the geometry, not between components",
                "open_ruling": "NAW2-OR-9",
            },
            {
                "id": "A.15",
                "rules": ["ART-18", "CBT-14"],
                "obligation": "MUST NOT",
                "requirement": "artillery that is not adjacent to the defender may never take the post-combat advance",
                "status": "OPEN",
            },
            {
                "id": "A.16",
                "rules": ["DIS-01", "ART-02"],
                "obligation": "MUST NOT",
                "requirement": "a disrupted artillery unit may NOT fire in the Combat Phase in which it was disrupted",
                "status": "OPEN",
                "difficulty": "two undefined edges (disruption_verified U6): whether the ban applies to a gun that had ALREADY fired earlier in the same Combat Phase (the ban is stated forward-looking), and whether a disrupted gun still counts as an adjacent participant for the CBT-07 obligation - if it does not, a disruption can make an otherwise complete assignment (C.6) impossible mid-phase, which is C.7's timing question in its sharpest form",
                "open_ruling": "NAW2-OR-10",
            },
        ],
    },
    {
        "phase": "P2b/P4b",
        "name": "COMBAT PHASE - result application (retreat, disruption, advance)",
        "when": "immediately after every resolved attack",
        "citation": "map sheet p.5 EXPLANATION OF RESULTS + RETREAT AND ADVANCE AS A RESULT OF COMBAT (both printed on the British/Prussian half only)",
        "cells": [
            {
                "id": "X.1",
                "rules": ["EXR-01", "CRT-01"],
                "obligation": "PROCEDURE",
                "requirement": "the five printed result codes and their meanings: AE Attacker Eliminated, Ar Attacker Retreats one hex, EX Exchange, Dr Defender Retreats one hex, DE Defender Eliminated",
                "status": "OPEN",
                "note": "the 3rd Edition renames these Ae/Ee/De - a RENAME, not a rules change. Map them; never branch on them",
            },
            {
                "id": "X.2",
                "rules": ["EXR-01", "RET-01"],
                "obligation": "PROCEDURE",
                "requirement": "retreat distance is ONE hex (stated in the Explanation of Results for both Ar and Dr; the Retreat and Advance block never restates a distance)",
                "status": "OPEN",
            },
            {
                "id": "X.3",
                "rules": ["RET-01"],
                "obligation": "PROCEDURE",
                "requirement": "the VICTORIOUS player decides the retreat direction - for Ar as well as Dr, because the paragraph is headed 'When units are forced to retreat' and is not scoped to defenders",
                "status": "OPEN",
                "note": "consequence the chart never states in so many words (combat_charts O2): on an Ar the victorious player is the DEFENDER, so the NON-PHASING player makes a decision inside the phasing player's Combat Phase. That is a decisional pending the engine must present to the non-phasing seat",
            },
            {
                "id": "X.4",
                "rules": ["RET-01"],
                "obligation": "MUST NOT",
                "requirement": "four printed bars: a retreat may not go into an enemy Zone of Control, off the map, into non-Road Woods, or into an enemy-occupied hex",
                "status": "OPEN",
                "note": "reads directly off Z.1/Z.5: because every unit projects ZOC into all six adjacent hexes with no terrain exception, a unit adjacent to two or more enemies will frequently have NO legal retreat hex and be eliminated by X.6. That is the printed consequence, not a bug - and it makes Z.5's phantom-ZOC trap decisive",
            },
            {
                "id": "X.5",
                "rules": ["RET-01"],
                "obligation": "MAY",
                "requirement": "nothing requires a retreat to move the unit AWAY from the attacker; within the four bars, sideways and forward retreats are legal",
                "status": "OPEN",
                "note": "combat_charts O4. A gate that computes 'directly away' will be silently wrong and will eliminate units the rules would have saved",
            },
            {
                "id": "X.6",
                "rules": ["RET-01"],
                "obligation": "PROCEDURE",
                "requirement": "if no path of retreat is open aside from the forbidden hexes, the retreating unit is ELIMINATED and removed immediately",
                "status": "OPEN",
            },
            {
                "id": "X.7",
                "rules": ["DIS-01"],
                "obligation": "PROCEDURE",
                "requirement": "DISRUPTION: if the only safe hex is occupied by another, uninvolved FRIENDLY unit, that unit is pushed out by the retreating unit; the victorious player moves it back as if it were retreating, and the retreating unit takes its place",
                "status": "OPEN",
                "note": "printed exactly once in the whole folio, on the map sheet, on the British/Prussian half only. A French player reading only his own half of the sheet is never shown it (NAW2-SD-2)",
            },
            {
                "id": "X.8",
                "rules": ["DIS-01"],
                "obligation": "MUST NOT",
                "requirement": "the disrupted unit may not be forced into enemy units, Zones of Control, or 'woods'",
                "status": "OPEN",
                "difficulty": "NAW2-SD-3, OPEN, BLOCKS PLAYABILITY. The retreat bar two paragraphs earlier prints 'non-Road Woods'; the disruption bar prints bare lower-case 'woods'. Reading A treats the shorthand as elision (disruption is barred exactly where retreat is barred); reading B takes it literally (disruption is barred from ALL woods, a HARSHER constraint than retreat). The same sentence also OMITS 'off the map', which the retreat bar includes (U1) - so the disruption bar is either deliberately narrower on one axis and wider on another, or loosely drafted. Blast radius 5 Woods/Road hexes in the displacement branch only, and it interacts with C.14: under Bruce's D4 ruling a Woods/Road hex is defensively FAVOURABLE, which sharpens whether a unit may be shoved into one. Awaiting Bruce",
                "open_ruling": "NAW2-SD-3",
            },
            {
                "id": "X.9",
                "rules": ["DIS-01"],
                "obligation": "PROCEDURE",
                "requirement": "the disrupted unit is 'moved back ... as if it were retreating'",
                "status": "OPEN",
                "difficulty": "UNDEFINED (U3): back relative to WHAT? The disrupted unit fought no combat, so it has no attacker to be pushed away from. The print names the victorious player as the chooser but gives no direction rule at all. Combined with X.5 (retreats need not move away) the practical reading is 'any hex passing the X.8 bars, chosen by the victorious player' - but that is a reading, not the print",
                "open_ruling": "NAW2-OR-11",
            },
            {
                "id": "X.10",
                "rules": ["DIS-01"],
                "obligation": "PROCEDURE",
                "requirement": "if the push cannot be made legally, the uninvolved unit is NOT disrupted, stays put, and the ORIGINAL retreating unit is eliminated instead",
                "status": "OPEN",
            },
            {
                "id": "X.11",
                "rules": ["DIS-01"],
                "obligation": "PROCEDURE",
                "requirement": "chain-reaction disruption: a disrupted unit may itself disrupt a further friendly unit when that is the only safe path open to it",
                "status": "OPEN",
                "difficulty": "UNDEFINED AT DEPTH (U4, U7). The print does not say whether each link of the chain is subject to the same X.8 bar and the same X.10 fallback, nor - if the chain fails at depth N - WHICH unit is eliminated: X.10's subject is 'the unit which was forced to retreat as a result of combat', which in a chain has no unique referent. And S5 says a disrupted unit CAN disrupt others, which reads permissive inside an otherwise mandatory procedure - is the chain compulsory when it is the only option, or may the victorious player decline it and eliminate instead? A recursive displacement engine cannot be written until this is ruled",
                "open_ruling": "NAW2-OR-12",
            },
            {
                "id": "X.12",
                "rules": ["DIS-01"],
                "obligation": "DEFINES",
                "requirement": "'uninvolved' friendly unit",
                "status": "OPEN",
                "difficulty": "NEVER DEFINED (U5). Uninvolved in the combat just resolved, or in any combat this Combat Phase - a unit that has already attacked, or that is a defender in a battle not yet resolved? Under CBT-06/CBT-07 nearly every unit in contact is 'involved' in something, so the narrow reading can leave no eligible disruptee at all",
                "open_ruling": "NAW2-OR-13",
            },
            {
                "id": "X.13",
                "rules": ["DIS-01"],
                "obligation": "DEFINES",
                "requirement": "how disruption ENDS",
                "status": "OPEN",
                "difficulty": "NO PRINTED END CONDITION. The rule states no removal step, no duration and no end-of-phase clause. The only durable consequence it names is bounded by its own wording - artillery may not fire 'in the Combat Phase in which they were disrupted' (A.16). The punched set contains exactly ONE marker (the turn marker), so there is no physical disrupted-unit counter and no component evidence for a persistent state. The conservative encoding is a per-Combat-Phase flag with no other effect - but it is a reading",
                "open_ruling": "NAW2-OR-14",
            },
            {
                "id": "X.14",
                "rules": ["EXR-01"],
                "obligation": "PROCEDURE",
                "requirement": "EX: the defender is eliminated and the attacker suffers a loss AT LEAST equal in Strength Points, made up ONLY from units directly involved in that attack; the attacker will sometimes be forced to lose more than the defender; both sides' losses are removed immediately; a surviving attacker may then advance",
                "status": "OPEN",
                "difficulty": "DECISIONAL OBLIGATION WITH NO PRINTED MINIMALITY RULE. 'AT LEAST equal' states a floor and no ceiling, and the print never says who selects the units nor that he must pick the cheapest sufficient subset. A player could deliberately over-pay - which is not idle, because both 40-point ledgers (V.1/V.2/V.3) are the victory condition, so over-paying can hand the opponent the race or trigger demoralization. The gate must present the selection as a constrained pending and must decide whether over-payment is legal. Not on any prior list - see N4",
                "open_ruling": "NAW2-OR-15",
            },
            {
                "id": "X.15",
                "rules": ["CBT-14", "CBT-16", "RET-01"],
                "obligation": "MAY",
                "requirement": "OPTIONAL ADVANCE: whenever a hex is vacated as a result of combat, the victorious unit responsible may advance into it; the option must be exercised IMMEDIATELY; a unit is never forced to advance; never more than one hex; advances are not regular Movement and expend no Movement Points",
                "status": "OPEN",
            },
            {
                "id": "X.16",
                "rules": ["CBT-15", "RET-01"],
                "obligation": "MAY",
                "requirement": "the advance is legal even if the advancing unit is still in an enemy ZOC AND/OR the vacated hex is in an enemy ZOC",
                "status": "OPEN",
                "note": "SOURCE-LOCATION CORRECTION. rules_2nd_ed.json flagged the second clause as an unsourced extension in RULEBOOK_VERIFIED, because the page-1 text (CBT-15) grants the permission only for the advancing unit's own ZOC situation. The page-5 chart DOES print 'and/or if the vacated hex is in an Enemy Zone of Control' verbatim. So the clause is printed, on the other sheet - not an invention, but it must be cited to p.5 and never to p.1. Also note the advance is the ONE way a unit may enter a hex in an enemy ZOC and later act, which is why it interacts so hard with X.17",
            },
            {
                "id": "X.17",
                "rules": ["RET-01", "CBT-06", "CBT-07"],
                "obligation": "MUST NOT",
                "requirement": "an advancing unit may not participate in another attack OR defense in the Combat Phase in which it advanced, even if the advance places it next to enemy units whose battles are yet to be resolved",
                "status": "OPEN",
                "difficulty": "DIRECT COLLISION WITH THE MANDATORY-ATTACK CLUSTER (combat_charts O5). CBT-07 says every friendly unit adjacent to an enemy MUST participate in an attack this phase; this paragraph says an advanced unit MUST NOT. An advance can also drop the advancing unit next to an as-yet-unattacked enemy, which under a live reading of CBT-06 (see C.7) creates an obligation that the advanced unit is forbidden to satisfy and that its neighbours may already have spent themselves on (CBT-10). The folio never reconciles the two. The bar on 'defense' is stranger still: a unit cannot decline to be a defender, so under an Ar-advance (X.15 applied to the non-phasing victor) the sentence forbids something the rules do not let a player choose. Which of C.7's two readings is adopted decides whether this is a contradiction or merely a sequencing constraint",
                "open_ruling": "NAW2-OR-16",
            },
            {
                "id": "X.18",
                "rules": ["RET-01", "SEQ-08", "SEQ-07", "CBT-14"],
                "obligation": "MAY",
                "requirement": "who may advance after an Ar result",
                "status": "OPEN",
                "difficulty": "NEW FINDING - see N7. RET-01 grants the advance to 'the victorious unit responsible for the Enemy elimination or retreat' whenever a hex is vacated as a result of combat. On an Ar the vacated hex is the ATTACKER's, and the victorious unit is the DEFENDER - a NON-PHASING unit. SEQ-08 states flatly that no Allied movement takes place during the French Player-Turn and vice-versa, and SEQ-07 permits movement in a Combat Phase only 'as directed by the Combat Resolution Table' - an optional advance is permitted, not directed. So either (a) the non-phasing player advances, contradicting SEQ-08 on its face, or (b) the advance is phasing-player-only, which the Retreat and Advance block's own wording does not say and which would make ART-11 (a bombarding gun VOLUNTARILY electing an Ar) pointless as a tactical device. A printed contradiction between page 1 and page 5 that no prior bite named; it must be ruled before the advance pending is built, and it decides which SEAT the engine prompts",
                "open_ruling": "NAW2-OR-17",
            },
            {
                "id": "X.19",
                "rules": ["VIC-13", "RET-01"],
                "obligation": "DEFINES",
                "requirement": "a unit forced to retreat off the map counts as DESTROYED, never as an exiting unit, for either side",
                "status": "OPEN",
                "note": "candidate proven-outcome-equivalence: X.4 already bars retreating off the map and X.6 eliminates a unit with no legal retreat, so the state VIC-13 describes cannot be entered and its accounting consequence (counted as destroyed) is exactly what X.6 produces anyway. If that argument survives review the cell closes vacuously - but it is an argument, not an encoding, and it stays OPEN until a validator asserts that no code path can retreat a unit off the map",
            },
        ],
    },
    {
        "phase": "V",
        "name": "VICTORY AND EXIT (continuous; checked immediately)",
        "when": "continuously, mid-phase",
        "citation": "p.1 col.7/col.8 HOW THE GAME IS WON + Cases",
        "cells": [
            {
                "id": "V.1",
                "rules": ["VIC-05"],
                "obligation": "PROCEDURE",
                "requirement": "both players keep a running total of Combat Strength Points lost by BOTH sides - two ledgers are part of game state",
                "status": "OPEN",
                "data": ["ingest/oob_2nd_ed.json totals: French 89 CSP at start, Allied 73 + 34 Prussian = 107"],
                "note": "the printed Demoralization Scale is a 1..40 track; the punched set has exactly ONE marker (the turn marker), so the scale's own instruction is to use a destroyed counter. No component evidence constrains the engine here",
            },
            {
                "id": "V.2",
                "rules": ["VIC-01", "VIC-02"],
                "obligation": "DEFINES",
                "requirement": "FRENCH VICTORY: destroy 40 Allied Combat Strength Points AND exit seven French units off the North edge, on or before Game-Turn 10, with the 40 reached BEFORE the Allies destroy 40 French points",
                "status": "OPEN",
            },
            {
                "id": "V.3",
                "rules": ["VIC-03"],
                "obligation": "DEFINES",
                "requirement": "ALLIED VICTORY: destroy 40 French Combat Strength Points before the enemy destroys 40 Allied points; no exit requirement",
                "status": "OPEN",
            },
            {
                "id": "V.4",
                "rules": ["VIC-04"],
                "obligation": "DEFINES",
                "requirement": "DRAW: neither side reaches 40, or the French reach 40 but fail to exit seven units",
                "status": "OPEN",
            },
            {
                "id": "V.5",
                "rules": ["VIC-08"],
                "obligation": "MUST",
                "requirement": "French units may exit ONLY from the arrow-marked North-edge hexes",
                "status": "OPEN",
                "data": ["ingest/map_grid.json editions.2nd.exit_hexes: 11 hexes, 0101..1101, read off the folio arrows; columns 12+ of row 01 carry no arrow", "ingest/timerecord_oob.json exit_arrows_corroboration: 11 arrows counted independently"],
                "note": "E41 is closed for the 2nd Edition with an enumerated set - do NOT reuse the 3rd Edition's 9 exit hexes",
            },
            {
                "id": "V.6",
                "rules": ["VIC-09", "MOV-05"],
                "obligation": "MUST",
                "requirement": "the act of exiting expends one Movement Point",
                "status": "OPEN",
            },
            {
                "id": "V.7",
                "rules": ["VIC-10"],
                "obligation": "MUST NOT",
                "requirement": "exited units may not return to the game",
                "status": "OPEN",
            },
            {
                "id": "V.8",
                "rules": ["VIC-11"],
                "obligation": "MAY",
                "requirement": "exits are unconstrained in timing and grouping - not all in one turn, not all from one hex, before and/or after the 40-point mark",
                "status": "OPEN",
            },
            {
                "id": "V.9",
                "rules": ["VIC-12", "REI-07"],
                "obligation": "MUST NOT",
                "requirement": "Allied units may NEVER exit the map, even to avoid destruction",
                "status": "OPEN",
            },
            {
                "id": "V.10",
                "rules": ["VIC-06", "VIC-13"],
                "obligation": "PROCEDURE",
                "requirement": "EXITED is a third unit state, neither on-map nor lost: exited French units are not counted in French losses and are kept on display off the map",
                "status": "OPEN",
                "note": "absent from RULEBOOK_VERIFIED. The printed Exited French Units box has exactly seven blank cells - a physical mirror of the victory requirement",
            },
            {
                "id": "V.11",
                "rules": ["VIC-14", "EXR-01"],
                "obligation": "PROCEDURE",
                "requirement": "if BOTH sides reach the 40-point level at exactly the same moment (only possible on an EX), the French win if seven units are already exited, otherwise the Allies win",
                "status": "OPEN",
                "note": "the only simultaneity the print admits, and it exists precisely because EX removes both sides' losses at one instant (X.14)",
            },
            {
                "id": "V.12",
                "rules": ["MOV-17", "VIC-08", "VIC-09"],
                "obligation": "MUST",
                "requirement": "exit hex 1101 is a Woods/Road hex whose road hexsides are N (off the north edge) and S",
                "status": "OPEN",
                "difficulty": "INTERACTION, NEW - see N3. Under M.12 a Woods/Road hex must be entered and exited along the road, so the eleventh exit hex is enterable ONLY from the south along the road and exitable only northwards off the map. The other ten exit hexes are clear terrain and carry no such constraint. Whether the off-map step counts as an 'exit along the road' for MOV-17 is not stated anywhere; the reading is natural but unprinted, and it decides whether one of the seven required French exits can be made through 1101 at all",
                "open_ruling": "NAW2-OR-18",
            },
        ],
    },
    {
        "phase": "D",
        "name": "ALLIED DEMORALIZATION (continuous latch)",
        "when": "the instant the trigger is met, mid-phase",
        "citation": "p.1 col.8 ALLIED DEMORALIZATION",
        "cells": [
            {
                "id": "D.1",
                "rules": ["DEM-01", "REI-05"],
                "obligation": "PROCEDURE",
                "requirement": "trigger: the French destroy 40 Allied Combat Strength Points FIRST but have not yet exited seven units; the game continues and ALL Allied units, Prussians included, are DEMORALIZED",
                "status": "OPEN",
            },
            {
                "id": "D.2",
                "rules": ["DEM-02", "DEM-08", "CBT-04"],
                "obligation": "PROCEDURE",
                "requirement": "demoralization takes effect IMMEDIATELY, even in the middle of a Player-Turn - between two attacks of the same Combat Phase if necessary; no delay",
                "status": "OPEN",
            },
            {
                "id": "D.3",
                "rules": ["DEM-03", "DEM-08"],
                "obligation": "DEFINES",
                "requirement": "a one-way latch: once demoralized the Allies stay demoralized for the rest of the game",
                "status": "OPEN",
            },
            {
                "id": "D.4",
                "rules": ["DEM-04", "DEM-09", "VIC-04"],
                "obligation": "DEFINES",
                "requirement": "after the latch the Allied victory branch is closed: destroying 40 French points is no longer an Allied victory, does not demoralize the French, and does not relieve the effects; the best Allied outcome is a Draw",
                "status": "OPEN",
                "note": "DEM-04 is a DERIVED state (a consequence of DEM-05 + VIC-04), never an independent gate check - flagged in rules_2nd_ed.json unenforceable_as_written. Encoding it as a check would be a fabricated rule",
            },
            {
                "id": "D.5",
                "rules": ["DEM-05", "VIC-03"],
                "obligation": "DEFINES",
                "requirement": "there is no French demoralized state",
                "status": "UNREACHABLE",
                "evidence": "printed, twice, in the 2nd Edition itself. DEM-05: 'The French army is never demoralized (for the point at which they would be demoralized, fulfills the Allied Victory Condition).' And the one board state that could otherwise reach it - the Allies passing 40 French points AFTER their own latch - is closed by DEM-09 in the same column: that achievement 'does not ... Demoralize the French or in any way relieve the effects of Allied Demoralization.' Both citations are verbatim from rules_2nd_ed.json rows DEM-05 and DEM-09; no board position, victory branch or demoralization path in this edition produces a demoralized French army. Evidence kind: printed rule closing its own state space, with the single bypass explicitly foreclosed by an adjacent printed rule",
                "note": "the engine must therefore have NO French demoralization code path at all, and a validator must assert its absence - an unreachable cell is a claim about the engine as much as about the rules",
            },
            {
                "id": "D.6",
                "rules": ["DEM-06", "DEM-07", "CRT-01"],
                "obligation": "PROCEDURE",
                "requirement": "while demoralized: every Allied attack is resolved one odds-column LOWER and every French attack one odds-column HIGHER than the computed odds",
                "status": "OPEN",
                "difficulty": "UNDEFINED AT BOTH ENDS OF THE TABLE. The printed columns run 1:5 .. 6:1. An Allied attack already at 1:5 has no column below it and a French attack already at 6:1 has none above it, and the print states nothing for either case. The CRT's clamp footnote does NOT obviously cover it: it is worded 'attacks EXECUTED AT worse than 1 to 5 are treated as 1 to 5', which speaks to the raw ratio a player computes, not to a column produced by a shift applied afterwards. So there are at least three readings - clamp at the printed end, treat the shift as impossible (refuse or leave unshifted), or extrapolate a column the table does not have - and they give different combat outcomes in exactly the situations demoralization is meant to punish. Ranked MATERIAL for a gate in rules_2nd_ed.json printed_defect_candidates and listed in unenforceable_as_written. Reachable: demoralization is a normal course of this game and the 1:5 and 6:1 columns are both printed",
                "open_ruling": "NAW2-OR-19",
            },
        ],
    },
]

STATE_LEDGER = [
    {
        "state": "unit hex",
        "written_by": "setup (S.1), movement (M.*), reinforcement entry (R.1-R.3), retreat (X.2-X.6), disruption displacement (X.7-X.11), advance (X.15-X.18)",
        "read_by": "everything",
        "status": "OPEN",
        "note": "three distinct writers inside the Combat Phase alone, two of them driven by the NON-owning player (X.3 retreat direction, X.7 disruption push)",
    },
    {
        "state": "movement points spent, per unit, per Player-Turn",
        "written_by": "movement (M.2), map entry (R.3), map exit (V.6)",
        "read_by": "movement legality (M.2), exit legality (V.6)",
        "status": "OPEN",
        "note": "explicitly NOT written by retreat or advance - CBT-16 puts both outside regular Movement",
    },
    {
        "state": "ZOC map (derived, continuous)",
        "written_by": "any change of unit hex, by any writer, including mid-Combat-Phase results",
        "read_by": "movement stop/lock (M.7-M.10), retreat bars (X.4), disruption bars (X.8), advance permission (X.16)",
        "status": "OPEN",
        "note": "must be recomputed after EVERY applied result, because CBT-04 applies results one at a time; a ZOC map cached at phase start would be wrong for the second attack onward",
    },
    {
        "state": "phase-start ZOC snapshot (movement freeze)",
        "written_by": "start of each Movement Phase",
        "read_by": "MOV-13 freeze (M.10)",
        "status": "OPEN",
        "note": "MOV-13 keys on the situation at the BEGINNING of the phase, so this is a separate snapshot from the live ZOC map above. Conflating them is a silent-incorrectness risk of exactly the class B18 closed in Siege of Jerusalem",
    },
    {
        "state": "units that have attacked / been attacked this Combat Phase",
        "written_by": "attack resolution (C.4)",
        "read_by": "the once-per-turn bar (C.15), the mandatory-assignment check (C.6)",
        "status": "OPEN",
    },
    {
        "state": "mandatory-attack obligation set",
        "written_by": "phase start and/or every applied result - UNDECIDED, this is C.7",
        "read_by": "every attack verdict, and the end-of-phase completion check (C.6)",
        "status": "OPEN",
        "note": "the single most consequential undecided piece of state in the encoding. Its write schedule is an open ruling, not an implementation detail",
    },
    {
        "state": "units that have advanced this Combat Phase",
        "written_by": "advance (X.15)",
        "read_by": "the no-further-participation bar (X.17), which the assignment check (C.6) must also honour",
        "status": "OPEN",
    },
    {
        "state": "disrupted-this-Combat-Phase flag",
        "written_by": "disruption displacement (X.7, X.11)",
        "read_by": "artillery firing ban (A.16)",
        "status": "OPEN",
        "note": "no printed end condition (X.13) and NO physical counterpart - the punched set has exactly one marker, the turn marker",
    },
    {
        "state": "loss ledgers, one per side, in Combat Strength Points",
        "written_by": "eliminations and EX losses (X.1, X.6, X.10, X.14)",
        "read_by": "victory (V.2, V.3, V.4, V.11), demoralization trigger (D.1)",
        "status": "OPEN",
        "note": "Prussian losses write the ALLIED ledger (R.7). Exited French units do NOT write the French ledger (V.10)",
    },
    {
        "state": "exited French units (count and identity)",
        "written_by": "exit (V.5, V.6)",
        "read_by": "victory (V.2), the draw branch (V.4), the demoralization trigger (D.1), the tie-break (V.11)",
        "status": "OPEN",
    },
    {
        "state": "Allied demoralization latch",
        "written_by": "the trigger test after every loss (D.1, D.2)",
        "read_by": "every odds computation thereafter (D.6), the victory branches (D.4)",
        "status": "OPEN",
        "note": "one-way; must be tested between attacks, not at end of phase (D.2)",
    },
    {
        "state": "Prussian reinforcement pool",
        "written_by": "setup staging (S.3 - reading undecided), entry (R.1)",
        "read_by": "entry legality (R.1-R.5), the non-delay obligation (R.5)",
        "status": "OPEN",
    },
    {
        "state": "turn and phase counter",
        "written_by": "the five-step sequence (T.1, T.2)",
        "read_by": "everything phase-gated; the turn-10 stop (T.1); the Game-Turn 2 entry window (R.1)",
        "status": "OPEN",
    },
    {
        "state": "pendings (retreat direction, disruption push, EX loss selection, advance decision)",
        "written_by": "combat resolution (X.3, X.7, X.14, X.15)",
        "read_by": "the propose/submit router",
        "status": "OPEN",
        "note": "at least two of these are prompted to the NON-phasing seat (X.3 on an Ar, X.7 whenever the victor is the defender). Per the standing GUI rule every mid-phase pending is a modal",
    },
]

OBLIGATION_FLAGS = [
    {
        "class": "automatic (engine does it, no player input)",
        "cells": ["T.1 turn advance", "T.6 immediate victory check", "C.3 die roll", "D.1/D.2 demoralization latch", "X.6 elimination when no retreat is open", "X.10 elimination when the push fails", "V.1 loss ledgers"],
        "status": "all OPEN",
    },
    {
        "class": "obligatory-decisional (the player MUST act and the gate must refuse everything else)",
        "cells": ["C.6 the assignment itself", "X.3 retreat direction (victorious player, either seat)", "X.7/X.9 disruption push direction", "X.11 chain continuation", "X.14 EX loss selection", "A.9 voluntary Ar election"],
        "status": "all OPEN; three of them (X.9, X.11, X.14) have no printed decision rule at all",
    },
    {
        "class": "optional-decisional (the gate must permit and must never require)",
        "cells": ["M.1 movement", "C.12 poor-odds attacks", "A.3 bombardment", "X.15 the advance", "V.8 exit timing"],
        "status": "all OPEN. C.12 and X.15 are the two most likely to be broken by a helpful engine that refuses a bad choice",
    },
    {
        "class": "ordered / quantified",
        "cells": ["T.2 the five-step sequence", "C.4 one attack at a time, results applied immediately", "C.8 free attack order", "R.1 entry at the beginning of the Allied Player-Turn of Game-Turn 2", "M.14 NO movement-finality rule exists"],
        "status": "all OPEN",
    },
    {
        "class": "prohibitive (the gate refuses the action)",
        "cells": ["T.3", "T.4", "T.5", "M.5", "M.8", "M.9", "M.10", "M.11", "M.12", "C.13", "C.15", "A.10", "A.12", "A.14", "A.15", "A.16", "X.4", "X.8", "X.17", "V.7", "V.9"],
        "status": "all OPEN",
    },
]

UNREACHABLE_REGISTER = [
    {
        "subject": "French demoralization (the only phase-spine cell marked UNREACHABLE: D.5)",
        "evidence": "DEM-05 verbatim: 'The French army is never demoralized (for the point at which they would be demoralized, fulfills the Allied Victory Condition).' The single bypass - the Allies passing 40 French points after their own latch - is foreclosed verbatim by DEM-09 in the same column. Two printed rules of this edition close the state space between them",
        "kind": "printed rule closing its own state space",
    },
    {
        "subject": "the Grouchy variant in its entirety (variant counters '5v', the variant arrival schedule, and every rule the sheet carries)",
        "evidence": "edition_diff.json module defect M3: 'the Grouchy variant does not exist in the Second Edition at all. A module labelled 2nd Ed ships a variant board for a subsystem that edition never had.' The sheet both modules ship is a retimed edit of the printed 3rd Edition [9.2]-[9.4] text (M2), with every turn number shifted one turn earlier and the counters relabelled 'Var' where printed [9.1] specifies '5v'. NOT CITABLE for anything, and out of edition scope entirely",
        "kind": "out-of-edition component; module scope error",
    },
    {
        "subject": "staggered or later Prussian arrivals; any reinforcement event other than the single Game-Turn 2 entry",
        "evidence": "ingest/timerecord_oob.json: all ten Time Record slots were read individually off the native scan; all nine Prussian units are printed in the single 2 pm slot and NO unit is printed in any other slot. Corroborated on the Oliver module map. The 2nd Edition has exactly one reinforcement event",
        "kind": "printed component enumeration (Time Record), two witnesses",
    },
    {
        "subject": "Prussian entry on Game-Turn 3 (3 pm)",
        "evidence": "edition_diff.json M4: the davejm 3rd Edition module's map Time Record marks Prussian entry at 3 pm while its own bundled Grouchy sheet says Game-Turn Two. That is a 3rd Edition module contradicting itself; the 2nd Edition folio prints 2 pm on the Time Record and 'the beginning of the Allied Player's second turn' in the rules. Out of edition and not citable here",
        "kind": "out-of-edition; module self-contradiction",
    },
    {
        "subject": "every 3rd Edition mechanic that has no 2nd Edition counterpart - including [6.3]'s closure of the all-bombardment Exchange (A.8), [5.6]'s no-bombarding-from-an-enemy-ZOC restriction (diff row D9), and [6.5] displacement",
        "evidence": "edition_diff.json, 41 diff rows over both printed editions; the 2nd Edition is encoded from its own printed folio only. A 3rd Edition rule may NEVER be used to fill a 2nd Edition gap - that is precisely the gap-fill the authority ladder forbids ('a non-primary asset may be cited only for a claim a primary witness independently covers')",
        "kind": "edition scope",
    },
    {
        "subject": "the 3rd Edition map, its 380 hexes, its 9 exit hexes and its opposite column parity",
        "evidence": "ingest/map_grid.json edition_comparison: '2nd Ed 27x22 = 594 hexes; 3rd Ed 23x(17/16) = 380 hexes. The 3rd Ed map is a SMALLER battlefield, not a renumbering of the same field.' The two editions' column parities are OPPOSITE",
        "kind": "edition scope; measured",
    },
    {
        "subject": "any additional scenario, campaign game or optional rule",
        "evidence": "the 2nd Edition folio prints exactly one game: ten Game-Turns, 1 pm to 10 pm, one at-start setup read off the map art, one reinforcement event. The 127-row rules index contains no scenario, campaign or optional-rule section, and the Time Record has exactly ten slots. This matrix's per-scenario scope is therefore the whole edition",
        "kind": "printed component enumeration",
    },
    {
        "subject": "the 2020 Sabin house rules ('Double Defence / Except Cavalry with 2020 Rules') and every other third-party redraw content",
        "evidence": "edition_diff.json M1: the davejm module's TEC.png is a redraw that bakes in Philip Sabin's April 2020 tweaks, omits the 2nd Edition's Woods/Road doubling and asserts a Woods/Road LOS block. 'must not be used as the source for E14 or E15.' authority_ladder.json tier T3c, flagged contaminated",
        "kind": "contaminated non-primary asset; never citable",
    },
]

NEW_GAPS = [
    {
        "id": "N1",
        "cell": "M.6",
        "rules": ["MOV-09", "MOV-07"],
        "finding": "MOV-09 is two sentences with two different scopes - 'may not finish their Movement Phase in the same hex' and the unqualified 'Players may NOT place more than one unit in a given hex'. Whether a unit may END ITS OWN MOVE stacked with a friendly and be moved off later in the same phase is undecided, and the two readings give different legal move sets",
        "class": "ambiguity in the original published game",
        "prior_lists": "none - not in printed_defect_candidates, not in unenforceable_as_written",
    },
    {
        "id": "N2",
        "cell": "M.12",
        "rules": ["MOV-17"],
        "finding": "Woods/Road hex 1014 carries exactly ONE road hexside (NW) in hexgraph_2nd_ed.json. Under MOV-17's enter-and-exit-along-the-road rule that makes it a cul-de-sac whose only legal exit is the entry side. Either the printed road dead-ends there or the road_sides extraction is incomplete for that hex",
        "class": "data verification item (possible ingest gap, possible printed map fact)",
        "prior_lists": "none",
    },
    {
        "id": "N3",
        "cell": "V.12",
        "rules": ["MOV-17", "VIC-08", "VIC-09"],
        "finding": "the eleventh exit hex, 1101, is the only Woods/Road exit hex; its road hexsides are N (off the map) and S. MOV-17 therefore constrains entry to the southern road hexside, and nothing printed says whether the off-map step counts as exiting 'along the road'. One of the seven required French exits may or may not be makeable through it",
        "class": "unstated interaction between the movement rules and the victory conditions",
        "prior_lists": "none",
    },
    {
        "id": "N4",
        "cell": "X.14",
        "rules": ["EXR-01"],
        "finding": "the EX loss is 'AT LEAST equal' with no ceiling and no printed minimality requirement, and the print never names who selects which attacking units pay. Deliberate over-payment is therefore arguably legal, and it is not idle - both 40-point ledgers ARE the victory condition, so over-paying can hand the opponent the race or trip demoralization",
        "class": "undefined case in the original published game",
        "prior_lists": "none",
    },
    {
        "id": "N5",
        "cell": "A.9",
        "rules": ["ART-11", "RET-01"],
        "finding": "ART-11 lets a bombarding gun VOLUNTARILY elect an Ar it is immune to, but RET-01 gives retreat direction to the VICTORIOUS player - who on an Ar is the defender. So a voluntary election hands the enemy the right to move the electing unit, unless the election also carries the direction. Undefined",
        "class": "undefined case in the original published game",
        "prior_lists": "none",
    },
    {
        "id": "N6",
        "cell": "X.17",
        "rules": ["RET-01", "CBT-06", "CBT-07"],
        "finding": "the advance bar on further participation collides with the mandatory-attack cluster - CARRIED, not new: recorded as combat_charts.json observation O5. Restated here as a matrix cell because O5 is an observation in an ingest file and would otherwise never be closed by anything",
        "class": "carried",
        "prior_lists": "combat_charts.json O5",
    },
    {
        "id": "N7",
        "cell": "X.18",
        "rules": ["RET-01", "SEQ-08", "SEQ-07", "CBT-14"],
        "finding": "ADVANCE AFTER AN Ar IS A PAGE-1 vs PAGE-5 CONTRADICTION. RET-01 grants the advance to the victorious unit whenever a hex is vacated by combat; on an Ar the vacated hex is the attacker's and the victor is the non-phasing defender. SEQ-08 states flatly that no non-phasing movement occurs, and SEQ-07 admits only movement DIRECTED by the CRT, which an optional advance is not. Either the non-phasing player advances (contradicting SEQ-08 on its face) or the advance is phasing-only (which the chart does not say, and which would make ART-11 pointless). It decides which seat the engine prompts",
        "class": "contradiction between two printed components of the same edition",
        "prior_lists": "adjacent to combat_charts.json O5, which notes the Ar/Dr asymmetry but does not name the SEQ-08 contradiction",
    },
]

OPEN_RULINGS = [
    ("NAW2-SD-3", "X.8", "disruption bar says 'woods', retreat bar says 'non-Road Woods'; and 'off the map' is absent from the disruption bar", "RESOLVED reading A - publisher clarification (SPI 1979 6.4/4.2/6.5): the displaced unit is barred exactly where a retreating unit is; Woods/Road across its road hexside. ENFORCED (validate_battle)"),
    ("NAW2-D4", "C.14", "TEC vs rules text on Woods/Road defence doubling", "RULED - Bruce 2026-08-14, follow the chart; corroborated by the printed 1979 sheet. ENFORCED"),
    ("NAW2-OR-1", "S.3", "SET-02 Prussian staging: off-map or literal East-edge placement", "RESOLVED A - SPI 1979 7.0 reinforcements ENTER during a Movement Phase: off-map pool. ENFORCED"),
    ("NAW2-OR-2", "M.6", "MOV-09's two stacking sentences, two scopes", "RESOLVED A - SPI 1979 4.4 'never END a Movement Phase stacked'; wedge-proof by the un-stack matching check. ENFORCED"),
    ("NAW2-OR-3", "M.13", "MOV-19 touch-move - PLATFORM-LEVEL: whether the engine's UNDO is legal under the printed rules, in this game and every other", "OPEN - Bruce's platform call (rec A: UNDO is a declared platform affordance). The game clause of MOV-19 is enforced; this is the ONE cell still open"),
    ("NAW2-OR-4", "R.5", "REI-06 non-delayable entry when entry is physically impossible", "RESOLVED A - SPI 1979 7.2 entry bars; a unit with no legal hex waits, logged. ENFORCED"),
    ("NAW2-OR-5", "C.6", "the mandatory-assignment problem: no printed relief when no complete assignment exists, no tie-break when several do", "CLOSED BY PROOF (Bruce 2026-08-17): with the pairs fixed at phase start the live contact graph has no isolated vertex, so a star partition (one-on-many / many-on-one attacks) always exists; the gate's forward check keeps every reachable position completable; complete_assignment() constructs it. ENFORCED (validate_battle: 150 positions + 6 full games)"),
    ("NAW2-OR-6", "C.7", "are the CBT-06/07 obligations fixed at phase start or re-evaluated after each result", "RULED A - Bruce 2026-08-17: fixed at Combat Phase start, resolved on the live board, lapse on lost contact. ENFORCED"),
    ("NAW2-OR-7", "A.8", "ART-05: EX with only bombarding attackers kills the defender at no cost", "RESOLVED A (literal) - SPI 1979 6.8 confirms. ENFORCED"),
    ("NAW2-OR-8", "A.9", "ART-11 voluntary Ar: who chooses the direction", "RESOLVED A - the owner (SPI 1979 6.8 'may voluntarily retreat'). ENFORCED"),
    ("NAW2-OR-9", "A.14", "ART-17: does one Woods hex among two candidate intervening hexes block the shot", "RESOLVED - SPI 1979 Terrain Key example: open if either candidate is clear; Woods-Road blocks. ENFORCED"),
    ("NAW2-OR-10", "A.16", "disrupted artillery: already-fired case, and whether it still counts as an adjacent participant for CBT-07", "RESOLVED A - forward-looking ban only. ENFORCED"),
    ("NAW2-OR-11", "X.9", "disruption direction - 'moved back' relative to what", "RESOLVED A - any safe hex, victor chooses (SPI 1979 6.5 has no direction rule). ENFORCED"),
    ("NAW2-OR-12", "X.11", "chain-reaction disruption: per-link bars, who dies when the chain fails at depth N, and whether the chain is compulsory", "RESOLVED A - SPI 1979 6.5: chain when only path; failure at any depth = the original retreater eliminated. ENFORCED"),
    ("NAW2-OR-13", "X.12", "'uninvolved' is never defined", "RESOLVED broad - any friendly unit not in the attack being resolved (SPI 1979 6.5). ENFORCED"),
    ("NAW2-OR-14", "X.13", "disruption has no printed end condition", "RESOLVED A - per-Player-Turn flag, only effect the artillery fire ban. ENFORCED"),
    ("NAW2-OR-15", "X.14", "EX loss selection: who chooses, and is over-payment legal", "RESOLVED A - attacker chooses whole units from the attack, >= PRINTED defender strength (SPI 1979 6.3), over-payment legal. ENFORCED"),
    ("NAW2-OR-16", "X.17", "advance bar vs mandatory participation", "RULED A - Bruce 2026-08-17: an advanced unit leaves the obligation list. ENFORCED"),
    ("NAW2-OR-17", "X.18", "advance after an Ar vs SEQ-08's no-non-phasing-action rule", "RESOLVED A - SPI 1979 6.3 'Defending unit has the option to advance after combat'; Stephen Oliver (BGG 2018) concurs. ENFORCED"),
    ("NAW2-OR-18", "V.12", "does an off-map step from exit hex 1101 satisfy MOV-17's along-the-road exit", "RESOLVED legal - SPI 1979 4.2 (the north hexside IS the road; the arrow is printed in the hex). ENFORCED"),
    ("NAW2-OR-19", "D.6", "the demoralization odds shift at the ends of the printed table, and whether the CRT clamp footnote governs a shifted column", "RESOLVED A - clamp at the printed end (SPI 1979 6.2). ENFORCED"),
]

VM = "games/napoleon-at-waterloo/validate_movement.py"
VD = "games/napoleon-at-waterloo/validate_data.py"
ENFORCED = {
    "S.1": ("scenario_2nd_ed.json units (44) built by build_data.py from oob_2nd_ed.json; engine/naw.py new_game", VD + ": at-start roster (hex, side, CS, MA, type, designation) == oob 44/44; no two units share a hex; strengths 89/73/34"),
    "S.2": ("scenario units carry side Fr/Al; game.json sides.detect_tokens", VD + ": every counter image resolves to its printed side; 26 French / 18 British at start"),
    "T.1": ("engine/naw.py _end_player_turn/_game_end: 10 Game-Turns then over (victory-halt = T.6, bite 6)", VM + ": ten Game-Turns then the game ends; no action after"),
    "T.2": ("engine/naw.py propose/end_movement/end_phase: French then Allied, Movement then Combat", VM + ": turn structure block"),
    "M.1": ("engine/naw.py: no obligation to move; end_movement legal with unmoved units", VM + ": random walk ends phases with unmoved units; end_movement always legal"),
    "M.2": ("engine/naw.py dests(): 1 MP per hex (gamespec.move_cost, TEC costs), MA cap, per-Player-Turn reset", VM + ": open field costs == hex distance, none beyond MA; gate == independent hexgraph oracle on >1500 positions"),
    "M.3": ("engine/naw.py dests(): Dijkstra over adjacent hexes only", VM + ": oracle BFS agreement"),
    "M.4": ("engine/naw.py dests(): friendly hexes traversable", VM + ": moves THROUGH the friendly hex"),
    "M.5": ("engine/naw.py dests(): enemy hexes never entered or traversed", VM + ": enemy-occupied hex never entered"),
    "M.6": ("engine/naw.py dests(): friendly-occupied destinations excluded (reading B - one unit per hex at all times); NAW2-OR-2 stays open, reading A is a one-line switch", VM + ": may not end the move on a friendly unit; gate refuses with MOV-09"),
    "M.7": ("engine/naw.py dests(): a hex in enemy ZOC is a terminal destination", VM + ": may move INTO the enemy ZOC / must STOP on entering it"),
    "M.8": ("engine/naw.py dests(): no expansion from an EZOC hex", VM + ": hexes beyond the ZOC ring unreachable through it"),
    "M.9": ("engine/naw.py in_ezoc(): a unit in enemy ZOC has no destinations; the lock is a live read of enemy positions so it releases exactly when the exerting enemy is gone (combat removal = bite 5)", VM + ": unit adjacent to an enemy may not move at all"),
    "M.10": ("engine/naw.py in_ezoc() at proposal time (only the phasing player moves, so live == phase-start)", VM + ": MOV-13 refusal with citation"),
    "M.11": ("terrain.json woods = 99 MP (never affordable) + gate reads terrain; MOV-18", VM + ": no Woods hex is ever a destination"),
    "M.12": ("terrain.json sides: road / woods_edge on the 5 Woods/Road hexes; gamespec.move_cost prohibit; N2 CLOSED 2026-08-17 - hex 1014 is a genuine printed cul-de-sac (road ends at Hougoumont), verified on Oliver's map scan", VM + ": 1014 only via 0913; 1503-1603-1702-1701-1801 = 1,2,3,4 MP; 1101 only from 1102"),
    "M.14": ("engine/naw.py: no finality rule beyond MOV-19; any order, interleaving allowed", VM + ": random walk interleaves units freely"),
    "Z.1": ("gamespec.zoc_hexes: every unit, all six neighbours, always", VM + ": an enemy unit controls exactly its six adjacent hexes"),
    "Z.2": ("engine/naw.py _board_sets: only enemy ZOC is computed", VM + ": friendly ZOC never inhibits friendly movement"),
    "Z.3": ("gamespec.zoc_hexes returns a set", VM + ": set membership (ZOC-06)"),
    "Z.4": ("engine/naw.py in_ezoc(): tests the unit's own hex against enemy ZOC only", VM + ": ZOC tests are unit-hex membership"),
    "Z.5": ("gamespec.zoc_hexes projects into every neighbour incl. Woods (no terrain exception)", VM + ": ZOC is projected into adjacent Woods hexes too"),
    "Z.6": ("engine/naw.py in_ezoc(): symmetric by construction (adjacency)", VM + ": mutual lock - unit adjacent to enemy may not move"),
    "V.5": ("engine/naw.py exit_options(): only game.json exit.hexes (11 arrowed hexes)", VM + ": exit from a non-arrowed hex refused; column 12+ not an exit hex"),
    "V.6": ("engine/naw.py exit_options(): +1 MP, must fit within MA", VM + ": exit costs 3 hexes + 1; unit at 0305 cannot exit"),
    "V.7": ("engine/naw.py _apply exit: unit deleted, exited ledger", VM + ": an exited unit is gone for good"),
    "V.8": ("engine/naw.py: exit legal in any own Movement Phase, any arrowed hex, no grouping", VM + ": exits at any time in the random walk"),
    "V.9": ("engine/naw.py _propose_exit: exit_side Fr only (VIC-12; REI-07)", VM + ": Allied units may never exit"),
    "V.12": ("engine/naw.py: 1101 enterable only from 1102 along the road (terrain.json sides), exit crosses the N road hexside - LEGAL; NAW2-OR-18 kept open for Bruce's confirmation (the exit arrow is printed inside the hex)", VM + ": exit through 1101 from 1102 = 2 MP; from 1002 = 3 MP via 1102"),
}
NOTES = {
    "T.4": "movement refusal in the Combat Phase is enforced (validate_movement: movement refused in the Combat Phase [SEQ-07]); the retreat/disruption/advance half lands with bite 5",
    "T.5": "non-phasing movement is refused (validate_movement: Allied move during the French Player-Turn refused [SEQ-08]); the combat-side clauses land with bites 3-5",
    "M.13": "the first clause IS enforced: once moved, a unit may not be moved again that Player-Turn (validate_movement: MOV-19 refusal); the consent-to-change clause remains the platform UNDO question",
    "S.3": "the engine stages the Prussians OFF-MAP (reserve pool, due Game-Turn 2) - the reading consistent with REI-01; NAW2-OR-1 stays open",
    "V.10": "the exited ledger exists (engine/naw.py s.exited, separate from s.dead); the loss ledger and its exclusion of exited units land with bite 6",
}


VC = "games/napoleon-at-waterloo/validate_combat.py"
ENFORCED.update({
    "C.1": ("engine/naw.py attack_strength/defense_strength/battle_check: summed strengths, ratio", VC + ": 27/27 printed examples through battle_check"),
    "C.2": ("engine/naw.py odds_column: floor(a/d):1 else 1:ceil(d/a), clamped to the printed columns", VC + ": rounding pairs incl. EX-13 (2 vs 3 = 1:2), clamp 1 vs 40 = 1:5 / 30 vs 1 = 6:1, the 8-vs-3 rules example"),
    "C.13": ("engine/naw.py battle_check: a unit named twice is refused; strengths enter whole", VC + ": a unit named twice is refused [CBT-17]"),
    "C.14": ("engine/naw.py defense_strength: x2 when the DEFENDER's hex kind is town or woods_road (game.json combat.terrain_effects, ruling NAW2-D4); attackers never doubled", VC + ": Town defender 6->12, Woods/Road 1014 defender 6->12, clear 6, attacker in Town 6 vs 6 = 1:1 (EX-03/EX-04)"),
    "C.16": ("engine/naw.py battle_check + odds_column + crt_result", VC + ": 27/27 printed examples reproduce their odds; 60/60 CRT cells == crt_2nd_ed.json; corpus gaps stated (no die/result printed, columns 1:5/1:3/5:1/6:1 and the clamp untested by print)"),
})
NOTES.update({
    "C.3": "roll_die (gate.py) is seeded/counted/replayable (validate_combat: 300 rolls 1..6, same seed same rolls); the per-attack roll lands with the battle action (bite 5)",
    "C.5": "predicate BUILT + validated (battle_check: adjacent legal, non-adjacent infantry refused, artillery at exactly two hexes) - flips to ENFORCED when the battle action makes battle_check the door (bite 5)",
    "C.10": "predicate built + validated (several attackers vs one defender, all adjacent) - flips with the battle action",
    "C.11": "predicate built + validated (one attacker vs several adjacent defenders; several-on-several EX-14 under the every-attacker-adjacent-to-every-defender reading) - flips with the battle action",
    "C.12": "validated: a 1:4 attack is legal, battle_check never refuses on odds - flips with the battle action",
    "C.15": "predicate built + validated via the fought/defended flags - the flags are set by the battle action (bite 5)",
    "A.1": "predicate built + validated: distance exactly 2 legal, 3 refused - flips with the battle action",
    "A.10": "predicate built + validated: bombarding gun vs two defenders refused (ART-13); adjacent gun vs two adjacent defenders legal (ART-14)",
    "A.11": "predicate built + validated: adjacent cavalry 1 + bombarding artillery 3 = 4:1 (EX-09/EX-24)",
    "A.13": "predicate built + validated: fires over an intervening enemy unit and over a Town hex",
    "A.14": "predicate built under the STRICT reading (any candidate intervening Woods hex blocks) - NAW2-OR-9 open; validated on a real Woods pair",
})

VV = "games/napoleon-at-waterloo/validate_victory.py"
ENFORCED.update({
    "S.3": ("engine/naw.py: the nine Prussians are an OFF-MAP reserve pool due Game-Turn 2 (SPI 1979 7.0: reinforcements ENTER during a Movement Phase - NAW2-OR-1 A)", VV + ": nine Prussians staged OFF the map, due Game-Turn 2"),
    "S.4": ("engine/naw.py new_game: turn 1, French mover, Movement Phase; no setup phase exists", "validate_movement.py: game opens with the French Movement Phase of Game-Turn 1"),
    "S.5": ("scenario_2nd_ed.json fixes both sides' setup at once; no setup action exists in the gate (simultaneity is trivial)", "validate_data.py: at-start roster 44/44"),
    "S.6": ("scenario units carry cls + stats{att,def,ma}; nothing else is read by any verdict", "validate_data.py: Combat Strength serves attack and defence alike; classes partition every piece"),
    "S.7": ("terrain.json 594 hexes; gamespec grid adjacency == the proved hexgraph", "validate_data.py: engine adjacency == PROVED hexgraph 594/594"),
    "S.8": ("terrain.json kinds {clear, town, woods, woods_road}; hexside features road/woods_edge; nothing else carries a rule", "validate_data.py: terrain counts 503/30/56/5; sides = exactly the Woods/Road hexsides"),
    "S.9": ("scenario turn_labels 1 pm..10 pm; scale is descriptive only (no rule keys on it)", "validate_data.py: turn labels = the printed Time Record"),
    "T.6": ("engine/naw.py _check_victory runs after every elimination and every exit and sets over/winner at once", VV + ": Allied win immediately on the fortieth French point; French win the instant the seventh exit follows demoralization"),
    "R.1": ("engine/naw.py _propose_reinforce: pool due Game-Turn 2, Allied Movement Phase only, refused before", VV + ": Game-Turn 1 refused [REI-01]; Game-Turn 2 accepted"),
    "R.2": ("engine/naw.py entry_hexes: column 27 = the East edge (all 22 hexes of the last column of the 594-hex graph; 4 are Woods), any number of entry points", VV + ": entry hexes = column 27 minus the 4 Woods hexes = 18; column 26 refused"),
    "R.3": ("engine/naw.py _apply reinforce: moved[pid] = 1 MP (game.json reinforcements.entry_cost_mp; NAW2-SD-1 'extends' = expends)", VV + ": Prussian enters at 2705 for 1 MP"),
    "R.4": ("engine/naw.py budget = MA - moved: an entered unit may still move MA-1 and fight (no done flag on entry)", VV + ": it may still move with MA-1 this turn"),
    "R.5": ("engine/naw.py end_movement refused while any due unit has a legal entry hex; no legal hex -> the unit waits (NAW2-OR-4 A, logged)", VV + ": end_movement REFUSED while due Prussians can still enter; entry physically impossible -> accepted, Prussians wait"),
    "R.6": ("engine/naw.py _propose_exit: exit_side Fr only", VV + ": Prussians may never leave the map [REI-07/VIC-12]"),
    "R.7": ("engine/naw.py _eliminate: losses[unit side]; Prussians carry side Al", VV + ": Prussian losses count as Allied losses"),
    "V.1": ("engine/naw.py s.losses {Fr, Al} incremented by printed Combat Strength in _eliminate", VV + ": eliminating an Allied unit adds its points to the Allied ledger"),
    "V.2": ("engine/naw.py _check_victory: first_forty == Fr and exited >= 7 -> French win", VV + ": forty Allied points with seven already exited -> French win; seventh exit after demoralization wins"),
    "V.3": ("engine/naw.py _check_victory: first_forty == Al -> Allied win", VV + ": forty French points destroyed first -> Allied win, immediately"),
    "V.4": ("engine/naw.py _game_end after Game-Turn 10: draw unless already over", VV + ": end of Game-Turn 10 while demoralized and under seven exits -> DRAW; validate_movement: no losses -> draw"),
    "V.10": ("engine/naw.py s.exited (separate from s.dead); _eliminate never touches exited units; losses unchanged by exit", VV + ": an exited French unit is not a French loss"),
    "V.11": ("engine/naw.py _check_victory: both ledgers crossing forty in one elimination step -> first_forty 'both' -> French if seven exited else Allied", VV + ": both ledgers cross forty in one step -> Allied win / French win with seven exited [VIC-14]"),
    "D.1": ("engine/naw.py _check_victory: first_forty == Fr and exited < 7 -> demoralized latch, game continues", VV + ": forty Allied points with no exits -> game continues, Allies DEMORALIZED"),
    "D.2": ("engine/naw.py: the latch is set inside _eliminate, i.e. at the instant of the loss, mid-phase", VV + ": latch set by the eliminating call itself"),
    "D.3": ("engine/naw.py: s.demoralized is never cleared", VV + ": demoralization stands after forty French points"),
    "D.4": ("engine/naw.py _check_victory: once first_forty == Fr, forty French points later never sets an Allied win; the French are never demoralized (D.5)", VV + ": forty French points AFTER demoralization: no Allied win, demoralization stands [DEM-09]"),
    "D.6": ("engine/naw.py demoralization_shift inside battle_check: Al -1 / Fr +1 column, clamped at the printed ends (NAW2-OR-19 A; SPI 1979 6.2)", VV + ": 2:1 -> 1:1 Allied / 3:1 French; 1:5 and 6:1 stay put; battle_check reports the shift"),
})

VB = "games/napoleon-at-waterloo/validate_battle.py"
VM2 = "games/napoleon-at-waterloo/validate_movement.py"
ENFORCED.update({
    "M.6": ("engine/naw.py dests()/_unstack_feasible(): a unit may end its own move on a friendly hex mid-phase only if every stacked hex can still be un-stacked (bipartite matching of unmoved occupants to free step-off hexes, re-checked on every later move); end_movement refused while any hex holds two units (SPI 1979 4.4 reading A, NAW2-OR-2)", VM2 + ": may END its own move on a friendly unit mid-phase; end_movement REFUSED while a hex holds two units, naming the hex; the other unit moves off; oracle can_step_off agreement on >1500 positions"),
    "T.3": ("engine/naw.py battle_check: phase != combat -> refused [SEQ-06/MOV-04]", "validate_combat.py: attack refused outside the Combat Phase; " + VB + ": every battle in the random games is in a Combat Phase (verify_game replays)"),
    "T.4": ("engine/naw.py _propose_move: movement refused in the Combat Phase; the only position changes are _do_retreat (retreat + disruption), advance, elimination", VM2 + ": movement refused in the Combat Phase [SEQ-07]; " + VB + ": retreat/advance are the only movers, each one hex"),
    "T.5": ("engine/naw.py propose: side != mover refused unless it owns the pending step; the non-phasing player acts only through pendings the gate opens (Ar retreat direction, defender advance); no defensive fire path exists (ART-15)", VM2 + ": Allied move during the French Player-Turn refused [SEQ-08]; " + VB + ": the other player cannot answer the pending; the attacker cannot choose his own retreat"),
    "C.3": ("engine/naw.py _apply_battle: one roll_die() (gate.py seeded, counted, replayable) per battle action, read against the demoralization-shifted column", VB + ": every game verify_game-replayed with every die reproduced; validate_combat: 300 rolls 1..6"),
    "C.4": ("engine/naw.py _apply_battle -> _run_queue: eliminations, retreats, disruptions and advances apply before the next battle can be proposed (pending gate: 'resolve the pending step first')", VB + ": no further battle while a pending stands; demoralization mid-phase changes the NEXT attack's column [DEM-02]"),
    "C.5": ("engine/naw.py battle_check: every non-artillery attacker adjacent to every defender; artillery non-adjacent only at exactly two hexes (bombardment)", "validate_combat.py: non-adjacent infantry refused, artillery at exactly two hexes; " + VB + ": 150 random positions"),
    "C.6": ("engine/naw.py: contacts fixed at end_movement (_contact_pairs); live_pairs/obligations; stranded_by() forward check inside battle_check refuses any attack that would leave a friendly unit with no enemy to attack or an enemy with no friendly attacker; end_phase refused while any live pair remains; complete_assignment() = star partition of the live contact forest (constructive proof of NAW2-OR-5)", VB + ": F1 alone refused when F2 would be stranded [CBT-07]; F vs E1 alone refused when E2 stranded [CBT-06]; 150 random positions x every complete_assignment attack legal in sequence, no obligation left; end_phase REFUSED naming the units; 6 full random games always closed every Combat Phase"),
    "C.7": ("engine/naw.py s.contacts written once at end_movement; a pair lives while both units stand on their phase-start hexes, the attacker unfought and the defender unattacked; lost contact = lapse (NAW2-OR-6 A, Bruce 2026-08-17)", VB + ": obligations fixed at the start of the Combat Phase; disruption moves an uninvolved unit -> its pair lapses (chain settled, phase closes)"),
    "C.8": ("engine/naw.py: any legal battle may be proposed in any order; nothing sequences attacks", VB + ": complete_assignment attacks accepted in arbitrary order in 150 positions; random games"),
    "C.9": ("engine/naw.py battle action names attackers and defenders freely within battle_check", VB + ": one attacker vs two defenders; two attackers vs one; several-on-several (validate_combat EX-14)"),
    "C.10": ("engine/naw.py battle_check melee set: every attacker adjacent to every defender; strengths summed", "validate_combat.py: several attackers vs one defender; " + VB + ": F1+F2 vs E accepted"),
    "C.11": ("engine/naw.py battle_check: one attacker vs several adjacent defenders, defenders summed", "validate_combat.py: EX-14; " + VB + ": F vs E1+E2 accepted [CBT-12]"),
    "C.12": ("engine/naw.py battle_check never refuses on odds", "validate_combat.py: a 1:4 attack is legal; " + VB + ": 1:5 attacks in random games (Ar/AE results present)"),
    "C.15": ("engine/naw.py s.fought / s.defended set by _apply_battle, checked by battle_check, reset per Player-Turn", VB + ": an advanced defender cannot be attacked again this phase [CBT-10]; validate_combat: repeats refused"),
    "A.1": ("engine/naw.py _bombard_los: distance exactly 2", "validate_combat.py: distance 2 legal, 3 refused; " + VB + ": adjacent infantry + bombarding artillery vs one defender"),
    "A.2": ("engine/naw.py _contact_pairs includes artillery like any unit; battle_check melee path for adjacent artillery", VB + ": 150 random positions include artillery contacts; validate_combat.py: adjacent artillery attacks like any unit"),
    "A.3": ("engine/naw.py _contact_pairs is adjacency only - range-2 creates no pair", VB + ": bombardment-only positions carry no obligation (obligations empty when no unit is adjacent)"),
    "A.4": ("engine/naw.py: an adjacent gun may bombard another target - its obligation is discharged by participation (fought), the adjacent enemy stays covered by the forward check", VB + ": forward check refuses stranding; validate_combat: adjacent gun bombarding elsewhere legal"),
    "A.5": ("engine/naw.py _apply_battle: AE eliminates melee only, Ar retreats melee only; bombarding units listed as immune", VB + ": AE: adjacent attacker eliminated, bombarding artillery immune; bombardment alone with AE: nothing happens to the gun"),
    "A.6": ("engine/naw.py: adjacent artillery is in the melee set and suffers AE/Ar/EX", VB + ": adjacent artillery lost in the automatic exchange payment"),
    "A.7": ("engine/naw.py: melee partners always in the loss/retreat set regardless of artillery distance", VB + ": AE with adjacent cavalry + bombarding gun: the cavalry dies"),
    "A.8": ("engine/naw.py _apply_battle EX: owe = printed defender total; payers = melee only; melee sum <= owe -> all melee lost; else exchange_loss pending; no melee -> free (NAW2-OR-7 A per SPI 1979 6.8)", VB + ": bombarding artillery cannot pay; all-bombardment EX free; adjacent 3 < 4 all lost; 7 for 4 accepted; printed 4 owed against a doubled defender"),
    "A.9": ("engine/naw.py Ar with bombarding artillery -> voluntary retreat pending for the OWNER (ART-11, NAW2-OR-8 A), decline = stand fast", VB + ": then the bombarding artillery may VOLUNTARILY take the Attacker Retreat; declined"),
    "A.10": ("engine/naw.py battle_check: bombarding gun with >1 defender refused; adjacent gun melee like any unit", "validate_combat.py: ART-13 refusal / ART-14 legal; " + VB + ": two guns bombarding one target"),
    "A.11": ("engine/naw.py battle_check melee+bombarding sets summed into one attack strength", "validate_combat.py: EX-09/EX-24; " + VB + ": 1 + 2 adjacent + 5 bombarding = 8 vs 4 = 2:1"),
    "A.12": ("engine/naw.py: defenders never roll; artillery as defender is an ordinary defender (no range path exists in defense)", VB + ": bombardment Dr - defender retreats; no defensive-fire action type exists in propose"),
    "A.13": ("engine/naw.py _bombard_los: only Woods/Woods-Road block", "validate_combat.py: fires over an intervening enemy unit and over a Town hex"),
    "A.14": ("engine/naw.py _bombard_los: blocked only if every intervening candidate hex is Woods/Woods-Road (SPI 1979 Terrain Key example, NAW2-OR-9 CLOSED)", "validate_combat.py: 0803->0805 blocked past 0804, 0803->0705 open; woods_road blocks and is targetable"),
    "A.15": ("engine/naw.py advance candidates = melee attackers only (bombarding never in the list)", VB + ": bombarding artillery may not advance [ART-18] - no advance offered; DE: exactly the melee attacker may advance"),
    "A.16": ("engine/naw.py s.disrupted (per Player-Turn); battle_check refuses a disrupted artillery attacker [DIS S6]; forward-looking only (NAW2-OR-10 A)", VB + ": disrupted artillery may NOT fire in the Combat Phase in which it was disrupted; fires once the flag is gone; flags clear with the Player-Turn"),
    "X.1": ("game.json combat.crt.results + engine/naw.py _apply_battle branches AE/Ar/EX/Dr/DE", VB + ": each result exercised (DE, Dr, Ar, AE, EX blocks) + random-game coverage of all five"),
    "X.2": ("engine/naw.py retreat_options: adjacent hexes only; advance: adjacent only", VB + ": retreat applied one hex; advance moves the unit one hex"),
    "X.3": ("engine/naw.py: retreat pending 'by' = the victor - attacker on Dr, DEFENDER on Ar (E21)", VB + ": Dr: the VICTORIOUS (attacking) player chooses; Ar: direction chosen by the victorious DEFENDER; the attacker cannot choose his own retreat"),
    "X.4": ("engine/naw.py _safe_hex: on map, not Woods, not enemy-occupied, not in enemy ZOC (+ road hexside for Woods/Road)", VB + ": a hex in the enemy ZOC is refused; edge unit: off-map hexes never offered; enemy hex excluded from the options; Woods never offered"),
    "X.5": ("engine/naw.py retreat_options: no direction rule - every safe adjacent hex offered", VB + ": retreat options = all adjacent hexes outside the attacker's ZOC (3 of 6)"),
    "X.6": ("engine/naw.py _settle_retreats: no option -> _eliminate", VB + ": Hougoumont cul-de-sac 1014 attacked from 1013 - no path, ELIMINATED; S4 case"),
    "X.7": ("engine/naw.py _retreat_rec: friendly-occupied safe hexes offered ONLY when no empty safe hex exists; _do_retreat pushes the occupant (disrupted), retreater takes its hex, victor moves it next", VB + ": no empty safe hex -> the three friendly-occupied hexes offered as DISRUPTIONS; retreater takes the disrupted unit's hex"),
    "X.8": ("engine/naw.py _safe_hex applied to the displaced unit too: enemy units, enemy ZOC, non-Road Woods barred, Woods/Road across its road hexside (NAW2-SD-3 A, SPI 1979 6.4/4.2/6.5)", VB + ": the disrupted unit may not be pushed into the retreater's vacated hex in the attacker's ZOC; 0913 -> 1014 along the road legal"),
    "X.9": ("engine/naw.py: displaced unit's options = every safe adjacent hex, chosen by the victor (NAW2-OR-11 A)", VB + ": chain front offered its options to the victor"),
    "X.10": ("engine/naw.py _retreat_rec feasibility: a friendly hex is offered only if the displaced unit can itself be moved (recursively); no feasible option -> the RETREATING unit is eliminated, the friend stays", VB + ": every friendly-occupied safe hex is itself boxed in: NO disruption, the units stay, the retreating unit is ELIMINATED instead [S4]"),
    "X.11": ("engine/naw.py chain: displaced unit becomes owed[0], its own displacement allowed (chain list), failure at any depth = the original retreater eliminated by pre-check (NAW2-OR-12 A)", VB + ": the disrupted unit is now first owed (chain reaction); another unit cannot be moved before the chain completes; 28 disruptions in random games"),
    "X.12": ("engine/naw.py involved = the attack's attackers + defenders; any other friendly unit may be displaced (NAW2-OR-13 broad)", VB + ": uninvolved units displaced; co-retreaters never offered as displacement targets (involved)"),
    "X.13": ("engine/naw.py s.disrupted cleared in _end_player_turn; its only effect is the artillery fire ban (NAW2-OR-14 A)", VB + ": disruption flags clear with the Player-Turn"),
    "X.14": ("engine/naw.py EX: owe = printed defender strength; payer chooses whole units from the melee set, sum >= owe (over-payment legal, NAW2-OR-15 A); melee total <= owe -> all melee lost automatically", VB + ": empty payment refused; 7 for 4 accepted; exact 4 for 4; printed 4 owed against a doubled defender; all adjacent lost when 3 < 4"),
    "X.15": ("engine/naw.py advance pending immediately after the result; one unit per vacated hex, each unit once (s.advanced), decline always legal, adjacent + road hexside (MOV-17)", VB + ": advance option pending; declined - never compulsory; after one advance that unit is spent and that hex filled; only the unit on the road hexside may advance into 1014"),
    "X.16": ("engine/naw.py advance_pairs: no ZOC test on the advancing unit or the vacated hex", VB + ": advance offered into a hex inside another enemy unit's ZOC [CBT-15]"),
    "X.17": ("engine/naw.py s.advanced: refused as attacker or defender for the rest of the Combat Phase; an advanced unit has left its phase-start hex so its fixed contacts lapse (NAW2-OR-16 A)", VB + ": an advanced defender cannot be attacked again this phase; advanced attackers are already fought"),
    "X.18": ("engine/naw.py Ar/AE queue an advance for the DEFENDER into the vacated attacker hexes (NAW2-OR-17 A, SPI 1979 6.3, Stephen Oliver BGG 2018)", VB + ": the DEFENDER may advance into the vacated attacker hex; defender advances; defender may advance into the eliminated attacker's hex"),
    "X.19": ("engine/naw.py: 'off the map' is not a retreat option; a unit with no on-map safe hex is eliminated and its printed strength goes to its side's loss ledger (VIC-13); s.exited untouched", VB + ": edge unit at 0110 - off-map hexes never offered; cul-de-sac elimination adds 2 to the Allied ledger; VIC-13 cited in the elimination reason"),
})
NOTES.update({
    "M.13": "GAME CLAUSE ENFORCED (once moved, a unit may not be moved again that Player-Turn - validate_movement MOV-19 refusal; a submitted proposal is final). The consent-to-change clause is the platform UNDO policy NAW2-OR-3 (Bruce): the engine has no 'hand leaves piece' event and UNDO rewinds the verified log in every game. Cell stays OPEN until Bruce rules OR-3; nothing else in this game depends on it.",
})


def apply_overlay():
    for ph in SPINE:
        for c in ph["cells"]:
            if c["id"] in ENFORCED:
                code, ev = ENFORCED[c["id"]]
                c["status"] = "ENFORCED"
                c["evidence"] = code + " || " + ev
            if c["id"] in NOTES:
                c["note"] = (c.get("note", "") + " || " if c.get("note") else "") + NOTES[c["id"]]


apply_overlay()


def build():
    with open(os.path.join(HERE, "rules_2nd_ed.json"), encoding="utf-8") as f:
        rules = json.load(f)
    index = {r["id"]: r for r in rules["rows"]}
    cited = set()
    cells = []
    for ph in SPINE:
        for c in ph["cells"]:
            for rid in c["rules"]:
                cited.add(rid)
            cells.append((ph, c))
    unknown = sorted(r for r in cited if r not in index)
    uncovered = sorted(r for r in index if r not in cited)
    counts = {}
    for ph in SPINE:
        counts[ph["phase"] + " " + ph["name"]] = {
            "cells": len(ph["cells"]),
            "OPEN": sum(1 for c in ph["cells"] if c["status"] == "OPEN"),
            "UNREACHABLE": sum(1 for c in ph["cells"] if c["status"] == "UNREACHABLE"),
            "ENFORCED": sum(1 for c in ph["cells"] if c["status"] == "ENFORCED"),
            "hard": sum(1 for c in ph["cells"] if "difficulty" in c),
        }
    total = {
        "cells": len(cells),
        "OPEN": sum(1 for _, c in cells if c["status"] == "OPEN"),
        "UNREACHABLE": sum(1 for _, c in cells if c["status"] == "UNREACHABLE"),
        "ENFORCED": sum(1 for _, c in cells if c["status"] == "ENFORCED"),
        "hard": sum(1 for _, c in cells if "difficulty" in c),
        "open_rulings": len(OPEN_RULINGS),
    }
    doc = {
        "produced_by": "games/napoleon-at-waterloo/ingest/naw_coverage_matrix.py (PREP-7 job A)",
        "read_on": "2026-08-14",
        "edition": "SPI Napoleon at Waterloo, SECOND EDITION, copyright 1971",
        "scenario": "the whole edition - one printed game, ten Game-Turns (1 pm .. 10 pm), one at-start setup, one reinforcement event",
        "what_this_is": "The coverage matrix defined by PLATFORM_SPEC #13 as amended 2026-08-09: the matrix IS the playability rating. A scenario is playable exactly when every cell is ENFORCED or UNREACHABLE-with-evidence. There is no third acceptable state; an OPEN cell is a named defect that blocks playability, and nothing may be left to a human umpire. Cells move to ENFORCED only with a code location and a validator line; the ENFORCED overlay in this script is the record.",
        "status_values": {
            "ENFORCED": "the gate checks it - must carry the code location and the validator that proves it against a printed table or worked example",
            "UNREACHABLE": "cannot arise in this scenario - must carry the evidence",
            "OPEN": "reachable and not (fully) enforced - the default, and a blocker",
        },
        "discipline": [
            "ENFORCED cells carry the code location and the validator line that proves them (ENFORCED overlay in naw_coverage_matrix.py); the overlay grows one bite at a time",
            "an UNREACHABLE claim with no evidence is exactly the silent gap this standard exists to prevent, so unreachability is claimed only from printed rules that close their own state space or from enumerated printed components",
            "where enforceability is uncertain the cell says so rather than choosing the optimistic answer - an over-optimistic call becomes a silent incorrectness, the worst failure class in this project",
        ],
        "inputs": [
            "ingest/rules_2nd_ed.json (127 rows; the spine)",
            "ingest/crt_2nd_ed.json (60 cells + clamp)",
            "ingest/combat_charts.json (TEC, Explanation of Results, Retreat and Advance)",
            "ingest/disruption_verified.json",
            "ingest/hexgraph_2nd_ed.json (594 hexes)",
            "ingest/oob_2nd_ed.json (44 at-start + 9 reinforcements)",
            "ingest/worked_examples.json + ingest/example_check.json (27 printed examples, 27/27 odds reproduced)",
            "ingest/timerecord_oob.json, ingest/rulings_2nd_ed.json, ingest/edition_diff.json, ingest/map_grid.json, ingest/authority_ladder.json",
        ],
        "spine": SPINE,
        "state_ledger": STATE_LEDGER,
        "obligation_flags": OBLIGATION_FLAGS,
        "unreachable_register": UNREACHABLE_REGISTER,
        "hard_cells": [c["id"] for _, c in cells if "difficulty" in c],
        "new_gaps": NEW_GAPS,
        "open_rulings": [{"id": a, "cell": b, "question": c, "status": d} for a, b, c, d in OPEN_RULINGS],
        "rule_coverage": {
            "rows_in_index": len(index),
            "rows_cited_by_a_cell": len(cited & set(index)),
            "rows_not_cited_by_any_cell": uncovered,
            "cell_citations_not_in_the_index": unknown,
        },
        "counts_by_phase": counts,
        "counts_total": total,
        "spec_conflict_surfaced": {
            "what": "PLATFORM_SPEC #21 as amended 2026-08-09 removed declared-umpired from the authority ladder and requires an unresolvable defect to be escalated to the game/module creator, blocking playability until resolved by authority.",
            "the_problem": "For Napoleon at Waterloo that route does not exist. SPI ceased trading in 1982 and the folio's designer is dead. Every one of the open rulings below is a defect in the 1971 PRINT, not in a VASSAL module, so the living module authors cannot resolve any of them.",
            "available_authorities": ["official errata, if any is ever found", "proven outcome-equivalence", "a declared ruling by Bruce - the rung the amendment removed"],
            "consequence_if_unaddressed": "the encoding terminates in 20 permanently-open cells and a game that can never reach playable",
            "status": "DIRECTION CALL FOR BRUCE, prior to any encoding work",
        },
        "playability_verdict": {
            "verdict": "PLAYABLE" if total["OPEN"] == 0 else "PLAYABLE PENDING ONE PLATFORM CALL",
            "reason": "all seven encoding bites built and validated (data layer, movement/ZOC/exit, combat arithmetic, mandatory-attack assignment, result application incl. retreat/disruption/advance/exchange/artillery immunity, reinforcement/victory/demoralization, matrix closure). " + str(total["ENFORCED"]) + " of " + str(total["cells"]) + " cells ENFORCED, " + str(total["UNREACHABLE"]) + " UNREACHABLE-with-evidence, " + str(total["OPEN"]) + " OPEN" + (" = M.13, the platform UNDO policy NAW2-OR-3 (Bruce; rec A = nothing changes). No game-level cell is open; nothing is human-umpired." if total["OPEN"] else ". Nothing is human-umpired.") + " Every ruling in the register is RULED (Bruce: D4, OR-6, OR-16), CLOSED BY PROOF (OR-5) or a PUBLISHER CLARIFICATION from SPI's own 1979 text; validators: validate_data / movement / combat / battle / victory.",
        },
    }
    return doc, index


def md_escape(s):
    return s.replace("|", "\\|")


def render_md(doc):
    L = []
    a = L.append
    a("# COVERAGE MATRIX — Napoleon at Waterloo, SECOND EDITION (SPI, 1971)")
    a("")
    a("**The instrument defined by PLATFORM_SPEC #13 (amended 2026-08-09): this matrix IS the playability")
    a("rating.** The game is **playable** exactly when every row below is `ENFORCED` or `UNREACHABLE`.")
    a("There is no third acceptable state; an `OPEN` row is a named defect that blocks playability, and")
    a("nothing may be left to a human umpire — *\"umpired\" is a failure point, not a disclosure*")
    a("(Bruce 2026-08-08). Internal report — builder + testers, never player-facing.")
    a("")
    a("**This is the SKELETON.** Nothing is encoded: there is no engine code, no validator and no")
    a("`game.json` for this game. Every cell that is not evidenced-unreachable therefore starts `OPEN`.")
    a("The matrix's job right now is to enumerate **exhaustively what must be closed**, so the encoder")
    a("can work down it and so nothing is silently skipped.")
    a("")
    a("Scope: **2nd Edition only**, and the 2nd Edition prints exactly one game — ten Game-Turns")
    a("(1 pm .. 10 pm), one at-start setup read off the map art, one reinforcement event. The")
    a("per-scenario scope of this file is therefore the whole edition. **No 3rd Edition rule, and no")
    a("module redraw, may ever be used to fill a gap here** (authority_ladder: a non-primary asset may")
    a("be cited only for a claim a primary witness independently covers).")
    a("")
    a("**Status values**")
    a("")
    a("| status | meaning | must carry |")
    a("|---|---|---|")
    a("| `ENFORCED` | the gate checks it | code location + the validator that proves it against a printed table or worked example |")
    a("| `UNREACHABLE` | cannot arise in this game | the evidence |")
    a("| `OPEN` | reachable, not (fully) enforced | the work that closes it |")
    a("")
    a("**Discipline observed in building this file**")
    a("")
    for d in doc["discipline"]:
        a("- " + d)
    a("")
    a("Every cell traces to one or more rule ids in `ingest/rules_2nd_ed.json`. Machine-verified")
    a("coverage of that index is reported in §8; the file that generates this document and its JSON")
    a("twin is `ingest/naw_coverage_matrix.py`.")
    a("")
    a("---")
    a("")
    a("## §1 PHASE SPINE")
    a("")
    a("2nd Edition turn structure (SEQ-02/03/04): **French Movement → French Combat → Allied Movement →")
    a("Allied Combat → advance the Time Record**, ten times. Setup is one-off and is not a phase")
    a("(SET-04). Zones of Control, victory and demoralization are **continuous** — they are read and")
    a("written inside other phases, so they carry their own sections rather than sitting in one.")
    a("")
    for ph in doc["spine"]:
        a("### " + ph["phase"] + " — " + ph["name"])
        a("")
        a("*" + ph["when"] + "; " + ph["citation"] + "*")
        a("")
        a("| cell | rules | requirement | status |")
        a("|---|---|---|---|")
        for c in ph["cells"]:
            body = md_escape(c["requirement"])
            if c.get("data"):
                body += " <br>**data:** " + md_escape("; ".join(c["data"]))
            if c.get("difficulty"):
                body += " <br>**HARD.** " + md_escape(c["difficulty"])
            if c.get("evidence"):
                body += " <br>**evidence:** " + md_escape(c["evidence"])
            if c.get("note"):
                body += " <br>*note:* " + md_escape(c["note"])
            if c.get("source"):
                body += " <br>*source:* " + md_escape(c["source"])
            if c.get("open_ruling"):
                body += " <br>*open ruling:* `" + c["open_ruling"] + "`"
            a("| **" + c["id"] + "** | " + ", ".join("`" + r + "`" for r in c["rules"]) + " | " + body + " | `" + c["status"] + "` |")
        a("")
    a("---")
    a("")
    a("## §2 STATE LEDGER")
    a("")
    a("Persistent state the gate must keep: which cells WRITE it, which READ it. This is where the")
    a("movement↔combat interplay lives; a phase-only view never tests that combat rewrote the map")
    a("movement runs on. In this game the Combat Phase writes unit positions through **three** distinct")
    a("doors (retreat, disruption displacement, advance), two of which are driven by the player who does")
    a("not own the unit.")
    a("")
    a("| state | written by | read by | status |")
    a("|---|---|---|---|")
    for s in doc["state_ledger"]:
        body = md_escape(s["read_by"])
        if s.get("note"):
            body += " <br>*note:* " + md_escape(s["note"])
        a("| " + md_escape(s["state"]) + " | " + md_escape(s["written_by"]) + " | " + body + " | `" + s["status"] + "` |")
    a("")
    a("## §3 OBLIGATION FLAGS")
    a("")
    a("| class | cells | status |")
    a("|---|---|---|")
    for o in doc["obligation_flags"]:
        a("| **" + md_escape(o["class"]) + "** | " + md_escape(", ".join(o["cells"])) + " | " + md_escape(o["status"]) + " |")
    a("")
    a("## §4 UNREACHABLE REGISTER")
    a("")
    a("Every claim carries its evidence. **One phase-spine cell** is marked `UNREACHABLE` (D.5); the")
    a("remaining entries are scope facts that keep out-of-edition and non-primary material from ever")
    a("becoming cells at all.")
    a("")
    a("| subject | evidence | kind |")
    a("|---|---|---|")
    for u in doc["unreachable_register"]:
        a("| " + md_escape(u["subject"]) + " | " + md_escape(u["evidence"]) + " | " + md_escape(u["kind"]) + " |")
    a("")
    a("## §5 THE HARD CELLS")
    a("")
    a("These are not ordinary rows. Each names a difficulty that a straightforward per-action legality")
    a("gate cannot absorb, and several must be **ruled before code is written**, not during it.")
    a("")
    hard = []
    for ph in doc["spine"]:
        for c in ph["cells"]:
            if c.get("difficulty"):
                hard.append((ph, c))
    for ph, c in hard:
        a("### " + c["id"] + " — " + ph["name"].split(" (")[0] + " · " + ", ".join(c["rules"]))
        a("")
        a("**" + c["requirement"] + "**")
        a("")
        a(c["difficulty"])
        if c.get("open_ruling"):
            a("")
            a("*Open ruling:* `" + c["open_ruling"] + "`")
        a("")
    a("## §6 OPEN RULINGS")
    a("")
    a("Per spec #21 as amended 2026-08-09, *declared-umpired was removed from the authority ladder*: a")
    a("defect we cannot derive, validate or resolve to a binary answer is registered with quoted")
    a("evidence, escalated to the game/module creator, and **blocks playability** until resolved. Every")
    a("row below is an input to `game.json` `source_defects`; none of them is a coding choice.")
    a("")
    a("> **A CONFLICT WITH THE AMENDED SPEC, SURFACED NOT WORKED AROUND.** #21 as amended routes an")
    a("> unresolvable defect to *the game/module creator* and blocks playability until **resolved by")
    a("> authority**. For this game that route does not exist: SPI ceased trading in 1982 and the folio's")
    a("> designer is dead. The module authors (PREP-7 job B's register) can answer questions about their")
    a("> *modules*; not one of the rulings below is a module question — every one is a defect in the 1971")
    a("> print. So the only authorities actually available for these 20 open items are (a) official errata,")
    a("> if any is ever found, (b) proven outcome-equivalence, and (c) a declared ruling by Bruce — which")
    a("> is the rung the 2026-08-09 amendment removed. Siege of Jerusalem could lean on a living module")
    a("> author; Napoleon at Waterloo cannot. **Bruce must decide how a dead-publisher game reaches")
    a("> playable at all before the encoding is worth starting** — otherwise the work terminates in 20")
    a("> permanently-open cells and a game that can never ship. This is a direction call, not a build")
    a("> problem, and it is prior to every item in the table.")
    a("")
    a("| id | cell | question | status |")
    a("|---|---|---|---|")
    for r in doc["open_rulings"]:
        a("| `" + r["id"] + "` | " + r["cell"] + " | " + md_escape(r["question"]) + " | " + md_escape(r["status"]) + " |")
    a("")
    a("## §7 NEW GAPS FOUND BY THIS MATRIX (N-list)")
    a("")
    a("Found 2026-08-14 by reading the 127-row rules index against the page-5 charts, the disruption")
    a("paragraph, the hexgraph and the worked-example corpus. **Five (N1–N5) appear on no prior list at")
    a("all**; a sixth (N7) sharpens a prior observation into a named page-1-vs-page-5 contradiction; N6 is")
    a("carried unchanged and is listed only so it has a cell that can be closed.")
    a("")
    a("| # | cell | rules | finding | class |")
    a("|---|---|---|---|---|")
    for n in doc["new_gaps"]:
        a("| " + n["id"] + " | " + n["cell"] + " | " + ", ".join("`" + r + "`" for r in n["rules"]) + " | " + md_escape(n["finding"]) + " <br>*prior lists:* " + md_escape(n["prior_lists"]) + " | " + md_escape(n["class"]) + " |")
    a("")
    a("## §8 COVERAGE AND VERDICT")
    a("")
    a("| phase | cells | OPEN | UNREACHABLE | ENFORCED | hard |")
    a("|---|---|---|---|---|---|")
    for k, v in doc["counts_by_phase"].items():
        a("| " + k + " | " + str(v["cells"]) + " | " + str(v["OPEN"]) + " | " + str(v["UNREACHABLE"]) + " | " + str(v["ENFORCED"]) + " | " + str(v["hard"]) + " |")
    t = doc["counts_total"]
    a("| **TOTAL** | **" + str(t["cells"]) + "** | **" + str(t["OPEN"]) + "** | **" + str(t["UNREACHABLE"]) + "** | **" + str(t["ENFORCED"]) + "** | **" + str(t["hard"]) + "** |")
    a("")
    rc = doc["rule_coverage"]
    a("**Rule-index coverage (machine-verified by `naw_coverage_matrix.py`):** " + str(rc["rows_cited_by_a_cell"]) + " of " + str(rc["rows_in_index"]) + " rows in")
    a("`rules_2nd_ed.json` are cited by at least one cell. Rows cited by no cell: " + (", ".join("`" + r + "`" for r in rc["rows_not_cited_by_any_cell"]) if rc["rows_not_cited_by_any_cell"] else "**none**") + ".")
    a("Cell citations not present in the index: " + (", ".join("`" + r + "`" for r in rc["cell_citations_not_in_the_index"]) if rc["cell_citations_not_in_the_index"] else "**none**") + ".")
    a("")
    a("### PLAYABILITY VERDICT")
    a("")
    a("**" + doc["playability_verdict"]["verdict"] + "** — " + doc["playability_verdict"]["reason"])
    a("")
    a("The gating work, in the order it must happen:")
    a("")
    a("1. **Rule the blockers first.** `NAW2-SD-3` (X.8), `NAW2-OR-6` (C.7 obligation timing) and")
    a("   `NAW2-OR-7` (A.8 costless Exchange) each decide the shape of code rather than a detail of it;")
    a("   `NAW2-OR-3` (M.13 touch-move vs UNDO) is a **platform-wide** question that reaches every")
    a("   shipped game and belongs to Bruce before Fable touches undo semantics anywhere.")
    a("2. **Then solve C.6.** The mandatory-assignment problem is the single largest engineering item;")
    a("   it cannot be started until C.7 is ruled, and A.4 widens its search space.")
    a("3. **Then the retreat/disruption engine** (X.2–X.13), which has five undefined edges of its own")
    a("   and no printed procedure on page 1 at all — the whole procedure lives on the map sheet, on the")
    a("   British/Prussian half only.")
    a("4. **Then everything else**, against the 27-example corpus for odds and against the printed CRT")
    a("   for results — with C.16's coverage gaps stated in the shipped register rather than glossed.")
    a("")
    return "\n".join(L) + "\n"


def main():
    doc, index = build()
    out_json = os.path.join(HERE, "coverage_matrix.json")
    out_md = os.path.join(GAME, "COVERAGE_MATRIX.md")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
        f.write("\n")
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(render_md(doc))
    rc = doc["rule_coverage"]
    print("cells:", doc["counts_total"])
    print("rule index rows:", rc["rows_in_index"], "cited:", rc["rows_cited_by_a_cell"])
    print("UNCITED ROWS:", rc["rows_not_cited_by_any_cell"])
    print("BAD CITATIONS:", rc["cell_citations_not_in_the_index"])
    for k, v in doc["counts_by_phase"].items():
        print(" ", k, v)
    print("wrote", out_json)
    print("wrote", out_md)


if __name__ == "__main__":
    main()
