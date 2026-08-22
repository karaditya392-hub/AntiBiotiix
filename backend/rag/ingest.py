"""
Guideline PDF ingestion: PDF -> text -> section/page-aware chunks -> store.
(Spec §13, §14, §21, §22)

Every chunk records the page it came from, so an evidence citation resolves to a
page in a named edition of a named document — which is what source traceability
actually requires. Prior document versions are never overwritten: a new edition
is inserted alongside, per §22.

Nothing here invents clinical content. Chunks are verbatim extracted text.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, List, Optional

CHUNK_TARGET_CHARS = 1100
CHUNK_OVERLAP_CHARS = 150
MIN_CHUNK_CHARS = 120


@dataclass
class Chunk:
    document_id: str
    version: str
    page: int
    section: Optional[str]
    char_start: int
    char_end: int
    text: str


@dataclass
class DocumentMeta:
    document_id: str
    title: str
    issuing_org: str
    geographic_scope: str
    version: str
    publication_date: str
    source_url: str
    source_file: str
    file_sha256: str
    page_count: int
    precedence_rank: int
    ingested_at: str
    notes: str = ""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# Headings in these documents are short, mostly-uppercase or numbered lines.
_HEADING = re.compile(
    r"^(?:\d+(?:\.\d+)*\s+[A-Z][^\n]{3,70}|[A-Z][A-Z \-/&,()]{6,70})$"
)


def _looks_like_heading(line: str) -> bool:
    s = line.strip()
    if not (6 <= len(s) <= 80):
        return False
    if s.endswith("."):
        return False
    return bool(_HEADING.match(s))


def _clean_page_text(raw: str) -> str:
    t = raw.replace("\r\n", "\n")
    t = re.sub(r"[ \t]+", " ", t)
    # Collapse the doubled glyphs some PDF encoders emit (e.g. "TThhee").
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def extract_pages(pdf_path: Path) -> List[str]:
    """
    Extract page text, then repair PDF artifacts.

    PyMuPDF is used rather than pypdf because these documents emit unmapped glyph
    names ("/g248uoroquinolone") under pypdf. PyMuPDF avoids that but encodes
    ligatures as font-specific control bytes, which backend.rag.textrepair
    resolves against a dictionary of words that extracted cleanly elsewhere in
    the same document. Nothing is paraphrased; only extraction damage is undone.
    """
    import pymupdf

    from backend.rag.textrepair import build_dictionary, repair

    doc = pymupdf.open(str(pdf_path))
    raw = [page.get_text("text") for page in doc]
    vocab = build_dictionary(raw)

    pages, totals = [], {"ligatures": 0, "dropped": 0, "spacing": 0}
    for page_text in raw:
        fixed, stats = repair(page_text, vocab)
        for k, v in stats.items():
            totals[k] += v
        pages.append(_clean_page_text(fixed))
    print(f"  text repair: {totals['ligatures']} ligature byte(s), "
          f"{totals['dropped']} dropped ligature(s), {totals['spacing']} split word(s)")
    return pages


def chunk_page(
    document_id: str, version: str, page_no: int, text: str, current_section: Optional[str]
) -> tuple[List[Chunk], Optional[str]]:
    """Split one page into overlapping chunks, tracking the last seen heading."""
    chunks: List[Chunk] = []
    if not text.strip():
        return chunks, current_section

    for line in text.split("\n")[:6]:
        if _looks_like_heading(line):
            current_section = line.strip()
            break

    start = 0
    n = len(text)
    while start < n:
        end = min(start + CHUNK_TARGET_CHARS, n)
        if end < n:
            # Prefer a sentence or paragraph boundary.
            window = text[start:end]
            cut = max(window.rfind(". "), window.rfind("\n"))
            if cut > CHUNK_TARGET_CHARS // 2:
                end = start + cut + 1
        body = text[start:end].strip()
        if len(body) >= MIN_CHUNK_CHARS:
            chunks.append(
                Chunk(
                    document_id=document_id,
                    version=version,
                    page=page_no,
                    section=current_section,
                    char_start=start,
                    char_end=end,
                    text=body,
                )
            )
        if end >= n:
            break
        start = max(end - CHUNK_OVERLAP_CHARS, start + 1)
    return chunks, current_section


def ingest_pdf(pdf_path: Path, meta: dict) -> tuple[DocumentMeta, List[Chunk]]:
    pages = extract_pages(pdf_path)
    empty = sum(1 for p in pages if not p.strip())
    if empty == len(pages):
        raise RuntimeError(
            f"{pdf_path.name}: no extractable text on any page. This looks like a "
            f"scanned PDF; OCR would be required. Refusing to ingest an empty corpus."
        )

    doc = DocumentMeta(
        document_id=meta["document_id"],
        title=meta["title"],
        issuing_org=meta["issuing_org"],
        geographic_scope=meta["geographic_scope"],
        version=meta["version"],
        publication_date=meta["publication_date"],
        source_url=meta["source_url"],
        source_file=pdf_path.name,
        file_sha256=sha256_file(pdf_path),
        page_count=len(pages),
        precedence_rank=meta["precedence_rank"],
        ingested_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        notes=meta.get("notes", ""),
    )

    chunks: List[Chunk] = []
    section: Optional[str] = None
    for i, page_text in enumerate(pages, start=1):
        page_chunks, section = chunk_page(doc.document_id, doc.version, i, page_text, section)
        chunks.extend(page_chunks)
    return doc, chunks


def main() -> int:
    p = argparse.ArgumentParser(description="Ingest a guideline PDF into the RAG corpus.")
    p.add_argument("--pdf", required=True, type=Path)
    p.add_argument("--manifest", required=True, type=Path,
                   help="JSON file of document provenance metadata")
    p.add_argument("--out", type=Path, default=Path("backend/guidelines/data/rag"))
    a = p.parse_args()

    meta = json.loads(a.manifest.read_text(encoding="utf-8"))
    doc, chunks = ingest_pdf(a.pdf, meta)
    a.out.mkdir(parents=True, exist_ok=True)
    payload = {"document": asdict(doc), "chunks": [asdict(c) for c in chunks]}
    out = a.out / f"{doc.document_id}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"{doc.document_id}: {doc.page_count} pages -> {len(chunks)} chunks -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
