# Afrika Korps — grid & rules validation worksheet

Spec #12 discipline: nothing ships until validated. This file records the
evidence chain for the sideways-grid mapping and, later, the CRT encoding.

## TIER 3a — POLICY AI: BUILT + VALIDATED 2026-07-10 (`python validate_ai.py` — ALL PASS)

The engine-owned opponent `engine/ai_strategic.py` plays AK through the ONE
legality gate (`StrategicGame.submit`) and nothing else — same doctrine as the
tactical `engine/ai.py`. `validate_ai.py` drives full AI-vs-AI campaigns at
several seeds plus a Tier-1 game and asserts, for each: the game completes with
no stall, issues real movement and >=1 CRT battle, and — the core property —
its log **replays byte-for-byte through `verify_game.py`** (every verdict, die
and state hash reproduced). Games are bounded to `VAL_MAX_TURNS` to keep the
suite to minutes; the gate + exact-replay properties hold at any length.

**Two engine defects the AI-vs-AI harness surfaced and fixed (both would hit a
human, not just the AI):**
- **Lone-attacker stack split (11.2/11.4).** `_propose_battle` let a SINGLE
  attacking unit attack a SUBSET of a stacked hex, and `_solo_attack_exists`/
  `_supply_free_attack_exists` enumerated subsets. A unit forced (8.4) to
  attack a stack it can't beat then had `forced_elim` wrongly blocked (the gate
  "saw" a phantom legal subset attack) while it could fight only once (11.8) —
  the turn deadlocked. Fix: the solo helpers now total the defense of ALL
  adjacent enemies (11.2/11.33); `_propose_battle` rejects a lone attacker that
  omits a co-stacked unit (11.2/11.4). 7.4/11.6 elimination now resolves.
- **land_supply KeyError.** The supply pool holds RECYCLED on-board supply
  counters (14.1 consumed / 15 captured) whose ids are scenario `units`, not
  `reserve`; `_apply` looked them up in `reserve` and crashed on re-landing.
  Fix: resolve the counter from `self.catalog` (units + reserve).

**Policy (declared-weak but honest):** territorial drive to the nearest
contested victory hex (4.1); supply units kept ALIVE >=6 hexes from the enemy
(losing the last collapses the army, 24.5; the isolation trace is
unlimited-length, so safe rear supply still supplies the army); combat units
never advance into a hex they could not trace supply from (24.1 — a per-turn
reverse-BFS supply-connected set, validated identical to `sg._isolated`, 0/151
mismatch) and fall back if isolated (24.2); voluntary contact only at 2-1 or
better WITH supply in range (a strong attack needs supply, 14.1). Not modelled
(all optional, skipping is legal): 11.6 soak-off search, replacements 20 /
substitutes 21, Rommel escort bonus 22.1. Regressions after all changes: 7 AK
validators ALL PASS, Arnhem baseline SHA fe2a652f6f9c byte-identical, Tobruk
verify 17/17. Server `/api/sg_ai_turn` + index.html "AI plays <side>'s turn".

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

## TIER 2 COMPLETE 2026-07-09 (late): supply capture + isolation + replacements + substitutes + AV
## (re-run `python validate_tier2.py` — ALL PASS; every session replays through verify_game.py)

The last five subsystems are enforced. Evidence highlights:

**SUPPLY CAPTURE (15)** — 15.21 auto-capture on movement adjacency with the
counter swap and pool return; one-directional trigger (15.21 "moves
adjacent" + 15.211: static enemy adjacency never captures — the first
implementation was a state-based sweep that PING-PONGED a 15.322 capture
back to the old escort standing on it; caught by the validator's own replay
log). Fortress shielding (15.23; capture only by moving onto it or the
combat-phase 'attack', with the 16.3 advance). Accompanied supplies: the
one-unit capture-attack with mandatory escort battles (15.322, figs 6/7/11;
the capturer is barred from other battles). Retreat/advance pickup (15.22,
incl. the sustaining-supply exception). Post-capture rights BY METHOD:
movement captures move+sustain (figs 1-2); combat captures move-only,
including the 15.34 escape from the old escort's ZOC (implemented as a
one-shot combat-phase move with exactly that ZOC negated); fortress and
retreat captures are frozen. 15.4 voluntary destruction. COUNTER RECYCLING:
consumed/destroyed/captured-away supplies return to the owner's off-board
pool — without this the Axis would run out of supply counters after three
sustained attacks (the 12.1/12.2 maxima are physical-counter counts).

**ISOLATION (24)** — two-consecutive-own-turns elimination with start+end
checks (24.2; clarification 8's land-then-destroy case counts as isolated,
validated verbatim); at-sea isolation (24.4); the 24.5 no-supplies game
loss (validated end-to-end: a side stripped of supply for two turns loses
everything). The end-of-turn isolation check runs BEFORE consumed supplies
leave the board (they are removed AT the end per 14.1; a wrong
auto-elimination is worse than a lenient order — documented call).
Trace-fix en route: a unit STACKED with its supply was counted isolated
(the BFS never revisits its start hex) — would have starved every W6 stack.

**REPLACEMENTS (20)** — accrual at own-turn start for controlled home base
(Axis 1 / Allied 2) + Tobruch (1 each) from 1 March 1942 (the printed
track's 'Begin Replacement Rate', asserted against the label list);
accumulation 20.5; spending attack factors to resurrect eliminated combat
units under the reinforcement rules; substitutes barred (21.6).

**SUBSTITUTES (21)** — needed unit TYPES, which the factor transcription
lacks: all 61 Allied combat counters were read visually (NATO symbols:
oval=armor, X=infantry, X-over-oval=armored infantry, RECCE box) and
encoded as game.json unit_types. Cross-check: the rulebook's own 7.3
example names the 3-3-7 'British 7th Armored Infantry' == the X-over-oval
on 'A 7 Arm 7'. Motor battalions carry the plain infantry X (infantry, NOT
armored infantry). Equal-factor exchange at the end of the movement
portion, type matching both directions, breakdown with the 21.4 factor/MF
constraints (fast components only if they originally formed the sub).

**AUTOMATIC VICTORY (9)** — declaration during movement at 7-1, or 5-1 with
a defender that provably cannot survive a back-2 (reuses the 7.62
survival-assignment search; the 5-1 stage builds a real three-unit ring —
and the gate REJECTED a live 2-unit 'ring' against Bengasi in the browser
session because a route genuinely remained open). Supply trace at the
instant with the defender's own ZOC still blocking (clarifications sec 10,
rejection validated); ZOC negation via a zoc_negated board flag (pass
through and OVER the AVed unit, never onto it — legal-destination sets
checked before/after); attacker + cutoff-blocker freeze (9.2/9.3);
end-of-movement supply revalidation incl. the 14.5 both-supplies-expended
replacement case; mandatory resolution before the turn ends (9.6); the AV
battle resolves without a die at >6-1.

**Umpired corners (declared in rules_scope):** 11.7 fortress twice-attacked
exception, 7.61 overstack-casualty choice, 21.3 mid-exchange breakdown,
9.4 joined-AV bookkeeping beyond the freeze, 22.4's isolation-encirclement
clause for Rommel. Web build still legacy JS (Tier 0).

**Regressions:** all seven AK validators ALL PASS, Arnhem baseline
fe2a652f identical, Tobruk 17/17, all games load. Source-defect register
grew to 8 entries (capture-vs-min-odds conflict, resolved by tournament
clarifications figs 3-4, enforced as the move-time fig-3 guard).

## TIER 2 COMBAT: VALIDATED 2026-07-09 (re-run `python validate_combat.py` — ALL PASS)

**CRT — two independent sources, all 66 cells identical.** The encoded table
(game.json `combat.crt`) is re-checked on every validator run against (1) the
rulebook back-page COMBAT RESULTS TABLE re-parsed live from
AfrikaKorps_3d_Ed_Rules.pdf, and (2) the mastermind's image-only map
transcription (map_tables_transcription.json — produced without consulting
the rulebook, so the sources are independent). 11 odds columns 1-6..6-1 ×
6 die rows; zero mismatches.

**The "7-1" question RESOLVED (was flagged since the transcription landed):**
rules text 7.4 says "odds greater than 7-1 are treated as 7-1" while the
printed CRT tops at 6-1. These agree: 9.1 defines 7-1 (or 5-1 surrounded) as
the automatic-elimination situation, and the map prints "odds greater than
6-1 ... mean automatic elimination" beside the CRT. Encoded as: >6-1 after
rounding = defender eliminated, NO die rolled (validate_combat: rng_calls
provably unchanged); worse than 1-6 = no voluntary attack, forced units
eliminated before any battle.

**Rulebook worked examples reproduced through the engine + gate:**
- 7.3 rounding: 7:2→3-1, 2:7→1-4, and the 3-3-7-vs-Savena battle at 1-1
  fought end-to-end through submit() with the supply rule enforced
- 7.5 exchange example 1: seven 1-1-6 vs a DOUBLED 2-3-4 on an escarpment at
  1-1 → exchange kills the 2-3-4 plus exactly SIX 1-1-6s (five rejected as
  too few, seven rejected as over-payment, the loser barred from choosing)
- 7.5 exchange example 2: 3-4-6 vs four 1-1-6 at 1-2 → the 3-4-6 plus
  exactly THREE 1-1-6s
- 11.6/7.4 soak-off limits incl. the 1-8-is-illegal diagram case
- 23.7: a besieged Tobruch garrison (doubled, attacked at the example's own
  3-1/die-3 row) suffers DB2 with no legal route → eliminated; the emptied
  fortress then opens advance after combat (16.1)
- clarifications sec. 5 trapped units: isolated-in-ZOC with no supply-free
  attack auto-eliminated at end of movement (11.9); with supply in reach the
  unit survives and the forced-elimination action is gated on a real
  no-legal-attack test (7.4)

**Combat gate mechanics validated through submit() (~90 checks, 15 staged
scenarios, EVERY session log replayed through engine/verify_game.py):**
movement/combat phase split (5.3/3.2: no moves after end_movement, no
battles before), mandatory-combat obligations both directions (8.4),
adjacency incl. the 5.7 anomalous-hexside engagement ban, 23.1 attack-into-
fortress must engage the whole garrison, 23.2 sortie coverage, 11.7/11.8
one-battle-per-unit, the 11.31-11.33 orphan guard (a battle may not strand
another unit with nothing left to attack — prevents dead-locking the
append-only turn), defense doubling 10.2, supply-to-attack 14.1-14.6
(radius 5 inclusive-of-supply-hex, enemy-ZOC blocking incl. the fig-12
uninvolved-blocker case, the fig-15 carve-out for the attacked unit's own
ZOC, consumption at end of player turn), retreats 7.6/7.61/7.62 (winner
chooses; no hex twice; never the battle hex per clarification 9; immediate-
elimination avoidance with a full survival-assignment search per
clarification 7), advance after combat 16.1 into vacated fortress/
escarpment, victory 4.1-4.3 (eliminate-all with the clarification-13 at-sea
exclusion; two-consecutive-turn control of all four objective hexes,
staged and won), Rommel guards (22.41 no voluntary lone move into enemy
ZOC; 22.4 displacement machinery).

**TWO MORE WRONG-GATE DEFECTS found + fixed en route (nos. 6 and 7 for this
game):** (1) fortress OUTWARD ZOC — a garrison wrongly exerted ZOC over its
surrounding hexes, pinning besiegers; 7.1 lists fortresses as ZOC
exceptions and 23.1/23.2 make attacks around a fortress optional BOTH ways
(clarifications fig. 9 agrees). Fixed spec-gated (`zoc.no_exert_terrain`).
(2) ZOC across prohibited hexsides — a unit on E18 wrongly projected ZOC
into F19 across the all-water hexside; 7.1 excepts exactly those hexsides.
Fixed spec-gated (`zoc.blocked_by_prohibited_hexsides`). Plus a stacked-
units bug in the new obligations code itself (dict keyed by hex collapsed
co-located units), caught during the browser session.

**Interpretation calls (documented, defensible, declared):**
- 24.1 isolation trace: the target supply's own hex is exempt from the
  ZOC-free test (the line runs TO the supply). A strict inclusive reading
  would wrongly auto-kill the fig-15 attacker via 11.9. The 14.2 attack-
  supply route keeps the strict inclusive test with the figs-12/15
  carve-out instead. A wrong elimination is worse than a lenient trace.
- Exchange ties (equal factors): both readings of "the player with fewer"
  produce the same outcome — both sides remove everything — so the gate
  auto-applies it; no player choice exists to get wrong.
- forced_elim requires fought==0 (7.4 "before any other battles" — also
  keeps a doomed unit's ZOC from influencing earlier retreats, which 7.4
  explicitly forbids).

**NOT yet enforced (declared in rules_scope, UI-visible):** AV movement
mechanics 9.1-9.7 (gate stricter — the 7-1 auto-elim itself IS enforced),
supply capture 15 (retreat/advance over lone enemy supply is allowed as
movement, the flip is umpired), isolation attrition 24.2-24.5, replacements
20 / substitutes 21, and the narrow corners listed in rules_scope
(multi-unit-support feasibility in the 7.4 forced test, 11.7 fortress
twice-attacked exception, 7.61 overstack-casualty choice, 15.22 mid-retreat
pickup).

**Browser + API session (2026-07-09):** full Mersa Brega meeting engagement
driven twice — once over raw HTTP, once by clicking the generic index.html
combat panel (battle builder with live odds preview, supply picker, retreat
route buttons straight from the gate's legal-path enumeration, forced-elim
buttons, obligations tracker). 24/24 log entries replayed through
verify_game.py afterward, 4 illegal proposals provably inert. Regressions
all green: Arnhem baseline SHA fe2a652f identical, terrain.json byte-
identical rebuild, Tobruk 17/17, ASL/Arnhem/Tobruk load, all six AK
validators ALL PASS.

## TIER 1 COMPLETE 2026-07-09 (late): arrivals + sea movement + Rommel bonus
## (re-run `python validate_arrivals.py` and `python validate_tier1.py`)

The three items Bruce gated the badge on are now enforced through the gate,
each with independent validation:

**ARRIVALS (3.1/3.3, 12, 19) — data cross-validated from FOUR sources**
(validate_arrivals.py, ALL PASS): the canonical 62-unit reinforcement
schedule was read cell-by-cell from the printed Turn Record track art and
verified against (1) the mastermind track transcription, (2) the
independent counter-face transcription, (3) the module setup pieces
physically parked on the track (x-position clusters reproduce every turn
group), (4) game.json stats. TRANSCRIPTION DEFECT found + corrected: the
1 Aug 41 brigades print "5I" (5th Indian: 29/9/10) — transcription misread
"51 Inf"; counter faces + module slots + printed art agree on 5I; factors
identical, no gate impact. The track's supply wedges (15 Apr 41: 1,2 "to
end of June"; 1 Jul 41: 1,2,3 "to end of November"; 1 Dec 41: 1 "to end of
game") are exactly the rulebook 12.2 SUPPLY TABLE columns — two-source
match. Gate enforcement (validate_tier1.py): due turns (19.1), controlled
ports only, Tobruch/own home base (19.2/19.7/4.3 — the OPPONENT's home
base and Bengasi rejected), later landing allowed (19.3), full move on
arrival (19.2/13.1), placements strictly before movement (3.1/3.3), own
player turn only (19.6), Allied 1 supply/turn max 4 (12.1), Axis Supply
Table d6 through the ENGINE-OWNED seeded RNG with the correct sunk window
per date column (12.2 — no roll turn 1, once per game turn), land-or-forfeit
(12.4), declining allowed (12.5), 19.8 at game end.

**SEA MOVEMENT (23.3-23.44)**: embark from Tobruch/own home base only
(Bengasi rejected 23.3, enemy home 23.5), move-then-embark same turn OK
(23.4), control-at-start OR ZOC-free embarkation (23.44), landing only on
the FOLLOWING friendly turn (23.4), same-port return OK (23.43), landing
requires start-of-turn port control (23.44), landed units may move inland
but not re-embark (23.42), units overdue at sea are ELIMINATED at the end
of their player turn (23.42 — validated: a garrison that sailed and lost
its only port died on schedule). Port control = 4.3 occupation by
combat/supply/Rommel, home bases additionally ZOC-free.

**ROMMEL BONUS (22.1) — ambiguity RESOLVED by the module's own tournament
clarifications** (both "Afrika Korps Rule Clarifications for Vassal.pdf"
and "Afrika_Korps_Clarifications_-_Nov_2023.docx", identical text): the
bonus may be taken at any point of the turn, even after Rommel departs, so
long as Rommel moved WITH the unit for the claimed hexes at some point;
1 co-moved hex = only +1; units may fully expend MF first and Rommel adds
the two escorted hexes afterward; combines with the coast road bonus (the
clarification's Q&A: 2 escorted + 10 road + regular MF on turn 1 = yes).
ENCODING: moves may carry an explicit `path`; Rommel's path move is
submitted first; a claim (`rommel_bonus` on a move, or a `rommel_extend`
appended to a completed path move) is legal iff the unit's path shares a
directed contiguous segment of >= claimed length with Rommel's submitted
path, once per unit per turn, whole path re-validated under the full
movement rules at MF+bonus. Validated: exact budget boundaries (MF4+2=6
hexes legal, 7 illegal), no-shared-segment and short-segment claims
rejected with citations, the move-first-escort-later flavor, and
escort+road+regular composition. Submission-order note: the gate requires
Rommel's path before claims — order inside the player turn is our
sequential-submission artifact; the clarification makes any order
outcome-equivalent, and every legal outcome remains expressible.

**MOVEMENT DEFECT FOUND + FIXED (was live in the shipped gate): fortress
ZOC immunity (19.5/23.1)** — "adjacent units do not exert a ZOC over a
fortress hex" was not encoded; enemy ZOC wrongly stopped/pinned movement
into and out of Tobruch/Bengasi. Fixed spec-gated (`zoc.immune_terrain:
["fortress"]`), validated (validate_tier1.py: H25 unit exerts no ZOC over
G25, garrison not ZOC-locked), Arnhem/Tobruk semantics untouched (no
immune_terrain in their specs — SHA/verify regressions identical).

Every session above replays through engine/verify_game.py (verdicts, dice,
state hashes; illegal proposals provably inert). UI: index.html arrivals
panel (ports, supply roll/land, due reinforcements, at-sea units) drives
/api/sg_action through the gate; confirmed in Chrome. Rommel path claims
are API-level (UI path-drawing is future polish — the UI cannot express an
escort, it simply doesn't offer it; nothing the UI offers bypasses a rule).

**Still NOT enforced (declared in rules_scope, UI-visible):** combat and
everything needing it (Tier 2), supply capture/consumption (14/15),
isolation (24), replacements (20), substitutes (21), victory adjudication
(4.1-4.3). Web build (web/) still runs the legacy JS engine — AK gate is
Python/HTTP only.

## SUPERSEDED — TIER-1 SUBMIT GATE: LIVE + VALIDATED 2026-07-09 (re-run `python validate_gate.py`)
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
