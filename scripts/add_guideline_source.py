"""
Intake for hand-transcribed ICMR guideline chapters.

Wraps raw pasted chapter text in consistent provenance front-matter and writes it
to backend/guidelines/data/sources/. Provenance is recorded honestly: these are
portal transcriptions, NOT ingested PDFs, so no file hash or page numbers are
claimed.

Usage:
    python scripts/add_guideline_source.py \
        --slug uti \
        --chapter "Urinary Tract Infections" \
        --raw path/to/pasted.txt

Then run with --report to see corpus coverage.
"""
import argparse
import datetime
import pathlib
import re
import sys

SOURCES = pathlib.Path("backend/guidelines/data/sources")

FRONT_MATTER = """---
document_id: ICMR-AMRTG-2022-{doc_id}
title: "Treatment Guidelines for Antimicrobial Use in Common Syndromes 2022 — {chapter}"
issuing_org: "Indian Council of Medical Research (ICMR), New Delhi, India"
geographic_scope: "National (India)"
version: "2022"
source_url: "https://amrtg.icmr.org.in/dashboard.html"
source_type: transcribed_text
transcribed_by: user
retrieved_at: "{today}"
chapter: "{chapter}"
provenance_note: >
  Text transcribed by hand from the ICMR AMR Treatment Guidelines web portal.
  NOT an ingested source PDF: no file hash is claimed and no page numbers are
  available, because the source is a web dashboard. Section anchors follow the
  portal's own headings. Any citation generated from this file must be labelled
  as portal-transcribed text, not a PDF extract.
tables_verified: false
table_note: >
  Tables transcribed from HTML may lose column alignment. Any table in this file
  is UNVERIFIED against the source rendering. Dosing content from a table must be
  re-checked before it is cited to a clinician.
---

"""


def normalise(raw: str) -> str:
    """Light cleanup only. Never alters clinical wording."""
    text = raw.replace("\r\n", "\n").replace(" ", " ")
    # Drop portal chrome that appears on every page.
    noise = [
        r"^\s*\[Dashboard\]\(.*?\)\s*$",
        r"^\s*\[Toggle\]\(.*?\)\s*$",
        r"^\s*©\s*Indian Council of Medical Research.*$",
        r"^\s*\*\s*$",
    ]
    for pattern in noise:
        text = re.sub(pattern, "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def add(slug: str, chapter: str, raw_path: pathlib.Path) -> pathlib.Path:
    raw = raw_path.read_text(encoding="utf-8")
    body = normalise(raw)
    header = FRONT_MATTER.format(
        doc_id=slug.upper().replace("_", "-"),
        chapter=chapter,
        today=datetime.date.today().isoformat(),
    )
    SOURCES.mkdir(parents=True, exist_ok=True)
    out = SOURCES / f"icmr_2022_{slug}.md"
    out.write_text(header + body, encoding="utf-8")
    return out


def report() -> None:
    if not SOURCES.exists():
        print("no sources directory yet")
        return
    files = sorted(SOURCES.glob("*.md"))
    print(f"{'file':38} {'sections':>9} {'words':>7} {'tables':>7}")
    print("-" * 66)
    total_words = 0
    for f in files:
        text = f.read_text(encoding="utf-8")
        sections = len(re.findall(r"^## ", text, flags=re.MULTILINE))
        words = len(text.split())
        tables = len(re.findall(r"^\|", text, flags=re.MULTILINE))
        total_words += words
        print(f"{f.name:38} {sections:>9} {words:>7} {tables:>7}")
    print("-" * 66)
    print(f"{len(files)} chapters, {total_words} words")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--slug", help="short filename slug, e.g. uti")
    p.add_argument("--chapter", help="chapter title as shown in the portal")
    p.add_argument("--raw", type=pathlib.Path, help="file containing the pasted text")
    p.add_argument("--report", action="store_true", help="show corpus coverage")
    args = p.parse_args()

    if args.report:
        report()
        return 0
    if not (args.slug and args.chapter and args.raw):
        p.error("--slug, --chapter and --raw are all required (or use --report)")
    out = add(args.slug, args.chapter, args.raw)
    text = out.read_text(encoding="utf-8")
    print(f"wrote {out}")
    print(f"  sections: {len(re.findall(r'^## ', text, flags=re.MULTILINE))}")
    print(f"  words:    {len(text.split())}")
    if re.search(r"^\|", text, flags=re.MULTILINE):
        print("  NOTE: contains tables — tables_verified is false, re-check before citing")
    return 0


if __name__ == "__main__":
    sys.exit(main())
