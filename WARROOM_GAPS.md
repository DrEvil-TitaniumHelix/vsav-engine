# War Room — engine gaps vs VALOR today

**Status: roadmap / gap register (not a build plan).**
**North star:** encode *War Room: A Larry Harris Game* (Nightingale Games) behind the same legality gate as the shipped hex games.
**Audience:** co-developers expanding the engine — not testers.

Related: `ENCODING_GUIDE.md` (pre-screen + iron rule), `LIBRARY_CENSUS.md` (area maps as the biggest unlock), `SCORECARD.md` (named-region ingest failures), `AREA_MAP_DESIGN.md` (first engine expansion, specified for implementation).

---

## What War Room needs

War Room is a 2–6 player WWII strategic game on a **round area map** of named territories. Core loop (seven phases):

1. Direct National Economy — income from controlled territories (oil / iron / OSR).
2. Strategic Planning — **secret simultaneous** movement orders + oil bid for turn order; ally discussion allowed.
3. Movement Operations — resolve written orders; command stacks (≤8 units) move across the map.
4. Combat Operations — units leave the map onto a **Battle Status Board**; choose **stances** per unit type; air battle then surface; custom d12s; Force Advantage; repair survivors.
5. Refit & Deploy — land planes; reorganize stacks; place newly built units.
6. Morale & Stress — cancel stress with medals / civilian goods; Homeland Status Wheel penalties.
7. Production — **secret simultaneous** builds with multi-resource costs and delayed delivery; optional neutral trade; strategic bombing of builds.

Scenarios include full world war and smaller theaters (Eastern Front, Pacific, North Africa). Digital reference exists on Tabletopia / TTS / third-party apps; **there is no VASSAL `.vmod`** on vassalengine.org as of this writing.

---

## Gap register

Each row is an **engine capability** War Room requires. Per `ENCODING_GUIDE.md`, these are future engine expansions, not per-game hacks. Priority is for the War Room path; many rows also unlock large library cohorts.

| # | Gap | Why War Room needs it | Engine today | Library payoff | Priority |
|---|---|---|---|---|---|
| G1 | **Area / territory map + playable UI** (+ VASSAL region-space file compat) | World map is named territories + adjacency; humans must verify snaps/moves on the real map; VASSAL modules already ship `RegionGrid` — we must consume it | **Implemented** (`AREA_MAP_DESIGN.md`): `space.kind=region`, ingest→`regions.json`, board/UI Tier-0, `.vsav` mirror at origins. Pilot A House Divided PARTIAL (sample edges). Hex games unchanged. | ~417 point-to-point + area games become **Tier-0 playable** in-browser once edges exist | **Done (engine)** — remaining work is per-game edge graphs + War Room content (G9) |
| G2 | **Sealed / simultaneous orders + planning UI** | Movement + production written secretly, then revealed; O&P / order-sheet UX | Alternating IGOUGO seats; state fully visible; no commit/reveal UI | Diplomacy-family, many CDGs with simultaneous planning | P1 |
| G3 | **N-seat model (2–6 nations)** | Six powers + alliances; oil bid for order | Two-side `side_order` / `enemy()`; match harnesses assume 2 | Multi-power strategic titles | P1 |
| G4 | **Battle-board combat flavor** (+ battle-board UI) | Separate combat board, stances, air-then-surface, custom d12, Force Advantage | Odds CRT (AK/B&G/Arnhem) or Tobruk to-hit/damage | Other stance / battle-board systems | P2 |
| G5 | **Air + naval as domains** | Land / sea / air units with distinct movement and combat roles | Explicit knockout in `ENCODING_GUIDE` + `rules_screen.py` (`air`, `naval`) | Large WWII strategic cohort | P2 |
| G6 | **Multi-resource economy + delayed production** | Oil / iron / OSR income, spend mixes, builds arrive later, trade | AK-style supply / replacements / arrivals only | Third Reich–class economy games | P2 |
| G7 | **National morale / stress track** | Stress → Homeland Status Wheel → penalties / defeat | No national ledger (unit morale in Napoleonic design is a different family) | Strategic “national will” systems | P3 |
| G8 | **Command stacks + written order sheets** | Stacks ≤8; ≤9 orders/turn; O&P chart as the planning artifact | Per-game stacking limits exist; no order-sheet commit model | Same as G2 once stacks live on a graph | P1 (with G2) |
| G9 | **Non-VASSAL content path** | No sanctioned `.vmod`; art/rules must come another way | Ingest/setup pipeline assumes `.vmod` + `.vsav` | Any title without a module | P1 (packaging; can parallel G1) |

---

## What already helps (do not rebuild)

- **Gate / log / verifier trinity** (`engine/gate.py`, `verify_game.py`) — every new family still proposes through `submit()`.
- **Seeded engine RNG** — oil bids, battle dice, production lottery all fit the existing die contract.
- **Spec-driven game directories** — `game.json` + one procedure module per family; data carries citations.
- **Tier ladder** — Tier 0 free play → Tier 1 movement → Tier 2 combat → Tier 3 AI; never ship unvalidated enforcement.
- **PBM / plan-DSL harness** (`PLAY_BY_MAIL.md`, `engine/plans.py`) — a *commit plan* shape exists for AI mail; harden into sealed-order gate semantics for G2, do not invent a second protocol.
- **Ingest already detects named regions** — `engine/ingest.py` counts named `Region` snap points and fails honestly; G1 turns that failure into a successful region-space emit.
- **`.vsav` is already pixel-based** — VASSAL region modules store piece/stack **pixel** positions the same way hex modules do; `vsav.py` read/write needs no new obfuscation format. What expands is the *interpretation* layer (`board.py`, `make_save.py`, ingest of `RegionGrid` names). See `AREA_MAP_DESIGN.md` § VASSAL compatibility.

---

## Explicit non-goals for the first expansion

Closing G1 does **not** claim War Room playability. Out of scope until their own design docs land:

- Sealed orders, oil bids, N seats, planning-sheet UI (G2–G3, G8)
- Battle boards / stances / air-naval (G4–G5)
- Economy / morale (G6–G7)
- Shipping War Room rules or art in the public repo (constitution: bring-your-own content; the publisher PDF stays outside git)

**G1 success** = named-region modules are **playable Tier-0 in the browser**: board + region graph + pieces + a starting setup, snap-to-territory moves with region highlights / legal-dest overlay, human-verifiable on the map — hex games still byte-identical. Area-map UI **and** VASSAL region-space file compatibility (ingest `RegionGrid`, `.vsav` mirror via region origins) are part of G1, not follow-ons. Adjacency graphs are usually *not* in the module (VASSAL snaps only) — edges remain authored data.

---

## Suggested sequence

```
G1 Area map + UI     →  AREA_MAP_DESIGN.md   (this tranche; playable Tier-0)
                         Pilot: A House Divided — implementer downloads
                         ahd_v05e.vmod from vassalengine.org (stage outside git)
G9 Content path      →  (short addendum once G1 schema is stable)
G2 + G8 Sealed orders→  SEALED_ORDERS_DESIGN.md  (includes planning UI)
G3 N-seat            →  can fold into sealed-orders design
G4–G7 WR depth       →  WARROOM_COMBAT / ECONOMY / MORALE designs
```

War Room encoding itself starts only after G1–G3 and a content path exist, and still follows the five-point pre-screen + validators + `VALIDATION.md` contract.

---

## Sources for War Room mechanics (external)

**Rulebook:** Nightingale Games publishes the 2nd Edition War Room rulebook as a free PDF (and mirrors it via retailers / Tabletopia). Pre-screen gate 1 (rules present) is therefore open for War Room — download the publisher PDF locally for encoding; do not commit it to the public repo.

Also useful: Nightingale / retailer FAQ & errata PDFs; Axis & Allies.org Kickstarter write-up; play summaries of the seven-phase loop. Tier-1+ encoding still requires cited transcription + validators against the publisher text (iron rule unchanged).
