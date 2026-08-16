import argparse
import json
import multiprocessing as mp
import os
import subprocess
import sys

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "engine")))


def parse_seeds(spec):
    out = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="900-959")
    ap.add_argument("--procs", type=int, default=max(1, (os.cpu_count() or 4) - 2))
    ap.add_argument("--tag", default="baseline")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    import optimize
    import families

    here = os.path.dirname(os.path.abspath(__file__))
    champ = json.load(open(os.path.join(here, "playbook", "champion.json"), encoding="utf-8"))
    weights = champ["portfolio"]["weights"]
    if len(weights) != 1 or abs(weights[0][1] - 1.0) > 1e-12:
        print(f"refusing: portfolio is a mixture ({weights}) - the measurement "
              "needs one deterministic genome")
        return 2
    theta = champ["portfolio"]["genomes"][weights[0][0]]
    fam = families.for_game_dir(here)
    if fam["kind"] != "bluegray":
        print(f"refusing: family {fam['kind']} is not bluegray")
        return 2

    seeds = parse_seeds(a.seeds)
    jobs = []
    for sd in seeds:
        jobs.append((here, theta, None, sd, None))
        jobs.append((here, None, theta, sd, None))

    pool = mp.Pool(a.procs, initializer=optimize._worker_init) if a.procs > 1 else None
    t0 = os.times()
    results = optimize.pool_run(pool, jobs)
    if pool:
        pool.close()
        pool.join()

    tagged = [(r, j[1] is theta) for r, j in zip(results, jobs)]
    pair_wins, total_margin = optimize.score(tagged)
    pairs = len(seeds)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=here,
                         capture_output=True, text=True).stdout.strip()
    rec = {
        "tag": a.tag,
        "gate_commit": sha,
        "genome": weights[0][0],
        "opponent": "shipped baseline policy AI (theta=None)",
        "seeds": seeds,
        "games": len(jobs),
        "home_away_pairs": pairs,
        "pair_wins": pair_wins,
        "win_rate": round(pair_wins / pairs, 4),
        "mean_pair_margin": round(total_margin / pairs, 3),
        "total_margin": total_margin,
    }
    out = a.out or os.path.join(here, "playbook", f"margin_{a.tag}.json")
    json.dump(rec, open(out, "w", encoding="utf-8"), indent=1)
    print(json.dumps(rec, indent=1))
    print(f"written: {out}")


if __name__ == "__main__":
    sys.exit(main())
