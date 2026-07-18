# SALVO — the VALOR match protocol

**SALVO** is how an outside AI (your LLM — Claude Code, Codex, any agent that
can read and write files) takes a seat in a VALOR game. The whole protocol is
two files in one folder: the game writes `packet.json`, your agent writes
`move.json`. Everything else — legality, dice, logging, replay — stays inside
the VALOR engine, where neither side can cheat.

SALVO powers two of VALOR's four play modes:

| Mode | Seats | Transport |
|---|---|---|
| 1 | You vs the built-in AI | none — one browser |
| **2** | **Your LLM vs the built-in AI** | **the SALVO folder** |
| **3** | **Your LLM vs DrEvil's champion AI, remote** | **SALVO folder + mailed turn files** |
| 4 | You vs another person | mailed turn files (play by mail) |

Mode 2 is the training ground: everything happens on your machine, and your
agent learns the loop with nothing at stake. Mode 3 is the challenge: same
folder, same packets — the only new step is that finished turns travel by
email (the play-by-mail turn file, unchanged) to the remote opponent.

## Why cheating is impossible (for both of us)

Every action your agent submits goes through the legality gate — the engine's
only door. Illegal proposals are rejected with the rulebook citation and
logged. Dice are engine-owned, seeded, and logged. The complete game is an
append-only JSONL log that `engine/verify_game.py` replays byte-exactly:
every verdict, every die, every state hash. Either side can verify the whole
match from the log alone. Your AI cannot cheat; neither can ours.

## The match folder

You pick a folder when the match starts (Chrome asks for permission — the
page can only touch that one folder). The game maintains:

```
<your match folder>/
  salvo.json         match card: game, scenario, match id, who sits where
  packet.json        the CURRENT packet — the one file your agent reads
  move.json          your agent's answer — the one file your agent writes
  log.jsonl          the complete engine log so far (the durable game record)
  history/           every packet and consumed move, numbered, append-only
```

`packet.json` and `move.json` are always the *live* pair; `history/` is the
audit trail. `log.jsonl` is rewritten after every accepted action — if your
browser ever loses the game, the folder still holds everything needed to
reconstruct it move by move.

## The loop (your agent's whole job)

1. Read `packet.json`. If its `n` is one you already answered, wait and
   re-read (poll every couple of seconds).
2. If `kind` is `"decision"` or `"rejection"`: decide, then write `move.json`.
3. If `kind` is `"wait"`: not your decision — keep polling.
4. If `kind` is `"over"`: the game is finished. Stop.

Every packet is **self-contained**: full situation briefing, your side, the
phase, what kind of actions are required, and a digest of everything that
happened since your last packet. Your agent needs no memory of earlier
packets — a fresh context can pick up the game from the current packet alone.

### Decision packet (`kind: "decision"`)

```json
{
  "format": "salvo-packet/1",
  "kind": "decision",
  "n": 17,
  "match_id": "a1b2c3d4e5f6",
  "game": "blue-and-gray-chickamauga",
  "you": "Confederate",
  "turn": 3, "of": 12, "phase": "movement",
  "require": "one or more gate actions for Confederate (movement phase)",
  "actions_allowed": ["move", "reinforce", "exit", "end_movement"],
  "briefing": "GAME TURN 3 of 12 ... (full text situation report)",
  "units": [ {"pid": "...", "side": "...", "hex": "0512", "strength": 4,
              "ma": 4, "class": "infantry", "moved": false}, ... ],
  "vp": {"Union": 10, "Confederate": 5},
  "since": ["n201 Union moved 20/IX 0810->0709", "n202 BATTLE 3:1 -> DR ..."],
  "schema_note": "action formats: see your challenger payload, section ACTIONS"
}
```

### Your move file

```json
{
  "format": "salvo-move/1",
  "n": 17,
  "actions": [
    {"type": "move", "unit": "csa_hood_1", "dest": [7, 9]},
    {"type": "end_movement"}
  ],
  "commentary": "optional: why (archived with the match record)"
}
```

- `n` **must equal** the packet's `n` — anything else is ignored (stale
  answer). Overwrite `move.json` in place.
- `actions` is a list of **one or more** gate actions, applied in order.
  Granularity is yours: one action per packet (safest — you see the result
  of each die before the next decision) or a whole phase at once.
- Actions are applied until the first rejection. **Accepted actions stand**
  (they were legal — a human at the table gets no take-backs either) and
  processing stops at the rejected one.

### Rejection packet (`kind: "rejection"`)

Assume every submission will be rejected; acceptance just means the next
packet asks for the next decision. A rejection packet is a decision packet
plus the verdict on what you sent:

```json
{
  "kind": "rejection", "n": 18,
  "rejected": {
    "your_move_n": 17,
    "accepted": 1,
    "failed_action": {"type": "move", "unit": "csa_hood_1", "dest": [1, 1]},
    "reasons": ["destination is 9 MP away, unit has 4 MA [5.1]"]
  },
  ... full decision packet fields follow ...
}
```

The reasons carry rulebook citations — the gate teaches your agent the rules
one rejection at a time. Fix the action (or choose another) and answer the
new `n`.

### Pending decisions land on the right seat

Some decisions belong to you *during the opponent's turn* — choosing a
retreat route, an advance after combat, an exchange loss. Whenever the game
is waiting on **your** side, a decision packet appears; when it waits on the
opponent, you get `"wait"`. Your agent never needs to know the turn
structure — if a packet asks, answer it.

## Resume — shut down anytime

The game state lives in your browser (saved automatically) and the complete
log lives in the match folder. Close the tab, shut the machine down, come
back in a week: reopen the game, re-pick the same match folder when asked,
and play continues from the exact position — turn 13 stays turn 13. Your
agent's context does not matter (packets are self-contained); your browser's
save does not matter either as long as the folder survives, because
`log.jsonl` replays into the identical position through the same engine that
produced it.

## Mode 3 — the remote challenge

Identical from your agent's point of view: same folder, same packets, same
move files. The differences are around it:

- Your opponent's side is played remotely (DrEvil's trained champion AI).
  When your player turn is complete, the game exports a **turn file** — the
  standard VALOR play-by-mail document, the complete verified log — and you
  email it. The reply file, imported, becomes your opponent's turn on your
  board, and your next packet appears in the folder.
- Both ends replay the full log on every exchange. A tampered file names the
  exact entry that fails; there is no trust involved, only verification.

## Versioning

`salvo-packet/1`, `salvo-move/1`. Fields may be added within a version;
nothing existing will be renamed or removed. Games covered by v1: the
strategic hex-and-counter family (Blue & Gray: Chickamauga, Westwall:
Arnhem, Afrika Korps). The Napoleonic command family (Austerlitz) follows —
same folder, same loop, finer-grained packets (its decisions interleave
between the sides, which is exactly what per-decision packets are for).
