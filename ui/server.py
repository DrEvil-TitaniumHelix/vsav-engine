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
import ai as ai_mod  # noqa: E402
import ai_strategic as sai_mod  # noqa: E402
import ai_bluegray as bai_mod  # noqa: E402


def sg_ai_module():
    """The policy-AI module matching the loaded strategic-family gate."""
    return bai_mod if SCEN_MODE == "bluegray" else sai_mod

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
            if SG.on_map(su):
                v.update(col=su["col"], row=su["row"],
                         status="moved" if u["id"] in SG.s["moved"] else done.get(u["id"]))
                x, y = GAME_OBJ.grid.hex_to_pixel(su["col"], su["row"])
                v.update(x=x, y=y, hexnum=GAME_OBJ.grid.hexnum(su["col"], su["row"]),
                         hexname=GAME_OBJ.grid.display_name(su["col"], su["row"]),
                         terrain=g.hex_terrain(su["col"], su["row"]),
                         onmap=True)
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
    """Diff-sync the work .vsav against the gate state: any on-map SG unit
    whose board position differs gets moved (covers captures, retreats,
    advances, substitutions, replacements, Rommel displacement — every
    side effect in one sweep)."""
    if not SG:
        return
    b = fresh_board()
    pos = {u["id"]: (u["col"], u["row"]) for u in b.units()}
    moved = False
    for u in SG.s["units"].values():
        if not SG.on_map(u):
            continue
        if pos.get(u["pid"]) not in (None, (u["col"], u["row"])):
            b.move_piece_by_id(u["pid"],
                               GAME_OBJ.grid.hexnum(u["col"], u["row"]))
            moved = True
    if moved:
        b.write(WORK)


def api_action(body):
    side, action = body["side"], body["action"]
    r = TG.submit(side, action)
    if r["verdict"]["legal"] and action.get("type") in ("move", "reverse"):
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
    )


# --- multi-game menu: the release bundles several games behind one engine ---
# Curated tester menu (order = display order; AK is the flagship). Games not in
# this list are still loadable via --game / /api/load_game, but the menu shows
# these. Keep in sync with the release scope.
RELEASE_GAMES = ["afrika-korps-classic-ah", "blue-and-gray-chickamauga", "tobruk"]


def game_client(scen_mode, has_scen):
    """Which front-end HTML plays this game: strategic + free-play games use the
    generic index.html; the tactical family (own scenario, AP-fire) uses
    tactical.html. Mirrors the '/' routing that ships today."""
    if scen_mode in ("strategic", "bluegray"):
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
        if scen_mode == "strategic":
            earned = (3 if spec.get("policy_ai") else 2) if spec.get("combat") else 1
            choices = list(range(earned + 1))
        else:
            earned, choices = 3, [0, 3]
    return dict(slug=slug, name=spec.get("name", slug),
                mode=scen_mode or ("tactical" if has_scen else "free"),
                client=game_client(scen_mode, has_scen),
                tier=dict(earned=earned, choices=choices),
                blurb=spec.get("blurb") or spec.get("description"))


def current_slug():
    return GAME_SLUG


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
    if combat and combat.get("crt"):
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
    return dict(ma=ma, dests=sorted(dests.values(), key=lambda d: d["cost"]),
                reasons=[])


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
    pid, dest, whole = body["id"], str(body["dest"]), body.get("whole")
    d = GAME_OBJ.grid.digits
    col, row = int(dest[:d]), int(dest[d:])
    ids = sg_stack_ids(pid) if whole else [pid]
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
    out = dict(ok=not rejected, applied=len(applied),
               rejected=rejected, flow=SG.flow())
    if rejected:
        out["error"] = "; ".join(rejected[0]["reasons"])
    return out


def api_end_phase():
    # bluegray splits the player turn into movement then combat: the top-bar
    # "End player turn" maps to whichever boundary is next
    t = "end_movement" if (SCEN_MODE == "bluegray"
                           and SG.s["phase"] == "movement") else "end_phase"
    r = SG.submit(SG.s["mover"], {"type": t})
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
    side = body.get("side") or SG.s["mover"]
    if SG.s["over"]:
        return dict(steps=[], flow=SG.flow(), error="game is over")
    if SG.s["mover"] != side or SG.s["phase"] != "movement":
        return dict(steps=[], flow=SG.flow(),
                    error=f"it is not the start of the {side} player turn")
    steps = sg_ai_module().take_turn(SG)
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
    if SG.s["over"]:
        AI_STEP = None
        return dict(done=True, step=None, next=None, flow=SG.flow(),
                    error="game is over")
    side = body.get("side") or SG.s["mover"]
    fresh = (AI_STEP is None or AI_STEP.done()
             or AI_STEP.sg is not SG
             or getattr(AI_STEP, "_for", None) != (SG.s["turn"], SG.s["mover"]))
    if fresh:
        if SG.s["mover"] != side or SG.s["phase"] != "movement":
            return dict(done=False, step=None, next=None, flow=SG.flow(),
                        error=f"it is not the start of the {side} player turn")
        AI_STEP = sg_ai_module().TurnStepper(SG)
        AI_STEP._for = (SG.s["turn"], SG.s["mover"])
        return dict(done=AI_STEP.done(), step=None, next=AI_STEP.peek(),
                    flow=SG.flow())          # reveal the first intent, execute nothing
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
    action = body["action"]
    side = body.get("side") or SG.s["mover"]
    r = SG.submit(side, action)
    if r["verdict"]["legal"]:
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


def api_reset(body=None):
    global TIER, AI_STEP
    AI_STEP = None
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
        if SCEN_MODE in ("strategic", "bluegray"):
            # mirror the engine's own earned-tier logic (strategic.py /
            # bluegray.py): 1 = movement gate, 2 = full combat gate, 3 = + AI
            TIER_EARNED = (
                (3 if GAME_OBJ.spec.get("policy_ai") else 2)
                if GAME_OBJ.spec.get("combat") else 1)
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
                 ".svg": "image/svg+xml", ".png": "image/png"}.get(ext, "image/png")
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
            if url.path == "/api/state":
                return self._json(api_state())
            if url.path == "/api/games":
                return self._json(api_games())
            if url.path == "/api/tables":
                return self._json(dict(tables=game_tables()))
            if url.path == "/api/legal":
                return self._json(api_legal(qs))
            if TG and url.path == "/api/game":
                return self._json(flow_view())
            if SG and url.path == "/api/battle_preview":
                atk = [p for p in qs.get("atk", [""])[0].split(",") if p]
                dfd = [p for p in qs.get("def", [""])[0].split(",") if p]
                return self._json(SG.battle_preview(SG.s["mover"], atk, dfd))
            if TG and url.path == "/api/legal_moves":
                return self._json(TG.legal_moves(qs["id"][0]))
            if TG and url.path == "/api/legal_targets":
                return self._json(dict(targets=TG.legal_targets(qs["id"][0])))
            if TG and url.path == "/api/range_info":
                col = int(qs["col"][0]) if "col" in qs else None
                row = int(qs["row"][0]) if "row" in qs else None
                return self._json(TG.range_info(qs["id"][0], col, row))
            if TG and url.path == "/api/log":
                return self._json(api_log_tail(qs))
            if TG and url.path == "/api/ai_plan":
                p = ai_mod.plan_next(TG, qs["side"][0])
                return self._json(p if p else dict(none=True, flow=flow_view()))
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
            if TG and self.path == "/api/action":
                return self._json(api_action(body))
            if TG and self.path == "/api/ai_turn":
                return self._json(api_ai_turn(body))
            if TG and self.path == "/api/new_game":
                return self._json(api_new_game(body))
            if self.path == "/api/load_game":
                return self._json(api_load_game(body))
            if self.path == "/api/move":
                return self._json(api_move(body))
            if SG and self.path == "/api/end_phase":
                return self._json(api_end_phase())
            if SG and self.path == "/api/sg_action":
                return self._json(api_sg_action(body))
            if SG and self.path == "/api/sg_ai_turn":
                return self._json(api_sg_ai_turn(body))
            if SG and self.path == "/api/ai_step":
                return self._json(api_ai_step(body))
            if self.path == "/api/pass":
                return self._json(api_pass(body))
            if self.path == "/api/face":
                return self._json(api_face(body))
            if self.path == "/api/reset":
                return self._json(api_reset(body))
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
