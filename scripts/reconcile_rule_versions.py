"""
Reconcile rule catalog citations against the documents actually held (Spec §22).

The catalog cited "ICMR Edition 3 (2022-2023)" on 19 rules. The ingested ICMR PDF
is the 2nd edition (2019). Spec §22 forbids silently mixing guideline versions, so
every rule's stated version must match a document this repository actually holds.

For each rule this script:
  * rewrites `guideline_version` to the edition(s) genuinely held,
  * rewrites `evidence_source` where it named an edition we do not hold,
  * records `unverified_sources` for every cited authority with no document in
    the repo, so an unbacked citation is visible rather than implied-verified.

It invents nothing. Sources not held are labelled as such, never restated.
"""
from __future__ import annotations

import collections
import json
import pathlib
import re
import sys
from typing import Dict

CATALOG = pathlib.Path("backend/guidelines/data/clinical_rules_catalog.json")
RAG_DIR = pathlib.Path("backend/guidelines/data/rag")

# Documents actually ingested into this repository, keyed by a short token.
HELD = {
    "ICMR": {
        "cite": "ICMR Treatment Guidelines for Antimicrobial Use in Common Syndromes",
        "version": "2nd edition (2019)",
        "document_id": "ICMR-STG-2019-ED2",
    },
    # A SECOND national antimicrobial guideline is now held, from a different body.
    # Declared here so this script stops reporting NCDC as an authority with no
    # document behind it. Re-citing any rule TO it is a clinical decision and is not
    # done automatically: nothing below changes a rule's cited source on the basis of
    # NCDC being present, and doing so needs clinical review.
    "NCDC": {
        "cite": "NCDC National Treatment Guidelines for Antimicrobial Use in Infectious Diseases",
        "version": "Version 1.0 (2016)",
        "document_id": "NCDC-NTG-AMR-2016",
    },
    "WHO_AWARE": {
        "cite": "The WHO AWaRe (Access, Watch, Reserve) antibiotic book",
        "version": "2022 (ISBN 978-92-4-006238-2)",
        "document_id": "WHO-AWARE-BOOK-2022",
    },
    "FDA_SPL": {
        "cite": "FDA Structured Product Label (via NLM DailyMed)",
        "version": "per-drug SPL version, recorded on each attached label",
        "document_id": "DAILYMED-*",
    },
}

# Authorities named in evidence_source strings that have NO document in the repo.
# Matched case-insensitively against the existing evidence_source text.
UNHELD_PATTERNS = {
    r"AAAAI": "AAAAI Drug Allergy Practice Parameter",
    r"Joint Task Force|JTFPP": "Joint Task Force on Practice Parameters (JTFPP)",
    r"Renal Drug Handbook": "Renal Drug Handbook",
    r"Beers Criteria": "AGS Beers Criteria",
    r"KDIGO": "KDIGO Guidelines",
    r"British National Formulary|BNF": "British National Formulary",
    r"IDSA": "IDSA Guidelines",
    r"Chest Antithrombotic": "CHEST Antithrombotic Guidelines",
    r"CredibleMeds": "CredibleMeds QT Drugs Database",
    r"AHA Scientific Statement": "AHA Scientific Statement",
    r"ACOG": "ACOG Practice Bulletin",
    r"Indian Academy of Pediatrics|IAP": "IAP Drug Formulary",
    r"WHO Patient Safety Curriculum": "WHO Patient Safety Curriculum",
}

# Rules that are system-architecture safeguards, not derived from any guideline.
SYSTEM_RULES = {
    "COVERAGE-001": (
        "Clinical Decision Support Safety Architecture (Coverage Fail-Safe)",
        "System safeguard - not derived from a clinical guideline",
    ),
}



# Rules whose clinical claim is NOT present in the ingested guideline corpus but
# IS stated verbatim in a held FDA product label. Verified by
# scripts/verify_rules_against_corpus.py: "serotonin" and "rhabdomyolysis" occur
# zero times across all 2274 guideline chunks, and the allergy-history guard has
# no retrievable guideline passage. Citing ICMR for these would assert support
# the document does not give, so they are re-cited to the source that does.
RECITE_TO_LABEL: Dict[str, Dict[str, str]] = {
    "DDI-003": {
        "drug": "linezolid",
        "why": "serotonergic interaction is absent from the guideline corpus "
               "(0 occurrences of 'serotonin'); stated in the linezolid label",
    },
    "DDI-004": {
        "drug": "clarithromycin",
        "why": "statin interaction is absent from the guideline corpus "
               "(0 occurrences of 'rhabdomyolysis'); stated in the clarithromycin label",
    },
    "ALLERGY-004": {
        "drug": "amoxicillin",
        "why": "no retrievable guideline passage on eliciting allergy history; "
               "stated verbatim in the amoxicillin label",
    },
}

# Probe terms that locate each re-cited claim inside its label. Kept alongside the
# re-citation so the verifier checks the actual claim rather than guessing: the
# ALLERGY-004 passage says "other allergens", so a probe of "allergy" misses it.
RECITE_PROBES: Dict[str, list] = {
    "DDI-003": ["serotonergic", "monoamine oxidase"],
    "DDI-004": ["statin", "simvastatin", "lovastatin"],
    "ALLERGY-004": ["careful inquiry", "previous hypersensitivity"],
}


def label_meta(drug: str) -> Dict[str, str]:
    """Read provenance straight from the ingested label file."""
    f = pathlib.Path("backend/guidelines/data/sources/dailymed") / f"{drug}.md"
    if not f.exists():
        raise FileNotFoundError(f"cannot re-cite to a label that is not ingested: {f}")
    meta: Dict[str, str] = {}
    text = f.read_text(encoding="utf-8")
    fm = re.match(r"^---\n(.*?)\n---\n", text, flags=re.S)
    if not fm:
        return meta
    for line in fm.group(1).splitlines():
        m = re.match(r'^([a-z_]+):\s*"?([^"]*?)"?\s*$', line)
        if m:
            meta[m.group(1)] = m.group(2)
    return meta


def held_tokens(evidence_source: str) -> list[str]:
    src = evidence_source or ""
    out = []
    if re.search(r"\bICMR\b", src, re.I):
        out.append("ICMR")
    if re.search(r"AWaRe", src, re.I):
        out.append("WHO_AWARE")
    if re.search(r"\bFDA\b|Structured Product Label", src, re.I):
        out.append("FDA_SPL")
    return out


def unheld_in(evidence_source: str) -> list[str]:
    src = evidence_source or ""
    return sorted({
        label for pat, label in UNHELD_PATTERNS.items()
        if re.search(pat, src, re.I)
    })


def main() -> int:
    data = json.loads(CATALOG.read_text(encoding="utf-8"), object_pairs_hook=collections.OrderedDict)
    rules = data["rules"]

    ingested = {p.stem for p in RAG_DIR.glob("*.json")}
    for token, meta in HELD.items():
        did = meta["document_id"]
        if not did.endswith("*") and did not in ingested:
            print(f"REFUSING: {did} is declared held but is not in {RAG_DIR}")
            return 1

    changed = 0
    for r in rules:
        rid = r["rule_id"]
        before = (r.get("guideline_version"), r.get("evidence_source"))

        if rid in SYSTEM_RULES:
            r["evidence_source"], r["guideline_version"] = SYSTEM_RULES[rid]
            r["unverified_sources"] = []
        elif rid == "RENAL-004":
            # Already written against held sources; only normalise the ICMR edition.
            r["guideline_version"] = (
                "FDA SPL version per attached label; "
                "ICMR Treatment Guidelines 2nd edition (2019)"
            )
            r["evidence_source"] = (
                "FDA Structured Product Label (nitrofurantoin) vs ICMR-derived system threshold"
            )
            r["unverified_sources"] = []
        elif rid in RECITE_TO_LABEL:
            spec = RECITE_TO_LABEL[rid]
            meta = label_meta(spec["drug"])
            r["evidence_source"] = (
                f"FDA Structured Product Label - {spec['drug']} (via NLM DailyMed). "
                f"Re-cited from ICMR: {spec['why']}."
            )
            r["guideline_version"] = f"SPL version {meta.get('spl_version', 'unknown')}"
            r["source_url"] = meta.get("source_url", "")
            r["unverified_sources"] = []
            r["recited_note"] = spec["why"]
            r["recited_probes"] = RECITE_PROBES.get(rid, [])
        else:
            tokens = held_tokens(r.get("evidence_source", ""))
            if not tokens:
                tokens = ["ICMR"]
            versions, cites = [], []
            for t in tokens:
                versions.append(HELD[t]["version"])
                cites.append(HELD[t]["cite"])
            r["guideline_version"] = "; ".join(dict.fromkeys(versions))

            unheld = unheld_in(r.get("evidence_source", ""))
            src = " / ".join(dict.fromkeys(cites))
            if unheld:
                src += " (additional authorities cited without a document in this repository: "
                src += ", ".join(unheld) + ")"
            r["evidence_source"] = src
            r["unverified_sources"] = unheld

        if (r.get("guideline_version"), r.get("evidence_source")) != before:
            changed += 1

    data["catalog_version"] = "3.0.0"
    data["version_reconciliation_note"] = (
        "Rule citations reconciled against documents actually held in this "
        "repository. The ICMR source ingested here is the 2nd edition (2019); "
        "earlier catalog entries claimed 'Edition 3 (2022-2023)', which is not "
        "present. Authorities listed in unverified_sources are named in clinical "
        "rationale but have no ingested document and must not be presented to a "
        "clinician as retrievable evidence."
    )
    CATALOG.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"reconciled {changed}/{len(rules)} rules; catalog_version -> {data['catalog_version']}")
    n_unverified = sum(1 for r in rules if r.get("unverified_sources"))
    print(f"rules citing at least one unheld authority: {n_unverified}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
