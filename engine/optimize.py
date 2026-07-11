"""
optimize.py - Tournament evolution over the strategy family (spec #22):
generate exhaustive experience by optimizing winning against the
engine-as-model. Population play, never one fixed opponent.

Each generation: every candidate plays home-and-away seeded campaigns
against (a) the shipped baseline policy AI, (b) the hall of fame of past
champions, (c) sampled peers. Fitness = wins + margin tiebreak. Top half
survives; children by crossover+mutation. The champion GRADUATES when it
goes unbeaten against baseline + hall of fame + fresh random challengers
on HELD-OUT seeds for --unbeaten consecutive generations ("until you
can't be beat" - within this family and opponent pool; humans still get
their turn afterwards).

Every game is played through the legality gate via the plans.py compiler.
The ledger counts every campaign; checkpoints make the run resumable;
status.json is the live scoreboard.

  python engine/optimize.py --game games/blue-and-gray-chickamauga \
      --out <dir> [--pop 16] [--gens 200] [--procs 8] [--unbeaten 3]
      [--resume] [--smoke]
"""
import argparse
import json
import multiprocessing as mp
import os
import random
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TRAIN_SEEDS = list(range(1, 401))
HELDOUT_SEEDS = list(range(900, 940))


def _load(game_dir):
    import gamespec
    game = gamespec.Game(game_dir)
    scen = None
    for cand in sorted(os.listdir(game_dir)):
        if cand.startswith("scenario") and cand.endswith(".json"):
            scen = os.path.join(game_dir, cand)
            break
    return game, scen


def play_one(args):
    """One full campaign. thetaA commands side_order[0], thetaB side_order[1];
    None = shipped baseline policy AI. Returns result dict."""
    game_dir, thetaA, thetaB, seed, max_gts = args
    import bluegray
    import plans
    import strategy_bg
    game, scen = _load(game_dir)
    with tempfile.TemporaryDirectory(prefix="opt_") as tmp:
        bg = bluegray.BlueGrayGame(game, scen, tmp, seed=seed)
        a, b = game.side_order
        planners = {}
        if thetaA is not None:
            planners[a] = strategy_bg.StrategyPlanner(thetaA)
        if thetaB is not None:
            planners[b] = strategy_bg.StrategyPlanner(thetaB)
        plans.play_game(bg, planners, max_turns=max_gts)
        vp = bg.s["vp"]
        return {"seed": seed, "vp": vp, "winner": bg.s["winner"],
                "over": bg.s["over"], "margin_a": vp[a] - vp[b]}


def matches_for(theta, opponents, seeds, game_dir, max_gts):
    """Home-and-away jobs for one candidate vs each opponent on each seed."""
    jobs = []
    for op in opponents:
        for sd in seeds:
            jobs.append((game_dir, theta, op, sd, max_gts))   # candidate = side A
            jobs.append((game_dir, op, theta, sd, max_gts))   # candidate = side B
    return jobs


def score(results_home_away):
    """wins + 0.5 draws, margin tiebreak, from the candidate's perspective."""
    w = m = 0.0
    for res, cand_is_a in results_home_away:
        margin = res["margin_a"] if cand_is_a else -res["margin_a"]
        m += margin
        if margin > 0:
            w += 1
        elif margin == 0:
            w += 0.5
    return w, m


def evaluate(pool, cands, opponents, seeds, game_dir, ledger, max_gts=None):
    """Fitness for every candidate; returns list of (wins, margin, games)."""
    jobs, spans = [], []
    for th in cands:
        j = matches_for(th, opponents, seeds, game_dir, max_gts)
        spans.append((len(jobs), len(j)))
        jobs.extend(j)
    results = pool.map(play_one, jobs) if pool else [play_one(j) for j in jobs]
    for r in results:
        ledger["games"] += 1
    out = []
    for (start, n), th in zip(spans, cands):
        ra = []
        for k in range(n):
            job = jobs[start + k]
            ra.append((results[start + k], job[1] is th))
        w, m = score(ra)
        out.append((w, m, n))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pop", type=int, default=16)
    ap.add_argument("--gens", type=int, default=200)
    ap.add_argument("--procs", type=int, default=max(1, os.cpu_count() - 2))
    ap.add_argument("--seeds-per-gen", type=int, default=1)
    ap.add_argument("--peers", type=int, default=3)
    ap.add_argument("--hof-size", type=int, default=4)
    ap.add_argument("--unbeaten", type=int, default=3,
                    help="consecutive gens the champion must stay unbeaten "
                         "on held-out seeds to graduate")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--smoke", action="store_true",
                    help="tiny run for validation: pop 4, 2 gens, serial")
    ap.add_argument("--max-gts", type=int, default=None)
    a = ap.parse_args()
    if a.smoke:
        a.pop, a.gens, a.procs, a.unbeaten = 4, 2, 1, 99
        a.peers, a.max_gts = 1, 4

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import strategy_bg

    os.makedirs(a.out, exist_ok=True)
    ck_path = os.path.join(a.out, "checkpoint.json")
    rng = random.Random(42)
    ledger = {"games": 0}
    gen0, streak = 0, 0

    if a.resume and os.path.exists(ck_path):
        ck = json.load(open(ck_path, encoding="utf-8"))
        popn, hof = ck["population"], ck["hall_of_fame"]
        gen0, streak = ck["generation"] + 1, ck.get("unbeaten_streak", 0)
        ledger["games"] = ck.get("games_played", 0)
        rng.setstate(tuple(ck["rng_state"][0:1] + [tuple(ck["rng_state"][1])]
                           + ck["rng_state"][2:]))
        print(f"resumed at generation {gen0}, {ledger['games']} games played")
    else:
        popn = [strategy_bg.baseline()]
        # a fortress-doctrine corner of the space (game 1's lessons)
        fortress = strategy_bg.baseline()
        fortress.update(garrison_per_10vp=6.0, hold_factor=1.0, mass_min=15.0,
                        endgame_turn=13.0, exit_turn=15.0, deny_weight=1.5)
        popn.append(fortress)
        while len(popn) < a.pop:
            popn.append(strategy_bg.random_theta(rng))
        hof = []

    pool = mp.Pool(a.procs) if a.procs > 1 else None
    t0 = time.time()
    try:
        for gen in range(gen0, a.gens):
            seeds = [TRAIN_SEEDS[(gen * a.seeds_per_gen + i) % len(TRAIN_SEEDS)]
                     for i in range(a.seeds_per_gen)]
            opponents = [None] + hof[-a.hof_size:] \
                + rng.sample(popn, min(a.peers, len(popn)))
            fits = evaluate(pool, popn, opponents, seeds, a.game, ledger,
                            a.max_gts)
            ranked = sorted(zip(fits, popn),
                            key=lambda fp: (-fp[0][0], -fp[0][1]))
            (bw, bm, bn), champ = ranked[0]

            # held-out gauntlet: baseline + HoF + fresh random challengers
            gauntlet = [None] + hof[-a.hof_size:] \
                + [strategy_bg.random_theta(rng) for _ in range(3)]
            gseeds = rng.sample(HELDOUT_SEEDS, 2 if not a.smoke else 1)
            gres = evaluate(pool, [champ], gauntlet, gseeds, a.game, ledger,
                            a.max_gts)
            gw, gm, gn = gres[0]
            unbeaten = gw >= gn - 1e-9
            streak = streak + 1 if unbeaten else 0

            elapsed = time.time() - t0
            status = {"generation": gen, "games_played": ledger["games"],
                      "champion_fitness": {"wins": bw, "of": bn, "margin": bm},
                      "gauntlet": {"wins": gw, "of": gn, "unbeaten": unbeaten,
                                   "streak": streak, "target": a.unbeaten},
                      "elapsed_s": round(elapsed), "champion": champ}
            json.dump(status, open(os.path.join(a.out, "status.json"), "w",
                                   encoding="utf-8"), indent=1)
            print(f"gen {gen}: champ {bw}/{bn} (margin {bm:+.0f}) | "
                  f"gauntlet {gw}/{gn} {'UNBEATEN' if unbeaten else ''} "
                  f"streak {streak}/{a.unbeaten} | games {ledger['games']} | "
                  f"{elapsed:.0f}s", flush=True)

            hof.append(dict(champ))
            hof = hof[-8:]
            ck = {"generation": gen, "population": popn, "hall_of_fame": hof,
                  "unbeaten_streak": streak, "games_played": ledger["games"],
                  "rng_state": [rng.getstate()[0], list(rng.getstate()[1]),
                                rng.getstate()[2]]}
            json.dump(ck, open(ck_path, "w", encoding="utf-8"), indent=1)

            if streak >= a.unbeaten:
                json.dump({"champion": champ, "graduated_at_gen": gen,
                           "games_played": ledger["games"]},
                          open(os.path.join(a.out, "champion.json"), "w",
                               encoding="utf-8"), indent=1)
                print(f"GRADUATED at generation {gen}: champion unbeaten "
                      f"{a.unbeaten} consecutive held-out gauntlets "
                      f"({ledger['games']} games played)", flush=True)
                break

            # next generation: top half survives, children fill the rest
            survivors = [p for _, p in ranked[:max(2, a.pop // 2)]]
            children = []
            while len(survivors) + len(children) < a.pop:
                pa, pb = rng.sample(survivors, 2)
                children.append(strategy_bg.mutate(
                    strategy_bg.crossover(pa, pb, rng), rng))
            popn = survivors + children
    finally:
        if pool:
            pool.close()
            pool.join()


if __name__ == "__main__":
    main()
