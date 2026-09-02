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
    page: Optional[int]
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
    page_count: Optional[int]
    precedence_rank: int
    ingested_at: str
    notes: str = ""
    # How this document reached the corpus, and therefore how much a citation
    # drawn from it is worth. An official PDF yields a real page in a real
    # edition; a transcription does not, and must not be rendered as though it
    # does. See backend.rag.store.PAGE_* for the rendering contract.
    source_type: str = "OFFICIAL_PDF"
    page_reference_kind: str = "OFFICIAL_DOCUMENT_PAGE"
    provenance_basis: str = "HASH_VERIFIED_PDF"
    # What the document is authoritative ABOUT. Defaults to the antimicrobial
    # domain because every document ingested before this field existed is an
    # antimicrobial source; see backend.rag.store.DOMAIN_* for the full set and
    # the reading contract attached to each.
    clinical_domain: str = "ANTIMICROBIAL_TREATMENT"


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
    document_id: str, version: str, page_no: Optional[int], text: str,
    current_section: Optional[str]
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


_MD_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_MD_PAGE_ANCHOR = re.compile(r"^<!--\s*page\s+(\d+)\s*-->$")


def chunk_markdown(
    document_id: str, version: str, markdown: str,
) -> List[Chunk]:
    """
    Split converted Markdown into chunks that keep their structure.

    THREE RULES, and each exists because breaking it produces a citation that
    misleads:

      1. A TABLE IS NEVER SPLIT. A pipe table cut in half leaves half its rows
         with no column headers, and a susceptibility figure without its column
         header is a figure attached to the wrong organism. An oversized table is
         emitted whole and over-length rather than divided.

      2. THE HEADING TRAIL TRAVELS WITH THE CHUNK. Each chunk records the nearest
         enclosing heading, so a retrieved dose carries the section that
         qualified it. `backend.rag.ingest.chunk_page` inferred this from the
         first few lines of a page; here it is read from the `#` levels, which is
         what the Markdown conversion existed to preserve.

      3. THE PAGE ANCHOR SETS THE PAGE. `<!-- page N -->` comments are written by
         the converter and consumed here, so a chunk cut from Markdown still
         cites the page of the PDF it came from. Anchors are stripped from the
         chunk body: they are machinery, and a passage quoted to a clinician must
         contain only what the document said.
    """
    chunks: List[Chunk] = []
    if not markdown or not markdown.strip():
        return chunks

    heading_trail: List[str] = []
    page: Optional[int] = None
    buffer: List[str] = []
    buffer_len = 0
    cursor = 0
    buffer_start = 0
    section_at_flush: Optional[str] = None

    def current_section() -> Optional[str]:
        return " > ".join(heading_trail[-2:]) if heading_trail else None

    def flush() -> None:
        nonlocal buffer, buffer_len, buffer_start, section_at_flush
        body = "\n\n".join(buffer).strip()
        if len(body) >= MIN_CHUNK_CHARS:
            chunks.append(Chunk(
                document_id=document_id,
                version=version,
                page=page,
                section=section_at_flush,
                char_start=buffer_start,
                char_end=buffer_start + len(body),
                text=body,
            ))
        buffer = []
        buffer_len = 0
        section_at_flush = None

    blocks = markdown.split("\n\n")
    for block in blocks:
        raw = block.strip()
        block_span = len(block) + 2
        start_of_block = cursor
        cursor += block_span
        if not raw:
            continue

        anchor = _MD_PAGE_ANCHOR.match(raw)
        if anchor:
            # A page boundary flushes: a chunk spanning two pages can only cite one
            # of them, and citing the wrong page is worse than a shorter chunk.
            flush()
            page = int(anchor.group(1))
            continue

        heading = _MD_HEADING.match(raw)
        if heading:
            flush()
            level = len(heading.group(1))
            title = heading.group(2).strip()
            del heading_trail[level - 1:]
            heading_trail.append(title)
            if not buffer:
                buffer_start = start_of_block
            section_at_flush = current_section()
            buffer.append(raw)
            buffer_len += len(raw)
            continue

        is_table = raw.startswith("|")
        if not buffer:
            buffer_start = start_of_block
            section_at_flush = current_section()

        # Rule 1: a table that will not fit is emitted on its own, whole.
        if is_table and buffer_len + len(raw) > CHUNK_TARGET_CHARS and buffer:
            flush()
            buffer_start = start_of_block
            section_at_flush = current_section()

        buffer.append(raw)
        buffer_len += len(raw)

        if buffer_len >= CHUNK_TARGET_CHARS and not is_table:
            trail = buffer[-1] if len(buffer) > 1 else ""
            flush()
            # Overlap by carrying the last block forward, so a statement split
            # across a boundary is still retrievable whole from one side of it.
            if trail and len(trail) <= CHUNK_OVERLAP_CHARS * 2 and not trail.startswith("|"):
                buffer = [trail]
                buffer_len = len(trail)
                buffer_start = start_of_block
                section_at_flush = current_section()
    flush()
    return chunks


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
        source_type=meta.get("source_type", "OFFICIAL_PDF"),
        page_reference_kind=meta.get("page_reference_kind", "OFFICIAL_DOCUMENT_PAGE"),
        provenance_basis=meta.get("provenance_basis", "HASH_VERIFIED_PDF"),
        clinical_domain=meta.get("clinical_domain", "ANTIMICROBIAL_TREATMENT"),
    )

    chunks: List[Chunk] = []
    section: Optional[str] = None
    for i, page_text in enumerate(pages, start=1):
        page_chunks, section = chunk_page(doc.document_id, doc.version, i, page_text, section)
        chunks.extend(page_chunks)
    return doc, chunks


def ingest_text(txt_path: Path, meta: dict) -> tuple[DocumentMeta, List[Chunk]]:
    """
    Ingest a plain-text transcription.

    A text file has no pages, so every chunk carries page=None and the document is
    marked NO_PAGINATION. The alternative -- synthesising page numbers from chunk
    order -- would manufacture exactly the false locator this pipeline exists to
    avoid. The file is still hashed: the hash proves which transcription was read,
    even though it says nothing about which edition the text came from.
    """
    raw = txt_path.read_text(encoding="utf-8", errors="replace")
    text = _clean_page_text(raw)
    if not text.strip():
        raise RuntimeError(f"{txt_path.name}: file is empty. Refusing to ingest an empty corpus.")

    doc = DocumentMeta(
        document_id=meta["document_id"],
        title=meta["title"],
        issuing_org=meta["issuing_org"],
        geographic_scope=meta["geographic_scope"],
        version=meta["version"],
        publication_date=meta["publication_date"],
        source_url=meta["source_url"],
        source_file=txt_path.name,
        file_sha256=sha256_file(txt_path),
        page_count=None,
        precedence_rank=meta["precedence_rank"],
        ingested_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        notes=meta.get("notes", ""),
        source_type=meta.get("source_type", "PLAIN_TEXT_TRANSCRIPTION"),
        page_reference_kind=meta.get("page_reference_kind", "NO_PAGINATION"),
        provenance_basis=meta.get("provenance_basis", "OPERATOR_ATTESTATION"),
        clinical_domain=meta.get("clinical_domain", "ANTIMICROBIAL_TREATMENT"),
    )

    chunks, _ = chunk_page(doc.document_id, doc.version, None, text, None)
    return doc, chunks


def main() -> int:
    p = argparse.ArgumentParser(description="Ingest a guideline document into the RAG corpus.")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--pdf", type=Path)
    src.add_argument("--text", type=Path, help="Plain-text transcription (no page numbers)")
    p.add_argument("--manifest", required=True, type=Path,
                   help="JSON file of document provenance metadata")
    p.add_argument("--out", type=Path, default=Path("backend/guidelines/data/rag"))
    a = p.parse_args()

    meta = json.loads(a.manifest.read_text(encoding="utf-8"))
    doc, chunks = ingest_pdf(a.pdf, meta) if a.pdf else ingest_text(a.text, meta)
    a.out.mkdir(parents=True, exist_ok=True)
    payload = {"document": asdict(doc), "chunks": [asdict(c) for c in chunks]}
    out = a.out / f"{doc.document_id}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"{doc.document_id}: {doc.page_count} pages -> {len(chunks)} chunks -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
