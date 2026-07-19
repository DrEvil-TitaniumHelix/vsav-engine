"""
server.py - Local board UI backend. Game-agnostic: launch with --game <dir>.

Serves the game's map + counters and exposes the spec-driven engine over HTTP:
  GET  /api/state              board state + game descriptor + move/pass progress
  GET  /api/legal?id=&whole=   legal destination hexes for a piece or its whole stack
  POST /api/move               {id, dest, whole} -> applies move, writes the work save
  POST /api/pass               {id, whole}       -> marks unit(s) passed
  POST /api/reset              restore the work save from the game's setup save
  GET  /gasset/map             the game's map image
  GET  /gasset/counters/<n>    a counter image

The work save is live\\game_<game>.vsav — VASSAL can open it at any time; the AI
plays through the same file. All rules semantics come from games/<game>/game.json.

Run:  python ui\\server.py [--game <dir>] [--port 8641]
"""
import argparse, http.server, json, os, shutil, struct, sys, urllib.parse

def _base_dir():
    """Read-only asset root (games/, ui/, engine/): the PyInstaller one-file
    bundle when frozen, else the repo checkout."""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


ROOT = _base_dir()
HERE = os.path.join(ROOT, "ui")


def _live_dir():
    """Writable per-game state (work .vsav, JSONL logs, tier/facing sidecars).
    Must survive app exit and NEVER live inside the read-only bundle, so a
    packaged build writes to %LOCALAPPDATA%\\TheVassal\\live; from source it
    stays live\\ in the repo (unchanged)."""
    if getattr(sys, "frozen", False):
        base = os.path.join(os.environ.get("LOCALAPPDATA",
                            os.path.expanduser("~")), "TheVassal", "live")
    else:
        base = os.path.join(ROOT, "live")
    os.makedirs(base, exist_ok=True)
    return base


LIVE = _live_dir()
sys.path.insert(0, os.path.join(ROOT, "engine"))
import board as board_mod  # noqa: E402
import gamespec  # noqa: E402
import gamestate as gs_mod  # noqa: E402
import strategic as strat_mod  # noqa: E402
import bluegray as bg_mod  # noqa: E402
import westwall as ww_mod  # noqa: E402
import napoleonic as nap_mod  # noqa: E402
import ai as ai_mod  # noqa: E402
import ai_strategic as sai_mod  # noqa: E402
import ai_bluegray as bai_mod  # noqa: E402
import ai_westwall as wai_mod  # noqa: E402
import ai_napoleonic as nai_mod  # noqa: E402
import pbm as pbm_mod  # noqa: E402
import plans as plans_mod  # noqa: E402
import champion as champ_mod  # noqa: E402
import salvo as salvo_mod  # noqa: E402
import undo as undo_mod  # noqa: E402

SG_FAMILY = ("strategic", "bluegray", "westwall", "napoleonic")


def sg_earned_tier(scen_mode, spec):
    """Mirror of each SG-family engine's earned-tier logic (spec #13).
    napoleonic: validated melee tables => tier 2, plus policy AI => 3
    (napoleonic.py _resolve_tier); others: combat block => 2, plus
    policy AI => 3."""
    if scen_mode == "napoleonic":
        melee = bool((spec.get("combat_tables") or {}).get("melee"))
        return (3 if spec.get("policy_ai") else 2) if melee else 1
    return (3 if spec.get("policy_ai") else 2) if spec.get("combat") else 1


def sg_ai_module():
    """The policy-AI module matching the loaded strategic-family gate."""
    return {"bluegray": bai_mod, "westwall": wai_mod,
            "napoleonic": nai_mod}.get(SCEN_MODE, sai_mod)


def sg_over():
    """Game-over for any SG-family gate (napoleonic computes it in
    flow(); the others keep it in state)."""
    if SCEN_MODE == "napoleonic":
        return SG.flow()["over"]
    return SG.s["over"]

VERSION = "0.1.0-beta"  # shown in-app so a tester's bug report names the build

GAME_OBJ = None   # gamespec.Game
GAME_SLUG = None  # basename of the loaded game dir (menu key)
TG = None         # gamestate.TacticalGame when the game spec names a scenario
SG = None         # strategic.StrategicGame when the scenario is mode=strategic
WORK = None       # working .vsav path
SCEN_PATH = None  # scenario file (None = the game has no gate to offer)
SCEN_MODE = None  # "strategic" | "tactical" | None
TIER = 0          # tier the server is RUNNING at (engine-level selection)
TIER_EARNED = 0   # highest tier the game has earned (spec #13)
TIER_CHOICES = [0]
AI_STEP = None    # sai_mod.TurnStepper — one AI action per /api/ai_step call
done = {}         # piece id -> "moved" | "passed"   (per server run; POC scope)
facing = {}       # piece id -> facing index (sidecar JSON next to the work save;
                  # VASSAL rotate-state write-through pending a save-diff experiment)


def facing_path():
    return WORK + ".facing.json"


def tier_path():
    return WORK + ".tier.json"


def load_tier():
    """Active tier: persisted sidecar, clamped to what the game has earned."""
    if os.path.exists(tier_path()):
        t = json.load(open(tier_path())).get("tier")
        if t in TIER_CHOICES:
            return t
    return TIER_EARNED


def save_tier():
    with open(tier_path(), "w") as f:
        json.dump({"tier": TIER}, f)


def build_gate():
    """(Re)build the legality gate for the ACTIVE tier — tier selection is an
    engine-level function: tier 0 = no gate (V3-parity free play, the user is
    the umpire), tier 1 = movement/arrivals gate, tier 2+ = full gate."""
    global TG, SG
    TG = SG = None
    if not SCEN_PATH or TIER == 0:
        return
    if SCEN_MODE == "strategic":
        SG = strat_mod.StrategicGame(GAME_OBJ, SCEN_PATH,
                                     LIVE, tier=TIER)
    elif SCEN_MODE == "bluegray":
        SG = bg_mod.BlueGrayGame(GAME_OBJ, SCEN_PATH, LIVE, tier=TIER)
    elif SCEN_MODE == "westwall":
        SG = ww_mod.WestwallGame(GAME_OBJ, SCEN_PATH, LIVE, tier=TIER)
    elif SCEN_MODE == "napoleonic":
        SG = nap_mod.NapoleonicGame(GAME_OBJ, SCEN_PATH, LIVE, tier=TIER)
    else:
        TG = gs_mod.TacticalGame(GAME_OBJ, SCEN_PATH, LIVE)


def load_facing():
    global facing
    facing = {}
    if os.path.exists(facing_path()):
        facing = json.load(open(facing_path()))


def save_facing():
    with open(facing_path(), "w") as f:
        json.dump(facing, f)


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return struct.unpack("<HH", head[6:10])
    return struct.unpack(">II", head[16:24])


def fresh_board():
    if not os.path.exists(WORK):
        shutil.copy(GAME_OBJ.setup_save, WORK)
        done.clear()
    return board_mod.Board(WORK, GAME_OBJ)


def unit_view(u):
    g = GAME_OBJ
    a, d, m = g.stats(u["name"])
    v = dict(u, att=a, dfn=d, ma=m, onmap=g.on_map(u["col"], u["row"]),
             terrain=g.hex_terrain(u["col"], u["row"]),
             cls=g.unit_class(u["name"]),
             hexname=g.grid.display_name(u["col"], u["row"]),
             status=done.get(u["id"]),
             facing=facing.get(u["id"], 0) if g.facing else None)
    if TG:
        tu = TG.s["units"].get(u["id"])
        if tu:
            v.update(side=tu["side"], facing=tu["facing"], afv=tu["afv"],
                     K=tu["K"], M=tu["M"], F=tu["F"], ma=TG.budget(tu),
                     moved=tu["pid"] in TG.s["moved"],
                     pivoted=tu["pid"] in TG.s["pivoted"],
                     fired=tu["pid"] in TG.s["fired"],
                     acquired=TG.s["acquired"].get(tu["pid"]))
    if SG:
        su = SG.s["units"].get(u["id"])
        if su:
            v.update(side=su["side"])
            if SCEN_MODE == "napoleonic":
                v.update(facing=su["facing"], formation=su["formation"],
                         morale_state=su.get("morale_state", "good"),
                         sp=su["sp"], arm=su["arm"],
                         blown=su.get("blown", 0),
                         fired=su["pid"] in SG.s.get("fired", []))
                if su.get("dead"):
                    v.update(status="eliminated", onmap=False)
            if SG.on_map(su):
                v.update(col=su["col"], row=su["row"],
                         status="moved" if u["id"] in SG.s["moved"] else done.get(u["id"]))
                x, y = GAME_OBJ.grid.hex_to_pixel(su["col"], su["row"])
                v.update(x=x, y=y, hexnum=GAME_OBJ.grid.hexnum(su["col"], su["row"]),
                         hexname=GAME_OBJ.grid.display_name(su["col"], su["row"]),
                         terrain=g.hex_terrain(su["col"], su["row"]),
                         onmap=True)
            elif SCEN_MODE == "napoleonic":
                v.update(status="eliminated", onmap=False)
            else:                      # at sea: mirror keeps the last board spot
                v.update(status="at sea",
                         must_land=su.get("embark_turn", SG.s["turn"]) < SG.s["turn"])
        elif u["id"] in SG.s.get("dead", []):
            v.update(status="eliminated", onmap=False)
        else:
            v["status"] = "reserve"    # OOA track / markers: outside the gate
            e = SG.schedule.get(u["id"])
            if e:
                v["due"] = SG.turn_label(e["due"])
    return v


def flow_view():
    s = TG.s
    return dict(turn=s["turn"], turns=TG.turns, segment=s["segment"],
                mover=s["mover"], initiative=s["initiative"],
                movement_done=s["movement_done"], fire_done=s["fire_done"],
                over=s["over"], winner=s["winner"], vp=TG.victory(),
                seed=s["seed"], n=s["n"],
                first_player=TG.first_player, combat_first=TG.combat_first,
                bounds=TG.bounds, scenario=TG.scenario["name"],
                rules_scope=TG.scenario.get("rules_scope"))


def mirror_move(pid, col, row):
    """Reflect a gate-applied position change into the work .vsav so real
    VASSAL can open the same game."""
    b = fresh_board()
    b.move_piece_by_id(pid, GAME_OBJ.grid.hexnum(col, row))
    b.write(WORK)


def sync_mirror():
    """Diff-sync the work .vsav against the gate state: any on-map gate unit
    whose board position differs gets moved (covers captures, retreats,
    advances, substitutions, replacements, Rommel displacement — and undo,
    which rewinds positions arbitrarily — every side effect in one sweep)."""
    gate = SG or TG
    if not gate:
        return
    b = fresh_board()
    pos = {u["id"]: (u["col"], u["row"]) for u in b.units()}
    moved = False
    for u in gate.s["units"].values():
        if not gate.on_map(u):
            continue
        if pos.get(u["pid"]) not in (None, (u["col"], u["row"])):
            b.move_piece_by_id(u["pid"],
                               GAME_OBJ.grid.hexnum(u["col"], u["row"]))
            moved = True
    if moved:
        b.write(WORK)


# --- undo (engine/undo.py): one USER decision per press, window of 5 --------
def undo_blocked():
    """Undo is refused while a mailed/LLM match is attached: accepted
    prefixes STAND (protocol rule, same as PBM/SALVO import law)."""
    if pbm_mod.load_sidecar(LIVE, GAME_SLUG):
        return "play-by-mail match - accepted moves stand"
    if salvo_mod.load_sidecar(LIVE, GAME_SLUG):
        return "SALVO match - accepted moves stand"
    return None


def mark_undo(n_before, label):
    """Record an accepted USER gesture as an undo point. Called only from
    the endpoints a human drives (moves, panel actions, phase ends) - never
    from AI/PBM/SALVO paths, so 'undo' always means 'my last decision'."""
    if undo_blocked():
        return
    undo_mod.mark(LIVE, GAME_SLUG, n_before, label)


def undo_status():
    gate = SG or TG
    if not gate:
        return None
    st = undo_mod.status(LIVE, GAME_SLUG, gate.s["n"])
    st["blocked"] = undo_blocked()
    return st


def api_undo(body=None):
    """Undo the user's most recent decision: truncate the log to just before
    it (unwinding every AI reply and consequence after it) and replay the
    prefix — which re-verifies every verdict, die and state hash on the way.
    The cut tail is archived, never destroyed. Seeded dice ride the replay:
    repeating the same action after an undo gives the same result."""
    global AI_STEP
    gate = SG or TG
    if not gate:
        return dict(error="undo needs the rules gate (tier 1+)")
    blocked = undo_blocked()
    if blocked:
        return dict(error="undo is not available in a match: " + blocked)
    try:
        replayed, label = undo_mod.undo_once(GAME_OBJ, LIVE, GAME_SLUG,
                                             gate.log_path)
    except ValueError:
        return dict(error="nothing to undo", undo=undo_status())
    except undo_mod.replay_mod.ReplayMismatch as e:
        return dict(error=f"undo aborted - the log failed re-verification: {e}")
    gate.s = replayed.s
    if hasattr(gate, "_apply_bridge_state"):
        gate._apply_bridge_state()    # westwall: hexside truth derives from
        #                               state (demolitions), re-derive after
        #                               the swap rather than trust the temp
        #                               replay's shared-terrain side effect
    gate.save()
    AI_STEP = None
    done.clear()
    sync_mirror()
    out = dict(ok=True, undone=label, undo=undo_status(),
               flow=SG.flow() if SG else flow_view())
    return out


def api_action(body):
    side, action = body["side"], body["action"]
    n0 = TG.s["n"]
    r = TG.submit(side, action)
    if r["verdict"]["legal"]:
        mark_undo(n0, action.get("type") or "action")
        if action.get("type") in ("move", "reverse"):
            u = TG.unit(action["unit"])
            mirror_move(u["pid"], u["col"], u["row"])
    r["flow"] = flow_view()
    return r


def api_ai_turn(body):
    side = body["side"]
    s = TG.s
    if s["over"]:
        return dict(error="game is over", flow=flow_view())
    steps = []
    if s["segment"] == "movement" and s["mover"] == side:
        steps = ai_mod.take_movement_segment(TG, side)
        for st in steps:
            if st["verdict"]["legal"] and st["action"].get("type") in ("move", "reverse"):
                u = TG.unit(st["action"]["unit"])
                mirror_move(u["pid"], u["col"], u["row"])
    elif s["segment"] == "combat" and s["initiative"] == side and side not in s["fire_done"]:
        steps = ai_mod.take_one_fire(TG, side)
    return dict(steps=steps, flow=flow_view())


def api_log_tail(qs):
    n = int(qs.get("n", ["40"])[0])
    if not os.path.exists(TG.log_path):
        return dict(entries=[])
    lines = open(TG.log_path, encoding="utf-8").read().splitlines()
    return dict(entries=[json.loads(l) for l in lines[-n:]])


def api_new_game(body):
    global done
    TG.new_game(body.get("seed"))
    undo_mod.clear(LIVE, GAME_SLUG)
    done = {}
    if os.path.exists(WORK):
        os.remove(WORK)
    fresh_board()
    return dict(ok=True, flow=flow_view())


def game_descriptor():
    g = GAME_OBJ
    w, h = png_size(g.assets["map"])
    return dict(
        name=g.name,
        slug=GAME_SLUG,
        map_url="/gasset/map", map_w=w, map_h=h,
        counters_url="/gasset/counters/",
        counter_px=g.spec.get("ui", {}).get("counter_px", 75),
        grid=dict(dx=g.grid.dx, dy=g.grid.dy, orient=g.grid.orient,
                  x0=g.grid.x0, y0=g.grid.y0, offset_parity=g.grid.offset_parity),
        sides=[dict(id=s, label=((TG or SG).scenario["game"].get("side_labels", {}) if (TG or SG) else {}).get(
                        s, g.spec["sides"].get("labels", {}).get(s, s)))
               for s in g.side_order],
        facing=g.facing,
        tier=dict(active=TIER, earned=TIER_EARNED, choices=TIER_CHOICES,
                  labels={0: "Tier 0 — free play, you are the umpire",
                          1: "Tier 1 — movement & arrivals enforced",
                          2: "Tier 2 — combat enforced (full gate)",
                          3: "Tier 3 — full gate + AI opponent"}),
        source_defects=g.spec.get("source_defects"),
        credits=g.spec.get("credits"),
        guide=g.spec.get("guide"),
        rules_docs=g.spec.get("rules_docs"),
    )


# --- multi-game menu: the release bundles several games behind one engine ---
# Curated tester menu (order = display order, simplest -> most complex per
# Bruce 2026-07-17). Games not in this list are still loadable via --game /
# /api/load_game, but the menu shows these. Keep in sync with the release scope.
RELEASE_GAMES = ["tobruk", "blue-and-gray-chickamauga", "westwall-arnhem",
                 "afrika-korps-classic-ah", "austerlitz-gmt"]


def game_client(scen_mode, has_scen):
    """Which front-end HTML plays this game: strategic + free-play games use the
    generic index.html; the tactical family (own scenario, AP-fire) uses
    tactical.html. Mirrors the '/' routing that ships today."""
    if scen_mode in SG_FAMILY:
        return "index.html"
    if has_scen:
        return "tactical.html"
    return "index.html"


def _game_assets_ok(gdir):
    """Can this game folder actually serve its art on THIS machine? Dev specs
    point outside the repo (module extracts); a fresh clone doesn't have those."""
    gj = os.path.join(gdir, "game.json")
    if not os.path.isfile(gj):
        return False
    try:
        spec = json.load(open(gj, encoding="utf-8"))
    except Exception:
        return False
    m = (spec.get("assets") or {}).get("map")
    if not m:
        return True                     # nothing external to resolve
    p = m if os.path.isabs(m) else os.path.join(gdir, m)
    return os.path.exists(p)


def game_dir(slug):
    """Resolve a slug to a runnable game folder. Prefer the dev folder
    (games/<slug>, full module extracts) when its assets resolve; otherwise the
    self-contained bundle (games_bundled/<slug>) that ships in the repo, so a
    fresh clone plays the release games out of the box."""
    dev = os.path.join(ROOT, "games", slug)
    if _game_assets_ok(dev):
        return dev
    bun = os.path.join(ROOT, "games_bundled", slug)
    if _game_assets_ok(bun):
        return bun
    return dev


# Friendly system names for the menu tags (engine families).
MODE_TAG = {"tactical": "Tactical armor", "strategic": "Strategic hex & counter",
            "bluegray": "Strategic hex & counter", "westwall": "Strategic hex & counter",
            "napoleonic": "Napoleonic command", "free": "Free play"}
TIER_TAG = {0: "Free play", 1: "Movement rules", 2: "Movement + combat rules",
            3: "Full rules"}
# Champion (trained, graduated) AIs are WIRED: the interactive AI seat and
# the PBM responder play the playbook champion wherever one exists
# (engine/champion.py), so "Advanced AI" is now the truth for those games.
CHAMPION_WIRED = True


def game_tags(gdir, spec, scen_mode, earned):
    """Capability tags for the selection pages — one implementation, both
    menus (app + browser demo). Every tag states something the build actually
    does; 'Advanced AI' appears only where the trained champion IS the
    opponent behind the button. A playbook whose training runs kept the
    baseline (Austerlitz: two evolutionary attacks, 92k games, no genome
    graduated) shows 'Advanced AI pending' (Bruce 2026-07-19): honest news
    — the shipped policy is still the reigning champion of its own decision
    space, and the upgrade remains open."""
    tags = [dict(label=TIER_TAG.get(earned, f"Tier {earned}"), kind="tier")]
    if earned >= 3:
        champion = champ_mod.genome(gdir) is not None
        tags.append(dict(
            label="Advanced AI" if champion
            else "Advanced AI pending" if champ_mod.validated(gdir)
            else "Basic AI",
            kind="ai"))
    m = MODE_TAG.get(scen_mode or "free")
    if m and earned > 0:
        tags.append(dict(label=m, kind="mode"))
    if scen_mode in pbm_mod.PBM_MODES:
        tags.append(dict(label="Play by mail", kind="feature"))
    if scen_mode in salvo_mod.SALVO_MODES:
        tags.append(dict(label="Hook up your LLM", kind="feature"))
    if spec.get("source_defects"):
        tags.append(dict(label="Defect register", kind="feature"))
    return tags


def game_meta(slug):
    """Cheap menu metadata for one game — reads game.json (+ its scenario's mode)
    only, WITHOUT constructing the engine or touching the loaded-game globals."""
    gdir = game_dir(slug)
    spec = json.load(open(os.path.join(gdir, "game.json"), encoding="utf-8"))
    scen = spec.get("scenario")
    scen_mode = has_scen = None
    earned, choices = 0, [0]
    if scen:
        has_scen = True
        scen_mode = json.load(open(os.path.join(gdir, scen),
                                   encoding="utf-8")).get("mode")
        if scen_mode in SG_FAMILY:
            earned = sg_earned_tier(scen_mode, spec)
            choices = list(range(earned + 1))
        else:
            earned, choices = 3, [0, 3]
    mode = scen_mode or ("tactical" if has_scen else "free")
    return dict(slug=slug, name=spec.get("name", slug),
                mode=mode,
                client=game_client(scen_mode, has_scen),
                tier=dict(earned=earned, choices=choices),
                tags=game_tags(gdir, spec, mode, earned),
                blurb=spec.get("blurb") or spec.get("description"))


def current_slug():
    return GAME_SLUG


def menu_art_path(slug):
    """Resolve a game's selection-card graphic: spec assets.menu_art (the
    module's own box/splash art, staged locally), else map_thumb, else the map.
    BYO posture unchanged — these paths point at the user's own module copy on
    this machine; nothing is bundled or committed."""
    gdir = game_dir(slug)
    try:
        spec = json.load(open(os.path.join(gdir, "game.json"), encoding="utf-8"))
    except Exception:
        return None
    a = spec.get("assets") or {}
    for key in ("menu_art", "map_thumb", "map"):
        p = a.get(key)
        if p:
            p = p if os.path.isabs(p) else os.path.join(gdir, p)
            if os.path.isfile(p):
                return p
    return None


def api_games():
    """List the games in the tester menu. If a non-menu game is currently
    loaded (e.g. dev ran --game arnhem), include it so it's still playable."""
    slugs = list(RELEASE_GAMES)
    cur = current_slug()
    if cur and cur not in slugs:
        slugs.append(cur)
    games = []
    for slug in slugs:
        try:
            m = game_meta(slug)
            m["current"] = (slug == cur)
            games.append(m)
        except Exception as e:
            games.append(dict(slug=slug, name=slug, error=str(e)))
    return dict(games=games, current=cur, version=VERSION)


def api_load_game(body):
    """Switch the engine onto another game at runtime (the in-app picker).
    Loads from disk (per-game state is file-backed), returns the client the
    menu should navigate to."""
    slug = body.get("slug")
    gdir = game_dir(slug) if slug else ""
    if not slug or not os.path.isfile(os.path.join(gdir, "game.json")):
        return dict(error=f"unknown game: {slug!r}")
    tier = body.get("tier")
    try:
        load_game(gdir, tier=tier)
    except ValueError as e:
        return dict(error=str(e))
    return dict(ok=True, slug=slug, client=game_client(SCEN_MODE, bool(SCEN_PATH)),
                game=game_descriptor())


def game_tables():
    """Combat tables for the loaded game, transcribed from the rulebook and
    rendered in the UI (not the module's PNG scans) — the same encoded data the
    gate resolves combat on. Generic grid schema so the client renders any game:
      {title, cite, columns[], rows[[...]], legend[{code,text}], notes[]}
    columns[0] is the row-header label; each row's cell 0 is its header."""
    g = GAME_OBJ
    if not g:
        return []
    tables = []

    # Strategic CRT (Afrika Korps and kin): odds columns x die rows.
    combat = g.spec.get("combat")
    if combat and (combat.get("crt") or {}).get("columns"):
        crt = combat["crt"]
        cols = ["die \\ odds"] + list(crt["columns"])
        rows = [[str(die)] + list(cells) for die, cells in crt["rows"].items()]
        legend = [{"code": k, "text": v} for k, v in crt.get("results", {}).items()]
        notes = [n for n in (
            (combat.get("odds") or {}).get("cite"),
            combat.get("defense_double_cite"),
            (combat.get("attack_supply") or {}).get("cite"),
        ) if n]
        tables.append(dict(title="Combat Results Table", cite=crt.get("cite"),
                           columns=cols, rows=rows, legend=legend, notes=notes))

    # Differential terrain-integrated CRT (Westwall family): each terrain row
    # carries its own differential brackets, all reading the same die rows
    # from the LEFT (engine westwall._column_pos / crt_result).
    if combat and (combat.get("crt") or {}).get("terrain_columns"):
        crt = combat["crt"]
        tc, dr = crt["terrain_columns"], crt["die_rows"]
        width = max(len(v) for v in dr.values())
        rows = [[t + "  (differential)"] + list(v) + [""] * (width - len(v))
                for t, v in tc.items()]
        rows += [["die " + d] + list(v) for d, v in dr.items()]
        legend = [{"code": k, "text": v} for k, v in crt.get("results", {}).items()]
        alias = crt.get("terrain_alias") or {}
        notes = ([f"Find your terrain's row, then the column bracketing your "
                  f"attack differential (columns count from that row's left); "
                  f"read down to the die row."]
                 + ([f"Terrain read as: "
                     + "; ".join(f"{k} → {v}" for k, v in alias.items())]
                    if alias else [])
                 + [n for n in (crt.get("alias_cite"), crt.get("bounds_cite")) if n])
        tables.append(dict(
            title="Combat Results Table (differential, terrain-integrated)",
            cite=crt.get("cite"), columns=[""] + ["c%d" % (i + 1) for i in range(width)],
            rows=rows, legend=legend, notes=notes))

    # Napoleonic family (Austerlitz and kin): the game.json combat_tables
    # block — fire, artillery range, morale, fatigue, melee. Rendered
    # cell-for-cell from the validated transcription.
    ct = g.spec.get("combat_tables")
    if ct:
        def nice(k):
            if k.startswith("le_"):
                return "≤ " + k[3:].replace("_", " ")
            if k.startswith("ge_"):
                return "≥ " + k[3:].replace("_", " ")
            if k.startswith("above_"):
                return "exceeds by " + k[6:].replace("_plus", "+").replace("_", "-")
            return k.replace("_plus", "+").replace("_", " ")

        fc = ct.get("fire_table_columns") or {}
        classes = [c for c in fc if c != "note"]
        if classes:
            ratings = sorted({r for c in classes for r in fc[c]}, key=int)
            legend = [{"code": c, "text": ", ".join((ct.get("fire_defense_classes")
                                                     or {}).get(c, []))}
                      for c in classes]
            tables.append(dict(
                title="Fire Table — fire column [8.1.8]",
                cite=(fc.get("note") or "") + " " + (ct.get("cite") or ""),
                columns=["rating \\ class"] + classes,
                rows=[[r] + [str(fc[c].get(r, "—")) for c in classes]
                      for r in ratings],
                legend=legend,
                notes=[f"{nice(k)}: {v}" for k, v in
                       (ct.get("fire_rating_adjustments") or {}).items()
                       if k != "cite"]
                    + [f"{nice(k)}: {v}" for k, v in
                       (ct.get("fire_column_modifiers") or {}).items()
                       if k != "cite"]))
        fr = ct.get("fire_results") or {}
        dice = [d for d in fr if d != "note"]
        if dice:
            ncol = max(len(fr[d]) for d in dice)
            tables.append(dict(
                title="Fire Table — results [8.1.8]",
                cite=fr.get("note"),
                columns=["die \\ column"] + [str(i + 1) for i in range(ncol)],
                rows=[[d] + [str(x) for x in fr[d]] for d in sorted(dice, key=int)],
                legend=[], notes=[]))
        ar = ct.get("artillery_range") or {}
        nations = [n for n in ar if n != "note"]
        if nations:
            bands = ["up2", "base", "down1", "down2"]
            rows = [[f"{n} {nice(gk)}"] + [str(gv.get(b, "—")) for b in bands]
                    for n in nations for gk, gv in ar[n].items()]
            tables.append(dict(
                title="Artillery Range Table [8.1.6]", cite=ar.get("note"),
                columns=["gun", "up 2", "base", "down 1", "down 2"],
                rows=rows, legend=[], notes=[]))
        mc = ct.get("morale_check") or {}
        if mc.get("results"):
            tables.append(dict(
                title="Morale Check Table [9.1]", cite=mc.get("note"),
                columns=["roll vs morale", "result"],
                rows=[[nice(k), str(v)] for k, v in mc["results"].items()],
                legend=[],
                notes=[f"DRM — {nice(k)}: {v}" for k, v in
                       (mc.get("drm") or {}).items()]))
        fe = ct.get("fatigue_effects") or {}
        levels = [k for k in fe if k != "note"]
        if levels:
            tables.append(dict(
                title="Fatigue Effects [13.0]", cite=fe.get("note"),
                columns=["army fatigue", "effects"],
                rows=[[nice(k),
                       "; ".join(f"{nice(ek)} {ev}" for ek, ev in fe[k].items())
                       or "no effect"] for k in levels],
                legend=[], notes=[]))
        me = ct.get("melee") or {}
        rt = me.get("result_table") or {}
        outcomes = [k for k in rt if k != "note"]
        if outcomes:
            def okey(k):
                if k.startswith("le_"):
                    return -99
                if k.startswith("ge_") or k.endswith("_plus"):
                    return 99
                try:
                    return int(k)
                except ValueError:
                    return 98
            cols = ["loser", "sp_lost", "morale", "other"]
            tables.append(dict(
                title="Melee Result Table [8.5]",
                cite=(rt.get("note") or "") + " " + (me.get("cite") or ""),
                columns=["modified die"] + [nice(c) for c in cols],
                rows=[[nice(k)] + [str(rt[k].get(c, "—")) for c in cols]
                      for k in sorted(outcomes, key=okey)],
                legend=[],
                notes=[f"DRM — {nice(k)}: {v}" for k, v in
                       (me.get("drm") or {}).items() if k != "note"]
                    + ["The full shock procedures (bayonet/assault/charge steps, "
                       "pre-shock checks, squares, pursuit, blown cavalry) are "
                       "enforced by the engine — see the Rules panel."]))

    # Tactical to-hit table (Tobruk and kin): weapon rows x range columns.
    cj = os.path.join(g.dir, "combat.json")
    if os.path.exists(cj):
        cd = json.load(open(cj, encoding="utf-8"))
        weapons = cd.get("weapons", {})
        users = {}
        for t in cd.get("afv_types", {}).values():
            tok = (t.get("counter_token") or "").replace("_", " ")
            users.setdefault(t.get("weapon"), []).append(tok)
        maxr = max((len(w.get("hpn_by_range", [])) for w in weapons.values()), default=0)
        cols = ["weapon  (range →)"] + [str(r) for r in range(1, maxr + 1)]
        rows = []
        for wk, w in weapons.items():
            hp = w.get("hpn_by_range", [])
            label = wk + (f"  ({', '.join(users[wk])})" if users.get(wk) else "")
            rows.append([label] + [str(x) for x in hp] + [""] * (maxr - len(hp)))
        mv = (cd.get("hpn_modifiers") or {}).get("target_moved", 1)
        cap = (cd.get("fire_initiation") or {}).get("max_unadjusted_hpn", 8)
        rof = "; ".join(f"{wk} fires {w.get('rof_initial')} "
                        f"{'die' if (w.get('rof_initial') or 0) == 1 else 'dice'} initially,"
                        f" {w.get('rof_acquired')} once the target is acquired"
                        for wk, w in weapons.items())
        notes = [
            "A hit needs the sum of the firer's dice (one per shot in its Rate of "
            "Fire) to reach the number shown at that range [I.F.1].",
            f"Add +{mv} to the number needed if the target moved this turn [I.F.1.b.2].",
            f"An AFV may not INITIATE fire where the unadjusted number exceeds {cap} "
            "unless the target already fired at it or shows its flank/rear [p.5 H].",
            "Rate of Fire — " + rof + ".",
        ]
        tables.append(dict(title="To-Hit Table (number needed, by range in hexes)",
                           cite="Tobruk rulebook pp.4-5 (module To-Hit chart)",
                           columns=cols, rows=rows, legend=[], notes=notes))
    return tables


def api_state():
    b = fresh_board()
    units = [unit_view(u) for u in b.units()]
    out = dict(units=units, game=game_descriptor(),
               notes=f"{GAME_OBJ.name} — spec-driven engine")
    if TG:
        out["flow"] = flow_view()
        out["notes"] = TG.scenario["name"]
    if SG:
        out["flow"] = SG.flow()
        out["notes"] = SG.scenario["name"]
    if SCEN_MODE in pbm_mod.PBM_MODES:
        out["pbm"] = pbm_status()
    if SCEN_MODE in salvo_mod.SALVO_MODES:
        out["salvo"] = salvo_status()
    if SG or TG:
        out["undo"] = undo_status()
    return out


def sg_stack_ids(pid):
    """Movable gate units stacked with pid (same hex, same side)."""
    u = SG.s["units"].get(pid)
    if not u:
        return [pid]
    return [v["pid"] for v in SG.s["units"].values()
            if v["side"] == u["side"] and (v["col"], v["row"]) == (u["col"], u["row"])
            and v["pid"] not in SG.s["moved"]
            and GAME_OBJ.unit_class(v["slot"]) != "markers"]


def api_legal_sg(qs):
    pid = qs["id"][0]
    whole = qs.get("whole", ["0"])[0] == "1"
    lm = SG.legal_moves(pid)
    if not lm["can_act"]:
        return dict(ma=0, dests=[], reasons=lm["reasons"])
    dests = {(d["col"], d["row"]): d for d in lm["dests"]}
    ma = lm["budget"]
    if whole:
        for mid in sg_stack_ids(pid):
            if mid == pid:
                continue
            lm2 = SG.legal_moves(mid)
            if not lm2["can_act"]:
                return dict(ma=0, dests=[], reasons=lm2["reasons"])
            ma = min(ma, lm2["budget"])          # 6.2: slowest unit's MF
            keep = {(d["col"], d["row"]) for d in lm2["dests"]}
            dests = {h: d for h, d in dests.items() if h in keep}
    out = dict(ma=ma, dests=sorted(dests.values(), key=lambda d: d["cost"]),
               reasons=[])
    for extra in ("rotations", "formations"):    # napoleonic panel data
        if extra in lm:
            out[extra] = lm[extra]
    return out


def api_legal_free(qs):
    """Free play (tier 0 / no gate): every hex on the board image is a valid
    drop — including off-map areas like printed turn/OOA tracks, exactly as
    VASSAL itself plays. No costs, no terrain filtering; the user is the
    umpire (spec #2 V3-parity floor)."""
    g = GAME_OBJ
    w, h = png_size(g.assets["map"])
    out = []
    c = 0
    while True:
        x0, _ = g.grid.hex_to_pixel(c, 0)
        if x0 > w:
            break
        r = 0
        while True:
            x, y = g.grid.hex_to_pixel(c, r)
            if y > h:
                break
            if x >= 0 and y >= 0:
                out.append(dict(col=c, row=r, x=x, y=y,
                                hexnum=g.grid.hexnum(c, r)))
            r += 1
        c += 1
    pid = qs["id"][0]
    b = fresh_board()
    me = next(u for u in b.units() if u["id"] == pid)
    return dict(ma=g.stats(me["name"])[2], dests=out, free=True)


def api_legal(qs):
    if SG:
        return api_legal_sg(qs)
    if not TG:
        return api_legal_free(qs)
    g = GAME_OBJ
    pid = qs["id"][0]
    whole = qs.get("whole", ["0"])[0] == "1"
    b = fresh_board()
    units = b.units()
    me = next(u for u in units if u["id"] == pid)
    ma = g.stats(me["name"])[2]
    mates = []
    if whole:
        sid = b.member_of.get(pid)
        mates = [u for u in units if u["id"] != pid
                 and b.member_of.get(u["id"]) == sid]
        ma = min([ma] + [g.stats(u["name"])[2] for u in mates])
    moving_ids = {pid} | {u["id"] for u in mates}
    # rules board = on-map units, minus the moving group (they don't block themselves)
    rb = [u for u in units if g.on_map(u["col"], u["row"]) and u["id"] not in moving_ids]
    dests = g.legal_destinations_t(me, ma, rb)
    out = []
    for (c, r), cost in dests.items():
        x, y = g.grid.hex_to_pixel(c, r)
        out.append(dict(col=c, row=r, x=x, y=y, hexnum=g.grid.hexnum(c, r),
                        cost=round(cost, 1), terrain=g.hex_terrain(c, r)))
    return dict(ma=ma, dests=out)


def api_move_sg(body):
    """Strategic mode: /api/move goes THROUGH the gate — the only door.
    Illegal proposals are rejected (and logged) with cited reasons."""
    blocked = pbm_blocked()
    if blocked:
        return dict(error=blocked, flow=SG.flow())
    pid, dest, whole = body["id"], str(body["dest"]), body.get("whole")
    d = GAME_OBJ.grid.digits
    col, row = int(dest[:d]), int(dest[d:])
    ids = sg_stack_ids(pid) if whole else [pid]
    n0 = SG.s["n"]          # one drag gesture = one undo point, stack or not
    applied, rejected = [], []
    for mid in ids:
        u = SG.s["units"].get(mid)
        side = u["side"] if u else SG.s["mover"]
        r = SG.submit(side, {"type": "move", "unit": mid, "dest": [col, row]})
        if r["verdict"]["legal"]:
            sync_mirror()
            applied.append(mid)
        else:
            rejected.append({"unit": mid, "reasons": r["verdict"]["reasons"]})
    if applied:
        mark_undo(n0, f"move {applied[0]}" if len(applied) == 1
                  else f"move stack ({len(applied)} units)")
    out = dict(ok=not rejected, applied=len(applied),
               rejected=rejected, flow=SG.flow())
    if rejected:
        out["error"] = "; ".join(rejected[0]["reasons"])
    return out


def api_end_phase():
    blocked = pbm_blocked()
    if blocked:
        return dict(error=blocked, flow=SG.flow())
    # bluegray splits the player turn into movement then combat: the top-bar
    # "End player turn" maps to whichever boundary is next
    if SCEN_MODE == "napoleonic":
        if SG.s["phase"] == "rally":
            t = "end_rally"
        elif getattr(SG, "_cmd", False):
            t = "end_activation"    # command flow [3.0]: the top-bar
            # button closes the open activation; other phases drive
            # through the left panel
        else:
            t = "end_turn"
    else:
        t = "end_movement" if (SCEN_MODE in ("bluegray", "westwall")
                               and SG.s["phase"] == "movement") \
            else "end_phase"
    n0 = SG.s["n"]
    r = SG.submit(SG.s["mover"], {"type": t})
    if r["verdict"]["legal"]:
        mark_undo(n0, t.replace("_", " "))
    out = dict(verdict=r["verdict"], result=r.get("result"), flow=SG.flow())
    if not r["verdict"]["legal"]:
        out["error"] = "; ".join(r["verdict"]["reasons"])
    done.clear()
    return out


def api_sg_ai_turn(body):
    """Strategic mode: let the policy AI play one whole player turn for `side`
    (default: the current mover) THROUGH the gate. Every proposal is logged
    with its verdict; the board mirror is diff-synced once at the end so real
    VASSAL and the browser see the result."""
    if pbm_mod.load_sidecar(LIVE, GAME_SLUG):
        return dict(steps=[], flow=SG.flow(),
                    error="play-by-mail: the AI opponent plays by email, "
                          "not locally")
    if sg_over():
        return dict(steps=[], flow=SG.flow(), error="game is over")
    if SCEN_MODE == "napoleonic":
        # napoleonic decisions interleave (LIM draws, reaction/shock
        # windows): the AI plays every decision belonging to `side`
        # and stops the moment the flow passes to the other side
        side = body.get("side") or SG.decider()
        if SG.decider() != side:
            return dict(steps=[], flow=SG.flow(),
                        error=f"it is not {side}'s decision")
        steps = sg_ai_module().take_turn(SG, side)
        sync_mirror()
        done.clear()
        return dict(steps=steps, flow=SG.flow())
    side = body.get("side") or SG.s["mover"]
    if SG.s["mover"] != side or SG.s["phase"] != "movement":
        return dict(steps=[], flow=SG.flow(),
                    error=f"it is not the start of the {side} player turn")
    plan = champ_mod.plan_for(SG)      # trained champion where one exists
    steps = (plans_mod.take_turn(SG, plan) if plan
             else sg_ai_module().take_turn(SG))
    sync_mirror()
    done.clear()
    return dict(steps=steps, flow=SG.flow())


def api_ai_step(body):
    """Advance the strategic AI by ONE action through the gate — the engine-level
    step-through the UI drives on spacebar (single-step) or a timer (animated
    whole-turn), so any StrategicGame with a policy AI plays one counter at a
    time instead of jump-cutting from turn-start to turn-end.

    A freshly created stepper REVEALS the first action's intent without executing
    (returns step=None, next=<intent>); each later call EXECUTES the pending
    action and reveals the next. Returns {done, step, next, flow}."""
    global AI_STEP
    if not SG:
        return dict(error="stepped AI is only for strategic games")
    if pbm_mod.load_sidecar(LIVE, GAME_SLUG):
        return dict(error="play-by-mail: the AI opponent plays by email, "
                          "not locally")
    if sg_over():
        AI_STEP = None
        return dict(done=True, step=None, next=None, flow=SG.flow(),
                    error="game is over")
    if SCEN_MODE == "napoleonic":
        side = body.get("side") or SG.decider()
        fresh = (AI_STEP is None or AI_STEP.done()
                 or AI_STEP.sg is not SG
                 or getattr(AI_STEP, "side", None) != side)
        if fresh:
            if SG.decider() != side:
                return dict(done=False, step=None, next=None,
                            flow=SG.flow(),
                            error=f"it is not {side}'s decision")
            AI_STEP = sg_ai_module().TurnStepper(SG, side)
            return dict(done=AI_STEP.done(), step=None,
                        next=AI_STEP.peek(), flow=SG.flow())
    else:
        side = body.get("side") or SG.s["mover"]
        fresh = (AI_STEP is None or AI_STEP.done()
                 or AI_STEP.sg is not SG
                 or getattr(AI_STEP, "_for", None) != (SG.s["turn"],
                                                       SG.s["mover"]))
        if fresh:
            if SG.s["mover"] != side or SG.s["phase"] != "movement":
                return dict(done=False, step=None, next=None, flow=SG.flow(),
                            error=f"it is not the start of the {side} "
                                  "player turn")
            plan = champ_mod.plan_for(SG)
            comp = plans_mod.COMPILERS.get(SCEN_MODE)
            if plan and plan.get("orders") and comp:
                # champion stepping: same planned action stream the
                # whole-turn path plays, revealed one action at a time
                AI_STEP = sg_ai_module().TurnStepper(
                    SG, gen=comp(SG, plan, None))
            else:
                AI_STEP = sg_ai_module().TurnStepper(SG)
            AI_STEP._for = (SG.s["turn"], SG.s["mover"])
            return dict(done=AI_STEP.done(), step=None, next=AI_STEP.peek(),
                        flow=SG.flow())      # reveal the first intent, execute nothing
    entry = AI_STEP.step()
    sync_mirror()
    done.clear()
    nxt = AI_STEP.peek()
    finished = AI_STEP.done()
    if finished:
        AI_STEP = None
    return dict(done=finished, step=entry, next=nxt, flow=SG.flow())


def api_sg_action(body):
    """Strategic mode: any gate action (arrivals, supply roll, sea movement,
    Rommel bonus) goes THROUGH the gate; placements are mirrored into the
    work .vsav (units at sea keep their last board spot in the mirror)."""
    blocked = pbm_blocked()
    if blocked:
        return dict(verdict=dict(legal=False, reasons=[blocked]),
                    error=blocked, flow=SG.flow())
    action = body["action"]
    side = body.get("side") or SG.s["mover"]
    n0 = SG.s["n"]
    r = SG.submit(side, action)
    if r["verdict"]["legal"]:
        mark_undo(n0, (action.get("type") or "action").replace("_", " "))
        sync_mirror()
    out = dict(verdict=r["verdict"], result=r.get("result"), flow=SG.flow())
    if not r["verdict"]["legal"]:
        out["error"] = "; ".join(r["verdict"]["reasons"])
    return out


def api_move(body):
    if SG:
        return api_move_sg(body)
    b = fresh_board()
    pid, dest, whole = body["id"], body["dest"], body.get("whole")
    me = next(u for u in b.units() if u["id"] == pid)
    if whole:
        msg = b.move_stack(me["hexnum"], dest)
        for mid in b.stacks[b.member_of[pid]]["members"]:
            done[mid] = "moved"
    else:
        msg = b.move_piece_by_id(pid, dest)
        done[pid] = "moved"
    b.write(WORK)
    return dict(ok=True, msg=msg)


def api_pass(body):
    b = fresh_board()
    pid = body["id"]
    ids = b.stacks[b.member_of[pid]]["members"] if body.get("whole") else [pid]
    for i in ids:
        done[i] = "passed"
    return dict(ok=True)


def api_face(body):
    if not GAME_OBJ.facing:
        return dict(error="this game has no facing")
    pid, step = body["id"], int(body.get("step", 1))
    n = GAME_OBJ.facing["count"]
    facing[pid] = (facing.get(pid, 0) + step) % n
    save_facing()
    return dict(ok=True, facing=facing[pid])


# --- play-by-mail (spec #19): the log IS the game; files travel by email ----
def pbm_blocked():
    """In a PBM match, the local user drives everything DURING their own
    player turn (including opponent forced choices like retreat routing -
    same protocol the AI follows in its turn), but may touch nothing while
    it is the mailed opponent's turn. Returns the refusal reason or None."""
    sc = pbm_mod.load_sidecar(LIVE, GAME_SLUG)
    if sc and SG and not SG.s["over"] and SG.s["mover"] != sc["human_side"]:
        return (f"play-by-mail: it is {sc['ai_side']}'s player turn - it is "
                "played by your email opponent. Export/send your file, then "
                "import the reply.")
    return None


def pbm_status():
    """PBM match status for the loaded game (None when no match is active)."""
    sc = pbm_mod.load_sidecar(LIVE, GAME_SLUG)
    if not sc:
        return None
    st = dict(sc)
    if SG:
        st["your_turn"] = (not SG.s["over"]) and SG.s["mover"] == sc["human_side"]
        st["over"] = SG.s["over"]
        st["winner"] = SG.s["winner"]
        st["can_export"] = SG.s["over"] or SG.s["mover"] != sc["human_side"]
        st["exported"] = sc.get("last_export_n") == SG.s["n"]
    return st


def api_pbm_start(body):
    """Begin a play-by-mail match: fresh game, you play ONE side, the other
    seat is your email opponent (the AI General). Runs at the earned tier -
    PBM is a full-gate feature by construction."""
    if SCEN_MODE not in pbm_mod.PBM_MODES:
        return dict(error="play-by-mail v1 plays the strategic-family games "
                          f"({', '.join(pbm_mod.PBM_MODES)})")
    side = body.get("side")
    if side not in GAME_OBJ.side_order:
        return dict(error=f"pick a side: {' or '.join(GAME_OBJ.side_order)}")
    if TIER != TIER_EARNED:
        r = api_reset(dict(tier=TIER_EARNED))   # PBM = full gate, always
        if r.get("error"):
            return r
    else:
        api_reset({})
    if body.get("seed") is not None:
        SG.new_game(int(body["seed"]))
    ai_s = next(s for s in GAME_OBJ.side_order if s != side)
    sc = dict(match_id=pbm_mod.new_match_id(), game=GAME_SLUG, mode=SCEN_MODE,
              human_side=side, ai_side=ai_s,
              labels={side: body.get("my_label") or "You",
                      ai_s: body.get("opponent_label") or "AI General"},
              seq=0, last_export_n=None)
    pbm_mod.save_sidecar(LIVE, GAME_SLUG, sc)
    return dict(ok=True, pbm=pbm_status(), flow=SG.flow())


def api_pbm_export():
    """The current game as a mailable turn file. Allowed once your player
    turn is over (or the game is) - the file is what you email out."""
    sc = pbm_mod.load_sidecar(LIVE, GAME_SLUG)
    if not (SG and sc):
        return dict(error="no play-by-mail match is active")
    if not SG.s["over"] and SG.s["mover"] == sc["human_side"]:
        return dict(error="it is still your turn - press End player turn "
                          "before exporting")
    entries = pbm_mod.read_log(SG.log_path)
    sides = {s: {"player": "human" if s == sc["human_side"] else "ai",
                 "label": sc["labels"].get(s, s)}
             for s in (sc["human_side"], sc["ai_side"])}
    sc["seq"] += 1
    doc = pbm_mod.make_turn_file(GAME_SLUG, SCEN_MODE, entries, sides,
                                 sc["match_id"], sc["seq"], SG.flow())
    sc["last_export_n"] = SG.s["n"]
    pbm_mod.save_sidecar(LIVE, GAME_SLUG, sc)
    return dict(doc=doc,
                filename=f"pbm_{GAME_SLUG}_{sc['match_id']}"
                         f"_{sc['seq']:03d}.json")


def api_pbm_import(body):
    """Install a received turn file as THE live game. The whole log is
    replayed through a fresh engine first (verify_game semantics) - a file
    that doesn't reproduce is rejected with the specific reason, exactly
    what we mail back to the sender."""
    global TIER, AI_STEP
    if SCEN_MODE not in pbm_mod.PBM_MODES:
        return dict(error="play-by-mail v1 plays the strategic-family games")
    try:
        doc = pbm_mod.load_turn_file(body.get("doc"))
    except pbm_mod.PBMError as e:
        return dict(error=str(e))
    if doc["game"] != GAME_SLUG:
        return dict(error=f"this file belongs to {doc['game']!r} - open that "
                          "game from the Games menu, then import it there")
    init_tier = doc["log"][0].get("tier")
    if init_tier != TIER_EARNED:
        return dict(error=f"file was played at tier {init_tier}; this "
                          f"machine's earned tier for the game is {TIER_EARNED}")
    sc = pbm_mod.load_sidecar(LIVE, GAME_SLUG)
    prev = []
    if sc:
        if doc["match_id"] != sc["match_id"]:
            return dict(error="this file belongs to a DIFFERENT match than "
                              "the one in progress - Reset game first if you "
                              "mean to abandon yours and adopt this one")
        if SG and os.path.exists(SG.log_path):
            prev = pbm_mod.read_log(SG.log_path)
    try:
        if prev:
            pbm_mod.ensure_extends(prev, doc["log"])
        pbm_mod.install(doc, LIVE, ROOT)
    except pbm_mod.PBMError as e:
        return dict(error="REJECTED: " + str(e))
    if not sc:                       # adopt: we are the second player
        sc = dict(match_id=doc["match_id"], game=GAME_SLUG, mode=doc["mode"],
                  human_side=pbm_mod.human_side(doc),
                  ai_side=pbm_mod.ai_side(doc),
                  labels={s: v.get("label", s)
                          for s, v in doc["sides"].items()},
                  seq=doc["seq"], last_export_n=None)
    else:
        sc["seq"] = doc["seq"]
    pbm_mod.save_sidecar(LIVE, GAME_SLUG, sc)
    if TIER != init_tier:            # gate must rebuild at the file's tier or
        TIER = init_tier             # the state-file tier check would reset it
        save_tier()
    AI_STEP = None
    done.clear()
    build_gate()
    fresh_board()
    sync_mirror()
    new = doc["log"][len(prev):] if prev else doc["log"][1:]
    return dict(ok=True, flow=SG.flow(), pbm=pbm_status(),
                new_entries=[e for e in new if e.get("event") == "action"
                             and e["verdict"]["legal"]])


def api_pbm_stop():
    pbm_mod.clear_sidecar(LIVE, GAME_SLUG)
    return dict(ok=True)


# --- SALVO (Modes 2/3): an outside LLM takes a seat via the match folder ----
# Protocol: SALVO_PROTOCOL.md (repo root). The server owns packet/move
# semantics; the client (web/shared/salvo.js) only ferries files.
def salvo_status():
    sc = salvo_mod.load_sidecar(LIVE, GAME_SLUG)
    if not sc:
        return None
    st = {k: sc[k] for k in ("match_id", "llm_side", "n")}
    if SG:
        st["decider"] = salvo_mod.decider(SG)
        st["over"] = sg_over()
        st["your_llm_up"] = (not sg_over()
                             and salvo_mod.decider(SG) == sc["llm_side"])
    st["pbm"] = bool(pbm_mod.load_sidecar(LIVE, GAME_SLUG))
    return st


def _salvo_packet_now(sc):
    return salvo_mod.build_packet(SG, sc, GAME_SLUG, SCEN_MODE)


def _salvo_advance_ai(sc):
    """Mode 2: play the house side (champion where one exists) until the
    game waits on the LLM seat again - whole opponent turns AND the
    opponent's own pending choices. The LLM seat's pendings are never
    touched (resolve_for), so they land in a packet. Mode 3 (a mailed
    match is active) never advances locally - the remote end plays."""
    if pbm_mod.load_sidecar(LIVE, GAME_SLUG):
        return
    llm = sc["llm_side"]
    house = next(s for s in GAME_OBJ.side_order if s != llm)
    guard = 0
    while guard < 300 and not sg_over():
        guard += 1
        if salvo_mod.decider(SG) == llm:
            break
        if SG.s.get("pending"):
            item = sg_ai_module()._resolve_pending(SG)
            if not item:
                break
            SG.submit(item[0], item[1])
            continue
        if SG.s["mover"] == llm:
            break                      # LLM's turn, no pending: its packet
        plan = (champ_mod.plan_for(SG)
                if SG.s.get("phase") == "movement" else None)
        if plan:
            plans_mod.take_turn(SG, plan, resolve_for={house})
        elif SCEN_MODE == "strategic":
            sg_ai_module().take_turn(SG)
        else:
            sg_ai_module().take_turn(SG, resolve_for={house})
    sync_mirror()
    done.clear()


def api_salvo_start(body):
    """Attach the player's own LLM to one seat (Mode 2; with a mailed match
    active it becomes Mode 3 - same packets, remote opponent). Plays at the
    earned tier: SALVO is a full-gate feature by construction."""
    global AI_STEP
    if SCEN_MODE not in salvo_mod.SALVO_MODES:
        return dict(error="SALVO v1 plays the strategic-family games "
                          f"({', '.join(salvo_mod.SALVO_MODES)})")
    side = body.get("side")
    if side not in GAME_OBJ.side_order:
        return dict(error=f"pick a side: {' or '.join(GAME_OBJ.side_order)}")
    pbm_sc = pbm_mod.load_sidecar(LIVE, GAME_SLUG)
    if pbm_sc and side != pbm_sc["human_side"]:
        return dict(error=f"in this mailed match your seat is "
                          f"{pbm_sc['human_side']} - the LLM plays YOUR "
                          "seat; the other side arrives by mail")
    if body.get("fresh"):
        r = api_reset(dict(tier=TIER_EARNED))
        if r.get("error"):
            return r
        if body.get("seed") is not None:
            SG.new_game(int(body["seed"]))
    elif TIER != TIER_EARNED:
        return dict(error=f"SALVO plays at the earned tier ({TIER_EARNED}); "
                          "this game is running at tier "
                          f"{TIER} - start fresh or switch tier first")
    AI_STEP = None
    # s["n"] counts log LINES (init included); action numbering starts at
    # the next line, so "everything the LLM has seen" = s["n"] - 1
    sc = dict(match_id=(pbm_sc or {}).get("match_id") or pbm_mod.new_match_id(),
              game=GAME_SLUG, mode=SCEN_MODE, llm_side=side,
              n=1, last_n=SG.s["n"] - 1, rejected=None)
    salvo_mod.save_sidecar(LIVE, GAME_SLUG, sc)
    _salvo_advance_ai(sc)              # the house may have the first move
    salvo_mod.save_sidecar(LIVE, GAME_SLUG, sc)
    return dict(ok=True, salvo=salvo_status(), packet=_salvo_packet_now(sc),
                flow=SG.flow())


def api_salvo_packet():
    sc = salvo_mod.load_sidecar(LIVE, GAME_SLUG)
    if not (SG and sc):
        return dict(error="no SALVO match is active")
    return dict(packet=_salvo_packet_now(sc), salvo=salvo_status(),
                flow=SG.flow())


def api_salvo_move(body):
    """Consume a move file: apply its actions through the gate (accepted
    prefix stands), advance the house side, hand back the next packet."""
    sc = salvo_mod.load_sidecar(LIVE, GAME_SLUG)
    if not (SG and sc):
        return dict(error="no SALVO match is active")
    if sg_over():
        return dict(packet=_salvo_packet_now(sc), salvo=salvo_status(),
                    flow=SG.flow())
    blocked = pbm_blocked()
    if blocked:
        return dict(error=blocked, packet=_salvo_packet_now(sc),
                    salvo=salvo_status(), flow=SG.flow())
    try:
        acts = salvo_mod.check_move(body.get("move"), sc["n"])
    except salvo_mod.MoveError as e:
        return dict(error=str(e), packet=_salvo_packet_now(sc),
                    salvo=salvo_status(), flow=SG.flow())
    if salvo_mod.decider(SG) != sc["llm_side"]:
        return dict(error=f"not {sc['llm_side']}'s decision right now - "
                          "wait for a decision packet",
                    packet=_salvo_packet_now(sc), salvo=salvo_status(),
                    flow=SG.flow())
    pre_n = SG.s["n"] - 1        # last logged action before this move file
    sc["rejected"] = None
    accepted, rejected = salvo_mod.apply_move(SG, sc["llm_side"], acts)
    if rejected:
        sc["rejected"] = dict(your_move_n=sc["n"], accepted=len(accepted),
                              **rejected)
    sc["last_n"] = pre_n
    sc["n"] += 1
    _salvo_advance_ai(sc)
    salvo_mod.save_sidecar(LIVE, GAME_SLUG, sc)
    sync_mirror()
    done.clear()
    return dict(ok=True, accepted=len(accepted), rejected=rejected,
                packet=_salvo_packet_now(sc), salvo=salvo_status(),
                flow=SG.flow())


def api_salvo_tick():
    """Advance the house side if the game waits on it (match start, or
    after a mailed import) and return the current packet."""
    sc = salvo_mod.load_sidecar(LIVE, GAME_SLUG)
    if not (SG and sc):
        return dict(error="no SALVO match is active")
    _salvo_advance_ai(sc)
    salvo_mod.save_sidecar(LIVE, GAME_SLUG, sc)
    return dict(packet=_salvo_packet_now(sc), salvo=salvo_status(),
                flow=SG.flow())


def api_salvo_log():
    """The complete engine log - salvo.js mirrors it into the match folder
    as log.jsonl (the durable, independently verifiable game record)."""
    if not SG or not os.path.exists(SG.log_path):
        return dict(lines=[])
    return dict(lines=open(SG.log_path, encoding="utf-8").read()
                .splitlines())


def api_salvo_payload():
    """The challenger payload for the loaded game - the paste-in document
    that teaches any file-capable LLM to play this seat."""
    if SCEN_MODE not in salvo_mod.SALVO_MODES:
        return dict(error="SALVO v1 plays the strategic-family games")
    text = salvo_mod.payload_text(GAME_SLUG, GAME_OBJ.spec, SCEN_MODE,
                                  game_dir(GAME_SLUG), turns=SG.turns)
    return dict(text=text, filename=f"salvo_payload_{GAME_SLUG}.md")


def api_salvo_stop():
    salvo_mod.clear_sidecar(LIVE, GAME_SLUG)
    return dict(ok=True)


def api_reset(body=None):
    global TIER, AI_STEP
    AI_STEP = None
    pbm_mod.clear_sidecar(LIVE, GAME_SLUG)   # a reset abandons any PBM match
    salvo_mod.clear_sidecar(LIVE, GAME_SLUG)  # ...and any SALVO attachment
    undo_mod.clear(LIVE, GAME_SLUG)          # ...and the undo window
    t = (body or {}).get("tier")
    if t is not None:
        if t not in TIER_CHOICES:
            return dict(error=f"tier {t} is not available for this game "
                              f"(earned: {TIER_EARNED})")
        TIER = t
        save_tier()
        build_gate()          # rebuild the gate at the newly selected tier
    if os.path.exists(WORK):
        os.remove(WORK)
    if os.path.exists(facing_path()):
        os.remove(facing_path())
    facing.clear()
    done.clear()
    if SG:
        SG.new_game()
    if TG:
        TG.new_game()
    fresh_board()
    return dict(ok=True, tier=TIER)


def load_game(game_dir, tier=None):
    """(Re)initialize the server onto a game — the single door for both the
    startup path and runtime game-switching. Tears down and rebuilds every
    module global that describes 'the loaded game', so switching games is just
    calling this again: per-game state is already file-backed (the work .vsav +
    JSONL log + tier/facing sidecars live under live\\game_<slug>.*), so a
    switch is load-from-disk, no new persistence.

    tier: run BELOW the earned tier (0=free play, 1=movement, ...). None = the
    persisted sidecar, clamped to what the game has earned."""
    global GAME_OBJ, GAME_SLUG, WORK, SCEN_PATH, SCEN_MODE
    global TIER, TIER_EARNED, TIER_CHOICES, done, facing, AI_STEP

    # reset per-game runtime state so nothing leaks across a switch
    done = {}
    facing = {}
    AI_STEP = None
    SCEN_PATH = SCEN_MODE = None
    TIER_EARNED = 0
    TIER_CHOICES = [0]

    GAME_OBJ = gamespec.Game(game_dir)
    gkey = GAME_SLUG = os.path.basename(os.path.normpath(game_dir))
    WORK = os.path.join(LIVE, f"game_{gkey}.vsav")
    if GAME_OBJ.spec.get("scenario"):
        SCEN_PATH = GAME_OBJ._path(GAME_OBJ.spec["scenario"])
        SCEN_MODE = json.load(open(SCEN_PATH, encoding="utf-8")).get("mode")
        if SCEN_MODE in SG_FAMILY:
            # mirror the engine's own earned-tier logic (sg_earned_tier):
            # 1 = movement gate, 2 = full combat gate, 3 = + AI
            TIER_EARNED = sg_earned_tier(SCEN_MODE, GAME_OBJ.spec)
            TIER_CHOICES = list(range(TIER_EARNED + 1))
        else:
            # tactical family: validated combat rules + policy AI both ship
            TIER_EARNED = 3
            TIER_CHOICES = [0, 3]
    TIER = load_tier()
    if tier is not None:
        if tier not in TIER_CHOICES:
            raise ValueError(f"tier {tier} not available (choices: {TIER_CHOICES})")
        TIER = tier
        save_tier()
    build_gate()
    # migrate the pre-generalization Arnhem work save (was live\game.vsav)
    legacy = os.path.join(LIVE, "game.vsav")
    if gkey == "arnhem" and not os.path.exists(WORK) and os.path.exists(legacy):
        shutil.copy(legacy, WORK)
    load_facing()
    fresh_board()
    return gkey


def make_server(port):
    """Build the HTTP server on 127.0.0.1:port (a game must already be loaded).
    Caller decides whether to serve_forever() (CLI) or run it in a thread behind
    a native window (app.py)."""
    return http.server.ThreadingHTTPServer(("127.0.0.1", port), H)


# --- API dispatch, shared by the HTTP handler and the browser (Pyodide) ---
# bridge. Pure functions: (path, qs/body) -> JSON-able dict, or None when the
# path is not an API route (handler then falls through to files/404).
def route_get(path, qs):
    if path == "/api/state":
        return api_state()
    if path == "/api/games":
        return api_games()
    if path == "/api/tables":
        return dict(tables=game_tables())
    if path == "/api/legal":
        return api_legal(qs)
    if TG and path == "/api/game":
        return flow_view()
    if SG and path == "/api/battle_preview":
        atk = [p for p in qs.get("atk", [""])[0].split(",") if p]
        dfd = [p for p in qs.get("def", [""])[0].split(",") if p]
        return SG.battle_preview(SG.s["mover"], atk, dfd)
    if TG and path == "/api/legal_moves":
        return TG.legal_moves(qs["id"][0])
    if TG and path == "/api/legal_targets":
        return dict(targets=TG.legal_targets(qs["id"][0]))
    if TG and path == "/api/range_info":
        col = int(qs["col"][0]) if "col" in qs else None
        row = int(qs["row"][0]) if "row" in qs else None
        return TG.range_info(qs["id"][0], col, row)
    if TG and path == "/api/log":
        return api_log_tail(qs)
    if TG and path == "/api/ai_plan":
        p = ai_mod.plan_next(TG, qs["side"][0])
        return p if p else dict(none=True, flow=flow_view())
    if path == "/api/pbm/export":
        return api_pbm_export()
    if SG and path == "/api/salvo/packet":
        return api_salvo_packet()
    if SG and path == "/api/salvo/log":
        return api_salvo_log()
    if SG and path == "/api/salvo/payload":
        return api_salvo_payload()
    return None


def route_post(path, body):
    if TG and path == "/api/action":
        return api_action(body)
    if TG and path == "/api/ai_turn":
        return api_ai_turn(body)
    if TG and path == "/api/new_game":
        return api_new_game(body)
    if path == "/api/load_game":
        return api_load_game(body)
    if path == "/api/move":
        return api_move(body)
    if SG and path == "/api/end_phase":
        return api_end_phase()
    if SG and path == "/api/sg_action":
        return api_sg_action(body)
    if SG and path == "/api/sg_ai_turn":
        return api_sg_ai_turn(body)
    if SG and path == "/api/ai_step":
        return api_ai_step(body)
    if path == "/api/pbm/start":
        return api_pbm_start(body)
    if path == "/api/pbm/import":
        return api_pbm_import(body)
    if path == "/api/pbm/stop":
        return api_pbm_stop()
    if SG and path == "/api/salvo/start":
        return api_salvo_start(body)
    if SG and path == "/api/salvo/move":
        return api_salvo_move(body)
    if SG and path == "/api/salvo/tick":
        return api_salvo_tick()
    if path == "/api/salvo/stop":
        return api_salvo_stop()
    if path == "/api/pass":
        return api_pass(body)
    if path == "/api/face":
        return api_face(body)
    if path == "/api/undo":
        return api_undo(body)
    if path == "/api/reset":
        return api_reset(body)
    return None


class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=HERE, **kw)

    def log_message(self, *a):  # quiet
        pass

    def _json(self, obj):
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _file(self, path):
        if not (path and os.path.isfile(path)):
            return self.send_error(404)
        with open(path, "rb") as f:
            data = f.read()
        ext = os.path.splitext(path)[1].lower()
        ctype = {"gif": "image/gif", ".gif": "image/gif",
                 ".svg": "image/svg+xml", ".png": "image/png",
                 ".bmp": "image/bmp", ".jpg": "image/jpeg",
                 ".jpeg": "image/jpeg"}.get(ext, "image/png")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        # Game assets (map, counters) share stable URLs across games, so a long
        # cache makes a game-switch show the PREVIOUS game's map. Revalidate
        # every time — cheap on localhost, and correctness beats caching here.
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(url.query)
        try:
            if url.path == "/api/pbm/export":
                # download semantics (Content-Disposition) — handler-only path
                r = api_pbm_export()
                if "error" in r:
                    return self._json(r)
                data = json.dumps(r["doc"]).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Disposition",
                                 f'attachment; filename="{r["filename"]}"')
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                return self.wfile.write(data)
            r = route_get(url.path, qs)
            if r is not None:
                return self._json(r)
            if url.path.startswith("/gasset/menu_art/"):
                slug = urllib.parse.unquote(url.path.rsplit("/", 1)[1])
                if slug not in set(RELEASE_GAMES) | {current_slug()}:
                    return self.send_error(404)
                return self._file(menu_art_path(slug))
            if url.path == "/gasset/map":
                return self._file(GAME_OBJ.assets.get("map"))
            if url.path.startswith("/gasset/counters/"):
                name = urllib.parse.unquote(url.path.split("/gasset/counters/", 1)[1])
                cdir = GAME_OBJ.assets.get("counters_dir")
                # counter names come from save data; keep the lookup inside the dir
                safe = os.path.normpath(os.path.join(cdir, name))
                if not safe.startswith(os.path.abspath(cdir)):
                    return self.send_error(403)
                return self._file(safe)
        except Exception as e:
            return self._json(dict(error=str(e)))
        if url.path in ("/", "/menu"):
            # "/menu" = the game picker (the native app opens here); "/" keeps
            # its ship-today behavior of dropping straight into the loaded game.
            self.path = "/menu.html" if url.path == "/menu" else (
                "/tactical.html" if TG else "/index.html")
        return super().do_GET()

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"] or 0)) or b"{}")
        try:
            r = route_post(self.path, body)
            if r is not None:
                return self._json(r)
        except Exception as e:
            return self._json(dict(error=str(e)))
        self.send_error(404)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    # bare `python ui/server.py` must work on a fresh clone: default to the
    # dev default only when its assets resolve, else the release flagship
    _default = gamespec.default_game_dir()
    if not _game_assets_ok(_default):
        _default = game_dir(RELEASE_GAMES[0])
    ap.add_argument("--game", default=_default)
    ap.add_argument("--port", type=int, default=8641)
    ap.add_argument("--tier", type=int, default=None,
                    help="run BELOW the earned tier (0=free play, 1=movement "
                         "gate, ...); default = the game's earned tier")
    a = ap.parse_args()
    try:
        load_game(a.game, tier=a.tier)
    except ValueError as e:
        sys.exit(str(e))
    if SG:
        print(f"strategic gate (tier {TIER} of {TIER_EARNED}): "
              f"{SG.scenario['name']} (log {SG.log_path})")
    elif TG:
        print(f"tactical mode (tier {TIER}): {TG.scenario['name']} "
              f"(log {TG.log_path})")
    elif SCEN_PATH:
        print(f"tier 0 selected (earned {TIER_EARNED}): free play, no gate")
    print(f"{GAME_OBJ.name} board UI ->  http://localhost:{a.port}   (Ctrl+C to stop)")
    make_server(a.port).serve_forever()
