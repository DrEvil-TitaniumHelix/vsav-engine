# G1 evidence — A House Divided (VASSAL ↔ VALOR)

**Date:** 2026-09-20  
**Module:** `ahd_v05e.vmod` (v0.5e) staged at `/home/devmapal/VassalIngest/a-house-divided/`  
**VASSAL:** 3.7.26 + Temurin JRE 17 (user-local; no root package needed for Java)  
**VALOR:** `python ui/server.py --game games/a-house-divided --port 8641`

## Screenshots

| File | What |
|---|---|
| `vassal_1861_main.png` | VASSAL 3.7.26 Player — stock **1861 Scenario.vsav** |
| `valor_1861_initial.png` | VALOR browser — same 1861 setup loaded |
| `compare_valor_vs_vassal_1861.png` | Side-by-side contact sheet (VALOR \| VASSAL) |
| `valor_1861_after_moves.png` | VALOR after API moves |
| `vassal_after_valor_mirror.png` | VASSAL opened **engine-written** `.vsav` after moves |
| `vassal_mirror_ne_crop.png` | NE crop of mirrored save (Baltimore / Philly area) |
| `valor_multihop_gettysburg.vsav` | Engine multi-hop path ending at Gettysburg |
| `vassal_multihop_gettysburg.png` | VASSAL 3.7.26 opened that save |
| `vassal_multihop_gettysburg_crop.png` | Crop of map area after multihop open |
| `validate_g1_runtime.report.json` | Automated deeper G1 suite output |

## Playtest log (API)

1. Selected unit `1588894742299` (Union Infantry) at **Fredericksburg**.
2. `/api/legal` → 22 graph destinations with edges PARTIAL (MA 6).
3. Move → **Washington** — `ok`; piece XY `(1399,268)` == region origin (`mirror_check.txt`).
4. Illegal move → **Atlanta** — rejected: `no route from washington to atlanta (region graph)` (`reject_off_graph.json`).
5. Move → **Baltimore** — `ok` (`move2_baltimore.json`).
6. Wrote `valor_after_move_baltimore.vsav`; opened in VASSAL 3.7.26 successfully (window title shows that filename).

## Rendering comparison (human)

- **Same map art** and **same counters** on named city boxes in both clients.
- Piece snaps sit on VASSAL Region origins in VALOR (no hex lattice artifacts).
- VASSAL chrome differs (toolbar, chat, army tracks as floating windows); VALOR uses its own top bar + origin-marker toggle (◎).
- VALOR shows Tier-0 banner (“no rules encoded”) — expected; not a VASSAL parity claim for rules.
- Stock VASSAL log notes missing `b_overview.gif` in the module — unrelated to VALOR.

## Known pilot UX notes

- Ingest `detect_tokens` empty → all pieces report **Side B**; pick **Side B** in the UI to drag.
- Edge graph is **PARTIAL** (37 edges); off-graph cities are not legal under Tier-0b.

## Deeper Tier-0 validation (2026-09-21)

Automated suite: `games/a-house-divided/validate_g1_runtime.py`  
Report: `evidence/validate_g1_runtime.report.json` — **PASS** (not AHD rules).

| Check | Result |
|---|---|
| `validate_region_space.py` | 129 locs, 37 edges, origin self-map |
| Spot-check printed names | 20/20 (incl. module spelling *Cincinnatti*) |
| All year setups + blank | 1861–1864 + Blank load; every unit has a `loc`; per-setup XOR keys `a8/b9/96/a7/41` |
| Graph BFS | From Fredericksburg, MA 6 → 22 dests; costs == distance; Atlanta off-component |
| Engine→.vsav→reload mirror | Move to Washington; XY == region origin after reload |
| Reverse snap (VASSAL→VALOR contract) | Place at Richmond origin XY → reload recovers `richmond` |
| Stacking | Two units onto Philadelphia at shared origin; `move_stack` → Harrisburg |
| Multi-hop path | Fredericksburg → … → Gettysburg; save `valor_multihop_gettysburg.vsav` |
| Loc distribution (1861) | 19 distinct locs (snap not collapsed) |
| Hex regression smoke | NAW + Afrika Korps `validate_movement.py` ALL PASS |
| VASSAL open smoke | 3.7.26 `--direct --load` opens multihop save (window title shows filename); `vassal_multihop_gettysburg.png` |

Note: nearest-origin assignment can map a stock piece to a city without sitting on the exact origin pixel; engine *moves* always write exact origin XY (required for VASSAL stack join).

## Not claimed

- Full AHD adjacency VERIFIED / SCORECARD FULL (P4).
- Pixel-identical chrome between VASSAL and VALOR (only board state / snap origins).
- Any AHD rulebook enforcement (combat, recruitment, SO, victory, etc.).
