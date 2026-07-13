# Play-by-Mail: AI-vs-AI match protocol

A repeatable harness for head-to-head matches between two (or more) AI
commanders — any mix of Claude Code sessions, Codex/GPT CLI agents, or
other terminal agents that can read/write files. Proven in the
Fable-5-vs-Opus-4.8 Chickamauga match (2026-07-13).

## Roles
- **Overseer** (the human): kicks off each general's turn ("Your turn —
  go"), may discuss the game with anyone at any time, makes all direction
  calls. Never carries one general's private reasoning to the other.
- **Judge / Orchestrator** (a dedicated Claude Code session, in this repo):
  owns the engine live dir, runs `engine/session_match.py`, ferries files
  between the live dir and the mailboxes, enforces anti-cheat, logs
  receipts. NEVER writes or suggests a plan for either side.
- **Generals** (one terminal session per side, separate tabs/windows):
  read their own mailbox, think, file plan JSONs. Any agent that can read
  files (including PNG images) and write files qualifies — verified for
  Claude Code and OpenAI Codex CLI (≥0.144, `codex` on PATH, ChatGPT
  subscription login; smoke-test: have it read a fake briefing and write
  the plan JSON, and confirm it can describe a PNG's contents).

## Directory layout (per match)
```
comms_<match>\
  judge_log.md                 receipts + confidence track (judge-owned)
  <generalA>\
    COMMANDER.md               standing orders (from template, see below)
    journal.md                 war journal (general-owned, confidential)
    inbox\                     judge drops briefing_gt<N>_<side>.txt,
                               map_gt<N>.png, REJECTED_gt<N>.txt
    outbox\                    general writes plan_gt<N>_<side>.json
  <generalB>\ (same shape)
runs\<match>\                  engine live dir — JUDGE ONLY (holds both
                               sides' secrets: plans, orders sidecars)
```
Template for COMMANDER.md: `pbm_templates/COMMANDER_TEMPLATE.md`.
Overseer quick-reference: `pbm_templates/README_OVERSEER_TEMPLATE.txt`.

## The knowledge package (THE hard-won lesson — never skip)
Each general gets, in COMMANDER.md, the COMPLETE game exactly as a human
owner would, or the match is invalid:
1. The game directory (`games/<game>/`): rules transcription, game.json
   (all encoded rules w/ citations, CRT/odds tables, VP schedule),
   terrain.json (every hex, every hexside, roads, creeks), scenario file
   (setup + full reinforcement schedule).
2. The printed originals (`literature/<family>/` — local only).
3. The playbook (`games/<game>/playbook/`) if one exists: doctrine,
   champion genome, corpus. Max-knowledge rule: the champion advisor
   stays ON in briefings for both sides.
4. A rendered map image of the current board EVERY TURN
   (`map_gt<N>.png` via `engine/render_movie.py --stills`, deliver the
   latest boundary still).
5. Their own training knowledge + open-web research whenever THEY judge
   their information incomplete.
First attempt at this match gave coordinates-only briefings — the general
immediately (and rightly) complained he was commanding through a keyhole.
Match was restarted once the full package was granted.

## Required plan fields (Overseer's standing orders, 2026-07-13)
Every plan JSON must carry, top-level:
- `commentary` — 2-4 sentences: intent + advisor verdict.
- `confidence` — low|medium|high + one clause why.
- `win_percent` — integer 0-100, the general's honest own-win probability
  (tracked per turn in judge_log.md; calibration is part of the
  post-game scorecard).
- `orders` — the plan-DSL orders (push/hold/standoff/run_exit).
Extra top-level fields are ignored by the compiler (session_match.py reads
only `orders` + `commentary`), so the report fields ride in the same file
and the judge harvests them from the mailbox copy.

## War journal (Overseer's order)
Each general appends a dated entry to their own `journal.md` after every
turn: situation read, options considered, why the plan, fears and
expectations. Confidential until game end — the opponent never sees it and
the JUDGE DOES NOT READ IT until the game is over (keeps the referee
unbiased and the journal honest). Published alongside the moves.

## Anti-cheat (all technically-unenforceable rules are honor + audit)
- Generals read ONLY: own mailbox, game dir, literature dir, open web.
  Write ONLY: own outbox + own journal.md. The live dir and the enemy
  mailbox are forbidden — the live dir holds both sides' commentary.
- Commentary/journals sealed from the opponent until game end.
- Generals must NOT save match info to auto-memory/MEMORY.md (two Claude
  generals in the same project share a memory directory — this is the one
  real cross-contamination channel; the sessions themselves are isolated).
- Judge NEVER authors/edits plans; plans are copied BYTE-FOR-BYTE into
  the live dir. Every file transferred (both directions) gets a SHA-256
  receipt in judge_log.md at the moment of transfer. Post-game, anyone
  can diff mailbox files vs live-dir files vs the compiled actions in the
  verified JSONL log.
- Seed announced by the judge at match start, before any plan.

## Judge per-turn loop
1. Watcher (persistent Monitor polling both outboxes for new/updated
   *.json) fires on a filed plan.
2. Read the plan. Reject (REJECTED_gt<N>.txt into that general's inbox,
   explain, request overwrite) if: malformed JSON, orders enemy/wrong-side
   units, or missing required fields. Bounces are administrative — orders
   already judged valid stay valid on resubmission.
3. SHA-256 receipt → judge_log.md. Byte-copy plan → live dir.
4. Re-run the driver:
   `python engine/session_match.py --game games/<game> --live runs/<match>
    --a <nameA>=<SideA> --b <nameB>=<SideB> --seed <seed>`
   Exit 2 = turn compiled, next briefing printed + written to live dir.
   Exit 3 = compile-check rejection → bounce per step 2.
   Gate rejections DURING a turn (n rejected in the driver's summary
   line) are normal — illegal proposals logged + provably inert.
5. Render the new boundary still (`render_movie.py --stills`), copy the
   latest PNG to the next general's inbox as map_gt<N>.png, copy the new
   briefing beside it, receipt both.
6. Harvest confidence/win_percent into judge_log.md's track table.
7. Tell the Overseer who is up. Repeat until the driver reports game end.

## Restart procedure (e.g. after a fairness defect)
Void the receipts (keep them in judge_log under a "voided" heading — the
audit trail survives), wipe the live dir, clear all inbox/outbox files,
re-init with the SAME announced seed, redeliver GT1 briefing + map. Same
seed ⇒ byte-identical opening briefing (determinism check: hash matches).

## Post-game deliverables
1. `engine/verify_game.py` the log (must PASS before anything is claimed).
2. `engine/grade_commander.py --live runs/<match>` — structural metrics +
   blind rubric + 0-1000 thinking score per move (judge can hand-grade
   blind with the same rubric if no API key).
3. `engine/render_movie.py` stills + full movie with
   `--label "Side=Commander"` per side → Desktop folder + explorer open.
4. Corpus-uniqueness curve: scratchpad script replays all stored logs and
   compares positions per boundary (fraction of units on identical hexes,
   nearest prior game, first boundary with no exact match). Pattern:
   replay via BlueGrayGame + submit(), snapshot at (turn, side) changes.
5. Confidence-calibration chart: each side's win_percent per turn vs the
   final result. 6. Publish package: verified log + commentary sidecars +
   war journals + confidence track + thinking scores + stills/movie.

## Stamping out a new match (checklist)
1. Pick game, sides, seed; name the match (`<date>_<A>_vs_<B>`).
2. `mkdir comms_<match>\{A,B}\{inbox,outbox}`; fill COMMANDER.md ×2 from
   the template (name, side, opponent, paths, filenames).
3. judge_log.md header (seed, sides, integrity rule).
4. Init the driver once (exit 2) → deliver GT1 briefing + setup still to
   the first mover's inbox with receipts.
5. Arm the outbox watcher (Monitor, persistent).
6. Give the Overseer the two kickoff lines (from README template) and the
   smoke-test result for any non-Claude agent.
