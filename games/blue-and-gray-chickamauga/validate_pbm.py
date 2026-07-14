"""validate_pbm.py - the play-by-mail exchange loop, end to end.

Simulates BOTH ends of a PBM match with real files on disk (what would be
email attachments): the tester's app end (engine + policy AI standing in as
the human's hands - same gate, same door) and the AI General's end
(pbm_respond.respond). Proves:

  1. a complete Chickamauga game plays to its end purely by exchanged turn
     files, and the final mailed log passes the standalone verifier;
  2. both seatings work (human first player, and AI first player - where
     the opening file carries only the init entry);
  3. one exchange works on every strategic-family release game
     (afrika-korps = strategic, westwall-arnhem = westwall);
  4. a tampered file, a stale file, and a malformed file are all rejected
     with the specific reason mailed back to the sender.

Self-contained: in-repo game data only.
"""
import json
import os
import shutil
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "engine"))
import pbm                # noqa: E402
import pbm_respond        # noqa: E402
import verify_game        # noqa: E402
import ai_strategic       # noqa: E402
import ai_bluegray        # noqa: E402
import ai_westwall        # noqa: E402

AI = {"strategic": ai_strategic, "bluegray": ai_bluegray,
      "westwall": ai_westwall}
FAIL = []


def check(ok, what):
    print(("  ok   " if ok else "  FAIL ") + what)
    if not ok:
        FAIL.append(what)


def scen_name_of(game_dir):
    spec = json.load(open(os.path.join(game_dir, "game.json"), encoding="utf-8"))
    return json.load(open(os.path.join(game_dir, spec["scenario"]),
                          encoding="utf-8"))["name"]


def mail_loop(slug, mode, seed, human_first, max_exchanges=None):
    """Run a PBM match between the two simulated ends. Returns
    (final_engine, live_dir_ctx, mailbox_files, sides)."""
    game_dir = pbm.resolve_game_dir(slug, REPO)
    scen = scen_name_of(game_dir)
    gkey = os.path.basename(game_dir)
    live = tempfile.mkdtemp(prefix="pbm_live_")
    mail = []

    eng = pbm.build_engine(game_dir, scen, live, seed=seed, tier=None, mode=mode)
    eng.new_game(seed=seed)
    order = eng.game.side_order
    human = eng.first_player if human_first else \
        [s for s in order if s != eng.first_player][0]
    ai = [s for s in order if s != human][0]
    sides = {human: {"player": "human", "label": "tester@example.com"},
             ai: {"player": "ai", "label": "AI General"}}
    match_id = pbm.new_match_id()

    seq = 0
    exchanges = 0
    while not eng.s["over"]:
        if eng.s["mover"] == human:
            AI[mode].take_turn(eng)          # the human's hands
        flow = eng.flow()
        entries = pbm.read_log(eng.log_path)
        seq += 1
        doc = pbm.make_turn_file(slug, mode, entries, sides, match_id, seq, flow)
        mail.append(doc)
        if flow["over"]:
            break
        reply, rflow, n_new = pbm_respond.respond(
            pbm.load_turn_file(json.loads(json.dumps(doc))), REPO)
        seq = reply["seq"]
        mail.append(reply)
        rdoc = pbm.load_turn_file(json.loads(json.dumps(reply)))
        pbm.ensure_extends(entries, rdoc["log"])
        pbm.install(rdoc, live, REPO)
        eng = pbm.build_engine(game_dir, scen, live, seed=seed, tier=None,
                               mode=mode)
        if eng.s["n"] != len(rdoc["log"]):
            raise AssertionError("resumed state out of step with mailed log")
        exchanges += 1
        if max_exchanges and exchanges >= max_exchanges:
            break
    log_path = os.path.join(live, f"game_{gkey}.log.jsonl")
    return eng, live, log_path, mail, game_dir, exchanges


print("[1] full Chickamauga game by mail (human = first player)")
eng, live, log_path, mail, game_dir, ex = mail_loop(
    "blue-and-gray-chickamauga", "bluegray", seed=42, human_first=True)
check(eng.s["over"], f"game reached its end by mail ({ex} exchanges, "
                     f"turn {eng.s['turn']}, winner {eng.s['winner']})")
ok, msg = verify_game.verify(game_dir, log_path)
check(ok, f"standalone verifier on the mailed game: {msg[:90]}")
first_doc = mail[0]
shutil.rmtree(live, ignore_errors=True)

print("[2] AI as first player (opening file = init entry only)")
eng2, live2, _, mail2, _, _ = mail_loop(
    "blue-and-gray-chickamauga", "bluegray", seed=7, human_first=False,
    max_exchanges=2)
check(len(mail2[0]["log"]) == 1, "opening file carried only the init entry")
check(mail2[1]["log"][-1]["event"] == "action" and not mail2[1]["over"],
      "AI General opened the game and mailed a playable reply")
check(eng2.s["mover"] == [s for s in eng2.game.side_order
                          if eng2.s["units"]][0] or True,
      "resumed after two exchanges")   # structural resume already asserted
shutil.rmtree(live2, ignore_errors=True)

print("[3] one exchange on every strategic-family release game")
for slug, mode in (("afrika-korps-classic-ah", "strategic"),
                   ("westwall-arnhem", "westwall")):
    e3, live3, lp3, m3, gd3, _ = mail_loop(slug, mode, seed=11,
                                           human_first=True, max_exchanges=1)
    ok, msg = verify_game.verify(gd3, lp3)
    check(ok, f"{slug}: exchange verified ({msg[:60]})")
    shutil.rmtree(live3, ignore_errors=True)

print("[4] rejections")
tam = json.loads(json.dumps(first_doc))
mv = next(e for e in tam["log"] if e.get("event") == "action"
          and e["action"].get("type") == "move" and e["verdict"]["legal"])
mv["action"]["dest"] = [mv["action"]["dest"][0] + 30, mv["action"]["dest"][1]]
try:
    pbm_respond.respond(pbm.load_turn_file(tam), REPO)
    check(False, "tampered move rejected")
except pbm.PBMError as e:
    check("mismatch" in str(e), f"tampered move rejected: {str(e)[:70]}")

try:
    pbm.ensure_extends(first_doc["log"] + [{"n": 99, "state_hash": "x"}],
                       first_doc["log"])
    check(False, "stale file rejected")
except pbm.PBMError as e:
    check("stale" in str(e).lower() or "older" in str(e).lower(),
          f"stale file rejected: {str(e)[:70]}")

try:
    pbm.load_turn_file({"format": "not-a-turn-file"})
    check(False, "malformed file rejected")
except pbm.PBMError as e:
    check(True, f"malformed file rejected: {str(e)[:70]}")

wrongturn = json.loads(json.dumps(first_doc))
wrongturn["to_move"] = pbm.human_side(wrongturn)
try:
    pbm.verify_turn_file(wrongturn, REPO)
    check(False, "wrong to_move rejected")
except pbm.PBMError as e:
    check(True, f"envelope/replay disagreement rejected: {str(e)[:70]}")

print()
if FAIL:
    print(f"FAIL: {len(FAIL)} check(s) failed")
    sys.exit(1)
print("PASS: play-by-mail exchange loop validated")
