# Engine design: Area / territory map (region space)

**Status: IMPLEMENTED (P1–P3) — 2026-09-20.** Pilot A House Divided is Tier-0 playable (`space.kind=region`, sample PARTIAL edges). P4 (full verified AHD adjacency → SCORECARD FULL) remains open.
**Trigger / north star:** unlock the spatial substrate War Room needs (`WARROOM_GAPS.md` G1), and convert the SCORECARD “named regions” PARTIAL/FAIL rows to **playable Tier-0 in the browser** (space model + area-map UI together).

**Primary pilot (required): A House Divided** — 125 named regions; bundled scenarios put pieces on the main map (best UI / `.vsav` verification). Other SCORECARD PARTIAL region titles (Diplomacy, Paths of Glory, …) are follow-on smoke once the primary pilot works. Wilderness War is a poor first smoke (ingest saw only 3 named regions).

### Implementer: obtain the pilot module yourself

Do **not** wait for the user to supply a `.vmod`. As step zero of P1:

1. Download **A House Divided** from the VASSAL module library:  
   https://vassalengine.org/library/projects/A_House_Divided  
   Prefer the file already reflected in-repo ingest notes: **`ahd_v05e.vmod`** (if the library has a newer GDW/Phalanx build, note the version in the ingest report and proceed).
2. Stage it **outside the git tree** (e.g. `~/VassalIngest/a-house-divided/` or similar). Never commit `.vmod`, extracted images, or rulebook PDFs.
3. Run `python engine/ingest.py <path-to.vmod> --out games/a-house-divided` (or the existing game dir) and continue the phases below against that staging.

Optional later smoke: Diplomacy (`Diplo-v0_2.vmod`) — https://vassalengine.org/library/projects/Diplomacy — but its setups park pieces off the main map, so it is worse than A House Divided for first UI proof.

This doc is the implementer’s contract. Prefer matching existing patterns in `gamespec.py`, `ingest.py`, `gate.py`, and `NAPOLEONIC_FAMILIES_DESIGN.md` (engine family, not game special).

---

## Why this is engine work, not game work

`ENCODING_GUIDE.md` pre-screen §3 and `LIBRARY_CENSUS.md` both name the same hole: the engine’s playable space is a **hex lattice**. Modules whose main board is a VASSAL `RegionGrid` of **named** snap points fail ingest with:

> board uses N NAMED regions (point-to-point/area map) — engine has no region-space support yet

That is ~13% of the catalog (point-to-point) plus area/region-snap titles — and it is a hard blocker for War Room’s world map. Building “Diplomacy hexes” or a War-Room-only coordinate hack would violate the standing rule: **capabilities once, at engine level**.

---

## What the engine already has (reuse)

| Capability | Where | Reuse for region space |
|---|---|---|
| Spec-driven movement queries | `gamespec.Game` | Same public query surface; swap geometry backend |
| Pixel placement of counters | `grid.hex_to_pixel` → UI `x,y` | Regions expose `origin` pixels the same way |
| `.vsav` piece XY | `board.py` / `vsav.py` | Unchanged — pieces still store pixel (or stack) positions; space layer *interprets* them |
| Gate / log / verify | `gate.py` | Unchanged contract; actions carry `dest` as a **location id** |
| Ingest RegionGrid parse | `ingest.parse_board` | Already collects `(originx, originy)` + names; today only *counts* named regions |
| Tier-0 free play | uniform 1 MP, no ZOC | Same defaults once neighbors exist |

---

## Goals / non-goals

### Goals (this design)

1. **`space` model** in `game.json`: either `hex` (today) or `region` (graph of named locations).
2. **Tier-0 playable in the browser**: load a named-region module, see the map + counters, snap pieces to regions, move with the same click/legal-highlight loop hex games use — so humans can verify ingest/edges on the real art immediately.
3. **Ingest**: named `RegionGrid` → emit region nodes (id, name, origin xy); do **not** invent edges from pixels alone.
4. **Hex games byte-identical**: no change to `HASH_KEYS`, movement results, or validators for existing hex titles.
5. **Area-map UI is in G1** (not deferred): region labels on hover/select, origin markers, legal-dest overlay keyed by region id. Planning-sheet / sealed-order UI stays in `WARROOM_GAPS.md` G2.

### Non-goals (explicit)

- Sealed orders, N seats, planning sheets, battle boards, air/naval domains, economy (`WARROOM_GAPS.md` G2+).
- Inferring a correct political/adjacency graph from map art or region XY alone (unsafe; author or cite).
- Shipping module art/rulebooks in the public repo.
- Square grids (separate future expansion; Twilight Struggle stays PARTIAL).
- Full Diplomacy / War Room rules enforcement (Tier 1+ is a later gate module).
- Polygon territory fills (nice-to-have; circle/origin highlights are enough for G1 verification).

---

## Conceptual model

```
LocationId  = stable string key (slug of printed name, or ingest id)
Space       = { locations: Map<LocationId, Location>, edges: Edge[] }
Location    = { id, name, origin: [x,y], tags?: string[], terrain?: string }
Edge        = { a, b, cost?: number, tags?: string[] }   # undirected unless directed:true
```

- A unit’s **logical** position is a `LocationId` (not `(col,row)`).
- A unit’s **render** position is the location’s `origin` (plus stack offset — existing UI stacking).
- **Adjacency** is only via `edges` (plus optional self for “stay”).
- **Distance** = shortest path over edges with edge `cost` (default 1).
- **On-map** = location id ∈ locations and not tagged impassable / offmap.

Point-to-point (PoG rail lines) and pure area maps (Diplomacy provinces) share this model: both are graphs. Hex space remains the lattice special case.

---

## VASSAL compatibility (expand the format surface — required for G1)

VASSAL **already supports** area / point-to-point boards. A typical module uses a `RegionGrid` of named `Region` snap points (`originx` / `originy` + `name`) on the main board. Players drag counters; VASSAL snaps to those origins. Saves (`.vsav`) still store **pixel coordinates** and stack membership — not hex numbers and usually **not** the region name string.

This engine is file-format-compatible with VASSAL 3 (zero VASSAL source; see README / CONTRIBUTING). G1 must **widen that compatibility** from “hex lattice modules” to “named-region modules,” not invent a parallel save format.

### What already works (keep)

| Layer | Status |
|---|---|
| `.vmod` zip extract, `buildFile` / `moduledata` | Works |
| `.vsav` `!VCSK` XOR zip read/write (`vsav.py`) | Works for region modules too (pixels) |
| Piece + stack command parse/mutate at XY (`board.py` `_set_piece_xy`, attach/detach) | Works — mutation is pixel-native |
| Setup save copy / legacy normalization in ingest | Works |
| Anonymous `RegionGrid` → hex lattice fit (Tobruk method) | Works; leave alone |

### What VASSAL has that we under-consume

| VASSAL artifact | Today in VALOR | G1 work |
|---|---|---|
| `RegionGrid` / `Region` **name + origin** | Parsed only enough to **count** names, then `bad("no region-space support")` | Full emit → `regions.json` locations |
| Piece at region snap in `.vsav` | Loaded as XY, then forced through `grid.pixel_to_hex` in `Board.units()` | `pixel_to_loc` → unit `loc` |
| Move / mirror back to `.vsav` | `move_piece*` / `ui/server.mirror_move` call `hexnum_to_pixel` | Resolve dest location id → origin XY, then existing `_set_piece_xy` |
| Scenario authoring (`make_save.py`) | `"hex": [col,row]` (or raw `"xy"`) | Accept `"loc": "berlin"` (and keep `"xy"` / hex for other kinds) |
| Predefined setups on region maps | Often pieces on charts / 0 on main map (SCORECARD) | Same honesty; author scenarios with `loc` once space works |
| Adjacency / movement graph | **Not in VASSAL** (snaps ≠ rules) | Still authored `edges` in `regions.json` — not a VASSAL-compat gap |

### Contract: round-trip with real VASSAL

For a region pilot that has a `.vmod` + setup:

1. Ingest module → `regions.json` locations match VASSAL region names/origins (spot-check).
2. Engine moves a piece to location L → writes `.vsav` with piece/stack XY = L’s origin.
3. **Open that `.vsav` in VASSAL 3** — counter sits on the same snap VASSAL would use for L.
4. Move a counter in VASSAL onto another named region, save, reload in VALOR — `pixel_to_loc` recovers that region (within snap tolerance / tie-break rules).

If (3) or (4) fail, G1 VASSAL-compat is not done — even if the browser UI looks fine.

### What does *not* change

- Still **no VASSAL source** in the repo (constitution).
- Still no claim that VASSAL enforces rules — parity is **board state / snap positions**, Tier-0 free play.
- War Room has **no** `.vmod` today → G1 VASSAL work unlocks Diplomacy / PoG / House Divided / etc.; War Room itself still needs G9 (hand-authored or other digital board data) using the **same** `regions.json` schema.

### Implementer touch list (VASSAL-facing)

- `engine/ingest.py` — named `RegionGrid` success path; store `{name,x,y}[]` not just counts
- `engine/board.py` — `units()` / `move_piece*` / CLI dump branch on `space.kind`; dest may be location id
- `engine/make_save.py` — `"loc"` placement → origin pixels; stack grouping by loc
- `ui/server.py` — `mirror_move` uses `loc_to_pixel`, not `hexnum`
- Optional later: zone / multi-board region grids if a pilot needs them (not required for first pilot)

Add a small **compat smoke** (manual or scripted): write `.vsav` after one region move; assert piece XY equals catalogued origin; document “open in VASSAL” as human check on the pilot.

---

## `game.json` schema

### Discriminator

```json
"space": {
  "kind": "hex" | "region",
  "...": "kind-specific block"
}
```

**Compatibility:** today’s specs omit `space` and carry top-level `"grid": { ... }`. Loader rule:

- If `space` absent and `grid` present → treat as `space.kind = "hex"` with `space.grid = grid` (legacy).
- If `space.kind == "region"` → `grid` must be absent or ignored; do not construct `gamespec.Grid`.

### Region block

```json
"space": {
  "kind": "region",
  "file": "regions.json",
  "provenance": "from VASSAL RegionGrid names+origins; edges hand-authored / cited"
}
```

### `regions.json` (or inline `space.locations` for tiny maps)

```json
{
  "locations": {
    "berlin": { "name": "Berlin", "origin": [812, 440], "tags": ["land", "supply_center"] },
    "baltic-sea": { "name": "Baltic Sea", "origin": [900, 300], "tags": ["sea"] }
  },
  "edges": [
    { "a": "berlin", "b": "silesia", "cost": 1 },
    { "a": "berlin", "b": "baltic-sea", "cost": 1, "tags": ["fleet_only"] }
  ],
  "impassable_tags": ["offmap"],
  "ingest": {
    "region_grid_points": 80,
    "edges_status": "UNAUTHORED | PARTIAL | VERIFIED"
  }
}
```

**Id stability:** slugify VASSAL region `name` (`"St. Petersburg"` → `st-petersburg`). Collision → append `-2`, `-3` and record mapping in ingest report. Never renumber silently after a game has logs.

### Movement block (region)

Reuse `movement` keys where they still make sense; ignore hex-only keys:

| Key | Hex today | Region meaning |
|---|---|---|
| `default_mp` | enter-hex cost | default edge cost if edge omits `cost` |
| `terrain_mp` | by hex terrain | optional cost by **destination** `terrain` / tag |
| `hexside_rules` | hexside features | **unused** (or map to edge `tags` later) |
| `zoc` | hex ZOC | Tier-0 off; Tier-1+ defined per game gate |
| `bounds` | col/row rect | unused |
| `impassable_terrain` | hex terrain set | prefer `impassable_tags` on locations |
| `stacking` | end-hex limit | end-**location** limit (same shape) |

Tier-0 ingest skeleton:

```json
"movement": {
  "default_mp": 1.0,
  "zoc": { "exerts": false },
  "enter_enemy_location": true,
  "pass_through_friendly": true,
  "note": "Tier 0 region: 1 MP per edge; edges may be empty (snap-only) until authored"
}
```

---

## `gamespec.py` API (implementer surface)

Introduce a small **Space** abstraction so callers stop assuming col/row.

### Required methods on `Game` (both kinds)

| Method | Hex behavior (preserve) | Region behavior |
|---|---|---|
| `location_id(pos)` | `grid.hexnum(col,row)` or display name | identity / slug |
| `neighbors(loc)` | lattice neighbors as location ids **or** keep returning `(col,row)` via adapter — see below | edge endpoints |
| `on_map(loc)` | terrain/bounds | loc exists ∧ not impassable |
| `move_cost(a, b)` | enter-hex cost | edge cost or None if no edge |
| `distance(a, b)` | `hex_distance` | Dijkstra / BFS on edges |
| `loc_to_pixel(loc)` | `hex_to_pixel` | `origin` |
| `pixel_to_loc(x, y)` | `pixel_to_hex` | nearest region origin (Tier-0 snap), optional max radius |
| `display_name(loc)` | grid naming styles | `locations[id].name` |

### Adapter strategy (critical for non-regression)

**Do not rewrite every gate in one PR.** Prefer:

1. Add `Game.space_kind` (`"hex"` | `"region"`).
2. For `kind=="hex"`, keep exact current `(col,row)` APIs (`neighbors(col,row)`, `hex_terrain`, …) untouched.
3. For `kind=="region"`, new APIs take string location ids; hex-only methods raise `NotImplementedError` with a clear message.
4. Shared helpers used by UI/server (`unit` view model) branch on `space_kind`.

Optional later cleanup: unify on opaque `Loc` tuples — **out of scope** for the first merge if it risks hex byte-drift.

### Unit state shape

Today strategic units carry `"col"`, `"row"`. For region games:

```json
"loc": "berlin"
```

UI/server may still expose `x,y` from `loc_to_pixel`. Do **not** synthesize fake col/row.

Gate move action:

```json
{"type": "move", "unit": "<pid>", "dest": "berlin"}
```

Hex continues to use `"dest": [col, row]` (unchanged).

---

## Ingest changes (`engine/ingest.py`)

When `regions and regions[0]["named"]`:

1. **Stop** emitting the current `bad(...)` as a hard stop for grid-lessness.
2. Emit `space.kind = "region"` and write `regions.json` with **locations only** (name + origin from each `Region` element).
3. Set `edges: []` and `ingest.edges_status: "UNAUTHORED"`.
4. Scorecard / INGEST_REPORT:
   - **PARTIAL** if edges unauthored (snap-to-region free play only), **or**
   - **FULL** once a verified edge list exists *and* runtime self-check sees units on named locs (see acceptance).
5. Parse improvement: store full `{name, x, y}` list on the board grid dict (today only `named=count` and anonymous `points`). Without names, region space cannot be rebuilt.

Suggested report lines:

```
- region space: 80 named locations from RegionGrid → regions.json (edges UNAUTHORED)
- Tier-0: counters snap to nearest region; movement along edges disabled until edges authored
```

Do **not** auto-edge by Delaunay / k-NN as “verified.” Optional `--guess-edges k` may write a separate `regions.guessed.json` marked UNVERIFIED for authoring aid only — never the live `regions.json` without human accept.

---

## Movement engine (Tier-0 / Tier-1)

### Tier-0a — snap only (edges empty)

- `pixel_to_loc` places / repositions units onto nearest origin.
- Legal move set = **all** on-map locations (or “any location within N pixels” if you want tighter UX) — umpire model, same spirit as hex Tier-0 with `enter_enemy_hex: true`.
- Log still records every move; no rules citations claiming adjacency.

### Tier-0b — graph free play (edges authored, still no ZOC/rules)

- `legal_dests(unit)` = BFS from current loc with remaining MA (`stats` MA, default 6 placeholder).
- Reject moves with no path; reason: `"no route from A to B (region graph)"` (not a rulebook cite).

### Tier-1 (later, per game gate)

- Domain tags (`land`/`sea`), ZOC-on-graph, stacking, enemy occupancy — owned by the game’s procedure module, reading the same `regions.json`.

War Room / Diplomacy rules do **not** belong in `gamespec` movement.

---

## `.vsav` / board layer

- Pieces continue to live at **pixel** coordinates in the save — that is already how VASSAL region modules work (see § VASSAL compatibility).
- On load: `loc = pixel_to_loc(x,y)` for each piece on the main map; store `loc` in engine state.
- On apply move: set piece XY to `loc_to_pixel(dest)` (stack offsets unchanged) via existing `board.py` pixel mutators.
- Round-trip: VASSAL opens our saves and vice versa at the snap origins; engine adds logical `loc` in `game_*.state.json`, not inside proprietary VASSAL fields.

If a setup parks pieces on charts / off the main map (Diplomacy stock boards), keep today’s “0 on main map” honesty — scenario authoring via `make_save` with `"loc"` remains required (already called out in SCORECARD).

---

## UI / server (required for G1 — not a follow-on)

Area-map UI is how G1 pays off: several SCORECARD PARTIAL titles become **immediately playable as Tier-0 free play**, and humans can eyeball wrong snaps / missing edges on the printed map instead of diffing JSON.

Work in `ui/server.py` + `ui/index.html` (strategic-style path). Tactical Tobruk UI ignores region space.

### Must-have (G1 done = these work on a pilot)

1. **Load & render** — map asset, counters at `loc_to_pixel`, stack offsets readable when several units share a region.
2. **Unit DTO** — `loc`, `locname`, `x`, `y`. Prefer aliases `hexnum`←`loc` and `hexname`←`locname` so existing JS selection/log panels keep working; document the alias in a one-line comment near the serializer.
3. **Select unit → legal dests** — `/api/legal` returns `{ dests: [{id, name, x, y, mp}, ...] }` (Tier-0a: all on-map locs or MA-reachable; Tier-0b: graph BFS).
4. **Overlay** — mark legal destination **origins** (filled circles / rings, same visual language as hex legal highlights). Selected unit’s current region gets a distinct ring. Optional faint marks for *all* region origins when a debug toggle is on (hugely useful for verifying ingest).
5. **Move** — click a highlighted dest (or drag onto it) posts `dest` as string location id; piece animates/snaps to that origin; toast/reject path shows engine reason text.
6. **Identity chrome** — selection panel / tooltip shows printed region **name** (not only the slug id).
7. **Same entry points as hex** — `python app.py` / `python ui/server.py --game games/<pilot>` opens the region pilot without a special binary.

### Explicitly out of G1 UI

- O&P / sealed-order planning sheet (G2)
- Battle Status Board view (G4)
- Polygon fills, territory ownership tinting, convoy lines (later polish / rules tiers)

### Human verification checklist (manual, on pilot)

- [ ] Every obvious province snap lands on the name you expect (spot-check ≥15 regions against map labels).
- [ ] Two units in one region stack legibly; picker still works.
- [ ] With edges: legal highlights only on adjacent (or MA-reachable) regions; off-graph click rejected.
- [ ] With edges empty (Tier-0a): can still free-move / snap for umpire play.
- [ ] Hex game (AK or Chickamauga) still looks and moves as before.

---

## Gate / verify

- No new shared gate subclass required for Tier-0 free play if the existing free-play path already moves pieces without a rules gate.
- If free play goes through a thin gate, add region `move` handling beside hex without changing hex `HASH_KEYS`.
- `verify_game.py`: location ids must round-trip in logged actions; state hash includes `loc` for region games (new games only — never rewrite shipped hex `HASH_KEYS`).

---

## Acceptance criteria (definition of done)

### A. Non-regression

- `python run_all.py --fast` green.
- Existing hex game validators unchanged in behavior (byte-exact AI campaigns still pass where they did).

### B. Ingest

- Implementer has downloaded and staged A House Divided (see header).
- Running ingest on that `.vmod` produces `regions.json` with **all** named origins and `space.kind=="region"`.
- INGEST_REPORT no longer says only “no region-space support”; it states locations emitted + edges status.
- SCORECARD row for A House Divided updates to PARTIAL (locations, no edges) or FULL (per below).

### C. Runtime Tier-0 pilot (**includes UI + VASSAL mirror**)

- `python ui/server.py --game games/<pilot>` (or `app.py`) opens the pilot; map + counters visible.
- Place/move a piece via the UI: engine state `loc` updates; counter sits on that origin; region name shows in selection chrome.
- Legal-dest overlay works (Tier-0a and, when edges exist, Tier-0b); illegal off-graph move rejected with visible reason.
- Debug (or always-on light) markers make region origins inspectable for ingest QA.
- Engine→`.vsav` mirror uses region origins; **VASSAL 3 opens the save on the matching snap** (compat contract above).
- With authored edges for a **subset** (≥10 connected locations): legal highlight follows the graph.
- `games/<pilot>/validate_region_space.py` checks:
  - every location has unique id + finite origin;
  - every edge endpoint exists;
  - graph is undirected-symmetric if `directed` absent;
  - `pixel_to_loc(origin)` returns self for every location;
  - distance symmetry on undirected graphs.

### D. Docs

- SCORECARD / LIBRARY_CENSUS one-line update: region space + Tier-0 UI supported (edges authored per game).
- Link from `WARROOM_GAPS.md` G1 → this file marked implemented when merged.

---

## Implementation phases (suggested PR split)

| Phase | Deliverable | Merge bar |
|---|---|---|
| **P1** | **Download** `ahd_v05e.vmod` (or current library build) yourself; stage outside git; parse named regions fully; write `regions.json` locations; `space.kind` in skeleton; SCORECARD PARTIAL wording | Ingest succeeds on A House Divided; locations emitted; no runtime required yet |
| **P2** | `gamespec` region Space + pixel↔loc; unit state `loc`; **board/make_save/server** region paths; **UI** Tier-0a on **1861** (or similar) setup; **VASSAL `.vsav` round-trip** at region origins | Pilot **playable in browser**; move mirrors to `.vsav` VASSAL can open; human verification started |
| **P3** | Edge list + BFS legal dests (Tier-0b); overlay respects graph; `validate_region_space.py` | Pilot with ≥10 edges green in UI and validator |
| **P4** | Hand-author full adjacency for **A House Divided**; SCORECARD FULL; edge provenance; VASSAL open/save smoke signed off | FULL row; human + VASSAL checklist complete |

**G1 is not done until P2 lands** — data without UI does not unlock “immediately playable” area games. P1 alone is an allowed intermediate merge. The implementer downloads the pilot `.vmod`; the user does not hand it over.

War Room map data is **not** required in P1–P4 (no WR `.vmod`). After P3, a hand-built `regions.json` for a WR scenario can use the same schema (G9 content path). The publisher rulebook PDF is free to download for later tiers; keep it out of git.

---

## Edge authoring guidance (for the human / agent filling graphs)

1. Prefer a **cited** source: rulebook adjacency list, play aid, or module chart — record `provenance` on `regions.json`.
2. Keep sea/land as **tags** on locations and/or edges; do not encode fleet rules in `gamespec`.
3. Coasts: either duplicate coastal provinces as dual land/sea nodes (Diplomacy-style) or tag edges `convoy` / `amphib` — pick one convention per game and stick to it in the gate later.
4. Never commit guessed edges without `edges_status: "UNVERIFIED"` and a validator skip (or explicit allowlist).

---

## Test plan (implementer checklist)

- [ ] Unit tests for slugify + collision
- [ ] Unit tests for BFS/distance on a 5-node fixture graph
- [ ] `pixel_to_loc` nearest-neighbor + tie-break (lower id wins — document it)
- [ ] Ingest dry-run on **downloaded** A House Divided `.vmod` (required); fixture XML `RegionGrid` snippet only as a unit-test supplement
- [ ] Hex: `validate_grid` / movement validators still pass for AK or Chickamauga smoke
- [ ] **UI:** A House Divided 1861 (or similar) opens in browser; move two stacks onto same region; stacking + picker OK
- [ ] **UI:** legal overlay + reject path; region name in selection panel
- [ ] **UI:** origin debug markers usable for ingest spot-check
- [ ] Human verification checklist (above) signed off for the pilot
- [ ] **VASSAL:** after a region move, `.vsav` piece XY == location origin; file opens in VASSAL 3 on the expected snap
- [ ] **VASSAL:** move in VASSAL onto another named region, reload in VALOR → correct `loc`

---

## Open questions (resolved during P1–P2)

1. **Alias fields in UI:** reuse `hexnum`/`hexname` as aliases for loc id/name (done).
2. **SCORECARD FULL bar:** complete graph for the main map’s playable locations (not just one setup’s reachable set).
3. **Multi-board modules:** region space only for `main_map`; stocks remain pixel-only until needed.
4. **Directed edges:** schema supports `directed: true`; Tier-0 treats undirected unless set.
5. **Always-on vs toggle for all-origin markers:** toolbar ◎ toggle, default **on** for region pilots.
6. **Region name in piece state?** AHD does not store region names in piece state — pixel snap is the compat contract.

---

## References in-repo

- `WARROOM_GAPS.md` — full War Room gap register (G1 = this family)
- `SCORECARD.md` — current named-region PARTIAL rows
- `LIBRARY_CENSUS.md` — “point-to-point/area-map support = single biggest unlock”
- `ENCODING_GUIDE.md` — mechanics fit / iron rule
- `engine/ingest.py` — `parse_board` RegionGrid; failure branch ~L596
- `engine/gamespec.py` — `Grid` + movement (hex substrate to parallel)
- `NAPOLEONIC_FAMILIES_DESIGN.md` — precedent for engine-family design docs
