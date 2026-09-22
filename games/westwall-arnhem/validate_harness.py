import json, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "engine"))
sys.path.insert(0, os.path.join(ROOT, "ui"))
import server as srv                            # noqa: E402
import harness                                  # noqa: E402
import ai_westwall as wai                       # noqa: E402
import verify_game                              # noqa: E402

ok = True


def check(cond, msg):
    global ok
    print(("  ok   " if cond else "  FAIL ") + msg)
    ok = ok and bool(cond)


tmp = tempfile.mkdtemp(prefix="harness_")
srv.LIVE = tmp
srv.load_game(HERE)
SG = srv.SG
HS, OPP = "All", "Ger"

print("== seat kinds")
kinds = srv.seat_kinds()
check("harness" in kinds, f"harness offered for westwall: {kinds}")
r = srv.api_seats({"seats": {HS: "harness", OPP: "champion"}})
check(r.get("ok") and r["seats"]["current"][HS] == "harness", "seats set: All=harness, Ger=champion")
check(srv.api_seats({"start": True}).get("error"), "Start refused while the harness is untested")

print("== readme")
rd = srv.api_harness_readme({"side": [HS]})
txt = rd.get("text", "")
for needle in ("FOLDER", "URL", "CHAT", "/api/harness/packet?side=All", "hello",
               harness.FORMAT_MOVE, "end_movement", "THE CHAMPION PLAYBOOK",
               "IS IT REALLY A GENERAL"):
    check(needle in txt, f"readme carries {needle!r}")

print("== transport + hello")
r = srv.api_harness_config({"side": HS, "transport": "chat"})
check(r["harness"][HS]["transport"] == "chat", "transport recorded")
pk = r["packet"]
check(pk["kind"] == "hello" and pk["format"] == harness.FORMAT_PACKET, f"pre-Start packet is a hello (n={pk['n']})")
check(pk["units"] and any(u["side"] == HS for u in pk["units"]), "hello packet lists units")
bad = srv.api_harness_hello({"side": HS, "move": "not json at all"})
check(bad.get("ok") is False and "JSON" in bad["verdict"], f"garbage reply refused: {bad['verdict']}")
mine = [u["pid"] for u in pk["units"] if u["side"] == HS]
theirs = [u["pid"] for u in pk["units"] if u["side"] == OPP]
wrong = srv.api_harness_hello({"side": HS, "move": {"format": harness.FORMAT_MOVE, "n": pk["n"],
                               "actions": [{"type": "move", "unit": theirs[0], "dest": [1, 1]}]}})
check(wrong.get("ok") is False and "not a All unit" in wrong["verdict"], f"enemy pid refused: {wrong['verdict']}")
check(not srv.harness_status()[HS]["tested"], "still untested after refusals")
fenced = "```json\n" + json.dumps({"format": harness.FORMAT_MOVE, "n": pk["n"],
                                    "actions": [{"type": "end_movement"}],
                                    "commentary": "hello"}) + "\n```"
good = srv.api_harness_hello({"side": HS, "move": fenced})
check(good.get("ok") is True, f"fenced chat reply passes: {good.get('verdict')}")
check(srv.harness_status()[HS]["tested"], "harness marked tested")
check(SG.s["n"] == 1 and SG.s["phase"] == "movement", "hello applied nothing")
r = srv.api_seats({"start": True})
check(r.get("ok") and srv.STARTED, "Start accepted after the test")

print("== play: rejection loop + accepted prefix")
r = srv.api_ai_step({"side": HS})
check(r.get("waiting") and r["packet"]["kind"] == "decision", "ai_step waits on the harness with a decision packet")
n = r["packet"]["n"]
unit = mine[0]
r = srv.api_harness_move({"side": HS, "move": {"format": harness.FORMAT_MOVE, "n": n,
                          "actions": [{"type": "end_movement"},
                                      {"type": "move", "unit": unit, "dest": [1, 1]}]}})
check(r.get("ok") and r["queued"] == 2, "reply of 2 orders queued")
steps = []
while True:
    r = srv.api_ai_step({"side": HS})
    if r.get("step"):
        steps.append(r["step"])
    if r.get("done") or r.get("waiting") or r.get("error"):
        break
check(len(steps) == 2 and steps[0]["verdict"]["legal"] and steps[0]["action"]["type"] == "end_movement"
      and not steps[1]["verdict"]["legal"], "both orders surfaced as steps: end_movement legal, move refused")
check(SG.s["phase"] == "combat", "phase advanced to combat")
st = harness.seat(harness.load(tmp, srv.GAME_SLUG), HS)
check(st["rejected"] and st["rejected"]["accepted"] == 1 and st["rejected"]["kind"] == "illegal",
      f"second order rejected, prefix of 1 stood: {st['rejected']['reasons'][:1]}")
r = srv.api_ai_step({"side": HS})
check(r.get("waiting") and r["packet"]["kind"] == "rejection" and r["packet"]["n"] == n + 1,
      "next packet is a rejection with a new n")
stale = srv.api_harness_move({"side": HS, "move": {"format": harness.FORMAT_MOVE, "n": n,
                              "actions": [{"type": "end_phase"}]}})
check("stale" in (stale.get("error") or ""), "stale n refused")

print("== full game vs champion")
guard = 0
replies = 0
while not srv.sg_over() and guard < 5000:
    guard += 1
    side = harness.decider(SG)
    r = srv.api_ai_step({"side": side})
    if r.get("waiting"):
        pk = r["packet"]
        if SG.s.get("pending"):
            by, act = wai._resolve_pending(SG)
            acts = [act]
        elif SG.s["phase"] == "movement":
            acts = [{"type": "end_movement"}]
        else:
            acts = [{"type": "end_phase"}]
        m = srv.api_harness_move({"side": HS, "move": {"format": harness.FORMAT_MOVE, "n": pk["n"],
                                  "actions": acts}})
        if not m.get("ok"):
            check(False, f"harness reply refused: {m.get('error')}")
            break
        replies += 1
        continue
    if r.get("error"):
        check(False, f"ai_step error for {side}: {r['error']}")
        break
check(srv.sg_over(), f"game reached its end (turn {SG.s['turn']}, {replies} harness replies, {guard} steps)")
check(srv.harness_status()[HS]["replies"] == replies + 1, "reply count tracked")
okv, msg = verify_game.verify(HERE, SG.log_path)
check(okv, f"log replays: {msg}")
r = srv.api_ai_step({"side": HS})
check(r.get("done") and "over" in (r.get("error") or ""), "ai_step reports game over")

print("== reset clears the harness")
srv.api_reset({})
check(not os.path.exists(harness.sidecar_path(tmp, srv.GAME_SLUG)), "sidecar removed on reset")
check(not srv.STARTED, "reset returns to setup")

print("\nvalidate_harness:", "ALL PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
