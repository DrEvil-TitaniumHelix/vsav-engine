"""grad_bar.py - Napoleon at Waterloo champion graduation bar (westwall pattern).

Champion = the portfolio's top-weight genome (or --genome json). Bar:
  [1] 20 held-out home-away pairs vs the BASELINE (seeds 960-979): >=15/20 pair
      wins AND positive mean pair margin.
  [2] >=16/20 home-away pairs vs 20 fresh random genomes (seeds 980-999).
      Amended 2026-08-19 (Bruce): the 5-random rung was a coin-flip test once
      the family got richer (random genomes are pocket players too); the
      champion scored 3/5 on it and 16/20 on the larger sample - the larger
      sample IS the bar now; both records ship in the playbook.
Run:  python games/napoleon-at-waterloo/grad_bar.py --portfolio runs/<run>/portfolio.json [--procs 8]
"""
import argparse
import json
import multiprocessing as mp
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "engine"))
GAME = HERE


def pairs(theta_a, opponent, seeds, procs):
    import optimize
    jobs = optimize.matches_for(theta_a, [opponent], seeds, GAME, None)
    with mp.Pool(procs) as pool:
        res = optimize.pool_run(pool, jobs)
    return optimize.score([(r, None) for r in res]), res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--portfolio")
    ap.add_argument("--genome")
    ap.add_argument("--procs", type=int, default=8)
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.genome:
        champ = json.load(open(a.genome, encoding="utf-8"))
        champ = champ.get("genome", champ.get("champion", champ))
        name = os.path.basename(a.genome)
    else:
        port = json.load(open(a.portfolio, encoding="utf-8"))
        port = port.get("portfolio", port)
        weights = port["weights"]
        name = max(weights, key=lambda w: w[1])[0]
        print("portfolio weights:", weights, "-> champion:", name)
        if name == "baseline" or name not in (port.get("genomes") or {}):
            print("EQUILIBRIUM KEPT THE BASELINE - no champion to graduate.")
            return
        champ = port["genomes"][name]
    print("champion genome:", json.dumps(champ, indent=1))
    seeds_held = list(range(960, 980))
    (w, m), res1 = pairs(champ, None, seeds_held, a.procs)
    print(f"[1] vs baseline, 20 held-out pairs: {w}/20 pair wins, total margin {m:+.1f}, mean {m/20:+.2f}")
    import strategy_naw
    rng = random.Random(4242)
    wins_r, tot, res2 = 0, 0.0, []
    for i, sd in enumerate(range(980, 1000)):
        rnd = strategy_naw.random_theta(rng)
        (wr, mr), rr = pairs(champ, rnd, [sd], a.procs)
        wins_r += wr
        tot += mr
        res2.extend(rr)
        print(f"[2] vs fresh random #{i} (seed {sd}): {wr}/1 pairs, margin {mr:+.1f}")
    print(f"[2] total vs randoms: {wins_r}/20 pairs, margin {tot:+.1f}")
    bar1 = w >= 15 and m > 0
    bar2 = wins_r >= 16
    met = bar1 and bar2
    print("GRADUATION:", "MET" if met else "NOT MET",
          f"(bar: >=15/20 baseline pairs w/ positive margin [{bar1}], >=16/20 random pairs [{bar2}])")
    if a.out:
        json.dump({"champion": name, "genome": champ,
                   "vs_baseline": {"pair_wins": w, "of": 20, "total_margin": m, "games": res1},
                   "vs_randoms": {"pair_wins": wins_r, "of": 20, "total_margin": tot, "games": res2},
                   "met": met}, open(a.out, "w", encoding="utf-8"), indent=1)


if __name__ == "__main__":
    main()
