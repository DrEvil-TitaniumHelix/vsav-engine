"""Grid + setup validation: the engine's own Grid class must resolve every
at-start piece position in the module's 'Chickamauga Start.vsav' to the hex
the 1975 Initial Deployment Chart assigns it (scan p5 [14.1/14.2]).

Known module deviations (rules_transcription.json module_deviations_worksheet):
  - Wilder parked at 0822 (chart: 1022)
  - 2/4/XIV omitted from the setup entirely (chart: 0822)
Both are asserted AS DEVIATIONS: the check fails if the module changes."""
import json, os, re, sys

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..")))
from engine import gamespec, vsav

HERE = os.path.dirname(os.path.abspath(__file__))
G = gamespec.load(HERE)
VSAV = os.path.normpath(os.path.join(HERE, "..", "..", "..", "VassalBlueGray",
                                     "extracted", "Chickamauga Start.vsav"))

chart = json.load(open(os.path.join(HERE, "rules_transcription.json"), encoding="utf-8"))
cx = chart["chickamauga_exclusive"]
ALIAS = {"Hmphry": "Humphrey", "Rbrtsn": "Robertson", "Andrsn": "Anderson",
         "Wlthll": "Walthall", "Armstng": "Armstrong", "Davdsn": "Davidson",
         "1/2 Cav": "1/2 Cavalry", "3": "3 Artillery"}
expected = {}
for u in cx["initial_deployment_union"] + cx["initial_deployment_confederate"]:
    nm = ALIAS.get(u["name"], u["name"])
    expected[nm] = u["hex"]

plain, _, _ = vsav.read_vsav(VSAV)
onmap = {}
for c in plain.split(chr(27)):
    if not c.startswith("+/") or "/stack/" in c:
        continue
    mi = re.search(r'piece;;;([^;]+?\.(?:png|gif|svg));([^;]*)', c)
    mp = re.search(r'Main Map;(\d+);(\d+);(\d+);', c)
    if not mi or not mp:
        continue
    name = mi.group(2).replace("\\/", "/").split("/true")[0].split("/false")[0].strip()
    if name.endswith(" c"):
        name = name[:-2]
    x, y = int(mp.group(1)), int(mp.group(2))
    col, row, hx = G.grid.pixel_to_hex(x, y)
    onmap[name] = hx

fails, ok = [], 0
for nm, hx in sorted(expected.items()):
    got = onmap.get(nm)
    if nm == "Wilder":
        if got == "0822":
            ok += 1
            print(f"PASS Wilder: module deviation confirmed at 0822 (chart 1022, scenario corrects)")
        else:
            fails.append(f"Wilder expected module-deviation 0822, got {got}")
        continue
    if nm == "2/4/XIV":
        if got is None:
            ok += 1
            print(f"PASS 2/4/XIV: module omission confirmed (scenario places it at 0822)")
        else:
            fails.append(f"2/4/XIV expected absent from module setup, found at {got}")
        continue
    if got == hx:
        ok += 1
    else:
        fails.append(f"{nm}: module {got} != chart {hx}")

print(f"\n{ok}/{len(expected)} positions validated against the 1975 chart")
# grid roundtrip: hex -> pixel -> hex, all playable hexes
bad_rt = 0
for c in range(1, 27):
    for r in range(1, 29):
        x, y = G.grid.hex_to_pixel(c, r)
        c2, r2, _ = G.grid.pixel_to_hex(x, y)
        if (c, r) != (c2, r2):
            bad_rt += 1
print(f"roundtrip: {728 - bad_rt}/728 hexes exact")
if bad_rt:
    fails.append(f"{bad_rt} roundtrip failures")
if fails:
    print("FAILURES:")
    for f in fails:
        print("  ", f)
    sys.exit(1)
print("ALL PASS")
