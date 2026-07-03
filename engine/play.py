"""
play.py - The application: an AI plays a side through VASSAL saves.

Loads a board, reasons with the spec-driven engine (legal moves, mandatory
combat, CRT), picks moves for a side, and writes a new .vsav VASSAL can load.
Unit stats and all movement semantics come from the game spec.

Usage:
  python play.py [--game <dir>] turn <save.vsav> <side> <out.vsav> [die]
  python play.py [--game <dir>] analyze <save.vsav> <side>
"""
import sys
import board as board_mod
import gamespec
import rules


def is_combat_unit(game, u):
    a, d, m = game.stats(u["name"])
    # rows 0-1 are the off-map reinforcement holding boxes / turn track, not the
    # playing area (heuristic; terrain-based on_map is the precise filter).
    hmax = game.holding_row_max if game.holding_row_max is not None else -1
    return (m > 0 and u["row"] > hmax - 1 and "DZ" not in u["name"]
            and "Game Turn" not in u["name"])


def nearest_enemy(game, unit, units, enemy):
    es = [u for u in units if u["side"] == enemy and is_combat_unit(game, u)]
    if not es:
        return None
    return min(es, key=lambda e: game.hex_distance((unit["col"], unit["row"]),
                                                   (e["col"], e["row"])) or 99)


def analyze(game, units, side):
    enemy = game.enemy(side)
    n = sum(1 for u in units if u["side"] == side and is_combat_unit(game, u))
    print(f"=== {side} situation: {n} combat units ===\n")
    for u in sorted([u for u in units if u["side"] == side and is_combat_unit(game, u)],
                    key=lambda u: u["hexnum"]):
        a, d, m = game.stats(u["name"])
        dests = game.legal_destinations(u, m, units)
        adj_enemy = [e for e in units if e["side"] == enemy and
                     (e["col"], e["row"]) in game.neighbors(u["col"], u["row"])]
        tag = f" MUST ATTACK {[e['name'] for e in adj_enemy]}" if adj_enemy else ""
        print(f"  {u['hexnum']} {u['name']:<14} [{a}-{d}-{m}]  {len(dests)} legal moves{tag}")


def take_turn(game, b, side, out_path, die=4):
    """One simple AI turn: resolve mandatory combats (report), then advance the most
    forward unit toward the enemy. Writes the resulting move to a new save."""
    units = b.units()
    enemy = game.enemy(side)
    log = []
    # 1) mandatory combats (units adjacent to enemy must attack) -- resolve & report
    for u in units:
        if u["side"] != side or not is_combat_unit(game, u):
            continue
        adj = [e for e in units if e["side"] == enemy and
               (e["col"], e["row"]) in game.neighbors(u["col"], u["row"])]
        for e in adj:
            terr = game.hex_terrain(e["col"], e["row"]) or "clear"
            res = rules.resolve_combat(game.stats(u["name"])[0],
                                       game.stats(e["name"])[1], terr, die)
            log.append(f"COMBAT {u['name']} -> {e['name']} @ {e['hexnum']}: "
                       f"{game.stats(u['name'])[0]} vs {game.stats(e['name'])[1]} "
                       f"({terr}, die {die}) = {res}")
    # 2) movement: pick the friendly combat unit nearest an enemy and step it closer
    movers = [u for u in units if u["side"] == side and is_combat_unit(game, u)]
    chosen, best, target = None, 99, None
    for u in movers:
        ne = nearest_enemy(game, u, units, enemy)
        if not ne:
            continue
        dist = game.hex_distance((u["col"], u["row"]), (ne["col"], ne["row"]))
        if dist and 1 < dist < best:
            chosen, best, target = u, dist, ne
    if chosen:
        dests = game.legal_destinations_t(chosen, game.stats(chosen["name"])[2],
                                          [u for u in units if game.on_map(u["col"], u["row"])
                                           and u["id"] != chosen["id"]])
        if dests:
            goal = min(dests, key=lambda h: game.hex_distance(h, (target["col"], target["row"])) or 99)
            msg = b.move_piece(chosen["name"], game.grid.hexnum(*goal))
            b.write(out_path)
            log.append(f"MOVE {msg} (closing on {target['name']} @ {target['hexnum']}); "
                       f"wrote {out_path}")
    return log


if __name__ == "__main__":
    args = sys.argv[1:]
    game_dir = gamespec.default_game_dir()
    if args and args[0] == "--game":
        game_dir = args[1]; args = args[2:]
    game = gamespec.Game(game_dir)
    cmd, save, side = args[0], args[1], args[2]
    b = board_mod.Board(save, game)
    if cmd == "analyze":
        analyze(game, b.units(), side)
    elif cmd == "turn":
        out = args[3]
        die = int(args[4]) if len(args) > 4 else 4
        for line in take_turn(game, b, side, out, die):
            print(line)
