"""salvo.py - SALVO: the folder protocol that gives an outside LLM a seat.

SALVO (Structured Adversarial LLM Versus Opponent) is Mode 2/3 of the VALOR match
system (SALVO_PROTOCOL.md at the repo root is the reference): the game
writes a self-contained DECISION PACKET describing the situation and what
kind of answer is required; the player's own LLM (Claude Code, Codex, any
file-capable agent) writes back a MOVE FILE of one or more gate actions.
Every action still enters through submit() - the packet layer adds zero
authority. Assume every submission is rejected; acceptance just advances
to the next packet (Bruce's framing - there is only one loop).

This module is pure protocol logic (packet build + move apply + the
challenger payload text). File I/O with the actual match folder lives in
the client (web/shared/salvo.js via the File System Access API); the
server exposes it at /api/salvo/* for both the native app and the
Pyodide browser build.

v1 grain: the strategic family (bluegray / westwall / strategic) - the
same games PBM v1 plays. Pending decisions (retreats, advances, exchange
losses, FPF) are routed to the seat that owns them via decider(), so a
packet can land mid-opponent-turn - the napoleonic family's interleaved
windows will reuse exactly that path.
"""
import json
import os

FORMAT_PACKET = "salvo-packet/1"
FORMAT_MOVE = "salvo-move/1"
MAX_ACTIONS = 200          # per move file; a whole player turn is ~10-40
SINCE_CAP = 200            # digest lines per packet

SALVO_MODES = ("strategic", "bluegray", "westwall")


# --------------------------------------------------------------- deciding
def decider(eng):
    """Whose input the game is waiting on: the owner of a pending
    combat-result decision when one exists, else the mover."""
    p = eng.s.get("pending")
    if p and p.get("by"):
        return p["by"]
    return eng.s.get("mover")


def allowed_actions(eng, mode):
    """Action types the current state can accept from the decider."""
    p = eng.s.get("pending")
    if p and p.get("awaiting"):
        return [p["awaiting"]]
    phase = eng.s.get("phase")
    if mode == "bluegray":
        return (["move", "reinforce", "exit", "end_movement"]
                if phase == "movement" else ["battle", "end_phase"])
    if mode == "westwall":
        return (["move", "reinforce", "exit", "demolition", "end_movement"]
                if phase == "movement" else ["battle", "end_phase"])
    if mode == "strategic":
        return ["move", "rommel_extend", "roll_supply", "land_supply",
                "land_reinforcement", "embark", "debark", "end_phase"]
    return []


# --------------------------------------------------------------- describing
def _cls(eng, u):
    f = getattr(eng, "cls", None)
    if f is None:
        return ""
    try:
        return f(u)                    # bluegray: cls(unit dict)
    except Exception:
        try:
            return f(u["pid"])         # westwall: cls(pid)
        except Exception:
            return ""


def unit_rows(eng):
    """Structured both-sides unit list (open information in these games)."""
    out = []
    moved = set(eng.s.get("moved") or [])
    for pid in sorted(eng.s["units"]):
        u = eng.s["units"][pid]
        st = eng.game.stats(u["slot"])
        out.append({"pid": pid, "side": u["side"], "slot": u["slot"],
                    "hex": f"{u['col']:02d}{u['row']:02d}",
                    "class": _cls(eng, u),
                    "attack": st[0], "defense": st[1], "ma": st[2],
                    "moved": pid in moved})
    return out


def briefing(eng, side):
    """Compact text situation report - the packet's human/LLM-readable
    core. Everything in it is derived from gate state."""
    s = eng.s
    enemy = eng.game.enemy(side)
    night = ""
    if getattr(eng, "is_night", None):
        try:
            night = " - NIGHT: no combat this game turn" if eng.is_night() else ""
        except Exception:
            night = ""
    lines = [f"GAME TURN {s['turn']} of {eng.turns}"
             f" ({eng.turn_label()})" + night,
             f"You command: {side}. Mover: {s.get('mover')}."
             f" Phase: {s.get('phase')}."]
    if s.get("vp"):
        lines.append("VP: " + "  ".join(f"{k} {v}"
                                        for k, v in sorted(s["vp"].items())))
    p = s.get("pending")
    if p:
        lines.append(f"PENDING decision ({p.get('awaiting')}) owed by "
                     f"{p.get('by')}: " +
                     json.dumps({k: v for k, v in p.items()
                                 if k not in ("awaiting", "by")},
                                default=str)[:400])
    for who in (side, enemy):
        rows = [r for r in unit_rows(eng) if r["side"] == who]
        lines.append(f"{who} units on map ({len(rows)}):")
        for r in rows:
            lines.append(f"  {r['pid']} {r['slot']} ({r['class']}, "
                         f"A{r['attack']}/D{r['defense']}/MA{r['ma']}) "
                         f"at {r['hex']}" + (" [moved]" if r["moved"] else ""))
    return "\n".join(lines)


def digest(entries, from_n):
    """One line per logged proposal after entry from_n - what happened
    since the LLM's previous packet (its own accepted prefix included)."""
    out = []
    for e in entries:
        if e.get("event") != "action" or e.get("n") is None:
            continue
        if e["n"] <= from_n:
            continue
        v = "ok" if e["verdict"]["legal"] else "REJECTED"
        r = e.get("result") or {}
        line = (f"n{e['n']} {e.get('side')} "
                + json.dumps(e["action"], separators=(",", ":"))[:160]
                + f" {v}")
        if v == "REJECTED":
            line += " (" + "; ".join(e["verdict"].get("reasons", []))[:200] + ")"
        elif r:
            line += " " + json.dumps(r, separators=(",", ":"),
                                     default=str)[:200]
        out.append(line)
    if len(out) > SINCE_CAP:
        out = ([f"... {len(out) - SINCE_CAP} earlier entries omitted ..."]
               + out[-SINCE_CAP:])
    return out


def read_log(log_path):
    if not (log_path and os.path.exists(log_path)):
        return []
    return [json.loads(l) for l in open(log_path, encoding="utf-8")
            if l.strip()]


# --------------------------------------------------------------- the packet
def build_packet(eng, sc, slug, mode):
    """The current packet - a pure function of (game state, sidecar).
    Rebuilt freely; n advances only when a move file is consumed."""
    side = sc["llm_side"]
    over = bool(eng.s.get("over"))
    dec = decider(eng)
    if over:
        kind = "over"
    elif dec != side:
        kind = "wait"
    else:
        kind = "rejection" if sc.get("rejected") else "decision"
    pkt = {"format": FORMAT_PACKET, "kind": kind, "n": sc["n"],
           "match_id": sc["match_id"], "game": slug, "you": side,
           "turn": eng.s.get("turn"), "of": eng.turns,
           "phase": eng.s.get("phase"), "mover": eng.s.get("mover")}
    entries = read_log(eng.log_path)
    pkt["since"] = digest(entries, sc.get("last_n", 0))
    if kind == "over":
        pkt["winner"] = eng.s.get("winner")
        pkt["vp"] = eng.s.get("vp")
        pkt["note"] = ("Game over. The complete verified log is log.jsonl "
                       "in this folder; engine/verify_game.py replays it "
                       "byte-exactly.")
        return pkt
    if kind == "wait":
        pkt["note"] = (f"Waiting on {dec}. Not your decision - keep "
                       "polling packet.json.")
        return pkt
    allowed = allowed_actions(eng, mode)
    pkt["actions_allowed"] = allowed
    pkt["require"] = (f"one or more gate actions for {side} "
                      f"(allowed now: {', '.join(allowed)}); write move.json "
                      f'{{"format":"{FORMAT_MOVE}","n":{sc["n"]},'
                      '"actions":[...]}')
    pkt["briefing"] = briefing(eng, side)
    pkt["units"] = unit_rows(eng)
    if eng.s.get("vp"):
        pkt["vp"] = eng.s["vp"]
    if sc.get("rejected"):
        pkt["rejected"] = sc["rejected"]
    pkt["schema_note"] = ("action formats: your challenger payload, section "
                          "ACTIONS. Answer THIS n; stale n is ignored.")
    return pkt


# --------------------------------------------------------------- the move
class MoveError(Exception):
    """A move file that cannot be processed at all (wrong format/n) -
    distinct from a legal rejection, which is normal play."""


def check_move(move, expect_n):
    if not isinstance(move, dict):
        raise MoveError("move.json is not a JSON object")
    if move.get("format") != FORMAT_MOVE:
        raise MoveError(f"unknown move format {move.get('format')!r} "
                        f"(this build speaks {FORMAT_MOVE})")
    if move.get("n") != expect_n:
        raise MoveError(f"move answers packet n={move.get('n')!r} but the "
                        f"current packet is n={expect_n} - stale answer")
    acts = move.get("actions")
    if not (isinstance(acts, list) and acts):
        raise MoveError("actions must be a non-empty list of gate actions")
    if len(acts) > MAX_ACTIONS:
        raise MoveError(f"too many actions in one move file "
                        f"(max {MAX_ACTIONS})")
    if not all(isinstance(a, dict) and a.get("type") for a in acts):
        raise MoveError("every action must be an object with a 'type'")
    return acts


def apply_move(eng, side, actions):
    """Apply the move file's actions in order through the gate. Returns
    (accepted, rejected): accepted = per-action log echoes that stood;
    rejected = None on a clean run, else the dict that goes into the next
    packet's `rejected` field. Accepted actions STAND either way."""
    accepted = []
    rejected = None
    for a in actions:
        dec = decider(eng)
        if eng.s.get("over"):
            rejected = {"failed_action": a,
                        "reasons": ["the game ended before this action"],
                        "kind": "game_over"}
            break
        if dec != side:
            rejected = {"failed_action": a,
                        "reasons": [f"the decision passed to {dec} - not an "
                                    "illegality; wait for your next packet "
                                    "before sending more actions"],
                        "kind": "not_your_decision"}
            break
        r = eng.submit(side, a)
        if r["verdict"]["legal"]:
            accepted.append({"action": a, "result": r.get("result")})
        else:
            rejected = {"failed_action": a,
                        "reasons": r["verdict"]["reasons"],
                        "kind": "illegal"}
            break
    return accepted, rejected


# --------------------------------------------------------------- sidecar
def sidecar_path(live_dir, slug):
    return os.path.join(live_dir, f"game_{slug}.salvo.json")


def load_sidecar(live_dir, slug):
    p = sidecar_path(live_dir, slug)
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    return None


def save_sidecar(live_dir, slug, sc):
    json.dump(sc, open(sidecar_path(live_dir, slug), "w", encoding="utf-8"),
              indent=1)


def clear_sidecar(live_dir, slug):
    p = sidecar_path(live_dir, slug)
    if os.path.exists(p):
        os.remove(p)


# --------------------------------------------------------------- payload
ACTION_DOCS = {
    "bluegray": """\
Movement phase (submit in any order, then end_movement):
  {"type":"move", "unit":"<pid>", "dest":[col,row]}
      One unit to a reachable hex within its MA; the gate path-finds and
      enforces terrain costs, ZOC and stacking [5.x, 6.x].
  {"type":"reinforce", "unit":"<pid>", "hex":[col,row]}   arrival by column entry [15.x]
  {"type":"exit", "unit":"<pid>"}                          exit-hex departure for VP [16.x]
  {"type":"end_movement"}                                  closes your movement phase
Combat phase (attacks are voluntary; adjacency constrains who may fight):
  {"type":"battle", "attackers":["<pid>",...], "defenders":["<pid>",...],
   "bombarding":["<pid>",...]?, "odds_reduce":[n,d]?}      one battle on the CRT [7.x, 8.x]
  {"type":"end_phase"}                                     closes the combat phase
Pending decisions (a packet will ask the owning side):
  {"type":"retreat", "unit":"<pid>", "dest":[col,row],
   "displace":[["<pid>",[col,row]],...]?}                  retreat route choice
  {"type":"advance", "unit":"<pid>", "dest":[col,row]}     / {"type":"advance"} = decline [7.75]
  {"type":"exchange_loss", "units":["<pid>",...]}          attacker owes an Exchange [7.6]
  {"type":"train_retreat", "dest":[col,row]}               / dest omitted = destroyed [18.11]
Hexes are [col,row] integers; packet unit hexes print as CCRR (e.g. "0512" = [5,12]).""",
    "westwall": """\
Movement phase (submit in any order, then end_movement):
  {"type":"move", "unit":"<pid>", "dest":[col,row]}        gate enforces MA/terrain/ZOC [5.x]
  {"type":"reinforce", "unit":"<pid>", "hex":[col,row]}    column/edge/airborne arrival [15.x]
  {"type":"exit", "unit":"<pid>", "edge":"west"|"east"}    German exit for VP [15.4]
  {"type":"demolition", "attempt":{"<bridge-key>":true}}   German bridge demolition [12.x]
  {"type":"end_movement"}
Combat phase:
  {"type":"battle", "attackers":["<pid>",...], "defenders":["<pid>",...], "gsp":n}
      CRT attack; gsp = General Supply Points committed [7.x, 8.x]
  {"type":"end_phase"}
Pending decisions (a packet will ask the owning side):
  {"type":"fpf", "allocations":[["<arty-pid>","<def-pid>"],...], "gsp":n}   final protective fire [8.4]
  {"type":"retreat", "unit":"<pid>", "path":[[col,row],...],
   "eliminate":false, "city_reduce":false}                 retreat route choice [7.7, 11.1]
  {"type":"advance", "unit":"<pid>", "dest":[col,row]}     / {"type":"advance","decline":1}
Hexes are [col,row] integers; packet unit hexes print as CCRR.""",
    "strategic": """\
Player turn (supply/reinforcement, then movement; end with end_phase):
  {"type":"roll_supply"}                                   Axis Supply Table roll [12.2]
  {"type":"land_supply", "port":[col,row]}                 place an arriving supply unit
  {"type":"land_reinforcement", "unit":"<pid>", "port":[col,row]}   [19.1-19.7]
  {"type":"move", "unit":"<pid>", "dest":[col,row], "path":[[col,row],...]?}
  {"type":"rommel_extend", "unit":"<pid>", "path":[[col,row],...]}  [22.1]
  {"type":"embark", "unit":"<pid>"} / {"type":"debark", "unit":"<pid>", "port":[col,row]}
  {"type":"end_phase"}
Hexes are [col,row] integers; packet unit hexes print as CCRR.""",
}

LOOP_TEXT = """\
THE LOOP (your whole job):
1. Read packet.json in the match folder. If you already answered its n,
   wait ~2 seconds and read it again.
2. kind "decision" or "rejection": decide, then OVERWRITE move.json with
     {"format":"salvo-move/1","n":<the packet's n>,"actions":[...],
      "commentary":"optional - why"}
   actions = one or more gate actions applied in order. One at a time is
   safest (you see each die before the next decision); a whole phase at
   once is faster. Accepted actions STAND even when a later one in your
   list is rejected - no take-backs, same as a table.
3. kind "rejection": your previous move file stopped at an illegal (or
   overtaken) action - the packet quotes the gate's rulebook-cited
   reasons. Fix it and answer the NEW n. Being rejected is normal; the
   gate is teaching you the rules.
4. kind "wait": not your decision. Keep polling.
5. kind "over": the game is finished - stop.
Every packet is SELF-CONTAINED (full situation + everything that happened
since your last packet in `since`). You need no memory of earlier packets:
if your context is cleared, re-read payload + current packet and continue.
If packet.json ever fails to parse, you caught it mid-write - just re-read.
NEVER touch any file except move.json. The log (log.jsonl) is the complete
verified game record - engine/verify_game.py in the public repo replays it
byte-exactly, so neither side can cheat: every action you submit is judged
by the legality gate, every die is engine-owned and seeded."""


def _genome_section(game_dir):
    """The champion genome itself - the exact numbers the opponent plays
    by (Bruce 2026-07-18: the challenger gets the genome, not just the
    prose; the corpus of played games is what stays home). Rendered as
    JSON + the family's own gene-by-gene distillation."""
    import champion
    g = champion.genome(game_dir)
    if g is None:
        return []
    lines = [
        "",
        "## THE CHAMPION GENOME (the exact numbers it plays by)",
        "",
        "This is not a summary - it IS the opponent. These parameters, "
        "plugged into the shipped policy (public code: engine/strategy_*.py "
        "in the repo), are everything its training learned. Read them as "
        "precise intelligence: they say exactly when it commits, how much "
        "force it masses, where it stands off. You may imitate them, "
        "counter them, or clone the repo and run them as your own advisor.",
        "",
        "```json",
        json.dumps(g, indent=1),
        "```",
        "",
    ]
    try:
        import families
        fam = families.for_game_dir(game_dir)
        strat = fam["strategy"]
        lines.append("Gene by gene:")
        for name, *_ in strat.GENES:
            if name in g:
                t = strat.GENE_PROSE.get(name)
                if t:
                    v = g[name]
                    lines.append("- `" + name + "`: "
                                 + t.format(v=v, alt=("yes" if v >= 0.5
                                                      else "no")))
    except Exception:
        pass                      # the raw JSON above is the contract
    return lines


def payload_text(slug, spec, mode, game_dir, turns=None):
    """The challenger payload: ONE paste-in document that teaches any
    file-capable LLM to play this game through the SALVO folder. Contents:
    the loop, this game's action formats, the game card, and the champion
    playbook (doctrine.md) - our own evolved doctrine, published as the
    standing challenge: beat it."""
    name = spec.get("name", slug)
    lines = [
        f"# SALVO CHALLENGER PAYLOAD - {name}",
        "",
        "You are an AI taking a seat in a VALOR Engine wargame. VALOR "
        "enforces the game's real rules through a legality gate: illegal "
        "moves are impossible for you AND your opponent, dice are "
        "engine-owned and seeded, and the whole game replays from its log "
        "for independent verification. You play by reading and writing two "
        "files in the match folder your human designated.",
        "",
        "MATCH FOLDER: the human running the match picked it in the game's "
        "Matches panel and will paste its path here - if you were not "
        "given a path, ask for it before doing anything else.",
        "",
        LOOP_TEXT,
        "",
        "## ACTIONS - " + name,
        "",
        ACTION_DOCS.get(mode, "(see SALVO_PROTOCOL.md)"),
        "",
        "## GAME CARD",
        f"- Game: {name}",
    ]
    if spec.get("blurb") or spec.get("description"):
        lines.append(f"- About: {spec.get('blurb') or spec.get('description')}")
    if turns:
        lines.append(f"- Length: {turns} game turns")
    order = (spec.get("sides") or {}).get("order")
    if order:
        lines.append(f"- Sides: {' vs '.join(order)} "
                     f"({order[0]} moves first each game turn)")
    lines.append("- Victory, terrain and combat are enforced by the gate; "
                 "rejections quote the rulebook section that stopped you. "
                 "The in-game Rules panel documents the enforced scope.")
    doctrine = os.path.join(game_dir, "playbook", "doctrine.md")
    if os.path.isfile(doctrine):
        lines += [
            "",
            "## THE CHAMPION PLAYBOOK (know your enemy)",
            "",
            "What follows is the shipped opponent's own doctrine - evolved "
            "in mass self-play through this same engine and published in "
            "full. This is the AI you are trying to beat. Use its doctrine "
            "against it, or find the line of play its training never met.",
            "",
            open(doctrine, encoding="utf-8").read(),
        ]
        lines += _genome_section(game_dir)
    else:
        lines += [
            "",
            "## OPPONENT",
            "",
            "This game's built-in opponent plays its shipped baseline "
            "policy (no trained champion playbook yet).",
        ]
    lines += [
        "",
        "## HONESTY",
        "Your commentary field is archived with the match record. The "
        "match folder's log.jsonl is the complete game; both sides can "
        "verify every entry. Play hard - you cannot cheat, and neither "
        "can we.",
    ]
    return "\n".join(lines)
