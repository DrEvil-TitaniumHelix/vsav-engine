# Afrika Korps — grid & rules validation worksheet (in progress)

Spec #12 discipline: nothing ships until validated. This file records the
evidence chain for the sideways-grid mapping and, later, the CRT encoding.

## Grid anchors (rulebook section 1.1, AfrikaKorps_3d_Ed_Rules.pdf)
| Landmark | Hex | Approx pixel (eyeballed, ±half hex — SNAP TO LATTICE BEFORE USE) |
|---|---|---|
| German home base (gray hex) | W3 | (150, 2410) |
| El Agheila (town O) | W6 | (455, 2425) |
| Bengasi (fortress) | H2 | (800, 1160) |
| Tobruch (fortress) | G25 | (3195, 1015) |
| El Alamein (town O) | L59 | (6420, 1422) |
| Allied home base (gray hex, Union Jack) | J62 | far right edge, ~(6700, ~1300) TBD |

Extra rulebook facts for later checks: escarpment example G24; T29 is NOT a
pass; Qattara example R60; coast road example K61; combat examples cluster
H23–J28 (adjacency ground truth for the movement/ZOC gate).

## Module grid (buildFile): sideways/pointy, dx=101.8, dy=88.126,
origin (0,32), stagger, offset_parity=1.
Numbering: first=H, hType=A (letters), vType=N, hOff=-5, vOff=-12.

## Findings so far (2026-07-09)
- Numbers increment along +x within a lettered row (W3→W6 = 3×dx exactly).
- Letters increment along +y (G Tobruch above H Bengasi... note actually
  G row is NORTH of H row: letters increase southward).
- Number is NOT a pure column index: same-letter rows run along the hex
  grain (diagonal), so number = col + f(row). Preliminary fit
  N = c + r/2 − 11.5 consistent for W3/W6/G25/L59 with odd r; letter↔r
  mapping not yet consistent under eyeballed centers (skipped letters on
  the printed edge — small map shows ...I,K,L..T,W,X — J/U/V may be
  skipped; must resolve with exact centers).
- Map edge shows NEGATIVE numbers (−1..−8) near Agheila corner: numbering
  extends west of 0 — matches vOff=−12-ish offsets. Resolve exactly.

## Method (next steps)
1. Fit exact lattice from the 79 self-positioned setup pieces (Tobruk
   region-fit method) → exact dx,dy,x0,y0,parity.
2. Snap the 6 landmark pixels to lattice nodes → exact (c,r) per landmark.
3. Solve the integer label mapping (letter,number)=f(c,r) over ALL anchors;
   must be exact on every anchor incl. an even-r one, else STOP.
4. Encode mapping in game.json; verify adjacency on the H23–J28 combat
   examples; only then build the movement gate.

## CRT (Tier 2, later)
The full CRT is printed on the map image (center-top) AND in the rulebook
text — transcribe from text, cross-check against the map image, validate
resolution against the rulebook's worked combat examples (H25/H26/I26...).
Classic AH odds-ratio CRT with A elim / A back 2 / Exchange / D back 2 /
D elim and soak-off rules.
