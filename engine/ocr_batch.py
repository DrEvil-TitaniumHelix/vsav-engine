"""
ocr_batch.py - OCR every scanned (no-text-layer) rulebook PDF in the Manuals
tree into _meta/ocr/<title>__<pdfname>.txt sidecars, which rules_screen.py
and doc_gaps.py already consume. Replaces the ad-hoc OCR rounds of 2026-07-09.

    python engine/ocr_batch.py [--limit N]

Resumable: a PDF is skipped when its sidecar already exists (any size).
Only rules-ish PDFs are OCR'd (rule|manual|book|chart|crt in the name) -
maps/counter scans waste hours and feed the screen nothing.
Requires local tesseract (5.x) on PATH. Pages rendered at 300 dpi via PyMuPDF.
"""
import argparse, os, re, subprocess, sys, tempfile

import fitz

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import census

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

META = census.META
MANUALS = os.path.join(census.LIB, "launchbox", "Manuals", "VASSAL")
OCRDIR = os.path.join(META, "ocr")
RULESISH = re.compile(r"rule|manual|book|chart|crt|table|exclusive|standard",
                      re.I)
MAX_PAGES = 80          # rulebooks; skip 200-page monsters' tails


def has_text(path):
    try:
        doc = fitz.open(path)
        pages = doc.page_count
        chars = sum(len(p.get_text()) for p in doc)
        doc.close()
        return (chars / max(1, pages)) >= 200 or chars > 3000, pages
    except Exception:
        return True, 0      # unreadable: skip


def ocr_pdf(path, out_txt):
    doc = fitz.open(path)
    n = min(doc.page_count, MAX_PAGES)
    texts = []
    with tempfile.TemporaryDirectory() as td:
        for i in range(n):
            png = os.path.join(td, f"p{i}.png")
            doc[i].get_pixmap(dpi=300).save(png)
            r = subprocess.run(["tesseract", png, "stdout", "--psm", "3"],
                               capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            texts.append(r.stdout or "")
    doc.close()
    txt = "\n".join(texts).strip()
    if len(txt) > 1500:
        open(out_txt, "w", encoding="utf-8").write(txt)
        return len(txt)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    os.makedirs(OCRDIR, exist_ok=True)
    done = n_ocr = n_skip = 0
    for title in sorted(os.listdir(MANUALS)):
        d = os.path.join(MANUALS, title)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.lower().endswith(".pdf") or not RULESISH.search(f):
                continue
            sidecar = os.path.join(
                OCRDIR, f"{title}__{os.path.splitext(f)[0].replace(' ', '_')}.txt")
            if os.path.exists(sidecar):
                n_skip += 1
                continue
            texty, pages = has_text(os.path.join(d, f))
            if texty:
                continue
            print(f"OCR {title} / {f} ({pages}p)...", flush=True)
            try:
                chars = ocr_pdf(os.path.join(d, f), sidecar)
                print(f"  -> {chars} chars")
                n_ocr += 1
            except Exception as e:
                print(f"  ERROR: {e}")
            done += 1
            if a.limit and done >= a.limit:
                print(f"limit {a.limit} reached")
                return
    print(f"OCR'd {n_ocr} PDFs (skipped {n_skip} existing sidecars)")


if __name__ == "__main__":
    main()
