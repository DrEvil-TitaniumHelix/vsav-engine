# Judge receipts log — Fable 5 (Union) vs Opus 4.8 (Confederate), Chickamauga campaign

## FINAL RESULT (2026-07-13)
**CONFEDERATE (General Opus / Opus 4.8) WINS 54–5.** Breakdown: eliminations 5 (3/1/XIV, GT13, surrounded — no retreat [7.72]) + occupation 10 (1108+1115) + Union train never exited 10 + 17.32 cutoff 29 (seven Union units: 2/4/XIV, 1/1/XXI, XIV Arty, 3/2/XXI, 1/3/XXI, 2/3/XXI, 3/3/XXI). Union: 5 (0822). CSA LOC road trace NOT clear at end (no exit VP taken — none attempted).
**Log VERIFIED 581/581** (every verdict, die, and state hash reproduced; 60 illegal proposals provably inert).
**Thinking scores (structural, grade_commander):** Opus mean 550, Fable mean 533 (grades.json in live dir).
**Corpus uniqueness:** NO exact position match at ANY of the game's boundaries. Similarity to nearest prior game: 89% after GT1-Union → 38% by GT2 → ≤20% from GT3 on → 5% at game end. Bruce's hypothesis (unprecedented board by GT2-3) CONFIRMED — and the divergence started at GT1-Confederate (57%).
**War journals (unsealed):** fable\outbox\war_diary.md (34.6 KB), opus\outbox\war_journal_opus.md.
**Judge's plan-language note:** the compiler's per-mover ≥1-1 odds guard shaped the whole midgame (fortress assaults could not assemble for either side; artillery bombardment was the only fortress-eviction tool). Both generals independently reverse-engineered its effects. Overseer was informed at GT8 and chose to play on without disclosure. DSL v2 items: assault verb (declared multi-unit contact), entry hold-back verb (Fable improvised it by blocking hexes — cost him the train).
Judge: The Vassal (this session). Seed: 1863 (announced at match start).
Engine live dir: runs\2026-07-13_fable_vs_opus (judge-only).
Integrity rule: every briefing delivered and every plan received is SHA-256
logged here at the moment of transfer; plans are copied byte-for-byte into
the engine, never edited. At game end, mailbox files vs live-dir files vs
the compiled orders in the JSONL log can be diffed by anyone.

## MATCH RESTART (Bruce's order, 2026-07-13)
The first start was voided after one Union plan: the generals lacked the
complete game knowledge (map/terrain data, rulebook, reinforcement
schedule, odds tables, map image, internet research). COMMANDER.md for
both sides was amended to grant it; the live dir was wiped and
re-initialized from setup with the SAME seed 1863. General Fable's context
was also cleared by Bruce — he starts fresh with full knowledge. The
voided GT1 receipts are preserved below for the audit trail.

### Voided receipts (first start, played without full game knowledge)
| # | GT | side | file | direction | SHA-256 |
|---|----|------|------|-----------|---------|
| v1 | 1 | union | briefing_gt1_union.txt | judge → fable inbox | 15087C983D10D7C853339745127C5F0A93A259CA892B680793409F743B3ED7A5 |
| v2 | 1 | union | plan_gt1_union.json | fable outbox → engine (15 actions, 0 rejected) | 7A9387911D646707DBD758E49112B85F167C34C17850556178FC51A25D1738E1 |
| v3 | 1 | confederate | briefing_gt1_confederate.txt | judge → opus inbox | E7B0B555142E30269DE5B9D5EB709EB104E3C5FBED07979290544DE2F26C0D1A |

## Confidence track (Bruce's order mid-GT1: REQUIRED on every plan from GT1-Confederate onward)
Each plan must carry "confidence" (low/medium/high) and "win_percent"
(0-100, own winning probability). Harvested here per plan; calibration vs
the actual result is part of the post-game scorecard. Fable's GT1 plan
predates the requirement — his track starts at GT2.

| GT | side | general | confidence | win% |
|----|------|---------|------------|------|
| 1 | confederate | Opus | medium ("structurally favored side... but GT1 of 15 against a reasoning opponent") | 65 |
| 2 | union | Fable | medium ("structural position sound, burden of action on Opus, but converting a Union edge is historically hard vs a reactive peer") | 52 |
| 2 | confederate | Opus | medium ("clear local superiority against Fable's forward line, east banked, but the deep western fortress is genuinely hard") | 65 |
| 3 | union | Fable | medium ("0-0, fortresses intact, Opus spending multi-unit attacks on empty hexes — but he can concentrate 3-1 and took 1115") | 53 |
| 3 | confederate | Opus | medium ("1115 banked, growing material edge, no counter-threat; but the doubled-terrain fortress is hard and I have not yet won a combat") | 67 |
| 4 | union | Fable | medium ("0-0, both 20-VP fortresses secure, his army committed to positions that score nothing if I stay compact; but he correctly walled my reinforcement flood, capping my upside") | 52 |
| 4 | confederate | Opus | medium ("every VP hex I want is undoubled clear terrain, overwhelming local numbers; but first turn combat resolves, real CRT variance") | 68 |
| 5 | union | Fable | medium ("fortresses strong, his east is thin — but a pure freeze LOSES by 5 on either-hex math; I must attack and my offensive mass is bottled") | 49 |
| 5 | confederate | Opus | medium ("Fable cedes the center, the gaps/exits are undoubled; but nothing banked, still 0-0, I have not yet won a combat") | 70 |
| 6 | union | Fable | medium ("all fortresses intact, Opus overextending — probes isolable, east bare; but he plays actively and my reserve is bottled, near even") | 48 |
| 6 | confederate | Opus | medium ("envelopment materializing with crushing numbers, Fable's NW undoubled; but 0-0, no combat resolved, a compact fortress can still spread my attacks") | 72 |
| 7 | union | Fable | medium ("a genuine coin flip with a clear winning path: hold both fortresses, farm his overextension for CSP, commit the reserve as his line thins; danger = he masses on 0211 before my defense sets") | 50 |
| 7 | confederate | Opus | medium ("overwhelming numbers, cornered enemy on undoubled terrain; but I have still not banked a VP or won a combat — want to see captures land") | 73 |
| 8 | union | Fable | medium ("genuine even fight; forest-rough forward line + exit anchor hard to break, I can farm his overextension — but ~65 str enveloping my NW is real") | 49 |
| 8 | confederate | Opus | medium ("dominant position and I now understand why prior turns stalled, but I refuse to raise the number until combat actually resolves") | 74 |
| 9 | union | Fable | medium ("it's now a race: he grinds my forest-rough belt slowly while my 45+ str rampages his undefended east/center for 30+ VP; genuinely even") | 48 |
| 9 | confederate | Opus | medium ("real occupation lead + material superiority, but thin margin, terrain-hard gaps, and I over-predicted my assaults landing twice — recalibrating down, prioritizing the lead") | 70 |
| 10 | union | Fable | medium ("concrete achievable win path — retake 1115 to flip the deficit — and Opus has scored nothing; but his NW mass genuinely threatens 0502 and I must beat his blockers to 1115") | 49 |
| 10 | confederate | Opus | medium ("I hold the lead with crushing superiority, Fable's only threat is one containable group; but my offense has failed to convert for four turns — playing to secure, not gamble") | 71 |
| 11 | union | Fable | medium ("I'm behind: self-inflicted train delay likely costs 10, either-hexes -5, retreat-heavy CRT makes offense unreliable in 4 turns; but Opus is scoreless and I deny him 40 VP") | 42 |
| 11 | confederate | Opus | medium ("the NW is structurally uncrackable so the game reduces to occupation, which I'm winning; the only threat is the 1115 race — securing, not gambling") | 72 |
| 12 | union | Fable | medium ("clean 67% flip of 1115 this turn and mass arriving, but the stranded train means one flip isn't enough — I need a second score and the CRT is retreat-heavy") | 41 |
| 12 | confederate | Opus | medium ("every scoring hex safe, reinforcements consolidating 1115, no clear Union path to flip two hexes in three turns; residual risk = a late lunge or an unseen rules interaction") | 76 |
| 13 | union | Fable | LOW ("I'm behind and running out of turns: even flipping 1115 leaves ~Conf +5, the CRT bounced my first 2-1, 0211 now pressured; my only chance is the 67% flip plus 1108 by GT15") | 32 |
| 13 | confederate | Opus | medium ("every scoring hex safe, 1115 fortified beyond assault range, two turns left; residual risk = an unseen rules interaction or a desperate lunge, both low") | 79 |
| 14 | union | Fable | LOW ("down 5-0 with no winning line in 2 turns — best case is a tie; Opus is through my NW, my flood is at 17.32 risk; playing for margin and a face-saving 1115 flip") | 6 |
| 14 | confederate | Opus | medium ("banked 5-0 lead plus secure occupation edge, combat proven to work on isolated stacks, 0211 is low-risk bonus; only an unforeseen swing loses it") | 84 |
| 15 | union | Fable | LOW ("final turn, down 5-0, stranded train and either-hex deficit make a Union win impossible; minimizing the margin — a loss, played out cleanly to the last hex") | 2 |

## Live receipts (restarted match)
| # | GT | side | file | direction | SHA-256 |
|---|----|------|------|-----------|---------|
| 1 | 1 | union | briefing_gt1_union.txt | judge → fable inbox (byte-identical to v1 — same seed, deterministic) | 15087C983D10D7C853339745127C5F0A93A259CA892B680793409F743B3ED7A5 |
| 2 | 1 | union | map_gt1.png | judge → fable inbox (rendered setup map) | 8E93951BEC2546BABBEF3B26D4AD2FDA77BE1A5D7387B1016A808F095E0050F4 |
| 3 | 1 | union | plan_gt1_union.json | fable outbox → engine (14 actions, 0 rejected) | 1E31C3848A6EA20DC12ECCCD1836CDDBEB4AB1331A9102D376E47DB9AFC3446C |
| 4 | 1 | confederate | briefing_gt1_confederate.txt | judge → opus inbox | 57337BC568F3A405D9766839CA175C55B880B8A25415FFD2205C9A47256CE8F6 |
| 5 | 1 | confederate | map_gt1.png | judge → opus inbox (board after Union GT1 move) | 504F0407CFA584A2EB7A1690AAC5F331778637A28C282C4BEF8D055A93C0F501 |
| 6 | 1 | confederate | plan_gt1_confederate.json | opus outbox → engine (32 actions, 0 rejected; first filing bounced for missing confidence fields, resubmission compiled) | 5C62E31A586F73BDC470C2D2AB7F2F43943501D0C4C1A114A321B5EF7E17F8AE |
| 7 | 2 | union | briefing_gt2_union.txt | judge → fable inbox | 4E6C7C91875CD7B6EC78AA1F9EFA19D7CAB44DFC58F51BF86F3C9F59227CB7F5 |
| 8 | 2 | union | map_gt2.png | judge → fable inbox (board after Confederate GT1 move) | D196B1148DD0CDC2D733B15F9A100CFE21BE990AA049D641EAECB951001716B8 |
| 9 | 2 | union | plan_gt2_union.json | fable outbox → engine (14 actions, 2 rejected by the gate; first filing bounced for missing confidence fields, resubmission compiled) | CCEC95F750917DDF6B56D8446D7F0828167DB6236352523A71D0E5CCB7BBC11D |
| 10 | 2 | confederate | briefing_gt2_confederate.txt | judge → opus inbox | CCA83470A6250F5DBDAAADB1D43FF6CEFF8C653B3CF525F183CAF043FD4713AB |
| 11 | 2 | confederate | map_gt2.png | judge → opus inbox (board after Union GT2 move) | FBD505DFCC54259E451E2B73A2E86DCF3F9FEA3EACC9787A524D0A56642AE697 |
| 12 | 2 | confederate | plan_gt2_confederate.json | opus outbox → engine (35 actions, 2 rejected by the gate) | 32BA9DCAE7E33889B99FC303DA923E2562F739CF5E51DC9A9AF536AA574A04E6 |
| 13 | 3 | union | briefing_gt3_union.txt | judge → fable inbox | 3365477BF974EBD39204342AB40BE69429215AAE3FA8F85E903CDC6ABB706FCC |
| 14 | 3 | union | map_gt3.png | judge → fable inbox (board after Confederate GT2 move) | 0EECB1ED8D097B03001D554FCC55FE176913EEB4E57DC0BF6B5B3F97CA0585F2 |
| 15 | 3 | union | plan_gt3_union.json | fable outbox → engine (10 actions, 2 rejected by the gate) | BC9B0FDF82DD6CCB5552B4251A88E4932DF4D1138A7B15E72B64D763DBB62C64 |
| 16 | 3 | confederate | briefing_gt3_confederate.txt | judge → opus inbox | 82D4190106715CC2F73F6BCC8730DFF36EB3BB5AA080383F8193E32378B85175 |
| 17 | 3 | confederate | map_gt3.png | judge → opus inbox (board after Union GT3 move) | F59C4D3B8F68FA7ADB12048475EA3D2E3D126283DD8F310C83BD5187241951C2 |
| 18 | 3 | confederate | plan_gt3_confederate.json | opus outbox → engine (28 actions, 2 rejected by the gate) | DCF2E6C12326BD76D92C44BB73C60FA80989D8AA1DEABF49A0236C26FE4A95A5 |
| 19 | 4 | union | briefing_gt4_union.txt | judge → fable inbox | 31A51EC0B45FB9FF03427E91F50AC03BB0F63657929F39324F5F4297EA925A59 |
| 20 | 4 | union | map_gt4.png | judge → fable inbox (board after Confederate GT3 move) | 3A28FA1F313A8D9C48C846B4835494022CFA1B5557A2A66C8C29B74DAF918358 |
| 21 | 4 | union | plan_gt4_union.json | fable outbox → engine (9 actions, 2 rejected by the gate) | DECD1458A47CD934166FE3B54D5CE112F592907096C6E0C384003CA6304BB7B5 |
| 22 | 4 | confederate | briefing_gt4_confederate.txt | judge → opus inbox | 4DCD0C79FE9B26B92D103508BBB0BDDD6E476631B3C142B73240A54A47B1DFD6 |
| 23 | 4 | confederate | map_gt4.png | judge → opus inbox (board after Union GT4 move) | 2D4477819A17BF557CE7741EF086884660BA13F15A99DC1C406A94BE44D80D6A |
| 24 | 4 | confederate | plan_gt4_confederate.json | opus outbox → engine (29 actions, 2 rejected; battle: Gist vs 2/3/XIV at 1-1, die 6 = Ar, attacker retreated) | 583EDA362B9E9626E9576DD824547BE92549F19FBEB4EEE9B9F401EB9A01ABE9 |
| 25 | 5 | union | briefing_gt5_union.txt | judge → fable inbox | 8A4AA61CCF50A07327EFF377F71EF440BA8C2DA92BCE79744D72C931B008D456 |
| 26 | 5 | union | map_gt5.png | judge → fable inbox (board after Confederate GT4 move) | 5124A0F9CBFA7714DA6B82895912C8C192DE74342DFCFF9A8FDDD15F4DCCBC41 |
| 27 | 5 | union | plan_gt5_union.json | fable outbox → engine (8 actions, 2 rejected; no combat) | 26D3E6E91FC0648EE4EF1C466427464D00B6C306CA5FEB4769E41D9EE7762C5B |
| 28 | 5 | confederate | briefing_gt5_confederate.txt | judge → opus inbox | BD40B242A810A49C769F540480902BC4367EC28EF61D046E7A789134848D9949 |
| 29 | 5 | confederate | map_gt5.png | judge → opus inbox (board after Union GT5 move) | C36C8238B480DE099DC8805162FA2C70DA8673FCF23E2F27E76F998A487D49F2 |
| 30 | 5 | confederate | plan_gt5_confederate.json | opus outbox → engine (27 actions, 2 rejected; no combat resolved) | 4B09DF391F4D324D5E275814B1E5B66F486D82F0FAA10BBA0768C320D9AC5070 |
| 31 | 6 | union | briefing_gt6_union.txt | judge → fable inbox | C8C70C3B0E3C28151D91F98B1D4EBA6D2A62CFCB119C5EF6E40757A541F96C60 |
| 32 | 6 | union | map_gt6.png | judge → fable inbox (board after Confederate GT5 move) | 948D0A1B50495A54649A7F54142A65ED44290469409F68636097B84D216D4070 |
| 33 | 6 | union | plan_gt6_union.json | fable outbox → engine (9 actions, 2 rejected; no combat) | 9D263D7FD88357C7BB62FED90AF7321332805E02D8C45A8B19E1C34D405A0F9A |
| 34 | 6 | confederate | briefing_gt6_confederate.txt | judge → opus inbox | 79DCB167454836A03F4FC177E7B0A9CA3D8F994FF45DC00F7C3C5DCB9E251686 |
| 35 | 6 | confederate | map_gt6.png | judge → opus inbox (board after Union GT6 move) | 07D84F58D517DC6833CC8EF8A95572EA6406627F8DF732003714720577F8CBA2 |
| 36 | 6 | confederate | plan_gt6_confederate.json | opus outbox → engine (35 actions, 3 rejected; no combat resolved) | 41EE586D9728D86B62E926DC4A03E71E8B7DC575F2FE6EEDEE1FB01B729E390B |
| 37 | 7 | union | briefing_gt7_union.txt | judge → fable inbox | 7775AFFC5C81D1D262472C19F7BCFFF03920F0E474A32CC762CA8CFB880D9A48 |
| 38 | 7 | union | map_gt7.png | judge → fable inbox (board after Confederate GT6 move) | A5618FCC3A975F8E3998FEC1C06F7AD109BC3DE2D37BCA7D02412FDAF1DC10CD |
| 39 | 7 | union | plan_gt7_union.json | fable outbox → engine (10 actions, 2 rejected; no combat) | D5CBF82FAB95491138CEA60F58AC9E43C90A6BBA499FCB6569771D2E675BE48B |
| 40 | 7 | confederate | briefing_gt7_confederate.txt | judge → opus inbox | 9D9D95B7912FCB9DA6994C41C2117812CFF977936A0DB60E5EC513A03846587A |
| 41 | 7 | confederate | map_gt7.png | judge → opus inbox (board after Union GT7 move) | 707905C17F6E71C69475C37827452886EA4E5A4ADE3C428F1F0C90F67C73CADF |
| 42 | 7 | confederate | plan_gt7_confederate.json | opus outbox → engine (33 actions, 2 rejected; battle: Ector vs 2/3/XIV at 1-1, die 1 = Dr, defender retreated) | E363145DCD6BB728E70DAD8FF6938C99C59BBDB86D66B6C6A5ED07E19E1B7E4D |
| 43 | 8 | union | briefing_gt8_union.txt | judge → fable inbox | 31C4B53003FA22B6A9EF204EB031C3CE3189178AB0588411C7053B97F14E5F2A |
| 44 | 8 | union | map_gt8.png | judge → fable inbox (board after Confederate GT7 move) | E85FC968320A2D6C94AEB89B953D49B8B40B29E261EDD57713ECCE734C82E949 |
| 45 | 8 | union | plan_gt8_union.json | fable outbox → engine (8 actions, 2 rejected; no combat) | 839F4A8A69750DCE878E232B6E5352417F5098242D98DD8B2A11773DEDABC1D1 |
| 46 | 8 | confederate | briefing_gt8_confederate.txt | judge → opus inbox (+ neutral night-turn rules reminder in YOUR_TURN, mirrored to Fable at GT9) | DBEC074F805268D3151731F37DCD920B337B65E4DE4D64D5D3B8931BCBD12D11 |
| 47 | 8 | confederate | map_gt8.png | judge → opus inbox (board after Union GT8 move) | F574588FAE213976B0E9A25C2BE4B34AAA1B2497E374A1E1BB7A12FF4F917630 |
| 48 | 8 | confederate | plan_gt8_confederate.json | opus outbox → engine (24 actions, 3 rejected; declared triple assault did NOT land — compiler odds-guard, see judge note below) | E3CCE0B0F98BC5C0D48BC4CBFFD835F3D595A6D47AA58E1A38962521F8119AB2 |
| 49 | 9 | union | briefing_gt9_union.txt | judge → fable inbox (night turn) | FAEA9924E2047C4751FDF5337973F9EF2ED700E92D15E641BC83F42A60A1C466 |
| 50 | 9 | union | map_gt9.png | judge → fable inbox (board after Confederate GT8 move) | 538CEBD7EE61C7FF16A641D93C7CF4677C66F3195B3323C1AC80AD353EBFB52E |
| 51 | 9 | union | plan_gt9_union.json | fable outbox → engine (11 actions, 3 rejected; night — no combat) | 6E90812880535622408FBE97A027318381E7D21BE5A99C6A2597174D426961F5 |
| 52 | 9 | confederate | briefing_gt9_confederate.txt | judge → opus inbox (night turn) | 9F6E7D23CF0A7E0FEE3C828FBC06E7B821EA0F4C7A47E715FD71DFE55295488D |
| 53 | 9 | confederate | map_gt9.png | judge → opus inbox (board after Union GT9 move) | AA253DE37BF02D144EC07CA0E038D97D75100013C6A5DA64CCE1DDA0E70A3785 |
| 54 | 9 | confederate | plan_gt9_confederate.json | opus outbox → engine (17 actions, 2 rejected; night — no combat) | 6EC742DEFB821C94EE1066FB823F5FD7A4F1E4F649206042420FCE2B43AD9495 |
| 55 | 10 | union | briefing_gt10_union.txt | judge → fable inbox | F39E6A36CA8C310BFF3984F939B743B3F84183DD155A84F94A9D35930C30705E |
| 56 | 10 | union | map_gt10.png | judge → fable inbox (board after Confederate GT9 move) | 8C929EAD29E95136C8ED3F9F9DA014D335CDEB91B46B66CDCC6B1A833CC8D914 |
| 57 | 10 | union | plan_gt10_union.json | fable outbox → engine (12 actions, 2 rejected; battle 4: Union XIV Artillery bombards 2 Artillery at 1-2, die 5 = Ar, no effect on pure bombardment [8.15]) | FACD1B91069B1A1A5BC5358255B408BEF9B1797F04517FB83E6D6138A14F0A8F |
| 58 | 10 | confederate | briefing_gt10_confederate.txt | judge → opus inbox | D0BA5D572D649B89EECD26BF28128397C36ACC766476DD4100B7C1FB6F9742AA |
| 59 | 10 | confederate | map_gt10.png | judge → opus inbox (board after Union GT10 move) | 48F03236723AFFF7E11B2C8F4832AD0566B4BF4546CE53732EBCE7C91659EE49 |
| 60 | 10 | confederate | plan_gt10_confederate.json | opus outbox → engine (21 actions, 3 rejected; battles 5-6: Deas drives 2/2/XIV back at 1-1 [die 2 Dr]; CSA artillery counter-bombardment drives XIV Artillery back [die 2 Dr]) | 5A4CB037144723DD6423EA2016C65E53E3FE6ABC0C372BCA04D101431FE4E2F4 |
| 61 | 11 | union | briefing_gt11_union.txt | judge → fable inbox | 044A4EAB8479D3CCF609C86268B257BC217937A8C8B7C26285BD05215140850B |
| 62 | 11 | union | map_gt11.png | judge → fable inbox (board after Confederate GT10 move) | F11BBD70230A04249B72D87DCCD7ABD09DB3B8A1C1615E6EB5FA5C974DFB59FA |
| 63 | 11 | union | plan_gt11_union.json | fable outbox → engine (15 actions, 2 rejected; battle 7: 1/2/XXI vs 2 Artillery at 1-1, die 5 = Ar, attacker retreated) | 2AE52C60A1F4CCBBEDB145CFFCE60830ABB9A22D93CC397B360AF3B215B5C957 |
| 64 | 11 | confederate | briefing_gt11_confederate.txt | judge → opus inbox | B5871C16A7254FC41035B13A0E25AC2A575EC12705BA81762E76758A07E27FB3 |
| 65 | 11 | confederate | map_gt11.png | judge → opus inbox (board after Union GT11 move) | 06C67BC0763A3FF994BC372942E46D6AF60FCD30CE3F87006FCC9B8D30B396E3 |
| 66 | 11 | confederate | plan_gt11_confederate.json | opus outbox → engine (23 actions, 2 rejected; battles 8-11: ALL four Confederate attacks repulsed — Deas and Manigault bounced at 1-1 [both die 6 Ar], both bombardments no effect) | 930945C79235191FF38CD8B4F05A0C4BC5AC221ABA1192E9C513EDB095785C73 |
| 67 | 12 | union | briefing_gt12_union.txt | judge → fable inbox | 2FA664576F53FC3AB2AE24AAF9BE05D40710711665451B918B4F16EED6940D0C |
| 68 | 12 | union | map_gt12.png | judge → fable inbox (board after Confederate GT11 move) | 8C85D828DE57DC5C621416BE797BE4D4FA07DD99BADC1B0F33669E7B76A74F47 |
| 69 | 12 | union | plan_gt12_union.json | fable outbox → engine (17 actions, 2 rejected; battle 12: Wilder alone vs Smith+Wright at 1-1 [not the planned 2-1], die 5 = Ar, repulsed; Opus declined the advance; battle 13: bombardment Ae ignored per 8.15 immunity — unit verified alive) | E505B2ED437A5F85212132037725C3BD263FF151BCF311B28258D272F161F0E5 |
| 70 | 12 | confederate | briefing_gt12_confederate.txt | judge → opus inbox | 5E956CFDBD8E15008AEF6409A164D65E51ED1022B56C10698BAC08ECA52CA63F |
| 71 | 12 | confederate | map_gt12.png | judge → opus inbox (board after Union GT12 move) | DDC2B3C24F3C8E656EFD034515E0F664518B584DAB096843C5EA7F2E2137AF4D |
| 72 | 12 | confederate | plan_gt12_confederate.json | opus outbox → engine (25 actions, 3 rejected; battles 14-16: Deas+Manigault repulsed at 2-1 [die 6]; bombardment drove the 0502 garrison [112+113] out of Rossville Gap to 0401 [die 2 Dr]; second bombardment drove XIV Artillery back) | 31F9C3BFCA6917584157F35D762872D1F5F4821A0916F3CDE0333888E397622E |
| 73 | 13 | union | briefing_gt13_union.txt | judge → fable inbox | 7A2C208F9B21752C8B47B5C66AD8F749C5696CB883BCF223FD588D610C575ED1 |
| 74 | 13 | union | map_gt13.png | judge → fable inbox (board after Confederate GT12 move) | C26AA0B0E5839F33AD485D033599B1EADAE55DB4E05F941CF3DB477B51DBCFFB |
| 75 | 13 | union | plan_gt13_union.json | fable outbox → engine (14 actions, 2 rejected; NO combat — the 1115 assault could not assemble: Anderson6 at 1116 makes the approach hex face 14 adjacent str, first mover fails the odds test; 0502 re-garrisoned by 112/113) | 7A27F7D161B58A43C4946F5C800480BD26551692B6F8369028CC88B5C369A2AA |
| 76 | 13 | confederate | briefing_gt13_confederate.txt | judge → opus inbox | 6C8C136180101C715FCA020D098B67188F936104C6B3B8E4A5F045FE80BBD9EF |
| 77 | 13 | confederate | map_gt13.png | judge → opus inbox (board after Union GT13 move) | 680C7229A163E1DDB92E9CC36C4E9BC8A81CC07FCBD1DCE2D5F395B3C2872F3A |
| 78 | 13 | confederate | plan_gt13_confederate.json | opus outbox → engine (40 actions, 2 rejected; 6 battles: FIRST KILL — 3/1/XIV surrounded, no retreat, eliminated [7.72], +5 VP Confederate; 3 other CSA attacks repulsed incl. Deas+Manigault's 4th bounce; 2 bombardments no effect). VP: Confederate 5 — Union 0 | C7197BE5CF98171A335B63239DE411CF91CDAFA858896EE14236B9CC1A7C517A |
| 79 | 14 | union | briefing_gt14_union.txt | judge → fable inbox | 5DC3416F90D410F87E0778B23B22FCA3C4B866804D4C59CC1B7997322B444A7B |
| 80 | 14 | union | map_gt14.png | judge → fable inbox (board after Confederate GT13 move) | 3934EA9CDAE5C4EE7EB41E18CBDA11B0EEA7912D2B15A06476E1E5BB55DAEEB2 |
| 81 | 14 | union | plan_gt14_union.json | fable outbox → engine (10 actions, 2 rejected; NO combat — the third 1115 assault also failed the odds-guard against the ~26-str fortified area) | 0314C15D961E55832D2336D59B917291A9C812D3AE21B72B6C940C4F2EF04F76 |
| 82 | 14 | confederate | briefing_gt14_confederate.txt | judge → opus inbox | 68248F3D1D723E5828FE0AA6442A3D1BFBEFD53C60B5D20FD95B120EE5189C81 |
| 83 | 14 | confederate | map_gt14.png | judge → opus inbox (board after Union GT14 move) | 342205063A4B14BBFB1A0F7564AEAEC90BFABECBFC41DFA4160C63D84D5F3068 |
| 84 | 14 | confederate | plan_gt14_confederate.json | opus outbox → engine (21 actions, 3 rejected; battles 23-24: bombardment evicted the 0502 garrison AGAIN [die 2 Dr] and drove 1/3/XXI back [die 1 Dr]; the 0211/0311 infantry assaults did not assemble) | DDFCDFEACF967EF7255D5E9418377EEA9BF74732B4A94A9F5C7BA7BECE26E872 |
| 85 | 15 | union | briefing_gt15_union.txt | judge → fable inbox (FINAL TURN) | B327E4A530AE87C018125268901E24F63C637B985A46460F0628FF5A506E775B |
| 86 | 15 | union | map_gt15.png | judge → fable inbox (board after Confederate GT14 move) | D7C55DB598EB26105DB53C8F741BE78A253BDA5568D0B1A6C4BCE3E190C807FD |
| 87 | 15 | union | plan_gt15_union.json | fable outbox → engine (15 actions, 2 rejected; no combat — the final 1115 swing again failed to assemble) | 76B09BC6C4574C98AF1EE5195ABED40B03FC96F186F7345C6EA92B7D4D7E6099 |
| 88 | 15 | confederate | briefing_gt15_confederate.txt | judge → opus inbox (FINAL PLAN of the game) | EA70415342CBAB931128A1AD4B5792DE43E40E07DDF615D123478323DBFB2C81 |
| 89 | 15 | confederate | map_gt15.png | judge → opus inbox (board after Union GT15 move) | BDCD905417F3713E25F88D8FAAB6216F02E1F82E38E93EB909BACAD0D39E5467 |

**JUDGE NOTE (GT8, escalated to the Overseer):** Opus's declared triple assault produced zero battles. Root cause verified in `engine/plans.py` + `engine/ai_bluegray.py::_local_odds_ok`: EVERY movement verb (push AND hold) applies a per-moving-unit odds guard — a unit may end adjacent to an enemy stack only if it PLUS friends already adjacent can fight at >=1-1 (defender terrain doubling included). Consequence: a 2-unit garrison (~10 str) can never be contacted by any single mover (max CSA unit str 7), so massed assaults on paired fortresses can never assemble — they are unassaultable through the current plan DSL, though fully assaultable under the printed rules (the gate allows any-odds adjacency; the guard is an AI-doctrine artifact inherited by the compiler). Both generals operate under the identical constraint. Overseer decides: disclose symmetrically / change nothing / amend DSL.
