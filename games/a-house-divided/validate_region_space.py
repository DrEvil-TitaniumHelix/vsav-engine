#!/usr/bin/env python3
"""Validate region-space data for A House Divided (AREA_MAP_DESIGN.md §C).

Checks:
  - every location has unique id + finite origin
  - every edge endpoint exists
  - undirected graphs are symmetric (absent directed:true)
  - pixel_to_loc(origin) returns self for every location
  - distance symmetry on undirected graphs
"""
import json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "engine"))
import gamespec


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def main():
    g = gamespec.Game(HERE)
    if g.space_kind != "region":
        fail(f"expected space.kind=region, got {g.space_kind!r}")
    rs = g.regions
    locs = rs.locations
    if not locs:
        fail("no locations")
    for lid, rec in locs.items():
        o = rec.get("origin")
        if not (isinstance(o, (list, tuple)) and len(o) == 2):
            fail(f"{lid}: missing origin")
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in o):
            fail(f"{lid}: non-finite origin {o}")
    for e in rs.edges:
        for end in ("a", "b"):
            if e[end] not in locs:
                fail(f"edge endpoint missing: {e[end]!r} in {e}")
        if not e.get("directed"):
            # undirected: both directions present in adjacency
            if e["b"] not in dict(rs._adj.get(e["a"], [])):
                fail(f"undirected edge {e['a']}—{e['b']} missing a→b in adj")
            if e["a"] not in dict(rs._adj.get(e["b"], [])):
                fail(f"undirected edge {e['a']}—{e['b']} missing b→a in adj")
    for lid, rec in locs.items():
        x, y = rec["origin"]
        got = g.pixel_to_loc(x, y)
        if got != lid:
            fail(f"pixel_to_loc({x},{y}) = {got!r}, expected {lid!r}")
    # distance symmetry (sample / all if small)
    undirected = [e for e in rs.edges if not e.get("directed")]
    if undirected:
        ids = sorted(locs)
        checked = 0
        for i, a in enumerate(ids):
            for b in ids[i:]:
                da, db = g.hex_distance(a, b), g.hex_distance(b, a)
                if da != db:
                    fail(f"distance asymmetry {a}↔{b}: {da} vs {db}")
                checked += 1
                if checked > 5000:
                    break
            if checked > 5000:
                break
    print(f"PASS: {len(locs)} locations, {len(rs.edges)} edges, "
          f"status={(rs.ingest or {}).get('edges_status')}")


if __name__ == "__main__":
    main()
