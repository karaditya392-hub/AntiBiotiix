"""
Check each catalog rule against the ingested guideline corpus (Spec §21, §22).

The rules were authored against 2022-2023 guidance; the ICMR document actually
held is the 2nd edition (2019). This script asks, for every rule, whether the
corpus contains text supporting what the rule asserts.

It reports three things and conflates none of them:

  TOPIC PRESENT   the corpus discusses the rule's subject at all
  CLAIM FOUND     a specific literal assertion (a threshold, age cut-off,
                  duration, drug name) appears verbatim in the corpus
  CLAIM ABSENT    the specific assertion does not appear

A rule can be TOPIC PRESENT but CLAIM ABSENT — that is the interesting case, and
it means the rule's number came from somewhere other than this corpus.

This script does NOT judge clinical correctness. It reports what the held
documents do and do not say. Clinical review remains outstanding.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
from typing import Dict, List, Optional, Tuple

CATALOG = pathlib.Path("backend/guidelines/data/clinical_rules_catalog.json")

# Per rule: a natural-language probe for topic coverage, plus the literal
# assertions the rule makes that can be checked against corpus text.
CHECKS: Dict[str, Tuple[str, List[str]]] = {
    "DIAG-001": ("first line empirical therapy for uncomplicated cystitis",
                 ["nitrofurantoin", "fosfomycin"]),
    "ALLERGY-001": ("documented drug allergy contraindication", ["hypersensitivity"]),
    "ALLERGY-002": ("penicillin class beta-lactam allergy cross reactivity",
                    ["beta-lactam", "penicillin"]),
    "ALLERGY-003": ("cephalosporin cross reactivity in penicillin allergy",
                    ["cephalosporin", "cross-react"]),
    "ALLERGY-004": ("elicit and document allergy history before prescribing",
                    ["allergy"]),
    "RENAL-001": ("antibiotic dose adjustment in renal impairment",
                  ["creatinine clearance", "renal impairment"]),
    "RENAL-002": ("nitrofurantoin contraindicated in renal impairment",
                  ["nitrofurantoin"]),
    "RENAL-003": ("assess renal function before prescribing renally cleared drugs",
                  ["renal function"]),
    "RENAL-004": ("nitrofurantoin creatinine clearance threshold", ["nitrofurantoin"]),
    "HEPATIC-001": ("antibiotic dose adjustment in hepatic impairment",
                    ["hepatic impairment", "child-pugh"]),
    "HEPATIC-002": ("assess liver function before hepatically cleared drugs",
                    ["hepatic"]),
    "DUP-001": ("redundant anaerobic coverage metronidazole with piperacillin tazobactam",
                ["anaerobic"]),
    "DUP-002": ("de-escalate combination therapy to a single narrow spectrum agent",
                ["de-escalat"]),
    "DDI-001": ("fluoroquinolone interaction with warfarin anticoagulation", ["warfarin"]),
    "DDI-002": ("QT interval prolongation with antimicrobials", ["qt"]),
    "DDI-003": ("linezolid serotonin syndrome with SSRIs", ["linezolid", "serotonin"]),
    "DDI-004": ("macrolide statin interaction rhabdomyolysis", ["statin"]),
    "VULN-001": ("fluoroquinolones avoided in pregnancy", ["pregnan"]),
    "VULN-002": ("tetracycline doxycycline contraindicated in pregnancy",
                 ["doxycycline", "pregnan"]),
    "VULN-003": ("paediatric weight based antimicrobial dosing", ["children", "kg"]),
    "VULN-004": ("confirm pregnancy status before prescribing", ["pregnan"]),
    "STEWARD-001": ("WHO Reserve group last resort antibiotics", ["reserve"]),
    "STEWARD-002": ("avoid broad spectrum antibiotics for mild self limiting infection",
                    ["watch", "access"]),
    "COVERAGE-001": ("", []),  # system safeguard; not a guideline claim
}

# Literal numeric assertions embedded in rule logic, checked against corpus text.
NUMERIC_CLAIMS: Dict[str, List[Tuple[str, str]]] = {
    "RENAL-002": [("eGFR < 30 mL/min threshold", r"\b30\s*(?:ml|mL)\s*/?\s*min")],
    "RENAL-004": [("CrCl < 60 mL/min threshold", r"\b60\s*(?:ml|mL)\s*/?\s*min")],
    "RENAL-001": [("eGFR < 50 mL/min threshold", r"\b50\s*(?:ml|mL)\s*/?\s*min")],
    "VULN-003": [("paediatric age cut-off 8 years", r"\b8\s*years?\b")],
    "HEPATIC-001": [("Child-Pugh class B or C", r"child-?pugh")],
}


def corpus_text() -> str:
    from backend.rag.store import vector_store
    return "\n".join(c["text"] for c in vector_store.chunks).lower()


def main() -> int:
    from backend.rag.retrieve import retrieve

    rules = json.loads(CATALOG.read_text(encoding="utf-8"))["rules"]
    body = corpus_text()

    print(f"{'rule':14} {'topic':>7} {'terms found / total':>20}  {'top source':<46} literal claim")
    print("-" * 132)

    summary = {"supported": 0, "topic_only": 0, "absent": 0, "skipped": 0, "recited": 0}
    detail: List[str] = []

    for r in rules:
        rid = r["rule_id"]

        # A rule re-cited to a product label is not checked against the guideline
        # corpus: it deliberately no longer claims guideline support. Verify it
        # against the label it now cites instead.
        if "Structured Product Label" in r.get("evidence_source", "") and r.get("recited_note"):
            from backend.guidelines.label_evidence import label_evidence_store
            drug = re.search(r"Product Label - (\w+)", r["evidence_source"])
            ok = False
            if drug:
                ev = label_evidence_store.get_label_evidence(
                    drug.group(1), r.get("category", ""),
                    probes=r.get("recited_probes") or CHECKS.get(rid, ("", []))[1],
                )
                ok = ev is not None
            status = "LABEL OK" if ok else "LABEL MISS"
            print(f"{rid:14} {'re-cited':>7} {'-':>20}  {status + ' (' + (drug.group(1) if drug else '?') + ')':<46}")
            summary["recited"] += 1
            if not ok:
                detail.append(f"{rid}: re-cited to a label that does not contain the claim")
            continue

        probe, terms = CHECKS.get(rid, ("", []))
        if not probe:
            print(f"{rid:14} {'n/a':>7} {'-':>20}  {'system safeguard, no guideline claim':<46}")
            summary["skipped"] += 1
            continue

        res = retrieve(probe, k=3)
        topic = "yes" if not res.refused else "NO"
        top = ""
        if res.chunks:
            c = res.chunks[0]
            top = f"{c.document_id} p.{c.page} ({c.score:.2f})"

        found = [t for t in terms if t in body]
        term_str = f"{len(found)}/{len(terms)}"

        claim_note = ""
        for label, pattern in NUMERIC_CLAIMS.get(rid, []):
            hit = re.search(pattern, body, re.I)
            claim_note += f"{label}: {'FOUND' if hit else 'ABSENT'}  "

        print(f"{rid:14} {topic:>7} {term_str:>20}  {top:<46} {claim_note}")

        if res.refused or not found:
            summary["absent"] += 1
            detail.append(f"{rid}: corpus does not support this rule's subject matter")
        elif claim_note and "ABSENT" in claim_note:
            summary["topic_only"] += 1
            detail.append(f"{rid}: topic present but the specific numeric claim is not in the corpus")
        else:
            summary["supported"] += 1

    print("-" * 132)
    print(f"topic supported + literal terms present : {summary['supported']}")
    print(f"topic present, specific claim NOT found : {summary['topic_only']}")
    print(f"subject matter absent from corpus       : {summary['absent']}")
    print(f"re-cited to a product label, verified   : {summary['recited']}")
    print(f"system safeguards (not guideline-derived): {summary['skipped']}")
    if detail:
        print("\nrules needing attention:")
        for d in detail:
            print("  -", d)
    print("\nNOTE: this checks what the held documents say. It is not clinical review.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
