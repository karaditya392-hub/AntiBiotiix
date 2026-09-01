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
        self.stw_collection: Dict[str, Any] = {}
        self.stg_syndromes: Dict[str, Any] = {}
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

        # ICMR Standard Treatment Workflows (2022).
        #
        # A DIFFERENT ICMR publication series from the antimicrobial Treatment
        # Guidelines above. It is loaded into its own attribute and never merged
        # into self.icmr_guidelines, so a condition sourced from a workflow can
        # never be cited as if it came from the treatment guidelines.
        stw_file = self.data_dir / "icmr_stw_2022.json"
        if stw_file.exists():
            with open(stw_file, "r", encoding="utf-8") as f:
                self.stw_collection = json.load(f)

        # Syndrome index of the ICMR Treatment Guidelines 2022-23 edition.
        #
        # Attribution rests on operator attestation: the chapters were supplied as
        # transcriptions and no official 2022-23 PDF is held, so no record carries a
        # page in the authority document. Where the same text also occurs in the
        # hash-verified 2019 edition, that location travels as a clearly-labelled
        # prior-edition cross-reference -- never as a page of this edition.
        stg_file = self.data_dir / "icmr_stg_2022_23_syndromes.json"
        if stg_file.exists():
            with open(stg_file, "r", encoding="utf-8") as f:
                self.stg_syndromes = json.load(f)

    KNOWN_NON_ANTIMICROBIALS = {
        "ondansetron", "warfarin", "pantoprazole", "atorvastatin", "simvastatin",
        "amiodarone", "haloperidol", "methadone", "sotalol", "fluoxetine",
        "sertraline", "escitalopram", "citalopram", "paroxetine", "venlafaxine",
        "duloxetine", "omeprazole", "metformin", "amlodipine", "aspirin",
        "lisinopril", "losartan", "furosemide", "digoxin", "spironolactone",
        "heparin", "enoxaparin", "apixaban", "rivaroxaban",
        # Co-prescribed alongside the antitubercular regimens and the workflows
        # added from the ICMR STWs. Without these, every TB or SSTI prescription
        # would raise a spurious COVERAGE-001 antimicrobial-coverage warning for
        # an adjunct that is not an antimicrobial at all.
        "pyridoxine", "prednisolone", "dexamethasone", "ibuprofen", "indomethacin",
        "paracetamol", "azathioprine", "methotrexate", "isotretinoin", "benzoyl_peroxide",
        "adapalene", "tretinoin", "azelaic_acid", "albumin", "terlipressin",
        # Named in the ICMR 2019 chapters as adjuncts, not as antimicrobials
        "loperamide", "oral_rehydration_solution", "ors", "ringers_lactate",
        "normal_saline", "noradrenaline", "ivig", "rituximab", "cyclophosphamide",
        "mycophenolate_mofetil", "dapsone", "niacinamide", "clobetasol_propionate"
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
            "macrobid": "nitrofurantoin",
            # Agents named by the ICMR Standard Treatment Workflows (2022)
            "cefalexin": "cephalexin",
            "cephalexine": "cephalexin",
            "keflex": "cephalexin",
            "cloxacilin": "cloxacillin",
            "co_trimoxazole": "cotrimoxazole",
            "cotrimoxazol": "cotrimoxazole",
            "septran": "cotrimoxazole",
            "bactrim": "cotrimoxazole",
            "tmp_smx": "cotrimoxazole",
            "sulfamethoxazole_trimethoprim": "cotrimoxazole",
            "trimethoprim_sulfamethoxazole": "cotrimoxazole",
            # The STW Vol. 3 source PDF prints this misspelling on page 11
            "minocycine": "minocycline",
            "minocin": "minocycline",
            "clinda": "clindamycin",
            "dalacin": "clindamycin",
            "erythro": "erythromycin",
            "bactroban": "mupirocin",
            "fucidin": "fusidic_acid",
            "sodium_fusidate": "fusidic_acid",
            "soframycin": "framycetin",
            "neomycin_b": "framycetin",
            # First-line antituberculars (NTEP 2HRZE/4HRE)
            "inh": "isoniazid",
            "isonicotinylhydrazide": "isoniazid",
            "rifampin": "rifampicin",
            "rifadin": "rifampicin",
            "pza": "pyrazinamide",
            "emb": "ethambutol",
            "streptomycine": "streptomycin",
            # Agents named by the ICMR Treatment Guidelines 2nd edition (2019)
            "cefoperazone": "cefoperazone_sulbactam",
            "cefoperazone_sulbactum": "cefoperazone_sulbactam",
            "sulperazone": "cefoperazone_sulbactam",
            "magnex": "cefoperazone_sulbactam",
            "ampicillin_sulbactum": "ampicillin_sulbactam",
            "unasyn": "ampicillin_sulbactam",
            "sultamicillin": "ampicillin_sulbactam",
            "imipenem_cilastatin": "imipenem",
            "imipenem_cilastatin_2": "imipenem",
            "primaxin": "imipenem",
            "ertapenam": "ertapenem",
            "invanz": "ertapenem",
            "benzathine_benzylpenicillin": "benzathine_penicillin",
            "benzathine_penicillin_g": "benzathine_penicillin",
            "polymyxin": "polymyxin_b",
            "colistimethate": "colistin",
            "colomycin": "colistin",
            "amphotericin": "amphotericin_b",
            "liposomal_amphotericin_b": "amphotericin_b",
            "l_amb": "amphotericin_b",
            "5_flucytosine": "flucytosine",
            "aciclovir": "acyclovir",
            "valaciclovir": "valacyclovir",
            "valgancyclovir": "valganciclovir",
            "ceftazidime_avibactam_aztreonam": "ceftazidime_avibactam",
            "avycaz": "ceftazidime_avibactam",
            "tamiflu": "oseltamivir",
            "diflucan": "fluconazole",
            "vfend": "voriconazole",
            "cancidas": "caspofungin",
            "mycamine": "micafungin",
            "targocid": "teicoplanin",
            "tygacil": "tigecycline",
            "monurol": "fosfomycin",
            "maxipime": "cefepime",
            "fortum": "ceftazidime",
            "claforan": "cefotaxime",
            "ancef": "cefazolin",
            "kefzol": "cefazolin"
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

        # Syndromes below are derived from documents held in the retrieval corpus
        # (scripts/add_syndromes_from_corpus.py). Each entry names its own source;
        # none of them carries an avoid_empirical list, so none makes DIAG-001 fire.
        # They are matched here so that a prescription for one of these diagnoses
        # returns the guidance actually held rather than nothing at all.

        # Scrub typhus / rickettsial illness. Matched before enteric fever because
        # "typhus" and "typhoid" are different diseases with different first-line
        # agents and are easy to conflate; anchoring both avoids a wrong match.
        if re.search(r'\b(?:scrub\s+typhus|typhus|rickettsial|rickettsios[ei]s)\b', d_lower):
            return syndromes.get("scrub_typhus")

        # Leptospirosis
        if re.search(r'\b(?:leptospirosis|leptospiral|weil\'?s\s+disease)\b', d_lower):
            return syndromes.get("leptospirosis")

        # Acute bacterial meningitis. Excludes viral/aseptic meningitis, for which
        # the held antibacterial guidance does not apply.
        if re.search(r'\b(?:bacterial\s+meningitis|meningitis|meningococcal)\b', d_lower) and not re.search(
            r'\b(?:viral|aseptic|tubercular|tuberculous|fungal|cryptococcal)\b', d_lower
        ):
            return syndromes.get("acute_bacterial_meningitis")

        # Enteric fever (typhoid / paratyphoid)
        if re.search(r'\b(?:enteric\s+fever|typhoid|paratyphoid|salmonella\s+typhi)\b', d_lower):
            return syndromes.get("enteric_fever")

        return None

    # ------------------------------------------------------------------
    # ICMR Standard Treatment Workflows (2022)
    # ------------------------------------------------------------------
    #
    # Kept deliberately separate from match_syndrome_guideline. The treatment
    # guidelines carry `avoid_empirical` / `first_line_preferred` and drive
    # DIAG-001; the workflows carry a different shape (presentation, medications,
    # severity_tiers) and must not be fed into a rule that expects the other.

    STW_CONDITION_PATTERNS: List[Tuple[str, str]] = [
        # Bacterial skin and soft tissue infections (STW Vol. 3, p.11)
        (r'\bimpetigo\b', "impetigo"),
        (r'\becthyma\b', "ecthyma"),
        (r'\bfolliculitis\b', "folliculitis"),
        (r'\b(?:furuncle|furunculosis|boil)\b', "furuncle"),
        (r'\bcarbuncle\b', "carbuncle"),
        (r'\b(?:cutaneous\s+abscess|skin\s+abscess)\b', "cutaneous_abscess"),
        (r'\bcellulitis\b', "cellulitis"),
        (r'\berysipelas\b', "erysipelas"),
        (r'\b(?:staphylococcal\s+scalded\s+skin(?:\s+syndrome)?|ssss)\b',
         "staphylococcal_scalded_skin_syndrome"),
        # Dermatology workflows with antibacterial therapy (STW Vol. 3, p.9, p.18)
        (r'\brosacea\b', "rosacea"),
        (r'\bacne\b', "acne_vulgaris"),
        # Other Vol. 3 workflows carrying named antimicrobials
        (r'\b(?:spontaneous\s+bacterial\s+peritonitis|sbp)\b',
         "spontaneous_bacterial_peritonitis"),
        (r'\bempyema\b', "empyema_thoracis_children"),
        (r'\bdiabetic\s+foot\b', "diabetic_foot_infection"),
        # Tuberculosis (STW Paediatric and Extrapulmonary TB, 2022).
        # Paediatric patterns are listed before the adult ones so that an
        # explicitly paediatric diagnosis is never matched to an adult workflow.
        (r'\b(?:paediatric|pediatric|childhood)\b.*\babdominal\s+(?:tb|tuberculosis)\b',
         "paediatric_abdominal_tuberculosis"),
        (r'\b(?:paediatric|pediatric|childhood)\b.*\b(?:intrathoracic|pulmonary)\s+(?:tb|tuberculosis)\b',
         "paediatric_intrathoracic_tuberculosis"),
        (r'\b(?:paediatric|pediatric|childhood)\b.*\blymph\s*node\s+(?:tb|tuberculosis)\b',
         "paediatric_lymph_node_tuberculosis"),
        (r'\b(?:paediatric|pediatric|childhood)\b.*\bosteoarticular\s+(?:tb|tuberculosis)\b',
         "paediatric_osteoarticular_tuberculosis"),
        (r'\b(?:paediatric|pediatric|childhood)\b.*\b(?:tubercular|tuberculous)\s+meningitis\b',
         "paediatric_tubercular_meningitis"),
        (r'\babdominal\s+(?:tb|tuberculosis)\b', "adult_abdominal_tuberculosis"),
        (r'\blymph\s*node\s+(?:tb|tuberculosis)\b', "adult_lymph_node_tuberculosis"),
        (r'\b(?:musculoskeletal|skeletal|spinal|pott)\w*\s*(?:tb|tuberculosis)?\b.*\b(?:tb|tuberculosis)\b',
         "adult_musculoskeletal_tuberculosis"),
        (r'\bpericardial\s+(?:tb|tuberculosis)\b', "adult_pericardial_tuberculosis"),
        (r'\bpleural\s+(?:tb|tuberculosis)\b', "adult_pleural_tuberculosis"),
        (r'\b(?:tubercular|tuberculous)\s+meningitis\b|\btbm\b',
         "adult_tubercular_meningitis"),
        (r'\bcutaneous\s+(?:tb|tuberculosis)\b', "cutaneous_tuberculosis"),
        (r'\b(?:female\s+genital|genital)\s+(?:tb|tuberculosis)\b|\bfgtb\b',
         "female_genital_tuberculosis"),
        (r'\b(?:genitourinary|renal|urinary)\s+(?:tb|tuberculosis)\b',
         "genitourinary_tuberculosis"),
        (r'\b(?:intraocular|ocular|ophthalmic)\s+(?:tb|tuberculosis)\b',
         "intraocular_tuberculosis"),
    ]

    def match_stw_condition(self, diagnosis: str) -> Optional[Dict[str, Any]]:
        """
        Deterministic word-boundary dispatch over the ICMR Standard Treatment
        Workflows (2022). Returns the matched condition with its source document
        record attached, so a caller can never render the clinical content
        without the provenance that qualifies it.
        """
        if not diagnosis:
            return None

        conditions = self.stw_collection.get("conditions", {})
        if not conditions:
            return None

        d_lower = diagnosis.lower()
        for pattern, key in self.STW_CONDITION_PATTERNS:
            if key in conditions and re.search(pattern, d_lower):
                condition = dict(conditions[key])
                condition["condition_key"] = key
                doc_id = condition.get("source_document_id")
                condition["source_document"] = self.stw_collection.get(
                    "documents", {}
                ).get(doc_id)
                ref = (condition.get("medications") or {}).get("regimen_ref")
                if ref:
                    for regimen in self.stw_collection.get("shared_regimens", {}).values():
                        if regimen.get("regimen_id") == ref:
                            condition["referenced_regimen"] = regimen
                            break
                return condition
        return None

    def get_stw_condition(self, condition_key: str) -> Optional[Dict[str, Any]]:
        return self.stw_collection.get("conditions", {}).get(condition_key)

    def list_stw_conditions(self) -> List[Dict[str, Any]]:
        """Index of every workflow condition, for the guidelines browse endpoint."""
        out = []
        for key, cond in self.stw_collection.get("conditions", {}).items():
            out.append({
                "condition_key": key,
                "condition_name": cond.get("condition_name"),
                "icd10": cond.get("icd10"),
                "specialty": cond.get("specialty"),
                "infection_type": cond.get("infection_type"),
                "source_document_id": cond.get("source_document_id"),
                "source_page": cond.get("source_page"),
            })
        return out

    # ------------------------------------------------------------------
    # ICMR Treatment Guidelines 2022-23 edition syndrome index
    # ------------------------------------------------------------------

    STG_CONDITION_PATTERNS: List[Tuple[str, str]] = [
        # -- ordered most specific first; the first match wins --
        # Tuberculosis and the STW-covered dermatoses are deliberately absent:
        # those belong to the workflow collection, not to this chapter set.
        (r'\bspontaneous\s+bacterial\s+peritonitis\b|\bsbp\b', "spontaneous_bacterial_peritonitis_stg"),
        (r'\binfected\s+pancreatic\s+necrosis\b|\bpancreatic\s+abscess\b', "iai_infected_pancreatic_necrosis"),
        (r'\bcholangitis\b|\bcholecystitis\b', "iai_cholangitis_cholecystitis"),
        (r'\bliver\s+abscess\b|\bhepatic\s+abscess\b', "iai_liver_abscess"),
        (r'\bhealth\s*care\s+associated\s+intra[\s-]?abdominal\b|\bhospital\s+acquired\s+intra[\s-]?abdominal\b',
         "iai_healthcare_associated"),
        (r'\bintra[\s-]?abdominal\b.*\b(?:severe|high\s+severity|high\s+risk)\b|\b(?:severe|high\s+severity)\b.*\bintra[\s-]?abdominal\b',
         "iai_community_high_severity"),
        (r'\bintra[\s-]?abdominal\b', "iai_community_mild_moderate"),
        (r'\bcholera\b', "diarrhea_cholera"),
        (r'\bshigell\w*\b', "diarrhea_shigella"),
        (r'\bamoebiasis\b|\bamoebic\s+dysentery\b', "diarrhea_amoebiasis"),
        (r'\bgiardiasis\b', "diarrhea_giardiasis"),
        (r'\bcampylobacter\b', "diarrhea_campylobacter"),
        (r'\baeromonas\b', "diarrhea_aeromonas"),
        (r'\b(?:bloody\s+diarrh\w+|dysentery)\b', "acute_bloody_diarrhea"),
        (r'\b(?:watery\s+diarrh\w+|acute\s+diarrh\w+|diarrh\w+|gastroenteritis)\b', "acute_watery_diarrhea"),
        # Skin and soft tissue
        (r'\bnecroti[sz]ing\s+fasciitis\b.*\b(?:fresh\s+water|salt\s+water|aeromonas|vibrio)\b',
         "necrotizing_fasciitis_aquatic"),
        (r'\bnecroti[sz]ing\s+fasciitis\b', "necrotizing_fasciitis"),
        (r'\bfurunculosis\b|\bfuruncle\b|\bboil\b', "furunculosis"),
        (r'\bcarbuncle\b', "carbuncle_stg"),
        (r'\berysipelas\b', "erysipelas_stg"),
        (r'\bcellulitis\b', "cellulitis_stg"),
        (r'\b(?:peri[\s-]?tonsillar\s+abscess|quinsy)\b', "peritonsillar_abscess"),
        (r'\bsuppurative\s+parotitis\b|\bparotitis\b', "suppurative_parotitis"),
        (r"\bludwig'?s?\s+angina\b", "ludwigs_angina"),
        (r'\bodontogenic\b', "odontogenic_deep_neck_infection"),
        (r'\brhinogenic\b', "rhinogenic_deep_neck_infection"),
        (r'\botologic\b', "otologic_deep_neck_infection"),
        (r'\bprevertebral\s+abscess\b', "prevertebral_abscess"),
        (r'\blemierre\b', "lemierre_syndrome"),
        (r'\b(?:skin|soft\s+tissue)\s+abscess\b', "skin_abscess_stg"),
        # Bone and joint
        (r'\bprosthetic\s+joint\s+infection\b|\bpji\b', "prosthetic_joint_infection"),
        (r'\bseptic\s+arthritis\b|\bpyogenic\s+arthritis\b', "septic_arthritis_native"),
        (r'\bchronic\s+osteomyelitis\b', "chronic_osteomyelitis"),
        (r'\bosteomyelitis\b', "acute_osteomyelitis"),
        # CNS
        (r'\bhealth\s*care\s+associated\s+(?:meningitis|ventriculitis)\b|\bventriculitis\b|\bpost[\s-]?neurosurgical\s+meningitis\b',
         "healthcare_associated_meningitis"),
        (r'\b(?:csf\s+)?shunt\s+infection\b', "csf_shunt_infection"),
        (r'\bbrain\s+abscess\b.*\b(?:hiv|immunocompromised|immunosuppressed)\b|\b(?:hiv|immunocompromised)\b.*\bbrain\s+abscess\b',
         "brain_abscess_immunocompromised"),
        (r'\bbrain\s+abscess\b.*\bneonat\w*\b|\bneonat\w*\b.*\bbrain\s+abscess\b', "brain_abscess_neonatal"),
        (r'\bbrain\s+abscess\b.*\b(?:otitis|mastoiditis|sinusitis|dental)\b', "brain_abscess_contiguous"),
        (r'\bbrain\s+abscess\b|\bsubdural\s+empyema\b|\bcerebral\s+abscess\b', "brain_abscess_hematogenous"),
        (r'\bacute\s+febrile\s+encephalopathy\b|\bacute\s+encephalitis\s+syndrome\b|\bafe\b|\baes\b',
         "acute_febrile_encephalopathy"),
        (r'\b(?:acute\s+)?bacterial\s+meningitis\b|\bpyogenic\s+meningitis\b|\bmeningitis\b',
         "acute_bacterial_meningitis"),
        # Urinary tract
        (r'\bcatheter[\s-]?associated\s+urinary\b|\bca[\s-]?uti\b|\bcauti\b', "catheter_associated_uti"),
        (r'\basymptomatic\s+bacteriuria\b|\basb\b', "asymptomatic_bacteriuria"),
        (r'\bpyelonephritis\b', "acute_pyelonephritis"),
        (r'\bprostatitis\b.*\bchronic\b|\bchronic\s+prostatitis\b', "sot_chronic_prostatitis"),
        (r'\bprostatitis\b', "acute_prostatitis"),
        (r'\bepididymo[\s-]?orchitis\b.*\b(?:sexually\s+transmitted|sti|high\s+risk)\b', "epididymo_orchitis_sti"),
        (r'\bepididymo[\s-]?orchitis\b|\borchitis\b|\bepididymitis\b', "epididymo_orchitis_enteric"),
        (r'\bcandiduria\b', "candiduria"),
        (r'\bcomplicated\s+uti\b|\bcomplicated\s+urinary\s+tract\s+infection\b', "complicated_uti"),
        (r'\buti\b.*\bchild\w*\b|\bchild\w*\b.*\buti\b|\bpaediatric\s+uti\b|\bpediatric\s+uti\b', "uti_in_children"),
        # Hospital acquired
        (r'\bsurgical\s+site\s+infection\b|\bssi\b', "surgical_site_infection"),
        (r'\bclabsi\b.*\bcandida\b|\bcandidemia\b|\bcandidaemia\b', "clabsi_candida"),
        (r'\bclabsi\b|\bcentral\s+line[\s-]?associated\b|\bcrbsi\b|\bcatheter[\s-]?related\s+blood\s*stream\b',
         "clabsi"),
        (r'\b(?:hospital\s+acquired|ventilator[\s-]?associated)\s+pneumonia\b|\bhap\b|\bvap\b', "hap_vap"),
        (r'\bc(?:lostridi\w*)?\.?\s*difficile\b|\bcdi\b|\bpseudomembranous\s+colitis\b',
         "clostridioides_difficile_infection"),
        # Immunocompromised host
        (r'\bfebrile\s+neutropenia\b|\bneutropenic\s+sepsis\b', "febrile_neutropenia"),
        (r'\binvasive\s+pulmonary\s+aspergillosis\b|\baspergillosis\b', "invasive_pulmonary_aspergillosis"),
        (r'\bmucormycosis\b|\bzygomycosis\b', "mucormycosis"),
        (r'\bpneumocystis\b|\bpcp\b|\bpjp\b', "pneumocystis_jirovecii_pneumonia"),
        (r'\bnocardia\w*\b', "nocardiosis"),
        (r'\bcmv\b|\bcytomegalovirus\b', "cmv_reactivation"),
        (r'\bherpes\s+simplex\b|\bhsv\b', "herpes_simplex_immunocompromised"),
        (r'\bvaricella\b|\bzoster\b|\bshingles\b', "varicella_zoster_immunocompromised"),
        (r'\bacute\s+bacterial\s+pharyngitis\b|\bpharyngitis\b|\bstrep\s+throat\b', "acute_bacterial_pharyngitis"),
        (r'\bacute\s+bronchitis\b|\bbronchitis\b', "acute_bronchitis_sot"),
        (r'\b(?:acute\s+)?sinusitis\b|\brhinosinusitis\b', "acute_sinusitis_sot"),
        (r'\blung\s+abscess\b|\bempyema\s+thoracis\b|\bempyema\b', "sot_lung_abscess_empyema"),
        (r'\bhead\s+and\s+neck\s+space\s+infection\b|\bdeep\s+neck\s+space\s+infection\b',
         "sot_head_neck_space_infection"),
        (r'\bacute\s+cystitis\b|\bcystitis\b|\bsimple\s+uti\b|\blower\s+uti\b', "acute_cystitis_stg"),
    ]

    def match_stg_condition(self, diagnosis: str) -> Optional[Dict[str, Any]]:
        """
        Deterministic word-boundary dispatch over the ICMR Treatment Guidelines
        2022-23 edition syndrome index. The matched condition is returned with its
        authority document and attribution basis attached, and never without them.
        """
        if not diagnosis:
            return None

        conditions = self.stg_syndromes.get("conditions", {})
        if not conditions:
            return None

        d_lower = diagnosis.lower()
        for pattern, key in self.STG_CONDITION_PATTERNS:
            if key in conditions and re.search(pattern, d_lower):
                condition = dict(conditions[key])
                condition["condition_key"] = key
                condition["authority_document_id"] = self.stg_syndromes.get("authority_document_id")
                condition["authority_document"] = self.stg_syndromes.get("documents", {}).get(
                    self.stg_syndromes.get("authority_document_id")
                )
                return condition
        return None

    def get_stg_condition(self, condition_key: str) -> Optional[Dict[str, Any]]:
        return self.stg_syndromes.get("conditions", {}).get(condition_key)

    def list_stg_conditions(self) -> List[Dict[str, Any]]:
        out = []
        for key, cond in self.stg_syndromes.get("conditions", {}).items():
            out.append({
                "condition_key": key,
                "condition_name": cond.get("condition_name"),
                "chapter": cond.get("chapter"),
                "source_page": cond.get("source_page"),
                "source_page_status": cond.get("source_page_status"),
                "attribution_basis": cond.get("attribution_basis"),
                "prior_edition_cross_reference": cond.get("prior_edition_cross_reference"),
            })
        return out

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

    def national_antimicrobial_authorities(self) -> List[Dict[str, Any]]:
        """
        The national antimicrobial guidelines this system actually holds.

        Read from the ingested corpus, not hardcoded. The previous hardcoded string
        named "ICMR Edition 3", an edition never present in this repository, which is
        precisely the stale-version claim Spec 22 exists to prevent. Two authorities
        are held now and the count is not assumed either.
        """
        from backend.config import NATIONAL_ANTIMICROBIAL_AUTHORITY_DOCUMENT_IDS

        try:
            from backend.rag.store import vector_store
            docs = vector_store.docs
        except Exception:  # pragma: no cover - retrieval must never break policy
            return []

        out = []
        for doc_id in NATIONAL_ANTIMICROBIAL_AUTHORITY_DOCUMENT_IDS:
            doc = docs.get(doc_id)
            if not doc:
                continue
            out.append({
                "document_id": doc_id,
                "title": doc.get("title"),
                "version": doc.get("version"),
                "issuing_org": doc.get("issuing_org"),
                "precedence_rank": doc.get("precedence_rank"),
            })
        return out

    def resolve_guideline_precedence(self, syndrome_key: str) -> Dict[str, Any]:
        """
        Documented guideline precedence policy (Section 8A):
        Returns the precedence order and surfaces any known conflicts between National
        and International guidance.
        """
        authorities = self.national_antimicrobial_authorities()
        precedence = {
            "hierarchy": GUIDELINE_PRECEDENCE_HIERARCHY,
            # Derived from the corpus rather than asserted. If nothing is ingested the
            # honest answer is that no national guideline is held, not a version string.
            "national_antimicrobial_authorities": authorities,
            "selected_scope": (
                "National (India) - "
                + "; ".join(f"{a['title']} [{a['version']}]" for a in authorities)
                if authorities else
                "No national antimicrobial guideline is currently ingested."
            ),
            "multiple_national_authorities_note": (
                "Two national antimicrobial guidelines from different bodies are held. "
                "Neither supersedes the other in this system and no adjudication between "
                "them is performed; where they differ, both are shown and the clinical "
                "resolution belongs to the reader."
                if len(authorities) > 1 else None
            ),
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
