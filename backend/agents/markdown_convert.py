"""
Document -> Markdown conversion, the first node of the ingestion pipeline.

WHY MARKDOWN RATHER THAN THE RAW TEXT EXTRACTION THIS SYSTEM USED BEFORE.
`page.get_text("text")` returns a flat string. Every heading, every table row and
every list item arrives as an undifferentiated line, and the structure that told a
reader "this dose applies to the paediatric column" is gone before the chunker
ever sees it. That structure is not decoration in a treatment guideline -- a dose
detached from its column header is a dose attached to the wrong patient.

So the pipeline converts to Markdown FIRST and chunks the Markdown. Headings
become `#` levels, so a chunk carries the section it belongs to. Tables become
pipe tables, so a susceptibility row keeps its column names inside the same
chunk. The Markdown is also what the clinician gets back: a file they can read,
diff and check against the PDF, which is the only way anyone can verify that what
was indexed is what the document actually said.

WHAT THIS MODULE MUST NEVER DO: invent content. Every character in the output
came from the document. The only transformations are structural markers (`#`,
`|`, `-`), whitespace normalisation, and the ligature repair that
`backend.rag.textrepair` already applies -- undoing extraction damage, never
paraphrasing. A converter that "cleaned up" a sentence would be a converter that
put words into a national guideline's mouth.

TABLES ARE EXTRACTED BEFORE TEXT AND THEIR REGIONS ARE THEN EXCLUDED. Otherwise
every cell appears twice: once inside the pipe table and again as loose prose
under it, and the duplicate is what a chunker would index.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend import config

# A heading is a line whose glyphs are meaningfully larger than the page's body
# text. "Meaningfully" is a ratio rather than an absolute point size because these
# documents are set at anything from 8pt to 12pt body.
H1_RATIO = 1.55
H2_RATIO = 1.28
H3_RATIO = 1.12

# A run of text longer than this is prose, whatever size it is set in. Without the
# cap, a document whose body text is a single large font turns every paragraph
# into an `#` heading and the outline becomes noise.
MAX_HEADING_CHARS = 110

# A true bullet glyph needs no trailing space -- PDFs routinely emit "•Text".
# A hyphen, asterisk or dash does need one, because "-based" and "5-10 mg" start
# lines in these documents and neither is a list item.
_BULLET_START = re.compile("^\\s*(?:[•●▪‣⁃·]\\s*|[-*–—]\\s+)")
_NUMBERED_START = re.compile(r"^\s*(\d{1,2}[.)]|\([a-z]\)|[a-z][.)])\s+")
_PIPE = re.compile(r"\|")

# Symbol and Wingdings bullets extract as Unicode PRIVATE USE AREA code points --
# characters with no meaning outside the font that produced them. Left alone they
# reach the reader as invisible boxes, and the list they marked reads as one run-on
# paragraph. Mapped here to the real characters they were drawn as, which is
# extraction repair in the same sense as backend.rag.textrepair: the document drew
# a bullet, and this records that it drew a bullet.
_PUA_GLYPHS = {
    "": "•",  # Symbol bullet
    "": "▪",  # Symbol square bullet
    "": "▪",  # Wingdings square
    "": "→",  # Symbol arrowhead
    "": "→",  # Wingdings arrow
    "": "✓",  # Wingdings check
    "": "✗",  # Wingdings cross
    "": "-",       # Symbol minus
    "": "°",  # Symbol degree
    "": "±",  # Symbol plus-minus
    "": "≥",  # Symbol greater-or-equal
    "": "≤",  # Symbol less-or-equal
    "": "→",  # Symbol right arrow
    "": "•",  # Symbol bullet variant
}
_PUA_RANGE = re.compile("[-]")


def _map_private_use(text: str) -> str:
    """Replace private-use glyphs with what the font drew; drop the unmappable."""
    if not _PUA_RANGE.search(text):
        return text
    return _PUA_RANGE.sub(lambda m: _PUA_GLYPHS.get(m.group(0), ""), text)


@dataclass
class MarkdownPage:
    """One page as Markdown, plus the plain text of that same page."""
    number: Optional[int]
    markdown: str
    plain: str
    headings: List[str] = field(default_factory=list)
    table_count: int = 0


@dataclass
class MarkdownDocument:
    markdown: str
    pages: List[MarkdownPage]
    heading_count: int = 0
    table_count: int = 0
    converter: str = ""
    truncated_at_page: Optional[int] = None
    notes: List[str] = field(default_factory=list)

    @property
    def char_count(self) -> int:
        return len(self.markdown)

    @property
    def page_count(self) -> Optional[int]:
        return len(self.pages) if self.pages and self.pages[0].number is not None else None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "converter": self.converter,
            "characters": self.char_count,
            "pages": self.page_count,
            "headings_detected": self.heading_count,
            "tables_detected": self.table_count,
            "truncated_at_page": self.truncated_at_page,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Table rendering
# ---------------------------------------------------------------------------

def _cell(value: Any) -> str:
    """
    One table cell, safe to place inside a pipe table.

    A literal `|` inside a cell would end the column early and silently shift
    every value in the row one place left -- which in a dosing table means a dose
    rendered against the wrong drug.
    """
    text = "" if value is None else str(value)
    text = _PIPE.sub("\\|", _map_private_use(text))
    return re.sub(r"\s+", " ", text).strip()


def _table_to_markdown(rows: List[List[Any]]) -> str:
    """
    A GFM pipe table, or an empty string when there is nothing tabular here.

    Ragged rows are padded rather than dropped: a table row with a missing cell is
    still evidence, and dropping it would remove a line from a guideline without
    telling anyone.
    """
    cleaned = [[_cell(c) for c in row] for row in rows if row is not None]
    cleaned = [r for r in cleaned if any(c for c in r)]
    if len(cleaned) < 2:
        return ""

    width = max(len(r) for r in cleaned)
    if width < 2:
        return ""
    cleaned = [r + [""] * (width - len(r)) for r in cleaned]

    header, *body = cleaned
    # A header row of entirely empty cells produces a table nothing can be read
    # against, so number the columns instead of shipping a blank header.
    if not any(header):
        header = [f"col {i + 1}" for i in range(width)]

    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    lines.extend("| " + " | ".join(r) + " |" for r in body)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Line classification
# ---------------------------------------------------------------------------

def _heading_level(size: float, body_size: float, text: str, bold: bool) -> Optional[int]:
    """
    The `#` level for a line, or None when it is body text.

    Size is the primary signal and bold is a tie-breaker for documents that set
    their headings in the body size -- which the MoHFW standard treatment
    guidelines do throughout.
    """
    stripped = text.strip()
    if not stripped or len(stripped) > MAX_HEADING_CHARS:
        return None
    if stripped.endswith((".", ";", ",")):
        return None
    if body_size <= 0:
        return None

    ratio = size / body_size
    if ratio >= H1_RATIO:
        return 1
    if ratio >= H2_RATIO:
        return 2
    if ratio >= H3_RATIO:
        return 3

    # Same size as the body: only a numbered or fully-capitalised bold line counts.
    if bold and (re.match(r"^\d+(\.\d+)*\s+\S", stripped) or stripped.isupper()):
        return 3
    return None


def _line_markdown(text: str, level: Optional[int]) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    if level:
        return f"{'#' * level} {stripped}"
    if _BULLET_START.match(stripped):
        return "- " + _BULLET_START.sub("", stripped)
    matched = _NUMBERED_START.match(stripped)
    if matched:
        return f"{matched.group(1).rstrip('.)')}. " + _NUMBERED_START.sub("", stripped)
    return stripped


# ---------------------------------------------------------------------------
# PDF -> Markdown
# ---------------------------------------------------------------------------

def _spans_to_lines(page_dict: Dict[str, Any], exclude: List[Tuple[float, float, float, float]]):
    """
    Page lines as (text, max_font_size, any_bold, y_position).

    Lines whose midpoint falls inside a table's bounding box are dropped: they were
    already emitted as table rows, and emitting them again would double every cell
    in the index.
    """
    out = []
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            text = "".join(s.get("text", "") for s in spans)
            if not text.strip():
                continue
            bbox = line.get("bbox") or [0, 0, 0, 0]
            mid_x = (bbox[0] + bbox[2]) / 2
            mid_y = (bbox[1] + bbox[3]) / 2
            if any(x0 <= mid_x <= x1 and y0 <= mid_y <= y1 for (x0, y0, x1, y1) in exclude):
                continue
            size = max(float(s.get("size", 0) or 0) for s in spans)
            bold = any("bold" in str(s.get("font", "")).lower() or (int(s.get("flags", 0)) & 16)
                       for s in spans)
            out.append((text, size, bold, bbox[1]))
    return out


def _body_font_size(lines) -> float:
    """
    The size most of the page's characters are set in.

    Weighted by character count, not by line count: a page with one long paragraph
    and eight short headers has a body size determined by the paragraph.
    """
    weights: Dict[float, int] = {}
    for text, size, _bold, _y in lines:
        key = round(size, 1)
        weights[key] = weights.get(key, 0) + len(text.strip())
    if not weights:
        return 0.0
    return max(weights.items(), key=lambda kv: kv[1])[0]


def _page_markdown(page, repair_fn) -> MarkdownPage:
    tables_md: List[str] = []
    exclude: List[Tuple[float, float, float, float]] = []

    try:
        found = page.find_tables()
        for table in found.tables:
            rendered = _table_to_markdown(table.extract())
            if rendered:
                tables_md.append(rendered)
                exclude.append(tuple(table.bbox))
    except Exception:
        # Table detection is a best effort. A page whose tables cannot be parsed
        # still yields its text, which is strictly better than failing the page.
        tables_md, exclude = [], []

    page_dict = page.get_text("dict")
    lines = _spans_to_lines(page_dict, exclude)
    body_size = _body_font_size(lines)

    parts: List[str] = []
    headings: List[str] = []
    plain_parts: List[str] = []
    buffer: List[str] = []

    def flush() -> None:
        if buffer:
            parts.append(" ".join(buffer).strip())
            buffer.clear()

    for text, size, bold, _y in lines:
        repaired = _map_private_use(repair_fn(text))
        stripped = repaired.strip()
        if not stripped:
            continue
        plain_parts.append(stripped)
        level = _heading_level(size, body_size, stripped, bold)
        if level:
            flush()
            headings.append(stripped)
            parts.append(_line_markdown(stripped, level))
            continue
        rendered = _line_markdown(stripped, None)
        if rendered.startswith(("- ", "1. ")) or re.match(r"^\d+\. ", rendered):
            flush()
            parts.append(rendered)
        else:
            buffer.append(rendered)
    flush()

    if tables_md:
        parts.append("")
        parts.extend(tables_md)
        plain_parts.extend(tables_md)

    markdown = "\n\n".join(p for p in parts if p.strip())
    return MarkdownPage(
        number=page.number + 1,
        markdown=markdown,
        plain="\n".join(plain_parts),
        headings=headings,
        table_count=len(tables_md),
    )


def pdf_to_markdown(pdf_path: Path, max_pages: Optional[int] = None) -> MarkdownDocument:
    """
    Convert a PDF to Markdown, page by page, preserving headings and tables.

    Raises rather than returning an empty document when nothing is extractable --
    the same refusal `backend.rag.ingest.ingest_pdf` makes, and for the same
    reason: a scanned PDF indexed as an empty document is a document the corpus
    claims to hold and cannot quote.
    """
    import pymupdf

    from backend.rag.textrepair import build_dictionary, repair

    limit = max_pages if max_pages is not None else config.MARKDOWN_MAX_PAGES

    doc = pymupdf.open(str(pdf_path))
    total = doc.page_count
    cap = min(total, limit) if limit and limit > 0 else total

    # The repair dictionary is built from the WHOLE document even when only part of
    # it is converted: a word that extracted cleanly on page 300 is what repairs the
    # same word broken on page 2, and narrowing the sample weakens every page.
    raw_pages = [doc[i].get_text("text") for i in range(total)]
    vocab = build_dictionary(raw_pages)

    def repair_fn(text: str) -> str:
        fixed, _stats = repair(text, vocab)
        return fixed

    pages: List[MarkdownPage] = []
    for index in range(cap):
        try:
            pages.append(_page_markdown(doc[index], repair_fn))
        except Exception:
            # One unreadable page must not lose the other 300. Recorded as an empty
            # page so the page numbering downstream still lines up with the PDF.
            pages.append(MarkdownPage(number=index + 1, markdown="", plain=""))

    if not any(p.markdown.strip() for p in pages):
        raise RuntimeError(
            f"{pdf_path.name}: no extractable text on any page. This looks like a "
            f"scanned PDF; OCR would be required. Refusing to ingest an empty corpus."
        )

    notes: List[str] = []
    truncated = None
    if cap < total:
        truncated = cap
        notes.append(
            f"Converted the first {cap} of {total} pages. The remainder was not indexed; "
            f"raise MARKDOWN_MAX_PAGES to ingest the whole document."
        )

    body = "\n\n".join(
        f"<!-- page {p.number} -->\n\n{p.markdown}" for p in pages if p.markdown.strip()
    )
    return MarkdownDocument(
        markdown=body,
        pages=pages,
        heading_count=sum(len(p.headings) for p in pages),
        table_count=sum(p.table_count for p in pages),
        converter="pymupdf-structural-markdown-v1",
        truncated_at_page=truncated,
        notes=notes,
    )


def text_to_markdown(txt_path: Path) -> MarkdownDocument:
    """
    A plain-text or Markdown upload, normalised.

    A `.md` file is already Markdown and is passed through with its structure
    intact. A `.txt` file gets the same line classification the PDF path applies,
    minus the font signals it does not have -- so ALL-CAPS lines and numbered
    headers become headings and bullets become list items, and nothing else moves.
    """
    raw = txt_path.read_text(encoding="utf-8", errors="replace")
    if not raw.strip():
        raise RuntimeError(f"{txt_path.name}: file is empty. Refusing to ingest an empty corpus.")

    if txt_path.suffix.lower() in (".md", ".markdown"):
        markdown = raw.replace("\r\n", "\n").strip()
        headings = [ln for ln in markdown.split("\n") if ln.startswith("#")]
        return MarkdownDocument(
            markdown=markdown,
            pages=[MarkdownPage(number=None, markdown=markdown, plain=markdown, headings=headings)],
            heading_count=len(headings),
            table_count=markdown.count("\n| ---"),
            converter="markdown-passthrough-v1",
        )

    parts: List[str] = []
    headings: List[str] = []
    buffer: List[str] = []

    def flush() -> None:
        if buffer:
            parts.append(" ".join(buffer).strip())
            buffer.clear()

    for line in raw.replace("\r\n", "\n").split("\n"):
        stripped = re.sub(r"[ \t]+", " ", line).strip()
        if not stripped:
            flush()
            continue
        is_heading = (
            len(stripped) <= MAX_HEADING_CHARS
            and not stripped.endswith((".", ",", ";"))
            and (stripped.isupper() or bool(re.match(r"^\d+(\.\d+)*\s+[A-Z]", stripped)))
        )
        if is_heading:
            flush()
            headings.append(stripped)
            parts.append(f"## {stripped}")
        elif _BULLET_START.match(stripped) or _NUMBERED_START.match(stripped):
            flush()
            parts.append(_line_markdown(stripped, None))
        else:
            buffer.append(stripped)
    flush()

    markdown = "\n\n".join(p for p in parts if p.strip())
    return MarkdownDocument(
        markdown=markdown,
        pages=[MarkdownPage(number=None, markdown=markdown, plain=raw.strip(), headings=headings)],
        heading_count=len(headings),
        converter="plaintext-structural-markdown-v1",
    )


def convert(path: Path, max_pages: Optional[int] = None) -> MarkdownDocument:
    """Dispatch on suffix. The one entry point the ingestion pipeline calls."""
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        return pdf_to_markdown(Path(path), max_pages=max_pages)
    return text_to_markdown(Path(path))
