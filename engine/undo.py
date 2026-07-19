"""undo.py - engine-level undo: truncate the log, replay the prefix.

State = log replay (the gate logs every accepted action; replay.py rebuilds
any prefix deterministically), so undo needs no inverse-move code and no
per-game work: ONE implementation, every gated game inherits it.

WHAT ONE UNDO MEANS (Bruce 2026-07-19): one USER decision. The log records
which SIDE acted but not who was driving it - and a human legitimately
submits for the enemy seat (retreat routing, opponent pendings), so side
attribution cannot identify user decisions. Instead the submission boundary
(ui/server.py - also the Pyodide bridge's entry) marks every accepted
user-driven gesture as an undo point in a sidecar. Undo truncates the log
to just before the most recent mark - which also unwinds every AI reply and
engine consequence after it - and replays the prefix. MAX_DEPTH marks are
kept, so at most MAX_DEPTH consecutive undos are possible; new decisions
refill the window.

Guarantees:
  * the replay re-verifies every verdict, die and state hash in the prefix
    (replay.ReplayMismatch aborts the undo, live files untouched);
  * seeded dice ride the replay: undo past a roll and repeat the same
    action = the same result. No reroll-scumming, by construction;
  * nothing is destroyed: the cut tail is appended to an archive file
    (live/game_<slug>.undo_archive.jsonl) for audit;
  * forbidden in PBM and SALVO matches - accepted prefixes STAND (protocol
    rule); the server refuses before this module is reached.
"""
import json
import os

import replay as replay_mod

MAX_DEPTH = 5     # undo window: at most this many consecutive undos


# ------------------------------------------------------------- sidecar
def sidecar_path(live_dir, slug):
    return os.path.join(live_dir, f"game_{slug}.undo.json")


def archive_path(live_dir, slug):
    return os.path.join(live_dir, f"game_{slug}.undo_archive.jsonl")


def load_marks(live_dir, slug):
    p = sidecar_path(live_dir, slug)
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8")).get("marks", [])
        except (ValueError, OSError):
            return []
    return []


def save_marks(live_dir, slug, marks):
    json.dump({"marks": marks[-MAX_DEPTH:]},
              open(sidecar_path(live_dir, slug), "w", encoding="utf-8"),
              indent=1)


def clear(live_dir, slug):
    """A new game (reset, tier change, match start) voids the undo window.
    The archive file is per-session audit trail and goes with it."""
    for p in (sidecar_path(live_dir, slug), archive_path(live_dir, slug)):
        if os.path.exists(p):
            os.remove(p)


def mark(live_dir, slug, n_before, label):
    """Record an accepted user gesture: the log held `n_before` lines when
    the gesture began (undo truncates back to that line count). Called by
    the submission boundary AFTER at least one submit of the gesture was
    accepted."""
    marks = [m for m in load_marks(live_dir, slug) if m["n"] < n_before]
    marks.append({"n": int(n_before), "label": str(label)})
    save_marks(live_dir, slug, marks)


def status(live_dir, slug, log_n):
    """What the UI shows: how many undos are available right now."""
    marks = [m for m in load_marks(live_dir, slug) if m["n"] < log_n]
    return {"available": len(marks), "max": MAX_DEPTH,
            "last": marks[-1]["label"] if marks else None}


# ------------------------------------------------------------- the undo
def undo_once(game, live_dir, slug, log_path):
    """Undo the most recent marked user decision: verify-replay the log
    prefix, then swap the truncated log + archive the cut tail. Returns
    (replayed_gate, undone_label). Raises ValueError when there is nothing
    to undo, replay.ReplayMismatch when the log does not prove the prefix
    (live files are untouched in both cases)."""
    lines = [json.loads(l) for l in open(log_path, encoding="utf-8")
             if l.strip()]
    marks = [m for m in load_marks(live_dir, slug) if m["n"] < len(lines)]
    if not marks:
        raise ValueError("nothing to undo")
    m = marks.pop()
    prefix, tail = lines[:m["n"]], lines[m["n"]:]

    # replay FIRST - only a proven prefix ever replaces the live state
    tg = replay_mod.replay_prefix(game, prefix)

    # archive the cut tail (never silently destroy log lines), then truncate
    with open(archive_path(live_dir, slug), "a", encoding="utf-8") as f:
        f.write(json.dumps({"event": "undo", "undone": m["label"],
                            "cut_from_n": m["n"],
                            "cut_entries": len(tail)}) + "\n")
        for e in tail:
            f.write(json.dumps(e) + "\n")
    raw = open(log_path, encoding="utf-8").read().splitlines()
    kept = [l for l in raw if l.strip()][:m["n"]]
    with open(log_path, "w", encoding="utf-8") as f:
        for l in kept:
            f.write(l + "\n")

    save_marks(live_dir, slug, marks)
    return tg, m["label"]
