"""
pbm.py - Play-by-mail core: the turn file, its verification, and installation.

A PBM turn file is ONE self-contained JSON document exchanged as an email
attachment. Nothing else ever travels. Format:

  {
    "format": "vsav-pbm/1",
    "game": "<slug>",              # games/<slug> (or games_bundled/<slug>)
    "mode": "bluegray",            # strategic-family gate that plays it
    "scenario": "<name>",          # cross-check vs the log's init entry
    "match_id": "...",             # stable id for the whole exchange
    "seq": 3,                      # exchange counter (increments per file)
    "sides": {"union": {"player": "human", "label": "tester@example.com"},
              "confederate": {"player": "ai", "label": "AI General"}},
    "to_move": "confederate",      # whose player turn it is after loading
    "over": false, "winner": null,
    "log": [ {...}, {...} ],       # the COMPLETE JSONL log, init entry first
    "note": "optional free-text message from the sender"
  }

The log is the game (spec #19): the init entry carries scenario, seed and
every starting position; every action entry carries the proposal, the gate's
verdict, the dice and the state hash. Receiving a file therefore means
replaying the WHOLE log through a fresh engine, exactly like
engine/verify_game.py: every verdict, every die and every state hash must
reproduce or the file is rejected with the specific failing entry. A file
built by our own app can only contain legal moves (the gate is the only
door), so a rejection means tampering, corruption, or a version mismatch -
and the sender is told to redo the turn.

PBM v1 covers the strategic family (strategic / bluegray / westwall) - the
games whose policy AI plays a whole player turn through the gate. The
tactical family (alternating fire) gets its own exchange grain later.
"""
import json
import os
import tempfile
import uuid

import gamespec
import strategic as strat_mod
import bluegray as bg_mod
import westwall as ww_mod

FORMAT = "vsav-pbm/1"
REJECT_FORMAT = "vsav-pbm-reject/1"
PBM_MODES = ("strategic", "bluegray", "westwall")

ENGINES = {"strategic": strat_mod.StrategicGame,
           "bluegray": bg_mod.BlueGrayGame,
           "westwall": ww_mod.WestwallGame}


class PBMError(Exception):
    """A turn file that must be rejected; str(e) is the reason we send back."""


# ------------------------------------------------------------ game resolution
def resolve_game_dir(slug, root=None):
    """Slug -> runnable game folder. Two passes: prefer the folder whose map
    art resolves (matches the server's pick, so the UI end serves pictures),
    but fall back to any folder with a game.json — the PBM engine replays
    LOGS, not art, and must work on an art-less checkout (BYO modules; this
    exact assumption failed in CI once)."""
    root = root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cands = []
    for base in ("games", "games_bundled"):
        d = os.path.join(root, base, slug)
        gj = os.path.join(d, "game.json")
        if not os.path.isfile(gj):
            continue
        try:
            spec = json.load(open(gj, encoding="utf-8"))
        except Exception:
            continue
        cands.append(d)
        m = (spec.get("assets") or {}).get("map")
        p = m if (not m or os.path.isabs(m)) else os.path.join(d, m)
        if not m or os.path.exists(p):
            return d
    if cands:
        return cands[0]          # engine-complete but art-less: fine for PBM
    raise PBMError(f"game {slug!r} is not installed on this machine")


def find_scenario(game_dir, name):
    for cand in sorted(os.listdir(game_dir)):
        if cand.startswith("scenario") and cand.endswith(".json"):
            s = json.load(open(os.path.join(game_dir, cand), encoding="utf-8"))
            if s.get("name") == name:
                return os.path.join(game_dir, cand)
    raise PBMError(f"scenario {name!r} not found in {game_dir}")


# ------------------------------------------------------------------ envelope
def load_turn_file(doc):
    """Validate a parsed turn-file document; returns it. Raises PBMError with
    the reason we mail back on anything malformed."""
    if not isinstance(doc, dict):
        raise PBMError("turn file is not a JSON object")
    if doc.get("format") != FORMAT:
        raise PBMError(f"unknown format {doc.get('format')!r} "
                       f"(this build speaks {FORMAT})")
    for k in ("game", "mode", "scenario", "match_id", "seq", "sides",
              "to_move", "log"):
        if k not in doc:
            raise PBMError(f"turn file is missing {k!r}")
    if doc["mode"] not in PBM_MODES:
        raise PBMError(f"mode {doc['mode']!r} is not play-by-mail capable "
                       f"(v1 plays: {', '.join(PBM_MODES)})")
    log = doc["log"]
    if not (isinstance(log, list) and log and log[0].get("event") == "init"):
        raise PBMError("log must be a list starting with the init entry")
    if log[0].get("mode") != doc["mode"]:
        raise PBMError("envelope mode does not match the log's init entry")
    if log[0].get("scenario") != doc["scenario"]:
        raise PBMError("envelope scenario does not match the log's init entry")
    sides = doc["sides"]
    players = sorted(v.get("player") for v in sides.values())
    if players != ["ai", "human"]:
        raise PBMError("sides must name exactly one human and one ai player")
    return doc


def read_turn_file(path):
    try:
        doc = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        raise PBMError(f"could not parse turn file: {e}")
    return load_turn_file(doc)


def ai_side(doc):
    return next(s for s, v in doc["sides"].items() if v["player"] == "ai")


def human_side(doc):
    return next(s for s, v in doc["sides"].items() if v["player"] == "human")


# -------------------------------------------------------------------- replay
def build_engine(game_dir, scenario_name, live_dir, seed, tier, mode):
    game = gamespec.Game(game_dir)
    scen_path = find_scenario(game_dir, scenario_name)
    cls = ENGINES[mode]
    return cls(game, scen_path, live_dir, seed=seed, tier=tier)


def replay(game_dir, entries, live_dir):
    """Replay a complete log through a FRESH engine in live_dir with full
    verify_game semantics - every verdict, resolution and state hash must
    reproduce. Returns the live engine positioned after the last entry.
    Raises PBMError naming the first failing entry."""
    init = entries[0]
    # a stale state file would make the engine RESUME instead of replaying
    gkey = os.path.basename(os.path.normpath(game_dir))
    for leftover in (f"game_{gkey}.state.json", f"game_{gkey}.log.jsonl"):
        p = os.path.join(live_dir, leftover)
        if os.path.exists(p):
            os.remove(p)
    eng = build_engine(game_dir, init["scenario"], live_dir,
                       init["seed"], init.get("tier"), init["mode"])
    for lu in init["units"]:
        u = eng.s["units"].get(lu["pid"])
        if not u or [u["col"], u["row"]] != lu["hex"] or u["side"] != lu["side"]:
            raise PBMError(f"init mismatch for {lu['pid']} - the scenario on "
                           "this machine differs from the sender's")
    for e in entries[1:]:
        if e.get("event") != "action":
            continue
        r = eng.submit(e["side"], e["action"])
        if e["verdict"]["legal"] != r["verdict"]["legal"]:
            raise PBMError(
                f"entry {e['n']}: verdict mismatch - the file says "
                f"{e['verdict']['legal']}, this engine says "
                f"{r['verdict']['legal']} ({'; '.join(r['verdict']['reasons'])})")
        if (e.get("result") or {}) != (r.get("result") or {}):
            raise PBMError(f"entry {e['n']}: dice/resolution mismatch")
        if e["state_hash"] != eng.state_hash():
            raise PBMError(f"entry {e['n']}: state hash mismatch")
    return eng


def verify_turn_file(doc, root=None):
    """Full check of a validated envelope: replay the whole log in a scratch
    dir and cross-check the envelope's own claims. Returns (game_dir, flow)
    where flow is the engine's flow() after the last entry."""
    game_dir = resolve_game_dir(doc["game"], root)
    with tempfile.TemporaryDirectory() as tmp:
        eng = replay(game_dir, doc["log"], tmp)
        flow = eng.flow()
    if bool(doc.get("over")) != bool(flow["over"]):
        raise PBMError("envelope 'over' flag disagrees with the replayed game")
    if not flow["over"] and doc["to_move"] != flow["mover"]:
        raise PBMError(f"envelope says {doc['to_move']} is to move but the "
                       f"replayed game says {flow['mover']}")
    return game_dir, flow


def ensure_extends(old_entries, new_entries):
    """An incoming file must EXTEND the game we already have - same entries,
    plus the opponent's new ones. Guards against importing a stale or forked
    file from an earlier exchange."""
    if len(new_entries) < len(old_entries):
        raise PBMError("incoming file is OLDER than the game on this machine "
                       "(fewer log entries) - it looks like a stale attachment")
    for i, (a, b) in enumerate(zip(old_entries, new_entries)):
        if a.get("n") != b.get("n") or a.get("state_hash") != b.get("state_hash"):
            raise PBMError(f"incoming file diverges from this game at entry "
                           f"{i} - it belongs to a different line of play")


def install(doc, live_dir, root=None):
    """Verify an incoming turn file and make it THE live game: replay in a
    scratch dir (rejecting on any mismatch), then write the received log
    verbatim plus the replayed state into live_dir. The engines resume from
    the state file, so after install a rebuilt gate is exactly the mailed
    position. Returns (game_dir, flow)."""
    game_dir = resolve_game_dir(doc["game"], root)
    gkey = os.path.basename(os.path.normpath(game_dir))
    with tempfile.TemporaryDirectory() as tmp:
        eng = replay(game_dir, doc["log"], tmp)
        flow = eng.flow()
        state = eng.s
    if bool(doc.get("over")) != bool(flow["over"]):
        raise PBMError("envelope 'over' flag disagrees with the replayed game")
    if not flow["over"] and doc["to_move"] != flow["mover"]:
        raise PBMError(f"envelope says {doc['to_move']} is to move but the "
                       f"replayed game says {flow['mover']}")
    with open(os.path.join(live_dir, f"game_{gkey}.log.jsonl"), "w",
              encoding="utf-8") as f:
        for e in doc["log"]:
            f.write(json.dumps(e) + "\n")
    json.dump(state, open(os.path.join(live_dir, f"game_{gkey}.state.json"),
                          "w", encoding="utf-8"), indent=1)
    return game_dir, flow


# -------------------------------------------------------------------- export
def read_log(log_path):
    return [json.loads(l) for l in open(log_path, encoding="utf-8")
            if l.strip()]


def make_turn_file(slug, mode, entries, sides, match_id, seq, flow, note=None):
    return {
        "format": FORMAT,
        "game": slug,
        "mode": mode,
        "scenario": entries[0]["scenario"],
        "match_id": match_id,
        "seq": seq,
        "sides": sides,
        "to_move": flow["mover"],
        "over": bool(flow["over"]),
        "winner": flow.get("winner"),
        "turn": flow.get("turn"),
        "log": entries,
        "note": note or "",
    }


def make_rejection(doc, reason):
    """What we mail back when a turn file fails verification."""
    return {
        "format": REJECT_FORMAT,
        "match_id": doc.get("match_id") if isinstance(doc, dict) else None,
        "seq": doc.get("seq") if isinstance(doc, dict) else None,
        "reason": str(reason),
        "action_required": "Your file could not be verified against the "
                           "rules engine. Please reload your last good "
                           "position and replay your turn, then send a "
                           "fresh file.",
    }


def new_match_id():
    return uuid.uuid4().hex[:12]


# ------------------------------------------------------------- match sidecar
def sidecar_path(live_dir, slug):
    return os.path.join(live_dir, f"game_{slug}.pbm.json")


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
