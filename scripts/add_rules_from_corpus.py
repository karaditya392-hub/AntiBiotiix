"""
Add clinical rules grounded in documents held in the retrieval corpus.

TWO RULES, AND WHY THESE TWO
Both close a gap that is structural rather than clinical -- a field this system
already collects and never reads, and a syndrome match it already makes and never
acts on. Neither invents a clinical position.

  VULN-005  Antimicrobial in a Lactating Patient
            `lactation_status` is on every PatientCreate, `lactation_safety` is on
            the drug records, and NO rule in the engine reads either. The system
            has been asking clinicians for lactation status and discarding it.
            NCDC-NTG-AMR-2016 states plainly that doxycycline is not recommended in
            nursing mothers, and NCDC-LEPTOSPIROSIS-2015 names ampicillin as the
            agent for pregnant and lactating women instead. The rule reads the
            drug's own lactation_safety text rather than carrying clinical claims
            of its own.

  DIAG-002  Prescribed Agent Not Among Guideline-Named Options
            DIAG-001 fires only on a syndrome's `avoid_empirical` list. None of the
            four syndromes added from the corpus
            (scripts/add_syndromes_from_corpus.py) has one, because none of their
            source documents names an agent to avoid -- so those syndromes matched
            a diagnosis and then changed nothing. DIAG-002 states the weaker,
            checkable fact instead: the prescribed agent is not among the agents
            this guideline names for this syndrome.

            LOW severity, deliberately. "Not named by this guideline" is not
            "wrong": a guideline lists common options, not every acceptable one,
            and culture results, allergy and local resistance all justify agents no
            guideline enumerates. Raising it higher would manufacture alarm from an
            absence.

WHAT NEITHER RULE DOES
Neither changes an existing rule, and neither asserts a clinical recommendation
this repository cannot cite. Both ship as PENDING_CLINICAL_REVIEW and mean nothing
until a clinician signs them off through the governance flow.

Usage:
    python -m scripts.add_rules_from_corpus --check
    python -m scripts.add_rules_from_corpus --apply
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

CATALOG = pathlib.Path("backend/guidelines/data/clinical_rules_catalog.json")

NEW_RULES = [
    {
        "rule_id": "VULN-005",
        "rule_name": "Antimicrobial Lactation Safety Review",
        "category": "VULNERABLE_POPULATION",
        "severity": "MODERATE",
        "description": (
            "An antimicrobial with recorded lactation-safety concerns is prescribed to a "
            "patient documented as lactating. Until this rule existed, `lactation_status` "
            "was collected on every patient and read by no rule in the engine, and the "
            "`lactation_safety` field on each drug record was never evaluated: the system "
            "asked for the information and discarded it. The rule reports the drug's own "
            "recorded lactation position rather than asserting one, and fires at MODERATE "
            "because most antimicrobials are compatible with breastfeeding and the "
            "clinically relevant question is usually duration of exposure, not whether to "
            "treat."
        ),
        "input_conditions": (
            "lactation_status == 'LACTATING' AND the prescribed drug's knowledge base entry "
            "carries a non-empty lactation_safety statement."
        ),
        "output_concern": (
            "Potential lactation safety consideration identified. The prescribed antimicrobial "
            "carries a recorded lactation-safety statement in this system's drug knowledge "
            "base, and the patient is documented as lactating."
        ),
        "recommendation": (
            "Review the drug's recorded lactation position, shown with this warning, against "
            "the expected duration of therapy and the age of the infant. Where an alternative "
            "with a more established safety position exists, consider it. NCDC-LEPTOSPIROSIS-2015 "
            "names ampicillin for pregnant and lactating women where doxycycline is otherwise "
            "first-line. Interrupting breastfeeding is rarely necessary and should not be "
            "advised reflexively."
        ),
        "evidence_source": (
            "NCDC National Treatment Guidelines for Antimicrobial Use in Infectious Diseases, "
            "Version 1.0 (2016) [NCDC-NTG-AMR-2016], and NCDC National Guidelines on "
            "Leptospirosis (2015) [NCDC-LEPTOSPIROSIS-2015]. Per-drug lactation statements are "
            "carried in this system's drug knowledge base and are surfaced verbatim with the "
            "warning."
        ),
        "guideline_version": "NCDC-NTG-AMR-2016 Version 1.0 (2016); NCDC-LEPTOSPIROSIS-2015 (2015)",
        "effective_date": None,
        "review_date": None,
        "author": "SYSTEM_GENERATED",
        "approval_status": "PENDING_CLINICAL_REVIEW",
        "approved_by": None,
        "source_url": "http://www.ncdc.gov.in/",
        "section_page": (
            "NCDC-NTG-AMR-2016, Section G (Obstetrics and Gynaecological Infections): "
            "\"Doxycycline is not recommended in nursing mothers. If need to administer "
            "doxycycline discontinuation of nursing may be contemplated.\""
        ),
        "unverified_sources": [],
    },
    {
        "rule_id": "DIAG-002",
        "rule_name": "Prescribed Agent Not Among Guideline-Named Options",
        "category": "DIAGNOSIS_GUIDELINE",
        "severity": "LOW",
        "description": (
            "A syndrome guideline was matched for this diagnosis, and the prescribed "
            "antimicrobial is not among any of the agents that guideline names for it - "
            "neither first-line, nor alternative, nor severe-presentation, nor "
            "penicillin-allergic. This is a weaker statement than DIAG-001, which fires only "
            "when a guideline explicitly lists an agent to AVOID. Four of the nine syndromes "
            "held here carry no avoid list at all, because their source documents state none, "
            "so before this rule a matched syndrome could change nothing about the review. "
            "The severity is LOW because a guideline enumerates common options rather than "
            "every acceptable one: culture results, allergy history and local resistance all "
            "justify agents no guideline lists."
        ),
        "input_conditions": (
            "A syndrome guideline matches the diagnosis AND the normalized prescribed drug is "
            "absent from every named agent list on that syndrome entry "
            "(first_line_preferred, alternative_atypical, alternative_penicillin_allergic, "
            "second_line, inpatient_severe, mrsa_suspected)."
        ),
        "output_concern": (
            "Prescribed agent is not among the options named by the matched syndrome guideline. "
            "This is an observation about the guideline's contents, NOT a finding that the "
            "prescription is inappropriate."
        ),
        "recommendation": (
            "Confirm the clinical reason for selecting an agent outside the guideline's named "
            "options - culture and susceptibility, documented allergy, local resistance, or "
            "prior therapy are all valid reasons. The agents this guideline does name are "
            "listed with this warning, together with the source document the syndrome entry "
            "was drawn from."
        ),
        "evidence_source": (
            "Computed against the syndrome entry matched for this diagnosis. Each syndrome "
            "entry names its own source document (source_document_id), and that document is "
            "reported with the warning rather than a generic guideline reference."
        ),
        "guideline_version": "Per matched syndrome; see the source_document_id on the entry",
        "effective_date": None,
        "review_date": None,
        "author": "SYSTEM_GENERATED",
        "approval_status": "PENDING_CLINICAL_REVIEW",
        "approved_by": None,
        "source_url": None,
        "section_page": "Syndrome Guideline Named-Agent Comparison",
        "unverified_sources": [],
    },
]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--apply", action="store_true")
    a = p.parse_args()

    if not CATALOG.exists():
        print(f"REFUSING: {CATALOG} not found. Run from the repository root.")
        return 1

    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    existing = {r["rule_id"] for r in data["rules"]}

    clash = sorted({r["rule_id"] for r in NEW_RULES} & existing)
    if clash:
        print(f"REFUSING: rule id(s) already in the catalog, refusing to overwrite: {clash}")
        return 1

    # Every field the engine's _create_warning validates must be present, or the
    # rule would fail loudly at evaluation time rather than here.
    reference = data["rules"][0]
    for rule in NEW_RULES:
        missing = sorted(set(reference) - set(rule))
        if missing:
            print(f"REFUSING: {rule['rule_id']} is missing catalog field(s): {missing}")
            return 1
        print(f"  {rule['rule_id']:<10} {rule['severity']:<9} {rule['category']:<22} {rule['rule_name']}")

    if a.check:
        print(f"\n--check only. Catalog would go from {len(existing)} to {len(existing) + len(NEW_RULES)} rules.")
        return 0

    data["rules"].extend(NEW_RULES)
    data["catalog_version"] = "3.2.0"
    data["new_rule_note"] = (
        "3.2.0 added VULN-005 (lactation safety) and DIAG-002 (agent not among "
        "guideline-named options). Both are grounded in documents held in the retrieval "
        "corpus and both close a structural gap rather than asserting a new clinical "
        "position: VULN-005 reads a patient field and a drug field the engine collected "
        "and never evaluated, and DIAG-002 acts on syndrome matches that previously "
        "changed nothing. Both are PENDING_CLINICAL_REVIEW."
    )
    CATALOG.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {CATALOG}: {len(data['rules'])} rules, catalog_version {data['catalog_version']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
