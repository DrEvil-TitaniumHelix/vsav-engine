"""
verify_game.py - Standalone auditor for a played game.

The game log (live/game_<game>.log.jsonl) is self-contained: the init entry
records the scenario, seed and starting positions; every subsequent entry
records a PROPOSAL (legal or not), the gate's verdict, and the state hash
after processing. This script replays the whole game from the init entry
through a FRESH engine and confirms, independently of the play session:

  1. every verdict — each accepted action re-validates as legal, each
     rejected action re-validates as illegal for the same reasons;
  2. every die roll — the seeded RNG stream reproduces the logged dice;
  3. every state hash — the replayed state matches after every entry;
  4. no state change ever came from anywhere but a logged legal action.

The replay itself is engine/replay.py — the same code undo runs on, so the
auditor and the undo feature can never disagree about what a log proves.

Anyone can run it:  python engine/verify_game.py --game games/tobruk live/game_tobruk.log.jsonl
If the AI (or the human!) had ever made an illegal move that was applied,
or fudged a die, or teleported a unit, this replay CANNOT reproduce the log.
"""
import argparse
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gamespec            # noqa: E402
import replay as replay_mod  # noqa: E402


def verify(game_dir, log_path, verbose=False):
    lines = [json.loads(l) for l in open(log_path, encoding="utf-8") if l.strip()]
    if not lines or lines[0].get("event") != "init":
        return False, "log does not start with an init entry"
    init = lines[0]

    game = gamespec.Game(game_dir)
    scen_path = replay_mod.find_scenario(game_dir, init)
    if not scen_path:
        return False, f"scenario '{init['scenario']}' not found in {game_dir}"

    counts = {"ok": 0, "actions": 0, "rejected": 0}

    def on_entry(e, r):
        counts["actions"] += 1
        counts["ok"] += 1
        if not e["verdict"]["legal"]:
            counts["rejected"] += 1
        if verbose:
            tag = "LEGAL  " if e["verdict"]["legal"] else "ILLEGAL"
            print(f"  ok n={e['n']:>3} t{e['turn']} {(e.get('segment') or e.get('phase')):<8} {e['side']:<7} "
                  f"{e['action'].get('type'):<13} {tag} {'; '.join(e['verdict']['reasons'])[:70]}")

    try:
        with tempfile.TemporaryDirectory() as tmp:
            replay_mod.replay_lines(game, scen_path, lines, tmp,
                                    on_entry=on_entry)
    except replay_mod.ReplayMismatch as e:
        return False, str(e)

    return True, (f"{counts['ok']}/{counts['actions']} entries verified: every verdict, every die, "
                  f"every state hash reproduced ({counts['rejected']} illegal proposals were "
                  f"rejected and provably never touched the game state)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--game", default=os.path.join(gamespec.games_root(), "tobruk"))
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    ok, msg = verify(a.game, a.log, a.verbose)
    print(("VERIFIED: " if ok else "FAILED: ") + msg)
    sys.exit(0 if ok else 1)
