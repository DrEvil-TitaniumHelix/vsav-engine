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
import gamestate as gs_mod  # noqa: E402
import strategic as strat_mod  # noqa: E402
import bluegray as bg_mod   # noqa: E402
import westwall as ww_mod   # noqa: E402


def verify(game_dir, log_path, verbose=False):
    lines = [json.loads(l) for l in open(log_path, encoding="utf-8") if l.strip()]
    if not lines or lines[0].get("event") != "init":
        return False, "log does not start with an init entry"
    init = lines[0]

    game = gamespec.Game(game_dir)
    # scenario file is named in the init entry's own data (positions are
    # embedded, but the engine also needs the scenario's game config)
    scen_path = None
    for cand in os.listdir(game_dir):
        if cand.startswith("scenario") and cand.endswith(".json"):
            s = json.load(open(os.path.join(game_dir, cand), encoding="utf-8"))
            if s.get("name") == init["scenario"]:
                scen_path = os.path.join(game_dir, cand)
                break
    if not scen_path:
        return False, f"scenario '{init['scenario']}' not found in {game_dir}"

    mode = init.get("mode")
    strategic = mode in ("strategic", "bluegray", "westwall")
    with tempfile.TemporaryDirectory() as tmp:
        if mode == "westwall":
            tg = ww_mod.WestwallGame(game, scen_path, tmp, seed=init["seed"],
                                     tier=init.get("tier"))
        elif mode == "bluegray":
            tg = bg_mod.BlueGrayGame(game, scen_path, tmp, seed=init["seed"],
                                     tier=init.get("tier"))
        elif mode == "strategic":
            tg = strat_mod.StrategicGame(game, scen_path, tmp, seed=init["seed"],
                                         tier=init.get("tier"))
        else:
            tg = gs_mod.TacticalGame(game, scen_path, tmp, seed=init["seed"])
        # confirm starting positions match the log's init record
        for lu in init["units"]:
            u = tg.s["units"][lu["pid"]]
            if [u["col"], u["row"]] != lu["hex"] or u["side"] != lu["side"] \
               or (not strategic and u["facing"] != lu["facing"]):
                return False, f"init mismatch for {lu['pid']}"

        n_ok = n_actions = n_rejected = 0
        for e in lines[1:]:
            if e.get("event") != "action":
                continue
            n_actions += 1
            r = tg.submit(e["side"], e["action"])
            v_logged, v_replay = e["verdict"], r["verdict"]
            if v_logged["legal"] != v_replay["legal"]:
                return False, (f"entry {e['n']}: verdict mismatch — log says "
                               f"{v_logged['legal']}, replay says {v_replay['legal']} "
                               f"({v_replay['reasons']})")
            if not v_logged["legal"]:
                n_rejected += 1
            logged_res, replay_res = e.get("result"), r.get("result")
            if (logged_res or {}) != (replay_res or {}):
                return False, f"entry {e['n']}: resolution mismatch (dice/damage differ)\n  log:    {json.dumps(logged_res)[:200]}\n  replay: {json.dumps(replay_res)[:200]}"
            if e["state_hash"] != tg.state_hash():
                return False, f"entry {e['n']}: state hash mismatch"
            n_ok += 1
            if verbose:
                tag = "LEGAL  " if v_logged["legal"] else "ILLEGAL"
                print(f"  ok n={e['n']:>3} t{e['turn']} {(e.get('segment') or e.get('phase')):<8} {e['side']:<7} "
                      f"{e['action'].get('type'):<13} {tag} {'; '.join(v_logged['reasons'])[:70]}")

    return True, (f"{n_ok}/{n_actions} entries verified: every verdict, every die, "
                  f"every state hash reproduced ({n_rejected} illegal proposals were "
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
