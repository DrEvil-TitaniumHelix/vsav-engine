#!/usr/bin/env python3
"""Minimal RegionSpace unit checks (no VASSAL assets required)."""
import os, sys, tempfile, json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import gamespec


def test_slug_collision_via_ingest():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    import ingest
    used = {}
    a, c1 = ingest.region_location_id("Macon", used)
    b, c2 = ingest.region_location_id("Macon", used)
    assert a == "macon" and not c1
    assert b == "macon-2" and c2


def test_pixel_tiebreak_and_bfs():
    data = {
        "locations": {
            "a": {"name": "A", "origin": [0, 0]},
            "b": {"name": "B", "origin": [10, 0]},
            "c": {"name": "C", "origin": [20, 0]},
            "d": {"name": "D", "origin": [10, 0]},  # same as b — lower id wins
        },
        "edges": [
            {"a": "a", "b": "b", "cost": 1},
            {"a": "b", "b": "c", "cost": 1},
        ],
        "ingest": {"edges_status": "PARTIAL"},
    }
    rs = gamespec.RegionSpace(data)
    assert rs.pixel_to_loc(10, 0) == "b"  # tie vs d: lower id
    assert rs.distance("a", "c") == 2
    assert rs.distance("c", "a") == 2
    reach = rs.reachable("a", 1)
    assert set(reach) == {"a", "b"}


def test_map_edge_loaded_from_spec():
    """game.json map_edge becomes Game.edge_w/h (board↔map conversion)."""
    with tempfile.TemporaryDirectory() as td:
        regions = {
            "locations": {"a": {"name": "A", "origin": [100, 200]}},
            "edges": [],
            "ingest": {"edges_status": "UNAUTHORED"},
        }
        open(os.path.join(td, "regions.json"), "w").write(json.dumps(regions))
        spec = {
            "name": "edge-test",
            "map_name": "Main Map",
            "save_key": "a3",
            "map_edge": {"width": 75, "height": 75},
            "space": {"kind": "region", "file": "regions.json"},
            "sides": {"order": ["A", "B"], "default": "A", "detect_tokens": {}},
            "unit_kinds": ["mark"],
            "stats": {"default": [0, 0, 1]},
            "movement": {"default_mp": 1.0},
        }
        open(os.path.join(td, "game.json"), "w").write(json.dumps(spec))
        g = gamespec.Game(td)
        assert g.edge_w == 75 and g.edge_h == 75
        assert g.loc_to_pixel("a") == (100, 200)


if __name__ == "__main__":
    test_slug_collision_via_ingest()
    test_pixel_tiebreak_and_bfs()
    test_map_edge_loaded_from_spec()
    print("PASS region_space unit checks")
