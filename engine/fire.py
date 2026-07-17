"""
fire.py - GBoNW fire-combat resolver (PURE functions, phase 2).

Implements the Fire Procedure [8.1.8] over the game's transcribed
combat_tables block: adjust the firer's rating letter (line/breakpoint/
square, artillery range 8.1.6), find the fire column for the target's
defense class, shift columns (rear/flank/massed/terrain), and interpret
the die-row cell into typed effects for the Family-C ledger.

NOT wired into any gate yet: the gate integration (LOS 8.1.6, arcs,
offensive/return fire phases) is phase 2c. Pure = testable now, and the
tables stay the single source of truth.
"""

LETTERS = "ABCDEF"


def adjust_letter(letter, steps):
    """Up (negative steps) / down (positive) the rating letter, clamped
    to A..F [8.1.6/8.1.8 'Up #/Dn #']."""
    i = LETTERS.index(letter) + steps
    return LETTERS[max(0, min(len(LETTERS) - 1, i))]


def range_adjustment(tables, nation, gun, hexes):
    """Artillery Range Table [8.1.6]: letter steps for the shot, or None
    if out of range. Also returns the band name (grapeshot matters to
    later rules)."""
    bands = tables["artillery_range"][nation][gun]
    for name, steps in (("up2", -2), ("base", 0),
                        ("down1", 1), ("down2", 2)):
        b = bands.get(name)
        if b and b[0] <= hexes <= b[1]:
            band = "grapeshot" if name == "up2" else \
                ("medium" if name == "base" else "long")
            return steps, band
    return None, "out_of_range"


def defense_class(tables, side, arm, formation):
    """Target's Fire Defense Value class a-g [8.1.8]."""
    if formation == "skirmish":
        key = "skirmishers"
    elif arm.startswith("artillery"):
        key = "artillery"
    elif formation == "square":
        key = "infantry in square"
    elif arm == "cavalry":
        key = ("cavalry column" if formation == "column"
               else f"cavalry in {formation}")
    else:
        nat = "french" if side == "French" else "allied"
        key = f"{nat} infantry in {formation}"
    for cls, members in tables["fire_defense_classes"].items():
        if key in members:
            return cls
    raise KeyError(f"no defense class for {key!r}")


def fire_column(tables, cls, letter):
    """Adjusted rating letter -> fire column for the class, or None
    (off the chart = no effect possible) [8.1.8]."""
    for col, cell in tables["fire_table_columns"][cls].items():
        if col == "note":
            continue
        if "-" in cell:
            a, b = cell.split("-")
            if a <= letter <= b:
                return int(col)
        elif cell == letter:
            return int(col)
    return None


def resolve(tables, cls, letter, die, column_shift=0):
    """Full resolution: returns a dict with the column used and the
    typed effect. column_shift: negative = left (worse for target...
    no — left = LOWER column number = HARSHER; the chart's 'columns
    left' modifiers help the firer)."""
    col = fire_column(tables, cls, letter)
    if col is None:
        return {"column": None, "effect": {"kind": "no_effect"},
                "why": f"rating {letter} off the chart for class {cls}"}
    col = max(1, min(8, col + column_shift))
    cell = tables["fire_results"][str(die)][col - 1]
    return {"column": col, "die": die, "cell": cell,
            "effect": interpret_cell(cell)}


def interpret_cell(cell):
    """Fire result cell -> typed effect [8.1.8 Combat Effects]:
    M+#/M/M-# = morale check with that DRM; integer n = lose n SP AND
    morale check at +(n-1); NE = nothing."""
    if cell == "NE":
        return {"kind": "no_effect"}
    if cell.startswith("M"):
        drm = 0
        if len(cell) > 1:
            drm = int(cell[1:].replace("–", "-"))
        return {"kind": "morale_check", "drm": drm}
    n = int(cell)
    return {"kind": "sp_loss", "sp": n,
            "then": {"kind": "morale_check", "drm": n - 1}}


def firer_letter(tables, base_letter, formation, at_breakpoint=False,
                 range_steps=0):
    """Apply Fire Rating Adjustments [8.1.8 panel] + range steps."""
    steps = range_steps
    if formation == "line":
        steps -= 1
    if formation == "square":
        steps += 2
    if at_breakpoint:
        steps += 1
    return adjust_letter(base_letter, steps)


def morale_check(tables, die, morale, drms):
    """Morale Check Table [9.1]: die + sum(DRMs) vs morale rating.
    Returns levels lost (0 = passed)."""
    total = die + sum(drms)
    over = total - morale
    if over <= 0:
        return 0
    if over <= 3:
        return 1
    if over <= 6:
        return 2
    return 3
