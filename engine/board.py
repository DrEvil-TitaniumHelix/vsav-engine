"""
board.py - Full-fidelity VASSAL save model (v2 mover). Game-agnostic:
grid, side detection and the stack-command map name come from the Game spec.

Understands the real save structure (cracked 2026-07-01):
  - piece commands:  +/<pieceId>/mark|immob;...piece;;;<img>.png;...;Map0;1;<x>,<y>...[<map>;<x>;<y>;<n>]
  - stack commands:  +/<stackId>/stack/<map>;<x>;<y>;<memberId>[;<memberId>...]
  - empty stack shells + immob markers (DZ/turn track) exist; left untouched.

Capabilities:
  - move ANY number of counters in one batch
  - move a piece that shares a stack (auto-split), or a whole stack at once
  - auto-join: moving onto an occupied hex appends to that hex's stack
  - identity-based editing (piece IDs), no blind string replacement

Usage:
  python board.py [--game <dir>] dump  <save.vsav>
  python board.py [--game <dir>] move  <save.vsav> <out.vsav> "<unit>=<hex>" ...
  python board.py [--game <dir>] movestack <save.vsav> <out.vsav> <from> <to>
"""
import re, sys
import vsav
import gamespec

PIECE_RE = re.compile(r"^\+/(\d+)/(\w+);")
IMG_RE = re.compile(r"piece;[^;]*;[^;]*;([^;]+?)\.(png|gif|svg|jpg|jpeg|bmp);")
# some modules reference counter art WITHOUT a file extension (VASSAL allows
# it); the BasicPiece image is then the raw 3rd field, escaped '/' permitted
IMG_NOEXT_RE = re.compile(r"piece;[^;]*;[^;]*;((?:\\.|[^;/])+);")
# blank-BasicPiece layered counters (A House Divided / VASL style): name in
# field 4, art lives on an emb2 layer image list
BP_NAME_RE = re.compile(r"piece;[^;]*;[^;]*;[^;]*;((?:\\.|[^/;])*)/")
# emb2 type: after 15 semicolons past "emb2" comes the comma-separated image list
EMB2_IMGS_RE = re.compile(r"emb2;(?:[^;]*;){15}([^;]+)")
# AHD-style pieces stack two emb2 traits: a "back"/damage face (*-back.png,
# often light-on-dark) and a Main face (dark-on-color). Prefer non-back art so
# the UI matches what VASSAL shows for an unflipped counter.
_BACK_FACE_RE = re.compile(r"-back\.(png|gif|jpe?g|bmp|svg)$", re.I)
# BasicPiece type ends at name/; state tokens follow (tab-separated).
_PIECE_STATE_RE = re.compile(
    r"piece;(?:\\.|[^;/])*;(?:\\.|[^;/])*;(?:\\.|[^;/])*;(?:\\.|[^/;])*/(.*)$")
ESC = "\x1b"


def _emb2_face_images(cmd):
    """Pick the best emb2 image list from a piece command (Main over -back)."""
    lists = []
    for raw in EMB2_IMGS_RE.findall(cmd):
        imgs = [s.strip().replace("\\", "") for s in raw.split(",") if s.strip()]
        if imgs:
            lists.append(imgs)
    if not lists:
        return []
    def score(imgs):
        return sum(0 if _BACK_FACE_RE.search(i) else 1 for i in imgs)
    return max(lists, key=score)


def _emb2_display_image(cmd):
    """Resolve the visible emb2 image: Main face list + current 1-based level.

    VASSAL Embellishment stores level as a signed int in piece state (see
    make_save.set_innermost_layer); draw uses image[abs(value)-1] when value≠0.
    When several emb2 traits exist, the last positive state token is the active
    Main-face level (back/damage twins are typically negative / inactive).
    """
    imgs = _emb2_face_images(cmd)
    if not imgs:
        return None
    m = _PIECE_STATE_RE.search(cmd)
    level = 1  # default: first layer (militia / N-00 / …)
    if m:
        positives = []
        for tok in m.group(1).split("\t"):
            t = tok.strip().rstrip("\\")
            if re.fullmatch(r"-?\d+", t):
                v = int(t)
                if v > 0:
                    positives.append(v)
        if positives:
            level = positives[-1]
    idx = max(0, min(len(imgs) - 1, abs(level) - 1))
    return imgs[idx]


class Board:
    def __init__(self, path, game):
        self.game = game
        self.path = path
        # Map edge: .vsav stores map-space XY; we keep board-space internally
        # so pieces align with the board image + Region/HexGrid origins.
        self.edge_w = int(getattr(game, "edge_w", 0) or 0)
        self.edge_h = int(getattr(game, "edge_h", 0) or 0)
        self.stack_re = re.compile(
            rf"^\+/(\d+)/stack/{re.escape(game.map_name)};(\d+);(\d+)((?:;\d+)*)\\*$")
        plain, self.moduledata, self.savedata = vsav.read_vsav(path)
        self.cmds = plain.split(ESC)
        self.pieces = {}   # id -> dict(name, kind, idx, x, y)  — board-space XY
        self.stacks = {}   # id -> dict(idx, x, y, members[list of piece ids])
        for i, c in enumerate(self.cmds):
            m = self.stack_re.match(c.rstrip())
            if m:
                members = [s for s in m.group(4).split(";") if s]
                mx, my = int(m.group(2)), int(m.group(3))
                self.stacks[m.group(1)] = dict(
                    idx=i, x=mx - self.edge_w, y=my - self.edge_h, members=members)
                continue
            m = PIECE_RE.match(c)
            if m:
                img = IMG_RE.search(c)
                if img:
                    # VASL escapes '/' in image paths as '\/' inside piece types
                    nm = img.group(1).strip().replace("\\", "")
                    imgfile = f"{nm}.{img.group(2)}"
                else:
                    img = IMG_NOEXT_RE.search(c)
                    if img:
                        nm = imgfile = img.group(1).strip().replace("\\", "")
                    else:
                        # blank BasicPiece + emb2 layer art (region-map modules)
                        bp = BP_NAME_RE.search(c)
                        imgfile = _emb2_display_image(c)
                        if not imgfile or not bp:
                            continue
                        nm = bp.group(1).strip().replace("\\", "") or imgfile.rsplit(".", 1)[0]
                # BasicPiece state, three formats seen in the wild:
                #   3.2-era (Westwall): "...\tfalse;<map>;1;x,y" (map EMPTY for singletons;
                #     Bitter Woods variant uses a map ID like "Map0" + board index 2)
                #   slot-style (Tobruk): "<map>;x;y;<gpid>"
                #   null-map (stacked AHD): "null;x;y;<gpid>" — XY comes from stack
                st = re.search(r"\tfalse;[^;\t]*;\d+;(\d+),(\d+)", c)
                if not st:
                    st = re.search(rf"[;\t]{re.escape(game.map_name)};(\d+);(\d+);\d+", c)
                if not st:
                    st = re.search(r"[;\t]null;(\d+);(\d+);\d+", c)
                if st:
                    x = int(st.group(1)) - self.edge_w
                    y = int(st.group(2)) - self.edge_h
                else:
                    x, y = None, None
                self.pieces[m.group(1)] = dict(name=nm, kind=m.group(2),
                                               img=imgfile,
                                               idx=i, x=x, y=y)
        self.member_of = {}  # piece id -> stack id
        for sid, s in self.stacks.items():
            for pid in s["members"]:
                self.member_of[pid] = sid
                # position pieces whose own state didn't parse from their stack
                p = self.pieces.get(pid)
                if p and p["x"] is None:
                    p["x"], p["y"] = s["x"], s["y"]
        # pieces with no resolvable position can't be played with
        self.pieces = {pid: p for pid, p in self.pieces.items() if p["x"] is not None}

    # ------------------------------------------------------------ queries
    def find(self, name_fragment):
        """Unique piece whose name contains the fragment. Raises if 0 or >1."""
        hits = [(pid, p) for pid, p in self.pieces.items() if name_fragment in p["name"]]
        exact = [(pid, p) for pid, p in hits if p["name"] == name_fragment]
        if len(exact) == 1:
            return exact[0]
        if len(hits) != 1:
            raise ValueError(f"'{name_fragment}': {len(hits)} matches "
                             f"{[p['name'] for _, p in hits][:6]}")
        return hits[0]

    def units(self):
        """All stacked (mark) pieces as the familiar unit dicts, one per piece."""
        out = []
        region = getattr(self.game, "space_kind", "hex") == "region"
        for pid, p in self.pieces.items():
            if p["kind"] not in self.game.unit_kinds:
                continue
            sid = self.member_of.get(pid)
            if region:
                loc = self.game.pixel_to_loc(p["x"], p["y"])
                locname = self.game.display_name(loc) if loc else None
                # hexnum/hexname stay as loc aliases for legal-dest / log chrome.
                # UI stack grouping must use stack_id (or pixel), not snapped loc —
                # multiple VASSAL stacks often nearest-snap to the same city.
                out.append(dict(id=pid, name=p["name"], side=self.game.side(p["name"]),
                                img=p["img"],
                                x=p["x"], y=p["y"], loc=loc, locname=locname,
                                hexnum=loc, hexname=locname,
                                stack_id=sid))
            else:
                col, row, hexn = self.game.grid.pixel_to_hex(p["x"], p["y"])
                out.append(dict(id=pid, name=p["name"], side=self.game.side(p["name"]),
                                img=p["img"],
                                x=p["x"], y=p["y"], col=col, row=row, hexnum=hexn,
                                stack_id=sid))
        return out

    def stack_at(self, x, y):
        """Non-empty stack id at exact pixel (x,y), else None."""
        for sid, s in self.stacks.items():
            if s["members"] and (s["x"], s["y"]) == (x, y):
                return sid
        return None

    # ------------------------------------------------------------ mutation
    def _fresh_id(self):
        top = max(int(i) for i in list(self.pieces) + list(self.stacks))
        return str(top + 1)

    def _to_map(self, x, y):
        """Board-space → VASSAL map-space (add Map edge padding)."""
        return x + self.edge_w, y + self.edge_h

    def _set_piece_xy(self, pid, nx, ny):
        p = self.pieces[pid]
        ox, oy = p["x"], p["y"]
        # Command strings store map-space coords; internals are board-space.
        omx, omy = self._to_map(ox, oy)
        nmx, nmy = self._to_map(nx, ny)
        c = self.cmds[p["idx"]]
        # exact old coord pair, both encodings, digit-boundary guarded
        c = re.sub(rf"(?<!\d){omx},{omy}(?!\d)", f"{nmx},{nmy}", c)
        c = re.sub(rf"(?<!\d){re.escape(self.game.map_name)};{omx};{omy};",
                   f"{self.game.map_name};{nmx};{nmy};", c)
        # stacked / null-map BasicPiece state (A House Divided et al.)
        c = re.sub(rf"(?<!\d)null;{omx};{omy};", f"null;{nmx};{nmy};", c)
        self.cmds[p["idx"]] = c
        p["x"], p["y"] = nx, ny

    def _rewrite_stack(self, sid):
        s = self.stacks[sid]
        mx, my = self._to_map(s["x"], s["y"])
        tail = "".join(f";{m}" for m in s["members"])
        self.cmds[s["idx"]] = (f"+/{sid}/stack/{self.game.map_name};"
                               f"{mx};{my}{tail}\\")

    def _detach(self, pid):
        sid = self.member_of.pop(pid, None)
        if sid:
            self.stacks[sid]["members"].remove(pid)
            self._rewrite_stack(sid)

    def _attach(self, pid, nx, ny):
        sid = self.stack_at(nx, ny)
        if sid is None:
            sid = self._fresh_id()
            self.stacks[sid] = dict(idx=None, x=nx, y=ny, members=[])
            # insert the new stack command right before end_save
            insert_at = len(self.cmds) - 1
            while insert_at > 0 and "end_save" not in self.cmds[insert_at]:
                insert_at -= 1
            self.cmds.insert(insert_at, "")
            # command indexes after the insertion point shift by one
            for coll in (self.pieces, self.stacks):
                for o in coll.values():
                    if o["idx"] is not None and o["idx"] >= insert_at:
                        o["idx"] += 1
            self.stacks[sid]["idx"] = insert_at
        self.stacks[sid]["members"].append(pid)
        self.member_of[pid] = sid
        self._rewrite_stack(sid)

    def _dest_xy(self, dest):
        """Resolve dest to pixel (x,y). Accepts (x,y), hexnum, or region loc id.

        Fail-closed: unknown region ids raise ValueError (no mutation).
        """
        if isinstance(dest, tuple):
            return dest
        if getattr(self.game, "space_kind", "hex") == "region":
            if dest not in self.game.regions.locations:
                raise ValueError(f"unknown region {dest!r}")
            return self.game.loc_to_pixel(dest)
        return self.game.grid.hexnum_to_pixel(dest)

    def _loc_label(self, x, y):
        if getattr(self.game, "space_kind", "hex") == "region":
            return self.game.pixel_to_loc(x, y)
        return self.game.grid.pixel_to_hex(x, y)[2]

    def _stacks_snapped_to(self, loc_id):
        """VASSAL stack ids whose members nearest-snap to region `loc_id`."""
        hits = []
        for s_id, s in self.stacks.items():
            if not s["members"]:
                continue
            for pid in s["members"]:
                p = self.pieces.get(pid)
                if p and self._loc_label(p["x"], p["y"]) == loc_id:
                    hits.append(s_id)
                    break
        return hits

    def move_piece_by_id(self, pid, dest):
        """Move ONE piece by its id (names may collide across sides — Tobruk '1/1')."""
        if pid not in self.pieces:
            raise ValueError(f"unknown piece id {pid!r}")
        p = self.pieces[pid]
        nx, ny = self._dest_xy(dest)  # validate dest before mutating
        old = self._loc_label(p["x"], p["y"])
        self._detach(pid)
        self._set_piece_xy(pid, nx, ny)
        self._attach(pid, nx, ny)
        return f"{p['name']}: {old} -> {self._loc_label(nx, ny)}"

    def move_piece(self, name_fragment, dest):
        """Move ONE piece (splitting its stack if shared) to dest hex/loc or (x,y)."""
        pid, p = self.find(name_fragment)
        nx, ny = self._dest_xy(dest)  # validate dest before mutating
        old = self._loc_label(p["x"], p["y"])
        self._detach(pid)
        self._set_piece_xy(pid, nx, ny)
        self._attach(pid, nx, ny)
        return f"{p['name']}: {old} -> {self._loc_label(nx, ny)}"

    def move_stack(self, hex_from, hex_to):
        """Move an entire stack (all members) between hexes/region locs.

        Region space: `hex_from` is a location id. Exactly one VASSAL stack must
        nearest-snap to that loc — zero → error, two or more → ambiguous error
        (never pick arbitrarily). Prefer move_stack_containing(pid, dest) when
        a piece is already selected.
        """
        if getattr(self.game, "space_kind", "hex") == "region":
            matches = self._stacks_snapped_to(hex_from)
            if not matches:
                raise ValueError(f"no stack at {hex_from}")
            if len(matches) > 1:
                raise ValueError(
                    f"ambiguous stack at {hex_from}: {len(matches)} VASSAL stacks "
                    f"snap here {matches}; use move_stack_containing(pid, dest)")
            sid = matches[0]
        else:
            fx, fy = self._dest_xy(hex_from)
            sid = self.stack_at(fx, fy)
            if sid is None:
                raise ValueError(f"no stack at {hex_from}")
        return self._move_stack_id(sid, hex_to, label_from=hex_from)

    def move_stack_containing(self, pid, dest):
        """Move the VASSAL stack that currently contains `pid` (by member_of)."""
        if pid not in self.pieces:
            raise ValueError(f"unknown piece id {pid!r}")
        sid = self.member_of.get(pid)
        if sid is None:
            return self.move_piece_by_id(pid, dest)
        if sid not in self.stacks or not self.stacks[sid]["members"]:
            raise ValueError(f"piece {pid} has stale stack membership {sid!r}")
        p = self.pieces[pid]
        label_from = self._loc_label(p["x"], p["y"])
        return self._move_stack_id(sid, dest, label_from=label_from)

    def _move_stack_id(self, sid, dest, label_from=None):
        if sid not in self.stacks:
            raise ValueError(f"unknown stack id {sid!r}")
        nx, ny = self._dest_xy(dest)  # validate dest before mutating
        s = self.stacks[sid]
        members = list(s["members"])
        if not members:
            raise ValueError(f"stack {sid} has no members")
        for pid in members:
            self._set_piece_xy(pid, nx, ny)
        s["x"], s["y"] = nx, ny
        self._rewrite_stack(sid)
        names = [self.pieces[m]["name"] for m in s["members"]]
        return f"stack {label_from or sid} -> {dest}: {names}"

    def write(self, out_path):
        vsav.write_vsav(out_path, ESC.join(self.cmds), self.moduledata, self.savedata,
                        key=self.game.save_key)


# ---------------------------------------------------------------- CLI
def _dump(b):
    units = b.units()
    from collections import defaultdict
    byhex = defaultdict(list)
    for u in units:
        byhex[u["hexnum"]].append(u)
    print(f"{len(units)} counters in {len(byhex)} hexes:")
    for h in sorted(byhex):
        us = byhex[h]
        tag = f"  [STACK x{len(us)}]" if len(us) > 1 else ""
        print(f"  {h}: " + ", ".join(f"{u['name']}({u['side']})" for u in us) + tag)


if __name__ == "__main__":
    args = sys.argv[1:]
    game_dir = gamespec.default_game_dir()
    if args and args[0] == "--game":
        game_dir = args[1]; args = args[2:]
    game = gamespec.Game(game_dir)
    cmd, save = args[0], args[1]
    b = Board(save, game)
    if cmd == "dump":
        _dump(b)
    elif cmd == "move":
        out = args[2]
        for spec in args[3:]:
            unit, dest = spec.rsplit("=", 1)
            print(" ", b.move_piece(unit, dest))
        b.write(out)
        print(f"wrote {out}")
    elif cmd == "movestack":
        # hex: movestack out.vsav FROM_HEX TO_HEX
        # region: movestack out.vsav --pid PIECE_ID TO_LOC  (loc-from is ambiguous)
        out = args[2]
        if args[3] == "--pid":
            print(" ", b.move_stack_containing(args[4], args[5]))
        else:
            print(" ", b.move_stack(args[3], args[4]))
        b.write(out)
        print(f"wrote {out}")
