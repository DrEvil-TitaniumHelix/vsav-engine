"""validate_undo.py - the undo feature, end to end, EVERY user decision type.

Undo is engine-level (engine/undo.py: truncate the log + verified replay)
but its meaning - "one USER decision" - lives at the submission boundary in
ui/server.py, where accepted user gestures are marked. So this validator
drives the REAL server layer (the api_* functions every click goes through,
and the same module the Pyodide browser demo bundles), one game per family:

  tobruk                     tactical    afrika-korps-classic-ah  strategic
  blue-and-gray-chickamauga  bluegray    westwall-arnhem          westwall
  austerlitz-gmt             napoleonic

Per game:
  A. HOTSEAT SWEEP - generate a full verified AI self-play game, then replay
     EVERY action through the user endpoints (both seats human: moves via
     the drag endpoint, End buttons via the End endpoint when they match,
     everything else via the panel-action endpoint). Every accepted action
     of a NEW type is undo-roundtripped on the spot:
         submit -> undo -> state hash == pre-hash -> resubmit ->
         state hash == post-hash  (same seeded dice: reroll-proof)
     already-covered types re-roundtrip every MOD-th action. Rejected
     proposals are asserted to leave no undo mark. After every submission
     the live state hash must equal the reference log's - the endpoint
     path is proven equivalent to the recorded game. The sweep ends with a
     full consecutive undo drain (window law: exactly min(5, marks) undos,
     then "nothing to undo"), a raw redo of the drained tail back to the
     exact end state, and a standalone verify_game pass on the live log.
  B. SOLO-VS-AI SWEEP - same reference game, one seat via user endpoints
     (marked), the other seat raw gate.submit (unmarked - exactly how the
     server AI paths submit). Deep-undo checkpoints unwind up to 5 marks
     in a row THROUGH the AI's replies, asserting each landing hash, then
     redo the cut tail raw and assert byte-perfect recovery. Also: undo
     while an AI TurnStepper is mid-turn (stepper must be dropped).
  C. LAWS - refused with no gate (tier 0), refused while a PBM or SALVO
     sidecar is attached, refused on an empty window, undo out of game
     over, state survives a gate rebuild (server restart), the .vsav
     mirror matches the gate after undo, the archive holds every cut line.
  D. COVERAGE - the roundtripped action types must include the REQUIRED
     set below (curated from each engine's dispatch vocabulary). Types the
     scenario genuinely cannot produce are listed in RARE with the reason
     and reported, never silently ignored.

Self-contained: in-repo game data only.
"""
import json
import os
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "engine"))
sys.path.insert(0, os.path.join(REPO, "ui"))
import server              # noqa: E402  (ui/server.py - the click layer)
import gamespec            # noqa: E402
import gamestate as gs_mod  # noqa: E402
import strategic as strat_mod  # noqa: E402
import bluegray as bg_mod   # noqa: E402
import westwall as ww_mod   # noqa: E402
import napoleonic as nap_mod  # noqa: E402
import ai as tac_ai         # noqa: E402
import ai_strategic         # noqa: E402
import ai_bluegray          # noqa: E402
import ai_westwall          # noqa: E402
import ai_napoleonic        # noqa: E402
import pbm as pbm_mod       # noqa: E402
import salvo as salvo_mod   # noqa: E402
import undo as undo_mod     # noqa: E402
import verify_game          # noqa: E402

AI = {"strategic": ai_strategic, "bluegray": ai_bluegray,
      "westwall": ai_westwall}

# (slug, mode, seed, tuning). Every undo replays the log prefix, so sweep
# cost is O(n²/mod) — the two long campaigns get a higher modulus and a
# capped solo sweep to keep the suite inside run_all's per-validator budget.
# NEW action types ALWAYS roundtrip regardless of mod: coverage never
# shrinks, only the density of repeat-checks on already-proven types.
GAMES = [
    ("tobruk", "tactical", 5, {}),
    ("afrika-korps-classic-ah", "strategic", 11, {"mod": 40, "solo_cap": 200}),
    ("blue-and-gray-chickamauga", "bluegray", 42, {}),
    ("westwall-arnhem", "westwall", 7, {"mod": 30, "solo_cap": 300}),
    ("austerlitz-gmt", "napoleonic", 3, {}),
]

# Action types that MUST be undo-roundtripped for the game to pass (the
# common vocabulary of each engine's dispatch that AI self-play reaches).
REQUIRED = {
    "tobruk": {"move", "fire", "end_movement", "pass_fire", "pivot"},
    "afrika-korps-classic-ah": {"move", "end_movement", "end_phase",
                                "battle", "roll_supply"},
    "blue-and-gray-chickamauga": {"move", "end_movement", "end_phase",
                                  "battle", "retreat", "advance",
                                  "reinforce"},
    "westwall-arnhem": {"move", "end_movement", "end_phase", "battle",
                        "retreat", "advance", "reinforce",
                        "demolition", "fpf"},
    # austerlitz plays the command flow [3.0]: turns end via end_rally
    # (end_turn = non-command flow only). Set = seed-3 observed coverage,
    # including every interleaved defender decision (return fire, square,
    # reactions) — the hardest undo cases.
    "austerlitz-gmt": {"move", "set_pool", "fire", "charge",
                       "activation_choice", "choose_initiative_lim",
                       "end_activation", "end_rally", "melee",
                       "non_lim", "rally", "return_fire", "square_choice",
                       "change_formation", "reaction_fire", "reaction_move",
                       "melee_return"},
}
# Engine vocabulary the reference scenario cannot be forced to produce on
# demand (reported when unseen; any of them that DOES occur is roundtripped
# by the new-type rule, so occurrence == coverage).
RARE = {
    "tobruk": {"reverse"},
    "afrika-korps-classic-ah": {"breakdown", "capture_supply", "debark",
                                "declare_av", "destroy_supply", "embark",
                                "forced_elim", "land_reinforcement",
                                "land_supply", "place_rommel", "replace",
                                "retreat", "advance", "exchange_loss",
                                "rommel_extend", "substitute", "reinforce",
                                "movement"},
    "blue-and-gray-chickamauga": {"exchange_loss", "exit", "train_retreat"},
    "westwall-arnhem": {"exit"},
    "austerlitz-gmt": {"about_face", "bd_activate", "bd_decline", "cossack",
                       "declare_strategic", "decline_reaction",
                       "decline_return", "end_turn", "melee_no_return",
                       "melee_withdraw", "pass_non_lim", "reaction_charge",
                       "reaction_face", "reaction_limber",
                       "reaction_reverse", "reverse", "slide"},
}

FAIL = []


def mod_for(n_entries):
    """Re-roundtrip every MOD-th already-covered action. Each undo replays
    the log prefix (O(n)), so a fixed modulus makes long games O(n²/MOD) —
    scale it to bound the sweep at roughly 60 modulo-roundtrips per game.
    NEW types always roundtrip regardless: coverage never shrinks."""
    return max(9, n_entries // 60)


def check(ok, what):
    print(("  ok   " if ok else "  FAIL ") + what)
    if not ok:
        FAIL.append(what)


def die(what):
    """An invariant broke mid-sweep - record and abort this game loudly."""
    check(False, what)
    raise RuntimeError(what)


# ------------------------------------------------- reference self-play game
def build_ref_gate(slug, mode, workdir, seed):
    """A gate constructed EXACTLY like server.build_gate builds the live one
    (tier=None = earned), so the reference game matches the live game."""
    game_dir = os.path.join(REPO, "games", slug)
    game = gamespec.Game(game_dir)
    scen = game._path(game.spec["scenario"])
    cls = {"strategic": strat_mod.StrategicGame, "bluegray": bg_mod.BlueGrayGame,
           "westwall": ww_mod.WestwallGame,
           "napoleonic": nap_mod.NapoleonicGame}.get(mode)
    g = cls(game, scen, workdir, tier=None) if cls \
        else gs_mod.TacticalGame(game, scen, workdir)
    g.new_game(seed)
    return g


def ref_over(mode, g):
    return g.flow()["over"] if mode == "napoleonic" else g.s["over"]


def selfplay_log(slug, mode, seed, cap=6000):
    """Generate a complete AI self-play game; return its parsed log lines."""
    tmp = tempfile.mkdtemp(prefix="undo_ref_")
    g = build_ref_gate(slug, mode, tmp, seed)
    while not ref_over(mode, g) and g.s["n"] < cap:
        if mode == "tactical":
            if g.s["segment"] == "movement":
                tac_ai.take_movement_segment(g, g.s["mover"])
            else:
                tac_ai.take_one_fire(g, g.s["initiative"])
        elif mode == "napoleonic":
            ai_napoleonic.take_turn(g, g.decider())
        else:
            AI[mode].take_turn(g)
    lines = [json.loads(l) for l in open(g.log_path, encoding="utf-8")
             if l.strip()]
    return lines, ref_over(mode, g)


# ----------------------------------------------------- the endpoint driver
def live_gate():
    return server.SG or server.TG


def expected_end_type(mode):
    SG = server.SG
    if mode == "napoleonic":
        if SG.s["phase"] == "rally":
            return "end_rally"
        if getattr(SG, "_cmd", False):
            return "end_activation"
        return "end_turn"
    if mode in ("bluegray", "westwall") and SG.s["phase"] == "movement":
        return "end_movement"
    return "end_phase"


def submit_entry(mode, e):
    """Submit a logged action through the endpoint a human's click uses."""
    a = e["action"]
    t = a.get("type")
    if mode == "tactical":
        return server.api_action({"side": e["side"], "action": a})
    if t == "move" and set(a) == {"type", "unit", "dest"} \
            and a["unit"] in server.SG.s["units"]:
        # exactly what a drag produces; moves with extra fields (napoleonic
        # facing = the rotate control) travel via the panel-action endpoint,
        # same as the real client's sgAction()
        d = server.GAME_OBJ.grid.digits
        col, row = a["dest"]
        return server.api_move({"id": a["unit"],
                                "dest": f"{col:0{d}d}{row:0{d}d}",
                                "whole": False})
    if t == expected_end_type(mode) and e["side"] == server.SG.s["mover"]:
        return server.api_end_phase()      # the top-bar End button itself
    return server.api_sg_action({"action": a, "side": e["side"]})


def marks():
    return undo_mod.load_marks(server.LIVE, server.GAME_SLUG)


# The .vsav mirror parse+rewrite on every endpoint submit is interactive-
# speed code; across thousands of harness submits it dominates the runtime
# without adding assertions. The bulk sweep stubs it out; every undo press
# runs the REAL mirror path (see undo_here) — which then must repair the
# accumulated staleness in one diff-sync, a stronger claim than keeping the
# board warm would be.
_real_sync, _real_mirror_move = server.sync_mirror, server.mirror_move


def stub_mirror(on):
    server.sync_mirror = (lambda: None) if on else _real_sync
    server.mirror_move = (lambda *a: None) if on else _real_mirror_move


# The board mirror is built from the game's setup .vsav — a module-derived
# asset that is deliberately NOT in the public repo (BYO principle), so CI
# has no board at all. The gate/log/undo claims never touch the board;
# where the asset is absent the board layer no-ops and the per-undo mirror
# assertion is SKIPPED with an honest note (it still runs on any checkout
# with local assets — the release machine).
class _NoBoard:
    def units(self):
        return []

    def __getattr__(self, name):
        return lambda *a, **k: None


_real_fresh_board = server.fresh_board


def _fresh_board_safe():
    if board_available():
        return _real_fresh_board()
    return _NoBoard()


def board_available():
    return bool(server.GAME_OBJ) and os.path.exists(server.GAME_OBJ.setup_save)


server.fresh_board = _fresh_board_safe


def undo_here(expect_hash, expect_n):
    """One undo press; assert it lands exactly on the recorded pre-state and
    leaves the .vsav mirror in step with the gate (undo diff-syncs the whole
    board, repairing even staleness left by earlier raw submits)."""
    stub_mirror(False)                 # the undo press runs the real mirror
    r = server.api_undo()
    stub_mirror(True)
    if not r.get("ok"):
        die(f"undo refused unexpectedly: {r.get('error')}")
    g = live_gate()
    if g.state_hash() != expect_hash or g.s["n"] != expect_n:
        die(f"undo landed wrong: n={g.s['n']} (want {expect_n})")
    raw = [l for l in open(g.log_path, encoding="utf-8") if l.strip()]
    if len(raw) != expect_n:
        die(f"log not truncated to {expect_n} lines (has {len(raw)})")
    if board_available():
        b = server.fresh_board()
        pos = {u["id"]: (u["col"], u["row"]) for u in b.units()}
        bad = [u["pid"] for u in g.s["units"].values()
               if g.on_map(u) and u["pid"] in pos
               and pos[u["pid"]] != (u["col"], u["row"])]
        if bad:
            die(f"mirror out of step after undo: {bad[:4]}")


def sweep(slug, mode, seed, lines, solo_side=None, tune=None):
    """Replay a reference game through the endpoints. solo_side=None:
    hotseat (everything via endpoints, roundtrip per policy). solo_side=S:
    only S's entries go via endpoints; the rest submit raw like the server
    AI does; deep-undo checkpoints run at 1/3, 2/3 and the end.
    Returns the set of action types roundtripped."""
    server.api_reset({})
    g = live_gate()
    g.new_game(seed)
    server.AI_STEP = None
    covered, shadow = set(), []       # shadow: [(n_before, pre_hash, type)]
    entries = [e for e in lines[1:] if e.get("event") == "action"]
    tune = tune or {}
    if solo_side is not None and tune.get("solo_cap"):
        entries = entries[:tune["solo_cap"]]
    mod = tune.get("mod") or mod_for(len(entries))
    # Deep-undo checkpoints (solo mode) must actually cut THROUGH the AI's
    # replies, so anchor them on solo entries that immediately follow an
    # enemy stretch — a blind len/3 split can land mid-solo-turn where the
    # 5-mark window holds only the player's own consecutive actions.
    checkpoints = set()
    if solo_side is not None:
        cands = [i for i in range(1, len(entries))
                 if entries[i]["side"] == solo_side
                 and entries[i - 1]["side"] != solo_side]
        checkpoints = ({cands[0], cands[len(cands) // 2], cands[-1]}
                       if cands else {len(entries) - 1})
    ai_unwound = 0
    n_round = 0

    for i, e in enumerate(entries):
        g = live_gate()
        t = e["action"].get("type")
        pre_hash, pre_n = g.state_hash(), g.s["n"]
        pre_marks = len(marks())
        is_user = solo_side is None or e["side"] == solo_side

        if is_user:
            submit_entry(mode, e)
        else:
            g.submit(e["side"], e["action"])
        if g.state_hash() != e["state_hash"]:
            die(f"{slug} entry {e['n']}: endpoint replay diverged from the "
                f"reference log ({t})")

        accepted = e["verdict"]["legal"]
        if is_user and accepted:
            m = marks()
            if not m or m[-1]["n"] != pre_n:
                die(f"{slug} entry {e['n']}: accepted user action left no "
                    f"undo mark ({t})")
            if len(m) > undo_mod.MAX_DEPTH:
                die(f"{slug}: undo window exceeded {undo_mod.MAX_DEPTH}")
            shadow.append((pre_n, pre_hash, t))
            # -------- the per-decision roundtrip: undo, verify, resubmit
            if t not in covered or i % mod == 0:
                post_hash, post_n = g.state_hash(), g.s["n"]
                undo_here(pre_hash, pre_n)
                submit_entry(mode, e)
                if g.state_hash() != post_hash or g.s["n"] != post_n:
                    die(f"{slug} entry {e['n']}: redo after undo did not "
                        f"reproduce the state ({t}) - dice or verdict drifted")
                covered.add(t)
                n_round += 1
        elif not accepted and is_user:
            if len(marks()) != pre_marks:
                die(f"{slug} entry {e['n']}: REJECTED proposal left an "
                    f"undo mark ({t})")

        # -------- deep-undo checkpoint (solo mode): through the AI's replies
        if solo_side is not None and i in checkpoints and shadow:
            avail = min(len(marks()), undo_mod.MAX_DEPTH)
            if avail:
                g = live_gate()
                end_hash, end_n = g.state_hash(), g.s["n"]
                landings = shadow[-avail:][::-1]
                cut_from = landings[-1][0]
                raw_lines = [json.loads(l) for l in
                             open(g.log_path, encoding="utf-8") if l.strip()]
                tail = raw_lines[cut_from:]
                ai_unwound += sum(1 for x in tail
                                  if x.get("event") == "action"
                                  and x["side"] != solo_side)
                for (mn, mh, _t) in landings:
                    undo_here(mh, mn)
                shadow = shadow[:-avail]
                for x in tail:                       # raw redo, like the AI
                    if x.get("event") == "action":
                        live_gate().submit(x["side"], x["action"])
                g = live_gate()
                if g.state_hash() != end_hash or g.s["n"] != end_n:
                    die(f"{slug}: raw redo after {avail} deep undos did not "
                        f"recover the state")
    print(f"       {slug}{' solo' if solo_side else ' hotseat'}: "
          f"{len(entries)} entries, {n_round} roundtrips"
          + (f", {ai_unwound} AI replies unwound" if solo_side else ""))
    if solo_side is not None:
        check(ai_unwound > 0,
              f"{slug}: deep undo unwound AI replies ({ai_unwound})")
    return covered


def drain_and_recover(slug):
    """Window law at game end: exactly min(5, marks) consecutive undos work,
    the next says 'nothing to undo', and a raw redo restores the end state
    (this also exercises undo OUT of game over)."""
    g = live_gate()
    end_hash, end_n = g.state_hash(), g.s["n"]
    m = marks()
    avail = len(m)
    if not avail:
        return
    cut_from = m[0]["n"]
    raw_lines = [json.loads(l) for l in open(g.log_path, encoding="utf-8")
                 if l.strip()]
    tail = raw_lines[cut_from:]
    n_ok = 0
    for _ in range(avail):
        if server.api_undo().get("ok"):
            n_ok += 1
    r = server.api_undo()
    check(n_ok == avail and r.get("error") == "nothing to undo",
          f"{slug}: window drained after exactly {n_ok} undos, then refused")
    for x in tail:
        if x.get("event") == "action":
            live_gate().submit(x["side"], x["action"])
    g = live_gate()
    check(g.state_hash() == end_hash and g.s["n"] == end_n,
          f"{slug}: end state recovered after full drain + redo")


def laws(slug, mode):
    """The refusal / persistence / mirror laws, on the live post-sweep game."""
    g = live_gate()
    # PBM and SALVO block undo (accepted prefixes stand)
    pbm_mod.save_sidecar(server.LIVE, server.GAME_SLUG,
                         {"match_id": "t", "human_side": "x", "ai_side": "y",
                          "game": slug, "mode": mode, "seq": 0,
                          "labels": {}, "last_export_n": None})
    r = server.api_undo()
    ok_pbm = "match" in (r.get("error") or "")
    st = server.undo_status()
    ok_pbm = ok_pbm and st and st.get("blocked")
    pbm_mod.clear_sidecar(server.LIVE, server.GAME_SLUG)
    check(ok_pbm, f"{slug}: undo refused + status blocked in a PBM match")
    salvo_mod.save_sidecar(server.LIVE, server.GAME_SLUG,
                           {"match_id": "t", "llm_side": "x", "game": slug,
                            "mode": mode, "n": 1, "last_n": 0,
                            "rejected": None})
    r = server.api_undo()
    salvo_mod.clear_sidecar(server.LIVE, server.GAME_SLUG)
    check("match" in (r.get("error") or ""),
          f"{slug}: undo refused in a SALVO match")
    # archive: every cut line is preserved
    arch = undo_mod.archive_path(server.LIVE, server.GAME_SLUG)
    check(os.path.exists(arch) and sum(1 for _ in open(arch)) > 0,
          f"{slug}: archive file holds the cut entries")
    # persistence: a rebuilt gate (server restart) resumes the undone state
    h = g.state_hash()
    server.build_gate()
    check(live_gate().state_hash() == h,
          f"{slug}: state survives a gate rebuild after undo")
    print("       (mirror consistency asserted after every undo press)"
          if board_available() else
          "       note: board setup .vsav absent (BYO asset, expected in "
          "CI) - mirror assertions skipped, gate/log/undo claims unaffected")
    # tier 0 = no gate = no undo
    if 0 in server.TIER_CHOICES:
        server.api_reset({"tier": 0})
        r = server.api_undo()
        check("gate" in (r.get("error") or ""),
              f"{slug}: undo refused at tier 0 (no gate)")
        server.api_reset({"tier": server.TIER_EARNED})
    # fresh game = empty window
    live_gate().new_game(1)
    r = server.api_undo()
    check(r.get("error") == "nothing to undo",
          f"{slug}: fresh game has nothing to undo")


def stepper_test(slug, mode, seed, lines):
    """Undo while an AI TurnStepper is mid-turn: the stepper must be dropped
    and the state land on the last user mark."""
    if mode == "napoleonic" or mode == "tactical":
        return                         # stepper micro-test uses the SG path
    server.api_reset({})
    g = live_gate()
    g.new_game(seed)
    fed, last = 0, None
    for e in lines[1:]:
        if e.get("event") != "action" or not e["verdict"]["legal"]:
            continue
        if e["action"].get("type") != "move" or e["side"] != g.s["mover"]:
            break
        pre = (g.s["n"], g.state_hash())
        submit_entry(mode, e)
        last = pre
        fed += 1
        if fed >= 2:
            break
    if fed < 2:
        return
    side = g.s["mover"]
    server.api_ai_step({"side": side})            # fresh stepper: peek
    r = server.api_ai_step({"side": side})        # executes ONE ai action
    if not r.get("step"):
        return
    check(server.AI_STEP is not None, f"{slug}: stepper is mid-turn")
    server.api_undo()
    check(server.AI_STEP is None and (g.s["n"], g.state_hash()) == last,
          f"{slug}: undo mid-stepping dropped the stepper and landed on "
          f"the last user mark")


# ------------------------------------------------------------------- main
def main():
    smoke = "--smoke" in sys.argv or bool(os.environ.get("VASSAL_AI_SMOKE"))
    only = None
    if "--game" in sys.argv:
        only = sys.argv[sys.argv.index("--game") + 1]
    tmp = tempfile.mkdtemp(prefix="undo_live_")
    server.LIVE = tmp
    games = GAMES
    if only:
        games = [g for g in GAMES if g[0] == only]
    elif smoke:
        games = [g for g in GAMES
                 if g[0] in ("tobruk", "blue-and-gray-chickamauga")]

    import time
    stub_mirror(True)
    for slug, mode, seed, tune in games:
        t0 = time.time()
        print(f"[{slug}] mode={mode} seed={seed}", flush=True)
        lines, finished = selfplay_log(slug, mode, seed)
        print(f"       reference self-play: {len(lines)} log lines, "
              f"game {'finished' if finished else 'CAPPED'} "
              f"({time.time() - t0:.0f}s)", flush=True)
        server.load_game(os.path.join(REPO, "games", slug))
        if server.TIER != server.TIER_EARNED:
            server.api_reset({"tier": server.TIER_EARNED})

        try:
            covered = sweep(slug, mode, seed, lines,          # A: hotseat
                            tune=tune)
            drain_and_recover(slug)
            ok, msg = verify_game.verify(os.path.join(REPO, "games", slug),
                                         live_gate().log_path)
            check(ok, f"{slug}: standalone verifier on the swept live log "
                      f"({msg[:60]})")

            first = lines[1]["side"] if len(lines) > 1 else None
            covered |= sweep(slug, mode, seed, lines,          # B: solo
                             solo_side=first, tune=tune)
            laws(slug, mode)                                   # C: laws
            stepper_test(slug, mode, seed, lines)
        except RuntimeError:
            continue                    # invariant died; already recorded

        missing = REQUIRED[slug] - covered                     # D: coverage
        check(not missing, f"{slug}: required decision types all "
                           f"roundtripped ({sorted(covered)})"
              if not missing else
              f"{slug}: REQUIRED types never roundtripped: {sorted(missing)}")
        unseen_rare = RARE[slug] - covered
        extra = covered - REQUIRED[slug] - RARE[slug]
        if extra:
            print(f"       note: also roundtripped {sorted(extra)}")
        if unseen_rare:
            print(f"       note: rare types not produced by this scenario "
                  f"(uncovered, reported honestly): {sorted(unseen_rare)}")
        print(f"       [{slug} done in {time.time() - t0:.0f}s]", flush=True)

    print()
    if FAIL:
        print(f"FAIL: {len(FAIL)} check(s) failed")
        return 1
    print("PASS: undo validated end to end - every produced decision type "
          "roundtrips through the real click layer")
    return 0


if __name__ == "__main__":
    sys.exit(main())
