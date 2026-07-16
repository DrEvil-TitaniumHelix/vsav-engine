"""Georeference the module's named SetupStack locations to hex coords.
Used to anchor terrain classification for the Northern Flank area."""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "engine"))
import gamespec

game = gamespec.load(HERE)
BUILD = r"C:\VassalIngest\austerlitz-gmt\extracted\buildFile.xml"
t = open(BUILD, encoding="utf-8", errors="replace").read()

for m in re.finditer(r"<VASSAL\.build\.module\.map\.SetupStack ([^>]+)>", t):
    a = m.group(1)

    def attr(k, a=a):
        mm = re.search(rf'\b{k}="([^"]*)"', a)
        return mm.group(1) if mm else None

    name, x, y = attr("name"), attr("x"), attr("y")
    if not name or not x or not y:
        continue
    x, y = int(x), int(y)
    c, r, hx = game.grid.pixel_to_hex(x, y)
    tag = "IN-PLAY" if (38 <= c <= 74 and 2 <= r <= 28) else ""
    print(f"{name:28s} col {c:3d} row {r:3d}  {tag}")
