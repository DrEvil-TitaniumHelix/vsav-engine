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
