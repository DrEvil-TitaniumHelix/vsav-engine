import json
import os
import re
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, r"C:\VassalArnhem")
from engine.vsav import read_vsav

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = r"C:\VassalNaW\modules\ed2_oliver"
BUILDFILE = os.path.join(MOD, "buildFile.xml")
MODULEDATA = os.path.join(MOD, "moduledata")
SAVE = os.path.join(MOD, "Beginning Setup.vsav")
MAPGRID = os.path.join(HERE, "map_grid.json")
OUT = os.path.join(HERE, "module_oob.json")
PACK = r"C:\VassalNaW\prep_packs\NAW_PREP4"
READ_ON = "2026-08-14"

BS = chr(92)
SEP = chr(27)
TAB = chr(9)

ZONE_HEXGRID = {"x0": 235.0, "y0": 4.0, "dx": 204.5999999999998, "dy": 238.4000000000001, "sideways": False}
ZONE_PATH = [(690, 360), (6322, 339), (6329, 5634), (687, 5607)]
COLS = 27
ROWS = 22
MODULE_COL_TO_OURS = -2
MODULE_ROW_TO_OURS = -1

NAME_RE = re.compile(r"^(.*?)\s*\((\d+)-(\d+)\)$")
PROTO_RE = re.compile(r"prototype;(FR|AL)(\d+)")

DISPUTED = [
    {
        "hex": "1110", "module": "British 1Gd Inf (7-4)", "prep3": "1-4",
        "third_read": "7-4, division symbol XX over a crossed box, designation '1 Gd'",
        "read_on": "the printed folio p.5 at 0.62-hex crop, rotated 180 (Allied pictures are printed "
                   "upside-down for the north player), and independently on the Oliver map restoration",
        "verdict": "MODULE CORRECT, PREP-3 MISREAD. The leading digit is an unmistakable 7 with a full "
                   "horizontal bar; the 1 in 1 Gd sits above it in the designation block, which is the likely "
                   "source of the confusion.",
        "classification": "OUR bug — a misreading in PREP-3's own PROVISIONAL at_start_pictures list. Not a "
                          "module defect and not a defect in the printed game.",
        "crop": "c_ed2_disputed_hexes.png row 1",
    },
    {
        "hex": "1210", "module": "British II Art (2-3)", "prep3": "7-3",
        "third_read": "2-3, artillery symbol (dot in a box), designation 'II'",
        "read_on": "same",
        "verdict": "MODULE CORRECT, PREP-3 MISREAD. The leading digit is a 2 with a flat foot serif; the II "
                   "designation to the right of the artillery box is the likely source of the confusion.",
        "classification": "OUR bug — PREP-3 misreading.",
        "crop": "c_ed2_disputed_hexes.png row 2",
    },
    {
        "hex": "1410", "module": "British R Art (3-3)", "prep3": "3-5",
        "third_read": "3-3, artillery symbol (dot in a box), designation 'R'",
        "read_on": "same",
        "verdict": "MODULE CORRECT, PREP-3 MISREAD. The second digit is a 3, not a 5; the hex is crossed by "
                   "the Mont St Jean road and a building block, which degrades the picture.",
        "classification": "OUR bug — PREP-3 misreading.",
        "crop": "c_ed2_disputed_hexes.png row 3",
    },
]

FINDINGS = [
    {
        "id": "P4C-1",
        "kind": "CORROBORATION",
        "text": "The module's at-start placement and the printed 2nd Ed map agree on all 44 hexes and, once "
                "the three PREP-3 misreads above are corrected, on all 44 factor pairs, all 44 sides and all "
                "44 unit types. The module additionally supplies unit designations (1 Gd, R, II, 3DB, Chs "
                "Gd, Grn Gd, Yg Gd, Gd Hvy, Gd Lite, ...) and these were checked hex by hex against the "
                "printed pictures on the two contact sheets c_ed2_atstart_allied.png and "
                "c_ed2_atstart_french.png: 44 of 44 agree, with the single omission noted in P4C-7.",
    },
    {
        "id": "P4C-2",
        "kind": "OUR BUG",
        "text": "Three of PREP-3's 44 at_start_pictures readings are wrong: 1110 is 7-4 not 1-4, 1210 is 2-3 "
                "not 7-3, 1410 is 3-3 not 3-5. All three were re-read off the primary folio for this job. "
                "map_grid.json is PREP-3's artifact and has NOT been edited by this job; the correction is "
                "reported for the parent to apply. Under the correction the 18 Allied at-start factor pairs "
                "become an exact multiset match for the module's 18 British counters, which they are not "
                "before it.",
    },
    {
        "id": "P4C-3",
        "kind": "MODULE DEFECT (corroborates PREP-2 M3, at piece level)",
        "text": "The module labelled 'Napoleon at Waterloo 2nd Edition' ships a complete Grouchy Variant "
                "subsystem: a separate 'Grouchy Variant' board holding 20 variant units, two hand maps "
                "('French Grouchy Variant', 'Allied Grouchy Variant'), and two six-card decks of numbered "
                "chits. The Grouchy Variant is a 3rd Edition rule ([9.0]) and does not exist in the 2nd "
                "Edition at all. Findings only; nothing goes to the author without Bruce's per-item go.",
    },
    {
        "id": "P4C-4",
        "kind": "MODULE DEFECT (corroborates PREP-2 M2, from art rather than text)",
        "text": "The variant counter art itself is labelled 'Var'. Printed 3rd Ed [9.1] specifies the marking "
                "'5v'. This is the same substitution PREP-2 found on the Grouchy Variant sheet, now confirmed "
                "on the counters.",
    },
    {
        "id": "P4C-7",
        "kind": "MODULE COSMETIC (minor, findings only)",
        "text": "The redrawn counters drop information the printed map pictures carry: no size-echelon marker "
                "at all (the printed pictures show XX on most units and X on the Hougoumont garrison at 1014 "
                "and on British 1Gd Cav at 1209), and no designation on the 1014 unit, where the printed "
                "picture reads 'H'. Nothing play-relevant follows — the 2nd Ed rules state that unit "
                "designations are historical only — but it means the counter art is not a complete substitute "
                "for the printed pictures.",
    },
    {
        "id": "P4C-8",
        "kind": "CORROBORATION",
        "text": "The nine Prussian reinforcement counters in the module are 5-4, 4-4, 4-4, 4-4, 4-4, 3-5, "
                "3-5, 4-3, 3-3 — an exact match, as a multiset and in the printed order, for the nine units "
                "printed at the 2 pm entry slot of the 2nd Edition Time Record (PREP-1 section 3). Third "
                "independent witness for E26.",
    },
    {
        "id": "P4C-9",
        "kind": "CLOSURE (settles JOB A's open Allied discrepancy)",
        "text": "PREP-4 JOB A read the primary counter photograph (folio p.4) and left an unresolved Allied "
                "disagreement: six factor values whose multiplicities differ between the photograph and "
                "PREP-3's map readings (1-4, 2-3, 3-3, 3-5, 7-3, 7-4), photograph sum 73 vs map sum 72. JOB "
                "A's Allied multiset is identical, value for value, to the 18 British counters this job read "
                "out of the module — and the three hexes this job found in disagreement (1110, 1210, 1410) "
                "are exactly the three values in question. Re-reading those three hexes on the printed folio "
                "map shows 7-4, 2-3 and 3-3, i.e. the printed map and the printed counters AGREE and PREP-3 "
                "misread them. This is therefore NOT a source-defect candidate in the printed game: it is our "
                "own reading error, and JOB A's unresolved item can be closed. Evidence: "
                "c_ed2_disputed_hexes.png. This file's extraction was completed before counters_photo.json "
                "was consulted, so the two witnesses are independent.",
    },
    {
        "id": "P4C-5",
        "kind": "OBSERVATION",
        "text": "buildFile.xml contains zero GridNumbering elements. The module therefore has no hex "
                "identities of any kind, exactly as the printed 2nd Ed map has none (PREP-1 D11). Every hex "
                "reference in this file is OURS, computed from pixel positions; there is no module hex name "
                "to disagree with.",
    },
    {
        "id": "P4C-6",
        "kind": "OBSERVATION",
        "text": "The module enforces nothing about reinforcement timing. All nine Prussians sit on the Main "
                "Map outside the Battlefield zone from the beginning of the save, movable at any time. This "
                "is a coverage-matrix input, not a defect in a piece-pusher.",
    },
]


def split_unesc(s, ch, maxn=None):
    out, cur, i = [], [], 0
    while i < len(s):
        c = s[i]
        if c == BS and i + 1 < len(s):
            cur.append(c)
            cur.append(s[i + 1])
            i += 2
            continue
        if c == ch and (maxn is None or len(out) < maxn):
            out.append("".join(cur))
            cur = []
            i += 1
            continue
        cur.append(c)
        i += 1
    out.append("".join(cur))
    return out


def unit_type(name):
    n = name.lower()
    if " art" in n:
        return "artillery"
    if " cav" in n:
        return "cavalry"
    if " inf" in n or "infantry" in n or " gd " in n or n.endswith(" gd"):
        return "infantry"
    return "unknown"


def parse_name(name):
    m = NAME_RE.match(name)
    if not m:
        return name, None, None
    return m.group(1), int(m.group(2)), int(m.group(3))


def read_moduledata():
    x = ET.parse(MODULEDATA).getroot()
    return {c.tag: (c.text or "") for c in x}


def read_roster():
    root = ET.parse(BUILDFILE).getroot()
    out = []
    stack = [(root, [])]
    while stack:
        el, path = stack.pop()
        tag = el.tag.rsplit(".", 1)[-1]
        nm = el.get("entryName") or el.get("name") or ""
        if tag == "PieceSlot":
            txt = el.text or ""
            img, disp = None, None
            for f in txt.split(TAB):
                if f.startswith("piece;"):
                    p = f.split(";")
                    if len(p) >= 5:
                        img = p[3]
                        disp = p[4].split("/")[0]
            pm = PROTO_RE.search(txt)
            side_proto = None
            if "prototype;French" in txt:
                side_proto = "French"
            elif "prototype;Allied" in txt:
                side_proto = "Allied"
            out.append({
                "gpid": el.get("gpid"),
                "list": path[-1] if path else "",
                "entry_name": el.get("entryName"),
                "piece_name": disp,
                "image": img,
                "prototype_side": side_proto,
                "prototype_strength": int(pm.group(2)) if pm else None,
                "prototype_tag": (pm.group(1) + pm.group(2)) if pm else None,
            })
            continue
        for c in el:
            stack.append((c, path + [nm] if nm else path))
    return out


def read_save():
    plain, md, sd = read_vsav(SAVE)
    lines = plain.split(SEP)
    pieces, meta = [], []
    for l in lines:
        if not l.startswith("+/"):
            meta.append(l)
            continue
        parts = split_unesc(l, "/", 3)
        pid, typ, st = parts[1], parts[2], parts[3]
        tt, ss = typ.split(TAB), st.split(TAB)
        if tt[0] == "stack":
            continue
        img = name = None
        for f in tt:
            if f.startswith("piece;"):
                p = f.split(";")
                if len(p) >= 5:
                    img, name = p[3], p[4]
        last = ss[-1].split(";")
        if len(last) < 3:
            continue
        try:
            x, y = int(last[1]), int(last[2])
        except ValueError:
            continue
        pieces.append({"pid": pid, "map": last[0], "x": x, "y": y, "image": img,
                       "name": name, "piece_id": last[3] if len(last) > 3 else None,
                       "is_deck": tt[0].startswith("deck")})
    return pieces, meta, md.decode("utf-8", "replace"), sd.decode("utf-8", "replace")


def module_indices(x, y):
    g = ZONE_HEXGRID
    ci = (x - g["x0"]) / g["dx"]
    c = int(round(ci))
    off = g["dy"] / 2.0 if c % 2 == 1 else 0.0
    ri = (y - g["y0"] - off) / g["dy"]
    r = int(round(ri))
    cx = g["x0"] + c * g["dx"]
    cy = g["y0"] + r * g["dy"] + off
    return c, r, round(x - cx, 2), round(y - cy, 2)


def ours_from_px(x, y, gp):
    ci = (x - gp["x0"]) / gp["dx"]
    c = int(round(ci)) + 1
    off = gp["dy"] / 2.0 if ((c % 2 == 0) == gp["even_down"]) else 0.0
    ri = (y - gp["y0"] - off) / gp["dy"]
    r = int(round(ri)) + 1
    cx = gp["x0"] + (c - 1) * gp["dx"]
    cy = gp["y0"] + (r - 1) * gp["dy"] + off
    return c, r, round(x - cx, 2), round(y - cy, 2)


def in_field(c, r):
    return 1 <= c <= COLS and 1 <= r <= ROWS


def main():
    mg = json.load(open(MAPGRID, encoding="utf-8"))
    ed2 = mg["editions"]["2nd"]
    gp = ed2["grid_px"]["oliver"]
    prep3 = ed2["at_start_pictures"]["hexes"]

    md = read_moduledata()
    roster = read_roster()
    pieces, meta, save_md, save_sd = read_save()

    players = [m for m in meta if m.startswith("PLAYER")]
    boards = [m for m in meta if "BoardPicker" in m]

    units, offfield, variant, markers = [], [], [], []
    resid = []
    for p in pieces:
        if p["is_deck"]:
            continue
        base, cs, ma = parse_name(p["name"] or "")
        rec = {
            "piece_id": p["piece_id"],
            "module_name": p["name"],
            "designation": base,
            "combat_strength": cs,
            "movement_allowance": ma,
            "type": unit_type(p["name"] or ""),
            "image": p["image"],
            "module_map": p["map"],
            "module_px": [p["x"], p["y"]],
        }
        if p["map"] != "Main Map":
            rec["module_hex"] = None
            rec["ccrr"] = None
            variant.append(rec)
            continue
        mc, mr, mdx, mdy = module_indices(p["x"], p["y"])
        oc, orr, odx, ody = ours_from_px(p["x"], p["y"], gp)
        rec["module_hexgrid_index"] = [mc, mr]
        rec["module_snap_residual_px"] = [mdx, mdy]
        rec["ccrr_residual_px"] = [odx, ody]
        rec["ccrr"] = f"{oc:02d}{orr:02d}" if in_field(oc, orr) else None
        rec["ccrr_from_module_index"] = (
            f"{mc + MODULE_COL_TO_OURS:02d}{mr + MODULE_ROW_TO_OURS:02d}"
            if in_field(mc + MODULE_COL_TO_OURS, mr + MODULE_ROW_TO_OURS) else None)
        if cs is None:
            markers.append(rec)
        elif rec["ccrr"] is not None:
            resid.append((abs(odx), abs(ody), abs(mdx), abs(mdy)))
            units.append(rec)
        else:
            offfield.append(rec)

    side_of = {}
    for r in roster:
        if r["piece_name"]:
            side_of.setdefault(r["piece_name"], r)
    for rec in units + offfield + variant:
        r = side_of.get(rec["module_name"])
        if r:
            rec["side"] = "French" if r["prototype_side"] == "French" else "Allied"
            rec["contingent"] = r["list"]
            rec["prototype_tag"] = r["prototype_tag"]
            rec["prototype_strength"] = r["prototype_strength"]
            rec["strength_agrees_with_prototype"] = (r["prototype_strength"] == rec["combat_strength"])
        else:
            rec["side"] = "French" if (rec["module_name"] or "").startswith("French") else "Allied"
            rec["contingent"] = None
            rec["prototype_tag"] = None
            rec["prototype_strength"] = None
            rec["strength_agrees_with_prototype"] = None

    mod_by_hex = {}
    for u in units:
        mod_by_hex.setdefault(u["ccrr"], []).append(u)

    p3 = {}
    for s in ("allied", "french"):
        for h, v in prep3[s].items():
            p3[h] = (s, v)

    agree, disagree, only_module, only_prep3 = [], [], [], []
    for h in sorted(set(mod_by_hex) | set(p3)):
        mu = mod_by_hex.get(h, [])
        pv = p3.get(h)
        if mu and pv:
            u = mu[0]
            mside = "french" if u["side"] == "French" else "allied"
            mfac = f"{u['combat_strength']}-{u['movement_allowance']}"
            row = {"hex": h, "module_unit": u["module_name"], "module_factors": mfac,
                   "module_side": mside, "prep3_factors": pv[1], "prep3_side": pv[0],
                   "stacked_in_module": len(mu)}
            if mfac == pv[1] and mside == pv[0]:
                agree.append(row)
            else:
                disagree.append(row)
        elif mu:
            only_module.append({"hex": h, "module_unit": mu[0]["module_name"],
                                "module_factors": f"{mu[0]['combat_strength']}-{mu[0]['movement_allowance']}",
                                "module_side": "french" if mu[0]["side"] == "French" else "allied"})
        else:
            only_prep3.append({"hex": h, "prep3_factors": pv[1], "prep3_side": pv[0]})

    maxres = {
        "ccrr_dx": max((r[0] for r in resid), default=None),
        "ccrr_dy": max((r[1] for r in resid), default=None),
        "module_snap_dx": max((r[2] for r in resid), default=None),
        "module_snap_dy": max((r[3] for r in resid), default=None),
    }

    doc = {
        "authority": "module-derived, corroborating only",
        "produced_by": "PREP-4 JOB C, games/napoleon-at-waterloo/ingest/naw_module_oob.py",
        "read_on": READ_ON,
        "edition": "2nd",
        "never_promotes": "Nothing in this file may overwrite a printed-source reading. The printed 1971 SPI "
                          "folio (NapoleonatWaterloo.pdf) is primary; this is a third independent witness.",
        "module": {
            "path": MOD,
            "name": md.get("name"),
            "version": md.get("version"),
            "vassal_version": md.get("VassalVersion"),
            "description": md.get("description"),
            "date_saved_epoch_ms": md.get("dateSaved"),
            "author_from_save_player_line": players,
            "save_file": os.path.basename(SAVE),
            "save_moduledata_version": re.search(r"<version>(.*?)</version>", save_md).group(1)
            if re.search(r"<version>(.*?)</version>", save_md) else None,
            "save_vassal_version": re.search(r"<VassalVersion>(.*?)</VassalVersion>", save_md).group(1)
            if re.search(r"<VassalVersion>(.*?)</VassalVersion>", save_md) else None,
            "boards_in_save": boards,
        },
        "authority_tiers": {
            "images/NAW_*.png (counter art)": {
                "tier": "REDRAW",
                "reason": "194x194 digital redraws, not scans of the punched 1971 counters: flat fills, rounded "
                          "corners with a red bleed border, modern sans-serif digits and vector-clean NATO "
                          "symbols, set against the visibly hand-printed thin-line pictures on the map sheet. "
                          "Usable only as a corroborating witness, and only because its factor pairs, unit "
                          "types and designations agree with the printed map pictures at 44 of 44 at-start "
                          "hexes. The national colours it uses (French blue / British red / Prussian pale "
                          "green) do match the printed scheme stated in the 2nd Ed rules.",
            },
            "images/NapWatvariant_*.png (Grouchy variant counter art)": {
                "tier": "REDRAW, and out-of-edition — must not be used for the 2nd Edition at all",
                "reason": "the Grouchy Variant does not exist in the 2nd Edition (PREP-2 defect M3). These "
                          "counters belong to a 3rd Edition subsystem. They are additionally labelled 'Var' "
                          "where printed 3rd Ed [9.1] specifies '5v', which independently corroborates PREP-2 "
                          "defect M2 from the counter art rather than from the variant sheet's text.",
            },
            "buildFile.xml PieceSlot names and prototypes": {
                "tier": "module-authored transcription (self-consistent; fidelity established only by "
                        "agreement with printed art)",
                "reason": "the factor pair is typed into the piece name by the module author and repeated as a "
                          "prototype tag FRn/ALn carrying the combat strength only. It is a transcription of "
                          "the counter art, not the art itself. Its evidential value is that the two "
                          "module-internal copies cross-check: all 53 units agree name-vs-prototype.",
            },
            "Beginning Setup.vsav": {
                "tier": "module-authored transcription of the printed at-start pictures",
                "reason": "Oliver placed every at-start counter by hand onto his map restoration. It is an "
                          "independent human read of the same printed pictures PREP-3 read, so it corroborates "
                          "or contradicts, but it never outranks the printed map.",
            },
            "images/Nap at Waterloo map 20mm hexes.jpg": {
                "tier": "faithful-reproduction (PREP-2 module_art_verified_good)",
                "reason": "already certified in PREP-2 as a faithful restoration of the printed 2nd Ed map; it "
                          "is the coordinate frame this job maps into.",
            },
        },
        "hex_mapping": {
            "problem": "the module declares NO hex numbering of any kind, matching the printed 2nd Ed map "
                       "(discrepancy D11). There are zero GridNumbering elements in buildFile.xml, so a module "
                       "hex has no name — only a pixel position on the board image.",
            "module_coordinates_are": "board-image pixels on 'Nap at Waterloo map 20mm hexes.jpg' (6623x5648), "
                                      "board placed at BoardPicker grid 0,0 so piece x,y are raw image pixels; "
                                      "plus the lattice index (col,row) of the module's own declared HexGrid.",
            "module_declared_hexgrid": ZONE_HEXGRID,
            "module_zone_polygon": ZONE_PATH,
            "our_grid_px_oliver": gp,
            "method": [
                "1. decode Beginning Setup.vsav and take each piece's BasicPiece state (map;x;y).",
                "2. route A: snap x,y to the module's own declared HexGrid lattice "
                "(x0=235 y0=4 dx=204.6 dy=238.4, odd column index offset +dy/2) giving (col_idx,row_idx).",
                "3. route B: snap the same x,y to PREP-3's independently fitted grid for the SAME image "
                "(ed2oliver_canon: x0=833.95 y0=487.0 dx=205.55 dy=238.0 even_down=false) giving our CCRR.",
                "4. the two lattices are the same lattice with a different origin: route A col_idx 3 = our "
                "column 01 and row_idx 1 = our row 01, i.e. our_col = col_idx - 2, our_row = row_idx - 1. "
                "Both routes are computed for every unit and must agree.",
            ],
            "parity_check": "the module's HexGrid offsets ODD column indices downward by dy/2; our CCRR offsets "
                            "ODD columns downward. After the -2 column shift odd maps to odd, so the parity "
                            "agrees and no half-hex stagger is introduced. This was the stated risk and it is "
                            "closed by the residuals below, which would explode to ~dy/2 = 119 px under a "
                            "parity error.",
            "independent_anchor": "the module's Battlefield zone polygon spans x 687..6329, y 339..5634. Our "
                                  "CCRR column 01 centre sits at x=833.95 and column 27 at x=6178.2; with a "
                                  "circumradius of dx/1.5 = 137 px the field spans x 697..6315 — inside the "
                                  "module's own declared battlefield to within 14 px at both ends, on 27 "
                                  "columns. A one-column error would show as a 205 px overhang.",
            "residual_px_max": maxres,
            "routes_agree": all(u["ccrr"] == u["ccrr_from_module_index"] for u in units),
            "confidence": "HIGH. Two independently derived lattices for the same image agree on every unit; "
                          "snap residuals are sub-pixel to a few px against a 205x238 px hex; the field extent "
                          "matches the module's own zone polygon; and the resulting hex set is compared below "
                          "against PREP-3 without any tuning (the grid parameters were fixed in PREP-3 for "
                          "terrain, before this job existed).",
        },
        "counts": {
            "roster_piece_slots": len(roster),
            "pieces_in_save": len(units) + len(offfield) + len(variant) + len(markers),
            "at_start_on_field": len(units),
            "off_field_staged_prussians": len(offfield),
            "grouchy_variant_units": sum(1 for u in variant if u["combat_strength"] is not None),
            "grouchy_variant_number_chits": sum(1 for u in variant if u["combat_strength"] is None),
            "markers": len(markers),
            "at_start_by_side": {
                "french": sum(1 for u in units if u["side"] == "French"),
                "allied": sum(1 for u in units if u["side"] == "Allied"),
            },
        },
        "at_start": sorted(units, key=lambda u: (u["side"], u["ccrr"])),
        "off_field_staged": sorted(offfield, key=lambda u: u["module_px"][1]),
        "markers": markers,
        "other_maps": sorted(variant, key=lambda u: (u["module_map"], u["module_name"] or "")),
        "roster": roster,
        "comparison_vs_prep3": {
            "prep3_source": "map_grid.json editions.2nd.at_start_pictures.hexes (PROVISIONAL, printed map, "
                            "one witness)",
            "agree": agree,
            "disagree": disagree,
            "only_in_module": only_module,
            "only_in_prep3": only_prep3,
            "tally": {"agree": len(agree), "disagree": len(disagree),
                      "only_in_module": len(only_module), "only_in_prep3": len(only_prep3)},
            "hex_set_verdict": "the two witnesses place units on exactly the same 44 hexes, 18 Allied and 26 "
                               "French, one unit per hex, with zero hexes unique to either side. This is the "
                               "corroboration PREP-4 was called to establish, and it also proves the hex "
                               "mapping: a one-column or one-row error would have produced 44 hexes unique to "
                               "each witness and zero overlap.",
        },
        "disputed_hexes": DISPUTED,
        "reinforcements": {
            "printed_time_record_2nd_ed": ["5-4", "4-4", "4-4", "4-4", "4-4", "3-5", "3-5", "4-3", "3-3"],
            "module_prussian_contingent": sorted(
                f"{u['combat_strength']}-{u['movement_allowance']}" for u in offfield),
            "match": sorted(["5-4", "4-4", "4-4", "4-4", "4-4", "3-5", "3-5", "4-3", "3-3"]) ==
                     sorted(f"{u['combat_strength']}-{u['movement_allowance']}" for u in offfield),
            "note": "the module parks all nine Prussians on the Main Map east of its own Battlefield zone "
                    "(x 6485-6496, outside the hex field) as a manual staging area. Nothing in the module "
                    "schedules or gates their turn-2 entry.",
        },
        "strength_totals": {
            "french_at_start": sum(u["combat_strength"] for u in units if u["side"] == "French"),
            "allied_at_start": sum(u["combat_strength"] for u in units if u["side"] == "Allied"),
            "prussian_reinforcements": sum(u["combat_strength"] for u in offfield),
            "note": "module-derived arithmetic; relevant to the printed 40-point victory and demoralization "
                    "thresholds but not itself a printed reading.",
        },
        "findings": sorted(FINDINGS, key=lambda f: f["id"]),
    }
    json.dump(doc, open(OUT, "w", encoding="utf-8"), indent=1)
    print(OUT)
    print("roster slots", len(roster), "| at-start on field", len(units),
          "| off-field", len(offfield), "| other maps", len(variant), "| markers", len(markers))
    print("routes agree:", doc["hex_mapping"]["routes_agree"], "| max residual px", maxres)
    t = doc["comparison_vs_prep3"]["tally"]
    print("vs PREP-3:", t)
    for r in disagree:
        print("  DISAGREE", r)
    for r in only_module:
        print("  ONLY MODULE", r)
    for r in only_prep3:
        print("  ONLY PREP3", r)
    bad = [u for u in units + offfield if u["strength_agrees_with_prototype"] is False]
    print("name-vs-prototype strength mismatches:", len(bad))
    for u in bad:
        print("  ", u["module_name"], u["prototype_tag"])


def pack():
    import math
    from PIL import Image, ImageDraw
    from naw_map import source, hex_center

    Image.MAX_IMAGE_PIXELS = None
    os.makedirs(PACK, exist_ok=True)
    doc = json.load(open(OUT, encoding="utf-8"))
    gf = json.load(open(r"C:\VassalNaW\grids\ed2_canon.json"))
    go = json.load(open(r"C:\VassalNaW\grids\ed2oliver_canon.json"))
    imgdir = os.path.join(MOD, "images")

    def hexcrop(key, g, hid, rot, flip, pad=0.62, cell=380):
        im = source(key)
        if rot:
            im = im.rotate(rot, expand=True)
        c, r = int(hid[:2]), int(hid[2:])
        x, y = hex_center(g, c, r)
        rad = g["dx"] * pad
        t = im.crop((int(x - rad), int(y - rad), int(x + rad), int(y + rad)))
        t = t.resize((cell, cell), Image.LANCZOS)
        return t.rotate(180) if flip else t

    cell = 380
    rows = []
    for d in doc["disputed_hexes"]:
        h = d["hex"]
        u = [x for x in doc["at_start"] if x["ccrr"] == h][0]
        rows.append((h, f"{d['module']}   PREP-3 read {d['prep3']}   -> {d['third_read']}", u["image"], True))
    sheet = Image.new("RGB", (cell * 3, (cell + 24) * len(rows)), (255, 255, 255))
    dr = ImageDraw.Draw(sheet)
    for i, (h, lab, cimg, flip) in enumerate(rows):
        y = i * (cell + 24)
        dr.text((6, y + 6), f"{h}  folio | oliver map | module counter    {lab}", fill=(0, 0, 0))
        sheet.paste(hexcrop("ed2folio", gf, h, 270, flip, cell=cell), (0, y + 24))
        sheet.paste(hexcrop("ed2oliver", go, h, 0, flip, cell=cell), (cell, y + 24))
        sheet.paste(Image.open(os.path.join(imgdir, cimg)).convert("RGB").resize((cell, cell), Image.LANCZOS),
                    (cell * 2, y + 24))
    p = os.path.join(PACK, "c_ed2_disputed_hexes.png")
    sheet.save(p)
    print(p, sheet.size)

    for side, flip, cols in (("Allied", True, 6), ("French", False, 6)):
        us = [u for u in doc["at_start"] if u["side"] == side]
        cw = 190
        n = len(us)
        nrows = (n + cols - 1) // cols
        s = Image.new("RGB", (cols * cw * 2, nrows * (cw + 26)), (255, 255, 255))
        d2 = ImageDraw.Draw(s)
        for i, u in enumerate(us):
            x = (i % cols) * cw * 2
            y = (i // cols) * (cw + 26)
            d2.text((x + 4, y + 3), f"{u['ccrr']} {u['module_name']}", fill=(0, 0, 0))
            d2.text((x + 4, y + 14), f"{u['type']}", fill=(90, 90, 90))
            s.paste(hexcrop("ed2folio", gf, u["ccrr"], 270, flip, cell=cw), (x, y + 26))
            s.paste(Image.open(os.path.join(imgdir, u["image"])).convert("RGB").resize((cw, cw), Image.LANCZOS),
                    (x + cw, y + 26))
        p = os.path.join(PACK, f"c_ed2_atstart_{side.lower()}.png")
        s.save(p)
        print(p, s.size)

    us = doc["off_field_staged"]
    cw = 190
    s = Image.new("RGB", (len(us) * cw, cw + 30), (255, 255, 255))
    d3 = ImageDraw.Draw(s)
    for i, u in enumerate(us):
        d3.text((i * cw + 4, 4), u["module_name"], fill=(0, 0, 0))
        d3.text((i * cw + 4, 16), f"px {u['module_px']}", fill=(90, 90, 90))
        s.paste(Image.open(os.path.join(imgdir, u["image"])).convert("RGB").resize((cw, cw), Image.LANCZOS),
                (i * cw, 30))
    p = os.path.join(PACK, "c_ed2_prussian_nine.png")
    s.save(p)
    print(p, s.size)

    im = source("ed2oliver").convert("RGB").copy()
    d4 = ImageDraw.Draw(im)
    occ = {u["ccrr"]: u for u in doc["at_start"]}
    rad = go["dx"] / 1.5
    for c in range(1, COLS + 1):
        for r in range(1, ROWS + 1):
            x, y = hex_center(go, c, r)
            pts = [(x + rad * math.cos(math.radians(a)), y + rad * math.sin(math.radians(a)))
                   for a in range(0, 360, 60)]
            hid = f"{c:02d}{r:02d}"
            d4.line(pts + [pts[0]], fill=(255, 0, 0) if hid in occ else (150, 150, 255), width=3)
    for u in doc["at_start"]:
        x, y = u["module_px"]
        d4.ellipse([x - 26, y - 26, x + 26, y + 26],
                   fill=(0, 0, 255) if u["side"] == "French" else (220, 0, 0))
        d4.text((x - 60, y + 34), f"{u['ccrr']} {u['combat_strength']}-{u['movement_allowance']}",
                fill=(0, 0, 0))
    w = 2400
    im = im.resize((w, int(im.size[1] * w / im.size[0])), Image.LANCZOS)
    p = os.path.join(PACK, "c_ed2_setup_overlay.png")
    im.save(p)
    print(p, im.size)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "pack":
        pack()
    else:
        main()
