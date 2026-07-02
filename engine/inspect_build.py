"""Inspect the Westwall module buildFile: boards, hex grids, numbering, piece prototypes."""
import re, sys, xml.etree.ElementTree as ET

BUILD = sys.argv[1] if len(sys.argv) > 1 else r"C:\VassalArnhem\ref\buildFile.xml"

raw = open(BUILD, "r", encoding="utf-8", errors="replace").read()
print(f"buildFile length: {len(raw)} chars\n")

# Find all board definitions (names) and hex grids with their attributes.
# VASSAL class names are long; match by local tag name.
print("=== Boards (Board elements) ===")
for m in re.finditer(r'<(\S*\.board\.Board|\S*Board)\b([^>]*)>', raw):
    attrs = dict(re.findall(r'(\w+)="([^"]*)"', m.group(2)))
    name = attrs.get("name") or attrs.get("image")
    if name:
        print(f"  Board: name={attrs.get('name')!r} image={attrs.get('image')!r} width={attrs.get('width')} height={attrs.get('height')}")

print("\n=== HexGrid elements ===")
for m in re.finditer(r'<(\S*HexGrid)\b([^>]*)/?>', raw):
    attrs = dict(re.findall(r'(\w+)="([^"]*)"', m.group(2)))
    keys = ["dx","dy","x0","y0","sideways","snapTo","visible","color","edgesLegal","cornersLegal"]
    print("  HexGrid: " + ", ".join(f"{k}={attrs.get(k)}" for k in keys if k in attrs))

print("\n=== HexGrid numbering ===")
for m in re.finditer(r'<(\S*HexGridNumbering)\b([^>]*)/?>', raw):
    attrs = dict(re.findall(r'(\w+)="([^"]*)"', m.group(2)))
    print("  Numbering:", attrs)

# Show raw context around first HexGrid for full attribute visibility
i = raw.find("HexGrid")
if i >= 0:
    print("\n=== raw context around first HexGrid ===")
    print(raw[max(0,i-200):i+600])
