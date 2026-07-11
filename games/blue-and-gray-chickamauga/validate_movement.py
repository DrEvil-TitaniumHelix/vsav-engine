"""Movement validation: TEC costs, hexside effects and ZOC semantics from the
1975 rules ([5.x], [6.x], [9.0]) exercised against the real terrain data
through the spec-driven engine (gamespec.Game.move_cost / legal_destinations_t).

Anchor hexes verified by eye against the module map + 1975 scan during the
terrain build (see build_terrain.py validation block)."""
import json, os, sys

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..")))
from engine import gamespec

HERE = os.path.dirname(os.path.abspath(__file__))
G = gamespec.load(HERE)

fails = []
def check(cond, what):
    if not cond:
        fails.append(what)
    print(("PASS " if cond else "FAIL ") + what)

def T(c, r):
    return G.hex_terrain(c, r)

# ------------------------------------------------------- terrain sanity
check(T(22, 21) == "clear", "2221 clear")
check(T(22, 24) == "forest", "2224 forest")
check(T(13, 27) == "rough", "1327 rough")
check(T(24, 20) == "forest", "2420 forest (ford destination)")

# ------------------------------------------------------- move costs [9.0 TEC]
mc = G.move_cost
check(mc((1, 10), (1, 11)) == 1.0, "clear hex = 1 MP [5.21] (0110->0111)")
check(mc((22, 23), (22, 24)) == 3.0, "forest hex = 3 MP [9.0] (2223->2224)")
# rough 3 MP: enter 1327 from a non-trail neighbor
rough_ok = any(mc(nb, (13, 27)) == 3.0 for nb in G.neighbors(13, 27)
               if not G.side_features(nb, (13, 27)))
check(rough_ok, "rough hex = 3 MP [9.0] (1327)")
# forest_rough 6 MP: find one adjacent to a featureless side
fr_checked = False
for key, v in G.terrain["hexes"].items():
    if v["t"] != "forest_rough" or fr_checked:
        continue
    c, r = int(key[:2]), int(key[2:])
    for nb in G.neighbors(c, r):
        if G.on_map(*nb) and not G.side_features(nb, (c, r)):
            check(mc(nb, (c, r)) == 6.0, f"forest+rough hex = 6 MP [9.0] ({key})")
            fr_checked = True
            break
check(fr_checked, "found a forest_rough cost test case")

# road override: road hexside into a non-clear hex still costs 1 [5.22]
road_case = None
for skey, f in G.terrain["sides"].items():
    if f.get("road") and not f.get("creek"):
        a, b = skey.split("|")
        pa = (int(a[:2]), int(a[2:])); pb = (int(b[:2]), int(b[2:]))
        for src, dst in ((pa, pb), (pb, pa)):
            if T(*dst) in ("forest", "forest_rough", "rough"):
                road_case = (src, dst, T(*dst))
                break
    if road_case:
        break
check(road_case is not None, "found a road-into-rough/forest case")
if road_case:
    src, dst, tt = road_case
    check(mc(src, dst) == 1.0, f"road hexside into {tt} = 1 MP [5.22] ({src}->{dst})")

# trail cap: 2123->2223 clear via trail = 1; trail into forest = 2 [5.23]
check(mc((21, 23), (22, 23)) == 1.0, "trail into clear = 1 MP [5.23/TEC] (2123->2223)")
trail_case = None
for skey, f in G.terrain["sides"].items():
    if f.get("trail") and not f.get("creek"):
        a, b = skey.split("|")
        pa = (int(a[:2]), int(a[2:])); pb = (int(b[:2]), int(b[2:]))
        for src, dst in ((pa, pb), (pb, pa)):
            if T(*dst) in ("forest", "forest_rough"):
                trail_case = (src, dst, T(*dst))
                break
    if trail_case:
        break
check(trail_case is not None, "found a trail-into-forest case")
if trail_case:
    src, dst, tt = trail_case
    check(mc(src, dst) == 2.0, f"trail hexside into {tt} = 2 MP [5.23] ({src}->{dst})")

# creek prohibition / bridge / ford [5.25]
check(mc((21, 22), (22, 21)) is None, "plain creek hexside prohibited [5.25] (2122->2221)")
check(mc((19, 22), (20, 22)) == 1.0, "bridge carries the road at 1 MP [5.22/5.25] (Alexander's 1922->2022)")
check(mc((23, 20), (24, 20)) == 3.0, "ford: trail-capped 2 + 1 ford surcharge [5.23/5.25] (2320->2420 forest)")
f2026 = mc((19, 26), (20, 26))
check(f2026 == (min({"clear": 1.0, "forest": 3.0, "rough": 3.0, "forest_rough": 6.0}[T(20, 26)], 2.0) + 1.0),
      f"ford 1926->2026 = trail cap + 1 (got {f2026}, terrain {T(20,26)})")

# ------------------------------------------------------- ZOC semantics
def U(pid, side, c, r, name="1/1/XIV c"):
    return dict(id=pid, name=name, side=side, col=c, row=r)

# enemy at 2223 (clear, no creek on its sides toward 2123/2222/2224)
me = U("m", "Union", 20, 23)             # 2023 clear, two hexes west
enemy = [U("e", "Confederate", 22, 23)]  # 2223
dd = G.legal_destinations_t(me, 6, enemy)
ez = G.zoc_hexes(enemy, "Confederate")
check((21, 23) in ez, "2123 is in 2223's ZOC (trail side, no creek) [6.0/6.6]")
check((21, 23) in dd, "may enter the EZOC hex 2123 [6.0]")
check((22, 23) not in dd, "enemy hex itself never enterable [5.12]")
# stop on enter: no destination may be purchased THROUGH a ZOC hex —
# structural check: no dest costs more than an adjacent in-ZOC dest it could
# only be reached through
ok_stop = all(not any(h2 in dd and dd[h2] > dd[h] for h2 in G.neighbors(*h)
                      if h2 in ez and h2 not in dd)
              for h in dd if h in ez)
check(ok_stop, "movement ceases on EZOC entry [6.0]")

# locked at start: unit adjacent to the enemy (in its ZOC) may not move [5.13/6.3]
me2 = U("m", "Union", 21, 23)
dd2 = G.legal_destinations_t(me2, 6, enemy)
check(dd2 == {}, "unit starting in an EZOC may not move [5.13/6.3]")

# ZOC does NOT cross a plain creek hexside [6.6]: enemy 2221 is creek-wrapped
# toward 2222 (side 2221|2222 carries creek) - a unit at 2222 is NOT locked
enemy_creek = [U("e2", "Confederate", 22, 21)]
me3 = U("m", "Union", 22, 22)
dd3 = G.legal_destinations_t(me3, 6, enemy_creek)
check(len(dd3) > 0, "no ZOC across a non-bridge/ford creek hexside [6.6] (2222 free beside 2221)")

# ZOC DOES cross a bridge hexside: enemy at 2022 (Alexander's), unit at 1922 locked
enemy2 = [U("e", "Confederate", 20, 22)]
me4 = U("m", "Union", 19, 22)
dd4 = G.legal_destinations_t(me4, 6, enemy2)
check(dd4 == {}, "ZOC crosses a bridge hexside [6.6] (1922 locked beside 2022)")

# ------------------------------------------------------- stacking [5.32]
# no enemies on the board for these: pure stacking semantics
friends1 = [U("f1", "Union", 21, 23)]                      # one friend on 2123
dd5 = G.legal_destinations_t(me, 6, friends1)
check((21, 23) in dd5, "may end stacked with ONE friendly unit [5.32]")
friends2 = friends1 + [U("f2", "Union", 21, 23, name="2/1/XIV c")]
dd6 = G.legal_destinations_t(me, 6, friends2)
check((21, 23) not in dd6, "may NOT end in a hex with two friendly units [5.32]")
# pass-through of the full stack is free [5.31/5.33]: 2223 beyond it, along
# the trail 2023->2123->2223 = 2 MP
check(dd6.get((22, 23)) == 2.0,
      f"free pass-through of a full friendly stack [5.31/5.33] (2223 at 2 MP, got {dd6.get((22,23))})")

# ------------------------------------------------------- budget: 6 MP [5.0]
me6 = U("m", "Union", 1, 10)
dd7 = G.legal_destinations_t(me6, 6, [])
far = max(G.hex_distance((1, 10), h) for h in dd7)
check(far >= 6, f"MA 6 reaches 6 hexes on roads/clear (max distance {far})")

print()
if fails:
    print(f"{len(fails)} FAILURES")
    sys.exit(1)
print(f"ALL PASS")
