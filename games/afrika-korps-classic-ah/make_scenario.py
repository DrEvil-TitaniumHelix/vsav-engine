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
    "name": "Afrika Korps campaign (March 1941 Situation) — Tier 1 movement",
    "mode": "strategic",
    "rules_scope": {
        "enforced": [
            "player-turn alternation, Axis first (3.1-3.5); arrivals precede movement (3.1/3.3)",
            "movement factors & terrain (5.2, 5.6, 5.7, 5.8)",
            "enemy combat units block on-top/through; lone supply/Rommel do not (5.4, 22.3, 15.22)",
            "stacking: 3 combat units, checked at end of movement and destinations (2.3, 6.1, 6.3)",
            "ZOC: stop on entry, no pass-through, same-unit first-step ban, supply exclusion, fortress immunity (7.1, 8.1, 8.3, 13.2, 19.5)",
            "coast road bonus +10 via road hexsides, I26 two-road exception (17.1-17.3)",
            "escarpment stop/one-hex + road exceptions, one non-road move (18.1-18.5)",
            "reinforcement arrivals per the validated Order of Appearance (19.1-19.8, 2.2): controlled port at start of turn, Tobruch/own home base only, later landing allowed, full move on arrival",
            "supply arrivals: Allied 1/turn max 4 own on board (12.1), Axis Supply Table die roll max 3 own (12.2) — engine-owned seeded dice; land-or-forfeit (12.4); declining allowed (12.5)",
            "port control snapshots at start of player turn (4.3: occupation by combat/supply/Rommel; home bases also ZOC-free)",
            "sea movement Tobruch <-> own home base (23.3-23.5): embark/at-sea/land cycle, control to land, ZOC-or-control to embark, overdue-at-sea elimination (23.42)",
            "Rommel movement bonus (22.1 + module tournament clarification): up to +2 hexes per unit once per turn, requires Rommel's explicit co-moved path segment",
        ],
        "not_enforced": [
            "combat and everything downstream (3.2/3.4, 7-11, 14-16) — Tier 2",
            "supply capture consequences (15) and supply consumption (14) — Tier 2; supply units move under 13/5.4 only",
            "isolation (24) — depends on the supply-line subsystem, Tier 2",
            "replacements (20) and substitute units (21) — need eliminated units, meaningless before combat",
            "victory adjudication (4.1-4.3) — needs combat; game ends unadjudicated after turn 38 (19.8 unlanded-reinforcement elimination IS applied then)",
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
