"""PREP-5 support tool: build the Siege of Jerusalem counter + marker manifest.

Reads Rob McRae's v3.0.0 module (buildFile.xml, images/, the seven scenario
.vsav setups) and emits one JSON describing every game piece the module can
produce, with its FRONT face, its BACK face, and where each face is evidenced.

Why this exists (PREP-5 brief): rule 2.6 prints Ramp/Wreck, Rout/Panic,
Breach/Damage and Broken-Testudo/Elim as ONE two-sided counter each, so a
census of module image filenames over-counts the physical component mix.
"Component genuinely absent from the counter mix" is one of only three valid
UNREACHABLE evidences in the coverage matrix, so the mix has to be measured,
not guessed.

Nothing here writes module art into the repo — only names, sizes and counts.

Usage:
    python counters_manifest.py                      # -> counters_manifest.json
    python counters_manifest.py --sheets DIR         # + front/back contact sheets (art; keep out of the repo)
    python counters_manifest.py --module C:\\VassalSoJ\\extracted --out foo.json
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MODULE = r"C:\VassalSoJ\extracted"

# piece;<cloneKey>;<cloneCmd>;<image>;<name>/   -- the BasicPiece, i.e. the FRONT face
BASIC = re.compile(r"piece;[^;]*;[^;]*;([^;]*);([^/\t]*)/")
IMAGE = re.compile(r"[\w \-'\.\(\)#&+]+\.(?:png|gif|jpg|jpeg)", re.I)
# VASSAL built-ins that live in the engine's own jar, not in the module
VASSAL_BUILTIN = {"camera.gif", "unmoved.gif", "zoom.png", "zoomIn.gif", "zoomOut.gif"}

EMB2_IMAGE_FIELD = 16  # index of the image-list field inside an emb2 (Layer) trait
EMB2_NAME_FIELD = 19  # the Layer's own name, e.g. "Eliminated Arty"
PREFIX = re.compile(r"^\+/[^/]*/")  # every definition opens with "+/null/" (or "+/<id>/" in a save)


def traits(defn: str):
    """Split a VASSAL piece definition into its trait segments.

    The leading "+/null/" must come off first, or the piece's FIRST trait is
    invisible to any startswith() test — which silently loses the Flip layer on
    every marker whose definition opens with one (Rout, Wall Damage, Escalade).
    """
    return [seg.rstrip("\\") for seg in PREFIX.sub("", defn).split("\t")]


def emb2_layers(defn: str):
    """Every Layer on a piece: (command name, [images], [level names])."""
    out = []
    for seg in traits(defn):
        if not seg.startswith("emb2;"):
            continue
        f = seg.split(";")
        if len(f) <= EMB2_IMAGE_FIELD:
            continue
        imgs = [i.strip() for i in f[EMB2_IMAGE_FIELD].split(",")]
        names = [n.strip() for n in f[EMB2_IMAGE_FIELD + 1].split(",")] if len(f) > EMB2_IMAGE_FIELD + 1 else []
        out.append({"command": f[1], "images": imgs, "level_names": names,
                    "menu_name": f[EMB2_NAME_FIELD] if len(f) > EMB2_NAME_FIELD else ""})
    return out


def prototypes_used(defn: str):
    return [seg.split(";", 1)[1].replace("\\/", "/").strip()
            for seg in traits(defn) if seg.startswith("prototype;")]


def slot_walk(root):
    """(widget path, entry name, definition) for every PieceSlot in the module."""
    out = []

    def rec(e, path):
        tag = e.tag.split(".")[-1]
        nm = e.get("entryName") or e.get("name") or ""
        if tag == "PieceSlot":
            out.append(("/".join(path), nm, (e.text or "").strip()))
            return
        for c in e:
            rec(c, path + [f"{tag}:{nm}"])

    rec(root, [])
    return out


def classify(path: str, name: str):
    """faction / group / kind for a palette slot."""
    faction = ("roman" if "BoxWidget:Romans" in path else
               "judaean" if "BoxWidget:Judaean" in path else
               "marker" if "ListWidget:Markers" in path else
               "misc")
    legion = ""
    m = re.search(r"ListWidget:(V|X|XII|XV) Legion", path)
    if m:
        legion = m.group(1)
    kind = path.rsplit("ListWidget:", 1)[-1] if "ListWidget:" in path else path.rsplit(":", 1)[-1]
    if legion and kind.endswith(" Legion"):
        kind = "Legion HQ / attached"
    return faction, legion, kind


def read_palette(build_root):
    """Every counter the module can produce, with front face and flip (back) face."""
    rows = []
    for path, name, defn in slot_walk(build_root):
        if "TabWidget:Game Pieces" not in path:
            continue
        m = BASIC.search(defn)
        front = (m.group(1).strip() if m else "")
        layers = emb2_layers(defn)
        flip = next((l for l in layers if l["command"].lower().startswith("flip")), None)
        back = ""
        if flip:
            # a layer image of " " is a real thing in this module: the layer exists,
            # is named, and draws nothing (see the Broken Testudo marker)
            back = next((i.strip() for i in flip["images"] if i.strip()), "")
        other = [l for l in layers if l is not flip]
        faction, legion, kind = classify(path, name)
        rows.append({
            # slot names in this module are not clean: nine X-Legion slots carry a
            # trailing space, so a raw name join silently drops them
            "name": " ".join(name.split()),
            "name_raw": name,
            "faction": faction,
            "legion": legion,
            "kind": kind,
            "front_image": front,
            "back_image": back,
            "back_is_blank": bool(flip) and not back,
            "flip_layer_name": (flip or {}).get("menu_name", ""),
            "overlay_layers": [{"name": l["menu_name"] or l["command"],
                                "images": [i for i in l["images"] if i]} for l in other],
            "prototypes": prototypes_used(defn),
            "widget_path": path.split("TabWidget:Game Pieces/")[-1],
        })
    rows.sort(key=lambda r: (r["faction"], r["legion"], r["kind"], r["name"]))
    return rows


def read_prototype_props(build_root):
    """PROP traits carry the module's encoding of the Weapons Effect ladders."""
    props = {}
    for e in build_root.iter():
        if not e.tag.endswith("PrototypeDefinition"):
            continue
        nm = e.get("name") or ""
        vals = []
        for seg in traits((e.text or "").strip()):
            if seg.startswith("PROP;"):
                f = seg.split(";")
                # field 3 is the command menu: "<label>:<key>:P\,<value>" items,
                # comma-separated, with the commas inside a keystroke escaped as "\,"
                menu = f[3] if len(f) > 3 else ""
                opts = []
                for item in re.split(r"(?<!\\),", menu):
                    if ":" not in item:
                        continue
                    label = item.split(":", 1)[0].strip()
                    mv = re.search(r"\\,(-?\d+)\s*$", item)
                    if label and mv:
                        opts.append({"label": label, "value": int(mv.group(1))})
                vals.append({"property": f[1] if len(f) > 1 else "", "options": opts})
            elif seg.startswith("setprop;"):
                f = seg.split(";")
                mv = re.search(r"I\\?,(-?\d+)", seg)
                vals.append({"property": f[1] if len(f) > 1 else "",
                             "set_value": int(mv.group(1)) if mv else None,
                             "description": f[4] if len(f) > 4 else ""})
        if vals:
            props[nm] = vals
    return props


def read_saves(module_dir):
    """Piece census of every scenario setup shipped with the module."""
    sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..")))
    from engine.vsav import decode_saved  # noqa: E402  (repo-local codec)

    out = {}
    for fn in sorted(f for f in os.listdir(module_dir) if f.lower().endswith(".vsav")):
        with zipfile.ZipFile(os.path.join(module_dir, fn)) as z:
            plain = decode_saved(z.read("savedGame").decode("latin-1"))
        pieces = collections.Counter()
        maps = collections.Counter()
        trays = collections.defaultdict(collections.Counter)
        for entry in plain.split("+/")[1:]:
            tail = entry.rsplit("\t", 1)[-1]
            mp = tail.split(";")[0].split("/")[-1]
            maps[mp] += 1
            m = BASIC.search(entry)
            if m and m.group(2).strip():
                nm = " ".join(m.group(2).split())
                pieces[nm] += 1
                if mp in TRAY_MAPS:
                    trays[mp][nm] += 1
        out[fn] = {"entries": len(plain.split("+/")) - 1,
                   "by_map": dict(sorted(maps.items())),
                   "by_piece": dict(sorted(pieces.items())),
                   "trays": {k: dict(sorted(v.items())) for k, v in sorted(trays.items())}}
    return out


# The campaign setup keeps every counter of the full game stacked at fixed points
# on two off-map "tray" windows — one per side.  That tray is the closest thing
# the module has to the printed counter mix, and for the XII Legion the printed
# Gallus card confirms it exactly.
TRAY_MAPS = {"Campaign Romans", "Campaign"}
CAMPAIGN_SAVE = "The Full Siege Campaign 70 AD.vsav"


def counter_mix(palette, saves):
    if CAMPAIGN_SAVE not in saves:
        return {"error": f"{CAMPAIGN_SAVE} not found in module"}
    units = {r["name"] for r in palette if r["faction"] in ("roman", "judaean")}
    out = {"_source": f"{CAMPAIGN_SAVE}: the two supply trays of the full campaign setup",
           "_caveat": "module evidence, not a scan of the printed countersheet. Confirmed against the "
                      "printed card for the XII Legion (Gallus intro = 65 Roman counters, exact match). "
                      "MARKERS are absent from both trays — the module treats them as an unlimited "
                      "palette, so it carries NO evidence about the printed marker counts.",
           "trays": {}}
    for tray, census in saves[CAMPAIGN_SAVE]["trays"].items():
        counters = {k: v for k, v in census.items() if k in units}
        out["trays"][tray] = {"unit_counters": sum(counters.values()), "by_piece": counters}
    # shared (non-legion) Roman equipment lives in the Roman tray too
    romans = saves[CAMPAIGN_SAVE]["trays"].get("Campaign Romans", {})
    out["shared_roman_equipment"] = {k: romans.get(k, 0) for k in ("Armored Tower", "Ramp")}
    out["total_unit_counters"] = sum(t["unit_counters"] for t in out["trays"].values())
    return out


def art_index(module_dir):
    from PIL import Image
    d = os.path.join(module_dir, "images")
    out = {}
    for f in sorted(os.listdir(d)):
        try:
            with Image.open(os.path.join(d, f)) as im:
                out[f] = {"w": im.size[0], "h": im.size[1]}
        except Exception as exc:  # pragma: no cover - corrupt art would be a finding
            out[f] = {"error": str(exc)}
    return out


def face_checks(palette, art):
    """Front/back consistency findings — the module's own art defects."""
    findings = []
    for r in palette:
        f, b = r["front_image"], r["back_image"]
        if f and f not in art:
            findings.append({"piece": r["name"], "issue": "front image missing from images/", "detail": f})
        if b and b not in art:
            findings.append({"piece": r["name"], "issue": "back image missing from images/", "detail": b})
        if r["back_is_blank"]:
            findings.append({"piece": r["name"], "issue": "flip layer defined with a blank image",
                             "detail": f"flip layer named '{r['flip_layer_name']}' shows nothing"})
        # Unit counters follow one naming law: <front>.gif flips to <front>_Reverse.gif.
        # Markers legitimately break it (Rout->Panic, Turn Roman->Judaean, Damage_1->Damage_2),
        # so the check only runs where the law applies.
        if f and b and r["faction"] in ("roman", "judaean"):
            stem_f = re.sub(r"\.(png|gif|jpg|jpeg)$", "", f, flags=re.I)
            stem_b = re.sub(r"_(Reverse|Rev|R)$", "", re.sub(r"\.(png|gif|jpg|jpeg)$", "", b, flags=re.I),
                            flags=re.I)
            if stem_b.lower() not in stem_f.lower() and stem_f.lower() not in stem_b.lower():
                findings.append({"piece": r["name"], "issue": "back face belongs to a different counter",
                                 "detail": f"{f} -> {b}"})
        if not b and r["faction"] in ("roman", "judaean"):
            findings.append({"piece": r["name"], "issue": "unit with no flip (Disrupted) face", "detail": f})
    dirty = [r["name_raw"] for r in palette if r["name_raw"] != r["name"]]
    if dirty:
        findings.append({"piece": ", ".join(dirty), "issue": "slot name carries stray whitespace",
                         "detail": f"{len(dirty)} slots; a raw-name join to save files drops them"})
    # shared backs: one reverse image serving many fronts
    shared = collections.defaultdict(list)
    for r in palette:
        if r["back_image"]:
            shared[r["back_image"]].append(r["name"])
    for img, users in sorted(shared.items()):
        if len(users) > 1:
            findings.append({"piece": ", ".join(users), "issue": "one back image shared by several counters",
                             "detail": f"{img} x{len(users)}"})
    return findings


# ---------------------------------------------------------------------------
# The printed component mix, read off the 2.6 MARKERS figure on rulebook page 5
# (600 dpi scan, Rules.pdf p.5, left column bottom + right column top).  This is
# the AUTHORITY on what one physical counter is; the module is only evidence of
# what art exists.  "module_pieces" names the palette slots that stand in for
# each printed counter — the tool asserts they still exist.
# ---------------------------------------------------------------------------
PRINTED_MARKERS = [
    {"front": "Rout +1", "back": "PANIC +2", "citation": "2.6 (p.5)",
     "module_pieces": ["Rout"], "module_models_as": "one two-sided piece (Rout.gif / Panic.gif)",
     "faithful": True},
    {"front": "TESTUDO (missile stripe 2/1, MF to form/disband 6, MA 4)",
     "back": "TESTUDO, No Missile Capability", "citation": "2.6 (p.5); legion-marked — the figure's sample reads XV",
     "module_pieces": ["V - Testudo", "X - Testudo", "XII - Testudo", "XV - Testudo"],
     "module_models_as": "one two-sided piece per legion", "faithful": True},
    {"front": "ESCALADE  1/2X-4", "back": "ESCALADE NA = Fully Occupied", "citation": "2.6 (p.5)",
     "module_pieces": ["Escalade"], "module_models_as": "one two-sided piece + six facing overlays",
     "faithful": True},
    {"front": "RAMP", "back": "WRECK (red X) = Wrecked Siege Engine", "citation": "2.6 (p.5)",
     "module_pieces": ["Ramp", "Wreck - Ram", "Wreck - Tower", "Wreck - Armored Tower"],
     "module_models_as": "FOUR one-sided pieces; the printed ramp/wreck counter is not modelled as one counter",
     "faithful": False},
    {"front": "DAMAGE 3", "back": "DAMAGE 4", "citation": "2.6 (p.5)",
     "module_pieces": ["Wall Damage 1"],
     "module_models_as": "one piece cycling Damage_1..Damage_14 + Damage_Breach", "faithful": False},
    {"front": "BREACH", "back": "DAMAGE 9 / DAMAGE 14", "citation": "2.6 (p.5) — one front, TWO backs printed",
     "module_pieces": ["Wall Damage 1"],
     "module_models_as": "a level of the same cycling damage piece", "faithful": False},
    {"front": "Turn (Roman Eagle)", "back": "Turn (Star of David)", "citation": "2.6 (p.5), 3.2, 4.2",
     "module_pieces": ["Turn Counter"], "module_models_as": "one two-sided piece", "faithful": True},
    {"front": "Broken Testudo (-6 MF to Fresh units, 16.4)", "back": "Elim. (red X over an engine)",
     "citation": "2.6 (p.5); the Elim face is what 13.21 calls for",
     "module_pieces": ["Broken Testuto", "Eliminated Ballista", "Eliminated Catapult", "Eliminated Onager"],
     "module_models_as": "Broken Testudo's flip layer is BLANK; three separate per-weapon Elim pieces instead",
     "faithful": False},
    {"front": "A Multiple Attacks", "back": "B Multiple Attacks / C Multiple Attacks",
     "citation": "2.6 (p.5) — one front, TWO backs printed",
     "module_pieces": ["Multiple Attack"], "module_models_as": "one piece cycling A/B/C, no base art",
     "faithful": False},
]


def printed_mix_join(palette):
    known = {r["name"] for r in palette}
    out = []
    for row in PRINTED_MARKERS:
        row = dict(row)
        row["module_pieces_present"] = {p: (p in known) for p in row["module_pieces"]}
        row["physical_counters_printed"] = 1
        out.append(row)
    return out


GALLUS_SAVE = "The Assault of Gallus 66 AD - Introductory Scenario.vsav"


def gallus_setup(palette, saves):
    """What the Gallus setup actually contains, split unit / marker / absent.

    Absence from a setup is NOT valid unreachable evidence (markers are created
    by mid-game actions), so this section exists to be read alongside the
    scenario card, never on its own.
    """
    if GALLUS_SAVE not in saves:
        return {"error": f"{GALLUS_SAVE} not found in module"}
    census = saves[GALLUS_SAVE]["by_piece"]
    units = {r["name"] for r in palette if r["faction"] in ("roman", "judaean")}
    markers = {r["name"] for r in palette if r["faction"] == "marker"}
    placed_units = {k: v for k, v in census.items() if k in units}
    return {
        "unit_pieces_placed": sum(placed_units.values()),
        "roman_units": sum(v for k, v in placed_units.items()
                           if next(r["faction"] for r in palette if r["name"] == k) == "roman"),
        "judaean_units": sum(v for k, v in placed_units.items()
                             if next(r["faction"] for r in palette if r["name"] == k) == "judaean"),
        "by_unit": dict(sorted(placed_units.items())),
        "markers_placed": {k: v for k, v in census.items() if k in markers},
        "markers_absent_from_setup": sorted(m for m in markers if m not in census),
    }


def contact_sheets(palette, module_dir, out_dir):
    """Front-above-back strips, one PNG per group. Art: never write into the repo."""
    from PIL import Image, ImageDraw
    os.makedirs(out_dir, exist_ok=True)
    d = os.path.join(module_dir, "images")
    groups = collections.defaultdict(list)
    for r in palette:
        groups[f"{r['faction']}_{r['legion'] or 'x'}_{r['kind']}".replace(" ", "-").replace("/", "-")].append(r)
    made = []
    for g, rows in sorted(groups.items()):
        cell, pad = 120, 16
        w = pad + len(rows) * (cell + pad)
        im = Image.new("RGB", (w, pad * 4 + cell * 2 + 34), "white")
        dr = ImageDraw.Draw(im)
        for i, r in enumerate(rows):
            x = pad + i * (cell + pad)
            for j, img in enumerate((r["front_image"], r["back_image"])):
                y = pad + 14 + j * (cell + pad + 8)
                dr.text((x, y - 13), ("FRONT " if j == 0 else "BACK  ") + r["name"][:16], fill="black")
                if not img:
                    dr.rectangle([x, y, x + cell, y + cell], outline="red")
                    dr.text((x + 6, y + cell // 2), "none", fill="red")
                    continue
                p = os.path.join(d, img)
                if not os.path.exists(p):
                    dr.rectangle([x, y, x + cell, y + cell], outline="red")
                    continue
                with Image.open(p) as face:
                    face = face.convert("RGB")
                    face.thumbnail((cell, cell), Image.LANCZOS)
                    im.paste(face, (x, y))
                dr.text((x, y + cell + 2), img[:20], fill="gray")
        path = os.path.join(out_dir, f"sheet_{g}.png")
        im.save(path)
        made.append(path)
    return made


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--module", default=DEFAULT_MODULE)
    ap.add_argument("--out", default=os.path.join(HERE, "counters_manifest.json"))
    ap.add_argument("--sheets", default="")
    args = ap.parse_args()

    root = ET.parse(os.path.join(args.module, "buildFile.xml")).getroot()
    palette = read_palette(root)
    art = art_index(args.module)
    saves = read_saves(args.module)
    props = read_prototype_props(root)

    all_refs = set(m.group(0).strip() for m in
                   IMAGE.finditer(open(os.path.join(args.module, "buildFile.xml"),
                                       encoding="utf-8", errors="replace").read()))
    manifest = {
        "_source": "Siege of Jerusalem, Rob McRae VASSAL module v3.0.0 (buildFile.xml + images/ + shipped .vsav setups)",
        "_method": "front = BasicPiece image; back = the piece's Flip layer image; overlays listed separately. "
                   "Printed pairing authority is rulebook 2.6 (page 5) — see COUNTERS_VERIFIED.md.",
        "counts": {
            "palette_slots": len(palette),
            "images_on_disk": len(art),
            "images_referenced": len(all_refs),
            "images_referenced_but_absent": sorted(r for r in all_refs if r not in art and r not in VASSAL_BUILTIN),
            "images_unreferenced": sorted(a for a in art if a not in all_refs),
        },
        "printed_marker_mix": printed_mix_join(palette),
        "counter_mix": counter_mix(palette, saves),
        "gallus_setup": gallus_setup(palette, saves),
        "palette": palette,
        "art": art,
        "scenarios": saves,
        "prototype_properties": props,
        "findings": face_checks(palette, art),
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1, sort_keys=False)
    print(f"palette slots      : {len(palette)}")
    print(f"images on disk     : {len(art)}")
    print(f"scenario setups    : {len(saves)}")
    print(f"findings           : {len(manifest['findings'])}")
    print(f"wrote              : {args.out}")
    if args.sheets:
        made = contact_sheets(palette, args.module, args.sheets)
        print(f"contact sheets     : {len(made)} -> {args.sheets}")


if __name__ == "__main__":
    main()
