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
| P0.8 | 3.4 | Roman Infantry may set up in Testudo | ENFORCED — `testudo` form admitted in `deploy_rom` (no MF, no CC gate at setup); deploy into a formed hex refused [6.61]; VC `testudo_checks` (B13) |
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
| F.15 | 9.31 + Q&A | errant fire on natural 1 vs higher-elevation target: adjacent friendly (ground or elevated) disrupted, defender's choice, never a Base unit w/ climbers | ENFORCED — `_resolve_missile` errant spec → `resolve_errant` pending (defender picks; auto when one candidate; chains after the loss pending); VC `fire_drm_checks`. Base-with-climbers exclusion ENFORCED — `_install_errant` candidate filter (B12); VC `escalade_checks`. B3 closed |
| F.16 | 9.4 + Q&A 11.1 | units beneath a SE may not fire; **riders atop a Tower may**; Fresh Velitae in Testudo may | Testudo half ENFORCED STRUCTURALLY (B13): the only missile-capable class that can ever occupy a Testudo hex is the Velitae (6.1's join whitelist bars Foederatti/Syrian Archers, 6.3 bars Artillery; Roman HI carry no missile factor), and the standing Fresh-to-fire gate [16.2] is exactly 9.4's "Fresh Velitae ... may fire" — no code path denies or over-admits; the 2.6 back face ("No Missile Capability") is the no-Velitae formation, consistent. SE half ENFORCED — **B14**: the 9.4 bar now keys on `up` — beneath-units refused, riders atop a Tower fire freely (Q&A 11.1: "they may initiate missile attacks because they're on a different elevation"), with the F.9 Fortress-group LOF lift already live for the firing hex; VC `tower_checks` |
| F.17 | 9.7 | adjacent enemies are mandatory targets (SE/Artillery never mandatory) | ENFORCED — `_fire_verdict`; VC |
| F.18 | 9.7 | among multiple adjacent targets: may not ignore a ZOC-exerter for a non-exerter | ENFORCED — `_fire_verdict` per-firer exerter test via `_unit_zoc` (the per-unit refactor of `_zoc_map`); VC `fire_drm_checks`. N3 closed |
| F.19 | 9.8 + Q&A | Wall attack bonus ×2 straight down connected Wall/Bridge path; **not over intervening units** | ENFORCED — `_wall_bonus`: path check + intervening-unit denial (Q&A 'A. Yes. No.'); gate inconsistency SETTLED: gates are not Wall hexes for 9.8 — a gate resolves on its ring class on every table (decode-prep 6), so all three gate types are excluded; VC `fire_drm_checks`. B5 closed |
| F.20 | 13.2 | column = Primary Target type row; minimum AF per column; attack-multiple ladder | ENFORCED — `_target_row`/`_resolve_missile`; VC (tables cell-exact) |
| F.21 | 13.2 + Q&A | most severe result **must** go to the Primary Target | ENFORCED — loss pending carries `primary` pids (`_primary_pids`); `_resolve_loss_verdict` forces the severest letter onto a surviving primary unit; VC `fire_drm_checks`. B4 closed |
| F.22 | 13.3 | drm: −1 Fresh HI (with the full exception list), +1 Militia, +1 per Cauldron | ENFORCED — `_resolve_missile`: full ** footnote list, Testudo/Broken-Testudo suppression included (B13); target rows swap to `testudo_artillery_ground` / one lower `breach_broken_testudo` on the marker faces [13.2/16.4]; VC `fire_drm_checks` + `testudo_checks` |
| F.23 | 13.3/9.5 | −1 firing from Breach; −1 ground-through-Breach-at-ground | ENFORCED — `_resolve_missile` per-firer breach terms off `_lof` info, *-pair non-cumulation honoured; VC `fire_drm_checks` |
| F.24 | 13.4 | extreme odds: +1 per Attack Multiple beyond the 7-column | ENFORCED — `_resolve_missile` extreme; VC |
| F.25 | 13.5 | fire results identical to Melee except no retreat on Disrupt | ENFORCED — `_apply_letter` fire path; VC. Note: the printed Missile Table contains no B result (encoded table letters = D/E only), so fire-source B retreats are structurally impossible — recorded to prevent a future false gap |
| F.26 | 13.21 | Artillery rout/panic ladder under fire; Elim marker on final elimination | ENFORCED — ladder (`_apply_letter`) + Elim marker via the single `_eliminate` door; marker holds the Artillery slot to scenario end (`_stack_check`/`_move_verdict`/`_retreat_full`); Elim-vs-Wreck conflict registered + proven outcome-equivalent in Gallus (`elim-vs-wreck-eliminated-artillery`; R7 stays a campaign question); VC `marker_checks` |
| F.27 | 13.21 | Cauldrons are not Artillery for Disrupt results (no ladder, no Elim marker) | ENFORCED — `_apply_letter` checks cls `artillery` only (cauldron cls separate) |
| F.28 | 2.523/10.2 | rocks: Fresh Zealots/Militia/Cauldrons on Elevated vs adjacent lower units | ENFORCED — `_fire_verdict` rock path; VC |
| F.29 | 10.2 | rocks from Bastion/Fortress vs **connected lower Elevated** hexes | OPEN → **N2** (gate refuses any Elevated target) |
| F.30 | 10.2 | +1 drm per attacking Cauldron; may combine with missile/artillery fire | ENFORCED — `cauldrons` count |
| F.31 | 9.11 + Q&A | fire vs Towers: declare pushers/riders/both; other level immune; DD-vs-lone eliminates; Cauldrons/rocks never vs riders | ENFORCED — **B14**: fire action `level` = above/below/both (default both = normal defender allocation); loss pending carries `lvl`, `_loss_elig`/`_resolve_loss_verdict` make the other level immune; DD vs the lone at-level unit collapses to elimination (`_auto_resolve_pending`); Cauldron/rock firers must declare `below`; the SE itself is NEVER loss-eligible on any path ("Fire does not affect Siege Engines" [9.1] — the old `_primary_pids` SE branch could force the severest letter ONTO the fire-immune engine, a silent incorrectness closed in the same pass); Q&A 9.11 both levels = Tower row (`_target_row` keys on the occupant SE, not a declared class); Q&A 9.6 split-level double attack = structurally impossible (`fired_hexes` one-attack-per-hex); VC `tower_checks` |
| F.32 | 9.12 | fire vs Escalades: Base unit hit last; DD top+bottom rule | ENFORCED — **B12 fire slice**: `_loss_elig` makes the Base ineligible while any other defending unit is left in the hex (any unit counts, incl. an HQ — literal "only unit left" reading); target row = the table's own `clear_slope_ramp_escalade` row (no row change); DD vs the lone eligible top unit eliminates it outright, the Base untouched (`_auto_resolve_pending` collapse, 9.11-consistent); E-chains spill onto the Base only once it is the last unit left; sequential-eligibility simulation in `_resolve_loss_verdict` refuses Base picks [9.12]. 9.4's fire-FROM bar unchanged; VC `escalade_checks` (fire scenes: door-open D pending, DD/DE/EE autos, lone-Base DD, manual distinctness) |
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
| M.1 | 8.11 | adjacency, no enemy-occupied hex entry, per-class TEC entry costs, MF budget | ENFORCED — `_move_verdict`/`_entry_cost`/`_ground_cost`; VM. 11.4 carve-out: an unescorted enemy Siege Engine hex IS enterable by Judaeans from Ground level (wrecking it) — VC `marker_checks` |
| M.2 | 2.7 | fractional costs retained and cumulative (no truncation) | ENFORCED — float arithmetic throughout; VM |
| M.3 | 8.91 | Gates: ground entry only via the two Entrance hexsides, own-control only; +2 MF inherent Interior Staircase to stop; closed to enemy | ENFORCED — `_entry_cost` + entrance data; VM. A5 data corrections DONE (G40/R49/LL30/MM32 retyped, W36→V36, OO33→OO34, P51 entrances added); A4 DONE: overlay sweep CLEAN — 12 Old City gates off-battlefield (asserted), **V42 encoded as the 10th playable gate** (Second-Wall corner gate, ring fort, entrances U42/W41 per overlay); VC `gate_ring_checks` |
| M.4 | 8.93 | Staircase/Breach level change = 2 MF flat | ENFORCED — `_entry_cost`; VM. A6 data corrections DONE (10 inert non-adjacent pairs deleted, Z33|Z34 added); VC. **19 doubtful staircases still → R4** |
| M.5 | 8.95 | Built-up entry: Jud 2 / Rom 3; stacking 2 | ENFORCED — `_ground_cost`/TEC; VM. A3 DONE: 42-hex correction applied, **Gallus Built-up = 92** per frozen PREP-4 evidence (`ingest/builtup_evidence.json`); `builtup_uncertain` retired (all 8 resolved by the printed art); VD `bound_and_builtup_checks` asserts the exact set |
| M.6 | 8.94/8.95/12.4 | interior roads: ½ MF; Cavalry/Artillery enter/exit Built-up only via road hexsides; road rate lost at half-damage | ENFORCED — **B8 done**: 105 art-derived city road hexsides (`ingest/road_hexsides.json` + `build_road_verdicts.py`: detector sweep of all 1041 new_city-interior sides + full contact-sheet/zoom/close-up adjudication, centerline rule; terrain.json `sides[*].road`, amended4); `_entry_cost` road rate ½ replaces terrain cost, cav/art Built-up entry AND exit locked to road sides, SE/testudo Built-up prohibition NOT lifted by roads; VM `road_checks`. 8.94 outside-roads-destroyed = no side encoded outside the walls (scope by construction). 12.4 half-damage transition: Elevated leg already in the both-elev ½→1 cost; GROUND road rate has no reachable damage path in Gallus (Clearance 18.37 = campaign scope). 6.61 testudo-on-road prohibition lands with **B13**. Termini/dead-ends documented in `open_observations` (module-author worksheet items); the U36→V36 road terminus = Damascus's corrected in-city entrance hex (gates_overlay), corroborating both datasets |
| M.7 | 8.96 | Breach entry for Art/Testudo/Cav/SE only if adjacent connecting Breach of same wall | ENFORCED — `_breach_link` in `_entry_cost` (Cav/Art/SE) + `_tst_move_verdict` (Testudo); same-wall = adjacency approximation, exact only at multi-wall junctions (N18); VC `testudo_checks` (B13, N19 closed) |
| M.8 | 7.31/7.311 | hard ZOC: stop on entry; exit only into ZOC-free first hex; Judaean freeze in Roman HI ground ZOC (official Q&A, both docs agree) | ENFORCED — `_move_verdict`; VM; register corrected (A1 done, ac848ec) |
| M.9 | 7.32/7.4 | soft ZOC (HQ/Cavalry): +3 MF to leave, paid once per hex left | ENFORCED — `_move_verdict`; VM |
| M.10 | 7.321 | soft ZOC exit is FREE if the first hex entered is ZOC-free | OPEN → **N6** (engine always charges +3) |
| M.11 | 7.2 | no ZOC at night / by Disrupted / Artillery / SE / Testudo / SE-or-Escalade-stacked Romans; no cross-level ZOC | ENFORCED — `_unit_zoc` (night: Q&A 18.23 confirmed). B12 closed a silent gap this row had over-claimed: the SE-or-Escalade-stacked exclusion was NOT implemented (pushers exerted ZOC); now in `_unit_zoc`, and `_heavy_ground_zoc` rerouted through it so the 7.311 freeze honors the same exclusions; VC `escalade_checks`. B13: the Testudo term is now real — intact-formation members excluded in `_unit_zoc`; Broken Testudos with a Fresh unit exert again [16.4]; VC `testudo_checks` |
| M.12 | 7.12 | Gate ZOC via connected Elevated + the two Entrance-hexside ground hexes | ENFORCED — `_zoc_map` gate branch; VM. A5 entrance data corrected + regression-tested (`gate_ring_checks`) |
| M.13 | 5.3 | out of CC: no enemy-ZOC entry; no moving adjacent to Elevated enemy; escalade/testudo placement barred | ENFORCED — `_move_verdict` ZOC/adjacency; `_escalade_verdict` `in_cc` (B12); `_testudo_verdict` `in_cc` on every forming/disbanding combat unit (B13); VC `escalade_checks` + `testudo_checks` |
| M.14 | 5.2/5.11 | CC = 10-hex radius, −2 night, −2 non-Fresh HQ, cumulative; path = HQ-movement-legality tracing | radius/reductions ENFORCED; exact tracing OPEN → **B18** |
| M.15 | 5.4/5.5/5.6 | Leaders by faction; Commanders all; Zealot/Cauldron/Artillery any-HQ exceptions; Judaean auto-CC (Fortress, Elevated path); Garrisons | ENFORCED — `in_cc`/`_elevated_path_to_fortress`; Garrison clause UNREACHABLE (no garrison units in Gallus OOB — card) |
| M.16 | 8.1/15.3/17.21 | Routed/Panicked must move toward Refuge | ENFORCED WHOLE — **B16** (17.21 full text read off p12_c2 and transcribed this bite). Per-hex direction: every hex a Routed/Panicked unit enters must be strictly closer to Refuge (`_refuge_dist` per-step in `_move_verdict`, replacing the endpoint-only test) — ruling documented: when no closer legal step exists the unit "unable to move due to enemy ZOC/terrain must remain in place" (17.21's own escape clause), so lateral/away MPh moves are refused outright rather than allowed as detours (the 15.1 whenever-possible search is retreat machinery; 17.21's MPh text is "must move towards Refuge" + "unable → remain"). Full-MF obligation: `end_phase` in a Movement Phase is refused while any friendly Routed/Panicked unit still has a legal move (`_refuge_laggards` probes every adjacent step through `_move_verdict` itself — the probe IS the law, no parallel approximation, no deadlock possible); a unit with no legal step is satisfied (remains in place). 15.3 ROAD LOCK ENFORCED: `_road_ref_dist` BFS from the refuge-gate doorstep road hexes (gates carry no road sides — 8.91) along road hexsides through hexes free of enemy units and their ZOC; a Routed/Panicked unit on an unobstructed-road hex must step along the road to a strictly-smaller road distance until Refuge; obstruction (no unobstructed road path) frees it to leave the road but the per-hex toward-Refuge rule still governs. Road lock structurally Judaean-only (roads are interior-city; the Roman Refuge is the board edge and 8.94 destroyed all exterior roads — none encoded). A mandatory Refuge move may never end in the 17.21 overstack elimination (M.18) — such a step is refused and counts as "unable". Garrison exception (15.3/18.4) UNREACHABLE — no Garrison units in Gallus OOB. VM `rout_obligation_checks` |
| M.17 | 8.1/4.13/17.21 | Panicked units move only after ALL other units have finished | ENFORCED — **B16**: the checkable content of the ordering rule, both directions: a Panicked unit's move is refused while any friendly ROUTED unit still has an unmet mandatory Refuge move (`_refuge_laggards(states=routed)` — routed movement is not forfeitable, so it can never be "finished" while legal moves remain); and once a Panicked unit has moved (`s["pmoved"]`, hashed, reset each phase), every further non-Panicked move that MPh is refused — moving a Panicked unit IS the declaration that all voluntary movement is finished. `end_phase` still enforces the Panicked units' own Refuge obligation (M.16). Escalade placement/removal and SE facing pivots are not "movement" under 8.1 and stay legal after the declaration (documented reading). VM `rout_obligation_checks` |
| M.18 | 17.21 | must stop entering a hex with a Panicked unit AND end its MPh there; overstacked forced stop eliminates the enterer; leaving a hex with a Panicked friend doubles cost | ENFORCED WHOLE — stop + exit-doubling were VM-enforced; **B16 closed the sentence's two unencoded halves (verbatim text was never transcribed pre-B16): (1) the forced stop ENDS the mover's MPh — `u["fin"]` (hashed via units, popped at phase change) refuses any later move AND any MF-spending Escalade op that phase ("end its MPh" read as stronger than the stop it would otherwise merely repeat); (2) a forced stop that overstacks the hex is LEGAL and ELIMINATES the entering unit (`panic_elim` verdict path through the `_eliminate` door) — the pre-B16 gate refused the entry, which was loud incompleteness against 17.21's own sentence. Any `_stack_check` violation on the forced stop (count, one-per-hex caps, Inf/Cav mix) reads as "overstacked" (conservative literal). Mandatory Refuge movers are barred from the suicide entry (M.16 ruling)**; VM `rout_obligation_checks` |
| M.19 | 16.51 | Disrupted units may not enter enemy ZOC | ENFORCED — `_move_verdict` |
| M.20 | 8.13 | through fully-stacked hex at double cost; no overstack at MPh end; HQ/Cauldron carve-out | double-cost ENFORCED; **HQ/Cauldron "not fully stacked to them" carve-out OPEN → N20** |
| M.21 | 8.2 | a unit's movement is complete once another unit begins to move | OPEN → **N11** |
| M.22 | 8.3 | Siege Engine + crew move as one locked stack at SE rate | ENFORCED — SE moves name their crew, crew arrives with the engine, pushers + engine spent for the MPh (`pushed` flags); VC `se_facing_checks`. (General one-mover-at-a-time finality stays M.21/N11) |
| M.23 | 8.6/2.45 | SE moves/changes facing only with Fresh HI/Velitae pushing unit at start of MPh (same Legion for Legion SEs) | ENFORCED — `crew0` start-of-MPh snapshot (`_mph_bookkeeping`) read by `_move_verdict`/`_change_facing_verdict`/`_se_crewed`; facing state = `u["facing"]` (DIRS index), free pivot via `change_facing` or the move's `facing` param; VC. Same-Legion UNREACHABLE (single-Legion OOB). 8.61/10.11 pivot lock after a level-crossing ENFORCED — **B14**: `u["lk"]` set on every tower↔Elevated crossing, refused in the SE move door and `_change_facing_verdict`, cleared at phase change; riders excluded from `crew0`/`_se_crewed` (a unit atop is not "beneath the engine"); VC `tower_checks` |
| M.24 | 2.45 | SE white side = no crew, MA 0 | ENFORCED — `game.json` SE `ma` now [n, 0]; `_ma` flips on the crew condition, not Fresh/Disrupted; VC `se_facing_checks` (N21 closed) |
| M.25 | 8.61 | Tower as portable staircase; 2 MF off the ramp; riders/pushers lose 2 MF per SE MF (damage-marker transit cost); tower locks after level-crossing | ENFORCED — **B14**: boarding = `move` with `up` (entry cost of the hex's other terrain, no climb surcharge; from Elevated only via the ramp/Facing hexside at 2 MF); move off the ramp = 2 MF, Facing hexside only, descend-and-walk at ground rate; riders carried with the locked stack at +2 MF per SE MF (`u["mv"]` bump), late boarders pay +2×`tmf` (the tower's per-MPh damage-number marker, `u["tmf"]`, reset at phase change); any tower↔Elevated crossing sets `u["lk"]` — no further tower movement or facing change that MPh [8.61/10.11]; capacity: one Infantry + HQ atop [6.42], two HI/Velitae + HQ beneath, entry/transit refused at two pushers [6.4], non-HI/Velitae below refused, Rams carry no passengers [6.41]; SE may not enter ANY occupied hex [6.4] (was silently permitted); riders never count as pushing crew (`crew0`/`_se_crewed` exclude `up`); VC `tower_checks` |
| M.26 | 8.7 | Escalade placement (4 MF, adjacency, capacity, Base unit rules, per-phase usage cap) | ENFORCED — B12 movement slice: `s["esc"]` (hashed) + `u["up"]`/`u["mv"]` unit state; `escalade` action (place/remove, 4 MF each vs the unit's cumulative MPh spend — the fresh-budget-per-action hole is CLOSED: `u["mv"]` accumulates across every action); placement door = Fresh HI/Velitae base, adjacency to Elevated, 6.5 occupant whitelist, one base per hex, 16.3 Disrupted bar, 5.3 out-of-CC bar; base locked in place; climb = `move` with `up` flag (4 MF + entry; flat 2 MF from an Elevated hex), two-above capacity (+HQ exempt), two-distinct-units-per-phase use cap with phase-end face reset; scale to any adjacent Elevated at flat 2 MF (`_entry_cost` opens the wall to `up` units); descend free beyond entry; no lateral escalade-to-escalade; into/through transit while not filled to capacity, no stopping beneath (base slot); auto-collapse sweep (`_esc_sweep` after every apply) on a Disrupted/eliminated/moved base, climbers drop into the hex; retreat arrival from Elevated lands `up` (the card's escalade-as-retreat route). TEC stacking still binds on top of escalade capacity (documented conservative reading). VC `escalade_checks` |
| M.27 | 8.8/6.6/6.61/16.4 | Testudo form/disband (6 MF), MA 4, join/leave costs, entry prohibitions | ENFORCED — `_testudo_verdict` (form: composition 2-3 Fresh HI / 2+Fresh Velitae + one HQ, one Legion, all-occupants-member, no Elevated/escalade hex, 6 MF each, in-CC; disband: unmoved only, 6 MF per Fresh occupant [p.8 tail, transcribed this bite]); `_tst_move_verdict` (MA 4, forming-MPh remainder per the registered 8.8 arithmetic defect, empty-hex/Elevated/Built-up bars, Roman gate pass-through via Entrance hexsides, ZOC stops); join = entering (6 MF flat, `_tst_join_ok`, hold-if-unmoved); leave = half-MA forfeit + never below 2 Fresh HI. Ruling notes: forming barred on Elevated (6.61's own bar — a formation whose movement/melee/missile rules all presuppose ground); HQ pays nothing at form ("stacks within"), joins later at 6 MF; Routed/Panicked never join (15.4/17.21 Refuge obligations; 16.4 names Disrupted only). **One-per-Legion count-limit cell OPEN → R2** (machinery done: formation carries `legion`); VC `testudo_checks` (B13) |
| M.28 | 6.1/6.2/6.3/6.4 | stacking interactions: Inf/Cav never mix; Artillery exclusions (Fortress 2-artillery-one-Cauldron); SE hex capacity | ENFORCED — `_stack_check`; VM/VD |
| M.29 | 6.2/6.4/8.4 TEC "P" | Cavalry/Ram/Testudo/Artillery may PASS THROUGH controlled Gate hexes (no stop) | Testudo half ENFORCED — `_tst_move_verdict` gate transit (Entrance hexsides both sides, Roman occupied-or-controlled, never final, no Panicked occupant); Cav/Ram/Artillery OPEN → **N16** |
| M.30 | 8.4 | Roman Artillery: Fresh may not move; flip-to-move (voluntary flip action); ground-start never Elevated | MA-side ENFORCED (`ma` [0,n]); **voluntary flip action OPEN → B19**; elevated-entry bar ENFORCED — `_entry_cost` |
| M.31 | 2.46/8.4 | Judaean Ballista/Onager/Catapult never move in Gallus | UNREACHABLE — units absent from Gallus OOB (also MA 0 both sides + no Interphase; 2.46, counter census) |
| M.32 | 8.5 | Cauldrons: move Fresh or Disrupted, Elevated-to-Elevated only, artillery-exclusion carve-outs | ENFORCED — `_entry_cost` cauldron branch; VM |
| M.33 | 8.14 | offboard exit: Romans as-if-Clear (return next AP = never in Gallus); Judaeans never return | OPEN → **N12** (engine forbids leaving the map at board edges) |
| M.34 | card SR2 | Giora reinforcement: dice count from turn 4, gate by odd/even die, blocked→other gate, retry each turn | ENFORCED — `_roll_reinforcements` + entry queue; VC. Dice-count ambiguity registered → **R8** |
| M.35 | card | south-gate Refuge exit removes routed/panicked units from play (Bruce-approved bound) | ENFORCED — `escaped`/refuge machinery. A4 DONE: `southern_bound` diagonals anchored on the card's arc ends (cols A–O ≤ printed 50 at O50; QQ–XX ≤ 32 at the QQ31/QQ32 junction) + Elevated fabric playable only where it borders battlefield ground; playable 1925→1341, all 219 Old City art hexes + typed south-junction strongpoints (P51/O53/Q50… cluster, 12 hexes) off-battlefield; VD `bound_and_builtup_checks` |
| M.36 | 6.5/6.4 | Judaeans never enter Escalade hexes; enter SE hexes only from Ground | ENFORCED — SE-hex half with B10 (`_move_verdict`: entry legal only for Judaeans, only from non-Elevated, only into unescorted-SE hexes, which it wrecks [11.4]; VC `marker_checks`); Escalade half with B12: structurally covered by 8.11/15.1 (a Fresh Roman Base always occupies the hex) + explicit 6.5 armor in `_move_verdict`/`_retreat_step` for unreachable states; VC `escalade_checks` |

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
| X.11 | 11.2/11.21/11.22 | Tower melee: riders ×2 through ramp hexside; ramp-hexside-only attacks vs Towers; pusher/rider defense rules; empty-Tower auto-wreck | ENFORCED — **B14**. Riders attack ×2, Facing hexside only, Elevated targets only; pushers/beneath may never attack [11.2]. Vs the Tower hex: Elevated attacks only from the Facing hex [11.21], riders-only defense at NORMAL strength, beneath immune, no advance from Elevated (lvl="above" guards); attack refused when no riders and pushers stand (beneath unaffected [11.21]); ground attacks [11.22] = pushers defend at normal strength, riders add nothing but absorb results FIRST (`_loss_elig` lvl="ground" riders-first ordering), riders-only defense ×0.5 when no pushers; vacant/unescorted Tower meleed through the ramp from Elevated = eliminated WITHOUT dice (`wreck` verdict path → `_eliminate` → Wreck marker [11.4]); above-battle that leaves the hex with no pushers and no riders fells the Tower (`_tower_fall` on every above-chain close: auto, manual-loss, and retreat paths [11.21]); Armored-Tower double defense UNREACHABLE (0 in Gallus OOB); VC `tower_checks` |
| X.12 | 11.3 | Rams: co-located Romans may not melee (counterattack exception); Judaeans may melee adjacent Ram hexes | ENFORCED — **B14**: any Roman in an SE hex who is not a Tower rider is refused as a melee attacker (`_melee_verdict`); Judaean Ground/Gate/Built-up attacks on the Ram hex resolve against the pushers (the SE contributes nothing and is never loss-eligible); the 11.14 Counterattack exception rides N7 (sortie machinery); VC `tower_checks` |
| X.13 | 11.4 | wrecking: unescorted SE entered/attacked → eliminated, hex gets WRECK (stacking + LOF persist) | ENFORCED WHOLE — entry-wreck + all marker effects (B10: `_move_verdict` carve-out + `_apply` wrecking + `_markers_at` in `_stack_check`/`_move_verdict`/`_retreat_full`/`_lof`; VC `marker_checks`); the melee-through-Ramp-hexside trigger closed with **B14** (the diceless `wreck` path in `_resolve_melee`; VC `tower_checks`) |
| X.14 | 11.5 | Testudo: may not attack; defends normally; Judaeans may melee adjacent Testudos | ENFORCED — `_melee_verdict`: intact-formation members refused as attackers; attacks on a Testudo hex admitted only from Ground/Gate/Built-up origin hexes (11.5's own list — Elevated origins refused); defense unmodified (normal terrain multipliers, 13.3's Testudo suppression is missile-only); VC `testudo_checks` (B13) |
| X.15 | 11.6/11.61/11.62 | Escalade melee: half strength, Base may not attack, top-first losses, end-of-phase move onto vacant Elevated | ENFORCED — **B12 melee slice**. Attack origin classified per the printed lists (11.61 "Elevated Hexes" = ELEVATED−GATES; 11.62 "Ground, Gate, and Built-up" = everything else — Gate is named ground-side by 11.62, Slope/Breach are Ground by 2.12); mixed-origin attacks refused, each level = a separate battle, one attack per LEVEL per phase (`melee_hexes` entry `[hex, lvl]` for Escalade targets — the 11.6/11.81 two-battle exception). GROUND attack [11.62]: defense = Base alone at half strength (climbers add nothing), losses fall top-first via `_loss_elig` (Base ineligible until last, same door as F.32). ABOVE attack [11.61]: only climbers targetable AND counting for defense (halved); Base/beneath units excluded from losses entirely (excess forfeits [14.4]), attack refused when no climbers; no advance after combat — explicit `lvl=="above"` guard on every `_open_adv` call site, and structural anyway (the Base can never die from above, so the hex never vacates). Attacks FROM the ladder [11.6]: climbers halved (`mult *= 0.5`), Elevated targets only, Base refused; approach for above-vs-Escalade bypasses `_entry_cost` (the ladder is the connection — 8.7 "attacked by Judaeans from all adjacent Elevated Hexes"). Advance off the ladder legal per 8.7's bracket (11.9 door; `_esc_sweep` clears `up`). End-of-Roman-Melee-Phase move-up onto vacant Elevated = modal `esc_up` pending on `end_phase` (voluntary, per-unit assignments, stacking-checked, Fresh-only [16.3], declinable; `resolve_esc_up` applies and then advances the phase — never auto-resolved, per the GUI modal directive); drm defender-side terms (Fresh-HI/commander/cohort/routed/factions) computed over the level's effective defenders; VC `escalade_checks` melee scenes |
| X.16 | 11.8/11.81 | totals, odds ratio rounded in defender's favor, one attack per hex per phase (exceptions listed) | ENFORCED — `_resolve_melee` + `melee_hexes` hex-once lock (B11 closed a silent gap: the lock had never been implemented; exceptions = CC same-units / marked-attacker per 11.81's own list); VC (worked examples + `multiple_attack_checks`). Escalade half of the attacked-from-both-levels exception ENFORCED — B12 melee slice: per-level `[hex, lvl]` lock entries, one attack per level, never combined (X.15); VC `escalade_checks`. Tower half ENFORCED — **B14**: same `[hex, lvl]` machinery ("above"/"ground"), mixed-origin combined attacks refused [11.2]; VC `tower_checks` |
| X.17 | 11.82 | defender chooses losses; excess losses forfeit; excess-E advance bonus | ENFORCED WHOLE — choice via pending machinery (B4); excess forfeits now run a sequential-eligibility guard in `_apply_loss` (**B15** closed a silent gap: picks past the point where eligibility emptied escaped verdict validation — `_resolve_loss_verdict`'s sim `break`s — and the old apply loop skipped only already-eliminated units, so an excess letter could land on a LIVE ineligible unit, e.g. the immune other Tower level [9.11]; every pick now re-checks `_loss_elig` at application and dead/ineligible picks forfeit). Each forfeited E is counted (`xe`) and earns the 11.86 bonus (X.22); VC `advance_bonus_checks` (tower-level guard scene + manual-picks forfeit scene) |
| X.18 | 11.83 | extreme odds clamp + drm | ENFORCED — `_resolve_melee`; VC |
| X.19 | 11.841 | cohort integrity ±1 (complete Fresh cohort, one hex, max one per attack) | ENFORCED — `_cohort_drm`; VC |
| X.20 | 11.842 | −1 per extra attacking Faction/Legion; +2 per extra defending; Zealot/Garrison/Cauldron exempt | ENFORCED — `_resolve_melee` (Roman multi-Legion side UNREACHABLE — single Legion) |
| X.21 | 11.85 | flank attack ×2: six hexes enemy/impassable/enemy-ZOC; fully-stacked friendly ≠ impassable; Tower/Escalade escape denial for Judaeans | core ENFORCED — `_resolve_melee`; VC. Escalade half of the escape-denial nuance CLOSED structurally (B12 melee slice): an Escalade hex always contains the Roman Base [8.7/15.1], so to a Judaean defender it is enemy-occupied and counts toward the ring (no escape — exactly 11.85's denial), while to a Roman defender on Elevated a friendly Escalade hex fails the ring test and breaks the flank (the escape route 11.85 grants); no code needed, documented here. Tower half CLOSED structurally (**B14**): a live Tower/Ram unit is a Roman occupant, so to a Judaean defender the SE hex is enemy-occupied and counts toward the ring (exactly 11.85's "Judaeans may not use Towers to escape"), while to a Roman defender on Elevated a friendly Tower hex fails the enemy/impassable/enemy-ZOC test and breaks the flank (the escape route 11.85 grants); the ring test in `_resolve_melee` needs no SE-specific code |
| X.22 | 11.86 | advance after combat into vacated hex + one extra hex per excess E; no MF cost; entry restrictions apply | ENFORCED WHOLE — vacated-hex advance per 11.9's own door (B11: ZOC/CC ignored for that hex, terrain re-checked, stacking-capped; VC `multiple_attack_checks`). Excess-E multi-hex bonus ENFORCED (**B15**): `xe` = E results that eliminated no unit, counted where letters are applied (`_auto_resolve_pending` auto path, `_apply_loss` manual path — see X.17's guard) and threaded through retreat pendings into the `advance` pending; `resolve_advance` takes `beyond: {pid: [hex,…]}` — any advancing unit may continue up to `xe` hexes past the vacated hex at NO MF cost. Each step demands normal entry (`_adv_step`: `_entry_cost` terrain, enemy-occupied bar [8.11], marker into/through, 16.51 Disrupted-into-ZOC with the Judaean night lift, 17.21 Panicked stop, Testudo hexes refused [6.61/8.8 — joining is an MPh action], Escalade/SE capacity doors); no step may START in enemy ZOC and lack of CC bars all beyond-movement [11.9 — subsumes the 7.311 hard-ZOC exit 11.86 cites]; destination stacking checked on the FINAL layout (advancers excluded from their origin hexes via `_stack_check` skip); transit through the vacated hex is capped by that hex's stacking limit (11.86's own parenthetical); advanced units carry the mk marker and capture control of every hex entered. Ruling documented: the bonus is an advance DEPTH (up to xe hexes for each advancing unit), the natural reading of "may move one additional hex … for each E result". Note: xe>0 alongside a surviving retreater is structurally dead at ground level (xe>0 ⇒ every eligible defender eliminated), so the retreat-pending thread is belt-and-braces; above-level battles never advance regardless (X.15). VC `advance_bonus_checks` = 6 scene groups (EE/EEE auto xe=1/2, manual-picks forfeit, BEE manual-via-B, refusal battery: non-advancer/over-length/out-of-CC/enemy-occupied/ZOC/no-bonus, 2-hex advance with transit capture, tower eligibility guard) |
| X.23 | 11.87 | continuous combat on die ≥6 (before or after drm), same units, recalculated odds, lost on interim attack | ENFORCED — `cc_hex` now `{hex, pids}`: re-attack demands the exact same unit set (subset/superset refused), any interim attack clears it (B11 closed the same-units audit); VC `multiple_attack_checks` |
| X.24 | 11.88 | cavalry ×2 into and from Clear | ENFORCED — `_melee_approach`; VC |
| X.25 | 11.9 | Multiple Attacks A/B/C ladder; ZOC-must-attack after advance; marker removal rules; Q&A retreat-adjacent item | ENFORCED — B11: `u["mk"]` ladder (advance grants A, A-attack advance → B, B-attack advance → C, then anew A [11.9 "chain begins anew"]); marked participants' markers consumed on their attack (11.9 states this for A; B/C read symmetrically — B's is implied by "grow a C"), a B-attack removes every A globally, a markerless attack removes ALL markers; a marked unit must target its ZOC enemies when any exist (skipped at night [7.2]); marker presence bypasses both once-per-phase locks and admits already-meleed partners ("even if they have already attacked"); markers cleared at Melee Phase end (phase-scoped state — 11.9's attacks exist only inside the phase); Q&A item 15 proven end-to-end (retreat-adjacent enemy attackable by an eligible unit); VC `multiple_attack_checks` |
| X.26 | 14.2 | B result: retreat 1-or-2 (unit's option), one at a time; substitute-D option; overstack→Disrupt+continue | ENFORCED — retreat engine (`_retreat_path_verdict`: free 1-2 window, forced continuation while fully stacked per 15.3, sequential one-at-a-time overlay; `substitute_d` in resolve_loss); VC `retreat_engine_checks`. N23 closed |
| X.27 | 14.21 | Judaeans in Roman HI ground ZOC: max 1-hex retreat; forced overstack = ELIMINATED | ENFORCED — `_retreat_capped` (attacker-aware: cap applies only when attacked BY that HI, via pending `attackers`), forced-overstack elimination through `eliminate`; VC `retreat_engine_checks` |
| X.28 | 14.3/14.31/13.5 | melee Disrupt retreats immediately (Fortress/Testudo/SE hexes exempt — "they may if their owner wishes"); fire Disrupt stays | ENFORCED — `_apply_loss` AND `_auto_resolve_pending` (B11 closed a silent gap: a lone defender auto-resolved to Disrupted never got its retreat). B13 completed 14.31 via `_melee_stay_ok` + `optional` retreat pendings (modal choose-or-decline; forced elimination refused), closing TWO more gaps this row had hidden: the SE-hex exemption was MISSING (escort defenders were FORCED to retreat — silent incorrectness, reachable in Gallus), and the Fortress "may if their owner wishes" option was silently denied (no pending was ever queued); VC `multiple_attack_checks` + `testudo_checks` |
| X.29 | 14.32 | Armored-Tower Catapults and Disrupted Judaean Artillery never retreat | UNREACHABLE — no Armored Towers, no Judaean Ballista/Onager/Catapult in Gallus OOB (counter census) |
| X.30 | 14.33 | DD: two units, lone defender eliminated, no voluntary single-unit absorption, ineligible-target rules | ENFORCED — `_auto_resolve_pending` (lone-eligible collapse) + `_resolve_loss_verdict` sequential simulation. B12 fire slice closed TWO silent gaps this row had over-claimed: (1) the no-voluntary-single-unit-absorption bar was never implemented — the defender could put both Ds of a DD on one unit in ANY hex (now refused [14.33]); (2) picks were validated positionally, not sequentially — an eliminated unit could be picked again. 9.12 escalade ineligibility ENFORCED (`_loss_elig`); 9.11 tower half ENFORCED — **B14**: level-scoped eligibility, DD vs the lone at-level unit eliminates outright; VC `tower_checks`. DD exists only on the missile table (letter census of both tables), so the rewrite is fire-scoped by construction; VC `escalade_checks` |
| X.31 | 14.4 | E eliminates defender's choice, Fresh or Disrupted | ENFORCED — `_apply_letter`; VC |
| X.32 | 14.5 | eliminated Artillery/SE leave Wrecks: stacking + similar-unit movement block (+LOF per 11.4) | ENFORCED — the single `_eliminate` door drops the marker on EVERY elimination path (fire E, 13.21 ladder, melee D-absorb, breach kill [12.2], rally 9+, retreat overstack/no-route, entry-wreck); slot held + into/through block + retreat full-to-them; Elim-vs-Wreck conflict registered, outcome-equivalent in Gallus (R7 campaign); VC `marker_checks` |
| X.33 | 15.1 | retreat = constrained search: MF budget ≤ Disrupted MA, avoid-Rout/Panic/elim preference, per-hex toward Refuge whenever possible, three absolute prohibitions, elimination on failure | ENFORCED — `_retreat_can_finish` memoized feasibility search backs every per-step check (MF budget, mandatory safe-route, per-hex Refuge direction, prohibitions); VC `retreat_engine_checks` (incl. the printed 15.3 EXAMPLE's fully-stacked arithmetic). N10 closed |
| X.34 | 7.5/15.1 | cannot-retreat ⇒ eliminated (never deadlock) | ENFORCED — `eliminate` claims verified by exhaustive search (`_retreat_survivable`); refused while any survivable route exists; VC `retreat_engine_checks` (ringed-unit case). B17 closed |
| X.35 | 15.2 | retreat stacking exemptions; no retreat through Cavalry/full SE; Testudo join-only | Infantry↔Cavalry interlock + no-stacking-limits-during-retreat ENFORCED — `_retreat_step`/`_retreat_full`; VC. Testudo-join gate ENFORCED — `_retreat_step` (join legality via `_tst_join_ok`, 6 MF cost, retreat ends in the formation; "can pay six MF" binds through the disrupt-retreat MF budget, and every joinable class's Fresh MA ≥ 6 covers B retreats); VC `testudo_checks` (B13). SE-with-two-pushers gate ENFORCED — **B14**: `_retreat_step` refuses Infantry into/through a hex holding an SE with two pushing units [15.2]; VC `tower_checks` |
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
| unit hex + facing-of-record | deploy, move, retreat, advance (incl. the 11.86 beyond-paths, B15 closed), losses, breach kill, escape | everything | hex ENFORCED; SE facing ENFORCED — `u["facing"]` set at deploy, carried by moves, pivoted via `change_facing` (B1 closed) |
| unit condition ladder (Fresh/Disrupted/Routed/Panicked) | losses [14.x/13.21], rally [17.x], retreat overstack [15.3] | fire eligibility [2.52], melee eligibility [11.1], MA [2.54], ZOC [7.2], rally, SE crew checks | ENFORCED — `state` field; VC |
| breach damage per hex | breach attacks [12.1] | dynamic terrain `hex_t` [12.2], movement costs [12.4 road, half-damage], LOF, missile rows, ZOC connectivity | ENFORCED — `breach` dict; VC. 12.4 movement transition: Elevated ½→1 at half-damage in `_entry_cost` (`_half_damaged`); ground road rate has no reachable damage path in Gallus (B8 closed; Clearance 18.37 campaign scope) |
| hex control (last occupant) | deploy, move (every hex entered), advance incl. every 11.86 transit hex (B15 closed) | gate entry [8.91], reinforcement gates, victory [18.3], auto-CC [5.6] | ENFORCED — `control`; VC |
| fired / fired-hexes (per Fire Phase) | fire, breach resolution | fire verdicts [9.1/9.6/13.1] | ENFORCED; reset in `_advance_phase` |
| Panicked-move-last declaration + forced-stop MPh lock | move apply (`s["pmoved"]` set by any Panicked move; `u["fin"]` set by a forced stop in a Panicked hex) | move + escalade verdicts [8.1/17.21], `end_phase` laggard gate [15.3/17.21] | ENFORCED — **B16**: `pmoved` in HASH_KEYS (setdefault resume-safe), `fin` hashes via units; both cleared at phase change; VM `rout_obligation_checks` |
| meleed + attacked-hexes + continuous-combat set (per Melee Phase) | melee resolution | melee verdicts [11.1/11.81/11.87] | ENFORCED — `meleed` + `melee_hexes` (both hashed) + `cc_hex` `{hex, pids}`; reset per phase |
| A/B/C Multiple Attack markers | advance after melee [11.9] via the `advance` pending | melee eligibility bypasses, ZOC-must-attack, marker-removal rules [11.9] | ENFORCED — `u["mk"]` (hashes via `units`), cleared at Melee Phase end; VC `multiple_attack_checks` (B11) |
| Escalade markers + Fully-Occupied face + per-phase usage count + above/below split | MPh placement/removal [8.7], auto-collapse sweep [8.7], climbs (`up` moves), melee-phase `esc_up` move-up + advance-off-ladder [11.6/8.7] | movement [8.7] ✓, ZOC [7.13/7.2] ✓, errant [9.31] ✓, fire-from bar [9.4] ✓, fire-at [9.12] ✓ (F.32), melee [11.6x] ✓ (X.15: per-level battles, halvings, top-first/above-only losses, no-advance-from-above, end-of-phase move-up), flank-escape ✓ (X.21, structural) | ENFORCED — `s["esc"]` (hashed: hex/base/used-pids) + `u["up"]` + `u["mv"]` + loss-pending `lvl`; all reads live; VC `escalade_checks` (movement+fire+melee scenes) |
| Testudo formations (marker, `mv`/`hold`, Broken members+armed) | `testudo` form/disband, joins (moves/retreats), `_tst_sweep` after every apply (break on <2 Fresh HI or Panicked occupant [16.4]; dissolve silently when emptied — no components remain for the −6), `_mph_bookkeeping` (arm Broken + 6-MF penalty entering the Roman MPh), `_advance_phase` (armed Broken removed leaving it) | movement [6.61/8.8/8.96] (`_tst_move_verdict`, join/leave in `_move_verdict`), fire rows + 13.3 [13.2/16.4], fire-from [9.4 structural], melee [11.5], ZOC [7.2/16.4], retreats [14.31/15.2], escalade/deploy exclusions [6.5/6.61] | ENFORCED — `s["testudo"]` hashed (HASH_KEYS); membership = occupancy (invariant: entering an intact formation's hex IS joining); VC `testudo_checks` (B13). Timing ruling: 14.31's exemption reads at the instant the loss lands (a D that itself breaks the formation still leaves the stay option); a B that empties the hex dissolves the formation with no Broken marker |
| riders/pushers split in SE hexes (above/below) | boarding moves [8.61] (`up` flag, same field the Escalade uses — hashes via `units`), locked-stack rides, `_esc_sweep` drop on SE elimination | fire [9.4/9.11] ✓ (rider door + level split), melee [11.2x] ✓ (rider ×2, riders-first/riders-only battles), SE movement [8.6] ✓ (riders carried, +2 MF/SE-MF, never crew), stacking [6.4/6.42] ✓ (1 atop + 2 beneath, entry/transit caps) | ENFORCED — **B14**; VC `tower_checks` |
| WRECK markers | SE elimination — any path through `_eliminate` [11.4/14.5] | stacking (`_stack_check`), LOF lift + 9.13 obstruction (`_lof`), similar-unit into/through block (`_move_verdict`), retreat full-to-them (`_retreat_full`) | ENFORCED — `s["markers"]`, hashed (HASH_KEYS); persists to scenario end (14.5 'Assault Phase' = registered dangling reference); VC `marker_checks` |
| Elim (Artillery) markers | non-Cauldron Artillery elimination — any path through `_eliminate` [13.21/14.5] | Artillery stacking slot to end of AP (= scenario end), similar-unit into/through block | ENFORCED — same machinery; Elim-vs-Wreck identity outcome-equivalent in Gallus, R7 open for campaign; VC `marker_checks` |
| Tower transit-cost damage markers (per MPh) | SE movement [8.61] (`u["tmf"]` accumulates the engine's MF, popped at phase change — the printed "damage number marker, removing ... at the end of the MPh") | boarding cost that MPh (+2×tmf), riders' `mv` bump | ENFORCED — **B14**; VC `tower_checks` |
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
| **obligatory-decisional** (player MUST act; gate must refuse everything else) | loss allocation (X.17/F.21→B4), retreat routing (X.33→N10), mandatory targets (F.17/F.18→N3), Routed/Panicked-toward-Refuge (M.16→B16 ✓ — per-step direction + `end_phase` laggard gate), B-result 1-or-2 + substitute-D (X.26→N23), Roman artillery rally opt-in (R.3), advance-or-decline after a vacating melee (X.22/X.25→B11 — modal `advance` pending, never auto-resolved: declining is a real choice) | mixed — see rows |
| **ordered/quantified** | non-phasing-fires-first (F.1 ✓), breach-before-missile (F.2→N1), panicked-move-last (M.17→B16 ✓ — `s["pmoved"]` declaration + routed-first bar), full-MF rout moves (M.16→B16 ✓), HQ-first alpha rally order (R.2 ✓), one-mover-at-a-time (M.21→N11) | mixed — see rows |

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
| N13 | 3.4 | setup options denied: Roman Artillery Fresh-or-Disrupted choice (~~Infantry setup in Testudo~~ closed with B13 — see P0.8) | 2 |
| N14 | — | ~~merged into B14~~ **CLOSED with B14** (riders/pushers state = `u["up"]` on Tower hexes) | ✓ |
| N15 | 2.7 | *verified enforced* (float arithmetic; no truncation found) — kept as a validator case to write | — |
| N16 | 6.2/6.4/8.4 + TEC "P" | Cavalry/Ram/Artillery pass-through of controlled Gates refused flat (the Testudo's own pass-through is ENFORCED in `_tst_move_verdict` — B13) | 2 |
| N17 | 3.3 | off-board Legion setup: verify card scope, then enforce or evidence | ? |
| N18 | 12.3 | multi-wall junction hexes (R51-class) breach-once semantics unverified | ? |
| N19 | 8.96 | ~~Breach entry for Art/Cav/SE/Testudo without the connecting-breach adjacency test~~ **CLOSED with B13** — `_breach_link` (an adjacent hex currently a Breach; same-wall identity approximated by adjacency, exact only at multi-wall junctions → N18's open question) in `_entry_cost` for Cav/Art/SE and in `_tst_move_verdict`; VC `testudo_checks` | ✓ |
| N20 | 8.13 | fully-stacked carve-out (hex not "full" to an entering HQ/Cauldron) not implemented | 1 |
| N21 | 2.45 | ~~SE `ma` encoded [n,n]; printed back side is MA 0 (no-crew state)~~ **CLOSED** — `ma` [n, 0], `_ma` flips on the crew condition (see M.24) | ✓ |
| N22 | 11.1 | Cauldron melee attack vs connected Elevated hexes refused (the one legal artillery-class attack) | 2 |
| N23 | 14.2 | ~~substitute-D-for-B~~ **CLOSED** — `substitute_d` in resolve_loss verdict+apply; VC `retreat_engine_checks` | ✓ |
| N24 | Q&A 11.81/14.3 | two Q&A permissions to verify with validator cases (retreat-into-hex defends; DE split choice) | ? |

---

## §6 PLAYABILITY VERDICT

**NOT PLAYABLE.** Open rows: **B18,
B19 (engine; B1–B17 closed — **B16 movement obligations CLOSED this commit**: 17.21 read off
the page and transcribed (it was never in the verified record); M.16 whole (per-hex
toward-Refuge direction replacing the endpoint test, full-MF obligation via the `end_phase`
`_refuge_laggards` gate whose probes ARE `_move_verdict`, 15.3 road lock on `_road_ref_dist`
BFS — Judaean-only structurally, obstruction frees the road), M.17 whole (`s["pmoved"]`
hashed declaration: panicked moves barred until routed obligations done, all non-Panicked
movement barred after a panicked move), M.18 whole — TWO unencoded 17.21 sentences closed
(forced stop ENDS the mover's MPh — `u["fin"]`; an overstacking forced stop is legal and
ELIMINATES the enterer, was loudly refused); mandatory movers never forced/permitted into the
suicide entry; VM `rout_obligation_checks` (6 scene groups). Before that **B15 excess-E advance bonus CLOSED**: `xe`
(E results that eliminated no unit) counted at both loss-application sites and threaded
loss→retreat→`advance` pending; `resolve_advance` `beyond` paths give any advancing unit up to
`xe` extra hexes at no MF cost through `_adv_step` normal-entry doors, ZOC-start/CC bars
[11.9/7.311], final-layout stacking, mk + control on every hex entered (X.22 ENFORCED WHOLE);
the same pass closed X.17's silent gap — excess loss picks past eligibility exhaustion escaped
verdict validation and could land letters on a live immune unit (other Tower level [9.11]);
`_apply_loss` now re-checks `_loss_elig` per pick and forfeits dead/ineligible picks; VC
`advance_bonus_checks` (6 scene groups). Before that **B14 Tower riding/boarding CLOSED**: `u["up"]`
extended to Tower hexes (riders) with `u["tmf"]` per-MPh transit marker + `u["lk"]`
level-crossing lock; boarding/capacity doors [6.4/6.42/6.41], locked-stack rides at +2 MF per
SE MF with late-boarder surcharge [8.3/8.61], 2-MF ramp move-off/boarding through the Facing
hexside only [8.61/10.11], rider fire door + 9.11 level-split allocation with other-level
immunity and DD-vs-lone collapse + Cauldron/rock below-only + occupant-keyed Tower row
[9.4/9.11/Q&A], 11.2x melee whole (rider ×2 ramp-only attacks, ramp-only Elevated attacks vs
the hex, riders-first ground losses, riders-half with no pushers, diceless vacant-Tower wreck,
`_tower_fall` above-battle destruction, per-level `[hex,lvl]` battles closing X.16's tower
half), 15.2 two-pusher retreat gate, `esc_up` modal extended to riders; FOUR silent gaps
closed in the same pass (SE could enter occupied hexes [6.4]; the two-pusher entry/transit
cap was never enforced [6.4]; `_primary_pids` could force fire losses ONTO the fire-immune
SE [9.1] — SEs now never loss-eligible anywhere; riders would have counted as pushing crew
[8.6]); VC `tower_checks` (10 scene groups). Before that **B13 Testudo CLOSED** except the R2-held
one-per-Legion count cell: `s["testudo"]` hashed state on membership-by-occupancy,
form/disband/join/leave/formation-move (`_testudo_verdict`/`_tst_move_verdict`/`_tst_join_ok`),
Broken Testudo lifecycle (−6 MF, armed removal, ZOC return, lower missile row), 11.5 melee bars,
13.2/13.3 fire rows+suppression, 15.2 retreat-joins, P0.8 setup-in-Testudo, plus riders: 8.96
connecting-Breach for Cav/Art/SE too (N19 closed) and 14.31 `optional` retreat pendings closing
two hidden gaps (SE-hex forced retreat = silent incorrectness; Fortress stay-option denial);
two NEW source defects registered off the page scans (6.61-vs-16.4 Disrupted-Velitae join;
8.8 "one MF remaining" vs MA-8 counters — the p.7→p.8 disband tail was never transcribed and
is now in RULEBOOK_VERIFIED.md); VC `testudo_checks`. Before that **B12 CLOSED WHOLE** with the melee slice:
X.15 ENFORCED end-to-end (per-level separate battles + `[hex, lvl]` hex-once lock closing
X.16's escalade half, 11.62 ground = Base-alone-halved defense with top-first losses, 11.61
above = climbers-only-halved with Base untouchable + no advance, climber attacks halved into
Elevated only, 8.7-bracket advance off the ladder, modal `esc_up` end-of-phase move-up
pending), X.21's escalade escape-denial half closed structurally (Base always occupies), loss
pendings carry `lvl`; melee scenes on `escalade_checks`. The FIRE slice the commit before:
F.32 ENFORCED (`_loss_elig` Base ineligibility, `clear_slope_ramp_escalade` row, DD-vs-lone-top
outright elimination, E-chain spill-to-Base-last, sequential-eligibility loss verdict) and X.30
completed, closing TWO more silent gaps X.30 had over-claimed (the 14.33 voluntary-single-unit-DD
bar missing in ANY hex; positional loss picks). The movement slice before that:
M.26/M.36/M.13-escalade + F.15 base-exclusion + 9.4 fire-from bar; `s["esc"]` +
`u["up"]`/`u["mv"]` state, place/remove/climb/scale/collapse; the M.11 7.2 ZOC exclusion +
fresh-MA-budget silent gaps closed there. B11 before that:
X.16/X.22-vacated-hex/X.23/X.25 + the A/B/C ledger row on `multiple_attack_checks`, `u["mk"]`
ladder, modal `advance` pending, `melee_hexes` hex-once lock, CC same-units audit, 14.3
auto-lone-D retreat fix on X.28; B9/B10 before that on `marker_checks`), N2,
N5–N9, N11–N13, N15–N18, N20, N22, N24 (N1 false gap; N3/N4/N10/N19/N21/N23 closed; N14
closed inside B14), R1/R2/R4/R8 (blocked on
Rob — cells stay open until his answers land; R7 no longer blocks Gallus: Elim-vs-Wreck proven
outcome-equivalent, campaign identity still with Rob).** The A-list is CLOSED: A1/A2/A8 (ac848ec),
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
