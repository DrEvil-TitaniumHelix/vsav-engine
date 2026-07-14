# Fable 5 vs. Opus 4.8 — Chickamauga head-to-head series
**2026-07-13 · Blue & Gray: Chickamauga — The Last Victory (campaign, 15 GTs) · play-by-mail harness (PLAY_BY_MAIL.md) · Judge: The Vassal · Overseer: Bruce**

## RESULT: OPUS 4.8 SWEEPS THE SERIES 2–0, WINNING FROM BOTH SEATS

| | Game 1 (seed 1863) | Game 2 (seed 1864, sides swapped, full game-1 knowledge both sides) |
|---|---|---|
| Sides | Fable=Union, Opus=Confederate | Opus=Union, Fable=Confederate |
| Final | **Confederate (Opus) 54 — Union (Fable) 5** | **Union (Opus) 40 — Confederate (Fable) 33** |
| Verification | 581/581 log entries reproduced | 560/560 log entries reproduced |
| Score anatomy | Opus: 5 elim + 10 occupation + 10 train + **29 cutoff (7 Union units, 17.32)**. Fable: 5 occupation. | Opus: **16 elim (all four = Fable units lost to forward placement)** + **24 CSP exited (the exit-engine innovation)**. Fable: 15 occupation (all three either-hexes — perfect) + 10 train + 3 elim + 5 cutoff (grand seal caught ONE unit). |
| Thinking score (structural, grade_commander) | Opus 550 — Fable 533 | Fable 557 — Opus 517 |
| Confidence curve | Opus 65→92 (well-calibrated). Fable 52→2 (honest collapse; called the loss 5 turns early). | Opus 55→90 (tracked reality). Fable 58→70 (final 70% rested on the misread "Opus did NOT exit" while 24 CSP were off-board). |

## The story in six decisions
1. **G1: Fable's entry-block gambit** — froze his own reinforcements off-board to dodge the 17.32 cutoff; it also stranded his train (+10 Opus) and, when the flood finally entered late, fed the cutoff 29 points anyway. The two boldest ideas of his game were the two line items that lost it.
2. **G1: Opus's economy-of-force discipline** — corrected the champion advisor's dead-corner over-garrison every single turn, realized at GT9 he was already winning on occupation, and flipped from conqueror to lead-protector.
3. **G1: The artillery discovery (GT12)** — Opus found bombardment as the only fortress-eviction tool that bypasses the odds guard: risk-free eviction lottery vs. "uncrackable" doubled fortresses.
4. **G2: Fable's grand seal (GT8-9)** — a ZOC-continuous wall to condemn Opus's whole SW wing (~50 str) to the cutoff that beat him in game 1. The series' boldest construction.
5. **G2: Opus's extraction (GT11-12)** — spotted the leash trap within two turns, pulled the entire wing through the one unsealable ridge lane, conceding 0822 as "only 5 points."
6. **G2: The exit engine (GT8-15)** — the series-winning innovation: no commander in six corpus games had ever monetized Union's humble 1-VP-per-CSP exits. Opus banked 24 CSP behind fortress rings with **every approach hex physically occupied** so no last-turn assault could even be staged — the anti-adjacency geometry that had frustrated him in game 1, weaponized.

## Verdicts (the questions the experiment was built to answer)
- **Skill vs. scenario:** the game-1 blowout was mostly *general*, not seat — Opus won from both chairs. But the seat swap shrank the margin sevenfold (49 → 7): the scenario still tilts Confederate. Both true, now with data.
- **Calibration beat deliberation.** The structurally-deeper thinker (by scorecard) LOST both games. What won: honest self-recalibration (Opus marked himself down twice after failed predictions) and one decisive rules innovation per game. Fable's characteristic failure mode: committing to elegant grand plans whose hidden costs surfaced late (entry-block → train; grand seal → outrun), plus reading absence of evidence as evidence of absence (the exit misread).
- **Corpus uniqueness (Bruce's GT2-3 hypothesis): CONFIRMED** in game 1 — no exact position match at any boundary; similarity to nearest prior game 89% → 38% → ≤20% → 5%. Confederate-side reactivity drove the divergence from GT1. (Game-2 curve not yet run — regenerable from the log.)
- **The gate held.** 1,141 verified log entries across both games; 124 illegal proposals rejected and provably inert; zero rules violations by either general; every plan hash-receipted; not one judge-authored order.

## Harness lessons (logged for v2)
1. **Deferred exit scoring is invisible** in the briefing VP counter — briefings must carry an exited-units tally per side (this directly caused Fable's decisive game-2 misread).
2. The plan compiler's per-mover ≥1-1 odds guard makes paired fortresses unassaultable by design (both generals reverse-engineered it; Overseer chose non-disclosure mid-match). DSL v2: assault verb, entry hold-back verb.
3. The renderer's news captions can report raw CRT results voided by rules (the "wiped out" artillery) — Fable caught and refused the false caption; fix caption to reflect applied results.
4. Retreat-into-EZOC-lock is the deadliest interface edge (killed Gracie): the guard prevents walking into suicide but not being stranded in it.
5. Play-by-mail autonomy: generals must arm background waits (foreground waits doze); bounce-and-resubmit self-heals without human touch.

## Where everything lives
- **This archive:** `matches/2026-07-13_fable_vs_opus/` — series report + copies of both judge logs (all SHA-256 receipts + full confidence tracks), both scorecards, both war journals per general.
- **Ground truth:** `runs/2026-07-13_fable_vs_opus/` and `runs/2026-07-13_fable_vs_opus_g2/` — verified JSONL logs, orders sidecars, grades.json. Everything regenerates from these.
- **Mailboxes (complete correspondence):** `comms_fable_vs_opus/`, `comms_fable_vs_opus_g2/` — every briefing, plan, rejection, map delivery, journal.
- **Bruce's deliverables:** `Desktop\fable_vs_opus\` — both labeled movies (module art, PRIVATE), stills flip-books for both games, README.
- **Publication rule:** anything published uses `--schematic` renders (zero copyrighted art); module-art movies/stills are private-use. Reproducers bring their own game per PLAY_BY_MAIL.md / ENCODING_GUIDE.md.
