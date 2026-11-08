import hashlib, io, json, os, re, shutil, stat, struct, sys, tempfile, threading, zipfile, zlib
from pathlib import Path

ROOT = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
MANIFESTS = ROOT / "web" / "manifests"
GAMES = ROOT / "games"
SETUP_GAMES = {"tobruk", "blue-and-gray-chickamauga", "westwall-arnhem", "napoleon-at-waterloo"}
LOCK = threading.RLock()
IMAGES = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".svg"}


def _manifest(slug):
    if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        raise ValueError("Invalid game slug")
    with (Path(MANIFESTS) / (slug + ".json")).open(encoding="utf-8") as f:
        m = json.load(f)
    reqs = m["requirements"]
    if not reqs or len({r["id"] for r in reqs}) != len(reqs):
        raise ValueError("Invalid module requirements")
    for r in reqs:
        if not re.fullmatch(r"[0-9a-f]{64}", r["sha256"]) or not isinstance(r["size"], int) or r["size"] <= 0:
            raise ValueError("Invalid module fingerprint")
    return m


def _root():
    return Path(os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))) / "TheVassal" / "byo"


def _name(name):
    if not isinstance(name, str) or not name or "\\" in name:
        raise ValueError(f"Unsafe module path: {name!r}")
    parts = name.split("/")
    for part in parts:
        if (not part or part in (".", "..") or part[-1] in " ." or
                any(ord(c) < 32 or c in ':<>"|?*' for c in part) or
                re.fullmatch(r"(?i:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", part)):
            raise ValueError(f"Unsafe module path: {name!r}")
    return name


def _path(root, name):
    path = root / _name(name)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Unsafe cache path: {name!r}")
    return path


def _setup(slug, m, req):
    if req != m.get("assets", {}).get("counters", {}).get("req"):
        return None
    gdir = Path(GAMES) / slug
    path = gdir / "setup_units.json"
    if not path.is_file() and slug not in SETUP_GAMES:
        return None
    raw = path.read_bytes()
    scenario = json.loads(raw)
    units = scenario.get("units", [])
    if set(scenario) != {"units"} or not units or any(
            set(u) != {"id", "gpid", "xy"} or
            any(not isinstance(u[k], str) or not re.fullmatch(r"[0-9]+", u[k]) for k in ("id", "gpid")) or
            not isinstance(u["xy"], list) or len(u["xy"]) != 2 or any(type(v) is not int for v in u["xy"])
            for u in units) or len({u["id"] for u in units}) != len(units):
        raise ValueError("Invalid numeric setup units")
    spec = json.loads((gdir / "game.json").read_text(encoding="utf-8"))
    name = _name(Path(spec["setup_save"]).name)
    if not name.lower().endswith(".vsav"):
        raise ValueError("Invalid generated setup filename")
    return dict(file=name, units_sha256=hashlib.sha256(raw).hexdigest(),
                map_name=spec.get("map_name", "Main Map"),
                board_name=spec.get("board_name", spec.get("map_name", "Main Map")),
                save_key=spec.get("save_key", "a3"))


def _layout(m, req, slug):
    assets = m.get("assets", {})
    board, counters = assets.get("map", {}), assets.get("counters", {})
    entries = {}
    if board.get("req") == req:
        entry = _name(board["entry"])
        entries[entry] = entry
    for ef in m.get("engine_files", []):
        if ef.get("req") == req and ef["fs_path"].lower().endswith(".vsav"):
            entries[_name(ef["entry"])] = _name(ef["fs_path"])
    prefix = counters["prefix"] if counters.get("req") == req else None
    if prefix is not None:
        prefix = _name(prefix.rstrip("/")) + "/"
    skip = set()
    cover = assets.get("cover", {})
    if cover.get("req") == req:
        skip.add(cover["entry"])
    for doc in m.get("docs", []):
        if doc.get("req") == req:
            skip.update(doc.get("entries", []))
    return dict(entries=entries, prefix=prefix, skip=sorted(n for n in skip - entries.keys()
                if prefix and n.startswith(prefix) and Path(n).suffix.lower() in IMAGES), setup=_setup(slug, m, req))


def _cached(m, r, slug):
    try:
        root = _root()
        dest = _path(root, r["sha256"])
        with _path(root, r["sha256"] + ".json").open(encoding="utf-8") as f:
            record = json.load(f)
        if not isinstance(record, dict) or record.get("sha256") != r["sha256"] or record.get("size") != r["size"] or record.get("layout") != _layout(m, r["id"], slug):
            return False
        files = record["files"]
        required = set(record["layout"]["entries"].values())
        if record["layout"]["setup"]:
            required.add(record["layout"]["setup"]["file"])
        if not isinstance(files, dict) or not files or not required <= files.keys():
            return False
        if record["layout"]["prefix"] and not any(n.startswith(record["layout"]["prefix"]) for n in files):
            return False
        return all(_path(dest, n).is_file() and _path(dest, n).stat().st_size == size for n, size in files.items())
    except (OSError, ValueError, KeyError, TypeError):
        return False


def status(slug):
    try:
        m = _manifest(slug)
        with LOCK:
            reqs = []
            for r in m["requirements"]:
                have = _cached(m, r, slug)
                reqs.append(dict(r, have=have, missing=not have, hash_ok=have))
        return dict(slug=slug, ready=all(r["have"] for r in reqs), requirements=reqs)
    except (OSError, ValueError, KeyError, TypeError) as e:
        return dict(slug=slug, ready=False, requirements=[], error=str(e))


def _regenerate(slug, setup, z, stage):
    sys.path.insert(0, str(ROOT / "engine"))
    import gamespec, make_save

    game = gamespec.Game(str(Path(GAMES) / slug))
    names = z.namelist()
    preferred = Path(game.spec["buildfile"]).name
    buildfile = next((n for n in dict.fromkeys((preferred, "buildFile", "buildFile.xml"))
                      if n in ("buildFile", "buildFile.xml") and n in names), None)
    if buildfile is None or "moduledata" not in names:
        raise ValueError("Module is missing buildFile/buildFile.xml or moduledata for setup generation")
    paths = []
    try:
        for key, name in (("buildfile", buildfile), ("moduledata", "moduledata")):
            info = z.getinfo(name)
            target = _path(stage, name)
            if names.count(name) != 1 or stat.S_ISLNK(info.external_attr >> 16) or target.exists():
                raise ValueError(f"Unsafe or conflicting setup input: {name}")
            paths.append(target)
            with z.open(info) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            game.spec[key] = str(target)
        raw = (Path(GAMES) / slug / "setup_units.json").read_bytes()
        if hashlib.sha256(raw).hexdigest() != setup["units_sha256"]:
            raise ValueError("Setup units changed during import")
        target = _path(stage, setup["file"])
        if target.exists():
            raise ValueError("Generated setup conflicts with a mapped asset")
        make_save.build(game, json.loads(raw), str(target))
    finally:
        for path in paths:
            path.unlink(missing_ok=True)


def import_module(slug, source):
    m = None
    try:
        m = _manifest(slug)
        with io.BytesIO(source) if isinstance(source, (bytes, bytearray)) else open(source, "rb") as f:
            digest = hashlib.file_digest(f, "sha256").hexdigest()
            size = f.seek(0, 2)
            r = next((r for r in m["requirements"] if r["sha256"] == digest and r["size"] == size), None)
            if r is None:
                raise ValueError("That is not the exact module this game requires.")
            with LOCK:
                if _cached(m, r, slug):
                    return dict(status(slug), ok=True, cached=True)
                layout = _layout(m, r["id"], slug)
                f.seek(0)
                with zipfile.ZipFile(f) as z:
                    selected, names = {}, set()
                    for info in z.infolist():
                        name = info.filename
                        if info.is_dir():
                            continue
                        counter = layout["prefix"] and name.startswith(layout["prefix"]) and Path(name).suffix.lower() in IMAGES and name not in layout["skip"]
                        if name not in layout["entries"] and not counter:
                            continue
                        _name(name)
                        out = layout["entries"].get(name, name)
                        if stat.S_ISLNK(info.external_attr >> 16) or out.casefold() in names:
                            raise ValueError(f"Unsafe or duplicate module entry: {name!r}")
                        names.add(out.casefold())
                        selected[out] = info
                    if not set(layout["entries"]) <= {i.filename for i in selected.values()}:
                        raise ValueError("A required map or setup entry is missing from the module")
                    if layout["prefix"] and not any(n.startswith(layout["prefix"]) for n in selected):
                        raise ValueError("No counter images found in the module")
                    if not selected:
                        raise ValueError("No mapped assets found in the module")
                    root = _root()
                    dest = _path(root, digest)
                    receipt = _path(root, digest + ".json")
                    root.mkdir(parents=True, exist_ok=True)
                    with tempfile.TemporaryDirectory(prefix=".import-", dir=root) as work:
                        stage = Path(work) / "assets"
                        stage.mkdir()
                        for out, info in selected.items():
                            target = _path(stage, out)
                            target.parent.mkdir(parents=True, exist_ok=True)
                            with z.open(info) as src, target.open("wb") as dst:
                                shutil.copyfileobj(src, dst)
                        files = {n: i.file_size for n, i in selected.items()}
                        if layout["setup"]:
                            _regenerate(slug, layout["setup"], z, stage)
                            name = layout["setup"]["file"]
                            files[name] = _path(stage, name).stat().st_size
                        record = dict(sha256=digest, size=size, layout=layout, files=files)
                        pending = Path(work) / "receipt.json"
                        pending.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
                        if dest.exists():
                            if dest.is_symlink() or dest.is_junction():
                                raise ValueError("Unsafe cache directory")
                            shutil.rmtree(dest)
                        os.replace(stage, dest)
                        os.replace(pending, receipt)
                return dict(status(slug), ok=True, cached=False)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, zipfile.BadZipFile, zlib.error, EOFError) as e:
        hint = " ".join(r.get("hint", "") for r in m["requirements"]) if m else ""
        return dict(slug=slug, ok=False, error=(str(e) + " " + hint).strip(), hint=hint)


def resolve(game):
    if not _root().is_dir():
        return game
    slug = Path(game.dir).name
    try:
        m = _manifest(slug)
    except (FileNotFoundError, ValueError):
        return game
    with LOCK:
        roots = {r["id"]: _path(_root(), r["sha256"]) for r in m["requirements"] if _cached(m, r, slug)}
        for key, field, directory in (("map", "entry", False), ("counters", "prefix", True)):
            a = m.get("assets", {}).get(key, {})
            if a.get("req") in roots:
                path = _path(roots[a["req"]], a[field].rstrip("/"))
                if path.is_dir() if directory else path.is_file():
                    game.assets["counters_dir" if directory else "map"] = str(path)
        if not game.setup_save or not os.path.isfile(game.setup_save):
            for ef in m.get("engine_files", []):
                if ef.get("req") in roots and ef["fs_path"].lower().endswith(".vsav"):
                    path = _path(roots[ef["req"]], ef["fs_path"])
                    if path.is_file():
                        game.setup_save = str(path)
                        break
        if not game.setup_save or not os.path.isfile(game.setup_save):
            for req, root in roots.items():
                setup = _setup(slug, m, req)
                if setup:
                    game.setup_save = str(_path(root, setup["file"]))
                    break
    return game


def png_size(path):
    if not path or not os.path.isfile(path):
        return 0, 0
    with open(path, "rb") as f:
        head = f.read(26)
        if head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR" and len(head) >= 24:
            return struct.unpack(">II", head[16:24])
        if head[:6] in (b"GIF87a", b"GIF89a") and len(head) >= 10:
            return struct.unpack("<HH", head[6:10])
        if head[:2] == b"BM" and len(head) >= 26:
            dib, = struct.unpack("<I", head[14:18])
            if dib == 12:
                return struct.unpack("<HH", head[18:22])
            if dib >= 40:
                w, h = struct.unpack("<ii", head[18:26])
                return abs(w), abs(h)
        if head[:2] == b"\xff\xd8":
            f.seek(2)
            while f.read(1) == b"\xff":
                marker = f.read(1)
                while marker == b"\xff":
                    marker = f.read(1)
                if not marker or marker[0] in (0xDA, 0xD9):
                    break
                if marker[0] in (0x01, *range(0xD0, 0xD9)):
                    continue
                raw = f.read(2)
                if len(raw) != 2:
                    break
                size, = struct.unpack(">H", raw)
                if size < 2:
                    break
                if marker[0] in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    data = f.read(5)
                    if size >= 7 and len(data) == 5:
                        h, w = struct.unpack(">HH", data[1:])
                        return w, h
                    break
                f.seek(size - 2, 1)
    raise ValueError(f"Unsupported or truncated map image: {path}")


def _self_check():
    import copy, importlib.util, subprocess, types, urllib.request
    from unittest.mock import patch

    global MANIFESTS, GAMES
    original_manifest, original_games, original_env = MANIFESTS, GAMES, os.environ.get("LOCALAPPDATA")
    had_live = (ROOT / "live").exists()
    try:
        with tempfile.TemporaryDirectory(prefix=".byo-check-", dir=ROOT) as td:
            tmp = Path(td)
            os.environ["LOCALAPPDATA"] = str(tmp / "local")
            MANIFESTS = tmp / "manifests"
            MANIFESTS.mkdir()
            GAMES = tmp / "games"
            png = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 37, 23)

            def archive(entries):
                b = io.BytesIO()
                with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
                    for n, data in entries:
                        z.writestr(n, data)
                return b.getvalue()

            def manifest(slug, data, changes=None):
                m = dict(requirements=[dict(id="module", filename="Exact module.vmod", size=len(data),
                         sha256=hashlib.sha256(data).hexdigest(), page="https://example.invalid/library",
                         hint="Use the exact fixture version.")],
                         assets=dict(map=dict(req="module", entry="images/map.png"),
                                     counters=dict(req="module", prefix="images/", all=True),
                                     cover=dict(req="module", entry="images/cover.png")),
                         engine_files=[dict(req="module", entry="Start.vsav", fs_path="setup_from_module.vsav")],
                         docs=[dict(req="module", entries=["images/rules.png", "rules.pdf"])])
                if changes:
                    changes(m)
                (MANIFESTS / (slug + ".json")).write_text(json.dumps(m), encoding="utf-8")
                return m

            def snapshot():
                return {str(p.relative_to(_root())): (p.stat().st_size, p.stat().st_mtime_ns)
                        for p in _root().rglob("*") if p.is_file()}

            entries = [("images/map.png", png), ("images/unit.png", png), ("images/sub/unit.gif", b"counter"),
                       ("Start.vsav", b"synthetic setup"), ("buildFile", b"not an asset"),
                       ("images/readme.txt", b"not an image"), ("images/cover.png", png),
                       ("images/rules.png", png), ("rules.pdf", b"not a counter"),
                       ("unselected/extra.png", png), ("../outside.txt", b"ignored")]
            data = archive(entries)
            m = manifest("fixture", data)
            assert "server" not in sys.modules
            assert not status("fixture")["ready"] and not _root().exists()
            custom = types.SimpleNamespace(dir=str(tmp / "Custom_dev_game"), assets={}, setup_save=None)
            assert resolve(custom) is custom and vars(custom) == dict(dir=str(tmp / "Custom_dev_game"), assets={}, setup_save=None)
            bad = data[:-1] + bytes([data[-1] ^ 1])
            result = import_module("fixture", bad)
            assert not result["ok"] and m["requirements"][0]["hint"] in result["error"]
            assert not _root().exists()
            print("b. Wrong SHA rejected with manifest hint; no cache created: PASS")

            game = types.SimpleNamespace(dir=str(tmp / "games" / "fixture"),
                                         assets={"map": "dev/map.png", "counters_dir": "dev/counters"},
                                         setup_save="dev/setup.vsav")
            before = copy.deepcopy(vars(game))
            assert resolve(game) is game and vars(game) == before
            result = import_module("fixture", data)
            assert result["ok"] and result["ready"] and not result["cached"], result
            assert resolve(custom) is custom and custom.assets == {} and custom.setup_save is None
            dest = _root() / m["requirements"][0]["sha256"]
            expected = {"images/map.png", "images/unit.png", "images/sub/unit.gif", "setup_from_module.vsav"}
            assert {p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file()} == expected
            assert (dest / "setup_from_module.vsav").read_bytes() == b"synthetic setup"
            assert not (tmp / "outside.txt").exists()
            print("a. Correct bytes import extracts only mapped map/counter/setup assets: PASS")

            saved = snapshot()
            module_path = tmp / "fixture.vmod"
            module_path.write_bytes(data)
            with patch.object(zipfile, "ZipFile", side_effect=AssertionError("cache reopened ZIP")):
                assert status("fixture")["ready"]
                assert all(r["have"] and r["hash_ok"] and not r["missing"] for r in status("fixture")["requirements"])
                assert import_module("fixture", module_path)["cached"]
            assert snapshot() == saved
            assert not import_module("fixture", bad)["ok"] and snapshot() == saved
            print("d. Cached status/path import never reopen ZIP or rewrite files: PASS")

            assert resolve(game) is game
            assert game.assets["map"] == str(dest / "images/map.png")
            assert game.assets["counters_dir"] == str(dest / "images")
            assert game.setup_save == str(dest / "setup_from_module.vsav")
            dev_setup = tmp / "dev.vsav"
            dev_setup.write_bytes(b"existing setup")
            game.setup_save = str(dev_setup)
            resolve(game)
            assert game.setup_save == str(dev_setup)
            print("e. Resolution prefers cached assets, fills missing setup, preserves dev fallback: PASS")

            unsafe = ["images/../escaped.png", "images/..\\escaped.png", "images/C:/escaped.png",
                      "images/NUL.png", "/escaped.png", "C:/escaped.png", "//host/share/escaped.png"]
            for i, name in enumerate(unsafe):
                malicious = archive(entries + [(name, png)])
                def unsafe_map(mm):
                    mm["assets"]["map"]["entry"] = name
                manifest(f"unsafe-{i}", malicious, None if name.startswith("images/") else unsafe_map)
                result = import_module(f"unsafe-{i}", malicious)
                assert not result["ok"] and "Unsafe" in result["error"], result
                assert snapshot() == saved
            link = zipfile.ZipInfo("images/link.png")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            malicious = archive(entries + [(link, b"../../escaped.png")])
            manifest("unsafe-link", malicious)
            assert not import_module("unsafe-link", malicious)["ok"]
            assert snapshot() == saved and not (tmp / "escaped.png").exists()
            assert not list(_root().glob(".import-*"))
            print("c. Traversal, absolute/drive/UNC paths and symlink members rejected without writes: PASS")

            (dest / "images/unit.png").unlink()
            assert not status("fixture")["ready"]
            assert import_module("fixture", module_path)["ready"]
            (_root() / (m["requirements"][0]["sha256"] + ".json")).write_text("[]", encoding="utf-8")
            assert not status("fixture")["ready"]
            assert import_module("fixture", module_path)["ready"]
            saved = snapshot()
            corrupt = io.BytesIO()
            with zipfile.ZipFile(corrupt, "w", zipfile.ZIP_STORED) as z:
                for name, contents in entries:
                    z.writestr(name, contents)
            broken = bytearray(corrupt.getvalue())
            broken[30 + len("images/map.png")] ^= 1
            manifest("broken-crc", broken)
            result = import_module("broken-crc", broken)
            assert not result["ok"] and "CRC" in result["error"], result
            assert snapshot() == saved and not list(_root().glob(".import-*"))
            print("Missing files/invalid receipts require reimport; failed extraction leaves no partial cache: PASS")

            board_data = archive([("images/map.png", png)])
            counter_data = archive([("images/piece.png", png)])
            def split(mm):
                mm["requirements"].append(dict(mm["requirements"][0], id="pieces", filename="pieces.vmod",
                    size=len(counter_data), sha256=hashlib.sha256(counter_data).hexdigest()))
                mm["assets"]["counters"]["req"] = "pieces"
                mm["engine_files"] = []
            multi = manifest("two-files", board_data, split)
            assert not import_module("two-files", board_data)["ready"]
            partial = status("two-files")
            assert [r["have"] for r in partial["requirements"]] == [True, False]
            mixed = types.SimpleNamespace(dir=str(tmp / "games/two-files"),
                                          assets=dict(before["assets"]), setup_save=before["setup_save"])
            resolve(mixed)
            assert mixed.assets["map"] == str(_root() / multi["requirements"][0]["sha256"] / "images/map.png")
            assert mixed.assets["counters_dir"] == before["assets"]["counters_dir"]
            assert import_module("two-files", counter_data)["ready"]
            resolve(mixed)
            assert mixed.assets["counters_dir"] == str(_root() / multi["requirements"][1]["sha256"] / "images")
            assert mixed.setup_save == before["setup_save"]
            print("Multiple module requirements track partial imports and resolve independently: PASS")

            units = [dict(id="2002", gpid="8", xy=[7, 11]), dict(id="1001", gpid="7", xy=[7, 11]),
                     dict(id="2003", gpid="8", xy=[12, 20])]
            bodies = {gp: f"+/null/mark;piece;;;unit.png;Unit/\tnull;0;0;{gp};0" for gp in ("7", "8")}
            xml = "<module>" + "".join(f'<VASSAL.build.widget.PieceSlot entryName="Unit {gp}" gpid="{gp}">{body}</VASSAL.build.widget.PieceSlot>'
                                       for gp, body in bodies.items()) + "</module>"
            setup_spec = dict(name="Synthetic setup", map_name="Main Map", board_name="Board", save_key="4e",
                              grid=dict(dx=1, dy=1, x0=0, y0=0), sides=dict(order=["a", "b"], default="a"),
                              assets=dict(map="dev/map.png", counters_dir="dev/counters"),
                              setup_save="setup.vsav", buildfile="dev/buildFile.xml", moduledata="dev/moduledata")
            expected = ["begin_save"] + [bodies[u["gpid"]].replace("+/null/", "+/" + u["id"] + "/", 1)
                .replace("null;0;0;", f'Main Map;{u["xy"][0]};{u["xy"][1]};', 1) for u in units]
            expected += ["+/1000000000004/stack/Main Map;7;11;2002;1001\\",
                         "+/1000000000005/stack/Main Map;12;20;2003\\", "Main MapBoardPicker\tBoard\t0\t0", "end_save"]
            for i, buildfile in enumerate(("buildFile", "buildFile.xml")):
                slug = f"generated-{i}"
                gdir = GAMES / slug
                gdir.mkdir(parents=True)
                setup_spec["buildfile"] = "dev/" + ("buildFile.xml" if i == 0 else "buildFile")
                spec_raw = json.dumps(setup_spec).encode()
                (gdir / "game.json").write_bytes(spec_raw)
                (gdir / "setup_units.json").write_bytes(json.dumps(dict(units=units)).encode())
                generated_data = archive([("images/map.png", png), ("images/unit.png", png),
                                          (buildfile, xml.encode()), ("moduledata", b"<data/>")])
                generated_manifest = manifest(slug, generated_data, lambda mm: mm.update(engine_files=[]))
                result = import_module(slug, generated_data)
                assert result["ok"] and result["ready"], result
                assert "server" not in sys.modules
                import gamespec, vsav
                generated_dir = _root() / generated_manifest["requirements"][0]["sha256"]
                generated_save = generated_dir / "setup.vsav"
                assert vsav.read_vsav(generated_save)[:2] == ("\x1b".join(expected), b"<data/>")
                assert vsav.save_key(generated_save) == 0x4e
                assert {p.relative_to(generated_dir).as_posix() for p in generated_dir.rglob("*") if p.is_file()} == {
                    "images/map.png", "images/unit.png", "setup.vsav"}
                assert not list(_root().glob(".import-*"))
                assert (gdir / "game.json").read_bytes() == spec_raw
                generated_game = resolve(gamespec.Game(str(gdir)))
                assert generated_game.setup_save == str(generated_save)
                assert generated_game.spec["buildfile"] == setup_spec["buildfile"]
                saved = snapshot()
                with patch.object(sys.modules[__name__], "_regenerate", side_effect=AssertionError("cache regenerated setup")):
                    assert status(slug)["ready"] and import_module(slug, generated_data)["cached"]
                assert snapshot() == saved
                generated_save.unlink()
                assert not status(slug)["ready"]
                assert import_module(slug, generated_data)["ready"]
                assert vsav.read_vsav(generated_save)[0] == "\x1b".join(expected)
            bad_dir = GAMES / "generated-missing"
            bad_dir.mkdir()
            (bad_dir / "game.json").write_bytes(spec_raw)
            (bad_dir / "setup_units.json").write_bytes(json.dumps(dict(units=units)).encode())
            missing_data = archive([("images/map.png", png), ("images/unit.png", png), ("buildFile", xml.encode())])
            manifest("generated-missing", missing_data, lambda mm: mm.update(engine_files=[]))
            saved = snapshot()
            result = import_module("generated-missing", missing_data)
            assert not result["ok"] and "moduledata" in result["error"]
            assert snapshot() == saved and not list(_root().glob(".import-*"))
            print("h. Setup generation accepts buildFile/buildFile.xml, preserves IDs/order/XY, removes build inputs, caches/rebuilds atomically: PASS")

            images = {"map.png": png,
                      "map.jpg": b"\xff\xd8\xff\xe0\x00\x04ab\xff\xff\xc2\x00\x0b\x08" + struct.pack(">HH", 23, 37) + b"\x01\x01\x11\x00",
                      "map.bmp": b"BM" + b"\0" * 12 + struct.pack("<Iii", 40, 37, -23),
                      "map-core.bmp": b"BM" + b"\0" * 12 + struct.pack("<IHHHH", 12, 37, 23, 1, 24),
                      "map.gif": b"GIF89a" + struct.pack("<HH", 37, 23),
                      "map87.gif": b"GIF87a" + struct.pack("<HH", 37, 23)}
            for name, contents in images.items():
                p = tmp / name
                p.write_bytes(contents)
                assert png_size(p) == (37, 23), name
            assert png_size(None) == png_size(tmp / "absent.png") == (0, 0)
            truncated = tmp / "truncated.jpg"
            truncated.write_bytes(b"\xff\xd8\xff\xe0\x00")
            try:
                png_size(truncated)
                raise AssertionError("truncated JPEG accepted")
            except ValueError:
                pass
            print("f. PNG/JPEG/BMP/GIF header dimensions, BMP variants and malformed JPEG: PASS")

            cmd = [sys.executable, "-c", "import sys;sys.path[:0]=['ui','engine'];import server"]
            proc = subprocess.run(cmd, cwd=ROOT, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                                  text=True, capture_output=True)
            assert proc.returncode == 0, proc.stdout + proc.stderr
            print('g. python -c "import sys;sys.path[:0]=[\'ui\',\'engine\'];import server": PASS (exit 0)')
            if proc.stdout or proc.stderr:
                print(proc.stdout + proc.stderr, end="")

            sys.path[:0] = [str(ROOT / "ui"), str(ROOT / "engine")]
            import server
            assert len(server.RELEASE_GAMES) == 7
            assert {"siege-of-jerusalem-ah", "napoleon-at-waterloo"} <= set(server.RELEASE_GAMES)
            assert server.png_size(tmp / "map.bmp") == (37, 23)
            menu_data = server.api_games()
            assert len(menu_data["games"]) == 7 and not any(g.get("error") for g in menu_data["games"])
            for item in menu_data["games"]:
                assert item["byo"]["requirements"] and not item["byo"].get("error"), item
                if not item["ready"]:
                    blocked = server.api_load_game(dict(slug=item["slug"]))
                    assert "Needs your module" in blocked["error"]
                    assert server.GAME_OBJ is None
            frozen_code = ("import sys,os;sys.frozen=True;sys._MEIPASS=os.getcwd();"
                           "sys.path[:0]=['ui','engine'];import server;"
                           "assert server.byo.MANIFESTS==os.path.join(sys._MEIPASS,'web','manifests');"
                           "assert server.LIVE==os.path.join(os.environ['LOCALAPPDATA'],'TheVassal','live')")
            proc = subprocess.run([sys.executable, "-c", frozen_code], cwd=ROOT,
                                  env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"), text=True, capture_output=True)
            assert proc.returncode == 0, proc.stdout + proc.stderr
            print("Seven menu manifests, pre-import load gate and frozen manifest/live roots: PASS")
            server.byo.MANIFESTS = MANIFESTS
            server.byo.GAMES = GAMES
            server.LIVE = str(tmp / "live")
            server.GAME_OBJ = types.SimpleNamespace(assets={"map": str(tmp / "map.png"), "counters_dir": str(dest / "images")})
            with server.make_server(0) as httpd:
                thread = threading.Thread(target=httpd.serve_forever, daemon=True)
                thread.start()
                base = "http://127.0.0.1:" + str(httpd.server_port)
                def request(path, body=None, ctype="application/json"):
                    req = urllib.request.Request(base + path, data=body, headers={"Content-Type": ctype})
                    with urllib.request.urlopen(req, timeout=10) as response:
                        return json.load(response)
                try:
                    assert request("/api/byo/fixture")["ready"]
                    assert request("/api/byo/fixture", json.dumps(dict(path=str(module_path))).encode())["cached"]
                    os.environ["LOCALAPPDATA"] = str(tmp / "http-local")
                    assert not request("/api/byo/fixture")["ready"]
                    result = request("/api/byo/fixture", bad, "application/octet-stream")
                    assert not result["ok"] and m["requirements"][0]["hint"] in result["error"]
                    assert not _root().exists()
                    assert request("/api/byo/fixture", data, "application/octet-stream")["ready"]
                    assert request("/api/byo/fixture", b"{bad json")["error"]
                    assert request("/api/load_game", b'{"slug":"../escape"}')["error"]
                    try:
                        urllib.request.urlopen(base + "/gasset/counters/../setup_from_module.vsav", timeout=10)
                        raise AssertionError("counter route escaped its directory")
                    except urllib.error.HTTPError as e:
                        assert e.code == 403
                    for ext, mime in (("png", "image/png"), ("jpg", "image/jpeg"), ("bmp", "image/bmp"), ("gif", "image/gif")):
                        server.GAME_OBJ.assets["map"] = str(tmp / ("map." + ext))
                        with urllib.request.urlopen(base + "/gasset/map", timeout=10) as response:
                            assert response.headers.get_content_type() == mime
                            assert response.read() == images["map." + ext]
                    with urllib.request.urlopen(base + "/menu", timeout=10) as response:
                        menu = response.read().decode()
                        assert "Needs your module" in menu and 'type="file"' in menu and '<img' not in menu
                finally:
                    httpd.shutdown()
                    thread.join(timeout=5)
            print("HTTP status, path/bytes import, error handling, map MIME types and text-only menu: PASS")

            fake_webview = types.ModuleType("webview")
            calls = []
            fake_webview.FileDialog = types.SimpleNamespace(OPEN=10)
            fake_webview.windows = [types.SimpleNamespace(create_file_dialog=lambda *a, **kw: (str(module_path),))]
            spec = importlib.util.spec_from_file_location("byo_app_check", ROOT / "app.py")
            app = importlib.util.module_from_spec(spec)
            with patch.dict(sys.modules, webview=fake_webview):
                spec.loader.exec_module(app)
            assert app.Api().choose_module() == str(module_path)
            fake_webview.windows[0].create_file_dialog = lambda *a, **kw: None
            assert app.Api().choose_module() is None
            fake_webview.create_window = lambda *a, **kw: calls.append(kw)
            fake_webview.start = lambda: None
            fake_httpd = types.SimpleNamespace(serve_forever=lambda: None, shutdown=lambda: None)
            with patch.object(server, "make_server", return_value=fake_httpd), patch.object(server, "load_game", side_effect=AssertionError("startup loaded game")), patch.object(sys, "argv", ["app.py", "12345"]):
                with patch("builtins.print"):
                    app.main()
            assert len(calls) == 1 and isinstance(calls[0]["js_api"], app.Api)
            print("Native picker path/cancel and first-run launcher without a module (webview stub): PASS")
    finally:
        MANIFESTS = original_manifest
        GAMES = original_games
        if original_env is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = original_env
        if not had_live and (ROOT / "live").exists():
            (ROOT / "live").rmdir()
    assert not Path(td).exists()
    print("PASS: native BYO self-check; temporary files removed")


if __name__ == "__main__":
    _self_check()
