"""
extract_terrain.py - Read per-hex terrain + hexside features off the Arnhem map image.

Palette calibrated from the map's own Terrain Key (2026-07-01). Movement costs per the
printed key: Mixed 2 / Woods 2 / Broken 3 / Rough 4 / City 1 / Town 1; Road hex-to-hex 1/2;
Trail 1; River hexside PROHIBITED; Stream +3; Ferry +3; Bridges no add (crossing allowed).

Outputs ref/terrain.json:
  { "hexes":  {"0203": {"t":"city","road":true}, ...},
    "sides":  {"0203|0303": {"water":"river","road":true,"bridge":true}, ...} }
Hexes classified "offmap" (map frame, turn track, terrain key, holding boxes) are the
authoritative on-map/off-map mask.

Also renders ref/terrain_debug.png (downscaled overlay) for visual verification.
"""
import json, math, os, sys
from collections import Counter
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import arnhem

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MAP = os.path.join(ROOT, "ui", "assets", "map.png")
OUT = os.path.join(ROOT, "ref", "terrain.json")
DEBUG = os.path.join(ROOT, "ref", "terrain_debug.png")

COLS, ROWS = range(0, 41), range(0, 28)

PALETTE = {
    "base":   (240, 230, 203),
    "woods1": (37, 116, 0), "woods2": (138, 177, 15),
    "broken": (198, 176, 152),
    "rough":  (207, 157, 42),
    "city":   (111, 70, 50),
    "town":   (127, 127, 127),
    "river":  (4, 131, 177),
    "stream": (35, 160, 205),
    "road":   (128, 93, 68),
    "white":  (255, 255, 229),
    "black":  (0, 0, 0),
    "frame1": (112, 97, 78),    # map frame (inner)
    "frame2": (192, 192, 192),  # canvas outside the sheet
}
MAXDIST = 45  # per-pixel sum-abs distance to count as a class

UNTINTED = ("white", "black", "frame1", "frame2", None)
# top-right GAME TURN TRACK + TERRAIN KEY box = off-map (holding area for reinforcements)
KEY_RECT = lambda x, y: x > 2790 and y < 660
# blue "WESTWALL Arnhem" title + map-edge text: suppress WATER detection here (text is river-blue)
TITLE_RECT = lambda x, y: 150 < x < 730 and 2780 < y < 3080


def classify_px(p):
    best, bd = None, MAXDIST
    for name, c in PALETTE.items():
        d = abs(p[0]-c[0]) + abs(p[1]-c[1]) + abs(p[2]-c[2])
        if d < bd:
            best, bd = name, d
    return best


class Extractor:
    def __init__(self):
        self.im = Image.open(MAP).convert("RGB")
        self.W, self.H = self.im.size
        self.px = self.im.load()

    def sample_disc(self, cx, cy, r, step=3):
        c = Counter()
        for dx in range(-r, r+1, step):
            for dy in range(-r, r+1, step):
                if dx*dx + dy*dy > r*r:
                    continue
                x, y = int(cx+dx), int(cy+dy)
                if 0 <= x < self.W and 0 <= y < self.H:
                    c[classify_px(self.px[x, y])] += 1
        return c

    def hex_terrain(self, col, row):
        x, y = arnhem.hex_to_pixel(col, row)
        if not (40 <= x < self.W-10 and 40 <= y < self.H-10):
            return None
        if KEY_RECT(x, y):
            return dict(t="offmap")
        # disc shifted +12px down / r=34 keeps the printed hex number (top of hex,
        # antialiased gray = town color) out of the sample
        c = self.sample_disc(x, y+12, 34)
        total = sum(c.values()) or 1
        untinted = sum(c[k] for k in UNTINTED)
        if untinted / total > 0.42:          # frame / edge of sheet
            return dict(t="offmap")
        water = c["river"] + c["stream"]
        if water / total > 0.45:
            return dict(t="water")
        # priority: point features first, then area tints. City/town are merged: both
        # cost 1 MP and the map prints village blocks in both colors — call it "town".
        if c["city"] + c["town"] >= 18:
            t = "town"
        elif c["woods1"] + c["woods2"] >= 30:
            t = "woods"
        elif c["rough"] >= 60:
            t = "rough"
        elif c["broken"] >= 100:
            t = "broken"
        else:
            t = "mixed"
        out = dict(t=t)
        if c["road"] >= 6:
            out["road"] = True
        return out

    def line_counts(self, x1, y1, x2, y2, lo, hi, r=6):
        """Class counts in a band along the centre line from fraction lo..hi."""
        c = Counter()
        steps = 30
        for i in range(steps+1):
            f = lo + (hi-lo)*i/steps
            cx, cy = x1+(x2-x1)*f, y1+(y2-y1)*f
            for dx in range(-r, r+1, 2):
                for dy in range(-r, r+1, 2):
                    x, y = int(cx+dx), int(cy+dy)
                    if 0 <= x < self.W and 0 <= y < self.H:
                        c[classify_px(self.px[x, y])] += 1
        return c

    def hexside(self, a, b):
        """Features on the hexside between hex a=(c,r) and b=(c,r)."""
        x1, y1 = arnhem.hex_to_pixel(*a)
        x2, y2 = arnhem.hex_to_pixel(*b)
        mid = self.line_counts(x1, y1, x2, y2, 0.40, 0.60, r=8)
        out = {}
        mx, my = (x1+x2)/2, (y1+y2)/2
        if (mid["river"] >= 8 or mid["stream"] >= 8) and not TITLE_RECT(mx, my):
            out["water"] = "river" if mid["river"] >= mid["stream"] else "stream"
        # road/trail connection: road pixels near the edge on BOTH sides, then classify
        # by line coverage (solid road ~1.0, dashed trail ~0.5-0.7, corner-graze < 0.45)
        s1 = self.line_counts(x1, y1, x2, y2, 0.20, 0.38, r=6)
        s2 = self.line_counts(x1, y1, x2, y2, 0.62, 0.80, r=6)
        if s1["road"] >= 4 and s2["road"] >= 4:
            cov = self.coverage(x1, y1, x2, y2)
            if cov >= 0.80:
                out["road"] = "road"
            elif cov >= 0.45:
                out["road"] = "trail"
            if out.get("road") and "water" in out:
                out["bridge"] = True
        return out

    def coverage(self, x1, y1, x2, y2):
        """Fraction of steps along the centre line with a road pixel within +/-8px."""
        steps, hit = 40, 0
        for i in range(steps+1):
            f = 0.15 + 0.70*i/steps
            cx, cy = x1+(x2-x1)*f, y1+(y2-y1)*f
            found = False
            for dx in range(-8, 9, 2):
                for dy in range(-8, 9, 2):
                    x, y = int(cx+dx), int(cy+dy)
                    if 0 <= x < self.W and 0 <= y < self.H and \
                       classify_px(self.px[x, y]) == "road":
                        found = True
                        break
                if found:
                    break
            hit += found
        return hit / (steps+1)


def main():
    ex = Extractor()
    hexes, sides = {}, {}
    for col in COLS:
        for row in ROWS:
            t = ex.hex_terrain(col, row)
            if t:
                hexes[f"{col:02d}{row:02d}"] = t
    onmap = {h for h, v in hexes.items() if v["t"] not in ("offmap",)}
    print(f"{len(hexes)} hexes classified, {len(onmap)} on-map")
    n = 0
    for h in sorted(onmap):
        c, r = int(h[:2]), int(h[2:])
        for nb in arnhem_neighbors(c, r):
            nh = f"{nb[0]:02d}{nb[1]:02d}"
            if nh not in onmap or (nh, h) in seen or (h, nh) in seen:
                continue
            seen.add((h, nh))
            feat = ex.hexside((c, r), nb)
            if feat:
                sides[f"{h}|{nh}"] = feat
                n += 1
    print(f"{n} hexsides with features")
    json.dump(dict(hexes=hexes, sides=sides), open(OUT, "w"), indent=1)
    print("wrote", OUT)
    render_debug(hexes, sides)


def arnhem_neighbors(c, r):
    import rules
    return rules.neighbors(c, r)


seen = set()

TCOLOR = {"mixed": (250, 245, 225), "woods": (60, 160, 40), "broken": (185, 160, 130),
          "rough": (215, 165, 40), "city": (140, 60, 40), "town": (120, 120, 130),
          "water": (30, 120, 200), "offmap": (0, 0, 0)}


def render_debug(hexes, sides):
    scale = 0.25
    im = Image.open(MAP).convert("RGB")
    im = im.resize((int(im.width*scale), int(im.height*scale)), Image.LANCZOS)
    dr = ImageDraw.Draw(im, "RGBA")
    for h, v in hexes.items():
        c, r = int(h[:2]), int(h[2:])
        x, y = arnhem.hex_to_pixel(c, r)
        x, y = x*scale, y*scale
        col = TCOLOR[v["t"]]
        dr.ellipse([x-7, y-7, x+7, y+7], fill=col + (170,),
                   outline=(0, 0, 0, 200))
        if v.get("road"):
            dr.ellipse([x-2, y-2, x+2, y+2], fill=(80, 40, 20, 255))
    for key, f in sides.items():
        a, b = key.split("|")
        x1, y1 = arnhem.hex_to_pixel(int(a[:2]), int(a[2:]))
        x2, y2 = arnhem.hex_to_pixel(int(b[:2]), int(b[2:]))
        mx, my = (x1+x2)/2*scale, (y1+y2)/2*scale
        if f.get("bridge"):
            dr.rectangle([mx-5, my-5, mx+5, my+5], fill=(255, 0, 255, 230))
        elif f.get("water") == "river":
            dr.rectangle([mx-4, my-4, mx+4, my+4], fill=(255, 40, 40, 230))
        elif f.get("water") == "stream":
            dr.rectangle([mx-3, my-3, mx+3, my+3], fill=(255, 150, 40, 230))
        elif f.get("road") == "road":
            dr.line([mx-4, my, mx+4, my], fill=(0, 0, 0, 230), width=3)
        elif f.get("road") == "trail":
            dr.line([mx-4, my, mx+4, my], fill=(90, 90, 90, 230), width=2)
    im.save(DEBUG)
    print("wrote", DEBUG)


if __name__ == "__main__":
    main()
