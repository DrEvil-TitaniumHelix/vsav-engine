"""
capture_baseline.py - Regression harness for the spec-driven refactor.

Dumps, for a game's setup save: every counter (id/name/side/hex) and the full
terrain-aware legal-destination map for every ON-MAP unit. Deterministically
sorted JSON. Captured before the refactor, re-run after — identical file = the
generalized engine reproduces the original engine exactly.

Usage: python capture_baseline.py [--game <dir>] <out.json>
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board  # noqa: E402
import gamespec  # noqa: E402


def main(game_dir, out_path):
    game = gamespec.Game(game_dir)
    b = board.Board(game.setup_save, game)
    units = sorted(b.units(), key=lambda u: int(u["id"]))
    onmap = [u for u in units if game.on_map(u["col"], u["row"])]

    snapshot = {
        "counters": [
            {"id": u["id"], "name": u["name"], "side": u["side"],
             "hex": u["hexnum"], "x": u["x"], "y": u["y"],
             "terrain": game.hex_terrain(u["col"], u["row"]),
             "onmap": game.on_map(u["col"], u["row"])}
            for u in units
        ],
        "legal": {},
    }
    for u in onmap:
        ma = game.stats(u["name"])[2]
        rb = [v for v in units
              if game.on_map(v["col"], v["row"]) and v["id"] != u["id"]]
        dests = game.legal_destinations_t(u, ma, rb)
        snapshot["legal"][u["id"]] = {
            "name": u["name"], "ma": ma,
            "dests": {f"{c:02d}{r:02d}": round(cost, 3)
                      for (c, r), cost in sorted(dests.items())},
        }

    with open(out_path, "w") as f:
        json.dump(snapshot, f, indent=1, sort_keys=True)
    n_moves = sum(len(v["dests"]) for v in snapshot["legal"].values())
    print(f"baseline: {len(units)} counters, {len(onmap)} on-map, "
          f"{n_moves} legal destinations total -> {out_path}")


if __name__ == "__main__":
    args = sys.argv[1:]
    game_dir = gamespec.default_game_dir()
    if args and args[0] == "--game":
        game_dir = args[1]; args = args[2:]
    main(game_dir, args[0] if args else "baseline.json")
