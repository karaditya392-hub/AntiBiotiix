"""
Clinical Guideline Repository, Knowledge Base & Precedence Engine
"""
import os
import re
import json
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

from backend.config import GUIDELINE_PRECEDENCE_HIERARCHY


class ClinicalKnowledgeBase:
    def __init__(self, data_dir: Optional[str] = None):
        if data_dir is None:
            data_dir = os.path.join(os.path.dirname(__file__), "data")
        self.data_dir = Path(data_dir)
        self.drugs_db: Dict[str, Any] = {}
        self.rules_catalog: List[Dict[str, Any]] = []
        self.icmr_guidelines: Dict[str, Any] = {}
        self.amr_data: Dict[str, Any] = {}
        self.who_aware: Dict[str, Any] = {}
        self.load_all()

    def load_all(self):
        """Load all structured clinical knowledge files."""
        # Drug safety DB
        drug_file = self.data_dir / "drug_safety_database.json"
        if drug_file.exists():
            with open(drug_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.drugs_db = data.get("drugs", {})

        # Rules catalog
        rules_file = self.data_dir / "clinical_rules_catalog.json"
        if rules_file.exists():
            with open(rules_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.rules_catalog = data.get("rules", [])
                self.rules_catalog_metadata = {k: v for k, v in data.items() if k != "rules"}

        # ICMR guidelines
        icmr_file = self.data_dir / "icmr_antimicrobial_guidelines_2022.json"
        if icmr_file.exists():
            with open(icmr_file, "r", encoding="utf-8") as f:
                self.icmr_guidelines = json.load(f)

        # AMR surveillance
        amr_file = self.data_dir / "icmr_amr_surveillance_2023.json"
        if amr_file.exists():
            with open(amr_file, "r", encoding="utf-8") as f:
                self.amr_data = json.load(f)

        # WHO AWaRe
        aware_file = self.data_dir / "who_aware_classification_2023.json"
        if aware_file.exists():
            with open(aware_file, "r", encoding="utf-8") as f:
                self.who_aware = json.load(f)

    KNOWN_NON_ANTIMICROBIALS = {
        "ondansetron", "warfarin", "pantoprazole", "atorvastatin", "simvastatin",
        "amiodarone", "haloperidol", "methadone", "sotalol", "fluoxetine",
        "sertraline", "escitalopram", "citalopram", "paroxetine", "venlafaxine",
        "duloxetine", "omeprazole", "metformin", "amlodipine", "aspirin",
        "lisinopril", "losartan", "furosemide", "digoxin", "spironolactone",
        "heparin", "enoxaparin", "apixaban", "rivaroxaban"
    }

    def is_known_non_antimicrobial(self, drug_name: str) -> bool:
        if not drug_name:
            return False
        norm = self.normalize_drug_name(drug_name)
        return norm in self.KNOWN_NON_ANTIMICROBIALS

    def normalize_drug_name(self, name: str) -> str:
        """Standardize drug string for exact dictionary lookup."""
        if not name:
            return ""
        n = name.strip().lower()
        n = n.replace("-", "_").replace(" ", "_").replace("/", "_")
        aliases = {
            "augmentin": "amoxicillin_clavulanate",
            "amox_clav": "amoxicillin_clavulanate",
            "amoxyclav": "amoxicillin_clavulanate",
            "amoxycillin": "amoxicillin",
            "pip_taz": "piperacillin_tazobactam",
            "piptaz": "piperacillin_tazobactam",
            "tazocin": "piperacillin_tazobactam",
            "cipro": "ciprofloxacin",
            "levo": "levofloxacin",
            "flagyl": "metronidazole",
            "vancocin": "vancomycin",
            "vanco": "vancomycin",
            "meropenum": "meropenem",
            "zyvox": "linezolid",
            "doxy": "doxycycline",
            "azithro": "azithromycin",
            "zithromax": "azithromycin",
            "rocephin": "ceftriaxone",
            "furadantin": "nitrofurantoin",
            "macrobid": "nitrofurantoin"
        }
        return aliases.get(n, n)

    def get_drug_info(self, drug_name: str) -> Optional[Dict[str, Any]]:
        norm = self.normalize_drug_name(drug_name)
        return self.drugs_db.get(norm)

    def get_rule_by_id(self, rule_id: str) -> Optional[Dict[str, Any]]:
        for r in self.rules_catalog:
            if r.get("rule_id") == rule_id:
                return r
        return None

    def get_all_rules(self) -> List[Dict[str, Any]]:
        return self.rules_catalog

    def get_aware_category(self, drug_name: str) -> str:
        norm = self.normalize_drug_name(drug_name)
        info = self.drugs_db.get(norm)
        if info and "aware_category" in info:
            return info["aware_category"]
        return "NOT_APPLICABLE"

    def retrieve_guideline_evidence(
        self, diagnosis: str, k: int = 3
    ) -> Dict[str, Any]:
        """
        Semantic retrieval over the ingested guideline corpus (Spec §9, §16).

        AUGMENTS the deterministic dispatch below; it never replaces it and never
        gates whether a clinical rule fires. Import is local and failure is
        swallowed so that an unavailable or broken index degrades retrieval only,
        leaving rule evaluation byte-identical.
        """
        try:
            from backend.rag.retrieve import retrieve as _retrieve

            result = _retrieve(diagnosis or "", k=k)
            return result.to_dict()
        except Exception as exc:  # pragma: no cover - defensive
            return {
                "query": diagnosis,
                "retrieved": [],
                "count": 0,
                "refused": True,
                "message": f"No sufficiently relevant evidence was retrieved. (retrieval unavailable: {type(exc).__name__})",
                "relevance_floor": None,
                "best_score": None,
                "store": {"available": False},
            }

    def match_syndrome_guideline(self, diagnosis: str) -> Optional[Dict[str, Any]]:
        """
        Deterministic keyword syndrome dispatch with word-boundary checks (Spec §9).
        Anchors keywords to prevent substring hallucinations (e.g. 'cap' inside other words).
        Does NOT match upper/complicated UTI (pyelonephritis) to uncomplicated cystitis.
        """
        if not diagnosis:
            return None
            
        d_lower = diagnosis.lower()
        syndromes = self.icmr_guidelines.get("syndromes", {})

        # Community-Acquired Pneumonia
        if re.search(r'\b(?:cap|pneumonia|chest\s+infection)\b', d_lower):
            return syndromes.get("community_acquired_pneumonia")
            
        # Uncomplicated Urinary Tract Infection (Acute Cystitis)
        # Note: Exclude pyelonephritis as it is upper/complicated UTI
        if re.search(r'\b(?:uncomplicated\s+uti|cystitis|acute\s+cystitis|lower\s+uti)\b', d_lower) or (
            re.search(r'\b(?:uti|urinary\s+tract\s+infection)\b', d_lower) and not re.search(r'\bpyelonephritis\b', d_lower)
        ):
            return syndromes.get("uncomplicated_urinary_tract_infection")
            
        # Skin and Soft Tissue Infection
        if re.search(r'\b(?:cellulitis|erysipelas|skin\s+and\s+soft\s+tissue|ssti)\b', d_lower):
            return syndromes.get("skin_and_soft_tissue_infection")
            
        # Acute Gastroenteritis / Infectious Diarrhea
        if re.search(r'\b(?:diarrhea|diarrhoea|gastroenteritis|acute\s+watery\s+diarrhea|dysentery)\b', d_lower):
            return syndromes.get("acute_gastroenteritis")
            
        # Acute Bacterial Sinusitis
        if re.search(r'\b(?:sinusitis|rhinosinusitis|bacterial\s+sinusitis)\b', d_lower):
            return syndromes.get("acute_bacterial_sinusitis")
            
        return None

    def get_local_amr_records(self, drug_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve relevant ICMR AMR surveillance records."""
        antibiogram = self.amr_data.get("antibiogram", [])
        if not drug_name:
            return antibiogram
        norm = self.normalize_drug_name(drug_name)
        results = []
        for row in antibiogram:
            if self.normalize_drug_name(row.get("antimicrobial", "")) == norm:
                results.append(row)
        return results

    def resolve_guideline_precedence(self, syndrome_key: str) -> Dict[str, Any]:
        """
        Documented guideline precedence policy (Section 8A):
        Returns the precedence order and surfaces any known conflicts between National (ICMR)
        and International (WHO/IDSA) guidance.
        """
        precedence = {
            "hierarchy": GUIDELINE_PRECEDENCE_HIERARCHY,
            "selected_scope": "National (India - ICMR Edition 3)",
            "conflict_surfaced": None
        }
        
        # Documented conflict: Fluoroquinolones in uncomplicated UTI
        s_lower = syndrome_key.lower()
        if "uti" in s_lower or "cystitis" in s_lower or "urinary" in s_lower:
            precedence["conflict_surfaced"] = {
                "topic": "Empirical Fluoroquinolone Use for Uncomplicated UTI",
                "national_icmr": "DO NOT USE empirical Ciprofloxacin/Levofloxacin due to >70% background resistance in Indian isolates (ICMR Guidelines 2022).",
                "international_note": "Older international guidelines (IDSA 2011) list Ciprofloxacin as second-line, but recent WHO & ICMR guidance strongly restrict fluoroquinolones.",
                "resolved_precedence_ruling": "National ICMR Guideline takes precedence for Indian clinical context. First-line is Nitrofurantoin or Fosfomycin."
            }
        return precedence



# Singleton instance
knowledge_base = ClinicalKnowledgeBase()
