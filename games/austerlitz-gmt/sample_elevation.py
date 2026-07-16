"""Sample hex-center colors over the Northern Flank area and cluster into
elevation bands (the map's elevation fills are flat colors; contours are
smooth, so hex-center samples are reliable away from art features)."""
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "engine"))
import gamespec
from PIL import Image

game = gamespec.load(HERE)
MAP = Image.open(r"C:\VassalIngest\austerlitz-gmt\assets\map.png").convert("RGB")

C0, C1, R0, R1 = 38, 74, 2, 28
samples = {}
for c in range(C0, C1 + 1):
    for r in range(R0, R1 + 1):
        x, y = game.grid.hex_to_pixel(c, r)
        # median of a small ring of samples dodges thin art (roads, text)
        pts = []
        for dx, dy in ((0, 0), (14, 8), (-14, 8), (14, -8), (-14, -8),
                       (0, 18), (0, -18), (22, 0), (-22, 0)):
            px = MAP.getpixel((x + dx, y + dy))
            pts.append(px)
        pts.sort(key=lambda p: p[0] + p[1] + p[2])
        samples[f"{c},{r}"] = pts[len(pts) // 2]

# cluster by quantized color
buckets = Counter()
for v in samples.values():
    q = (v[0] // 12 * 12, v[1] // 12 * 12, v[2] // 12 * 12)
    buckets[q] += 1
print("top quantized colors:")
for q, n in buckets.most_common(14):
    print("  ", q, n)
json.dump(samples, open(os.path.join(
    os.path.dirname(HERE), "..", "..",  # placeholder, overwritten below
), "w")) if False else None
out = r"C:\Users\fisch\AppData\Local\Temp\claude\C--VassalArnhem\838ac18b-7d61-4f33-a640-dc51a8b58aff\scratchpad\nf_samples.json"
json.dump(samples, open(out, "w"))
print("saved", out)
