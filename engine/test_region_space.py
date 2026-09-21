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


if __name__ == "__main__":
    test_slug_collision_via_ingest()
    test_pixel_tiebreak_and_bfs()
    print("PASS region_space unit checks")
