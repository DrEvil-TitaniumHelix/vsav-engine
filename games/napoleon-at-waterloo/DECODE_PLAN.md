# NAPOLEON AT WATERLOO (SPI, 2nd Edition 1971) — DECODE PLAN

**Written 2026-08-14 at the close of the decode-prep phase (PREP-1 … PREP-7).**
Audience: Fable, who writes the encoding. Everything here is backed by a committed, machine-readable
artefact; nothing asks you to re-derive a reading.

**Scope: the 2nd Edition only.** Bruce decided 2026-08-13 that NaW ships as **two games sharing one
engine module**, encoded one at a time, 2nd Edition first. There is no edition flag. See §7 for where
the 3rd Edition now stands — it moved this evening.

---

## 1. THE ONE-LINE STATUS

**The 2nd Edition is blocked on nothing and nobody.** Every rule is transcribed, every chart is data,
the order of battle is confirmed on three independent witnesses, the map is a validated graph, and
the game's own 27 printed worked examples replay against our arithmetic with no mismatches. What
remains is encoding work and **three rulings only Bruce can give** (§4).

---

## 2. WHAT YOU CAN CONSUME DIRECTLY

All under `games/napoleon-at-waterloo/ingest/`, all committed.

| File | Contents | Confidence |
|---|---|---|
| `rules_2nd_ed.json` | **127 rule rows** — id, verbatim text, `obligation` (MUST/MUST NOT/MAY/DEFINES/PROCEDURE), `enforceability`, citation, `depends_on`, `edition_diff` tag | read off the print, OCR cross-checked |
| `crt_2nd_ed.json` | 60 CRT cells, clamp, rounding rule, result codes | read **4×**, 60/60 agree |
| `hexgraph_2nd_ed.json` | 594 hexes: terrain, exits, road hexsides, six-way adjacency | parity **proved** against two independently fitted pixel grids |
| `oob_2nd_ed.json` | 44 at-start units + 9 reinforcements, per-field provenance | **three witnesses**, zero disagreements |
| `combat_charts.json` | Terrain Effects Chart, Explanation of Results, Retreat and Advance | verbatim, 37 crops |
| `disruption_verified.json` | the whole DISRUPTION rule, 6 sentences | 6× zoom, OCR-confirmed |
| `worked_examples.json` + `example_check.json` | 27 printed examples; **27/27 odds reproduced** | machine-replayed |
| `timerecord_oob.json` | Time Record, Demoralization Scale, Exited French box | unreadable list empty |
| `rulings_2nd_ed.json` | declared rulings + source defects, with authority | 1 open |
| `authority_ladder.json` | 39 assets tiered, with the Gap Rule | — |
| `coverage_matrix.json` + `COVERAGE_MATRIX.md` | **111 cells**, all traceable to rule ids | 0 enforced (nothing built yet) |

**Prose is not authority any more.** `literature/napoleon-at-waterloo/RULEBOOK_VERIFIED.md` is now
corrected and carries a §0 admitting its own failure history — read that section before quoting it.
Where the JSON and the prose disagree, **the JSON was read later and more carefully**; report the
difference rather than picking.

---

## 3. THE FIVE TRAPS

These cost real work to find. Do not rediscover them.

1. **Never share hex arithmetic between the editions.** The 2nd Edition puts **odd columns half a hex
   LOWER**; the printed 3rd Edition map is the **opposite parity**. A shared helper silently
   mis-staggers one of them and everything looks fine until units attack hexes they are not next to.
   Use `hexgraph_2nd_ed.json`; the adjacency is already proved.
2. **Four rules reverse between editions and would break a shared implementation silently** — tagged
   in `rules_2nd_ed.json` as E17, **E21**, E23, E28. The sharp one is **E21: in the 2nd Edition the
   VICTORIOUS player chooses the retreat direction**, where the 3rd lets the owner choose.
3. **The combat phase is a global assignment problem, not a per-action check.** Every adjacent enemy
   must be attacked and every adjacent friendly must participate, and **the printed rules contain no
   relief clause if no complete assignment exists.** A gate validating one attack at a time cannot
   enforce this and will not know it is failing. Matrix cell **C.6**.
4. **The rules sheet contains no retreat procedure at all.** Direction, distance, legality, failure —
   none of it is in the rules columns; it lives only on the map sheet. Working from the rules text
   alone ships a game with no retreat rule.
5. **The map sheet's two halves are asymmetric.** The French half has the Terrain Chart and no retreat
   rules; the Allied half has retreat, disruption and advance and no Terrain Chart. Registered as
   **NAW2-SD-2**. It explains why a human player may sincerely believe a rule does not exist.

---

## 4. WHAT ONLY BRUCE CAN DECIDE — three rulings and one direction call

**Do not encode past these. Do not pick a reading to keep moving.**

| Id | Question | Why it cannot be defaulted |
|---|---|---|
| **NAW2-SD-3** | May a *disrupted* unit be pushed into a Woods/Road hex? The retreat bar says "non-Road Woods"; the disruption bar says bare "woods" | Two printed clauses, two scopes, five hexes. Sharpened by the D4 ruling, which makes those hexes defensively valuable |
| **C.7** | Are the mandatory-attack obligations fixed at phase start, or re-evaluated as results apply? | Results apply immediately, so the adjacency set changes mid-phase. **The two readings give different legal move sets** — this is a ruling, not a coding choice |
| **M.13 / MOV-19** | The printed rules require the **opponent's consent to change a move**. The platform ships UNDO in all five games | Platform-level engine policy. Options: face-to-face courtesy an engine may ignore · UNDO legal in solo/sandbox only · consent prompt in any two-player mode. **Not for whoever wires the UI to settle** |

**And the direction call, which sits ahead of the encoding:** spec #21 routes unresolvable defects to
the game or module creator and blocks playability until an authority resolves them. **For this game
that route does not exist.** SPI is long gone, and not one of the open rulings is a module question —
every one is a defect in the 1971 print. Siege of Jerusalem had Rob to lean on; Napoleon has nobody.
The remaining rungs are official errata (if ever found), proven outcome-equivalence, and **a declared
ruling by Bruce** — the rung he already used for SoJ's R-cells and for D4 this evening. The question
is not whether that rung is legitimate; it is **how much declared-ruling load a game may carry and
still be called playable.** Surfaced in `COVERAGE_MATRIX.md` §6 as `spec_conflict_surfaced`.

---

## 5. THE BITE SEQUENCE

One bite ≈ one context, save + clear between, suite green + commit at each boundary.

1. **Data layer.** `game.json`, `terrain.json`, scenario. Terrain, adjacency, exits and road hexsides
   come straight from `hexgraph_2nd_ed.json`; the roster from `oob_2nd_ed.json`; the CRT from
   `crt_2nd_ed.json`. Every enforced rule carries its `rules_2nd_ed.json` id as its citation (spec #8),
   and `credits` is populated from the printed folio plus the module listings. **No engine logic.**
2. **Movement + ZOC.** Matrix phases P1/P3 and Z. The stop-on-entering-ZOC and cannot-move-if-starting-
   in-ZOC pair, woods entry prohibition, the woods/road hexside restriction, the 11 exit hexes.
3. **Combat arithmetic.** Odds, doubling (defender's hex only — the printed examples prove an attacker
   in a Town gets nothing), rounding toward the defender, clamping, the CRT lookup.
   **Gate: all 27 worked examples must replay green.** `naw_example_check.py` already does this; wire
   it as a validator. This is the same bar SoJ's combat tables had to clear.
4. **The assignment problem** (C.6/C.7). Needs the §4 ruling first. Expect this to be the hardest bite
   in the game and design it as a phase-level constraint check, not a per-action predicate.
5. **Result application.** Retreat (victor chooses), DISRUPTION with its narrow failure trigger, the
   advance option and its prohibition on attacking again that phase, EX losses.
6. **Reinforcement, victory, demoralization.** One reinforcement event, turn 2, East edge, non-delayable.
   Two 40-point ledgers on one shared track.
7. **Matrix closure + validators.** Every cell ENFORCED or UNREACHABLE-with-evidence. Nothing umpired.

---

## 6. DEFINITION OF DONE

Per the 2026-08-09 spec amendment, playability is binary and strict: **every one of the 111 cells is
either ENFORCED or UNREACHABLE with evidence recorded.** No cell may be closed by assertion — three
cells in the current matrix that *could* have been claimed unreachable were deliberately left open
with the argument written down, because an argument is not an encoding and a validator must assert it.
Nothing is human-umpired; per Bruce 2026-08-08 an umpired action is an engine failure point, not a
disclosure.

---

## 7. THE 3rd EDITION MOVED TONIGHT

The standing blocker was that defence doubling and artillery line-of-sight blocking appear nowhere in
the printed 1979 rules text and could only live on that edition's terrain chart, which we did not
hold. **On 2026-08-14 a scan of the printed 1979 map sheet was obtained** (`C:\VassalNaW\sources_1979\`,
Bruce-authorised download) carrying the Terrain Key, both Combat Results Tables, the Game-Turn Record
Track, printed four-digit hex numbers, nine exit arrows and the at-start unit pictures. Both blocking
questions are answered on it, the second with the game's own worked example.

It also **independently corroborates Bruce's D4 ruling**: the 1979 key groups **Building and
Woods-Road in one row with "Defender in hex is doubled"** — structurally identical to the 1971 chart's
"Towns & Woods/Roads". The 1971 grouping was not a typesetting slip.

**This is a lead, not yet an authority.** It is a fan re-host, and the authority ladder's whole point
is that a genuine scan and a good redraw look identical until examined. The physical evidence is
strong (page curl, binding shadow, per-page dimension drift, no text layer) but it must be tiered
against the ladder and read in full before anything is cited from it. **That is its own bite, and it
does not touch the 2nd Edition.**
