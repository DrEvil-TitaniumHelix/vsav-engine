"""validate_grid.py - SoJ letter-diagonal grid identity.

PASS requires:
  1. Every parseable region name from the v2.3 module RegionGrid (the
     3,096-name corpus committed in ingest/letter_hex_regions.json)
     round-trips pixel -> (col,row) -> display_name EXACTLY, except the
     25 known module typos (listed here, verified by hand against the map).
  2. The rulebook's printed landmark hexes [2.14] land on their map-art
     pixel positions: Damascus Gate W36, Yafo Gate P51, Psephinus G39.
  3. terrain.json hex keys invert to their recorded display names.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "engine"))
import gamespec  # noqa: E402

KNOWN_TYPOS = 25   # author-misplaced/typo'd regions in the v2.3 module

def main():
    game = gamespec.Game(HERE)
    g = game.grid
    regions = json.load(open(os.path.join(HERE, "ingest",
                                          "letter_hex_regions.json")))
    ok = bad = skipped = 0
    fails = []
    for name, x, y in regions:
        m = re.fullmatch(r"([A-Z])(\1)?(\d{1,3})", name.replace(" ", ""))
        if not m:
            skipped += 1
            continue
        col, row, _ = g.pixel_to_hex(x, y)
        if g.display_name(col, row) == name.replace(" ", ""):
            ok += 1
        else:
            bad += 1
            fails.append(name)
    print(f"region names: {ok} exact, {bad} mismatched "
          f"({skipped} non-hex names skipped)")
    assert bad == KNOWN_TYPOS, \
        f"expected exactly the {KNOWN_TYPOS} known module typos, got {bad}: {fails[:10]}"
    assert ok >= 3071, f"exact matches regressed: {ok} < 3071"

    # printed landmarks [2.14] vs map-art positions (validated by eye 2026-08-07)
    landmarks = {"W36": (1845, 2069), "P51": (1345, 3011), "G39": (705, 1657)}
    for name, (ex, ey) in landmarks.items():
        m = re.fullmatch(r"([A-Z])(\1)?(\d+)", name)
        L = ord(m.group(1)) - 64 + (26 if m.group(2) else 0)
        N = int(m.group(3))
        px, py = g.hex_to_pixel(L, N + L // 2)
        d = ((px - ex) ** 2 + (py - ey) ** 2) ** 0.5
        assert d < 10, f"{name}: engine pixel ({px},{py}) vs map ({ex},{ey}) off {d:.1f}px"
        print(f"landmark {name}: engine ({px},{py}) vs map art ({ex},{ey}) - {d:.1f}px")

    # terrain.json keys invert to their display names
    terr = game.terrain
    n = 0
    for k, v in terr["hexes"].items():
        col, row = int(k[:2]), int(k[2:])
        assert g.display_name(col, row) == v["name"], \
            f"terrain key {k}: display {g.display_name(col, row)} != {v['name']}"
        n += 1
    print(f"terrain keys: {n} invert exactly")
    print("validate_grid: PASS")

if __name__ == "__main__":
    main()
