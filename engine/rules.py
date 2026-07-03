"""
rules.py - Combat resolution (the Arnhem Integrated CRT).

Movement, geometry, ZOC and terrain moved to the spec-driven layer in
gamespec.py (2026-07-03 generalization pass) — this module is now combat only.
The CRT below is still Arnhem-specific; it generalizes into game.json when the
combat phase lands (a CRT is just data: column brackets x die -> result).

Transcribed from the Westwall Standard Rules [7.61]. Combat is DIFFERENTIAL
(attack minus defense), terrain-integrated. Validated against the rulebook's
own worked example: Town, +9 differential, die 5 -> D1.
"""

# ----------------------------------------------------------------- Integrated CRT [7.61]
# Each terrain row lists its differential brackets left-to-right; the column POSITION
# (1-based) indexes the shared result matrix. Terrain is integrated: better defensive
# terrain has more left-columns, shifting a given differential to a lower position.
TERRAIN_COLUMNS = {
    "rough":  ["-2", "-1", "0", "+1", "+2,3", "+4,5", "+6-8", "+9-11", "+12"],
    "broken": ["-3", "-2", "-1", "0", "+1", "+2,3", "+4,5", "+6-8", "+9-11", "+12"],   # broken/town/woods/stream
    "grove":  ["-5", "-4,3", "-2", "-1", "0", "+1", "+2,3", "+4,5", "+6-8", "+9-11", "+12"],  # grove/bridge
    "clear":  ["-7", "-6,5", "-4,3", "-2", "-1", "0", "+1", "+2,3", "+4,5", "+6-8", "+9-11", "+12"],  # clear/mixed
}
TERRAIN_ALIAS = {"town": "broken", "woods": "broken", "stream": "broken",
                 "bridge": "grove", "mixed": "clear"}

RESULT_MATRIX = {  # die -> result per column position (1..12)
    1: ["A1", "A1", "A1", "Br", "D1", "D2", "D2", "D2", "D2", "D3", "D4", "De"],
    2: ["A1", "A1", "A1", "A1", "Br", "D1", "D2", "D2", "D2", "D2", "D3", "D4"],
    3: ["A1", "A1", "A1", "A1", "A1", "Br", "D1", "D2", "D2", "D2", "D2", "D3"],
    4: ["A2", "A1", "A1", "A1", "A1", "Br", "Br", "D1", "D2", "D2", "D2", "D2"],
    5: ["A2", "A2", "A1", "A1", "A1", "A1", "Br", "Br", "D1", "D2", "D2", "D2"],
    6: ["Ae", "Ae", "A2", "A1", "A1", "A1", "A1", "Br", "Br", "Br", "D2", "D2"],
}


def _bracket_matches(bracket, diff):
    if "," in bracket:                      # e.g. "+2,3" or "-6,5" or "-4,3"
        lo, hi = bracket.replace("+", "").split(",")
        lo, hi = int(lo), int(hi if not bracket.startswith("-") else "-" + hi)
        a, b = sorted((int(bracket.split(",")[0]), hi))
        return a <= diff <= b
    if "-" in bracket[1:]:                   # range like "+6-8" or "+9-11"
        lo, hi = bracket.replace("+", "").split("-")
        return int(lo) <= diff <= int(hi)
    return diff == int(bracket)


def _column_position(terrain, diff):
    cols = TERRAIN_COLUMNS[TERRAIN_ALIAS.get(terrain, terrain)]
    first = cols[0]
    low_val = int(first.split(",")[0]) if "," in first else int(first)
    if diff <= low_val:
        return 1
    if diff >= 12:
        return len(cols)
    for i, bracket in enumerate(cols):
        if _bracket_matches(bracket, diff):
            return i + 1
    return len(cols)  # fallback (shouldn't hit)


def resolve_combat(att_strength, def_strength, terrain, die):
    """Return the combat result code (A1/A2/Ae/Br/D1..D4/De)."""
    diff = att_strength - def_strength
    pos = _column_position(terrain, diff)
    return RESULT_MATRIX[die][pos - 1]


# ----------------------------------------------------------------- self-test
if __name__ == "__main__":
    r = resolve_combat(13, 4, "town", 5)
    print(f"CRT checksum  Town +9 die5 = {r}   (rulebook says D1)  -> {'PASS' if r=='D1' else 'FAIL'}")
    for (a, d, t, die) in [(13, 4, "town", 1), (5, 5, "clear", 6), (20, 2, "clear", 1), (2, 8, "grove", 6)]:
        print(f"  {a} vs {d} {t} die{die} -> {resolve_combat(a,d,t,die)}")
