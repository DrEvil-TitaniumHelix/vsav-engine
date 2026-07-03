"""
make_save.py - Construct a VASSAL .vsav from scratch: a scenario JSON placing
units drawn from the module's own PieceSlot definitions (buildFile).

This is the "scenarios are data too" layer: modules that ship no setup saves
(Tobruk) get scenarios authored as JSON — the piece type/state strings come
verbatim from the module's buildFile, so VASSAL loads what it defined.

Scenario JSON:
  {"units": [{"slot": "Panzer-III H", "hex": [5, 19]},
             {"gpid": "580", "hex": [29, 20]}, ...]}
  "slot" = PieceSlot entryName (must be unique in the module) or use "gpid".
  "hex"  = [col, row] in engine grid coords.

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
        col, row = u["hex"]
        x, y = game.grid.hex_to_pixel(col, row)
        body = rec["body"]
        if not body.startswith("+/null/"):
            raise ValueError(f"unexpected slot body for {rec['name']}: {body[:60]}")
        # place: id null -> real id; BasicPiece state "null;0;0;<gpid>" -> on-map coords
        placed = "+/" + str(pid) + "/" + body[len("+/null/"):]
        marker = f"null;0;0;{rec['gpid']}"
        if marker not in placed:
            raise ValueError(f"no placeable BasicPiece state in slot {rec['name']}")
        placed = placed.replace(marker, f"{game.map_name};{x};{y};{rec['gpid']}")
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
