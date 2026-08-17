# Napoleon at Waterloo (2nd Ed) — rulings needed from Bruce

Written 2026-08-17 after bites 1–3. SPI is gone and no errata for the 1971 folio exists, so for every item below the only remaining rung on the authority ladder is **a declared ruling by you**. Nothing here is a coding choice; each one changes what moves the gate accepts. Where I have already encoded a reading to keep working, it says so — a different answer is a small change, not a rewrite.

Answer format that works: the item id and a letter (e.g. `OR-2: B`). Anything you don't answer stays OPEN and blocks the cell it touches.

---

## A. Blocks bite 4 (mandatory attacks — the "assignment problem")

**OR-6 (cell C.7) — when are the must-attack obligations evaluated?**
The rules say every enemy adjacent to your units must be attacked and every unit of yours adjacent to an enemy must attack (CBT-06/07), and results apply immediately (CBT-04) — so the set of "adjacent enemies" changes during the phase.
- **A. Fixed at the start of the Combat Phase.** The gate computes the obligation set once; retreats/advances mid-phase don't add or remove duties. *(Recommended: computable, matches how the printed 16-unit battle-line examples are drawn — one board, two complete partitions.)*
- B. Re-evaluated live after each result. New contacts create new duties (which CBT-10 may make impossible to meet).

**OR-5 (cell C.6) — what does the gate do when NO complete assignment exists, or several do?**
- **A. The gate solves it: end_phase is refused while any obligation is unmet AND a complete assignment still exists; if none exists from the phase-start position, the player must still attack with everything that can attack, and unattackable enemies are excused with the reason logged.** *(Recommended: the print's spirit — attack everything you can — with a loud, logged excuse instead of a silent one.)*
- B. Refuse end_phase whenever any obligation is unmet, full stop (a position with no complete assignment cannot be closed — game wedges).
- C. Any partition the player picks is fine as long as every attacker attacks once (drop the "every enemy attacked" half).

## B. Blocks bite 5 (applying results)

**SD-3 (cell X.8) — may a DISRUPTED (pushed) unit be shoved into a Woods/Road hex?** Retreat bar says "non-Road Woods"; disruption bar says bare "woods".
- **A. Same as retreat: barred from non-Road Woods only, Woods/Road allowed.** *(Recommended: the two bars sit two paragraphs apart and were plainly meant to match.)*
- B. Literal: barred from ALL woods including Woods/Road.

**OR-11 (X.9) — disruption direction ("moved back … as if retreating"): back relative to what?**
- **A. Any hex passing the bars, chosen by the victorious player** (same freedom a retreat has — X.5 says retreats needn't move away). *(Recommended.)*
- B. Must increase distance from the retreating unit's attacker.

**OR-12 (X.11) — chain disruption (a pushed unit pushes another): compulsory? who dies if the chain fails?**
- **A. Each link obeys the same bars; the chain is taken when it is the only safe path; if the chain fails at any depth nothing moves and the ORIGINAL retreating unit is eliminated.** *(Recommended: one rule applied recursively, one loser.)*
- B. Chains never happen: a friendly-occupied "only safe hex" whose occupant cannot itself be pushed = retreating unit eliminated. (Contradicts the printed sentence that says chains occur.)

**OR-13 (X.12) — "uninvolved" friendly unit means:**
- **A. Not part of the attack just resolved.** *(Recommended: the natural reading; anything narrower leaves nobody to disrupt.)*
- B. Not part of ANY attack this Combat Phase.

**OR-14 (X.13) — how long does "disrupted" last?**
- **A. A flag for the rest of that Combat Phase only (its sole printed effect: disrupted artillery may not fire that phase); cleared at phase end.** *(Recommended: the punched set has no marker for it.)*
- B. Until the unit's next friendly Movement Phase.

**OR-15 (X.14) — EX loss: who picks the attacking units lost, and may he over-pay?**
- **A. The attacker picks, from units in that attack, any subset totalling AT LEAST the defender's (printed, undoubled) strength; over-payment allowed.** *(Recommended: the print says "at least", not "cheapest".)*
- B. Attacker picks but must choose a minimal sufficient subset.
- Sub-question: the loss compares against the defender's printed strength or its doubled defence value? *(Recommended: printed strength — "Strength Points" is the printed number, and the loss ledgers count printed points.)*

**OR-16 (X.17) — an advanced unit "may not participate in another attack or defense" that phase, but CBT-07 says every adjacent unit MUST attack.**
- **A. The advance bar wins: an advanced unit is excluded from the obligation set and cannot be named an attacker again; if it is later attacked (as defender) that phase — impossible for the phasing side's own units — no conflict.** *(Recommended, and consistent with OR-6 A.)*
- B. Advance is refused whenever it would put the unit next to an as-yet-unattacked enemy.

**OR-17 (X.18) — after an Ar (attacker retreats), may the DEFENDER (non-phasing) advance into the vacated hex?**
- A. Yes — the Retreat and Advance block grants the advance to "the victorious unit", which on an Ar is the defender.
- **B. No — advances are phasing-player only (SEQ-08: no non-phasing movement); the vacated hex simply stays empty.** *(Recommended: keeps SEQ-08 whole; the cost is that ART-11's voluntary Ar has no purpose, which is a print oddity either way.)*

**OR-7 (A.8) — EX when EVERY attacker is bombarding artillery (immune): does the defender die for free?**
- **A. Yes — literal: the defender is eliminated, nobody pays.** *(Recommended: the 2nd Ed print says immune; the 3rd Ed later closed this; we encode the 2nd Ed as printed and register the exploit.)*
- B. Such an EX is read as "no effect" (defender survives).
- C. The gate refuses an all-bombardment attack whose column can produce an EX (blocks the exploit at declaration).

**OR-8 (A.9) — a bombarding gun VOLUNTARILY takes an Ar it is immune to: who picks its direction?**
- **A. The gun's owner picks (it is his election).** *(Recommended.)*
- B. The victorious (enemy) player, as with any retreat.

**OR-10 (A.16) — disrupted artillery "may not fire in the Combat Phase in which it was disrupted":**
- **A. Forward-looking only (a gun that already fired is unaffected), and a disrupted gun still counts as an adjacent unit for the obligation set (its duty is discharged by other units attacking its neighbour).** *(Recommended.)*
- B. A disrupted gun is out of the phase entirely and drops out of the obligation set.

## C. Already encoded under a stated reading — confirm or flip

**OR-2 (M.6) — stacking.** Encoded **B: no hex ever holds two units** (a unit may not even end its own move on a friend and shuffle later). A = allowed mid-phase, must be un-stacked by phase end. *(Recommended B.)*

**OR-18 (V.12) — exit through Woods/Road hex 1101.** Encoded **LEGAL** (enter only from 1102 along the road, exit north — the exit arrow is printed inside that hex). *(Recommended: confirm.)*

**OR-9 (A.14) — artillery firing over Woods on a "bent" two-hex line (two candidate intervening hexes).** Encoded **STRICT: blocked if either candidate hex is Woods.** Alternative: blocked only if both are. *(Recommended strict.)*

**D4 (C.14) — Town OR Woods/Road defender doubles** — you ruled 2026-08-14; encoded and validated. Nothing needed.

## D. Bite 6 (reinforcement / victory / demoralization) — I will encode these readings unless you object

**OR-1 (S.3) — "Place the Prussian units on the East side":** encoded as **off-map staging** (they enter at the start of the Allied turn of Game-Turn 2, REI-01). *(Recommended.)*

**OR-4 (R.5) — Prussians "may not be delayed", but every East-edge hex is enemy-occupied / in enemy ZOC:** encoded as **enter wherever legally possible; a unit that cannot legally enter this turn enters on the first later turn it can, and the gate logs the excuse; entering into an enemy ZOC hex is legal (the unit just stops there).** *(Recommended.)*

**OR-19 (D.6) — demoralization shifts a column that is already at the end of the table (Allied at 1:5, French at 6:1):** encoded as **clamp at the printed end (no change)**. *(Recommended: the table has no other column, and the clamp footnote is the only printed guidance.)*

## E. Platform-level (not NaW-specific)

**OR-3 (M.13) — MOV-19 "may not change its move without the consent of the opposing Player" vs the platform's UNDO in all games.**
- **A. UNDO is a platform affordance declared as such (solo/hot-seat convenience); it is already unavailable in mailed and LLM matches, which is where an opponent's consent would matter.** *(Recommended: nothing changes.)*
- B. Add an opponent-consent prompt to UNDO in any two-player mode.
- C. Disable UNDO in Full-rules mode for this game.

---

Counts: 5 answers unblock bite 4/5 fully if you take every recommendation (OR-6, OR-5, SD-3, OR-15, OR-17 are the ones with real teeth; the rest follow). Everything else keeps moving meanwhile.
