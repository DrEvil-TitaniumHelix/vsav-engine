import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "engine"))
import gamespec  # noqa: E402
from naw import NawGame  # noqa: E402

G = gamespec.Game(HERE)
SCEN = os.path.join(HERE, "scenario_2nd_ed.json")
CRT = json.load(open(os.path.join(HERE, "ingest", "crt_2nd_ed.json"), encoding="utf-8"))
EXS = json.load(open(os.path.join(HERE, "ingest", "worked_examples.json"), encoding="utf-8"))["examples"]
CAT = json.load(open(SCEN, encoding="utf-8"))
ok = True


def check(cond, msg):
    global ok
    print(("PASS  " if cond else "FAIL  ") + msg)
    ok = ok and bool(cond)


def fresh(seed=42):
    g = NawGame(G, SCEN, tempfile.mkdtemp(), seed=seed)
    g.s["units"] = {}
    g.s["phase"] = "combat"
    return g


def hx(s):
    return int(s[:2]), int(s[2:])


def hn(h):
    return f"{h[0]:02d}{h[1]:02d}"


def units_by(side, cls, cs):
    return [u["id"] for u in CAT["units"] + CAT["reserve"] if u["side"] == side and u["cls"] == cls and u["stats"]["att"] == cs]


POOL = {}


def take(side, cls, cs):
    key = (side, cls, cs)
    used = POOL.setdefault(key, 0)
    cands = units_by(side, cls, cs)
    if used >= len(cands):
        other = "Al" if side == "Fr" else "Fr"
        cands = cands + units_by(other, cls, cs)
    if used >= len(cands):
        return None
    POOL[key] = used + 1
    return cands[used]


def place(g, pid, h, side=None):
    e = g.catalog[pid]
    g.s["units"][pid] = {"pid": pid, "slot": e["slot"], "name": e["name"], "side": side or e["side"], "col": h[0], "row": h[1]}


def terr(h):
    return G.hex_terrain(*h)


def clear_region_center():
    for h, v in sorted(G.terrain["hexes"].items()):
        c = hx(h)
        ring1 = G.neighbors(*c)
        ring2 = {n for r in ring1 for n in G.neighbors(*r)} - set(ring1) - {c}
        if v["t"] == "clear" and all(G.on_map(*n) and terr(n) == "clear" for n in ring1) \
           and all(G.on_map(*n) and terr(n) == "clear" for n in ring2):
            return c
    raise RuntimeError("no clear region")


CENTER = clear_region_center()
RING = G.neighbors(*CENTER)


def norm_odds(t):
    W = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
    t = str(t).lower()
    m = re.search(r"(\d+)\s*to\s*(\d+)", t)
    if m:
        return f"{m.group(1)}:{m.group(2)}"
    m = re.search(r"(one|two|three|four|five|six)\s*to\s*(one|two|three|four|five|six)", t)
    return f"{W[m.group(1)]}:{W[m.group(2)]}"


def is_town(v):
    return "town" in str(v or "").lower()


print("== CRT table, clamp, rounding ==")
g = fresh()
cols = CRT["odds_columns"]
cells = sum(1 for d in "123456" for c in cols if g.crt_result(c, int(d)) == CRT["table"][d][c])
check(cells == 60, f"crt_result reproduces all 60 printed cells ({cells})")
check(g.crt_result("1:5", 1) == "AE" and g.crt_result("6:1", 6) == "DE" and g.crt_result("1:1", 3) == "Dr", "spot cells 1:5/1 AE, 6:1/6 DE, 1:1/3 Dr")
pairs = {(8, 3): "2:1", (9, 4): "2:1", (6, 4): "1:1", (13, 4): "3:1", (2, 3): "1:2", (13, 6): "2:1", (4, 3): "1:1", (3, 2): "1:1",
         (1, 4): "1:4", (1, 1): "1:1", (7, 1): "6:1", (13, 2): "6:1", (30, 1): "6:1", (1, 5): "1:5", (1, 6): "1:5", (1, 40): "1:5",
         (5, 6): "1:2", (5, 11): "1:3", (12, 5): "2:1", (2, 5): "1:3", (3, 12): "1:4"}
bad = {k: g.odds_column(*k) for k, v in pairs.items() if g.odds_column(*k) != v}
check(not bad, f"odds arithmetic: floor(a/d):1 when a>=d else 1:ceil(d/a), clamped 1:5..6:1 [CBT-02, clamp footnote] ({bad})")
check(g.odds_column(8, 3) == "2:1", "the rules' own printed example: 8 vs 3 = 2 to 1 [CBT-EX-01]")

print("== the 27 printed Examples of Attacks through battle_check ==")
town = next(hx(h) for h, v in sorted(G.terrain["hexes"].items()) if v["t"] == "town"
            and sum(1 for n in G.neighbors(*hx(h)) if G.on_map(*n) and terr(n) == "clear") >= 5)
n_ok = 0
for e in EXS:
    POOL.clear()
    g = fresh()
    printed = norm_odds(e["printed_label_verbatim"])
    atk_units, def_units = e["attackers"], e["defenders"]
    def_town = any(is_town(u.get("in_terrain")) for u in def_units)
    atk_town = any(is_town(u.get("in_terrain")) for u in atk_units)
    if def_town or atk_town:
        c = town
        ring = [n for n in G.neighbors(*c) if G.on_map(*n) and terr(n) == "clear"]
        if atk_town:
            c, ring = ring[0], [town]
    else:
        c, ring = CENTER, list(RING)
    dpos = [c]
    if len(def_units) == 2:
        dpos = [c, ring[0]]
        ring = [n for n in G.neighbors(*c) if n in G.neighbors(*ring[0])]
    dids = []
    for u, h in zip(def_units, dpos):
        pid = take("Al", u["type"], u["combat_strength"])
        place(g, pid, h, "Al")
        dids.append(pid)
    aids = []
    ri = 0
    for u in atk_units:
        pid = take("Fr", u["type"], u["combat_strength"])
        rng2 = e.get("geometry", "")
        bombard = u["type"] == "artillery" and ("arrow" in rng2 and "no arrow" not in rng2 or "two hexes" in rng2)
        if bombard:
            far = next(h for h in G.neighbors(*G.neighbors(*dpos[0])[3]) if G.hex_distance(h, dpos[0]) == 2 and G.on_map(*h)
                       and terr(h) != "woods" and all(terr(b) != "woods" for b in set(G.neighbors(*h)) & set(G.neighbors(*dpos[0]))))
            place(g, pid, far, "Fr")
        else:
            place(g, pid, ring[ri], "Fr")
            ri += 1
        aids.append(pid)
    legal, reasons, meta = g.battle_check("Fr", aids, dids)
    got = meta["column"] if meta else None
    good = legal and got == printed
    n_ok += good
    if not good:
        print("   ", e["id"], e["printed_label_verbatim"].replace("\n", " "), "->", got, reasons)
check(n_ok == 27, f"27/27 printed examples reproduce their printed odds through the gate's battle_check ({n_ok}) [C.16]")

print("== terrain doubling (NAW2-D4) ==")
g = fresh()
d1 = take("Al", "infantry", 6)
place(g, d1, town)
check(g.defense_strength([d1]) == 12, "defender in a Town hex doubles: 6 -> 12 [CBT-18/TEC row 2; EX-04]")
g = fresh()
place(g, d1, hx("1014"))
check(g.defense_strength([d1]) == 12, "defender in Woods/Road hex 1014 doubles: 6 -> 12 [TEC row 2, ruling NAW2-D4]")
g = fresh()
place(g, d1, CENTER)
check(g.defense_strength([d1]) == 6, "defender in clear terrain: 6 [TEC row 1]")
g = fresh()
POOL.clear()
a1 = take("Fr", "infantry", 6)
place(g, a1, town)
dclear = next(n for n in G.neighbors(*town) if G.on_map(*n) and terr(n) == "clear")
place(g, d1, dclear)
legal, reasons, meta = g.battle_check("Fr", [a1], [d1])
check(legal and meta["attack"] == 6 and meta["column"] == "1:1", "attacker in a Town hex is NOT doubled: 6 vs 6 = 1:1 [EX-03; TEC 'normal value when units attack from such terrain']")

print("== attack legality (per attack; the phase-level assignment is bite 4) ==")
POOL.clear()
g = fresh()
d = take("Al", "infantry", 4)
place(g, d, CENTER)
a = take("Fr", "infantry", 4)
b = take("Fr", "infantry", 5)
place(g, a, RING[0])
far2 = next(h for h in {n for r in RING for n in G.neighbors(*r)} if G.hex_distance(h, CENTER) == 2)
place(g, b, far2)
legal, reasons, _ = g.battle_check("Fr", [a], [d])
check(legal, "adjacent attacker legal [CBT-05]")
legal, reasons, _ = g.battle_check("Fr", [a, b], [d])
check(not legal and "CBT-05" in reasons[0], "non-adjacent infantry cannot join the attack [CBT-05/CBT-11]")
legal, reasons, _ = g.battle_check("Fr", [b], [d])
check(not legal, "infantry two hexes away cannot attack at all [CBT-05]")
g.s["phase"] = "movement"
legal, reasons, _ = g.battle_check("Fr", [a], [d])
check(not legal and "SEQ-06" in reasons[0], "no attack in the Movement Phase [SEQ-06/MOV-04]")
g.s["phase"] = "combat"
legal, reasons, _ = g.battle_check("Fr", [a, a], [d])
check(not legal and "CBT-17" in reasons[0], "a unit named twice is refused [CBT-17]")
legal, reasons, _ = g.battle_check("Al", [d], [a])
check(legal, "the other side's attack is checked symmetrically (side-agnostic predicate)")
g.s["fought"].append(a)
legal, reasons, _ = g.battle_check("Fr", [a], [d])
check(not legal and "CBT-10" in reasons[0], "an attacker that already attacked this phase is refused [CBT-10]")
g.s["fought"] = []
g.s["defended"].append(d)
legal, reasons, _ = g.battle_check("Fr", [a], [d])
check(not legal and "CBT-10" in reasons[0], "a defender already attacked this phase is refused [CBT-10]")
g.s["defended"] = []
POOL.clear()
g = fresh()
d = take("Al", "artillery", 4)
place(g, d, CENTER)
a = take("Fr", "cavalry", 1)
place(g, a, RING[0])
legal, reasons, meta = g.battle_check("Fr", [a], [d])
check(legal and meta["column"] == "1:4", "a 1:4 'diversionary' attack is legal - the gate never requires better odds [CBT-13; EX-16]")
POOL.clear()
g = fresh()
d = take("Al", "infantry", 4)
place(g, d, CENTER)
a = take("Fr", "cavalry", 1)
place(g, a, RING[0])
legal, reasons, meta = g.battle_check("Fr", [a], [d])
check(legal and meta["column"] == "1:4" and g.odds_column(1, 8) == "1:5", "1 vs 4 = 1:4; 1 vs 8 (a doubled 4 in a Town) clamps to 1:5 [clamp footnote]")

print("== artillery ==")
POOL.clear()
g = fresh()
d = take("Al", "cavalry", 1)
place(g, d, CENTER)
art = take("Fr", "artillery", 3)
straight = [h for h in {n for r in RING for n in G.neighbors(*r)} if G.hex_distance(h, CENTER) == 2 and len(set(G.neighbors(*h)) & set(G.neighbors(*CENTER))) == 1]
bent = [h for h in {n for r in RING for n in G.neighbors(*r)} if G.hex_distance(h, CENTER) == 2 and len(set(G.neighbors(*h)) & set(G.neighbors(*CENTER))) == 2]
check(len(straight) == 6 and len(bent) == 6, f"geometry: 12 hexes at distance 2 - 6 straight (one intervening hex), 6 bent (two candidate intervening hexes) ({len(straight)}/{len(bent)})")
place(g, art, straight[0])
legal, reasons, meta = g.battle_check("Fr", [art], [d])
check(legal and meta["column"] == "3:1" and meta["bombarding"] == [art], "artillery bombards a unit exactly two hexes away: 3 vs 1 = 3:1 [ART-01; EX-02/EX-17]")
inf = take("Fr", "cavalry", 1)
place(g, inf, RING[0])
legal, reasons, meta = g.battle_check("Fr", [inf, art], [d])
check(legal and meta["column"] == "4:1" and meta["melee"] == [inf] and meta["bombarding"] == [art], "adjacent cavalry 1 + bombarding artillery 3 combine: 4:1 [ART-08; EX-09/EX-24]")
blocker = take("Al", "infantry", 6)
mid = list(set(G.neighbors(*straight[0])) & set(G.neighbors(*CENTER)))[0]
place(g, blocker, mid)
legal, reasons, meta = g.battle_check("Fr", [art], [d])
check(legal, "bombardment fires OVER an intervening enemy unit [ART-16]")
del g.s["units"][blocker]
far3 = next(h for h in {n for r in G.neighbors(*straight[0]) for n in G.neighbors(*r)} if G.hex_distance(h, CENTER) == 3 and G.on_map(*h) and terr(h) != "woods")
g.s["units"][art]["col"], g.s["units"][art]["row"] = far3
legal, reasons, _ = g.battle_check("Fr", [art], [d])
check(not legal and "ART-01" in reasons[0], "artillery three hexes away may not attack [ART-01: exactly two hexes]")
g.s["units"][art]["col"], g.s["units"][art]["row"] = straight[0]
d2 = take("Al", "cavalry", 1)
far_ring = next(h for h in RING if h not in G.neighbors(*straight[0]) and h != RING[0])
place(g, d2, far_ring, "Al")
legal, reasons, _ = g.battle_check("Fr", [art], [d, d2])
check(not legal and "ART-13" in reasons[0], f"a bombarding gun may attack only a single unit [ART-13] ({reasons[0][:60]})")
place(g, art, RING[2])
g.s["units"].pop(d2)
d3 = take("Al", "cavalry", 1)
common = [h for h in G.neighbors(*RING[2]) if h in G.neighbors(*CENTER)]
place(g, d3, common[0], "Al")
legal, reasons, meta = g.battle_check("Fr", [art], [d, d3])
check(legal and meta["melee"] == [art] and meta["column"] == "1:1", f"an ADJACENT artillery unit may attack every unit it is adjacent to: 3 vs 1+1 [ART-14] ({reasons[0][:80]})")
woods_pairs = []
for h, v in G.terrain["hexes"].items():
    if v["t"] != "clear":
        continue
    c = hx(h)
    for w in G.neighbors(*c):
        if G.on_map(*w) and terr(w) == "woods":
            for t in G.neighbors(*w):
                if G.on_map(*t) and terr(t) == "clear" and G.hex_distance(c, t) == 2 and all(terr(b) == "woods" for b in set(G.neighbors(*c)) & set(G.neighbors(*t))):
                    woods_pairs.append((c, t))
                    break
    if woods_pairs:
        break
c, t = woods_pairs[0]
POOL.clear()
g = fresh()
d = take("Al", "cavalry", 1)
place(g, d, t)
art = take("Fr", "artillery", 3)
place(g, art, c)
legal, reasons, _ = g.battle_check("Fr", [art], [d])
check(not legal and "ART-17" in reasons[0], f"bombardment across a Woods hex refused ({hn(c)} -> {hn(t)}) [ART-17/TEC row 3]")
town_pairs = []
for h, v in G.terrain["hexes"].items():
    if v["t"] != "town":
        continue
    w = hx(h)
    for c in G.neighbors(*w):
        for t in G.neighbors(*w):
            if G.on_map(*c) and G.on_map(*t) and terr(c) != "woods" and terr(t) != "woods" and G.hex_distance(c, t) == 2 and all(terr(b) != "woods" for b in set(G.neighbors(*c)) & set(G.neighbors(*t))):
                town_pairs.append((c, t))
                break
        if town_pairs:
            break
    if town_pairs:
        break
bent = []
for h, v in G.terrain["hexes"].items():
    if v["t"] != "clear":
        continue
    c = hx(h)
    for t in {n for r in G.neighbors(*c) for n in G.neighbors(*r)}:
        if G.on_map(*t) and terr(t) == "clear" and G.hex_distance(c, t) == 2:
            mids = list(set(G.neighbors(*c)) & set(G.neighbors(*t)))
            if len(mids) == 2 and sum(1 for b in mids if terr(b) in ("woods", "woods_road")) == 1:
                bent.append((c, t))
                break
    if bent:
        break
c, t = bent[0]
POOL.clear()
g = fresh()
d = take("Al", "cavalry", 1)
place(g, d, t, "Al")
art = take("Fr", "artillery", 3)
place(g, art, c, "Fr")
legal, reasons, _ = g.battle_check("Fr", [art], [d])
check(legal, f"bent two-hex shot with ONE woods candidate and one clear candidate is OPEN ({hn(c)} -> {hn(t)}) [SPI 1979 Terrain Key example: 0803 fires into 0705 past woods 0804]")
wr_t = next(hx(h) for h, v in G.terrain["hexes"].items() if v["t"] == "woods_road")
src = next(h for h in {n for r in G.neighbors(*wr_t) for n in G.neighbors(*r)} if G.on_map(*h) and terr(h) == "clear" and G.hex_distance(h, wr_t) == 2
           and any(terr(b) not in ("woods", "woods_road") for b in set(G.neighbors(*h)) & set(G.neighbors(*wr_t))))
POOL.clear()
g = fresh()
d = take("Al", "cavalry", 1)
place(g, d, wr_t, "Al")
art = take("Fr", "artillery", 3)
place(g, art, src, "Fr")
legal, reasons, _ = g.battle_check("Fr", [art], [d])
check(legal, f"a Woods/Road hex may be bombarded INTO ({hn(src)} -> {hn(wr_t)}) [1979 Terrain Key: 'Artillery may bombard into Woods-Road hexes']")
c, t = town_pairs[0]
POOL.clear()
g = fresh()
d = take("Al", "cavalry", 1)
place(g, d, t)
art = take("Fr", "artillery", 3)
place(g, art, c)
legal, reasons, _ = g.battle_check("Fr", [art], [d])
check(legal, f"bombardment over a Town hex is legal ({hn(c)} -> {hn(t)}) [ART-16]")

print("== dice ==")
g = fresh(seed=3)
rolls = [g.roll_die() for _ in range(300)]
check(all(1 <= r <= 6 for r in rolls) and len(set(rolls)) == 6 and g.s["rng_calls"] == 300, "engine-owned d6: 1..6, seeded, counted [CBT-03, spec #11]")
g2 = fresh(seed=3)
check([g2.roll_die() for _ in range(300)] == rolls, "same seed -> same 300 rolls")

print("ALL PASS" if ok else "FAILURES ABOVE")
sys.exit(0 if ok else 1)
