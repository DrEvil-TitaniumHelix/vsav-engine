"""
play.py - The application: Claude plays a side of Arnhem through VASSAL saves.

Loads a board, reasons with the rules engine (legal moves, mandatory combat, CRT),
picks moves for a side, and writes a new .vsav VASSAL can load. This is the AI opponent
loop. Terrain is treated as clear pending per-hex map data (flagged); unit factors come
from the player-aid cards (pattern table below).

Usage:
  python play.py turn <save.vsav> <Ger|All> <out.vsav> [die]
  python play.py analyze <save.vsav> <Ger|All>
"""
import sys, arnhem, rules

# Unit combat factors (ATT, DEF, MOVE) from the player-aid cards. Pattern-matched by
# name fragment; falls back to a sensible default. (Authoritative list in ref/rules_and_oob.md.)
STAT_PATTERNS = [
    ("9SS Recon", (2, 2, 12)), ("9SS Arty", (0, 3, 7)), ("Kraft", (3, 3, 7)),
    ("Grsn", (2, 2, 12)), ("BrDf", (2, 2, 7)), ("Hnke", (4, 3, 10)), ("Wlt", (0, 2, 7)),
    ("Hber", (0, 2, 7)), ("Hbr", (5, 5, 10)), ("Jng", (2, 3, 7)), ("2107", (4, 4, 10)),
    ("180", (2, 3, 7)), ("vT", (3, 3, 7)), ("-59", (3, 3, 7)), ("406", (2, 2, 7)),
    ("6P", (2, 3, 7)), ("1PT", (2, 2, 7)), ("1P", (2, 2, 7)),
    ("9SS", (4, 4, 7)), ("10SS Arty", (0, 3, 7)), ("10SS", (3, 4, 7)),
    ("DZ", (0, 0, 0)), ("Game Turn", (0, 0, 0)),
    ("Arty", (0, 2, 7)), ("Fire", (0, 2, 7)), ("Engineers", (3, 3, 10)),
    ("Pol", (2, 2, 7)), ("82-", (2, 2, 7)), ("101-", (2, 2, 7)),
    ("325", (2, 3, 7)), ("327", (2, 3, 7)),
    ("130", (5, 5, 7)), ("214", (5, 5, 7)), ("129", (5, 5, 7)), ("32", (4, 3, 10)),
    ("231", (4, 3, 10)), ("5-1C", (4, 3, 10)), ("5-2", (4, 3, 10)), ("55", (3, 3, 10)),
    ("1-1", (2, 2, 7)), ("1-2", (2, 2, 7)), ("1-4", (2, 2, 7)),
]
DEFAULT_STAT = (2, 2, 7)

def stats(name):
    for frag, st in STAT_PATTERNS:
        if frag in name:
            return st
    return DEFAULT_STAT

def is_combat_unit(u):
    a, d, m = stats(u["name"])
    # rows 0-1 are the off-map reinforcement holding boxes / turn track, not the playing
    # area -- exclude them (heuristic; precise holding-box layout needs the map data).
    return (m > 0 and u["row"] >= 2 and "DZ" not in u["name"]
            and "Game Turn" not in u["name"])

def nearest_enemy(unit, board, enemy):
    es = [u for u in board if u["side"] == enemy and is_combat_unit(u)]
    if not es:
        return None
    return min(es, key=lambda e: rules.hex_distance((unit["col"], unit["row"]),
                                                     (e["col"], e["row"])) or 99)

def analyze(board, side):
    enemy = "All" if side == "Ger" else "Ger"
    print(f"=== {side} situation: {sum(1 for u in board if u['side']==side and is_combat_unit(u))} combat units ===\n")
    for u in sorted([u for u in board if u["side"] == side and is_combat_unit(u)],
                    key=lambda u: u["hexnum"]):
        a, d, m = stats(u["name"])
        dests = rules.legal_destinations(u, m, board)
        adj_enemy = [e for e in board if e["side"] == enemy and
                     (e["col"], e["row"]) in rules.neighbors(u["col"], u["row"])]
        tag = f" MUST ATTACK {[e['name'] for e in adj_enemy]}" if adj_enemy else ""
        print(f"  {u['hexnum']} {u['name']:<14} [{a}-{d}-{m}]  {len(dests)} legal moves{tag}")

def take_turn(board, side, out_path, src_vsav, die=4):
    """One simple AI turn: resolve mandatory combats (report), then advance the most
    forward unit toward the enemy. Writes the resulting move to a new save."""
    enemy = "All" if side == "Ger" else "Ger"
    log = []
    # 1) mandatory combats (units adjacent to enemy must attack) -- resolve & report
    for u in board:
        if u["side"] != side or not is_combat_unit(u):
            continue
        adj = [e for e in board if e["side"] == enemy and
               (e["col"], e["row"]) in rules.neighbors(u["col"], u["row"])]
        for e in adj:
            res = rules.resolve_combat(stats(u["name"])[0], stats(e["name"])[1], "clear", die)
            log.append(f"COMBAT {u['name']} -> {e['name']} @ {e['hexnum']}: "
                       f"{stats(u['name'])[0]} vs {stats(e['name'])[1]} (clear, die {die}) = {res}")
    # 2) movement: pick the friendly combat unit nearest an enemy and step it closer
    movers = [u for u in board if u["side"] == side and is_combat_unit(u)]
    chosen, best = None, 99
    for u in movers:
        ne = nearest_enemy(u, board, enemy)
        if not ne:
            continue
        dist = rules.hex_distance((u["col"], u["row"]), (ne["col"], ne["row"]))
        if dist and 1 < dist < best:
            chosen, best, target = u, dist, ne
    if chosen:
        dests = rules.legal_destinations(chosen, stats(chosen["name"])[2], board)
        if dests:
            goal = min(dests, key=lambda h: rules.hex_distance(h, (target["col"], target["row"])) or 99)
            gx, gy = arnhem.hex_to_pixel(*goal)
            plain, md, sd = arnhem.read_vsav(src_vsav)
            new_plain, info = arnhem.move_unit(plain, chosen["name"], gx, gy)
            arnhem.write_vsav(out_path, new_plain, md, sd)
            log.append(f"MOVE {chosen['name']} {chosen['hexnum']} -> {goal[0]:02d}{goal[1]:02d} "
                       f"(closing on {target['name']} @ {target['hexnum']}); wrote {out_path}")
    return log

if __name__ == "__main__":
    cmd = sys.argv[1]
    save = sys.argv[2]
    side = sys.argv[3]
    plain, md, sd = arnhem.read_vsav(save)
    board = arnhem.parse_board(plain)
    if cmd == "analyze":
        analyze(board, side)
    elif cmd == "turn":
        out = sys.argv[4]
        die = int(sys.argv[5]) if len(sys.argv) > 5 else 4
        for line in take_turn(board, side, out, save, die):
            print(line)
