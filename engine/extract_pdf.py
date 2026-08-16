"""Extract text from the Westwall rules PDF. Detects scanned-vs-text per page."""
import sys
pdf = r"C:\VassalArnhem\literature\westwall\WestWallStdRules.pdf"
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
if sum(len(t.strip()) for t in out) < 200:
    print(f"\nREFUSING TO WRITE: {pdf} has no usable text layer "
          f"({sum(len(t.strip()) for t in out)} chars across {len(out)} pages). "
          f"This PDF is a scan — it needs OCR, not text extraction. "
          f"Use: python tools/extract_literature.py")
    sys.exit(1)
open(r"C:\VassalArnhem\literature\westwall\WestWallStdRules.txt", "w", encoding="utf-8").write(full)
print(f"\nTotal extracted text: {len(full)} chars -> WestWallStdRules.txt")
print("\n--- first 1500 chars ---\n")
print(full[:1500])
