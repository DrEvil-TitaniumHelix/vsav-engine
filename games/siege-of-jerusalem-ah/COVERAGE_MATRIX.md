# COVERAGE MATRIX — The Assault of Gallus (Siege of Jerusalem, AH 1989)

**The instrument defined by PLATFORM_SPEC #13 (amended 2026-08-09): this matrix IS the playability
rating.** The scenario is **playable** exactly when every row below is `ENFORCED` or `UNREACHABLE`.
There is no third acceptable state; an `OPEN` row is a named defect that blocks playability.
Internal report — builder + testers, never player-facing.

Scope: **PER SCENARIO** — this file covers *The Assault of Gallus* only. The unreachable column is
never inherited by any other scenario.

**Status values**
| status | meaning | must carry |
|---|---|---|
| `ENFORCED` | the gate checks it | code location + the validator that proves it |
| `UNREACHABLE` | cannot arise in Gallus | one of the four valid evidence kinds (see SOJ_HANDOFF §0) |
| `OPEN` | reachable, not (fully) enforced | the work item that closes it (A#/B#/N#/R#) |

Work-item keys: `A#`/`B#`/`R#` = SOJ_HANDOFF.md items. **`N#` = new gaps found building this
matrix** (§5) — they were on no prior list; audit source was the rulebook/card read against
`engine/soj.py` line by line, per SOJ_HANDOFF §2.

Validators (all in `games/siege-of-jerusalem-ah/`): `validate_grid.py` (VG), `validate_deploy.py`
(VD), `validate_movement.py` (VM), `validate_combat.py` (VC). New enforcement ships only with a
validator proving it against a worked example or printed table (spec #12).

---

## §1 PHASE SPINE

Gallus turn = **8 phases** (4.1–4.3) + one-off deployment. Game opens with the **Roman Fire Phase**
(card). Turns 8–10 are night. Each Fire Phase has two ordered segments: **non-phasing side fires
first**, then the phasing side (no printed intra-segment ordering — see F.2).
Judaean Rally's reserve sub-step never runs in Gallus (card: reserves not used).

### P0 — DEPLOYMENT (one-off; Judaeans first, then Romans; card + 3.3/3.4)

| row | rule | requirement | status |
|---|---|---|---|
| P0.1 | card | Judaeans deploy first, inside New City / on its outer walls | ENFORCED — `_deploy_verdict` jud_zone; VD |
| P0.2 | card SR1 | ≥1 unit in each North Wall Bastion/Fortress O50..QQ29 (21 hexes) before deploy_done | ENFORCED — `_deploy_done_verdict` min_force; VD |
| P0.3 | card | Romans second, outside Jerusalem, ≥5 hexes from any Elevated hex, after observing | ENFORCED — `_roman_zone`; VD |
| P0.4 | card | Romans never enter Garrison Areas | OPEN → **R1** (only the 2 example hexes encoded; area extents are Rob's) |
| P0.5 | 6.2/6.4/8.4/8.5 | per-class placement: no cavalry/SE/Roman artillery on Elevated; Cauldrons Elevated-only | ENFORCED — `_deploy_verdict`; VD |
| P0.6 | 2.46/8.4 | Judaean Ballista/Onager/Catapult set up on Elevated only | UNREACHABLE — units absent from Gallus OOB (card; counter census `COUNTERS_VERIFIED.md`) |
| P0.7 | 3.4 | Roman Artillery may set up Fresh **or** Disrupted (player's choice) | OPEN → **N13** (deploy places every unit fresh; option denied) |
| P0.8 | 3.4 | Roman Infantry may set up in Testudo | OPEN → **N13** + B13 |
| P0.9 | 3.3 | off-board Legion setup w/ recorded turn/edge | OPEN → **N17** — verify the Gallus card permits/forbids it, then enforce or evidence unreachable |
| P0.10 | 6.x | stacking legal at end of deployment | ENFORCED — `_stack_check` in deploy; VD |

### P1/P5 — RALLY PHASE (Roman 4.11 / Judaean 4.21)

| row | rule | requirement | status |
|---|---|---|---|
| R.1 | 4.11/17.1 | rally attempt is **mandatory** for every Disrupted/Routed/Panicked non-Artillery unit, one roll each | ENFORCED (automatic at end_phase) — `_rally_side`; VC |
| R.2 | 17.1 | order: HQ first, then alpha-numeric hex order | ENFORCED — `order_key`; VC |
| R.3 | 17.1 | Artillery/Cauldron rally is optional (owner lists which roll) | ENFORCED — `artillery_pids` param |
| R.4 | 4.11/2.55 | success ladder: Disrupted→Fresh; Routed→Disrupted (stays Disrupted); Panicked→Routed | ENFORCED — `_rally_side`; VC |
| R.5 | 17.2 | failure ladder: adj 7 = Rout (from Disrupted), 8 = Panic, ≥9 = eliminated | ENFORCED — `_rally_side`; VC |
| R.6 | Rally Table | all 12 drm causes, cumulative, each once per unit | ENFORCED — `_rally_side` + game.json `rally.drm`; VC |
| R.7 | 17.3 | HQ cannot modify own roll; Judaean Artillery+Zealots respond only to Commander | ENFORCED — `_hq_affects` |
| R.8 | 17.3 (Q&A) | leader and Commander rally drm are separate and additive | ENFORCED — confirmed decode-prep 6; do not re-litigate |
| R.9 | 4.21 | Judaean reserve activation sub-step (before rallying) | UNREACHABLE — card: "Reserves (18.61) and Garrison forces (18.4) are not used" |
| R.10 | 5.12 | units need not be in CC to rally; +1 drm if out of CC | ENFORCED — `_rally_side` (in_cc check) |
| R.11 | 17.24/18.22 | +1 within range+LOF of Fresh enemy missile unit (not artillery/rock; adjacent-only at night) | ENFORCED — `_enemy_missile_threat` |

### P2/P6 — FIRE PHASE (4.12/4.22; two ordered segments)

| row | rule | requirement | status |
|---|---|---|---|
| F.1 | 4.12/4.22 | non-phasing side fires first; phasing side only after | ENFORCED — `seg` machinery in `_advance_phase`/`_fire_verdict`; VC |
| F.2 | 4.12/4.22 | intra-segment ordering of Breach attacks vs missile fire | ENFORCED (vacuously) — **no printed ordering exists**: 4.12 lists rams-then-missiles, 4.22 lists "fire and conduct Breach attacks" — opposite orders, so the listing is not normative; only non-phasing-first is mandated (F.1). N1 closed as a false gap; correction noted in RULEBOOK_VERIFIED |
| F.3 | 2.52 | fire only by **Fresh** units (Disrupted have no missile/rock capability at all) | ENFORCED — `_fresh` checks in fire/breach verdicts; VC |
| F.4 | 9.1 | one target hex per firer per phase; each firer fires once | ENFORCED — `fired` list |
| F.5 | 9.1/9.6 | all fire at one target hex combines into a single attack; a hex is missile-attacked once per phase | ENFORCED — `fired_hexes` |
| F.6 | 9.6 | same hex may be Breach-attacked AND missile-attacked in one phase | ENFORCED — breach path doesn't consume `fired_hexes` |
| F.7 | 9.2 | range incl. target hex, excl. firing hex; AF by range band (Weapons Effect Chart) | ENFORCED — `_dist` + `_range_af`; VC |
| F.8 | 9.5 + card | LOF: center-to-center, obstacle classes per LOF Determination Table, closer-to tiebreaks | ENFORCED (4×4 matrix + tiebreaks, cell-exact per decode-prep 6) — `_lof`; VC. Sub-gaps below. |
| F.9 | card LOF | siege-Tower **unit** occupancy = "Fortress, Tower" group on both LOF axes | ENFORCED — `_lof` `has_tower` lifts the hex to the FT row/column. **Tower only, by the card's own text**: the LOF table names "Tower" bare, the card names "Tower/Armored Tower" wherever it means both (9.11/9.13), and the Missile Table rows Armored Tower with Bastion, not Fortress. Armored Towers are moot regardless: **0 in the Gallus OOB** (VC asserts). Tiebreak scoping fixed in the same pass: the card key defines closer-to for **B\*, W\* / B@, W@ only — F and P block unconditionally** (old code wrongly applied \*/@ to F); VC `lof_crest_checks` |
| F.10 | 9.51 | Elevated↔Ground fire blocked by Built-up adjacent to the lower end | ENFORCED (exact) — `_lof`: crossed Built-up adjacent to the ground end blocks both directions; Built-up adjacent to the elevated end does not (the old crossed-hex-P approximation removed). Temple exception 10.3 outside the battlefield; VC `lof_crest_checks` real-map axis |
| F.11 | 9.52 | Ground-to-Ground across elevations: Slope-hex intervening limit | ENFORCED — `_lof`: ground-level LOF crossing an intervening Slope hex may pass through/into at most ONE clear hex (target counts, firing hex excluded per the printed formula), unless both ends share an elevation region (`_build_elevation_regions`: maximal connected non-slope ground areas — "as distinguished by the Slopes"). **Directional by the printed text**: the "exclusive of the firing hex" carve-out only ever binds downhill, so the plateau edge may fire at the slope face while the climber cannot see past the crest — documented + asserted in VC. Printed example TT46/QQ48/RR48/QQ49/BB69/EE67 reproduced (QQ49 leg on the printed-art bastion overlay; the hex is A4-zeroed out-of-scope) |
| F.12 | 9.13 | −1 drm per Tower/Armored Tower hex fired through | ENFORCED — `_lof` info.towers → `_resolve_missile` (per traversed hex, worst-firer convention); VC `fire_drm_checks` |
| F.13 | 9.9 | indirect fire: over ONE combat-unit hex max, ground-ground or same-height elevated, not through higher; −1 drm not cumulative w/ Breach −1 | ENFORCED — `_lof`: same-height-group occupied crossings (infantry/cavalry screen; equipment/HQ do not), >1 blocks, ==1 = indirect; *-pair non-cumulation in `_resolve_missile`; VC `fire_drm_checks`. N4 closed |
| F.14 | 9.3 | Artillery never fires from Built-up/Breach; −1 Judaean artillery beyond Primary Range | hex bar ENFORCED (`_fire_verdict`; VC); the −1 drm is UNREACHABLE in Gallus — the only Judaean artillery in the card OOB is Cauldrons (counter census, units-only evidence; corrects F7's reachability note, which contradicted the census). Build with the campaign scenarios |
| F.15 | 9.31 + Q&A | errant fire on natural 1 vs higher-elevation target: adjacent friendly (ground or elevated) disrupted, defender's choice, never a Base unit w/ climbers | ENFORCED — `_resolve_missile` errant spec → `resolve_errant` pending (defender picks; auto when one candidate; chains after the loss pending); VC `fire_drm_checks`. Base-unit exclusion lands with B12 (no escalades yet). B3 closed |
| F.16 | 9.4 + Q&A 11.1 | units beneath a SE may not fire; **riders atop a Tower may**; Fresh Velitae in Testudo may | OPEN → **B14** (gate refuses all fire from SE hexes — denies legal fire) |
| F.17 | 9.7 | adjacent enemies are mandatory targets (SE/Artillery never mandatory) | ENFORCED — `_fire_verdict`; VC |
| F.18 | 9.7 | among multiple adjacent targets: may not ignore a ZOC-exerter for a non-exerter | ENFORCED — `_fire_verdict` per-firer exerter test via `_unit_zoc` (the per-unit refactor of `_zoc_map`); VC `fire_drm_checks`. N3 closed |
| F.19 | 9.8 + Q&A | Wall attack bonus ×2 straight down connected Wall/Bridge path; **not over intervening units** | ENFORCED — `_wall_bonus`: path check + intervening-unit denial (Q&A 'A. Yes. No.'); gate inconsistency SETTLED: gates are not Wall hexes for 9.8 — a gate resolves on its ring class on every table (decode-prep 6), so all three gate types are excluded; VC `fire_drm_checks`. B5 closed |
| F.20 | 13.2 | column = Primary Target type row; minimum AF per column; attack-multiple ladder | ENFORCED — `_target_row`/`_resolve_missile`; VC (tables cell-exact) |
| F.21 | 13.2 + Q&A | most severe result **must** go to the Primary Target | ENFORCED — loss pending carries `primary` pids (`_primary_pids`); `_resolve_loss_verdict` forces the severest letter onto a surviving primary unit; VC `fire_drm_checks`. B4 closed |
| F.22 | 13.3 | drm: −1 Fresh HI (with the full exception list), +1 Militia, +1 per Cauldron | ENFORCED — `_resolve_missile`: full ** footnote list (SE-in-hex + artillery-primary suppression added; Testudo term lands with B13); VC `fire_drm_checks` |
| F.23 | 13.3/9.5 | −1 firing from Breach; −1 ground-through-Breach-at-ground | ENFORCED — `_resolve_missile` per-firer breach terms off `_lof` info, *-pair non-cumulation honoured; VC `fire_drm_checks` |
| F.24 | 13.4 | extreme odds: +1 per Attack Multiple beyond the 7-column | ENFORCED — `_resolve_missile` extreme; VC |
| F.25 | 13.5 | fire results identical to Melee except no retreat on Disrupt | ENFORCED — `_apply_letter` fire path; VC. Note: the printed Missile Table contains no B result (encoded table letters = D/E only), so fire-source B retreats are structurally impossible — recorded to prevent a future false gap |
| F.26 | 13.21 | Artillery rout/panic ladder under fire; Elim marker on final elimination | partial — ladder ENFORCED (`_apply_letter`); **Elim marker stacking OPEN → B9**; Elim-vs-Wreck conflict → **R7** |
| F.27 | 13.21 | Cauldrons are not Artillery for Disrupt results (no ladder, no Elim marker) | ENFORCED — `_apply_letter` checks cls `artillery` only (cauldron cls separate) |
| F.28 | 2.523/10.2 | rocks: Fresh Zealots/Militia/Cauldrons on Elevated vs adjacent lower units | ENFORCED — `_fire_verdict` rock path; VC |
| F.29 | 10.2 | rocks from Bastion/Fortress vs **connected lower Elevated** hexes | OPEN → **N2** (gate refuses any Elevated target) |
| F.30 | 10.2 | +1 drm per attacking Cauldron; may combine with missile/artillery fire | ENFORCED — `cauldrons` count |
| F.31 | 9.11 + Q&A | fire vs Towers: declare pushers/riders/both; other level immune; DD-vs-lone eliminates; Cauldrons/rocks never vs riders | OPEN → **B14** |
| F.32 | 9.12 | fire vs Escalades: Base unit hit last; DD top+bottom rule | OPEN → **B12** (no escalades yet; transcribe 9.12) |
| F.33 | 10.1/10.11 | Breach attacks: Roman segment only; Fresh manning unit; adjacency | ENFORCED — `_breach_verdict`; VC |
| F.34 | **10.11** | Breach attack **only vs the Facing-arrow hex** | ENFORCED — `_breach_verdict` facing test vs `_facing_hex`; VC `se_facing_checks` + E2E negative |
| F.35 | 6.41 | Ram's pushing unit must be same Legion | UNREACHABLE — single-Legion (XII) Roman OOB; no non-XII Roman unit exists (card OOB, `COUNTERS_VERIFIED.md`) |
| F.36 | 10.1/12.5 | vs Gate through Entrance hexside: AF doubled (only entrance-side attackers double) | ENFORCED for the single-attacker case — `_resolve_breach`; VC. Multi-engine selective doubling UNREACHABLE (below) — code note in §5/N5 |
| F.37 | 12.5 | combining Rams/Armored Towers from different hexes | UNREACHABLE — Gallus has exactly one Breach-capable unit (1 Ram, 0 Armored Towers; card OOB + counter census) |
| F.38 | 12.1/12.2 | cumulative damage; breach at ≥ defense; occupants eliminated at that instant; damage markers | ENFORCED — `_resolve_breach` + `breach` state + `hex_t` dynamic terrain; VC |
| F.39 | 12.2/card | Breach Defense values per hex class (incl. printed-errata QQ32 = Fort) | ENFORCED — `BREACH_DEF` = card values; VC; source_defect `qq32-hexside-color` |
| F.40 | 12.3 | multi-wall junction hex breached once (e.g. R51) | OPEN → **N18** — verify `hex_t`/`BREACH_DEF` treat junction hexes as one breach; then enforce or evidence |
| F.41 | decode-prep 6 | a Gate's breach & missile defense = its printed strongpoint ring class | ENFORCED — `_breach_def`/`_target_row` read the hex `ring` (9 gates, gates overlay); gate rows removed from `BREACH_DEF`/`ROW_OF_TERRAIN` so a ringless gate fails loudly; VC `gate_ring_checks` |
| F.42 | 18.21 | night: fire adjacent-only | ENFORCED — `_fire_verdict`; VC |
| F.43 | 5.3 | out of CC: fire at adjacent targets only | ENFORCED — `_fire_verdict` |

### P3/P7 — MOVEMENT PHASE (4.13/4.23)

| row | rule | requirement | status |
|---|---|---|---|
| M.1 | 8.11 | adjacency, no enemy-occupied hex entry, per-class TEC entry costs, MF budget | ENFORCED — `_move_verdict`/`_entry_cost`/`_ground_cost`; VM |
| M.2 | 2.7 | fractional costs retained and cumulative (no truncation) | ENFORCED — float arithmetic throughout; VM |
| M.3 | 8.91 | Gates: ground entry only via the two Entrance hexsides, own-control only; +2 MF inherent Interior Staircase to stop; closed to enemy | ENFORCED — `_entry_cost` + entrance data; VM. A5 data corrections DONE (G40/R49/LL30/MM32 retyped, W36→V36, OO33→OO34, P51 entrances added); A4 DONE: overlay sweep CLEAN — 12 Old City gates off-battlefield (asserted), **V42 encoded as the 10th playable gate** (Second-Wall corner gate, ring fort, entrances U42/W41 per overlay); VC `gate_ring_checks` |
| M.4 | 8.93 | Staircase/Breach level change = 2 MF flat | ENFORCED — `_entry_cost`; VM. A6 data corrections DONE (10 inert non-adjacent pairs deleted, Z33|Z34 added); VC. **19 doubtful staircases still → R4** |
| M.5 | 8.95 | Built-up entry: Jud 2 / Rom 3; stacking 2 | ENFORCED — `_ground_cost`/TEC; VM. A3 DONE: 42-hex correction applied, **Gallus Built-up = 92** per frozen PREP-4 evidence (`ingest/builtup_evidence.json`); `builtup_uncertain` retired (all 8 resolved by the printed art); VD `bound_and_builtup_checks` asserts the exact set |
| M.6 | 8.94/8.95/12.4 | interior roads: ½ MF; Cavalry/Artillery enter/exit Built-up only via road hexsides; road rate lost at half-damage | ENFORCED — **B8 done**: 105 art-derived city road hexsides (`ingest/road_hexsides.json` + `build_road_verdicts.py`: detector sweep of all 1041 new_city-interior sides + full contact-sheet/zoom/close-up adjudication, centerline rule; terrain.json `sides[*].road`, amended4); `_entry_cost` road rate ½ replaces terrain cost, cav/art Built-up entry AND exit locked to road sides, SE/testudo Built-up prohibition NOT lifted by roads; VM `road_checks`. 8.94 outside-roads-destroyed = no side encoded outside the walls (scope by construction). 12.4 half-damage transition: Elevated leg already in the both-elev ½→1 cost; GROUND road rate has no reachable damage path in Gallus (Clearance 18.37 = campaign scope). 6.61 testudo-on-road prohibition lands with **B13**. Termini/dead-ends + Damascus rut-mark approach documented in `open_observations` (module-author worksheet items) |
| M.7 | 8.96 | Breach entry for Art/Testudo/Cav/SE only if adjacent connecting Breach of same wall | OPEN → **N19** (engine allows breach entry per GROUND costs without the connecting-breach test) |
| M.8 | 7.31/7.311 | hard ZOC: stop on entry; exit only into ZOC-free first hex; Judaean freeze in Roman HI ground ZOC (official Q&A, both docs agree) | ENFORCED — `_move_verdict`; VM; register corrected (A1 done, ac848ec) |
| M.9 | 7.32/7.4 | soft ZOC (HQ/Cavalry): +3 MF to leave, paid once per hex left | ENFORCED — `_move_verdict`; VM |
| M.10 | 7.321 | soft ZOC exit is FREE if the first hex entered is ZOC-free | OPEN → **N6** (engine always charges +3) |
| M.11 | 7.2 | no ZOC at night / by Disrupted / Artillery / SE / Testudo / SE-or-Escalade-stacked Romans; no cross-level ZOC | ENFORCED — `_zoc_map` (night: Q&A 18.23 confirmed); VC |
| M.12 | 7.12 | Gate ZOC via connected Elevated + the two Entrance-hexside ground hexes | ENFORCED — `_zoc_map` gate branch; VM. A5 entrance data corrected + regression-tested (`gate_ring_checks`) |
| M.13 | 5.3 | out of CC: no enemy-ZOC entry; no moving adjacent to Elevated enemy; escalade/testudo placement barred | ZOC/adjacency ENFORCED — `_move_verdict`; escalade/testudo gating lands with **B12/B13** |
| M.14 | 5.2/5.11 | CC = 10-hex radius, −2 night, −2 non-Fresh HQ, cumulative; path = HQ-movement-legality tracing | radius/reductions ENFORCED; exact tracing OPEN → **B18** |
| M.15 | 5.4/5.5/5.6 | Leaders by faction; Commanders all; Zealot/Cauldron/Artillery any-HQ exceptions; Judaean auto-CC (Fortress, Elevated path); Garrisons | ENFORCED — `in_cc`/`_elevated_path_to_fortress`; Garrison clause UNREACHABLE (no garrison units in Gallus OOB — card) |
| M.16 | 8.1/15.3/17.21 | Routed/Panicked must move toward Refuge | direction ENFORCED — `_refuge_dist` endpoint test; **full-MF obligation + per-hex whenever-possible routing + the 15.3 ROAD LOCK (p.12: on reaching an unobstructed road to Refuge the unit must stay on it in subsequent MPh; obstructed → may leave but must continue toward Refuge) OPEN → B16** |
| M.17 | 8.1/4.13 | Panicked units move only after ALL other units have finished | OPEN → **B16** |
| M.18 | 17.21 | must stop entering a hex with a Panicked unit; leaving a hex with a Panicked friend doubles cost | ENFORCED — `_move_verdict`; VM |
| M.19 | 16.51 | Disrupted units may not enter enemy ZOC | ENFORCED — `_move_verdict` |
| M.20 | 8.13 | through fully-stacked hex at double cost; no overstack at MPh end; HQ/Cauldron carve-out | double-cost ENFORCED; **HQ/Cauldron "not fully stacked to them" carve-out OPEN → N20** |
| M.21 | 8.2 | a unit's movement is complete once another unit begins to move | OPEN → **N11** |
| M.22 | 8.3 | Siege Engine + crew move as one locked stack at SE rate | ENFORCED — SE moves name their crew, crew arrives with the engine, pushers + engine spent for the MPh (`pushed` flags); VC `se_facing_checks`. (General one-mover-at-a-time finality stays M.21/N11) |
| M.23 | 8.6/2.45 | SE moves/changes facing only with Fresh HI/Velitae pushing unit at start of MPh (same Legion for Legion SEs) | ENFORCED — `crew0` start-of-MPh snapshot (`_mph_bookkeeping`) read by `_move_verdict`/`_change_facing_verdict`/`_se_crewed`; facing state = `u["facing"]` (DIRS index), free pivot via `change_facing` or the move's `facing` param; VC. Same-Legion UNREACHABLE (single-Legion OOB). 8.61/10.11 pivot lock after a level-crossing lands with **B14** (no crossing action exists yet) |
| M.24 | 2.45 | SE white side = no crew, MA 0 | ENFORCED — `game.json` SE `ma` now [n, 0]; `_ma` flips on the crew condition, not Fresh/Disrupted; VC `se_facing_checks` (N21 closed) |
| M.25 | 8.61 | Tower as portable staircase; 2 MF off the ramp; riders/pushers lose 2 MF per SE MF (damage-marker transit cost); tower locks after level-crossing | OPEN → **B14** |
| M.26 | 8.7 | Escalade placement (4 MF, adjacency, capacity, Base unit rules, per-phase usage cap) | OPEN → **B12** |
| M.27 | 8.8/6.6/6.61 | Testudo form/disband (6 MF), MA 4, join/leave costs, entry prohibitions | OPEN → **B13** (formation now; one-per-Legion limit blocked on **R2**) |
| M.28 | 6.1/6.2/6.3/6.4 | stacking interactions: Inf/Cav never mix; Artillery exclusions (Fortress 2-artillery-one-Cauldron); SE hex capacity | ENFORCED — `_stack_check`; VM/VD |
| M.29 | 6.2/6.4/8.4 TEC "P" | Cavalry/Ram/Testudo/Artillery may PASS THROUGH controlled Gate hexes (no stop) | OPEN → **N16** (flat refusal denies the legal pass-through) |
| M.30 | 8.4 | Roman Artillery: Fresh may not move; flip-to-move (voluntary flip action); ground-start never Elevated | MA-side ENFORCED (`ma` [0,n]); **voluntary flip action OPEN → B19**; elevated-entry bar ENFORCED — `_entry_cost` |
| M.31 | 2.46/8.4 | Judaean Ballista/Onager/Catapult never move in Gallus | UNREACHABLE — units absent from Gallus OOB (also MA 0 both sides + no Interphase; 2.46, counter census) |
| M.32 | 8.5 | Cauldrons: move Fresh or Disrupted, Elevated-to-Elevated only, artillery-exclusion carve-outs | ENFORCED — `_entry_cost` cauldron branch; VM |
| M.33 | 8.14 | offboard exit: Romans as-if-Clear (return next AP = never in Gallus); Judaeans never return | OPEN → **N12** (engine forbids leaving the map at board edges) |
| M.34 | card SR2 | Giora reinforcement: dice count from turn 4, gate by odd/even die, blocked→other gate, retry each turn | ENFORCED — `_roll_reinforcements` + entry queue; VC. Dice-count ambiguity registered → **R8** |
| M.35 | card | south-gate Refuge exit removes routed/panicked units from play (Bruce-approved bound) | ENFORCED — `escaped`/refuge machinery. A4 DONE: `southern_bound` diagonals anchored on the card's arc ends (cols A–O ≤ printed 50 at O50; QQ–XX ≤ 32 at the QQ31/QQ32 junction) + Elevated fabric playable only where it borders battlefield ground; playable 1925→1341, all 219 Old City art hexes + typed south-junction strongpoints (P51/O53/Q50… cluster, 12 hexes) off-battlefield; VD `bound_and_builtup_checks` |
| M.36 | 6.5/6.4 | Judaeans never enter Escalade hexes; enter SE hexes only from Ground | OPEN → **B12/B14** (with those states) |

### P4/P8 — MELEE PHASE (4.14/4.24)

| row | rule | requirement | status |
|---|---|---|---|
| X.1 | 11.1/4.14 | only Fresh Combat units attack; Disrupted defend only; Artillery/SE never attack (Cauldron connected-Elevated exception) | ENFORCED — `_melee_verdict`; VC. Cauldron-attack exception OPEN → **N22** (currently refused entirely) |
| X.2 | 11.1 | eligibility = could-enter-if-vacated | ENFORCED — `_melee_approach` via `_entry_cost`; VC |
| X.3 | 11.1 | Heavy Infantry stacked with Foederatti/Syrian Archers: whole stack may not Melee or fire | OPEN → **N9** (class-1: gate allows it) |
| X.4 | 11.11/11.12/11.13 | Fortress/Bastion ground melee only via shared Staircase hexside; halving through stairs/breach | ENFORCED — `_melee_approach` + entry legality; VC. A6 staircase corrections DONE; **19 doubtful hexsides still → R4** |
| X.5 | 11.14 | Gate melee: entrance-hexside attacks at HALF strength; Sortie opening; defender's bonus counterattack at end of phase | OPEN → **N7** (no halving through entrance; no sortie/counterattack mechanics) |
| X.6 | 11.15 | attack all units in one hex; one hex per attack | ENFORCED — `_melee_verdict`/`_resolve_melee` |
| X.7 | 11.17 | Crest hexside: attacker halved upslope vs Ground-level non-Slope defender | ENFORCED — `_melee_approach` ×0.5 when the shared side is in `terrain.json` crests and the defender is non-Slope (crest sides are slope\|clear, so the defender's clear hex is the higher ground by construction). Crest set = **182 hexsides read off the printed art** (`ingest/extract_crest_hexsides.py` → `ingest/crest_hexsides.json`: 11.17's own dark-brown criterion as per-hexside paired luminance, dark_frac ≥ 0.5 over 997 slope\|clear candidates, bimodal; full ambiguous band adjudicated on contact sheets; printed examples RR8-SS8 and the 9.52 crest RR48 reproduced by calibration assert). VC `lof_crest_checks` both directions |
| X.8 | 11.18 | −1 Elevated-defense drm forfeit when attacked from connected Elevated/Ramp | OPEN → **N8** (the −1 itself is missing too) |
| X.9 | 11.19 | Built-up defender −1 drm; Edifice doubled defense | −1 ENFORCED — `_resolve_melee` (now over all 92 Built-up hexes, A3); Edifice doubled defense UNREACHABLE — every Edifice is Old City (decode-prep 4 measurement) and the A4 bound is enforced + validated (VD asserts no Edifice hex playable) |
| X.10 | 11.7 | Elevated defense ×2 / Fortress ×3; −1 drm unless attack from connected Elevated/Breach/Ramp/Staircase | multipliers ENFORCED — `_resolve_melee`; VC. **The −1 drm is not applied at all → N8** |
| X.11 | 11.2/11.21/11.22 | Tower melee: riders ×2 through ramp hexside; ramp-hexside-only attacks vs Towers; pusher/rider defense rules; empty-Tower auto-wreck | OPEN → **B14** (+ B10 for the wreck) |
| X.12 | 11.3 | Rams: co-located Romans may not melee (counterattack exception); Judaeans may melee adjacent Ram hexes | OPEN → **B14 cluster** (no above/below state) |
| X.13 | 11.4 | wrecking: unescorted SE entered/attacked → eliminated, hex gets WRECK (stacking + LOF persist) | OPEN → **B10** |
| X.14 | 11.5 | Testudo: may not attack; defends normally; Judaeans may melee adjacent Testudos | OPEN → **B13** |
| X.15 | 11.6/11.61/11.62 | Escalade melee: half strength, Base may not attack, top-first losses, end-of-phase move onto vacant Elevated | OPEN → **B12** |
| X.16 | 11.8/11.81 | totals, odds ratio rounded in defender's favor, one attack per hex per phase (exceptions listed) | ENFORCED — `_resolve_melee`; VC (worked examples 11.81/11.82/11.83) |
| X.17 | 11.82 | defender chooses losses; excess losses forfeit; excess-E advance bonus | choice ENFORCED — pending machinery; VC. Excess-E bonus → **B15** |
| X.18 | 11.83 | extreme odds clamp + drm | ENFORCED — `_resolve_melee`; VC |
| X.19 | 11.841 | cohort integrity ±1 (complete Fresh cohort, one hex, max one per attack) | ENFORCED — `_cohort_drm`; VC |
| X.20 | 11.842 | −1 per extra attacking Faction/Legion; +2 per extra defending; Zealot/Garrison/Cauldron exempt | ENFORCED — `_resolve_melee` (Roman multi-Legion side UNREACHABLE — single Legion) |
| X.21 | 11.85 | flank attack ×2: six hexes enemy/impassable/enemy-ZOC; fully-stacked friendly ≠ impassable; Tower/Escalade escape denial for Judaeans | core ENFORCED — `_resolve_melee`; VC. Judaean escape-denial nuance lands with **B12/B14** |
| X.22 | 11.86 | advance after combat into vacated hex + one extra hex per excess E; no MF cost; entry restrictions apply | OPEN → **B15** (no advance action exists in the gate at all) |
| X.23 | 11.87 | continuous combat on die ≥6 (before or after drm), same units, recalculated odds, lost on interim attack | ENFORCED — `cc_hex`; VC. Same-units constraint audit → **B11** |
| X.24 | 11.88 | cavalry ×2 into and from Clear | ENFORCED — `_melee_approach`; VC |
| X.25 | 11.9 | Multiple Attacks A/B/C ladder; ZOC-must-attack after advance; marker removal rules; Q&A retreat-adjacent item | OPEN → **B11** |
| X.26 | 14.2 | B result: retreat 1-or-2 (unit's option), one at a time; substitute-D option; overstack→Disrupt+continue | ENFORCED — retreat engine (`_retreat_path_verdict`: free 1-2 window, forced continuation while fully stacked per 15.3, sequential one-at-a-time overlay; `substitute_d` in resolve_loss); VC `retreat_engine_checks`. N23 closed |
| X.27 | 14.21 | Judaeans in Roman HI ground ZOC: max 1-hex retreat; forced overstack = ELIMINATED | ENFORCED — `_retreat_capped` (attacker-aware: cap applies only when attacked BY that HI, via pending `attackers`), forced-overstack elimination through `eliminate`; VC `retreat_engine_checks` |
| X.28 | 14.3/14.31/13.5 | melee Disrupt retreats immediately (Fortress/Testudo/SE hexes exempt); fire Disrupt stays | ENFORCED — `_apply_loss`; VC (Testudo/SE exemptions land with B13/B14) |
| X.29 | 14.32 | Armored-Tower Catapults and Disrupted Judaean Artillery never retreat | UNREACHABLE — no Armored Towers, no Judaean Ballista/Onager/Catapult in Gallus OOB (counter census) |
| X.30 | 14.33 | DD: two units, lone defender eliminated, no voluntary single-unit absorption, ineligible-target rules | core ENFORCED — `_auto_resolve_pending`/loss pending; VC. Ineligible-target rules (9.11/9.12 towers/escalades) → **B14/B12** |
| X.31 | 14.4 | E eliminates defender's choice, Fresh or Disrupted | ENFORCED — `_apply_letter`; VC |
| X.32 | 14.5 | eliminated Artillery/SE leave Wrecks: stacking + similar-unit movement block (+LOF per 11.4) | OPEN → **B10** (+ **R7** for the 13.21 Elim conflict) |
| X.33 | 15.1 | retreat = constrained search: MF budget ≤ Disrupted MA, avoid-Rout/Panic/elim preference, per-hex toward Refuge whenever possible, three absolute prohibitions, elimination on failure | ENFORCED — `_retreat_can_finish` memoized feasibility search backs every per-step check (MF budget, mandatory safe-route, per-hex Refuge direction, prohibitions); VC `retreat_engine_checks` (incl. the printed 15.3 EXAMPLE's fully-stacked arithmetic). N10 closed |
| X.34 | 7.5/15.1 | cannot-retreat ⇒ eliminated (never deadlock) | ENFORCED — `eliminate` claims verified by exhaustive search (`_retreat_survivable`); refused while any survivable route exists; VC `retreat_engine_checks` (ringed-unit case). B17 closed |
| X.35 | 15.2 | retreat stacking exemptions; no retreat through Cavalry/full SE; Testudo join-only | Infantry↔Cavalry interlock + no-stacking-limits-during-retreat ENFORCED — `_retreat_step`/`_retreat_full`; VC. SE-with-two-pushers + Testudo-join gates land with **B13/B14** |
| X.36 | 15.3 | +1 disruption level per overstacked hex entered in retreat | ENFORCED — `_apply_retreat`; VC |
| X.37 | Q&A 11.81 | a unit that just retreated into a hex MAY join its melee defense | OPEN → **N24** (verify — likely already true via occupant-based defense; prove with a validator case) |
| X.38 | Q&A 14.3 | on DE the defender may eliminate the Disrupted unit and disrupt the Fresh one | OPEN → **N24** (verify allocation permits it) |
| X.39 | 18.3 + card SR3 | control = last occupant; Roman win at ≥10 Built-up at end of any Judaean Melee Phase; Judaean win by prevention through turn 10 | ENFORCED — control map + `_advance_phase` victory check; VC. A3 DONE: the objective pool is now the full printed 92 (was 50 — the Roman was being denied 42 objectives); VD asserts pool == 92, all playable |
| X.40 | 18.25 | Judaeans +1 melee drm attacking at night | ENFORCED — `_resolve_melee` |

---

## §2 STATE LEDGER

Persistent state the gate keeps (or must keep): which rules WRITE it, which READ it. This is where
movement↔combat interplay lives; a phase-only view never tests that combat rewrote the map movement
runs on.

| state | written by | read by | status |
|---|---|---|---|
| unit hex + facing-of-record | deploy, move, retreat, advance (B15), losses, breach kill, escape | everything | hex ENFORCED; SE facing ENFORCED — `u["facing"]` set at deploy, carried by moves, pivoted via `change_facing` (B1 closed) |
| unit condition ladder (Fresh/Disrupted/Routed/Panicked) | losses [14.x/13.21], rally [17.x], retreat overstack [15.3] | fire eligibility [2.52], melee eligibility [11.1], MA [2.54], ZOC [7.2], rally, SE crew checks | ENFORCED — `state` field; VC |
| breach damage per hex | breach attacks [12.1] | dynamic terrain `hex_t` [12.2], movement costs [12.4 road, half-damage], LOF, missile rows, ZOC connectivity | ENFORCED — `breach` dict; VC. 12.4 movement transition: Elevated ½→1 at half-damage in `_entry_cost` (`_half_damaged`); ground road rate has no reachable damage path in Gallus (B8 closed; Clearance 18.37 campaign scope) |
| hex control (last occupant) | deploy, move (every hex entered), advance (B15) | gate entry [8.91], reinforcement gates, victory [18.3], auto-CC [5.6] | ENFORCED — `control`; VC |
| fired / fired-hexes (per Fire Phase) | fire, breach resolution | fire verdicts [9.1/9.6/13.1] | ENFORCED; reset in `_advance_phase` |
| meleed + continuous-combat hex (per Melee Phase) | melee resolution | melee verdicts [11.1/11.87] | ENFORCED; reset per phase |
| **A/B/C Multiple Attack markers** | advance after melee [11.9] | melee eligibility, marker-removal rules | **OPEN → B11** (state absent) |
| **Escalade markers + Fully-Occupied face + per-phase usage count** | MPh placement [8.7], Disrupt/elim of Base [8.7] | movement [8.7], fire [9.12], melee [11.6], ZOC [7.13/7.2], flank escape [11.85] | **OPEN → B12** |
| **Testudo formations (members, marker, Broken state)** | form/disband [6.6/8.8], melee results [16.4] | movement [6.61/8.8], fire [9.4], melee [11.5], ZOC [7.2], missile row [13.4] | **OPEN → B13** |
| **riders/pushers split in SE hexes (above/below)** | boarding moves [8.61] | fire [9.4/9.11], melee [11.2x], SE movement [8.6], stacking [6.4] | **OPEN → B14** |
| **WRECK markers** | SE elimination [11.4/14.5] | stacking, LOF, similar-unit movement block | **OPEN → B10** |
| **Elim (Artillery) markers** | artillery final elimination [13.21] | stacking to end of AP | **OPEN → B9** (+ R7) |
| **Tower transit-cost damage markers (per MPh)** | SE movement [8.61] | boarding cost that MPh | **OPEN → B14** |
| **current-mover lock (8.2)** | first move segment of a new unit | move verdicts | **OPEN → N11** |
| pending (loss/retreat choice) | combat resolution | propose() router | ENFORCED |
| reinforcement pool + entry queue | `_roll_reinforcements` | move-from-offboard | ENFORCED; VC |
| escaped (refuge exits) | refuge-exit moves | removal from play | ENFORCED (card/Bruce bound) |
| turn/phase/segment, night flag | `_advance_phase` | everything phase-gated | ENFORCED; VC |
| **per-AP artillery start location** | deployment (Gallus = the whole AP) | 8.4 elevated/ground artillery constraints | trivially ENFORCED in Gallus (deployment = AP start; Roman artillery cannot reach Elevated) |

## §3 OBLIGATION FLAGS

| class | rows | status |
|---|---|---|
| **automatic** (engine does it, no player input) | rally attempts + ladders (R.1–R.7), reinforcement rolls (M.34), victory check (X.39), segment transitions (F.1), night effects, breach state (F.38) | ENFORCED |
| **obligatory-decisional** (player MUST act; gate must refuse everything else) | loss allocation (X.17/F.21→B4), retreat routing (X.33→N10), mandatory targets (F.17/F.18→N3), Routed/Panicked-toward-Refuge (M.16→B16), B-result 1-or-2 + substitute-D (X.26→N23), Roman artillery rally opt-in (R.3) | mixed — see rows |
| **ordered/quantified** | non-phasing-fires-first (F.1 ✓), breach-before-missile (F.2→N1), panicked-move-last (M.17→B16), full-MF rout moves (M.16→B16), HQ-first alpha rally order (R.2 ✓), one-mover-at-a-time (M.21→N11) | mixed — see rows |

---

## §4 UNREACHABLE REGISTER (Gallus)

Every claim carries its evidence kind per SOJ_HANDOFF §0. Component-absence is **units only, never
markers**.

| rule(s) | evidence |
|---|---|
| 19.2 Mining + all Interphase mechanics | scenario-card exclusion: "The Roman may not engage in Mining (19.2)" |
| 18.61 Reserves, 18.4 Garrison forces (incl. R.9, garrison auto-CC clause) | scenario-card exclusion: "Reserves (18.61) and Garrison forces (18.4) are not used" |
| 18.81 Ramps (and Ramp LOF obstacle class) | phase-gated behind the Interphase, which never runs (built "prior to only one Assault Period") |
| Armored Towers (all rules: 6.43, 9.3 carve-out, 11.21 doubled defense, 14.32 catapult) | units absent from card OOB (counter census, decode-prep 5 — units-only evidence) |
| Judaean Ballista/Onager/Catapult rules (movement, placement, 14.32) | units absent from card OOB; doubly: MA 0 both sides + no Interphase [2.46/8.4] |
| 11.19 Edifice doubled defense, 10.3 Temple fire, 11.16 Temple Quarter drm, 8.92 Courts | map area outside the scenario's stated bounds — the A4 bound is ENFORCED + validated (VD `bound_and_builtup_checks`); every Edifice on the map is Old City (decode-prep 4 measurement) |
| Bridge hexes (Q&A 12/19.51; bridge rows in tables) | only Bridge is GG46–II44 (TEC) — outside the bounded battlefield |
| 6.41/6.42/8.6 same-Legion crew constraints; 11.842 Roman multi-Legion attack penalty | single-Legion (XII) Roman OOB — no non-XII Roman unit exists |
| 12.5 combining multiple Rams/Armored Towers | exactly one Breach-capable unit in the OOB (1 Ram, 0 Armored Towers) |
| campaign-scope Q&A items (17./18.611, 17.3&18.4, 18.611, 18.7, 19.2, 19.21) | reserves/garrisons/campaign scope (card exclusions above) |

## §5 NEW GAPS FOUND BY THIS MATRIX (N-list)

Found 2026-08-09 by auditing `engine/soj.py` against the verified rulebook/card — none were on the
handoff's B-list. Classes: 1 = silent incorrectness, 2 = loud incompleteness.

| # | rule | what's wrong | class |
|---|---|---|---|
| N1 | 4.12/4.22 | ~~breach-before-missile order~~ **CLOSED as a false gap** — verified against the printed 4.12/4.22: no such ordering exists (see F.2) | ✓ |
| N2 | 10.2 | rocks from Bastion/Fortress vs connected lower Elevated hexes refused | 2 |
| N3 | 9.7 | ~~ZOC-exerter preference~~ **CLOSED** — see F.18 | ✓ |
| N4 | 9.9 | ~~indirect fire~~ **CLOSED** — see F.13 | ✓ |
| N5 | 12.5 | `_resolve_breach` doubles the WHOLE combined BF if any attacker is entrance-side; rule doubles only entrance-side attackers. Unreachable in Gallus (one Breach unit) — **fix before any scenario with 2+ Breach engines**; noted so it cannot ship silently | (1, campaign) |
| N6 | 7.321 | soft-ZOC exit: +3 MF charged even when first hex entered is ZOC-free | 1 |
| N7 | 11.14 | gate entrance-hexside melee not halved; Sortie opening + defender's end-of-phase bonus counterattack missing | 1+2 |
| N8 | 11.7/11.18 | the −1 Elevated-defense drm (and its 11.18 forfeit) never applied in `_resolve_melee` | 1 |
| N9 | 11.1 | mixed Heavy-Infantry + Foederatti/Syrian-Archer stacks are combat-inert — gate allows them to melee and fire | 1 |
| N10 | 15.1/14.21 | ~~retreat engine~~ **CLOSED** — full constrained-search rewrite (see X.27/X.33/X.34); VC `retreat_engine_checks` | ✓ |
| N11 | 8.2 | unit movement finality (done once another unit moves) untracked | 1 |
| N12 | 8.14 | offboard exit denied (Romans as-if-Clear; Judaeans never return) | 2 |
| N13 | 3.4 | setup options denied: Roman Artillery Fresh-or-Disrupted choice; Infantry setup in Testudo | 2 |
| N14 | — | *merged into B14* | — |
| N15 | 2.7 | *verified enforced* (float arithmetic; no truncation found) — kept as a validator case to write | — |
| N16 | 6.2/6.4/8.4 + TEC "P" | Cavalry/Ram/Testudo/Artillery pass-through of controlled Gates refused flat | 2 |
| N17 | 3.3 | off-board Legion setup: verify card scope, then enforce or evidence | ? |
| N18 | 12.3 | multi-wall junction hexes (R51-class) breach-once semantics unverified | ? |
| N19 | 8.96 | Breach entry for Art/Cav/SE/Testudo without the connecting-breach adjacency test | 1 |
| N20 | 8.13 | fully-stacked carve-out (hex not "full" to an entering HQ/Cauldron) not implemented | 1 |
| N21 | 2.45 | ~~SE `ma` encoded [n,n]; printed back side is MA 0 (no-crew state)~~ **CLOSED** — `ma` [n, 0], `_ma` flips on the crew condition (see M.24) | ✓ |
| N22 | 11.1 | Cauldron melee attack vs connected Elevated hexes refused (the one legal artillery-class attack) | 2 |
| N23 | 14.2 | ~~substitute-D-for-B~~ **CLOSED** — `substitute_d` in resolve_loss verdict+apply; VC `retreat_engine_checks` | ✓ |
| N24 | Q&A 11.81/14.3 | two Q&A permissions to verify with validator cases (retreat-into-hex defends; DE split choice) | ? |

---

## §6 PLAYABILITY VERDICT

**NOT PLAYABLE.** Open rows: **B8–B16, B18, B19 (engine; B1–B7/B17 closed — B6/B7 this commit:
F.9/F.10/F.11/X.7 flipped on `lof_crest_checks` + the 182-side art-derived crest set), N2, N5–N9,
N11–N20, N22, N24 (N1 false gap; N3/N4/N10/N21/N23 closed), R1/R2/R4/R7/R8 (blocked on Rob —
cells stay open until his answers land).** The A-list is CLOSED: A1/A2/A8 (ac848ec),
A5/A6 (cd12f76), A3/A4 (2e227ce), A7 by disposition (edifice/bridge/temple classes = campaign
scope in the unreachable register; road/crest land with B7/B8), **A9 done this commit** —
`rules_scope.umpired` retired (all ten entries were B-list build work, now the `build_open`
register mirroring this matrix), `enforced_tier2` cut to true claims only (advance-after-combat,
full-LOF, wall-bonus and mandatory-target overclaims removed), `SoJGame.rules_scope()` composes
the matrix-regime shape with a NOT-PLAYABLE banner (gate.py's tiered base untouched for the
legacy games until their conversion).
The scenario ships when this section reads "PLAYABLE: every row ENFORCED or UNREACHABLE" and
`run_all` + all four validators prove it.

*Maintained by hand during the build; every closed row must name its validator in the same commit.*
