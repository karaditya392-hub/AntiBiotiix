"""
Ingest the MoHFW / NHSRC Standard Treatment Guidelines into the RAG corpus.

These twelve documents are national Indian Standard Treatment Guidelines developed
under the Task Force for the Development of STGs for the National Health Mission,
with technical support from NHSRC and NICE International. They are NOT antimicrobial
stewardship guidelines. Most of them -- hypertension, osteoarthritis, dry eye,
alcohol dependence, snakebite, major trauma, recurrent miscarriage, neonatal
jaundice, low birth weight feeding -- say nothing about antimicrobial choice at all.
Three of them -- acute sinusitis, paediatric respiratory infection, the diabetic
foot -- do carry antibiotic recommendations, for their own condition and nothing
wider.

Why this script exists rather than twelve loose manifest files: the corpus JSON is
committed but the source PDFs are not, so this file IS the reproducibility record of
what was ingested and what was claimed about it. Every provenance string below was
read off the document itself. Where a document does not state something -- a date, an
issuing organisation -- the manifest says so instead of supplying a plausible value.

Usage:
    python -m scripts.ingest_mohfw_stg --pdf-dir .cache/mohfw_stg
    python -m scripts.ingest_mohfw_stg --pdf-dir .cache/mohfw_stg --rebuild-index
"""
from __future__ import annotations

import sys

from scripts._guideline_batch import run_batch

# The ministry's own website. Deliberately not a deep link: the operator supplied
# these as bare numeric download files and the URL each came from was not recorded,
# so a per-file URL here would be a guess rendered into clinical citations.
MOHFW_URL = "https://www.mohfw.gov.in/"

_HASH_VERIFIED = (
    "Hash-verified against the copy held by the operator. Page numbers are genuine "
    "pages of this document."
)

_NOT_AMR = (
    "CONDITION-SPECIFIC GUIDELINE, NOT AN ANTIMICROBIAL STEWARDSHIP SOURCE: it carries "
    "no antimicrobial guidance and must never be cited for antimicrobial choice."
)

_GOVERNING = (
    "For antimicrobial choice the ICMR national treatment guidelines and the local "
    "hospital antibiogram remain the governing sources in this system's precedence "
    "hierarchy; this document must not be read as overriding them."
)


def _supplied_as(original: str) -> str:
    return (
        "Supplied by the operator as the download file '" + original + "'; the exact "
        "download URL was not recorded and could not be verified in this environment, "
        "so source_url names the issuing ministry's website rather than a deep link."
    )


MANIFESTS = [
    {
        "document_id": "MOHFW-STG-SNAKEBITE-2016",
        "source_file": "MoHFW_STG_Snakebite_2016.pdf",
        "title": "Standard Treatment Guidelines: Snakebite",
        "issuing_org": (
            "Directorate General of Health Services, Ministry of Health and Family "
            "Welfare, Government of India, with technical support from the National "
            "Health Systems Resource Centre (NHSRC)"
        ),
        "version": "June 2016",
        "publication_date": "2016-06",
        "notes": (
            _HASH_VERIFIED + " Envenomation and antivenom only. " + _NOT_AMR + " It does "
            "mention antibiotic prophylaxis of bite wounds in passing; that guidance is "
            "specific to snakebite wounds and must not be generalized. "
            + _supplied_as("3941.pdf")
        ),
    },
    {
        "document_id": "MOHFW-STG-OA-KNEE-2017",
        "source_file": "MoHFW_STG_Osteoarthritis_Knee_2017.pdf",
        "title": "Standard Treatment Guidelines: Management of Osteoarthritis Knee",
        "issuing_org": "Ministry of Health and Family Welfare, Government of India",
        "version": "January 2017",
        "publication_date": "2017-01",
        "notes": _HASH_VERIFIED + " " + _NOT_AMR + " " + _supplied_as("31911.pdf"),
    },
    {
        "document_id": "MOHFW-STG-NEONATAL-JAUNDICE-2016",
        "source_file": "MoHFW_STG_Neonatal_Hyperbilirubinemia_2016.pdf",
        "title": (
            "Background Document: Detection, management and prevention of "
            "hyperbilirubinemia in term and late preterm newborn infants"
        ),
        "issuing_org": (
            "ISSUING ORGANISATION NOT NAMED ON THE DOCUMENT. Its own methodology section "
            "places it under the Task Force for the Development of Standard Treatment "
            "Guidelines for the National Health Mission, Ministry of Health and Family "
            "Welfare, Government of India"
        ),
        "version": "October 2016 (background document)",
        "publication_date": "2016-10",
        "notes": (
            _HASH_VERIFIED + " ATTRIBUTION IS INFERRED, NOT PRINTED: the title page names "
            "no issuing organisation, and the ministry attribution rests on the document's "
            "own methodology section. WORKING COPY, NOT A FINAL PUBLICATION: its funding "
            "source section reads 'NHSRC?' -- an unresolved placeholder left in the file -- "
            "so this is a pre-final draft and must be cited as one. " + _NOT_AMR + " "
            + _supplied_as("8591.pdf")
        ),
    },
    {
        "document_id": "MOHFW-STG-LBW-FEEDING-UNDATED",
        "source_file": "MoHFW_STG_LBW_Infant_Feeding_undated.pdf",
        "title": "Standard Treatment Guidelines: Optimal Feeding of Low Birth Weight Infants",
        "issuing_org": (
            "Neonatal Guideline Development Group (Secretariat: Department of Pediatrics, "
            "AIIMS, New Delhi); funding source stated as the National Health Systems "
            "Resource Centre (NHSRC), New Delhi. No ministry imprint appears on the title page"
        ),
        "version": "Undated working copy",
        "publication_date": (
            "NOT STATED IN THE DOCUMENT (the embedded source file name is "
            "'LBW guidelines - Oct 2016.docx', which evidences a drafting date only)"
        ),
        "notes": (
            _HASH_VERIFIED + " UNDATED AND UNFINISHED: the title page carries no date, the "
            "foreword reads 'To be developed', and the contributor table reads '(NHSRC team "
            "to fill the names and their roles)'. This is a pre-final working copy and every "
            "citation must say so; it must not be presented as a dated national publication. "
            + _NOT_AMR + " " + _supplied_as("8361.pdf")
        ),
    },
    {
        "document_id": "MOHFW-STG-ACUTE-SINUSITIS-UNDATED",
        "source_file": "MoHFW_STG_Acute_Sinusitis_undated.pdf",
        "title": "Standard Treatment Guidelines on Acute Sinusitis",
        "issuing_org": (
            "Ministry of Health and Family Welfare, Government of India (Standard Treatment "
            "Guidelines programme, National Health Mission). NOTE: the title page of this "
            "file carries no ministry imprint; the attribution comes from the document's own "
            "development section"
        ),
        "version": "Undated (development record runs to January 2016)",
        "publication_date": (
            "NOT STATED IN THE DOCUMENT (its own development record ends January 2016; the "
            "PDF was generated August 2017)"
        ),
        "notes": (
            _HASH_VERIFIED + " CONTAINS ANTIMICROBIAL RECOMMENDATIONS, for acute bacterial "
            "sinusitis only. " + _GOVERNING + " Its recommendations must not be generalized "
            "to any other syndrome, and because the document is undated its currency against "
            "present resistance patterns cannot be assessed from the file. "
            + _supplied_as("4221.pdf")
        ),
    },
    {
        "document_id": "MOHFW-STG-RSA-2017",
        "source_file": "MoHFW_STG_Recurrent_Spontaneous_Abortion_2017.pdf",
        "title": "Standard Treatment Guidelines: Management of Recurrent Spontaneous Abortion",
        "issuing_org": "Ministry of Health and Family Welfare, Government of India",
        "version": "January 2017",
        "publication_date": "2017-01",
        "notes": _HASH_VERIFIED + " " + _NOT_AMR + " " + _supplied_as("3361.pdf"),
    },
    {
        "document_id": "MOHFW-STG-PAED-RESP-INFECTIONS-2016",
        "source_file": "MoHFW_STG_Respiratory_Infections_Children_2016.pdf",
        "title": (
            "Standard Treatment Guidelines: Management of Common Respiratory Infections in "
            "Children in India"
        ),
        "issuing_org": "Ministry of Health and Family Welfare, Government of India",
        "version": "July 2016",
        "publication_date": "2016-07",
        "notes": (
            _HASH_VERIFIED + " CONTAINS ANTIMICROBIAL RECOMMENDATIONS, for paediatric "
            "respiratory infection only, following the WHO/IMNCI assessment algorithm. "
            + _GOVERNING + " Its paediatric dosing must not be generalized to adults or to "
            "other syndromes, and its 2016 agent choices predate the ICMR AMR surveillance "
            "data held in this system. " + _supplied_as("4671.pdf")
        ),
    },
    {
        "document_id": "MOHFW-STG-DIABETIC-FOOT-2016-DRAFT",
        "source_file": "MoHFW_STG_Diabetic_Foot_2016_DRAFT_v3.pdf",
        "title": (
            "Standard Treatment Guidelines: The Diabetic Foot - Prevention and management in "
            "India (Full Background Document, Ver. 3.0, DRAFT)"
        ),
        "issuing_org": "Ministry of Health and Family Welfare, Government of India",
        "version": "Ver. 3.0 DRAFT, January 2016",
        "publication_date": "2016-01 (draft)",
        "notes": (
            _HASH_VERIFIED + " DRAFT, AND SAYS SO ON EVERY PAGE: the running header reads "
            "'The Diabetic Foot - Full Background Document Ver. 3.0 (Draft)'. It has not been "
            "established here whether a final edition superseded it, so every citation drawn "
            "from it must be labelled a draft. CONTAINS ANTIMICROBIAL RECOMMENDATIONS, for "
            "infected diabetic foot ulcer only. " + _GOVERNING + " "
            + _supplied_as("5381.pdf")
        ),
    },
    {
        "document_id": "MOHFW-STG-DRY-EYE-2016",
        "source_file": "MoHFW_STG_Dry_Eye_Disease_2016.pdf",
        "title": (
            "Standard Treatment Guidelines: Dry Eye Disease - Screening, Diagnosis, "
            "Assessment and Management of Dry Eye Disease in India (Full Background Document)"
        ),
        "issuing_org": "Ministry of Health and Family Welfare, Government of India",
        "version": "June 2016",
        "publication_date": "2016-06",
        "notes": _HASH_VERIFIED + " " + _NOT_AMR + " " + _supplied_as("6411.pdf"),
    },
    {
        "document_id": "MOHFW-STG-ALCOHOL-DEPENDENCE-2016",
        "source_file": "MoHFW_STG_Alcohol_Dependence_2016.pdf",
        "title": (
            "Standard Treatment Guidelines: Management of Alcohol Dependence "
            "(Full Background Document)"
        ),
        "issuing_org": "Ministry of Health and Family Welfare, Government of India",
        "version": "February 2016 (full background document, ver. 17-02-16)",
        "publication_date": "2016-02",
        "notes": (
            _HASH_VERIFIED + " " + _NOT_AMR + " It does cover psychotropic and disulfiram "
            "prescribing, which is context for interaction checking but is not antimicrobial "
            "guidance and is not used as a rule source here. " + _supplied_as("7661.pdf")
        ),
    },
    {
        "document_id": "MOHFW-STG-HYPERTENSION-2016",
        "source_file": "MoHFW_STG_Hypertension_2016.pdf",
        "title": (
            "Standard Treatment Guidelines: Screening, Diagnosis, Assessment, and Management "
            "of Primary Hypertension in Adults in India (Background Document)"
        ),
        "issuing_org": "Ministry of Health and Family Welfare, Government of India",
        "version": "March 2016 (background document)",
        "publication_date": "2016-03",
        "notes": (
            _HASH_VERIFIED + " " + _NOT_AMR + " It does cover antihypertensive prescribing, "
            "which is context for interaction and renal-dosing discussion but is not "
            "antimicrobial guidance and is not used as a rule source here. "
            + _supplied_as("5191.pdf")
        ),
    },
    {
        "document_id": "MOHFW-STG-MAJOR-TRAUMA-UNDATED",
        "source_file": "MoHFW_STG_Major_Trauma_undated.pdf",
        "title": "Standard Treatment Guidelines: Major Trauma",
        "issuing_org": "Ministry of Health and Family Welfare, Government of India",
        "version": "Undated (embedded file name records ver. 5.0)",
        "publication_date": (
            "NOT STATED IN THE DOCUMENT (its own development record runs to January 2017; "
            "the PDF was generated August 2017)"
        ),
        "notes": (
            _HASH_VERIFIED + " " + _NOT_AMR + " KNOWN DEFECT IN THE SOURCE: its 'How this STG "
            "was developed' section carries sentences copied from the diabetic foot guideline "
            "and refers to 'the diabetic foot guideline' by name. That section describes the "
            "wrong document and must not be cited as the development record of this one; the "
            "clinical recommendation sections are unaffected. " + _supplied_as("9451.pdf")
        ),
    },
]

COMMON = {
    "geographic_scope": "National (India)",
    "source_url": MOHFW_URL,
    # National-level Indian guidance, the same rank the ICMR sources hold. The scope
    # notes above, not the rank, are what stop a dry eye document being read as
    # antimicrobial guidance: rank only orders documents that have already cleared
    # relevance in backend.guidelines.cross_source.
    "precedence_rank": 2,
    "source_type": "OFFICIAL_PDF",
    "page_reference_kind": "OFFICIAL_DOCUMENT_PAGE",
    "provenance_basis": "HASH_VERIFIED_PDF",
    # Every document in this batch is condition-specific clinical guidance. None is
    # an antimicrobial guideline, including the three that carry antibiotic
    # recommendations for their own condition -- those are listed in
    # backend.config.ANTIMICROBIAL_CONTENT_DOCUMENT_IDS, which is a separate claim.
    # Set here rather than left to the default: the default is
    # ANTIMICROBIAL_TREATMENT, which for this batch would be false.
    "clinical_domain": "CLINICAL_CONDITION_SPECIFIC",
}


def main() -> int:
    return run_batch(
        MANIFESTS, COMMON,
        default_pdf_dir=".cache/mohfw_stg",
        description="Ingest the MoHFW STG set into the RAG corpus.",
    )


if __name__ == "__main__":
    sys.exit(main())
