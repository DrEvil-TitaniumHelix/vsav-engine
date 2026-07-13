"""
render_movie.py - Schematic playthrough movie from a verified game log.

Replays the log through a FRESH engine (verify_game-style: same actions,
same seed, positions taken from live engine state, never trusted from the
log alone) and draws every state as an ORIGINAL schematic frame - engine-
drawn hexes, terrain colors, our own counters. ZERO module art: nothing in
the output derives from third-party scans, so the movie is publishable.

    python engine/render_movie.py --game games/blue-and-gray-chickamauga \
        --log runs/<dir>/game_blue-and-gray-chickamauga.log.jsonl \
        --out movie.mp4 [--fps 6] [--width 1400] \
        [--label "Union=Fable 5" --label "Confederate=Champion genome"]

Commander plan commentary is read from orders_<side>.jsonl sidecars found
next to the log (written by llm_planner / session_play) and overlaid as
subtitles during that side's turns.

Output: .mp4 via ffmpeg (piped rawvideo) or .gif via Pillow.
Families: bluegray (Chickamauga). Other families register a UNITS/HUD
adapter as their engines gain movie support.
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gamespec             # noqa: E402
import bluegray as bg_mod   # noqa: E402

HUD_H, SUB_H, MARGIN = 84, 96, 40
SIDE_FILL = {0: "#2b5ea7", 1: "#8a8265"}          # first side, second side
TERRAIN = {"clear": "#e9dfc2", "forest": "#96ad7e", "rough": "#cbb98e",
           "forest_rough": "#7e9468", "water": "#a8c0cf", "stream": "#a8c0cf",
           "town": "#d8c8a8", "offmap": "#efefef"}
CLASS_GLYPH = {"infantry": "X", "cavalry": "/", "artillery": "•",
               "train": "T"}


def font(sz):
    try:
        return ImageFont.truetype("arial.ttf", sz)
    except OSError:
        return ImageFont.load_default()


class Frames:
    """Sink: pipes RGB frames to ffmpeg for .mp4, collects for .gif."""

    def __init__(self, out, size, fps):
        self.out, self.size, self.fps = out, size, fps
        self.gif = out.lower().endswith(".gif")
        self.images, self.proc, self.n = [], None, 0
        if not self.gif:
            self.proc = subprocess.Popen(
                ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo",
                 "-pix_fmt", "rgb24", "-s", f"{size[0]}x{size[1]}",
                 "-r", str(fps), "-i", "-", "-c:v", "libx264",
                 "-pix_fmt", "yuv420p", "-crf", "22", out],
                stdin=subprocess.PIPE)

    def add(self, img, hold=1):
        for _ in range(hold):
            self.n += 1
            if self.gif:
                self.images.append(img.copy())
            else:
                self.proc.stdin.write(img.tobytes())

    def close(self):
        if self.gif:
            self.images[0].save(self.out, save_all=True,
                                append_images=self.images[1:],
                                duration=int(1000 / self.fps), loop=0)
        else:
            self.proc.stdin.close()
            if self.proc.wait() != 0:
                raise RuntimeError("ffmpeg failed")


class BGMovie:
    """Bluegray adapter + painter."""

    def __init__(self, game, tg, terrain, width, labels):
        self.game, self.tg, self.terrain = game, tg, terrain
        self.labels = labels
        g = game.grid
        self.digits = g.digits
        hexes = terrain["hexes"]
        centers = {}
        for key in hexes:
            c, r = int(key[:self.digits]), int(key[self.digits:])
            centers[key] = g.hex_to_pixel(c, r)
        xs = [p[0] for p in centers.values()]
        ys = [p[1] for p in centers.values()]
        self.R = g.dx / 1.5                       # flat-top: col pitch = 1.5R
        self.H = g.dy                             # hex height = row pitch
        x0, y0 = min(xs) - self.R - MARGIN, min(ys) - self.H / 2 - MARGIN
        map_w = (max(xs) - min(xs)) + 2 * self.R + 2 * MARGIN
        map_h = (max(ys) - min(ys)) + self.H + 2 * MARGIN
        self.scale = width / map_w
        self.W = int(round(map_w * self.scale / 2)) * 2
        self.MH = int(round(map_h * self.scale))
        self.HT = int(round((HUD_H + SUB_H + self.MH) / 2)) * 2
        self.off = (-x0 * self.scale, -y0 * self.scale + HUD_H)
        self.centers = {k: self.P(*p) for k, p in centers.items()}
        self.f_hud = font(int(30 * min(1.5, self.scale * 4)))
        self.f_sub = font(22)
        self.f_small = font(max(10, int(self.R * self.scale * 0.42)))
        self.f_big = font(44)
        self.sides = game.side_order
        self.base = self._paint_base()

    def P(self, x, y):
        return (x * self.scale + self.off[0], y * self.scale + self.off[1])

    def hexkey(self, col, row):
        return f"{col:0{self.digits}d}{row:0{self.digits}d}"

    def _hexpoly(self, cx, cy):
        R, H = self.R * self.scale, self.H * self.scale
        return [(cx + R, cy), (cx + R / 2, cy + H / 2),
                (cx - R / 2, cy + H / 2), (cx - R, cy),
                (cx - R / 2, cy - H / 2), (cx + R / 2, cy - H / 2)]

    def _shared_edge(self, ka, kb):
        (ax, ay), (bx, by) = self.centers[ka], self.centers[kb]
        va = self._hexpoly(ax, ay)
        d2 = lambda p: (p[0] - bx) ** 2 + (p[1] - by) ** 2
        return sorted(sorted(va, key=d2)[:2])

    def _paint_base(self):
        """Static layer: terrain, roads, VP/exit markers."""
        img = Image.new("RGB", (self.W, self.HT), "#f4f1e8")
        d = ImageDraw.Draw(img)
        for key, cell in self.terrain["hexes"].items():
            cx, cy = self.centers[key]
            col = TERRAIN.get(cell.get("t", "clear"), "#cccccc")
            d.polygon(self._hexpoly(cx, cy), fill=col, outline="#b0a888")
        for pair, feats in self.terrain.get("sides", {}).items():
            ka, kb = pair.split("|")
            if ka not in self.centers or kb not in self.centers:
                continue
            pa, pb = self.centers[ka], self.centers[kb]
            if feats.get("road"):
                d.line([pa, pb], fill="#7a5230", width=max(2, int(4 * self.scale)))
            elif feats.get("trail"):
                self._dashed(d, pa, pb, "#9a7a50", max(1, int(3 * self.scale)))
            for k in feats:
                if k in ("stream", "creek", "river"):
                    e = self._shared_edge(ka, kb)
                    d.line(e, fill="#5f8fb0", width=max(2, int(5 * self.scale)))
        vp = self.tg.vp_cfg.get("occupation") or {}
        for owner, hexes in vp.items():
            for hx, pts in hexes.items():
                cx, cy = self.centers[hx]
                d.polygon(self._hexpoly(cx, cy), outline="#c9a227",
                          width=max(2, int(4 * self.scale)))
                d.text((cx, cy + self.H * self.scale * 0.30), f"{pts}VP",
                       fill="#8a6d13", font=self.f_small, anchor="mm")
        for (c, r) in self.tg.exit_hexes:
            cx, cy = self.centers[self.hexkey(c, r)]
            d.polygon(self._hexpoly(cx, cy), outline="#b03a2e",
                      width=max(2, int(4 * self.scale)))
            d.text((cx, cy), "EXIT", fill="#b03a2e",
                   font=self.f_small, anchor="mm")
        return img

    @staticmethod
    def _dashed(d, a, b, color, width, dash=8, gap=6):
        import math
        dist = math.hypot(b[0] - a[0], b[1] - a[1])
        if not dist:
            return
        ux, uy = (b[0] - a[0]) / dist, (b[1] - a[1]) / dist
        t = 0.0
        while t < dist:
            e = min(t + dash, dist)
            d.line([(a[0] + ux * t, a[1] + uy * t),
                    (a[0] + ux * e, a[1] + uy * e)], fill=color, width=width)
            t = e + gap

    # -------------------------------------------------------------- frame
    def frame(self, hud, sub, highlights=None, arrows=None, kills=None,
              banner=None):
        tg = self.tg
        img = self.base.copy()
        d = ImageDraw.Draw(img, "RGBA")
        R = self.R * self.scale
        for hx, colr in (highlights or {}).items():
            cx, cy = self.centers[hx]
            d.polygon(self._hexpoly(cx, cy), outline=colr,
                      width=max(3, int(6 * self.scale)))
        for (fr, to, colr) in (arrows or []):
            d.line([self.centers[fr], self.centers[to]], fill=colr,
                   width=max(2, int(5 * self.scale)))
            d.ellipse([self.centers[to][0] - 4, self.centers[to][1] - 4,
                       self.centers[to][0] + 4, self.centers[to][1] + 4],
                      fill=colr)
        # counters, stacked with a small offset
        by_hex = {}
        for i, side in enumerate(self.sides):
            for u in tg._live(side):
                by_hex.setdefault((u["col"], u["row"]), []).append((i, u))
        cw, ch = R * 1.05, R * 0.95
        for (c, r), units in by_hex.items():
            cx, cy = self.centers[self.hexkey(c, r)]
            n = len(units)
            for j, (i, u) in enumerate(units[:3]):
                ox = cx + (j - min(n - 1, 2) / 2) * cw * 0.28
                oy = cy - j * ch * 0.16
                st = self.game.stats(u["slot"])
                d.rounded_rectangle([ox - cw / 2, oy - ch / 2,
                                     ox + cw / 2, oy + ch / 2],
                                    radius=int(4 * self.scale) + 2,
                                    fill=SIDE_FILL[i], outline="#222222")
                glyph = CLASS_GLYPH.get(tg.cls(u), "?")
                d.text((ox, oy - ch * 0.18), glyph, fill="white",
                       font=self.f_small, anchor="mm")
                d.text((ox, oy + ch * 0.22), str(st[0] or st[1]),
                       fill="white", font=self.f_small, anchor="mm")
            if n > 3:
                d.text((cx + cw * 0.65, cy - ch * 0.5), f"x{n}",
                       fill="#222222", font=self.f_small, anchor="mm")
        for hx in (kills or []):
            cx, cy = self.centers[hx]
            k = R * 0.8
            for s in (-1, 1):
                d.line([(cx - k, cy - s * k), (cx + k, cy + s * k)],
                       fill="#a01818", width=max(3, int(7 * self.scale)))
        if tg.is_night():
            d.rectangle([0, HUD_H, self.W, HUD_H + self.MH],
                        fill=(20, 30, 70, 60))
        # HUD
        d.rectangle([0, 0, self.W, HUD_H], fill="#1e1e28")
        vp = " ".join(f"{s} {v}" for s, v in sorted(tg.s["vp"].items()))
        d.text((12, 10), f"{tg.turn_label()}  |  {tg.s['phase']}  |  VP: {vp}"
               + ("  |  NIGHT" if tg.is_night() else ""),
               fill="#e8e8e8", font=self.f_sub)
        d.text((12, 44), hud[:160], fill="#b8c8e8", font=self.f_sub)
        # subtitles
        d.rectangle([0, self.HT - SUB_H, self.W, self.HT], fill="#14141c")
        for i, line in enumerate(self._wrap(sub, 110)[:3]):
            d.text((12, self.HT - SUB_H + 8 + i * 27), line,
                   fill="#d8d0a8", font=self.f_sub)
        if banner:
            d.rectangle([0, self.HT // 2 - 44, self.W, self.HT // 2 + 44],
                        fill=(20, 20, 30, 215))
            d.text((self.W // 2, self.HT // 2), banner, fill="#f0e8c8",
                   font=self.f_big, anchor="mm")
        return img

    @staticmethod
    def _wrap(text, n):
        words, lines, cur = (text or "").split(), [], ""
        for w in words:
            if len(cur) + len(w) + 1 > n:
                lines.append(cur)
                cur = w
            else:
                cur = (cur + " " + w).strip()
        if cur:
            lines.append(cur)
        return lines or [""]


def load_orders(log_dir):
    """(turn, side_lower) -> commentary, from any orders_*.jsonl sidecars."""
    out = {}
    for path in glob.glob(os.path.join(log_dir, "orders_*.jsonl")):
        for line in open(path, encoding="utf-8"):
            e = json.loads(line)
            c = e.get("commentary")
            if c:
                out[(e["turn"], e["side"].lower())] = c
    return out


def describe(e):
    """One HUD line for a legal action entry."""
    a, res = e["action"], e.get("result") or []
    t = a["type"]
    if t == "move":
        r = res[0] if res else {}
        return f"{e['side']}: {r.get('move', a['unit'])} moves to {a['dest']}"
    if t == "reinforce":
        r = res[0] if res else {}
        return f"{e['side']}: {r.get('reinforce', a['unit'])} enters at {a['hex']}"
    if t == "battle":
        r = res[0] if res else {}
        return (f"BATTLE {' + '.join(r.get('attackers', []))} vs "
                f"{' + '.join(r.get('defenders', []))} - {r.get('odds')}, "
                f"die {r.get('die')} -> {r.get('result')}")
    if t == "retreat":
        r = res[0] if res else {}
        return f"{r.get('retreat', a.get('unit'))} retreats to {a.get('dest')}"
    if t == "advance":
        return f"{e['side']}: advance after combat"
    return f"{e['side']}: {t}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--fps", type=int, default=6)
    ap.add_argument("--width", type=int, default=1400)
    ap.add_argument("--label", action="append", default=[],
                    help='Side=Commander name, e.g. "Union=Fable 5"')
    ap.add_argument("--stills", default=None, metavar="DIR",
                    help="instead of a movie, write one PNG per player-turn "
                         "boundary (end of each side's turn = start-of-turn "
                         "state for the next) plus setup + final, into DIR")
    ap.add_argument("--divergence", default=None, metavar="COMPARISON_JSON",
                    help="decision_probe comparison.json: annotate each "
                         "still's caption with commander agreement at that "
                         "decision point")
    a = ap.parse_args()
    out = a.out or os.path.join(os.path.dirname(a.log), "playthrough.mp4")

    lines = [json.loads(l) for l in open(a.log, encoding="utf-8") if l.strip()]
    init = lines[0]
    assert init.get("event") == "init", "log must start with init"
    if init.get("mode") != "bluegray":
        raise SystemExit(f"family '{init.get('mode')}' has no movie adapter yet "
                         "(bluegray only)")
    labels = dict(s.split("=", 1) for s in a.label)

    game = gamespec.Game(a.game)
    scen = None
    for cand in sorted(os.listdir(a.game)):
        if cand.startswith("scenario") and cand.endswith(".json"):
            s = json.load(open(os.path.join(a.game, cand), encoding="utf-8"))
            if s.get("name") == init["scenario"]:
                scen = os.path.join(a.game, cand)
                break
    if not scen:
        raise SystemExit(f"scenario '{init['scenario']}' not found")
    terrain = json.load(open(os.path.join(
        a.game, json.load(open(os.path.join(a.game, "game.json"),
                               encoding="utf-8"))["terrain_file"]),
        encoding="utf-8"))
    orders = load_orders(os.path.dirname(os.path.abspath(a.log)))

    with tempfile.TemporaryDirectory() as tmp:
        tg = bg_mod.BlueGrayGame(game, scen, tmp, seed=init["seed"],
                                 tier=init.get("tier"))
        mv = BGMovie(game, tg, terrain, a.width, labels)
        if a.stills:
            os.makedirs(a.stills, exist_ok=True)
            diverge = {}
            if a.divergence:
                comp = json.load(open(a.divergence, encoding="utf-8"))
                for row in comp.get("decisions", []):
                    ps = {k: v for k, v in row["plans"].items()
                          if k != "_advisor" and v}
                    names = sorted(ps)
                    if len(names) >= 2:
                        u = set().union(*(set(p) for p in ps.values()))
                        same = sum(1 for x in u if len(
                            {json.dumps(p.get(x)) for p in ps.values()}) == 1)
                        diverge[(row["turn"], row["side"])] = \
                            (f"commanders ({'/'.join(names)}) agreed on "
                             f"{same}/{len(u)} units at this decision point")
            n = 0

            def live_set():
                return {u["pid"]: u["slot"] for s_ in game.side_order
                        for u in tg._live(s_)}

            def snap(name, hud, cap=""):
                nonlocal n
                n += 1
                mv.frame(hud, cap).save(
                    os.path.join(a.stills, f"{n:02d}_{name}.png"))

            def caption(ev, cur):
                bits = []
                if ev["battles"]:
                    bits.append(f"{len(ev['battles'])} battle(s): "
                                + "; ".join(ev["battles"][:3]))
                if ev["dead"]:
                    bits.append("eliminated: " + ", ".join(ev["dead"][:6]))
                if ev["reinf"]:
                    bits.append(f"{ev['reinf']} reinforcements entered")
                if ev["exits"]:
                    bits.append(f"{ev['exits']} unit(s) exited")
                dv = diverge.get(cur)
                if dv:
                    bits.append(dv)
                return ". ".join(bits) if bits else "quiet turn - maneuver only"

            def fresh():
                return {"battles": [], "dead": [], "reinf": 0, "exits": 0}

            snap("setup", f"{init['scenario']} - starting positions")
            cur, ev, before = None, fresh(), live_set()
            for e in lines[1:]:
                if e.get("event") != "action":
                    continue
                key = (e["turn"], e["side"])
                if e.get("phase") == "movement" and key != cur:
                    if cur:
                        now = live_set()
                        ev["dead"] = [before[p] for p in before
                                      if p not in now]
                        snap(f"gt{cur[0]}_{cur[1].lower()}_done",
                             f"end of {cur[1]}'s player turn, GT {cur[0]}",
                             caption(ev, cur))
                    cur, ev, before = key, fresh(), live_set()
                r = tg.submit(e["side"], e["action"])
                if r["verdict"]["legal"]:
                    t = e["action"]["type"]
                    res = e.get("result") or []
                    if t == "battle" and res:
                        b = res[0]
                        ev["battles"].append(
                            f"{'+'.join(b.get('attackers', []))} vs "
                            f"{'+'.join(b.get('defenders', []))} {b.get('odds')}"
                            f" -> {b.get('result')}")
                    if t == "reinforce":
                        ev["reinf"] += 1
                    for d_ in res:
                        if isinstance(d_, dict) and ("exit" in d_
                                                     or "exited" in d_):
                            ev["exits"] += 1
                if tg.s["over"]:
                    break
            if cur:
                now = live_set()
                ev["dead"] = [before[p] for p in before if p not in now]
                snap(f"gt{cur[0]}_{cur[1].lower()}_done",
                     f"end of {cur[1]}'s player turn, GT {cur[0]}",
                     caption(ev, cur))
            vp = " ".join(f"{s} {v}" for s, v in sorted(tg.s["vp"].items()))
            snap("final", f"FINAL - winner {tg.s['winner']} ({vp})"
                 if tg.s["over"] else "final logged state (game unfinished)")
            print(f"{n} stills -> {a.stills}")
            return
        sink = Frames(out, (mv.W, mv.HT), a.fps)

        def sub_for(turn, side):
            c = orders.get((turn, side.lower()))
            name = labels.get(side, side)
            return f"{name} ({side}): {c}" if c else \
                   f"{name} ({side}) - standing doctrine / policy"

        vs = " vs ".join(labels.get(s, s) for s in game.side_order)
        sink.add(mv.frame(f"{init['scenario']}", vs,
                          banner=f"{init['scenario']} - {vs}"), hold=a.fps * 2)
        last_turn = 0
        for e in lines[1:]:
            if e.get("event") != "action":
                continue
            side, act = e["side"], e["action"]
            pre = {u["pid"]: (u["col"], u["row"])
                   for s_ in game.side_order for u in tg._live(s_)}
            r = tg.submit(side, act)
            if not r["verdict"]["legal"]:
                continue
            if tg.s["turn"] != last_turn and not tg.s["over"]:
                last_turn = tg.s["turn"]
                sink.add(mv.frame("", sub_for(last_turn, tg.s["mover"]),
                                  banner=tg.turn_label()
                                  + (" - NIGHT" if tg.is_night() else "")),
                         hold=max(2, a.fps))
            t = act["type"]
            if t in ("end_movement", "end_phase", "advance") \
               and not tg.s["over"]:
                continue
            hud = describe(e)
            sub = sub_for(e["turn"], side)
            highlights, arrows, kills, hold = {}, [], [], 1
            live_now = {u["pid"] for s_ in game.side_order
                        for u in tg._live(s_)}
            side_i = {s_: i for i, s_ in enumerate(game.side_order)}
            if t in ("move", "retreat") and act.get("unit") in pre \
               and act.get("dest"):
                frm = mv.hexkey(*pre[act["unit"]])
                to = mv.hexkey(*act["dest"])
                arrows = [(frm, to, "#d04030" if t == "retreat"
                           else ["#78a8f0", "#c8c090"][side_i[side]])]
            if t == "battle":
                hold = 3
                for pid in act.get("attackers", []) + act.get("defenders", []):
                    if pid in pre:
                        hx = mv.hexkey(*pre[pid])
                        if pid in live_now:
                            highlights[hx] = "#d04030"
                        else:
                            kills.append(hx)
            if tg.s["over"]:
                vp = " ".join(f"{s} {v}" for s, v in sorted(tg.s["vp"].items()))
                sink.add(mv.frame(hud, sub,
                                  banner=f"GAME OVER - {tg.s['winner']} wins "
                                  f"({vp})"), hold=a.fps * 3)
                break
            sink.add(mv.frame(hud, sub, highlights, arrows, kills), hold=hold)
        sink.close()
    print(f"{sink.n} frames -> {out}")


if __name__ == "__main__":
    main()
