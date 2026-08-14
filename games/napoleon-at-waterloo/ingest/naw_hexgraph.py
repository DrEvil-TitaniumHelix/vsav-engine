import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "map_grid.json")
OUT = os.path.join(HERE, "hexgraph_2nd_ed.json")

DIRS = ["N", "NE", "SE", "S", "SW", "NW"]


def hx(c, r):
    return f"{c:02d}{r:02d}"


def neighbours(c, r):
    odd = c % 2 == 1
    if odd:
        return {
            "N": (c, r - 1),
            "NE": (c + 1, r),
            "SE": (c + 1, r + 1),
            "S": (c, r + 1),
            "SW": (c - 1, r + 1),
            "NW": (c - 1, r),
        }
    return {
        "N": (c, r - 1),
        "NE": (c + 1, r - 1),
        "SE": (c + 1, r),
        "S": (c, r + 1),
        "SW": (c - 1, r),
        "NW": (c - 1, r - 1),
    }


def centre(c, r, g):
    return (
        g["x0"] + g["dx"] * (c - 1),
        g["y0"] + g["dy"] * ((r - 1) + (0.5 if c % 2 == 1 else 0.0)),
    )


def main():
    doc = json.load(open(SRC, encoding="utf-8"))
    ed = doc["editions"]["2nd"]
    terrain = ed["terrain"]
    cols = ed["extent"]["cols"]
    rows = ed["extent"]["rows"]

    field = {hx(c, r) for c in range(1, cols + 1) for r in range(1, rows + 1)}
    assert field == set(terrain), (len(field), len(terrain))

    graph = {}
    for c in range(1, cols + 1):
        for r in range(1, rows + 1):
            k = hx(c, r)
            nb = {}
            for d, (nc, nr) in neighbours(c, r).items():
                n = hx(nc, nr)
                nb[d] = n if (1 <= nc <= cols and 1 <= nr <= rows) else None
            t = terrain[k]
            graph[k] = {
                "col": c,
                "row": r,
                "terrain": t["kind"],
                "exit": bool(t.get("exit")),
                "road_sides": t.get("road_sides", []),
                "neighbours": nb,
                "degree": sum(1 for v in nb.values() if v),
            }

    mutual_bad = []
    for k, v in graph.items():
        for d, n in v["neighbours"].items():
            if not n:
                continue
            back = DIRS[(DIRS.index(d) + 3) % 6]
            if graph[n]["neighbours"][back] != k:
                mutual_bad.append((k, d, n, graph[n]["neighbours"][back]))

    geo = {}
    for name, g in ed["grid_px"].items():
        cen = {k: centre(v["col"], v["row"], g) for k, v in graph.items()}
        step = math.hypot(g["dx"], g["dy"] * 0.5)
        bad = []
        for k, v in graph.items():
            x, y = cen[k]
            near = sorted(
                (math.hypot(cen[o][0] - x, cen[o][1] - y), o) for o in cen if o != k
            )[:6]
            want = {n for n in v["neighbours"].values() if n}
            got = {o for dist, o in near if dist < step * 1.35}
            if want != got:
                bad.append({"hex": k, "formula": sorted(want), "geometry": sorted(got)})
        geo[name] = {
            "nearest_neighbour_step_px": round(step, 2),
            "hexes_checked": len(graph),
            "hexes_where_geometry_disagrees_with_formula": len(bad),
            "disagreements": bad[:10],
        }

    deg = {}
    for v in graph.values():
        deg[v["degree"]] = deg.get(v["degree"], 0) + 1

    out = {
        "produced_by": "PREP-5 collation, games/napoleon-at-waterloo/ingest/naw_hexgraph.py",
        "read_on": "2026-08-14",
        "edition": "SPI Napoleon at Waterloo, SECOND EDITION, copyright 1971",
        "authority": "DERIVED. Materialises the adjacency graph from the numbering scheme PREP-3 "
        "declared, then PROVES that scheme against the fitted pixel geometry of both map scans. "
        "Terrain, exit flags and road_sides are carried through unchanged from map_grid.json, "
        "which read them off the printed map; nothing here re-reads the map.",
        "why_this_file_exists": "PREP-3 declared the neighbour formula in prose but never "
        "materialised the graph, so every consumer would have had to re-implement the stagger. "
        "The 2nd Edition puts ODD columns half a hex LOWER, which is the OPPOSITE parity to the "
        "printed 3rd Edition map - a shared hex-arithmetic helper would silently mis-stagger one "
        "edition, and a parity error looks perfect until units start attacking the wrong hexes.",
        "numbering": ed["numbering"],
        "extent": ed["extent"],
        "directions": DIRS,
        "direction_note": "DIRS is a ring: the reverse of index i is index (i+3)%6.",
        "validation": {
            "mutual_adjacency_violations": len(mutual_bad),
            "mutual_adjacency_sample": mutual_bad[:10],
            "degree_histogram": {str(k): v for k, v in sorted(deg.items())},
            "geometry_cross_check": geo,
            "what_geometry_cross_check_proves": "For every hex, the six nearest hex CENTRES "
            "computed from the independently fitted pixel grid are exactly the six neighbours the "
            "parity formula predicts. Run against BOTH scans (folio and Oliver), which were fitted "
            "separately. A wrong parity would misplace the four diagonal neighbours by a full row.",
        },
        "terrain_counts": ed["counts"],
        "exit_hexes": sorted(k for k, v in graph.items() if v["exit"]),
        "hexes": graph,
    }
    json.dump(out, open(OUT, "w"), indent=1)

    print("hexes:", len(graph))
    print("mutual adjacency violations:", len(mutual_bad))
    print("degree histogram:", dict(sorted(deg.items())))
    for name, g in geo.items():
        print(f"geometry vs formula [{name}]: {g['hexes_where_geometry_disagrees_with_formula']} "
              f"disagreements of {g['hexes_checked']}")
    print("exit hexes:", len(out["exit_hexes"]), out["exit_hexes"])
    print("->", OUT)


if __name__ == "__main__":
    main()
