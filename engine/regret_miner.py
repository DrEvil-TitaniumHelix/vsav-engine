"""
regret_miner.py - Counterfactual debrief: which decisions decided this game?

Stage 1 of the expert-AI plan. For a FINISHED game log (the same append-only
JSONL that verify_game.py audits), this tool finds the moves that mattered
and PROVES how much, by replaying the roads not taken:

  1. the log is replayed through a fresh gate (verify_game's mechanism) and
     the state is snapshotted just before each mined decision;
  2. from each snapshot, branches are spawned: the FACTUAL branch (the
     logged action) and up to K ALTERNATIVE branches (different legal
     destinations / targets, chosen by spread heuristics);
  3. every branch is completed by the SAME policy AI for BOTH sides on the
     SAME seeded dice stream, and scored at game end;
  4. the report ranks decisions by proven regret: the exact final-margin
     delta between the best alternative and the factual move.

Integrity: every branch action enters through the gate's submit() - the
miner has no other door. Illegal alternatives are recorded as discarded
(the gate's verdict is the authority). Each spawned branch's state hash is
asserted equal to the source snapshot before play continues. The whole run
is deterministic: same log + same game dir => same report.

Honest limitations (v1, declared):
  - decisions mined: "move" (all games) and "fire" (Tobruk). Battle
    declarations, retreats and reinforcement placement are not yet varied.
  - alternatives are completed by the shipped policy AI, so a delta means
    "better/worse under continued policy play", not perfect play.
  - Afrika Korps (mode "strategic") has no VP score - margins there are
    win/draw/loss (+1/0/-1), so only result-flipping regrets are visible.
  - the delta baseline is the FACTUAL BRANCH (logged action + policy
    completion), not the game's actual ending. Both branches are completed
    by identical machinery, so a delta is attributable to the substituted
    action alone. At some mid-turn points the restarted policy generator
    diverges from the original continuation (in-turn memory such as the
    reinforcement entry-hex alternator resets); the report marks these,
    and the per-run summary counts how many baselines reproduced the
    actual ending exactly.

Usage:
  python engine/regret_miner.py live/game_<g>.log.jsonl --game games/<dir>
         [--points 20] [--alts 3] [--top 8] [--json out.json] [-v]
"""
import argparse
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gamespec            # noqa: E402
import gamestate as gs_mod  # noqa: E402
import strategic as strat_mod  # noqa: E402
import bluegray as bg_mod   # noqa: E402
import westwall as ww_mod   # noqa: E402
import ai as ai_tactical    # noqa: E402
import ai_strategic         # noqa: E402
import ai_bluegray          # noqa: E402
import ai_westwall          # noqa: E402


# ------------------------------------------------------------ family registry
def _rollout_generic(ai_mod):
    def run(tg):
        ai_mod.play_game(tg)
    return run


def _rollout_tactical(tg):
    """Whole-game driver for TacticalGame (movement segments per side, then
    alternating best-shot fire), all through the gate."""
    guard = 0
    while not tg.s["over"] and guard < 5000:
        guard += 1
        if tg.s["segment"] == "movement":
            ai_tactical.take_movement_segment(tg, tg.s["mover"])
        else:
            ai_tactical.take_one_fire(tg, tg.s["initiative"])


FAMILIES = {
    "bluegray": dict(ctor=bg_mod.BlueGrayGame, rollout=_rollout_generic(ai_bluegray),
                     mined={"move"}, tiered=True),
    "westwall": dict(ctor=ww_mod.WestwallGame, rollout=_rollout_generic(ai_westwall),
                     mined={"move"}, tiered=True),
    "strategic": dict(ctor=strat_mod.StrategicGame, rollout=_rollout_generic(ai_strategic),
                      mined={"move"}, tiered=True),
    None: dict(ctor=gs_mod.TacticalGame, rollout=_rollout_tactical,
               mined={"move", "fire"}, tiered=False),
}


# ------------------------------------------------------------ engine plumbing
def find_scenario(game_dir, init):
    for cand in sorted(os.listdir(game_dir)):
        if cand.startswith("scenario") and cand.endswith(".json"):
            s = json.load(open(os.path.join(game_dir, cand), encoding="utf-8"))
            if s.get("name") == init["scenario"]:
                return os.path.join(game_dir, cand)
    raise SystemExit(f"scenario '{init['scenario']}' not found in {game_dir}")


def make_engine(game, scen_path, live_dir, init, fam):
    if fam["tiered"]:
        return fam["ctor"](game, scen_path, live_dir, seed=init["seed"],
                           tier=init.get("tier"))
    return fam["ctor"](game, scen_path, live_dir, seed=init["seed"])


def spawn(game, scen_path, init, fam, snapshot, want_hash):
    """Build a branch engine resuming from `snapshot` in its own temp dir.
    The state hash MUST match the source - a mismatch means the resume path
    rebuilt the game, and the branch would be a lie."""
    tmp = tempfile.mkdtemp(prefix="regret_")
    gkey = os.path.basename(os.path.normpath(game.dir))
    with open(os.path.join(tmp, f"game_{gkey}.state.json"), "w",
              encoding="utf-8") as f:
        json.dump(snapshot, f)
    tg = make_engine(game, scen_path, tmp, init, fam)
    if tg.state_hash() != want_hash:
        raise RuntimeError("branch resume produced a different state hash - "
                           "snapshot injection is broken for this family")
    return tg, tmp


def cleanup(tmp):
    try:
        for f in os.listdir(tmp):
            os.remove(os.path.join(tmp, f))
        os.rmdir(tmp)
    except OSError:
        pass


# ------------------------------------------------------------ scoring
def side_pair(tg, side):
    return side, tg.game.enemy(side)


def final_score(tg, mode):
    s = tg.s
    if mode in ("bluegray", "westwall"):
        vp, winner = dict(s["vp"]), s["winner"]
    elif mode == "strategic":
        vp, winner = None, s["winner"]
    else:
        v = tg.victory()
        vp = v["scores"]
        winner = s["winner"] if s["winner"] is not None else \
            (v["winner"] if s["over"] else None)
    return {"over": s["over"], "end_turn": s["turn"], "vp": vp,
            "winner": winner, "level": s.get("level")}


def margin(score, side, enemy):
    if score["vp"] is not None:
        return score["vp"][side] - score["vp"][enemy]
    w = score["winner"]
    return 0 if w in (None, "draw") else (1 if w == side else -1)


def describe_score(score):
    if score["vp"] is not None:
        vps = " ".join(f"{k} {v}" for k, v in sorted(score["vp"].items()))
        base = f"{score['winner'] or 'ongoing'} ({vps})"
    else:
        base = f"{score['winner'] or 'no winner'}"
    if score.get("level"):
        base += f" [{score['level']}]"
    return base + ("" if score["over"] else " UNFINISHED")


# ------------------------------------------------------------ alternatives
def _pix(tg, h):
    return tg.game.grid.hex_to_pixel(h[0], h[1])


def _d2(tg, a, b):
    ax, ay = _pix(tg, a)
    bx, by = _pix(tg, b)
    return (ax - bx) ** 2 + (ay - by) ** 2


def _live_enemy_hexes(tg, side):
    enemy = tg.game.enemy(side)
    try:
        return [(u["col"], u["row"]) for u in tg._live(enemy)]
    except AttributeError:
        return [(u["col"], u["row"]) for u in tg.s["units"].values()
                if u["side"] == enemy and not u.get("K")]


def _dests_of(tg, u):
    try:
        return tg.dests(u)
    except (TypeError, KeyError):
        return tg.dests(u["pid"])


def _spread_picks(tg, cands, foes, factual, k):
    """Up to k destination picks with distinct doctrine labels: aggressive
    (closest to the enemy), cautious (farthest), divergent (least like the
    actual move). Deterministic: ties broken by hex order."""
    picks, seen = [], set()

    def near(h):
        return min((_d2(tg, h, e) for e in foes), default=0)

    for label, key in (
            ("aggressive", lambda h: (near(h), h)),
            ("cautious", lambda h: (-near(h), h)),
            ("divergent", lambda h: (-_d2(tg, h, tuple(factual)), h))):
        if len(picks) >= k or not cands:
            break
        h = min(sorted(cands), key=key)
        if h not in seen:
            seen.add(h)
            picks.append((label, h))
    return picks


def alternatives(tg, mode, entry, k):
    """Candidate alternative actions for a logged decision, as
    (label, action) - all subject to the gate's verdict when submitted."""
    act = entry["action"]
    side = entry["side"]
    pid = str(act.get("unit"))
    u = tg.s["units"].get(pid)
    if u is None:
        return []
    if act["type"] == "move" and mode is not None:
        dd = _dests_of(tg, u)
        cands = [tuple(h) for h in dd if list(h) != list(act["dest"])]
        foes = _live_enemy_hexes(tg, side)
        return [(lbl, {"type": "move", "unit": u["pid"], "dest": list(h)})
                for lbl, h in _spread_picks(tg, cands, foes, act["dest"], k)]
    if act["type"] == "move" and mode is None:              # Tobruk
        lm = tg.legal_moves(pid)
        cands = {(d["col"], d["row"]): d for d in lm["dests"]
                 if [d["col"], d["row"]] != list(act["dest"])}
        foes = _live_enemy_hexes(tg, side)
        out = []
        for lbl, h in _spread_picks(tg, list(cands), foes, act["dest"], k):
            d = cands[h]
            if foes:
                near = min(foes, key=lambda e: _d2(tg, h, e))
                face = tg.facing_of_step(h, near)
            else:
                face = u["facing"]
            if face not in d["free_facings"] and not d["any_facing"]:
                face = d["free_facings"][0] if d["free_facings"] else face
            out.append((lbl, {"type": "move", "unit": u["pid"],
                              "dest": [h[0], h[1]], "facing": face}))
        return out
    if act["type"] == "fire" and mode is None:              # Tobruk
        tgts = [t for t in tg.legal_targets(pid)
                if t["legal"] and t["target"] != act["target"]]
        tgts.sort(key=lambda t: (t["hpn_adjusted"] if t["hpn_adjusted"]
                                 is not None else 99, t["target"]))
        return [(f"other-target #{str(t['target'])[-2:]}",
                 {"type": "fire", "unit": u["pid"], "target": t["target"]})
                for t in tgts[:k]]
    return []


# ------------------------------------------------------------ the mine
def hexnum(c, r):
    return f"{c:02d}{r:02d}"


def _uname(tg_units, pid):
    pid = str(pid)
    u = tg_units.get(pid)
    if not u:
        return pid
    # disambiguate same-named units (Tobruk pids) with a short id suffix
    dup = sum(1 for x in tg_units.values() if x.get("slot") == u["slot"]) > 1
    return f"{u['slot']} #{pid[-2:]}" if dup else u["slot"]


def describe_action(tg_units, act):
    name = _uname(tg_units, act.get("unit", ""))
    if act["type"] == "move":
        return f"{name} moves to {hexnum(*act['dest'])}"
    if act["type"] == "fire":
        return f"{name} fires at {_uname(tg_units, act['target'])}"
    return f"{name} {act['type']}"


def mine(game_dir, log_path, points=20, alts=3, verbose=False):
    lines = [json.loads(l) for l in open(log_path, encoding="utf-8") if l.strip()]
    if not lines or lines[0].get("event") != "init":
        raise SystemExit("log does not start with an init entry")
    init = lines[0]
    mode = init.get("mode")
    fam = FAMILIES.get(mode)
    if fam is None:
        raise SystemExit(f"unknown game mode '{mode}'")
    game = gamespec.Game(game_dir)
    scen_path = find_scenario(game_dir, init)

    # ---- pass 1: replay the log once; snapshot before each minable decision
    actions = [e for e in lines[1:] if e.get("event") == "action"]
    minable = [i for i, e in enumerate(actions)
               if e["verdict"]["legal"] and e["action"].get("type") in fam["mined"]]
    if len(minable) > points:
        stride = len(minable) / points
        minable = [minable[int(j * stride)] for j in range(points)]
    chosen = set(minable)

    snaps = []                     # (action_idx, snapshot, hash, units_by_pid)
    with tempfile.TemporaryDirectory() as tmp:
        tg = make_engine(game, scen_path, tmp, init, fam)
        for i, e in enumerate(actions):
            if i in chosen:
                snaps.append((i, json.loads(json.dumps(tg.s)), tg.state_hash(),
                              {p: dict(u) for p, u in tg.s["units"].items()}))
            r = tg.submit(e["side"], e["action"])
            if r["verdict"]["legal"] != e["verdict"]["legal"]:
                raise SystemExit(f"log replay diverged at n={e.get('n')} - "
                                 "run verify_game.py first")
        actual = final_score(tg, mode)

    # ---- pass 2: branch + roll out each snapshot
    results = []
    t0 = time.time()
    for k, (i, snapshot, want_hash, units0) in enumerate(snaps):
        e = actions[i]
        side = e["side"]
        _, enemy = side_pair_from(game, side)
        point = {"n": e.get("n"), "turn": e.get("turn"),
                 "phase": e.get("phase") or e.get("segment"),
                 "side": side, "action": e["action"],
                 "desc": describe_action(units0, e["action"]),
                 "from": _from_hex(units0, e["action"]), "branches": []}

        # factual branch: the logged action, then policy completion
        tg, tmp = spawn(game, scen_path, init, fam, snapshot, want_hash)
        r = tg.submit(side, e["action"])
        assert r["verdict"]["legal"], "factual action rejected on branch replay"
        fam["rollout"](tg)
        fact = final_score(tg, mode)
        cleanup(tmp)
        point["factual"] = fact
        fm = margin(fact, side, enemy)
        point["baseline_matches_actual"] = (
            fact["vp"] == actual["vp"] and fact["winner"] == actual["winner"])

        # alternative branches
        tg, tmp = spawn(game, scen_path, init, fam, snapshot, want_hash)
        cands = alternatives(tg, mode, e, alts)
        cleanup(tmp)
        for label, alt_action in cands:
            tg, tmp = spawn(game, scen_path, init, fam, snapshot, want_hash)
            r = tg.submit(side, alt_action)
            if not r["verdict"]["legal"]:
                point["branches"].append(
                    {"label": label, "action": alt_action, "legal": False,
                     "reasons": r["verdict"]["reasons"]})
                cleanup(tmp)
                continue
            fam["rollout"](tg)
            sc = final_score(tg, mode)
            cleanup(tmp)
            point["branches"].append(
                {"label": label, "action": alt_action, "legal": True,
                 "desc": describe_action(units0, alt_action),
                 "final": sc, "delta": margin(sc, side, enemy) - fm,
                 "flips": sc["winner"] != fact["winner"]})
        legal_b = [b for b in point["branches"] if b.get("legal") and
                   b["final"]["over"]]
        point["regret"] = max((b["delta"] for b in legal_b), default=None)
        point["dodged"] = min((b["delta"] for b in legal_b), default=None)
        results.append(point)
        if verbose:
            el = time.time() - t0
            print(f"  [{k + 1}/{len(snaps)}] n={point['n']} GT{point['turn']} "
                  f"{side} {point['desc']}: regret "
                  f"{point['regret']:+} / dodged {point['dodged']:+}"
                  if point['regret'] is not None else
                  f"  [{k + 1}/{len(snaps)}] n={point['n']} no legal alternatives",
                  f"({el:.0f}s)")

    return {"log": os.path.abspath(log_path), "game": os.path.abspath(game_dir),
            "mode": mode or "tactical", "scenario": init["scenario"],
            "seed": init["seed"], "points_mined": len(results),
            "alts_per_point": alts, "actual_final": actual,
            "points": results}


def side_pair_from(game, side):
    return side, game.enemy(side)


def _from_hex(units0, act):
    u = units0.get(str(act.get("unit", "")))
    return hexnum(u["col"], u["row"]) if u else None


# ------------------------------------------------------------ report
def report(data, top=8):
    pts = [p for p in data["points"] if p.get("regret") is not None]
    pts.sort(key=lambda p: -p["regret"])
    print(f"\nREGRET REPORT - {data['scenario']} (seed {data['seed']}, "
          f"{data['mode']})")
    print(f"actual result: {describe_score(data['actual_final'])}")
    n_match = sum(1 for p in data["points"] if p.get("baseline_matches_actual"))
    print(f"{data['points_mined']} decisions mined, "
          f"{data['alts_per_point']} alternatives each; "
          f"regret = best alternative's final-margin delta for the acting "
          f"side, PROVEN by branch replay on the same dice stream")
    print(f"baseline check: factual rollouts reproduced the actual ending at "
          f"{n_match}/{data['points_mined']} points (elsewhere the restarted "
          f"policy continuation diverges; deltas stay like-for-like)\n")
    if not pts:
        print("no decision produced a completed alternative branch")
        return
    print(f"--- the {min(top, len(pts))} decisions that decided this game ---")
    for rank, p in enumerate(pts[:top], 1):
        head = (f"#{rank}  n={p['n']} GT{p['turn']} {p['phase']} {p['side']}: "
                f"{p['desc']}" + (f" (from {p['from']})" if p["from"] else ""))
        print(head)
        tag = "" if p.get("baseline_matches_actual") else \
            "  (baseline diverges from the actual ending - like-for-like)"
        print(f"    factual outcome: {describe_score(p['factual'])}{tag}")
        best = max((b for b in p["branches"] if b.get("legal") and
                    b["final"]["over"]), key=lambda b: b["delta"])
        for b in sorted([b for b in p["branches"] if b.get("legal")],
                        key=lambda b: -b.get("delta", 0)):
            if not b["final"]["over"]:
                continue
            mark = "  ** RESULT FLIPS **" if b["flips"] else ""
            star = " <== best" if b is best and p["regret"] > 0 else ""
            print(f"    ALT {b['label']:<24} {b['desc']}: "
                  f"{describe_score(b['final'])}  d{b['delta']:+}{mark}{star}")
        print()


def main():
    try:                                  # Windows consoles default to cp1252
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("log")
    ap.add_argument("--game", required=True)
    ap.add_argument("--points", type=int, default=20,
                    help="max decision points to mine (evenly spread)")
    ap.add_argument("--alts", type=int, default=3,
                    help="alternative branches per decision")
    ap.add_argument("--top", type=int, default=8, help="report size")
    ap.add_argument("--json", help="write full results JSON here")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    data = mine(a.game, a.log, points=a.points, alts=a.alts, verbose=a.verbose)
    report(data, top=a.top)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
        print(f"full results -> {a.json}")
    print(f"({time.time() - t0:.0f}s total)")


if __name__ == "__main__":
    main()
