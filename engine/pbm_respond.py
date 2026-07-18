"""
pbm_respond.py - The AI General's side of a play-by-mail exchange.

Feed it the turn file a tester mailed in; it verifies the ENTIRE game
(every verdict, die and state hash replayed through a fresh engine), plays
the AI's whole player turn through the same legality gate, and writes the
reply file to mail back. If the incoming file fails verification it writes
a rejection document instead, naming the exact failure, and exits 2 - the
tester is asked to redo their turn from their last good position.

  python engine\\pbm_respond.py incoming.json -o reply.json
  python engine\\pbm_respond.py incoming.json            (reply lands next to
                                                          the incoming file)

Exit codes: 0 reply written / game over ack, 2 rejected, 1 usage error.
"""
import argparse
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pbm                       # noqa: E402
import ai_strategic              # noqa: E402
import ai_bluegray               # noqa: E402
import ai_westwall               # noqa: E402
import champion as champ_mod     # noqa: E402
import plans as plans_mod        # noqa: E402

AI = {"strategic": ai_strategic, "bluegray": ai_bluegray,
      "westwall": ai_westwall}


def respond(doc, root=None):
    """Verified envelope in -> reply envelope out (the AI's turn played).
    Raises pbm.PBMError for anything that must bounce back to the sender."""
    game_dir = pbm.resolve_game_dir(doc["game"], root)
    received = doc["log"]
    with tempfile.TemporaryDirectory() as tmp:
        eng = pbm.replay(game_dir, received, tmp)
        flow = eng.flow()
        if bool(doc.get("over")) != bool(flow["over"]):
            raise pbm.PBMError("envelope 'over' flag disagrees with the "
                               "replayed game")
        if flow["over"]:
            # final position confirmed - mail back an acknowledgement copy
            return pbm.make_turn_file(
                doc["game"], doc["mode"], received, doc["sides"],
                doc["match_id"], int(doc["seq"]) + 1, flow,
                note=f"Game over - winner: {flow.get('winner')}. "
                     "Position verified. Good game!"), flow, 0
        side = pbm.ai_side(doc)
        if flow["mover"] != side:
            raise pbm.PBMError(
                f"this file says it is {flow['mover']}'s turn, but "
                f"{flow['mover']} is the human seat - the AI has nothing to "
                "play. Did you send your file before ending your turn?")
        if flow.get("phase") != "movement":
            raise pbm.PBMError(
                f"the {side} player turn is already part-played "
                f"(phase: {flow.get('phase')}) - a mailed turn must start "
                "at the top of the player turn")
        plan = champ_mod.plan_for(eng, game_dir)   # trained champion
        steps = (plans_mod.take_turn(eng, plan) if plan
                 else AI[doc["mode"]].take_turn(eng))
        flow = eng.flow()
        full = pbm.read_log(eng.log_path)
        entries = received + full[len(received):]   # sender's bytes + AI delta
        n_new = len(entries) - len(received)
        note = (f"AI General played turn {doc.get('turn', '?')}: "
                f"{n_new} logged actions.")
        if flow["over"]:
            note += f" GAME OVER - winner: {flow.get('winner')}."
        return pbm.make_turn_file(
            doc["game"], doc["mode"], entries, doc["sides"],
            doc["match_id"], int(doc["seq"]) + 1, flow, note=note), flow, n_new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("incoming")
    ap.add_argument("-o", "--out", default=None,
                    help="reply file path (default: reply of <incoming>)")
    ap.add_argument("--root", default=None,
                    help="repo root holding games/ (default: this checkout)")
    a = ap.parse_args()
    out = a.out or os.path.join(
        os.path.dirname(os.path.abspath(a.incoming)),
        "reply_" + os.path.basename(a.incoming))

    raw = None
    try:
        raw = json.load(open(a.incoming, encoding="utf-8"))
        doc = pbm.load_turn_file(raw)
        reply, flow, n_new = respond(doc, a.root)
    except pbm.PBMError as e:
        rej = pbm.make_rejection(raw, e)
        json.dump(rej, open(out, "w", encoding="utf-8"), indent=1)
        print(f"REJECTED: {e}\n  rejection written: {out}")
        sys.exit(2)
    json.dump(reply, open(out, "w", encoding="utf-8"))
    tag = "GAME OVER" if reply["over"] else f"to move: {reply['to_move']}"
    print(f"VERIFIED + played: {n_new} AI actions, seq {reply['seq']}, "
          f"turn {reply.get('turn')}, {tag}\n  reply written: {out}")
    sys.exit(0)


if __name__ == "__main__":
    main()
