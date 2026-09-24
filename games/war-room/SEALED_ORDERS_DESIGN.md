# War Room — sealed simultaneous orders: engine design note (bite 1, 2026-09-24)

Rulings this note obeys (the owner 2026-09-24): War Room is ISOLATED from the shared engine (no retest of the other games); BYO deferred (own board now, Fabian's VASSAL module later); Eastern Front 2-player first.
Source: rulebook 2nd ed 2025 update v27u (literature/war-room/rulebook_2nd_ed_v27u.txt). Page cites below are the rulebook's printed page numbers.

## 1. Isolation shape
- `engine/warroom.py` subclasses `GateGame`; `engine/gate.py` is NOT edited. All phase/seal logic lives in the subclass.
- `games/war-room/` = game.json, scenario `eastern-front.json`, `regions.json` (Fabian's region-space schema: locations + edges), validators.
- Own client page (`ui/warroom.html`, the SoJ precedent). `ui/index.html` never loads War Room.
- Server: one optional hook `view(side, state)` the base returns unchanged; War Room's strips the other seat's unrevealed sealed payloads from the state AND the log the client fetches. Other games byte-identical.
- Departure from plan step 1 ("general capability in the engine"): superseded by today's isolation ruling — sealed orders are War Room-local until a second game needs them.

## 2. Where the round is simultaneous vs sequential (rulebook p.7-23)
Round = 7 phases. Exactly TWO points are sealed; everything else is the existing alternating-seat model under a phase state machine.
| Phase | Step | Kind | Note |
|---|---|---|---|
| 1 Economy p.8 | flip cards, tally income | engine-automatic | reorganize (split/merge) = open per-seat action, any order |
| 2 Planning p.9 | Step 1 write orders + bid | **SEALED** | ≤9 orders (6 CHI/ITA), 1 per Command, dest may = origin; oil bid ≥0 (CHI must bid 0); splits/merges announced publicly before Step 2 |
| 2 | Step 2 reveal bids, pick slots | engine reveal, then sequential | descending bid, each nation picks ANY open Turn Order slot; ties = random flag draw (engine dice) |
| 2 | Step 3 pay oil | engine-automatic | all bids paid win or lose |
| 3 Movement p.11 | Step 1 flip hotspots | engine-automatic | |
| 3 | Step 2 resolve in Turn Order | sequential, reveal-on-turn | a nation's orders stay SECRET until its turn (p.11 "Until a Nation takes their turn, their written orders remain secret"); the active nation may CANCEL any order (whole order, never partial), chooses routes for 2-region naval/transport moves, forced pinning splits; illegal orders auto-cancel; only the FIRST order per Command executes |
| 3 | Step 3 carrier fighters | sequential | |
| 4 Combat p.14-19 | battles per hotspot | sequential sub-machine | stances, commanders, damage assignment, repairs = interactive; separate design (battle board) |
| 5 Refit p.20 | land air, deploy, reorganize | sequential in Turn Order | |
| 6 Morale p.21 | casualties→stress, medals | engine + sequential (medal submission) | |
| 7 Production p.22 | Step 2 note purchases | **SEALED** | secret purchases; trade Global-War only (not EF) |
| 7 | Step 3 reveal, update resources | engine reveal | Step 4 placement happens next round's Phase 5 |

## 3. State model
- `s.phase` ∈ econ / plan_seal / plan_pick / plan_pay / move / combat / refit / morale / prod_seal / prod_reveal; `s.active` = seat on turn, or `"all"` in a seal phase; `s.pending` = seats not yet committed; `s.turn_order` = list set in plan_pick; `s.sealed = {seat: payload}`.
- Seal action: `{"type":"seal","orders":[{"cmd":id,"dest":region}],"bid":n}` (plan) / `{"type":"seal","buy":{unit:n}}` (prod). Legal iff phase is a seal phase and the seat has not committed. Stored in `s.sealed[seat]`, NOT applied.
- Last commit auto-advances (engine-originated log events): `reveal_bids` → ties rolled with `roll_die` → phase plan_pick with active = top bidder; pick actions are ordinary sequential submits; then plan_pay (automatic) → move with active = turn_order[0].
- Reveal-on-turn: when a seat becomes active in `move`, the engine logs `reveal_orders` with its payload; from then the view hook shows it. Order resolution = sequential submits `{"type":"execute"|"cancel", "order":i, "route":[...]}` walking the O&P rows in order (p.11: left to right, row 1 to 3), gate enforcing "as written or cancelled".
- Hashing: `s.sealed` is inside HASH_KEYS (opaque digest, leaks nothing). The log entry for a seal carries the full payload so `verify_game.py` replays unchanged; secrecy is a VIEW property (hook §1), not a log property. Trade-off accepted for v1: a hot-seat human could read the raw log file on disk; the two-humans-one-screen case is honour-system exactly as the paper game is. Commitment hashes (log sha at seal, payload at reveal) are a later upgrade if PBM needs it; the verifier would then need the payload from the reveal entry.
- Undo: a seat may undo its own seal while `s.pending` still contains the other seat (delete `s.sealed[seat]`, re-add to pending). After the reveal event no undo crosses the boundary.
- AI seat: the AI produces a seal payload through the same door; it runs inside the engine so nothing leaks. Basic AI for EF = random legal orders (bite later).
- Dice: engine-owned d12 pool (p.16) added to the subclass (`roll_d12`), counted on the same seeded stream as `roll_die`.

## 4. Eastern Front scenario facts to encode (p.30)
- Seats: SOVIET UNION, GERMANY (Italy absent). 9 orders each. Win: control both capitals (g1 Greater Germany, r1 Moscow — TTS ids) at end of Morale, else play to Collapse (p.23). Morale Board side "Eastern Front".
- Board subset (TTS `scenarios` exclusion flags, extracted 2026-09-24): 33 regions in play = a3 a4 a5 a6 g1 g4 g5 g6 g7 g8 g9 m4 m6 n10 n13 n14 r1-r17 (r1..r17). Only sea regions adjacent to in-play territories enterable, Pacific + Mediterranean excluded; Germany always controls the Danish Straits (A-5/A-6 passage). Neutrals in play: Sweden, Switzerland, Turkey. USSR all cards except Soviet Sakhalin; Germany 7 cards (Greater Germany, Poland-Slovakia-Hungary, Bulgaria-Rumania, Ukraine, Belarus, Baltic States, Finland).
- Stress thresholds for EF are image-only in the PDF: two agreeing fan sources (GER 6/6, USSR 6/5) — cite as "graphic, confirmed by 2 sources" or read off the page render before the gate ships.

## 5. Proof plan (before any War Room rule beyond movement)
1. `games/war-room/validate_sealed.py`: two seats, seal → last-seal auto-reveal → pick → move with reveal-on-turn, cancel + execute paths; replay through `verify_game.py` with exact hash match; view hook proven to strip the uncommitted seat's payload.
2. Full suite `run_all.py --fast` + Arnhem baseline sha unchanged = proof nothing shared moved.
3. Then coverage matrix per phase, source-defect register, credits (Larry Harris; Thomas Gale; Kevin Chapman; Nightingale Games).

## 6. Bite sequence
1. (this bite) design note + board-data diff (TTS vs warroom-app vs rulebook p.5) → disagreement worksheet for the owner/publisher.
2. regions.json for the EF subset + schematic board render + warroom.py skeleton with the seal/pick/move machine + validate_sealed.
3. Movement rules gate (adjacency, rail, pinning, passages, cancel/illegal).
4. Combat sub-machine (battle board), then refit/morale/production.
