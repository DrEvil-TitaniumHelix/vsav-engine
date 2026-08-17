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
