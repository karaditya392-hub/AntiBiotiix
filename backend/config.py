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
        "version": "2nd edition (2019) - the edition ingested in this system"
    },
    {
        "rank": 3,
        "category": "INTERNATIONAL_WHO_IDSA",
        "description": "WHO AWaRe Classification of Antibiotics & IDSA Clinical Practice Guidelines",
        "issuing_org": "World Health Organization / Infectious Diseases Society of America",
        "version": "WHO AWaRe antibiotic book 2022 (ingested); IDSA guidance not held in this system"
    }
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
