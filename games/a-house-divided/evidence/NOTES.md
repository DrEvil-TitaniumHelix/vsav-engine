# G1 evidence — A House Divided (VASSAL ↔ VALOR)

**Date:** 2026-09-20 (deeper suite + claim-review hygiene 2026-09-21)  
**Module:** `ahd_v05e.vmod` (v0.5e) staged at `~/VassalIngest/a-house-divided/`  
**VASSAL:** 3.7.26 + Temurin JRE 17 (user-local; no root package needed for Java)  
**VALOR:** `python ui/server.py --game games/a-house-divided --port 8641`

Playability of this folder requires that out-of-tree staging (map + setups). A clean clone alone is not enough.

## Screenshots (local; `*.png` / `*.vsav` gitignored)

| File | What | Trust |
|---|---|---|
| `vassal_1861_main.png` | VASSAL 3.7.26 Player — stock **1861 Scenario.vsav** | OK (human map view) |
| `valor_1861_initial.png` | VALOR browser — same 1861 setup loaded | OK |
| `compare_valor_vs_vassal_1861.png` | Side-by-side contact sheet (VALOR /| VASSAL) | OK |
| `valor_1861_after_moves.png` | VALOR after API moves (Fredericksburg→Washington→Baltimore); re-captured 2026-09-21 | OK (≠ initial) |
| `vassal_after_valor_mirror.png` | VASSAL full player window on `valor_after_move_baltimore.vsav` (1854×1011); re-captured 2026-09-21 | OK map view |
| `vassal_mirror_ne_crop.png` | NE crop of that mirrored save | OK secondary |
| `valor_multihop_gettysburg.vsav` | Engine multi-hop path ending at Gettysburg | **primary** XY proof via validators |
| `vassal_multihop_gettysburg.png` | VASSAL opened that save (title bar shows filename) | OK load proof |
| `validate_g1_runtime.report.json` | Automated deeper G1 suite output | **primary** |

**Withdrawn (claim review):** earlier `vassal_after_valor_mirror.png` was only a “Start new Logfile?” dialog (488×111); earlier `valor_1861_after_moves.png` was byte-identical to `valor_1861_initial.png`. Both were replaced 2026-09-21.

**Strongest VASSAL↔VALOR proof remains programmatic:** piece XY after engine moves == region catalog origin (see mirror_check.txt + `validate_g1_runtime.py`).

## Playtest log (API)

1. Selected unit `1588894742299` (Union Infantry) at **Fredericksburg**.
2. `/api/legal` → 22 graph destinations with edges PARTIAL (MA 6).
3. Move → **Washington** — `ok`; piece XY `(1399,268)` == region origin (`mirror_check.txt`).
4. Illegal move → **Atlanta** — rejected: `no route from washington to atlanta (region graph)` (`reject_off_graph.json`).
5. Move → **Baltimore** — `ok` (`move2_baltimore.json`).
6. Wrote `valor_after_move_baltimore.vsav`; VASSAL 3.7.26 loads it (window title shows that filename). Map chrome screenshot is secondary to XY proof.

## Rendering comparison (human)

- **Same map art** and **same counters** on named city boxes in both clients.
- After an engine *move*, piece XY equals the VASSAL Region origin (no hex lattice).
- Stock setups: after correcting VASSAL Map `edgeWidth`/`edgeHeight` (75px),
  **26** combat pieces sit on catalog origins; **2** cavalry sit on recruitment-
  poster holding boxes (`loc=None`); **4** army-size `N-00` markers (`report`)
  sit on the Army Size track (also outside city snap). Counters render at
  native **51×51**; emb2 art prefers the Main face (not `*-back.png`).
- VASSAL chrome differs; VALOR uses its own top bar + origin-marker toggle (◎).
- VALOR guide for PARTIAL region games states graph free play + off-graph reject (not “drag anywhere”).

## Known pilot UX notes

- Ingest `detect_tokens` empty → all pieces report **Side B**; pick **Side B** in the UI to drag.
- Edge graph is **PARTIAL**: 37 edges, **31/129 (24%)** locs with ≥1 edge, **2** components (sizes 24 and 7), **98** isolated. Under Tier-0b, most printed cities are illegal destinations — sample-graph free play, not full-map graph play.
- Edges have no cite/tags yet (sample authoring only).

## Deeper Tier-0 validation (2026-09-21)

Automated suite: `games/a-house-divided/validate_g1_runtime.py`  
Report: `evidence/validate_g1_runtime.report.json` — **PASS** (not AHD rules).

| Check | Result |
|---|---|
| `validate_region_space.py` | 129 locs, 37 edges, origin self-map |
| Spot-check printed names | 20/20 (incl. module spelling *Cincinnatti*) |
| All year setups + blank | 1861–1864 + Blank load; every unit has a nearest-origin `loc`; keys `a8/b9/96/a7/41` |
| Graph BFS | From Fredericksburg, MA 6 → 22 dests; costs == distance; Atlanta off-component |
| Engine→.vsav→reload mirror | Move to Washington; XY == region origin after reload |
| Reverse snap (VASSAL→VALOR contract) | Place at Richmond origin XY → reload recovers `richmond` |
| Stacking | Two units onto Philadelphia at shared origin; `move_stack` → Harrisburg |
| Multi-hop path | Fredericksburg → … → Gettysburg; save `valor_multihop_gettysburg.vsav` |
| Loc distribution (1861) | 19 distinct locs (snap not collapsed) |
| Hex regression smoke | `games/napoleon-at-waterloo/validate_movement.py` + `games/afrika-korps-classic-ah/validate_movement.py` ALL PASS |
| VASSAL open smoke | 3.7.26 `--direct --load` opens multihop save (title bar); XY proof for moved piece |

## Hex note

“Hex games unchanged” means **validators still pass** (behavior preserved). Hex paths in `board.py` were refactored through shared `_dest_xy` / `_loc_label` helpers — not a claim of an untouched hex code path.

## Not claimed

- Full AHD adjacency VERIFIED / SCORECARD FULL (P4).
- Pixel-identical chrome between VASSAL and VALOR.
- Any AHD rulebook enforcement (combat, recruitment, SO, victory, etc.).
- In-repo completeness without `~/VassalIngest/a-house-divided/` staging.
