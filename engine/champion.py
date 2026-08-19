"""champion.py - load and play a game's trained champion (spec #22).

The champion is the playbook's highest-weight portfolio genome
(games/<slug>/playbook/champion.json). One loader, three consumers:

  ui/server.py      the interactive AI seat (whole-turn and stepped) plays
                    the champion instead of the baseline policy, and the
                    menu tag flips to "Advanced AI" - truthfully, because
                    the champion IS the opponent behind the button
  engine/pbm_respond.py   the AI General answers mailed turns with the
                    champion for the same reason
  engine/salvo.py   Mode-3 challenge matches (their LLM vs our champion)

A playbook whose portfolio kept only the baseline has no separate champion
(Austerlitz: 43k games of attack proved the equilibrium IS the shipped
policy - doctrine.md there tells the story). genome() returns None for it
and every caller falls back to the shipped policy, which the playbook
itself certifies as the strongest known strategy. The honesty rule follows:
"Advanced AI" appears only where genome() finds a real champion; a
baseline-equilibrium playbook shows "Advanced AI pending" instead (Bruce
2026-07-19) - the button plays the same shipped policy the training runs
failed to beat, and the upgrade is honestly still open.

Napoleonic-family champions would be doctrine thetas, not turn plans
(plans.take_turn handles both); none exists yet, so the napoleonic path
is exercised only by its baseline==champion identity today.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def genome(game_dir):
    """The champion genome dict, or None (no playbook, or the playbook's
    portfolio kept only the baseline)."""
    path = os.path.join(game_dir, "playbook", "champion.json")
    if not os.path.exists(path):
        return None
    try:
        c = json.load(open(path, encoding="utf-8"))
    except Exception:
        return None
    port = c.get("portfolio") or {}
    weights = port.get("weights") or []
    genomes = port.get("genomes") or {}
    if weights:
        best = max(weights, key=lambda w: w[1])[0]
        g = genomes.get(best)          # 'baseline' carries no genome entry
        return dict(g) if g else None
    g = c.get("genome")                # single-genome playbooks
    return dict(g) if g else None


def graduated(game_dir):
    """The graduation-bar record (spec #22) when the game's champion CLEARED
    the bar, else None. A wired genome is not a graduated one: the bar is
    held-out pairs against the shipped baseline plus fresh random genomes the
    champion never trained against, and only a manifest that records the run
    counts. Public 'Champion AI' claims key off this, never off genome()."""
    path = os.path.join(game_dir, "playbook", "manifest.json")
    if not os.path.exists(path):
        return None
    try:
        m = json.load(open(path, encoding="utf-8"))
    except Exception:
        return None
    bar = (m.get("earned_by") or {}).get("graduation_bar")
    if not isinstance(bar, dict):
        return None
    res = str(bar.get("result", "")).upper()
    return bar if "MET" in res and "NOT MET" not in res else None


GENERALSHIP = [
    (1, "Benedict Arnold", "cannot finish a legal game, or loses to random play"),
    (2, "Ambrose Burnside", "beats random play; loses to the scripted baseline every time"),
    (3, "George McClellan", "trades with the baseline - the training run kept the baseline as its champion"),
    (4, "Joseph Hooker", "won its own training run's gauntlet; never faced the graduation bar"),
    (5, "George Meade", "graduation bar MET - held-out pairs vs the baseline and fresh random genomes all won"),
    (6, "George Thomas", "bar met AND the genome held an unbeaten self-play streak (defended its title to the run's target)"),
    (7, "William Sherman", "bar + streak met, and beats every other genome of its own hall of fame in round-robin"),
    (8, "Ulysses Grant", "all of that, in both seats, across two independent training runs"),
    (9, "Erwin Rommel", "beats a graduated champion of a different training family (cross-family gauntlet)"),
    (10, "George Patton", "reserved - earned only against a human commander or a foreign champion, on a verified log"),
]


def _manifest(game_dir):
    path = os.path.join(game_dir, "playbook", "manifest.json")
    if not os.path.exists(path):
        return None
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return None


def generalship(game_dir):
    """The 1-10 generalship rung of the game's shipped AI, computed from the
    training record and nothing else (Bruce 2026-08-18: the data is whether
    the genome graduated correctly and what streaks it ran). Returns
    {rung, general, meaning, evidence} or None when the game ships no
    playbook (a scripted policy alone is not rated). Every rung above 4
    requires a record in playbook/manifest.json earned_by; a rung the record
    does not prove is never printed."""
    m = _manifest(game_dir)
    if m is None:
        return None
    eb = m.get("earned_by") or {}
    grad = eb.get("graduation") or {}
    bar = graduated(game_dir)
    has_genome = genome(game_dir) is not None
    wins, of = grad.get("wins"), grad.get("of")
    streak, target = grad.get("streak", 0), grad.get("target")
    unbeaten = bool(grad.get("unbeaten"))
    ev = []
    if wins is not None and of:
        ev.append(f"self-play gauntlet {wins:g}/{of}")
    if target:
        ev.append(f"title streak {streak}/{target}" + (" unbeaten" if unbeaten else ""))
    if not has_genome:
        rung = 3
        bar_rec = eb.get("graduation_bar")
        if isinstance(bar_rec, dict) and "NOT MET" in str(bar_rec.get("result", "")).upper():
            ev.append(f"graduation bar NOT MET ({bar_rec.get('held_out_pairs_vs_baseline', '')}; randoms "
                      f"{bar_rec.get('fresh_random_pairs', '')}) - baseline retained as the shipped AI")
        else:
            ev.append("training kept the baseline as champion")
    elif not bar:
        rung = 4
        ev.append("graduation bar not run")
    else:
        rung = 5
        ev.append(f"graduation bar MET ({bar.get('held_out_pairs_vs_baseline', '')}; randoms {bar.get('fresh_random_pairs', '')})")
        if unbeaten and target and streak >= target:
            rung = 6
            rr = eb.get("portfolio_round_robin")
            if rr and eb.get("round_robin_swept"):
                rung = 7
    r, name, meaning = GENERALSHIP[rung - 1]
    return dict(rung=r, of=10, general=name, meaning=meaning,
                evidence="; ".join(ev), label=f"Generalship {r}/10 - {name}")


def validated(game_dir):
    """True when the game ships a playbook at all - the self-play
    certificate exists even where the equilibrium kept the baseline."""
    return os.path.exists(os.path.join(game_dir, "playbook",
                                       "champion.json"))


def planner(eng, game_dir=None):
    """Side-agnostic planner callable(tg, side) -> plan for the game's
    champion, or None when the shipped policy is already the champion.
    eng is any gate engine built on a gamespec.Game."""
    gdir = game_dir or eng.game.dir
    g = genome(gdir)
    if g is None:
        return None
    import families
    fam = families.for_game(eng.game)
    if fam["kind"] == "napoleonic":
        # a napoleonic champion is a doctrine theta: the 'plan' IS the
        # genome (plans.take_turn hands it to ai_napoleonic as theta)
        return lambda tg, side: g
    return fam["strategy"].StrategyPlanner(g)


def plan_for(eng, game_dir=None, side=None):
    """This turn's champion plan for the current mover (or `side`), or
    None = play the shipped policy."""
    p = planner(eng, game_dir)
    if p is None:
        return None
    return p(eng, side or eng.s.get("mover"))


def take_turn(eng, game_dir=None, side=None):
    """Play the mover's whole player turn as the champion (falls back to
    the shipped policy when there is none). Same gate, same log."""
    import plans
    return plans.take_turn(eng, plan_for(eng, game_dir, side))
