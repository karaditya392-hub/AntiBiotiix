"""
Make recorded pregnancy contraindications actionable (rule VULN-008).

THE GAP
Twelve drugs in the knowledge base carry a pregnancy_category that states a
contraindication. Three of them are read by a rule: ciprofloxacin and levofloxacin
by VULN-001, doxycycline by VULN-002. The other nine are recorded and never
evaluated -- including gentamicin, whose own record reads "Category D / HIGH RISK
(Risk of irreversible congenital bilateral sensorineural deafness...)". Adding the
hepatitis antivirals made this worse rather than better: ribavirin, sofosbuvir,
daclatasvir, velpatasvir and entecavir all arrived with a recorded pregnancy
contraindication and nothing to read it.

WHY A FLAG AND NOT A TEXT MATCH
pregnancy_category is prose, and the prose is not uniform:

  ribavirin                "CONTRAINDICATED..."                       -> fire
  entecavir                "NOT RECOMMENDED IN PREGNANCY..."          -> fire
  gentamicin               "Category D / HIGH RISK..."                -> fire
  nitrofurantoin           "Category B (Contraindicated AT TERM,      -> do NOT fire on
                            38-42 weeks gestation...)"                   trimester alone
  amoxicillin-clavulanate  "Category B (Use with caution; avoid       -> do not fire
                            near term...)"
  clarithromycin           "Category C (Avoid ... unless no           -> do not fire
                            alternative; azithromycin preferred)"

A keyword match on "contraindicated" or "avoid" fires on the last three, and the
nitrofurantoin case is the sharp one: the contraindication is real but applies at
38-42 weeks, and this system records a trimester, not a gestational week. Firing it
in the first trimester would be a false alarm derived from a true sentence.

So membership is explicit, per drug, and each entry below records the wording that
justifies it. Nitrofurantoin, amoxicillin-clavulanate and clarithromycin are
deliberately excluded and the reason is recorded with them.

DOUBLE-FIRING
VULN-008 skips any drug already handled by a drug-specific pregnancy rule
(ciprofloxacin, levofloxacin, doxycycline, primaquine), so a single prescription
never raises two pregnancy warnings for the same agent.

Usage:
    python -m scripts.add_pregnancy_contraindication_rule --check
    python -m scripts.add_pregnancy_contraindication_rule --apply
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

CATALOG = pathlib.Path("backend/guidelines/data/clinical_rules_catalog.json")
DRUGS = pathlib.Path("backend/guidelines/data/drug_safety_database.json")

# drug key -> why its own recorded wording justifies the flag.
CONTRAINDICATED = {
    "gentamicin": "Recorded as \"Category D / HIGH RISK\" with irreversible fetal ototoxicity.",
    "ribavirin": "Recorded as \"CONTRAINDICATED\"; the held guideline cites fetal abnormalities.",
    "sofosbuvir": "Recorded as \"CONTRAINDICATED in pregnancy\" per the held hepatitis guideline.",
    "daclatasvir": "Recorded as \"CONTRAINDICATED in pregnancy\" per the held hepatitis guideline.",
    "velpatasvir": "Recorded as \"CONTRAINDICATED in pregnancy\" per the held hepatitis guideline.",
    "entecavir": "Recorded as \"NOT RECOMMENDED IN PREGNANCY\" by the held hepatitis guideline.",
}

# Deliberately NOT flagged, and why. Written into the records so the omission is a
# decision on the file rather than an oversight nobody can see.
NOT_FLAGGED = {
    "nitrofurantoin": (
        "NOT flagged for VULN-008. Its recorded contraindication applies at term (38-42 weeks "
        "gestation); this system records a trimester, not a gestational week, so a "
        "trimester-level alert would fire outside the window the source describes."
    ),
    "amoxicillin_clavulanate": (
        "NOT flagged for VULN-008. Recorded as Category B with caution near term, which is a "
        "caution rather than a contraindication."
    ),
    "clarithromycin": (
        "NOT flagged for VULN-008. Recorded as Category C, to be avoided unless no alternative "
        "exists, which is a preference rather than a contraindication."
    ),
}

RULE = {
    "rule_id": "VULN-008",
    "rule_name": "Antimicrobial with a Recorded Pregnancy Contraindication",
    "category": "VULNERABLE_POPULATION",
    "severity": "HIGH",
    "description": (
        "A pregnant patient is prescribed an antimicrobial whose knowledge-base record states a "
        "pregnancy contraindication, and which no drug-specific rule already covers. Before this "
        "rule, only three of the twelve drugs carrying such a record were read by any rule: "
        "gentamicin's own entry recorded a risk of irreversible congenital deafness and nothing "
        "evaluated it, and the hepatitis antivirals arrived with recorded contraindications that "
        "were equally inert. The rule fires on an EXPLICIT per-drug flag rather than on keyword "
        "matching of the prose, because the prose is not uniform: nitrofurantoin's "
        "contraindication applies at 38-42 weeks gestation and this system records only a "
        "trimester, so a text match would raise a first-trimester alarm from a true sentence "
        "about term."
    ),
    "input_conditions": (
        "pregnancy_status is any PREGNANT_TRIMESTER value AND the prescribed drug's record "
        "carries pregnancy_contraindicated == true AND no drug-specific pregnancy rule "
        "(VULN-001, VULN-002, VULN-006) already applies to that drug."
    ),
    "output_concern": (
        "Potential pregnancy contraindication identified. The prescribed antimicrobial's record "
        "in this system states a contraindication in pregnancy, and the patient is documented as "
        "pregnant."
    ),
    "recommendation": (
        "Review against the drug's recorded pregnancy position, shown verbatim with this "
        "warning, and select an alternative where one exists. This rule reports what the "
        "knowledge base records; it does not grade fetal risk by trimester, and where the "
        "recorded contraindication is gestation-specific the record says so."
    ),
    "evidence_source": (
        "Per-drug pregnancy records in this system's drug knowledge base, each carrying its own "
        "source. The hepatitis antiviral entries are drawn from the National Guidelines for "
        "Diagnosis & Management of Viral Hepatitis (2018) [MOHFW-NVHCP-VIRAL-HEPATITIS-2018]."
    ),
    "guideline_version": "Per drug; see each drug's recorded pregnancy_category",
    "effective_date": None,
    "review_date": None,
    "author": "SYSTEM_GENERATED",
    "approval_status": "PENDING_CLINICAL_REVIEW",
    "approved_by": None,
    "source_url": None,
    "section_page": "Drug knowledge base pregnancy records",
    "unverified_sources": [],
}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--apply", action="store_true")
    a = p.parse_args()

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    doc = json.loads(DRUGS.read_text(encoding="utf-8"))
    drugs = doc.get("drugs", doc)

    if RULE["rule_id"] in {r["rule_id"] for r in catalog["rules"]}:
        print(f"REFUSING: {RULE['rule_id']} already present.")
        return 1

    missing = sorted((set(CONTRAINDICATED) | set(NOT_FLAGGED)) - set(drugs))
    if missing:
        print(f"REFUSING: drug key(s) not in the knowledge base: {missing}")
        return 1

    print("Flagged as contraindicated in pregnancy:")
    for key, why in CONTRAINDICATED.items():
        print(f"  {key:<24} {why}")
    print("\nDeliberately NOT flagged:")
    for key, why in NOT_FLAGGED.items():
        print(f"  {key:<24} {why[:96]}")
    print(f"\nRule: {RULE['rule_id']} {RULE['severity']} - {RULE['rule_name']}")

    if a.check:
        print("\n--check only. Nothing written.")
        return 0

    for key, why in CONTRAINDICATED.items():
        drugs[key]["pregnancy_contraindicated"] = True
        drugs[key]["pregnancy_contraindication_basis"] = why
    for key, why in NOT_FLAGGED.items():
        drugs[key]["pregnancy_contraindicated"] = False
        drugs[key]["pregnancy_contraindication_basis"] = why

    catalog["rules"].append(RULE)
    catalog["catalog_version"] = "3.4.0"
    catalog["pregnancy_rule_note"] = (
        "3.4.0 added VULN-008, which reads an explicit per-drug pregnancy_contraindicated flag. "
        "Nine drugs carried a recorded pregnancy contraindication that no rule evaluated, "
        "gentamicin among them. Drugs whose recorded contraindication is gestation-specific or "
        "is a caution rather than a contraindication are flagged false, with the reason recorded "
        "on the drug. PENDING_CLINICAL_REVIEW."
    )
    CATALOG.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
    DRUGS.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {CATALOG}: {len(catalog['rules'])} rules, version {catalog['catalog_version']}")
    print(f"wrote {DRUGS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
