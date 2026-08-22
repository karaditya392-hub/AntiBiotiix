"""
Deterministic Antimicrobial Stewardship Priority Rollup (Spec §14, §15, §20)
Pure, deterministic function computing clinical review priority directly from active warnings.
Zero machine learning, zero opaque scoring, 100% explainable and reproducible.
"""
from typing import List, Dict, Any
from backend.models.schemas import SafetyWarning, SeverityLevel, RuleCategory, PrescriptionItem, AWaReCategory


def compute_stewardship_priority(
    warnings: List[SafetyWarning],
    items: List[PrescriptionItem]
) -> Dict[str, Any]:
    """
    Compute clinical stewardship review priority based on deterministic severity rollup:
    - Any CRITICAL warning -> HIGH
    - Any ALLERGY warning of severity HIGH or CRITICAL -> HIGH
    - Any item not covered by knowledge base (Rule COVERAGE-001) -> HIGH ("unable to assess")
    - >=2 HIGH warnings, or 1 HIGH + a WHO Reserve agent -> HIGH
    - 1 HIGH warning, or >=2 MODERATE warnings -> MODERATE
    - Otherwise -> LOW
    """
    contributing_rule_ids: List[str] = []
    
    crit_warnings = [w for w in warnings if w.severity == SeverityLevel.CRITICAL]
    allergy_high_or_crit = [
        w for w in warnings 
        if (w.category == RuleCategory.ALLERGY or getattr(w.category, "value", str(w.category)) == "ALLERGY")
        and w.severity in (SeverityLevel.CRITICAL, SeverityLevel.HIGH)
    ]
    high_warnings = [w for w in warnings if w.severity == SeverityLevel.HIGH]
    mod_warnings = [w for w in warnings if w.severity == SeverityLevel.MODERATE]
    
    # Check for uncovered drug rule
    has_coverage_warning = any(w.rule_id == "COVERAGE-001" for w in warnings)
    has_reserve_agent = any(
        (isinstance(it.aware_category, AWaReCategory) and it.aware_category == AWaReCategory.RESERVE)
        or (isinstance(it.aware_category, str) and it.aware_category.upper() == "RESERVE")
        for it in items
    )

    tier = "LOW"
    rationale = "No critical or multi-factor high severity warnings identified."

    if crit_warnings:
        tier = "HIGH"
        contributing_rule_ids.extend([w.rule_id for w in crit_warnings])
        rationale = f"High priority triggered by {len(crit_warnings)} CRITICAL contraindication/safety warning(s)."
    elif allergy_high_or_crit:
        tier = "HIGH"
        contributing_rule_ids.extend([w.rule_id for w in allergy_high_or_crit])
        allergy_ids = ", ".join(w.rule_id for w in allergy_high_or_crit)
        rationale = f"High priority: Documented drug/class allergy cross-reactivity warning ({allergy_ids}) requires immediate clinician review."
    elif has_coverage_warning:
        tier = "HIGH"
        coverage_warns = [w for w in warnings if w.rule_id == "COVERAGE-001"]
        contributing_rule_ids.extend([w.rule_id for w in coverage_warns])
        rationale = "High priority: Prescription contains medication(s) outside validated knowledge base (unable to assess safety)."
    elif len(high_warnings) >= 2 or (len(high_warnings) >= 1 and has_reserve_agent):
        tier = "HIGH"
        contributing_rule_ids.extend([w.rule_id for w in high_warnings])
        if has_reserve_agent:
            rationale = "High priority: Combination of HIGH safety warning with WHO Reserve group antimicrobial."
        else:
            rationale = f"High priority triggered by multiple ({len(high_warnings)}) HIGH safety warnings."
    elif len(high_warnings) == 1:
        tier = "MODERATE"
        contributing_rule_ids.extend([w.rule_id for w in high_warnings])
        rationale = "Moderate priority triggered by 1 HIGH safety warning."
    elif len(mod_warnings) >= 2:
        tier = "MODERATE"
        contributing_rule_ids.extend([w.rule_id for w in mod_warnings])
        rationale = f"Moderate priority triggered by multiple ({len(mod_warnings)}) MODERATE safety warnings."
    else:
        if mod_warnings:
            contributing_rule_ids.extend([w.rule_id for w in mod_warnings])
        tier = "LOW"
        rationale = "Low stewardship priority: Standard Access or low-risk therapy with minimal safety concerns."

    # Deduplicate rule IDs while preserving order
    deduped_rule_ids = list(dict.fromkeys(contributing_rule_ids))

    return {
        "tier": tier,
        "contributing_rule_ids": deduped_rule_ids,
        "rationale": rationale,
        "basis": "deterministic_severity_rollup"
    }
