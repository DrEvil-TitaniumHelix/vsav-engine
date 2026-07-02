"""Extract text from the Westwall rules PDF. Detects scanned-vs-text per page."""
import sys
pdf = r"C:\VassalArnhem\literature\WestWallStdRules.pdf"
try:
    import fitz  # PyMuPDF
except ImportError:
    print("NO_FITZ"); sys.exit(0)

doc = fitz.open(pdf)
print(f"pages: {doc.page_count}")
out = []
for i, page in enumerate(doc):
    t = page.get_text()
    out.append(t)
    print(f"  page {i+1}: {len(t)} text chars")
full = "\n\n===PAGE BREAK===\n\n".join(out)
open(r"C:\VassalArnhem\literature\WestWallStdRules.txt", "w", encoding="utf-8").write(full)
print(f"\nTotal extracted text: {len(full)} chars -> WestWallStdRules.txt")
print("\n--- first 1500 chars ---\n")
print(full[:1500])
