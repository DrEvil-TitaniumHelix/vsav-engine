import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai_soj as aso     # noqa: E402

_D = aso.DEFAULTS

GENES = [
    ("sector", 0.0, 1.0, _D["sector"]),
    ("sector_width", 0.04, 0.30, _D["sector_width"]),
    ("escalade_share", 0.0, 0.8, _D["escalade_share"]),
    ("tower_commit", 0.0, 1.0, _D["tower_commit"]),
    ("cav_flank", 0.0, 1.0, _D["cav_flank"]),
    ("archer_stand", 1.0, 4.0, _D["archer_stand"]),
    ("stage_dist", 2.0, 6.0, _D["stage_dist"]),
    ("target_pref", 0.0, 2.0, _D["target_pref"]),
    ("protect_leader", 0.0, 1.0, _D["protect_leader"]),
    ("jud_wall_share", 0.2, 0.9, _D["jud_wall_share"]),
    ("jud_reserve_depth", 1.0, 6.0, _D["jud_reserve_depth"]),
    ("jud_react", 0.0, 6.0, _D["jud_react"]),
    ("jud_react_size", 2.0, 25.0, _D["jud_react_size"]),
    ("sortie", 0.0, 1.0, _D["sortie"]),
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
    ram = baseline()
    ram.update(escalade_share=0.0, tower_commit=1.0, sector_width=0.06,
               stage_dist=2.0)
    ladders = baseline()
    ladders.update(escalade_share=0.75, tower_commit=0.0, sector_width=0.2,
                   stage_dist=2.0, archer_stand=1.0)
    wide = baseline()
    wide.update(sector_width=0.3, escalade_share=0.5, tower_commit=1.0,
                target_pref=1.5)
    walls = baseline()
    walls.update(jud_wall_share=0.9, jud_reserve_depth=1.0, jud_react=6.0,
                 sortie=0.0)
    reserve = baseline()
    reserve.update(jud_wall_share=0.3, jud_reserve_depth=2.0, jud_react=0.0,
                   jud_react_size=25.0, sortie=1.0)
    return [ram, ladders, wide, walls, reserve]


GENE_PROSE = {
    "sector": "the Roman assault sector is centred at {v:.2f} of the way "
              "round the assaultable perimeter (0.62 = the shipped north "
              "wall choice; the perimeter is the 63 wall hexes with an "
              "outside approach, ordered by angle round the city)",
    "sector_width": "the sector spans {v:.2f} of the perimeter (breach "
                    "targets, escalade spots and tower posts are all drawn "
                    "from it)",
    "escalade_share": "{v:.2f} of the heavy infantry not crewing engines "
                      "carries ladders against the sector walls [6.5]; the "
                      "rest stage for the breach",
    "tower_commit": "{v:.2f} of the siege towers are crewed and pushed to "
                    "their posts (0 = park them all) [10.x]",
    "cav_flank": "cavalry rides the high end of the sector's perimeter "
                 "window: {alt} (no = the low end)",
    "archer_stand": "velitae/archers hold {v:.0f} hexes off the sector "
                    "walls, outside the ram lane [4.x missile ranges]",
    "stage_dist": "assault cohorts stage {v:.0f} hexes from the sector "
                  "before the breach opens",
    "target_pref": "fire targets weight fresh occupants at {v:.2f} per "
                   "unit against plain nearest-hex (0 = closest legal "
                   "target)",
    "protect_leader": "loss allocations spare leaders: {alt}",
    "jud_wall_share": "{v:.2f} of the Judaean units left after the "
                      "strongpoint garrisons [SR1] man the walls "
                      "(plain wall hexes first); the rest form the "
                      "reserve",
    "jud_reserve_depth": "the Judaean reserve stands {v:.0f} hexes "
                         "inside the walls",
    "jud_react": "the reserve commits once breach damage reaches "
                 "{v:.0f} (or a breach opens, or three walls are "
                 "threatened)",
    "jud_react_size": "at most {v:.0f} fresh reserve units react per "
                      "movement phase",
    "sortie": "the Judaeans take counterattack windows: {alt} [14.x]",
}


EXECUTE_NOTE = ("strategy_soj.StrategyPlanner(genome) parameterizes the "
                "sector-template and doctrine knobs of the per-action "
                "policy (ai_soj.DEFAULTS) - siege decisions interleave "
                "(pendings, fire segments), so there is no turn-plan DSL; "
                "every pick still enters through the legality gate")


class StrategyPlanner:
    def __init__(self, theta):
        self.theta = dict(theta)

    def __call__(self, g, side):
        return self.theta
