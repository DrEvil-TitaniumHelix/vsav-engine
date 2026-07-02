"""
arnhem.py - Toolkit for reading/writing VASSAL saves for the SPI Westwall 'Arnhem' game.

Core capability (PROVEN end-to-end 2026-06-30): decode a .vsav -> full board state,
move any unit, re-encode -> a .vsav VASSAL loads with the move applied.

This is the model-agnostic "body". A brain (rules + AI, or a stronger model) plugs in on top.
"""
import zipfile, re, sys, json, os

XORKEY = 0xA3  # from the !VCSK header of this module's saves

# --- Arnhem board hex grid (extracted from buildFile.xml) ---
# dx=96 (column pixel spacing), dy=119 (row spacing), origin (60,60), staggered.
GRID = dict(dx=96.0, dy=119.0, x0=60.0, y0=60.0, stagger=True)

# ---------------------------------------------------------------- codec
def decode_saved(raw: str) -> str:
    assert raw.startswith("!VCSK"), "not an obfuscated VASSAL save"
    key = int(raw[5:7], 16)
    body = raw[7:]
    return bytes(int(body[i:i+2], 16) ^ key for i in range(0, len(body), 2)).decode("latin-1")

def encode_saved(plain: str, key: int = XORKEY) -> str:
    return "!VCSK" + f"{key:02x}" + "".join(f"{b ^ key:02x}" for b in plain.encode("latin-1"))

def read_vsav(path):
    with zipfile.ZipFile(path) as z:
        return (decode_saved(z.read("savedGame").decode("latin-1")),
                z.read("moduledata"), z.read("savedata"))

def write_vsav(path, plain, moduledata, savedata, key: int = XORKEY):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("moduledata", moduledata)
        z.writestr("savedata", savedata)
        z.writestr("savedGame", encode_saved(plain, key).encode("ascii"))

# ---------------------------------------------------------------- hex math
def pixel_to_hex(x, y, g=GRID):
    """Return (col,row,hexnum) for a map pixel.
    Validated against the printed player-aid cards at: 9SS=3322, Kraft=3722, Grsn=0702,
    BrDf=2621, 101DZ=1007, 82DZ=2323, 1DZ=3919. Odd (staggered-down) columns carry +1 row."""
    col = round((x - g["x0"]) / g["dx"])
    odd = (col % 2 == 1)
    yoff = (g["dy"] / 2.0) if (g["stagger"] and odd) else 0.0
    row = round((y - g["y0"] - yoff) / g["dy"]) + (1 if odd else 0)
    return col, row, f"{col:02d}{row:02d}"

def hex_to_pixel(col, row, g=GRID):
    odd = (col % 2 == 1)
    yoff = (g["dy"] / 2.0) if (g["stagger"] and odd) else 0.0
    base = row - (1 if odd else 0)
    return round(g["x0"] + col * g["dx"]), round(g["y0"] + base * g["dy"] + yoff)

def hexnum_to_pixel(hexnum, g=GRID):
    s = f"{int(hexnum):04d}"
    return hex_to_pixel(int(s[:2]), int(s[2:]), g)

# ---------------------------------------------------------------- board parse
# A unit's authoritative on-map position lives in BOTH its BasicPiece state
# ("...;x,y") and a stack command ("+/<t>/stack/Main Map;x;y;<id>").
# Robust approach: split on the AddPiece marker, take the reliable image name
# (before .png) as the unit label, and the Main Map;x;y as the position.
IMG_RE = re.compile(r"^([^;]+?)\.png;")
POS_RE = re.compile(r"Main Map;(\d+);(\d+);")

# Side detection (HEURISTIC, derived from the two player-aid cards). German units are
# the distinctive ones (SS formations + named Kampfgruppen); everything else = Allied.
# Authoritative per-unit side/setup lives in ref/rules_and_oob.md.
GERMAN_TOKENS = ("SS", "Kraft", "Krft", "Grsn", "BrDf", "Hnke", "Wlt", "Hbr", "Hber",
                 "vT", "2107", "180", "406", "6P", "1P", "Jng", "-59")

def side(name):
    return "Ger" if any(t in name for t in GERMAN_TOKENS) else "All"

def parse_board(plain):
    """Return list of dicts: name, x, y, col, row, hexnum. One entry per placed piece."""
    units = []
    for chunk in plain.split("piece;;;")[1:]:
        img = IMG_RE.match(chunk)
        pos = POS_RE.search(chunk[:400])   # position is early in the piece record
        if not (img and pos):
            continue
        name = img.group(1).strip()
        x, y = int(pos.group(1)), int(pos.group(2))
        col, row, hexn = pixel_to_hex(x, y)
        units.append(dict(name=name, side=side(name), x=x, y=y, col=col, row=row, hexnum=hexn))
    return units

# ---------------------------------------------------------------- mover
def move_unit(plain, name_fragment, new_x, new_y):
    """Move the (unique) unit whose name contains name_fragment to pixel (new_x,new_y).
    Changes the unit's piece-state coord AND its stack coord. Works for units alone in
    their hex (own single-piece stack) - the common case. Returns (new_plain, info)."""
    idx = plain.find(name_fragment)
    if idx < 0:
        raise ValueError(f"unit '{name_fragment}' not found")
    end = plain.find("+/", idx)
    rec = plain[idx:end]
    mm = re.search(r"Main Map;(\d+);(\d+);", rec)
    if not mm:
        raise ValueError("no Main Map coord in unit record")
    ox, oy = mm.group(1), mm.group(2)
    comma, semi = f"{ox},{oy}", f"{ox};{oy}"
    n_comma = plain.count(comma)
    n_semi = plain.count(semi)
    if n_comma > 1:
        raise ValueError(f"position {comma} shared by >1 unit (stacked) - mover needs stack-split (TODO)")
    new_plain = plain.replace(comma, f"{new_x},{new_y}").replace(semi, f"{new_x};{new_y}")
    return new_plain, dict(unit=name_fragment, old=(int(ox), int(oy)), new=(new_x, new_y),
                           comma_hits=n_comma, semi_hits=n_semi)

# ---------------------------------------------------------------- CLI
def _cli():
    import argparse
    ap = argparse.ArgumentParser(description="Arnhem VASSAL save toolkit")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dump"); d.add_argument("vsav"); d.add_argument("--json", action="store_true")
    mv = sub.add_parser("move")
    mv.add_argument("vsav"); mv.add_argument("unit"); mv.add_argument("dest")  # dest = hexnum or x,y
    mv.add_argument("out")
    a = ap.parse_args()

    if a.cmd == "dump":
        plain, _, _ = read_vsav(a.vsav)
        units = parse_board(plain)
        if a.json:
            print(json.dumps(units, indent=2))
        else:
            ger = sum(1 for u in units if u["side"] == "Ger")
            print(f"{len(units)} pieces on the Arnhem board  ({ger} Ger / {len(units)-ger} All):\n")
            for u in sorted(units, key=lambda u: u["hexnum"]):
                print(f"  hex {u['hexnum']}  [{u['side']}]  ({u['x']:>4},{u['y']:>4})  {u['name']}")
    elif a.cmd == "move":
        plain, md, sd = read_vsav(a.vsav)
        if "," in a.dest:
            nx, ny = map(int, a.dest.split(","))
        else:
            nx, ny = hexnum_to_pixel(a.dest)
        new_plain, info = move_unit(plain, a.unit, nx, ny)
        write_vsav(a.out, new_plain, md, sd)
        print(f"moved {info['unit']}: {info['old']} -> {info['new']}  wrote {a.out}")

if __name__ == "__main__":
    _cli()
