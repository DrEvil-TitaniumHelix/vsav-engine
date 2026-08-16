import argparse, html, os, re, shutil, subprocess, sys, tempfile

import fitz

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIT = os.path.join(ROOT, "literature")
AK_SRC = r"C:\VassalIngest\afrika-korps-classic-ah\extracted"
AK_PDFS = ["AfrikaKorps_3d_Ed_Rules.pdf",
           "Afrika Korps Rule Clarifications for Vassal.pdf",
           "Afrika Korps 3.0 Start text.pdf"]
TEXT_MIN = 120
DPI = 300


def stage_afrika_korps():
    dst = os.path.join(LIT, "afrika-korps")
    os.makedirs(dst, exist_ok=True)
    staged = []
    for n in AK_PDFS:
        src = os.path.join(AK_SRC, n)
        if not os.path.exists(src):
            print(f"  MISSING {src}")
            continue
        tgt = os.path.join(dst, n.replace(" ", "_"))
        if not os.path.exists(tgt):
            shutil.copy2(src, tgt)
        staged.append(os.path.relpath(tgt, ROOT))
    return staged


def ocr_page(page):
    pix = page.get_pixmap(dpi=DPI)
    with tempfile.TemporaryDirectory() as td:
        img = os.path.join(td, "p.png")
        pix.save(img)
        out = os.path.join(td, "o")
        r = subprocess.run(["tesseract", img, out, "-l", "eng", "--psm", "3"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            return None, r.stderr.strip()[:200]
        try:
            return open(out + ".txt", encoding="utf-8", errors="replace").read(), None
        except OSError as e:
            return None, str(e)


def extract_pdf(path):
    doc = fitz.open(path)
    parts, prov, errs = [], [], []
    for i, page in enumerate(doc):
        t = page.get_text()
        kind = "TEXT"
        if len(t.strip()) < TEXT_MIN:
            o, err = ocr_page(page)
            if o is None:
                kind, t = "FAILED", ""
                errs.append(f"p{i+1}: {err}")
            else:
                kind, t = "OCR", o
        prov.append(kind)
        parts.append(f"=== PAGE {i+1} [{kind}] ===\n{t}")
    doc.close()
    return "\n\n".join(parts), prov, errs


def extract_html(path):
    raw = open(path, encoding="utf-8", errors="replace").read()
    raw = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</p>|</tr>|</h[1-6]>", "\n", raw)
    raw = re.sub(r"(?i)</t[dh]>", "\t", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = html.unescape(raw)
    raw = re.sub(r"[ \t]+", " ", raw)
    raw = re.sub(r"\n\s*\n\s*\n+", "\n\n", raw)
    return raw.strip()


def sidecar_is_real(p):
    if not os.path.exists(p):
        return False
    body = open(p, encoding="utf-8", errors="replace").read()
    body = re.sub(r"===[^=]*===", "", body)
    return len(body.strip()) >= 200


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--only", default=None)
    args = ap.parse_args()

    print("staging Afrika Korps rulebooks into literature/afrika-korps/")
    for s in stage_afrika_korps():
        print(f"  {s}")

    targets = []
    for dirpath, _, files in os.walk(LIT):
        for f in sorted(files):
            if f.lower().endswith((".pdf", ".html", ".htm")):
                targets.append(os.path.join(dirpath, f))
    if args.only:
        targets = [t for t in targets if args.only.lower() in t.lower()]

    rows, reused = [], 0
    for path in sorted(targets):
        rel = os.path.relpath(path, ROOT).replace("\\", "/")
        side = os.path.splitext(path)[0] + ".txt"
        if not args.force and sidecar_is_real(side):
            body = open(side, encoding="utf-8", errors="replace").read()
            prov = re.findall(r"=== PAGE \d+ \[(\w+)\] ===", body)
            n = len(prov)
            nt, no, nf = (prov.count("TEXT"), prov.count("OCR"),
                          prov.count("FAILED"))
            if not prov:
                kind, detail = "clean", f"html markup stripped; {len(body)} chars"
            else:
                kind = ("clean" if no == 0 and nf == 0 else
                        "ocr" if nt == 0 and nf == 0 else
                        "failed" if nf == n else "mixed")
                detail = f"text={nt} ocr={no} failed={nf}"
            rows.append((rel, os.path.relpath(side, ROOT).replace("\\", "/"),
                         kind, n, detail))
            reused += 1
            continue
        print(f"[extract] {rel}")
        try:
            if path.lower().endswith(".pdf"):
                body, prov, errs = extract_pdf(path)
            else:
                body, prov, errs = extract_html(path), ["HTML"], []
        except Exception as e:
            rows.append((rel, "-", "ERROR", 0, str(e)[:160]))
            print(f"    ERROR {e}")
            continue
        open(side, "w", encoding="utf-8").write(body)
        n = len(prov)
        nt, no, nf = prov.count("TEXT"), prov.count("OCR"), prov.count("FAILED")
        if prov == ["HTML"]:
            kind, detail = "clean", f"html markup stripped; {len(body)} chars"
        else:
            kind = ("clean" if no == 0 and nf == 0 else
                    "ocr" if nt == 0 and nf == 0 else
                    "failed" if nf == n else "mixed")
            detail = (f"text={nt} ocr={no} failed={nf}"
                      + ("; " + "; ".join(errs[:3]) if errs else ""))
        rows.append((rel, os.path.relpath(side, ROOT).replace("\\", "/"),
                     kind, n, detail))
        print(f"    {kind}: {n} pages, text={nt} ocr={no} failed={nf}"
              f" -> {len(body)} chars")

    lines = ["# LITERATURE EXTRACTION REPORT",
             "",
             "Generated by `tools/extract_literature.py`. Local-only, gitignored.",
             "",
             "## Provenance is the point",
             "",
             "Every sidecar `.txt` tags each page `[TEXT]`, `[OCR]`, or `[FAILED]`.",
             "",
             "- `[TEXT]` — lifted from the PDF's own text layer. Trustworthy.",
             "- `[OCR]` — tesseract 5.5 at 300 dpi on a page image. **UNVERIFIED.**",
             "- `[FAILED]` — no text recovered. Read the page image.",
             "",
             "**No number, table cell, CRT row, terrain cost or hex ID may be encoded",
             "from an `[OCR]` page without reading the page image to confirm it.**",
             "OCR of a 1970s scan is exactly where wrong data enters, and wrong data",
             "means a wrong rules engine (CLAUDE.md hard rule 1). OCR text is a search",
             "index and a reading aid, never an authority.",
             "",
             "## Every extracted source",
             "",
             "Quality is derived from the sidecar's own page tags, so this table",
             "describes the CURRENT state of every sidecar, not just the last run.",
             "",
             "| source | sidecar | quality | pages | detail |",
             "|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda x: (x[2], x[0])):
        lines.append(f"| `{r[0]}` | `{r[1]}` | **{r[2]}** | {r[3]} | {r[4]} |")
    lines += ["", "## Not machine-readable by this tool", "",
              "Handle by hand if a decode needs them:", ""]
    for dirpath, _, files in os.walk(LIT):
        for f in sorted(files):
            if f.lower().endswith((".doc", ".docx", ".zip", ".gif", ".png")):
                rel = os.path.relpath(os.path.join(dirpath, f), ROOT)
                lines.append(f"- `{rel.replace(chr(92), '/')}`")
    open(os.path.join(LIT, "EXTRACTION_REPORT.md"), "w",
         encoding="utf-8").write("\n".join(lines) + "\n")
    print(f"\n{len(rows)} sources ({reused} reused from existing sidecars)"
          f" -> literature/EXTRACTION_REPORT.md")


if __name__ == "__main__":
    main()
