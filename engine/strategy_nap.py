"""
strategy_nap.py - A parameterized strategy family for GBoNW napoleonic
games (spec #22: the expertise standard), Austerlitz A15.1 Northern
Flank first.

Unlike the strategic families (strategy_bg / strategy_ww), a napoleonic
genome is NOT a turn-plan: GBoNW decisions INTERLEAVE between the sides
(LIM draws, reaction and shock windows, return fire), so a per-turn plan
has nothing stable to bind to. The genome instead parameterizes the
DOCTRINE KNOBS of the stateless per-action policy
(ai_napoleonic.DOCTRINE). Every action the parameterized policy picks
still enters through the one legality gate - a genome can prefer
differently, never act illegally.

The genes span the command economy the A15.1 victory actually prices
(French win at 7 Allied units destroyed/routed/unsteady, Allied at 10
French [A15.1]): pool commitment against the fatigue spiral [13.1/13.2],
initiative sequencing [4.4], Full-vs-Limited activation risk
[4.5.1/4.6/4.7], breakdown offers [4.7], the stand-off distance [5.1],
cavalry May-Charge preservation and charge acceptance [5.1.2/8.4],
melee odds appetite [8.2], the square-vs-charge answer [8.4.2#4], and
artillery unlimber timing [6.3.7].

Not parameterized, with reasons: rally order (every eligible unit gets
its independent attempt each Rally Phase [12.0], so priority cannot
change outcomes); the policy's declared-weak list (melee supports,
strategic movement, reaction limber, countercharge) stays out - a gene
may only re-weight decisions the validated policy already makes, never
grant it new mechanics.

theta == baseline() IS the shipped policy: baselines are read from
ai_napoleonic.DOCTRINE, the single source of the shipped constants
(validate_ai.py proves the equivalence action-by-action).

Used by engine/optimize.py for tournament evolution via families.py.
Deterministic given (theta, game state); no LLM, no randomness of its own.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai_napoleonic as anp     # noqa: E402

_D = anp.DOCTRINE

GENES = [
    # name, min, max, baseline (= ai_napoleonic.DOCTRINE, the shipped policy)
    ("pool_fatigue_max", 0.0, 9.0, _D["pool_fatigue_max"]),   # LIM committed below this fatigue [13.1/13.2]
    ("pool_enemy_near", 0.0, 10.0, _D["pool_enemy_near"]),    # ...or with an enemy this close [13.2]
    ("init_own_first", 0.0, 1.0, _D["init_own_first"]),       # initiative picks own LIM first [4.4]
    ("full_enemy_dist", 0.0, 15.0, _D["full_enemy_dist"]),    # Full Activation with enemy within this [4.6]
    ("full_rating_min", 4.0, 10.0, _D["full_rating_min"]),    # ...or leader rating at least this [4.5.1/4.7]
    ("bd_take", 0.0, 1.0, _D["bd_take"]),                     # take breakdown offers [4.7]
    ("hold_dist", 0.0, 12.0, _D["hold_dist"]),                # never voluntarily close inside this [5.1]
    ("cav_preserve_slack", 0.0, 12.0, _D["cav_preserve_slack"]),  # May-Charge cap while enemy <= MA+this [5.1.2]
    ("charge_accept", 0.0, 1.0, _D["charge_accept"]),         # cavalry declares charges at all [8.4]
    ("melee_sp_ratio", 0.5, 2.5, _D["melee_sp_ratio"]),       # melee only at this x defender SP [8.2]
    ("square_form", 0.0, 1.0, _D["square_form"]),             # form square against a charge [8.4.2#4]
    ("unlimber_slack", -2.0, 4.0, _D["unlimber_slack"]),      # unlimber at fire range + this [6.3.7]
]


def baseline():
    return {n: b for n, _, _, b in GENES}


def random_theta(rng):
    return {n: rng.uniform(lo, hi) for n, lo, hi, _ in GENES}


def mutate(theta, rng, rate=0.35, scale=0.25):
    out = dict(theta)
    for n, lo, hi, _ in GENES:
        if rng.random() < rate:
            out[n] = min(hi, max(lo, out[n] + rng.gauss(0, (hi - lo) * scale)))
    return out


def crossover(a, b, rng):
    return {n: (a if rng.random() < 0.5 else b)[n] for n, _, _, _ in GENES}


def corners():
    """Doctrine-seeded corners of the space (spec #22: seed the population
    from knowledge). A15.1's asymmetric thresholds - the French need 7
    Allied units broken, the Allied 10 French - reward two opposite
    postures: REFUSE (rest divisions, stand off, decline bad odds; deny
    the enemy his 7) and PRESS (commit everything, force the Full
    Activations, take every shock; race to the threshold first)."""
    refuse = baseline()
    refuse.update(pool_fatigue_max=4.0, full_enemy_dist=4.0,
                  full_rating_min=9.0, hold_dist=3.0, melee_sp_ratio=1.6,
                  charge_accept=0.0, unlimber_slack=2.0)
    press = baseline()
    press.update(pool_enemy_near=8.0, full_enemy_dist=15.0,
                 full_rating_min=5.0, melee_sp_ratio=0.75,
                 cav_preserve_slack=8.0, unlimber_slack=2.0)
    return [refuse, press]


GENE_PROSE = {
    "pool_fatigue_max": "a division's LIM goes into the pool while its "
                        "fatigue is under {v:.1f} (policy rests it from "
                        "6, 13.1/13.2)",
    "pool_enemy_near": "a fatigued division still commits its LIM when "
                       "an enemy stands within {v:.0f} hexes - it will "
                       "fight anyway (13.2)",
    "init_own_first": "initiative picks an own-side LIM first: {alt} "
                      "(no = hand the enemy division the opening "
                      "instead, 4.4)",
    "full_enemy_dist": "a division attempts the Full Activation with an "
                       "enemy within {v:.0f} hexes - melee and free "
                       "adjacency need Full (4.6)",
    "full_rating_min": "beyond that range, Full is attempted only when "
                       "the leader's activation rating is at least "
                       "{v:.0f}; otherwise the roll-free Limited march "
                       "beats gambling on the Breakdown Table "
                       "(4.5.1/4.7)",
    "bd_take": "breakdown Enemy/Reactivate offers are taken: {alt} "
               "(a free activation, 4.7)",
    "hold_dist": "units never voluntarily close inside {v:.0f} hexes "
                 "(0 = close to contact; a stand-off gates the "
                 "approach, never forces a retreat, 5.1)",
    "cav_preserve_slack": "cavalry preserves May Charge (spends at most "
                          "half MA) while an enemy is within MA+{v:.0f} "
                          "hexes (5.1.2)",
    "charge_accept": "cavalry declares charges: {alt} (8.4)",
    "melee_sp_ratio": "infantry melees only when its stack has {v:.2f}x "
                      "the defender stack's SP or better (policy parity "
                      "is 1.0, 8.2/8.5.1)",
    "square_form": "infantry answers a declared charge by forming "
                   "square: {alt} (8.4.2#4)",
    "unlimber_slack": "artillery unlimbers at its fire range {v:+.0f} "
                      "hexes (6.3.7)",
}


EXECUTE_NOTE = ("strategy_nap.StrategyPlanner(genome) parameterizes the "
                "doctrine knobs of the stateless per-action policy "
                "(ai_napoleonic.DOCTRINE) - napoleonic decisions "
                "interleave, so there is no turn-plan DSL; every pick "
                "still enters through the legality gate")


class StrategyPlanner:
    """Planner callable for plans.play_game: for the napoleonic family
    the 'plan' IS the doctrine genome - plans.py hands it to
    ai_napoleonic as theta."""

    def __init__(self, theta):
        self.theta = dict(theta)

    def __call__(self, g, side):
        return self.theta
