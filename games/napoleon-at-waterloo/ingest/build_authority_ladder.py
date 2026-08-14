import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "authority_ladder.json")

T = {
    "T0": {
        "name": "PRINTED PRIMARY",
        "definition": "A scan or photograph of the published component, with provenance traceable to that component.",
        "citable_for": "anything it legibly shows, including the existence and the absence of things",
        "not_citable_for": "completeness. A punched counter set proves what is there, not what was there (PREP-4 section 10)",
    },
    "T1": {
        "name": "FAITHFUL REPRODUCTION",
        "definition": "A copy or restoration whose content has been checked against a T0 witness and matched over the whole of the content being relied on.",
        "citable_for": "corroboration of what the T0 witness shows; legibility where the T0 scan is poor",
        "not_citable_for": "anything the T0 witness does not cover (Gap Rule). Provenance is not established, so it is not T0 however scan-like it measures",
    },
    "T2": {
        "name": "MODULE-AUTHORED TRANSCRIPTION",
        "definition": "The module author re-typed or re-placed printed content: piece names, prototypes, setup files, rules-text play aids. An independent human read of the same printed source.",
        "citable_for": "agreement or disagreement with a primary reading, which is real evidence in both directions",
        "not_citable_for": "outranking a printed source, ever; supplying a value the printed source does not carry",
    },
    "T3": {
        "name": "REDRAW",
        "definition": "The content was re-authored graphically.",
        "citable_for": "corroboration, over the exact extent where a T0 or T1 witness has been compared and agrees",
        "not_citable_for": "being a sole source for anything; the parts a redraw silently drops (echelon symbols, designations, PREP-4 P4C-7); typography, notation or layout",
    },
    "T3c": {
        "name": "CONTAMINATED REDRAW",
        "definition": "A redraw carrying rules content traceable to a third party.",
        "citable_for": "nothing about the published game. It is evidence only about itself",
        "not_citable_for": "any rule, any value, any part of it. Worse than T3 and worse than T5, because it is presented as the game's own component",
    },
    "T4": {
        "name": "OUT-OF-EDITION / OUT-OF-PRODUCT PRIMARY",
        "definition": "Genuine printed material for a different edition or a different product.",
        "citable_for": "its own scope, at T0 strength",
        "not_citable_for": "being merged into another edition's rules (PREP-1 D16)",
    },
    "T5": {
        "name": "THIRD-PARTY / FAN",
        "definition": "House rules, tweaks, revamps, fan reissues.",
        "citable_for": "awareness of what a tester or a module may be running",
        "not_citable_for": "any rule, even where it happens to be right. Review-only",
    },
    "T6": {
        "name": "SCAFFOLD-ONLY",
        "definition": "Navigation and reading aids: web transcriptions, contents pages, nameplates, icons.",
        "citable_for": "nothing, not even their own content",
        "not_citable_for": "anything. PREP-1 D3: the fan transcription says six items of information where printed [2.4] says five",
    },
    "D": {
        "name": "DERIVED (OURS)",
        "definition": "Our own VERIFIED documents and ingest JSON. Outside the ladder: the record of a reading, not a source.",
        "citable_for": "internal working reference and audit trail",
        "not_citable_for": "game.json citations, which point at the printed section and page (hard rule #8). See disagreement C",
    },
}

FLAGS = {
    "out-of-edition": "genuine for some edition or product, but not this one",
    "contaminated": "carries rules content traceable to a third party",
    "retimed": "printed content whose values were altered in the copy",
    "provenance-unestablished": "measures and reads as printed art, but its chain to the published component is unknown",
    "gap-fill": "currently relied on for a claim no primary witness covers, contrary to the Gap Rule",
    "unexamined": "tier assigned by class, not by opening it",
}


def A(aid, tier, evidence, citable, notcitable="", flags=(), ruling="carried", bite="", holder="", extra=None):
    d = {
        "id": aid,
        "tier": tier,
        "tier_name": T[tier]["name"] if tier in T else tier,
        "flags": list(flags),
        "evidence": evidence,
        "citable_for": citable,
        "not_citable_for": notcitable,
        "ruling": ruling,
        "bite": bite,
    }
    if holder:
        d["holder"] = holder
    if extra:
        d.update(extra)
    return d


PDF = "C:\\VassalLibrary\\launchbox\\Manuals\\VASSAL\\Napoleon at Waterloo"
E2 = "C:\\VassalNaW\\modules\\ed2_oliver"
E3 = "C:\\VassalNaW\\modules\\ed3_davejm"

ASSETS = [
    A(f"{PDF} (2nd Ed)/NapoleonatWaterloo.pdf p.1", "T0",
      "PREP-1 section 1 and 2. Masthead: Second Edition Copyright 1971, Simulations Publications, Inc. Graphics Redmond A. Simonsen. 6968x3519 native.",
      "every 2nd Edition rule as printed: movement, ZOC, combat, artillery, DISRUPTION, Prussian entry, victory, demoralization, exit",
      "", (), "carried", "PREP-1", "SPI 1971"),
    A(f"{PDF} (2nd Ed)/NapoleonatWaterloo.pdf p.2", "T0",
      "PREP-1 section 2. Examples of Attacks, ~24 printed worked examples with stated odds including a Doubled due to Town-hex case.",
      "the 2nd Edition worked-example validation corpus required by hard rule #1",
      "", (), "carried", "PREP-1", "SPI 1971"),
    A(f"{PDF} (2nd Ed)/NapoleonatWaterloo.pdf p.3", "T0",
      "PREP-1 D15. Dunnigan cover letter on SPI letterhead, references S&T 31/32 and a 15 May shipping date.",
      "provenance and dating of this copy only",
      "any rule. The page contains none", (), "carried", "PREP-1", "SPI 1971"),
    A(f"{PDF} (2nd Ed)/NapoleonatWaterloo.pdf p.4", "T0",
      "PREP-4 witness A. Photograph of the punched 2nd Edition counter set, 4400x3400 native, read by eye at 3x-6x.",
      "counter mix (54 counters), unit types, designations, factors, echelon symbols, and the fact that the box holds exactly one marker",
      "completeness of the set: a punched copy cannot prove nothing is missing (PREP-4 section 10). Counter reverses were never photographed",
      (), "carried", "PREP-4", "SPI 1971"),
    A(f"{PDF} (2nd Ed)/NapoleonatWaterloo.pdf p.5", "T0",
      "PREP-1 section 2 (chart locations by fractional bbox), PREP-3 sections 2-5 (grid fit, terrain, at-start pictures), PREP-4 section 6 (Time Record, Demoralization Scale, Exited box, exit arrows). 6952x5171 native.",
      "the printed CRT (all 60 cells, twice), the printed TEC, the Time Record with Prussian entry at 2 pm, the Demoralization Scale and its usage instruction, the Exited French Units box, the 11 exit arrows, the at-start unit pictures, and the terrain field",
      "", (), "carried", "PREP-1/3/4", "SPI 1971"),
    A(f"{PDF} (3rd Ed)/Napoleon at Waterloo rules org and 79 and tweeks.pdf pp.7-12", "T0",
      "PREP-1 section 1 and 2. Scan of the printed later-edition rules booklet in SPI case format; printed page numbers 9, 10, 14, 16 visible.",
      "sections [1.0] through [10.0] as printed, and the 3rd Edition Examples of Attacks on p.11",
      "anything about the 3rd Edition map or its Terrain Effects Chart, neither of which the booklet reproduces (PREP-2 E14/E15)",
      (), "carried", "PREP-1", "SPI"),
    A(f"{PDF} (3rd Ed)/Napoleon at Waterloo rules org and 79 and tweeks.pdf pp.1-6", "T6",
      "PREP-1 section 1 and D2/D3. A fan website printed to PDF: http://www.kobudovenlo.nl/napoleonatwaterloo/, browser furniture (1 van 6, 27-2-20), layout credited to M vd Zanden. Its text layer decodes to garbage, so any pipeline trusting PDF text extraction ingests noise.",
      "nothing. Reading scaffold only",
      "any rule. It paraphrases: printed [2.4] says five items of information, the transcription says six",
      (), "carried", "PREP-1", "M vd Zanden"),
    A(f"{PDF} (3rd Ed)/Napoleon at Waterloo rules org and 79 and tweeks.pdf pp.13-19", "T5",
      "PREP-1 section 1. Philip Sabin, Simple Rules Tweaks, April 2020.",
      "awareness of what a tester or module may be running",
      "any rule of either published edition", (), "carried", "PREP-1", "Philip Sabin"),
    A(f"{PDF} (3rd Ed)/Napoleon_at_Waterloo_Improved_Rules_Tweaks_Sabin_11.23.pdf", "T5",
      "PREP-1 D14. Sabin, Improved Rules Tweaks, Second Edition, November 2023; flags its own substantive changes in red and states that Allied Demoralisation and the exiting of French units no longer apply.",
      "awareness only, and the fact that two different Sabin editions circulate in our holdings",
      "any rule of either published edition", (), "carried", "PREP-1", "Philip Sabin"),
    A(f"{PDF} (2nd & 3rd Ed)/rules.pdf", "T5",
      "PREP-1 D1. Christian Holm Christensen's 2024 LaTeX revamp, CC BY-SA 4.0; p.2: This version all text, illustrations, graphics, and layout by Christian Holm Christensen. Merges basic, advanced, Grouchy and Esdaile material and both maps.",
      "nothing",
      "anything. Its Woods x2 defence and 4 MF entry, symmetric 40/90 demoralisation, chit-drawn reinforcement and 2021 Esdaile variant are in neither printed edition. It is the file a naive reader reaches first",
      (), "carried", "PREP-1", "Christian Holm Christensen"),
    A(f"{PDF} (2nd & 3rd Ed)/org.pdf", "T5",
      "PREP-1 section 1. OOB charts belonging to the same 2024 revamp.",
      "nothing", "any order of battle", (), "carried", "PREP-1", "Christian Holm Christensen"),
    A(f"{PDF} (2nd Ed)/NapExpansionRules.pdf", "T4",
      "PREP-1 D16. SPI Advanced Game Expansion Kit, Copyright 1971, Simulations Publications, Inc. Genuine period document, brigade-level escalation with its own TEC. PREP-6 inspection t_ed2_expansion_p1 confirms period type with ink irregularity, descreened and thresholded.",
      "the Expansion Kit only, at T0 strength for that product",
      "either base edition. Merging it into the base game is exactly what the 2024 revamp does",
      ("out-of-edition",), "carried", "PREP-1", "SPI 1971"),

    A(f"{E2}/images/Nap at Waterloo map 20mm hexes.jpg", "T1",
      "PREP-2 module_art_verified_good; PREP-3 section 4: 61 woods hexes identical to the folio hex for hex, from a separately fitted grid, plus the full village set including Ohain, Maransart and Maison du Roi. PREP-6 inspection t_ed2mod_map: scanned paper tone, soft hex rule, JPEG fringing on the printed title. Measured redraw_score 0.285 (scan-like).",
      "corroborating the printed 2nd Edition map: terrain, villages, Time Record 2 pm, exit arrows, at-start pictures; and as a clean coordinate frame",
      "anything the folio map does not show",
      ("provenance-unestablished",), "carried", "PREP-2/3", "Stephen Oliver"),
    A(f"{E2}/images/NapatWatCRT.jpg", "T1",
      "PREP-2 module_art_verified_good: independently confirms the folio transcription in all 60 cells plus the clamp footnote. PREP-6 inspection t_ed2mod_crt: period type, visible halftone screen in the grey bands, cream paper, contrast-boosted. Measured redraw_score 0.442 (borderline), driven by pure_black_share 0.962 which is the levels adjustment, not the authorship.",
      "corroborating the printed 2nd Edition Combat Resolution Table",
      "the 3rd Edition table, which must be compared separately",
      ("provenance-unestablished",), "carried", "PREP-2", "Stephen Oliver",
      {"open_question": "disagreement D: measures and looks like a scan of printed 1971 art; held at T1 only because provenance is unestablished"}),
    A(f"{E2}/images/NapatWat TEC.jpg", "T1",
      "PREP-2 module_art_verified_good: word for word including the Towns & Woods/Roads grouping and the Woods entry prohibition. PREP-6 inspection t_ed2mod_tec: period type, cream paper, a pink printer guide line still present. Measured redraw_score 0.538 (borderline), pure_black_share 0.971.",
      "corroborating the printed 2nd Edition Terrain Effects Chart",
      "the 3rd Edition chart. No 3rd Edition TEC exists in our holdings",
      ("provenance-unestablished",), "carried", "PREP-2", "Stephen Oliver",
      {"open_question": "disagreement D"}),
    A(f"{E2}/buildFile.xml PieceSlot names and prototypes", "T2",
      "PREP-4 section 9 and module_oob.json: the factor pair is typed into the piece name and repeated as a prototype tag carrying combat strength; all 53 units agree name-vs-prototype. Declares zero GridNumbering elements, matching the unnumbered printed map.",
      "agreement or disagreement with the printed counters; the module's declared HexGrid as a second lattice witness",
      "any factor the printed counters do not carry", (), "carried", "PREP-4", "Stephen Oliver"),
    A(f"{E2}/Beginning Setup.vsav", "T2",
      "PREP-4 section 9 and section 4: Oliver's own placement of the printed at-start pictures; 44/44 hexes identical to PREP-3's independent read, one unit per hex.",
      "an independent human read of the at-start pictures",
      "outranking the printed map, ever", (), "carried", "PREP-4", "Stephen Oliver"),
    A(f"{E2}/images/NAW_*.png (53 counter faces)", "T3",
      "PREP-4 section 9: 194x194 digital redraws, flat fills, rounded corners with a red bleed border, modern sans digits, vector-clean NATO symbols. PREP-6 inspection t_counter_NAW_1_2_zoom confirms, and confirms FOUR printed items (type, designation, CS, MA) with no setup hex. Measured redraw_score 0.716-0.721.",
      "corroboration of factors, unit type and designation, and only because it agrees with the printed map pictures at 44 of 44 at-start hexes",
      "echelon symbols and the Hougoumont H designation, which the redraw drops (PREP-4 P4C-7); anything about counter typography or reverses",
      (), "carried", "PREP-4", "Stephen Oliver"),
    A(f"{E2}/images/NapWatvariant_*.png (29 variant counters)", "T3",
      "PREP-4 section 9 and P4C-4: labelled Var where printed 3rd Ed [9.1] specifies 5v. Measured redraw_score 0.897.",
      "corroborating PREP-2 defect M2 from art rather than text",
      "anything about the 2nd Edition. The Grouchy variant does not exist in it (PREP-2 M3)",
      ("out-of-edition",), "carried", "PREP-4", "Stephen Oliver"),
    A(f"{E2}/images/Grouchy Variant.jpg", "T3c",
      "PREP-2 M2/M3: a retimed edit of printed [9.2]-[9.4]. Every turn number shifted one turn earlier, substituted words set in a visibly heavier face: Game-Turn Four where printed reads Five, Game-Turn Two where printed reads Three. PREP-6 inspection t_mod_grouchy_sheet confirms the heavier substituted face and the digitally drawn Var counters. Byte-identical in both modules.",
      "nothing",
      "the Grouchy variant schedule, which it silently changes; and nothing at all for the 2nd Edition, which has no Grouchy variant",
      ("retimed", "out-of-edition"), "carried", "PREP-2", "Stephen Oliver"),
    A(f"{E2}/images/NAW 2nd Edition nameplate.png", "T6",
      "PREP-2 M5. Byte-identical in both modules, which is why they cannot be told apart by asset inspection alone. Measured redraw_score 0.262, production method never established.",
      "nothing; branding only", "", (), "carried", "PREP-2", "Stephen Oliver"),
    A(f"{E2}/moduledata", "T2",
      "Read this bite: name 'Napoleon at Waterloo 2nd Edition', version 2.2, VASSAL 3.6.4, dateSaved 1643054903748, description 'SPI NAW 2nd Edition '.",
      "the identity and provenance of the module", "the identity of the edition it claims: PREP-2 M3 shows the label is wrong about its own contents",
      (), "new", "PREP-6", "Stephen Oliver"),

    A(f"{E3}/images/Map to use 3 copy.jpg", "T3",
      "PREP-2 module_art_verified_good (hex numbers 0101-2317, Time Record 3 pm, seven-slot Exited box, north-edge arrows); PREP-3 section 2 (grid fitted, OCR read the printed number in every legible cell) and section 6 (terrain and exit list recorded under terrain_module_art and explicitly NOT promoted). PREP-6 inspection t_ed3mod_map: synthetic parchment fill, modern serif hex numerals, vector hex rule, flat crimson buildings. Measured redraw_score 0.252, a FALSE scan-like verdict.",
      "the 3rd Edition hex-numbering scheme and grid geometry, carried provisionally; see disagreement B",
      "terrain of any kind, the exit list, the village set, or map extent as a printed fact",
      ("gap-fill",), "carried", "PREP-2/3", "davejm"),
    A(f"{E3}/images/CRT.jpg", "T3",
      "PREP-2 module_art_verified_good: a redraw whose 60 cells agree exactly with the printed 2nd Edition table under the Ae/Ee/De rename. PREP-6 inspection t_ed3mod_crt: modern serif on a synthetic parchment gradient, ratios retyped as 1:2 where the folio prints 1 to 2. Measured redraw_score 0.383 (borderline).",
      "corroborating the 60 CRT cells",
      "anything else printed on the sheet; the printed notation", (), "carried", "PREP-2", "davejm"),
    A(f"{E3}/images/TEC.png", "T3c",
      "PREP-2 M1: the Building row reads 'Double Defence / Except Cavalry with 2020 Rules', an explicit reference to Philip Sabin's April 2020 house rules. It also omits the doubling the 2nd Edition printed TEC grants to Woods/Road hexes and asserts that Woods/Road blocks artillery line of sight. The module's own moduledata describes it as 'Original and P Sabin 2020 & 2023 Rules'. PREP-6 inspection t_ed3mod_tec: modern serif, drop shadows, synthetic parchment hex fills, vector outlines. Measured redraw_score 0.315, a FALSE scan-like verdict caused by the synthetic parchment texture (bg_texture 11.19, the highest in the corpus).",
      "nothing",
      "E14 (3rd Edition defence doubling) and E15 (3rd Edition artillery line of sight), which is precisely what it appears to offer. It cannot be substituted, partially used, or cleaned up",
      ("contaminated",), "carried", "PREP-2", "davejm"),
    A(f"{E3}/images/Grouchy Variant.jpg", "T3c",
      "Byte-identical to Oliver's copy (PREP-6 section 5). Same defect, same file.",
      "nothing", "the Grouchy variant schedule", ("retimed",), "carried", "PREP-2", "davejm"),
    A(f"{E3}/images/NAW_*.png and NapWatvariant_*.png", "T3",
      "PREP-6 section 5: byte-identical to Oliver's 2nd Edition counter art (52 of 53 NAW_ files and all 29 variant files). This module's buildFile.xml binds pieces to 51 of them and to all 29 variant files.",
      "nothing about 3rd Edition counters",
      "the 3rd Edition counter face. These print four items; printed 3rd Ed [2.4] specifies FIVE, the fifth being the starting hex or Game-Turn of entry",
      ("out-of-edition",), "new", "PREP-6", "davejm / Stephen Oliver"),
    A(f"{E3}/images/NAW_3_10.png", "T3",
      "PREP-6 section 5: the single counter file unique to this module. Not opened this bite.",
      "nothing yet", "anything until it is opened and compared", ("unexamined",), "new", "PREP-6", "davejm"),
    A(f"{E3}/Beginning Setup.vsav", "T3",
      "PREP-6 section 5: byte-identical to Oliver's file, i.e. a 2nd Edition setup on a 594-hex field shipped inside a module whose map is the 380-hex 3rd Edition field (PREP-3 section 1).",
      "nothing about the 3rd Edition at-start",
      "the 3rd Edition setup. It cannot describe both fields",
      ("out-of-edition",), "new", "PREP-6", "davejm / Stephen Oliver"),
    A(f"{E3}/images/2020 Aid.png and 2023 Aid.png", "T5",
      "Sabin play aids shipped as module components; corroborated by the module's own moduledata description 'Original and P Sabin 2020 & 2023 Rules'. Measured redraw_score 0.976.",
      "awareness of what this module runs", "any rule", (), "new", "PREP-6", "Philip Sabin / davejm"),
    A(f"{E3}/images/Movement.png, Combat.png, Combat Preconditions.png, Combat Resolution*.png, How the Game is Won.png, Aid *.png, Advance.png, Ret*.png", "T2",
      "Module-authored rules-text panels rendered as images. Measured redraw_score 0.976 on Movement.png.",
      "agreement or disagreement with the printed booklet",
      "being a source. Each panel must be checked against pp.7-12 before it corroborates anything",
      (), "new", "PREP-6", "davejm"),
    A(f"{E3}/2020 Tweaks final.vsav, 2023 Tweaks final.vsav, N@W 2020 Rules.vsav, P Salvin *.vsav, Set up P S 2020 rules*.vsav", "T5",
      "Saved positions built for Sabin's tweak rule sets, named as such.",
      "awareness only", "any at-start or rule of either published edition", (), "new", "PREP-6", "davejm"),
    A(f"{E3}/Set Up.vsav, Set Up MT.vsav, N@W Standard.vsav, Stahndard.vsav", "T2",
      "Module-authored standard setups. Not decoded this bite.",
      "the 3rd Edition at-start, but only after decoding and only as a transcription",
      "anything until decoded", ("unexamined",), "new", "PREP-6", "davejm"),
    A(f"{E3}/buildFile.xml", "T2",
      "Read this bite for image bindings: 51 distinct NAW_ counter files and 29 variant files referenced; one reference each to Map to use 3 copy.jpg and TEC.png.",
      "module structure and piece-to-art bindings", "any game value", (), "new", "PREP-6", "davejm"),
    A(f"{E3}/moduledata", "T2",
      "Read this bite: name 'Napoleon at Waterloo', version 1.1, VASSAL 3.7.14, description 'Original and P Sabin 2020 & 2023 Rules '. The module declares its own contamination.",
      "the module's own statement that it carries Sabin's rule sets",
      "the edition it implements", (), "new", "PREP-6", "davejm"),
    A(f"{E3}/Napoleon at Waterloo V1.1.vmod", "container",
      "The packaged module, shipped alongside its own extraction.",
      "nothing; a container", "", (), "new", "PREP-6", "davejm"),

    A("literature/napoleon-at-waterloo/*_VERIFIED.md", "D",
      "Our own bite records. PREP-4 section 7 proved they are good but not infallible.",
      "internal working reference and audit trail",
      "a citation in game.json, which must point at the printed section and page (hard rule #8)",
      (), "new", "PREP-6", "The Vassal"),
    A("games/napoleon-at-waterloo/ingest/*.json", "D",
      "Machine record of the same readings.",
      "internal working reference; the data an encoding is built from, each field carrying its own evidence",
      "being cited as a source in place of the printed component", (), "new", "PREP-6", "The Vassal"),
    A("the 2nd Edition CCRR hex numbering", "D",
      "PREP-3 section 2: the printed 2nd Edition map carries no hex numbers at all (PREP-1 D11), so the coordinate system is ours. 0101 is the north-westernmost hex and carries an exit arrow; odd columns sit half a hex lower, the OPPOSITE parity to the printed 3rd Edition map.",
      "our own coordinate frame, verified twice by independent grid fits agreeing on all 44 at-start units",
      "a printed fact. No published component uses it", (), "new", "PREP-6", "The Vassal"),
]

DOC = {
    "authority": "This file is the ruling on what may be cited as evidence for what, per asset, across the whole Napoleon at Waterloo corpus. It carries forward the rulings of PREP-1 through PREP-4 unchanged and adds the assets those bites did not reach. It is itself tier D: a record, not a source.",
    "read_on": "2026-08-14",
    "produced_by": "PREP-6, games/napoleon-at-waterloo/ingest/build_authority_ladder.py",
    "companion_document": "literature/napoleon-at-waterloo/AUTHORITY_LADDER_VERIFIED.md",
    "measurement_companion": "games/napoleon-at-waterloo/ingest/asset_tier_measure.json (produced by naw_asset_tier.py)",
    "image_evidence": "C:\\VassalNaW\\prep_packs\\NAW_PREP6",
    "gap_rule": "A non-primary asset may be cited only for a claim that a primary witness independently covers. Non-primary art can corroborate; it can never fill a gap. An asset's tier never improves. What improves is the set of claims it may support, and only when a primary witness arrives to cover them.",
    "two_axes": {
        "production_method": "were these pixels made by a scanner pointed at printed paper, or by a drawing program? Answered by measurement (naw_asset_tier.py). A screening prior only.",
        "content_fidelity": "does what this asset says match what the published component says? Answered by clause-by-clause or cell-by-cell comparison against a primary witness. THIS, and only this, sets the tier.",
        "why_it_matters": "Oliver's map is digitally restored and faithful; davejm's TEC is clean digital art and contaminated. A well-made redraw is safer to read and more dangerous to trust.",
    },
    "tiers": T,
    "flags": FLAGS,
    "assets": ASSETS,
    "promotion_rule": {
        "tier_promotion": "not a thing. An asset's production history does not change. Assign the tier once, with evidence, and leave it.",
        "scope_expansion": "the only move available. A non-primary asset's citable_for list grows when a primary witness arrives covering the same content, and it grows to exactly the extent of the comparison performed: cell by cell, clause by clause, hex by hex. Sampling does not expand scope. The record must state what was compared, not that a check was done.",
        "accepted_grounds": [
            "a printed component enters our hands and is compared over the full extent relied on",
            "two independent non-primary witnesses that could not have derived from each other agree, and the claim is structural rather than a value. This is NOT a promotion, it is a provisional carry with a named blocker; PREP-6 section 5 shows how the two-witness test fails when both witnesses are one file",
            "official errata or a publisher clarification covering the claim (hard rule #9 authority order: official errata > tournament/publisher clarification > proven outcome-equivalence > declared umpired)",
        ],
        "errata_status": "No official SPI errata or Q&A for either Napoleon at Waterloo edition has been found. PREP-1 section 6 raised the question; nothing has turned up since. The printed 3rd Edition booklet prints a rules-question address, which is evidence that a Q&A channel existed, not that any answer survives.",
    },
    "standing_blockers": [
        {
            "id": "BLOCK-ED3",
            "statement": "The 3rd Edition cannot ship playable until a printed 3rd Edition map sheet AND its printed Terrain Effects Chart exist.",
            "why": "PREP-2 section 3 (E14/E15): the printed 3rd Edition rules text, read end to end from [1.0] to [9.5], never states defence doubling or artillery line-of-sight blocking, so those rules can only live on that edition's TEC, which we do not hold. PREP-3 section 6: even with a correct chart, the terrain the chart applies to would still be a redraw's opinion.",
            "why_no_substitute": "The only 3rd Edition TEC in our possession is TEC.png, tier T3c contaminated. PREP-6 section 5 removes the last plausible relief inside our holdings: most of the davejm module's other assets are Oliver's 2nd Edition files byte for byte.",
            "unblocked_by": "one thing: a scan of the printed 3rd Edition map sheet and its TEC",
        },
        {
            "id": "NOT-BLOCKED-ED2",
            "statement": "The 2nd Edition is NOT blocked.",
            "why": "Its TEC and CRT are printed on the folio map sheet and have been read twice from two independent artefacts (PREP-2 sections 1 and 5). Its rules, charts, counter photograph and map are all T0, with T1 and T2 corroboration on all of it.",
        },
    ],
    "carried_to_source_defect_register": [
        "PREP-1 D4 / PREP-2 section 4: the 2nd Edition rules text and its printed TEC disagree on whether Woods/Road hexes double the defender. Both are printed components of the same edition. Bruce's call, not an authority-ladder question.",
        "PREP-4 NAW2-SD-1: the printed 2nd Edition p.1 reads 'The act of placing a Prussian unit on the map EXTENDS one Movement Point' where the same page prints 'expends' correctly two columns later. Printed typo, harmless to play, belongs in the register.",
    ],
    "disagreements_recorded_not_resolved": [
        {
            "id": "A",
            "subject": "the word 'redraw' is used for two different things, and one of them is now a tier",
            "detail": "PREP-2 section 5 certifies Oliver's map as 'a faithful restoration'. PREP-3 section 2 writes 'The Oliver art fits cleanly because it is a redraw.' PREP-6 inspection (t_ed2mod_map) shows scanned paper tone, a soft hex rule and JPEG fringing: a restored scan, not a re-authoring. Nothing downstream broke; PREP-3 was explaining why a lattice fit cleanly.",
            "action": "the ladder carries PREP-2's tier (T1). The word needs retiring from casual use in documents that assign authority.",
        },
        {
            "id": "B",
            "subject": "the 3rd Edition hex numbering is itself a gap-fill by the Gap Rule PREP-3 applied to terrain",
            "detail": "PREP-3 section 6 refuses to promote davejm's terrain and exit list because we hold no printed 3rd Edition map, then carries the numbering forward from the same art on the ground that it is verified against numbers printed on that art. Those numbers are printed on a T3 redraw of a sheet no primary witness covers. Self-consistent, and adequate as an internal coordinate convention, but a gap-fill by any reading of the rule, and the only one in the corpus.",
            "options": [
                "treat it as ours, like the 2nd Edition CCRR convention",
                "hold it under the same blocker as the terrain",
            ],
            "action": "NOT resolved here. Both are defensible; the call belongs to the parent or to Bruce. It does not block the 2nd Edition.",
        },
        {
            "id": "C",
            "subject": "a defect in our own document, still open",
            "detail": "PREP-4 section 7 found RULEBOOK_VERIFIED.md section 3 quoting the folio as 'expends one Movement Point' where the folio prints 'extends'. Re-checked in PREP-6: still uncorrected at RULEBOOK_VERIFIED.md line 203.",
            "action": "not fixed here; PREP-5 agents are working in that file concurrently. It is the reason tier D exists: a normalisation that looks like a transcription is the failure mode our own documents are prone to.",
        },
        {
            "id": "D",
            "subject": "Oliver's CRT and TEC may be T0 candidates",
            "detail": "Both measure and look like scans of printed 1971 art, which is the definition this ladder gives T0. They are held at T1 solely because provenance is unestablished: a JPEG in a module zip could be a scan of the folio, of a reprint, or of a retouched intermediate. PREP-1 already treats an equivalent artefact, the booklet scan bundled inside a fan compilation, as T0.",
            "action": "the line between those two cases deserves an explicit ruling rather than my judgement. NOT resolved here.",
        },
    ],
    "module_defect_candidates_new_this_bite": [
        {
            "id": "M6",
            "module": "napoleon_at_waterloo_3rd_ed_davejm",
            "asset": "the module as a whole",
            "defect": "90 of 94 shared filenames are byte-identical with the Oliver 2nd Edition module. Only buildFile.xml, moduledata and the two hand-icon PNGs differ. Byte-identical: 52 of 53 NAW_ counter faces, all 29 NapWatvariant_ counters, Grouchy Variant.jpg, the 2nd Edition nameplate, graveyard.jpg, the hand boards, the VP and code charts, and Beginning Setup.vsav.",
            "consequences": [
                "the module contains no 3rd Edition counter art: its pieces print four items where printed 3rd Ed [2.4] specifies five",
                "its Beginning Setup.vsav is a 2nd Edition setup, a 594-hex field inside a module whose map is 380 hexes",
                "nothing in the shared 90 files can corroborate anything about the 3rd Edition, because nothing in them was authored for it",
            ],
            "supersedes": "PREP-2 M5 recorded the shared nameplate as SUGGESTING derivation. It is now proven.",
            "severity": "the 3rd Edition module cannot serve as a second witness for the 3rd Edition",
            "sent": False,
            "sending_rule": "Nothing goes to any module author without Bruce's explicit per-item go. THREE authors are in scope for NaW (Stephen Oliver, davejm, Christian Holm Christensen), plus Philip Sabin as author of the tweaks two of them ship.",
        },
    ],
    "platform_rule": [
        "Authority is judged per asset, never per module. The redraw boundary in this corpus runs INSIDE a single module, and the module label lies in both directions.",
        "The Gap Rule. Corroborate, never fill. If the only artefact stating a rule is non-primary, the rule is not encodable and the game is not playable: a coverage-matrix verdict, not a disclaimer.",
        "Two axes. Measure production method to triage; judge content fidelity to set the tier. Never let the first stand in for the second.",
        "The convenient artefact is the dangerous one. Three times in four bites the cleanest, best-typeset, easiest-to-read file was the one that must never be cited (rules.pdf, TEC.png, Grouchy Variant.jpg). Same failure class as SoJ's soj_errata.txt. An ingest pipeline that prefers legibility prefers contamination.",
        "Modules declare their own contamination more often than you would expect. Read moduledata first; it is free.",
        "Hash the tree before trusting a second witness. Two modules agreeing is worth nothing if one is a copy of the other.",
        "Our own documents get a tier too. They are the record of a reading, never the source.",
        "Every tier assignment names the artefact it was read off and the bite that read it. A tier without evidence is an opinion.",
    ],
    "open_for_prep5": {
        "instruction": "PREP-5's asset verdicts are received, not pre-empted. Append one row per asset to assets[] with id, tier, flags, evidence, citable_for, not_citable_for, ruling='new', bite='PREP-5'.",
        "already_ruled": "Anything read off folio p.2 or booklet p.11 is T0 and needs no adjudication: those rows exist in assets[].",
        "for_new_module_assets": "run `python naw_asset_tier.py <path>` for the triage row, then open it and look, then rule on content fidelity. The measurement never sets the tier.",
        "on_contradiction": "if a PREP-5 finding contradicts a ruling in assets[], it becomes a disagreements_recorded_not_resolved entry, not an edit.",
    },
}


def main():
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(DOC, f, indent=2)
        f.write("\n")
    tiers = {}
    for a in DOC["assets"]:
        tiers[a["tier"]] = tiers.get(a["tier"], 0) + 1
    print(f"{OUT}  assets={len(DOC['assets'])}")
    for k in sorted(tiers):
        print(f"  {k:4s} {tiers[k]}")
    print(f"  new this bite: {sum(1 for a in DOC['assets'] if a['ruling'] == 'new')}")
    print(f"  carried:       {sum(1 for a in DOC['assets'] if a['ruling'] == 'carried')}")


if __name__ == "__main__":
    main()
