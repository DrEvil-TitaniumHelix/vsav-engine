"""Generate scenario_campaign.json from the module's setup save.

Deployed units = pieces standing on playable terrain (the March 1941
Situation Chart placement, rules 2.3). Reserve = pieces parked on the
printed Order of Appearance track and holding boxes (rules 2.2) plus
status markers — visible on the board, outside the Tier-1 gate.

Run:  python games/afrika-korps-classic-ah/make_scenario.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "engine"))
sys.path.insert(0, HERE)
import board  # noqa: E402
import gamespec  # noqa: E402
from validate_arrivals import SCHEDULE, SUPPLY_TABLE  # noqa: E402  canonical, 4-source validated

g = gamespec.Game(HERE)
b = board.Board(g.setup_save, g)

due = {slot: turn for turn, side, slot, factors in SCHEDULE}
deployed, reserve = [], []
for u in sorted(b.units(), key=lambda u: int(u["id"])):
    t = g.hex_terrain(u["col"], u["row"])
    cls = g.unit_class(u["name"])
    if t in (None, "offmap", "sea", "qattara") or cls == "markers":
        reserve.append(dict(id=u["id"], slot=u["name"], side=u["side"],
                            **({"cls": cls} if cls else {}),
                            **({"due": due[u["name"]]} if u["name"] in due else {})))
    else:
        deployed.append(dict(id=u["id"], slot=u["name"], side=u["side"],
                             hex=[u["col"], u["row"]]))

# every scheduled arrival must exist exactly once in the reserve
sched_in_reserve = [r for r in reserve if "due" in r]
assert len(sched_in_reserve) == len(SCHEDULE) == len(due), \
    f"schedule/reserve mismatch: {len(sched_in_reserve)} vs {len(SCHEDULE)}"

# own supply pools still off board (2.4): arrival stock for 12.1/12.2.
# Captured-supply counters represent Tier-2 capture states — excluded.
supply_pool = {}
for side, prefix in (("Axis", "G Supply "), ("Allied", "A Supply ")):
    pool = [r["id"] for r in sorted(reserve, key=lambda r: r["slot"])
            if r["slot"].startswith(prefix) and "Captured" not in r["slot"]]
    supply_pool[side] = pool
assert len(supply_pool["Axis"]) == 2 and len(supply_pool["Allied"]) == 3, \
    f"supply pools changed: {supply_pool}"  # G Supply 2,3 / A Supply 2,3,4

# ---- sanity assertions (fail loudly rather than write a wrong scenario)
n_ax = sum(1 for u in deployed if u["side"] == "Axis")
n_al = sum(1 for u in deployed if u["side"] == "Allied")
assert (len(deployed), n_al, n_ax) == (23, 12, 11), \
    f"deployment split changed: {len(deployed)} ({n_al} Allied / {n_ax} Axis)"
w6 = [u for u in deployed if u["hex"] == [4, 27]]
assert len(w6) == 11, f"Axis start force at W6 should be 11 pieces, got {len(w6)}"
forts = {tuple(u["hex"]) for u in deployed if u["side"] == "Allied"}
assert (31, 11) in forts and (8, 12) in forts, "Tobruch/Bengasi garrisons missing"
assert not any("Sub" in u["slot"] for u in deployed), "substitute counters deployed"

# ---- 38 half-month turns, 1 April 1941 .. 15 October 1942 (3.5, 4.1)
labels = []
months = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
y, m = 1941, 3            # April 1941
for _ in range(19):
    labels += [f"1 {months[m]} {y}", f"15 {months[m]} {y}"]
    m += 1
    if m == 12:
        m, y = 0, y + 1
labels = labels[:38]
assert labels[0] == "1 April 1941" and labels[-1] == "15 October 1942"

scenario = {
    "name": "Afrika Korps campaign (March 1941 Situation) — Tier 2 combat",
    "mode": "strategic",
    "rules_scope": {
        "enforced": [
            "player-turn alternation, Axis first (3.1-3.5); arrivals precede movement (3.1/3.3); all movement precedes combat (5.3), battles resolved one at a time (3.2/3.4, 8.6)",
            "movement factors & terrain (5.2, 5.6, 5.7, 5.8)",
            "enemy combat units block on-top/through; lone supply/Rommel do not (5.4, 22.3, 15.22)",
            "stacking: 3 combat units, checked at end of movement and destinations (2.3, 6.1, 6.3)",
            "ZOC: stop on entry, no pass-through, same-unit first-step ban, supply exclusion, fortress immunity BOTH ways, no ZOC across the E18-F19/W62-X62 hexsides (7.1, 8.1, 8.3, 13.2, 19.5, 23.1-23.2)",
            "coast road bonus +10 via road hexsides, I26 two-road exception (17.1-17.3)",
            "escarpment stop/one-hex + road exceptions, one non-road move (18.1-18.5)",
            "reinforcement arrivals per the validated Order of Appearance (19.1-19.8, 2.2): controlled port at start of turn, Tobruch/own home base only, later landing allowed, full move on arrival",
            "supply arrivals: Allied 1/turn max 4 own on board (12.1), Axis Supply Table die roll max 3 own (12.2) — engine-owned seeded dice; land-or-forfeit (12.4); declining allowed (12.5)",
            "port control snapshots at start of player turn (4.3: occupation by combat/supply/Rommel; home bases also ZOC-free)",
            "sea movement Tobruch <-> own home base (23.3-23.5): embark/at-sea/land cycle, control to land, ZOC-or-control to embark, overdue-at-sea elimination (23.42)",
            "Rommel movement bonus (22.1 + module tournament clarification): up to +2 hexes per unit once per turn, requires Rommel's explicit co-moved path segment; Rommel cannot be attacked/eliminated, displaces to the closest friendly combat unit when alone in enemy ZOC (22.4-22.42); no voluntary lone move into enemy ZOC (22.41)",
            "COMBAT on the two-source-validated CRT (back of rulebook == printed map, 66 cells): odds rounded in the defender's favor (7.3), >6-1 automatic elimination without a roll, no voluntary attack worse than 1-6 (7.4, 9.1), engine-owned seeded die",
            "mandatory combat: every unit in enemy ZOC attacks, every enemy with units in its ZOC is attacked, attacker adjacency, no splitting, one battle per unit per turn, legal partitions only (7.2, 8.4-8.5, 11.3-11.8)",
            "defense doubled on fortress/escarpment (10.2); attack factors never terrain-affected (8.7)",
            "attack supply: 1-2 or better requires a stated supply within 5 ZOC-free hexes of ALL attackers (route carve-out for the attacked units' own ZOC per 13.2 + tournament clarification figs 12/15); used supply removed at end of the player turn; 1-3 or worse free (14.1-14.7)",
            "results: A/D Elim, Exchange with terrain-doubled defense factors and at-least-no-more removal, back-2 retreats chosen by the WINNER under 7.61/7.62 (immediate-elimination avoidance, no hex twice, never the battle hex — tournament clarifications 7/9), fortress no-retreat elimination (23.7)",
            "advance after combat into vacated fortress/escarpment hexes before the next battle (16.1-16.3)",
            "pre-combat eliminations: isolated in enemy ZOC with no legal supply-free attack (11.9, 24.1, clarifications sec. 5); forced to attack worse than 1-6 (7.4) — strictly before any battle",
            "fortress combat: attacks into a fortress engage every unit in it; fortress sorties must attack all adjacent enemies; attacks around a fortress optional both ways (23.1-23.2)",
            "victory: elimination of all enemy combat units on the board (clarification 13: at-sea excluded) and two-consecutive-turn control of both fortresses + both home bases (4.1-4.3); Allied win by survival through 15 Oct 1942 (4.2)",
        ],
        "not_enforced": [
            "Automatic Victory ZOC negation during movement (9.1-9.7) — the gate is STRICTER: a 7-1 declared in combat still auto-eliminates, but AV movement-phase pass-through is not yet offered",
            "supply capture (15): moving/retreating onto or adjacent to an unaccompanied enemy supply does not yet flip it — umpire captures manually; captured-supply counters stay in reserve",
            "isolation attrition (24.2-24.5): two-turn isolation elimination and the no-supplies game loss are not tracked (the 24.1 supply trace IS used for 11.9)",
            "replacements (20) and substitute units (21)",
            "corner cases umpired (declared, gate never permits an illegal state): 7.4's voluntary-vs-forced distinction beyond the solo-attack test (multi-unit support feasibility not searched), the 11.7 fortress twice-attacked exception, 7.61's retreating-player pick of overstack casualties, 15.22 mid-retreat supply pickup",
        ],
    },
    "supply_table": {
        "windows": SUPPLY_TABLE,
        "cite": "12.2 SUPPLY TABLE (rulebook) == printed track wedges 15 Apr 41 / 1 Jul 41 / 1 Dec 41 — cross-validated in validate_arrivals.py",
    },
    "supply_pool": supply_pool,
    "supply_max_on_board": {"Axis": 3, "Allied": 4,
                            "cite": "12.2 / 12.1 own-supply on-board maxima"},
    "game": {
        "turns": 38,
        "first_player": "Axis",
        "side_labels": {"Axis": "Axis (German-Italian)",
                        "Allied": "Allied (British Commonwealth)"},
        "turn_labels": labels,
        "cite": "3.1-3.5 sequence of play; 2.2-2.3 setup; game span 1.1/4.1",
    },
    "units": deployed,
    "reserve": reserve,
}

out = os.path.join(HERE, "scenario_campaign.json")
json.dump(scenario, open(out, "w", encoding="utf-8"), indent=1)
print(f"scenario_campaign.json: {len(deployed)} deployed "
      f"({n_al} Allied / {n_ax} Axis), {len(reserve)} reserve/track pieces, "
      f"{len(labels)} turns {labels[0]} .. {labels[-1]}")
