import json
import math
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from naw_render import DOCS, page_image

Image.MAX_IMAGE_PIXELS = None

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = r"C:\VassalNaW\prep_packs\NAW_PREP6"
OUT = os.path.join(HERE, "asset_tier_measure.json")
ED2 = r"C:\VassalNaW\modules\ed2_oliver\images"
ED3 = r"C:\VassalNaW\modules\ed3_davejm\images"

WIN = 512
NPATCH = 10

ASSETS = [
    ("ed2_folio_p1_rules", ("pdf", "ed2scan", 1), "scan", "printed 2nd Ed rules sheet, PREP-1 tier PRIMARY"),
    ("ed2_folio_p2_examples", ("pdf", "ed2scan", 2), "scan", "printed 2nd Ed Examples of Attacks, PREP-1 tier PRIMARY"),
    ("ed2_folio_p4_counterphoto", ("pdf", "ed2scan", 4), "scan", "photograph of punched 2nd Ed counters, PREP-4 witness A"),
    ("ed2_folio_p5_mapsheet", ("pdf", "ed2scan", 5), "scan", "printed 2nd Ed map sheet + charts, PREP-1 tier PRIMARY"),
    ("ed2_expansion_p1", ("pdf", "ed2exp", 1), "scan", "SPI Advanced Game Expansion Kit 1971, out-of-edition primary; PREP-6 inspected t_ed2_expansion_p1: period type with ink irregularity, descreened and thresholded to near-bitonal"),
    ("ed3_booklet_p7", ("pdf", "ed3", 7), "scan", "printed later-edition rules booklet p.9, PREP-1 tier PRIMARY"),
    ("ed3_booklet_p9", ("pdf", "ed3", 9), "scan", "printed later-edition booklet, combat sections"),
    ("ed3_booklet_p11", ("pdf", "ed3", 11), "scan", "printed later-edition Examples of Attacks"),
    ("ed3_webscaffold_p3", ("pdf", "ed3", 3), "digital", "fan web transcription printed to PDF, PREP-1 scaffold-only"),
    ("ed3_sabin2020_p14", ("pdf", "ed3", 14), "digital", "Sabin Simple Rules Tweaks April 2020, third-party"),
    ("sabin2023_p2", ("pdf", "sabin", 2), "digital", "Sabin Improved Rules Tweaks Nov 2023, third-party"),
    ("fan_revamp_rules_p5", ("pdf", "rules", 5), "digital", "Christensen 2024 LaTeX revamp, never a citation"),
    ("fan_revamp_org_p1", ("pdf", "org", 1), "digital", "2024 revamp OOB charts, never a citation"),
    ("ed2mod_map", ("file", os.path.join(ED2, "Nap at Waterloo map 20mm hexes.jpg")), "scan_restored", "Oliver map restoration, PREP-2 faithful reproduction; PREP-6 inspected t_ed2mod_map: scanned paper tone, soft hex rule, JPEG fringing on the printed title"),
    ("ed2mod_crt", ("file", os.path.join(ED2, "NapatWatCRT.jpg")), "scan", "Oliver CRT, PREP-2 faithful reproduction; PREP-6 inspected t_ed2mod_crt: period type, visible halftone screen in the grey bands, cream paper, contrast-boosted"),
    ("ed2mod_tec", ("file", os.path.join(ED2, "NapatWat TEC.jpg")), "scan", "Oliver TEC, PREP-2 faithful reproduction; PREP-6 inspected t_ed2mod_tec: period type, cream paper, a pink printer guide line still present, contrast-boosted"),
    ("mod_grouchy_sheet", ("file", os.path.join(ED2, "Grouchy Variant.jpg")), "hybrid", "PREP-2 M2 retimed edit; PREP-6 inspected t_mod_grouchy_sheet: thresholded scan of printed text with retyped passages in a heavier face and digitally drawn Var counters"),
    ("mod_nameplate", ("file", os.path.join(ED2, "NAW 2nd Edition nameplate.png")), "unknown", "2nd Ed nameplate, PREP-2 M5, byte-identical in both modules; production method never established"),
    ("mod_counter_NAW_1_2", ("file", os.path.join(ED2, "NAW_1_2.png")), "digital", "counter art, PREP-4 REDRAW; PREP-6 inspected t_counter_NAW_1_2_zoom: flat fill, rounded corners with red bleed, sans digits, vector NATO symbol, FOUR items only, no setup hex"),
    ("mod_counter_NAW_2_3", ("file", os.path.join(ED2, "NAW_2_3.png")), "digital", "counter art, PREP-4 REDRAW"),
    ("mod_counter_NAW_5_2", ("file", os.path.join(ED2, "NAW_5_2.png")), "digital", "counter art, PREP-4 REDRAW"),
    ("mod_counter_variant_1_1", ("file", os.path.join(ED2, "NapWatvariant_1_1.png")), "digital", "Grouchy variant counter, PREP-4 REDRAW and out-of-edition"),
    ("ed3mod_map", ("file", os.path.join(ED3, "Map to use 3 copy.jpg")), "digital", "davejm map, PREP-3 not promoted to terrain authority; PREP-6 inspected t_ed3mod_map: synthetic parchment fill, modern serif hex numerals, vector hex rule, flat crimson buildings"),
    ("ed3mod_crt", ("file", os.path.join(ED3, "CRT.jpg")), "digital", "davejm CRT, PREP-2 redraw but 60/60 correct; PREP-6 inspected t_ed3mod_crt: modern serif on synthetic parchment gradient, ratios retyped as 1:2 where the folio prints 1 to 2"),
    ("ed3mod_tec", ("file", os.path.join(ED3, "TEC.png")), "digital", "davejm TEC, PREP-2 M1 contaminated redraw; PREP-6 inspected t_ed3mod_tec: modern serif, drop shadows, synthetic parchment hex fills, vector hex outlines"),
    ("ed3mod_aid_2020", ("file", os.path.join(ED3, "2020 Aid.png")), "digital", "Sabin 2020 play aid shipped in module, third-party"),
    ("ed3mod_aid_2023", ("file", os.path.join(ED3, "2023 Aid.png")), "digital", "Sabin 2023 play aid shipped in module, third-party"),
    ("ed3mod_aid_movement", ("file", os.path.join(ED3, "Movement.png")), "digital", "module-authored rules aid"),
]

SIGNALS = [
    ("flat_frac", "redraw", 0.35, 0.09, 1.5),
    ("noise_sigma", "scan", 1.10, 0.40, 1.5),
    ("top8_mass", "redraw", 0.55, 0.13, 1.0),
    ("palette_log10_per_mpx", "scan", 4.30, 0.35, 1.0),
    ("pure_black_share", "redraw", 0.25, 0.12, 1.2),
    ("gray_chroma", "scan", 6.00, 2.00, 1.0),
    ("edge_band_ratio", "scan", 3.00, 0.90, 1.0),
    ("axis_concentration", "redraw", 0.35, 0.10, 0.6),
]

REPORTED_ONLY = ["bg_texture", "jpeg_block_ratio", "pure_white_share", "alpha_present", "alpha_soft_frac",
                 "skew_deg", "megapixels", "patches"]


def load(spec):
    if spec[0] == "pdf":
        import fitz
        doc = fitz.open(DOCS[spec[1]])
        im = page_image(doc, spec[2], 300)
    else:
        im = Image.open(spec[1])
    alpha = None
    if im.mode in ("RGBA", "LA"):
        alpha = np.asarray(im.convert("RGBA"))[:, :, 3].astype(np.float32)
    return im.convert("RGB"), alpha


def patches(rgb):
    h, w = rgb.shape[:2]
    win = int(min(WIN, h, w))
    g = rgb.mean(axis=2)
    cand = []
    for y in range(0, max(1, h - win + 1), win):
        for x in range(0, max(1, w - win + 1), win):
            t = g[y:y + win, x:x + win]
            if t.shape != (win, win):
                continue
            cand.append((float(t.std()), y, x))
    if not cand:
        return [(0, 0)], win
    cand.sort(key=lambda c: (-c[0], c[1], c[2]))
    return [(y, x) for _, y, x in cand[:NPATCH]], win


def immerkaer(g):
    k = np.array([[1.0, -2.0, 1.0], [-2.0, 4.0, -2.0], [1.0, -2.0, 1.0]])
    r = ndimage.convolve(g, k, mode="reflect")
    return float(1.4826 * np.median(np.abs(r)) / 6.0)


def sobel(g):
    gx = ndimage.sobel(g, axis=1, mode="reflect")
    gy = ndimage.sobel(g, axis=0, mode="reflect")
    return gx, gy, np.hypot(gx, gy)


def measure_patch(rgb, a=None):
    g = rgb.mean(axis=2)
    lum = g
    out = {}
    out["noise_sigma"] = immerkaer(g)
    mx = ndimage.maximum_filter(g, size=3)
    mn = ndimage.minimum_filter(g, size=3)
    out["flat_frac"] = float(((mx - mn) < 0.75).mean())
    flat = rgb.reshape(-1, 3).astype(np.uint8)
    vals, counts = np.unique(flat, axis=0, return_counts=True)
    n = flat.shape[0]
    out["palette_log10_per_mpx"] = float(math.log10(max(1.0, len(vals) * 1e6 / n)))
    counts = np.sort(counts)[::-1]
    out["top8_mass"] = float(counts[:8].sum() / n)
    dark = lum <= 64
    pb = (rgb <= 6).all(axis=2)
    out["pure_black_share"] = float(pb[dark].mean()) if dark.sum() > 200 else 0.0
    light = lum >= 200
    pw = (rgb >= 250).all(axis=2)
    out["pure_white_share"] = float(pw[light].mean()) if light.sum() > 200 else 0.0
    spread = rgb.max(axis=2) - rgb.min(axis=2)
    sel = (spread <= 40) & (lum >= 30) & (lum <= 240)
    out["gray_chroma"] = float(spread[sel].mean()) if sel.sum() > 200 else 0.0
    gx, gy, mag = sobel(g)
    gmax = float(np.percentile(mag, 99.5)) or 1.0
    core = mag > 0.50 * gmax
    band = (mag > 0.12 * gmax) & ~core
    near = ndimage.binary_dilation(mag > 0.12 * gmax, iterations=3)
    bg = light & ~near
    out["bg_texture"] = float(g[bg].std()) if bg.sum() > 400 else 0.0
    out["edge_band_ratio"] = float(band.sum() / max(1, core.sum()))
    th = np.degrees(np.arctan2(gy[core], gx[core]))
    if th.size > 200:
        f = ((th + 45.0) % 90.0) - 45.0
        hist, edges = np.histogram(f, bins=360, range=(-45, 45))
        out["axis_concentration"] = float((np.abs(f) <= 2.0).mean())
        out["skew_deg"] = float((edges[int(hist.argmax())] + edges[int(hist.argmax()) + 1]) / 2.0)
    else:
        out["axis_concentration"] = 0.0
        out["skew_deg"] = 0.0
    if g.shape[1] > 24:
        d = np.abs(np.diff(g, axis=1))
        idx = np.arange(d.shape[1])
        db = float(d[:, idx % 8 == 7].mean())
        dn = float(d[:, idx % 8 == 3].mean())
        out["jpeg_block_ratio"] = db / dn if dn > 1e-6 else 0.0
    else:
        out["jpeg_block_ratio"] = 0.0
    if a is not None:
        out["alpha_soft_frac"] = float(((a > 8) & (a < 247)).mean())
    return out


def logistic(x, x0, k):
    return 1.0 / (1.0 + math.exp(-(x - x0) / k))


def score(m):
    parts = {}
    num = den = 0.0
    for name, direction, x0, k, w in SIGNALS:
        v = m.get(name)
        if v is None:
            continue
        p = logistic(v, x0, k)
        if direction == "scan":
            p = 1.0 - p
        parts[name] = round(p, 3)
        num += w * p
        den += w
    s = num / den if den else 0.0
    if s >= 0.66:
        v = "redraw-like"
    elif s <= 0.34:
        v = "scan-like"
    else:
        v = "borderline"
    return s, v, parts


def measure(spec):
    im, alpha = load(spec)
    rgb = np.asarray(im).astype(np.float32)
    h, w = rgb.shape[:2]
    locs, win = patches(rgb)
    rows = []
    for y, x in locs:
        a = alpha[y:y + win, x:x + win] if alpha is not None else None
        rows.append(measure_patch(rgb[y:y + win, x:x + win], a))
    agg = {}
    for k in rows[0]:
        agg[k] = float(np.median([r[k] for r in rows if k in r]))
    agg["megapixels"] = round(h * w / 1e6, 2)
    agg["patches"] = len(rows)
    agg["window_px"] = win
    agg["alpha_present"] = alpha is not None
    if alpha is None:
        agg["alpha_soft_frac"] = 0.0
    agg["size_px"] = [w, h]
    agg["patch_origins"] = [[int(x), int(y)] for y, x in locs]
    s, v, parts = score(agg)
    agg["redraw_score"] = round(s, 3)
    agg["measured_verdict"] = v
    agg["signal_votes"] = parts
    return agg, im, locs, win


def panel(name, im, locs, win):
    os.makedirs(PACK, exist_ok=True)
    cells = []
    for y, x in locs[:6]:
        c = im.crop((x, y, x + win, y + win))
        n = min(256, win)
        z = c.crop((0, 0, n, n)).resize((512, 512), Image.NEAREST)
        cells.append(z)
    if not cells:
        return None
    sheet = Image.new("RGB", (512 * len(cells), 512), (255, 255, 255))
    for i, c in enumerate(cells):
        sheet.paste(c, (512 * i, 0))
    p = os.path.join(PACK, f"t_{name}.png")
    sheet.save(p)
    return p


def run(names, do_pack):
    reg = {a[0]: a for a in ASSETS}
    sel = [reg[n] for n in names] if names else ASSETS
    results = {}
    for name, spec, byeye, note in sel:
        try:
            agg, im, locs, win = measure(spec)
        except Exception as e:
            print(f"{name:28s} ERROR {e}")
            results[name] = {"error": str(e)}
            continue
        agg["by_eye_production"] = byeye
        agg["by_eye_note"] = note
        expect = {"scan": "scan-like", "scan_restored": "scan-like", "digital": "redraw-like"}.get(byeye)
        agg["agrees_with_eye"] = None if expect is None else (agg["measured_verdict"] == expect)
        agg["source"] = list(spec)
        if do_pack:
            agg["panel"] = panel(name, im, locs, win)
        results[name] = agg
        mark = {True: "AGREE", False: "DISAGREE", None: "no-call"}[agg["agrees_with_eye"]]
        print(f"{name:28s} score={agg['redraw_score']:.3f} {agg['measured_verdict']:12s} eye={byeye:13s} {mark:8s} "
              f"flat={agg['flat_frac']:.3f} noise={agg['noise_sigma']:.2f} top8={agg['top8_mass']:.3f} "
              f"pal={agg['palette_log10_per_mpx']:.2f} pb={agg['pure_black_share']:.3f} "
              f"gc={agg['gray_chroma']:.2f} eb={agg['edge_band_ratio']:.2f} ax={agg['axis_concentration']:.3f} bgt={agg['bg_texture']:.2f} "
              f"jb={agg['jpeg_block_ratio']:.2f} a={int(agg['alpha_present'])}")
    return results


def write(results):
    doc = {
        "produced_by": "games/napoleon-at-waterloo/ingest/naw_asset_tier.py",
        "bite": "PREP-6",
        "what_this_measures": "PRODUCTION METHOD ONLY: whether the pixels were made by a scanner pointed at printed paper, or by a drawing program. It does not measure CONTENT FIDELITY and must never be read as a tier assignment. An asset can be digitally redrawn and still faithful, and can be a true scan of a document that is worthless as authority.",
        "signals": [{"name": n, "favours": d, "midpoint": x0, "slope": k, "weight": w} for n, d, x0, k, w in SIGNALS],
        "reported_but_unweighted": REPORTED_ONLY,
        "thresholds": {"redraw_like": ">=0.66", "borderline": "0.34-0.66", "scan_like": "<=0.34"},
        "window_px": WIN,
        "patches_per_asset": NPATCH,
        "patch_selection": "highest-ink windows, deterministic, native resolution, no rescaling",
        "assets": results,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")
    print(f"\n{OUT}  assets={len(results)}")


def main():
    a = sys.argv[1:]
    do_pack = "--pack" in a
    a = [t for t in a if not t.startswith("--")]
    if a and a[0] == "list":
        for n, spec, eye, note in ASSETS:
            print(f"{n:28s} {eye:8s} {note}")
        return
    if a and os.path.exists(a[0]):
        agg, im, locs, win = measure(("file", a[0]))
        print(json.dumps({k: v for k, v in agg.items() if k != "patch_origins"}, indent=1))
        return
    write(run(a, do_pack))


if __name__ == "__main__":
    main()
