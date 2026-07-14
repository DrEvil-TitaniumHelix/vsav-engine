"""
portfolio.py - The equilibrium exit (spec #22): when a game's elite
strategy space is intransitive, no single genome is unbeatable - the
mathematically unbeatable object is the Nash MIXTURE over the elite.

Takes an optimize.py checkpoint, gathers the candidate pool (reigning
champion + hall of fame + baseline policy), plays the full home-and-away
round-robin on held-out seeds through the gate, then solves the resulting
symmetric zero-sum game by fictitious play. Outputs:

  matrix.json     pairwise mean pair-margins (evidence, replayable seeds)
  portfolio.json  the equilibrium mixture: [(weight, genome), ...] plus
                  worst-case expected margin (>= ~0 means no strategy in
                  the pool beats the mixture on average)

  python engine/portfolio.py --checkpoint <ck.json> --game <dir> --out <dir>
         [--k 8] [--seeds 10] [--procs 8]
"""
import argparse
import json
import multiprocessing as mp
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import optimize  # noqa: E402
import families  # noqa: E402

HELDOUT = list(range(940, 990))       # disjoint from training AND gauntlet


def dedupe(genomes, genes):
    seen, out = set(), []
    for g in genomes:
        key = tuple(round(g[n], 4) for n, _, _, _ in genes)
        if key not in seen:
            seen.add(key)
            out.append(g)
    return out


def pair_margin(results):
    """results: [res_as_A, res_as_B] -> candidate aggregate margin."""
    return results[0]["margin_a"] - results[1]["margin_a"]


def fictitious_play(M, iters=200000):
    """Symmetric zero-sum equilibrium over payoff matrix M (row beats col
    when positive). Returns mixture weights."""
    n = len(M)
    counts = [1.0] * n
    for _ in range(iters):
        # best response to the opponent mixture implied by counts
        tot = sum(counts)
        vals = [sum(M[i][j] * counts[j] for j in range(n)) / tot
                for i in range(n)]
        counts[max(range(n), key=lambda i: vals[i])] += 1.0
    tot = sum(counts)
    return [c / tot for c in counts]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--game", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--procs", type=int, default=8)
    a = ap.parse_args()

    ck = json.load(open(a.checkpoint, encoding="utf-8"))
    genes = families.for_game_dir(a.game)["strategy"].GENES
    pool_genomes = dedupe(([ck["reigning"]] if ck.get("reigning") else [])
                          + list(reversed(ck.get("hall_of_fame", []))),
                          genes)[:a.k]
    # entrants: elite genomes + None (the shipped baseline policy AI)
    entrants = pool_genomes + [None]
    names = [f"elite_{i}" for i in range(len(pool_genomes))] + ["baseline"]
    seeds = HELDOUT[:a.seeds]
    n = len(entrants)
    print(f"round-robin: {n} entrants x {n - 1} opponents x {len(seeds)} "
          f"seeds x 2 seatings = {n * (n - 1) * len(seeds)} games")

    jobs, index = [], []
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            for sd in seeds:
                jobs.append((a.game, entrants[i], entrants[j], sd, None))
                index.append((i, j, sd))
    with mp.Pool(a.procs) as pl:
        results = pl.map(optimize.play_one, jobs)

    # mean pair margin M[i][j] over seeds (i as side A vs j, minus reverse)
    sums = [[0.0] * n for _ in range(n)]
    cnts = [[0] * n for _ in range(n)]
    by_key = {}
    for (i, j, sd), res in zip(index, results):
        by_key[(i, j, sd)] = res["margin_a"]
    M = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            vals = []
            for sd in seeds:
                # i's aggregate when i is A vs j, and B when j is A
                vals.append(by_key[(i, j, sd)] - by_key[(j, i, sd)])
            M[i][j] = sum(vals) / (2 * len(vals))   # per-game normalized

    os.makedirs(a.out, exist_ok=True)
    json.dump({"names": names, "seeds": seeds, "matrix": M},
              open(os.path.join(a.out, "matrix.json"), "w",
                   encoding="utf-8"), indent=1)

    weights = fictitious_play(M)
    # worst case for the mixture: min over pure strategies of -M[i]·w
    worst = min(-sum(M[i][j] * weights[j] for j in range(n))
                for i in range(n))
    port = {"weights": [(names[i], round(weights[i], 4)) for i in range(n)
                        if weights[i] > 0.005],
            "worst_case_mean_margin_for_mixture": round(worst, 2),
            "genomes": {names[i]: entrants[i] for i in range(n)
                        if weights[i] > 0.005 and entrants[i] is not None}}
    json.dump(port, open(os.path.join(a.out, "portfolio.json"), "w",
                         encoding="utf-8"), indent=1)

    print("\nPAYOFF MATRIX (mean pair margin, row vs col):")
    print("            " + " ".join(f"{nm[:9]:>9}" for nm in names))
    for i in range(n):
        print(f"{names[i][:11]:>11} "
              + " ".join(f"{M[i][j]:>9.1f}" for j in range(n)))
    print("\nEQUILIBRIUM PORTFOLIO:")
    for nm, w in port["weights"]:
        print(f"  {w:.1%}  {nm}")
    print(f"worst-case mean margin vs any pool strategy: {worst:+.2f} "
          f"(>= 0 means the mixture is unbeaten in expectation)")


if __name__ == "__main__":
    main()
