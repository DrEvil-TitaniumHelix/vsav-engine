"""
watch.py - Gated monitor: detect + validate the human's moves between two save states.

The loop: the human moves a piece in VASSAL and hits Save. The watcher sees the
file change, diffs the board against the last-known state, and rules on every change:
  LEGAL    - destination is reachable per the rules model (MA budget, ZOC stop, occupancy)
  ILLEGAL  - with the specific reason (too far / ZOC violation / etc.)
  ENTERED / LEFT MAP - reinforcement deployment or elimination (holding boxes <-> map)

All game knowledge (stats, grid, ZOC mode, holding rows) comes from the game spec.

Usage:
  python watch.py [--game <dir>] diff  <old.vsav> <new.vsav>
  python watch.py [--game <dir>] live  <save.vsav> [side]
"""
import os, sys, time
import board
import gamespec


def snapshot(path, game):
    """id -> unit dict, for every counter."""
    return {u["id"]: u for u in board.Board(path, game).units()}


def on_map(game, u):
    hmax = game.holding_row_max if game.holding_row_max is not None else -1
    return u["row"] > hmax


def judge_move(game, u_old, u_new, old_units):
    """Validate one piece's move against the rules model built on the OLD board."""
    ma = game.stats(u_old["name"])[2]
    old_board = [u for u in old_units.values() if on_map(game, u)]
    legal = game.legal_destinations(u_old, ma, old_board)
    dest = (u_new["col"], u_new["row"])
    if dest in legal:
        d = game.hex_distance((u_old["col"], u_old["row"]), dest)
        return f"LEGAL ({d} of {ma} MP)"
    # diagnose why
    d = game.hex_distance((u_old["col"], u_old["row"]), dest)
    if d is None:
        return "ILLEGAL: unreachable"
    if d > ma:
        return f"ILLEGAL: {d} hexes exceeds movement allowance {ma}"
    enemy = game.enemy(u_old["side"])
    if (u_old["col"], u_old["row"]) in game.zoc_hexes(old_board, enemy):
        return "ILLEGAL: started in enemy ZOC (may only leave via combat)"
    if dest in game.zoc_hexes(old_board, enemy):
        return f"ILLEGAL: path enters enemy ZOC before {u_new['hexnum']} (must stop on entry)"
    return f"ILLEGAL: no legal path within {ma} MP (blocked by units/ZOC)"


def diff(game, old_units, new_units, side_filter=None):
    lines = []
    for pid, u_new in new_units.items():
        u_old = old_units.get(pid)
        if u_old is None:
            lines.append(f"NEW COUNTER  {u_new['name']} at {u_new['hexnum']}")
            continue
        if (u_old["x"], u_old["y"]) == (u_new["x"], u_new["y"]):
            continue
        if side_filter and u_new["side"] != side_filter:
            continue
        tag = f"{u_new['name']:<16} {u_old['hexnum']} -> {u_new['hexnum']}"
        if not on_map(game, u_old) and on_map(game, u_new):
            lines.append(f"DEPLOYED     {tag}  (from holding box - reinforcement)")
        elif on_map(game, u_old) and not on_map(game, u_new):
            lines.append(f"REMOVED      {tag}  (to holding box - eliminated/withdrawn)")
        elif not on_map(game, u_old) and not on_map(game, u_new):
            lines.append(f"BOX SHUFFLE  {tag}  (off-map, not judged)")
        else:
            lines.append(f"MOVE         {tag}  {judge_move(game, u_old, u_new, old_units)}")
    for pid, u_old in old_units.items():
        if pid not in new_units:
            lines.append(f"GONE         {u_old['name']} (was {u_old['hexnum']})")
    return lines


def live(game, path, side_filter=None, poll=1.0):
    print(f"watching {path} (Ctrl+C to stop)...")
    last_mtime = None
    old_units = None
    while True:
        try:
            mt = os.path.getmtime(path)
        except OSError:
            time.sleep(poll); continue
        if mt != last_mtime:
            time.sleep(0.3)  # let VASSAL finish writing
            new_units = snapshot(path, game)
            if old_units is not None:
                out = diff(game, old_units, new_units, side_filter)
                stamp = time.strftime("%H:%M:%S")
                print(f"\n[{stamp}] save changed:")
                for l in (out or ["  (no piece changes)"]):
                    print("  " + l)
            else:
                print(f"baseline loaded: {len(new_units)} counters")
            old_units, last_mtime = new_units, mt
        time.sleep(poll)


if __name__ == "__main__":
    args = sys.argv[1:]
    game_dir = gamespec.default_game_dir()
    if args and args[0] == "--game":
        game_dir = args[1]; args = args[2:]
    game = gamespec.Game(game_dir)
    cmd = args[0]
    if cmd == "diff":
        old, new = snapshot(args[1], game), snapshot(args[2], game)
        for l in diff(game, old, new) or ["(no piece changes)"]:
            print(l)
    elif cmd == "live":
        live(game, args[1], args[2] if len(args) > 2 else None)
