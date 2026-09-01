"""
Fill drug-knowledge gaps and add rules from ICMR-STG-2019-ED2, which is held here
as a hash-verified PDF.

WHAT THIS FIXES FIRST
The knowledge-base records for voriconazole and primaquine both carry:

    "The fields listed in coverage_gaps are not stated in any document held by
     this repository and have NOT been supplied from memory."

That sentence is FALSE for several of the listed fields, and has been for as long
as ICMR-STG-2019-ED2 has been in the corpus. That document states, verbatim:

  voriconazole (p. 184)  hepatic dose reduction, a renal restriction on the IV
                         cyclodextrin preparation, and an explicit contraindicated
                         drug list
  primaquine (pp. 19-20) exclusion of pregnant women and women breastfeeding
                         infants under 6 months, and that G6PD status should guide
                         administration

Under-claiming coverage is not a safe failure. COVERAGE-001 fires "safety checks
could not be evaluated" for these drugs while the evidence sits in a held document,
which is both alert noise and a check that never runs. The gaps are closed here
with the document's own words, and only the gaps that document actually closes.

THE THREE RULES

  DDI-005   Contraindicated Azole - Enzyme Inducer Combination
            ICMR-STG-2019-ED2 p. 184 lists voriconazole as contraindicated with
            rifampicin, carbamazepine, long-acting barbiturates, phenytoin and
            ivabradine. The existing DDI rules cover QT prolongation, serotonin
            syndrome, statins and warfarin; a stated CONTRAINDICATION had no rule.

  VULN-006  Primaquine in Pregnancy or Breastfeeding an Infant Under 6 Months
            The exclusion is stated in the same sentence as the recommendation, so
            a system holding one and not the other is holding half a guideline.

  VULN-007  Primaquine Prescribed Without Documented G6PD Status
            LOW. The source does not say do not prescribe: it says the decision
            must be a risk-benefit assessment when status is unknown. The rule says
            exactly that and no more.

All three ship PENDING_CLINICAL_REVIEW.

Usage:
    python -m scripts.add_rules_from_stg_2019 --check
    python -m scripts.add_rules_from_stg_2019 --apply
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

CATALOG = pathlib.Path("backend/guidelines/data/clinical_rules_catalog.json")
DRUGS = pathlib.Path("backend/guidelines/data/drug_safety_database.json")

_STG = "ICMR Treatment Guidelines for Antimicrobial Use in Common Syndromes, 2nd edition (2019) [ICMR-STG-2019-ED2]"

# Verbatim from the held PDF. Quoted rather than paraphrased so the claim and its
# evidence cannot drift apart.
VORICONAZOLE_INTERACTIONS = [
    {
        "interacting_drug_or_class": drug,
        "severity": "CONTRAINDICATED",
        "mechanism": (
            "Stated as a contraindication by the source; the pharmacological basis is not "
            "given in the held text and is not supplied here."
        ),
        "recommendation": (
            "The guideline lists this combination as contraindicated. Select an alternative "
            "antifungal or an alternative to the interacting agent, or seek specialist advice."
        ),
        "evidence_source": _STG + ", p. 184",
        "verbatim_passage": (
            "Contraindicated with rifampicin, carbamazepine, long acting barbiturates, "
            "phenytoin, Ivabradine. Interactions with warfarin, Tacrolimus and cyclosporine"
        ),
    }
    for drug in ["rifampicin", "carbamazepine", "phenytoin", "barbiturate", "ivabradine"]
]

DRUG_UPDATES = {
    "voriconazole": {
        "interactions": VORICONAZOLE_INTERACTIONS,
        "hepatic_dosing": {
            "requires_adjustment": True,
            "recommendation": "Reduce to 50% of dose in Child-Pugh Class A or B.",
            "evidence_source": _STG + ", p. 184",
            "evidence_passage": "Dose reduction : 50 % of dose in Child-pugh Class A/B",
        },
        "renal_dosing": {
            "egfr_threshold_ml_min": 50,
            "recommendation": (
                "The intravenous preparation contains cyclodextrin and is restricted below "
                "CrCl 50 mL/min. The oral route is not subject to this restriction."
            ),
            "evidence_source": _STG + ", p. 184",
            "evidence_passage": (
                "IV preparation containing cyclodextrin should not be administered in "
                "Patients with CrCL < 50"
            ),
        },
        "_close_gaps": ["interactions", "hepatic_dosing", "renal_dosing"],
    },
    "primaquine": {
        "pregnancy_category": (
            "EXCLUDED IN PREGNANCY by the held guideline, which excepts pregnant women from "
            "primaquine administration. No FDA pregnancy category is stated in any document "
            "held here and none is supplied."
        ),
        "lactation_safety": (
            "Excluded in women breastfeeding infants aged under 6 months, and in infants "
            "aged under 6 months, by the held guideline."
        ),
        "_close_gaps": ["pregnancy_category", "lactation_safety"],
        "_evidence": {
            "evidence_source": _STG + ", pp. 19-20",
            "verbatim_passage": (
                "give a single dose of 0.25 mg/kg body weight (BW) primaquine with ACT to "
                "patients with P. falciparum malaria (except pregnant women, infants aged < 6 "
                "months and women breastfeeding infants aged < 6 months) to reduce "
                "transmission. G6PD testing is not required."
            ),
        },
    },
}

NEW_RULES = [
    {
        "rule_id": "DDI-005",
        "rule_name": "Contraindicated Azole - Enzyme Inducer Combination",
        "category": "DRUG_INTERACTION",
        "severity": "CRITICAL",
        "description": (
            "Voriconazole is prescribed alongside an agent the held national guideline lists "
            "as contraindicated with it: rifampicin, carbamazepine, a long-acting barbiturate, "
            "phenytoin or ivabradine. The existing interaction rules cover QT prolongation "
            "(DDI-002), serotonin syndrome (DDI-003), statin myopathy (DDI-004) and warfarin "
            "(DDI-001); a combination the guideline states outright as CONTRAINDICATED had no "
            "rule of its own, and would previously have surfaced, if at all, as a generic "
            "interaction. The source states the contraindication without giving a mechanism, "
            "and no mechanism is supplied here."
        ),
        "input_conditions": (
            "Prescribed Voriconazole AND a home medication or co-prescribed item matching "
            "rifampicin, carbamazepine, phenytoin, a barbiturate, or ivabradine."
        ),
        "output_concern": (
            "Potential contraindicated combination identified. The national treatment "
            "guideline held by this system lists this pairing as contraindicated with "
            "voriconazole."
        ),
        "recommendation": (
            "Review urgently. The guideline lists this combination as contraindicated: select "
            "an alternative antifungal, or an alternative to the interacting agent, or seek "
            "infectious diseases and pharmacy advice before administration."
        ),
        "evidence_source": _STG,
        "guideline_version": "2nd edition (2019)",
        "effective_date": None,
        "review_date": None,
        "author": "SYSTEM_GENERATED",
        "approval_status": "PENDING_CLINICAL_REVIEW",
        "approved_by": None,
        "source_url": None,
        "section_page": (
            "p. 184, antifungal agents table, entry 4 (Voriconazole): \"Contraindicated with "
            "rifampicin, carbamazepine, long acting barbiturates, phenytoin, Ivabradine.\""
        ),
        "unverified_sources": [],
    },
    {
        "rule_id": "VULN-006",
        "rule_name": "Primaquine in Pregnancy or Breastfeeding an Infant Under 6 Months",
        "category": "VULNERABLE_POPULATION",
        "severity": "HIGH",
        "description": (
            "Primaquine is prescribed to a patient who is pregnant, or who is documented as "
            "lactating. The held national guideline states its primaquine recommendation and "
            "its exclusions in the same sentence: pregnant women, infants under 6 months and "
            "women breastfeeding infants under 6 months are excepted. A system that held the "
            "recommendation without the exception would be holding half of it. THE RULE IS "
            "WIDER THAN THE SOURCE ON LACTATION: the guideline excludes women breastfeeding "
            "infants UNDER 6 MONTHS, and this system does not record the infant's age, so the "
            "alert is raised for any documented lactation and says so."
        ),
        "input_conditions": (
            "Prescribed Primaquine AND (pregnancy_status is any PREGNANT_TRIMESTER value OR "
            "lactation_status == 'LACTATING')."
        ),
        "output_concern": (
            "Potential vulnerable-population exclusion identified. The held national guideline "
            "excepts pregnant women and women breastfeeding infants under 6 months from "
            "primaquine administration."
        ),
        "recommendation": (
            "Review against the guideline exclusion. Where the patient is lactating, establish "
            "the infant's age: the stated exclusion applies to infants under 6 months, and "
            "this system does not hold that age. Chloroquine prophylaxis of relapse is "
            "discussed by the same source as the option in pregnancy."
        ),
        "evidence_source": _STG,
        "guideline_version": "2nd edition (2019)",
        "effective_date": None,
        "review_date": None,
        "author": "SYSTEM_GENERATED",
        "approval_status": "PENDING_CLINICAL_REVIEW",
        "approved_by": None,
        "source_url": None,
        "section_page": (
            "pp. 19-20, section 2.2.2 / 2.2.4.3: \"(except pregnant women, infants aged < 6 "
            "months and women breastfeeding infants aged < 6 months)\""
        ),
        "unverified_sources": [],
    },
    {
        "rule_id": "VULN-007",
        "rule_name": "Primaquine Prescribed Without Documented G6PD Status",
        "category": "VULNERABLE_POPULATION",
        "severity": "LOW",
        "description": (
            "Primaquine is prescribed and no glucose-6-phosphate dehydrogenase (G6PD) status "
            "is recorded in the patient's history. The held national guideline states that "
            "G6PD status should be used to guide administration of primaquine for preventing "
            "relapse, and that where status is unknown and testing unavailable the decision "
            "must rest on an assessment of risks and benefits. The rule says exactly that and "
            "no more: the source does NOT say withhold primaquine, and the same source notes "
            "that for the single low-dose transmission-blocking indication G6PD testing is not "
            "required. LOW severity accordingly - this is a prompt to record a status, not a "
            "finding against the prescription."
        ),
        "input_conditions": (
            "Prescribed Primaquine AND no entry in medical_history or clinical_notes matching "
            "G6PD / glucose-6-phosphate dehydrogenase."
        ),
        "output_concern": (
            "G6PD status is not documented for a patient prescribed primaquine. The held "
            "guideline uses G6PD status to guide primaquine administration for relapse "
            "prevention."
        ),
        "recommendation": (
            "Record the patient's G6PD status where testing is available. Where it is unknown "
            "and testing is unavailable, the held guideline states the decision must be based "
            "on an assessment of the risks and benefits, weighing relapse prevention against "
            "potential primaquine-induced haemolysis. For single-dose transmission-blocking "
            "use the same source states G6PD testing is not required."
        ),
        "evidence_source": _STG,
        "guideline_version": "2nd edition (2019)",
        "effective_date": None,
        "review_date": None,
        "author": "SYSTEM_GENERATED",
        "approval_status": "PENDING_CLINICAL_REVIEW",
        "approved_by": None,
        "source_url": None,
        "section_page": (
            "p. 20, section 2.2.4.3: \"The G6PD status of patients should be used to guide "
            "administration of primaquine for preventing relapse.\""
        ),
        "unverified_sources": [],
    },
]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--apply", action="store_true")
    a = p.parse_args()

    for path in (CATALOG, DRUGS):
        if not path.exists():
            print(f"REFUSING: {path} not found. Run from the repository root.")
            return 1

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    drugs_doc = json.loads(DRUGS.read_text(encoding="utf-8"))
    drugs = drugs_doc.get("drugs", drugs_doc)

    existing = {r["rule_id"] for r in catalog["rules"]}
    clash = sorted({r["rule_id"] for r in NEW_RULES} & existing)
    if clash:
        print(f"REFUSING: rule id(s) already present: {clash}")
        return 1

    reference = catalog["rules"][0]
    for rule in NEW_RULES:
        missing = sorted(set(reference) - set(rule))
        if missing:
            print(f"REFUSING: {rule['rule_id']} missing catalog field(s): {missing}")
            return 1

    print("Closing knowledge-base gaps the held document actually closes:")
    for key, update in DRUG_UPDATES.items():
        if key not in drugs:
            print(f"REFUSING: {key} not in the drug knowledge base")
            return 1
        closing = update["_close_gaps"]
        remaining = [g for g in drugs[key].get("coverage_gaps", []) if g not in closing]
        print(f"  {key:<14} closes {closing}")
        print(f"  {'':<14} still open: {remaining or 'none'}")
        if a.apply:
            for field, value in update.items():
                if field.startswith("_"):
                    continue
                drugs[key][field] = value
            drugs[key]["coverage_gaps"] = remaining
            if not remaining:
                drugs[key]["knowledge_coverage"] = "FULL"
            drugs[key]["coverage_note"] = (
                "Originally added from the ICMR 2022-23 edition, which states indication and "
                "dose only, and recorded as having no held evidence for the fields above. That "
                "was incorrect: ICMR-STG-2019-ED2, a hash-verified PDF held in this repository, "
                "states them. The fields closed above carry that document's own wording and its "
                "page. Any field still listed in coverage_gaps remains unstated in every held "
                "document and has NOT been supplied from memory."
            )

    print("\nAdding rules:")
    for rule in NEW_RULES:
        print(f"  {rule['rule_id']:<10} {rule['severity']:<9} {rule['category']:<22} {rule['rule_name']}")

    if a.check:
        print(f"\n--check only. Catalog would go from {len(existing)} to {len(existing)+len(NEW_RULES)} rules.")
        return 0

    catalog["rules"].extend(NEW_RULES)
    catalog["catalog_version"] = "3.3.0"
    catalog["stg_2019_rule_note"] = (
        "3.3.0 added DDI-005, VULN-006 and VULN-007, all grounded verbatim in "
        "ICMR-STG-2019-ED2, and closed knowledge-base gaps for voriconazole and primaquine "
        "that the same document had always closed. The previous coverage notes on those two "
        "drugs claimed no held document stated those fields, which was false and caused "
        "COVERAGE-001 to report safety checks as unevaluable while the evidence was present. "
        "All three rules are PENDING_CLINICAL_REVIEW."
    )
    CATALOG.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
    DRUGS.write_text(json.dumps(drugs_doc, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {CATALOG}: {len(catalog['rules'])} rules, version {catalog['catalog_version']}")
    print(f"wrote {DRUGS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
