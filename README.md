# VALOR Engine — classic board wargames, playable on your PC

**VALOR turns classic hex-and-counter wargames into computer games.** The
map, the counters, the rules and the combat tables are all built in. You move
your units, the computer applies the rules, rolls the dice and keeps score.
Play against a computer opponent, against a friend on the same PC, or watch
two computer players fight it out.

No rulebook lookups in the middle of a turn. Legal moves light up on the map,
and the built-in Rules panel explains any rule with its rulebook reference.

## Get it

- **Quiver Launcher:** find **VALOR Engine (for VASSAL games)** in the
  catalog and click install:
  https://quiverlauncher.com/apps/valor-engine-for-vassal-games
- **Direct download (Windows):** get the latest zip from the
  [Releases page](https://github.com/DrEvil-TitaniumHelix/vsav-engine/releases/latest),
  unzip it, and double-click `Legality Engine for VASSAL.exe`.
- **In your browser, nothing to install:** https://master.vassal-test.pages.dev

**Watch it play:** https://www.youtube.com/watch?v=Afomvk0LjU8

## First run: bring your own game module

VALOR ships **no game art**. Each game uses the free VASSAL module for that
game, which you download yourself from the VASSAL library. You do this once
per game.

1. Start the app. Every game shows **Needs your module**.
2. Pick a game. Its card shows the exact module file it needs and a link to
   the library page.
3. Download that `.vmod` file from the link.
4. Back in the app, choose the file you downloaded.
5. The card turns **Ready**. Click it and play.

## The games

| Game | Publisher | What it is | Module page |
|---|---|---|---|
| **Afrika Korps** | Avalon Hill, 1964 | The full North Africa campaign: supply, fortresses, Rommel | [library](https://vassalengine.org/library/projects/Afrika_Korps_Classic_Avalon_Hill) |
| **Blue & Gray: Chickamauga** | SPI, 1975 | The classic Civil War battle, all 15 turns | [library](https://vassalengine.org/library/projects/Blue__Gray_Four_American_Civil_War_Battles) |
| **Westwall: Arnhem** | SPI, 1976 | Operation Market-Garden: airborne drops, bridges, engineers | [library](https://vassalengine.org/library/projects/Westwall_Four_Battles_to_Germany) |
| **Tobruk** | Avalon Hill, 1975 | Tank-against-tank firefights in the desert | [library](https://vassalengine.org/library/projects/Tobruk_Tank_Battles_in_North_Africa_1942) |
| **Austerlitz** | GMT, 2000 | Napoleon's greatest victory: command chits, cavalry charges | [library](https://vassalengine.org/library/projects/Austerlitz_clanmacrae) |
| **The Siege of Jerusalem** | Avalon Hill, 1989 | The Roman assault of AD 70: siege towers, rams, ladders | [library](https://vassalengine.org/library/projects/The_Siege_of_Jerusalem) |
| **Napoleon at Waterloo** (2nd Edition) | Stephen Oliver's edition of the SPI classic | The famous introductory wargame | [library](https://vassalengine.org/library/projects/napoleon_at_waterloo_2nd_ed_stephen_oliver) |

The exact file name for each game is shown in the app and listed in
[RELEASE_README.md](RELEASE_README.md).

## What you get in every game

- **The whole game, with the rules built in.** Movement, combat, supply,
  reinforcements and victory conditions are all handled for you.
- **A computer opponent.** Each seat can be you or the computer, in any
  combination. Several games also have a stronger, trained opponent.
- **Honest dice.** The computer rolls every die and keeps a complete record
  of the game, so both sides play by the same rules.
- **A Rules panel.** Searchable rules summary, full credits for the original
  designers and module makers, and notes on known errors in the printed game.
- **Undo.** Take back a mistake.

## Windows will probably warn you the first time

The app is not code-signed, so Windows may show "Windows protected your PC".
Click **More info**, then **Run anyway**. If your antivirus quarantines the
file, restore it or add an exception. If you are not comfortable doing that,
use the browser version instead.

## Problems or ideas?

Open an issue: https://github.com/DrEvil-TitaniumHelix/vsav-engine/issues

Tell us the version number shown at the bottom of the game menu and what you
were doing when it went wrong.

## Want your favorite game added?

See [ENCODING_GUIDE.md](ENCODING_GUIDE.md) for how a game gets encoded, or
open an issue and name the game.

## For developers

How the engine works, how to run from source and how to run the test suite:
[DEVELOPERS.md](DEVELOPERS.md).

## Credits

By **DrEvil / Titanium Helix**. Code is MIT licensed.

VALOR exists because the VASSAL community spent thirty years digitizing these
games. Each game's Rules panel credits the original designers, the publisher
and the people who made its VASSAL module.

- **Fabian Schaffert** ([devmapal](https://github.com/devmapal)) contributed
  area-map support.

## Legal

All games are © their respective rights holders. This project ships none of
their material: no maps, no counters, no rulebooks. You supply your own
module. Not affiliated with or endorsed by VASSAL or any game publisher.
