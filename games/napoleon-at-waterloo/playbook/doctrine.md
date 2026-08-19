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
