import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai_naw as anw     # noqa: E402

_D = anw.DEFAULTS

GENES = [
    ("aggression", 0.0, 1.0, _D["aggression"]),
    ("risk", 0.0, 1.5, _D["risk"]),
    ("terrain", 0.0, 1.5, _D["terrain"]),
    ("cohesion", 0.0, 1.5, _D["cohesion"]),
    ("exit_turn", 2.0, 10.0, _D["exit_turn"]),
    ("exit_weak", 1.0, 7.0, _D["exit_weak"]),
    ("north_drive", 0.0, 1.5, _D["north_drive"]),
    ("hold_row", 4.0, 12.0, _D["hold_row"]),
    ("block", 0.0, 1.5, _D["block"]),
    ("advance", 0.0, 1.0, _D["advance"]),
    ("art_stand", 0.0, 1.0, _D["art_stand"]),
    ("bombard_min", 3.0, 8.0, _D["bombard_min"]),
    ("prussian_target", 0.0, 1.0, _D["prussian_target"]),
    ("concentrate", 0.0, 1.0, _D["concentrate"]),
    ("pocket", 0.0, 1.5, _D["pocket"]),
    ("pocket_risk", 0.0, 1.5, _D["pocket_risk"]),
    ("race_push", 0.0, 1.0, _D["race_push"]),
    ("race_guard", 0.0, 1.0, _D["race_guard"]),
    ("runners", 0.0, 8.0, _D["runners"]),
    ("runner_turn", 1.0, 10.0, _D["runner_turn"]),
    ("dr_w", 0.0, 0.6, _D["dr_w"]),
    ("ar_w", 0.0, 0.6, _D["ar_w"]),
    ("ex_w", 0.0, 0.6, _D["ex_w"]),
    ("al_aggression", 0.0, 1.0, _D["al_aggression"]),
    ("al_risk", 0.0, 1.5, _D["al_risk"]),
    ("al_terrain", 0.0, 1.5, _D["al_terrain"]),
    ("al_cohesion", 0.0, 1.5, _D["al_cohesion"]),
    ("al_advance", 0.0, 1.0, _D["al_advance"]),
    ("al_bombard_min", 3.0, 8.0, _D["al_bombard_min"]),
    ("al_pocket", 0.0, 1.5, _D["al_pocket"]),
    ("al_pocket_risk", 0.0, 1.5, _D["al_pocket_risk"]),
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
    hammer = baseline()
    hammer.update(aggression=1.0, risk=0.2, north_drive=0.2, exit_turn=9.0, concentrate=1.0)
    runner = baseline()
    runner.update(aggression=0.25, risk=1.2, north_drive=1.5, exit_turn=3.0, exit_weak=7.0)
    line = baseline()
    line.update(aggression=0.25, risk=1.2, terrain=1.5, cohesion=1.2, hold_row=9.0, block=1.5)
    counterpunch = baseline()
    counterpunch.update(aggression=0.9, risk=0.3, hold_row=7.0, block=0.4, prussian_target=1.0, advance=1.0)
    guns = baseline()
    guns.update(bombard_min=3.0, art_stand=1.0, aggression=0.5, terrain=1.0, al_bombard_min=3.0)
    pocketer = baseline()
    pocketer.update(pocket=1.2, pocket_risk=1.0, al_pocket=1.2, al_pocket_risk=1.0, dr_w=0.3)
    relay = baseline()
    relay.update(runners=4.0, runner_turn=4.0, pocket=0.8, race_push=1.0, race_guard=0.8)
    wall = baseline()
    wall.update(al_aggression=0.3, al_risk=1.2, al_terrain=1.5, al_pocket_risk=1.2, al_pocket=1.0,
                hold_row=9.0, aggression=0.8, pocket=1.0)
    return [hammer, runner, line, counterpunch, guns, pocketer, relay, wall]


GENE_PROSE = {
    "aggression": "attacks are planned down to the {v:.2f} mark of the odds ladder (1.0 = accept 1:1 "
                  "attacks, 0.5 = mass for 3:1, 0 = only 5:1 or better) [CRT p.5]",
    "risk": "a hex the enemy can reach next Player-Turn is discounted by {v:.2f} times the "
            "expected loss there",
    "terrain": "Town and Woods/Road hexes (defender doubled, TEC) are worth {v:.2f} times half "
               "the unit's Defense Strength",
    "cohesion": "each adjacent friendly unit (up to three) adds {v:.2f} x 0.4 to a hex",
    "exit_turn": "from Game-Turn {v:.0f} the weak French units start leaving by the eleven "
                 "arrowed North-edge hexes [VIC-08]",
    "exit_weak": "'weak' = Attack Strength {v:.0f} or less; those exit first, the strong "
                 "units keep fighting",
    "north_drive": "every French hex is pulled toward the nearest exit hex at {v:.2f} x 0.35 "
                   "per hex of distance (x2.5 once the Allies are demoralized) [DEM-01]",
    "hold_row": "the Allied line stands on map row {v:.0f}, between the French mass and the "
                "exit hexes",
    "block": "Allied units are pulled toward that line at {v:.2f} x 0.35 per hex",
    "advance": "victorious units advance after combat when the new hex scores at least "
               "{v:.2f} (0 = only clearly better hexes, 1 = nearly always) [OPTIONAL ADVANCE p.5]",
    "art_stand": "bombarding artillery stands fast on an Ar result: {alt} [ART-11]",
    "bombard_min": "free (unobligated) bombardments fire only at column {v:.0f} of the CRT "
                   "or better (3 = 1:2, 5 = 2:1, 6 = 3:1) [ART-01]",
    "prussian_target": "the Prussians enter {v:.2f} of the way toward the French mass "
                       "(0 = the northernmost free East-edge hex) [REI-02]",
    "concentrate": "when scoring a hex next to a target, {v:.2f} of the planned attack "
                   "strength on that target counts as already present",
    "pocket": "attacks are posted to deny the defender a retreat hex (an occupied "
              "neighbour and both its flanks are closed; two attackers on opposite sides "
              "close all six) - a defender with no safe hex is ELIMINATED on a Dr, so a "
              "pocketed Dr counts {v:.2f} x the full Defense Strength; extra attackers "
              "join to close the last gap when that is worth more than 0.6 "
              "[RETREAT AND ADVANCE p.5: no retreat into EZOC/off-map/Woods/enemy hex; S4]",
    "pocket_risk": "a threatened hex with fewer than three open neighbours (map edge, "
                   "Woods, friends, enemies) is discounted {v:.2f} x half its doubled "
                   "Defense Strength per missing neighbour - do not stand where a Dr kills",
    "race_push": "once the enemy has lost 25 Strength Points, aggression rises by {v:.2f} "
                 "per full 15 further points toward forty - the loss race is closed out "
                 "[VIC-01/VIC-03]",
    "race_guard": "once we have lost 25 Strength Points, aggression falls by {v:.2f} per "
                  "full 15 further points - stay above forty",
    "runners": "from the runner turn, the {v:.0f} weakest free French units become runners: "
               "no attack posts, strong pull to the exits, double threat discount, exit the "
               "moment an exit hex is in reach [VIC-02/VIC-08]",
    "runner_turn": "runners are designated from Game-Turn {v:.0f}",
    "dr_w": "a Defender-retreat result is worth {v:.2f} x the Defense Strength in the "
            "attack's expected value",
    "ar_w": "an Attacker-retreat result costs {v:.2f} x the melee Attack Strength",
    "ex_w": "an Exchange costs {v:.2f} x the melee Attack Strength [EX: attacker loses at "
            "least the defender's printed strength, bombarding artillery exempt]",
    "al_aggression": "ALLIED seat override of aggression: {v:.2f}",
    "al_risk": "ALLIED seat override of risk: {v:.2f}",
    "al_terrain": "ALLIED seat override of terrain: {v:.2f}",
    "al_cohesion": "ALLIED seat override of cohesion: {v:.2f}",
    "al_advance": "ALLIED seat override of advance: {v:.2f}",
    "al_bombard_min": "ALLIED seat override of bombard_min: column {v:.0f}",
    "al_pocket": "ALLIED seat override of pocket: {v:.2f}",
    "al_pocket_risk": "ALLIED seat override of pocket_risk: {v:.2f}",
}


EXECUTE_NOTE = ("strategy_naw.StrategyPlanner(genome) parameterizes the attack planner "
                "and doctrine knobs of the per-action policy (ai_naw.DEFAULTS) - "
                "movement plans mass attackers on chosen targets, the Combat Phase "
                "resolves the fixed obligations best-first, pendings (victor-chosen "
                "retreats, exchanges, advances) interleave; every pick enters through "
                "the legality gate")


class StrategyPlanner:
    def __init__(self, theta):
        self.theta = dict(theta)

    def __call__(self, g, side):
        return self.theta
