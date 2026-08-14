import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

GRIDS = r"C:\VassalNaW\grids"
OPP = {"N": "S", "S": "N", "NE": "SW", "SW": "NE", "NW": "SE", "SE": "NW"}

ED2_TOWN = """0210 0306 0308 0309 0409 0705 0706 0708 0808 0809 1013 1102 1103 1206 1306 1410
1519 1717 1811 1816 1817 1910 1917 2001 2110 2211 2407 2704 2716 2717""".split()

ED2_EXIT = [f"{c:02d}01" for c in range(1, 12)]


def load(name):
    return json.load(open(os.path.join(GRIDS, name)))


def neighbor(c, r, side, odd_down=True):
    if side == "N":
        return c, r - 1
    if side == "S":
        return c, r + 1
    down = (c % 2 == 1) if odd_down else (c % 2 == 0)
    if side == "NE":
        return (c + 1, r) if down else (c + 1, r - 1)
    if side == "SE":
        return (c + 1, r + 1) if down else (c + 1, r)
    if side == "NW":
        return (c - 1, r) if down else (c - 1, r - 1)
    if side == "SW":
        return (c - 1, r + 1) if down else (c - 1, r)
    raise ValueError(side)


def road_map(stats, cols, rows, thr, mutual_thr, odd_down=True):
    raw = {}
    for hid, v in stats.items():
        raw[hid] = {k: (val or 0.0) for k, val in v["sides"].items()}
    out = {}
    for hid, sides in raw.items():
        c, r = int(hid[:2]), int(hid[2:])
        keep = []
        for k, val in sides.items():
            if val < thr:
                continue
            nc, nr = neighbor(c, r, k, odd_down)
            nid = f"{nc:02d}{nr:02d}"
            edge = not (1 <= nc <= cols and 1 <= nr <= rows) or nid not in raw
            if edge or raw[nid].get(OPP[k], 0.0) >= mutual_thr:
                keep.append(k)
        out[hid] = sorted(keep)
    return out


def build_ed2(thr=0.09, mutual_thr=0.06):
    fo = load("ed2folio_stats.json")
    ol = load("ed2oliver_stats.json")
    g = load("ed2_canon.json")
    roads = road_map(fo, g["cols"], g["rows"], thr, mutual_thr)
    out = {}
    for c in range(1, g["cols"] + 1):
        for r in range(1, g["rows"] + 1):
            hid = f"{c:02d}{r:02d}"
            f, o = fo.get(hid), ol.get(hid)
            if not f or not o:
                continue
            woods = o["green"] > 0.5 and f["speck"] > 0.13
            town = hid in ED2_TOWN
            rs = roads.get(hid, [])
            kind = "woods" if woods else ("town" if town else "clear")
            if rs and kind == "woods":
                kind = "woods_road"
            out[hid] = {"kind": kind, "roads": rs, "exit": hid in ED2_EXIT,
                        "evidence": {"green_oliver": round(o["green"], 3), "speck_folio": round(f["speck"], 3),
                                     "blob_folio": round(f["blob"], 3)}}
    return g, out


def build_ed3(thr=0.09, mutual_thr=0.06, green_thr=0.5):
    st = load("ed3_stats.json")
    g = load("ed3_canon.json")
    rows_of = lambda c: g["rows"] if c % 2 == 1 else g["rows"] - 1
    st = {h: v for h, v in st.items() if int(h[2:]) <= rows_of(int(h[:2]))}
    roads = road_map(st, g["cols"], g["rows"], thr, mutual_thr, odd_down=False)
    out = {}
    for hid, v in st.items():
        woods = v["green"] > green_thr
        rs = roads.get(hid, [])
        kind = "woods_road" if woods and rs else ("woods" if woods else "clear")
        out[hid] = {"kind": kind, "roads": rs, "evidence": {"green": round(v["green"], 3)}}
    return g, out


def main():
    a = sys.argv[1:]
    g2, ed2 = build_ed2()
    if a and a[0] == "paint":
        from naw_terrain import paint
        classes = {h: (v["kind"] if v["kind"] != "clear" or not v["roads"] else "road") for h, v in ed2.items()}
        for h, v in ed2.items():
            if v["kind"] == "town" and v["roads"]:
                classes[h] = "town_road"
        boxes = {"nw": (0.03, 0.17, 0.40, 0.48), "n": (0.30, 0.17, 0.67, 0.48), "ne": (0.57, 0.17, 0.95, 0.48),
                 "sw": (0.03, 0.45, 0.40, 0.80), "s": (0.30, 0.45, 0.67, 0.80), "se": (0.57, 0.45, 0.95, 0.80)}
        for name, b in boxes.items():
            paint("ed2folio", g2, g2["cols"], g2["rows"], classes, f"p3_ed2_paint_{name}", box=b, maxw=1500)
        return
    from collections import Counter
    print("ED2", Counter(v["kind"] for v in ed2.values()), len(ed2))
    print("ED2 road hexes", sum(1 for v in ed2.values() if v["roads"]))
    g3, ed3 = build_ed3()
    print("ED3", Counter(v["kind"] for v in ed3.values()), len(ed3))
    print("ED3 road hexes", sum(1 for v in ed3.values() if v["roads"]))
    for hid in sorted(h for h, v in ed2.items() if v["kind"] == "woods_road"):
        print("  ed2 woods/road", hid, ed2[hid]["roads"])


if __name__ == "__main__":
    main()
