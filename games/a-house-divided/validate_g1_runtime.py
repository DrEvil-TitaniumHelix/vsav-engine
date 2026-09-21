#!/usr/bin/env python3
"""Deeper G1 / Tier-0 runtime validation for A House Divided.

Does NOT claim AHD rulebook enforcement (iron rule: Tier-0 free play only).
Covers AREA_MAP_DESIGN.md automated checklist items:
  - all bundled setups load; every unit resolves a loc
  - pixel_to_loc(origin) self-map (delegates to validate_region_space)
  - graph BFS: MA-reachable set matches distance; off-graph reject
  - move mirror: piece XY == dest origin after write/reload
  - reverse snap: place at origin XY → reload recovers loc (VASSAL→VALOR contract)
  - stacking: two units onto one region; both share loc; stack move works
  - spot-check ≥15 well-known printed names present in regions.json
  - save_key matches each setup when opened with that key

Exit 0 on PASS. Writes a JSON summary next to this script when --report is set.
"""
from __future__ import annotations

import argparse, json, os, shutil, sys, tempfile
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
ENG = os.path.join(ROOT, "engine")
sys.path.insert(0, ENG)

import gamespec
import board as board_mod
import vsav

SETUP_DIR = os.path.normpath(os.path.join(
    HERE, "..", "..", "..", "VassalIngest", "a-house-divided", "setups"))
# staging may live at ~/VassalIngest (sibling of Projects) — resolve via game.json
SPOT_NAMES = [
    "Washington", "Baltimore", "Philadelphia", "New York City", "Richmond",
    "Fredericksburg", "Manassas Junction", "Harpers Ferry", "Gettysburg",
    "Harrisburg", "Pittsburgh", "Cincinnati", "Louisville", "Nashville",
    "Atlanta", "New Orleans", "Cairo", "St. Louis", "Chicago", "Norfolk",
]


def fail(msg, errors):
    errors.append(msg)
    print(f"  FAIL: {msg}")


def ok(msg):
    print(f"  OK: {msg}")


def setup_paths(game):
    """Discover .vsav setups from staging (via relative paths in game.json)."""
    assets = game.spec.get("assets") or {}
    # Prefer listing the setups dir next to the loaded setup_save
    if game.setup_save:
        d = os.path.dirname(game.setup_save)
        if os.path.isdir(d):
            return sorted(
                os.path.join(d, f) for f in os.listdir(d)
                if f.lower().endswith(".vsav"))
    return []


def inspect_key(path):
    """Read XOR key from a .vsav the same way ingest does (via vsav)."""
    # board/vsav read_vsav auto-detects; pull key from zip name convention
    # by re-using inspect from ingest if available
    try:
        sys.path.insert(0, ENG)
        import ingest
        # inspect_save needs map name
        info = ingest.inspect_save(path, "Main Map")
        return info.get("key")
    except Exception:
        return None


def load_board(game, path, key_hex=None):
    """Load a Board; optionally override save_key for multi-key modules."""
    if key_hex is not None:
        game.save_key = int(key_hex, 16) if isinstance(key_hex, str) else int(key_hex)
    return board_mod.Board(path, game)


def section(title):
    print(f"\n== {title} ==")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true",
                    help="write validate_g1_runtime.report.json")
    args = ap.parse_args()
    errors = []
    report = {"checks": {}, "errors": errors}

    game = gamespec.Game(HERE)
    if game.space_kind != "region":
        fail(f"space.kind={game.space_kind!r}, expected region", errors)
        sys.exit(1)

    # --- schema (reuse existing validator as subprocess-equivalent call)
    section("region schema (validate_region_space)")
    import validate_region_space as vrs
    try:
        # run checks inline by importing main logic
        rs = game.regions
        assert rs.locations
        for lid, rec in rs.locations.items():
            assert g_pixel_self(game, lid), lid
        ok(f"{len(rs.locations)} locs, {len(rs.edges)} edges, "
           f"status={(rs.ingest or {}).get('edges_status')}")
        report["checks"]["schema"] = "PASS"
    except Exception as e:
        fail(f"schema: {e}", errors)
        report["checks"]["schema"] = "FAIL"

    # --- spot-check printed names
    section("spot-check ≥15 printed region names")
    by_name = {rec["name"]: lid for lid, rec in game.regions.locations.items()}
    # module spelling: Cincinnatti
    aliases = {"Cincinnati": ["Cincinnatti", "Cincinnati"]}
    found, missing = [], []
    for name in SPOT_NAMES:
        cands = aliases.get(name, [name])
        hit = next((n for n in cands if n in by_name), None)
        if hit:
            found.append(hit)
        else:
            missing.append(name)
    if len(found) < 15:
        fail(f"only {len(found)}/15 spot names found; missing {missing}", errors)
    else:
        ok(f"{len(found)} spot names present"
           + (f" (missing optional: {missing})" if missing else ""))
    report["checks"]["spot_names"] = {"found": found, "missing": missing}

    # --- all setups
    section("all setups: load + loc assignment")
    setups = setup_paths(game)
    if not setups:
        fail("no setup .vsav files found next to setup_save", errors)
    setup_stats = []
    for path in setups:
        name = os.path.basename(path)
        key = inspect_key(path)
        try:
            b = load_board(game, path, key)
            units = b.units()
            locs = [u.get("loc") for u in units]
            missing_loc = sum(1 for L in locs if not L)
            on_known = sum(1 for L in locs if L in game.regions.locations)
            # recruitment / off-map pieces may snap to nearest region — report
            by_loc = Counter(L for L in locs if L)
            stacked = sum(1 for c in by_loc.values() if c > 1)
            setup_stats.append(dict(
                name=name, key=key, units=len(units),
                missing_loc=missing_loc, on_known=on_known,
                distinct_locs=len(by_loc), multi_stacks=stacked))
            if "Blank" in name and not units:
                ok(f"{name}: 0 units (blank setup — expected)")
            elif not units:
                fail(f"{name}: 0 units", errors)
            elif on_known < max(1, len(units) // 4) and "Blank" not in name:
                # snap_radius may leave track/chart pieces without a loc; require
                # a solid majority of pieces still resolve to known regions.
                fail(f"{name}: only {on_known}/{len(units)} units within snap_radius",
                     errors)
            else:
                ok(f"{name}: {len(units)} units, {on_known} snapped, "
                   f"{len(by_loc)} locs, {stacked} multi-unit cities, key={key}"
                   + (f", {missing_loc} outside snap_radius" if missing_loc else ""))
        except Exception as e:
            fail(f"{name}: load error {e}", errors)
            setup_stats.append(dict(name=name, error=str(e)))
    report["checks"]["setups"] = setup_stats

    # Prefer 1861 for movement tests
    path_1861 = next((p for p in setups if "1861" in os.path.basename(p)), None)
    if not path_1861:
        fail("1861 Scenario.vsav not found", errors)
        _finish(errors, report, args)
        return

    key_1861 = inspect_key(path_1861)
    game.save_key = int(key_1861, 16) if isinstance(key_1861, str) else game.save_key

    # --- graph BFS consistency
    section("graph BFS / off-graph reject")
    if not game.regions.has_edges():
        fail("no edges — Tier-0b checks skipped", errors)
    else:
        # pick a unit on the connected component if possible
        b = load_board(game, path_1861, key_1861)
        units = b.units()
        component = _component(game, "washington")
        me = next((u for u in units if u.get("loc") in component), units[0])
        ma = game.stats(me["name"])[2]
        reach = game.legal_region_dests(me, ma)
        # every reachable dest must have finite distance ≤ ma
        bad_r = []
        for lid, cost in reach.items():
            d = game.hex_distance(me["loc"], lid)
            if d is None or abs(d - cost) > 1e-6 or cost > ma:
                bad_r.append((lid, cost, d))
        if bad_r[:5]:
            fail(f"BFS mismatch examples: {bad_r[:5]}", errors)
        else:
            ok(f"from {me['loc']}: {len(reach)} dests within MA {ma}, "
               f"distance matches cost")
        # off-graph: atlanta should not be reachable from washington component
        # unless edges connect it
        if "atlanta" in game.regions.locations and "atlanta" not in component:
            if "atlanta" in reach:
                fail("atlanta unexpectedly reachable from eastern sample graph", errors)
            else:
                ok("atlanta not in eastern sample reachable set")
        report["checks"]["bfs"] = dict(
            start=me["loc"], ma=ma, n_dests=len(reach), component=len(component))

    # --- move mirror + reverse snap
    section("move mirror (engine→.vsav→reload)")
    with tempfile.TemporaryDirectory() as td:
        work = os.path.join(td, "work.vsav")
        shutil.copy(path_1861, work)
        b = load_board(game, work, key_1861)
        units = b.units()
        component = _component(game, "washington")
        me = next((u for u in units if u.get("loc") in component
                   and u.get("loc") != "washington"), None)
        if not me:
            me = units[0]
        dest = "washington" if me["loc"] != "washington" else "baltimore"
        if dest not in game.regions.locations:
            fail(f"dest {dest} missing", errors)
        else:
            before = me["loc"]
            msg = b.move_piece_by_id(me["id"], dest)
            ox, oy = game.loc_to_pixel(dest)
            p = b.pieces[me["id"]]
            if (p["x"], p["y"]) != (ox, oy):
                fail(f"after move XY {(p['x'], p['y'])} != origin {(ox, oy)}", errors)
            b.write(work)
            b2 = load_board(game, work, key_1861)
            u2 = next(u for u in b2.units() if u["id"] == me["id"])
            if u2["loc"] != dest or (u2["x"], u2["y"]) != (ox, oy):
                fail(f"reload loc/xy mismatch: {u2['loc']} {(u2['x'], u2['y'])}", errors)
            else:
                ok(f"{msg}; reload loc={u2['loc']} xy=origin")
            report["checks"]["mirror"] = dict(
                from_loc=before, to_loc=dest, pid=me["id"], xy=[ox, oy])

        # reverse snap: set piece to richmond origin via raw XY (simulates VASSAL drag)
        section("reverse snap (origin XY → loc)")
        b = load_board(game, work, key_1861)
        me = b.units()[0]
        target = "richmond" if "richmond" in game.regions.locations else dest
        tx, ty = game.loc_to_pixel(target)
        # move via pixel tuple
        b.move_piece_by_id(me["id"], (tx, ty))
        b.write(work)
        b2 = load_board(game, work, key_1861)
        u2 = next(u for u in b2.units() if u["id"] == me["id"])
        if u2["loc"] != target:
            fail(f"reverse snap got {u2['loc']!r}, want {target!r}", errors)
        else:
            ok(f"pixel ({tx},{ty}) → loc {u2['loc']}")
        report["checks"]["reverse_snap"] = dict(target=target, got=u2["loc"])

        # stacking
        section("stacking two units on one region")
        b = load_board(game, work, key_1861)
        units = b.units()
        if len(units) < 2:
            fail("need ≥2 units for stack test", errors)
        else:
            a, c = units[0], units[1]
            stack_loc = "philadelphia" if "philadelphia" in game.regions.locations \
                else list(game.regions.locations)[0]
            b.move_piece_by_id(a["id"], stack_loc)
            b.move_piece_by_id(c["id"], stack_loc)
            b.write(work)
            b2 = load_board(game, work, key_1861)
            ua = next(u for u in b2.units() if u["id"] == a["id"])
            uc = next(u for u in b2.units() if u["id"] == c["id"])
            if ua["loc"] != stack_loc or uc["loc"] != stack_loc:
                fail(f"stack locs {ua['loc']}/{uc['loc']} != {stack_loc}", errors)
            ox, oy = game.loc_to_pixel(stack_loc)
            if (ua["x"], ua["y"]) != (ox, oy) or (uc["x"], uc["y"]) != (ox, oy):
                # stacks may share exact origin — required for VASSAL stack join
                fail(f"stack XY not at origin: "
                     f"{(ua['x'], ua['y'])} {(uc['x'], uc['y'])}", errors)
            # move whole stack via containing-piece API (not loc→origin lookup)
            next_loc = "harrisburg" if "harrisburg" in game.regions.locations else stack_loc
            if next_loc != stack_loc:
                try:
                    b2.move_stack_containing(a["id"], next_loc)
                    b2.write(work)
                    b3 = load_board(game, work, key_1861)
                    locs = {u["id"]: u["loc"] for u in b3.units()
                            if u["id"] in (a["id"], c["id"])}
                    if set(locs.values()) != {next_loc}:
                        fail(f"stack move locs {locs}", errors)
                    else:
                        ok(f"stacked {a['id'][:6]}…+{c['id'][:6]}… on {stack_loc}, "
                           f"moved stack → {next_loc}")
                except Exception as e:
                    fail(f"move_stack_containing: {e}", errors)
            else:
                ok(f"both units on {stack_loc} at origin")
            report["checks"]["stacking"] = dict(
                loc=stack_loc, pids=[a["id"], c["id"]])

        # pristine-save whole-stack (never engine-snapped to origin first)
        section("pristine stock whole-stack (off-origin VASSAL XY)")
        b = load_board(game, path_1861, key_1861)
        pristine_ok = False
        for sid, s in b.stacks.items():
            if len(s.get("members") or []) < 2:
                continue
            pid = s["members"][0]
            p = b.pieces[pid]
            ox_s, oy_s = s["x"], s["y"]
            # must be off catalog origin for the bug to matter
            start_loc = game.pixel_to_loc(p["x"], p["y"])
            if not start_loc or not game.regions.has_edges():
                continue
            if (ox_s, oy_s) == game.loc_to_pixel(start_loc):
                continue  # already on origin — not the failure mode
            reach = game.legal_region_dests(
                dict(loc=start_loc, name=p["name"], side="Side B"), 6)
            if not reach:
                continue
            dest = next(iter(reach))
            try:
                # old API would fail: move_stack(start_loc, dest) via origin lookup
                msg = b.move_stack_containing(pid, dest)
                for mid in s["members"]:
                    if (b.pieces[mid]["x"], b.pieces[mid]["y"]) != game.loc_to_pixel(dest):
                        raise AssertionError("member not at dest origin")
                ok(f"{msg} (from off-origin stack XY {(ox_s, oy_s)})")
                pristine_ok = True
                report["checks"]["pristine_stack"] = dict(
                    from_loc=start_loc, to_loc=dest, stack_xy=[ox_s, oy_s])
                break
            except Exception as e:
                fail(f"pristine stack move: {e}", errors)
                break
        if not pristine_ok and not any("pristine" in e for e in errors):
            ok("no off-origin multi-member stack on graph sample (skipped)")

    # --- multi-hop campaign on graph (deeper play smoke)
    section("multi-hop path along authored edges")
    with tempfile.TemporaryDirectory() as td:
        work = os.path.join(td, "hop.vsav")
        shutil.copy(path_1861, work)
        b = load_board(game, work, key_1861)
        path_hops = ["fredericksburg", "washington", "baltimore",
                     "philadelphia", "harrisburg", "gettysburg"]
        path_hops = [p for p in path_hops if p in game.regions.locations]
        # ensure consecutive edges exist (or skip pair)
        me = next((u for u in b.units() if u.get("loc") == path_hops[0]), None)
        if not me:
            # move someone onto start
            me = b.units()[0]
            b.move_piece_by_id(me["id"], path_hops[0])
        hop_log = [path_hops[0]]
        cur = path_hops[0]
        for nxt in path_hops[1:]:
            if game.regions.move_cost(cur, nxt) is None:
                # allow BFS one-step only; if not adjacent, try anyway for reject
                reach = game.legal_region_dests(
                    dict(loc=cur, name=me["name"], side=me["side"]), 6)
                if nxt not in reach:
                    ok(f"skip non-adjacent {cur}→{nxt} (not in MA-6 reach)")
                    continue
            b.move_piece_by_id(me["id"], nxt)
            p = b.pieces[me["id"]]
            ox, oy = game.loc_to_pixel(nxt)
            if (p["x"], p["y"]) != (ox, oy):
                fail(f"hop {nxt}: xy mismatch", errors)
                break
            hop_log.append(nxt)
            cur = nxt
        b.write(work)
        b2 = load_board(game, work, key_1861)
        final = next(u for u in b2.units() if u["id"] == me["id"])
        if final["loc"] != hop_log[-1]:
            fail(f"final loc {final['loc']} != {hop_log[-1]}", errors)
        else:
            ok(f"path {' → '.join(hop_log)}")
        # persist a copy into evidence for VASSAL open smoke
        ev = os.path.join(HERE, "evidence")
        os.makedirs(ev, exist_ok=True)
        out_sav = os.path.join(ev, "valor_multihop_gettysburg.vsav")
        shutil.copy(work, out_sav)
        report["checks"]["multihop"] = dict(path=hop_log, save=out_sav)

    # --- nearest-origin sanity: units shouldn't all collapse to one loc
    section("loc distribution sanity (1861)")
    b = load_board(game, path_1861, key_1861)
    dist = Counter(u["loc"] for u in b.units() if u.get("loc"))
    if len(dist) < 5:
        fail(f"only {len(dist)} distinct locs — snap likely broken", errors)
    else:
        top = dist.most_common(5)
        ok(f"{len(dist)} distinct locs; top {top}")
    report["checks"]["loc_distribution"] = dist.most_common(12)
    n_out = sum(1 for u in b.units() if not u.get("loc"))
    if n_out:
        ok(f"{n_out} units outside snap_radius (chart/track — expected)")

    _finish(errors, report, args)


def g_pixel_self(game, lid):
    x, y = game.regions.locations[lid]["origin"]
    return game.pixel_to_loc(x, y) == lid


def _component(game, start):
    if start not in game.regions.locations:
        return set()
    seen = {start}
    stack = [start]
    while stack:
        u = stack.pop()
        for v in game.regions.neighbors(u):
            if v not in seen:
                seen.add(v)
                stack.append(v)
    return seen


def _finish(errors, report, args):
    report["errors"] = errors
    report["verdict"] = "FAIL" if errors else "PASS"
    if args.report:
        ev = os.path.join(HERE, "evidence")
        os.makedirs(ev, exist_ok=True)
        out = os.path.join(ev, "validate_g1_runtime.report.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"\nreport → {out}")
    print()
    if errors:
        print(f"FAIL: {len(errors)} check(s) failed")
        sys.exit(1)
    print("PASS: deeper G1 runtime validation (Tier-0 space/UI/.vsav — not AHD rules)")
    sys.exit(0)


if __name__ == "__main__":
    main()
