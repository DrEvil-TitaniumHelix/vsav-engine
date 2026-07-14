# War Journal — General Opus (Confederate), Fable-vs-Opus match

Chickamauga — The Last Victory (campaign, 15 GTs). Confederate command.
Private strategic narrative. Lives in `outbox\` only (anti-cheat: my mailbox
is my sole match record; confidential from Fable until game end).

Per turn I record: the read, the decision + why, what I expect Fable to do,
and my win estimate with the reasoning behind the number so I can check my
own calibration later.

---

## Standing strategic framework (the whole game)

The VP schedule dictates everything. Ranked by swing available to me:

1. **The exits (0101/0111) pay Confederate 10 VP per strength point** (Union
   gets 1). This is the game's dominant term — but only if my LOC road trace
   west→east is clear of Union units at game end [17.31]. Late-game prize.
2. **[17.32] cutoff is the real kill-switch.** Any Union unit that can't trace
   a 10-hex road path to 0101/0111 at game end counts as *destroyed, credited
   to me*. The champion won its self-play test (51-27) mostly on this — ~41
   Union CSP cut off at the buzzer by blocking geometry. My eastern mass is a
   wall that traps Union units that come east to contest my hexes.
3. **Take & hold 0211 + 0502 (McFarland's / Rossville Gap) = +40.** Far NW,
   behind the Union body. Main offensive prize.
4. **Hold 2311 (deny 20) + 1920 (deny 10) = 30 VP swing.** I start holding both.
   2311 is creek-walled at Dyer's Bridge — cheap to hold. 1920 is central,
   contestable — needs real depth.
5. **Union train (arrives GT7) = +10 to me if it never exits.** Deny/capture.
6. **Three 5-VP hexes (0822/1108/1115)** — start Union-held, flip to last side
   through them. Opportunistic.
7. **Attrition = 1 VP/CSP**, symmetric. Slow; don't trade for its own sake.

Reinforcements: I get ~41 str GT2 at south-central (16,27)/(19,28); Union gets
~55 str GT2 at south-west (7,28)/(10,27), then XX Corps (~43) GT5, cav GT6,
train GT7. Both columns throttle through 2 entry hexes — nobody fully arrives
in 15 turns.

**The opponent.** Fable is a reasoning LLM, NOT the shipped policy AI and NOT
the champion. It WILL react to me — so the champion-advisor exploits that rely
on enemy-blindness (feints, decoys, odds-poisoning empty hexes) are worth less
against Fable than they were in self-play. My edge over the pure champion is
the thing the champion lacks: I can read Fable's moves and re-weight. My job is
to keep the champion's proven endgame geometry while adding live reaction.

---

## GT1 — deployment (VP 0-0)

**Read.** Quiet turn, both armies just deployed. I'm massed center-east along
the creek; Union body (XIV Corps, Wilder) sits center-west, cols 8-15; weak
Union detachments hold the far-NW gaps (112/113) and north (114); one lone
Union cav (109) is the only thing near my NE.

**Decision: MODIFY the advisor.** Its geometry is sound but it's enemy-blind —
it marched ~50 strength into the creek-walled NE corner to over-garrison 2311
against a single cav that would have to cross Dyer's Bridge (defender doubled)
to reach it. Textbook fixed-ratio garrisoning ignoring terrain and threat. I:
- screened 2311 with 3 fast cavalry (143/144/146) — creek-anchored, ample;
- kept a 6-unit denial strongpoint on 1920 (133/136/131/127/141/142);
- redirected the freed heavy infantry to the decisive center-west axis —
  14 units (~55 str) pushing the 5-VP hex 1115 into the Union XIV Corps,
  timed to link with my GT2 reinforcements;
- kept the champion's southern thrust: Gracie's column (str 21) on 0211,
  a second (118/119/120) on 0822;
- gun on standoff.

Fixed the economy-of-force error; kept everything else the champion had right.
GT1 is pure deployment with no enemy move to react to, so I diverged minimally.

**What I expect Fable to do.** As Union it wants to: retake 1920/2311 (30 VP),
hold the gaps (40 VP), avoid the 17.32 cutoff (likely withhold or hug the exit
roads), and contest the 5-VP hexes. Most likely GT1-2: consolidate the center,
feed GT2 reinforcements in, and NOT over-commit east early. I'm watching for
whether it defends the west passively (then I grind the gaps) or lunges at my
denial hexes (then I trap it east of the exit roads).

**Win estimate: 65% (medium confidence).** Confederate is the structurally
favored side (exit asymmetry, the cutoff kill-switch, a proven advisor), and
that side won its reasoning-LLM test 51-27. I discount from ~80% because Fable
is a competent reactive opponent who can play the withhold/cutoff-avoidance
defense, and 14 turns is a long time for the position to swing. GT1 changed
nothing material — no fight — so I hold the number.

**Admin note.** Judge amended COMMANDER.md mid-GT1: every plan now carries
`confidence` and `win_percent` top-level fields, tracked for calibration.
Re-filed GT1 with them.

---

## GT2 — Fable shows its hand: turtle west (VP 0-0)

**Read — and it's the big one.** Fable moved its ENTIRE army west/NW and
conceded the east outright. 106 garrisons 0211 (20 VP), 112/113 hold 0502
(20 VP), the XXI cluster (108/110/111) + Wilder hold 0822, 104/105/114 hold
1108, and 101/102/103 pulled back to 0412/0513 covering the exit-road
approaches and McFarland's Gap. One lone cav (109 at 1311) is the only Union
unit east of column 13. This is exactly the withhold/cutoff-avoidance defense
I flagged GT1: defend the 40 VP of western gaps, sit on the exit roads so
17.32 can't catch its army, bank the three 5-VP hexes. Its GT2 reinforcement
wave throttled hard — only 2 of 12 due units entered (0728/1027). My GT1 push
landed my center mass at cols 14-20 and Gracie's column into the south-center.

**The VP reality this exposes.** Occupation "denial" doesn't score FOR me —
holding 1920/2311 only keeps Union at 0 there (worth preventing 30, not
gaining it). Frozen to GT15, Union wins ~15-10 on the three 5-VP hexes alone.
To WIN I must change the board: flip the 5-VP belt (0822/1108/1115 = 30-pt
swing), take a gap, capture/deny the train (+10), and above all keep alive the
exit trump — 10 VP per CSP exited dwarfs everything, but Fable is sitting on
the 0101/0111 roads precisely to deny it.

**Decision: MODIFY — mass west, hold east on a shoestring.** Since Fable
abandoned the east, 2311 (creek-walled) and 1920 face zero threat; I hold them
with 2 cav + 4 units respectively and pour everything else into three
coordinated thrusts against Fable's forward 5-VP belt, where I have clear local
superiority: northern (~41 str) on the 1108 cluster, center (~34 str) to seize
the *empty* 5-VP hex 1115 and press toward 0502, southern (Gracie + column,
~26 str) on 0822 — which also develops pressure on the Union entry/train
corridor at 0728/1027. Not expecting to carry 1108 this turn (may be
defender-doubled); GT2 closes the distance, GT3 assaults concentrated with my
41-str reinforcements up. The champion again piled ~11 units on 2311; I keep
its western objectives but redirect that dead-corner pile into the assault.

**What I expect Fable to do.** Hold the western line, feed its trickle of
reinforcements into the 0822/1108 sector, retreat 109 cav rather than lose it,
and keep refusing battle on the deep gaps behind doubled terrain. Watch for:
does it stand and fight for the 5-VP belt (then I grind it down with
superiority) or trade space and fall back onto 0211/0502 + the exit roads
(then the game becomes a siege of the NW and the exit/train subplot decides
it). Either way the east stays mine, uncontested.

**Win estimate: 65% (medium, held).** Slightly reassuring that Fable's total
commitment west makes my 30-VP eastern denial permanently secure, and I have
material + reinforcement superiority in the decisive zone. Tempered because a
correctly-played western fortress + exit-road screen is hard, and the raw
occupation math currently favors Union until I actually flip the 5-VP belt. The
number rides on execution over the next 3-4 turns.

---

## GT3 — first hex flipped; closing to contact (VP 0-0)

**Read.** GT2's push paid: **1115 is now mine** (Smith/Wright on it) — first of
the 5-VP belt flipped, occupation now Union 10 (0822+1108) vs me 5. Gracie's
column drove all the way to 0824, one bound under the 0822 cluster. Fable stayed
totally passive: it reinforced McFarland's Gap (0211 now 101+106 = 10 str),
pulled 102/103 back to 0309 covering the exits, and otherwise just sits on its
western hexes. Zero Union presence east of column 11. Reinforcement throttle
continues — only 2 of its wave entered; only 2 of mine (173/174) did too.

**Decision: MODIFY — press two concentrated assaults, hold east on a shoestring.**
East is a non-issue (nothing within a dozen hexes of 2311/1920), so 2 cav + 3
units hold both denial hexes and everything else goes west. Southern column
(~26 str) closes on 0822; center mass (~55 str) advances north on the 1108
cluster; 1115 anchored to bank the 5 VP; 173/174 up the center; the 175-181
arrivals will flow toward 0822 under standing doctrine and weight the harder
southern fight (Wilder-8 is the anchor there). Still maneuver-to-contact through
forest — the real assaults are GT4-5 once fully massed. Then the plan is to
punch through 1108, wheel the center WEST onto McFarland's Gap (0211), and open
the 0111 exit: that single breakthrough pays the 20-VP gap AND unlocks the
10-per-CSP exit trump, which is the game's highest ceiling.

**What I expect Fable to do.** More of the same — stand on the western hexes,
feed its trickle of reinforcements into 0822/1108, refuse open battle. The
question is whether it fights for the 5-VP belt (I grind it with superiority) or
falls back onto 0211/0502 + the exit roads and makes me besiege the NW. I'm
also now watching the SW entry/train corridor (0726/1027): my southern mass
developing there threatens to choke its reinforcements and set up the +10 train
denial.

**Win estimate: 67% (medium, +2).** Nudged up on concrete progress and an
overwhelming, growing material edge with no Union counter-threat. Held back from
higher because Fable's passivity is *correct* fortress play, not error — the
doubled-terrain gaps and exit screen are the hard part, and I still have to win
the actual fights (no combat resolved yet; variance ahead).

---

## GT4 — at contact; terrain recon changes the picture (VP 0-0)

**Read.** My army reached Fable's line. The big discovery: I pulled the terrain
data and **every VP hex I want — 1108, 0822, 0211, 0502 — is CLEAR, defenders
undoubled.** Only Wilder's 0922 (rough) and 109's 1009 (forest-rough) double,
and I can avoid attacking into those. That means my numerical edge converts
straight into 2-1/3-1 odds against the actual objectives — the fortress is far
less solid than "dug-in terrain" made it look. Fable still passive: pulled 109
cav back to 1009, kept every cluster in place, and is stacking reinforcements
(147/148/149) in the SW behind Wilder. Positionally my southern column is one
hex short of 0822 (a row-23 gap); my center is ~1 turn from massing on 1108;
Scott's cavalry has worked around NORTH of the 1108 pocket (1206).

**Decision: MODIFY — open the assault.** Southern column (~26 str) closes and
hits 0822 (9 on clear) at ~2-1 to flip the 5-VP hex and peel Fable's SW cluster
apart. Center mass (~55 str) concentrates on the isolated 1108 seam (14 str)
for a decisive GT5 blow, Scott poised to block its northern retreat so a
defender-retreat result becomes elimination (surround-and-destroy, the system's
core weapon). Strategic aim crystallized: **1108 is the seam between Fable's SW
(0722/0822/0922 + reinforcements) and NW (0211/0311/0502) concentrations** —
punch through it, split the army, then exploit NW toward 0502 and the
0111/0101 exits (10 VP/CSP, the trump). East minimal, reinforcements to center.

**What I expect Fable to do.** If I take 0822, watch whether Wilder+147/148/149
counterattack to retake it (SW is its strongest concentration and its
reinforcement inflow) or whether it keeps turtling. On the center, it may feed
109 cav / shuffle 104/105/114 to delay the 1108 break. Its correct move would
be to start pulling back toward a tighter NW perimeter on the gaps+exits before
I split the seam — if it does, the game becomes a NW siege; if it stands
forward, I split and envelop.

**Win estimate: 68% (medium, +1).** Up on the terrain intel (undoubled
objectives) and reaching contact with overwhelming numbers. Only +1 because
this is the first turn steel actually meets steel — 0822 at 2-1 next to a
doubled Wilder-8 has genuine CRT variance, and I want to see combat results
land before trusting the trajectory.

**Procedure note.** COMMANDER.md upgraded to AUTONOMOUS turns: judge signals
via `inbox\YOUR_TURN.txt`; between turns I arm a PowerShell wait loop as a
BACKGROUND command whose completion re-invokes me. Every reply now ends with an
armed wait; if ever awake unarmed with no signal, re-arm. (Keyed the wait to
fire only when the signal is NEWER than my last-filed plan, so the stale
current-turn signal doesn't false-wake me.)

---

## GT5 — Fable withdraws; I take the center, aim at the NW (VP 0-0)

**Read — Fable is reacting.** Two things happened to my GT4 orders: (1) the
southern push on 0822 was REFUSED by odds-safety — advancing would have forced a
three-way fight against 0822 + doubled Wilder + 111, worse than 1-1, so the
column held one hex short. (2) Fable pulled its 1108 center garrison back onto
FOREST at 1006/1007 (doubled) rather than let me crush it — a fighting
withdrawal into a tighter NW perimeter on the gaps/exits. 1108 is now empty and
mine for the taking. Still 0-0.

**Terrain recon drives the plan.** The retreated group sits doubled (1006/1007 =
forest) — not worth battering. But 1108, both 20-VP gaps (0211/0502), and BOTH
exits (0101/0111) are clear/undoubled. So: grab 1108 free (+5, occupation goes
me-10 / Union-5), screen the forest group, and drive the main mass (~18 units)
NW up the Rossville Road at Rossville Gap and the exits. Southern column + 2
reinforcements press 0822 from the clean southern angle (0723/0821, avoiding
Wilder's 0922); if refused again they pin the SW while my reinforcement flood
(177-185, incl. cavalry) builds an overwhelming force.

**The tactical lesson I'm now designing around:** against Fable's tight clusters,
"push" won't commit my troops to a multi-hex fight below 1-1 — good discipline,
but it means I must either (a) mass enough that even the spread fight is
favorable, or (b) attack a hex from an angle touching only ONE defender. The SW
is a cluster (hard); the NW gaps are isolated on clear terrain (soft once I
arrive). That's why the Schwerpunkt is the NW, not the SW 5-pointer.

**What I expect Fable to do.** Keep contracting the NW perimeter, hold the forest
shoulder (1006/1007) and the gaps, funnel XX-Corps reinforcements into the SW
behind Wilder. Its best play is to trade space for a compact fortress on the
gaps+exits and dare me to crack undoubled hexes under time pressure. If it keeps
refusing battle, I keep taking ground and close on the exits — where its
army-hugging-the-roads posture collides with my need to physically occupy them.

**Win estimate: 70% (medium, +2).** Up because Fable ceded the center and 1108
without a fight and my numbers are becoming decisive as reinforcements pour in;
the decisive gaps/exits are undoubled. Still capped at 70 — nothing is banked
(0-0), the forest perimeter is genuine, and I need to convert maneuver into
actual captured hexes and, ideally, the exit trump. Watching GT6-8 to see if I
crack the NW before night (GT9) resets the tempo.

---

## GT6 — envelopment of the NW seam (VP 0-0)

**Read.** My NW drive punched into the SEAM between Fable's two concentrations:
141/142 at 0612, 173 at 0719, 131 at 0914, cav at 1103, the mass at 1103-1510.
Fable pulled its center reserve further back to 0704/0805 (clear) — it keeps
trading space, contracting into the NW corner (~49 str across 0211/0311/0502/
0704/0805). SW cluster still parked (Wilder + 108/110/111 + reinforcements,
~35). My southern column's 0822 push was refused a THIRD time (Wilder's
doubling makes the three-way sub-1-1) — but 111 vacated 0722, so the west edge
is now open for me to flank around. My 1108 grab overshot to 1207; 1108 still
empty/Union-credited, but 115/116 sit adjacent at 1109 and take it clean now.
Big reinforcement wave (178-185, four cavalry) arriving. Still 0-0.

**Terrain recon = green light.** Fable's NW is almost entirely CLEAR/undoubled:
the 0704/0805 reserve, both gaps (0211/0502), 0311/0312 - only the mountain
approaches (0511/0512/0611/0210) are rough. So my ~110 str converging on the
NW crushes its ~49 at strong odds; the only doubled defender left is Wilder in
the SW, which I'm now bypassing rather than assaulting.

**Decision: MODIFY — grab 1108, two convergent thrusts.** (1) Wood/Polk take the
empty 1108 (+5; occupation flips to me 10 / Union 5 — I take the lead). (2)
Center mass onto the 0704 reserve (clear) — the seam-plug and nearest big
target; break it and the NW opens. (3) West wing (141/142/173/131) + the
freed-up southern column swing up the now-open west edge onto McFarland's Gap
(0211). **0211 is the key: 20 VP AND the adjacent 0111 exit** — and my
west-to-east LOC is already clear of Union units, so exiting for 10-per-CSP is
live the moment I hold it. Gap assaults land GT7-8, before night GT9.

**What I expect Fable to do.** It's nearly out of room to retreat. Either it
stands in the NW corner and I grind it at 2-1+ on clear terrain (and start
cutting units off from the exit roads — 17.32), or it makes a desperate sortie.
Its SW cluster is now a detached 35-str island I'm flanking north of; if it
doesn't march that force to the NW soon, it risks being cut off entirely.

**Win estimate: 72% (medium, +2).** The envelopment is real, terrain favors
every assault, and my material edge is now overwhelming and still growing. Held
at 72 only because I haven't banked a single VP or won a fight yet — the next
two turns must convert maneuver into captured gaps and, ideally, the first
exits. If GT7 cracks a gap, this jumps.

---

## GT7 - 1108 flipped; Fable cornered (VP 0-0, occupation me 10 / Union 5)

**Read.** 1108 is mine (Wood/Polk on it) - I now hold 1108+1115, leading
occupation 10-5 (scores at GT15). My army has flooded the NW: 173 deep at 0215,
141/142 at 0511, cav at 0903, north mass at rows 02-11, southern column flanked
up to 0523/0622 west of the SW cluster. Fable retreated its reserve again
(0604/0704) - but it is now BACKED INTO THE CORNER (0211 / 0502 / 0311-0312 /
the reserve), edge at its back, no more room to trade space. SW cluster (Wilder
+ 108/110/111 + 147/148/149, ~30 str) still parked in the SW, and I'm now north
AND west of it. Reinforcement wave 178-185 (incl. 4 cavalry) arriving. Still 0-0
(no kills yet - three turns of pushes were refused/bloodless because Fable kept
slipping out of contact).

**Why this turn should finally bite.** The pushes got refused before for two
reasons: odds-safety on cluster-spread, and Fable retreating out of reach. Both
now break my way - Fable is cornered (can't retreat) and its positions are
clear/undoubled, so a push into contact yields a real 2-1+ fight I win.

**Decision: MODIFY - two convergent gap assaults.** North mass (~50 str) crushes
the 0604/0704 reserve (clear, 19) and drives Rossville Gap (0502, 20 VP). West
spearhead (173/141/142/131) + the northbound southern column converge on
McFarland's Gap (0211, 20 VP) - the exit key: holding it frees the adjacent 0111
exit, and my west-east LOC is already clear, so 10-per-CSP exits go live.
Leaving Wilder's SW cluster bottled south of my line is deliberate - it sets up
a 17.32 cutoff worth up to +30 at game end (the champion's own kill mechanism,
turned on Fable).

**What I expect Fable to do.** Nearly trapped. Best case for it: pack the two
gaps hard and pray the clock (GT15) runs out before I dig it out and exit. Worst
case: I crack a gap GT7-8, pour through the exit GT10+, and/or its SW island
scores as destroyed.

**Win estimate: 73% (medium, +1).** Only +1 despite the dominant position
because the ledger is still 0-0 - I refuse to over-credit a maneuver advantage I
haven't cashed. The moment GT7/GT8 banks a gap or a kill-stack, this jumps
toward the high 70s/80s. Genuine risk: the clock - if Fable turtles perfectly
into a corner fortress, digging out 40 VP of gaps + exiting in the remaining
turns is the real test.

---

## GT8 - I diagnose my own stalled offensive (VP 0-0, occ. me 10 / Union 5)

**The key realization.** Eight turns, still 0-0, armies in contact - because of
MY verb choice, not Fable's defense. 'push' advances toward the objective but
(by rule) refuses to end adjacent to an enemy it can't fight >=1-1, so my units
have been threading AROUND Fable's gap garrisons to the target hexes instead of
assaulting them. That's why every turn was 'a quiet turn, no fight.' The champion
uses 'hold at <hex>' for its gap units - that idiom drives to contact and forces
the mandatory combat. My units are finally at contact range with Fable pinned
against the map edge, so this turn I switch mechanics and force the fight.

**Position.** My army has completely enveloped Fable's NW corner: 173 at 0213,
141/142 at 0511, cav at 0701 (top edge), southern column up at 0322/0417, north
mass across rows 01-06. Fable holds both gaps (0211, 0502), the 0311/0312 screen,
and its reserve (0603/0604) - all clear/undoubled - plus the bottled SW cluster
(~30). I hold 1108+1115 (occupation lead 10-5). Reinforcements still flowing.

**Decision: MODIFY - three concentrated assaults, last combat turn before night.**
Rossville Gap 0502 (~27 vs 10), the 0604 reserve (~29 vs 19), McFarland's Gap
0211 (~46 vs the 20-str shoulder). 3-1-ish everywhere; I accept Ex losses given
my numbers. Taking the gaps banks 40 VP and frees the 0111 exit for the
10-per-CSP windfall from GT10. GT9 (night, no combat) = reposition toward the
exits; GT10-15 = exit en masse + hold gaps + keep the SW cluster cut off (17.32).

**What I expect Fable to do.** Its cornered garrisons have almost no retreat room
(edge at their backs), so forced assaults may ELIMINATE rather than just push
them - kills on top of hexes. If it had a sortie, this is when it comes; I don't
think it has the force.

**Win estimate: 74% (medium, +1).** Deliberately restrained: the board screams
higher, but I predicted 'it bites' on GT7 and it didn't (0-0 again). I will not
re-rate up until steel actually resolves. If GT8 banks a gap or a kill-stack, GT9
jumps to the low 80s. The correction (hold-at, not push) is the crux - if it
works, the dam breaks; if 'hold at <occupied hex>' is somehow rejected, I lose
the last pre-night combat turn and fix it on the resubmit.

---

## GT9 (NIGHT) - hard truths and a recalibration (VP 0-0, occ. me 10 / Union 5)

**Two things clarified, both sobering.** (1) The gap assaults keep fizzling for a
STRUCTURAL reason, not bad luck: I finally extracted the true hex adjacency from
the map data - 0211's only non-enemy neighbors are 0111/0112 (clear) and
0210/0212 (forest-rough), ALL inside its ZOC. The gap is a chokepoint: the rough
approaches throttle how many units reach contact, so my numerical edge does not
convert. Same at 0502 (0501/0503 rough). That is why 4 straight turns of assaults
produced nothing. (2) I re-did the VP math: I am ALREADY WINNING - occupation me
10 (1108+1115) vs Union 5 (0822), plus a probable +10 if the Union train never
exits (still hasn't entered by GT9). BUT the margin is thin: if Fable retakes
1108+1115 it flips to a Union win. Fable has read this - it's driving Wilder's
cluster (~21 str) EAST from 1022 at my 5-VP hexes. Its passivity is over.

**Decision: OVERRIDE - night reposition + rebalance.** Night = no combat, no
entering EZOC. Stage the western mass tight on 0211 to strike it concentrated
GT10 (all four open neighbors at once); keep a northern group fixing 0502/the
reserve; and REINFORCE THE CENTER - Deshler+Anderson6 onto 1115 (~18 str), the
rest of the wave covering 1108 - so Fable's counterstrike can't crack my winning
margin. New priorities GT10-15: (a) HOLD 1108/1115/1920/2311 = the game; (b) grab
now-lightly-held 0822 (Wilder left it) for a safer +10 swing; (c) crack 0211 for
the 20 VP + 0111-exit blowout if the chokepoint allows.

**Honest self-assessment.** I twice predicted assaults would land and they didn't
- I over-weighted numbers, under-weighted chokepoint terrain and the
odds-safety/mandatory-combat mechanics. This is a grinding, thin, PROBABLE win
off material dominance + occupation lead, not the blowout I was narrating at
GT6-8. My job now is to not lose it.

**Win estimate: 70% (medium, -4).** Recalibrating DOWN despite a dominant board:
the gaps may never fall (terrain), my occupation margin is thin, and Fable is now
attacking it. Still favored - ~150 str vs ~90 and I hold the lead, so defending
through GT15 is achievable - but pricing in the higher variance of a thin-margin
defensive game. If I secure 0822 or crack a gap, this climbs back toward the high
70s.

---

## GT10 - defend-first; targeting the empty neighbor to force combat (VP 0-0)

**Read.** Post-night, still 0-0. Wilder group (~16 str) at 1019/1020 closing on
my center 5-VP hexes; rest of Fable frozen in the NW gaps (0 value to Union but
they must deny me). My reinforcement wave (178/179/180 + arriving 181-186) is
converging from the south-center - well placed to defend 1115/1108.

**Decision: MODIFY, defend-first.** (1) Lock the center: pile 178/179/180 onto
1115 with Smith/Wright, keep 1108 held - Wilder breaks on a wall. (2) Force
combat at last: instead of stalling on the occupied gap, target the empty clear
neighbor 0602 to drive the northern group (~55 str) into contact with 0502 +
the 0603/0604 reserve (0502 has 4 clear neighbors vs 0211 single forest
chokepoint). (3) Western mass pins 0211. (4) Artillery bombards; east held.

**Why defend-first.** I keep failing to convert offense (4 turns, chokepoint
terrain + odds-safety). But I am WINNING on the board, and Fable only mobile
threat is one group my reinforcements outnumber. So the disciplined line is:
hold the 10-5(+train) lead, take 0502/0822 as insurance if combat finally works.

**Win estimate: 71% (medium, +1).** Nudged up a hair: the center is now being
reinforced faster than Wilder can arrive, so the main downside risk (losing a
5-hex) is shrinking. Still capped - offense unproven, margin thin. A confirmed
0502 capture or a clean center hold for 2 turns pushes this to high 70s.

---

## GT11 - the NW is uncrackable; pivot to pure defense (VP 0-0)

**The verdict, after 11 turns at 0-0.** Combat will not fire in the NW, for a
structural reason I finally proved with the adjacency + terrain data: the gaps,
their screen (0311/0312), and the reserve (0603/0604) are mutually supporting,
so every hex from which I could mass onto one is simultaneously adjacent to a
second Union stack. That dilutes every attack below the engine odds-safety
commit threshold, so my units never close. 0604 is also forest-rough (doubled).
My repeated hold-at/push orders were never going to work here. Lesson logged:
against a mutually-supporting cluster on rough terrain, numerical superiority
alone does not convert - you need an isolated stack to attack, and Fable never
gave me one.

**But I am winning.** Occupation me 10 (1108+1115) / Union 5 (0822), plus a
probable +10 (Union train still hasn
---

## GT11 - the NW is uncrackable; pivot to pure defense (VP 0-0)

**The verdict, after 11 turns at 0-0.** Combat will not fire in the NW, for a
structural reason I finally proved with the adjacency + terrain data: the gaps,
their screen (0311/0312), and the reserve (0603/0604) are mutually supporting,
so every hex from which I could mass onto one is simultaneously adjacent to a
second Union stack. That dilutes every attack below the engine's odds-safety
commit threshold, so my units never close. 0604 is also forest-rough (doubled).
Lesson logged: against a mutually-supporting cluster on rough terrain, numerical
superiority alone does not convert - you need an isolated stack to attack, and
Fable never gave me one by keeping its line intact.

**But I am winning.** Occupation me 10 (1108+1115) / Union 5 (0822), plus a
probable +10 (Union train still hasn't entered by GT11). Hold my four hexes to
GT15 and I win, ~20-5. The game has reduced to ONE question: can I hold 1115
against Wilder's group (~16 str, now at 1017)?

**Decision: OVERRIDE - pure defense.** Reinforce 1115 to ~14+ (Deas/Anderson6/
Manigault converging) so Wilder's odds fall below the same threshold that has
protected Fable all game; keep 1108/1920/2311 held; leave the NW army forward as
a PIN on Fable's 48-str garrison (they can't leave without ceding 40 VP of gaps
to me); free swing at the clear reserve stack 0603 in case odds trigger. Incoming
cavalry backs the center.

**What I expect Fable to do.** Press Wilder at 1115; maybe probe 1108. It cannot
reach 1920/2311. If its own odds-safety mirrors mine, a 14-str 1115 is simply
un-attackable and the game is effectively decided in my favor.

**Win estimate: 72% (medium, +1).** The win condition is now clean and I have the
material to hold it. Capped because the center race has real stakes: if 1115
falls before my reinforcements consolidate, occupation goes me 5 / Union 10 and
the game hangs on the uncertain train. Holding 1115 two turns pushes this to ~80.

---

## GT12 - threat recedes; consolidate the win (VP 0-0)

**Read.** Wilder's group pulled BACK west (1017 -> 0915) rather than charging
1115 - so the center threat receded and all four of my scoring hexes are safe
this turn. Fable is packing a big western/SW blob but nothing of mine is within
reach of it. My reinforcements (Deas/Manigault at 1121/1122, Anderson6 1417,
Crews cav) are converging on 1115.

**Position is a won game if I hold.** Occupation me 10 (1108+1115) / Union 5
(0822), plus a probable +10 (Union train STILL not on board at GT12). Three
turns left. To lose I'd have to give up TWO hexes (or one + the train), and
Fable has no path to reach two of my deep hexes through my consolidating
defense in three turns.

**Decision: MODIFY - hold, no gambles.** Turn 1115 into a fortress (~20+ str),
keep 1108/1920/2311 held, keep the NW army forward pinning Fable's 48-str gap
garrison. There is no extra VP reachable for me (exits ZOC-blocked, 0822 now
heavily held), so protecting the lead is the whole game.

**Win estimate: 76% (medium, +4).** Up meaningfully: the one live threat
(Wilder) retreated, every scoring hex is safe, and 1115 is being fortified
beyond assault range. Not higher only because this game has surprised me
repeatedly (combat mechanics, chokepoints) - I'll bank the number when GT15
actually scores. A clean hold next turn takes this to ~82.

---

## GT13 - fortress holds; running the clock (VP 0-0)

**Read.** Quiet again. Wilder's blob stays parked in the SW (0915); nearest
Union units (151/147 at 1017/1019) are ~3 hexes from 1115, which is now
hardening (Smith/Wright on-hex, Anderson6 adjacent at 1116, Deas/Manigault + cav
converging to ~26 str). All four scoring hexes safe. Lead intact: me 10 / Union
5 + probable +10 train (train STILL never entered by GT13).

**Decision: MODIFY - hold, run the clock.** Finish fortifying 1115 beyond
assault range, keep 1108/1920/2311 held, keep the NW army forward (pins Fable's
48-str gap garrison AND sits across the roads its SW blob would need to trace to
the exits - a possible 17.32 cutoff bonus at game end; noted, not banked). No
reachable VP for me to chase.

**Late realization worth noting.** Fable's SW blob may be near/over the 10-hex
leash to the exit roads. If my NW screen severs that trace, a chunk of Union
strength scores as destroyed at GT15 (17.32) - which would turn a thin 10-5 win
into a comfortable one. I can't adjudicate the exact road distances, so I keep
it as upside, not a plan.

**Win estimate: 79% (medium, +3).** Two turns left, every hex safe, 1115
un-assaultable. Fable cannot reach and crack two deep hexes through this
defense. Not banking 100% only for an unseen rules interaction or the small
chance the train appears and exits AND I lose a hex. A clean GT14 makes GT15 a
formality.

---

## GT14 - FIRST BLOOD: 103 eliminated, VP me 5 / Union 0

**The dam cracked.** My western pin group caught 103 (str 5) isolated and
killed it - the game's first combat result after 13 dry turns. Proof that the
engine DOES fire combat when I concentrate on a stack without mutual support.
The kill also emptied 0312, partially un-blocking McFarland's Gap.

**Position is now a secured win.** Banked: me 5 / Union 0 on eliminations. Add
occupation at GT15 (me 10 = 1108+1115 / Union 5 = 0822) and a probable +10
(train never entered) -> floor ~15-5, ceiling higher. Two turns left.

**Decision: MODIFY - ironclad the four hexes, take 0211 as free upside.** 1115
is a ~26-str fortress; 1108/1920/2311 held. Since it can't weaken those, I throw
the western group at the now-isolated McFarland's complex: 0311 (5 str, ~3.5-1)
and 0211 (10 str, ~2.5-1). Taking 0211 = +20 occupation and a lock. Northern
group keeps pinning the reserve/0502.

**Lesson, now proven twice over.** The whole midgame stall wasn't a verb bug -
it was that Fable never left me an isolated stack to hit at clean odds. The
moment its line frayed (103 exposed after 0312 emptied), combat resolved
instantly. Concentration converts ONLY against an unsupported target.

**Win estimate: 84% (medium, +5).** A banked elimination lead + secure
occupation + low-risk 0211 upside. Not calling it higher only for the residual
unknown of how the judge scores edge cases (train, any 17.32 cutoff) - but I no
longer see a realistic path for Fable to win. GT15 should confirm.

---

## GT15 (FINAL) - closing out the win (VP me 5 / Union 0)

**Read.** GT14's 0211 assault fizzled (still 0211+0311+reserve mutually
supporting - the same wall). Doesn't matter. As second player I have the last
move and Fable cannot respond. I lead every scored category:
- eliminations 5-0 (Union 103 killed GT13)
- occupation at scoring: me 10 (1108+1115) / Union 5 (0822)
- train: never entered all game -> +10 me
- projected ~25-5.

None of my four scoring hexes is adjacent to a Union unit, so they cannot be
dislodged in my own combat phase. I hold every garrison, throw the western group
at McFarland's once more as zero-risk upside, and keep the northern group
forward (pinning + possible 17.32 cutoff of Fable's SW blob at scoring).

**Retrospective (win in hand).** The through-line: Confederate is the
structurally favored side, and I converted the occupation + elimination edge
into a clear win - but NOT the blowout I kept forecasting midgame. Two honest
errors I logged and corrected: (1) over-crediting numerical superiority against a
mutually-supporting line on chokepoint terrain - combat only ever fired when
Fable exposed an isolated stack (103); (2) briefly leaving my winning margin thin
before pivoting to defend it. Calibration arc: 65 -> 67 -> 70 -> 74, a correction
DOWN to 68/70 when I saw the gaps were uncrackable and the margin thin, then back
up 72 -> 76 -> 79 -> 84 -> 92 as the defense held and I banked the kill. The
down-correction at GT9-11 was the most important call of the game: I stopped
chasing an unwinnable assault and secured the win I already held.

**Final estimate: 92% (high).** Every scored category mine, hexes unassailable,
opponent out of moves. Only a scoring-interpretation surprise could dent it, and
the floor is still a clear Confederate win. Awaiting GAME_OVER.

---

## GAME OVER - Confederate 54, Union 5 (verified 581/581)

**Won - and by more than I knew.** Final breakdown: eliminations 5 + occupation
10 (1108/1115) + train-fail 10 + **17.32 cutoff 29 (seven Union units severed
from an exit-connected road at game end)**. Union 5 (0822).

**The lesson I get to keep.** The 29-point cutoff is the exact bonus I logged at
GT13/GT15 as "possible, can't adjudicate, not banked." It was real. Keeping the
NW and northern groups forward - which felt like idle pinning once I'd conceded
the gaps were uncrackable - was in fact executing the champion's core kill
geometry: my line sat astride the roads Fable's SW blob needed to trace west, and
at scoring a third of its army evaporated. I under-credited my own position
because I was fixated on the gaps I COULDN'T take and blind to the cutoff I WAS
building passively. Calibration humility: my 92/"~25-5" was 29 points low.

**What actually decided it, ranked:**
1. Economy-of-force correction of the advisor's dead-corner over-garrison, every
   single turn - it freed the mass that enveloped the NW and formed the cutoff wall.
2. The GT9 occupation-ledger realization - flipping from would-be conqueror to
   lead-protector - which stopped me throwing the game away on unwinnable assaults.
3. The passive cutoff geometry, which I built almost by accident and nearly
   talked myself out of valuing.

**Calibration arc:** 65 -> 67 -> 70 -> 74, honest correction DOWN to 68/70/71 at
GT9-11 (gaps uncrackable, margin thin), then 72 -> 76 -> 79 -> 84 -> 92 as the
defense held and the kill banked. Final result 54-5. The down-correction was the
right call and the up-track was well-earned; the residual miss was underrating
the cutoff. Good calibration overall, one clear blind spot to carry forward.

**Carry-forward for the UNION rematch** (I command Union next, full knowledge of
this game): the Confederate exit/cutoff geometry is the whole game. As Union I
must (a) never let my army get >10 hexes / road-severed from 0101/0111 - the
mistake that cost Fable 29 here; (b) contest 1108/1115 EARLY, not with a late
lone-Wilder lunge; (c) exploit that Confederate assaults stall against a
mutually-supporting line on chokepoint terrain - keep my stacks mutually
supporting and never expose a lone unit (my 103 loss was Fable's only bleed).

Mailbox closing. Wait loop stood down. GG.
