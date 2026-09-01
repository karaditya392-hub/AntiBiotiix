"""
Add syndrome entries derived from documents actually held in the retrieval corpus.

WHY EACH SYNDROME NOW CARRIES ITS OWN SOURCE
backend/guidelines/data/icmr_antimicrobial_guidelines_2022.json is labelled, at the
file level, as ICMR "Edition 3 (2022-2023)". Its syndrome entries carried no source
of their own, so every syndrome in the file inherited that attribution.

That was survivable while every syndrome came from one document. It is not
survivable now: the syndromes added here are drawn from the DHR-ICMR rickettsial
guidelines, the NCDC leptospirosis guidelines, the NCDC national treatment
guidelines and the WHO AWaRe book. Writing them into this file without a per-entry
source would silently attribute NCDC and WHO content to an ICMR edition -- and to
an edition this repository does not even hold as a verified PDF (see the
version_reconciliation_note in clinical_rules_catalog.json: the ingested ICMR
source is the 2nd edition, 2019).

So `source_document_id`, `source_location` and `source_quote` are added to every
syndrome. The five pre-existing entries are marked as inheriting the FILE-LEVEL
claim rather than a verified per-passage citation, because that is what is
actually known about them.

WHAT THESE ENTRIES DO AND DO NOT DO
They enrich the syndrome match returned with every prescription analysis. They do
NOT make rule DIAG-001 fire: that rule fires on a syndrome's `avoid_empirical`
list, and NONE of the four sources below states an agent to avoid for its syndrome.
An empty avoid list is therefore left empty rather than populated by inference --
inventing an avoid list would manufacture a clinical warning from nothing.

Usage:
    python -m scripts.add_syndromes_from_corpus --check
    python -m scripts.add_syndromes_from_corpus --apply
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

GUIDELINES = pathlib.Path("backend/guidelines/data/icmr_antimicrobial_guidelines_2022.json")

_INHERITED = (
    "Inherited from this file's document-level attribution. No per-passage citation "
    "was recorded when this entry was written, and none is claimed here."
)

NEW_SYNDROMES = {
    "scrub_typhus": {
        "syndrome_name": "Scrub Typhus / Rickettsial Illness",
        "first_line_preferred": ["Doxycycline"],
        "alternative_atypical": ["Azithromycin"],
        "avoid_empirical": [],
        "recommended_duration_days": "7 days",
        "clinical_notes": (
            "DHR-ICMR Guidelines for Diagnosis and Management of Rickettsial Diseases in "
            "India (2015): in fever of 5 days or more where malaria, dengue and typhoid have "
            "been ruled out, doxycycline is to be administered when scrub typhus is "
            "considered likely. Doxycycline is first-line INCLUDING in children, where the "
            "usual under-8 tetracycline restriction is set aside because the infection is "
            "life-threatening -- see rule VULN-005, which states that exception rather than "
            "blocking the prescription."
        ),
        "source_document_id": "DHR-ICMR-RICKETTSIAL-2015",
        "source_location": "p. 17",
        "source_quote": (
            "Doxycycline 200 mg/day in two divided doses for individuals above 45 kg for "
            "duration of 7 days."
        ),
    },
    "leptospirosis": {
        "syndrome_name": "Leptospirosis",
        "first_line_preferred": ["Doxycycline"],
        "alternative_penicillin_allergic": [],
        "avoid_empirical": [],
        "recommended_duration_days": "7 days",
        "clinical_notes": (
            "NCDC National Guidelines on Leptospirosis (2015): doxycycline 100 mg twice a "
            "day for seven days in adults. The source names DIFFERENT agents for the groups "
            "in whom doxycycline is restricted: ampicillin 500 mg six-hourly for pregnant "
            "and lactating women, and amoxycillin or ampicillin 30-50 mg/kg/day for children "
            "under 8 years. Severe disease is treated with intravenous penicillin after a "
            "negative test dose."
        ),
        "source_document_id": "NCDC-LEPTOSPIROSIS-2015",
        "source_location": "p. 11",
        "source_quote": (
            "Adults: Doxycycline 100 mg twice a day for seven days. Pregnant & lactating "
            "mothers should be given capsule ampicillin 500 mg every 6 hourly. Children< 8 "
            "years: Amoxycillin/ Ampicillin 30-50 mg/kg/day in divided doses for 7 days."
        ),
    },
    "acute_bacterial_meningitis": {
        "syndrome_name": "Acute Bacterial Meningitis",
        "first_line_preferred": ["Ceftriaxone", "Cefotaxime"],
        "inpatient_severe": ["Ceftriaxone", "Vancomycin"],
        "avoid_empirical": [],
        "recommended_duration_days": "10 to 14 days",
        "clinical_notes": (
            "NCDC National Treatment Guidelines for Antimicrobial Use in Infectious Diseases "
            "(2016), central nervous system infections: empirical ceftriaxone 2 g IV "
            "12-hourly or cefotaxime 2 g IV 4-6 hourly for 10-14 days, against S. pneumoniae, "
            "H. influenzae and N. meningitidis. The same source gives pathogen-specific "
            "durations once confirmed: 7 days for meningococcal, 10 for H. influenzae type b, "
            "14 for S. pneumoniae."
        ),
        "source_document_id": "NCDC-NTG-AMR-2016",
        "source_location": "Section B, Central Nervous System Infections",
        "source_quote": (
            "Acute bacterial Meningitis - S. pneumoniae, H.influenzae, Neisseria "
            "meningititdis - Ceftriaxone 2 g IV 12hourly/ Cefotaxime 2 g IV 4-6hourly - "
            "10-14 days treatment"
        ),
    },
    "enteric_fever": {
        "syndrome_name": "Enteric Fever (Typhoid / Paratyphoid)",
        "first_line_preferred": ["Ceftriaxone", "Azithromycin"],
        "avoid_empirical": [],
        "recommended_duration_days": "Source-dependent; see clinical notes",
        "clinical_notes": (
            "WHO AWaRe antibiotic book (2022): empirical treatment should be chosen on "
            "severity of presentation and on LOCAL PREVALENCE OF FLUOROQUINOLONE RESISTANCE "
            "among Salmonella Typhi and Paratyphi, and treatment should start as soon as the "
            "diagnosis is suspected. Where ceftriaxone resistance is increasing, azithromycin "
            "should be prioritized. No agent is listed as one to avoid empirically, because "
            "the source makes the choice conditional on local resistance rather than fixed - "
            "which is why this entry carries no avoid_empirical list and DIAG-001 does not "
            "fire on it. The local antibiogram governs."
        ),
        "source_document_id": "WHO-AWARE-BOOK-2022",
        "source_location": "Primary health care, ch. 15 (Enteric fever), pp. 202-208",
        "source_quote": (
            "Empiric treatment should be chosen based on - Severity of presentation - Local "
            "prevalence of fluoroquinolone resistance among serotypes Typhi or Paratyphi "
            "Salmonella"
        ),
    },
}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--apply", action="store_true")
    a = p.parse_args()

    if not GUIDELINES.exists():
        print(f"REFUSING: {GUIDELINES} not found. Run from the repository root.")
        return 1

    data = json.loads(GUIDELINES.read_text(encoding="utf-8"))
    syndromes = data.setdefault("syndromes", {})

    clash = sorted(set(NEW_SYNDROMES) & set(syndromes))
    if clash:
        print(f"REFUSING: syndrome key(s) already present, refusing to overwrite: {clash}")
        return 1

    print("Backfilling provenance on existing entries:")
    for key, entry in syndromes.items():
        marker = "already set" if "source_document_id" in entry else "-> file-level attribution"
        print(f"  {key:<38} {marker}")
        if a.apply and "source_document_id" not in entry:
            entry["source_document_id"] = data.get("document_id", "ICMR-AMR-GUIDELINES-2022")
            entry["source_location"] = "NOT RECORDED"
            entry["source_quote"] = _INHERITED

    print("\nAdding syndromes derived from held documents:")
    for key, entry in NEW_SYNDROMES.items():
        fires = "yes" if entry.get("avoid_empirical") else "no (no avoid list in the source)"
        print(f"  {key:<38} {entry['source_document_id']:<28} DIAG-001 fires: {fires}")
        if a.apply:
            syndromes[key] = entry

    if a.check:
        print("\n--check only. Nothing written.")
        return 0

    data["syndrome_attribution_note"] = (
        "Each syndrome entry carries its own source_document_id, source_location and "
        "source_quote. This file's document-level fields describe the file, NOT every "
        "entry in it: entries added from the DHR-ICMR rickettsial guidelines, the NCDC "
        "leptospirosis and national treatment guidelines, and the WHO AWaRe book are "
        "attributed to those documents and must never be cited as ICMR Edition 3. "
        "Entries whose source_quote says the attribution is inherited predate this field "
        "and carry no verified per-passage citation."
    )
    GUIDELINES.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {GUIDELINES} ({len(syndromes)} syndromes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
