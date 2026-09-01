"""
System Configuration, Version Pinning & Precedence Rules for S11 Assistant
"""
import hashlib
import os
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
            "12 MoHFW/NHSRC Standard Treatment Guidelines, 13 national programme "
            "guidelines (NCDC, NVBDCP, NLEP, NACO/MoHFW, NPCDCS, NPPMBI), and 29 ICMR "
            "national clinical documents -- 22 cancer-site consensus documents, the type 1 "
            "and type 2 diabetes guidelines, celiac disease, DNAR, haematopoietic cell "
            "transplantation, the stem cell therapy evidence review, and the DHR-ICMR "
            "rickettsial diseases guidelines. ALL are condition-specific. Outside their own "
            "condition they carry NO antimicrobial authority, and where one that does carry "
            "antibiotic recommendations differs from the national antimicrobial guidelines "
            "or the local antibiogram, those govern. Of the ICMR batch only the rickettsial "
            "guidelines carry antimicrobial recommendations as their own subject, and only "
            "for rickettsial infection. Each document's provenance notes state its own "
            "scope, and `clinical_domain` states it in a form a caller can filter on."
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
        #
        # WIDENED for the ICMR national corpus. Rank 4 now also holds documents that are
        # national authorities in their own right and simply do not govern patient care:
        # research-ethics guidelines, laboratory biosafety manuals, programme policy and
        # two research-activity compendia. Rank 4 is not a judgement on their standing --
        # the ICMR National Ethical Guidelines are authoritative about research ethics.
        # It records that none of them is clinical guidance, which is the only question
        # this hierarchy asks. Which kind a document is, is carried separately by
        # `clinical_domain` (see backend.rag.store.DOMAIN_*), because "not an
        # antimicrobial source" and "not about patient care at all" are different
        # warnings and a reader needs the right one.
        "rank": 4,
        "category": "NOT_A_CLINICAL_GUIDELINE",
        "description": (
            "Held for retrieval but carrying no clinical authority: public information "
            "material, community programme leaflets, documents whose issuing body cannot "
            "be established from the document itself, and authoritative documents that do "
            "not govern patient care -- research ethics and governance, laboratory "
            "procedure and biosafety, programme and institutional policy, and research "
            "activity reports. Never a basis for an antimicrobial or prescribing decision."
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

# Documents that carry ANTIBACTERIAL recommendations, and may therefore be compared
# against one another when backend.guidelines.cross_source computes which sources
# name which agent.
#
# EXPLICIT, for the same reason the list above is explicit: nothing in a document's
# metadata says "this one names antibiotics", and inferring it goes wrong in both
# directions. Inferring from precedence rank admits every condition-specific
# guideline in the corpus -- 22 ICMR cancer consensus documents among them -- and a
# gallbladder cancer document that does not mention piperacillin would then be
# counted as a national guideline omitting it. Inferring from `clinical_domain ==
# ANTIMICROBIAL_TREATMENT` errs the other way and drops NCDC-LEPTOSPIROSIS-2015 from
# a leptospirosis comparison, which is the one source that actually covers it.
#
# Membership here is taken from each document's OWN recorded provenance note, not
# from a fresh reading: a document whose note says it "CONTAINS ANTIMICROBIAL
# RECOMMENDATIONS" is in, and one whose note says it "must not be cited for
# antibiotic selection" is out. The excluded infectious-disease documents are
# excluded on their own say-so -- viral hepatitis (antivirals only), rabies
# prophylaxis (vaccine and immunoglobulin), malaria (an explicit "NOT AN
# ANTIBACTERIAL GUIDELINE"), kala-azar (a programme roadmap), leprosy DPMR
# (rehabilitation) and Standard Treatment Workflows Vol. 3 (an explicit "NOT an
# antimicrobial stewardship guideline").
#
# Being in this set is NOT authority. Precedence still governs that, and a
# condition-specific document still speaks only about its own condition -- which is
# enforced upstream by the retrieval relevance threshold, not here.
ANTIMICROBIAL_CONTENT_DOCUMENT_IDS = frozenset({
    # Primary antimicrobial sources.
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
    # Condition-specific documents that carry named antibacterial regimens for
    # their own condition, per their own provenance notes.
    "NACO-MOHFW-RTI-STI-2014",
    "MOHFW-STG-ACUTE-SINUSITIS-UNDATED",
    "MOHFW-STG-PAED-RESP-INFECTIONS-2016",
    "MOHFW-STG-DIABETIC-FOOT-2016-DRAFT",
    "MOHFW-INTRAOCULAR-SURGERY-PRECAUTIONS-UNDATED",
    "NCDC-LEPTOSPIROSIS-2015",
    "NLEP-MO-TRAINING-MANUAL-2013",
    "NPPMBI-BURNS-UNDATED",
    "NVBDCP-AES-JE-2009",
    # ICMR national corpus (scripts/ingest_icmr_national_corpus.py). Exactly one of
    # its 55 documents carries antimicrobial recommendations as its own subject.
    "DHR-ICMR-RICKETTSIAL-2015",
})

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


# ---------------------------------------------------------------------------
# Appointment notification delivery (Section 28)
#
# Every value is read from the environment and every one defaults to empty. That
# is deliberate: with nothing configured the system sends nothing and SAYS it
# sent nothing. The previous engine returned "DELIVERED" from functions whose own
# docstrings said "Simulate", which recorded a delivery that never happened -- the
# same class of false claim the guideline provenance work exists to prevent.
#
# Configure SMTP to turn e-mail on, and an SMS webhook to turn SMS on. Until then
# the channels report NOT_CONFIGURED and only the in-app channel is real.
# ---------------------------------------------------------------------------

def _env_flag(name: str, default: str = "1") -> bool:
    return os.getenv(name, default).strip().lower() not in ("0", "false", "no", "off", "")


NOTIFICATION_SMTP_HOST = os.getenv("S11_SMTP_HOST", "").strip()
NOTIFICATION_SMTP_PORT = int(os.getenv("S11_SMTP_PORT", "587") or 587)
NOTIFICATION_SMTP_USER = os.getenv("S11_SMTP_USER", "").strip()
NOTIFICATION_SMTP_PASSWORD = os.getenv("S11_SMTP_PASSWORD", "")
NOTIFICATION_SMTP_FROM = os.getenv("S11_SMTP_FROM", "").strip()
NOTIFICATION_SMTP_STARTTLS = _env_flag("S11_SMTP_STARTTLS", "1")
NOTIFICATION_SMTP_TIMEOUT_SECONDS = int(os.getenv("S11_SMTP_TIMEOUT_SECONDS", "20") or 20)

# Provider-agnostic: any endpoint accepting a JSON POST of {to, message}. Keeping
# it generic avoids taking a dependency on one vendor's SDK for one feature.
NOTIFICATION_SMS_WEBHOOK_URL = os.getenv("S11_SMS_WEBHOOK_URL", "").strip()
NOTIFICATION_SMS_AUTH_HEADER = os.getenv("S11_SMS_AUTH_HEADER", "").strip()
NOTIFICATION_SMS_TIMEOUT_SECONDS = int(os.getenv("S11_SMS_TIMEOUT_SECONDS", "15") or 15)

# How far ahead the advance reminder goes out. The record used to claim
# "SCHEDULED_2_DAYS_PRIOR" while no code ever sent it; this is the real offset the
# scheduler now acts on.
NOTIFICATION_ADVANCE_NOTICE_DAYS = int(os.getenv("S11_ADVANCE_NOTICE_DAYS", "2") or 2)

# Background scheduler. Without it an appointment booked for next week is never
# announced, because the only trigger was a manual endpoint call.
NOTIFICATION_SCHEDULER_INTERVAL_SECONDS = int(
    os.getenv("S11_NOTIFICATION_INTERVAL_SECONDS", "900") or 900
)


def notification_scheduler_enabled() -> bool:
    """
    Read at thread start, not at import, so a test run or a deployment can switch
    the scheduler off without depending on module import order.
    """
    return _env_flag("S11_NOTIFICATION_SCHEDULER", "1")


def email_channel_configured() -> bool:
    return bool(NOTIFICATION_SMTP_HOST and (NOTIFICATION_SMTP_FROM or NOTIFICATION_SMTP_USER))


def sms_channel_configured() -> bool:
    return bool(NOTIFICATION_SMS_WEBHOOK_URL)
