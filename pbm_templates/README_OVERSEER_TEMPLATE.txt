{{MATCH_TITLE}} — play-by-mail. Your only job: tell each general when to move.

FIRST TIME in each terminal, paste the matching line:

  General {{A_NAME}} terminal:
    You are General {{A_NAME}}, commanding the {{A_SIDE}} army in a head-to-head wargame match against an AI opponent. Read {{COMMS_ROOT}}\{{A_MAILBOX}}\COMMANDER.md and follow it exactly — it defines your knowledge sources (the complete game: rulebook, map data, odds tables, reinforcement schedule, playbook, and internet research when you judge you need it), your mailbox, and how to file plans. Study your materials, then check your inbox: your first briefing and a map image are waiting. Your turn - go.

  General {{B_NAME}} terminal:
    (same text with {{B_NAME}}/{{B_SIDE}}/{{B_MAILBOX}})

EVERY TURN AFTER THAT, just type in whichever terminal the judge says is up:
    Your turn - go.

The judge watches the mailboxes automatically: when a general files a
plan, the judge runs the engine and drops the next briefing + current map
image in the right inbox, then tells you who is up next.

You can chat with all three models at any time. The generals may not read
each other's mailboxes or the judge's match directory; the judge logs a
SHA-256 receipt of every file transferred so nobody — including the judge —
can tamper unnoticed. Each general keeps a private war journal, published
after the match.
