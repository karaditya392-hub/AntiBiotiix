"""
FDA Structured Product Label evidence store (Spec §17, §19, §21).

Indexes the labels ingested by scripts/ingest_dailymed.py and returns
drug-specific verbatim passages to attach to safety warnings.

The ICMR guideline portal is organised by infection syndrome and carries no
cross-cutting sections on allergy cross-reactivity, renal/hepatic dose
adjustment, or drug interactions. Product labels do carry that content, as
legally mandated sections, with stable per-label identifiers.

PROVENANCE BOUNDARY: these are UNITED STATES regulatory product labels. They are
not ICMR national guidance, not WHO guidance, and not clinical practice
guidelines. Every citation produced here carries its own issuing_org and
geographic_scope so it can never be rendered as guideline content.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

# Probe terms per rule category. A label section is offered as supporting
# evidence only when it actually contains language about the concept the rule
# asserts. A section is never attached merely because it exists.
LABEL_PROBES: Dict[str, List[str]] = {
    "ALLERGY": ["hypersensitivity", "anaphyla", "cross-sensitiv", "cross-react", "allergic"],
    "RENAL": ["creatinine clearance", "renal impairment", "renal function", "crcl", "dialysis"],
    "HEPATIC": ["hepatic impairment", "hepatic function", "liver disease", "child-pugh", "cholestatic"],
    "DRUG_INTERACTION": [
        "warfarin", "qt prolongation", "serotonin", "statin", "anticoagulant",
        "coadministration", "concomitant",
    ],
    "VULNERABLE_POPULATION": [
        "pregnan", "lactation", "nursing", "pediatric patients", "geriatric",
        "tooth", "skeletal",
    ],
}

# Label sections eligible for each rule category, in preference order.
LABEL_SECTIONS: Dict[str, List[str]] = {
    "ALLERGY": ["Contraindications", "Boxed Warning", "Warnings and Precautions", "Warnings"],
    "RENAL": [
        "Contraindications", "Dosage and Administration", "Warnings and Precautions",
        "Warnings", "Use in Specific Populations", "Precautions",
    ],
    "HEPATIC": [
        "Contraindications", "Warnings and Precautions", "Warnings",
        "Use in Specific Populations", "Precautions", "Dosage and Administration",
    ],
    "DRUG_INTERACTION": [
        "Drug Interactions", "Boxed Warning", "Warnings and Precautions",
        "Warnings", "Precautions",
    ],
    "VULNERABLE_POPULATION": [
        "Pregnancy", "Lactation", "Pediatric Use", "Geriatric Use",
        "Use in Specific Populations", "Contraindications",
        "Warnings and Precautions", "Warnings",
    ],
}

MAX_PASSAGE_CHARS = 700


class LabelEvidenceStore:
    """In-memory index of ingested FDA Structured Product Labels."""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self.dir = Path(data_dir) if data_dir else Path(__file__).parent / "data" / "sources" / "dailymed"
        self.labels: Dict[str, Dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        if not self.dir.exists():
            return
        for f in sorted(self.dir.glob("*.md")):
            try:
                self.labels[f.stem] = self._parse(f.read_text(encoding="utf-8"))
            except Exception:
                # A malformed source file must never break clinical evaluation.
                continue

    @staticmethod
    def _parse(text: str) -> Dict[str, Any]:
        meta: Dict[str, Any] = {}
        body = text
        m = re.match(r"^---\n(.*?)\n---\n", text, flags=re.S)
        if m:
            body = text[m.end():]
            for line in m.group(1).split("\n"):
                km = re.match(r'^([a-z_]+):\s*"?([^"]*?)"?\s*$', line)
                if km:
                    meta[km.group(1)] = km.group(2)
        sections: Dict[str, str] = {}
        for sm in re.finditer(r"^## (.+?)\n(.*?)(?=^## |\Z)", body, flags=re.S | re.M):
            sections[sm.group(1).strip()] = sm.group(2).strip()
        return {"meta": meta, "sections": sections}

    @staticmethod
    def _excerpt(section_text: str, probes: List[str]) -> Optional[str]:
        """Return only the sentences mentioning the concept, never the whole section."""
        flat = section_text.replace("\n", " ")
        sentences = re.split(r"(?<=[.;])\s+", flat)
        keep = [
            s.strip() for s in sentences
            if any(p in s.lower() for p in probes) and not LabelEvidenceStore._is_table_scaffold(s)
        ]
        if not keep:
            return None
        out = " ".join(keep)
        if len(out) > MAX_PASSAGE_CHARS:
            out = out[:MAX_PASSAGE_CHARS].rsplit(" ", 1)[0] + " ..."
        return out

    @staticmethod
    def _is_table_scaffold(sentence: str) -> bool:
        """Reject table headers/column labels that carry no clinical statement."""
        low = sentence.lower()
        if re.match(r"^\s*table\s+\d+", low):
            return True
        scaffold = ("recommendation", "comments", "drug(s)", "drugs that are")
        return sum(1 for w in scaffold if w in low) >= 2

    def get_label_evidence(
        self,
        drug_key: str,
        category: str,
        probes: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Drug-specific product-label evidence for a rule category, or None.

        Returns None rather than a weak match when the label does not discuss the
        concept: an absent citation is preferable to an irrelevant one.
        """
        label = self.labels.get(drug_key)
        if not label:
            return None
        # Caller-supplied probes describe the exact concept that fired the rule
        # (e.g. the specific interacting drug). They are far more precise than the
        # category defaults, so they take priority.
        specific = [p.lower() for p in (probes or []) if p]
        probes_used = specific or LABEL_PROBES.get(category) or []
        if not probes_used:
            return None
        for section_name in LABEL_SECTIONS.get(category, []):
            body = label["sections"].get(section_name)
            if not body:
                continue
            passage = self._excerpt(body, probes_used)
            if not passage and specific:
                # No sentence about the specific concept in this section; do not
                # fall back to a generic one, which would cite the wrong thing.
                continue
            if not passage:
                continue
            meta = label["meta"]
            return {
                "document_title": meta.get("title", f"FDA Product Label - {drug_key}"),
                "issuing_org": meta.get("issuing_org", "US FDA (via NLM DailyMed)"),
                "geographic_scope": meta.get(
                    "geographic_scope", "United States (US product labelling)"
                ),
                "guideline_version": f"SPL version {meta.get('spl_version', 'unknown')}",
                "publication_date": meta.get("published_date"),
                "source_url": meta.get("source_url"),
                "section_page": f"Label section: {section_name}",
                "verbatim_passage": passage,
                "evidence_class": "REGULATORY_PRODUCT_LABELLING",
            }
        return None


label_evidence_store = LabelEvidenceStore()
