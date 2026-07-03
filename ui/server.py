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

The work save is live\game_<game>.vsav — VASSAL can open it at any time; the AI
plays through the same file. All rules semantics come from games/<game>/game.json.

Run:  python ui\server.py [--game <dir>] [--port 8641]
"""
import argparse, http.server, json, os, shutil, struct, sys, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "engine"))
import board as board_mod  # noqa: E402
import gamespec  # noqa: E402

GAME_OBJ = None   # gamespec.Game
WORK = None       # working .vsav path
done = {}         # piece id -> "moved" | "passed"   (per server run; POC scope)
facing = {}       # piece id -> facing index (sidecar JSON next to the work save;
                  # VASSAL rotate-state write-through pending a save-diff experiment)


def facing_path():
    return WORK + ".facing.json"


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
    return struct.unpack(">II", head[16:24])


def fresh_board():
    if not os.path.exists(WORK):
        shutil.copy(GAME_OBJ.setup_save, WORK)
        done.clear()
    return board_mod.Board(WORK, GAME_OBJ)


def unit_view(u):
    g = GAME_OBJ
    a, d, m = g.stats(u["name"])
    return dict(u, att=a, dfn=d, ma=m, onmap=g.on_map(u["col"], u["row"]),
                terrain=g.hex_terrain(u["col"], u["row"]),
                status=done.get(u["id"]),
                facing=facing.get(u["id"], 0) if g.facing else None)


def game_descriptor():
    g = GAME_OBJ
    w, h = png_size(g.assets["map"])
    return dict(
        name=g.name,
        map_url="/gasset/map", map_w=w, map_h=h,
        counters_url="/gasset/counters/",
        counter_px=g.spec.get("ui", {}).get("counter_px", 75),
        grid=dict(dx=g.grid.dx, dy=g.grid.dy, orient=g.grid.orient),
        sides=[dict(id=s, label=g.spec["sides"].get("labels", {}).get(s, s))
               for s in g.side_order],
        facing=g.facing,
    )


def api_state():
    b = fresh_board()
    units = [unit_view(u) for u in b.units()]
    return dict(units=units, game=game_descriptor(),
                notes=f"{GAME_OBJ.name} — spec-driven engine")


def api_legal(qs):
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


def api_move(body):
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


def api_reset():
    if os.path.exists(WORK):
        os.remove(WORK)
    if os.path.exists(facing_path()):
        os.remove(facing_path())
    facing.clear()
    fresh_board()
    return dict(ok=True)


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
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "max-age=3600")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(url.query)
        try:
            if url.path == "/api/state":
                return self._json(api_state())
            if url.path == "/api/legal":
                return self._json(api_legal(qs))
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
        if url.path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"] or 0)) or b"{}")
        try:
            if self.path == "/api/move":
                return self._json(api_move(body))
            if self.path == "/api/pass":
                return self._json(api_pass(body))
            if self.path == "/api/face":
                return self._json(api_face(body))
            if self.path == "/api/reset":
                return self._json(api_reset())
        except Exception as e:
            return self._json(dict(error=str(e)))
        self.send_error(404)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default=gamespec.default_game_dir())
    ap.add_argument("--port", type=int, default=8641)
    a = ap.parse_args()
    GAME_OBJ = gamespec.Game(a.game)
    gkey = os.path.basename(os.path.normpath(a.game))
    WORK = os.path.join(ROOT, "live", f"game_{gkey}.vsav")
    # migrate the pre-generalization Arnhem work save (was live\game.vsav)
    legacy = os.path.join(ROOT, "live", "game.vsav")
    if gkey == "arnhem" and not os.path.exists(WORK) and os.path.exists(legacy):
        shutil.copy(legacy, WORK)
    load_facing()
    fresh_board()
    print(f"{GAME_OBJ.name} board UI ->  http://localhost:{a.port}   (Ctrl+C to stop)")
    http.server.ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()
