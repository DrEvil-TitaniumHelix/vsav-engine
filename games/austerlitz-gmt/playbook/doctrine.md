# Austerlitz (GMT) — A15.1 The Northern Flank — doctrine (knowledge corpus, spec #22)

Every claim below carries its rules citation (GMT living rules section
numbers; A-sections from the sanctioned Spanish rulebook+playbook
translation, El Viejo Tercio, which carries the scenario's victory
conditions; designer rulings from the David Fox Q&A) or a measured
result from seeded, verified games (`engine/verify_game.py` replays;
seeds noted). Language knowledge first; the auto-distilled champion
genome is appended by `make_playbook.py`.

## The victory arithmetic (what the scenario actually pays)

- French win the instant **7 Allied units** are destroyed, routed or
  unsteady; Allied win at **10 French**; otherwise the 4:40 pm turn
  limit (16 turns) is a **draw** [A15.1]. First to reach the threshold
  wins — the check is live, mid-activation.
- The rosters make those thresholds asymmetric work: the Allied field
  **10** non-leader units (9 infantry battalions + the a/B horse
  battery — no cavalry), the French **15** (8 infantry, 4 cavalry, 3
  batteries). The French must break 70% of the Allied army; the Allied
  67% of the French — but with no cavalry arm to do it with [A15.1
  OOB / scenario roster].
- "Broken" counts **current** state: a routed or unsteady unit that
  rallies [12.0] stops counting. Rally is threshold denial, not
  housekeeping — the game ends only if the count stands at 7 (or 10)
  at some instant.
- The engine's graded margin (engine/families.py) is the
  cross-multiplied differential 10·(Allied broken) − 7·(French
  broken): zero when both sides sit at the same fraction of their own
  threshold, ±100 on an actual A15.1 win.

## The command economy (the activation currency)

- A turn is Pool Placement → Initiative → LIM Activations → Non-LIM →
  Rally/Fatigue [3.0]. In A15.1 the pool is **voluntary** per turn
  (replaces the 4.2 rolls): a division not committed rests [A15.1].
- Every LIM committed costs its division **+1 fatigue — even a STOP
  result or a declined attempt** [13.1, Fox Q&A; register AUS-CMD-3];
  a resting division recovers. Fatigue 7 crossings cost morale
  [13.2] — the fatigue track is a second casualty stream, paid before
  any enemy action.
- Full Activation requires the leader's activation roll and risks the
  Breakdown Table [4.5.1/4.7]; the Limited activation is roll-free at
  half MA [4.6.2]. Melee, charges and free adjacency need Full
  [4.6/8.2–8.4] — the roll is the price of fighting.
- Division breakpoints (Command Card): Suchet 8, Markov 5, Vorpatzki
  2, Treilhard 3, Milhaud 2 broken units. At breakpoint: no Full
  Activation, the LIM never re-enters the pool [11.2.1] — Markov's 5
  is 5 of the same 9 battalions the French need 7 of; the Allied
  command dies before the army does.
- Rules-as-written baked into training: all nine Allied battalions
  answer to **Markov** (counter art + A15.2 OOB; register AUS-CMD-2,
  flagged for expert review of the printed playbook p8) — Vorpatzki
  commands at most the a/B battery via the A15.1 artillery-attachment
  rule.

## The arms asymmetry

- The four French cavalry regiments are the scenario's only charge
  threat [8.4]; the Allied answer is the square [8.4.2#4] — a square
  that stands cancels the charge bonus, and cavalry that charges home
  goes Blown (half MA, no charging) with recovery only through quiet
  turns [8.4.4/8.4.5]. May Charge is preserved only by spending at
  most half MA [5.1.2].
- Allied infantry in square against cavalry is nearly safe from the
  charge but a fire target in the open [8.1]; the French combined-arms
  play (threaten the charge, punish the square with fire) is the
  scenario's core tactical engine — and the policy AI plays both
  halves of it only as far as its declared doctrine reaches.

## Measured baseline (the gap the optimizer is asked to close)

- Shipped policy vs itself, seeds 1–20, one game each through the full
  schema-4 gate (verified pipeline): **French 20/20 wins, mean graded
  margin +160**. Typical game: 7–10 Allied units broken by turn 3–8 of
  16; the Allied counter-score 0–5. Historically the battle was a
  crushing French victory — but a 20/20 sweep with the Allied never
  reaching half their threshold is a strategy floor, not proof of the
  scenario's ceiling. How much of the gap is doctrine is exactly what
  the tournament run measures.

## Measured result (the run of 2026-07-17/18)

- Tournament: population 16, 150 generations, **43,384 verified games**
  (engine/optimize.py, seeds 1–400 training, 900–939 gauntlet; run
  interrupted once at gen 70 by an OS-killed worker — gen 70 replayed
  clean, the optimizer now survives lost workers, resumed from
  checkpoint with nothing lost). No in-run graduation (streak never
  exceeded 1 - the fresh-random gauntlet variance, as in both prior
  runs).
- Equilibrium exit (engine/portfolio.py, held-out seeds 940–949, full
  home-and-away round-robin): **the Nash mixture is 100% BASELINE.**
  The shipped policy's mean pair margin against the three distinct
  elite genomes is +3.6 / +0.3 / +4.2 — statistical parity in a game
  whose decisive margins run ±160. No evolved doctrine-knob setting
  beats the shipped policy on seeds it never trained on.
- **Graduation bar (spec #22): NOT MET** — the bar requires dominating
  the shipped baseline, and the equilibrium of this strategy space IS
  the shipped baseline.
- What the verdict means (the elites are NOT baseline clones — they
  hand the enemy the initiative, stand off at 3.4 hexes, melee only at
  1.41:1, preserve May Charge to MA+11 — and still only tie): within
  the 12-knob command-economy space, the A15.1 outcome is driven by
  the shared per-action core (nearest-enemy maneuver, the 8.1.1 fire
  hierarchy, always-rally), not by these thresholds. The in-run
  fitness wins (+133 to +354 per generation) were seed-specific: one
  training seed per generation lets selection latch onto noise that
  held-out seeds erase.
- Two honest readings, both earned by the data: (1) a robustness
  certificate — 43,384 games of evolutionary attack found no doctrine
  setting that beats the shipped AI within its own decision space;
  (2) a boundary marker — beating it will take genes the current
  genome deliberately does not have: unit-level MANEUVER doctrine
  (concentration of force, focus-fire target selection, objective
  steering beyond nearest-foe) rather than thresholds on the existing
  picks. That is the v2 genome direction, Bruce's call.
- Corpus (runs/…/corpus, every log verified byte-exact): baseline
  self-play seeds 950/951 (French +145/+186); the final reigning
  genome as French vs baseline +162/+183 (no better than baseline's
  own +160 mean), as Allied vs baseline still French +149/+163 — the
  parity claim, replayable.

## The strategy space the genome spans (engine/strategy_nap.py)

- Command economy: how deep into the fatigue track a division keeps
  committing its LIM [13.1/13.2], whether a fatigued division near the
  enemy still commits, initiative sequencing (own LIM first vs handing
  the enemy the opening) [4.4], the Full-vs-Limited risk threshold by
  enemy distance and leader rating [4.5.1/4.6/4.7], breakdown offers
  [4.7].
- Battle doctrine: the stand-off distance (refusing contact denies the
  French their 7), cavalry May-Charge preservation and charge
  acceptance [5.1.2/8.4], melee odds appetite [8.2/8.5.1], the
  square-vs-charge answer [8.4.2#4], artillery unlimber timing
  [6.3.7].
- Not in the genome (declared, per the policy's own known-weak list):
  melee supports [8.2.1#2], strategic movement declarations [5.2],
  reaction limber [6.2.5], countercharge (scenario-unreachable — the
  Allied have no cavalry), multi-turn plans. A gene may only re-weight
  decisions the validated policy already makes, never grant it new
  mechanics; the register of what the champion does NOT know is part
  of the book.
