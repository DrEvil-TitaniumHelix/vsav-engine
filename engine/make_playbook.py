"""
make_playbook.py - Assemble a game's PLAYBOOK (spec #22): the versioned,
evidence-linked expertise package any future AI can consume three ways -
RETRIEVE (doctrine + games into an LLM context), EXECUTE (champion genome
through any gate), TRAIN (the verified corpus).

  games/<name>/playbook/
    manifest.json     provenance: how the expertise was earned (games
                      played, generations, gauntlet/graduation record,
                      matrix evidence) - the diploma
    doctrine.md       language knowledge, every claim evidence-cited
                      (copied from the game dir, plus an auto-distilled
                      reading of the champion genome)
    champion.json     the optimized strategy: single genome, or the
                      equilibrium portfolio when the elite is intransitive
    corpus/           verified game logs, commanders' orders logs,
                      regret-miner debriefs

  python engine/make_playbook.py --game <dir> --checkpoint <ck.json>
         [--portfolio <portfolio.json>] [--corpus <file>...] --status <status.json>
"""
import argparse
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import families  # noqa: E402


def distill(theta, strat):
    """strat = the family's strategy module (owns GENES + GENE_PROSE)."""
    lines = ["## The champion genome, in words (auto-distilled)",
             "",
             "Machine-optimized doctrine - every number below was selected "
             "by tournament survival, not by argument:", ""]
    for name, _, _, _ in strat.GENES:
        v = theta[name]
        t = strat.GENE_PROSE[name]
        lines.append("- " + t.format(v=v, alt=("yes" if v >= 0.5 else "no")))
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", required=True)
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--status", required=True)
    ap.add_argument("--portfolio", default=None)
    ap.add_argument("--matrix", default=None)
    ap.add_argument("--corpus", nargs="*", default=[])
    a = ap.parse_args()

    ck = json.load(open(a.checkpoint, encoding="utf-8"))
    status = json.load(open(a.status, encoding="utf-8"))
    strat = families.for_game_dir(a.game)["strategy"]
    out = os.path.join(a.game, "playbook")
    os.makedirs(os.path.join(out, "corpus"), exist_ok=True)

    champion = {"type": "portfolio" if a.portfolio else "single",
                "strategy_family": f"engine/{strat.__name__}.py",
                "consume": {
                    # a family may describe its own execute contract
                    # (napoleonic has no turn-plan DSL)
                    "execute": getattr(
                        strat, "EXECUTE_NOTE",
                        f"{strat.__name__}.StrategyPlanner(genome) "
                        "emits one plans.py-DSL plan per turn; every "
                        "order is validated by the legality gate"),
                    "retrieve": "load doctrine.md + corpus logs into any LLM "
                                "context; plans are written in the DSL "
                                "documented in engine/plans.py",
                    "train": "corpus logs are verified, seeded, replayable "
                             "(engine/verify_game.py) - clean RL/fine-tune "
                             "trajectories"}}
    if a.portfolio:
        champion["portfolio"] = json.load(open(a.portfolio, encoding="utf-8"))
        # distill the portfolio's top-weight genome - the equilibrium winner
        # may be a hall-of-famer, not the final reigning champion
        port = champion["portfolio"]
        named = [(w, nm) for nm, w in port.get("weights", [])
                 if nm in port.get("genomes", {})]
        best = port["genomes"][max(named)[1]] if named else ck.get("reigning")
    else:
        champion["genome"] = ck.get("reigning")
        best = ck.get("reigning")
    json.dump(champion, open(os.path.join(out, "champion.json"), "w",
                             encoding="utf-8"), indent=1)

    doctrine_src = os.path.join(a.game, "doctrine.md")
    doctrine = open(doctrine_src, encoding="utf-8").read() \
        if os.path.exists(doctrine_src) else ""
    with open(os.path.join(out, "doctrine.md"), "w", encoding="utf-8") as f:
        f.write(doctrine)
        if best:
            f.write("\n\n" + distill(best, strat))

    for src in a.corpus:
        if os.path.exists(src):
            shutil.copy(src, os.path.join(out, "corpus",
                                          os.path.basename(src)))

    manifest = {
        "playbook_version": 1,
        "game": os.path.basename(os.path.normpath(a.game)),
        "earned_by": {
            "games_played": ck.get("games_played"),
            "generations": ck.get("generation"),
            "graduation": status.get("gauntlet"),
            "champion_fitness": status.get("champion_fitness"),
            "matrix_evidence": os.path.basename(a.matrix) if a.matrix
            else None,
        },
        "contents": {
            "champion.json": champion["type"],
            "doctrine.md": "evidence-cited knowledge + auto-distilled genome",
            "corpus/": sorted(os.listdir(os.path.join(out, "corpus"))),
        },
        "verification": "every corpus log replays byte-exact through "
                        "engine/verify_game.py; optimization games used "
                        "seeded dice through the same gate",
    }
    if a.matrix and os.path.exists(a.matrix):
        shutil.copy(a.matrix, os.path.join(out, "matrix.json"))
    json.dump(manifest, open(os.path.join(out, "manifest.json"), "w",
                             encoding="utf-8"), indent=1)
    print(f"playbook assembled -> {out}")
    for k, v in manifest["contents"].items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
