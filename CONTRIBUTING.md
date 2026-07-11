# Contributing

Thanks for your interest. This engine encodes printed wargames *whole* — map,
counters, rules, combat tables — behind one deterministic legality gate. The bar
for anything that enforces a rule is high on purpose; the notes below are how to
clear it.

## Ground rules

1. **Never ship a wrong rules engine.** A rule is only enforced where it's been
   validated against worked examples, an independent source, or expert review.
   If a table can't be validated, the game stays at a lower tier with that rule
   unenforced. A wrong gate is worse than no gate.
2. **Every encoded rule cites its source.** Rulebook section/page references live
   in the game's `game.json` alongside the rule, the way the existing games do.
   Original-game defects found while encoding go in `source_defects` with quoted
   evidence, the enforced resolution, and that resolution's authority.
3. **Zero VASSAL code.** Reading VASSAL's file formats and documented behavior is
   fine; copying VASSAL source into this repo is not. This engine is
   file-format-compatible with VASSAL, not derived from it.
4. **No copyrighted game content in the repo.** No rulebook scans, PDFs, or
   unused module art. Games are brought by the user from vassalengine.org.

## Adding a game

Start with **`ENCODING_GUIDE.md`** — it walks the full pipeline (grid geometry
from the module `buildFile`, counters from PieceSlots, terrain, the rules layer
as `game.json` plus one procedure module, the validators, and the tier system).
`games/afrika-korps-classic-ah/` is the worked reference: `game.json`,
`terrain.json`, a scenario file, the `validate_*.py` evidence chain, and
`VALIDATION.md`.

A game earns a tier only when its validators are green and its `VALIDATION.md`
documents the evidence. That's the contract between "it runs" and "it's correct."

## Running the tests

```
python run_all.py          # the whole suite, one PASS/FAIL summary
python run_all.py --fast    # skip the slow multi-seed AI campaigns
python run_all.py --game <folder>   # one game only
```

The engine is stdlib-only — no install step. Validators that cross-check against
private decode material not in this repo skip cleanly when it's absent. CI runs
`python run_all.py` on every push (Python 3.10 and 3.12); keep it green.

## Pull requests

- Keep changes to shared engine code behind existing spec/config switches so
  older games stay byte-for-byte identical — run `run_all.py` before and after.
- New enforcement comes with its validator and a `VALIDATION.md` note.
- One concept per change; match the style of the code around you.
