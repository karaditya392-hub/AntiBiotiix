"""
Add the hepatitis B and C antivirals to the drug knowledge base.

SOURCE
All of it comes from MOHFW-NVHCP-VIRAL-HEPATITIS-2018 -- the National Guidelines
for Diagnosis & Management of Viral Hepatitis, held here as a hash-verified PDF.
Doses are Tables 3, 4 and 9; the contraindications are pp. 38-39 and 44. Every
field carries the document's own wording and its page.

WHAT IS DELIBERATELY LEFT EMPTY
These entries are knowledge_coverage=PARTIAL. The source is a national treatment
guideline, not a pharmacology reference: it states indication, dose and a small
number of explicit contraindications, and says nothing about renal thresholds for
most agents, hepatic adjustment, or lactation. Those stay in coverage_gaps and
COVERAGE-001 keeps firing for them, which is the point -- a clinician is told the
assessment is incomplete instead of being given a silent all-clear. Nothing was
supplied from memory to make an entry look finished.

SUPER-CLASSES ARE MECHANISTIC, AND THAT IS LOAD-BEARING
DUP-002 fires when two prescribed drugs share a super_class. The guideline's own
first-line regimens are sofosbuvir + daclatasvir and sofosbuvir + velpatasvir, so
filing all the direct-acting antivirals under one "DAA" super_class would make the
engine raise a duplication warning against the exact combination the guideline
recommends. They are therefore classed by target: NS5B for sofosbuvir, NS5A for
daclatasvir and velpatasvir. Two NS5A agents together would still be flagged,
which is correct.

WHAT THIS UNLOCKS
Two contraindications the corpus states and the engine could not previously reach,
because the drugs did not exist in the knowledge base:

  sofosbuvir + amiodarone            "significant bradyarrhythmias ... therefore it
                                      is contraindicated in these patients" (p. 38)
  any DAA + carbamazepine/phenytoin  "contraindicated with all regimens ...
                                      significantly reduced concentrations of DAAs,
                                      which may lead to virological failure" (p. 39)

Both route to DDI-005 because their recorded severity is CONTRAINDICATED.

Usage:
    python -m scripts.add_hepatitis_antivirals --check
    python -m scripts.add_hepatitis_antivirals --apply
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

DRUGS = pathlib.Path("backend/guidelines/data/drug_safety_database.json")

DOC = "MOHFW-NVHCP-VIRAL-HEPATITIS-2018"
SRC = (
    "National Guidelines for Diagnosis & Management of Viral Hepatitis, National Viral "
    "Hepatitis Control Programme, Ministry of Health & Family Welfare, Government of India "
    f"(2018) [{DOC}]"
)

_AWARE_NA = (
    "The WHO AWaRe classification covers antibacterials. This agent is an antiviral and is "
    "not assigned an AWaRe group by any source held here."
)

_NOTE = (
    "Added from " + DOC + ", a hash-verified PDF held in this repository, which states "
    "indication, dose and a small number of explicit contraindications. It is a national "
    "treatment guideline rather than a pharmacology reference, so the fields listed in "
    "coverage_gaps are NOT stated in any document held here and have NOT been supplied from "
    "memory. COVERAGE-001 continues to fire for this drug."
)

# Contraindicated with every direct-acting antiviral regimen (p. 39).
_DAA_INDUCERS = [
    {
        "interacting_drug_or_class": agent,
        "severity": "CONTRAINDICATED",
        "mechanism": (
            "Cytochrome P450 (CYP) / P-glycoprotein (P-gp) induction reduces direct-acting "
            "antiviral concentrations."
        ),
        "recommendation": (
            "The guideline lists this combination as contraindicated with all DAA regimens. "
            "Review the anticonvulsant with the prescriber before starting antiviral therapy."
        ),
        "evidence_source": SRC + ", p. 39",
        "verbatim_passage": (
            "The cytochrome P450 (CYP)/P-glycoprotein (P-gp) inducing agents, such as "
            "carbamazepine and phenytoin, are contraindicated with all regimens. Simultaneous "
            "use lead to significantly reduced concentrations of DAAs, which may lead to "
            "virological failure."
        ),
    }
    for agent in ("carbamazepine", "phenytoin")
]

_DAA_PREGNANCY = (
    "CONTRAINDICATED in pregnancy and in women of childbearing potential unless two forms of "
    "effective contraception can be guaranteed during treatment. The guideline states that the "
    "safety of DAAs in pregnancy has not been established."
)

_DAA_PREG_EVIDENCE = (
    "Safety of DAAs in pregnancy has not been established. Ribavirin is associated with fetal "
    "abnormalities. DAAs are thus contraindicated in pregnant women and those with child "
    "bearing potential unless effective contraception (i.e. two forms of contraception) can be "
    "guaranteed during treatment and, for women taking ribavirin, for 6months after completing "
    "therapy."
)


def _base(name, klass, super_class, indication, dose, passage, gaps, **extra):
    entry = {
        "name": name,
        "class": klass,
        "super_class": super_class,
        "route": "Oral",
        "aware_category": "NOT_APPLICABLE",
        "aware_category_source": _AWARE_NA,
        "knowledge_coverage": "PARTIAL",
        "coverage_gaps": gaps,
        "coverage_note": _NOTE,
        "indications_from_held_sources": [indication],
        "dosing_from_held_sources": {
            "stated_dose": dose,
            "source_document_id": DOC,
            "verbatim_passage": passage,
        },
        "unverified_sources": [],
    }
    entry.update(extra)
    return entry


NEW_DRUGS = {
    # -- Hepatitis B: nucleos(t)ide analogues -------------------------------
    "tenofovir": _base(
        "Tenofovir Disoproxil Fumarate (TDF)", "Nucleotide Analogue",
        "Nucleotide Reverse Transcriptase Inhibitors",
        "Chronic hepatitis B in adults, adolescents and children aged 12 years or older",
        "300 mg once daily",
        "Tenofovir disoproxil fumarate (TDF) 300 mg once daily",
        ["renal_dosing", "hepatic_dosing", "lactation_safety", "interactions"],
        pregnancy_category=(
            "PREFERRED where pregnancy is a possibility. The guideline states tenofovir may be "
            "preferred as the drug of choice in women of childbearing age in the eventuality of "
            "a pregnancy. This is a statement of preference over entecavir, not a full "
            "pregnancy safety category, and none is stated in any held document."
        ),
        pediatric_dosing={
            "restricted": False,
            "weight_based": False,
            "standard_dose": "300 mg once daily in children 12 years or older weighing at least 35 kg",
            "recommendation": (
                "Indicated from 12 years of age and 35 kg. For children aged 2-11 years the "
                "guideline recommends entecavir instead."
            ),
            "evidence_source": SRC + ", Table 4, p. 25",
        },
    ),
    "tenofovir_alafenamide": _base(
        "Tenofovir Alafenamide Fumarate (TAF)", "Nucleotide Analogue",
        "Nucleotide Reverse Transcriptase Inhibitors",
        "Chronic hepatitis B, including where renal function or bone disease limits other agents",
        "25 mg once daily",
        "Tenofovir alafenamide fumarate ( TAF) 25 mg once daily",
        ["hepatic_dosing", "pregnancy_category", "lactation_safety", "interactions", "pediatric_dosing"],
        renal_dosing={
            "egfr_threshold_ml_min": None,
            "recommendation": (
                "Named by the guideline as the drug of choice in patients with reduced renal "
                "function or bone disease. NO eGFR THRESHOLD IS STATED in any held document, so "
                "none is asserted here and no automatic threshold check is possible."
            ),
            "evidence_source": SRC + ", p. 26",
            "evidence_passage": (
                "Tenofovir alafenamide fumarate ( TAF) is the drug of choice in patients with "
                "reduced renal function or bone disease bone toxicities, where entecavir is "
                "contraindicated"
            ),
        },
    ),
    "entecavir": _base(
        "Entecavir", "Nucleoside Analogue",
        "Nucleoside Analogue HBV Polymerase Inhibitors",
        "Chronic hepatitis B in lamivudine-naive adults, and in children aged 2-11 years",
        "0.5 mg once daily in compensated liver disease; 1 mg once daily in decompensated liver disease",
        (
            "Entecavir ( adult with compensated liver disease and lamivudine naive) 0.5 mg once "
            "daily 3 Entecavir ( adult with decompensated liver disease) 1 mg once daily"
        ),
        ["renal_dosing", "lactation_safety", "interactions"],
        pregnancy_category=(
            "NOT RECOMMENDED IN PREGNANCY. The guideline states this directly and names "
            "tenofovir as the preferred agent where pregnancy is a possibility."
        ),
        hepatic_dosing={
            "requires_adjustment": True,
            "recommendation": (
                "Dose differs by hepatic status: 0.5 mg once daily in compensated liver disease, "
                "1 mg once daily in decompensated liver disease. This is a dose selection stated "
                "by the guideline, not a Child-Pugh reduction schedule; no Child-Pugh banding is "
                "stated in any held document."
            ),
            "evidence_source": SRC + ", Table 3, p. 25",
        },
        pediatric_dosing={
            "restricted": False,
            "weight_based": True,
            "standard_dose": (
                "Children 2 years of age or older weighing at least 10 kg; the oral solution is "
                "used. The per-kg schedule is not reproduced in the held text."
            ),
            "recommendation": "Recommended agent for chronic hepatitis B in children aged 2-11 years.",
            "evidence_source": SRC + ", Table 4, p. 25",
        },
    ),
    "lamivudine": _base(
        "Lamivudine", "Nucleoside Analogue",
        "Nucleoside Analogue HBV Polymerase Inhibitors",
        (
            "Chronic hepatitis B. NOT RECOMMENDED as a preferred agent: the guideline groups it "
            "with adefovir and telbivudine as drugs with a low barrier to resistance"
        ),
        "NOT STATED for hepatitis B in the held document",
        (
            "Drugs with a low barrier to resistance (lamivudine, adefovir or telbivudine) are "
            "available but not recommended as they lead to drug resistance"
        ),
        ["renal_dosing", "hepatic_dosing", "pregnancy_category", "lactation_safety",
         "interactions", "pediatric_dosing"],
        clinical_notes_from_held_sources=[
            "Low barrier to resistance; the guideline recommends tenofovir or entecavir instead. "
            "Where a patient has prior lamivudine exposure, the guideline prefers tenofovir over "
            "entecavir because of the potential for entecavir resistance."
        ],
    ),
    # -- Hepatitis C: direct-acting antivirals ------------------------------
    "sofosbuvir": _base(
        "Sofosbuvir", "NS5B Polymerase Inhibitor", "NS5B Polymerase Inhibitors",
        "Chronic hepatitis C, in combination with daclatasvir or velpatasvir",
        "400 mg once a day",
        "Sofosbuvir 400 mg once a day",
        ["renal_dosing", "hepatic_dosing", "lactation_safety", "pediatric_dosing"],
        pregnancy_category=_DAA_PREGNANCY,
        interactions=[
            {
                "interacting_drug_or_class": "amiodarone",
                "severity": "CONTRAINDICATED",
                "mechanism": "Significant bradyarrhythmias reported with sofosbuvir and amiodarone together.",
                "recommendation": (
                    "The guideline states this combination is contraindicated. Review the "
                    "amiodarone with cardiology before starting sofosbuvir."
                ),
                "evidence_source": SRC + ", p. 38",
                "verbatim_passage": (
                    "Recent evidence has emerged of significant bradyarrhythmias associated with "
                    "sofosbuvir in patients also taking amiodarone and therefore it is "
                    "contraindicated in these patients."
                ),
            },
            *_DAA_INDUCERS,
        ],
    ),
    "daclatasvir": _base(
        "Daclatasvir", "NS5A Inhibitor", "NS5A Inhibitors",
        "Chronic hepatitis C without cirrhosis, with sofosbuvir for 12 weeks",
        "60 mg once a day",
        "Daclatasvir 60mg once a day",
        ["renal_dosing", "hepatic_dosing", "lactation_safety", "pediatric_dosing"],
        pregnancy_category=_DAA_PREGNANCY,
        interactions=list(_DAA_INDUCERS),
    ),
    "velpatasvir": _base(
        "Velpatasvir", "NS5A Inhibitor", "NS5A Inhibitors",
        "Chronic hepatitis C with compensated or decompensated cirrhosis, with sofosbuvir",
        "100 mg once a day, given with sofosbuvir 400 mg",
        "Sofosbuvir + Velpatasvir Sofosbuvir(400mg) + Velpatasvir (100mg) once a day",
        ["renal_dosing", "hepatic_dosing", "lactation_safety", "pediatric_dosing"],
        pregnancy_category=_DAA_PREGNANCY,
        interactions=list(_DAA_INDUCERS),
    ),
    "ribavirin": _base(
        "Ribavirin", "Nucleoside Analogue", "Nucleoside Analogue Antivirals (Broad Spectrum)",
        "Chronic hepatitis C with decompensated cirrhosis, added to sofosbuvir and velpatasvir",
        (
            "800-1200 mg, decided on weight, haemoglobin level, renal function and presence of "
            "cirrhosis"
        ),
        (
            "Ribavirin 800-1200 mg (to be decided based on weight, hemoglobin level, renal "
            "function and presence of cirrhosis)"
        ),
        ["hepatic_dosing", "lactation_safety", "pediatric_dosing"],
        pregnancy_category=(
            "CONTRAINDICATED. The guideline states ribavirin is associated with fetal "
            "abnormalities, and that women of childbearing potential require effective "
            "contraception during treatment and for six months after completing therapy."
        ),
        renal_dosing={
            "egfr_threshold_ml_min": None,
            "recommendation": (
                "The guideline states the dose is decided partly on renal function but gives NO "
                "eGFR threshold or adjusted dose, so none is asserted here and no automatic "
                "threshold check is possible."
            ),
            "evidence_source": SRC + ", Table 9, p. 37",
            "evidence_passage": (
                "Ribavirin 800-1200 mg (to be decided based on weight, hemoglobin level, renal "
                "function and presence of cirrhosis)"
            ),
        },
        interactions=list(_DAA_INDUCERS),
        clinical_notes_from_held_sources=[
            "Anaemia is described by the guideline as a common and predictable side-effect of "
            "ribavirin. " + _DAA_PREG_EVIDENCE
        ],
    ),
}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--apply", action="store_true")
    a = p.parse_args()

    if not DRUGS.exists():
        print(f"REFUSING: {DRUGS} not found. Run from the repository root.")
        return 1

    doc = json.loads(DRUGS.read_text(encoding="utf-8"))
    drugs = doc.get("drugs", doc)

    clash = sorted(set(NEW_DRUGS) & set(drugs))
    if clash:
        print(f"REFUSING: drug key(s) already present, refusing to overwrite: {clash}")
        return 1

    # The guideline's own recommended regimens must not trigger DUP-002.
    regimens = [("sofosbuvir", "daclatasvir"), ("sofosbuvir", "velpatasvir"),
                ("sofosbuvir", "velpatasvir", "ribavirin")]
    for regimen in regimens:
        classes = [NEW_DRUGS[d]["super_class"] for d in regimen]
        if len(set(classes)) != len(classes):
            print(f"REFUSING: recommended regimen {regimen} shares a super_class and would "
                  f"raise a false DUP-002 duplication warning: {classes}")
            return 1
    print("Recommended regimens checked against DUP-002: no shared super_class.\n")

    for key, entry in NEW_DRUGS.items():
        held = [f for f in ("pregnancy_category", "renal_dosing", "hepatic_dosing",
                            "pediatric_dosing", "interactions") if f in entry]
        print(f"  {key:<22} {entry['super_class']:<44}")
        print(f"  {'':<22} held: {held or ['dose/indication only']}")
        print(f"  {'':<22} gaps: {entry['coverage_gaps']}")

    if a.check:
        print(f"\n--check only. Knowledge base would go from {len(drugs)} to "
              f"{len(drugs) + len(NEW_DRUGS)} drugs.")
        return 0

    drugs.update(NEW_DRUGS)
    doc.setdefault("source_documents", {})[DOC] = (
        "National Guidelines for Diagnosis & Management of Viral Hepatitis, NVHCP, MoHFW, "
        "Government of India (2018) (sha256 "
        "167d0852b0202fc2e0617a6358d8068fdc0135fec1f23fc364708eb36b09162c) - held and "
        "hash-verified; source of the hepatitis B and C antiviral entries"
    )
    DRUGS.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {DRUGS}: {len(drugs)} drugs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
