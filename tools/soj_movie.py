import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
import gamespec
import replay
from PIL import Image, ImageDraw, ImageEnhance, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, "live", "game_siege-of-jerusalem-ah.log.jsonl")
GAME = os.path.join(ROOT, "games", "siege-of-jerusalem-ah")
IMGD = r"C:\VassalIngest\soj\extracted\images"
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(tempfile.gettempdir(), "soj_movie")

SIDE_NAME = {"Jud": "Judaean", "Rom": "Roman"}
SIDE_COL = {"Jud": (58, 110, 210), "Rom": (188, 40, 34), None: (90, 90, 90)}
PHASE = {"deploy_jud": "Judaean Deployment", "deploy_rom": "Roman Deployment",
         "rom_fire": "Roman Fire", "rom_move": "Roman Movement",
         "rom_melee": "Roman Melee", "jud_rally": "Judaean Rally",
         "jud_fire": "Judaean Fire", "jud_move": "Judaean Movement",
         "jud_melee": "Judaean Melee", "rom_rally": "Roman Rally"}
RES = {"-": "no effect", "D": "Disrupted!", "DD": "Double Disruption!",
       "E": "Eliminated!", "B": "Driven back!"}


def snapshot(tg):
    s = tg.s
    units, marks, over = [], [], []
    for u in s["units"].values():
        if u["hex"] is None:
            continue
        rev = u["state"] != "fresh" or (
            tg.utype(u)["cls"] == "siege_engine" and not tg._se_crewed(u))
        img = u["slot"] + ("_Reverse.gif" if rev else
                           ("_" + u["cohort"] if u.get("cohort") else "") + ".gif")
        x, y = tg.px[u["hex"]]
        ph = s["phase"]
        done = (ph.endswith("_fire") and u["pid"] in s["fired"]) or (
            ph.endswith("_move") and bool(u.get("m0"))
            and u["pid"] not in (s.get("lastm") or []))
        units.append(dict(pid=u["pid"], img=img, x=x, y=y, done=done,
                          up=bool(u.get("up")), side=u["side"], hex=u["hex"]))
    for m in s["markers"]:
        img = ("Wreck_" + "_".join(w.capitalize() for w in m["type"].split("_"))
               + ".gif") if m["kind"] == "wreck" \
            else m["type"].split("_")[-1].capitalize() + "_Eliminated.gif"
        x, y = tg.px[m["hex"]]
        marks.append(dict(img=img, x=x, y=y))
    for e in s["esc"]:
        x, y = tg.px[e["hex"]]
        marks.append(dict(img="Escalade.gif", x=x, y=y))
    for h, d in s["breach"].items():
        if d <= 0:
            continue
        img = "Damage_Breach.gif" if tg.hex_t(h) == "breach" \
            else f"Damage_{min(int(d), 14)}.gif"
        x, y = tg.px[h]
        marks.append(dict(img=img, x=x, y=y))
    for t in s["testudo"]:
        if t.get("hex") is None:
            continue
        x, y = tg.px[t["hex"]]
        over.append(dict(img=t.get("legion", "XII") + "_Testudo"
                         + ("_Reverse" if t.get("broken") else "") + ".gif",
                         x=x, y=y))
    return dict(units=units, marks=marks, over=over)


def build_frames():
    lines = [json.loads(x) for x in open(LOG, encoding="utf-8")]
    init = lines[0]
    game = gamespec.Game(GAME)
    scen = replay.find_scenario(game.dir, init)
    work = tempfile.mkdtemp()
    tg = replay.make_gate(game, scen, work, init)
    replay.check_init(tg, init)
    pool = set(init.get("pool") or [])
    entered = set()
    frames = []

    def nm(pid):
        return tg.s["units"][pid]["slot"].replace("_", " ")

    def emit(cap, actors=(), thex=None, dur=0.4, side=None, path=None,
             phase=None, title=None, sub=None):
        frames.append(dict(snap=snapshot(tg), cap=cap, actors=list(actors),
                           thex=thex, dur=dur, side=side, path=path,
                           turn=tg.s["turn"], phase=phase or tg.s["phase"],
                           title=title, sub=sub))

    emit(None, dur=3.2, title="THE SIEGE OF JERUSALEM",
         sub="The Assault of Gallus, 66 AD — a full game, every action validated by the rules engine")
    dep_buf, dep_side = [], None
    last_turn = 0
    for e in [x for x in lines[1:] if x.get("event") == "action"]:
        r = tg.submit(e["side"], e["action"])
        if r["verdict"]["legal"] != e["verdict"]["legal"] \
           or e["state_hash"] != tg.state_hash():
            raise SystemExit(f"replay divergence at entry {e['n']}")
        if not e["verdict"]["legal"]:
            continue
        a, res = e["action"], e.get("result") or {}
        t = a["type"]
        if t == "deploy":
            dep_buf.append(a["pid"])
            dep_side = e["side"]
            if len(dep_buf) >= 8:
                emit(f"{SIDE_NAME[dep_side]} deployment", dep_buf, dur=0.45,
                     side=dep_side, phase=e["phase"])
                dep_buf = []
            continue
        if dep_buf:
            emit(f"{SIDE_NAME[dep_side]} deployment", dep_buf, dur=0.45,
                 side=dep_side, phase=e["phase"])
            dep_buf = []
        if tg.s["turn"] != last_turn and tg.s["turn"] > 0:
            last_turn = tg.s["turn"]
            emit(None, dur=1.5, title=f"Turn {last_turn} of 10")
        if t == "deploy_done":
            emit(f"{SIDE_NAME[e['side']]} deployment complete", dur=1.2,
                 side=e["side"], phase=e["phase"])
        elif t == "end_phase":
            continue
        elif t == "move":
            pid = a["pid"]
            pts = [tg.px[tg.name_hex[h]] for h in a["path"] if h in tg.name_hex]
            if pid in pool and pid not in entered:
                entered.add(pid)
                emit(f"Reinforcements! {nm(pid)} pours in through the "
                     f"{a['path'][0]} gate", [pid], dur=1.4, side=e["side"],
                     path=pts, phase=e["phase"])
            else:
                emit(f"{nm(pid)} \u2192 {a['path'][-1]}", [pid], dur=0.35,
                     side=e["side"], path=pts, phase=e["phase"])
        elif t == "fire":
            outc = RES.get(res.get("result"), res.get("result"))
            emit(f"Missile fire at {a['target']} — die {res['die']}: {outc}",
                 a["firers"], thex=a["target"],
                 dur=0.8 if res.get("result") == "-" else 1.2,
                 side=e["side"], phase=e["phase"])
        elif t == "melee":
            outc = RES.get(res.get("result"), res.get("result"))
            pre = "Sortie! " if res.get("sortie") else ""
            emit(f"{pre}Melee at {a['target']} ({res['col']}, die {res['die']}): {outc}",
                 a["attackers"], thex=a["target"],
                 dur=1.0 if res.get("result") == "-" else 1.4,
                 side=e["side"], phase=e["phase"])
        elif t == "escalade":
            cap = f"Escalade! Ladders raised at {res.get('escalade')}" \
                if a.get("op") == "place" \
                else f"Escalade ladders withdrawn at {res.get('escalade')}"
            emit(cap, [a["pid"]], dur=1.5, side=e["side"], phase=e["phase"])
        elif t == "testudo":
            op = a.get("op")
            cap = {"form": f"Testudo formed at {res.get('testudo')} — shields locked",
                   "disband": f"Testudo at {res.get('testudo')} disbands",
                   "move": f"Testudo advances to {res.get('testudo')}"}.get(
                       op, f"Testudo {op}")
            emit(cap, a.get("pids") or [], dur=1.4, side=e["side"],
                 phase=e["phase"])
        elif t == "flip":
            emit(f"{nm(a['pid'])} crew {res.get('state')}", [a["pid"]],
                 dur=1.0, side=e["side"], phase=e["phase"])
        elif t == "resolve_loss":
            parts = [f"{nm(ev['pid'])} {ev['event']}"
                     for ev in res.get("events", [])]
            emit("Losses: " + "; ".join(parts) if parts else "Losses allocated",
                 [ev["pid"] for ev in res.get("events", [])], dur=1.3,
                 side=e["side"], phase=e["phase"])
        elif t == "resolve_retreat":
            ret = res.get("retreated", [])
            emit("Retreat! " + ", ".join(f"{nm(x['pid'])} falls back to {x['to']}"
                                         for x in ret),
                 [x["pid"] for x in ret], dur=1.4, side=e["side"],
                 phase=e["phase"])
        elif t == "resolve_advance":
            adv = res.get("advanced", [])
            emit("Advance! " + ", ".join(nm(p) for p in adv)
                 + f" takes {res.get('hex')}", adv, thex=res.get("hex"),
                 dur=1.5, side=e["side"], phase=e["phase"])
        elif t == "resolve_esc_up":
            ups = res.get("esc_up", [])
            emit("Up the ladders! " + ", ".join(f"{nm(x['pid'])} gains the wall"
                                                for x in ups),
                 [x["pid"] for x in ups], dur=1.6, side=e["side"],
                 phase=e["phase"])
        elif t == "resolve_counterattack":
            outc = RES.get(res.get("result"), res.get("result"))
            emit(f"Counterattack through the gate at {res.get('counterattack')}"
                 f" — die {res.get('die')}: {outc}",
                 a.get("attackers") or [], thex=res.get("counterattack"),
                 dur=1.7, side=e["side"], phase=e["phase"])
        else:
            emit(t.replace("_", " "), dur=0.8, side=e["side"], phase=e["phase"])
    if dep_buf:
        emit(f"{SIDE_NAME[dep_side]} deployment", dep_buf, dur=0.45,
             side=dep_side)
    emit(None, dur=4.5, title="JUDAEAN VICTORY — the assault is repulsed",
         sub="Rome built up 0 of 10 wall hexes \u00b7 replay verified: 583/583 log entries")
    return tg, frames


def render(tg, frames):
    os.makedirs(OUT, exist_ok=True)
    pts = []
    for f in frames:
        for u in f["snap"]["units"]:
            pts.append((u["x"], u["y"]))
        for m in f["snap"]["marks"] + f["snap"]["over"]:
            pts.append((m["x"], m["y"]))
        for p in f.get("path") or []:
            pts.append(p)
    mp = Image.open(os.path.join(IMGD, "SoJ_map.jpg")).convert("RGB")
    pad = 160
    x0 = max(0, min(p[0] for p in pts) - pad)
    y0 = max(0, min(p[1] for p in pts) - pad)
    x1 = min(mp.width, max(p[0] for p in pts) + pad)
    y1 = min(mp.height, max(p[1] for p in pts) + pad)
    crop = mp.crop((int(x0), int(y0), int(x1), int(y1)))
    S = min(1.0, 1920 / crop.width, 1440 / crop.height)
    W = int(crop.width * S) // 2 * 2
    H = int(crop.height * S) // 2 * 2
    base = crop.resize((W, H), Image.LANCZOS)
    print(f"crop=({int(x0)},{int(y0)})-({int(x1)},{int(y1)}) scale={S:.3f} out={W}x{H}")

    cache, missing = {}, set()
    def cimg(name, done=False):
        key = (name, done)
        if key not in cache:
            if done:
                base_im = cimg(name)
                if base_im is None:
                    cache[key] = None
                else:
                    r, g, b, a = base_im.split()
                    d = Image.merge("RGB", (r, g, b))
                    d = ImageEnhance.Color(d).enhance(0.4)
                    d = ImageEnhance.Brightness(d).enhance(0.7)
                    d.putalpha(a)
                    cache[key] = d
                return cache[key]
            p = os.path.join(IMGD, name)
            if not os.path.exists(p):
                alt = name.rsplit("_", 1)[0] + ".gif"
                if os.path.exists(os.path.join(IMGD, alt)):
                    p = os.path.join(IMGD, alt)
                else:
                    missing.add(name)
                    cache[key] = None
                    return None
            im = Image.open(p).convert("RGBA")
            cache[key] = im.resize((max(2, int(im.width * S)),
                                    max(2, int(im.height * S))), Image.LANCZOS)
        return cache[key]

    try:
        fcap = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 30)
        fmid = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 56)
        fcor = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 26)
        fhud = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 24)
        fbig = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 72)
        fsub = ImageFont.truetype(r"C:\Windows\Fonts\segoeui.ttf", 32)
    except OSError:
        fcap = fmid = fcor = fhud = fbig = fsub = ImageFont.load_default()

    def tx(x, y):
        return ((x - x0) * S, (y - y0) * S)

    def wrap(txt, font, dr, maxw):
        lines, cur = [], ""
        for w_ in txt.split():
            t2 = (cur + " " + w_).strip()
            if dr.textlength(t2, font=font) > maxw and cur:
                lines.append(cur)
                cur = w_
            else:
                cur = t2
        lines.append(cur)
        return lines

    t = 0.0
    for f in frames:
        f["t0"] = t
        t += f["dur"]

    for i, f in enumerate(frames):
        im = base.copy().convert("RGBA")
        lay = Image.new("RGBA", im.size, (0, 0, 0, 0))
        dr = ImageDraw.Draw(lay)
        for m in f["snap"]["marks"]:
            ci = cimg(m["img"])
            if ci:
                fx, fy = tx(m["x"], m["y"])
                im.alpha_composite(ci, (int(fx - ci.width / 2), int(fy - ci.height / 2)))
        if f.get("path") and len(f["path"]) > 1:
            dr.line([tx(*p) for p in f["path"]], fill=(255, 215, 60, 230),
                    width=max(3, int(6 * S)))
            ex, ey = tx(*f["path"][-1])
            rr = max(4, int(9 * S))
            dr.ellipse([ex - rr, ey - rr, ex + rr, ey + rr],
                       fill=(255, 215, 60, 230))
        stacks = {}
        for u in f["snap"]["units"]:
            stacks.setdefault(u["hex"], []).append(u)
        pos = {}
        actors = set(f.get("actors") or [])
        for h, us in stacks.items():
            us.sort(key=lambda u: (u["up"], u["pid"] in actors))
            off = max(3, int(7 * S))
            for j, u in enumerate(us):
                ci = cimg(u["img"], u.get("done", False))
                if not ci:
                    continue
                fx, fy = tx(u["x"], u["y"])
                fx += j * off
                fy -= j * off
                im.alpha_composite(ci, (int(fx - ci.width / 2),
                                        int(fy - ci.height / 2)))
                pos[u["pid"]] = (fx, fy, ci.width)
        for o in f["snap"]["over"]:
            ci = cimg(o["img"])
            if ci:
                fx, fy = tx(o["x"], o["y"])
                im.alpha_composite(ci, (int(fx - ci.width / 2), int(fy - ci.height / 2)))
        if f.get("thex") and f["thex"] in tg.name_hex:
            fx, fy = tx(*tg.px[tg.name_hex[f["thex"]]])
            rr = max(14, int(46 * S))
            dr.ellipse([fx - rr, fy - rr, fx + rr, fy + rr],
                       outline=(255, 50, 40, 255), width=max(3, int(6 * S)))
        for pid in actors:
            if pid in pos:
                fx, fy, cw = pos[pid]
                rr = cw * 0.72
                dr.ellipse([fx - rr, fy - rr, fx + rr, fy + rr],
                           outline=(255, 215, 60, 255), width=max(2, int(5 * S)))
        im.alpha_composite(lay)
        dr2 = ImageDraw.Draw(im)
        if f.get("title"):
            im.alpha_composite(Image.new("RGBA", im.size, (0, 0, 0, 150)))
            dr2 = ImageDraw.Draw(im)
            tw = dr2.textlength(f["title"], font=fbig)
            dr2.text(((W - tw) / 2, H / 2 - 70), f["title"],
                     font=fbig, fill=(255, 240, 200, 255))
            if f.get("sub"):
                sw = dr2.textlength(f["sub"], font=fsub)
                dr2.text(((W - sw) / 2, H / 2 + 20), f["sub"],
                         font=fsub, fill=(230, 230, 230, 255))
        else:
            ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
            do = ImageDraw.Draw(ov)
            if f.get("cap") and f["dur"] >= 1.2:
                lines = wrap(f["cap"], fmid, do, W * 0.84)
                lh = 78
                y = (H - lh * len(lines)) / 2
                col = SIDE_COL.get(f.get("side"))
                for ln in lines:
                    tw = do.textlength(ln, font=fmid)
                    x = (W - tw) / 2
                    do.rounded_rectangle([x - 30, y - 6, x + tw + 30, y + 70],
                                         18, fill=(10, 10, 12, 175))
                    do.rectangle([x - 30, y - 6, x - 16, y + 70],
                                 fill=col + (235,))
                    do.text((x, y), ln, font=fmid, fill=(255, 255, 255, 255))
                    y += lh
            cy = 14
            for g in [g for g in frames[:i] if g.get("cap") and g["dur"] >= 1.2
                      and 0 < f["t0"] - g["t0"] < 5.0][-3:][::-1]:
                a = 1 - (f["t0"] - g["t0"]) / 5.0
                cap = g["cap"]
                if do.textlength(cap, font=fcor) > W * 0.4:
                    while do.textlength(cap + "\u2026", font=fcor) > W * 0.4:
                        cap = cap[:-1]
                    cap += "\u2026"
                tw = do.textlength(cap, font=fcor)
                x = W - tw - 44
                do.rounded_rectangle([x - 16, cy, x + tw + 16, cy + 42], 10,
                                     fill=(10, 10, 12, int(165 * a)))
                do.rectangle([x - 16, cy, x - 8, cy + 42],
                             fill=SIDE_COL.get(g.get("side")) + (int(220 * a),))
                do.text((x, cy + 5), cap, font=fcor,
                        fill=(255, 255, 255, int(255 * a)))
                cy += 50
            im.alpha_composite(ov)
            bar = Image.new("RGBA", (W, 62), (10, 10, 12, 185))
            im.alpha_composite(bar, (0, H - 62))
            dr2 = ImageDraw.Draw(im)
            dr2.rectangle([0, H - 62, 14, H], fill=SIDE_COL.get(f.get("side")))
            if f.get("cap"):
                dr2.text((30, H - 52), f["cap"], font=fcap,
                         fill=(255, 255, 255, 255))
            hud = (f"Turn {f['turn']} \u00b7 " if f["turn"] else "") \
                + PHASE.get(f["phase"], f["phase"])
            hw = dr2.textlength(hud, font=fhud)
            chip = Image.new("RGBA", (int(hw) + 28, 40), (10, 10, 12, 165))
            im.alpha_composite(chip, (12, 12))
            dr2 = ImageDraw.Draw(im)
            dr2.text((26, 18), hud, font=fhud, fill=(255, 230, 160, 255))
        im.convert("RGB").save(os.path.join(OUT, f"frame_{i:04d}.png"))
        if i % 50 == 0:
            print(f"frame {i}/{len(frames)}")
    if missing:
        print("MISSING IMAGES:", sorted(missing))
    with open(os.path.join(OUT, "list.txt"), "w") as fp:
        for i, f in enumerate(frames):
            fp.write(f"file 'frame_{i:04d}.png'\nduration {f['dur']}\n")
        fp.write(f"file 'frame_{len(frames) - 1:04d}.png'\n")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i",
                    "list.txt", "-fps_mode", "vfr", "-pix_fmt", "yuv420p",
                    "-c:v", "libx264", "-crf", "19",
                    "soj_gallus_playthrough.mp4"], cwd=OUT, check=True,
                   capture_output=True)
    total = sum(f["dur"] for f in frames)
    print(f"DONE: {len(frames)} frames, {total:.0f}s -> "
          + os.path.join(OUT, "soj_gallus_playthrough.mp4"))


if __name__ == "__main__":
    tg, frames = build_frames()
    render(tg, frames)
