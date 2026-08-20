import json
import os

import salvo

FORMAT_PACKET = "harness-packet/1"
FORMAT_MOVE = "harness-move/1"
TRANSPORTS = ("folder", "url", "chat")


def supported(mode, eng=None):
    return mode in salvo.ACTION_DOCS or hasattr(eng, "allowed_actions")


def decider(eng):
    f = getattr(eng, "decider", None)
    return f() if callable(f) else salvo.decider(eng)


def allowed(eng, mode):
    f = getattr(eng, "allowed_actions", None)
    return f() if callable(f) else salvo.allowed_actions(eng, mode)


def action_types(mode):
    doc = salvo.ACTION_DOCS.get(mode, "")
    out = []
    i = 0
    while True:
        i = doc.find('{"type":"', i)
        if i < 0:
            break
        j = doc.find('"', i + 9)
        t = doc[i + 9:j]
        if t not in out:
            out.append(t)
        i = j
    return out


def sidecar_path(live_dir, slug):
    return os.path.join(live_dir, f"game_{slug}.harness.json")


def load(live_dir, slug):
    p = sidecar_path(live_dir, slug)
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    return {"seats": {}}


def save(live_dir, slug, sc):
    json.dump(sc, open(sidecar_path(live_dir, slug), "w", encoding="utf-8"),
              indent=1)


def clear(live_dir, slug):
    p = sidecar_path(live_dir, slug)
    if os.path.exists(p):
        os.remove(p)


def seat(sc, side, create=False):
    st = sc["seats"].get(side)
    if st is None and create:
        st = sc["seats"][side] = {"transport": None, "tested": False, "n": 1,
                                  "last_n": 0, "rejected": None, "queue": [],
                                  "replies": 0, "commentary": ""}
    return st


def eng_over(eng):
    s = getattr(eng, "s", None) or {}
    if s.get("over") is not None:
        return bool(s["over"])
    f = getattr(eng, "flow", None)
    return bool(f and f().get("over"))


def status(sc, eng):
    out = {}
    for side, st in sc["seats"].items():
        o = {k: st[k] for k in ("transport", "tested", "n", "replies")}
        o["queued"] = len(st["queue"])
        o["rejected"] = bool(st["rejected"])
        if eng is not None:
            o["up"] = (not eng_over(eng)) and decider(eng) == side
        out[side] = o
    return out


def packet(eng, st, side, slug, mode, kind=None):
    sc = {"llm_side": side, "n": st["n"], "match_id": slug,
          "last_n": st["last_n"], "rejected": st["rejected"]}
    pkt = salvo.build_packet(eng, sc, slug, mode)
    pkt["format"] = FORMAT_PACKET
    if kind:
        pkt["kind"] = kind
    if kind == "hello":
        pkt.pop("note", None)
        pkt["actions_allowed"] = action_types(mode)
        pkt["briefing"] = salvo.briefing(eng, side)
        pkt["units"] = salvo.unit_rows(eng)
        pkt["require"] = (
            "CONNECTION TEST. Reply with {\"format\":\"" + FORMAT_MOVE
            + "\",\"n\":" + str(st["n"]) + ",\"actions\":[...]} holding ONE "
            "OR MORE plausible opening orders for " + side + " using real "
            "unit pids from the list below (order types in this game: "
            + ", ".join(action_types(mode)) + "). Nothing is applied; the "
            "Umpire only checks that you can read a packet and answer in "
            "the right shape.")
    elif "require" in pkt:
        pkt["require"] = pkt["require"].replace(
            salvo.FORMAT_MOVE, FORMAT_MOVE).replace("write move.json",
                                                     "reply with")
    pkt.pop("schema_note", None)
    pkt["transport"] = st["transport"]
    return pkt


def check_reply(move, expect_n):
    if isinstance(move, str):
        t = move.strip()
        if t.startswith("```"):
            t = t.strip("`")
            if t.startswith("json"):
                t = t[4:]
        try:
            move = json.loads(t)
        except Exception as e:
            raise salvo.MoveError(f"reply is not JSON: {e}")
    if not isinstance(move, dict):
        raise salvo.MoveError("reply is not a JSON object")
    fmt = move.get("format")
    if fmt not in (FORMAT_MOVE, salvo.FORMAT_MOVE):
        raise salvo.MoveError(f"unknown reply format {fmt!r} (this build "
                              f"speaks {FORMAT_MOVE})")
    acts = salvo.check_move(dict(move, format=salvo.FORMAT_MOVE), expect_n)
    return acts, str(move.get("commentary") or "")


def hello_verdict(eng, side, mode, acts):
    types = action_types(mode)
    mine = {str(pid) for pid, u in eng.s["units"].items()
            if u["side"] == side}
    problems = []
    for a in acts:
        if types and a["type"] not in types:
            problems.append(f"{a['type']!r} is not an order type in this "
                            f"game (allowed: {', '.join(types)})")
        if "unit" in a and str(a["unit"]) not in mine:
            problems.append(f"{a['unit']!r} is not a {side} unit")
        for pid in a.get("attackers") or []:
            if str(pid) not in mine:
                problems.append(f"{pid!r} is not a {side} unit")
    judged = None
    if not problems and decider(eng) == side:
        judged = [eng.propose(side, a) for a in acts]
    return problems, judged


def accept_reply(st, acts, commentary):
    st["queue"] = list(acts)
    st["rejected"] = None
    st["commentary"] = commentary
    st["replies"] += 1
    st["accepted_this"] = 0


class HarnessStepper:
    def __init__(self, eng, st, side, save_cb):
        self.sg = eng
        self.st = st
        self.side = side
        self.save_cb = save_cb
        self.brain = "harness"

    def done(self):
        return not self.st["queue"]

    def peek(self):
        if not self.st["queue"]:
            return None
        a = self.st["queue"][0]
        return {"side": self.side, "action": a,
                "desc": "harness: " + json.dumps(a, separators=(",", ":"))}

    def step(self):
        if not self.st["queue"]:
            return None
        a = self.st["queue"][0]
        if eng_over(self.sg):
            self._reject(a, ["the game ended before this order"], "game_over")
            return None
        dec = decider(self.sg)
        if dec != self.side:
            self._reject(a, [f"the decision passed to {dec} - not an "
                             "illegality; wait for your next packet"],
                         "not_your_decision")
            return None
        desc = self.peek()["desc"]
        r = self.sg.submit(self.side, a)
        entry = {"side": self.side, "action": a, "desc": desc,
                 "verdict": r["verdict"], "result": r.get("result")}
        if r["verdict"]["legal"]:
            self.st["queue"].pop(0)
            self.st["accepted_this"] = self.st.get("accepted_this", 0) + 1
            if not self.st["queue"]:
                self._close()
        else:
            self._reject(a, r["verdict"]["reasons"], "illegal")
        self.save_cb()
        return entry

    def _reject(self, a, reasons, kind):
        self.st["rejected"] = {"your_move_n": self.st["n"],
                               "accepted": self.st.get("accepted_this", 0),
                               "failed_action": a, "reasons": reasons,
                               "kind": kind}
        self.st["queue"] = []
        self._close()

    def _close(self):
        self.st["last_n"] = self.sg.s["n"] - 1
        self.st["n"] += 1
        self.save_cb()


README_INTRO = """\
# HARNESS README - {name}

You are an AI being HARNESSED into a seat in a VALOR Engine wargame.
A human (your chaperone) will carry text between this game and you, or
give you a way to reach the game yourself. From the moment the game
starts you play the {side} seat on your own: the game sends you a
PACKET describing the situation and the decision it needs; you answer
with a REPLY holding one or more orders. A rules engine (the Umpire)
checks every order against the real rules of the game. Illegal orders
are rejected with the rulebook section cited and you are asked again.
You cannot break a rule, and neither can your opponent; every die is
engine-owned and seeded; the whole game replays from its log.

## STEP 1 - TELL YOUR CHAPERONE HOW YOU CAN CONNECT

Read the three ways below and answer your chaperone with exactly one of
the words FOLDER, URL or CHAT - whichever is the best you can do.

FOLDER - you can read and write files in a folder on this computer
  (Claude Code, Codex, any agent with file tools). The game writes
  packet.json into a folder the chaperone picks; you answer by writing
  move.json next to it. Ask the chaperone for the folder path. Poll
  packet.json every ~2 seconds; answer only a packet whose n you have
  not answered yet. Never touch any file except move.json.

URL - you can make HTTP requests to a local address (an agent with a
  fetch/curl tool, or a script). {url_line}
  GET  {url_base}/api/harness/packet?side={side}
       -> the current packet (JSON)
  POST {url_base}/api/harness/move
       body {{"side":"{side}","move":<your reply object>}}
  Poll the packet every ~2 seconds; POST once per packet n.

CHAT - you can do neither. The chaperone will paste each packet into
  this conversation and paste your reply back into the game. Reply with
  the JSON reply object ONLY, in one code block, nothing else around it,
  so it can be copied in one gesture.

## STEP 2 - THE CONNECTION TEST

Before the game starts you receive one packet of kind "hello". It is a
real position. Answer it exactly like a decision packet (below) with one
or more plausible opening orders for your side. Nothing is applied; it
proves you can read a packet and answer in shape. The chaperone cannot
start the game until your test answer passes.

## STEP 3 - THE LOOP (your whole job once the game starts)

1. Read the packet. "kind" tells you what is wanted:
   decision  - your orders are needed. Answer it.
   rejection - your last reply stopped at an illegal (or overtaken)
               order; "rejected" quotes the Umpire's cited reasons. The
               orders BEFORE it stood. Fix and answer the NEW n.
   wait      - not your decision. Do nothing (folder/URL: keep polling).
   over      - the game is finished. Stop.
2. Your reply is one JSON object:
     {{"format":"{fmt}","n":<the packet's n>,
      "actions":[<order>, <order>, ...],
      "commentary":"optional - your reasoning, archived with the game"}}
   Orders apply IN ORDER through the Umpire and animate on the board one
   by one. Accepted orders STAND even if a later one is rejected - no
   take-backs, same as a table. A whole phase in one reply is normal; end
   it with the phase-closing order listed below or you will be asked
   again for the same phase.
3. Every packet is SELF-CONTAINED: full situation + everything that
   happened since your last packet in "since". You need no memory of
   earlier packets; if your context is cleared, re-read this README and
   the current packet.

## ORDERS - {name}

{actions}
"""

README_PATHWAY = """\

## IS IT REALLY A GENERAL? (optional, for the chaperone and the AI)

Any capable model can send legal orders after reading this file. Very
few win: in our own tests a frontier model handed the champion's doctrine
cold scored BELOW the shipped basic policy, while the trained champion
beat it decisively. Reading is not preparation. If you want your AI to
be a general rather than a clerk, the pathway is:

1. BRIEFING - this README, the game card, the champion's doctrine and
   genome below. Keep them; an agent should carry them between games.
2. DRILL - play practice games against the Basic AI (folder or URL
   transport, unattended). After each, read the verified log and your
   rejection count; write down what cost you.
3. EXAM - play the Champion. The graduation bar the champions had to
   pass is the same bar for you.
4. RATING - results feed the generalship ladder; an unrated harness may
   still sit, and shows as unrated.
5. RESEARCHERS retraining weights: the verified log format
   (engine/verify_game.py replays any game byte-exactly), the headless
   play API (engine/plans.py play_game) and the graduation bar are all
   public in the repo. Your games are welcome in the corpus.
"""


def readme_text(slug, spec, mode, game_dir, side, turns=None, url_base=None,
                web=False):
    name = spec.get("name", slug)
    if web:
        url_line = ("(NOT available in the browser build - the engine runs "
                    "inside the page. Choose FOLDER or CHAT.)")
        base = "http://localhost:<port>"
    else:
        url_line = "The game is serving at the address below right now."
        base = url_base or "http://localhost:8641"
    lines = [README_INTRO.format(
        name=name, side=side, url_line=url_line, url_base=base,
        fmt=FORMAT_MOVE,
        actions=salvo.ACTION_DOCS.get(mode, "(see the game's Rules panel)"))]
    lines += ["## GAME CARD", f"- Game: {name}", f"- Your side: {side}"]
    if spec.get("blurb") or spec.get("description"):
        lines.append(f"- About: {spec.get('blurb') or spec.get('description')}")
    if turns:
        lines.append(f"- Length: {turns} game turns")
    order = (spec.get("sides") or {}).get("order")
    if order:
        lines.append(f"- Sides: {' vs '.join(order)} "
                     f"({order[0]} moves first each game turn)")
    lines.append("- Victory, terrain and combat are enforced by the Umpire; "
                 "rejections quote the rulebook section that stopped you.")
    lines.append(README_PATHWAY)
    doctrine = os.path.join(game_dir, "playbook", "doctrine.md")
    if os.path.isfile(doctrine):
        lines += ["## THE CHAMPION PLAYBOOK (know your enemy)", "",
                  open(doctrine, encoding="utf-8").read()]
        lines += salvo._genome_section(game_dir)
    lines += ["", "## HONESTY",
              "Your commentary is archived with the game record. The log is "
              "the complete game; both sides can verify every entry. Play "
              "hard - you cannot cheat, and neither can we."]
    return "\n".join(lines)
