"""
families.py - The strategy-family registry (spec #22 infrastructure).

One optimizer, many game families. A FAMILY binds together everything the
optimization stack (optimize.py / portfolio.py / make_playbook.py) needs to
run tournament evolution on a game:

  game_cls   the gate-owning Game class (the engine-as-model)
  ai         the shipped baseline policy module (take_turn/_drive/play_game)
  strategy   the genome module: GENES, baseline(), random_theta(), mutate(),
             crossover(), corners(), StrategyPlanner, GENE_PROSE
  margin     graded margin from side_order[0]'s perspective; zero at the
             game's draw line, positive = first side ahead. This is the
             per-family "graded margin fn" - victory conditions differ
             (B&G: VP difference; Westwall: the 17.4 German:Allied RATIO,
             draw exactly at Ger = 2 x All; Austerlitz: broken-unit
             counts against the asymmetric A15.1 thresholds).
  result     OPTIONAL: fn(tg) -> {"vp", "winner", "over"} for families
             whose game keeps victory out of s["vp"]/s["winner"]
             (napoleonic computes it in flow()); absent = the strategic
             default, read straight from tg.s.

Detection reads game.json policy_ai.kind - the same field the UI and PBM
responder dispatch on.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _bluegray():
    import bluegray
    import ai_bluegray
    import strategy_bg
    return {
        "kind": "bluegray",
        "game_cls": bluegray.BlueGrayGame,
        "ai": ai_bluegray,
        "strategy": strategy_bg,
        # classic VP differential [B&G 17.x]
        "margin": lambda vp, order: vp[order[0]] - vp[order[1]],
    }


def _westwall():
    import westwall
    import ai_westwall
    import strategy_ww
    return {
        "kind": "westwall",
        "game_cls": westwall.WestwallGame,
        "ai": ai_westwall,
        "strategy": strategy_ww,
        # victory is the German:Allied ratio [17.4]: German Tactical above
        # 2.0, Allied Tactical below, draw exactly at Ger = 2 x All. The
        # graded margin from the Allied seat (side_order[0]) is therefore
        # 2*All - Ger: zero on the draw line, sign = winner, magnitude =
        # how far past the ratio line the result landed.
        "margin": lambda vp, order: 2 * vp[order[0]] - vp[order[1]],
    }


def _nap_margin(vp, order):
    """A15.1 graded margin from the French seat (side_order[0]). vp =
    _victory_state()['counts']: each side's OWN units destroyed/routed/
    unsteady. The French win at 7 Allied broken, the Allied at 10 French
    [A15.1]; the cross-multiplied differential (10 x Allied broken -
    7 x French broken) is zero when both sides sit at the same fraction
    of their own threshold, positive when the French are closer. The
    +/-100 bonus fires exactly when a threshold was reached - the game
    ends at that instant, so final counts imply the winner (ordered as
    _victory_state checks: French first)."""
    a, b = order                       # French, Allied
    m = 10.0 * vp[b] - 7.0 * vp[a]
    if vp[b] >= 7:
        m += 100.0
    elif vp[a] >= 10:
        m -= 100.0
    return m


def _nap_result(tg):
    """Napoleonic keeps victory in flow(), not s['vp']: mirror flow()'s
    formula exactly (live victory until the first turn-end stores it)."""
    v = tg.s.get("victory") or tg._victory_state()
    return {"vp": v["counts"], "winner": v.get("winner"),
            "over": bool(v.get("winner")) or tg.s["turn"] > tg.turns}


def _napoleonic():
    import napoleonic
    import ai_napoleonic
    import strategy_nap
    return {
        "kind": "napoleonic",
        "game_cls": napoleonic.NapoleonicGame,
        "ai": ai_napoleonic,
        "strategy": strategy_nap,
        "margin": _nap_margin,
        "result": _nap_result,
    }


_LOADERS = {"bluegray": _bluegray, "westwall": _westwall,
            "napoleonic": _napoleonic}


def kind_of(game):
    """Family kind for a loaded gamespec.Game."""
    return (game.spec.get("policy_ai") or {}).get("kind")


def for_game(game):
    """Family bundle for a loaded gamespec.Game; raises on unknown kinds -
    a game without a registered family cannot be optimized (spec #22 needs
    a plan compiler + genome per family, never a guessed one)."""
    kind = kind_of(game)
    loader = _LOADERS.get(kind)
    if loader is None:
        raise NotImplementedError(
            f"no strategy family registered for policy_ai.kind={kind!r} - "
            "register it in engine/families.py")
    return loader()


def for_game_dir(game_dir):
    import gamespec
    return for_game(gamespec.Game(game_dir))
