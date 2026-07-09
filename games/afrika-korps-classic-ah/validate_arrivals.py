"""Afrika Korps arrivals data cross-validation (spec #12 evidence).

The CANONICAL reinforcement schedule below (also consumed by
make_scenario.py) was established 2026-07-09 by direct visual read of the
printed Turn Record track on the module map art, cell by cell (see
VALIDATION.md, ARRIVALS section). This script re-verifies it against every
independent source on disk:

  1. the mastermind track transcription (image-only read of the printed
     track): C:/VassalIngest/afrika-korps-classic-ah/map_tables_transcription.json
  2. the mastermind counter-face transcription (independent read of the
     75x75 counter PNGs): counter_stats.json — factors must agree
  3. the module setup save: reserve pieces are physically parked on the
     printed track (rules 2.2); their x-position clusters must reproduce
     the schedule's turn groups in order
  4. game.json stats patterns (the engine's own MFs) — factors must agree

Known transcription defect (recorded, corrected in the canonical data):
the 1 Aug 1941 Allied brigades print "5I" (5th Indian Division: 29, 9, 10)
— source 1 misread them as "51 Inf". Counter faces (source 2) and module
slot names both read 5 I. Factors identical (1-1-6), no gate impact.

The Axis supply-arrival wedges on the track (15 Apr 41: rolls 1-2 sunk "to
end of June"; 1 Jul 41: rolls 1-3 sunk "to end of November"; 1 Dec 41:
roll 1 sunk "to end of game") are the printed form of the rulebook 12.2
SUPPLY TABLE columns (Apr-Jun / Jul-Nov / Dec-end) — cross-checked here.

Run:  python games/afrika-korps-classic-ah/validate_arrivals.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "engine"))
import gamespec  # noqa: E402
import board  # noqa: E402

ING = os.path.join(HERE, "..", "..", "..", "VassalIngest", "afrika-korps-classic-ah")

# --------------------------------------------------------------- canonical
# turn = 1..38 (1 = "1 April 1941"); slot = module piece name; factors as
# printed A-D-M. Visually verified against the printed track cell by cell.
SCHEDULE = [
    # 1 May 1941 (turn 3) — Axis: 15th Panzer Division
    (3, "Axis", "G 15Pz 8", "7-7-10"),
    (3, "Axis", "G 15Pz 115", "3-3-10"),
    (3, "Axis", "G 15Pz 33", "2-2-12"),
    # 1 June 1941 (turn 5) — Allied: 7th Armoured + 4th Indian
    (5, "Allied", "A 7 Arm 4", "4-4-7"),
    (5, "Allied", "A 7 Arm 7", "3-3-7"),
    (5, "Allied", "A 7 Arm 7 S.G", "1-1-7"),
    (5, "Allied", "A 7 Arm 4SA Motor", "1-1-6"),
    (5, "Allied", "A 4 I Inf 23", "1-1-6"),
    # 1 July 1941 (turn 7) — Allied
    (7, "Allied", "A 50 Inf 6SA Motor", "1-1-6"),
    (7, "Allied", "A 2 SA Inf 4", "1-1-6"),
    (7, "Allied", "A 2 SA Inf 6", "1-1-6"),
    (7, "Allied", "A 2 SA Inf 7 Recce", "1-1-12"),
    (7, "Allied", "A 9A Inf 18", "2-2-6"),
    (7, "Allied", "A 50 Inf 69", "1-1-6"),
    (7, "Allied", "A 50 Inf 150", "1-1-6"),
    (7, "Allied", "A 50 Inf 151", "1-1-6"),
    # 1 Aug 1941 (turn 9) — Allied: 70th + 5th INDIAN (printed "5I", NOT "51")
    (9, "Allied", "A 70 Inf 23", "1-1-6"),
    (9, "Allied", "A 5 I Inf 29", "1-1-6"),
    (9, "Allied", "A 5 I Inf 9", "1-1-6"),
    (9, "Allied", "A 5 I Inf 10", "1-1-6"),
    # 1 Nov 1941 (turn 15) — Allied 13 units (largest cell)
    (15, "Allied", "A 1 SA Inf 1", "1-1-6"),
    (15, "Allied", "A 1 SA Inf 2", "1-1-6"),
    (15, "Allied", "A 1 SA Inf 3", "1-1-6"),
    (15, "Allied", "A 1 SA Inf 5", "1-1-6"),
    (15, "Allied", "A 1 SA Inf 3 Recce", "1-1-12"),
    (15, "Allied", "A 1 Arm", "2-2-7"),
    (15, "Allied", "A 1 Arm 2", "4-4-7"),
    (15, "Allied", "A 1 Arm 22", "4-4-7"),
    (15, "Allied", "A 1 Arm 201 Gds", "2-2-6"),
    (15, "Allied", "A 2 NZ Inf 4", "1-1-6"),
    (15, "Allied", "A 2 NZ Inf 5", "1-1-6"),
    (15, "Allied", "A 2 NZ Inf 6", "1-1-6"),
    (15, "Allied", "A 32 Arm", "2-2-7"),
    # 1 Nov 1941 (turn 15) — Axis
    (15, "Axis", "G 90Inf 361", "3-3-7"),
    (15, "Axis", "I Trieste", "3-4-6"),
    (15, "Axis", "I Sabratha", "2-2-4"),
    (15, "Axis", "I Facists", "2-3-4"),
    # 1 Feb 1942 (turn 21) — Axis: 90th Light
    (21, "Axis", "G 90Inf 55", "2-2-7"),
    (21, "Axis", "G 90Inf 200", "2-2-7"),
    (21, "Axis", "G 90Inf 580", "2-2-12"),
    # 1 May 1942 (turn 27) — Allied
    (27, "Allied", "A 8 I Inf 18", "1-1-6"),
    (27, "Allied", "A 10 I Inf 21", "1-1-6"),
    (27, "Allied", "A 10 I Inf 25", "1-1-6"),
    (27, "Allied", "A Free Fr Inf", "1-1-6"),
    (27, "Allied", "A Jews Inf", "1-1-6"),
    # 1 June 1942 (turn 29) — Axis
    (29, "Axis", "G 51 Fj", "4-4-7"),
    (29, "Axis", "I Centor", "2-2-4"),
    (29, "Axis", "I Pistolio", "2-2-4"),
    (29, "Axis", "G 164Inf 125", "2-2-7"),
    (29, "Axis", "G 164Inf 382", "2-2-7"),
    (29, "Axis", "G 164Inf 433", "2-2-7"),
    # 1 Aug 1942 (turn 33) — Allied ("Substitute Units now available" printed here)
    (33, "Allied", "A 10 Arm 8", "3-3-7"),
    (33, "Allied", "A 10 Arm 23", "3-3-7"),
    (33, "Allied", "A 9A Inf 24", "2-2-6"),
    (33, "Allied", "A 8 I Inf 161", "1-1-6"),
    (33, "Allied", "A 44 Inf 61", "1-1-6"),
    (33, "Allied", "A 44 Inf 132", "1-1-6"),
    # 1 Aug 1942 (turn 33) — Axis
    (33, "Axis", "I Littorio", "4-5-6"),
    (33, "Axis", "I Folgere", "1-1-7"),
    # 1 Oct 1942 (turn 37) — Allied
    (37, "Allied", "A 51 Inf 1", "1-1-6"),
    (37, "Allied", "A 51 Inf 2", "1-1-6"),
    (37, "Allied", "A NZ 2 Inf", "1-1-6"),
]

# 12.2 SUPPLY TABLE windows, printed on the track as sunk-roll wedges.
# turn ranges are inclusive; sunk = die rolls losing the Axis supply.
SUPPLY_TABLE = [
    {"turns": [1, 6], "sunk": [1, 2],
     "track": "15 Apr 41 wedges 1,2 'to end of June'"},
    {"turns": [7, 16], "sunk": [1, 2, 3],
     "track": "1 Jul 41 wedges 1,2,3 'to end of November'"},
    {"turns": [17, 38], "sunk": [1],
     "track": "1 Dec 41 wedge 1 'to end of game'"},
]

# transcription id_text -> module slot (documents every naming delta,
# including the corrected 5I misread)
ID_TO_SLOT = {
    "15 Pz / 8": "G 15Pz 8", "15 Pz / 115": "G 15Pz 115",
    "15 Pz / 33 Recce": "G 15Pz 33",
    "7 Arm / 4": "A 7 Arm 4", "7 Arm / 7": "A 7 Arm 7",
    "7 Arm / 7 S.G.": "A 7 Arm 7 S.G",
    "7 Arm / 4SA Motor": "A 7 Arm 4SA Motor",
    "4 I Inf / 23": "A 4 I Inf 23",
    "50 Inf / 6SA Motor": "A 50 Inf 6SA Motor",
    "2SA / 4": "A 2 SA Inf 4", "2SA / 6": "A 2 SA Inf 6",
    "2SA / 7 Recce": "A 2 SA Inf 7 Recce",
    "9A / 18": "A 9A Inf 18",
    "50 Inf / 69": "A 50 Inf 69", "50 Inf / 150": "A 50 Inf 150",
    "50 Inf / 151": "A 50 Inf 151",
    "70 Inf / 23": "A 70 Inf 23",
    # transcription misread "51 Inf" — printed track and counter faces say 5I
    "51 Inf / 29": "A 5 I Inf 29", "51 Inf / 9": "A 5 I Inf 9",
    "51 Inf / 10": "A 5 I Inf 10",
    "1SA / 1": "A 1 SA Inf 1", "1SA / 2": "A 1 SA Inf 2",
    "1SA / 3": "A 1 SA Inf 3", "1SA / 5": "A 1 SA Inf 5",
    "1SA / 3 Recce": "A 1 SA Inf 3 Recce",
    "1 Arm (id 1)": "A 1 Arm", "1 Arm / 2": "A 1 Arm 2",
    "1 Arm / 22": "A 1 Arm 22", "1 Arm / 201 Gds": "A 1 Arm 201 Gds",
    "2NZ / 4": "A 2 NZ Inf 4", "2NZ / 5": "A 2 NZ Inf 5",
    "2NZ / 6": "A 2 NZ Inf 6",
    "32 Arm": "A 32 Arm",
    "90 Inf / 361": "G 90Inf 361",
    "It Trieste": "I Trieste", "It Sabratha": "I Sabratha",
    "It Facists": "I Facists",
    "90 Inf / 55": "G 90Inf 55", "90 Inf / 200": "G 90Inf 200",
    "90 Inf / 580 Recce": "G 90Inf 580",
    "8 I Inf / 18": "A 8 I Inf 18",
    "10 I Inf / 21": "A 10 I Inf 21", "10 I Inf / 25": "A 10 I Inf 25",
    "Free Fr / 1": "A Free Fr Inf", "Jews": "A Jews Inf",
    "51 Fj (id 51)": "G 51 Fj",
    "It Centor": "I Centor", "It Pistolio": "I Pistolio",
    "164 Inf / 125": "G 164Inf 125", "164 Inf / 382": "G 164Inf 382",
    "164 Inf / 433": "G 164Inf 433",
    "10 Arm / 8": "A 10 Arm 8", "10 Arm / 23": "A 10 Arm 23",
    "9A / 24": "A 9A Inf 24",
    "8 I Inf / 161": "A 8 I Inf 161",
    "44 Inf / 61": "A 44 Inf 61", "44 Inf / 132": "A 44 Inf 132",
    "It Littorio": "I Littorio", "It Folgere": "I Folgere",
    "51 Inf / 1": "A 51 Inf 1", "51 Inf / 2": "A 51 Inf 2",
    "NZ / 2": "A NZ 2 Inf",
}

TURN_NAME = {}  # 1..38 -> "1941 1 April" style used by the transcription
months = ["April", "May", "June", "July", "Aug", "Sep", "Oct", "Nov", "Dec",
          "Jan", "Feb", "March", "April", "May", "June", "July", "Aug", "Sep", "Oct"]
t = 1
for i, m in enumerate(months):
    year = 1941 if i < 9 else 1942
    for half in ("1", "15"):
        TURN_NAME[t] = f"{year} {half} {m}"
        t += 1
assert TURN_NAME[1] == "1941 1 April" and TURN_NAME[38] == "1942 15 Oct"

fails = []


def check(cond, what):
    print(("  PASS  " if cond else "  FAIL  ") + what)
    if not cond:
        fails.append(what)


def main():
    # -------------------------------------------- source 1: transcription
    print("source 1 — mastermind track transcription:")
    tx = json.load(open(os.path.join(ING, "map_tables_transcription.json"),
                        encoding="utf-8"))
    tx_units = {}   # (turn, side, slot) -> factors, via ID_TO_SLOT
    for e in tx["order_of_appearance"]["entries"]:
        for u in e.get("units", []):
            slot = ID_TO_SLOT.get(u["id_text"])
            check(slot is not None, f"transcription id '{u['id_text']}' maps to a module slot")
            turn = [k for k, v in TURN_NAME.items() if v == e["turn"]]
            check(len(turn) == 1, f"transcription turn '{e['turn']}' resolves")
            tx_units[(turn[0], e["side"].capitalize(), slot)] = u["factors"]

    canon = {(t_, s, sl): f for t_, s, sl, f in SCHEDULE}
    check(set(tx_units) == set(canon),
          f"transcription unit set == canonical schedule ({len(canon)} arrivals, "
          f"{len(set(canon) - set(tx_units))} missing / {len(set(tx_units) - set(canon))} extra)")
    fmis = [k for k in canon if k in tx_units and tx_units[k] != canon[k]]
    check(not fmis, f"factors agree on every arrival ({len(canon) - len(fmis)}/{len(canon)})")

    # supply wedge windows vs the rulebook 12.2 table
    sup = {e["turn"]: e["axis_supply"] for e in tx["order_of_appearance"]["entries"]
           if e.get("axis_supply")}
    check(sup.get("1941 15 April", {}).get("markers") == [1, 2]
          and "June" in sup.get("1941 15 April", {}).get("window", ""),
          "supply wedges 15 Apr 41 = sunk on 1,2 to end of June (12.2 col 1)")
    check(sup.get("1941 1 July", {}).get("markers") == [1, 2, 3]
          and "November" in sup.get("1941 1 July", {}).get("window", ""),
          "supply wedges 1 Jul 41 = sunk on 1,2,3 to end of November (12.2 col 2)")
    check(sup.get("1941 1 Dec", {}).get("markers") == [1]
          and "game" in sup.get("1941 1 Dec", {}).get("window", ""),
          "supply wedge 1 Dec 41 = sunk on 1 to end of game (12.2 col 3)")
    check(SUPPLY_TABLE[0]["turns"] == [1, 6] and SUPPLY_TABLE[1]["turns"] == [7, 16]
          and SUPPLY_TABLE[2]["turns"] == [17, 38],
          "SUPPLY_TABLE turn windows = Apr-Jun 41 / Jul-Nov 41 / Dec 41-end (12.2)")

    # ------------------------------------------- source 2: counter-face stats
    print("source 2 — counter-face transcription:")
    cs = json.load(open(os.path.join(ING, "counter_stats.json"), encoding="utf-8"))["counters"]
    bad = [sl for _, _, sl, f in SCHEDULE
           if cs.get(sl + ".png", {}).get("factors") != f]
    check(not bad, f"counter faces confirm all {len(SCHEDULE)} arrival factors"
                   + (f" (mismatch: {bad})" if bad else ""))
    for sl in ("A 5 I Inf 29", "A 5 I Inf 9", "A 5 I Inf 10"):
        check(cs[sl + ".png"]["id_text"].startswith("5I"),
              f"counter face '{sl}' reads 5I (5th Indian), not 51")

    # --------------------------------------------- source 3: module positions
    print("source 3 — module setup pieces parked on the printed track:")
    g = gamespec.Game(HERE)
    b = board.Board(g.setup_save, g)
    onmap = ("clear", "escarpment", "qattara_partial", "fortress", "homebase")
    sched_slots = {sl for _, _, sl in canon}
    placed = {}
    for u in b.units():
        t_ = g.hex_terrain(u["col"], u["row"])
        if t_ not in onmap and u["name"] in sched_slots:
            placed[u["name"]] = (u["x"], u["y"], u["side"])
    check(set(placed) == sched_slots,
          f"every scheduled arrival is a reserve piece off the playable map "
          f"({len(placed)}/{len(sched_slots)})")

    # cluster by x (Allied above the track y<300, Axis below y>300; counters
    # within a printed arrival box sit <=100px apart, boxes sit >=110px apart)
    for side in ("Allied", "Axis"):
        xs = sorted((x, sl) for sl, (x, y, s) in placed.items() if s == side)
        groups, cur = [], [xs[0]]
        for x, sl in xs[1:]:
            if x - cur[-1][0] > 100:
                groups.append(cur)
                cur = []
            cur.append((x, sl))
        groups.append(cur)
        turns = sorted({t_ for t_, s, sl in canon if s == side})
        check(len(groups) == len(turns),
              f"{side}: {len(groups)} position clusters == {len(turns)} arrival turns")
        for turn, grp in zip(turns, groups):
            want = {sl for t_, s, sl in canon if s == side and t_ == turn}
            got = {sl for x, sl in grp}
            check(got == want,
                  f"{side} cluster @x~{int(sum(x for x, _ in grp)/len(grp))} == "
                  f"turn {turn} ({TURN_NAME[turn]}) group of {len(want)}")

    # --------------------------------------------- source 4: game.json stats
    print("source 4 — engine stats patterns:")
    bad = [(sl, g.stats(sl), f) for _, _, sl, f in SCHEDULE
           if "-".join(str(x) for x in g.stats(sl)) != f]
    check(not bad, f"game.json stats agree on all {len(SCHEDULE)} arrivals"
                   + (f" (mismatch: {bad})" if bad else ""))

    print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILURES'}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
