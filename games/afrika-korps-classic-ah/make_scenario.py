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
    "name": "Afrika Korps campaign (March 1941 Situation) — Tier 2 complete",
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
            "victory: elimination of all enemy combat units on the board (clarification 13: at-sea excluded) and two-consecutive-turn control of both fortresses + both home bases (4.1-4.3); Allied win by survival through 15 Oct 1942 (4.2); no-supplies-for-two-turns loss (24.5)",
            "SUPPLY CAPTURE (15): automatic capture when a combat unit moves adjacent to / onto an unaccompanied enemy supply (15.21, one-directional trigger per 15.211), fortress shielding (15.23, capture by combat-phase 'attack' with advance 16.3), the one-unit capture-attack on accompanied supplies with mandatory escort battles (15.322, clarification figs 6/7/11), retreat/advance pickup (15.22 incl. the sustaining-supply exception), post-capture rights per method (15.21 free / 15.33-15.34 move-only incl. escape from the old escort's ZOC / 15.23 frozen), voluntary destruction (15.4), counter recycling to the off-board pools, and the fig-3 guard: no voluntary move into a hopeless capture position (7.4 supersedes 15.21)",
            "ISOLATION (24): the 24.1 trace (also used by 11.9), elimination after two consecutive own player turns isolated at start AND end (24.2, clarification 8: mid-turn supply that is gone by turn end does not break the count), at-sea isolation (24.4), and the two-turn no-supplies-on-board game loss (24.5)",
            "REPLACEMENTS (20, from 1 March 1942 per the printed track): accrual at the start of the own player turn for controlled home base/Tobruch (Axis 1+1, Allied 2+1), accumulation (20.5/20.6), spending attack factors to return eliminated combat units under the reinforcement rules (20.4); substitutes never return as replacements (21.6)",
            "SUBSTITUTES (21, Allied, from 1 Aug 1942 per the printed track): equal-attack-factor exchange at the end of the movement portion in one hex (21.1/21.2), type matching from the counter-face symbols (armor <-> armor/armored-infantry, infantry <-> infantry/recce — all 61 Allied counters visually classified), breakdown with the 21.4 factor/MF constraints, stacking 21.5, never at sea/off-board (21.6), only real substitute counters (21.7)",
            "AUTOMATIC VICTORY (9): declaration during movement at 7-1, or 5-1 with a defender that provably cannot survive a back-2 (9.1), supply trace at the instant with the defender's own ZOC still blocking (9.2 + clarification sec 10), ZOC negation for the rest of the turn with move-over-but-never-onto the AVed unit (9.1), attacker/blocker freeze (9.2/9.3), end-of-movement supply revalidation with the two-supply expenditure (14.5), and mandatory resolution before the turn ends (9.6)",
        ],
        "not_enforced": [
            "corner cases umpired (declared, gate never permits an illegal state): 7.4's voluntary-vs-forced distinction beyond the solo-attack + support-presence tests, the 11.7 fortress twice-attacked exception, 7.61's retreating-player pick of overstack casualties, 21.3's mid-exchange breakdown during combat resolution, 9.4's joined-AV bookkeeping beyond the freeze, Rommel isolation displacement when encircled with friends (22.4 second clause)",
            "web build (web/) still runs the legacy JS engine — the AK gate is Python/HTTP only",
        ],
    },
    "supply_table": {
        "windows": SUPPLY_TABLE,
        "cite": "12.2 SUPPLY TABLE (rulebook) == printed track wedges 15 Apr 41 / 1 Jul 41 / 1 Dec 41 — cross-validated in validate_arrivals.py",
    },
    "replacements": {
        "start_turn": labels.index("1 March 1942") + 1,
        "rates": {"Axis": {"homebase": 1, "fortress_port": 1},
                  "Allied": {"homebase": 2, "fortress_port": 1}},
        "cite": "20.1 starting March 1942 (Time Record 'Begin Replacement Rate' at 1 March 1942, printed '1 1T 2'); 20.2 Axis 1/turn home base + 1/turn Tobruch; 20.3 Allied 2/turn home base + 1/turn Tobruch; control at the beginning of the player turn per 4.3; 20.5 factors accumulate; 20.4 placement per the reinforcement rules; 21.6 substitutes never enter as replacements",
    },
    "substitutes": {
        "start_turn": labels.index("1 August 1942") + 1,
        "side": "Allied",
        "cite": "21.1 starting August 1942 (Time Record 'Substitute Units now available' at 1 Aug 1942); armor for armor/armored-infantry, infantry for infantry/recce, equal attack factors; 21.2 at the end of the Allied movement portion, same hex, no movement after placement; 21.5 stacking limits before and after; 21.6 not at sea/off board",
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
