# vassalengine.org library census — 2026-07-08

Metadata census of the complete VASSAL module library, taken via the library's
public JSON API (`engine/census.py`; sequential, identified, rate-limited).
No modules were downloaded for this census — every number below comes from the
library's own catalog data. 3,557 projects queried, **0 API errors**.

## Size

| | |
|---|---|
| Projects in the library | **3,557** |
| Projects with a downloadable `.vmod` | **3,315** (242 are placeholders/tools/board-only) |
| One main `.vmod` per game (newest release) | **85.0 GB** |
| Everything (all versions, extensions, maps, PDFs) | **274.4 GB** |

A full one-module-per-game mirror is 85 GB — trivially storable; the constraint
on a whole-library conversion study is ingest runtime, not disk or bandwidth.

## Age (year of each game's newest main-module release)

The library is alive, not a museum: **54% of games (1,790) had their current
module released 2020–2026**. The old tail is real but bounded — 398 games
(12%) are frozen at 2010 or earlier (these are also where pre-3.x save-format
dialects live; the ingest tool already normalizes the ones met so far).

```
<=2010: 398   2011-2014: 528   2015-2019: 599
2020: 222   2021: 354   2022: 217   2023: 265
2024: 288   2025: 259   2026 (half-year): 185
```

## What the library is (top tags, per the library's own metadata)

- **Era:** WWII 813, Gunpowder 340, Fantasy 305, Modern 199, Future 188,
  Ancient 177, Contemporary 175, Modern Warfare 173, Napoleonic 169,
  Medieval 166, WWI 125
- **Scale:** Tactical ~1,000, Operational ~900, Strategic ~600, Abstract ~525
- **Topic:** Western Front 229, Science Fiction 207, Eastern Front 200,
  American Civil War 181, Napoleonic Wars 163, Naval 109, Politics 69

Hex-and-counter wargames (tactical/operational/strategic WWII+historical) are
the library's overwhelming center of mass — which is the ingest tool's home
turf (see SCORECARD.md: 9/26 pilot modules convert FULL today, runtime-verified,
with point-to-point/area-map support identified as the single biggest unlock).

## Next (pending authorization)

`python engine/census.py download` mirrors the 3,315 main modules (85 GB,
resumable, sha256-verified, rate-limited) into `C:\VassalLibrary\modules\`;
then `ingest.py` over the mirror turns this census into hard conversion-rate
statistics by category and age.
