"""
Assign `clinical_domain` to the 39 documents ingested before that field existed.

WHY THIS IS A SCRIPT AND NOT A RE-INGEST
The source PDFs for those documents are not committed -- only the corpus JSON
derived from them. They cannot be re-ingested here, so the field is written into
the existing corpus JSON in place, and this file is the record of what was
written and on what evidence. The manifests in scripts/ingest_mohfw_stg.py and
scripts/ingest_national_guidelines.py have been updated to match, so a future
re-ingest from the original PDFs reproduces these values rather than falling back
to the default.

WHY THE DEFAULT WAS NOT LEFT ALONE
backend.rag.ingest.DocumentMeta defaults clinical_domain to ANTIMICROBIAL_TREATMENT
so that the field's introduction changes nothing for documents that predate it.
For the primary antimicrobial sources that default is correct. For the rest of the
legacy corpus it is a false claim: a dry eye guideline, a hypertension guideline
and an unattributed Ayurvedic compilation are not antimicrobial sources, and
leaving them labelled as such would have made the new domain axis assert something
the corpus contradicts -- the precise failure the axis was added to prevent.

EVIDENCE
Every assignment below is taken from the document's OWN provenance note, already
recorded in the corpus at ingestion time. Nothing here is a fresh reading of a
source document, and nothing is inferred from a title. The note text that decides
each group is quoted in the group comment.

Usage:
    python -m scripts.backfill_clinical_domains --check
    python -m scripts.backfill_clinical_domains --apply
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Dict

from backend.rag.store import (
    DOMAIN_ANTIMICROBIAL,
    DOMAIN_CLINICAL_OTHER,
    DOMAIN_PUBLIC_INFORMATION,
)

RAG_DIR = pathlib.Path("backend/guidelines/data/rag")

# Documents whose own subject is antimicrobial therapy. These are the sources a
# clinician consults TO CHOOSE an antimicrobial, and the only legacy documents for
# which the ANTIMICROBIAL_TREATMENT default was already correct.
_ANTIMICROBIAL = {
    "ICMR-STG-2019-ED2",
    "NCDC-NTG-AMR-2016",
    "WHO-AWARE-BOOK-2022",
    "ICMR-STG-2022-23-CH05-IAI",
    "ICMR-STG-2022-23-CH06-SSTI",
    "ICMR-STG-2022-23-CH07-BJI",
    "ICMR-STG-2022-23-CH08-CNS",
    "ICMR-STG-2022-23-CH09-UTI",
    "ICMR-STG-2022-23-CH10-HAI",
    "ICMR-STG-2022-23-CH11-IMM",
}

# Not clinical guidelines at all, and already held at precedence rank 4: a community
# mass-drug-administration leaflet, a 2006 public fact sheet, and a compilation whose
# issuing body could not be established from the document itself.
_PUBLIC_INFORMATION = {
    "NVBDCP-LF-DRUG-DISTRIBUTORS-UNDATED",
    "MOHFW-CHIKUNGUNYA-FACTS-2006",
    "AYURVEDA-STG-UNATTRIBUTED-UNDATED",
}

# Everything else in the legacy corpus is condition-specific clinical guidance:
# the 12 MoHFW/NHSRC Standard Treatment Guidelines, the ICMR Standard Treatment
# Workflows (whose own note says "NOT an antimicrobial stewardship guideline"), and
# the national programme guidelines. Several of them DO carry antibacterial regimens
# for their own condition -- leptospirosis, RTI/STI, acute sinusitis, paediatric
# respiratory infection, diabetic foot, burns, AES/JE, leprosy MO training and
# intraocular surgery prophylaxis. That is recorded separately, in
# backend.config.ANTIMICROBIAL_CONTENT_DOCUMENT_IDS, because "names antibiotics for
# its own condition" and "is an antimicrobial guideline" are different claims and
# only the second one belongs in the domain.


def planned() -> Dict[str, str]:
    """document_id -> domain, for every document currently in the corpus JSON."""
    out: Dict[str, str] = {}
    for f in sorted(RAG_DIR.glob("*.json")):
        payload = json.loads(f.read_text(encoding="utf-8"))
        doc = payload["document"]
        doc_id = doc["document_id"]
        # A document that already declares a domain was ingested with one and is
        # left exactly as its manifest set it.
        if "clinical_domain" in doc:
            continue
        if doc_id in _ANTIMICROBIAL:
            out[doc_id] = DOMAIN_ANTIMICROBIAL
        elif doc_id in _PUBLIC_INFORMATION:
            out[doc_id] = DOMAIN_PUBLIC_INFORMATION
        else:
            out[doc_id] = DOMAIN_CLINICAL_OTHER
    return out


def apply(plan: Dict[str, str]) -> int:
    written = 0
    for f in sorted(RAG_DIR.glob("*.json")):
        payload = json.loads(f.read_text(encoding="utf-8"))
        doc_id = payload["document"]["document_id"]
        if doc_id not in plan:
            continue
        payload["document"]["clinical_domain"] = plan[doc_id]
        f.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        written += 1
    return written


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="show what would be written")
    g.add_argument("--apply", action="store_true", help="write the field into the corpus JSON")
    a = p.parse_args()

    if not RAG_DIR.exists():
        print(f"REFUSING: {RAG_DIR} does not exist. Run from the repository root.")
        return 1

    plan = planned()
    if not plan:
        print("Every document in the corpus already declares a clinical_domain. Nothing to do.")
        return 0

    unknown = sorted((_ANTIMICROBIAL | _PUBLIC_INFORMATION) - set(plan))
    for doc_id in unknown:
        # Named here but absent from the corpus, or already carrying a domain. Either
        # way, silently skipping it would hide a drift between this script and the
        # corpus it describes.
        print(f"  NOTE: {doc_id} is named in this script but needed no backfill")

    by_domain: Dict[str, int] = {}
    for domain in plan.values():
        by_domain[domain] = by_domain.get(domain, 0) + 1
    for doc_id, domain in sorted(plan.items(), key=lambda kv: (kv[1], kv[0])):
        print(f"  {domain:<34} {doc_id}")
    print(f"\n{len(plan)} document(s) to backfill: {by_domain}")

    if a.check:
        print("\n--check only. Nothing written.")
        return 0

    written = apply(plan)
    print(f"\nwrote clinical_domain into {written} corpus file(s)")
    print(
        "The vector index is unaffected: this changes document metadata only, not chunk "
        "text or chunk count, so no re-embedding is required."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
