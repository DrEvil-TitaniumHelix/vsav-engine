# Westwall: Arnhem — doctrine (knowledge corpus, spec #22)

Every claim below carries its rulebook citation (sections per
`rules_transcription.json`, transcribed from the module's rules) or a
measured result from seeded, verified games (`engine/verify_game.py`
replays; seeds noted). Language knowledge first; the auto-distilled
champion genome is appended by `make_playbook.py`.

## The VP arithmetic (what the game actually pays)

- Allied income [17.11]: **1 VP** per German unit eliminated; **5 VP per
  GT** per non-airborne, non-glider unit north of the Waal with a LOC at
  the end of the GT; **10 VP** per such unit north of the Neder Rijn at
  game end with a LOC.
- German income [17.12]: **5 VP** per Allied unit destroyed; **3 VP per
  German player-turn** per Allied unit that cannot trace a LOC [17.35].
- Victory is the **ratio** German:Allied [17.4] — ≥3.0 German Strategic,
  2.01–2.99 German Tactical, exactly 2.0 Draw, 1.0–1.99 Allied Tactical,
  ≤1.0 Allied Strategic. The draw line is Ger = 2 × All: every Allied VP
  is "worth" two German VP. The engine's graded margin is therefore
  2·All − Ger (engine/families.py).
- Consequences the schedule forces:
  - An Allied unit lost is a 5-VP gift [17.12]; an Allied unit parked
    north of the Waal with a LOC is a 5-VP-per-GT annuity [17.11]. The
    same unit is worth more banking geography than trading itself away.
  - A cut LOC bleeds 3 VP per failing unit per German player-turn
    [17.35] — corridor security is not logistics flavor, it is the
    German player's second income stream.
  - Ten GTs of a single Waal-zone unit (50 VP) outweigh eliminating
    ten German battalions (10 VP). Geography >> attrition for the
    Allied player; attrition + LOC cuts are the German game.

## LOC mechanics (where the corridor can be cut)

- Ground LOC [17.31]: contiguous hexes to the south-edge exits
  0105/0106; entering a trail hex locks the trace to road/trail
  hexsides, entering a road hex locks it to road hexsides only — the
  corridor is effectively the road net, and one German unit (or
  un-negated ZOC hex) on it severs everything forward [17.33].
- Friendly units negate EZOC for LOC [17.33]: pickets standing ON the
  road keep the trace alive through German ZOC — the rules reward
  leaving units behind on the corridor.
- Airborne LOC [17.32]: ≤7 hexes, any terrain, to the DZ counter of the
  unit's own division; Polish and all German units exempt [17.36];
  never through unbridged river/stream hexsides [17.34].
- Demolished bridges [12.x] interact with 17.34: dropping the road
  bridges doesn't just slow movement, it deletes LOC routes.

## Measured baseline (the gap the optimizer was asked to close)

- Shipped policy vs itself (seed 7, verified): **All 19 — Ger 509,
  German Strategic**. The naive corridor charge feeds the German
  5-VP-per-kill and 3-VP-per-LOC-fail streams and banks almost nothing.
  The historical result was also a German win — but not a 26:1 ratio;
  most of that gap is strategy, not situation.
- Doctrine-seeded corners (seed 7, one game each, verified pipeline):
  Allied zone-banking corner improved the Allied graded margin by ~20;
  German corridor-scissors corner improved the German margin by ~21.

## Measured result (the run of 2026-07-14)

- Tournament: population 16, 150 generations, **43,400 verified games**
  (engine/optimize.py, seeds 1–400 training, 900–939 gauntlet). No
  in-run graduation (the gauntlet's fresh-random challengers keep
  variance high — same behavior as the Chickamauga run).
- Equilibrium exit (engine/portfolio.py, held-out seeds 940–949): the
  elite pool is TRANSITIVE; a hall-of-fame genome (elite_1) beats the
  final reigning champion +18.4/pair and the baseline +96.3/pair; the
  Nash mixture is **100% elite_1** with worst-case mean margin ≥ 0
  against every pool strategy. elite_1 is the shipped champion.
- **Graduation bar (spec #22) — MET.** Vs the shipped baseline,
  home-and-away on 20 held-out seed pairs (960–979): **20/20 pairs won,
  average pair margin +144**. Vs three fresh random genomes it never
  trained on (seeds 980–984): **15/15 pairs won, average +176**.
- What the champion does NOT change: every corpus game is still a
  German Strategic win (as history was). As Allied it cuts the bleed
  by 150–220 graded-margin points per game (e.g. seed 970: All 17 —
  Ger 334 vs the baseline-mirror's ~19–509); as German it beats the
  baseline Allied harder than the baseline itself does (490s vs 509).
  The Allied game this scenario pays is damage control toward a
  Tactical result, not victory — the champion proves the ceiling is
  much higher than the naive floor, not that the ratio flips.
- The champion's discovered doctrine, in one line: **bank the Waal zone
  from GT 1, picket the whole corridor (LOC pickets negate EZOC,
  17.33), fight only near even odds, dash for the Rijn on the final
  GT — and artillery fights in the line rather than standing off.**
  The naive bridge charge never survives contact with the VP schedule.

## The strategy space the genome spans (strategy_ww.py)

- Allied: when to stop driving at the Arnhem bridge approach and start
  banking Waal-zone (then Rijn-zone) VP [17.11]; how far airborne
  battalions stray from their DZ against the 7-hex leash [17.32]; what
  fraction of the column stands as corridor pickets [17.33/17.35]; the
  minimum local combat differential a unit will voluntarily accept
  (every loss pays 5 VP [17.12]; the policy floor is −2 [7.0]).
- German: how strongly units steer for corridor-road LOC hexes
  [17.31/17.33] versus the nearest enemy; the pull toward the airborne
  pockets; mass discipline before advancing.
- Not in the genome (declared, per the policy's own known-weak list):
  German map exit/re-entry [15.4], Engineer assault stacks [13.24],
  deliberate bridge-line attacks, diversionary attacks [7.51]. These
  wait for a DSL that can express them; the register of what the
  champion does NOT know is part of the book.


## The champion genome, in words (auto-distilled)

Machine-optimized doctrine - every number below was selected by tournament survival, not by argument:

- from GT 1, Allied ground units break off the bridge drive and bank Waal-zone VP (5/unit/GT, 17.11)
- from GT 10, Allied ground units head north of the Rijn for the 10 VP/unit end bonus (17.11)
- airborne battalions engage enemies up to 7 hexes from their DZ (LOC limit is 7, 17.32)
- the Allied column advances only above 23 combined attack strength - below that it stands
- 100% of Allied ground units (rearmost first) stand as corridor pickets against LOC cuts (17.35)
- Allied units accept a mandatory battle only at a local differential of -1 or better (policy floor is -2, 7.0)
- German units weight corridor-road LOC hexes at 0.00 (0 = ignore the corridor, chase units)
- German units weight the airborne pockets at 0.00
- the German field force advances only above 3 combined attack strength
- artillery no (1 = 8.11 barrage standoff, 0 = fights in the line)
