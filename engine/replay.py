"""replay.py - ONE implementation of "rebuild a game from its log".

The JSONL game log is self-contained (init entry = scenario + seed + starting
positions; every action entry = proposal + verdict + result + post-state
hash), so any prefix of a verified log deterministically reconstructs the
exact game state it describes. Two engine features depend on that and MUST
share this code so they can never drift (the fix-the-class rule):

  * verify_game.py - the standalone auditor replays the WHOLE log;
  * undo.py        - undo replays a PREFIX of the log (state = log replay,
                     so undo = truncate + replay).

replay_lines() re-submits every logged proposal through a FRESH gate and
re-checks every verdict, every die-dependent result and every state hash.
Any divergence raises ReplayMismatch - a caller never receives a state that
the log does not prove.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gamespec            # noqa: E402
import gamestate as gs_mod  # noqa: E402
import strategic as strat_mod  # noqa: E402
import bluegray as bg_mod   # noqa: E402
import westwall as ww_mod   # noqa: E402
import napoleonic as nap_mod  # noqa: E402

STRATEGIC_MODES = ("strategic", "bluegray", "westwall", "napoleonic")


class ReplayMismatch(Exception):
    """The log does not replay: a verdict, result or state hash diverged."""


def find_scenario(game_dir, init):
    """The scenario file whose name matches the log's init entry."""
    for cand in sorted(os.listdir(game_dir)):
        if cand.startswith("scenario") and cand.endswith(".json"):
            import json
            s = json.load(open(os.path.join(game_dir, cand), encoding="utf-8"))
            if s.get("name") == init["scenario"]:
                return os.path.join(game_dir, cand)
    return None


def make_gate(game, scen_path, workdir, init):
    """A fresh gate of the family the init entry names, seeded from the log."""
    mode = init.get("mode")
    if mode == "napoleonic":
        return nap_mod.NapoleonicGame(game, scen_path, workdir,
                                      seed=init["seed"],
                                      tier=init.get("tier"),
                                      command=init.get("schema", 2) >= 3)
    if mode == "westwall":
        return ww_mod.WestwallGame(game, scen_path, workdir,
                                   seed=init["seed"], tier=init.get("tier"))
    if mode == "bluegray":
        return bg_mod.BlueGrayGame(game, scen_path, workdir,
                                   seed=init["seed"], tier=init.get("tier"))
    if mode == "strategic":
        return strat_mod.StrategicGame(game, scen_path, workdir,
                                       seed=init["seed"],
                                       tier=init.get("tier"))
    return gs_mod.TacticalGame(game, scen_path, workdir, seed=init["seed"])


def check_init(tg, init):
    """Confirm the fresh gate's starting positions match the log's record."""
    strategic = init.get("mode") in STRATEGIC_MODES
    for lu in init["units"]:
        u = tg.s["units"][lu["pid"]]
        if [u["col"], u["row"]] != lu["hex"] or u["side"] != lu["side"] \
           or (not strategic and u["facing"] != lu["facing"]):
            raise ReplayMismatch(f"init mismatch for {lu['pid']}")


def replay_lines(game, scen_path, lines, workdir, on_entry=None):
    """Replay parsed log entries (init first) through a fresh gate built in
    `workdir`. Re-checks verdict + result + state hash on every action entry;
    raises ReplayMismatch on any divergence. Returns the gate, whose state
    is then PROVEN equal to the state after the last replayed entry.

    on_entry(entry, replay_result) is called per verified action entry
    (verify_game uses it for counting and verbose output)."""
    import json
    if not lines or lines[0].get("event") != "init":
        raise ReplayMismatch("log does not start with an init entry")
    init = lines[0]
    tg = make_gate(game, scen_path, workdir, init)
    check_init(tg, init)
    for e in lines[1:]:
        if e.get("event") != "action":
            continue
        r = tg.submit(e["side"], e["action"])
        v_logged, v_replay = e["verdict"], r["verdict"]
        if v_logged["legal"] != v_replay["legal"]:
            raise ReplayMismatch(
                f"entry {e['n']}: verdict mismatch — log says "
                f"{v_logged['legal']}, replay says {v_replay['legal']} "
                f"({v_replay['reasons']})")
        logged_res, replay_res = e.get("result"), r.get("result")
        if (logged_res or {}) != (replay_res or {}):
            raise ReplayMismatch(
                f"entry {e['n']}: resolution mismatch (dice/damage differ)\n"
                f"  log:    {json.dumps(logged_res)[:200]}\n"
                f"  replay: {json.dumps(replay_res)[:200]}")
        if e["state_hash"] != tg.state_hash():
            raise ReplayMismatch(f"entry {e['n']}: state hash mismatch")
        if on_entry:
            on_entry(e, r)
    return tg


def replay_prefix(game_dir, lines):
    """Rebuild the state a log PREFIX proves, in a throwaway workdir.
    Returns the replayed gate (caller reads .s and discards). The workdir's
    regenerated log/state files never touch the caller's live files."""
    game = game_dir if isinstance(game_dir, gamespec.Game) \
        else gamespec.Game(game_dir)
    scen_path = find_scenario(game.dir, lines[0])
    if not scen_path:
        raise ReplayMismatch(
            f"scenario '{lines[0].get('scenario')}' not found in {game.dir}")
    with tempfile.TemporaryDirectory() as tmp:
        return replay_lines(game, scen_path, lines, tmp)
