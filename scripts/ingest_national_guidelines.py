"""
Ingest the Indian national programme guidelines into the RAG corpus.

Sixteen documents from NCDC, the national disease-control programmes (NVBDCP,
NLEP, NPCDCS, NPPMBI), NACO/MoHFW and one unattributed Ayurvedic file. Unlike the
MoHFW STG batch in scripts/ingest_mohfw_stg.py, most of THIS batch is infectious
disease, and one document changes what the corpus can answer:

  NCDC-NTG-AMR-2016 is the National Treatment Guidelines for Antimicrobial Use in
  Infectious Diseases, Version 1.0 (2016). It is a national antimicrobial authority
  in its own right, issued by NCDC -- a different body from ICMR, whose guidelines
  this system already holds. Both now sit at national rank. Neither supersedes the
  other here, and this system does not adjudicate between them.

Ingesting adds retrievable evidence. It changes no clinical rule: the rule engine
does not import retrieval (see backend/rag/retrieve.py), and no rule in the catalog
cites any document in this batch.

Provenance strings were read off each document. Where a document states nothing --
no date, no issuing organisation, no title page -- the manifest says so rather than
supplying a plausible value, and `source_url` names the issuer's own website (never
a deep link) because the operator supplied these as bare numeric download files.

Usage:
    python -m scripts.ingest_national_guidelines --pdf-dir .cache/national_guidelines
    python -m scripts.ingest_national_guidelines --pdf-dir .cache/national_guidelines --rebuild-index
"""
from __future__ import annotations

import sys

from scripts._guideline_batch import run_batch

MOHFW_URL = "https://www.mohfw.gov.in/"
NCDC_URL = "http://www.ncdc.gov.in/"
NVBDCP_URL = "http://www.nvbdcp.gov.in/"
NLEP_URL = "http://www.nlep.nic.in/"
NACO_URL = "http://www.naco.gov.in/"

_HASH_VERIFIED = (
    "Hash-verified against the copy held by the operator. Page numbers are genuine "
    "pages of this document."
)

# Which sources govern an antimicrobial decision. Updated from the MoHFW batch: NCDC
# is now held too, so naming only ICMR would misdescribe the corpus.
_GOVERNING = (
    "For antimicrobial choice the national antimicrobial treatment guidelines held "
    "here (ICMR, and NCDC-NTG-AMR-2016) and the local hospital antibiogram govern; "
    "this document must not be read as overriding them."
)

_NOT_AMR = (
    "CONDITION-SPECIFIC GUIDELINE, NOT AN ANTIMICROBIAL STEWARDSHIP SOURCE: it carries "
    "no antimicrobial guidance and must never be cited for antimicrobial choice."
)


def _supplied_as(original: str) -> str:
    return (
        "Supplied by the operator as the download file '" + original + "'; the exact "
        "download URL was not recorded and could not be verified in this environment, "
        "so source_url names the issuing body's own website rather than a deep link."
    )


MANIFESTS = [
    # -- NCDC ---------------------------------------------------------------
    {
        "document_id": "NCDC-NTG-AMR-2016",
        "source_file": "NCDC_National_Treatment_Guidelines_Antimicrobial_Use_v1_2016.pdf",
        "title": (
            "National Treatment Guidelines for Antimicrobial Use in Infectious Diseases, "
            "Version 1.0 (2016)"
        ),
        "issuing_org": (
            "National Centre for Disease Control (NCDC), Directorate General of Health "
            "Services, Ministry of Health & Family Welfare, Government of India"
        ),
        "version": "Version 1.0 (2016)",
        "publication_date": "2016",
        "source_url": NCDC_URL,
        "notes": (
            _HASH_VERIFIED + " PRIMARY ANTIMICROBIAL SOURCE, and the only document in "
            "this batch that is one. Its syndromic empirical therapy chapter covers "
            "gastrointestinal and intra-abdominal, CNS, cardiovascular, skin and soft "
            "tissue, respiratory, urinary, obstetric and gynaecological, bone and joint, "
            "and eye infections. TWO NATIONAL AUTHORITIES ARE NOW HELD: this is an NCDC "
            "publication, and the ICMR treatment guidelines also held here are a separate "
            "national guideline from a separate body. Neither supersedes the other in this "
            "system and no adjudication between them is performed; where they differ, the "
            "difference is a fact about the two documents and its clinical resolution "
            "belongs to the reader. VERSION 1.0 (2016): it predates the ICMR AMR "
            "surveillance data held here, and this repository holds no later NCDC "
            "revision, so currency against present resistance patterns cannot be assessed "
            "from the file. No clinical rule in this system cites this document; ingesting "
            "it adds retrievable evidence and changes no rule. " + _supplied_as("86111.pdf")
        ),
    },
    {
        "document_id": "NCDC-LEPTOSPIROSIS-2015",
        "source_file": "NCDC_Leptospirosis_National_Guidelines_2015.pdf",
        "title": (
            "National Guidelines: Diagnosis, Case Management, Prevention and Control of "
            "Leptospirosis"
        ),
        "issuing_org": (
            "National Centre for Disease Control (NCDC), Directorate General of Health "
            "Services, Ministry of Health & Family Welfare, Government of India "
            "(Programme for Prevention and Control of Leptospirosis)"
        ),
        "version": "2015",
        "publication_date": "2015",
        "source_url": NCDC_URL,
        "notes": (
            _HASH_VERIFIED + " CONTAINS ANTIMICROBIAL RECOMMENDATIONS, for leptospirosis "
            "only (doxycycline, penicillins, third-generation cephalosporins, "
            "erythromycin). " + _GOVERNING + " " + _supplied_as("919.pdf")
        ),
    },
    {
        "document_id": "NCDC-RABIES-PROPHYLAXIS-2015",
        "source_file": "NCDC_Rabies_Prophylaxis_National_Guidelines_2015.pdf",
        "title": "National Guidelines on Rabies Prophylaxis",
        "issuing_org": (
            "National Centre for Disease Control (NCDC), Directorate General of Health "
            "Services, Ministry of Health & Family Welfare, Government of India "
            "(National Rabies Control Programme)"
        ),
        "version": "2015",
        "publication_date": "2015",
        "source_url": NCDC_URL,
        "notes": (
            _HASH_VERIFIED + " POST-EXPOSURE PROPHYLAXIS, NOT ANTIBACTERIAL THERAPY: it "
            "covers wound washing, rabies vaccine schedules and rabies immunoglobulin. It "
            "names no antibacterial regimen and must not be cited for antibiotic selection. "
            + _supplied_as("238.pdf")
        ),
    },
    # -- National Viral Hepatitis Control Program ---------------------------
    {
        "document_id": "MOHFW-NVHCP-VIRAL-HEPATITIS-2018",
        "source_file": "MoHFW_NVHCP_Viral_Hepatitis_National_Guidelines_2018.pdf",
        "title": "National Guidelines for Diagnosis & Management of Viral Hepatitis",
        "issuing_org": (
            "National Viral Hepatitis Control Program, Ministry of Health and Family "
            "Welfare, Government of India (prepared by the Technical Resource Group on "
            "Hepatitis Treatment constituted by the MoHFW)"
        ),
        "version": "2018",
        "publication_date": "2018",
        "source_url": MOHFW_URL,
        "notes": (
            _HASH_VERIFIED + " ANTIVIRAL THERAPY ONLY: it carries hepatitis B and C "
            "treatment guidance. It contains no antibacterial guidance, the agents it "
            "names sit outside this system's antibacterial formulary, and it must never be "
            "cited for antibiotic selection. " + _supplied_as("3591.pdf")
        ),
    },
    # -- NVBDCP -------------------------------------------------------------
    {
        "document_id": "NVBDCP-MALARIA-DX-TX-2013",
        "source_file": "NVBDCP_Malaria_Diagnosis_Treatment_2013.pdf",
        "title": "Diagnosis and Treatment of Malaria",
        "issuing_org": (
            "Directorate of the National Vector Borne Disease Control Programme (NVBDCP), "
            "Directorate General of Health Services, Ministry of Health & Family Welfare, "
            "Government of India"
        ),
        "version": "2013",
        "publication_date": "2013",
        "source_url": NVBDCP_URL,
        "notes": (
            _HASH_VERIFIED + " CONTAINS ANTIMALARIAL DRUG POLICY (artemisinin combination "
            "therapy, chloroquine, primaquine) together with doxycycline and clindamycin in "
            "specific regimens. NOT AN ANTIBACTERIAL GUIDELINE: those two agents appear "
            "only inside antimalarial regimens and must not be generalized. 2013 edition: "
            "India's national antimalarial drug policy has been revised since and no later "
            "edition is held here, so its regimens must be checked against current national "
            "policy before use. " + _supplied_as("892.pdf")
        ),
    },
    {
        "document_id": "NVBDCP-AES-JE-2009",
        "source_file": "NVBDCP_Acute_Encephalitis_Syndrome_JE_2009.pdf",
        "title": (
            "Guidelines: Clinical Management of Acute Encephalitis Syndrome including "
            "Japanese Encephalitis"
        ),
        "issuing_org": (
            "Directorate of the National Vector Borne Disease Control Programme (NVBDCP), "
            "Directorate General of Health Services, Ministry of Health & Family Welfare, "
            "Government of India"
        ),
        "version": "August 2009",
        "publication_date": "2009-08",
        "source_url": NVBDCP_URL,
        "notes": (
            _HASH_VERIFIED + " CONTAINS ANTIMICROBIAL RECOMMENDATIONS for the differential "
            "management of acute encephalitis syndrome (ceftriaxone, ampicillin, acyclovir, "
            "amphotericin B, antitubercular agents), for that syndrome only. " + _GOVERNING
            + " PUBLISHED 2009 and the oldest clinical guideline in this corpus: its agent "
            "choices predate every resistance dataset held here. " + _supplied_as("5041.pdf")
        ),
    },
    {
        "document_id": "NVBDCP-KALA-AZAR-ROADMAP-UNDATED",
        "source_file": "NVBDCP_Kala_azar_Elimination_Roadmap_undated.pdf",
        "title": "National Roadmap for Kala-azar Elimination (NRKE)",
        "issuing_org": (
            "Directorate of the National Vector Borne Disease Control Programme (NVBDCP), "
            "Directorate General of Health Services, Ministry of Health & Family Welfare, "
            "Government of India. NOTE: the file has no title page and names no issuing "
            "body on it; the attribution comes from the document's own text"
        ),
        "version": "Undated (activity timelines run to 2014-2015)",
        "publication_date": (
            "NOT STATED IN THE DOCUMENT (its own action plan runs to 2014-2015; the PDF was "
            "generated July 2018)"
        ),
        "source_url": NVBDCP_URL,
        "notes": (
            _HASH_VERIFIED + " PROGRAMME ROADMAP, NOT A CLINICAL TREATMENT GUIDELINE: it "
            "sets elimination goals, responsibilities and timelines. It mentions "
            "amphotericin B in a programme-supply context, not as a dosing recommendation, "
            "and must not be cited for antileishmanial dosing or for any antimicrobial "
            "choice. " + _supplied_as("7051.pdf")
        ),
    },
    {
        "document_id": "NVBDCP-LF-DRUG-DISTRIBUTORS-UNDATED",
        "source_file": "NVBDCP_Lymphatic_Filariasis_Drug_Distributors_undated.pdf",
        "title": "Elimination of Lymphatic Filariasis: Guidelines for Drug Distributors",
        "issuing_org": (
            "Directorate of the National Vector Borne Disease Control Programme (NVBDCP), "
            "Directorate General of Health Services, Ministry of Health and Family Welfare, "
            "Government of India, with the Vector Control Research Centre (Indian Council of "
            "Medical Research), Puducherry"
        ),
        "version": "Undated",
        "publication_date": (
            "NOT STATED IN THE DOCUMENT (the PDF was generated June 2007)"
        ),
        "source_url": NVBDCP_URL,
        "precedence_rank": 4,
        "notes": (
            _HASH_VERIFIED + " COMMUNITY MASS-DRUG-ADMINISTRATION LEAFLET FOR NON-CLINICAL "
            "DRUG DISTRIBUTORS, not a clinical treatment guideline: it instructs village "
            "volunteers on distributing diethylcarbamazine (DEC) and albendazole during MDA "
            "rounds. Ranked below the clinical guidelines for that reason. IT DOES NAME "
            "ANTIPARASITIC DRUGS, but as a whole-population public-health intervention rather "
            "than as individual therapy: it is not antimicrobial selection guidance, contains "
            "no antibacterial content, and must never be cited for antimicrobial choice. "
            + _supplied_as("5021.pdf")
        ),
    },
    {
        "document_id": "MOHFW-CHIKUNGUNYA-FACTS-2006",
        "source_file": "MoHFW_Chikungunya_Fever_Facts_2006.pdf",
        "title": "Chikungunya Fever: Facts",
        "issuing_org": (
            "ISSUING ORGANISATION NOT NAMED ON THE DOCUMENT. It cites the National "
            "Institute of Virology (NIV), Pune and the National Institute of Communicable "
            "Diseases (NICD) as data sources, which is not the same as naming a publisher"
        ),
        "version": "Undated fact sheet (surveillance figures run to 30 October 2006)",
        "publication_date": (
            "NOT STATED IN THE DOCUMENT (its case counts run to 30 October 2006 and the PDF "
            "was generated 31 October 2006)"
        ),
        "source_url": MOHFW_URL,
        "precedence_rank": 4,
        "notes": (
            _HASH_VERIFIED + " PUBLIC INFORMATION FACT SHEET, NOT A TREATMENT GUIDELINE, and "
            "the oldest document in this corpus by a wide margin: it is a question-and-answer "
            "sheet whose epidemiology is that of the 2006 outbreak. Ranked below the clinical "
            "guidelines. " + _NOT_AMR + " " + _supplied_as("155.pdf")
        ),
    },
    # -- NACO / MoHFW -------------------------------------------------------
    {
        "document_id": "NACO-MOHFW-RTI-STI-2014",
        "source_file": "NACO_MoHFW_RTI_STI_National_Guidelines_2014.pdf",
        "title": (
            "National Guidelines on Prevention, Management and Control of Reproductive Tract "
            "Infections and Sexually Transmitted Infections"
        ),
        "issuing_org": (
            "STI/RTI Division, Department of AIDS Control, and the Maternal Health Division, "
            "Ministry of Health and Family Welfare, Government of India"
        ),
        "version": "July 2014",
        "publication_date": "2014-07",
        "source_url": NACO_URL,
        "notes": (
            _HASH_VERIFIED + " CONTAINS SUBSTANTIAL ANTIMICROBIAL RECOMMENDATIONS: syndromic "
            "management of reproductive tract and sexually transmitted infections with named "
            "regimens (azithromycin, ceftriaxone, benzathine penicillin, metronidazole, "
            "acyclovir and others). After NCDC-NTG-AMR-2016 it is the most antimicrobial-dense "
            "document in this batch, and its guidance is confined to RTI/STI syndromes. "
            + _GOVERNING + " 2014 edition: gonococcal susceptibility in particular has moved "
            "since, so its regimens must be read against current national guidance and the "
            "local antibiogram. " + _supplied_as("448.pdf")
        ),
    },
    # -- NLEP ---------------------------------------------------------------
    {
        "document_id": "NLEP-DPMR-2012",
        "source_file": "NLEP_DPMR_Guidelines_2012.pdf",
        "title": (
            "Guidelines for Primary, Secondary and Tertiary Level Care: Disability Prevention "
            "& Medical Rehabilitation"
        ),
        "issuing_org": (
            "Central Leprosy Division, Directorate General of Health Services, Ministry of "
            "Health & Family Welfare, Government of India (National Leprosy Eradication "
            "Programme)"
        ),
        "version": "June 2012",
        "publication_date": "2012-06",
        "source_url": NLEP_URL,
        "notes": (
            _HASH_VERIFIED + " Leprosy disability prevention and rehabilitation. Antimicrobial "
            "content is limited to multi-drug therapy context; this is not an antimicrobial "
            "selection guideline and must not be cited as one. COMMERCIAL SPONSOR ACKNOWLEDGED "
            "IN THE SOURCE: the document carries a Novartis statement about that company's "
            "donation of leprosy multi-drug therapy through WHO. That acknowledgement is part "
            "of the source text and is disclosed here rather than retrieved silently. "
            + _supplied_as("516.pdf")
        ),
    },
    {
        "document_id": "NLEP-MO-TRAINING-MANUAL-2013",
        "source_file": "NLEP_Medical_Officer_Training_Manual_2013.pdf",
        "title": "Training Manual for Medical Officer",
        "issuing_org": (
            "Central Leprosy Division, Directorate General of Health Services, Ministry of "
            "Health & Family Welfare, Government of India (National Leprosy Eradication "
            "Programme)"
        ),
        "version": "2013 (foreword dated 14 March 2013)",
        "publication_date": "2013-03",
        "source_url": NLEP_URL,
        "notes": (
            _HASH_VERIFIED + " CONTAINS ANTIMICROBIAL RECOMMENDATIONS: leprosy multi-drug "
            "therapy regimens (rifampicin, clofazimine, dapsone) as set by the National "
            "Leprosy Eradication Programme. PROGRAMME-DETERMINED REGIMENS: MDT composition and "
            "duration are set by national programme policy rather than by empirical "
            "antibacterial selection, so this document must not be generalized to any other "
            "infection. " + _supplied_as("50.pdf")
        ),
    },
    # -- Other national programmes -----------------------------------------
    {
        "document_id": "NPPMBI-BURNS-UNDATED",
        "source_file": "NPPMBI_Burn_Injuries_undated.pdf",
        "title": "National Programme for Prevention and Management of Burn Injuries (NPPMBI)",
        "issuing_org": (
            "Directorate General of Health Services, Ministry of Health and Family Welfare, "
            "Government of India (images credited to the Bihar Burn & Trauma Research Centre)"
        ),
        "version": "Undated",
        "publication_date": "NOT STATED IN THE DOCUMENT (the PDF was generated April 2015)",
        "source_url": MOHFW_URL,
        "notes": (
            _HASH_VERIFIED + " CONTAINS ANTIMICROBIAL RECOMMENDATIONS for burn wound care and "
            "burn wound sepsis (topical silver sulphadiazine, framycetin, neosporin), for "
            "burns only, and it explicitly cautions against routine systemic antibiotic "
            "prophylaxis on resistance grounds. " + _GOVERNING + " " + _supplied_as("520.pdf")
        ),
    },
    {
        "document_id": "NPCDCS-MO-MANUAL-UNDATED",
        "source_file": "NPCDCS_Medical_Officer_Manual_undated.pdf",
        "title": (
            "National Programme for Prevention and Control of Cancer, Diabetes, Cardiovascular "
            "Disease and Stroke (NPCDCS): A Manual for Medical Officer"
        ),
        "issuing_org": (
            "Ministry of Health and Family Welfare, Government of India, developed under the "
            "Government of India - WHO Collaborative Programme 2008-2009"
        ),
        "version": "Undated (developed under the 2008-2009 collaborative programme)",
        "publication_date": (
            "NOT STATED IN THE DOCUMENT (it names the 2008-2009 collaborative programme it was "
            "developed under; the PDF was generated August 2015)"
        ),
        "source_url": MOHFW_URL,
        "notes": (
            _HASH_VERIFIED + " " + _NOT_AMR + " Antibiotics appear only as referral "
            "criteria (an unresponsive urinary tract infection or a deep-seated diabetic "
            "foot infection needing intravenous therapy); no agent, dose or regimen is "
            "named anywhere in the document. " + _supplied_as("58.pdf")
        ),
    },
    {
        "document_id": "MOHFW-INTRAOCULAR-SURGERY-PRECAUTIONS-UNDATED",
        "source_file": "MoHFW_Intraocular_Surgery_Precautions_undated.pdf",
        "title": (
            "Guidelines for Pre-operative, Operative and Post-operative Precautions for Intra "
            "Ocular Eye Surgery"
        ),
        "issuing_org": (
            "Expert committee convened under the Ministry of Health & Family Welfare, "
            "Government of India; the document carries a signature page listing its members, "
            "headed by the Additional Secretary (MoHFW), with faculty from AIIMS New Delhi and "
            "state programme officers. It has no title page and no publisher imprint"
        ),
        "version": "Undated",
        "publication_date": "NOT STATED IN THE DOCUMENT (the PDF was generated August 2016)",
        "source_url": MOHFW_URL,
        "notes": (
            _HASH_VERIFIED + " ANTIMICROBIAL-RELEVANT: it covers peri-operative antisepsis and "
            "antibiotic prophylaxis against post-operative endophthalmitis, for intraocular "
            "surgery only. It prescribes sterilisation and asepsis protocol rather than "
            "systemic antimicrobial selection. " + _GOVERNING + " UNDATED AND WITHOUT A TITLE "
            "PAGE: the file begins with the guideline text itself. " + _supplied_as("5801.pdf")
        ),
    },
    # -- Traditional medicine ----------------------------------------------
    {
        "document_id": "AYURVEDA-STG-UNATTRIBUTED-UNDATED",
        "source_file": "Ayurveda_STG_unattributed_undated.pdf",
        "title": "Standard Treatment Guidelines (Ayurveda) - unattributed compilation",
        "issuing_org": (
            "NOT NAMED ANYWHERE IN THE DOCUMENT. The file has no title page, no publisher, no "
            "author, no programme and no date across all 16 of its pages"
        ),
        "version": "Unattributed and undated",
        "publication_date": "NOT STATED IN THE DOCUMENT (the PDF was generated October 2017)",
        "source_url": "",
        "precedence_rank": 4,
        "notes": (
            _HASH_VERIFIED + " TRADITIONAL MEDICINE (AYURVEDA), NOT ALLOPATHIC GUIDANCE: it "
            "sets out classical Ayurvedic management for conditions named in Sanskrit "
            "(Jalodara, Kustha, Tamaka Shwasa, Jwara, Grahni and others), using Ayurvedic "
            "preparations. WEAKEST PROVENANCE IN THE CORPUS: the only provenance this file "
            "carries is its own SHA-256 and an embedded source file name of '880.docx'. It "
            "names no issuing organisation, no author and no date, so nothing here "
            "establishes that it is an official publication of anything, and it is ranked "
            "below the clinical guidelines accordingly. " + _NOT_AMR + " This system performs "
            "no interaction, dosing or safety checking for Ayurvedic preparations, so a "
            "passage retrieved from this document carries none of the safety analysis that "
            "surrounds the allopathic corpus. " + _supplied_as("6391.pdf")
        ),
    },
]

COMMON = {
    "geographic_scope": "National (India)",
    "source_url": MOHFW_URL,
    # National-level Indian guidance. Three documents in this batch override this to
    # rank 4 (see backend/config.py): a community MDA leaflet, a 2006 public fact
    # sheet, and an unattributed Ayurvedic compilation are not clinical guidelines and
    # should not sort alongside ICMR and NCDC.
    "precedence_rank": 2,
    "source_type": "OFFICIAL_PDF",
    "page_reference_kind": "OFFICIAL_DOCUMENT_PAGE",
    "provenance_basis": "HASH_VERIFIED_PDF",
}


def main() -> int:
    return run_batch(
        MANIFESTS, COMMON,
        default_pdf_dir=".cache/national_guidelines",
        description="Ingest the Indian national programme guidelines into the RAG corpus.",
    )


if __name__ == "__main__":
    sys.exit(main())
