"""
melee.py - GBoNW melee-combat resolver (PURE functions, phase 4).

Implements the shock-combat procedures [8.2 Bayonet, 8.3 Assault,
8.4 Charge] over the game's transcribed combat_tables.melee block:
pre-shock morale checks, form-square reaction checks, charge range and
bonus arithmetic (playbook A8.1.1/A8.1.2), the size-ratio DRM, the
Melee Result Table [8.5] with the errata-defined Retreat result, and
the Pursuit Table [8.4.2 #8].

NOT wired into any gate here: the gate integration (declarations,
reaction windows, retreat execution) lives in napoleonic.py. Pure =
testable in isolation, and the tables stay the single source of truth.

Rulings baked in (all cited in combat_tables.melee / source_defects):
- Retreat result = ONE Unsteady-style retreat in addition to any
  morale-driven retreat (errata 2000-07-20, supersedes the Q&A answer
  of one hex per level - AUS-MEL-2).
- Continued melee repeats the Melee step without the Charge Bonus
  (8.4.2#7 'step 5' is a misprint for 6 - AUS-MEL-3).
- Countercharge net bonus = attacker bonus minus countercharger bonus,
  may be negative (Fox Q&A).
- Heavy/Cuirassier may charge from 2 hexes but forfeit their bonus
  (playbook A8.1.1).
"""


# ---------- charge legality & bonus [A8.1.1 / A8.1.2 / 8.4] ----------

def charge_range_ok(tables, cav_type, dist):
    """May cavalry of this type DECLARE a charge at this distance?
    [A8.1.1] Never adjacent; max 4; min 2 (Heavy/Cuirassier may also
    charge at 2, at the cost of their bonus - so their legal band is
    still 2..4)."""
    rng = tables["melee"]["charge"]["range"]
    if dist < 2:                      # adjacent (or same hex) - never
        return False
    return dist <= rng["max_hexes"]


def charge_bonus(tables, cav_type, dist=None, vs_square=False,
                 in_column=False, countercharger_bonus=0):
    """Net Charge Bonus DRM for a charging/reaction-charging/counter-
    charging unit [A8.1.2 + 8.4.2#6 + Fox Q&A countercharge offset].
    dist = declaration distance (None for reaction/countercharges,
    whose range is their Reaction Zone [8.4.1] - no minimum-range
    forfeiture applies to them)."""
    bonus = tables["melee"]["charge"]["bonus"][cav_type]
    if dist is not None and dist < \
            tables["melee"]["charge"]["range"]["min_hexes_default"]:
        raise ValueError("charge declared adjacent")
    if cav_type in ("heavy", "cuirassier") and dist is not None and \
            dist < tables["melee"]["charge"]["range"][
                "min_hexes_heavy_cuirassier"]:
        bonus = 0                     # charged from 2 hexes [A8.1.1]
    if vs_square:
        bonus = (bonus + 1) // 2      # halved, round up [8.4.2#6]
    if in_column:
        bonus = (bonus + 1) // 2      # halved, round up [8.4.2#6]
    return bonus - countercharger_bonus


# ---------- size ratio [8.3.1#5 / chart panel] ----------

def size_ratio_drm(att_sp, def_sp):
    """Attacker:Defender SP ratio DRM, fractions rounded down.
    Cavalry-in-column thirds and artillery exclusion are the CALLER's
    job (they need unit state); this is the pure ratio ladder."""
    if def_sp <= 0:
        return 3                      # no effective defenders = 4:1+
    if att_sp <= 0:
        return -2
    if att_sp >= def_sp:
        ratio = att_sp // def_sp
        if ratio >= 4:
            return 3
        return {1: 0, 2: 1, 3: 2}[ratio]
    ratio = def_sp // att_sp          # defender's favor [8.3.1#5]
    if ratio >= 3:
        return -2
    return {1: 0, 2: -1}[ratio]


def melee_sp(units):
    """Total SPs on one side of a melee: artillery never counts; a
    charging cavalry unit in column counts one-third rounded down
    [8.4.2#6]. units = iterable of (sp, arm, formation, charging)."""
    total = 0
    for sp, arm, formation, charging in units:
        if arm.startswith("artillery"):
            continue
        if arm == "cavalry" and charging and formation == "column":
            total += sp // 3
        else:
            total += sp
    return total


# ---------- pre-shock morale check [8.2/8.3/8.4, chart p4] ----------

def _ladder(over, bands):
    """Shared 'roll over morale' band lookup. bands = list of
    (max_over_inclusive, result); the last band catches everything."""
    for cap, result in bands:
        if over <= cap:
            return result
    return bands[-1][1]


def pre_shock_attacker(die, morale, drms):
    """Attacker's Pre-Melee Morale Check -> typed effect dict.
    Bands: pass / 1-3 no melee / 4+ no melee + disorder + level."""
    over = die + sum(drms) - morale
    if over <= 0:
        return {"kind": "may_melee"}
    if over <= 3:
        return {"kind": "no_melee"}
    return {"kind": "no_melee", "disorder": True, "levels": 1}


def pre_shock_defender(die, morale, drms):
    """Defender's Pre-Melee Morale Check -> typed effect dict.
    Bands: stand / 1-2 lose 1 SP + disorder + retreat + 1 level /
    3-5 lose 2 SP + disorder + retreat + 2 levels /
    6+ lose 2 SP + rout & retreat."""
    over = die + sum(drms) - morale
    if over <= 0:
        return {"kind": "stand"}
    if over <= 2:
        return {"kind": "shock_loss", "sp": 1, "disorder": True,
                "retreat": True, "levels": 1}
    if over <= 5:
        return {"kind": "shock_loss", "sp": 2, "disorder": True,
                "retreat": True, "levels": 2}
    return {"kind": "shock_loss", "sp": 2, "rout": True,
            "retreat": True}


def form_square(die, morale, drms):
    """Forming Square in Reaction [8.4.2 #4] -> typed effect dict."""
    over = die + sum(drms) - morale
    if over <= 0:
        return {"kind": "square_formed"}
    if over <= 2:
        return {"kind": "square_failed", "disorder": True}
    return {"kind": "square_failed", "disorder": True, "levels": 1}


# ---------- melee result [8.5] ----------

def resolve_melee(tables, die, drm_total):
    """Melee Result Table lookup on the modified die. Returns the
    typed row: who loses, SPs lost, the morale consequence, and the
    other-effect keyword (retreat / melee_continues / rout_retreat).
    'retreat' = one Unsteady-style retreat move IN ADDITION to any
    morale-driven retreat (errata 2000-07-20)."""
    t = tables["melee"]["result_table"]
    m = die + drm_total
    if m <= 0:
        row = t["le_0"]
    elif m >= 9:
        row = t["ge_9"]
    else:
        row = t[str(m)]
    out = {"modified": m, "loser": row["loser"], "sp": row["sp_lost"],
           "other": row["other"]}
    if row["morale"] == "routs":
        out["morale"] = {"kind": "rout"}
    elif row["morale"] == "check":
        # each side that lost the SP checks morale [8.5.3]
        out["morale"] = {"kind": "morale_check", "drm": 0}
    else:
        out["morale"] = {"kind": "lose_levels",
                         "levels": int(row["morale"][1])}
    return out


# ---------- pursuit [8.4.2 #8] ----------

def pursuit(die, morale, drms):
    """Pursuit Table: hexes of involuntary pursuit (0 = none)."""
    over = die + sum(drms) - morale
    if over <= 0:
        return 0
    if over <= 2:
        return 1
    if over <= 4:
        return 2
    return 3


# ---------- terrain gates [TEC combat_effects, formations block] ----------
# rows = game.json formations.combat_effects.rows; columns are
# [fire, melee, cav_charge, defensive] per the columns list there.

def terrain_melee_drm(rows, row_names):
    """Sum the TEC Melee-column DRMs for the defender's hex/hexsides.
    Returns (drm, allowed): 'NA' anywhere = melee not allowed across/
    into that feature (deep stream, sharp slopes)."""
    drm, allowed = 0, True
    for name in row_names:
        cell = rows[name][1]
        if cell == "NA":
            allowed = False
        elif cell != "NE":
            drm += int(cell)
    return drm, allowed


def terrain_defensive(rows, row_names):
    """Is the defender in Defensive terrain (must be Assaulted, may
    not be Bayoneted)? [8.2/8.3 + TEC Defensive column]"""
    return any(rows[name][3] == "Yes" for name in row_names)


def terrain_chargeable(rows, row_names):
    """May cavalry charge into/through these TEC rows? [8.4.1 + TEC
    Cav Charge column]"""
    return all(rows[name][2] == "Yes" for name in row_names)
