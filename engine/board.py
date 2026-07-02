"""
board.py - Full-fidelity VASSAL save model for Arnhem (v2 of the mover in arnhem.py).

Understands the real save structure (cracked 2026-07-01):
  - piece commands:  +/<pieceId>/mark|immob;...piece;;;<img>.png;...;Map0;1;<x>,<y>...[Main Map;<x>;<y>;<n>]
  - stack commands:  +/<stackId>/stack/Main Map;<x>;<y>;<memberId>[;<memberId>...]
  - 66 empty stack shells + 42 immob markers (DZ/turn track) exist; left untouched.

Capabilities the old mover lacked:
  - move ANY number of counters in one batch
  - move a piece that shares a stack (auto-split), or a whole stack at once
  - auto-join: moving onto an occupied hex appends to that hex's stack
  - identity-based editing (piece IDs), no blind string replacement across the file

Usage:
  python board.py dump  <save.vsav>
  python board.py move  <save.vsav> <out.vsav> "<unit>=<hex>" ["<unit>=<hex>" ...]
  python board.py movestack <save.vsav> <out.vsav> <hex_from> <hex_to>
"""
import re, sys
import arnhem  # codec + hex math (proven, unchanged)

PIECE_RE = re.compile(r"^\+/(\d+)/(mark|immob);")
STACK_RE = re.compile(r"^\+/(\d+)/stack/Main Map;(\d+);(\d+)((?:;\d+)*)\\*$")
IMG_RE   = re.compile(r"piece;;;([^;]+?)\.png;")
ESC = "\x1b"


class Board:
    def __init__(self, path):
        self.path = path
        plain, self.moduledata, self.savedata = arnhem.read_vsav(path)
        self.cmds = plain.split(ESC)
        self.pieces = {}   # id -> dict(name, idx, x, y)
        self.stacks = {}   # id -> dict(idx, x, y, members[list of piece ids])
        for i, c in enumerate(self.cmds):
            m = STACK_RE.match(c.rstrip())
            if m:
                members = [s for s in m.group(4).split(";") if s]
                self.stacks[m.group(1)] = dict(idx=i, x=int(m.group(2)), y=int(m.group(3)),
                                               members=members)
                continue
            m = PIECE_RE.match(c)
            if m:
                img = IMG_RE.search(c)
                # BasicPiece state = ".../Pieces\tfalse;<map>;1;x,y" — map is "Map0" for
                # units placed via stacks, EMPTY for singletons (Grsn, DZs, etc.)
                st = re.search(r"/Pieces\tfalse;[^;]*;1;(\d+),(\d+)", c)
                if img and st:
                    self.pieces[m.group(1)] = dict(name=img.group(1).strip(), kind=m.group(2),
                                                   idx=i, x=int(st.group(1)), y=int(st.group(2)))
        self.member_of = {}  # piece id -> stack id
        for sid, s in self.stacks.items():
            for pid in s["members"]:
                self.member_of[pid] = sid

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
        for pid, p in self.pieces.items():
            if p["kind"] != "mark":
                continue
            col, row, hexn = arnhem.pixel_to_hex(p["x"], p["y"])
            out.append(dict(id=pid, name=p["name"], side=arnhem.side(p["name"]),
                            x=p["x"], y=p["y"], col=col, row=row, hexnum=hexn))
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

    def _set_piece_xy(self, pid, nx, ny):
        p = self.pieces[pid]
        ox, oy = p["x"], p["y"]
        c = self.cmds[p["idx"]]
        # exact old coord pair, both encodings, digit-boundary guarded
        c = re.sub(rf"(?<!\d){ox},{oy}(?!\d)", f"{nx},{ny}", c)
        c = re.sub(rf"(?<!\d)Main Map;{ox};{oy};", f"Main Map;{nx};{ny};", c)
        self.cmds[p["idx"]] = c
        p["x"], p["y"] = nx, ny

    def _rewrite_stack(self, sid):
        s = self.stacks[sid]
        tail = "".join(f";{m}" for m in s["members"])
        self.cmds[s["idx"]] = f"+/{sid}/stack/Main Map;{s['x']};{s['y']}{tail}\\"

    def _detach(self, pid):
        sid = self.member_of.pop(pid, None)
        if sid:
            self.stacks[sid]["members"].remove(pid)
            self._rewrite_stack(sid)

    def _attach(self, pid, nx, ny):
        sid = self.stack_at(nx, ny)
        if sid is None:
            sid = self._fresh_id()
            src = self.stacks[self.member_of.get(pid, next(iter(self.stacks)))]
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

    def move_piece(self, name_fragment, dest):
        """Move ONE piece (splitting its stack if shared) to dest hex ('2010') or (x,y)."""
        pid, p = self.find(name_fragment)
        nx, ny = dest if isinstance(dest, tuple) else arnhem.hexnum_to_pixel(dest)
        old = arnhem.pixel_to_hex(p["x"], p["y"])[2]
        self._detach(pid)
        self._set_piece_xy(pid, nx, ny)
        self._attach(pid, nx, ny)
        return f"{p['name']}: {old} -> {arnhem.pixel_to_hex(nx, ny)[2]}"

    def move_stack(self, hex_from, hex_to):
        """Move an entire stack (all members) between hexes."""
        fx, fy = arnhem.hexnum_to_pixel(hex_from)
        sid = self.stack_at(fx, fy)
        if sid is None:
            raise ValueError(f"no stack at hex {hex_from}")
        nx, ny = arnhem.hexnum_to_pixel(hex_to)
        s = self.stacks[sid]
        for pid in list(s["members"]):
            self._set_piece_xy(pid, nx, ny)
        s["x"], s["y"] = nx, ny
        self._rewrite_stack(sid)
        names = [self.pieces[m]["name"] for m in s["members"]]
        return f"stack {hex_from} -> {hex_to}: {names}"

    def write(self, out_path):
        arnhem.write_vsav(out_path, ESC.join(self.cmds), self.moduledata, self.savedata)


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
    cmd, save = sys.argv[1], sys.argv[2]
    b = Board(save)
    if cmd == "dump":
        _dump(b)
    elif cmd == "move":
        out = sys.argv[3]
        for spec in sys.argv[4:]:
            unit, dest = spec.rsplit("=", 1)
            print(" ", b.move_piece(unit, dest))
        b.write(out)
        print(f"wrote {out}")
    elif cmd == "movestack":
        out, hf, ht = sys.argv[3], sys.argv[4], sys.argv[5]
        print(" ", b.move_stack(hf, ht))
        b.write(out)
        print(f"wrote {out}")
