# Doctrine — Blue & Gray: Chickamauga (v1, authored)

## Published literature on this title (retrieved 2026-07-11)

Design: Irad B. Hardy, Redmond A. Simonsen, John Young (SPI 1975, Blue &
Gray quad; system adapted from Napoleon at War 1972; TSR reissue 1984,
Decision Games revision 1995). Ranked 15th of 202 in SPI's North American
popularity poll; a perennial convention tournament favorite.

- Jay Nelson, MOVES #23 (Oct 1975), Blue & Gray Profile: "a simple game
  that portrays a rather complex situation... interesting challenges to
  both sides"; his conclusion — play comes down to "exploiting specific
  weaknesses and strengths that will be unique to each game."
- Tom Walczyk, MOVES (Oct 1976): QuadriGame errata covering Blue & Gray.
- Charles Vasey (1977): "simple tactical surround-and-destroy system" —
  encirclement to cut retreat paths is the system's core weapon.
- Jon Freeman, Complete Book of Wargames (1980): rules "ideal" in their
  simplicity; judged the scenario UNBALANCED IN FAVOR OF THE UNION.
- Steve List, MOVES #54 (1981): "easily the best of the B&Gs", B+,
  "outcome usually in doubt to the end."
- Luc Olivier, Simulacrum #20 (2004): "by far the best", historical
  victory conditions create natural balance.

**Calibration consequence:** the published consensus (balanced to
Union-favored) contradicts our policy-vs-policy baseline (Confederate
+90). The baseline therefore reflects weak POLICY Union play, not the
game - the expert bar for Union is WINNING, not losing gracefully.

**Retrieval targets (work orders):** full text of Nelson's MOVES #23
profile and Walczyk's Oct-1976 errata - candidate transcription jobs for
the OCR pipeline; check the errata against our source-defect register.
**Verification note:** Wikipedia describes an "Attack Effectiveness"
rule (Attacker-Retreat results bar further attacks that day) and a
10-turn day; our validated transcription/scenario runs 15 GTs - likely
edition differences (quad standard vs folio vs DG revision), but check
the module's rulebook edition against both claims on next touch.

This is the doctrine book the LLM planner reads before writing each turn's
plan. v1 is authored from the encoded victory schedule and the strategy the
map dictates; as the Staff College loop comes online, entries earned from
counterfactual debriefs will carry evidence tags (game log, turn, proven VP
delta) exactly like the source-defect register carries citations.

## The victory arithmetic rules everything [17.1/17.2/17.3]

- Every enemy combat-strength point eliminated = 1 VP. Attrition is real but
  slow; the map objectives dwarf it.
- **Confederate exit VPs are 10 per CSP** (Union's are 1). A Confederate
  brigade of strength 5 that walks off the east edge is worth 50 VP — but
  ONLY if the Confederate line of communication (the road trace from
  0101/0111 to the east edge) is clear of Union units at game end [17.31].
  Union: killing exits at the source (sitting on that road) can void the
  entire Confederate exit account at once.
- Deep objectives: Union takes 1920 (10 VP) and 2311 (20 VP) in Confederate
  country; Confederate takes 0211 and 0502 (20 VP each) in Union country.
  The three 5-VP hexes (0822, 1108, 1115) start Union-held and flip to the
  last side through them.
- The Union Train is 10 VP to the Confederacy unless it EXITS. It moves on
  roads/trails only [18.23] — its escape route is a plan-level concern from
  turn 1, not an afterthought.
- **Union cutoff rule [17.32]**: any live Union unit that cannot reach an
  exit-connected road within 10 hexes at game end counts as destroyed.
  A Union wing that wins its firefight but is cut off scores as a corpse.

## Operational principles

1. **Play the schedule, not the skirmish.** A 20-VP hex out-values weeks of
   even attrition. Commit strength where the schedule pays; refuse battle
   where it doesn't.
2. **Concentration beats dispersion.** Combat is odds-based on adjacent
   strength; night turns freeze combat. Attack with everything adjacent to
   one defender or don't attack at all — mandatory combat [7.0] punishes
   units that drift into contact alone.
3. **Terrain sets the tempo.** Forest/rough cost 3-6 MP against a 6-MP
   allowance; roads cost 1. Whoever owns the road net moves twice as fast.
   Plans should march columns down roads and fight off them.
4. **The creek is a wall with doors.** Creek hexsides are impassable except
   bridges (free) and fords (+1 MP) [5.25]. Holding a bridge with one unit
   equals holding the creek with five.
5. **Confederate: the LOC is the whole game.** Exits are worth 10x, but only
   with the road trace clear. Screen it, and clear Union units off it before
   the end. Union: a late-game lunge onto that road is worth more than any
   attack.
6. **Union: mind the 10-hex leash.** Every deep Union adventure must end
   within reach of an exit-connected road, or it scores as destroyed.
7. **Reinforcements are tempo.** Entry columns pay road costs [15.0]; feed
   them toward the active objective, not the nearest fight.

## Lessons from Game 1 (Claude-as-Union vs policy, seed 1, 2026-07-11)

Final 116-25 Confederate — margin -91, statistically identical to the
policy-vs-policy baseline (-90). Verified log (759/759) + regret-mined.
What the game proved:

1. **The reinforcement entry system is the dominant Union VP leak vs this
   opponent.** ~35 VP of my losses were reinforcements eaten on or near
   the south-edge entry hexes; the enemy repeatedly re-tasked whole wings
   to farm them. Either plan an extraction corridor with covering force,
   or accept the column stall (blocked head = nothing enters) as
   protection. Evidence: game log, GT2-GT14 eliminations.
2. **Exit-blocking has ZERO marginal value against the policy AI** — it
   only ever exits trains, never combat units. The doctrine kill-shot
   (LOC void + exit denial) targets a capability this opponent doesn't
   use. Against humans it stays live; against the policy, those garrisons
   are better spent contesting occupation hexes. Evidence: 0 Confederate
   exit attempts in 15 GTs while both exits sat garrisoned.
3. **Odds-poisoning works.** An empty VP hex ringed by strong stacks
   never flips: the policy's local-odds check refuses to step in. 0211
   (20 VP) stayed Union-credited all game with no unit standing on it.
4. **The 17.32 leash is merciless.** Two XX Corps entrants parked "safe"
   at 1128 scored as destroyed (+10 enemy) for want of a reachable
   exit-connected road. Late entrants must march west immediately or not
   exist.
5. **Decoys are absurdly profitable.** One 5-strength brigade (147) led
   30+ CSP in circles for six game turns and got home alive. The policy
   chases nearest targets unconditionally.
6. **Mined regrets** (policy-completion baseline, see
   claude_game_regret.json): the GT1 commitment of the delay line toward
   1115 carries the game's largest counterfactual swing; the GT2 south
   scramble of 110/111 was correctly rated a bullet dodged.

## What the current policy AI does (know your baseline)

The shipped opponent walks each unit toward the nearest enemy-held VP hex,
keeps artillery at 2-3 hex standoff, runs the train for the exit, and
discharges all mandatory battles. It does not concentrate beyond local
odds checks, does not time attacks around night turns, and does not play
the LOC/cutoff endgame. Beating it means exploiting exactly those gaps.
