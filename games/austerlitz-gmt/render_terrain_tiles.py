"""Render the Northern Flank map area as labeled tiles for terrain
classification (hex centers + col,row labels overlaid)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "engine"))
import gamespec
from PIL import Image, ImageDraw

OUT = sys.argv[1] if len(sys.argv) > 1 else HERE
game = gamespec.load(HERE)
MAP = Image.open(r"C:\VassalIngest\austerlitz-gmt\assets\map.png")

C0, C1, R0, R1 = 38, 74, 2, 28
xs, ys = [], []
for c in (C0, C1):
    for r in (R0, R1):
        x, y = game.grid.hex_to_pixel(c, r)
        xs.append(x)
        ys.append(y)
x0, x1 = min(xs) - 50, max(xs) + 50
y0, y1 = min(ys) - 60, max(ys) + 60

region = MAP.crop((x0, y0, x1, y1)).convert("RGB")
dr = ImageDraw.Draw(region)
for c in range(C0, C1 + 1):
    for r in range(R0, R1 + 1):
        x, y = game.grid.hex_to_pixel(c, r)
        px, py = x - x0, y - y0
        dr.ellipse([px - 3, py - 3, px + 3, py + 3], fill="red")
        dr.text((px - 16, py + 4), f"{c},{r}", fill="red")

# split into 2x2 tiles, upscale 1.6x for legibility
W, H = region.size
tw, th = W // 2, H // 2
for ty in range(2):
    for tx in range(2):
        tile = region.crop((tx * tw, ty * th, (tx + 1) * tw, (ty + 1) * th))
        tile = tile.resize((int(tw * 1.6), int(th * 1.6)), Image.LANCZOS)
        tile.save(os.path.join(OUT, f"nf_tile_{ty}{tx}.png"))
print("region px", region.size, "tiles saved to", OUT)
