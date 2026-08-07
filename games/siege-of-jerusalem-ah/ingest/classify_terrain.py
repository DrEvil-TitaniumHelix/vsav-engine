"""SoJ map terrain classifier — first pass.

Samples every letter-grid hex of SoJ_map.jpg and emits a candidate class:
  ring:  fortress (red ring) / fort (orange ring) / bastion (blue ring)
  wall:  gray stone band crossing the hex (wall/gate candidates)
  fill:  builtup / edifice / slope / clear
Output: C:\\VassalSoJ\\terrain_pass1.json  {hexname: {cls, ring, wall_frac, dark_frac, ...}}
Hand verification pass follows; gates/north-wall arc/staircases are hand-annotated.
"""
import json, math
from PIL import Image
import numpy as np

im = Image.open(r'C:\VassalSoJ\extracted\images\SoJ_map.jpg').convert('RGB')
W, H = im.size
A = np.asarray(im, dtype=np.int16)

DX, CX = 71.0749, 207.60
DY, CY = 82.2902, -1840.52

def center(L, N):
    return CX + DX * L, CY + DY * (N + L / 2.0)

def letters(L):
    return chr(64 + L) if L <= 26 else chr(64 + L - 26) * 2

# hex geometry: flat-top, width = 4/3*dx? For flat-top: dx = 0.75*width -> width = dx/0.75
R = DX / 1.5  # circumradius ~47.4
r_in = DY / 2  # inradius ~41.1

def sample_disc(cx, cy, rad, step=3):
    xs, ys = [], []
    for yy in range(int(cy - rad), int(cy + rad) + 1, step):
        for xx in range(int(cx - rad), int(cx + rad) + 1, step):
            if 0 <= xx < W and 0 <= yy < H and (xx - cx) ** 2 + (yy - cy) ** 2 <= rad * rad:
                xs.append(xx); ys.append(yy)
    if not xs:
        return None
    return A[np.array(ys), np.array(xs)]

def sample_ring(cx, cy, rad, n=72):
    pts = []
    for k in range(n):
        t = 2 * math.pi * k / n
        xx, yy = int(cx + rad * math.cos(t)), int(cy + rad * math.sin(t))
        if 0 <= xx < W and 0 <= yy < H:
            pts.append(A[yy, xx])
    return np.array(pts) if pts else None

def classify(L, N):
    cx, cy = center(L, N)
    if not (30 <= cx < W - 5 and 30 <= cy < H - 5):
        return None
    out = {}
    # --- ring colors (two radii to catch ring thickness) ---
    ring = np.concatenate([p for p in (sample_ring(cx, cy, r_in * 0.94),
                                       sample_ring(cx, cy, r_in * 0.82)) if p is not None])
    rr, gg, bb = ring[:, 0], ring[:, 1], ring[:, 2]
    red = ((rr > 150) & (gg < 90) & (bb < 90)).mean()
    orange = ((rr > 180) & (gg > 90) & (gg < 170) & (bb < 80)).mean()
    blue = ((bb > 130) & (rr < 100) & (gg > 80) & (gg < 180)).mean()
    out['ring'] = {'red': round(float(red), 3), 'orange': round(float(orange), 3),
                   'blue': round(float(blue), 3)}
    # --- disc fill ---
    disc = sample_disc(cx, cy, r_in * 0.85)
    rr, gg, bb = disc[:, 0].astype(float), disc[:, 1].astype(float), disc[:, 2].astype(float)
    v = (rr + gg + bb) / 3
    sat = (np.max(disc, axis=1) - np.min(disc, axis=1)).astype(float)
    # gray stone (walls / buildings): low saturation, mid value
    gray = ((sat < 40) & (v > 90) & (v < 190)).mean()
    dark = (v < 95).mean()
    # slope: red-brown — r noticeably above g and b, mid-dark
    slope = ((rr - gg > 25) & (gg - bb > 10) & (v < 165)).mean()
    tan = ((rr > 150) & (rr - bb > 40) & (rr - bb < 110) & (v > 140)).mean()
    out.update(gray=round(float(gray), 3), dark=round(float(dark), 3),
               slope=round(float(slope), 3), tan=round(float(tan), 3),
               v=round(float(v.mean()), 1))
    # --- verdict ---
    cls = 'clear'
    if slope > 0.30: cls = 'slope'
    if gray > 0.22 or dark > 0.30: cls = 'builtup'
    if gray > 0.22 and v.mean() < 120: cls = 'edifice'
    if out['ring']['blue'] > 0.10: cls = 'bastion'
    if out['ring']['orange'] > 0.10: cls = 'fort'
    if out['ring']['red'] > 0.10: cls = 'fortress'
    # wall candidate: strong gray band but not builtup texture — refine by hand
    out['cls'] = cls
    return out

result = {}
for L in range(1, 51):
    # N range: map top y>~230 -> N > (230+1840)/82.3 - L/2 ; bottom y<5400
    n_lo = math.ceil((235 - CY) / DY - L / 2)
    n_hi = math.floor((5400 - CY) / DY - L / 2)
    for N in range(n_lo, n_hi + 1):
        c = classify(L, N)
        if c:
            result[f'{letters(L)}{N}'] = c

json.dump(result, open(r'C:\VassalSoJ\terrain_pass1.json', 'w'), indent=0)
import collections
print(len(result), 'hexes classified')
print(collections.Counter(v['cls'] for v in result.values()))
