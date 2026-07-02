import fitz, os, sys
pdf = sys.argv[1] if len(sys.argv) > 1 else r"C:\VassalArnhem\literature\WestWallStdRules.pdf"
outdir = sys.argv[2] if len(sys.argv) > 2 else r"C:\VassalArnhem\literature\pages"
os.makedirs(outdir, exist_ok=True)
doc = fitz.open(pdf)
for i, page in enumerate(doc):
    try:
        pix = page.get_pixmap(dpi=140)
        p = os.path.join(outdir, f"rules_p{i+1}.png")
        pix.save(p)
        print(f"page {i+1}: {pix.width}x{pix.height}  {os.path.getsize(p)//1024} KB -> {p}")
    except Exception as e:
        print(f"page {i+1}: render failed: {e}")
