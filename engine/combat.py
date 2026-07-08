"""
combat.py - Tobruk Scenario One direct-fire resolution (rulebook pp.4-5).

Data-driven: all numbers come from games/<game>/combat.json, which is itself a
transcription of the charts inside the VASSAL module (each table cites its
source image). This module implements the PROCEDURE — the three questions of
I.F — as pure functions. The RNG is injected so every roll is owned, seeded
and logged by the caller (the legality gate / game log), never by the AI.

Q1  Has the target been hit?   rounds (ROF initial/acquired) x 2d6 >= HPN(range) [+1 target moved]
Q2  What part was hit?         aspect (facing vs shortest-path hexside) -> card's Area Impacted, 2d6
Q3  What damage?               card's damage row: weapon x part, range-gated clauses

Damage-code grammar (p.5.b): clauses split on '|', each optionally gated
'<=R' (applies only at range<=R; clauses ordered, first match by range wins;
none matching = hit, no effect). Tokens: K, M, F, Cn (crew — IGNORED in
Scenario 1 per p.5.e), (Pn) = roll one die, result <= n is a K-kill. '-' =
ricochet, no damage.
"""
import json
import math
import os
import re

CLAUSE_RE = re.compile(r"^(?P<body>[^<]*?)(?:<=(?P<rng>\d+))?$")
PK_RE = re.compile(r"\(P(\d+)\)")


class CombatData:
    def __init__(self, game_dir):
        with open(os.path.join(game_dir, "combat.json"), encoding="utf-8") as f:
            self.raw = json.load(f)
        self.weapons = self.raw["weapons"]
        self.afv_types = self.raw["afv_types"]
        self.cards = self.raw["cards"]
        self.target_moved_mod = self.raw["hpn_modifiers"]["target_moved"]
        self.init_max_hpn = self.raw["fire_initiation"]["max_unadjusted_hpn"]

    def afv_type(self, counter_name):
        for key, t in self.afv_types.items():
            if t["counter_token"] in counter_name:
                return key
        return None

    def weapon_of(self, afv_key):
        return self.afv_types[afv_key]["weapon"]

    def hpn(self, weapon_key, rng_hexes):
        """Unadjusted Hit Probability Number at a range, or None = no fire possible."""
        tbl = self.weapons[weapon_key]["hpn_by_range"]
        if rng_hexes < 1 or rng_hexes > len(tbl):
            return None
        return tbl[rng_hexes - 1]

    def rof(self, weapon_key, acquired):
        w = self.weapons[weapon_key]
        return w["rof_acquired"] if acquired else w["rof_initial"]


def parse_damage_cell(cell):
    """'K/C2<=4|C2(P4)<=8' -> [{'dmg':{'K','C2'},'pk':None,'max_range':4}, ...]"""
    if cell.strip() in ("-", ""):
        return []
    out = []
    for part in cell.split("|"):
        m = CLAUSE_RE.match(part.strip())
        body, rng = m.group("body"), m.group("rng")
        pk = None
        pkm = PK_RE.search(body)
        if pkm:
            pk = int(pkm.group(1))
            body = PK_RE.sub("", body)
        toks = {t for t in body.split("/") if t}
        out.append({"dmg": toks, "pk": pk,
                    "max_range": int(rng) if rng else None})
    return out


# ------------------------------------------------------------------ aspect
# Pointy-top facing indices (matches game.json facing: offset 30deg, step 60):
# 0=NE 1=E 2=SE 3=SW 4=W 5=NW. Angle measured clockwise from screen-up.
def bearing_sector(from_xy, to_xy):
    """Which hexside sector of the hex at from_xy faces to_xy.
    Returns (sector 0..5, on_boundary bool)."""
    dx = to_xy[0] - from_xy[0]
    dy = to_xy[1] - from_xy[1]
    ang = math.degrees(math.atan2(dx, -dy)) % 360.0   # clockwise from up
    sector = round((ang - 30.0) / 60.0) % 6
    center = (30.0 + sector * 60.0) % 360.0
    delta = abs((ang - center + 180.0) % 360.0 - 180.0)
    return sector, delta > 29.0   # within ~1deg of the vertex line = tie


def target_aspect(target_facing, target_xy, firer_xy, target_moved):
    """Rulebook I.F.2.b: aspect = relation of the target hexside crossed by the
    shortest path (approximated by bearing) to the target's facing. Ties on a
    vertex line use the printed tie rules: front/flank -> FRONT; flank/rear ->
    REAR if stationary, FLANK if it moved (I.F.2.b.2-3)."""
    sector, boundary = bearing_sector(target_xy, firer_xy)
    rel = (sector - target_facing) % 6
    base = {0: "front", 1: "flank", 2: "flank", 3: "rear", 4: "flank", 5: "flank"}[rel]
    if boundary:
        # the two candidate sectors around the vertex line
        other = {0: "flank", 1: "front", 2: "rear", 3: "flank", 4: "rear", 5: "front"}
        cand = {base, other[rel]}
        if cand == {"front", "flank"}:
            return "front"
        if cand == {"flank", "rear"}:
            return "flank" if target_moved else "rear"
    return base


# ------------------------------------------------------------------ resolution
def resolve_fire(cd, firer_afv, target_afv, rng_hexes, target_moved,
                 target_facing, target_xy, firer_xy, acquired, roll2, roll1,
                 same_hex=False):
    """Full three-question fire procedure for one unit's combat-segment fire.
    roll2() -> (d1, d2) two dice; roll1() -> one die. Returns a dict with every
    intermediate number so the log can show the whole audit trail."""
    weapon = cd.weapon_of(firer_afv)
    card = cd.cards[cd.afv_types[target_afv]["card"]]
    dmg_rows = card["damage"][weapon]

    out = {"weapon": weapon, "range": rng_hexes, "acquired": bool(acquired),
           "rounds": cd.rof(weapon, acquired), "same_hex": bool(same_hex),
           "hpn": None, "hpn_adjusted": None, "shots": [], "damage": [],
           "k_kill": False, "m_kill": False, "f_kill": False}

    if same_hex:
        aspect = "front"                      # I.G.1: front for both units
        out["aspect"] = aspect
        hits = out["rounds"]                  # all rounds hit automatically
        out["shots"] = [{"auto": True, "hit": True}] * hits
    else:
        hpn = cd.hpn(weapon, rng_hexes)
        out["hpn"] = hpn
        if hpn is None:
            out["error"] = "beyond weapon's table — no hit possible (I.F.1.d)"
            return out
        adj = hpn + (cd.target_moved_mod if target_moved else 0)
        out["hpn_adjusted"] = adj
        aspect = target_aspect(target_facing, target_xy, firer_xy, target_moved)
        out["aspect"] = aspect
        hits = 0
        for _ in range(out["rounds"]):
            d1, d2 = roll2()
            hit = (d1 + d2) >= adj
            out["shots"].append({"dice": [d1, d2], "total": d1 + d2, "hit": hit})
            if hit:
                hits += 1
    out["hits"] = hits

    area = card["area_impacted"][aspect]
    for _ in range(hits):
        d1, d2 = roll2()
        part = area[str(d1 + d2)]
        rec = {"area_dice": [d1, d2], "part": part, "result": []}
        if part == "-":
            rec["note"] = "ricochet (p.5: '-' round fails to penetrate)"
            out["damage"].append(rec)
            continue
        row = dmg_rows[aspect] if part in dmg_rows.get(aspect, {}) else dmg_rows["any"]
        clauses = parse_damage_cell(row.get(part, "-"))
        applied = None
        for cl in clauses:
            if cl["max_range"] is None or rng_hexes <= cl["max_range"]:
                applied = cl
                break
        if applied is None:
            rec["note"] = "hit but no damage at this range (p.5.b '<=' rule)"
            out["damage"].append(rec)
            continue
        toks = {t for t in applied["dmg"] if not t.startswith("C")}  # p.5.e: ignore Cx in Scenario 1
        ignored = applied["dmg"] - toks
        if ignored:
            rec["ignored_crew"] = sorted(ignored)
        rec["result"] = sorted(toks)
        if applied["pk"] is not None:
            die = roll1()
            rec["pk_roll"] = {"die": die, "needed": applied["pk"],
                              "k_kill": die <= applied["pk"]}
            if die <= applied["pk"]:
                toks = toks | {"K"}
                rec["result"] = sorted(rec["result"] + ["K(P)"])
        out["k_kill"] = out["k_kill"] or ("K" in toks)
        out["m_kill"] = out["m_kill"] or ("M" in toks)
        out["f_kill"] = out["f_kill"] or ("F" in toks)
        out["damage"].append(rec)
    return out


# ------------------------------------------------------------------ self-test
if __name__ == "__main__":
    import gamespec
    cd = CombatData(os.path.join(gamespec.games_root(), "tobruk"))
    ok = True

    # Rulebook p.4 worked example: 47mm M37 (I) needs 11+ at 12-13 hexes.
    # (Stated for the ATG; the M13/40's tank mount of the same gun reads the
    # same at those ranges on the module's To-Hit table.)
    for r, want in [(12, 11), (13, 11)]:
        got = cd.hpn("47mmM37", r)
        print(f"47mmM37 @ {r} hexes -> HPN {got} (rulebook: {want})",
              "PASS" if got == want else "FAIL")
        ok &= got == want

    # Beyond-table = no fire (I.F.1.d)
    print("47mmM37 @ 17 hexes ->", cd.hpn("47mmM37", 17), "(expect None)")
    ok &= cd.hpn("47mmM37", 17) is None

    # Damage grammar
    cl = parse_damage_cell("K/C2<=4|C2(P4)<=8")
    assert cl[0]["dmg"] == {"K", "C2"} and cl[0]["max_range"] == 4
    assert cl[1]["pk"] == 4 and cl[1]["max_range"] == 8
    print("damage grammar PASS")

    # Aspect: firer due south of a north-facing (NE=0) target -> rear-ish
    a = target_aspect(0, (0, 0), (0, 1000), target_moved=False)
    print("aspect: firer due S of NE-facing target ->", a)

    # Deterministic fire: force dice
    seq2 = iter([(6, 6), (5, 4), (3, 3), (2, 5), (4, 4)])
    res = resolve_fire(cd, "stuart", "m13_40", 6, False, 0, (0, 0), (0, 1000),
                       acquired=False, roll2=lambda: next(seq2), roll1=lambda: 1)
    print("Stuart @6 vs M13/40 (rear), dice 12 & 9 vs HPN", res["hpn"],
          "-> hits", res["hits"], "damage", [d["result"] for d in res["damage"]])
    print("SELF-TEST", "PASS" if ok else "FAIL")
