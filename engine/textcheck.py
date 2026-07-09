"""
textcheck.py - Text-layer inventory of every PDF in the LaunchBox Manuals
tree. Regenerate after each acquisition pipeline so doc_gaps.py grades from
disk truth.

    python engine/textcheck.py

Scans <LIB>/launchbox/Manuals/VASSAL/<title>/*.pdf and writes
_meta/manual_textcheck.json: {title: [{file, pages, chars_per_page, text}]}.
A PDF "has text" when it averages >=200 chars/page (same threshold as
rules_screen.py) or exceeds 3000 chars total.
"""
import json, os, sys

import fitz

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import census

META = census.META
MANUALS = os.path.join(census.LIB, "launchbox", "Manuals", "VASSAL")


def check_pdf(path):
    doc = fitz.open(path)
    pages = doc.page_count
    chars = sum(len(p.get_text()) for p in doc)
    doc.close()
    cpp = chars // max(1, pages)
    return dict(file=os.path.basename(path), pages=pages, chars_per_page=cpp,
                text=cpp >= 200 or chars > 3000)


def main():
    out = {}
    n_pdf = n_err = 0
    for title in sorted(os.listdir(MANUALS)):
        d = os.path.join(MANUALS, title)
        if not os.path.isdir(d):
            continue
        entries = []
        for f in sorted(os.listdir(d)):
            if not f.lower().endswith(".pdf"):
                continue
            try:
                entries.append(check_pdf(os.path.join(d, f)))
                n_pdf += 1
            except Exception as e:
                entries.append(dict(file=f, pages=0, chars_per_page=0,
                                    text=False, error=str(e)[:120]))
                n_err += 1
        if entries:
            out[title] = entries
    json.dump(out, open(os.path.join(META, "manual_textcheck.json"), "w",
                        encoding="utf-8"), indent=1)
    with_text = sum(1 for v in out.values() if any(e.get("text") for e in v))
    print(f"{len(out)} games / {n_pdf} PDFs checked ({n_err} unreadable); "
          f"{with_text} games text-readable -> manual_textcheck.json")


if __name__ == "__main__":
    main()
