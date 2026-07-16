"""
formations.py - Family B: formation states + facing geometry (engine-level).

Any game whose spec declares a `formations` block gets formation-keyed
movement: unit state carries (facing, formation), and every movement
question — which hexes are in front, what a step costs, what a facing or
formation change costs, where a unit may slide/reverse — is answered from
the game's transcribed Terrain Effects Chart, not from code constants.
The TEC lives in game.json as the chart's literal cell tokens so a human
can audit the transcription against the printed page (spec #14).

Reference implementation: Austerlitz (GMT 2000), GBoNW Vol. I — rulebook
sections cited per function. The same shapes drive the Triumph & Glory
siblings by swapping the data block.

Direction model (flat-top hexes): 12 facings.
  even d = hexside facing:  d//2 in 0..5 = N, NE, SE, S, SW, NW
  odd  d = vertex facing:   between hexsides (d-1)//2 and ((d+1)%12)//2
A unit facing a hexside is in Column-family formation; facing a vertex is
Line-family [6.3.1/6.3.2: "Any unit facing a vertex is considered to be in
Line ... facing a hexside is considered to be in Column"]. Square/Skirmish/
Disorder are explicit states carried alongside facing.

TEC cell tokens (verbatim from the chart, parsed here and only here):
  "2" / "1/2"    entry cost in MPs (fractions allowed on roads)
  "+1"           hexside surcharge (streams, slopes, walls)
  "2D" "+1d"     cost with auto-disorder (D) / disorder check (d) [5.1.1]
  "P"            prohibited for that unit column
  "OT"           pay the other terrain in the hex (roads: Lines can't use
                 Road Movement) [TEC key]
  "M" / "m"      all / half-rounded-up of the unit's movement allowance
  "2x"           double the underlying terrain cost (slide/reverse)
  "NA" / "na"    not allowed / not applicable
  "†" / "‡"      minor-slope escalators: first crossing free, +1 (†) or
                 +2 (‡) per additional minor slope crossed this move
"""

FACINGS = 12
HEXSIDES = 6
# Flat-top hexside order (pixel deltas mirror gamespec.Game.neighbors).
_SIDE_NAMES = ("N", "NE", "SE", "S", "SW", "NW")


def is_vertex(facing):
    return facing % 2 == 1


def side_neighbor(game, col, row, side):
    """Neighbor hex across hexside `side` (0..5 N,NE,SE,S,SW,NW), or None
    off-map. Pixel math like gamespec.neighbors so column parity is safe."""
    g = game.grid
    dx, dy = g.dx, g.dy
    offs = {0: (0, -dy), 1: (dx, -dy / 2), 2: (dx, dy / 2),
            3: (0, dy), 4: (-dx, dy / 2), 5: (-dx, -dy / 2)}
    x, y = g.hex_to_pixel(col, row)
    ox, oy = offs[side]
    c, r, _ = g.pixel_to_hex(x + ox, y + oy)
    if game.bounds:
        (c0, c1), (r0, r1) = game.bounds["cols"], game.bounds["rows"]
        if not (c0 <= c <= c1 and r0 <= r <= r1):
            return None
    return (c, r)


def facing_sides(facing, formation_kind):
    """The hexside indexes a unit's FRONT covers, by facing kind.
    hexside-facer (column family): the faced side only [6.3.2 Fig B].
    vertex-facer (line family): the two sides meeting at the vertex
    [6.3.1 Fig A]. all-around (skirmish/square): every side [6.3.3/6.3.4]."""
    if formation_kind == "all":
        return list(range(HEXSIDES))
    if is_vertex(facing):
        a = (facing - 1) % FACINGS // 2
        b = (facing + 1) % FACINGS // 2
        return [a, b]
    return [facing // 2]


def front_hexes(game, col, row, facing, kind):
    """Hexes adjacent through the unit's front hexside(s) — the move-through
    set [5.0] and the 5.1.3 enemy-contact set."""
    out = []
    for s in facing_sides(facing, kind):
        n = side_neighbor(game, col, row, s)
        if n:
            out.append(n)
    return out


def flank_hexes(game, col, row, facing, kind):
    """Line-family flank hexes (slide targets [6.3.1]); hexside-facers and
    all-around units have none that matter for movement (slide NA/na)."""
    if kind != "vertex" or not is_vertex(facing):
        return []
    a = (facing - 3) % FACINGS // 2
    b = (facing + 3) % FACINGS // 2
    return [n for n in (side_neighbor(game, col, row, a),
                        side_neighbor(game, col, row, b)) if n]


def rear_hexes(game, col, row, facing, kind):
    """Reverse-movement targets [6.3.1/6.3.2]: the hex(es) opposite the
    front — two for vertex-facers, one for hexside-facers."""
    back = (facing + HEXSIDES) % FACINGS if is_vertex(facing) \
        else (facing + HEXSIDES) % FACINGS
    return front_hexes(game, col, row, back, "vertex" if is_vertex(facing)
                       else "hexside")


# --------------------------------------------------------------- TEC tokens
class Cell:
    """One parsed TEC cell. Kept verbatim in `raw` for citation display."""
    __slots__ = ("raw", "cost", "surcharge", "prohibited", "other_terrain",
                 "whole_ma", "half_ma", "double", "auto_disorder",
                 "disorder_check", "minor_slope", "not_applicable")

    def __init__(self, raw):
        self.raw = raw
        t = str(raw).strip()
        self.cost = None
        self.surcharge = None
        self.prohibited = t in ("P", "NA")
        self.not_applicable = t == "na"
        self.other_terrain = t.startswith("OT")
        self.whole_ma = t == "M"
        self.half_ma = t == "m"
        self.double = t == "2x"
        self.minor_slope = 1 if t == "†" else (2 if t == "‡" else 0)
        self.auto_disorder = "D" in t
        self.disorder_check = "d" in t
        core = t.rstrip("Dd").replace("†", "").replace("‡", "")
        if core.startswith("+"):
            self.surcharge = _num(core[1:])
        elif core and not (self.prohibited or self.not_applicable
                           or self.other_terrain or self.whole_ma
                           or self.half_ma or self.double):
            self.cost = _num(core)


def _num(s):
    s = s.strip()
    if not s:
        return None
    if "/" in s:
        a, b = s.split("/")
        return float(a) / float(b)
    return float(s)


class TEC:
    """The game's Terrain Effects Chart, keyed (row, column-id). Column ids
    are '<arm>_<formation>' ('infantry_line', 'artillery_foot', 'skirmisher',
    'leader'), exactly as the spec block declares them."""

    def __init__(self, block):
        self.columns = block["columns"]
        self.rows = {}
        for row_name, cells in block["rows"].items():
            if isinstance(cells, str):        # banner rows (Pond, Deep Stream)
                self.rows[row_name] = cells
                continue
            if len(cells) != len(self.columns):
                raise ValueError(
                    f"TEC row {row_name!r}: {len(cells)} cells for "
                    f"{len(self.columns)} columns")
            self.rows[row_name] = {c: Cell(v)
                                   for c, v in zip(self.columns, cells)}

    def cell(self, row, column):
        r = self.rows.get(row)
        if r is None or isinstance(r, str):
            return None
        return r.get(column)


def column_id(arm, formation):
    """TEC column for a unit. A unit IN skirmish formation uses the
    Skirmisher column whatever its arm [6.3.3]; leaders have their own
    column; artillery columns split foot/horse, not formation."""
    if formation == "skirmish":
        return "skirmisher"
    if arm in ("skirmisher", "leader"):
        return arm
    if arm.startswith("artillery"):
        return arm                            # artillery_foot / artillery_horse
    if formation == "square":                 # square is immobile [6.3.4];
        return f"{arm}_column"                # cost column only used for
    return f"{arm}_{formation}"               # formation-change pricing


# ----------------------------------------------------------------- family
class Formations:
    """The per-game Family-B bundle: parsed TEC + formation properties.
    Constructed from game.spec['formations']; games without the block don't
    build one (gamespec untouched — frozen contract)."""

    def __init__(self, game):
        self.game = game
        block = game.spec["formations"]
        self.tec = TEC(block["tec"])
        self.defs = block["formations"]       # name -> properties dict
        self.stacking = block.get("stacking", {})
        self.cite = block.get("cite", "")

    # ---------------------------------------------------------- properties
    def kind(self, formation):
        """Facing kind: 'vertex' (line family), 'hexside' (column family),
        'all' (skirmish/square)."""
        return self.defs[formation]["facing"]

    def may_road_move(self, formation):
        return bool(self.defs[formation].get("road_movement"))

    def immobile(self, formation):
        return bool(self.defs[formation].get("immobile"))

    # ------------------------------------------------------------- costing
    def entry(self, unit, terrain, road=None):
        """Entry Cell for `unit` moving into `terrain`, honoring Road
        Movement [5.3] when `road` names the road row and the formation may
        use it (Lines may not; OT in the road column = pay other terrain)."""
        col = column_id(unit["arm"], unit["formation"])
        if road and self.may_road_move(unit["formation"]):
            c = self.tec.cell(road, col)
            if c is not None and not c.other_terrain:
                return c
        return self.tec.cell(terrain, col)

    def hexside(self, unit, hexside_row):
        """Hexside-crossing Cell (streams, slopes, walls) or None."""
        if not hexside_row:
            return None
        return self.tec.cell(hexside_row, column_id(unit["arm"],
                                                    unit["formation"]))

    def action_cost(self, unit, action, ma):
        """MP cost of a TEC action row for this unit: 'change_formation',
        'change_facing', 'about_face' — resolving M/m against the unit's
        movement allowance [TEC key]. None = not allowed (NA/na)."""
        override = self.defs[unit["formation"]].get(f"{action}_override")
        if override is not None:              # TEC note S: a unit already in
            return float(override)            # square pays 2 MPs to change
        c = self.tec.cell(action, column_id(unit["arm"], unit["formation"]))
        if c is None or c.prohibited or c.not_applicable:
            return None
        if c.whole_ma:
            return float(ma)
        if c.half_ma:
            return float((int(ma) + 1) // 2)  # half rounded up [TEC key 'm']
        return c.cost

    # ------------------------------------------------------------ stacking
    def stack_limit(self, arm, formation, terrain_class):
        """Per-hex SP limit from the Stacking Chart [7.1]; None = NA (that
        formation may not be in that terrain with multiple units)."""
        lim = (self.stacking.get(arm, {}).get(formation, {})
               .get(terrain_class))
        return lim
