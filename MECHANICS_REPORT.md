# Mechanics classification - full library (module-derived signals)

Scope: 3204 dedup'd games with a harvested module (247 games had no readable module). Signals come from module buildFiles/zips ONLY - rules semantics live in rulebooks; scores mean "cheap to attempt + validatable-looking", never "rules verified" (spec #12). BGG mechanics taxonomy slots in when the API key arrives.

## Board-style families

| style | games |
|---|---|
| hex | 1498 (46%) |
| gridless-board | 777 (24%) |
| square | 493 (15%) |
| point-to-point | 417 (13%) |
| region-snap | 15 (0%) |
| none | 4 (0%) |

## The hex conversion funnel (engine-today lane)

| stage | games | % of hex |
|---|---|---|
| hex grid | 1498 | 100% |
| + bundled setup(s) | 942 | 62% |
| + dice button(s) | 648 | 43% |
| + chart window(s) (CRT candidates) | 467 | 31% |
| + bundled rules PDF (gate 1 free) | 78 | 5% |

## Rules availability (pre-screen gate 1, pre-acquisition-sweep)

| grade | games | note |
|---|---|---|
| bundled PDF | 447 (13%) | gate 1 passes for free |
| html help in module | 51 (1%) | often full rules, needs eyeballing |
| unknown | 2706 (84%) | acquisition sweep / BGG to grade: publisher-free > obtainable > unobtainable |

## Style x scale (top scales)

| style | Tactical | Operational | Strategic | Abstract | ? | unknown | Miniatures | Mixed |
|---|---|---|---|---|---|---|---|---|
| hex | 519 | 604 | 157 | 54 | 70 | 30 | 17 | 20 |
| gridless-board | 193 | 139 | 156 | 164 | 33 | 31 | 22 | 17 |
| square | 102 | 33 | 119 | 146 | 21 | 31 | 20 | 7 |
| point-to-point | 71 | 58 | 128 | 106 | 18 | 12 | 7 | 5 |
| region-snap | 1 | 1 | 5 | 4 | 1 | 3 | 0 | 0 |
| none | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 0 |

## Card usage (gate 3: cards = future engine expansion)

| decks in module | games |
|---|---|
| 3+ decks (card-driven?) | 1396 (43%) |
| no decks | 1239 (38%) |
| 1-2 decks | 569 (17%) |

## Preliminary tier-target queue (top 60 by score)

Score = mechanics fit (40) + scenario (20) + rules (25) + validation signals (15). Full ranked list: `_meta/tier_targets.json` (local).

| # | title | score | style | setups | dice | charts | rules | scale | pilot |
|---|---|---|---|---|---|---|---|---|---|
| 1 | DNPS | 100 | hex | 4 | 1d6/2d6/3d6/4d6 | 1 | bundled | Tactical |  |
| 2 | Last Full Measure: The Battles of South Mountain | 100 | hex | 5 | 1d6 | 1 | bundled | Tactical |  |
| 3 | A Time for Trumpets: The Battle of the Bulge, December 1944 | 100 | hex | 11 | 1d6/1d6/1d6 | 9 | bundled | Operational |  |
| 4 | Last Full Measure: The Maryland Campaign | 100 | hex | 5 | 1d6 | 1 | bundled | Tactical |  |
| 5 | Last Full Measure: The Battle of Second Manassas | 100 | hex | 2 | 1d6 | 1 | bundled | Tactical |  |
| 6 | Last Full Measure: The Battles of Aldie, Middleburg, and Upperville | 100 | hex | 1 | 1d6 | 2 | bundled | Tactical |  |
| 7 | Star Fleet Battles Cadet Training Manual | 100 | hex | 12 | 1d6/2d6/3d6/4d6 | 4 | bundled | Tactical |  |
| 8 | 1914: Twilight in the East | 100 | hex | 7 | 2d6/1d6 | 2 | bundled | Operational |  |
| 9 | Last Full Measure: The Battle of Gettysburg (Second Edition) | 100 | hex | 5 | 1d6 | 1 | bundled | Tactical |  |
| 10 | Last Full Measure: The Battle of Cedar Mountain | 100 | hex | 3 | 1d6 | 2 | bundled | Tactical |  |
| 11 | Last Full Measure: The Battles of Kernstown | 100 | hex | 2 | 1d6 | 2 | bundled | Tactical |  |
| 12 | Last full measure: The Battle of Trevilians Station | 100 | hex | 2 | 1d6 | 2 | bundled | Tactical |  |
| 13 | Last Full Measure: The Battle of Shiloh | 100 | hex | 1 | 1d6 | 1 | bundled | Tactical |  |
| 14 | The Battle of the Bulge | 100 | hex | 1 | 1d6 | 2 | bundled | Operational |  |
| 15 | Horse & Musket: Annual Number 1 | 100 | hex | 40 | 1d6/1d10/2d10/3d10 | 4 | bundled | Tactical |  |
| 16 | Horse & Musket: Crucible of War | 100 | hex | 40 | 1d6/1d10/2d10/3d10 | 4 | bundled | Tactical |  |
| 17 | Horse & Musket: Sport of Kings | 100 | hex | 40 | 1d6/1d10/2d10/3d10 | 4 | bundled | Tactical |  |
| 18 | Pacific War | 100 | hex | 33 | 1d10 | 1 | bundled | Strategic |  |
| 19 | Panzer North Africa | 100 | hex | 31 | 1d100 | 2 | bundled | Tactical |  |
| 20 | War Galley | 100 | hex | 29 | 2d6/1d6/1d10 | 1 | bundled | unknown |  |
| 21 | DAK2 | 100 | hex | 21 | 1d6/2d6/3d6/2d6 | 2 | bundled | Operational |  |
| 22 | Hungarian Rhapsody: The Eastern Front in Hungary – October 1944-February 1945 | 100 | hex | 15 | 1d6/2d6/3d6/2d6 | 2 | bundled | Operational |  |
| 23 | Korea: The Forgotten War | 100 | hex | 13 | 1d6/2d6/3d6/2d6 | 2 | bundled | Operational |  |
| 24 | Enemy at the Gates | 100 | hex | 10 | 1d6/2d6/3d6/2d6 | 2 | bundled | Operational |  |
| 25 | The Blitzkrieg Legend: The Battle for France, 1940 | 100 | hex | 9 | 1d6/2d6/3d6/2d6 | 2 | bundled | Operational |  |
| 26 | Sicily: Triumph and Folly | 100 | hex | 8 | 1d6/2d6/3d6/2d6 | 2 | bundled | Operational |  |
| 27 | Under the Lily Banners | 100 | hex | 7 | 1d10 | 1 | bundled | Tactical |  |
| 28 | Hube's Pocket | 100 | hex | 6 | 1d6/2d6/3d6/2d6 | 2 | bundled | Operational |  |
| 29 | Sicily II | 100 | hex | 6 | 1d6/2d6/3d6/2d6 | 2 | bundled | Operational |  |
| 30 | The Arab-Israeli Wars | 100 | hex | 6 | 1d6/2d6/1d10 | 2 | bundled | Tactical |  |
| 31 | The Guns of August | 100 | hex | 6 | 1d6 | 1 | bundled | Operational |  |
| 32 | Tunisia | 100 | hex | 6 | 1d6/2d6/3d6/2d6 | 2 | bundled | Operational |  |
| 33 | Tunisia II | 100 | hex | 6 | 1d6/2d6/3d6/2d6 | 2 | bundled | Operational |  |
| 34 | Rostov '41: Race to the Don | 100 | hex | 4 | 1d6/2d6 | 3 | bundled | Operational |  |
| 35 | Fifth Corps | 100 | hex | 3 | 1d6 | 1 | bundled | Operational |  |
| 36 | Europa: Scorched Earth | 100 | hex | 2 | 1d6/1d6/2d6/1d100 | 1 | bundled | Operational |  |
| 37 | Luftwaffe | 100 | hex | 2 | 1d6 | 2 | bundled | Strategic |  |
| 38 | Talavera & Vimeiro | 100 | hex | 2 | 2d6/1d6 | 1 | bundled | Operational |  |
| 39 | Battle for Galicia, 1914 | 100 | hex | 1 | 1d6/2d6 | 1 | bundled | Operational |  |
| 40 | D-Day (2nd Ed) | 100 | hex | 1 | 1d6 | 1 | bundled | Operational |  |
| 41 | Pirates of the Spanish Main | 96 | hex | 3 | 1d2700/1d2700 | 1 | bundled | Tactical |  |
| 42 | La Bataille d'Austerlitz | 96 | hex | 2 | 1d6/2d6 | 2 | bundled | Tactical |  |
| 43 | Into the Woods: The Battle of Shiloh | 96 | hex | 13 | 1d10 | 1 | bundled | Tactical |  |
| 44 | Invasion: Malta | 96 | hex | 4 | 1d10/1d10 | 2 | bundled | Operational |  |
| 45 | Rise and Decline of the Third Reich 4th Edition (PBEM) | 96 | hex | 1 | 1d6/2d6 | 1 | bundled | ? |  |
| 46 | Case Blue / Guderian's Blitzkrieg II | 96 | hex | 36 | 1d6/2d6/3d6/2d6 | 3 | bundled | Operational |  |
| 47 | Dragonlance | 96 | hex | 17 | 2d4/1d6/2d6/1d10 | 5 | bundled | Strategic |  |
| 48 | Dragons of Glory | 96 | hex | 17 | 2d4/1d6/2d6/1d10 | 5 | bundled | Strategic |  |
| 49 | Beyond the Rhine | 96 | hex | 10 | 1d6/2d6/3d6/2d6 | 2 | bundled | Operational |  |
| 50 | The Third Winter: The Battle for the Ukraine September 1943-April 1944 | 96 | hex | 9 | 1d6/2d6/3d6/2d6 | 3 | bundled | Operational |  |
| 51 | Baltic Gap | 96 | hex | 8 | 1d6/2d6/3d6/2d6 | 2 | bundled | Operational |  |
| 52 | Valley of Tears: The Yom Kippur War, 1973 | 96 | hex | 8 | 1d6/2d6/1d6/2d6 | 5 | bundled | Operational |  |
| 53 | Arracourt | 96 | hex | 6 | 1d6/2d6/1d6/2d6 | 4 | bundled | Operational |  |
| 54 | By Swords & Bayonets (Great Battles of the American Civil War) | 96 | hex | 6 | 1d10 | 1 | bundled | ? |  |
| 55 | Reluctant Enemies: Operation Exporter – The Commonwealth Invasion of Lebanon & Syria, June-July, 1941 | 96 | hex | 2 | 1d6/2d6/3d6/2d6 | 2 | bundled | Operational |  |
| 56 | Torch | 96 | hex | 2 | 1d6/2d6/1d6/2d6 | 3 | bundled | Operational |  |
| 57 | Great War _The Fall of the Alicorn_EAW | 96 | hex | 1 | 1d6 | 5 | bundled | ? |  |
| 58 | Luzon: Race for Bataan | 96 | hex | 1 | 1d6/2d6/3d6/2d6 | 2 | bundled | Operational |  |
| 59 | Highway to the Reich: Operation Market-Garden 17-26 September 1944 – 2nd Edition | 93 | hex | 7 | - | 1 | bundled | Tactical |  |
| 60 | Russian Front | 93 | hex | 6 | - | 1 | bundled | Operational |  |

Pilot coverage check: 26 of the 26 pilot games matched in the dedup'd set; 0 of them land in the top 100 - the pilot is calibration for exactly this queue.
