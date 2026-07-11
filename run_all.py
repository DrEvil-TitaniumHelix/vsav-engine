#!/usr/bin/env python3
"""run_all.py - one command to run the whole engine test suite.

Discovers and runs every game's validate_*.py, reports one PASS/FAIL summary,
and exits non-zero if anything failed. This is the single entry point CI uses
(`python run_all.py`) and the one you run locally before a commit.

Two kinds of validator:
  * self-contained - runs from a clean checkout using only in-repo game data
    (games/<name>/) and the stdlib-only engine. These run everywhere.
  * needs-local-material - cross-checks against the private decode/ingest
    material under ../VassalIngest (rulebook PDFs, module extracts) that is
    NOT in the public repo. These SKIP cleanly when that material is absent
    (e.g. in CI), exactly like the emulator's fixture-gated tests.

A SKIP never fails the run; only a real FAIL (or timeout/crash) does.

Usage:
  python run_all.py            # everything (validators are the whole suite)
  python run_all.py --fast     # skip the slow multi-seed AI campaigns
  python run_all.py --game westwall-arnhem   # one game only
"""
import argparse
import os
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.abspath(__file__))
GAMES_DIR = os.path.join(REPO, "games")
# The private decode material lives beside the repo, not inside it.
# Overridable via env so CI (and this repo's own smoke test) can point it at a
# missing path to exercise the clean-skip behaviour.
INGEST_ROOT = os.environ.get(
    "VASSAL_INGEST_ROOT",
    os.path.normpath(os.path.join(REPO, "..", "VassalIngest")),
)
PER_VALIDATOR_TIMEOUT = 900  # seconds; the 5-seed AI campaigns are the long pole

GREEN, RED, YELLOW, DIM, RESET = (
    "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
)


def needs_local_material(src_path):
    """True if the validator cross-checks against ../VassalIngest material."""
    with open(src_path, "r", encoding="utf-8", errors="replace") as fh:
        src = fh.read()
    return "VassalIngest" in src or "extracted" in src


def discover(one_game=None, fast=False):
    """Yield (game, validator_path) for every validator to consider."""
    for game in sorted(os.listdir(GAMES_DIR)):
        if one_game and game != one_game:
            continue
        gdir = os.path.join(GAMES_DIR, game)
        if not os.path.isdir(gdir):
            continue
        for fn in sorted(os.listdir(gdir)):
            if not (fn.startswith("validate_") and fn.endswith(".py")):
                continue
            if fast and fn == "validate_ai.py":
                continue
            yield game, os.path.join(gdir, fn)


def run_one(path, extra_args=None):
    """Run a validator. Returns (status, seconds, tail) where status is one of
    PASS / FAIL / SKIP."""
    if needs_local_material(path) and not os.path.isdir(INGEST_ROOT):
        return "SKIP", 0.0, "needs ../VassalIngest decode material (absent)"
    start = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, path] + (extra_args or []),
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=PER_VALIDATOR_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return "FAIL", time.time() - start, f"TIMEOUT after {PER_VALIDATOR_TIMEOUT}s"
    secs = time.time() - start
    if proc.returncode == 0:
        return "PASS", secs, ""
    tail = (proc.stdout + proc.stderr).strip().splitlines()
    tail = tail[-1] if tail else f"exit {proc.returncode}"
    return "FAIL", secs, tail


def main():
    ap = argparse.ArgumentParser(description="Run the whole engine test suite.")
    ap.add_argument("--fast", action="store_true",
                    help="skip the slow multi-seed AI campaigns")
    ap.add_argument("--ai-smoke", action="store_true",
                    help="run validate_ai in --smoke mode (1 seed, short game) "
                         "instead of the full 5-seed soak; also enabled by the "
                         "VASSAL_AI_SMOKE env var. Used by CI.")
    ap.add_argument("--game", default=None,
                    help="run only this game's validators (folder name)")
    args = ap.parse_args()
    ai_smoke = args.ai_smoke or bool(os.environ.get("VASSAL_AI_SMOKE"))

    validators = list(discover(args.game, args.fast))
    if not validators:
        print("no validators found", file=sys.stderr)
        return 2

    color = sys.stdout.isatty()
    def c(code, s):
        return f"{code}{s}{RESET}" if color else s

    print(f"Running {len(validators)} validators "
          f"(engine is stdlib-only; suite = the validators)\n")
    if not os.path.isdir(INGEST_ROOT):
        print(c(DIM, f"note: {INGEST_ROOT} absent - ingest cross-checks will "
                     f"skip (expected in CI)\n"))

    counts = {"PASS": 0, "FAIL": 0, "SKIP": 0}
    failures = []
    cur_game = None
    for game, path in validators:
        if game != cur_game:
            print(c(DIM, f"{game}"))
            cur_game = game
        name = os.path.basename(path)
        extra = ["--smoke"] if (ai_smoke and name == "validate_ai.py") else None
        status, secs, tail = run_one(path, extra)
        if extra and status != "SKIP":
            name += " (smoke)"
        counts[status] += 1
        mark = {"PASS": c(GREEN, "PASS"), "FAIL": c(RED, "FAIL"),
                "SKIP": c(YELLOW, "SKIP")}[status]
        timing = f"{secs:5.1f}s" if secs else "     -"
        line = f"  {mark}  {name:<24} {timing}"
        if tail:
            line += f"  {c(DIM, tail[:80])}"
        print(line)
        if status == "FAIL":
            failures.append((game, name, tail))

    print(f"\n{'='*60}")
    summary = (f"{counts['PASS']} passed, {counts['SKIP']} skipped, "
               f"{counts['FAIL']} failed")
    if counts["FAIL"]:
        print(c(RED, f"FAILED - {summary}"))
        for game, name, tail in failures:
            print(c(RED, f"  x {game}/{name}: {tail}"))
        return 1
    print(c(GREEN, f"ALL GREEN - {summary}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
