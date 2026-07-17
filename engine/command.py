"""
command.py - Family A core: chit-pull command pool table resolvers.

Pure, data-driven lookups over a game.json `command` block (the GBoNW
reference implementation: Austerlitz [4.0-4.8, A4.2-A4.3]). No state, no
dice - the gate owns both; these functions only read cited table data, so
a transcription fix never touches code (spec #14).

Reused by any chit-pull/random-activation family game: the tables change,
the shapes stay.
"""


def breakdown(cmd, personality, die, prior=None):
    """Command Breakdown Table [4.7]: personality column (A/N/C) x d10.
    `prior` = the breakdown result that opened this (chained) activation
    attempt: ENEMY twice in a row = STOP, REACTIVATE twice = FULL [4.7]."""
    res = cmd["command_breakdown"]["by_die"][str(die)][personality]
    if prior == "enemy" and res == "enemy":
        return "stop"
    if prior == "reactivate" and res == "reactivate":
        return "full"
    return res


def independent_allowance(cmd, side_key, die):
    """Independent Activation Table [A4.3.2]: how many of the side's
    Independent leaders may attempt activation this draw."""
    return int(cmd["independent_activation"][side_key][str(die)])


def command_change(cmd, side_key, die, buxhowden=False):
    """Command Change Table [4.2]: die -> effect key. Buxhowden rolling
    adds one (table note; rolls off the bottom stay 'none')."""
    if buxhowden:
        die = die + 1
    table = cmd["command_change"][side_key]
    key = str(min(die, 9))
    return table[key]


def fatigue_threshold_effects(new_level, crossed):
    """Fatigue Effects Table [13.3] + errata 2000-07-20: the ONE-TIME
    immediate effects triggered by RISING to a level. `crossed` = set of
    thresholds this division already triggered. Returns (effects, newly):
    effects = list of "morale_level" / "disorder" to apply now."""
    out = []
    newly = []
    for level, effects in ((7, ["morale_level"]), (8, ["disorder"]),
                           (9, ["morale_level", "disorder"])):
        if new_level >= level and level not in crossed:
            out.extend(effects)
            newly.append(level)
    return out, newly
