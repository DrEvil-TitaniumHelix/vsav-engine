"""Afrika Korps Tier-1 submit-gate validation (spec #9/#12 evidence).

Drives a scripted opening through StrategicGame — legal moves AND illegal
proposals (wrong player turn, double move, reserve/track pieces, unreachable
destinations, ending the phase while overstacked) — asserting every verdict
with its rulebook citation, then replays the produced audit log through
engine/verify_game.py. The illegal proposals are logged too: the log proves
they never touched the game state.

Run:  python games/afrika-korps-classic-ah/validate_gate.py
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "engine"))
import gamespec  # noqa: E402
import strategic  # noqa: E402
import verify_game  # noqa: E402

g = gamespec.Game(HERE)
tmp = tempfile.mkdtemp()
sg = strategic.StrategicGame(g, os.path.join(HERE, "scenario_campaign.json"),
                             tmp, seed=20260709)

fails = []


def check(cond, what):
    print(("  PASS  " if cond else "  FAIL  ") + what)
    if not cond:
        fails.append(what)


def by_slot(slot):
    return next(u for u in sg.s["units"].values() if u["slot"] == slot)


def expect(side, action, legal, what, contains=None):
    r = sg.submit(side, action)
    ok = r["verdict"]["legal"] == legal
    if ok and contains:
        ok = any(contains in reason for reason in r["verdict"]["reasons"])
    check(ok, f"{what} -> {r['verdict']['reasons'] or r.get('result')}")
    return r


W6 = [4, 27]
print("phase discipline (3.1/3.3):")
gds = by_slot("A 22 Gds Inf")
expect("Allied", {"type": "move", "unit": gds["pid"], "dest": [37, 13]},
       False, "Allied move during the Axis player turn is ILLEGAL", "3.1/3.3")

print("legal Axis movement:")
pz5 = by_slot("G 21Pz 5")
lm = sg.legal_moves(pz5["pid"])
check(lm["can_act"] and len(lm["dests"]) > 50,
      f"21Pz/5 (MF {lm['budget']}) has rich legal destinations from W6 "
      f"({len(lm['dests'])} incl. coast road bonus)")
dest = max(lm["dests"], key=lambda d: d["col"])          # far east along the road
expect("Axis", {"type": "move", "unit": pz5["pid"], "dest": [dest["col"], dest["row"]]},
       True, f"21Pz/5 W6 -> {g.grid.display_name(dest['col'], dest['row'])} "
             f"(cost {dest['cost']}) is LEGAL")
expect("Axis", {"type": "move", "unit": pz5["pid"], "dest": W6},
       False, "moving 21Pz/5 AGAIN is ILLEGAL", "5.2, 5.5")

print("reserve/track pieces are outside the Tier-1 scope:")
res_unit = next(u for u in sg.reserve.values() if u["side"] == "Axis"
                and not u.get("cls"))
res_marker = next(u for u in sg.reserve.values() if u.get("cls") == "markers")
expect("Axis", {"type": "move", "unit": res_unit["id"], "dest": W6},
       False, f"moving OOA-track reinforcement '{res_unit['slot']}' is ILLEGAL",
       "scheduled reinforcement")
expect("Axis", {"type": "move", "unit": res_marker["id"], "dest": W6},
       False, f"moving status marker '{res_marker['slot']}' is ILLEGAL")

print("destination legality flows from the validated movement engine:")
expect("Axis", {"type": "move", "unit": by_slot("I Savena")["pid"], "dest": [31, 11]},
       False, "Savena (MF 4) to Tobruch G25 across the map is ILLEGAL")
expect("Axis", {"type": "move", "unit": by_slot("I Bologna")["pid"], "dest": [4, 26]},
       False, "Bologna into sea hex V5 is ILLEGAL")

print("stacking must be legal to end the player turn (2.3/6.1/6.3):")
expect("Axis", {"type": "end_phase"}, False,
       "Axis end_phase with 8 combat units still at W6 is ILLEGAL", "6.1")
moved = 0
for slot in ["G 21Pz 104", "G 21Pz 3", "I Ariete", "I Bologna", "I Brescia"]:
    u = by_slot(slot)
    dd = sg.legal_moves(u["pid"])["dests"]
    tgt = next(d for d in dd
               if (d["col"], d["row"]) != tuple(W6) and d["cost"] >= 1)
    r = sg.submit("Axis", {"type": "move", "unit": u["pid"],
                           "dest": [tgt["col"], tgt["row"]]})
    moved += r["verdict"]["legal"]
check(moved == 5, f"dispersal: 5 more Axis units moved off W6 ({moved}/5 legal)")
expect("Axis", {"type": "end_phase"}, True,
       "Axis end_phase after dispersal (3 combat left at W6) is LEGAL")

print("Allied player turn:")
expect("Axis", {"type": "move", "unit": by_slot("I Pavia")["pid"], "dest": [5, 27]},
       False, "Axis move during the Allied player turn is ILLEGAL", "3.1/3.3")
expect("Allied", {"type": "end_phase"}, False,
       "Allied end_phase with 4 combat units at L59 is ILLEGAL", "6.1")
pol = by_slot("A Pol Carpathian")
dd = sg.legal_moves(pol["pid"])["dests"]
tgt = next(d for d in dd if d["cost"] >= 1)
expect("Allied", {"type": "move", "unit": pol["pid"], "dest": [tgt["col"], tgt["row"]]},
       True, f"Poles disperse L59 -> {g.grid.display_name(tgt['col'], tgt['row'])}")
r = expect("Allied", {"type": "end_phase"}, True,
           "Allied end_phase ends game turn 1")
check(sg.s["turn"] == 2 and sg.s["mover"] == "Axis"
      and sg.turn_label() == "15 April 1941",
      f"game turn 2 begins ({sg.turn_label()}), Axis moves first [3.5]")

print("independent verifier replay of the produced audit log:")
ok, msg = verify_game.verify(HERE, sg.log_path)
check(ok, f"verify_game: {msg}")
n_ill = sum(1 for l in open(sg.log_path, encoding="utf-8")
            if '"legal": false' in l)
check(n_ill >= 9, f"the log records {n_ill} rejected proposals verbatim")

shutil.rmtree(tmp, ignore_errors=True)
print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILURES'}")
sys.exit(1 if fails else 0)
