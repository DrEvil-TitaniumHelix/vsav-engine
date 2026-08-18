# Napoleon at Waterloo (2nd Ed) — open rulings, DISTILLED (v2, 2026-08-17 evening)

**What changed since v1:** I ran every open item against **SPI's own 1979 Third Edition text** (same publisher, same designer, rules rewritten by Simonsen — the printed booklet scan we hold, plus the 1979 map-sheet Terrain Key). Where the 1979 text answers a 2nd Ed gap in so many words, that is a **publisher clarification** — a real rung on the authority ladder, above a declared ruling. Christian Holm Christensen's community rules (GitLab) were read as a second opinion only.

Result: **14 of 21 items are answered by SPI's own later text. 3 remain for you (OR-6, OR-5, OR-16) and block bites 4–5; 2 more (OR-4, OR-19) are encoded per my recommendation pending your objection; 1 is platform policy; D4 was already ruled.**

Sources: 3rd Ed rules booklet [case numbers in brackets], read verbatim from the printed scan (RULEBOOK_VERIFIED §4, ed3 OCR pages 4–5 cross-checked); 1979 Terrain Key read by OCR at 2× off the map sheet scan (`Nap_Waterloo_1979_Map.pdf` p.1, rotated 90°).

---

## RESOLVED by SPI's own 1979 text (encoded / to be encoded as stated — tell me only if you object)

| item | question | SPI 1979 says | encoding |
|---|---|---|---|
| **OR-9** | bombardment past Woods on a "bent" two-hex line | Terrain Key: *"an artillery unit in hex 0803 could not fire into hex 0805 (but could fire into 0705 and 0905) because of the intervening woods in hex 0804. Artillery may bombard into Woods-Road hexes."* Woods **and Woods-Road** block. | **DONE (this session):** bent shot open if either candidate hex is clear; woods_road blocks and is a legal target. My earlier "strict" reading was wrong and is fixed. |
| **SD-3** | may a displaced unit be pushed into a Woods/Road hex | [6.4] safe hex = "traversable" (a hex the unit could enter in movement) + not in EZOC; [4.2] woods entered only via road hexsides "even when advancing or retreating"; [6.5] displaced units retreat to safe hexes | **A** — same bars as a retreat; Woods/Road allowed via its road hexside |
| **OR-11** | displacement direction | [6.5] no direction rule; any safe hex | **A** — any safe hex, victorious player chooses (2nd Ed's chooser) |
| **OR-12** | chain displacement; who dies | [6.5] *"The displaced unit may itself cause a displacement in a sort of chain reaction of retreats"*; *"if not, the original unit is destroyed instead of causing displacement"* | **A** — chain compulsory when only path; failure at any depth ⇒ original retreating unit eliminated |
| **OR-13** | "uninvolved" | [6.5] any friendly unit in the only safe hex may be displaced (only bar: artillery still owing a required bombardment) | **broad** — any friendly unit not in the attack being resolved |
| **OR-14** | how long "disrupted" lasts | 3rd Ed has no disrupted state at all | **A** — per-Combat-Phase flag; only effect = disrupted artillery may not fire that phase |
| **OR-15** | EX: who pays, how much, over-pay | [6.3] Ee: *"the attacking force must lose a number of Combat Strength Points at least equal to the PRINTED value of the defending force"* | **A** — attacker picks from units in the attack; ≥ printed (undoubled) strength; over-payment legal |
| **OR-17** | defender advances after Ar/AE? | [6.3] Ae/Ar: *"Defending unit has the option to advance after combat"* | **A** — YES, the non-phasing defender may advance one unit (reverses my v1 recommendation) |
| **OR-7** | all-bombardment EX kills for free? | [6.8] *"Even in the case of an Ee result, the defender is destroyed but the artillery unit is unaffected."* | **A** — literal; SPI confirmed it, not an oversight we may fix. (PREP-7's note that the 3rd Ed "closes" this was wrong.) |
| **OR-8** | voluntary Ar by a bombarding gun — who picks direction | [6.8] *"Bombarding artillery units may voluntarily retreat after combat"* — the owner's option | **A** — owner chooses hex |
| **OR-10** | disrupted artillery already fired / still counts for obligations | 3rd Ed instead forbids displacing artillery that still owes a bombardment | **A** — forward-looking; disrupted gun still counts as adjacent |
| **OR-2** | stacking reading | [4.4] units may never **END a Movement Phase** stacked (penalty if inadvertent) | **A — DONE (bite 6):** a unit may end its own move on a friend mid-phase (only if that friend can still move off), end_movement refused while any hex holds two. |
| **OR-18** | exit through Woods/Road hex 1101 | [4.2] woods entered/left only via road hexsides — the north hexside IS the road | **legal** (as encoded) |
| **OR-1** | Prussian staging | [7.0] reinforcements ENTER during the Movement Phase | **off-map pool** (as encoded) |
| (C.10/11) | several-on-several attack geometry | [5.4] *"provided each attacker could have attacked each defender separately"* | every attacker adjacent to every defender (as encoded) |

## RULED BY BRUCE 2026-08-17 (evening)
- **OR-6: A** — must-attack obligations are fixed at the start of the Combat Phase; each attack resolves on the live board; an obligation lapses if its contact no longer exists when it comes up. *Reasoning: this is how humans play the physical game; matches the printed battle-line examples; the only reading a referee can enforce without inventing relief rules.*
- **OR-5: closed by proof** — with the list fixed at phase start a complete assignment always exists (any uncovered enemy can be folded into an adjacent friend's attack, since one unit may attack every enemy it touches). validate_combat will prove it constructively on every reachable position rather than assert it.
- **OR-16: A** — an advanced unit drops off the fixed obligation list and may not be named again that phase.
Christian's reply (asked the same evening) may still overturn these.

## PREVIOUS TEXT (kept for the record) — 3 items that blocked bites 4–5

**OR-6 (C.7) — when are the must-attack obligations evaluated?** 3rd Ed [5.1]/[6.1] repeats the same words (per-attack announcement, any order, results immediate) and does not say.
- **A. Fixed at the start of the Combat Phase** *(recommended — computable once; matches the printed battle-line examples).*
- B. Re-evaluated live after each result.

**OR-5 (C.6) — no complete assignment exists / several do.** No help from 1979.
- **A. Gate solves it: end_phase refused while an obligation is unmet AND a complete assignment still exists; if none exists from the phase-start position, attack with everything that can, unattackable enemies excused with the reason logged** *(recommended).*
- B. Refuse end_phase whenever any obligation is unmet (can wedge).
- C. Only "every attacker attacks once" is enforced.

**OR-16 (X.17) — advanced unit "may not participate in another attack or defense that phase" vs CBT-07.** 2nd-Ed-only clause; 3rd Ed dropped it. With OR-6 = A it is a sequencing constraint.
- **A. Advanced unit leaves the obligation set; may not be named again** *(recommended).*
- B. Refuse advances that create new contact.

**OR-4 (R.5) — ENCODED A in bite 6 — Prussians "may not be delayed" but no legal entry hex.** 3rd Ed [7.2]: no entry into an enemy-occupied hex or an enemy ZOC; [7.3] made delay legal (a deliberate 2nd→3rd change, so it does not bind).
- **A. Entry hex must be free of enemy units and enemy ZOC (per [7.2]); a unit with no legal entry hex enters at the first later Movement Phase it can, reason logged; a unit that CAN enter must** *(recommended).*
- B. Entry into an EZOC hex allowed (unit just stops); refuse end_movement only if literally no hex exists.

**OR-19 (D.6) — ENCODED A in bite 6 — demoralization shift at the table's ends.** 3rd Ed [6.2] *"ratios beyond the table's ends are treated as the end column"* — arguably covers it.
- **A. Clamp at the printed end** *(recommended, low stakes).*
- B. Shift is void when at the end.

## PLATFORM — 1 item

**OR-3 (M.13) — MOV-19 "may not change its move without the consent of the opposing Player" vs UNDO.**
- **A. UNDO is a declared platform affordance (already unavailable in mailed/LLM matches)** *(recommended: nothing changes).*
- B. Opponent-consent prompt in two-player modes. C. Disable UNDO in Full rules for this game.

## Sources checked 2026-08-17 evening (nothing further needed)
- **spigames.net "Errata for SPI Games" storehouse** (Joe Beard, "central storehouse for all known official errata"): lists errata pages for ~80 SPI titles — **no Napoleon at Waterloo entry**. Strongest available evidence that SPI never published NaW errata. (It DOES carry official errata for Westwall/Arnhem and Blue & Gray — noted for those games.)
- **MOVES #3** "The Bias Nobody Knows" (Simonsen; spigames M3BiasNAW.pdf): strategy essay, no rulings; confirms the 2nd Ed changes (Towns ×2, adjacent artillery suffers results, the 1-4 added in the Woods hex SW of Hougoumont = our 1014) and the victory logic (40 points beats exits).
- **MOVES #28** "8,000 to 1" (spigames 8000To1NAWM28.pdf): Simonsen's own eight-line rules summary — "all Friendly units adjacent to Enemy units must participate in an attack", artillery bombards "a single target two hexes distant", combined attacks "against individual defenders", "Units may Advance after Combat (**one unit per vacated loser's hex**)". Consistent with everything encoded; nothing on OR-5/OR-6/OR-16.
- **MOVES #30** results (8000To1NAWM30.pdf): narrative of the staff play; the panel's standing order "advance after combat only to surround units about to be attacked" shows advances used positionally mid-phase — consistent with sequential declaration and with OR-16 A, not decisive.
- **Christian Holm Christensen's rules** (GitLab rules.tex): agrees on EX at-least/printed/attacker-picks, chain displacement, defender advance after Ar; his retreat chooser = owner (3rd Ed).
- BGG needs a login (API and site) — untested; Decision Games 2014 = 3rd Ed text (not needed).

- **BGG rules forum, read 2026-08-17 evening through Bruce's browser** (98 threads listed; the rules threads that touch our items):
  - *Advance from ZOC, combat order* (2023, incl. "Donald Johnson, Designer"): advancing while in another enemy's ZOC is legal; advances DO shape later combats in the same phase; the attacker orders his combats to advantage — "all yes". Consistent with sequential resolution on a live board (fits OR-6 A: obligation set fixed, board live) and with OR-16 A.
  - *[SOLVED] Combat results with Ee* + *question on Ee*: whole units, attacker chooses, must total at least the defender's points, no step reduction — = OR-15 A.
  - *Defender advance after combat* (2018): **Stephen Oliver himself** — "either the attacker or the defender can advance after combat if eligible" — = OR-17 A.
  - *Retreat question*: one hex; may displace a friendly unit, again one hex.
  - *Voluntarily eliminate unit(s) instead of retreating?* (2026): consensus NOT allowed (retreat is mandatory).
  - *Attacking Enemy in Wood Hex Through Non-Road Hexside* (2022): attacks across a non-road hexside into a Woods/Road hex are legal (adjacency has no terrain limit); advancing into it across a non-road hexside is not (3rd Ed 4.2 "even when advancing or retreating"). Our per-attack adjacency already matches; the advance/retreat hexside bar goes into bite 5.
  - *Clarification on Reinforcement rules* (2021): **Stephen Oliver** — reinforcements may not enter an edge hex that is enemy-occupied or in an enemy ZOC — = the entry bar encoded under OR-4 A.
  - Nothing found on OR-5 (no complete assignment) or OR-6 (timing) as such — the community plays sequentially and never names the edge case.
  - Stephen Oliver is active on BGG as @Snowdash — a second person to ask alongside Christian.

## Still worth downloading (nice-to-have, not blocking)
- Decision Games 2014 rules = 3rd Ed per Christian's edition history — **not needed**.
