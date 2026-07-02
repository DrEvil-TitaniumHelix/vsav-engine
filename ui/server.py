"""
server.py - Local board UI backend (Option A proof of concept).

Serves the Arnhem map + counters and exposes the engine over HTTP:
  GET  /api/state              board state + move/pass progress
  GET  /api/legal?id=&whole=   legal destination hexes for a piece or its whole stack
  POST /api/move               {id, dest, whole} -> applies move, writes game.vsav
  POST /api/pass               {id, whole}       -> marks unit(s) passed
  POST /api/reset              restore game.vsav from the historical setup

The working save is live\game.vsav — VASSAL can open it at any time; the AI plays
through the same file. Rules model: MA budget + ZOC stop + occupied-hex block;
terrain uniform "clear" pending per-hex map data (flagged in the UI).

Run:  python ui\server.py   ->  http://localhost:8641
"""
import http.server, json, os, shutil, sys, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "engine"))
import arnhem, board, rules, play  # noqa: E402

GAME = os.path.join(ROOT, "live", "game.vsav")
SETUP = os.path.join(ROOT, "ref", "Arnhem Historical.vsav")
HOLDING_ROW_MAX = 2

done = {}  # piece id -> "moved" | "passed"   (per server run; POC scope)


def fresh_board():
    if not os.path.exists(GAME):
        shutil.copy(SETUP, GAME)
        done.clear()
    return board.Board(GAME)


def unit_view(u):
    a, d, m = play.stats(u["name"])
    return dict(u, att=a, dfn=d, ma=m, onmap=rules.on_map(u["col"], u["row"]),
                terrain=rules.hex_terrain(u["col"], u["row"]),
                status=done.get(u["id"]))


def api_state():
    b = fresh_board()
    units = [unit_view(u) for u in b.units()]
    return dict(units=units, grid=arnhem.GRID,
                notes="terrain LIVE (roads ½ MP, streams +3, rivers blocked except bridges)")


def api_legal(qs):
    pid = qs["id"][0]
    whole = qs.get("whole", ["0"])[0] == "1"
    b = fresh_board()
    units = b.units()
    me = next(u for u in units if u["id"] == pid)
    ma = play.stats(me["name"])[2]
    mates = []
    if whole:
        sid = b.member_of.get(pid)
        mates = [u for u in units if u["id"] != pid
                 and b.member_of.get(u["id"]) == sid]
        ma = min([ma] + [play.stats(u["name"])[2] for u in mates])
    moving_ids = {pid} | {u["id"] for u in mates}
    # rules board = on-map units, minus the moving group (they don't block themselves)
    rb = [u for u in units if rules.on_map(u["col"], u["row"]) and u["id"] not in moving_ids]
    dests = rules.legal_destinations_t(me, ma, rb)
    out = []
    for (c, r), cost in dests.items():
        x, y = arnhem.hex_to_pixel(c, r)
        out.append(dict(col=c, row=r, x=x, y=y, hexnum=f"{c:02d}{r:02d}",
                        cost=round(cost, 1), terrain=rules.hex_terrain(c, r)))
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
        msg = b.move_piece(me["name"], dest)
        done[pid] = "moved"
    b.write(GAME)
    return dict(ok=True, msg=msg)


def api_pass(body):
    b = fresh_board()
    pid = body["id"]
    ids = b.stacks[b.member_of[pid]]["members"] if body.get("whole") else [pid]
    for i in ids:
        done[i] = "passed"
    return dict(ok=True)


def api_reset():
    if os.path.exists(GAME):
        os.remove(GAME)
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

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(url.query)
        try:
            if url.path == "/api/state":
                return self._json(api_state())
            if url.path == "/api/legal":
                return self._json(api_legal(qs))
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
            if self.path == "/api/reset":
                return self._json(api_reset())
        except Exception as e:
            return self._json(dict(error=str(e)))
        self.send_error(404)


if __name__ == "__main__":
    fresh_board()
    print("Arnhem board UI ->  http://localhost:8641   (Ctrl+C to stop)")
    http.server.ThreadingHTTPServer(("127.0.0.1", 8641), H).serve_forever()
