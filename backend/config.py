"""
System Configuration, Version Pinning & Precedence Rules for S11 Assistant
"""
import hashlib
from typing import Dict, List, Any

SYSTEM_VERSION = "1.4.0-clinical-safety"
ENGINE_BUILD = "2026.08.22-release"
MODEL_NAME = "antigravity-deterministic-explainer-v1"
PROMPT_TEMPLATE_ID = "clinical_explanation_tmpl_v2.1"

# Standard explanation template text from which hash is deterministically calculated
EXPLANATION_TEMPLATE_TEXT = (
    "CLINICAL_DECISION_SUPPORT_EXPLANATION_TEMPLATE_V2.1:\n"
    "Summary: {total_warnings} potential safety concern(s) surfaced.\n"
    "Warnings List: {warnings_corpus}\n"
    "Guideline References: {guidelines_corpus}\n"
    "Boundary: Clinical Decision Support Only. Clinician retains full prescribing responsibility."
)

PROMPT_TEMPLATE_HASH = f"sha256:{hashlib.sha256(EXPLANATION_TEMPLATE_TEXT.encode('utf-8')).hexdigest()}"

# Guideline Precedence Hierarchy (Section 8A)
# When clinical recommendations differ, precedence is resolved according to this documented hierarchy:
GUIDELINE_PRECEDENCE_HIERARCHY = [
    {
        "rank": 1,
        "category": "LOCAL_INSTITUTIONAL",
        "description": "Local Hospital Antibiogram & Formulary Guidelines (Highest priority for local pathogen susceptibility)",
        "issuing_org": "Institutional Infection Control Committee (AIIMS / PGI / Hospital Level)"
    },
    {
        "rank": 2,
        "category": "NATIONAL_INDIA",
        "description": "Indian Council of Medical Research (ICMR) National Treatment Guidelines for Antimicrobial Use in Infectious Diseases",
        "issuing_org": "ICMR, Ministry of Health and Family Welfare, Govt. of India",
        "version": "2nd edition (2019) - the edition ingested in this system",
        # A SECOND national antimicrobial authority is now held: the NCDC National
        # Treatment Guidelines for Antimicrobial Use, Version 1.0 (2016). It is a
        # different body's guideline, not a newer ICMR edition, and this system does
        # not adjudicate between them -- it shows what each says.
        "second_national_antimicrobial_authority": (
            "National Treatment Guidelines for Antimicrobial Use in Infectious Diseases, "
            "Version 1.0 (2016), National Centre for Disease Control (NCDC), DGHS, MoHFW "
            "[document NCDC-NTG-AMR-2016]. Held at this same national rank. Neither it nor "
            "the ICMR guidelines supersedes the other here; where they differ, the "
            "difference is reported and its clinical resolution is left to the reader."
        ),
        # The retrieval corpus also holds condition-specific national guidelines and
        # programme documents at this rank. Stating that here rather than leaving the
        # API to describe rank 2 as ICMR-only, which is how a response comes to make a
        # claim the corpus contradicts (Spec 22).
        "also_held_at_this_rank": (
            "12 MoHFW/NHSRC Standard Treatment Guidelines and 13 national programme "
            "guidelines (NCDC, NVBDCP, NLEP, NACO/MoHFW, NPCDCS, NPPMBI), all "
            "condition-specific. Outside their own condition they carry NO antimicrobial "
            "authority, and where one that does carry antibiotic recommendations differs "
            "from the national antimicrobial guidelines or the local antibiogram, those "
            "govern. Each document's provenance notes state its own scope."
        )
    },
    {
        "rank": 3,
        "category": "INTERNATIONAL_WHO_IDSA",
        "description": "WHO AWaRe Classification of Antibiotics & IDSA Clinical Practice Guidelines",
        "issuing_org": "World Health Organization / Infectious Diseases Society of America",
        "version": "WHO AWaRe antibiotic book 2022 (ingested); IDSA guidance not held in this system"
    },
    {
        # Held and retrievable, but deliberately sorted below every clinical guideline.
        # A community mass-drug-administration leaflet, a 2006 public fact sheet and an
        # unattributed Ayurvedic compilation are all legitimately part of the corpus and
        # none of them is a clinical guideline. Ranking them with ICMR and NCDC would be
        # the claim; ranking them here is the absence of one.
        "rank": 4,
        "category": "NOT_A_CLINICAL_GUIDELINE",
        "description": (
            "Held for retrieval but carrying no clinical authority: public information "
            "material, community programme leaflets, and documents whose issuing body "
            "cannot be established from the document itself. Never a basis for an "
            "antimicrobial or prescribing decision."
        ),
        "issuing_org": "Various; see each document's provenance notes",
        "version": "n/a"
    }
]

# The documents that carry national antimicrobial authority, by corpus id.
#
# Explicit rather than inferred: nothing in a document's metadata says "this is an
# antimicrobial guideline", and guessing from the title would quietly promote a
# condition-specific guideline that happens to mention antibiotics. Everything else
# in the corpus is condition-specific, reference-only, or international.
#
# Read back out of the corpus at call time so the versions reported are the ones
# actually held -- the API previously stated "ICMR Edition 3", an edition this
# repository has never held (Spec 22).
NATIONAL_ANTIMICROBIAL_AUTHORITY_DOCUMENT_IDS = [
    "ICMR-STG-2019-ED2",
    "NCDC-NTG-AMR-2016",
]

# Role Authorization Configuration (Section 18A)
AUTHORIZED_OVERRIDE_ROLES = [
    "ATTENDING_PHYSICIAN",
    "INFECTIOUS_DISEASE_SPECIALIST",
    "CLINICAL_PHARMACIST",
    "RESIDENT_PHYSICIAN"
]

AUTHORIZED_RULE_AUTHORING_ROLES = [
    "INFECTIOUS_DISEASE_SPECIALIST",
    "CLINICAL_PHARMACIST",
    "ATTENDING_PHYSICIAN"
]

# Alert Fatigue Thresholds (Section 16A)
# If override rate exceeds 60% with at least 10 triggers, rule is flagged for clinical recalibration
ALERT_FATIGUE_OVERRIDE_RATE_THRESHOLD = 0.60
ALERT_FATIGUE_MIN_TRIGGERS = 10
