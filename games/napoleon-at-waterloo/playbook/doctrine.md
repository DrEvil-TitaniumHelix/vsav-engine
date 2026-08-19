# Napoleon at Waterloo (SPI, Second Edition 1971) — doctrine (knowledge corpus, spec #22)

Every claim below carries its rule citation (the NAW2 rule ids of
`games/napoleon-at-waterloo/ingest/rules_2nd_ed.json`, transcribed from the
printed 1971 folio; the folio's own Examples of Attacks and the SPI 1979
answers where a 2nd-Ed reading needed them) or a measured result from
seeded, verified games (`engine/verify_game.py` replays; seeds noted).
Language knowledge first; the auto-distilled champion genome is appended by
`make_playbook.py`.

## What the game pays (the whole game in one sentence)

- Two ledgers, one shared Demoralization Scale: **forty Combat Strength
  Points destroyed** breaks an army [VIC-01/VIC-03]. Whoever loses forty
  first loses — the Allies outright [VIC-03/VIC-07]; the French only
  after the Allies were broken first AND **seven French units exited** the
  north edge by the end of Game-Turn 10 [VIC-01/VIC-02]. Neither → draw
  [VIC-04]; both at once → French win only if the seven are already out,
  else Allied win [VIC-14].
- Forty Allied points destroyed with fewer than seven French out does not
  end the game: the Allies are **DEMORALIZED** for the rest of it — Allied
  attacks shift one column left, French attacks one column right
  [DEM-01/DEM-06/DEM-07] — and the best the Allies can then reach is a
  draw [DEM-04]. Destroying forty French points afterwards relieves
  nothing [DEM-09]. The French are never demoralized [DEM-05].
- The engine's graded margin from the French seat is therefore
  `Allied CS destroyed − French CS destroyed + 2 × French units exited`,
  +100 for a win, −100 for a loss (`engine/families.py::_naw_margin`).
  Exits are worth two points each because they are the second half of the
  French victory condition and cost nothing on the loss ledger [VIC-06].
- Ten Game-Turns, French Player-Turn first, Movement Phase then Combat
  Phase [SEQ-01..SEQ-04]. Victory is checked the instant a condition is
  met, mid Player-Turn included [VIC-07].

## Movement, Zones of Control, exits (what a turn can physically do)

- One Movement Point per hex, whatever the terrain [MOV-02/MOV-05]; Woods
  are impassable except along the road through a Woods/Road hex
  [MOV-16/MOV-17/MOV-18]; roads give no bonus and no combat effect (TEC).
  Infantry MA 4, cavalry MA 5, artillery MA 3 (counter photograph, PREP-4).
- **A unit that begins its Movement Phase in an enemy Zone of Control may
  not move at all** [MOV-13; ZOC-05/ZOC-08 mutual lock] — contact is a
  lock that only combat (elimination or retreat) breaks. A unit entering
  an enemy ZOC stops [MOV-10/ZOC-04]; it never moves through one [MOV-11].
- **Never end a Movement Phase stacked** [MOV-09; SPI 1979 4.4, NAW2-OR-2
  reading A]: the gate refuses `end_movement` while two friendly units share
  a hex, and refuses any move that would leave a stacked hex un-clearable.
- French exits: only the eleven arrowed North-edge hexes 0101–1101, one
  extra MP to leave [VIC-08/VIC-09], never from an enemy ZOC, never back
  [VIC-10]. Exited units are not losses [VIC-06]; units retreated off the
  map by combat ARE losses [VIC-13]. Allied units may never exit [VIC-12].
- The nine Prussians enter at the beginning of the Allied second turn
  along the East edge (column 27), any non-Woods hex free of enemy units,
  enemy ZOC and friendly units, for one MP, and may move and fight that
  turn [REI-01..REI-04; SPI 1979 7.2]; they may not be delayed while a
  legal entry hex exists [REI-06]. Their losses are Allied losses [REI-05].

## Combat (the mechanics that decide the loss race)

- Every friendly unit adjacent to an enemy unit MUST attack, every enemy
  unit adjacent to a friendly unit MUST be attacked, each unit once per
  Combat Phase [CBT-06/CBT-07/CBT-10]. The obligations are fixed the moment
  the Movement Phase ends [NAW2-OR-6 A] and a legal complete assignment
  always exists [NAW2-OR-5, `complete_assignment()`]. **Making contact is
  choosing to fight this turn** — there is no threatening without attacking.
- Odds = attack sum ÷ defence sum, rounded toward the defender, 1:5..6:1
  [CBT-01/CBT-02]; one die per battle [CBT-03]. CRT (folio map sheet, read
  4×): 1:5 is six Attacker Eliminated; 1:2 still carries one AE; **1:1 is
  the first column with no AE** (three Dr, three Ar) but it eliminates
  nothing either; 2:1 brings the first Exchange; **3:1 the first Defender
  Eliminated** (1 of 6, four Dr, one EX); 4:1 two DE + two EX; 5:1 four DE
  + two EX; 6:1 six DE. Exchange (both sides lose the defender's printed
  strength) lives in the 2:1..5:1 band [game.json combat.crt.die_rows].
- Defender doubled in a Town hex or a Woods/Road hex (TEC; D4 ruled and
  corroborated by the 1979 sheet). Attackers are never modified by terrain.
- Artillery attacks adjacent like anyone else OR **bombards from exactly
  two hexes** [ART-01], a single unit only [ART-13], not across an
  intervening Woods hex when both candidate paths are blocked
  [ART-17/TEC]; a bombarding gun is **immune to its own result** — never
  eliminated, never retreated except by choice, never pays an Exchange
  [ART-03/ART-05/ART-09/ART-11]. Guns adjacent to any enemy are obligated
  like every other unit [CBT-07]. Disrupted artillery may not fire in the
  Combat Phase it was disrupted [DISRUPTION S6].
- Retreats are one hex, **direction chosen by the victor** (2nd Ed; the
  defender chooses after an Ar — folio Example 21), never into enemy ZOC,
  off the map, into non-road Woods or an enemy hex; a friendly-occupied hex
  only when it is the ONLY safe hex and the occupant can itself be moved
  back (it is disrupted, DISRUPTION S1–S5); no safe hex = eliminated
  [RETREAT AND ADVANCE p.5, S4, VIC-13]. **A unit with its back to enemy
  ZOC dies to a Dr** — pinning a defender against ZOC or the map edge is
  worth a column.
- Exchange: the defender's PRINTED strength is owed and paid by adjacent
  attackers only, whole units, at least the amount owed [EX p.5,
  NAW2-OR-15 A]; when the adjacent attackers together cannot exceed it they
  are all lost, when every attacker bombarded it is free [ART-05,
  NAW2-OR-7 A]. Small attackers with a big gun behind them turn an EX into
  a bargain.
- Advance after combat is optional, one unit per vacated hex, one hex,
  and the advanced unit is out of that Combat Phase [CBT-14..CBT-16,
  OPTIONAL ADVANCE p.5, NAW2-OR-16 A]; the defender may advance after an
  Ar/AE [NAW2-OR-17].

## Measured baseline (shipped policy vs itself, seeds 900–909, full games)

- 7 draws, 2 Allied wins, 1 French win; mean French margin −3.1; mean
  29.1 French / 28.0 Allied CS destroyed; 20.8 battles per game. The
  French win (seed 909) came on Game-Turn 9 by demoralizing the Allies
  (42 CS destroyed) and running seven units out; the Allied wins (903 on
  turn 8, 905 on turn 9) were the French bleeding to forty first. `validate_ai.py` seed 8
  reproduces a French win the same way. Baseline vs baseline is balanced,
  which is what a training run needs.
- The shipped policy (`engine/ai_naw.py`) is a Movement-Phase attack
  planner: targets picked by the odds column the reachable attackers can
  build (defence doubled by terrain, artillery posted at two hexes with a
  clear line), attackers massed on adjacent hexes that touch no other
  enemy, everyone else positioned by enemy threat, terrain, cohesion and
  the objective (French: distance to the exit hexes, ×2.5 once the Allies
  are demoralized; Allied: a blocking line on `hold_row` between the French
  mass and the exits). Combat Phase resolves the fixed obligations
  best-expected-value first with `complete_assignment()` as the always-legal
  fallback; retreats as victor push the enemy away from its objective and
  prefer disrupting chains; exchanges pay the cheapest whole units; advances
  only into hexes that score higher.
- Full games run in ~3 s; every log replays byte-exact (`verify_game`).

## Measured champion run (2026-08-18/19, `runs/2026-08-18_naw_optimizer`)

- 150 generations, 43,408 games, 16 workers, ~2 h wall clock. Every
  generation's champion beat the shipped baseline in the in-run fitness
  (6–8 of 8 pairs, margins +180 to +1573), but the self-play title streak
  never held (streak 0 of 3; gauntlet 9–14 of 16) — the elite is
  intransitive, as it was for Siege of Jerusalem.
- Equilibrium portfolio (`engine/portfolio.py`, 4 entrants × 10 seeds × 2
  seatings): elite_0 50.4 %, elite_1 47.7 %, baseline 1.9 %. In that
  round-robin elite_0 LOST to the baseline (mean pair margin −30.5) while
  beating elite_2 (+51.8); elite_1 beat the baseline (+32.5). Rock-paper-
  scissors, not dominance.
- Graduation bar (`grad_bar.py`: ≥15/20 held-out pairs vs the baseline, seeds
  960–979, with positive margin, AND ≥4/5 pairs vs fresh random genomes,
  seeds 980–984): **elite_0 9/20 (+115) and 4/5 randoms (+846) — NOT MET;
  elite_1 9.5/20 (+513) and 1/5 randoms (−100) — NOT MET.** Both genomes
  trade with the baseline on seeds they never trained on.
- Verdict: **the baseline policy stays the shipped AI — no genome promoted**
  (the Austerlitz precedent). Against the shipped policy the trained elite is
  at parity, which is itself the measurement: the 14-gene family's
  optimum sits where the hand-written policy already is, and a stronger
  Napoleon needs a richer family (timing of the Prussian-facing screen,
  multi-turn exit planning), not more generations of this one.
- Reproducible: the bar records are `grad_bar.json` / `grad_bar_elite_1.json`
  in the run dir; the corpus (7 games, baseline self-play + elite_0 vs
  baseline both seats, all verified byte-exact) is `corpus_games/`.

## Measured champion run 2 — the richer family (2026-08-19, `runs/2026-08-19_naw_v2_optimizer`)

- The 14-gene family could only re-weight a fixed one-phase planner, so the
  family was widened to 31 genes (`engine/ai_naw.py` / `strategy_naw.py`),
  every default reproducing the shipped policy byte-exact (the seed-970
  corpus game replays identically). What was added is structure, not
  weights: **pocket** — attack posts are chosen to cover the defender's safe
  retreat hexes, because a unit with no legal retreat hex is ELIMINATED on a
  Dr [RETREAT AND ADVANCE p.5; DISRUPTION S4] and Dr is the commonest result
  from 1:1 to 3:1 (two attackers on opposite sides close all six hexes);
  **pocket_risk** (do not stand where a Dr kills); per-seat Allied overrides
  (`al_*`, one genome plays both seats); demoralization-race switches
  (`race_push`/`race_guard` move aggression as either ledger nears forty
  [VIC-01/VIC-03]); runner designation for the exits; CRT result weights.
- Before training, a hand-set `pocket = 1.0` alone took 18/20 held-out pairs
  off the shipped baseline (+48 mean); the `wall` corner 17/20 (+127). The
  family had a real gradient.
- Run: 120 generations × 2 training seeds per generation (16 pairs/gen, twice
  run 1's sample), 65,056 games, 14 workers, 3 h 7 min. The reigning champion
  beat the training field every generation (12–16 of 16) while the self-play
  title streak again never held (gauntlet 8.5–14/16) — the same intransitive
  shape as run 1 and SoJ. Equilibrium portfolio: a single genome, **elite_0
  100 %**, beating the baseline +87.4 mean pair margin in the round-robin.
- **Graduation bar (`grad_bar.py`): [1] 18/20 held-out pairs vs the baseline
  (seeds 960–979), total +3304, mean +165.2; [2] 18/20 pairs vs 20 fresh
  random genomes (seeds 980–999), total +3793 — MET.** The bar's second rung
  was amended this day by Bruce from 5 randoms (≥4) to 20 randoms (≥16): on
  the original 5-random rung the champion scored 3/5 (losses −109 and −8, one
  home-away pair each), and 16/20 on a first 20-random check (the baseline on
  the same 20: 8/20, −60.5) — the 5-pair test was a coin flip once random
  genomes of the richer family were pocket players themselves. Both records
  ship: `playbook/grad_bar.json` (the bar) and
  `playbook/grad_bar_5random_original.json`.
- What the champion learned (genome, distilled below by `make_playbook.py`):
  as French — full aggression (1.00) with the threat discount almost off
  (risk 0.08) but pocket 1.21 / pocket_risk 1.44: it attacks everything it
  can pocket and refuses to stand in corners; retreats valued 0.40 × Defense
  (dr_w, 2.7× the hand-written 0.15), attacker retreats nearly free (ar_w
  0.03), exchanges dear (ex_w 0.49); race_push 0.74 — it closes out the loss
  race; no runners (0) and exits only from Game-Turn 9 for units of Attack 6
  or less — it wins by destroying forty first, then runs; Prussians brought
  in toward the French mass (0.99). As Allied — aggression 0.57, cohesion
  1.11 (a line, not a swarm), no free bombardments (8.00), blocking line on
  row 11 with block 1.50 (stands between the French and the exits and holds).
- Corpus (`playbook/corpus/`): baseline self-play 970–972 + champion vs
  baseline both seats 970–971, 7/7 verified byte-exact. Champion as French
  seed 971: Allies demoralized, 7 exits, French win on Game-Turn 8.
- Verdict: **graduated — the champion genome is the shipped AI (Champion AI
  seat), generalship 5/10.** The Basic AI seat keeps the hand-written policy.


## The champion genome, in words (auto-distilled)

Machine-optimized doctrine - every number below was selected by tournament survival, not by argument:

- attacks are planned down to the 1.00 mark of the odds ladder (1.0 = accept 1:1 attacks, 0.5 = mass for 3:1, 0 = only 5:1 or better) [CRT p.5]
- a hex the enemy can reach next Player-Turn is discounted by 0.08 times the expected loss there
- Town and Woods/Road hexes (defender doubled, TEC) are worth 0.00 times half the unit's Defense Strength
- each adjacent friendly unit (up to three) adds 0.00 x 0.4 to a hex
- from Game-Turn 9 the weak French units start leaving by the eleven arrowed North-edge hexes [VIC-08]
- 'weak' = Attack Strength 6 or less; those exit first, the strong units keep fighting
- every French hex is pulled toward the nearest exit hex at 0.36 x 0.35 per hex of distance (x2.5 once the Allies are demoralized) [DEM-01]
- the Allied line stands on map row 11, between the French mass and the exit hexes
- Allied units are pulled toward that line at 1.50 x 0.35 per hex
- victorious units advance after combat when the new hex scores at least 0.50 (0 = only clearly better hexes, 1 = nearly always) [OPTIONAL ADVANCE p.5]
- bombarding artillery stands fast on an Ar result: yes [ART-11]
- free (unobligated) bombardments fire only at column 5 of the CRT or better (3 = 1:2, 5 = 2:1, 6 = 3:1) [ART-01]
- the Prussians enter 0.99 of the way toward the French mass (0 = the northernmost free East-edge hex) [REI-02]
- when scoring a hex next to a target, 0.46 of the planned attack strength on that target counts as already present
- attacks are posted to deny the defender a retreat hex (an occupied neighbour and both its flanks are closed; two attackers on opposite sides close all six) - a defender with no safe hex is ELIMINATED on a Dr, so a pocketed Dr counts 1.21 x the full Defense Strength; extra attackers join to close the last gap when that is worth more than 0.6 [RETREAT AND ADVANCE p.5: no retreat into EZOC/off-map/Woods/enemy hex; S4]
- a threatened hex with fewer than three open neighbours (map edge, Woods, friends, enemies) is discounted 1.44 x half its doubled Defense Strength per missing neighbour - do not stand where a Dr kills
- once the enemy has lost 25 Strength Points, aggression rises by 0.74 per full 15 further points toward forty - the loss race is closed out [VIC-01/VIC-03]
- once we have lost 25 Strength Points, aggression falls by 0.00 per full 15 further points - stay above forty
- from the runner turn, the 0 weakest free French units become runners: no attack posts, strong pull to the exits, double threat discount, exit the moment an exit hex is in reach [VIC-02/VIC-08]
- runners are designated from Game-Turn 10
- a Defender-retreat result is worth 0.40 x the Defense Strength in the attack's expected value
- an Attacker-retreat result costs 0.03 x the melee Attack Strength
- an Exchange costs 0.49 x the melee Attack Strength [EX: attacker loses at least the defender's printed strength, bombarding artillery exempt]
- ALLIED seat override of aggression: 0.57
- ALLIED seat override of risk: 0.00
- ALLIED seat override of terrain: 0.00
- ALLIED seat override of cohesion: 1.11
- ALLIED seat override of advance: 0.47
- ALLIED seat override of bombard_min: column 8
- ALLIED seat override of pocket: 0.05
- ALLIED seat override of pocket_risk: 0.60
