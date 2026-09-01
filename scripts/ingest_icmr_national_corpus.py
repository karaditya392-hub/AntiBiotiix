"""
Ingest the ICMR national document corpus supplied by the operator.

FIFTY-FIVE documents, and the batch that changes what this corpus IS. Every
document held before this one was an antimicrobial or condition-specific treatment
guideline. Most of this batch is neither: it is research-ethics governance,
laboratory biosafety, programme policy, oncology consensus guidance and two
research-activity compendia.

That is why `clinical_domain` exists (backend/rag/store.py DOMAIN_*). Precedence
rank says how much weight a document carries in a clinical conflict; it cannot say
what the document is authoritative ABOUT, and without that second axis the ICMR
National Ethical Guidelines and the ICMR antimicrobial guidelines would be
indistinguishable to a caller assembling prescribing evidence. Each manifest below
declares its domain, and backend.rag.store attaches the matching reading contract
to every passage retrieved from it.

WHAT THIS BATCH DOES NOT DO
  - It adds NO antimicrobial authority except ICMR-RICKETTSIAL-2015. Rank 2 here
    means "national clinical guidance on its own condition", not "may be cited for
    antimicrobial choice".
  - It changes NO clinical rule. The rule engine does not import retrieval
    (backend/rag/retrieve.py), and no rule in the catalog cites any document here.
  - It asserts nothing about documents it does not hold. Four supplied files are
    NOT in this manifest because their text could not be extracted; they are listed
    under EXCLUDED below so the omission is a record rather than a silence.

Provenance strings were read off each document's own pages. Where a document states
no publication year in extractable text, the manifest says so and the document_id
carries UNDATED, rather than inheriting a plausible year from its siblings.

Usage:
    python -m scripts.ingest_icmr_national_corpus --pdf-dir <dir>
    python -m scripts.ingest_icmr_national_corpus --pdf-dir <dir> --rebuild-index
"""
from __future__ import annotations

import sys

from scripts._guideline_batch import run_batch

ICMR_URL = "https://www.icmr.gov.in/"
DHR_URL = "https://dhr.gov.in/"

# ---------------------------------------------------------------------------
# Documents supplied but NOT ingested, and why. Recorded here because a corpus
# that silently drops four of fifty-nine files cannot be audited against the set
# the operator actually handed over.
#
#   NARI_Guideline_2022.pdf                 244 pages, zero extractable characters
#   guidelines_GTP.pdf                       22 pages, zero extractable characters
#   1724914698_policy_statement_...1980.pdf  11 pages, 50 extractable characters
#       All three are scanned images. backend.rag.ingest.ingest_pdf refuses them by
#       design; OCR would be required, and OCR output is not a hash-verified page.
#
#   1779363003_operationalguidelines...single ethics review
#       56 pages, 4,461 extractable characters, of which one page carries text and
#       fifty-five are empty. Not refused by the pipeline -- only wholly empty
#       documents are -- but ingesting it would let the corpus report that it holds
#       the Operational Guidelines for Single Ethics Review while holding one page
#       of a foreword. The FAQ on the same guidelines IS held and does extract.
#
#   Prescription_PATIENT-021 / -022
#       Not guideline documents at all: they are this system's own generated patient
#       prescription records. Ingesting them would put patient-visit content into the
#       corpus that answers clinical questions, where a query about pneumonia therapy
#       could retrieve a prescription record as though it were guideline evidence.
#
#   1724842648_ethical_guidelines_application_artificial_intelligence_biomed_rsrch_2023.pdf
#       Byte-different, text-identical duplicate of Ethical_Guidelines_AI_Healthcare_2023.pdf
#       (78 pages, 109,679 vs 109,681 characters). Only one copy is ingested: two
#       copies would return the same passage twice and read as two sources agreeing.
# ---------------------------------------------------------------------------

_HASH_VERIFIED = (
    "Hash-verified against the copy held by the operator. Page numbers are genuine "
    "pages of this document."
)

_GOVERNING = (
    "For antimicrobial choice the national antimicrobial treatment guidelines held "
    "here (ICMR, and NCDC-NTG-AMR-2016) and the local hospital antibiogram govern; "
    "this document must not be read as overriding them."
)

_NOT_CLINICAL = (
    "NOT CLINICAL GUIDANCE. This document is authoritative within its own subject and "
    "says nothing about how a patient should be diagnosed or treated. It is never "
    "evidence for a clinical decision."
)

_ONCOLOGY = (
    "ICMR consensus document on the management of one cancer site, produced by an ICMR "
    "subcommittee. It is national clinical guidance for that cancer and carries NO "
    "antimicrobial authority: where it mentions infection prophylaxis or febrile "
    "neutropenia, that wording is incidental to oncology care. " + _GOVERNING
)

_ONCOLOGY_DISCLAIMER = (
    "The document's own disclaimer states that it represents expert thinking on "
    "available evidence and does not bind a clinician to follow it, and that mention "
    "of a pharmaceutical drug is not an endorsement."
)

_SUPPLIED_NUMERIC = (
    "Supplied by the operator as a bare numeric download file; the exact download URL "
    "was not recorded and could not be verified in this environment, so source_url "
    "names the issuing body's own website rather than a deep link."
)

# Shared by every manifest unless the manifest overrides it.
COMMON = {
    "geographic_scope": "National (India)",
    "source_url": ICMR_URL,
    "precedence_rank": 2,
}

# Rank 4: held and retrievable, deliberately sorted below every clinical guideline.
# See backend.config.GUIDELINE_PRECEDENCE_HIERARCHY rank 4 and
# backend.rag.store.NOT_A_CLINICAL_GUIDELINE_RANK.
_R4 = {"precedence_rank": 4}

D_AMR = "ANTIMICROBIAL_TREATMENT"
D_CLIN = "CLINICAL_CONDITION_SPECIFIC"
D_ETHICS = "RESEARCH_ETHICS_GOVERNANCE"
D_LAB = "LABORATORY_PROCEDURE_BIOSAFETY"
D_POLICY = "PROGRAMME_AND_INSTITUTIONAL_POLICY"
D_REPORT = "RESEARCH_ACTIVITY_REPORT"


def _icmr_ncd(year: str) -> str:
    return (
        "Division of Non Communicable Diseases, Indian Council of Medical Research "
        f"(ICMR), Department of Health Research, Ministry of Health & Family Welfare, "
        f"Government of India, New Delhi ({year})"
    )


def _oncology(doc_id, source_file, site, year, extra=""):
    """One ICMR cancer-site consensus document."""
    return {
        "document_id": doc_id,
        "source_file": source_file,
        "title": f"Consensus Document for Management of {site}",
        "issuing_org": _icmr_ncd(year),
        "version": year,
        "publication_date": year,
        "clinical_domain": D_CLIN,
        "notes": (
            _HASH_VERIFIED + " " + _ONCOLOGY + " " + _ONCOLOGY_DISCLAIMER
            + (" " + extra if extra else "")
        ),
    }


MANIFESTS = [
    # =======================================================================
    # ANTIMICROBIAL. The only document in this batch that carries antimicrobial
    # recommendations as its own subject, and therefore the only one that may be
    # cited for antimicrobial choice.
    # =======================================================================
    {
        "document_id": "DHR-ICMR-RICKETTSIAL-2015",
        "source_file": "DHR-ICMR Guidelines on Ricketesial Diseases.pdf",
        "title": "Guidelines for Diagnosis and Management of Rickettsial Diseases in India",
        "issuing_org": (
            "Department of Health Research (DHR) and Indian Council of Medical Research "
            "(ICMR), Ministry of Health & Family Welfare, Government of India"
        ),
        "version": "February 2015",
        "publication_date": "2015",
        "source_url": DHR_URL,
        "clinical_domain": D_AMR,
        "notes": (
            _HASH_VERIFIED + " CARRIES ANTIMICROBIAL RECOMMENDATIONS, for rickettsial "
            "infections only (doxycycline, azithromycin, chloramphenicol and related "
            "agents). Outside rickettsial disease it has no antimicrobial standing. "
            "Its own disclaimer states the guidance is based on a review of available "
            "evidence and best practices and may be revised. " + _GOVERNING
        ),
    },

    # =======================================================================
    # CONDITION-SPECIFIC CLINICAL GUIDANCE. National clinical documents that
    # govern their own condition and carry no antimicrobial authority.
    # =======================================================================
    {
        "document_id": "ICMR-T1DM-2022",
        "source_file": "ICMR_Guidelines_for_Management_of_Type_1_Diabetes.pdf",
        "title": "Guidelines for Management of Type 1 Diabetes",
        "issuing_org": _icmr_ncd("2022"),
        "version": "2022",
        "publication_date": "2022",
        "clinical_domain": D_CLIN,
        "notes": (
            _HASH_VERIFIED + " Copyright page states 2022. Endocrine guidance. Its text "
            "mentions antimicrobials in the context of diabetic infection, which does NOT "
            "make it an antimicrobial source. " + _GOVERNING
        ),
    },
    {
        "document_id": "ICMR-T2DM-2018",
        "source_file": "ICMR_GuidelinesType2diabetes2018_0.pdf",
        "title": "ICMR Guidelines for Management of Type 2 Diabetes 2018",
        "issuing_org": _icmr_ncd("2018"),
        "version": "2018",
        "publication_date": "2018",
        "clinical_domain": D_CLIN,
        "notes": _HASH_VERIFIED + " Endocrine guidance, no antimicrobial scope. " + _GOVERNING,
    },
    {
        "document_id": "ICMR-CELIAC-DISEASE-UNDATED",
        "source_file": "ICMR - Diagnosis and Managmemnt.pdf",
        "title": "ICMR Guideline on Diagnosis and Management of Celiac Disease in India",
        "issuing_org": _icmr_ncd("undated"),
        "version": (
            "UNDATED: the document states no publication year in extractable text. Its "
            "own account of its development ends with a core writing group meeting in "
            "January 2016, after a public comment period from September to December 2015"
        ),
        "publication_date": "NOT STATED IN THE DOCUMENT",
        "clinical_domain": D_CLIN,
        "notes": (
            _HASH_VERIFIED + " NO PUBLICATION YEAR is claimed because the document states "
            "none in extractable text; the drafting dates above are the document's own "
            "account of its development, not a publication date, and must not be cited as "
            "one. Gastroenterology guidance, no antimicrobial scope. " + _GOVERNING
        ),
    },
    {
        "document_id": "ICMR-DNAR-CONSENSUS-2020",
        "source_file": "1724842795_icmr_consensus_guidelines_do_not_attempt_resuscitation_natl_med_journal.pdf",
        "title": "ICMR Consensus Guidelines on 'Do Not Attempt Resuscitation'",
        "issuing_org": (
            "Indian Council of Medical Research Expert Group on DNAR, published in The "
            "National Medical Journal of India, Vol. 33, No. 2, 2020"
        ),
        "version": "2020 (NMJI Vol. 33, No. 2)",
        "publication_date": "2020",
        "clinical_domain": D_CLIN,
        "notes": (
            _HASH_VERIFIED + " END-OF-LIFE CARE guidance on withholding cardiopulmonary "
            "resuscitation. JOURNAL ARTICLE, not a standalone ICMR guideline publication: "
            "page numbers are pages of this six-page reprint, and the journal's own "
            "pagination begins at 107. No antimicrobial or prescribing scope. "
            + _SUPPLIED_NUMERIC
        ),
    },
    {
        "document_id": "ICMR-HCT-2021",
        "source_file": "Nat_Guide_HCT.pdf",
        "title": "National Guidelines for Hematopoietic Cell Transplantation",
        "issuing_org": (
            "Indian Council of Medical Research (ICMR), Department of Health Research, "
            "Ministry of Health & Family Welfare, Government of India"
        ),
        "version": "2021",
        "publication_date": "2021",
        "clinical_domain": D_CLIN,
        "notes": (
            _HASH_VERIFIED + " Transplantation guidance. Transplant patients receive "
            "antimicrobial prophylaxis and this document may touch on it, but it is not an "
            "antimicrobial guideline and does not set antimicrobial policy. " + _GOVERNING
        ),
    },
    {
        "document_id": "ICMR-STEMCELL-THERAPY-EVIDENCE-2021",
        "source_file": "1745229591_evidence_based_status_of_stem_cell_therapy_for_human_diseases_v1.pdf",
        "title": "Evidence Based Status of Stem Cell Therapy for Human Diseases",
        "issuing_org": (
            "Indian Council of Medical Research (ICMR), Department of Health Research, "
            "Ministry of Health & Family Welfare, Government of India"
        ),
        "version": "2021",
        "publication_date": "2021",
        "clinical_domain": D_CLIN,
        "notes": (
            _HASH_VERIFIED + " EVIDENCE REVIEW, not a treatment guideline: it reports which "
            "stem cell therapies have evidence for which diseases, and much of what it "
            "records is that evidence is absent or insufficient. A passage from it is a "
            "statement about the state of evidence, not a recommendation to treat. "
            + _SUPPLIED_NUMERIC
        ),
    },

    # -- ICMR cancer-site consensus documents -------------------------------
    # Twenty-two documents from the ICMR Task Force on Management of Cancers.
    # National clinical guidance, each on one site. Several discuss infection
    # prophylaxis and febrile neutropenia; none is an antimicrobial authority.
    _oncology("ICMR-CONSENSUS-GALLBLADDER-2014", "GALLBLADDER CANCER_0.pdf",
              "Gallbladder Cancer", "2014"),
    _oncology("ICMR-CONSENSUS-GASTRIC-2014", "Gastric Cancer Final pdf for farrow_0.pdf",
              "Gastric Cancer", "2014",
              "Carries more antimicrobial wording than most of this group, in the context "
              "of Helicobacter pylori eradication and perioperative care. That is gastric "
              "cancer management, not antimicrobial guidance."),
    _oncology("ICMR-CONSENSUS-COLORECTAL-2014", "Colorectal Cancer_0.pdf",
              "Colorectal Cancer", "2014"),
    _oncology("ICMR-CONSENSUS-BUCCAL-MUCOSA-2014", "Buccal Mucosa Cancer final pdf 9.6.14.pdf",
              "Buccal Mucosa Cancer", "2014"),
    _oncology("ICMR-CONSENSUS-ESOPHAGEAL-2017", "Esophagus final ICMR2014_0.pdf",
              "Esophageal Cancer", "2017",
              "The operator's filename says 2014; the document's own title page and "
              "publication statement say 2017, and the document is authoritative about "
              "itself."),
    _oncology("ICMR-CONSENSUS-CERVIX-2016", "Consensus Document for The Management of Cancer Cervix_0.pdf",
              "Cancer Cervix", "2016"),
    _oncology("ICMR-CONSENSUS-PAEDIATRIC-ONCOLOGY-2017", "PEDIATRIC_LYMPHOMAS_AND_SOLID_TUMORS_0.pdf",
              "Pediatric Lymphomas and Solid Tumors", "2017"),
    _oncology("ICMR-CONSENSUS-BREAST-2016", "Breast_Cancer.pdf", "Breast Cancer", "2016"),
    _oncology("ICMR-CONSENSUS-PANCREATIC-2019", "consensu_3.pdf", "Pancreatic Cancer", "2019"),
    _oncology("ICMR-CONSENSUS-HEPATOCELLULAR-2019", "Consensus_Document_1.pdf",
              "Hepatocellular Carcinoma", "2019"),
    _oncology("ICMR-CONSENSUS-NEUROENDOCRINE-2019", "Consensus_2.pdf",
              "Neuroendocrine Tumours (GEP-NETs)", "2019"),
    _oncology("ICMR-CONSENSUS-URINARY-BLADDER-2024", "1736419688_printedubcancerdocument.pdf",
              "Urinary Bladder Cancer", "2024", _SUPPLIED_NUMERIC),
    _oncology("ICMR-CONSENSUS-UTERINE-2019", "Uterine_Cancer.pdf", "Uterine Cancer", "2019"),
    _oncology("ICMR-CONSENSUS-PROSTATE-2023", "Prostate_Cancer_Consensus_Doc.pdf",
              "Prostate Cancer", "2023"),
    _oncology("ICMR-CONSENSUS-SARCOMA-2016", "SARCOMA AND OSTEOSARCOMA final pdf_0.pdf",
              "Soft Tissue Sarcoma and Osteosarcoma", "2016"),
    _oncology("ICMR-CONSENSUS-RETINOBLASTOMA-2023", "RB_Document.pdf", "Retinoblastoma", "2023"),
    _oncology("ICMR-CONSENSUS-OVARIAN-2019", "Ovarian_Cancer.pdf",
              "Epithelial Ovarian Cancer", "2019"),
    _oncology("ICMR-CONSENSUS-MYELOMA-2017", "Multiple Myeloma_0.pdf", "Multiple Myeloma", "2017"),
    _oncology("ICMR-CONSENSUS-NHL-HIGH-GRADE-2016", "NHL-HG 29.06.2016_0.pdf",
              "Non Hodgkin's Lymphoma (High Grade)", "2016"),
    _oncology("ICMR-CONSENSUS-MDS-2019", "MSS_Myelodysplastic_Syndrome_MDS.pdf",
              "Myelodysplastic Syndrome (MDS)", "2019"),
    _oncology("ICMR-CONSENSUS-LARYNX-HYPOPHARYNX-2017", "Larynx and Hypopharynx Cancers_0.pdf",
              "Larynx and Hypopharynx Cancers", "2017"),
    {
        "document_id": "ICMR-CONSENSUS-TONGUE-UNDATED",
        "source_file": "tongue.pdf",
        "title": "Consensus Document for Management of Tongue Cancer",
        "issuing_org": _icmr_ncd("undated"),
        "version": (
            "UNDATED: the title page is a scanned image and no publication year appears "
            "in extractable text. The document states that literature was reviewed to "
            "December 2012 and cites cancer registry reports for 2009-2011"
        ),
        "publication_date": "NOT STATED IN THE DOCUMENT",
        "clinical_domain": D_CLIN,
        "notes": (
            _HASH_VERIFIED + " NO PUBLICATION YEAR is claimed. Its sibling head-and-neck "
            "consensus documents in this batch are dated 2014-2017, and it would have been "
            "easy to assume a year from them; the literature-review cut-off recorded above "
            "is the document's own statement and is NOT a publication date. " + _ONCOLOGY
            + " " + _ONCOLOGY_DISCLAIMER
        ),
    },

    # =======================================================================
    # RESEARCH ETHICS AND GOVERNANCE -- rank 4.
    #
    # These are national authorities, and rank 4 is not a judgement on their
    # standing. They govern how research is proposed, reviewed and conducted;
    # they say nothing about how a patient is treated, so they are not clinical
    # guidelines and must never be assembled into clinical evidence.
    # =======================================================================
    {
        **_R4,
        "document_id": "ICMR-ETHICS-NATIONAL-2017",
        "source_file": "ICMR_Ethical_Guidelines_2017.pdf",
        "title": (
            "National Ethical Guidelines for Biomedical and Health Research Involving "
            "Human Participants"
        ),
        "issuing_org": "Indian Council of Medical Research (ICMR), New Delhi",
        "version": "2017 (ISBN 978-81-910091-94)",
        "publication_date": "October 2017",
        "clinical_domain": D_ETHICS,
        "notes": (
            _HASH_VERIFIED + " THE CURRENT NATIONAL RESEARCH-ETHICS AUTHORITY in this "
            "corpus, and the document that several later addenda held here amend. "
            + _NOT_CLINICAL
        ),
    },
    {
        **_R4,
        "document_id": "ICMR-ETHICS-2006",
        "source_file": "ethical_guidelines_0.pdf",
        "title": "Ethical Guidelines for Biomedical Research on Human Participants",
        "issuing_org": "Indian Council of Medical Research (ICMR), New Delhi",
        "version": "2006",
        "publication_date": "October 2006",
        "clinical_domain": D_ETHICS,
        "notes": (
            _HASH_VERIFIED + " SUPERSEDED EDITION, retained because prior versions are "
            "never overwritten in this corpus. ICMR-ETHICS-NATIONAL-2017 is the later "
            "edition held here. " + _NOT_CLINICAL
        ),
    },
    {
        **_R4,
        "document_id": "ICMR-ETHICS-2000",
        "source_file": "1724914501_ethical_guidelines_for_biomedical_research_on_human_subject_2000.pdf",
        "title": "Ethical Guidelines for Biomedical Research on Human Subjects",
        "issuing_org": "Indian Council of Medical Research (ICMR), New Delhi",
        "version": "2000",
        "publication_date": "2000",
        "clinical_domain": D_ETHICS,
        "notes": (
            _HASH_VERIFIED + " SUPERSEDED EDITION, retained for the same reason as "
            "ICMR-ETHICS-2006. " + _NOT_CLINICAL + " " + _SUPPLIED_NUMERIC
        ),
    },
    {
        **_R4,
        "document_id": "ICMR-ETHICS-CHILDREN-2017",
        "source_file": "National_Ethical_Guidelines_for_BioMedical_Research_Involving_Children_0.pdf",
        "title": "National Ethical Guidelines for Biomedical Research Involving Children",
        "issuing_org": "Indian Council of Medical Research (ICMR), New Delhi",
        "version": "2017",
        "publication_date": "2017",
        "clinical_domain": D_ETHICS,
        "notes": (
            _HASH_VERIFIED + " Research ethics for paediatric participants. This concerns "
            "consent, assent and protection in RESEARCH; it is not paediatric clinical or "
            "paediatric dosing guidance and must never be retrieved as such. " + _NOT_CLINICAL
        ),
    },
    {
        **_R4,
        "document_id": "ICMR-ETHICS-HANDBOOK-2018",
        "source_file": "1724914217_handbook_on_icmr_ethical_guidelines_2018.pdf",
        "title": (
            "Handbook on National Ethical Guidelines for Biomedical and Health Research "
            "Involving Human Participants"
        ),
        "issuing_org": "Indian Council of Medical Research (ICMR), New Delhi",
        "version": "2018",
        "publication_date": "2018",
        "clinical_domain": D_ETHICS,
        "notes": (
            _HASH_VERIFIED + " Companion handbook to ICMR-ETHICS-NATIONAL-2017, not an "
            "independent guideline. " + _NOT_CLINICAL + " " + _SUPPLIED_NUMERIC
        ),
    },
    {
        **_R4,
        "document_id": "ICMR-ETHICS-AI-2023",
        "source_file": "Ethical_Guidelines_AI_Healthcare_2023.pdf",
        "title": (
            "Ethical Guidelines for Application of Artificial Intelligence in Biomedical "
            "Research and Healthcare"
        ),
        "issuing_org": (
            "DHR-ICMR Artificial Intelligence Cell, Indian Council of Medical Research, "
            "New Delhi"
        ),
        "version": "2023 (ISBN 978-93-5811-343-3)",
        "publication_date": "2023",
        "clinical_domain": D_ETHICS,
        "notes": (
            _HASH_VERIFIED + " DIRECTLY RELEVANT TO THIS SYSTEM'S OWN GOVERNANCE: it sets "
            "the national ethical expectations for AI-based clinical decision support, "
            "including accountability, validation and human oversight. It is still a "
            "governance document, not clinical guidance, and holding it does not "
            "constitute a claim that this system complies with it. A byte-different, "
            "text-identical duplicate was supplied as "
            "'1724842648_ethical_guidelines_application_artificial_intelligence_biomed_"
            "rsrch_2023.pdf' and was NOT ingested; two copies would return the same "
            "passage twice and read as two sources agreeing. " + _NOT_CLINICAL
        ),
    },
    {
        **_R4,
        "document_id": "ICMR-ETHICS-JOINT-REVIEW-2023",
        "source_file": "1724842504_final_guidelines_for_joint_ethics_review_at_icmr_v22607.pdf",
        "title": "Guidelines for Joint Ethics Review at ICMR",
        "issuing_org": "ICMR Bioethics Unit, Indian Council of Medical Research, New Delhi",
        "version": "Version 1.0, dated 17 March 2023",
        "publication_date": "2023",
        "clinical_domain": D_ETHICS,
        "notes": _HASH_VERIFIED + " " + _NOT_CLINICAL + " " + _SUPPLIED_NUMERIC,
    },
    {
        **_R4,
        "document_id": "MOHFW-ICMR-ETHICS-LEFTOVER-SAMPLES-2024",
        "source_file": "1732704229_guidelinesforethicaluse.pdf",
        "title": (
            "MoHFW-ICMR Joint Guidelines for Ethical Use of Leftover De-identified/"
            "Anonymous Samples for Commercial Purpose"
        ),
        "issuing_org": (
            "Ministry of Health and Family Welfare and Indian Council of Medical Research, "
            "New Delhi"
        ),
        "version": "Version 1.1, October 2024 (Version 1.0 was December 2023)",
        "publication_date": "October 2024",
        "clinical_domain": D_ETHICS,
        "notes": _HASH_VERIFIED + " " + _NOT_CLINICAL + " " + _SUPPLIED_NUMERIC,
    },
    {
        **_R4,
        "document_id": "ICMR-ETHICS-SYSTEMATIC-REVIEW-ADDENDUM-2024",
        "source_file": "1724842157_ethical_requirements_for_systematic_review_metaanalysis_proposals_an_addendum.pdf",
        "title": (
            "Ethical Requirements for Systematic Review & Meta-Analysis Proposals - An "
            "Addendum to ICMR National Ethical Guidelines for Biomedical and Health "
            "Research Involving Human Participants, 2017"
        ),
        "issuing_org": "Indian Council of Medical Research (ICMR), New Delhi",
        "version": "February 2024",
        "publication_date": "February 2024",
        "clinical_domain": D_ETHICS,
        "notes": (
            _HASH_VERIFIED + " ADDENDUM to ICMR-ETHICS-NATIONAL-2017, which is also held "
            "here; it amends that document rather than standing alone. " + _NOT_CLINICAL
            + " " + _SUPPLIED_NUMERIC
        ),
    },
    {
        **_R4,
        "document_id": "ICMR-ETHICS-LAB-VALIDATION-2024",
        "source_file": "1724842064_guidance_on_ethical_requirements_for_laboratory_validation_testing.pdf",
        "title": "Guidance on Ethical Requirements for Laboratory Validation Testing",
        "issuing_org": "Indian Council of Medical Research (ICMR), New Delhi",
        "version": "February 2024",
        "publication_date": "February 2024",
        "clinical_domain": D_ETHICS,
        "notes": (
            _HASH_VERIFIED + " Concerns the ETHICS of validation studies, not how to perform "
            "or interpret a laboratory test. " + _NOT_CLINICAL + " " + _SUPPLIED_NUMERIC
        ),
    },
    {
        **_R4,
        "document_id": "ICMR-ETHICS-INTEGRATIVE-MEDICINE-ADDENDUM-2025",
        "source_file": "1740984016_icmraddendumethicalrequirementsforresearchinintegrativemedicine.pdf",
        "title": (
            "Ethical Requirements for Research in Integrative Medicine - An Addendum to "
            "ICMR National Ethical Guidelines for Biomedical and Health Research Involving "
            "Human Participants, 2017"
        ),
        "issuing_org": "Indian Council of Medical Research (ICMR), New Delhi",
        "version": "March 2025",
        "publication_date": "March 2025",
        "clinical_domain": D_ETHICS,
        "notes": (
            _HASH_VERIFIED + " ADDENDUM to ICMR-ETHICS-NATIONAL-2017. Concerns the ethics of "
            "RESEARCH involving Ayush practices; it is not a source of Ayurvedic or "
            "integrative treatment guidance, and must not be confused with "
            "AYURVEDA-STG-UNATTRIBUTED-UNDATED, which is held separately and is also not a "
            "clinical guideline. " + _NOT_CLINICAL + " " + _SUPPLIED_NUMERIC
        ),
    },
    {
        **_R4,
        "document_id": "ICMR-IAEC-FAQ-2025",
        "source_file": "1744029514_final_faq_iaecapproval1_1.pdf",
        "title": "Frequently Asked Questions: Institutional Animal Ethics Committees (IAEC)",
        "issuing_org": "Indian Council of Medical Research (ICMR), New Delhi",
        "version": "2025",
        "publication_date": "2025",
        "clinical_domain": D_ETHICS,
        "notes": (
            _HASH_VERIFIED + " ANIMAL research ethics, in FAQ form. It concerns neither human "
            "participants nor patient care. " + _NOT_CLINICAL + " " + _SUPPLIED_NUMERIC
        ),
    },
    {
        **_R4,
        "document_id": "ICMR-SINGLE-ETHICS-REVIEW-FAQ-2026",
        "source_file": "1785836796_frequentlyaskedquestions.pdf",
        "title": (
            "Frequently Asked Questions on Operational Guidelines for Single Ethics Review "
            "of Multicentre Research in India"
        ),
        "issuing_org": "Indian Council of Medical Research (ICMR), New Delhi",
        "version": "2026",
        "publication_date": "2026",
        "clinical_domain": D_ETHICS,
        "notes": (
            _HASH_VERIFIED + " FAQ ONLY. The Operational Guidelines this FAQ explains were "
            "also supplied but could NOT be ingested: 55 of their 56 pages hold no "
            "extractable text. The corpus therefore holds the explanation of that document "
            "and not the document itself, and must not be described as holding the "
            "Operational Guidelines. " + _NOT_CLINICAL + " " + _SUPPLIED_NUMERIC
        ),
    },
    {
        **_R4,
        "document_id": "ICMR-CHIS-POLICY-2023",
        "source_file": "ICMR_CHIS _Policy_Document.pdf",
        "title": (
            "ICMR Policy Statement on the Ethical Conduct of Controlled Human Infection "
            "Studies (CHIS) in India"
        ),
        "issuing_org": "ICMR Bioethics Unit, Indian Council of Medical Research, New Delhi",
        "version": "2023 (ISBN 978-81-965854-4-0)",
        "publication_date": "December 2023",
        "clinical_domain": D_ETHICS,
        "notes": (
            _HASH_VERIFIED + " Governs the ETHICAL CONDUCT of studies in which participants "
            "are deliberately infected. It concerns research design and oversight, not the "
            "treatment of infection, and is never evidence about managing an infection in a "
            "patient. " + _NOT_CLINICAL
        ),
    },

    # =======================================================================
    # LABORATORY PROCEDURE AND BIOSAFETY -- rank 4.
    # =======================================================================
    {
        **_R4,
        "document_id": "ICMR-BSL3-GENERAL-UNDATED",
        "source_file": "Revised_ICMR_Guidelines_2_December.pdf",
        "title": "General Guidelines for Establishment of Biosafety Level-3 Laboratory",
        "issuing_org": (
            "Indian Council of Medical Research, Department of Health Research, Ministry of "
            "Health & Family Welfare, Government of India, New Delhi"
        ),
        "version": (
            "UNDATED: the document states no publication year or version number in "
            "extractable text. The operator's filename is 'Revised_ICMR_Guidelines_2_"
            "December.pdf', which is not a statement by the document"
        ),
        "publication_date": "NOT STATED IN THE DOCUMENT",
        "clinical_domain": D_LAB,
        "notes": (
            _HASH_VERIFIED + " 31 pages. A SEPARATE AND LONGER BSL-3 document is also held "
            "as ICMR-BSL3-V3 (112 pages). This system does not assert which supersedes "
            "which: neither states a version this pipeline could verify, and inferring an "
            "order from page count or filename would be a claim about editions rather than "
            "a fact from them. " + _NOT_CLINICAL
        ),
    },
    {
        **_R4,
        "document_id": "ICMR-BSL3-V3",
        "source_file": "1736402847_biosaftylevel3_ver3_101020243.pdf",
        "title": "Guidelines for Establishment of Biosafety Level 3 (BSL-3) Laboratory",
        "issuing_org": (
            "Indian Council of Medical Research, Department of Health Research, Ministry of "
            "Health & Family Welfare, Government of India, New Delhi"
        ),
        "version": (
            "Version 3 per the operator's filename ('biosaftylevel3_ver3'). THE DOCUMENT "
            "ITSELF STATES NO VERSION OR DATE in extractable text: its first five pages, "
            "including the title page, are scanned images. Its body text refers to events "
            "up to 2024, so it is not earlier than 2024"
        ),
        "publication_date": "NOT STATED IN THE DOCUMENT (body text refers to 2024 events)",
        "clinical_domain": D_LAB,
        "notes": (
            _HASH_VERIFIED + " for pages 6 onward; pages 1-5 are images and contribute no "
            "text. The version above comes from the FILENAME, not the document, and is "
            "labelled as such because a version number the document does not state is not a "
            "version number this system may assert. See ICMR-BSL3-GENERAL-UNDATED, also "
            "held. " + _NOT_CLINICAL + " " + _SUPPLIED_NUMERIC
        ),
    },
    {
        **_R4,
        "document_id": "ICMR-BIOREPOSITORY-2026",
        "source_file": "1779287592_biorepositoryfinal_v2.pdf",
        "title": "Guidelines for Establishment of Biorepositories in ICMR Institutes",
        "issuing_org": (
            "Division of Communicable Diseases, Indian Council of Medical Research, New Delhi"
        ),
        "version": "2026",
        "publication_date": "2026",
        "clinical_domain": D_LAB,
        "notes": (
            _HASH_VERIFIED + " Copyright page states 2026. Governs sample storage "
            "infrastructure. " + _NOT_CLINICAL + " " + _SUPPLIED_NUMERIC
        ),
    },
    {
        **_R4,
        "document_id": "ICMR-SOP-IMMUNOPHENOTYPING-2016",
        "source_file": "Immunophenotyping of Hematolymphoid Neoplasms_0.pdf",
        "title": (
            "Standard Operating Procedures for Immunophenotyping of Hematolymphoid Neoplasms"
        ),
        "issuing_org": _icmr_ncd("2016"),
        "version": "2016",
        "publication_date": "2016",
        "clinical_domain": D_LAB,
        "notes": (
            _HASH_VERIFIED + " LABORATORY METHOD for diagnosing haematolymphoid neoplasms: "
            "panels, gating and reporting. It is a diagnostic laboratory standard, not "
            "treatment guidance, and prescribes nothing. " + _NOT_CLINICAL
        ),
    },

    # =======================================================================
    # PROGRAMME AND INSTITUTIONAL POLICY -- rank 4.
    # =======================================================================
    {
        **_R4,
        "document_id": "ICMR-STEMCELL-RESEARCH-2007",
        "source_file": "stem_cell_guidelines_2007_0.pdf",
        "title": "Guidelines for Stem Cell Research and Therapy",
        "issuing_org": "Indian Council of Medical Research (ICMR), New Delhi",
        "version": "November 2007",
        "publication_date": "November 2007",
        "clinical_domain": D_POLICY,
        "notes": (
            _HASH_VERIFIED + " SUPERSEDED: the 2013 and 2017 national stem cell research "
            "guidelines are also held here. Governs which stem cell research is permissible, "
            "restricted or prohibited, and how it is reviewed. " + _NOT_CLINICAL
        ),
    },
    {
        **_R4,
        "document_id": "ICMR-DBT-STEMCELL-RESEARCH-2013",
        "source_file": "NGSCR 2013_0.pdf",
        "title": "National Guidelines for Stem Cell Research",
        "issuing_org": "Indian Council of Medical Research (ICMR), New Delhi",
        "version": "December 2013",
        "publication_date": "December 2013",
        "clinical_domain": D_POLICY,
        "notes": (
            _HASH_VERIFIED + " SUPERSEDED by the 2017 edition, also held. " + _NOT_CLINICAL
        ),
    },
    {
        **_R4,
        "document_id": "ICMR-DBT-STEMCELL-RESEARCH-2017",
        "source_file": "Guidelines_for_stem_cell_research_2017.pdf",
        "title": "National Guidelines for Stem Cell Research",
        "issuing_org": (
            "Indian Council of Medical Research (ICMR) and Department of Biotechnology (DBT), "
            "Government of India, New Delhi"
        ),
        "version": "2017",
        "publication_date": "October 2017",
        "clinical_domain": D_POLICY,
        "notes": (
            _HASH_VERIFIED + " The LATEST stem cell research governance edition held here; "
            "the 2007 and 2013 editions are retained alongside it. Research governance, not "
            "a statement that any stem cell therapy is clinically established -- for what "
            "the evidence supports, see ICMR-STEMCELL-THERAPY-EVIDENCE-2021, which is a "
            "separate document with a different purpose. " + _NOT_CLINICAL
        ),
    },
    {
        **_R4,
        "document_id": "ICMR-IRISE-POLICY-2024",
        "source_file": "1735624173_prise.pdf",
        "title": "Policy on ICMR Research Infrastructure Sharing Ecosystem (I-RISE)",
        "issuing_org": (
            "Division of Policy & Communications, Indian Council of Medical Research and "
            "Department of Health Research, New Delhi"
        ),
        "version": "2024",
        "publication_date": "2024",
        "clinical_domain": D_POLICY,
        "notes": (
            _HASH_VERIFIED + " ADMINISTRATIVE POLICY on sharing research infrastructure "
            "between institutions. It has no clinical or scientific content whatsoever. "
            + _NOT_CLINICAL + " " + _SUPPLIED_NUMERIC
        ),
    },
    {
        **_R4,
        "document_id": "ICMR-NCDC-NVBDCP-PESTICIDE-PROTOCOL-2014",
        "source_file": (
            "Revised Common Protocol for Uniform Evaluation of Public Health Pesticides "
            "including Bio-larvicides for use in Vector Control.pdf"
        ),
        "title": (
            "Revised Common Protocol for Uniform Evaluation of Public Health Pesticides "
            "including Bio-larvicides for use in Vector Control"
        ),
        "issuing_org": (
            "Indian Council of Medical Research, National Centre for Disease Control (NCDC) "
            "and National Vector Borne Disease Control Programme (NVBDCP), Government of India"
        ),
        "version": "2014",
        "publication_date": "2014",
        "clinical_domain": D_POLICY,
        "notes": (
            _HASH_VERIFIED + " EVALUATION PROTOCOL FOR INSECTICIDES, not medicines. It "
            "describes how a public health pesticide is trialled and assessed for vector "
            "control. Nothing in it concerns treating a patient, and its dosing and efficacy "
            "language refers to insecticide application rates. " + _NOT_CLINICAL
        ),
    },
    {
        **_R4,
        "document_id": "ICMR-NCDC-NVBDCP-PESTICIDE-SOP-2014",
        "source_file": (
            "Standard Operating Procedure (SOP) for introduction of public Health Pesticides "
            "including Biolarvicides in the National Vector Control Programme.pdf"
        ),
        "title": (
            "Standard Operating Procedure (SOP) for Introduction of Public Health Pesticides "
            "including Biolarvicides in the National Vector Control Programme"
        ),
        "issuing_org": (
            "Indian Council of Medical Research, National Centre for Disease Control (NCDC) "
            "and National Vector Borne Disease Control Programme (NVBDCP), Government of India"
        ),
        "version": "2014",
        "publication_date": "2014",
        "clinical_domain": D_POLICY,
        "notes": (
            _HASH_VERIFIED + " Companion SOP to ICMR-NCDC-NVBDCP-PESTICIDE-PROTOCOL-2014. "
            "Programme procedure for introducing an insecticide, not medical guidance. "
            + _NOT_CLINICAL
        ),
    },

    # =======================================================================
    # RESEARCH ACTIVITY REPORTS -- rank 4.
    #
    # These recommend nothing. They describe research that ICMR carried out. They
    # are the clearest case in the corpus of a document that must never be read as
    # guidance, and they are held because the operator supplied them and a corpus
    # that quietly drops files cannot be audited.
    # =======================================================================
    {
        **_R4,
        "document_id": "ICMR-CANCER-RESEARCH-NINETIES-UNDATED",
        "source_file": "cancer_0.pdf",
        "title": "Cancer Research in ICMR: Achievements in Nineties",
        "issuing_org": "Indian Council of Medical Research (ICMR), New Delhi",
        "version": (
            "UNDATED: the document states no publication year in extractable text. Its "
            "subject is ICMR cancer research during the 1990s"
        ),
        "publication_date": "NOT STATED IN THE DOCUMENT",
        "clinical_domain": D_REPORT,
        "notes": (
            _HASH_VERIFIED + " A RETROSPECTIVE ACCOUNT OF RESEARCH ACTIVITY, not guidance. "
            "It contains no recommendation of any kind. Despite naming cancers throughout, "
            "it must never be retrieved as cancer management guidance -- the ICMR consensus "
            "documents in this batch are that. " + _NOT_CLINICAL
        ),
    },
    {
        **_R4,
        "document_id": "ICMR-CANCER-MONOGRAPH-2019",
        "source_file": "Cancer_Monographs-new.pdf",
        "title": "Cancer Monograph: Compendium of ICMR's Cancer Research Activities",
        "issuing_org": _icmr_ncd("2019"),
        "version": "2019",
        "publication_date": "2019",
        "clinical_domain": D_REPORT,
        "notes": (
            _HASH_VERIFIED + " A COMPENDIUM OF RESEARCH ACTIVITIES, not guidance. Same "
            "caution as ICMR-CANCER-RESEARCH-NINETIES-UNDATED: it is the largest document "
            "in this batch and names cancers on almost every page, which makes it the most "
            "likely of the two to surface on an oncology query and the most important to "
            "label. " + _NOT_CLINICAL
        ),
    },
]


def main() -> int:
    return run_batch(
        MANIFESTS,
        COMMON,
        default_pdf_dir=".cache/icmr_national_corpus",
        description=__doc__,
    )


if __name__ == "__main__":
    sys.exit(main())
