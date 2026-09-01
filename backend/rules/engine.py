"""
Clinical Safety Rule Engine for S11 Prescription Safety & Stewardship Assistant
Strictly deterministic, evidence-grounded clinical decision-support evaluator.
"""
import re
from typing import List, Dict, Any, Optional
from datetime import datetime

from backend.models.schemas import (
    SafetyWarning, SeverityLevel, RuleCategory, EvidenceCitation,
    PatientCreate, PrescriptionCreate, PrescriptionItem, PregnancyStatus,
    AgeCategory, LactationStatus
)
from backend.guidelines.knowledge_base import knowledge_base
from backend.guidelines.label_evidence import label_evidence_store


class ClinicalRuleEngine:
    def __init__(self):
        self.kb = knowledge_base

    def evaluate_prescription(
        self,
        patient: PatientCreate,
        prescription: PrescriptionCreate,
        prescription_id: Optional[str] = None
    ) -> List[SafetyWarning]:
        """
        Execute all deterministic clinical safety checks for a patient and prescription.
        Returns a list of structured SafetyWarning objects.
        """
        warnings: List[SafetyWarning] = []
        presc_id = prescription_id or getattr(prescription, "prescription_id", None) or "RX-CURRENT"
        items = prescription.items or []

        # 0. KNOWLEDGE BASE COVERAGE FAIL-SAFE (Spec §17, §23, §32)
        warnings.extend(self._check_kb_coverage(presc_id, items))

        # 1. ALLERGY CHECKS (Spec §4)
        warnings.extend(self._check_allergies(presc_id, patient, items))

        # 2. RENAL CONSIDERATIONS (Spec §5)
        warnings.extend(self._check_renal(presc_id, patient, items))

        # 3. HEPATIC CONSIDERATIONS (Spec §5A)
        warnings.extend(self._check_hepatic(presc_id, patient, items))

        # 4. DUPLICATION CHECKS (Spec §6)
        warnings.extend(self._check_duplications(presc_id, items))

        # 5. NON-DUPLICATE DRUG-DRUG INTERACTIONS (Spec §6A) - Home meds + Co-prescribed items
        warnings.extend(self._check_drug_interactions(presc_id, patient, items))

        # 6. VULNERABLE POPULATIONS (Spec §3B)
        warnings.extend(self._check_vulnerable_populations(presc_id, patient, items))

        # 7. DIAGNOSIS-GUIDELINE DISCORDANCE (Spec §7)
        warnings.extend(self._check_diagnosis_guideline(presc_id, prescription.diagnosis, items))

        # 8. ANTIMICROBIAL STEWARDSHIP & WHO AWARE CHECKS (Spec §8, §13)
        warnings.extend(self._check_stewardship(presc_id, prescription.diagnosis, items))

        return warnings

    def _check_kb_coverage(self, prescription_id: str, items: List[PrescriptionItem]) -> List[SafetyWarning]:
        """
        Fail-safe: Flag any antimicrobial or candidate medication outside the validated clinical knowledge base (Spec §17, §23, §32).
        Prevents silent all-clear for unsupported/unrecognized antimicrobial medications.
        Excludes known non-antimicrobial concomitant medications (e.g. Ondansetron, Warfarin) to prevent alert fatigue.
        """
        warnings = []
        rule = self.kb.get_rule_by_id("COVERAGE-001")
        if not rule:
            raise ValueError("Required clinical rule 'COVERAGE-001' not found in clinical_rules_catalog.json")

        for item in items:
            norm_drug = self.kb.normalize_drug_name(item.medication_name)
            
            # Non-antimicrobial concomitant medications are evaluated for DDIs, not antimicrobial stewardship coverage
            if self.kb.is_known_non_antimicrobial(norm_drug):
                continue

            drug_info = self.kb.get_drug_info(norm_drug)
            if not drug_info:
                warnings.append(self._create_warning(
                    prescription_id=prescription_id,
                    rule=rule,
                    prescribed_drug=item.medication_name,
                    norm_drug=norm_drug,
                    interacting_factor="Medication Outside Validated Knowledge Base",
                    citation_text="Clinical Decision Support Safety Architecture (Coverage Fail-Safe): Prescribed medication is outside the validated clinical knowledge base. Comprehensive safety checks (allergies, renal/hepatic adjustments, teratogenicity, interactions) cannot be evaluated. Manual clinician review required."
                ))
                continue

            # Partial coverage is not coverage.
            #
            # Drugs sourced from a guideline that states only indication and dose
            # have no renal, hepatic, pregnancy, lactation or interaction data in
            # this repository. Having an entry at all is enough to silence the
            # branch above, so without this check adding a drug would CONVERT a
            # loud "not assessed" into a silent all-clear on exactly the checks
            # that were never performed. The gaps are named so the clinician
            # knows which ones to carry out themselves.
            if drug_info.get("knowledge_coverage") == "PARTIAL":
                gaps = drug_info.get("coverage_gaps") or []
                gap_text = ", ".join(g.replace("_", " ") for g in gaps) or "one or more safety domains"
                warnings.append(self._create_warning(
                    prescription_id=prescription_id,
                    rule=rule,
                    prescribed_drug=item.medication_name,
                    norm_drug=norm_drug,
                    interacting_factor="Partial Knowledge Base Coverage",
                    citation_text=(
                        "Clinical Decision Support Safety Architecture (Coverage Fail-Safe): "
                        f"{item.medication_name} is present in the knowledge base for indication and dose only, "
                        "sourced from a held clinical guideline. The following safety domains are NOT held by "
                        f"this system and have NOT been assessed: {gap_text}. This is an absence of data, not a "
                        "finding of safety. Manual clinician review of the unassessed domains is required."
                    )
                ))
        return warnings

    def _check_allergies(self, prescription_id: str, patient: PatientCreate, items: List[PrescriptionItem]) -> List[SafetyWarning]:
        warnings = []

        # Missing allergy information guard (Rule ALLERGY-004)
        if not patient.allergy_status_known or patient.allergies is None:
            rule = self.kb.get_rule_by_id("ALLERGY-004")
            if not rule:
                raise ValueError("Required clinical rule 'ALLERGY-004' not found")
            for item in items:
                norm_d = self.kb.normalize_drug_name(item.medication_name)
                warnings.append(self._create_warning(
                    prescription_id=prescription_id,
                    rule=rule,
                    prescribed_drug=item.medication_name,
                    norm_drug=norm_d,
                    interacting_factor="Allergy History Not Recorded",
                    citation_text="WHO & ICMR Patient Safety Guidelines: Medication allergy history must be explicitly elicited and documented before antimicrobial administration."
                ))
            return warnings

        # Normalized token matching for allergies (Spec §4)
        documented_allergies = [a.strip() for a in patient.allergies if a and a.strip()]

        # Provenance for each allergy, when the caller supplied it. A patient
        # self-report still fires the rule -- withholding a safety check because
        # the report is unverified would be the wrong trade -- but the warning
        # must say which kind of report it came from, so a clinician knows
        # whether to confirm it before acting.
        provenance = getattr(patient, "allergy_provenance", None) or {}

        def _allergy_provenance(raw: str) -> str:
            src = provenance.get(raw.strip().lower())
            if src == "SELF_REPORTED":
                return (" [PATIENT-REPORTED, NOT YET CLINICIAN-VERIFIED - confirm the "
                        "reaction history before relying on or dismissing this warning]")
            return ""

        def _allergy_label(raw: str) -> str:
            src = provenance.get(raw.strip().lower())
            tag = " (patient-reported, unverified)" if src == "SELF_REPORTED" else ""
            return f"{raw.title()}{tag}"

        for item in items:
            drug_name = item.medication_name
            norm_drug = self.kb.normalize_drug_name(drug_name)
            drug_info = self.kb.get_drug_info(norm_drug)
            if not drug_info:
                continue

            drug_class = drug_info.get("class", "").lower()
            super_class = drug_info.get("super_class", "").lower()
            drug_tokens = set(re.findall(r'[a-z0-9]+', norm_drug.lower()))

            for raw_allergy in documented_allergies:
                norm_allergy = self.kb.normalize_drug_name(raw_allergy)
                allergy_tokens = set(re.findall(r'[a-z0-9]+', norm_allergy.lower()))

                # Filter out negation tokens so "not penicillin" does not direct-match
                negations = {"not", "no", "non", "never", "tolerated", "denies"}
                has_negation = bool(allergy_tokens & negations)
                if has_negation:
                    continue

                # Direct Exact/Normalized Match (Rule ALLERGY-001)
                is_direct_match = (norm_allergy == norm_drug) or bool(allergy_tokens & drug_tokens)
                if is_direct_match:
                    rule = self.kb.get_rule_by_id("ALLERGY-001")
                    if rule:
                        warnings.append(self._create_warning(
                            prescription_id=prescription_id,
                            rule=rule,
                            prescribed_drug=drug_name,
                            norm_drug=norm_drug,
                            interacting_factor=f"Documented Allergy: {_allergy_label(raw_allergy)}",
                            citation_text=f"ICMR Guidelines Section 2: Direct match with documented patient allergy '{raw_allergy}'. Prescribing this specific agent is contraindicated without formal desensitization or allergy delabeling.{_allergy_provenance(raw_allergy)}"
                        ))
                    continue

                # Class Match (Rule ALLERGY-002) - Penicillins
                if ("penicillin" in norm_allergy or "penicillin" in raw_allergy.lower()) and (
                    "penicillin" in drug_class or "penicillin" in super_class or norm_drug in ["amoxicillin", "amoxicillin_clavulanate", "piperacillin_tazobactam", "ampicillin"]
                ):
                    rule = self.kb.get_rule_by_id("ALLERGY-002")
                    if rule:
                        warnings.append(self._create_warning(
                            prescription_id=prescription_id,
                            rule=rule,
                            prescribed_drug=drug_name,
                            norm_drug=norm_drug,
                            interacting_factor=f"Documented Allergy: {_allergy_label(raw_allergy)}",
                            citation_text=f"ICMR Guidelines 2022 / JTFPP 2022: Prescribed drug {drug_name} belongs to the penicillin class and shares the beta-lactam core, presenting high allergic cross-reactivity with documented penicillin allergy.{_allergy_provenance(raw_allergy)}"
                        ))
                    continue

                # Cross-reactivity: Penicillin allergy with Cephalosporin (Rule ALLERGY-003)
                if ("penicillin" in norm_allergy or "penicillin" in raw_allergy.lower()) and (
                    "cephalosporin" in super_class or "cephalosporin" in drug_class or norm_drug.startswith("cef")
                ):
                    rule = self.kb.get_rule_by_id("ALLERGY-003")
                    if rule:
                        warnings.append(self._create_warning(
                            prescription_id=prescription_id,
                            rule=rule,
                            prescribed_drug=drug_name,
                            norm_drug=norm_drug,
                            interacting_factor=f"Documented Allergy: {_allergy_label(raw_allergy)}",
                            citation_text=f"ICMR Guidelines 2022: 3rd-generation cephalosporins (e.g. Ceftriaxone) have low cross-reactivity (<1%) with penicillins due to distinct R1/R2 side chains, but require clinical vigilance if prior reaction was severe IgE-mediated anaphylaxis.{_allergy_provenance(raw_allergy)}"
                        ))

        return warnings

    def _check_renal(self, prescription_id: str, patient: PatientCreate, items: List[PrescriptionItem]) -> List[SafetyWarning]:
        warnings = []

        for item in items:
            drug_name = item.medication_name
            norm_drug = self.kb.normalize_drug_name(drug_name)
            drug_info = self.kb.get_drug_info(norm_drug)
            if not drug_info:
                continue

            renal_data = drug_info.get("renal_dosing")
            if not renal_data:
                continue

            threshold = renal_data.get("egfr_threshold_ml_min", 0)
            # None means the held source says renal function MATTERS for this drug but
            # states no number to compare against -- the hepatitis guideline names
            # tenofovir alafenamide as the choice "in patients with reduced renal
            # function" and gives no eGFR, and doses ribavirin partly on renal function
            # without a threshold. That is a different thing from threshold 0 ("no renal
            # restriction"), but it has the same consequence here: no automatic
            # comparison is possible, and inventing a cut-off to make one possible is
            # exactly the fabrication this knowledge base refuses. The recommendation
            # text still reaches the clinician through the drug's evidence record.
            #
            # Without this guard the comparison below raised TypeError and took down
            # the whole analysis for any prescription containing such a drug.
            if threshold is None or threshold == 0:
                continue

            # Check missing renal info guard (Rule RENAL-003)
            if not patient.renal_status_known or patient.egfr_ml_min is None:
                rule = self.kb.get_rule_by_id("RENAL-003")
                if rule:
                    warnings.append(self._create_warning(
                        prescription_id=prescription_id,
                        rule=rule,
                        prescribed_drug=drug_name,
                        norm_drug=norm_drug,
                        interacting_factor="Renal Function (eGFR) Unrecorded",
                        citation_text=f"ICMR Guidelines 2022: {drug_name} is renally cleared. Baseline eGFR/serum creatinine measurement required to verify safe dosing."
                    ))
                continue

            # Severe Renal Contraindication: Nitrofurantoin (Rule RENAL-002)
            if norm_drug == "nitrofurantoin" and patient.egfr_ml_min < 30:
                rule = self.kb.get_rule_by_id("RENAL-002")
                if rule:
                    warnings.append(self._create_warning(
                        prescription_id=prescription_id,
                        rule=rule,
                        prescribed_drug=drug_name,
                        norm_drug=norm_drug,
                        interacting_factor=f"Patient eGFR: {patient.egfr_ml_min} mL/min (CKD-EPI 2021 non-race)",
                        citation_text=renal_data.get("evidence_passage", "ICMR Guidelines: Nitrofurantoin is contraindicated if eGFR < 30 mL/min due to inadequate urinary therapeutic concentrations and increased neurotoxicity."),
                        evidence_probes=["creatinine clearance", "renal function"]
                    ))
                continue

            # Nitrofurantoin 30-59 mL/min: authoritative sources disagree (Rule RENAL-004).
            # The FDA product label contraindicates below CrCl 60; the ICMR-derived
            # threshold used above flags only below 30. Neither is adopted silently --
            # the divergence itself is surfaced at MODERATE severity so the clinician
            # decides which threshold governs. See RENAL-004 in the rule catalog.
            if norm_drug == "nitrofurantoin" and 30 <= patient.egfr_ml_min < 60:
                rule = self.kb.get_rule_by_id("RENAL-004")
                if rule:
                    warnings.append(self._create_warning(
                        prescription_id=prescription_id,
                        rule=rule,
                        prescribed_drug=drug_name,
                        norm_drug=norm_drug,
                        interacting_factor=(
                            f"Patient eGFR: {patient.egfr_ml_min} mL/min (CKD-EPI 2021 non-race) "
                            f"- within source-divergence band (30-59)"
                        ),
                        citation_text=(
                            "Source threshold divergence. FDA product labelling for nitrofurantoin lists "
                            "creatinine clearance under 60 mL/min as a contraindication. The ICMR-derived "
                            "threshold applied by this system flags below 30 mL/min. This prescription falls "
                            "between the two, so both positions are surfaced rather than one being adopted "
                            "silently. Clinician judgement governs."
                        ),
                        evidence_probes=["creatinine clearance"]
                    ))
                continue

            # Standard Renal Impairment Consideration (Rule RENAL-001)
            if patient.egfr_ml_min < threshold:
                rule = self.kb.get_rule_by_id("RENAL-001")
                if rule:
                    rec = renal_data.get("recommendation", "Adjust dose or interval.")
                    passage = renal_data.get("evidence_passage", "ICMR Guidelines: Dosage adjustment required based on eGFR.")
                    warnings.append(self._create_warning(
                        prescription_id=prescription_id,
                        rule=rule,
                        prescribed_drug=drug_name,
                        norm_drug=norm_drug,
                        interacting_factor=f"Patient eGFR: {patient.egfr_ml_min} mL/min (< threshold {threshold} mL/min)",
                        recommendation_override=f"{rec} (Current eGFR: {patient.egfr_ml_min} mL/min)",
                        citation_text=passage
                    ))

        return warnings

    def _check_hepatic(self, prescription_id: str, patient: PatientCreate, items: List[PrescriptionItem]) -> List[SafetyWarning]:
        warnings = []

        for item in items:
            drug_name = item.medication_name
            norm_drug = self.kb.normalize_drug_name(drug_name)
            drug_info = self.kb.get_drug_info(norm_drug)
            if not drug_info:
                continue

            hepatic_data = drug_info.get("hepatic_dosing", {})
            requires_adj = hepatic_data.get("requires_adjustment", False)
            if not requires_adj:
                continue

            # Check missing hepatic info guard (Rule HEPATIC-002)
            if not patient.hepatic_status_known or (patient.child_pugh_class is None and patient.hepatic_status_known is False):
                rule = self.kb.get_rule_by_id("HEPATIC-002")
                if rule:
                    warnings.append(self._create_warning(
                        prescription_id=prescription_id,
                        rule=rule,
                        prescribed_drug=drug_name,
                        norm_drug=norm_drug,
                        interacting_factor="Hepatic Function Unrecorded",
                        citation_text=f"ICMR Guidelines: {drug_name} is extensively cleared via hepatic metabolism. Assessment of hepatic function recommended."
                    ))
                continue

            # Hepatic impairment alert (Rule HEPATIC-001)
            if patient.child_pugh_class in ["B", "C", "Child-Pugh B", "Child-Pugh C"]:
                rule = self.kb.get_rule_by_id("HEPATIC-001")
                if rule:
                    rec = hepatic_data.get("recommendation", "Review hepatic dose adjustment.")
                    passage = hepatic_data.get("evidence_passage", "ICMR Guidelines Section 7: In severe hepatic dysfunction, clearance is decreased, warranting dose reduction to prevent toxicity.")
                    warnings.append(self._create_warning(
                        prescription_id=prescription_id,
                        rule=rule,
                        prescribed_drug=drug_name,
                        norm_drug=norm_drug,
                        interacting_factor=f"Hepatic Impairment: {patient.child_pugh_class}",
                        recommendation_override=f"{rec} (Patient Child-Pugh: {patient.child_pugh_class})",
                        citation_text=passage
                    ))

        return warnings

    def _check_duplications(self, prescription_id: str, items: List[PrescriptionItem]) -> List[SafetyWarning]:
        warnings = []
        if len(items) < 2:
            return warnings

        norm_drugs = [self.kb.normalize_drug_name(i.medication_name) for i in items]

        # 1. Redundant Anaerobic Coverage (Rule DUP-001)
        if "metronidazole" in norm_drugs:
            for drug in norm_drugs:
                if drug in ["piperacillin_tazobactam", "meropenem", "amoxicillin_clavulanate", "clindamycin"]:
                    rule = self.kb.get_rule_by_id("DUP-001")
                    if rule:
                        warnings.append(self._create_warning(
                            prescription_id=prescription_id,
                            rule=rule,
                            prescribed_drug="Metronidazole",
                            norm_drug="metronidazole",
                            interacting_factor=f"Concurrent Agent: {drug.replace('_', ' ').title()}",
                            citation_text=f"ICMR Guidelines 2022 / IDSA Guidelines: {drug.replace('_', ' ').title()} already provides potent anaerobic spectrum against Bacteroides fragilis; simultaneous Metronidazole creates redundant duplication without proven benefit."
                        ))
                    break

        # 2. Same Class Duplication (Rule DUP-002)
        classes_seen: Dict[str, List[str]] = {}
        for item in items:
            norm_d = self.kb.normalize_drug_name(item.medication_name)
            info = self.kb.get_drug_info(norm_d)
            if info:
                s_class = info.get("super_class", "")
                if s_class:
                    if s_class not in classes_seen:
                        classes_seen[s_class] = []
                    classes_seen[s_class].append(item.medication_name)

        for s_class, drug_list in classes_seen.items():
            if len(drug_list) > 1:
                rule = self.kb.get_rule_by_id("DUP-002")
                if rule:
                    norm_first = self.kb.normalize_drug_name(drug_list[0])
                    warnings.append(self._create_warning(
                        prescription_id=prescription_id,
                        rule=rule,
                        prescribed_drug=drug_list[0],
                        norm_drug=norm_first,
                        interacting_factor=f"Same-Class Agent: {', '.join(drug_list[1:])} (Class: {s_class})",
                        citation_text=f"ICMR Guidelines 2022 / WHO AWaRe Policy: Regimen contains multiple agents from {s_class}. Streamline to a single targeted agent."
                    ))

        return warnings

    def _check_drug_interactions(
        self, prescription_id: str, patient: PatientCreate, items: List[PrescriptionItem]
    ) -> List[SafetyWarning]:
        """
        Check drug interactions against BOTH patient.active_medications and co-prescribed items (Spec §6A).
        Excludes self by list index.
        """
        warnings = []
        home_meds = [m.strip().lower() for m in (patient.active_medications or []) if m and m.strip()]

        for idx, item in enumerate(items):
            drug_name = item.medication_name
            norm_drug = self.kb.normalize_drug_name(drug_name)
            drug_info = self.kb.get_drug_info(norm_drug)
            if not drug_info:
                continue

            interactions = drug_info.get("interactions", [])
            if not interactions:
                continue

            # Build candidate list: Home medications + Other co-prescribed items (exclude self by index)
            candidate_meds = []
            for hm in home_meds:
                candidate_meds.append({"name": hm, "source": "Home Medication"})
            for jdx, other_item in enumerate(items):
                if jdx != idx:
                    candidate_meds.append({"name": other_item.medication_name.lower(), "source": "Co-prescribed Order"})

            for inter in interactions:
                target = inter.get("interacting_drug_or_class", "").lower()
                target_tokens = [t for t in re.split(r'[/(),\s]+', target) if t]

                for cand in candidate_meds:
                    cand_name = cand["name"]
                    cand_source = cand["source"]
                    cand_tokens = [c for c in re.split(r'[/(),\s]+', cand_name) if c]

                    match_found = False

                    # Specific pharmacological checks
                    if "warfarin" in target and "warfarin" in cand_name:
                        match_found = True
                    elif "ondansetron" in target and "ondansetron" in cand_name:
                        match_found = True
                    elif "amiodarone" in target and "amiodarone" in cand_name:
                        match_found = True
                    elif "haloperidol" in target and "haloperidol" in cand_name:
                        match_found = True
                    elif "statin" in target and any(s in cand_name for s in ["statin", "atorvastatin", "simvastatin", "rosuvastatin"]):
                        match_found = True
                    elif "ssri" in target and any(s in cand_name for s in ["fluoxetine", "sertraline", "escitalopram", "citalopram", "paroxetine", "venlafaxine", "duloxetine"]):
                        match_found = True
                    elif any(t in cand_tokens for t in target_tokens if len(t) > 3):
                        match_found = True

                    if match_found:
                        rule_id = "DDI-001"
                        # A combination the guideline states outright as
                        # CONTRAINDICATED is checked first and routed to its own
                        # rule. Falling through to the mechanism heuristics below
                        # would grade it by whichever keyword happened to match --
                        # a contraindicated pairing with no QT or serotonin wording
                        # would land on DDI-001 and be reported as an ordinary
                        # interaction, which is a weaker claim than the source makes.
                        if str(inter.get("severity", "")).upper() == "CONTRAINDICATED":
                            rule_id = "DDI-005"
                        elif "qt" in inter.get("mechanism", "").lower() or "amiodarone" in target or "ondansetron" in target:
                            rule_id = "DDI-002"
                        elif "serotonin" in inter.get("mechanism", "").lower() or norm_drug == "linezolid":
                            rule_id = "DDI-003"
                        elif "statin" in target or "rhabdomyolysis" in inter.get("mechanism", "").lower():
                            rule_id = "DDI-004"
                        elif "warfarin" in target:
                            rule_id = "DDI-001"

                        rule = self.kb.get_rule_by_id(rule_id)
                        if rule:
                            warnings.append(self._create_warning(
                                prescription_id=prescription_id,
                                rule=rule,
                                prescribed_drug=drug_name,
                                norm_drug=norm_drug,
                                interacting_factor=f"{cand_source}: {cand_name.title()}",
                                recommendation_override=inter.get("recommendation"),
                                citation_text=f"{inter.get('evidence_source', 'ICMR 2022')}: {inter.get('mechanism')} {inter.get('recommendation')}",
                                evidence_probes=[cand_name, inter.get("interacting_drug_or_class", "")]
                            ))

        return warnings

    def _check_vulnerable_populations(
        self, prescription_id: str, patient: PatientCreate, items: List[PrescriptionItem]
    ) -> List[SafetyWarning]:
        warnings = []

        for item in items:
            drug_name = item.medication_name
            norm_drug = self.kb.normalize_drug_name(drug_name)
            drug_info = self.kb.get_drug_info(norm_drug)
            if not drug_info:
                continue

            # 1. Pregnancy Safety (Rule VULN-001 for Fluoroquinolones, VULN-002 for Tetracyclines)
            is_pregnant = patient.pregnancy_status in [
                PregnancyStatus.PREGNANT_TRIMESTER_1,
                PregnancyStatus.PREGNANT_TRIMESTER_2,
                PregnancyStatus.PREGNANT_TRIMESTER_3,
                "PREGNANT_TRIMESTER_1", "PREGNANT_TRIMESTER_2", "PREGNANT_TRIMESTER_3"
            ]

            if is_pregnant:
                if norm_drug in ["ciprofloxacin", "levofloxacin"]:
                    rule = self.kb.get_rule_by_id("VULN-001")
                    if rule:
                        warnings.append(self._create_warning(
                            prescription_id=prescription_id,
                            rule=rule,
                            prescribed_drug=drug_name,
                            norm_drug=norm_drug,
                            interacting_factor=f"Pregnancy Status: {patient.pregnancy_status}",
                            evidence_probes=["pregnan", "fetal", "teratogen"],
                            citation_text="ICMR Guidelines 2022 Section 8: Fluoroquinolones cross the placenta and carry risk of fetal chondrotoxicity and arthropathy; avoid in pregnancy unless no alternatives exist."
                        ))
                elif norm_drug in ["doxycycline"]:
                    rule = self.kb.get_rule_by_id("VULN-002")
                    if rule:
                        warnings.append(self._create_warning(
                            prescription_id=prescription_id,
                            rule=rule,
                            prescribed_drug=drug_name,
                            norm_drug=norm_drug,
                            interacting_factor=f"Pregnancy Status: {patient.pregnancy_status}",
                            evidence_probes=["pregnan", "fetal", "last half of pregnancy"],
                            citation_text="ICMR Guidelines 2022 / FDA Category D: Tetracyclines cause permanent fetal tooth discoloration, enamel hypoplasia, and skeletal growth restriction when administered during pregnancy."
                        ))

                # Recorded pregnancy contraindication with no drug-specific rule
                # (Rule VULN-008).
                #
                # The branches above name four drugs. Twelve carry a recorded
                # pregnancy contraindication, so eight were recorded and never
                # evaluated -- gentamicin's own entry cites irreversible fetal
                # ototoxicity and nothing read it.
                #
                # Gated on an explicit per-drug flag, not on the prose: the recorded
                # wording is not uniform, and nitrofurantoin's contraindication
                # applies at 38-42 weeks while this system records only a trimester.
                # See scripts/add_pregnancy_contraindication_rule.py.
                elif drug_info.get("pregnancy_contraindicated") is True:
                    rule = self.kb.get_rule_by_id("VULN-008")
                    if rule:
                        recorded = drug_info.get("pregnancy_category") or "Contraindicated in pregnancy."
                        warnings.append(self._create_warning(
                            prescription_id=prescription_id,
                            rule=rule,
                            prescribed_drug=drug_name,
                            norm_drug=norm_drug,
                            interacting_factor=f"Pregnancy Status: {patient.pregnancy_status}",
                            recommendation_override=(
                                f"Recorded pregnancy position for {drug_name}: {recorded} "
                                f"Review and select an alternative where one exists."
                            ),
                            evidence_probes=["pregnan", "fetal", "teratogen"],
                            citation_text=(
                                f"Drug knowledge base pregnancy record for {drug_name}: {recorded} "
                                f"Basis: {drug_info.get('pregnancy_contraindication_basis', 'not recorded')}"
                            )
                        ))

            # Pregnancy Unknown Guard (Rule VULN-004)
            elif patient.pregnancy_status in [PregnancyStatus.UNKNOWN, "UNKNOWN"]:
                if patient.sex and patient.sex.upper() == "FEMALE" and patient.age and 12 <= patient.age <= 50:
                    if norm_drug in ["ciprofloxacin", "levofloxacin", "doxycycline", "clarithromycin"]:
                        rule = self.kb.get_rule_by_id("VULN-004")
                        if rule:
                            warnings.append(self._create_warning(
                                prescription_id=prescription_id,
                                rule=rule,
                                prescribed_drug=drug_name,
                                norm_drug=norm_drug,
                                interacting_factor="Pregnancy Status Unknown in Female of Reproductive Potential",
                                citation_text="ICMR Guidelines 2022: Pregnancy status must be confirmed prior to initiating antimicrobials with established fetal risks."
                            ))

            # 2. Pediatric Dosing (Rule VULN-003)
            is_pediatric = patient.age_category in [AgeCategory.PEDIATRIC, AgeCategory.NEONATAL, "PEDIATRIC", "NEONATAL"] or (patient.age is not None and patient.age < 18)
            if is_pediatric:
                ped_data = drug_info.get("pediatric_dosing", {})
                if ped_data.get("restricted", False):
                    rule = self.kb.get_rule_by_id("VULN-003")
                    if rule:
                        rec = ped_data.get("recommendation", "Avoid in pediatric patients.")
                        warnings.append(self._create_warning(
                            prescription_id=prescription_id,
                            rule=rule,
                            prescribed_drug=drug_name,
                            norm_drug=norm_drug,
                            interacting_factor=f"Pediatric Patient (Age: {patient.age} years)",
                            recommendation_override=rec,
                            citation_text=f"Indian Academy of Pediatrics (IAP) / ICMR 2022: {rec}"
                        ))
                elif ped_data.get("weight_based", False) and (patient.weight_kg is None or item.dose is None):
                    rule = self.kb.get_rule_by_id("VULN-003")
                    if rule:
                        std_dose = ped_data.get("standard_dose", "Weight-based dosing required.")
                        warnings.append(self._create_warning(
                            prescription_id=prescription_id,
                            rule=rule,
                            prescribed_drug=drug_name,
                            norm_drug=norm_drug,
                            interacting_factor=f"Pediatric Patient (Age: {patient.age} years, Weight: {patient.weight_kg} kg)",
                            recommendation_override=f"Verify weight-based dosing: {std_dose}",
                            citation_text=f"IAP / ICMR Pediatric Stewardship 2022: Standard pediatric dose is {std_dose}."
                        ))

            # 3. Lactation Safety (Rule VULN-005)
            #
            # `lactation_status` has been collected on every patient and
            # `lactation_safety` recorded on every drug since both were added, and
            # until this branch existed neither was read by any rule. The system was
            # asking clinicians for lactation status and discarding the answer.
            #
            # The drug's own recorded statement is surfaced verbatim rather than
            # restated here, so this branch carries no clinical claim of its own: if
            # the knowledge base says nothing about a drug in lactation, nothing is
            # asserted about it.
            is_lactating = patient.lactation_status in [LactationStatus.LACTATING, "LACTATING"]
            lactation_note = (drug_info.get("lactation_safety") or "").strip()
            if is_lactating and lactation_note:
                rule = self.kb.get_rule_by_id("VULN-005")
                if rule:
                    warnings.append(self._create_warning(
                        prescription_id=prescription_id,
                        rule=rule,
                        prescribed_drug=drug_name,
                        norm_drug=norm_drug,
                        interacting_factor="Patient documented as lactating",
                        recommendation_override=(
                            f"Recorded lactation position for {drug_name}: {lactation_note} "
                            f"Review against the expected duration of therapy and the age of the "
                            f"infant. Interrupting breastfeeding is rarely necessary and should "
                            f"not be advised reflexively."
                        ),
                        evidence_probes=["lactation", "nursing", "breast", "milk"],
                        citation_text=(
                            f"Drug knowledge base lactation record for {drug_name}: {lactation_note} "
                            f"NCDC National Treatment Guidelines for Antimicrobial Use (2016), Section G: "
                            f"\"Doxycycline is not recommended in nursing mothers. If need to administer "
                            f"doxycycline discontinuation of nursing may be contemplated.\""
                        )
                    ))

            # 4. Primaquine exclusions (Rules VULN-006, VULN-007)
            #
            # ICMR-STG-2019-ED2 states the primaquine recommendation and its
            # exclusions in one sentence. Holding the recommendation without the
            # exclusion would be holding half the guideline.
            if norm_drug == "primaquine":
                if is_pregnant or is_lactating:
                    rule = self.kb.get_rule_by_id("VULN-006")
                    if rule:
                        # The source excludes women breastfeeding infants UNDER 6
                        # MONTHS. This system does not record the infant's age, so
                        # the alert is raised for any documented lactation and the
                        # gap is stated rather than silently assumed either way.
                        which = "Pregnancy" if is_pregnant else "Lactation"
                        extra = "" if is_pregnant else (
                            " The guideline's exclusion applies to infants aged under 6 months; "
                            "this system does not record the infant's age, so confirm it."
                        )
                        warnings.append(self._create_warning(
                            prescription_id=prescription_id,
                            rule=rule,
                            prescribed_drug=drug_name,
                            norm_drug=norm_drug,
                            interacting_factor=f"{which} documented",
                            recommendation_override=(rule.get("recommendation", "") + extra).strip(),
                            evidence_probes=["pregnan", "breastfeed", "lactat"],
                            citation_text=(
                                "ICMR Treatment Guidelines for Antimicrobial Use in Common Syndromes, "
                                "2nd edition (2019), pp. 19-20: \"(except pregnant women, infants aged "
                                "< 6 months and women breastfeeding infants aged < 6 months)\""
                            )
                        ))

                # G6PD status is not a structured field on the patient record, so
                # the free-text history is searched. A recorded status of EITHER
                # kind satisfies this: the rule asks whether the status is known,
                # not what it is.
                history_blob = " ".join(
                    list(patient.medical_history or []) + [patient.clinical_notes or ""]
                ).lower()
                if not re.search(r"g6pd|glucose[- ]6[- ]phosphate", history_blob):
                    rule = self.kb.get_rule_by_id("VULN-007")
                    if rule:
                        warnings.append(self._create_warning(
                            prescription_id=prescription_id,
                            rule=rule,
                            prescribed_drug=drug_name,
                            norm_drug=norm_drug,
                            interacting_factor="No G6PD status recorded in patient history",
                            evidence_probes=["g6pd", "glucose-6-phosphate", "haemolysis", "hemolysis"],
                            citation_text=(
                                "ICMR Treatment Guidelines for Antimicrobial Use in Common Syndromes, "
                                "2nd edition (2019), p. 20: \"The G6PD status of patients should be "
                                "used to guide administration of primaquine for preventing relapse.\" "
                                "The same source states that for single low-dose transmission-blocking "
                                "use, G6PD testing is not required."
                            )
                        ))

        return warnings

    # Agent lists a syndrome entry may carry. Every one of them is a list of agents
    # the guideline NAMES for the syndrome; a drug absent from all of them is absent
    # from the guideline's options, which is the only claim DIAG-002 makes.
    _SYNDROME_AGENT_FIELDS = (
        "first_line_preferred",
        "alternative_atypical",
        "alternative_penicillin_allergic",
        "second_line",
        "inpatient_severe",
        "mrsa_suspected",
    )

    def _check_diagnosis_guideline(
        self, prescription_id: str, diagnosis: Optional[str], items: List[PrescriptionItem]
    ) -> List[SafetyWarning]:
        """
        Check prescribed antimicrobial against ICMR guideline empirical recommendations (Spec §7).
        Surfaces DIAG-001 when a drug is in avoid_empirical or discouraged for the matched syndrome.
        """
        warnings = []
        if not diagnosis:
            return warnings

        syndrome = self.kb.match_syndrome_guideline(diagnosis)
        if not syndrome:
            return warnings

        avoid_list = syndrome.get("avoid_empirical", [])
        norm_avoid = [self.kb.normalize_drug_name(a) for a in avoid_list]

        for item in items:
            norm_drug = self.kb.normalize_drug_name(item.medication_name)
            if norm_drug in norm_avoid or item.medication_name in avoid_list:
                rule = self.kb.get_rule_by_id("DIAG-001")
                if rule:
                    notes = syndrome.get("clinical_notes", "ICMR Guidelines: Agent is not recommended as empirical first-line therapy.")
                    first_line = ", ".join(syndrome.get("first_line_preferred", ["standard first-line agent"]))
                    rec = f"Review ICMR guideline for {syndrome.get('syndrome_name', diagnosis)}. Preferred first-line empirical: {first_line}."
                    warnings.append(self._create_warning(
                        prescription_id=prescription_id,
                        rule=rule,
                        prescribed_drug=item.medication_name,
                        norm_drug=norm_drug,
                        interacting_factor=f"Diagnosis: {diagnosis} (ICMR Avoid Empirical: {item.medication_name})",
                        recommendation_override=rec,
                        citation_text=notes
                    ))
                continue

            # DIAG-002: the agent is not on the avoid list, and is not among the
            # agents this guideline names either.
            #
            # Four of the nine syndromes held here carry no avoid_empirical list,
            # because their source documents state none. Without this branch those
            # syndromes matched a diagnosis and then changed nothing about the
            # review. The claim made here is deliberately weak and checkable: the
            # drug is absent from every named-agent list on the entry. It is NOT a
            # finding that the prescription is wrong, and the severity is LOW to say
            # so -- guidelines name common options, not every acceptable one.
            named = []
            for field in self._SYNDROME_AGENT_FIELDS:
                named.extend(syndrome.get(field) or [])
            if not named:
                continue
            norm_named = {self.kb.normalize_drug_name(n) for n in named}
            if norm_drug in norm_named:
                continue
            # Only assess agents the knowledge base recognises. An unrecognised drug
            # is already reported by COVERAGE-001, and saying it is also absent from
            # a guideline's list would be a second warning about the same fact.
            if not self.kb.get_drug_info(norm_drug):
                continue
            if self.kb.is_known_non_antimicrobial(norm_drug):
                continue

            rule = self.kb.get_rule_by_id("DIAG-002")
            if rule:
                source_doc = syndrome.get("source_document_id") or "the matched syndrome guideline"
                source_loc = syndrome.get("source_location")
                where = f"{source_doc}" + (f", {source_loc}" if source_loc and source_loc != "NOT RECORDED" else "")
                warnings.append(self._create_warning(
                    prescription_id=prescription_id,
                    rule=rule,
                    prescribed_drug=item.medication_name,
                    norm_drug=norm_drug,
                    interacting_factor=(
                        f"Diagnosis: {diagnosis} ({syndrome.get('syndrome_name', diagnosis)})"
                    ),
                    recommendation_override=(
                        f"{item.medication_name} is not among the agents named for "
                        f"{syndrome.get('syndrome_name', diagnosis)} by {where}. Named agents: "
                        f"{', '.join(sorted(set(named)))}. Confirm the clinical reason for "
                        f"selecting an agent outside that list - culture and susceptibility, "
                        f"documented allergy, local resistance or prior therapy are all valid "
                        f"reasons."
                    ),
                    citation_text=(
                        f"Source: {where}. "
                        + (syndrome.get("source_quote") or syndrome.get("clinical_notes") or "")
                    )
                ))

        return warnings

    def _check_stewardship(
        self, prescription_id: str, diagnosis: Optional[str], items: List[PrescriptionItem]
    ) -> List[SafetyWarning]:
        warnings = []

        for item in items:
            drug_name = item.medication_name
            norm_drug = self.kb.normalize_drug_name(drug_name)
            aware_cat = self.kb.get_aware_category(norm_drug)
            item.aware_category = aware_cat  # type: ignore

            # WHO Reserve Group Alert (Rule STEWARD-001)
            if aware_cat == "RESERVE":
                rule = self.kb.get_rule_by_id("STEWARD-001")
                if rule:
                    warnings.append(self._create_warning(
                        prescription_id=prescription_id,
                        rule=rule,
                        prescribed_drug=drug_name,
                        norm_drug=norm_drug,
                        interacting_factor="WHO 'RESERVE' Category Antimicrobial",
                        citation_text=f"WHO AWaRe Classification 2023 / ICMR National Guidelines: {drug_name} is a last-resort reserve antimicrobial requiring pre-authorization and microbiology confirmation."
                    ))

            # Watch escalation alert for mild outpatient diagnosis (Rule STEWARD-002)
            if aware_cat in ["WATCH", "RESERVE"] and diagnosis:
                d_lower = diagnosis.lower()
                if any(m in d_lower for m in ["bronchitis", "mild cystitis", "uncomplicated cystitis", "pharyngitis", "mild sinusitis"]):
                    rule = self.kb.get_rule_by_id("STEWARD-002")
                    if rule:
                        warnings.append(self._create_warning(
                            prescription_id=prescription_id,
                            rule=rule,
                            prescribed_drug=drug_name,
                            norm_drug=norm_drug,
                            interacting_factor=f"Mild Indication: {diagnosis}",
                            citation_text=f"ICMR Guidelines 2022 / WHO AWaRe 2023: First-line therapy for {diagnosis} is an Access group antibiotic (e.g. Amoxicillin, Nitrofurantoin). Broad-spectrum Watch agent should be de-escalated if possible."
                        ))

        return warnings

    def _create_warning(
        self,
        prescription_id: str,
        rule: Dict[str, Any],
        prescribed_drug: str,
        norm_drug: str,
        interacting_factor: Optional[str] = None,
        recommendation_override: Optional[str] = None,
        citation_text: Optional[str] = None,
        evidence_probes: Optional[List[str]] = None
    ) -> SafetyWarning:
        """
        Construct a deterministic, immutable structured SafetyWarning with full evidence traceability.
        Stable warning IDs keyed on (prescription_id, rule_id, norm_drug) to prevent orphaning overrides.
        """
        # Validate that required catalog rule fields exist (fail loudly)
        required_fields = ["rule_id", "category", "severity", "author", "approval_status"]
        for rf in required_fields:
            if not rule.get(rf):
                raise ValueError(f"Malformed clinical rule: missing required field '{rf}' in rule catalog for {rule}")

        # Deterministic stable warning ID.
        #
        # The interacting factor is part of the key because one rule can fire
        # more than once for the same drug: a patient on both Ondansetron and
        # Amiodarone triggers DDI-002 twice for Azithromycin, once per
        # interacting agent. Keying only on (prescription, rule, drug) made those
        # two warnings collide on the unique constraint and returned HTTP 500.
        # Both are clinically distinct and both must be shown.
        clean_norm = re.sub(r'[^a-zA-Z0-9_]', '', norm_drug).upper()
        warning_id = f"WARN-{prescription_id}-{rule['rule_id']}-{clean_norm}"
        if interacting_factor:
            factor_key = re.sub(r'[^a-zA-Z0-9]', '', interacting_factor).upper()[:24]
            if factor_key:
                warning_id = f"{warning_id}-{factor_key}"

        # Attach drug-specific regulatory product-label evidence when the label
        # actually discusses this rule's concept. Returns None otherwise, so an
        # irrelevant citation is never manufactured.
        supporting: List[EvidenceCitation] = []
        label_ev = label_evidence_store.get_label_evidence(
            norm_drug, rule.get("category", ""), probes=evidence_probes
        )
        if label_ev:
            supporting.append(EvidenceCitation(
                document_title=label_ev["document_title"],
                issuing_org=label_ev["issuing_org"],
                geographic_scope=label_ev["geographic_scope"],
                guideline_version=label_ev["guideline_version"],
                publication_date=label_ev.get("publication_date"),
                source_url=label_ev.get("source_url"),
                section_page=label_ev.get("section_page"),
                verbatim_passage=label_ev["verbatim_passage"],
            ))

        return SafetyWarning(
            warning_id=warning_id,
            rule_id=rule.get("rule_id"),
            category=RuleCategory(rule.get("category", "STEWARDSHIP")),
            severity=SeverityLevel(rule.get("severity", "MODERATE")),
            title=f"Potential {rule.get('category', '').replace('_', ' ').title()} Concern: {prescribed_drug}",
            clinical_concern=rule.get("output_concern", "Potential clinical safety concern identified."),
            recommendation=recommendation_override or rule.get("recommendation", "Clinician review recommended."),
            prescribed_drug=prescribed_drug,
            interacting_factor=interacting_factor,
            evidence=EvidenceCitation(
                document_title=rule.get("evidence_source", "ICMR National Guidelines"),
                issuing_org="Indian Council of Medical Research (ICMR) / WHO",
                geographic_scope="National (India - ICMR) / Global (WHO)",
                # No default edition: a rule without a stated version must not
                # silently inherit one this system may not hold (Spec 22).
                guideline_version=rule.get("guideline_version") or "VERSION NOT STATED IN RULE CATALOG",
                publication_date=rule.get("effective_date"),
                verbatim_passage=citation_text or rule.get("description", "Documented clinical safety rule."),
                source_url=rule.get("source_url"),
                unverified_sources=rule.get("unverified_sources") or []
            ),
            supporting_labels=supporting,
            rule_author=rule.get("author", "SYSTEM_GENERATED"),
            rule_approval_status=rule.get("approval_status", "PENDING_CLINICAL_REVIEW"),
            rule_effective_date=rule.get("effective_date"),
            status="ACTIVE"
        )


# Singleton instance
rule_engine = ClinicalRuleEngine()
