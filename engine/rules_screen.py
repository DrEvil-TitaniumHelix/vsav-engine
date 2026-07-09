"""
rules_screen.py - Keyword screen of every game's on-disk rules text for
gate-3 knockouts (subsystems our engine doesn't have) and gate-5 positives
(CRT/TEC/ZOC/odds/examples). SIGNALS, NOT VERDICTS (spec #12): a CLEAN-FIT
still needs a human read + validated encoding before any tier claim.

    python engine/rules_screen.py

Text sources per game, all concatenated:
  - text-layer PDFs in  <LIB>/launchbox/Manuals/VASSAL/<title>/  (bundled,
    library-package fetched, publisher living rules - anything on disk)
  - OCR sidecars        _meta/ocr/<title>__*.txt

Writes _meta/rules_screen.json and prints the funnel.
"""
import json, os, re, sys
from collections import Counter

import fitz

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import census

META = census.META
MANUALS = os.path.join(census.LIB, "launchbox", "Manuals", "VASSAL")
OCRDIR = os.path.join(META, "ocr")

KNOCK = {
    "supply": re.compile(r"supply (line|point|source|trace|state)|out of supply", re.I),
    "hidden": re.compile(r"hidden (unit|movement|placement)|concealed|dummy (unit|counter)|untried", re.I),
    "air": re.compile(r"air (mission|superiority|unit|phase|combat|point)", re.I),
    "naval": re.compile(r"naval (unit|movement|combat|phase)|sea zone", re.I),
    "cards": re.compile(r"(play|draw|discard)s? (a |the )?(strategy |event )?card|card play", re.I),
}
POS = {
    "crt": re.compile(r"combat results table|CRT", re.I),
    "tec": re.compile(r"terrain effects? (chart|table)", re.I),
    "zoc": re.compile(r"zones? of control|ZOC", re.I),
    "example": re.compile(r"example (of play|:)|for example", re.I),
    "odds": re.compile(r"odds (ratio|column)|\b\d\s*:\s*1 odds|die roll modifier|DRM", re.I),
}


def clean_title(t):
    # trailing dots/spaces are stripped by Win32 at dir creation - mirror that
    return re.sub(r"\s+", " ", re.sub(r"[\\/:*?\"<>|']", "_", t or "")) \
        .strip().rstrip(". ")


def game_text(title):
    """(text, sources[]) from PDFs with a text layer + OCR sidecars."""
    t = clean_title(title)
    text, src = [], []
    d = os.path.join(MANUALS, t)
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            if not f.lower().endswith(".pdf"):
                continue
            try:
                doc = fitz.open(os.path.join(d, f))
                pages = doc.page_count
                s = " ".join(p.get_text() for p in doc)
                doc.close()
                if len(s) / max(1, pages) >= 200 or len(s) > 3000:
                    text.append(s)
                    src.append(f)
            except Exception:
                pass
    if os.path.isdir(OCRDIR):
        for f in sorted(os.listdir(OCRDIR)):
            if f.startswith(t + "__") and f.endswith(".txt"):
                s = open(os.path.join(OCRDIR, f), encoding="utf-8").read()
                if len(s) > 1500:
                    text.append(s)
                    src.append("OCR:" + f)
    return " ".join(text), src


def screen_text(text):
    knocks = {k: len(v.findall(text)) for k, v in KNOCK.items()}
    poss = {k: len(v.findall(text)) for k, v in POS.items()}
    hard = [k for k, n in knocks.items() if n >= 5]
    good = [k for k, n in poss.items() if n >= 2]
    verdict = ("CLEAN-FIT" if not hard and {"crt", "zoc"} <= set(good)
               else "KNOCKOUT:" + "+".join(hard) if hard else "WEAK-SIGNALS")
    return verdict, {k: n for k, n in knocks.items() if n}, \
        {k: n for k, n in poss.items() if n}


def main():
    rows = json.load(open(os.path.join(META, "tier_targets.json"),
                          encoding="utf-8"))
    out = []
    for x in rows:
        text, src = game_text(x["title"])
        if len(text) < 2000:
            continue
        verdict, knocks, poss = screen_text(text)
        out.append(dict(x, screen=verdict, text_chars=len(text), sources=src,
                        knocks=knocks, positives=poss))
    json.dump(out, open(os.path.join(META, "rules_screen.json"), "w",
                        encoding="utf-8"), indent=1)
    c = Counter(o["screen"].split(":")[0] for o in out)
    print(f"screened {len(out)} games with rules text: {dict(c)}")
    clean_hex = [o for o in out if o["screen"] == "CLEAN-FIT"
                 and o["style"] == "hex" and (o["setups"] or 0) > 0]
    print(f"CLEAN-FIT hex+setups (tier-attempt ready): {len(clean_hex)}")
    for o in sorted(clean_hex, key=lambda o: -o["score"]):
        print(f"  {o['score']:3} {o['title'][:64]}")


if __name__ == "__main__":
    main()
