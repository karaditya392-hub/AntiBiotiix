"""
Expand the `description` field of thinly-documented clinical rules.

WHAT THIS DOES AND DOES NOT ADD
Every clinical claim added here is traceable to a document ACTUALLY HELD in this
repository, and the added text names that document. Where the corpus supports
nothing, the description is expanded only with statements about the RULE ITSELF --
what makes it fire, how wide its trigger is, what it cannot see -- which are facts
about this system and are verifiable from backend/rules/engine.py.

Nothing here invents a clinical recommendation, changes any rule's trigger,
severity, category or recommendation, or alters which warnings fire. The rule
engine reads `input_conditions` semantics from code, not from `description`.

WHY THIS BECAME POSSIBLE
The corpus grew from 39 to 94 documents (scripts/ingest_icmr_national_corpus.py).
Passages that were not retrievable when these rules were written now are, and one
rule's evidence note had become false as a result: ALLERGY-004 stated that no
retrievable guideline passage on eliciting allergy history existed. The WHO AWaRe
book, held here, discusses exactly that. Leaving that sentence in place would have
been a stale claim of the kind Spec 22 exists to prevent.

THREE RULES RECORD A SCOPE GAP rather than closing it. VULN-001 fires in all three
trimesters while the national guideline held here contraindicates fluoroquinolones
in the first; VULN-002 fires on 2nd/3rd trimester while the held national text
addresses nursing mothers; RENAL-002 has no supporting passage in the corpus at
all. Widening or narrowing a trigger to match is a clinical decision, so the
descriptions state the gap and the triggers are untouched.

Every rule remains PENDING_CLINICAL_REVIEW. These are edits to clinical text and
require a clinician sign-off through the governance flow before they mean anything.

Usage:
    python -m scripts.expand_rule_descriptions --check
    python -m scripts.expand_rule_descriptions --apply
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Dict

CATALOG = pathlib.Path("backend/guidelines/data/clinical_rules_catalog.json")

# rule_id -> replacement description.
#
# Held-document citations use the corpus document_id so a reader can retrieve the
# passage. Claims attributed to a document NOT held are never added here; the
# existing `unverified_sources` field is where those already live.
DESCRIPTIONS: Dict[str, str] = {
    "ALLERGY-001": (
        "Prescribed medication matches an exact documented drug allergy in the patient's "
        "medical record, by generic or brand name. This is a string-level match against "
        "what is recorded for the patient: it fires on the name, and therefore cannot "
        "distinguish a true IgE-mediated allergy from an intolerance or a previously "
        "mislabelled reaction. WHO-AWARE-BOOK-2022 notes that a true immune-mediated "
        "antibiotic allergy is rare, and that intolerance reactions and viral rashes are "
        "commonly recorded as allergies. That distinction is exactly what the clinician "
        "is asked to make below; the system cannot make it from the record alone."
    ),
    "ALLERGY-002": (
        "Prescribed medication belongs to the same structural class (e.g. aminopenicillin) "
        "as a documented allergy, so the concern is the shared beta-lactam core and side "
        "chain rather than the specific agent. WHO-AWARE-BOOK-2022 describes cross-"
        "reactivity between penicillin and other beta-lactams as arising from closely "
        "related structure. The rule fires on class membership and does not grade the "
        "severity of the original reaction, which is the factor that determines whether "
        "an alternative is required or a supervised challenge is appropriate."
    ),
    "ALLERGY-003": (
        "Patient has a documented penicillin allergy and is prescribed a cephalosporin. "
        "Cross-reactivity between penicillin and other beta-lactams is described in "
        "WHO-AWARE-BOOK-2022 as following from closely related structure, and it is "
        "generation-dependent: the cross-reactivity estimates this rule carries are "
        "roughly 5-10% for 1st and 2nd generation agents and under 1-2% for 3rd and 4th. "
        "Severity is MODERATE rather than CRITICAL for that reason - for most 3rd-"
        "generation cephalosporins the expected risk is low, and the alert exists to "
        "prompt a check of the original reaction rather than to block the prescription."
    ),
    "ALLERGY-004": (
        "Patient allergy status is recorded as unknown or has not been elicited, so no "
        "allergy rule in this catalog can be evaluated for this prescription. The "
        "severity is LOW because nothing unsafe has been detected; what has been detected "
        "is that the safety check could not run, and an absent allergy history must not "
        "be read as an absence of allergy. WHO-AWARE-BOOK-2022 notes that recorded "
        "antibiotic allergies are frequently intolerance reactions or viral rashes rather "
        "than true immune-mediated allergy, which is why the history is worth eliciting "
        "properly rather than assumed either way."
    ),
    "RENAL-002": (
        "Nitrofurantoin prescribed in a patient with eGFR below 30 mL/min. NO SUPPORTING "
        "PASSAGE FOR THIS THRESHOLD IS RETRIEVABLE FROM THE CORPUS HELD HERE: the "
        "concerns stated below (loss of urinary efficacy, peripheral neuropathy risk) are "
        "carried by the rule itself and by the product labelling, and the additional "
        "authority named in this rule's rationale has no ingested document. See "
        "RENAL-004, which covers the 30-59 mL/min band where the FDA label and this "
        "system's ICMR-derived threshold openly disagree. The eGFR used is CKD-EPI 2021, "
        "an implemented formula rather than an ingested guideline."
    ),
    "VULN-001": (
        "Prescription of ciprofloxacin or levofloxacin in a pregnant or lactating patient. "
        "THE TRIGGER IS WIDER THAN THE GUIDANCE HELD HERE, deliberately: this rule fires "
        "in all three trimesters, while NCDC-NTG-AMR-2016 states that fluoroquinolones "
        "are contraindicated in the first trimester and the corpus holds no passage "
        "extending that to the second or third. The cartilage-toxicity concern below is "
        "not trimester-limited in the product labelling, so the alert is raised "
        "throughout; a clinician reviewing a second or third trimester alert should know "
        "the national guideline held here speaks only to the first."
    ),
    "VULN-002": (
        "Prescription of doxycycline or another tetracycline in the second or third "
        "trimester of pregnancy, when fetal dental and skeletal development is under way. "
        "The teratogenicity concern below is drawn from the product labelling. The "
        "national guideline held here addresses a neighbouring but distinct case: "
        "NCDC-NTG-AMR-2016 states that doxycycline is not recommended in nursing mothers. "
        "The corpus therefore supports caution around doxycycline in pregnancy and "
        "lactation without containing the trimester-specific statement this rule encodes."
    ),
    "VULN-003": (
        "An antimicrobial is prescribed for a paediatric patient, where dosing is "
        "calculated per kilogram of body weight rather than from a fixed adult dose. "
        "WHO-AWARE-BOOK-2022 carries a dedicated children's dosing chapter on exactly "
        "this basis. The rule fires on age alone and does NOT verify the arithmetic: it "
        "cannot confirm that the prescribed dose matches the recommended mg/kg/day "
        "schedule, only that a paediatric prescription requires that check. A recorded "
        "weight is a precondition for making it."
    ),
    "STEWARD-001": (
        "The prescribed agent is classified in the WHO Reserve group - antibiotics held "
        "back as last-resort options. WHO-AWARE-BOOK-2022, which is the source of that "
        "classification and is held here in full, states that Reserve antibiotics could "
        "be considered for empiric therapy only in very select cases where a "
        "multidrug-resistant pathogen can be strongly suspected. The alert is a "
        "stewardship prompt, not a finding of error: the rule sees the agent's AWaRe "
        "category and cannot see the culture result, local resistance pattern or prior "
        "therapy that may well justify a Reserve agent in this patient."
    ),
}


def load() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--apply", action="store_true")
    a = p.parse_args()

    if not CATALOG.exists():
        print(f"REFUSING: {CATALOG} not found. Run from the repository root.")
        return 1

    data = load()
    by_id = {r["rule_id"]: r for r in data["rules"]}

    missing = sorted(set(DESCRIPTIONS) - set(by_id))
    if missing:
        print(f"REFUSING: rule id(s) not in the catalog: {missing}")
        return 1

    for rule_id, new_text in DESCRIPTIONS.items():
        rule = by_id[rule_id]
        old = rule["description"]
        print(f"  {rule_id:<14} {len(old):>4} -> {len(new_text):>4} chars")
        if a.apply:
            rule["description"] = new_text

    # ALLERGY-004's evidence note stated that no retrievable guideline passage on
    # eliciting allergy history existed. The WHO AWaRe book is held here and
    # discusses it, so the sentence had become false.
    allergy_004 = by_id["ALLERGY-004"]
    corrected = (
        "FDA Structured Product Label - amoxicillin (via NLM DailyMed), and "
        "WHO-AWARE-BOOK-2022, which discusses the distinction between true "
        "immune-mediated antibiotic allergy, intolerance reactions and viral rash. An "
        "earlier version of this field stated that no retrievable guideline passage on "
        "eliciting allergy history existed; that was true of the corpus as it stood and "
        "is no longer true."
    )
    print(f"\n  ALLERGY-004 evidence_source corrected (stale 'no retrievable passage' claim)")
    if a.apply:
        allergy_004["evidence_source"] = corrected

    if a.check:
        print("\n--check only. Nothing written.")
        return 0

    data["catalog_version"] = "3.1.0"
    data["description_expansion_note"] = (
        "3.1.0 expanded the `description` field of 9 rules and corrected ALLERGY-004's "
        "evidence_source. Every clinical claim added names a document held in this "
        "repository; where the corpus supports nothing, the expansion is limited to "
        "statements about the rule's own behaviour. No trigger, severity, category or "
        "recommendation changed, and no warning fires differently. VULN-001, VULN-002 "
        "and RENAL-002 record a gap between the rule's trigger and the guidance actually "
        "held, rather than closing it: changing a trigger is a clinical decision. All "
        "rules remain PENDING_CLINICAL_REVIEW."
    )
    CATALOG.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {CATALOG} (catalog_version -> {data['catalog_version']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
