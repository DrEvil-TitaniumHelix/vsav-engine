import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEM = os.path.join(os.path.expanduser("~"), ".claude", "projects",
                   "C--VassalArnhem", "memory")
NOTES = os.path.join(ROOT, "INTERNAL_NOTES.md")

SUBJECTS = {
    "Siege of Jerusalem": dict(
        topic="siege-of-jerusalem-encoding.md",
        game="siege-of-jerusalem-ah",
        code=["engine/soj.py", "ui/soj.html"],
        keys=[r"\bsoj\b", r"siege of jerusalem", r"\bjerusalem\b"]),
    "Napoleon at Waterloo": dict(
        topic="napoleon-at-waterloo-encoding.md",
        game="napoleon-at-waterloo",
        code=[],
        keys=[r"\bnaw\b", r"napoleon at waterloo", r"waterloo"]),
    "Afrika Korps": dict(
        topic="afrika-korps-encoding-status.md",
        game="afrika-korps-classic-ah",
        code=["engine/strategic.py", "engine/ai_strategic.py"],
        keys=[r"afrika korps", r"\bak\b"]),
    "Blue & Gray Chickamauga": dict(
        topic="blue-and-gray-chickamauga-overnight.md",
        game="blue-and-gray-chickamauga",
        code=["engine/bluegray.py", "engine/ai_bluegray.py"],
        keys=[r"chickamauga", r"blue *& *gray", r"blue and gray", r"b&g"]),
    "Westwall: Arnhem": dict(
        topic="westwall-arnhem-encoding.md",
        game="westwall-arnhem",
        code=["engine/westwall.py", "engine/ai_westwall.py"],
        keys=[r"westwall"]),
    "Austerlitz": dict(
        topic="austerlitz-napoleonic-families.md",
        game="austerlitz-gmt",
        code=["engine/napoleonic.py", "engine/ai_napoleonic.py"],
        keys=[r"austerlitz", r"napoleonic"]),
    "Arnhem (original)": dict(
        topic=None, game="arnhem",
        code=["engine/rules.py", "engine/gamestate.py"],
        keys=[r"arnhem baseline", r"\barnhem\b"]),
    "Tobruk": dict(
        topic="tobruk-ui-is-the-reference-interface.md", game="tobruk",
        code=["engine/combat.py", "engine/gamestate.py", "ui/tactical.html"],
        keys=[r"tobruk"]),
    "ASL": dict(topic=None, game="asl", code=["engine/gamestate.py"],
                keys=[r"\basl\b"]),
    "Coverage matrix / playability standard": dict(
        topic="coverage-matrix-standard.md", game=None, code=[],
        keys=[r"coverage matrix", r"playab", r"umpired", r"matrix"]),
    "Tiers / mode selector": dict(
        topic="tier-selection-engine-function.md", game=None,
        code=["engine/gate.py", "ui/server.py"],
        keys=[r"\btier\b", r"mode selector", r"sandbox"]),
    "Legality gate / engine core": dict(
        topic="legality-engine-optimization-2026-07-16.md", game=None,
        code=["engine/gate.py", "engine/gamespec.py", "engine/gamestate.py",
              "engine/verify_game.py"],
        keys=[r"legality", r"\bgate\b", r"gamespec", r"verify_game"]),
    "Web build / Valor engine": dict(
        topic="browser-demo-pyodide.md", game=None,
        code=["web/build_web.py"],
        keys=[r"pyodide", r"valor", r"web build", r"deploy", r"pages\.dev"]),
    "Source-defect register": dict(
        topic="source-defect-register-process.md", game=None, code=[],
        keys=[r"source.?defect", r"register", r"defect"]),
    "Module screener / commoditize": dict(
        topic="commoditize-encoding-module-screener.md", game=None,
        code=["tools/build_screen_index.py"],
        keys=[r"screener", r"screen", r"commoditi", r"funnel"]),
    "PBM / SALVO / matches": dict(
        topic="salvo-challenge-system.md", game=None,
        code=["engine/pbm.py", "engine/salvo.py"],
        keys=[r"\bpbm\b", r"salvo", r"match", r"champion", r"judge"]),
}


def headers():
    out = []
    with open(NOTES, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if line.startswith("#"):
                out.append((i, len(line) - len(line.lstrip("#")),
                            line.strip("#").strip()))
    return out


def blocks():
    hs = headers()
    total = sum(1 for _ in open(NOTES, encoding="utf-8"))
    out = []
    for n, (ln, lvl, txt) in enumerate(hs):
        end = hs[n + 1][0] - 1 if n + 1 < len(hs) else total
        out.append(dict(line=ln, end=end, level=lvl, text=txt))
    return out


def assign(bs):
    hit = {k: [] for k in SUBJECTS}
    for b in bs:
        low = b["text"].lower()
        for name, cfg in SUBJECTS.items():
            if any(re.search(k, low) for k in cfg["keys"]):
                hit[name].append(b)
    return hit


def commits(game):
    if not game:
        return ""
    p = subprocess.run(["git", "log", "--oneline", "--", f"games/{game}"],
                       cwd=ROOT, capture_output=True, text=True)
    lines = [x for x in p.stdout.splitlines() if x.strip()]
    if not lines:
        return ""
    return f"{lines[-1].split()[0]}..{lines[0].split()[0]} ({len(lines)})"


def gate_classes():
    out = {}
    for fn in sorted(os.listdir(os.path.join(ROOT, "engine"))):
        if not fn.endswith(".py"):
            continue
        p = os.path.join(ROOT, "engine", fn)
        src = open(p, encoding="utf-8", errors="replace").read()
        cls = re.findall(r"^class (\w+)\(GateGame\)", src, re.M)
        out[fn] = dict(lines=src.count("\n") + 1, gate=cls[0] if cls else None,
                       pending="self.s[\"pending\"]" in src
                       or 's["pending"]' in src)
    return out


def modes():
    out = {}
    import glob
    for p in glob.glob(os.path.join(ROOT, "games", "*", "scenario*.json")):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        m = d.get("mode")
        if m:
            out[os.path.basename(os.path.dirname(p))] = m
    return out


def write_toc(bs):
    L = ["# NOTES_TOC — line map of INTERNAL_NOTES.md",
         "",
         "Generated by tools/memory_index.py. INTERNAL_NOTES.md is 444KB and "
         "must never be read whole.",
         "Read a block with: `Read INTERNAL_NOTES.md offset=<line> limit=<end-line>`",
         "", "| line | end | section |", "|---|---|---|"]
    for b in bs:
        t = b["text"].replace("|", "\\|")
        L.append(f"| {b['line']} | {b['end']} | {'  ' * (b['level'] - 1)}{t} |")
    open(os.path.join(MEM, "NOTES_TOC.md"), "w", encoding="utf-8").write(
        "\n".join(L) + "\n")
    return len(bs)


def write_code_map(gc, md):
    inv = {}
    for g, m in md.items():
        inv.setdefault(m, []).append(g)
    L = ["# CODE_MAP — long-term memory of the codebase", "",
         "Generated by tools/memory_index.py. Lets a session answer "
         "\"which games do X\" without reading the code.", "",
         "## Gate classes (the legality engines)", "",
         "| module | lines | class | games | pending model |", "|---|---|---|---|---|"]
    mode_of = {"engine/strategic.py": "strategic", "engine/bluegray.py": "bluegray",
               "engine/westwall.py": "westwall", "engine/napoleonic.py": "napoleonic",
               "engine/soj.py": "soj", "engine/gamestate.py": "tactical"}
    for fn, info in sorted(gc.items()):
        if not info["gate"]:
            continue
        key = f"engine/{fn}"
        gm = inv.get(mode_of.get(key, ""), [])
        if key == "engine/gamestate.py":
            gm = ["arnhem", "tobruk", "asl"]
        L.append(f"| `{key}` | {info['lines']} | {info['gate']} | "
                 f"{', '.join(gm) or '-'} | {'yes' if info['pending'] else 'NO'} |")
    L += ["", "## Shared layer", "",
          "| module | lines | role |", "|---|---|---|"]
    for fn in ("gate.py", "gamespec.py", "verify_game.py", "vsav.py",
               "board.py", "make_save.py"):
        if fn in gc:
            L.append(f"| `engine/{fn}` | {gc[fn]['lines']} | shared |")
    L += ["", "## Clients", "", "| file | lines | serves |", "|---|---|---|"]
    for f, serves in (("ui/index.html", "strategic family (AK, B&G, Westwall, Austerlitz)"),
                      ("ui/tactical.html", "tactical family (Arnhem, Tobruk, ASL)"),
                      ("ui/soj.html", "Siege of Jerusalem")):
        p = os.path.join(ROOT, f)
        n = sum(1 for _ in open(p, encoding="utf-8", errors="replace")) \
            if os.path.exists(p) else 0
        L.append(f"| `{f}` | {n} | {serves} |")
    L += ["", "## Encoded games", "", "| game | mode | game.json | commits |",
          "|---|---|---|---|"]
    for g in sorted(md):
        p = os.path.join(ROOT, "games", g, "game.json")
        sz = os.path.getsize(p) if os.path.exists(p) else 0
        L.append(f"| {g} | {md[g]} | {sz}b | {commits(g)} |")
    open(os.path.join(MEM, "CODE_MAP.md"), "w", encoding="utf-8").write(
        "\n".join(L) + "\n")


def write_index(hit):
    L = ["# INDEX — the memory router", "",
         "**Read this before answering any question about a game, a "
         "subsystem, or a past decision.**", "",
         "It resolves a subject to the exact files and line ranges that hold "
         "the answer, so no session has to reconstruct from source code. "
         "Reconstruction is where fabrication happens.", "",
         "Levels: `NOW.md` = short term (current job) · topic file = medium "
         "term (this subject) · `INTERNAL_NOTES.md` blocks + `CODE_MAP.md` + "
         "git = long term.", "",
         "Regenerate: `python tools/memory_index.py`", "",
         "| subject | topic file (medium) | INTERNAL_NOTES lines (long) | code | commits |",
         "|---|---|---|---|---|"]
    for name, cfg in SUBJECTS.items():
        bs = hit[name]
        spans = ", ".join(f"{b['line']}-{b['end']}" for b in bs[:6])
        if len(bs) > 6:
            spans += f", +{len(bs) - 6} more"
        topic = f"`{cfg['topic']}`" if cfg["topic"] else "-"
        code = ", ".join(f"`{c}`" for c in cfg["code"]) or "-"
        L.append(f"| **{name}** | {topic} | {spans or '-'} | {code} | "
                 f"{commits(cfg['game']) or '-'} |")
    L += ["", "## All topic files", ""]
    for fn in sorted(os.listdir(MEM)):
        if not fn.endswith(".md") or fn in ("MEMORY.md", "INDEX.md",
                                            "NOTES_TOC.md", "CODE_MAP.md",
                                            "NOW.md"):
            continue
        desc = ""
        try:
            for line in open(os.path.join(MEM, fn), encoding="utf-8"):
                if line.startswith("description:"):
                    desc = line.split(":", 1)[1].strip().strip('"')[:150]
                    break
        except Exception:
            pass
        L.append(f"- `{fn}` — {desc}")
    open(os.path.join(MEM, "INDEX.md"), "w", encoding="utf-8").write(
        "\n".join(L) + "\n")


def main():
    bs = blocks()
    n = write_toc(bs)
    write_code_map(gate_classes(), modes())
    write_index(assign(bs))
    print(f"NOTES_TOC.md  {n} sections")
    print("CODE_MAP.md   gate classes + clients + encoded games")
    print(f"INDEX.md      {len(SUBJECTS)} routed subjects")
    print(f"-> {MEM}")


if __name__ == "__main__":
    main()
