# Ingest report — PanzerBlitz/Panzer Leader v3.7

**Verdict: FULL** (Tier-0 conversion — free piece pushing; no rules learned, no enforcement claimed)

- module file: `Pzb-Pzl37.vmod`
- staged at: `C:\VassalIngest\panzerblitz-panzer-leader` (assets stay OUT of the repo)

Play it:  `python ui/server.py --game games\panzerblitz-panzer-leader`

## What worked

- extracted 796 entries -> C:\VassalIngest\panzerblitz-panzer-leader\extracted
- module: 'PanzerBlitz/Panzer Leader' v3.7; 686 images staged
- 310 piece/card slots (289 with BasicPiece art, 1 blank-image layer pieces VASL-style); 4 prototypes
- declared sides: ['German', 'Russian', 'Allied', 'Moderator']
- main board: 'PZL Board C' on map 'Mapboard'; 8 other board(s) not converted: PZL Board A (map 'Mapboard'), PZL Board B (map 'Mapboard'), PZL Board D (map 'Mapboard'), PZB Board 1 (map 'Mapboard'), PZB Board 2 (map 'Mapboard'), PZB Board 3 (map 'Mapboard')
- hex grid from buildFile: flat dx=52.0 dy=60.0 origin=(-2.0,30.0)
- map asset: PL_board_C.gif (1667x600 px)
- setup 'PZB #1 White Russia': 47 pieces (47 self-positioned, 47 in stacks), key 0x6a
- setup 'PZB #2 Nikopol': 60 pieces (60 self-positioned, 60 in stacks), key 0xae
- setup 'PZB #3 Vyazma': 51 pieces (51 self-positioned, 51 in stacks), key 0x53
- setup 'PZB #4 Minsk': 69 pieces (69 self-positioned, 69 in stacks), key 0x97
- setup 'PZB #5 Lutezh Bridgehead.': 68 pieces (68 self-positioned, 68 in stacks), key 0x4c
- setup 'PZB #6 Dnieper River Crossing.': 68 pieces (68 self-positioned, 68 in stacks), key 0x35
- setup 'PZB #7 Kiev': 88 pieces (88 self-positioned, 88 in stacks), key 0xdd
- setup 'PZB #8 Korsun Pocket': 125 pieces (125 self-positioned, 125 in stacks), key 0xd0
- setup 'PZB #9 Stalino': 105 pieces (105 self-positioned, 105 in stacks), key 0x34
- setup 'PZB #10 Prochorovka': 113 pieces (113 self-positioned, 113 in stacks), key 0xe4
- setup 'PZB #11 Unorganized Russian Position (Buchach)': 115 pieces (115 self-positioned, 115 in stacks), key 0x9c
- setup 'PZB #12 Nikopol Bridgehead': 160 pieces (160 self-positioned, 160 in stacks), key 0xb1
- setup 'PZL #1 Utah Beach': 42 pieces (42 self-positioned, 42 in stacks), key 0xdb
- setup 'PZL #2 Omaha Beach': 115 pieces (115 self-positioned, 115 in stacks), key 0xd3
- setup 'PZL #3 Gold Beach': 88 pieces (88 self-positioned, 88 in stacks), key 0xaa
- setup 'PZL #4 St. Lo': 78 pieces (78 self-positioned, 78 in stacks), key 0x8f
- setup 'PZL #5 Operation Goodwood': 127 pieces (127 self-positioned, 127 in stacks), key 0xfe
- setup 'PZL #6 The Reichswald': 78 pieces (78 self-positioned, 78 in stacks), key 0xfd
- setup 'PZL #7 Encirclement of Nancy': 67 pieces (67 self-positioned, 67 in stacks), key 0xeb
- setup 'PZL #8 Marieulles': 49 pieces (49 self-positioned, 49 in stacks), key 0xfe
- setup 'PZL #9 Operation Market: Nijmegen': 73 pieces (73 self-positioned, 73 in stacks), key 0x94
- setup 'PZL #10 Operation Market: Arnhem': 52 pieces (52 self-positioned, 52 in stacks), key 0x73
- setup 'PZL #11 Operation Garden: Anticlimax': 122 pieces (122 self-positioned, 122 in stacks), key 0xc9
- setup 'PZL #12 Prelude: The Saar': 93 pieces (93 self-positioned, 93 in stacks), key 0x90
- setup 'PZL #13 Fortified Goose Egg': 180 pieces (180 self-positioned, 180 in stacks), key 0x2b
- setup 'PZL #14 Bulge: Thrust': 75 pieces (75 self-positioned, 75 in stacks), key 0x32
- setup 'PZL #15 Elsenborn Ridge': 120 pieces (120 self-positioned, 120 in stacks), key 0xbb
- setup 'PZL #16 Bastonge: Prelude': 54 pieces (54 self-positioned, 54 in stacks), key 0xd0
- setup 'PZL #17 Turning Point: Celles': 153 pieces (153 self-positioned, 153 in stacks), key 0x29
- setup 'PZL #18 Bastonge: Siege': 118 pieces (118 self-positioned, 118 in stacks), key 0x75
- setup "PZL #19 Patton's Counter Offensive": 190 pieces (190 self-positioned, 190 in stacks), key 0x8c
- setup 'PZL #20 Remagen Bridge': 28 pieces (28 self-positioned, 28 in stacks), key 0x4d
- no terrain metadata (normal — terrain is not a Tier-0 item)
- spec skeleton -> C:\VassalArnhem\games\panzerblitz-panzer-leader\game.ingest.json

## What didn't (and why)

- game.json already exists in C:\VassalArnhem\games\panzerblitz-panzer-leader — wrote game.ingest.json instead (NOT clobbering a curated spec)

## Grid

```json
{
 "orient": "flat",
 "dx": 52.0,
 "dy": 60.0,
 "x0": -2.0,
 "y0": 30.0,
 "stagger": true,
 "stagger_sign": 1,
 "odd_row_carry": 1,
 "provenance": "hexgrid-direct (flat-top mapping validated on Westwall/Arnhem); module numbering: first=H hType=A vType=N hOff=0 vOff=-2 stagger=false \u2014 hex LABELS unverified, geometry is what matters for Tier 0",
 "hexnum_digits": 2
}
```
- detection: **hexgrid**
- hex geometry is what Tier-0 needs; printed hex LABELS are unverified until checked against a map anchor.

## Setups

- 'PZB #1 White Russia': 47 pieces, 47 in stacks, kinds {'report': 35, 'label': 11, 'rotate': 1}
- 'PZB #2 Nikopol': 60 pieces, 60 in stacks, kinds {'report': 59, 'rotate': 1}
- 'PZB #3 Vyazma': 51 pieces, 51 in stacks, kinds {'report': 50, 'rotate': 1}
- 'PZB #4 Minsk': 69 pieces, 69 in stacks, kinds {'report': 68, 'rotate': 1}
- 'PZB #5 Lutezh Bridgehead.': 68 pieces, 68 in stacks, kinds {'label': 11, 'report': 53, 'piece': 2, 'rotate': 1, 'emb2': 1}
- 'PZB #6 Dnieper River Crossing.': 68 pieces, 68 in stacks, kinds {'report': 63, 'piece': 2, 'label': 1, 'emb2': 1, 'rotate': 1}
- 'PZB #7 Kiev': 88 pieces, 88 in stacks, kinds {'report': 83, 'piece': 2, 'rotate': 1, 'emb2': 1, 'label': 1}
- 'PZB #8 Korsun Pocket': 125 pieces, 125 in stacks, kinds {'label': 25, 'report': 96, 'emb2': 1, 'piece': 2, 'rotate': 1}
- 'PZB #9 Stalino': 105 pieces, 105 in stacks, kinds {'report': 91, 'label': 10, 'piece': 2, 'emb2': 1, 'rotate': 1}
- 'PZB #10 Prochorovka': 113 pieces, 113 in stacks, kinds {'report': 107, 'piece': 2, 'label': 1, 'rotate': 2, 'emb2': 1}
- 'PZB #11 Unorganized Russian Position (Buchach)': 115 pieces, 115 in stacks, kinds {'report': 109, 'rotate': 2, 'label': 1, 'piece': 2, 'emb2': 1}
- 'PZB #12 Nikopol Bridgehead': 160 pieces, 160 in stacks, kinds {'report': 128, 'label': 28, 'piece': 2, 'rotate': 1, 'emb2': 1}
- 'PZL #1 Utah Beach': 42 pieces, 42 in stacks, kinds {'report': 35, 'rotate': 3, 'label': 3, 'piece': 1}
- 'PZL #2 Omaha Beach': 115 pieces, 115 in stacks, kinds {'report': 80, 'label': 24, 'rotate': 10, 'piece': 1}
- 'PZL #3 Gold Beach': 88 pieces, 88 in stacks, kinds {'report': 57, 'label': 22, 'rotate': 8, 'piece': 1}
- 'PZL #4 St. Lo': 78 pieces, 78 in stacks, kinds {'report': 73, 'piece': 1, 'label': 3, 'rotate': 1}
- 'PZL #5 Operation Goodwood': 127 pieces, 127 in stacks, kinds {'report': 122, 'label': 2, 'piece': 1, 'rotate': 2}
- 'PZL #6 The Reichswald': 78 pieces, 78 in stacks, kinds {'report': 73, 'piece': 1, 'rotate': 1, 'label': 3}
- 'PZL #7 Encirclement of Nancy': 67 pieces, 67 in stacks, kinds {'report': 63, 'label': 2, 'piece': 1, 'rotate': 1}
- 'PZL #8 Marieulles': 49 pieces, 49 in stacks, kinds {'report': 45, 'label': 2, 'rotate': 1, 'piece': 1}
- 'PZL #9 Operation Market: Nijmegen': 73 pieces, 73 in stacks, kinds {'report': 69, 'piece': 1, 'label': 2, 'rotate': 1}
- 'PZL #10 Operation Market: Arnhem': 52 pieces, 52 in stacks, kinds {'report': 48, 'rotate': 1, 'piece': 1, 'label': 2}
- 'PZL #11 Operation Garden: Anticlimax': 122 pieces, 122 in stacks, kinds {'report': 118, 'label': 2, 'piece': 1, 'rotate': 1}
- 'PZL #12 Prelude: The Saar': 93 pieces, 93 in stacks, kinds {'report': 89, 'label': 2, 'piece': 1, 'rotate': 1}
- 'PZL #13 Fortified Goose Egg': 180 pieces, 180 in stacks, kinds {'report': 175, 'label': 3, 'rotate': 1, 'piece': 1}
- 'PZL #14 Bulge: Thrust': 75 pieces, 75 in stacks, kinds {'report': 70, 'piece': 1, 'label': 2, 'rotate': 2}
- 'PZL #15 Elsenborn Ridge': 120 pieces, 120 in stacks, kinds {'report': 114, 'rotate': 2, 'piece': 1, 'label': 3}
- 'PZL #16 Bastonge: Prelude': 54 pieces, 54 in stacks, kinds {'report': 51, 'rotate': 1, 'piece': 2}
- 'PZL #17 Turning Point: Celles': 153 pieces, 153 in stacks, kinds {'report': 150, 'rotate': 1, 'piece': 2}
- 'PZL #18 Bastonge: Siege': 118 pieces, 118 in stacks, kinds {'report': 115, 'piece': 2, 'rotate': 1}
- "PZL #19 Patton's Counter Offensive": 190 pieces, 190 in stacks, kinds {'report': 187, 'piece': 2, 'rotate': 1}
- 'PZL #20 Remagen Bridge': 28 pieces, 28 in stacks, kinds {'report': 24, 'label': 1, 'piece': 2, 'rotate': 1}

---
*Generated by engine/ingest.py — every claim above was produced by running the tool against the module, not by hand.*