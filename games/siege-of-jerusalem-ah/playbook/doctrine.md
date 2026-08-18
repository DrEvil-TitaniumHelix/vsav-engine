# Siege of Jerusalem (AH, 4th ed.) — Gallus scenario doctrine (knowledge corpus, spec #22)

Every claim below carries its rulebook citation (sections per
`literature/siege-of-jerusalem/RULEBOOK_VERIFIED.md`, transcribed from the
printed rules and the two official Q&A documents) or a measured result from
seeded, verified games (`engine/verify_game.py` replays; seeds noted).
Language knowledge first; the auto-distilled champion genome is appended by
`make_playbook.py`.

## What the scenario pays (the whole game in one sentence)

- The Romans win the moment they **control ten Built-up hexes at the end of
  any Judaean Melee Phase** (scenario special rule 3; `scenario_gallus.json`
  `vp.roman_win`); hex control = last occupant [18.3]. The Judaeans win by
  denying that through the end of turn 10 (or by Roman concession).
- There is no attrition score. Judaean losses matter only as far as they
  open the walls; Roman losses matter only as far as they run the assault
  out of infantry. The engine's graded margin from the Roman seat is
  therefore `built-up controlled − 10`, +50 for the win, ±0.01 per unit as
  a tiebreak (`engine/families.py::_soj_margin`) — a 9-of-10 finish scores
  −0.6, a win +49.85; the loss tiebreak never flips the sign.
- Ten turns is short. Every Roman turn spent staging is a turn not
  converting a breach into interior control; every Judaean turn spent
  counter-attacking outside the walls is a turn the wall stands unmanned.

## How the walls fall (the mechanics that decide the game)

- A wall hex is breached when cumulative Breach damage ≥ its Breach
  Defense; **everything in the hex at that instant is eliminated** [12.1/
  12.2]. Defense values (printed beneath the Breach Table, `engine/soj.py`
  `BREACH_DEF`): north wall 6, wall 8, bastion 10, fort 12, fortress 15.
  A plain north-wall hex falls to roughly a third of the damage a fortress
  needs — the ram goes where the number is 6, never where it is 15.
- Three ways over: **breach** (ram + escort, then assault through the gap
  [12.x/8.96]); **escalade** (ladders placed by Fresh heavy infantry or
  velitae, two climbers per phase, only Fresh units climb [6.5/8.7/16.3]);
  **towers** (crewed, pushed to a post, riders attack ×2 through the ramp
  hexside, Elevated targets only [11.2/11.21]). All three are Roman heavy-
  infantry sinks: a ram needs two pushers, a tower needs two, an escalade
  base is a Fresh unit locked in place.
- **Judaeans in Roman heavy-infantry ground ZOC may not move at all** in
  their MPh [7.311 exception; official Q&A 1/6/1992] and, when meleed by
  that heavy infantry, **retreat exactly one hex — a forced overstack
  eliminates them** [14.21]. Roman heavy infantry standing on the ground
  against the wall is a freeze, not a threat.
- Retreats are a constrained search, not a direction: MF ≤ Disrupted MA,
  avoid Rout/Panic/elimination first, then toward Refuge every hex, three
  absolute prohibitions, elimination on failure [15.1]; the Judaean Refuge
  is the Temple Quarter [15.4]. Interior control therefore comes from
  pushing units through the breach in numbers, not from single spearheads —
  a single Roman unit inside is retreated or eliminated by weight.
- Rally is mandatory and ordered (HQ first, then board sweep A1→…) [17.1];
  HQs adjacent to Disrupted units are worth −2/−3 on the rally die
  (`_rally_side`). Keeping the HQ one hex behind the assault is a real
  effect, and losing it is a real cost.
- Command control [5]: an out-of-CC unit may not place an escalade [5.3]
  and CC is traced from the HQ each phase boundary (`_cc_snapshot`) — the
  Roman HQ has to advance with the assault sector, and the Judaean leaders
  have to sit where the reserve is.

## Deployment (what the encoded scenario fixes and what is free)

- Judaean minimum force: 26 named strongpoint hexes must be garrisoned
  before anything else deploys (card SR1 / 12.1; `min_force`,
  `validate_deploy.py`); cauldrons go on walls; the rest is the defender's
  choice inside the city (`jud_zone`).
- Romans deploy outside the walls in `rom_zone`, never in the 9 garrison-
  area perimeter hexes (`rom_prohibited`, ruling in `source_defects`
  `gallus-garrison-extent`); no more than one artillery piece per hex
  outside a fortress [6.3].
- The policy AI compiles both deployments as sector templates (WO-03 §6):
  the Roman genome names a sector (a contiguous window of the 63
  assaultable perimeter hexes ordered by angle round the city), the breach
  targets are the first two plain north-wall hexes in it, escalade spots
  and tower posts the other sector walls; the Judaean genome names how much
  of the free force stands on the walls versus a reaction reserve at a
  given depth.

## Measured baseline (shipped policy vs itself; verified, seeded)

- Baseline-vs-baseline games complete in ~10 s and replay byte-exact
  (`validate_ai.py`; per-game hashes stable across processes and
  PYTHONHASHSEED values after champion bite C1).
- Held-out seeds 900–909, both seats the shipped policy (measured
  2026-08-17, commit 4633dfa): **Romans win 2/10** (seed 906: 17 built-up,
  seed 907: 13); the eight Judaean holds end at built-up 0, 7, 4, 0, 3, 3,
  0, 1. Mean Roman margin −4.5 per game on the ±50 scale — a real contest,
  Judaean-favored. Roman losses 7–18 units, Judaean 1–20 (control, not
  attrition, decides). The gap between "the ram opened the north wall"
  and "ten interior hexes held at the end of a Judaean melee phase" is
  what the 14-gene strategy family (`engine/strategy_soj.py`) was built
  to grade.

## Measured champion (trained 2026-08-17, run `runs/2026-08-17_soj_optimizer`)

- Optimizer: 150 generations, 43,396 verified games, population 16,
  hall of fame 8, seat-alternating gauntlet vs the hall (16 games/gen).
  The self-play gauntlet never held an unbeaten streak past 1 of 3, so
  the run did NOT graduate by its own streak rule; the champion is the
  equilibrium of the final elite (`portfolio.json`: one genome, elite_0,
  100%).
- Round-robin vs the shipped baseline (10 seeds × 2 seatings, 20 games):
  mean pair margin **+32.8** for elite_0.
- Graduation bar (`grad_bar.py`, westwall pattern, held-out seeds
  960–984): **20/20** home-away pairs vs the baseline, total margin
  +1350.4 (mean +67.5 per pair); **5/5** pairs vs five fresh random
  genomes. **GRADUATION MET** — the second champion to clear the bar
  (Westwall was the first).
- Corpus (`playbook/corpus/`, seeds 970–972, champion vs baseline both
  seats, every log replayed byte-exact by verify_game): champion **6/6**.
  As Roman it wins on turn 5–6 with 20, 24, 26 built-up hexes (need 10);
  as Judaean it holds the baseline Romans to **0** built-up hexes through
  turn 10 in all three games. Against the same baseline the shipped
  policy managed Rom 2/10 on seeds 900–909 (previous section).
- What the genome does (see the auto-distilled reading appended to the
  playbook copy of this file): concentrates the assault sector
  (sector≈0.32, width≈0.24), stages the second line closer than the
  baseline (stage_dist≈3.6), commits almost nothing to escalade
  (≈0.001) or towers (≈0.015), uses the cavalry flank (≈0.15) and a
  target preference (≈0.59); on the Judaean seat it holds a third of the
  force on the walls (jud_wall_share≈0.34), keeps a full reserve depth
  (1.0), reacts strongly and in size (jud_react≈2.95, size≈12.7) and
  sorties freely (≈0.82).
- Caveat stated plainly: both seats are graded against the SAME
  baseline family; a champion that beats the baseline 6/6 both ways is
  strong evidence, not proof, of good play against a human — the
  Judaean seat's dominance says as much about the baseline Roman's
  weakness (its assault dissipates) as about the champion.

## Doctrine the encoded rules force (before any training)

- **Concentrate the sector.** Breach defense is per hex; two rams on two
  north-wall hexes take longer than one ram plus escalades on the flanks of
  a single window. Wide sectors dilute the two-pusher engines.
- **Freeze, then break.** Roman heavy infantry adjacent to the wall on
  the ground pins the defenders in place [7.311] and shortens their retreat
  to one hex [14.21]; the melee that follows converts stacks, not units.
- **Convert with weight.** The tenth Built-up hex is scored at the end of
  the Judaean melee phase [SR3] — a Roman unit standing alone inside is
  meleed off before the count. Push cohorts, hold the breach hex, spread
  only as far as the stacks can hold.
- **The defender's counter is the reserve, not the wall.** Units on the
  wall die when the hex breaches [12.1]; a reaction reserve at depth 2–3
  behind the threatened sector re-occupies Built-up hexes after each Roman
  melee phase and resets the count. Sorties (counterattack pending, gene
  `sortie`) spend that reserve outside the walls.


## The champion genome, in words (auto-distilled)

Machine-optimized doctrine - every number below was selected by tournament survival, not by argument:

- the Roman assault sector is centred at 0.32 of the way round the assaultable perimeter (0.62 = the shipped north wall choice; the perimeter is the 63 wall hexes with an outside approach, ordered by angle round the city)
- the sector spans 0.24 of the perimeter (breach targets, escalade spots and tower posts are all drawn from it)
- 0.00 of the heavy infantry not crewing engines carries ladders against the sector walls [6.5]; the rest stage for the breach
- 0.02 of the siege towers are crewed and pushed to their posts (0 = park them all) [10.x]
- cavalry rides the high end of the sector's perimeter window: no (no = the low end)
- velitae/archers hold 1 hexes off the sector walls, outside the ram lane [4.x missile ranges]
- assault cohorts stage 4 hexes from the sector before the breach opens
- fire targets weight fresh occupants at 0.59 per unit against plain nearest-hex (0 = closest legal target)
- loss allocations spare leaders: no
- 0.34 of the Judaean units left after the strongpoint garrisons [SR1] man the walls (plain wall hexes first); the rest form the reserve
- the Judaean reserve stands 1 hexes inside the walls
- the reserve commits once breach damage reaches 3 (or a breach opens, or three walls are threatened)
- at most 13 fresh reserve units react per movement phase
- the Judaeans take counterattack windows: yes [14.x]
