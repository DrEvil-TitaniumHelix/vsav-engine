"""Afrika Korps grid + naming validation (spec #12 evidence, re-runnable).

Every anchor below is quoted from AfrikaKorps_3d_Ed_Rules.pdf (section given).
Checks, all must pass:
  1. name round-trip: rulebook label -> (col,row) -> display_name identical
  2. landmark anchors land on the lattice nodes located on the map image
  3. rule 5.8 east-edge playable hexes all fall in one column (c=68) and
     R68 falls in the partial column east of it (c=69)
  4. rule 18 movement-chain examples: every consecutive pair is adjacent
  5. anomalous hexsides E18-F19 / W62-X62 (rules 5.x/14.x) are adjacent

Run:  python games/afrika-korps-classic-ah/validate_grid.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "engine"))
import gamespec

GAME_DIR = os.path.dirname(os.path.abspath(__file__))
g = gamespec.load(GAME_DIR)
grid = g.grid

ROW0, NUM0 = 5, -10          # must match game.json grid.naming


def name_to_cr(name):
    """Inverse of Grid.display_name for letter_diag (single letters only)."""
    li = ord(name[0]) - ord("A")
    num = int(name[1:])
    row = li + ROW0
    col = num - li // 2 - NUM0 - 1
    return col, row


fails = []


def check(cond, what):
    print(("  PASS  " if cond else "  FAIL  ") + what)
    if not cond:
        fails.append(what)


# 1+2 --- landmark anchors (rulebook 1.1) at map-image-located lattice nodes
print("landmarks (rulebook 1.1; image-located lattice node in comment):")
LANDMARKS = [
    ("W3", 1, 27, "German home base, gray hex, SW corner"),
    ("W6", 4, 27, "El Agheila town circle"),
    ("H2", 8, 12, "Bengasi fortress cross-hatch"),
    ("G25", 31, 11, "Tobruch fortress cross-hatch"),
    ("L59", 63, 16, "El Alamein town circle"),
    ("J62", 67, 14, "Allied home base, Union Jack hex"),
]
for name, c, r, what in LANDMARKS:
    check(name_to_cr(name) == (c, r), f"{name} -> (c={c},r={r})  [{what}]")
    check(grid.display_name(c, r) == name, f"display_name({c},{r}) == {name}")

# 3 --- rule 5.8: playable east-edge hexes; R68 is a forbidden partial hex
print("rule 5.8 east edge:")
EDGE = ["I63", "K64", "M65", "O66", "Q67", "S68", "U69"]
cols = [name_to_cr(n)[0] for n in EDGE]
check(cols == [68] * 7, f"playable east-edge hexes {EDGE} all in column 68 (got {cols})")
check(name_to_cr("R68")[0] == 69, "R68 in partial column 69 (rule 5.8 forbids it)")
for n in EDGE + ["R68"]:
    c, r = name_to_cr(n)
    check(grid.display_name(c, r) == n, f"round-trip {n}")

# 4 --- rule 18 movement chains: consecutive hexes must be adjacent
print("rule 18 movement-chain adjacency:")
CHAINS = [
    ("G25", "H26", "I27", "J27", "J28"),          # 'may move H26-I27-J27-J28' from Tobruch
    ("H24", "I25", "I26", "J27", "I27", "I28", "H28", "H29", "I30"),
    ("G22", "H23", "H24", "H25", "H26", "H27"),
    ("H24", "H25", "H26"),
    ("I26", "J27", "I26"),
]
for chain in CHAINS:
    for a, b in zip(chain, chain[1:]):
        ca, cb = name_to_cr(a), name_to_cr(b)
        check(cb in g.neighbors(*ca), f"{a} adjacent {b}")

# 5 --- anomalous hexsides are real hexsides (adjacent pairs)
print("anomalous hexsides:")
for a, b in [("E18", "F19"), ("W62", "X62")]:
    check(name_to_cr(b) in g.neighbors(*name_to_cr(a)), f"{a}-{b} share a hexside")

print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILURES'}")
sys.exit(1 if fails else 0)
