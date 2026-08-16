# COVERAGE MATRIX — Blue & Gray: Chickamauga (SPI 1975)

**The instrument defined by PLATFORM_SPEC #13 (amended 2026-08-09): this matrix IS the playability
rating.** The scenario is **playable** exactly when every row below is `ENFORCED` or `UNREACHABLE`.
There is no third acceptable state; an `OPEN` row is a named defect that blocks playability.
Internal report — builder + testers, never player-facing.

Scope: **PER SCENARIO** — this file covers *Chickamauga — The Last Victory* (the campaign, 15 GTs)
only. The unreachable column is never inherited by any other scenario.

Ruleset in force: **the 1975 original** (Bruce, 2026-07-10). Decision Games **Deluxe** ranks above
the 1975 text **where it corrects it** (errata-bearing primary); the Stafford 2018 revision is
clarification only and is cited nowhere as authority. All scan references are to
`literature/blue-and-gray/` (BGStandardRules.pdf 4pp; BGChickamauga.pdf scans p01–p10;
`deluxe_fulltext.txt` line refs).

**Status values**
| status | meaning | must carry |
|---|---|---|
| `ENFORCED` | the gate checks it | code location + the validator that proves it |
| `ENFORCED (unproven)` | code exists, no validator exercises it | the N-list work item (RULE 1) |
| `UNREACHABLE` | cannot arise in this scenario | one of the four valid evidence kinds |
| `OPEN` | reachable, not (fully) enforced | the N-item that closes it |

Work-item key: **`N#` = gap found building this matrix** (§5) — none of them were on the prior
`rules_scope.umpired` list. Row-key prefixes: `P0` deployment · `S` sequence · `M` movement (5.x)
· `Z` ZOC (6.x) · `RF` reinforcements (15.x) · `EX` exit (16.x) · `C` combat (7.0–7.9) ·
`B` artillery (8.x) · `R` retreat (7.7) · `D` displacement (7.8) · `A` advance (7.75/7.76) ·
`X` exchange (7.6 Ex) · `T` train (18.x) · `N` night (10.x) · `V` victory (17.x). Keys are stable
and unique; later bites cite them.

Validators (all in `games/blue-and-gray-chickamauga/`): `validate_grid.py` (**VG** — grid + 45
at-start positions vs the 1975 chart), `validate_movement.py` (**VM** — TEC costs, ZOC semantics,
stacking, MA), `validate_gate.py` (**VGa §A–§I** — end-to-end phase law), `validate_combat.py`
(**VC §1–§9**), `validate_retreat_chain.py` (**VR** — displacement-cycle regression),
`validate_undo.py` (**VU**), `validate_ai.py` (**VA** — 5-seed full campaigns, byte-exact
replays), plus platform-layer `validate_plans.py` / `validate_pbm.py` / `validate_optimizer.py` /
`validate_llm_harness.py`. Eleven validators total; every enforcement claim below names one.

---

## §1 PHASE SPINE

Read from 1975 §4.0/§4.1 + Exclusive [14.3]/[15.53] and **confirmed against the code** — this
matrix's independent reading of the rulebook **agrees with the handoff's table**; no divergence to
flag. One turn = two Player-Turns (Union always first, 14.3), each = Movement Phase then Combat
Phase, then the Game-Turn Record Interphase (4.1.3 — engine-automatic). **15 GTs, GT 9 night**
(15.53): the night turn OMITS both Combat Phases entirely (10.0) and tightens movement (10.2).
Engine: `_next_player` bluegray.py:966 (turn advance + interphase), `end_movement` apply
bluegray.py:928 (phase pivot; night skips combat), `propose` bluegray.py:389 (phase/mover/pending
doors). Validated VGa §A (sequence incl. GT rollover), §F (night skip).

The Combat Phase carries **interrupt sub-steps** — `retreat` [7.7], `advance` [7.75/7.76],
`exchange_loss` [7.6 Ex], `train_retreat` [18.11] — each its own action type with its own rows
below, front-gated on the hashed `pending` (bluegray.py:397–404), exactly as SoJ treats segments.

### P0 — DEPLOYMENT (one-off, scenario-fixed; 3.0 + charts 14.1/14.2)

Deployment is not a player action in this game (3.0: players place the chart's units
simultaneously; no choice exists beyond which side you sit). It earns data rows, not action rows.

| row | rule | requirement | status |
|---|---|---|---|
| P0.1 | 14.1 | Union at-start OOB: 14 units at the charted hexes/strengths (incl. Wilder 8 at 1022, 2/4/XIV at 0822 — the module's two deviations corrected to print) | ENFORCED — scenario data `scenario_chickamauga.json` units; VG asserts 45/45 module positions resolve to the chart and pins both deviations as deviations |
| P0.2 | 14.2 | Confederate at-start OOB: 32 units incl. artillery "3" (5 CSP, 2120) and 4 cavalry | ENFORCED — same data + VG |
| P0.3 | 14.0 | class typing: "a" = artillery, "c" = cavalry, rest infantry (drives 8.x / 18.x / ZOC-exempt law) | ENFORCED — scenario `cls` + game.json `classes`; exercised end-to-end by VA (real-scenario campaigns through the gate) and VGa §H/§I (arty/train class behavior) |

### S — SEQUENCE & INTERPHASE (4.0/4.1, 14.3, 15.53)

| row | rule | requirement | status |
|---|---|---|---|
| S.1 | 4.1/14.3 | Union is First Player in every GT; mover doors reject the non-phasing side | ENFORCED — `propose` bluegray.py:404; VGa §A |
| S.2 | 4.1.3/15.53 | GT marker advances after the second player-turn; game ends after GT 15 → victory determination | ENFORCED — `_next_player` :966, `_final_scoring` :1201; VGa §A/:272 |
| S.3 | 4.1.A/4.1.B | Movement Phase precedes Combat Phase; combat only in the combat phase; no movement in combat except forced retreat/advance (5.11) | ENFORCED — phase gates in `_propose_move` :441 / `_propose_battle` :513 / retreat-advance pendings; VGa §A/§B |
| S.4 | 15.53 | GT 9 is the night turn (label + behavior) | ENFORCED — scenario `night_turns:[9]` + `is_night` :98; mechanics VGa §F |

### M — MOVEMENT PHASE: MOVEMENT & TERRAIN (5.x, 9.0 TEC)

| row | rule | requirement | status |
|---|---|---|---|
| M.1 | 5.0 | MA = 6 MP for ALL units (attack/defense/move from one printed factor, 2.4) | ENFORCED — `budget` :131 (stats[2]); VM budget block |
| M.2 | 5.0/5.16 | contiguous-hex paths, one unit at a time | ENFORCED — Dijkstra over `neighbors` (gamespec.py:172, `_legal_destinations_ext` :510); VM |
| M.3 | 5.11 | movement only in own movement phase | ENFORCED — `_propose_move` :441; VGa §A |
| M.4 | 5.12 | never enter an enemy-occupied hex | ENFORCED — enemy hexes block (`_enemy_hexes` gamespec.py:438); VM "enemy hex itself never enterable"; VGa §A |
| M.5 | 5.14 | no combat during the movement phase (a battle irreversibly initiates the Combat Phase) | ENFORCED — battle refused unless `phase=="combat"` :513; VGa §A/§B |
| M.6 | 5.15 | MP spend ≤ MA; no accumulation, no transfer | ENFORCED — cost cap in the Dijkstra (`nc > ma` gamespec.py:694) + `moved` map :446; VM |
| M.7 | 5.17 | a unit moves once per movement phase (hand-off-the-piece) | ENFORCED — `moved` map refuses a second move :446; VGa §A:89. The change-with-consent half of 5.17 is N12 (cross-game) |
| M.8 | 5.21/9.0 | TEC entry costs: clear 1 / forest 3 / rough 3 / forest+rough 6 | ENFORCED — `move_cost` gamespec.py:255 + game.json `terrain_mp`; VM cost block (each value pinned incl. a forest_rough case) |
| M.9 | 5.22/TEC | road hex→road hex through a road hexside = 1 MP regardless of other terrain | ENFORCED — road `override` rule (game.json hexside_rules; `move_cost` :274); VM road-into-forest/rough case |
| M.10 | 5.23/TEC | trail hexside: 2 MP into forest/rough, 1 MP into clear ("ignore trails in clear terrain") | ENFORCED — trail `cap` rule; VM trail cases both ways |
| M.11 | 5.25/TEC | creek hexsides impassable except bridge (no extra cost) and ford (+1 MP) | ENFORCED — creek `prohibit unless crossing` + ford `add`; VM (plain creek = None; bridge 1 MP; Alexander's Bridge case) |
| M.12 | 5.24 | river hexes / river ferry hexes | UNREACHABLE — component absent: TEC prints both rows "(Shiloh, Antietam only)"; terrain.json census = clear 241 / forest 300 / forest_rough 121 / rough 12 / offmap 54, no river or ferry hex exists |
| M.13 | 5.23+5.25 | ford×trail cost composition (both printed on the same hexsides, rules silent on combining) | ENFORCED — trail-capped base + ford surcharge; declared ruling already registered (`source_defects.ford-trail-cost-composition`); VM pins both map cases (2320→2420 = 3; 1926→2026 = cap+1) |
| M.14 | 5.31/5.33 | free, unlimited pass-through of friendly-occupied hexes | ENFORCED — pass-through never blocked, only `_stack_ok` gates ENDING (gamespec.py:463/:530); VM pass-through case |
| M.15 | 5.32 | max TWO units per hex at end of any phase | ENFORCED — `can_end`/`_stack_ok` + reinforce-unstacked + retreat-stacking + displacement 1-for-1 make overstacking structurally unreachable; VM stacking block |
| M.16 | 5.34 | friendly ZOC never inhibits friendly movement | ENFORCED — ZOC computed for the enemy side only (`zoc_hexes` gamespec.py:369); VM stacking cases move with friends on board |

### Z — ZONES OF CONTROL (6.x) — four-row minimum from the handoff, split further where separately checkable

| row | rule | requirement | status |
|---|---|---|---|
| Z.1 | 6.0/6.1 | every unit exerts ZOC into all six adjacent hexes, throughout the GT, any phase, never negated by units | ENFORCED — `zoc_hexes`/`_zoc_neighbors` gamespec.py:369/:350; VM |
| Z.2 | 6.0 | a unit must CEASE movement when it enters an EZOC hex | ENFORCED — `stop_on_enter` halts Dijkstra expansion (gamespec.py:569); VM "movement ceases on EZOC entry" structural check |
| Z.3 | 6.2 | no extra MP to enter an EZOC hex | ENFORCED — no cost hook on ZOC (move_cost never reads ZOC); VM "may enter the EZOC hex 2123" |
| Z.4 | 5.13/6.3/10.2 | a unit may never EXIT an EZOC hex during any Movement Phase — only by combat retreat/advance or removal of the exerting unit | ENFORCED — `locked_at_start` zeroes destinations (gamespec.py:536/:675); VM "unit starting in an EZOC may not move"; VGa §B:128 |
| Z.5 | 6.6 | ZOC never extends through a non-bridge non-ford creek hexside (and never into river ferry hexes) | ENFORCED — `blocked_by_prohibited_hexsides` + the crossing data (game.json zoc cite); VM both directions (no ZOC across plain creek; ZOC across the bridge). Ferry clause UNREACHABLE — no ferry hex exists (census, M.12) |
| Z.6 | 6.4/6.5 | ZOCs are mutual and co-exist; multiple exerters add nothing | ENFORCED — symmetric set-union computation, no multiplicity term (gamespec.py:369-376); VM |

### RF — REINFORCEMENT ENTRY (15.x) — a Movement-Phase action type

| row | rule | requirement | status |
|---|---|---|---|
| RF.1 | 15.0 | column entry: 1st unit 1 MP, 2nd 2 MP, 3rd 3 MP…; owner picks order and moment | ENFORCED — `cost = 1 + entered` :488; one global column per player-turn (declared reading of "and/or" — the 15.3 excess rule is the column binding); VGa §A:108-117 |
| RF.2 | 15.1/15.4 | enter at a charted southern-edge hex, during the movement phase, never stacked | ENFORCED — `_propose_reinforce` :465 (hex list, phase, occupancy); VGa §A |
| RF.3 | 15.2 | once entered, a unit "may move and attack freely, just as any other unit" (remaining MA spendable) | ENFORCED — the entry stores its column cost as a NEGATIVE spend (`moved[pid] = -cost`); the move door treats a negative entry as an unfinished single move: `dests` computes with the remaining budget, the apply writes the cumulative spend, a stop locks the unit for the phase ([5.17] reads spend ≥ 0); the exit door and the UI panels read `abs()`. VGa §K proves all four arms: continuation at remaining MA, cumulative spend 1+1, second-move refusal, post-entry attack in the combat phase, and the 6-MP column entry leaving no MA. **Closed N9, 2026-08-16** |
| RF.4 | 15.3 | excess units roll to later GTs | ENFORCED — pool retains pid; column-cost refusal :489-491; VGa §J stages the full column (units 1–6 at costs 1–6 accepted, the 7th refused at 7 MP > MA [15.0/15.3], held in pool, entering next GT at cost 1) |
| RF.5 | 15.5 | may enter an EZOC hex; delayed only while BOTH entry hexes are physically occupied | ENFORCED — occupancy-only test :483-487 (no ZOC check — deliberate); VGa §A (occupied-hex refusals) |
| RF.6 | 15.51/15.52 | the printed schedules: Union 0728/1027 (GT2 ×12, GT5 ×9, GT6 ×3cav, GT7 train, GT8 ×1cav); CSA 1627/1928 (GT2 ×9, GT5 ×4cav, GT8 ×1cav) | ENFORCED — scenario `reserve` data cross-checked against `rules_transcription.json` per (GT, class, strength) + entry hexes, both sides, on every run (validate_scoring.py §1 — **closed N22**); VGa §A exercises the entry machinery on the real scenario; VA campaigns place the schedule |
| RF.7 | 10.2 | at night, reinforcement entry may not enter an EZOC hex (entry is movement, 15.1) | ENFORCED — night/EZOC test in `_propose_reinforce` (bluegray.py, after the occupancy check; VGa §F stages all three arms: night+EZOC refused [10.2/15.1], night+clean hex accepted, day+EZOC accepted — EZOC is not occupancy [15.5]). **Closed N7, 2026-08-16** |

### EX — EXITING THE MAP (16.x) — a Movement-Phase action type

| row | rule | requirement | status |
|---|---|---|---|
| EX.1 | 16.0/16.1 | exit hexes are 0101 and 0111 (1975 prints "0110"; resolved defect — see `source_defects.exit-hex-0110-vs-0111`, Deluxe 18.3 concurs) | ENFORCED — `exit_hexes` from game.json exit.hexes :50; VGa §G |
| EX.2 | 16.2 | exiting costs 1 MP within the unit's MA | ENFORCED — `spent + mp <= budget` :503-505; VGa §G |
| EX.3 | 16.3/16.4 | exited units are out permanently, counted for VP, never "eliminated" | ENFORCED — `exited` map + `_final_scoring` :1230-1236; VGa §G:273 |
| EX.4 | 16.5 | no exit except at the two hexes | ENFORCED — hex membership test :501 + refusal off-hex VGa §A:98 |
| EX.5 | 16.6 | no exit in fulfillment of a combat retreat — eliminated instead | ENFORCED — structurally: retreat destinations are on-map neighbors only (`_retreat_hexes` :705, no exit door); VC §7 |
| EX.6 | 16.7 | unlimited exits per hex | ENFORCED — no counter on exit; VGa §G |
| EX.7 | 5.13/6.3 | a unit on an exit hex that is enemy-controlled may NOT exit (EZOC exit bar applies — only combat frees it, and 16.6 bars that) | ENFORCED — `_propose_exit` EZOC membership test (bluegray.py, after the hex-membership check; the exit door has no Dijkstra so the bar is explicit); VGa §G stages both arms (refused with the Confederate on 0201 controlling 0101; the clean-arm acceptance is §G's original session). **Closed N1, 2026-08-16** |
| EX.8 | 16.0/17.11 | WHO may exit: 1975 says "Union Units"; the same folder's VP schedule scores Confederate exits ×10 — Deluxe 18.3 corrects to "Either Player" | ENFORCED (unproven, CSA arm) — code has no side restriction on exit :494 (both sides may exit = the Deluxe correction; **N13** registers the 1975 internal inconsistency). Union exit arm VGa §G; the CSA-exit-to-VP arm blocked by **N25** (the LOC gate is dead on fragmented road data) |

### C — COMBAT PHASE CORE (7.0–7.5, 7.9, CRT)

| row | rule | requirement | status |
|---|---|---|---|
| C.1 | 7.0 | combat between adjacent opposing units is mandatory (artillery the only non-adjacent attacker) | ENFORCED — `_contacts` :306 + `_propose_end_phase` :860 refuse phase close while contacts are unengaged; VGa §B:134 |
| C.2 | 7.0 | odds = attack strength ÷ defense strength, rounded down in the defender's favor (13:4 → 3-1) | ENFORCED — `odds` gamespec.py:708; VC §2 |
| C.3 | 7.11 | every enemy unit with a friendly unit in its ZOC must be attacked | ENFORCED — `un_att` sweep :870; VGa §B (end_phase refused until the contact is attacked) |
| C.4 | 7.12 | every phasing unit in an EZOC must attack; every adjacent friendly unit participates | ENFORCED — `un_fgt` sweep :877; VGa §B |
| C.5 | 7.13 | attackers from up to six adjacent hexes + any artillery in range | ENFORCED — by construction (any adjacent set + bombard checks); VGa §B/§H |
| C.6 | 7.14 | a unit attacks max once per Combat Phase; an enemy unit is attacked max once (7.74 bombardment exception aside) | ENFORCED — `fought`/`defended` maps :535-544 (+ retreat exception :542-544); VGa §B |
| C.7 | 7.15 | attack only when adjacent (exception 8.0), and only across crossable hexsides (TEC: attacks cross bridges/fords only) | ENFORCED — `_engage_adjacent` :145 on every melee attacker-defender pair :604-614; VC §3 |
| C.8 | 7.21 | a defending stack is attacked as one total strength; no withholding | ENFORCED — `stackmates` refusal :549-561; VC §3 |
| C.9 | 7.22 | co-stacked attackers are one integral combat strength — never separate attacks | OPEN — **N6**: the engine refuses the SECOND separate attack (:566-573) but ACCEPTS the first partial attack while the co-stacked partner is itself contact-obligated (7.12) — after which the partner can never legally fight and `end_phase` deadlocks. Strict-reading fix + validator both owed (the refusal half is currently unproven — folded into N6's close) |
| C.10 | 7.23 | a unit in the ZOC of >1 enemy must attack all of them not engaged by others | ENFORCED — the same `un_att`/`defended` machinery treats each contacted enemy independently :870; VGa §B (single-enemy staging = the minimal case) |
| C.11 | 7.24 | units in different hexes may combine against one hex | ENFORCED — multi-attacker battles; VC §3/§5 |
| C.12 | 7.25 | in multi-hex combat ALL attackers adjacent to ALL defenders, plus bombarding artillery exempt from adjacency | ENFORCED — per-pair adjacency test :604-614, bombards exempt; VC §3 |
| C.13 | 7.3 | a unit's combat strength is unitary — never split between combats | ENFORCED — structural (a unit is in one battle; `fought` bars a second); VC §3/§5 |
| C.14 | 7.4/TEC + Deluxe 7.4 | defender doubled in rough / forest+rough; multiplier, effects NOT cumulative — single best benefit | ENFORCED — `defense_double_terrain` + the one-doubling-per-hex logic :673-695 (terrain takes precedence, hexside checked only if terrain didn't double — never both); VGa §E, VC §2/§4 |
| C.15 | 7.5 | diversionary attacks at poor odds are legal | ENFORCED — any column ≥ 1-5 attackable; 7.9 covers deliberate reduction; VC §14 stages the 2-vs-14 attack and asserts acceptance |
| C.16 | 7.6 | the CRT itself (10 columns × 6 rows) and the note >6-1→6-1, <1-5→1-5 (both still roll) | ENFORCED — game.json `crt` re-checked against BOTH printings on every run; VC §1 (60 cells), high clamp VGa §D:204, low clamp VC §14 (natural 1-7 rolls on the 1-5 column) |
| C.17 | 7.6/7.9 | the attacker may voluntarily reduce the odds column before the roll, never after | ENFORCED — `odds_reduce` ≤ computed odds + valid column :616-626 (atomic propose-resolve makes "before the roll" structural); VGa §D:206-208, VC §2 |
| C.18 | TEC + Deluxe 9.0 | defender doubled behind a bridge/ford hexside only when ALL adjacent attackers cross such a side (bombarders don't count) | ENFORCED — per-hex `all(...)` over adjacent melee :680-687; VC §4 (doubled across the ford; voided when one attacker crosses open ground) |
| C.19 | Deluxe 9.0 (SPI clarification) | a unit attacked SOLELY by bombarding artillery is doubled when the LOS crosses a ford/bridge/creek hexside or an impassable hex | ENFORCED — `_los_crosses_double` :369 + the no-melee branch :688-694 (off-map sampling hexes read as impassable — declared reading, LOS near map edges only); VC §10 stages both arms on the real creek (crossed 3v6 = 1-2; clear control 3v3 = 1-1) |

### B — ARTILLERY (8.x) — the intricate subsystem, line-by-line per the handoff

| row | rule | requirement | status |
|---|---|---|---|
| B.1 | 8.0/8.41 | artillery in an EZOC fights as a normal unit and may NOT bombard | ENFORCED — EZOC membership bars bombardment :582-585; VGa §H:333 |
| B.2 | 8.11 | may attack non-adjacent units 2–3 hexes out; never forced to bombard merely by range | ENFORCED — range window + voluntariness (no obligation test for range) :577-596; VGa §H:291 |
| B.3 | 8.12 | range counts the target hex, excludes the firer's | ENFORCED — `hex_distance` (gamespec.py:197); VGa §H:287 |
| B.4 | 8.13 | a bombardment-only attack hits a single hex (combined attacks excepted) | ENFORCED — refusal :599-603; positive VC §6, negative VC §11 (both single-hex arms accepted, the two-hex pure bombardment refused [8.13]) |
| B.5 | 8.14 | two artillery in one hex bombarding must share the target | ENFORCED (unproven negative) — enforced via the 7.22 co-stacked mechanism (:566-573, a second separate attack is refused); positive case VC §6 (stacked pair, one target). Negative + N6's fix land together |
| B.6 | 8.15 | bombarding artillery suffers no combat results (never destroyed/retreated by its own attack) | ENFORCED — `victims = melee_ids` / pure-bombard no-op :1027-1061; VC §6 |
| B.7 | 8.16 | bombarding artillery MAY voluntarily elect to suffer Ar | OPEN — **N10**: no door exists; a pure-bombard Ar is a forced no-op :1058-1061. Loud incompleteness (a printed option the gate cannot express) |
| B.8 | 8.21 | combined attacks: bombard strength joins adjacent friendly attackers | ENFORCED — bombard ids ⊆ attackers :524 + strength summed in `_battle_odds` :667; VGa §H |
| B.9 | 8.22 | in a multi-hex combined attack, artillery need range/LOS to only ONE defending hex | ENFORCED — the any-defender loop :586-596; VC §12 (artillery 4 hexes from the far defender joins the multi-hex combined attack) |
| B.10 | 8.23 | in combined attacks inf/cav suffer all results; bombarding artillery does not | ENFORCED — Ar/Ae pendings carry melee-only unit lists :1027-1061; VC §13 stages both results on a mixed attack (Ar: retreat list = the melee unit only; Ae: melee eliminated, battery and defender both alive) |
| B.11 | 8.31/8.34 | LOS center-to-center; blocked by intervening blocking terrain; firer's and target's hexes never block | ENFORCED — `_hex_line`/`_los_clear` :325-367 (endpoints excluded); VGa §H (clear accepted :291, blocked refused :320) |
| B.12 | 8.32 | LOS congruent to a hexside blocks only if BOTH adjacent hexes block | ENFORCED — congruence pair logic :337-366; VGa §H |
| B.13 | 8.33 | blocking terrain = forest (incl. forest+rough) and town; rough alone never blocks | ENFORCED — `los_blocking_terrain` [forest, forest_rough] + forest cases VGa §H. Town clause UNREACHABLE — TEC prints town "(Cemetery Hill, Antietam only)"; census: zero town hexes |
| B.14 | 8.35 | artillery fires over units, enemy or friendly | ENFORCED — LOS tests terrain only, never occupancy :352-367; VGa §H |
| B.15 | 8.42/8.43 | from an EZOC an artillery attacks as many adjacent units as it likes and suffers all results | ENFORCED — normal-attacker path + `strength`/result application; VGa §B/§H |
| B.16 | 8.44 | terrain does not prohibit artillery attacks into adjacent hexes | ENFORCED (declared reading) — adjacency attacks ride C.7's door: `_engage_adjacent` tests the hexside, never the intervening terrain (no terrain bar exists at range 1 to remove); VC §3 |
| B.17 | 8.45 | across a creek hexside from its only adjacent enemy, artillery may bombard anything in range — "even the adjacent unit across the Creek hexside" | OPEN — **N11**: the engine's range window is strictly 2–3 (:577), so the adjacent unit can never be bombarded; under a strict 2–3 reading 8.45's final clause is void text, under the lenient reading the engine refuses a legal bombardment. Printed-range tension (8.0 "two or three hexes" vs 8.45) carried verbatim by Deluxe — register candidate, engine currently strict |
| B.18 | 8.51 | artillery never adds strength to another unit's defense; bombards only in its own combat phase | ENFORCED — no defensive-strength path exists (defense totals read target-hex occupants only, `_battle_odds` :676-695, exercised VC §2/§4) + the combat-phase gate :513 (VGa §B) |
| B.19 | 8.52 | attacked artillery (incl. bombarded) suffers all results normally | ENFORCED — defenders take results :1024-1061; VC §8 (bombarded stack includes the retreat rule) |

### R — RETREAT INTERRUPT (7.7)

| row | rule | requirement | status |
|---|---|---|---|
| R.1 | 7.71 | owner retreats each unit one hex out of all EZOCs, direction owner's choice, stack may split | ENFORCED — retreat pending `by` = owning side :745-751 + `_retreat_hexes` :705; VGa §B, VC §7 |
| R.2 | 7.72 | never into a prohibited hex/hexside or EZOC; no hex open ⇒ eliminated | ENFORCED — `open_h` empties ⇒ elimination accepted :758-765; VC §7 (surrounded defender) |
| R.3 | 7.73 | may join a friendly stack (within limits) not in an EZOC, else displace (7.8) | ENFORCED — stacking-aware hex classes :728-738; VC §7, VR |
| R.4 | 7.74 | a unit retreated this phase contributes NO strength if its new hex is attacked, but suffers the result | ENFORCED — `retreated_phase` excluded from defense :678-679, re-bombardment exception :542-544, results still applied; VC §8 (odds pinned 1-2 not 1-3) |

### D — DISPLACEMENT INTERRUPT (7.8)

| row | rule | requirement | status |
|---|---|---|---|
| D.1 | 7.81 | displace only when no other retreat path; displaced unit retreats likewise; never into EZOC/prohibited; 1-for-1 per stack | ENFORCED — displacement offered only when `open_h` empty :769-774, chain resolution :1118-1131; VR |
| D.2 | 7.82 | if the displacement would eliminate the displaced unit, the RETREATING unit is eliminated instead | OPEN — **N4**: the engine eliminates the displaced unit when its own retreat finds no hex (:1110-1111 → `_eliminate [7.72]`; anchor corrected in the 2026-08-16 audit from :1131, which is the retreat event line); print swaps the fates. Silent incorrectness, reachable in crowded pockets |
| D.3 | 7.82 | displacement chains (chain reactions) resolve | ENFORCED — displaced units join the pending queue :1124-1127; VR (the captured cycle fixture resolves to completion) |
| D.4 | 7.81 | displaced artillery that has not yet engaged may not fire this Combat Phase | OPEN — **N5**: no displacement state exists; a displaced, unfired battery can still bombard. Silent incorrectness; all six batteries reachable |
| D.5 | 7.82 | a unit may be displaced more than once per Combat Phase if that is the only path | ENFORCED (declared ruling) — the per-battle `chain` cycle guard ends impossible chains in elimination instead of recursing (:737-742) — the printed text, read literally, permits non-terminating cycles; the engine's terminating resolution is regression-pinned (VR). **N14** registers the printed defect |

### A — ADVANCE INTERRUPT (7.75/7.76)

| row | rule | requirement | status |
|---|---|---|---|
| A.1 | 7.75 | ONE victorious unit that participated may advance into the vacated hex (bombarding artillery excluded — at range) | ENFORCED — `_offer_advance` candidates :1080-1092; VC §9 |
| A.2 | 7.75 | advance into a VACATED hex only; max one hex; adjacency + crossable side | ENFORCED — `_offer_advance_vacated` :1094 + dest tests :800-808 (crossable bar = 5.25's blanket "never cross creek" applied to advance — declared reading) |
| A.3 | 7.75 | regardless of enemy ZOC; optional (decline is a real choice); must be exercised immediately, before any other combat resolution | ENFORCED — no ZOC test :788-809; decline :795; pending blocks all other actions :397-404; VC §9, VGa §B |
| A.4 | 7.75 | an advanced unit may neither attack nor be attacked that phase | ENFORCED — `advanced` excluded from battles :545 and from contacts :311-321; VGa §B |
| A.5 | 7.76 | only one unit advances even if a single combat vacated two hexes | ENFORCED — one advance action clears the pending :1141-1154; VC §9:283-285 |

### X — EXCHANGE INTERRUPT (7.6 Ex)

| row | rule | requirement | status |
|---|---|---|---|
| X.1 | 7.6 | all defenders eliminated; attacker eliminates participating units whose total PRINTED strength ≥ the defenders' printed total; bombarding artillery immune and unchoosable | ENFORCED — pending `owe`/`units` = melee only :1032-1044; `_propose_exchange_loss` :811-839; VC §5 (owe = printed 2, not doubled 4) |
| X.2 | 7.6 | "at least equals" — the printed rule also permits over-removal | ENFORCED (stricter than print) — the engine refuses unnecessary over-removal :833-838 (note: over-removal can only gift the enemy VP; refusal is conservative and outcome-favorable, recorded as a declared strictness) |
| X.3 | 7.6 | only units which participated may be eliminated | ENFORCED — subset test :819-822; VC §5 stages the in-set payments, the over-removal refusal, and the non-participant refusal |

### T — THE UNION TRAIN (18.x)

| row | rule | requirement | status |
|---|---|---|---|
| T.1 | 18.11/18.12 | never attacks; defense strength 1 | ENFORCED — attacker refusal :547-548; stats [0,1,6]; VGa §I |
| T.2 | 18.11 | WHENEVER adjacent to a Confederate unit in the Union Combat Phase it must auto-retreat; no Confederate advance after | OPEN — **N3**: armed only at the phase-start transition (:934) — a Confederate ADVANCE during the Union combat phase landing adjacent never arms it (and `train_checked` short-circuits the end_phase recheck :867). The start-of-phase arm is §I-proven; the mid-phase arm is missing. Silent incorrectness |
| T.3 | 18.21 | never stacks with anyone | ENFORCED — train excluded from every stacking door (`rules_board` flip :115-129, `_train_dests` occupancy :189, `_retreat_hexes` :729-732); VGa §I |
| T.4 | 18.22 | no unit moves through its hex; it moves through no one (both directions) | ENFORCED — symmetric blocking via the side flip; VGa §I:347 |
| T.5 | 18.23 | MA 6, roads/trails ONLY; forced retreat to a non-road/trail hex destroys it | ENFORCED — `_road_or_trail` gate :186-187/:724-725, destroy on no-open :853-854; VGa §I:365 |
| T.6 | 18.24 | may displace and be displaced, may retreat | ENFORCED — the generic 7.8 displacement/retreat doors contain NO train carve-out (the only train exclusions are stacking/transit/attack), and those doors are VR-proven for units; the train's participation is the absence of an exclusion — noted so nobody reads a train-specific test into VR |
| T.7 | 18.25 | no ZOC; Confederates never required to attack it; (it remains subject to enemy ZOC) | ENFORCED — `exempt_classes:["train"]` + contact exclusion :313-317; ZOC-lock VGa §I:356 |

### N — NIGHT GAME-TURNS (10.x) — GT 9

| row | rule | requirement | status |
|---|---|---|---|
| N.1 | 10.0/10.1 | the Combat Phase is omitted entirely; no combat of any kind, no bombardment | ENFORCED — night skips the combat phase :928-942 + battle refusal :515-516; VGa §F:252-255 |
| N.2 | 10.2 | units may not ENTER an EZOC during a night GT (units already in one may not exit — 5.13, already Z.4) | ENFORCED — `dests` night filter :162-164; VGa §F:250. The reinforcement-entry arm is RF.7 (OPEN, N7) |

### V — VICTORY & SCORING (17.x)

| row | rule | requirement | status |
|---|---|---|---|
| V.1 | 17.0/18.4 | most VP at game end wins (a tie prints "draw" — the rules are silent on ties; declared) | ENFORCED — `_final_scoring` :1289-1293; VGa §G; the tie reading pinned by validate_scoring.py §6 (exact 10-10 → draw) |
| V.2 | 17.11 | 1 VP per enemy CSP eliminated (live accrual) | ENFORCED — `_eliminate` :1073; every validator's battles |
| V.3 | 17.11/17.31 | exit VP: Union 1/CSP; Confederate 10/CSP gated on the 17.31 LOC | ENFORCED (Union arm) — :1230-1236; VGa §G:273. CSA arm: unprovable on current data — the 17.31 trace is dead because the road network is fragmented (**N25** wrong data; was N15's missing test, found trying to write it) |
| V.4 | 17.11 | CSA +10 if the Train fails to exit (destroyed ≠ exited) | ENFORCED — :1237-1241; VGa §G:274 |
| V.5 | 17.12/17.21/17.22 | occupation = last side to move a unit onto/through the hex | ENFORCED — `_credit_occupation` :282, all three writers proven (move/reinforce/advance each staged, credit + VP asserted; validate_scoring.py §3/§4/§5). **N8** still flags the retreat/displacement arm as a declared narrow reading (Bruce) |
| V.6 | 17.12 | end-of-game scoring of the seven VP hexes (union/confederate/either pools) | ENFORCED — :1242-1250; pool-owner semantics pinned exactly (union-pool scored, enemy-held confederate-pool hex unscored, unheld either-pool unscored; validate_scoring.py §3, plus the draw case §6) |
| V.7 | 17.23 | start occupation seeded (Union 0211/0502/0822/1108/1115; CSA 1920/2311) | ENFORCED — `new_game` :64-68; validate_scoring.py §2 (real scenario seeding exercised end-to-end by every VA campaign) |
| V.8 | 17.31 | CSA LOC: a continuous road chain from 0101/0111 off the EASTERN edge, free of Union units (ZOCs irrelevant) | ENFORCED (unproven) — road-graph BFS :1210-1227; the `col ≥ 25` proxy is exact on this map — the only road hex at col ≥ 25 is 2503, the network's eastern terminus (terrain.json census). Validator debt **N15**. **2026-08-16: the trace is DEAD on current data — the road graph fragments into 29 components and no exit-hex chain reaches the east edge in any game (N25, wrong data); loc_ok is always False and the CSA exit VP is unawardable** |
| V.9 | 17.32/Deluxe 18.4.3 | Union units unable to trace a ≤10-hex path (EZOC ok, enemy units not) to a road exiting at 0101/0111 are destroyed for VP — "including blocked reinforcements" | OPEN — **N2**: `_final_scoring` sweeps on-map units only (:1266); unentered pool units are never scored (and the Train is excluded — strict "any Union units" would include it, ±1 VP). Silent incorrectness |

---

## §2 STATE LEDGER

All 22 `HASH_KEYS` (bluegray.py:38) — the frozen log contract. State NOT in the hash: `seed`
(immutable after init), `n` (log sequence), `tier` (fixed at construction) — none is game state;
no mutable state escapes the hash. **Finding: none.**

| state | what it holds | written by (rule + code) | read by (rule + code) | reset when |
|---|---|---|---|---|
| `turn` / `phase` / `mover` | GT, phase, phasing side | `_next_player` :966 (4.1), `end_movement` :928 | every propose door :389-428 | continuous |
| `over` / `winner` | game end + result | `_final_scoring` :1289 (17.0) | propose :395 | never |
| `rng_calls` | dice stream position | `roll_die` gate.py:153 (spec #11) | `_rng` replay | never |
| `units` | pid → identity + hex | deploy, `move` :901, `reinforce` :911, retreat :1103, advance :1141, `_eliminate` :1064, `exit` :923 | everything | continuous |
| `moved` | pid → MP spent this movement phase | move :908 (cumulative), reinforce :920 (column cost as a NEGATIVE continuation marker, 15.2) | `_propose_move` (5.17 — spend ≥ 0 = locked), `dests` (remaining budget, 15.2), `_propose_exit` :503 + UI panels (abs, 16.2) | every phase change :929/:973 |
| `pool` | reinforcement pid → due GT | init :75, reinforce pops :918 (15.0/15.3) | `_propose_reinforce` :476 | entries removed on entry |
| `entered` | reinforcement column position this player-turn | reinforce :919 | column cost :488 (15.0) | every player-turn :930/:974 |
| `exited` | pid → side, permanent | `exit` :925 (16.3) | `_final_scoring` :1230 (17.11) | never |
| `dead` | eliminated pids | `_eliminate` :1074, train destroy :1174 | VP already accrued at write | never |
| `vp` | live VP per side | `_eliminate` :1073 (17.11) | `flow()` display | never (exits/occupation added at end) |
| `occ` | VP hex → last side through | init seed :64 (17.23), `_credit_occupation` :282 on move/reinforce/advance (17.21/17.22) | `_final_scoring` :1242 (17.12) | never |
| `attacked` | attacker pid → battle no | `_apply_battle` :1012 | **write-only bookkeeping** (display/history; the 7.14 door reads `fought`) | per combat phase :961 |
| `defended` | defender pid → battle no (the 7.14 "attacked once" door) | `_apply_battle` :1014 | once-bars + `end_phase` :870 (7.11/7.14), 7.74 exception :542 | per combat phase :961 |
| `fought` | attacker pids this combat phase | `_apply_battle` :1011 | 7.14 bar :535, 7.22 bar :566-573, end_phase :877, contacts | per combat phase :962 |
| `advanced` | advanced pids this combat phase | `_apply_advance` :1150 (7.75) | battle bars :545, contacts :311 (7.75) | per combat phase :962 |
| `retreated_phase` | retreated-this-phase pids | `_apply_retreat` :1129 (7.71) | no-strength rule :678 (7.74), re-bombard exception :542 | per combat phase :963 |
| `battle_no` | battle counter | `_apply_battle` :1008 | pending bookkeeping, display | never |
| `pending` | the ONE open interrupt (retreat/advance/exchange/train + chain/vacating/adv_* payload) | battle results :1036-1061, end_movement :936 (18.11) | propose router :397, resolvers :745-858 | on resolution / phase change :976 |
| `train_checked` | 18.11 handled this combat phase | end_movement :940, `_apply_train_retreat` :1186 | end_phase recheck :867 | per combat phase :964 |

Movement↔combat interplay, the section's point: `retreated_phase` is written by the retreat
interrupt and read by the ODDS engine (7.74 — a combat result rewriting the combat map), and
`advanced`/`defended`/`fought` are written by combat and read by the contact obligation door —
both directions live and hashed. `occ` is written by movement and read only at game end (17.12) —
the N8 declared-reading question sits exactly on that seam.

## §3 OBLIGATION FLAGS

| class | rows | status |
|---|---|---|
| **automatic** (gate executes, no player input) | GT advance + interphase (S.2), night phase skip (N.1), VP accrual on elimination (V.2), occupation credit (V.5), train auto-retreat ARMING (T.2 — arming automatic, resolution decisional), final scoring incl. LOC/path checks (V.1/V.3/V.6/V.8/V.9) | ENFORCED (T.2's mid-phase trigger and V.9's blocked-reinforcements arm are N3/N2) |
| **obligatory-decisional** (player must act; gate blocks phase close) | contact-must-attack / must-participate (C.1/C.3/C.4/C.10 — `_propose_end_phase` :860 refuses until every contact is engaged); retreat resolution (R.1); advance-or-decline (A.3); exchange loss (X.1); train retreat (T.2/T.5); pending resolution blocks ALL other actions :397-404 | ENFORCED — what the door does NOT block on: mid-phase train adjacency (N3), the 7.22 partial-attack lock-in (N6), night reinforcement entry (N7) |
| **ordered-or-quantified** | one attack per unit / one defense per unit per phase (C.6); advance before any other combat resolution (A.3); reinforcement column order+costs (RF.1); one move per unit per phase (M.7); combats resolvable in any order the attacker wishes (7.0 — engine imposes none); displacement 1-for-1 (D.1) | ENFORCED |

## §4 UNREACHABLE REGISTER

Every claim carries its evidence kind. Component-absence here is TERRAIN components (map data),
cited to the TEC's own "(…only)" parentheticals + the terrain.json census: clear 241, forest 300,
forest_rough 121, rough 12, offmap 54 — nothing else exists.

| rule(s) | evidence |
|---|---|
| 5.24 river hexes / river ferry hexes (all rules: entry, ferry-through rules, never-end-in-ferry, ferry-hexside doors) | component absent — TEC prints both rows "(Shiloh, Antietam only)"; census: zero such hexes |
| 6.6's river-ferry ZOC clause; 8.33's town blocking clause; TEC town combat column | component absent — same census; town is "(Cemetery Hill, Antietam only)" |
| 11.0 Attack Effectiveness (all of 11.1–11.4: inverted units, ineffective attacks, 11.31 forced retreat) | explicit published exclusion — the rule is titled OPTIONAL and the Chickamauga folder/scenario never invokes it (published default); no ineffective state exists in the gate. **Reclassified from the umpired list** |
| Deluxe "Stream hexside" references (movement 5.2 example, 9.0 doubling) | component absent — no stream terrain on the map (creek only); the 1975 text's own map has none |
| Stafford 2018 additions (min-one-hex move 6.15, leaders, disruption, 2d6 CRT, breastworks) | not a rules-exclusion row — recorded to prevent encoding drift: Stafford is CLARIFICATION ONLY and is in force nowhere |

## §5 NEW GAPS FOUND BY THIS MATRIX (the N-list)

Built 2026-08-15 by the two-directional audit — rulebook → `engine/bluegray.py`/`gamespec.py` line
by line, and code → rulebook. None were on the `rules_scope.umpired` list (that list measured
what was noticed; this measures what is there). Classes: **1** silent incorrectness · **2** loud
incompleteness · **3** wrong data · **4** unchecked obligation · **VD** validator debt (code
exists, believed correct, no proving test — RULE 1 work items).

| # | rule | what's wrong | class |
|---|---|---|---|
| N1 | 5.13/6.3/16.x | exit from an enemy-controlled exit hex accepted — `_propose_exit` :494 never tests EZOC; the endgame the rule guards (units at the gap under pressure) is exactly when it bites — **CLOSED 2026-08-16: explicit EZOC test in the exit door, VGa §G both arms; VR's seed-1 pin unchanged (33/123), VA 5-seed campaigns complete** | 1 |
| N2 | 17.32 | blocked reinforcements (and the Train) never scored as destroyed at game end — `_final_scoring` sweeps on-map units only; Deluxe 18.4.3 says "including blocked reinforcements" verbatim | 1 |
| N3 | 18.11 | train auto-retreat armed only at phase start — a Confederate advance during the Union combat phase landing adjacent ("WHENEVER adjacent") never triggers it | 1 |
| N4 | 7.82 | displacement-that-would-eliminate kills the DISPLACED unit; print eliminates the retreating unit instead (fates swapped) | 1 |
| N5 | 7.81 | displaced, unfired artillery may still bombard — no displacement state exists | 1 |
| N6 | 7.22/7.12 | a partial co-stacked attack is accepted while the co-stacked partner is contact-obligated; the partner can then never legally fight and `end_phase` deadlocks — the phase becomes unwinnable. Strict 7.22 (refuse the partial attack when the partner owes 7.12) + validator | 1 (+2 consequence) |
| N7 | 10.2/15.1 | night reinforcement entry into an EZOC accepted (reachable via any unit delayed onto GT 9 under 15.3) — **CLOSED 2026-08-16: night/EZOC bar in the reinforce door, VGa §F three arms; VR seed-1 pin unchanged** | 1 |
| N8 | 17.21/17.22 | retreats/displacement do not confer occupation credit (engine = deliberate-moves-only reading; the printed "last to have moved a Friendly unit onto the hex" plausibly includes combat moves) — declared reading, Bruce to rule | 1 under the literal reading |
| N9 | 15.2 | a reinforcement's entry cost is treated as its whole movement — post-entry movement refused; print: "may move and attack freely, just as any other unit" — **CLOSED 2026-08-16: negative-spend continuation convention (no new HASH_KEYS entry), VGa §K; policy AI's own gate (`pid in moved`) skips continuations, so VR's seed-1 pin (33/123) and the VA campaigns are unchanged** | 2 |
| N10 | 8.16 | no door for bombarding artillery to voluntarily suffer Ar | 2 |
| N11 | 8.45 vs 8.0/8.11 | the adjacent-unit-across-the-creek bombardment is refused (range strictly 2–3); 8.45's own words make the adjacent unit bombardable, which contradicts 8.0's "two or three hexes" — **register candidate** (ambiguity), engine strict pending the ruling | 2 |
| N12 | 5.17 | "nor may it change its move without the consent of the opposing Player" vs the platform's UNDO (1 press = 1 decision, all games) — the same cross-game item as NaW M.13/MOV-19, already queued to Bruce (NOW.md call #3); recorded so the matrix does not silently bless it | cross-game, Bruce-blocked |
| N13 | 16.0 vs 17.11 | 1975 prints "UNION Units may exit" while the same folder scores Confederate exits ×10 VP — internal inconsistency; Deluxe 18.3 corrects to "Either Player" (engine already Deluxe-correct) — **register candidate**, companion aspect of the registered exit-hex defect | register candidate |
| N14 | 7.82 | the printed displacement rules, read literally, permit non-terminating cycles (proven live: the 14,000-entry loop behind VR); the engine's terminating resolution (impossible chains end in elimination) is a declared resolution of a printed defect — **register candidate** | register candidate |
| N15 | 17.12/17.21–17.23/17.31 | validator debt: occupation credit, start-occupation seeding, occupation scoring, the CSA LOC trace, and a CSA-arm exit (V.3/V.5/V.6/V.7/V.8, EX.8) have code but no asserting test — **CLOSED 2026-08-16 by validate_scoring.py except the LOC/CSA-exit arms, which are blocked by N25** (the trace is dead on fragmented road data; closing them requires the terrain fix first). Also pinned en route: V.1's draw tie and V.9's on-map 17.32 sweep | VD |
| N16 | Deluxe 9.0 | validator debt: the solely-bombarded doubling (C.19) untested — **CLOSED 2026-08-16 by VC §10** (creek-crossed vs clear-ground control) | VD |
| N17 | 8.13 | validator debt: the multi-hex pure-bombardment refusal (B.4) untested — **CLOSED 2026-08-16 by VC §11** | VD |
| N18 | 8.22 | validator debt: the multi-hex combined attack needing range to only one defending hex (B.9) untested — **CLOSED 2026-08-16 by VC §12** | VD |
| N19 | 8.15/8.23 | validator debt: the mixed melee+bombard result split under Ar/Ae (B.10) untested — **CLOSED 2026-08-16 by VC §13** | VD |
| N20 | 7.22 | validator debt: the co-stacked separate-attack refusal's negative case (B.5/C.9) untested — ships with N6's fix | VD |
| N21 | 15.0/15.3 | validator debt (audit 2026-08-16): the column-excess arm (cost 1+entered > MA ⇒ refused, unit rolls to a later GT) untested — **CLOSED 2026-08-16 by VGa §J** | VD |
| N22 | 15.51/15.52 | validator debt (audit 2026-08-16): the reinforcement schedule contents never cross-checked against print — **CLOSED 2026-08-16 by validate_scoring.py §1** (per-(GT, class, strength) multiset + entry hexes, both sides, vs rules_transcription.json) | VD |
| N23 | 7.5/7.6 | validator debt (audit 2026-08-16): no poor-odds battle staged asserting acceptance (C.15), and the <1-5→1-5 low clamp (both still roll) untested (C.16) — **CLOSED 2026-08-16 by VC §14** (2-vs-14 accepted, natural 1-7 → column 1-5, still rolls) | VD |
| N24 | 7.6 | validator debt (audit 2026-08-16): the exchange non-participant refusal (X.3 subset door :819-822) never staged — **CLOSED 2026-08-16 by VC §5** (bystander refusal added) | VD |
| N25 | 5.22/17.31/18.23 | **WRONG DATA (found staging N15, 2026-08-16): the road network in terrain.json fragments into 29 disconnected components** — `_road_graph` from the exit hexes reaches ≤27 of 174 road hexes, never col ≥ 25, so `csa_loc_road_clear` is False in every reachable game and the 17.31-gated CSA exit VP (V.3/EX.8) is dead code; units overpay at every under-captured road junction (5.22); the Train's network is pocketed (18.23). Verified against the 1975 scan: solid printed roads run through the fragment gaps (e.g. 0417, 0217/0218, 0715) — the build_terrain.py solid-line discriminator (≥0.78 coverage) under-captured. Fix = recalibrate + per-side scan verification + validator; margin baseline MUST precede it (Stage C ordering already does). Escalated to Bruce 2026-08-16 | 3 |

Related but NOT new: the three registered `source_defects` (exit-hex 0110→0111; ford+trail
composition; CSA exit-VP asymmetry) are enforced as registered and cited in their rows (M.13,
EX.1, V.3). The prior `umpired` list reclassifies as: 11.0 → UNREACHABLE (§4); ford+trail →
ENFORCED with declared ruling (M.13); 5.17 → split M.7 ENFORCED + N12 cross-game. All three
reclassifications were verified independently against print and code, not copied from the prior
analysis.

## §6 PLAYABILITY VERDICT

**BUILD IN PROGRESS. build_open: 7.**

Row counts: **117 rows** — ENFORCED 109 (fully proven 106, plus ENFORCED-unproven 3: EX.8, B.5,
V.8 — B.5 rides N6/D6; EX.8+V.8 blocked by N25),
UNREACHABLE 1 full row (M.12) plus two unreachable
sub-clauses (Z.5 ferry clause, B.13 town clause), **OPEN 7** (C.9, B.7,
B.17, D.2, D.4, T.2, V.9 — EX.7/N1, RF.7/N7, RF.3/N9 closed 2026-08-16).

**Stage-A audit 2026-08-16 (pre-enforcement re-verification of this file):** every code anchor
re-checked against `bluegray.py`/`gamespec.py` at `7c69220` — one wrong anchor corrected (D.2
:1131 → :1110-1111); every validator-section claim opened and tested against what the section
actually asserts — five rows re-statused for citing tests that don't exist or don't assert the
rule (RF.4 phantom §A test, RF.6 "VG §A" miscite, C.15/C.16-low unasserted, X.3 negative
unasserted), four new validator-debt items N21–N24; both UNREACHABLE claims and both
sub-clauses re-proven against RULE 2 (census re-counted from terrain.json: clear 241 / forest
300 / forest_rough 121 / rough 12 / offmap 54; `2503` re-confirmed the only road hex at
col ≥ 25; the three registered `source_defects` IDs confirmed); ten-spot code→rulebook sweep
clean (every legality door in `propose`/`_propose_*` maps to a row). N1–N20 unchanged.

Blocking rows: N2 (V.9), N3 (T.2), N4 (D.2), N5 (D.4), N6 (C.9),
N10 (B.7), N11 (B.17). Five are class-1 silent incorrectness — the class this instrument exists
to surface. Demotion of a shipped game is the expected outcome Bruce predicted 2026-08-08 ("the
audit can DEMOTE shipped games"): Chickamauga shipped at earned Tier 3 under the tier ladder the
coverage matrix has since replaced; under spec #13 as amended it is BUILD IN PROGRESS until the
N-list closes (Bite 4 ships each closure with a validator; the two register candidates and the
two Bruce-flagged items route per spec #21).

Suite state at this writing: `python run_all.py` 38/38 green (no code changed in this bite — the
matrix is the change). `rules_scope.umpired` still sits in the scenario file untouched, by design
— retiring it is Bite 3.

*Maintained by hand during the build; every closed row must name its validator in the same commit.*
