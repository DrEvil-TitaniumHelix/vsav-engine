"""Render terrain_nf.json back onto the map for visual verification:
roads (red=primary, orange=secondary), streams (blue), bridges (black),
slopes (yellow=minor, magenta=sharp), villages (V), woods (W), elevation
tint. Output tiles mirror render_terrain_tiles.py."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "engine"))
import gamespec
from PIL import Image, ImageDraw

OUT = sys.argv[1] if len(sys.argv) > 1 else HERE
game = gamespec.load(HERE)
T = json.load(open(os.path.join(HERE, "terrain_nf.json")))
MAP = Image.open(r"C:\VassalIngest\austerlitz-gmt\assets\map.png").convert("RGB")

C0, C1 = T["area"]["cols"]
R0, R1 = T["area"]["rows"]
xs, ys = [], []
for c in (C0, C1):
    for r in (R0, R1):
        x, y = game.grid.hex_to_pixel(c, r)
        xs.append(x); ys.append(y)
x0, y0 = min(xs) - 50, min(ys) - 60
region = MAP.crop((x0, y0, max(xs) + 50, max(ys) + 60)).convert("RGB")
dr = ImageDraw.Draw(region)


def P(c, r):
    x, y = game.grid.hex_to_pixel(c, r)
    return x - x0, y - y0


def mid(a, b):
    ax, ay = P(*a); bx, by = P(*b)
    return (ax + bx) / 2, (ay + by) / 2


for kind, color, w in (("primary", "red", 7), ("secondary", "orange", 5)):
    for a, b in T["road_pairs"][kind]:
        dr.line([P(*a), P(*b)], fill=color, width=w)
for a, b in T["hexsides"]["stream"]:
    mx, my = mid(a, b)
    dr.ellipse([mx - 9, my - 9, mx + 9, my + 9], outline="blue", width=4)
for a, b in T["hexsides"]["bridge"]:
    mx, my = mid(a, b)
    dr.rectangle([mx - 10, my - 10, mx + 10, my + 10], outline="black", width=5)
for a, b in T["hexsides"]["minor_slope"]:
    mx, my = mid(a, b)
    dr.line([mx - 6, my - 6, mx + 6, my + 6], fill="yellow", width=4)
for a, b in T["hexsides"]["sharp_slope"]:
    mx, my = mid(a, b)
    dr.line([mx - 8, my + 8, mx + 8, my - 8], fill="magenta", width=6)
for key, t in T["hexes"].items():
    c, r = map(int, key.split(","))
    x, y = P(c, r)
    if t == "village":
        dr.text((x - 5, y - 26), "V", fill="purple")
    elif t == "woods":
        dr.text((x - 5, y - 26), "W", fill="darkgreen")
    lv = T["elevation"][key]
    dr.text((x + 8, y + 8), str(lv), fill="brown")

W, H = region.size
tw, th = W // 2, H // 2
for ty in range(2):
    for tx in range(2):
        tile = region.crop((tx * tw, ty * th, (tx + 1) * tw, (ty + 1) * th))
        tile = tile.resize((int(tw * 1.45), int(th * 1.45)), Image.LANCZOS)
        tile.save(os.path.join(OUT, f"nf_overlay_{ty}{tx}.png"))
print("overlay tiles ->", OUT)
