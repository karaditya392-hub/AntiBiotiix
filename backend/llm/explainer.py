"""
Deterministic Clinical Explainer with Injection-Hardened Input Handling & Version Pinning (Spec §9, §10, §10A, §22A, §23)
Strictly explains deterministic rule engine findings without independent prescribing authority.
"""
import re
import hashlib
from typing import List, Dict, Any, Optional, Tuple

from backend.config import MODEL_NAME, PROMPT_TEMPLATE_ID, PROMPT_TEMPLATE_HASH
from backend.models.schemas import SafetyWarning, PrescriptionItem, PatientCreate
from backend.guidelines.knowledge_base import knowledge_base


class ClinicalExplainer:
    def __init__(self):
        self.model_name = MODEL_NAME
        self.prompt_template_id = PROMPT_TEMPLATE_ID
        self.prompt_template_hash = PROMPT_TEMPLATE_HASH
        self.kb = knowledge_base
        
        # Injection detection patterns (Spec §10A)
        self.injection_patterns = [
            # `ignore ... instructions` allows the qualifier that almost every real
            # attempt puts in the middle -- "ignore ALL previous instructions",
            # "ignore the above instructions". The original pattern required the
            # three words adjacent and so missed the single most common phrasing.
            re.compile(r'(?:(?:ignore|disregard|forget)\s+(?:\w+\s+){0,3}(?:instructions?|prompts?|rules?|context)|system\s*:\s*override|disregard\s+prior|mark\s+as\s+safe|do\s+not\s+warn|safe\s+to\s+prescribe)', re.IGNORECASE),
            re.compile(r'(?:</context>|<system>|\[INST\]|###\s*instruction|```system)', re.IGNORECASE),
            re.compile(r'(?:you\s+are\s+now|bypass\s+safety|override\s+alert)', re.IGNORECASE)
        ]

    def sanitize_input(self, text: Optional[str]) -> Tuple[str, bool]:
        """
        Sanitize user/patient-supplied text to prevent prompt injection.
        Returns cleaned text and a boolean indicating whether an injection attempt was detected.
        """
        if not text:
            return "", False
            
        is_adversarial = False
        for pattern in self.injection_patterns:
            if pattern.search(text):
                is_adversarial = True
                break

        # Strip structural delimiters and suspicious tokens
        cleaned = re.sub(r'</?[a-zA-Z0-9_\-]+>', '', text)
        cleaned = re.sub(r'[\[\]\{\}\<\>\(\)]', '', cleaned)
        cleaned = cleaned.replace("SYSTEM:", "USER_NOTE:").replace("Assistant:", "")
        
        return cleaned.strip(), is_adversarial

    def generate_explanation(
        self,
        patient: PatientCreate,
        items: List[PrescriptionItem],
        warnings: List[SafetyWarning],
        diagnosis: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate clinician-friendly explanation strictly grounded in deterministic warnings and guidelines.
        """
        # Check all free-text fields for adversarial injection
        notes_clean, notes_inj = self.sanitize_input(patient.clinical_notes)
        diag_clean, diag_inj = self.sanitize_input(diagnosis)
        
        injection_flagged = notes_inj or diag_inj

        # Compute evidence hash for audit reproducibility (Spec §22A)
        evidence_corpus = " | ".join([
            f"{w.rule_id}:{w.evidence.document_title}:{w.evidence.verbatim_passage}" 
            for w in warnings
        ]) if warnings else "NO_WARNINGS_EMPTY_CORPUS"
        evidence_hash = hashlib.sha256(evidence_corpus.encode("utf-8")).hexdigest()

        # Identify any uncovered drugs
        uncovered_items = [
            it.medication_name for it in items
            if self.kb.get_drug_info(self.kb.normalize_drug_name(it.medication_name)) is None
        ]

        if not warnings:
            if not items:
                explanation_text = "No medications entered. Insufficient information to perform prescription safety analysis."
            elif uncovered_items:
                # Uncovered medications fail-safe branch
                uncovered_str = ", ".join(uncovered_items)
                explanation_text = (
                    f"Prescription contains medication(s) outside the validated antimicrobial knowledge base: {uncovered_str}. "
                    f"Safety evaluation (allergies, renal/hepatic adjustments, teratogenicity, interactions) was UNAVAILABLE for these agents. "
                    f"Manual clinical pharmacotherapy review is required prior to dispensing. Do not assume absence of safety concerns."
                )
            else:
                med_names = ", ".join([i.medication_name for i in items])
                explanation_text = (
                    f"Prescription for {med_names} evaluated against validated clinical safety rules and ICMR antimicrobial guidance. "
                    f"No contraindications or safety concerns were triggered for the recorded patient parameters. "
                    f"Please review clinical indication, renal dosing, and allergy records to confirm appropriateness."
                )
        else:
            explanation_parts = []
            if uncovered_items:
                uncovered_str = ", ".join(uncovered_items)
                explanation_parts.append(
                    f"**Notice: Prescription contains uncovered medication(s) ({uncovered_str}) outside validated knowledge base.**\n"
                )
            explanation_parts.append(
                f"**Clinical Decision-Support Analysis Summary ({len(warnings)} Potential Concern(s) Identified):**\n"
            )
            
            for idx, w in enumerate(warnings, 1):
                severity_badge = f"[{w.severity.value}]"
                explanation_parts.append(
                    f"{idx}. {severity_badge} **{w.title}**\n"
                    f"   - **Clinical Concern:** {w.clinical_concern}\n"
                    f"   - **Recommended Action:** {w.recommendation}\n"
                    f"   - **Supporting Evidence:** {w.evidence.document_title} ({w.evidence.guideline_version})\n"
                    f"   - *Passage:* \"{w.evidence.verbatim_passage}\"\n"
                )
            
            explanation_parts.append(
                "\n*Notice: This system is a Clinical Decision-Support tool. Final prescribing authority rests with the responsible clinician.*"
            )
            explanation_text = "\n".join(explanation_parts)

        return {
            "explanation": explanation_text,
            "metadata": {
                "explainer_component": "Deterministic Template Explainer with Injection-Hardened Input Handling",
                "model_identifier": self.model_name,
                "prompt_template_id": self.prompt_template_id,
                "prompt_template_hash": self.prompt_template_hash,
                "evidence_hash": f"sha256:{evidence_hash}",
                "injection_detected": injection_flagged,
                "clinical_decision_support_only": True
            }
        }


# Singleton explainer
clinical_explainer = ClinicalExplainer()
