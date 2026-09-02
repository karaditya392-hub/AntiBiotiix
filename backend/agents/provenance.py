"""
Origin labelling for every passage that reaches a reader (Spec §21).

THE RULE THIS MODULE EXISTS TO ENFORCE: a reader must never have to work out
where a sentence came from. Guideline evidence and web evidence may sit in the
same answer, but they may never look alike. Each passage carries a printed origin
- the issuing authority and page for a held document, the site and retrieval time
for a web result - and that label travels attached to the passage rather than
being reconstructed by whatever renders it. A label the caller has to assemble is
a label that will eventually be dropped, and the passage will then be read as
carrying an authority nobody gave it.

Web citations are built with the SAME key set as
backend.rag.store.RetrievedChunk.to_citation, plus web-only fields. Downstream
code renders one shape, not two, so a web passage can never slip through a code
path that was only written for guideline passages.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from backend.config import WEB_EVIDENCE_PRECEDENCE_RANK
from backend.rag.store import DOMAIN_READING_CONTRACT, DOMAIN_WEB_UNVERIFIED

# Origin kinds. Carried explicitly on every citation so a renderer never has to
# infer origin from the presence or absence of some other field.
ORIGIN_HELD_CORPUS = "HELD_CORPUS"
ORIGIN_WEB = "WEB_RETRIEVED"

WEB_STANDING_NOTICE = (
    "WEB SOURCE, NOT A HELD GUIDELINE. Retrieved live from the page cited above and "
    "passed by the filtration agent. Not hash-verified and not held by this system. "
    "It may add context to a national guideline and may never replace one."
)


def site_of(url: str) -> str:
    """The host a web passage came from, for printing next to the passage."""
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return "unknown source"
    return host[4:] if host.startswith("www.") else (host or "unknown source")


def source_label(citation: Dict[str, Any]) -> str:
    """
    One line naming where a passage came from, for display beside it.

    Held corpus  ->  "ICMR - National Treatment Guidelines (2019), p. 44"
    Web          ->  "Web - who.int, retrieved 02 Sep 2026"

    Never returns an empty string. A passage whose origin cannot be described is a
    passage that must not be shown, and the caller sees that as the label.
    """
    if not citation:
        return "origin unrecorded - do not cite"

    if citation.get("origin") == ORIGIN_WEB:
        site = citation.get("source_site") or site_of(citation.get("source_url", ""))
        when = citation.get("retrieved_at", "")
        stamp = ""
        if when:
            try:
                stamp = f", retrieved {datetime.fromisoformat(when).strftime('%d %b %Y')}"
            except ValueError:
                stamp = f", retrieved {when}"
        return f"Web - {site}{stamp}"

    issuer = (citation.get("issuing_org") or "").strip()
    title = (citation.get("document_title") or "").strip()
    page = (citation.get("section_page") or "").strip()

    # The issuing body first, because that is the part that carries the authority.
    # An acronym the reader recognises does more work here than the full document
    # title, which is often three lines long.
    short_issuer = issuer.split(",")[0].strip() if issuer else ""
    head = " - ".join(p for p in (short_issuer, title) if p) or "held document"
    return f"{head}, {page}" if page else head


def web_citation(
    *,
    url: str,
    title: str,
    passage: str,
    filter_score: float,
    filter_reason: str,
    filter_model: str,
    site_claimed_publisher: Optional[str] = None,
    published_date: Optional[str] = None,
    retrieved_at: Optional[str] = None,
) -> Dict[str, Any]:
    """
    A web result rendered into the citation shape the rest of the system reads.

    Note what is deliberately NOT claimed here. `issuing_org` records what the page
    says about itself and says so in those words, because we did not verify it.
    `provenance_basis` is UNVERIFIED_WEB_RETRIEVAL rather than the HASH_VERIFIED_PDF
    a held document carries. `section_page` is the URL, since a web page has no
    printed page number to cite and inventing one would fabricate the single field a
    reader uses to check a claim by hand.
    """
    stamp = retrieved_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    claimed = (site_claimed_publisher or "").strip()
    return {
        # --- same keys as a held-corpus citation -------------------------------
        "document_title": title.strip() or "Untitled web page",
        "issuing_org": (
            f"{claimed} (claimed by the page; not verified)" if claimed
            else "Not stated by the page; unverified"
        ),
        "geographic_scope": "Unstated - web source",
        "guideline_version": "n/a - live web retrieval",
        "publication_date": published_date or "Not stated by the page",
        "source_url": url,
        "section_page": url,
        "page_reference_kind": "URL_NOT_A_PRINTED_PAGE",
        "source_type": "WEB_PAGE",
        "provenance_basis": "UNVERIFIED_WEB_RETRIEVAL",
        "verbatim_passage": passage,
        "retrieval_score": round(float(filter_score), 4),
        "provenance_note": filter_reason,
        "precedence_rank": WEB_EVIDENCE_PRECEDENCE_RANK,
        "is_clinical_guideline": False,
        "clinical_domain": DOMAIN_WEB_UNVERIFIED,
        "carries_antimicrobial_authority": False,
        "domain_caveat": DOMAIN_READING_CONTRACT[DOMAIN_WEB_UNVERIFIED],
        "clinical_standing": WEB_STANDING_NOTICE,
        # --- web-only ----------------------------------------------------------
        "origin": ORIGIN_WEB,
        "source_site": site_of(url),
        "retrieved_at": stamp,
        "filter_verdict": "ACCEPTED",
        "filter_score": round(float(filter_score), 4),
        "filter_reason": filter_reason,
        "filter_model": filter_model,
    }


def mark_held(citation: Dict[str, Any]) -> Dict[str, Any]:
    """
    Stamp a held-corpus citation with its origin.

    Held citations predate the agent layer and carry no `origin` key. Rather than
    letting downstream code treat "no origin" as "corpus" - which would silently
    promote any future citation shape that forgot the field - the origin is written
    on explicitly at the point the two kinds first meet.
    """
    out = dict(citation)
    out["origin"] = ORIGIN_HELD_CORPUS
    out.setdefault("source_site", None)
    return out
