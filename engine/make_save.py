"""
make_save.py - Construct a VASSAL .vsav from scratch: a scenario JSON placing
units drawn from the module's own PieceSlot definitions (buildFile).

This is the "scenarios are data too" layer: modules that ship no setup saves
(Tobruk) get scenarios authored as JSON — the piece type/state strings come
verbatim from the module's buildFile, so VASSAL loads what it defined.

Scenario JSON:
  {"units": [{"slot": "Panzer-III H", "hex": [5, 19]},
             {"gpid": "580", "hex": [29, 20]},
             {"gpid": "2363", "hex": [2, 5], "layer": 2,
              "img": "ge/ge467S.svg", "name": "4-6-7 1sq"}, ...]}
  "slot" = PieceSlot entryName (must be unique in the module) or use "gpid".
  "hex"  = [col, row] in engine grid coords.
  "layer" (optional) = level for the slot's INNERMOST emb2. VASL counters are
    quality ladders (one slot = 4-6-8/4-6-7/4-4-7/4-3-6 as layer levels); this
    sets that layer's state to N and the paired broken-side layer before it
    to -N so real VASSAL shows the right face both sides.
  "img"/"name" (optional) = override the BasicPiece image/name. VASL squads
    and leaders ship a BLANK BasicPiece image (all art comes from layers);
    the override gives our parser/UI a concrete identity and is harmless in
    real VASSAL (the active layer draws the same art on top).

Usage: python make_save.py --game <dir> <scenario.json> <out.vsav>
"""
import html, json, os, re, sys
from collections import defaultdict

import gamespec
import vsav

ESC = "\x1b"
SLOT_RE = re.compile(
    r'<VASSAL\.build\.widget\.PieceSlot[^>]*?entryName="([^"]*)"[^>]*?gpid="(\d+)"[^>]*>'
    r'(.*?)</VASSAL\.build\.widget\.PieceSlot>', re.S)


def load_slots(buildfile_path):
    txt = open(buildfile_path, encoding="utf-8", errors="replace").read()
    by_name, by_gpid = {}, {}
    for name, gpid, body in SLOT_RE.findall(txt):
        body = html.unescape(body).strip()
        rec = dict(name=html.unescape(name), gpid=gpid, body=body)
        by_name.setdefault(rec["name"], []).append(rec)
        by_gpid[gpid] = rec
    return by_name, by_gpid


def set_innermost_layer(placed, level, slotname):
    """Set the innermost emb2's state (the last numeric state token before the
    BasicPiece state) to `level`, and the token before it — its broken-side
    twin layer in VASL counters — to -level. State tokens are separated by
    tab at escalating backslash depth; emb2 state is just the level int."""
    m = re.search(r"(-?\d+)(;?\\*\t)(-?\d+)(;?\\*\t)([^\t]*)$", placed)
    if not m:
        raise ValueError(f"no layer state tokens found in slot {slotname}")
    return (placed[:m.start(1)] + str(-level) + m.group(2)
            + str(level) + m.group(4) + m.group(5))


def set_basic_piece(placed, img, name, slotname):
    """Rewrite the BasicPiece type's image and/or name fields ('/' in the image
    path must stay escaped as '\\/' — '/' is the piece type/state separator)."""
    m = None
    for m in re.finditer(r"piece;([^;]*);([^;]*);((?:\\.|[^;/])*);((?:\\.|[^/;])*)/", placed):
        pass
    if not m:
        raise ValueError(f"no BasicPiece type found in slot {slotname}")
    new_img = img.replace("/", "\\/") if img is not None else m.group(3)
    new_name = name if name is not None else m.group(4)
    return (placed[:m.start()] + f"piece;{m.group(1)};{m.group(2)};{new_img};{new_name}/"
            + placed[m.end():])


def build(game, scenario, out_path):
    by_name, by_gpid = load_slots(game._path(game.spec["buildfile"]))
    moduledata = open(game._path(game.spec["moduledata"]), "rb").read()
    savedata = (b'<?xml version="1.0" encoding="UTF-8"?>\n<data version="1">\n'
                b'  <version></version>\n  <VassalVersion>3.2.17</VassalVersion>\n'
                b'  <dateSaved>0</dateSaved>\n</data>')

    cmds = ["begin_save"]
    pid = 1000000000001
    byhex = defaultdict(list)
    for u in scenario["units"]:
        if "gpid" in u:
            rec = by_gpid[str(u["gpid"])]
        else:
            recs = by_name[u["slot"]]
            if len(recs) > 1:
                raise ValueError(f"slot '{u['slot']}' ambiguous ({len(recs)} defs) — use gpid")
            rec = recs[0]
        if "xy" in u:                       # raw pixel placement (at-start ingest)
            x, y = int(u["xy"][0]), int(u["xy"][1])
        else:
            col, row = u["hex"]
            x, y = game.grid.hex_to_pixel(col, row)
        body = rec["body"]
        if not body.startswith("+/null/"):
            raise ValueError(f"unexpected slot body for {rec['name']}: {body[:60]}")
        # place: id null -> real id; BasicPiece state "null;0;0;..." -> on-map
        # coords. BasicPiece state is the LAST state token, so rfind is safe
        # (placeDM traits contain earlier "null;0;0;false" lookalikes); the
        # gpid field after y may be empty (VASL squads) — keep the tail as-is.
        placed = "+/" + str(pid) + "/" + body[len("+/null/"):]
        i = placed.rfind("null;0;0;")
        if i < 0:
            raise ValueError(f"no placeable BasicPiece state in slot {rec['name']}")
        placed = placed[:i] + f"{game.map_name};{x};{y};" + placed[i + len("null;0;0;"):]
        if "layer" in u:
            placed = set_innermost_layer(placed, int(u["layer"]), rec["name"])
        if "img" in u or "name" in u:
            placed = set_basic_piece(placed, u.get("img"), u.get("name"), rec["name"])
        cmds.append(placed)
        byhex[(x, y)].append(pid)
        pid += 1
    sid = pid
    for (x, y), members in byhex.items():
        tail = "".join(f";{m}" for m in members)
        cmds.append(f"+/{sid}/stack/{game.map_name};{x};{y}{tail}\\")
        sid += 1
    board = game.spec.get("board_name", game.map_name)
    cmds.append(f"{game.map_name}BoardPicker\t{board}\t0\t0")
    cmds.append("end_save")

    vsav.write_vsav(out_path, ESC.join(cmds), moduledata, savedata, key=game.save_key)
    print(f"{len(scenario['units'])} units in {len(byhex)} hexes -> {out_path}")


if __name__ == "__main__":
    args = sys.argv[1:]
    game_dir = gamespec.default_game_dir()
    if args and args[0] == "--game":
        game_dir = args[1]; args = args[2:]
    game = gamespec.Game(game_dir)
    scenario = json.load(open(args[0]))
    build(game, scenario, args[1])
