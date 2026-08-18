import json
import os
import random
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "engine"))
sys.path.insert(0, HERE)
import gamespec  # noqa: E402
import verify_game  # noqa: E402
from naw import NawGame  # noqa: E402
import naw_drive as D  # noqa: E402

G = gamespec.Game(HERE)
SCEN = os.path.join(HERE, "scenario_2nd_ed.json")
CAT = json.load(open(SCEN, encoding="utf-8"))
UNITS = {u["id"]: u for u in CAT["units"] + CAT["reserve"]}
ok = True


def check(cond, msg):
    global ok
    print(("PASS  " if cond else "FAIL  ") + msg)
    ok = ok and bool(cond)


def hx(s):
    return int(s[:2]), int(s[2:])


def hn(h):
    return f"{h[0]:02d}{h[1]:02d}"


def fresh(seed=42, mover="Fr", phase="combat"):
    g = NawGame(G, SCEN, tempfile.mkdtemp(), seed=seed)
    g.s["units"] = {}
    g.s["mover"] = mover
    g.s["phase"] = phase
    g.s["pool"] = {}
    return g


def place(g, pid, h):
    e = g.catalog[pid]
    g.s["units"][pid] = {"pid": pid, "slot": e["slot"], "name": e["name"], "side": e["side"], "col": h[0], "row": h[1]}


def arm(g):
    g.s["contacts"] = g._contact_pairs(g.s["mover"])
    g.s["fought"], g.s["defended"], g.s["advanced"], g.s["disrupted"] = [], [], [], []
    g.s["pending"] = None


def set_die(g, want):
    for seed in range(1, 100000):
        r = random.Random(seed)
        for _ in range(g.s["rng_calls"]):
            r.random()
        if 1 + int(r.random() * 6) == want:
            g.s["seed"] = seed
            return
    raise RuntimeError("no seed")


def die_for(g, col, want_result):
    for d in range(1, 7):
        if g.crt_result(col, d) == want_result:
            return d
    raise RuntimeError(f"{want_result} not in column {col}")


def battle(g, atk, dfd, want=None):
    side = g.s["mover"]
    okc, reasons, meta = g.battle_check(side, atk, dfd)
    if not okc:
        raise RuntimeError(reasons)
    if want:
        set_die(g, die_for(g, meta["column"], want))
    r = g.submit(side, {"type": "battle", "attackers": atk, "defenders": dfd})
    if not r["verdict"]["legal"]:
        raise RuntimeError(r["verdict"])
    return r


def result_of(r):
    return [e for e in r["result"] if "battle" in e][0]


def nb(h, i):
    return sorted(G.neighbors(*h))[i]


def by(side, cls, att, n=0):
    c = [u["id"] for u in CAT["units"] + CAT["reserve"] if u["side"] == side and u["cls"] == cls and u["stats"]["att"] == att]
    return c[n]


C = hx("0613")
N = sorted(G.neighbors(*C))
FR_INF4, FR_INF4b = by("Fr", "infantry", 4, 0), by("Fr", "infantry", 4, 1)
FR_INF7 = by("Fr", "infantry", 7, 0)
FR_INF5 = by("Fr", "infantry", 5, 0)
FR_ART3, FR_ART5, FR_ART2 = by("Fr", "artillery", 3, 0), by("Fr", "artillery", 5, 0), by("Fr", "artillery", 2, 0)
FR_CAV1 = by("Fr", "cavalry", 1, 0)
AL_INF4, AL_INF6, AL_INF7, AL_INF1, AL_INF2 = by("Al", "infantry", 4, 0), by("Al", "infantry", 6, 0), by("Al", "infantry", 7, 0), by("Al", "infantry", 1, 0), by("Al", "infantry", 2, 0)
AL_ART2, AL_ART3 = by("Al", "artillery", 2, 0), by("Al", "artillery", 3, 0)
AL_CAV1, AL_CAV3 = by("Al", "cavalry", 1, 0), by("Al", "cavalry", 3, 0)

print("== obligations fixed at the start of the Combat Phase (CBT-06/07/10, NAW2-OR-6 A) ==")
g = fresh(phase="movement")
g.s["units"] = g._scenario_units()
r = g.submit("Fr", {"type": "end_movement"})
check(r["verdict"]["legal"] and g.s["contacts"], f"end_movement fixes {len(g.s['contacts'])} contact pairs from the printed at-start position")
fs, es = g.obligations()
check(fs and es, f"at-start obligations: {len(fs)} French must attack, {len(es)} Allied must be attacked [CBT-06/CBT-07]")
r = g.submit("Fr", {"type": "end_phase"})
check(not r["verdict"]["legal"] and "CBT-06" in r["verdict"]["reasons"][0], "end_phase REFUSED while mandatory attacks remain, naming them [CBT-06/CBT-07]")
fl = g.flow()["combat"]
check(fl["obligations_fixed"] and [u["pid"] for u in fl["must_attack"]] == fs and [u["pid"] for u in fl["must_be_attacked"]] == es, "flow.combat carries the fixed obligation lists")

g = fresh()
place(g, FR_INF4, N[0])
place(g, FR_INF4b, N[1])
place(g, AL_INF4, C)
arm(g)
okc, why, _ = g.battle_check("Fr", [FR_INF4], [AL_INF4])
check(not okc and "CBT-07" in why[0] and g.unit(FR_INF4b)["name"] in why[0], f"F1 alone vs E when F2 touches only E: refused - F2 would be stranded [CBT-07/CBT-10]: {why[0][:90]}")
okc, why, _ = g.battle_check("Fr", [FR_INF4, FR_INF4b], [AL_INF4])
check(okc, "F1+F2 vs E accepted")
g = fresh()
place(g, FR_INF7, C)
place(g, AL_INF4, N[0])
place(g, AL_INF6, N[1])
arm(g)
okc, why, _ = g.battle_check("Fr", [FR_INF7], [AL_INF4])
check(not okc and "CBT-06" in why[0] and g.unit(AL_INF6)["name"] in why[0], f"F vs E1 alone when E2's only attacker is F: refused - E2 must be attacked [CBT-06/CBT-10]: {why[0][:80]}")
okc, why, _ = g.battle_check("Fr", [FR_INF7], [AL_INF4, AL_INF6])
check(okc, "F vs E1+E2 accepted (one attacker, several defenders) [CBT-12]")
g = fresh()
place(g, FR_INF7, C)
place(g, FR_INF4, nb(N[0], 0) if nb(N[0], 0) != C else nb(N[0], 1))
h_e1 = N[0]
place(g, AL_INF4, h_e1)
place(g, AL_INF6, N[1])
arm(g)
lp = g.live_pairs()
check((FR_INF4, AL_INF4) in lp or not any(f == FR_INF4 for f, _ in lp), "contact geometry set")
plan = g.complete_assignment()
check(plan and all(g.battle_check("Fr", a, d)[0] for a, d in plan), f"complete_assignment yields legal attacks: {plan}")

print("== the constructive proof of NAW2-OR-5: a complete assignment exists at every phase-start position ==")
rng = random.Random(7)
n_pos = n_pairs = 0
bad = []
FRS = [u["id"] for u in CAT["units"] if u["side"] == "Fr"]
ALS = [u["id"] for u in CAT["units"] if u["side"] == "Al"]
for trial in range(150):
    g = fresh()
    cells = [(c, r) for c in range(4, 12) for r in range(10, 17) if G.hex_terrain(c, r) != "woods"]
    rng.shuffle(cells)
    k = rng.randint(3, 8)
    for pid in rng.sample(FRS, k):
        place(g, pid, cells.pop())
    for pid in rng.sample(ALS, k):
        place(g, pid, cells.pop())
    arm(g)
    plan = g.complete_assignment()
    lp = g.live_pairs()
    n_pos += 1
    n_pairs += len(lp)
    if not lp:
        if plan:
            bad.append((trial, "plan without pairs"))
        continue
    for a, d in plan:
        okc, why, _ = g.battle_check("Fr", a, d)
        if not okc:
            bad.append((trial, a, d, why[0][:80]))
            break
        g.s["fought"] += a
        g.s["defended"] += d
    if g.obligations() != ([], []):
        bad.append((trial, "obligations left", g.obligations()))
check(not bad and n_pairs > 200, f"{n_pos} random positions, {n_pairs} contact pairs: every complete_assignment attack legal in sequence (forward check included) and no obligation left {bad[:2]}")

print("== results: DE / Dr / advance ==")
g = fresh()
place(g, FR_INF7, C)
place(g, FR_ART3, nb(C, 0))
place(g, AL_INF1, N[5])
arm(g)
r = battle(g, [FR_INF7], [AL_INF1], "DE")
b = result_of(r)
check(b["result"] == "DE" and AL_INF1 not in g.s["units"] and g.s["losses"]["Al"] == 1, "DE: defender eliminated, one printed Strength Point on the Allied ledger [DE; VIC-05]")
p = g.s["pending"]
check(p and p["awaiting"] == "advance" and p["by"] == "Fr", "advance option pending for the attacker [CBT-14]")
pv = g._pending_view()
check(pv["pairs"] == [{"pid": FR_INF7, "slot": g.unit(FR_INF7)["name"], "hex": list(N[5]), "name": hn(N[5])}], f"exactly the melee attacker may advance into the vacated hex {pv['pairs']}")
r = g.submit("Fr", {"type": "advance", "unit": FR_INF7, "hex": [1, 1]})
check(not r["verdict"]["legal"], "advance elsewhere refused")
r = g.submit("Al", {"type": "advance", "unit": FR_INF7, "hex": list(N[5])})
check(not r["verdict"]["legal"], "the other player cannot answer the pending")
r = g.submit("Fr", {"type": "advance", "unit": FR_INF7, "hex": list(N[5])})
check(r["verdict"]["legal"] and (g.unit(FR_INF7)["col"], g.unit(FR_INF7)["row"]) == N[5] and FR_INF7 in g.s["advanced"] and g.s["pending"] is None, "advance moves the unit one hex, marks it advanced, clears the pending [CBT-14/CBT-16]")
r = g.submit("Fr", {"type": "end_phase"})
check(r["verdict"]["legal"], "no obligations left: Combat Phase closes")

g = fresh()
place(g, FR_INF7, C)
place(g, AL_INF1, N[5])
arm(g)
battle(g, [FR_INF7], [AL_INF1], "DE")
r = g.submit("Fr", {"type": "advance", "decline": True})
check(r["verdict"]["legal"] and g.s["pending"] is None and (g.unit(FR_INF7)["col"], g.unit(FR_INF7)["row"]) == C, "advance declined - never compulsory [OPTIONAL ADVANCE p.5]")

g = fresh()
place(g, FR_INF4, C)
place(g, AL_INF2, N[5])
arm(g)
r = battle(g, [FR_INF4], [AL_INF2], "Dr")
b = result_of(r)
p = g.s["pending"]
check(b["result"] == "Dr" and p and p["awaiting"] == "retreat" and p["by"] == "Fr", "Dr: retreat pending, the VICTORIOUS (attacking) player chooses the direction [RETREAT AND ADVANCE p.5, E21]")
pv = g._pending_view()
opts = {o["name"] for o in pv["units"][0]["options"]}
_, epos, _, ezoc = g._board_sets("Al")
legal = {hn(h) for h in G.neighbors(*N[5]) if G.on_map(*h) and h not in ezoc and h not in epos and G.hex_terrain(*h) != "woods"}
check(opts == legal and len(opts) == 3, f"retreat options = adjacent hexes outside the attacker's ZOC: {sorted(opts)} [RET p.5 'not into Enemy Zones of Control']")
bad_h = [h for h in G.neighbors(*N[5]) if h in ezoc][0]
r = g.submit("Fr", {"type": "retreat", "unit": AL_INF2, "path": [list(bad_h)]})
check(not r["verdict"]["legal"] and "Zones of Control" in r["verdict"]["reasons"][0], "a hex in the enemy ZOC is refused")
r = g.submit("Al", {"type": "retreat", "unit": AL_INF2, "path": [list(hx(sorted(legal)[0]))]})
check(not r["verdict"]["legal"], "the defender does not choose his own retreat in the 2nd Edition [E21]")
tgt = hx(sorted(legal)[0])
r = g.submit("Fr", {"type": "retreat", "unit": AL_INF2, "path": [list(tgt)]})
check(r["verdict"]["legal"] and (g.unit(AL_INF2)["col"], g.unit(AL_INF2)["row"]) == tgt, "retreat applied one hex")
p = g.s["pending"]
check(p and p["awaiting"] == "advance" and g._pending_view()["pairs"][0]["hex"] == list(N[5]), "then the attacker may advance into the vacated hex [CBT-14]")
r = g.submit("Fr", {"type": "advance", "unit": FR_INF4, "hex": list(N[5])})
check(r["verdict"]["legal"], "advance after Dr")

print("== retreat bars: EZOC, off map, woods, enemy hex, road hexside ==")
g = fresh()
place(g, FR_INF4, hx("0210"))
place(g, AL_INF2, hx("0110"))
for h in G.neighbors(1, 10):
    if G.on_map(*h) and h != (2, 10) and G.hex_terrain(*h) != "woods" and h not in G.neighbors(2, 10):
        pass
arm(g)
r = battle(g, [FR_INF4], [AL_INF2], "Dr")
ret = [e for e in r["result"] if "retreat" in e]
check(g.s["pending"] and g.s["pending"]["awaiting"] == "advance" and ret and ret[0]["to"] == "0111" and ret[0]["forced"],
      f"edge unit at 0110 attacked from 0210: 0010/0011 are off the map, 0109/0211 in the attacker's ZOC - the ONLY safe hex 0111 is taken automatically {ret and ret[0]['to']} [RET p.5 'off the map']")
g = fresh()
place(g, FR_INF4, hx("0912"))
place(g, FR_INF4b, hx("0813"))
place(g, AL_INF7, hx("0913"))
arm(g)
r = battle(g, [FR_INF4, FR_INF4b], [AL_INF7], "Dr")
pv = g._pending_view()
opts = {o["name"] for o in pv["units"][0]["options"]} if g.s["pending"] else set()
check(hx("1014") not in {hx(o) for o in opts} or G.move_cost(hx("0913"), hx("1014")) is not None, "Woods/Road hex only across its road hexside [MOV-17, SPI 1979 4.2, NAW2-SD-3 A]")
check("1014" in opts, f"0913 -> 1014 along the road IS a legal retreat hex {sorted(opts)}")
g = fresh()
place(g, FR_INF4, hx("1013"))
place(g, AL_INF2, hx("1014"))
arm(g)
r = battle(g, [FR_INF4], [AL_INF2], "Dr")
check(AL_INF2 not in g.s["units"] and g.s["losses"]["Al"] == 2 and any("no path of retreat" in e.get("why", "") for e in r["result"]), "unit in the Hougoumont cul-de-sac (1014) attacked from 1013: only exit 0913 lies in the attacker's ZOC - no path, ELIMINATED [RET p.5]")

print("== retreat: victor picks the order; a unit without a path is eliminated ==")
g = fresh()
place(g, FR_INF7, C)
place(g, AL_INF1, N[0])
place(g, AL_INF2, N[1])
for h in set(G.neighbors(*N[0])) | set(G.neighbors(*N[1])):
    if h != C and h not in (N[0], N[1]) and h not in G.neighbors(*C):
        pass
arm(g)
okc, why, meta = g.battle_check("Fr", [FR_INF7], [AL_INF1, AL_INF2])
check(okc, "one attacker vs two adjacent defenders legal [CBT-12]")
r = battle(g, [FR_INF7], [AL_INF1, AL_INF2], "Dr")
p = g.s["pending"]
check(p and set(p["owed"]) <= {AL_INF1, AL_INF2} and p["by"] == "Fr", f"both defenders owe a retreat; the victor resolves them in any order {p['owed']}")
u0 = g._pending_view()["units"]
check(len(u0) == 2 and all(u["options"] for u in u0), "each still has options while both stand")

print("== disruption (p.5 DISRUPTION S1-S6) ==")
def ring_block(g, target, keep, side_pids):
    i = 0
    for h in sorted(G.neighbors(*target)):
        if h in keep:
            continue
        place(g, side_pids[i], h)
        i += 1
    return side_pids[:i]

g = fresh()
place(g, FR_INF4, N[0])
place(g, AL_INF2, C)
far = [h for h in G.neighbors(*C) if h not in G.neighbors(*N[0]) and h != N[0]]
check(len(far) == 3, f"three hexes of the defender's ring lie outside the attacker's ZOC {far}")
place(g, AL_INF1, far[0])
place(g, AL_INF4, far[1])
place(g, AL_INF6, far[2])
arm(g)
r = battle(g, [FR_INF4], [AL_INF2], "Dr")
pv = g._pending_view()
opts = pv["units"][0]["options"]
check(len(opts) == 3 and all("disrupts" in o["name"] for o in opts), f"no empty safe hex: the three friendly-occupied safe hexes are offered as DISRUPTIONS {[o['name'] for o in opts]} [S1]")
r = g.submit("Fr", {"type": "retreat", "unit": AL_INF2, "path": [list(far[0])]})
check(r["verdict"]["legal"] and (g.unit(AL_INF2)["col"], g.unit(AL_INF2)["row"]) == far[0] and AL_INF1 in g.s["disrupted"], "retreater takes the disrupted unit's hex; that unit is flagged disrupted [S1/S2]")
p = g.s["pending"]
check(p and p["owed"][0] == AL_INF1 and p["chain"] == [AL_INF2], "the disrupted unit is now first owed (chain reaction) [S5]")
pv = g._pending_view()
check(len(pv["units"]) == 1 and pv["units"][0]["displaced"], "only the chain front is offered while the chain runs")
opts2 = {o["name"] for o in pv["units"][0]["options"]}
check(hn(C) not in opts2, "the disrupted unit may not be pushed into the hex the retreater vacated - it lies in the attacker's ZOC [S3]")
r = g.submit("Fr", {"type": "retreat", "unit": AL_INF2, "path": [list(C)]})
check(not r["verdict"]["legal"], "another unit cannot be moved before the chain completes [S5]")

g = fresh()
place(g, FR_INF4, N[0])
place(g, AL_INF2, C)
place(g, AL_ART2, far[0])
place(g, AL_INF4, far[1])
place(g, AL_INF6, far[2])
arm(g)
battle(g, [FR_INF4], [AL_INF2], "Dr")
g.submit("Fr", {"type": "retreat", "unit": AL_INF2, "path": [list(far[0])]})
D.resolve_pending(g)
check(AL_ART2 in g.s["disrupted"] and g.s["pending"] is None, "artillery disrupted and chain settled")
g.submit("Fr", {"type": "end_phase"})
check(g.s["mover"] == "Al" and g.s["phase"] == "movement" and g.s["disrupted"] == [], "disruption flags clear with the Player-Turn")

g = fresh(mover="Al")
place(g, AL_ART2, C)
place(g, FR_INF4, N[0])
g.s["disrupted"] = [AL_ART2]
arm(g)
g.s["disrupted"] = [AL_ART2]
okc, why, _ = g.battle_check("Al", [AL_ART2], [FR_INF4])
check(not okc and "S6" in why[0], "disrupted artillery may NOT fire in the Combat Phase in which it was disrupted [DISRUPTION S6]")
g.s["disrupted"] = []
okc, why, _ = g.battle_check("Al", [AL_ART2], [FR_INF4])
check(okc, "the same artillery fires once the flag is gone")

g = fresh()
place(g, FR_INF4, N[0])
place(g, AL_INF2, C)
place(g, AL_INF1, far[0])
place(g, AL_INF4, far[1])
place(g, AL_INF6, far[2])
for h in set(G.neighbors(*far[0])) | set(G.neighbors(*far[1])) | set(G.neighbors(*far[2])):
    if h in (C, N[0]) or h in far or h in g.s["units"] and False:
        continue
    if not G.on_map(*h) or G.hex_terrain(*h) == "woods":
        continue
    if any((v["col"], v["row"]) == h for v in g.s["units"].values()):
        continue
    if h in G.neighbors(*N[0]):
        continue
    place(g, [u["id"] for u in CAT["units"] if u["side"] == "Fr" and u["id"] not in g.s["units"]][0], h)
arm(g)
if g.battle_check("Fr", [FR_INF4], [AL_INF2])[0]:
    r = battle(g, [FR_INF4], [AL_INF2], "Dr")
    check(AL_INF2 not in g.s["units"] and all(p in g.s["units"] for p in (AL_INF1, AL_INF4, AL_INF6)) and not g.s["disrupted"],
          "every friendly-occupied safe hex is itself boxed in: NO disruption, the units stay, the retreating unit is ELIMINATED instead [S4]")
else:
    check(False, "S4 geometry could not be built: " + g.battle_check("Fr", [FR_INF4], [AL_INF2])[1][0][:80])

print("== Ar / AE: attacker retreat chosen by the DEFENDER, defender may advance (NAW2-OR-17 A), artillery immunity ==")
g = fresh()
place(g, FR_INF4, N[0])
place(g, FR_ART3, hx("0611"))
place(g, AL_INF7, C)
arm(g)
okc, why, meta = g.battle_check("Fr", [FR_INF4, FR_ART3], [AL_INF7])
check(okc and meta["melee"] == [FR_INF4] and meta["bombarding"] == [FR_ART3], "adjacent infantry + bombarding artillery vs one defender [ART-08]")
r = battle(g, [FR_INF4, FR_ART3], [AL_INF7], "Ar")
p = g.s["pending"]
check(p and p["awaiting"] == "retreat" and p["by"] == "Al" and p["owed"] == [FR_INF4], "Ar: the adjacent attacker retreats, direction chosen by the victorious DEFENDER [Ar; RET p.5]")
r = g.submit("Fr", {"type": "retreat", "unit": FR_INF4, "path": [list(nb(N[0], 0))]})
check(not r["verdict"]["legal"], "the attacker cannot choose his own retreat")
pv = g._pending_view()
r = g.submit("Al", {"type": "retreat", "unit": FR_INF4, "path": pv["units"][0]["options"][0]["path"]})
check(r["verdict"]["legal"], "defender-chosen retreat applied")
p = g.s["pending"]
check(p and p["awaiting"] == "retreat" and p["voluntary"] and p["by"] == "Fr" and p["owed"] == [FR_ART3], "then the bombarding artillery may VOLUNTARILY take the Attacker Retreat [ART-11]")
r = g.submit("Fr", {"type": "retreat", "decline": True})
check(r["verdict"]["legal"] and (g.unit(FR_ART3)["col"], g.unit(FR_ART3)["row"]) != N[0], "declined: bombarding artillery unaffected [ART-03/ART-09]")
p = g.s["pending"]
check(p and p["awaiting"] == "advance" and p["by"] == "Al" and g._pending_view()["pairs"][0]["hex"] == list(N[0]), "the DEFENDER may advance into the vacated attacker hex [SPI 1979 6.3, NAW2-OR-17 A]")
r = g.submit("Al", {"type": "advance", "unit": AL_INF7, "hex": list(N[0])})
check(r["verdict"]["legal"] and AL_INF7 in g.s["advanced"], "defender advances")
okc, why, _ = g.battle_check("Fr", [FR_ART3], [AL_INF7])
check(not okc and "CBT-10" in why[0], "an advanced defender cannot be attacked again this phase [CBT-10 / OPTIONAL ADVANCE p.5]")

g = fresh()
place(g, FR_CAV1, N[0])
place(g, FR_ART3, hx("0611"))
place(g, AL_INF7, C)
arm(g)
r = battle(g, [FR_CAV1, FR_ART3], [AL_INF7], "AE")
check(FR_CAV1 not in g.s["units"] and FR_ART3 in g.s["units"] and g.s["losses"]["Fr"] == 1 and any("immune" in e for e in r["result"]),
      "AE: adjacent attacker eliminated (1 SP to the French ledger), bombarding artillery immune [AE; ART-03/ART-09]")
p = g.s["pending"]
check(p and p["awaiting"] == "advance" and p["by"] == "Al", "defender may advance into the eliminated attacker's hex [NAW2-OR-17 A]")
g = fresh()
place(g, FR_ART3, hx("0611"))
place(g, AL_INF7, C)
arm(g)
r = battle(g, [FR_ART3], [AL_INF7], "AE")
check(FR_ART3 in g.s["units"] and g.s["pending"] is None and g.s["losses"]["Fr"] == 0, "bombardment alone with AE: nothing happens to the gun, no advance [ART-09/ART-18]")
g = fresh()
place(g, FR_ART3, hx("0611"))
place(g, AL_INF1, C)
arm(g)
r = battle(g, [FR_ART3], [AL_INF1], "Dr")
p = g.s["pending"]
check(p and p["awaiting"] == "retreat", "bombardment Dr: defender retreats")
D.resolve_pending(g)
check(g.s["pending"] is None and (g.unit(FR_ART3)["col"], g.unit(FR_ART3)["row"]) == hx("0611"), "bombarding artillery may not advance [ART-18] - no advance offered")

print("== EX (Exchange): printed strength, adjacent attackers only, over-payment, free all-bombardment ==")
g = fresh()
place(g, FR_INF7, N[0])
place(g, FR_INF4, N[1])
place(g, FR_ART3, hx("0611"))
place(g, AL_INF4, C)
arm(g)
r = battle(g, [FR_INF7, FR_INF4, FR_ART3], [AL_INF4], "EX")
check(AL_INF4 not in g.s["units"] and g.s["losses"]["Al"] == 4, "EX: defender eliminated")
p = g.s["pending"]
check(p and p["awaiting"] == "exchange_loss" and p["by"] == "Fr" and p["owe"] == 4 and set(p["involved"]) == {FR_INF7, FR_INF4}, f"attacker owes 4 SP from the ADJACENT attackers only {p and p['involved']} [EX; ART-04/05]")
r = g.submit("Fr", {"type": "exchange_loss", "units": [FR_ART3]})
check(not r["verdict"]["legal"], "bombarding artillery cannot pay the exchange [ART-05]")
r = g.submit("Fr", {"type": "exchange_loss", "units": []})
check(not r["verdict"]["legal"], "empty payment refused")
r = g.submit("Fr", {"type": "exchange_loss", "units": [FR_INF7]})
check(r["verdict"]["legal"] and FR_INF7 not in g.s["units"] and g.s["losses"]["Fr"] == 7, "paying 7 for 4 (whole units, AT LEAST equal) accepted [EX; NAW2-OR-15 A]")
p = g.s["pending"]
check(p and p["awaiting"] == "advance" and g._pending_view()["pairs"] == [{"pid": FR_INF4, "slot": g.unit(FR_INF4)["name"], "hex": list(C), "name": hn(C)}], "the surviving adjacent attacker may advance [EX p.5 'A surviving attacking unit may then exercise the option to advance']")
g = fresh()
place(g, FR_INF7, N[0])
place(g, FR_INF4, N[1])
place(g, AL_INF4, C)
arm(g)
battle(g, [FR_INF7, FR_INF4], [AL_INF4], "EX")
r = g.submit("Fr", {"type": "exchange_loss", "units": [FR_INF4]})
check(r["verdict"]["legal"] and FR_INF4 not in g.s["units"] and FR_INF7 in g.s["units"], "exact payment (4 for 4)")
g = fresh()
place(g, FR_CAV1, N[0])
place(g, FR_ART2, N[1])
place(g, FR_ART5, hx("0611"))
place(g, AL_INF4, C)
arm(g)
okc, why, meta = g.battle_check("Fr", [FR_CAV1, FR_ART2, FR_ART5], [AL_INF4])
check(okc and meta["column"] == "2:1" and meta["melee"] == [FR_CAV1, FR_ART2], "1 + 2 adjacent + 5 bombarding = 8 vs 4 = 2:1")
r = battle(g, [FR_CAV1, FR_ART2, FR_ART5], [AL_INF4], "EX")
check(FR_CAV1 not in g.s["units"] and FR_ART2 not in g.s["units"] and FR_ART5 in g.s["units"] and AL_INF4 not in g.s["units"] and g.s["pending"] is None and any(e.get("exchange") == "all" for e in r["result"]),
      "adjacent attackers total 3 < defender 4: every adjacent attacker is lost automatically (adjacent artillery included), the bombarding gun untouched [EX 'forced to lose more'; ART-10/ART-05]")
g2 = fresh()
FR_INF7b = by("Fr", "infantry", 7, 1)
place(g2, FR_INF7, hx("1409"))
place(g2, FR_INF7b, hx("1309"))
place(g2, FR_INF5, hx("1509"))
place(g2, AL_INF4, hx("1410"))
arm(g2)
okc, why, meta = g2.battle_check("Fr", [FR_INF7, FR_INF7b, FR_INF5], [AL_INF4])
check(okc and meta["defense"] == 8 and meta["column"] == "2:1", "defender in Town 1410 doubles for the odds: 19 vs 8 = 2:1 [CBT-18]")
r = battle(g2, [FR_INF7, FR_INF7b, FR_INF5], [AL_INF4], "EX")
p = g2.s["pending"]
check(p and p["awaiting"] == "exchange_loss" and p["owe"] == 4, "EX against a doubled defender: the exchange owes the PRINTED 4, not 8 [SPI 1979 6.3 'PRINTED value', NAW2-OR-15 A]")
r = g2.submit("Fr", {"type": "exchange_loss", "units": [FR_INF5]})
check(r["verdict"]["legal"] and g2.s["losses"] == {"Fr": 5, "Al": 4}, "the 5 pays for 4 (whole unit)")
g = fresh()
place(g, FR_ART3, hx("0611"))
place(g, FR_ART5, hx("0413"))
place(g, AL_INF2, C)
arm(g)
okc, why, meta = g.battle_check("Fr", [FR_ART3, FR_ART5], [AL_INF2])
check(okc and meta["melee"] == [], f"two guns bombarding one target from two hexes {why[0][:40]} [ART-08/ART-13]")
r = battle(g, [FR_ART3, FR_ART5], [AL_INF2], "EX")
check(AL_INF2 not in g.s["units"] and FR_ART3 in g.s["units"] and FR_ART5 in g.s["units"] and g.s["losses"]["Fr"] == 0 and any(e.get("exchange") == "free" for e in r["result"]),
      "all-bombardment EX: defender eliminated at no cost [ART-05; SPI 1979 6.8; NAW2-OR-7 A]")

print("== advance details: one per vacated hex, once per unit, road hexside, into EZOC ==")
g = fresh()
place(g, FR_INF7, C)
place(g, AL_INF1, N[0])
place(g, AL_INF2, N[1])
place(g, FR_INF4, [h for h in G.neighbors(*N[0]) if h in G.neighbors(*N[1]) and h != C][0])
arm(g)
r = battle(g, [FR_INF7, FR_INF4], [AL_INF1, AL_INF2], "DE")
pv = g._pending_view()
check(len(pv["hexes"]) == 2 and len(pv["pairs"]) == 4, f"two vacated hexes x two eligible attackers = 4 options {len(pv['pairs'])}")
g.submit("Fr", {"type": "advance", "unit": FR_INF7, "hex": list(N[0])})
pv = g._pending_view()
check(pv and all(p["pid"] != FR_INF7 for p in pv["pairs"]) and all(p["hex"] != list(N[0]) for p in pv["pairs"]) and len(pv["pairs"]) == 1,
      "after one advance: that unit is spent and that hex is filled - one unit per vacated hex, one hex per unit [Simonsen MOVES 28; OPTIONAL ADVANCE p.5]")
g.submit("Fr", {"type": "advance", "unit": FR_INF4, "hex": list(N[1])})
check(g.s["pending"] is None and set(g.s["advanced"]) == {FR_INF7, FR_INF4}, "second unit advances into the second hex; pending cleared")
g = fresh()
place(g, FR_INF7, hx("1013"))
place(g, FR_INF4, hx("0913"))
place(g, AL_INF1, hx("1014"))
arm(g)
okc, why, meta = g.battle_check("Fr", [FR_INF7, FR_INF4], [AL_INF1])
check(okc and meta["defense"] == 2, "attack across a non-road hexside into Woods/Road 1014 is legal (adjacency has no terrain limit); defender doubles [CBT-05, NAW2-D4]")
battle(g, [FR_INF7, FR_INF4], [AL_INF1], "DE")
pv = g._pending_view()
check([p["pid"] for p in pv["pairs"]] == [FR_INF4], f"only the unit on the road hexside (0913) may advance into 1014; 1013 may not [MOV-17, SPI 1979 4.2] {pv['pairs']}")
g = fresh()
place(g, FR_INF7, C)
place(g, AL_INF1, N[0])
place(g, AL_INF7, [h for h in G.neighbors(*N[0]) if h != C and h not in G.neighbors(*C)][0])
arm(g)
okc, why, _ = g.battle_check("Fr", [FR_INF7], [AL_INF1])
r = battle(g, [FR_INF7], [AL_INF1], "DE")
pv = g._pending_view()
check(pv and pv["pairs"] and pv["pairs"][0]["hex"] == list(N[0]) and N[0] in g._board_sets("Fr")[3], "advance offered into a hex inside another enemy unit's ZOC [CBT-15, OPTIONAL ADVANCE p.5]")

print("== demoralization and victory mid-phase (DEM-02, VIC-07) ==")
g = fresh()
place(g, FR_INF7, N[0])
place(g, FR_INF5, N[1])
place(g, AL_INF2, C)
place(g, AL_INF1, [h for h in G.neighbors(*N[1]) if h not in G.neighbors(*C) and h != C and h not in G.neighbors(*N[0])][0])
g.s["losses"] = {"Fr": 0, "Al": 38}
arm(g)
okc, why, meta = g.battle_check("Fr", [FR_INF5], [AL_INF1])
col_before = meta["column"]
r = battle(g, [FR_INF7], [AL_INF2], "DE")
check(g.s["demoralized"] and any("demoralized" in e for e in r["result"]) and g.s["first_forty"] == "Fr", "the fortieth Allied point falls mid-phase: DEMORALIZED immediately [DEM-01/DEM-02]")
D.resolve_pending(g)
okc, why, meta = g.battle_check("Fr", [FR_INF5], [AL_INF1])
check(meta["column"] == g.shift_column(col_before, 1) and "DEM-07" in why[0], f"the next French attack in the same phase is one column better ({col_before} -> {meta['column']}) [DEM-07/DEM-08]")
g = fresh()
place(g, FR_INF4, N[0])
place(g, AL_INF7, C)
g.s["losses"] = {"Fr": 36, "Al": 0}
arm(g)
r = battle(g, [FR_INF4], [AL_INF7], "AE")
check(g.s["over"] and g.s["winner"] == "Al" and g.s["pending"] is None, "the fortieth French point falls on an AE: Allied victory declared IMMEDIATELY, no pending survives [VIC-03/VIC-07]")
r = g.submit("Fr", {"type": "end_phase"})
check(not r["verdict"]["legal"], "no further action after the win")

print("== full random games through the gate: every combat state completable, logs replay, hashes identical ==")
n_games = 6
tot_b = tot_ret = tot_dis = tot_adv = 0
for seed in range(n_games):
    g = NawGame(G, SCEN, tempfile.mkdtemp(), seed=seed)
    D.play_game(g, seed=seed, aggression=0.8)
    check(g.s["over"], f"seed {seed}: game ends ({g.s['winner']}, GT {g.s['turn']}, {g.s['battle_no']} battles, losses {g.s['losses']}, {g.s['n']} entries)")
    okv, msg = verify_game.verify(HERE, g.log_path)
    check(okv, f"  verify_game: {msg[:70]}")
    g2 = NawGame(G, SCEN, tempfile.mkdtemp(), seed=seed)
    for e in [json.loads(l) for l in open(g.log_path, encoding="utf-8")][1:]:
        g2.submit(e["side"], e["action"])
    check(g2.state_hash() == g.state_hash(), "  same seed + same proposals -> identical state hash in a second gate")
    for l in open(g.log_path, encoding="utf-8"):
        e = json.loads(l)
        for ev in e.get("result") or []:
            tot_b += "battle" in ev
            tot_ret += "retreat" in ev
            tot_dis += "disrupted" in ev
            tot_adv += "advance" in ev
check(tot_b > 200 and tot_ret > 100 and tot_dis > 5 and tot_adv > 50, f"coverage: {tot_b} battles, {tot_ret} retreats, {tot_dis} disruptions, {tot_adv} advances")

print("ALL PASS" if ok else "FAILURES ABOVE")
sys.exit(0 if ok else 1)
