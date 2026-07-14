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

## Naive vs. veteran commanders (Overseer's designation, 2026-07-14)
Every commander ALWAYS gets the complete knowledge package above — the
designation controls only exposure to MATCH HISTORY on top of it:
- **NAIVE** — has never played and gets no prior-match archive. Full
  library, zero games.
- **VETERAN** — additionally receives their own accumulated match record
  (their prior games' logs, journals, judge logs, grades).
Standing rule: a general who WINS a match keeps that match in their
record and enters future matches as a veteran of it. The designation of
each commander is declared in the judge log before the first plan.
(First use: 2026-07-14 Opus-vs-GPT-5.6 — both commanders naive by the
Overseer's ruling, GPT compensated instead with the stronger seat.)

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

## Fully-autonomous mode (the YOUR_TURN signal contract)
The Overseer's relay can be removed entirely: generals run a cheap shell
wait-loop between turns (pattern is in COMMANDER_TEMPLATE.md) watching
their inbox for `YOUR_TURN.txt`; the judge is the only writer of that
file. Contract:
- Judge writes `inbox\YOUR_TURN.txt` (naming the briefing) when a general
  is up; deletes it when the plan is TAKEN; re-creates it pointing at
  REJECTED_gt<N>.txt on a bounce; writes `inbox\GAME_OVER.txt` to both
  mailboxes (with the result) when the driver reports game end — the
  generals' loops exit on it.
- The disappear-then-reappear sequence is the general's resubmission
  signal; generals never delete signal files.
- Overseer's role shrinks to: paste ONE autonomy kickoff prompt per
  terminal, then watch (and chat with anyone at will).

## Judge per-turn loop
1. Watcher (persistent Monitor polling both outboxes for new/updated
   *.json) fires on a filed plan.
2. Read the plan; delete that general's YOUR_TURN.txt (the plan is
   TAKEN). Reject (REJECTED_gt<N>.txt into that general's inbox +
   re-create YOUR_TURN.txt pointing at it) if: malformed JSON, orders
   enemy/wrong-side units, or missing required fields. Bounces are
   administrative — orders already judged valid stay valid on
   resubmission.
3. SHA-256 receipt → judge_log.md. Byte-copy plan → live dir.
4. Re-run the driver:
   `python engine/session_match.py --game games/<game> --live runs/<match>
    --a <nameA>=<SideA> --b <nameB>=<SideB> --seed <seed>`
   Exit 2 = turn compiled, next briefing printed + written to live dir.
   Exit 3 = compile-check rejection → bounce per step 2.
   Gate rejections DURING a turn (n rejected in the driver's summary
   line) are normal — illegal proposals logged + provably inert.
5. Render the new boundary still (`render_movie.py --stills`) and copy it
   to the next general's inbox as map_gt<N>.png — select the still by
   NAME PATTERN (`*gt<N>_<side>_done.png`), not by index (stale files
   from prior renders accumulate in the stills dir). Copy the new
   briefing beside it, receipt both.
6. Harvest confidence/win_percent into judge_log.md's track table.
7. Write YOUR_TURN.txt into the next general's inbox (autonomous mode)
   and/or tell the Overseer who is up. Repeat until the driver reports
   game end, then write GAME_OVER.txt (with the result + VP) to BOTH
   inboxes and notify the Overseer.

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

## Lessons from the first series (Fable-vs-Opus, 2026-07-13) — v2 items
- Briefings MUST carry a per-side exited-units tally: exit VP scores at the
  end, so the running VP counter silently hides exits — this directly
  caused a decisive misread ("he did not exit" while 24 CSP were off-board).
- The compiler's per-mover >=1-1 odds guard makes 2-unit garrisons
  unassaultable; artillery bombardment is the only eviction tool. DSL v2:
  assault verb (declared multi-unit contact), entry hold-back verb.
- Renderer news captions can state raw CRT results that rules then void
  (bombardier immunity) — captions should reflect applied results only.
- Retreat-into-EZOC-lock is the deadliest interface edge: the guard stops
  units walking into hopeless adjacency but not being STRANDED in it by a
  retreat (mandatory combat then forces the suicide attack).
- Full archive pattern: matches/<match>/ = series report + judge logs +
  scorecards + journals + verified logs (gitignored; publication per-match).

## Reproducibility & copyright — BYO, stated plainly
Everything the harness itself needs is public in this repo: the engine,
this protocol, the templates, and our own derived encodings
(game.json / terrain.json / rules_transcription.json / scenarios). What is
NOT ours and never ships: the published game's map/counter art, rulebook
scans/PDFs, and VASSAL module contents (`literature/`, module art, and
`comms_*/` mailboxes are all gitignored). To REPRODUCE a match someone
needs their own copy of the game's resources:
1. Own the printed game and/or download its module from vassalengine.org
   (BYO principle — see ENCODING_GUIDE.md).
2. Place rulebook material under `literature/<family>/` and extracted
   module art where the renderer looks for it (it says at startup which
   path it used); WITHOUT module art the renderer automatically falls
   back to `--schematic`, which is fully self-contained.
3. Everything else (logs, seeds, briefings, judge receipts) regenerates
   deterministically from the public engine + the match log.
PUBLISHING a match story: module-art renders are for the players'/owner's
private use during the match. Anything published (stills, movie, posts)
uses `--schematic` renders unless rights to the art are cleared —
schematic output contains zero copyrighted material by construction.

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

---

# Play-by-Mail v1: HUMAN vs AI General by email (shipped 2026-07-14)

The tester-facing mode (spec #19): a person plays one side in this app,
the AI General plays the other, and the two exchange ONE small .json turn
file per player turn as a plain email attachment. Nothing else travels.

## The turn file (`vsav-pbm/1`, engine/pbm.py)
Self-contained JSON: game slug, mode, scenario, match id, seq counter,
side->player mapping, and the COMPLETE JSONL log from game start (init
entry = scenario + seed + every starting position; every action entry =
proposal, verdict, dice, state hash). The log IS the game.

## Trust model
Every received file is replayed move-by-move through a fresh engine
(verify_game semantics) before it is accepted: every verdict, every die,
every state hash must reproduce, and the file must EXTEND the game already
on disk (stale or forked files bounce). A file built by this app can only
contain legal moves — the gate is the only door — so a rejection means
tampering, corruption, or a version mismatch, and the sender is told to
redo the turn from their last good position. Dice are engine-owned and in
the log: both sides can audit every roll of the whole game at any time.

## Protocol
1. Tester: ✉ Mail panel -> start a match, pick a side (or import the
   opening file someone sent them). Play the turn; End player turn;
   Export; email the downloaded file to the AI General's address.
2. Our side: `python engine\pbm_respond.py incoming.json -o reply.json`
   — verifies, plays the AI's whole player turn through the gate, writes
   the reply (or a `vsav-pbm-reject/1` doc naming the exact failure).
   Email reply.json back.
3. Tester: ✉ Mail -> Import reply file — the app re-verifies, shows what
   the AI played, and hands them the turn. Repeat to game end.

Whoever's player turn it is also executes the opponent's forced responses
that arise inside it (retreat routing, exchange picks, FPF) — the same
protocol the AI follows during its turn. Mid-turn decision handshakes are
a possible v2 refinement.

Scope: strategic-family games (Afrika Korps, Blue & Gray Chickamauga,
Westwall Arnhem — every current Tier-3 strategic game inherits it).
Tactical family needs its own exchange grain (alternating fire) — later.
Validated end-to-end by games/blue-and-gray-chickamauga/validate_pbm.py.
