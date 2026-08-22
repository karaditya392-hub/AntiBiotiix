"""
Structured Prescription Extraction & Clinical Parsing Layer (Section 3A)
Extracts structured prescription entities from free-text clinician notes / orders
with per-field confidence scoring and human-in-the-loop confirmation triggers.
"""
import re
from typing import Dict, List, Any, Optional, Tuple

from backend.models.schemas import (
    PrescriptionItem, ExtractedPrescription, AWaReCategory
)
from backend.guidelines.knowledge_base import knowledge_base


class ClinicalPrescriptionParser:
    def __init__(self):
        self.kb = knowledge_base
        
        # Regex patterns for clinical dosing entities
        # Support single doses (500 mg) and combination strengths (875/125 mg, 500/125 mg, 400/80 mg)
        self.combo_dose_pattern = re.compile(r'(\b\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*(mg|g|gm|mcg|ml|iu|units?)\b', re.IGNORECASE)
        self.dose_pattern = re.compile(r'(\b\d+(?:\.\d+)?)\s*(mg|g|gm|mcg|ml|iu|units?)\b', re.IGNORECASE)
        self.route_pattern = re.compile(r'\b(po|oral|iv|intravenous|im|intramuscular|topical|inh|inhaled|sc|subcutaneous)\b', re.IGNORECASE)
        self.freq_pattern = re.compile(r'\b(qd|od|daily|once daily|bid|bd|twice daily|tid|tds|three times daily|qid|four times daily|q8h|q12h|q24h|q6h|q4h|prn|stat|hs)\b', re.IGNORECASE)
        self.dur_pattern = re.compile(r'(?:x|for|\*)\s*(\d+)\s*(days?|d|weeks?|wks?)\b|\b(\d+)\s*(?:days?|d)\s*(?:course|duration)?\b', re.IGNORECASE)
        self.diag_pattern = re.compile(r'(?:dx|diagnosis|for|indication|indicated for|due to|presenting with)\s*:?\s*([a-zA-Z\s\-\(\)]+?)(?:,|\.|\n|$|;|with)', re.IGNORECASE)
        
        # Known antimicrobial dictionary sorted by DESCENDING length so multi-word (e.g. Amoxicillin-Clavulanate) matches before single words
        drugs = list(self.kb.drugs_db.keys())
        self.known_drugs = sorted(drugs, key=lambda d: len(d.replace("_", " ")), reverse=True)

    def parse_free_text(self, text: str) -> ExtractedPrescription:
        """
        Parse free-text prescription string into structured fields with derived confidence scores.
        """
        if not text or not text.strip():
            return ExtractedPrescription(
                raw_text="",
                items=[],
                field_confidences={"medication": 0.0, "dose": 0.0, "route": 0.0, "frequency": 0.0, "duration": 0.0},
                overall_confidence=0.0,
                needs_clinician_confirmation=True,
                unparsed_tokens=[]
            )

        clean_text = text.strip()
        # Split on line breaks or conjunctions like ' and ' / semicolons
        raw_segments = re.split(r'[\n;]+|\band\b(?=\s+[A-Za-z]+)', clean_text)
        segments = [s.strip() for s in raw_segments if s.strip()]

        items: List[PrescriptionItem] = []
        overall_conf_scores: List[float] = []
        extracted_diagnosis: Optional[str] = None
        multi_drug_line_flag = False

        # Extract diagnosis if present
        diag_match = self.diag_pattern.search(clean_text)
        if diag_match:
            candidate_diag = diag_match.group(1).strip()
            if len(candidate_diag) > 3 and not any(candidate_diag.lower().startswith(d.replace("_", " ")) for d in self.known_drugs):
                extracted_diagnosis = candidate_diag.title()

        for seg in segments:
            # Check for multiple drugs in a single segment
            parsed_items = self._parse_segment_multi(seg)
            if len(parsed_items) > 1:
                multi_drug_line_flag = True

            for item, confidences in parsed_items:
                if extracted_diagnosis and not item.indication:
                    item.indication = extracted_diagnosis
                items.append(item)
                line_avg_conf = sum(confidences.values()) / max(len([v for v in confidences.values() if v > 0]), 1)
                overall_conf_scores.append(line_avg_conf)

        if not items:
            # Fallback whole-text parse
            parsed_items = self._parse_segment_multi(clean_text)
            for item, confidences in parsed_items:
                if extracted_diagnosis and not item.indication:
                    item.indication = extracted_diagnosis
                items.append(item)
                overall_conf_scores.append(sum(confidences.values()) / max(len([v for v in confidences.values() if v > 0]), 1))

        # Calculate overall confidence
        overall_confidence = (
            sum(overall_conf_scores) / len(overall_conf_scores) if overall_conf_scores else 0.0
        )

        # Check for combination strength dose (e.g. 875/125 mg)
        combo_dose_flag = bool(self.combo_dose_pattern.search(clean_text))

        # Trigger mandatory clinician confirmation if:
        # 1. No items detected or overall confidence < 0.80
        # 2. Multiple drug items in order
        # 3. Any item missing dose, route, or frequency
        # 4. Multi-drug segment detected
        # 5. Ambiguous combination strength detected (e.g. 875/125 mg)
        needs_confirmation = False
        if not items or overall_confidence < 0.80 or len(items) > 1 or multi_drug_line_flag or combo_dose_flag:
            needs_confirmation = True
        else:
            for it in items:
                if it.dose is None or not it.route or not it.frequency:
                    needs_confirmation = True
                    break

        field_confidences = {
            "medication": round(sum(i.extraction_confidence.get("medication", 0.0) for i in items) / max(len(items), 1), 2) if items else 0.0,
            "dose": round(sum(i.extraction_confidence.get("dose", 0.0) for i in items) / max(len(items), 1), 2) if items else 0.0,
            "route": round(sum(i.extraction_confidence.get("route", 0.0) for i in items) / max(len(items), 1), 2) if items else 0.0,
            "frequency": round(sum(i.extraction_confidence.get("frequency", 0.0) for i in items) / max(len(items), 1), 2) if items else 0.0,
            "duration": round(sum(i.extraction_confidence.get("duration", 0.0) for i in items) / max(len(items), 1), 2) if items else 0.0,
            "diagnosis": 0.85 if extracted_diagnosis else 0.0
        }

        return ExtractedPrescription(
            raw_text=clean_text,
            diagnosis=extracted_diagnosis,
            items=items,
            field_confidences=field_confidences,
            overall_confidence=round(overall_confidence, 2),
            needs_clinician_confirmation=needs_confirmation,
            extraction_method="HYBRID_REGEX_NER_CLINICAL_PARSER"
        )

    def _parse_segment_multi(self, text: str) -> List[Tuple[PrescriptionItem, Dict[str, float]]]:
        """Detect all drug matches in a segment and parse each corresponding prescription item."""
        results: List[Tuple[PrescriptionItem, Dict[str, float]]] = []
        norm_text = text.lower().replace("-", " ")

        # Find all drug mentions in text
        drug_mentions: List[Tuple[int, int, str, float]] = []  # (start, end, drug_name, confidence)

        for drug_key in self.known_drugs:
            formatted_key = drug_key.replace("_", " ")
            pattern = rf'\b{re.escape(formatted_key)}\b'
            for m in re.finditer(pattern, norm_text):
                drug_info = self.kb.get_drug_info(drug_key)
                canonical_name = drug_info.get("name", drug_key.title()) if drug_info else drug_key.title()
                # Check for overlap with existing longer mention
                overlap = any(m.start() < end and m.end() > start for start, end, _, _ in drug_mentions)
                if not overlap:
                    drug_mentions.append((m.start(), m.end(), canonical_name, 0.98))

        # Check aliases
        words = text.split()
        for word in words:
            clean_word = re.sub(r'[^a-zA-Z]', '', word).lower()
            norm = self.kb.normalize_drug_name(clean_word)
            if norm in self.known_drugs and norm != clean_word:
                drug_info = self.kb.get_drug_info(norm)
                canonical_name = drug_info.get("name", norm.title()) if drug_info else norm.title()
                pattern = rf'\b{re.escape(clean_word)}\b'
                for m in re.finditer(pattern, text.lower()):
                    overlap = any(m.start() < end and m.end() > start for start, end, _, _ in drug_mentions)
                    if not overlap:
                        drug_mentions.append((m.start(), m.end(), canonical_name, 0.90))

        if not drug_mentions:
            return []

        # Sort mentions by appearance order
        drug_mentions.sort(key=lambda x: x[0])

        # If single mention, parse full segment
        if len(drug_mentions) == 1:
            _, _, drug_name, drug_conf = drug_mentions[0]
            item, confs = self._parse_fields(text, drug_name, drug_conf)
            results.append((item, confs))
        else:
            # Multi-drug: divide text into slices for each drug
            for idx, (start, end, drug_name, drug_conf) in enumerate(drug_mentions):
                next_start = drug_mentions[idx + 1][0] if idx + 1 < len(drug_mentions) else len(text)
                slice_text = text[start:next_start]
                item, confs = self._parse_fields(slice_text, drug_name, drug_conf)
                results.append((item, confs))

        return results

    def _parse_fields(self, slice_text: str, found_med: str, med_conf: float) -> Tuple[PrescriptionItem, Dict[str, float]]:
        """Parse dose, route, frequency, duration for a specific drug slice."""
        confidences = {
            "medication": med_conf,
            "dose": 0.0,
            "unit": 0.0,
            "route": 0.0,
            "frequency": 0.0,
            "duration": 0.0
        }

        # 1. Detect Dose & Unit (Handle combination strengths e.g. 875/125 mg)
        extracted_dose: Optional[float] = None
        extracted_unit: Optional[str] = None

        combo_m = self.combo_dose_pattern.search(slice_text)
        if combo_m:
            try:
                d1 = float(combo_m.group(1))
                d2 = float(combo_m.group(2))
                extracted_dose = d1 + d2  # Total mg or combination strength
                extracted_unit = combo_m.group(3).lower()
                confidences["dose"] = 0.95
                confidences["unit"] = 0.95
            except ValueError:
                pass
        else:
            dose_m = self.dose_pattern.search(slice_text)
            if dose_m:
                try:
                    extracted_dose = float(dose_m.group(1))
                    extracted_unit = dose_m.group(2).lower()
                    confidences["dose"] = 0.95
                    confidences["unit"] = 0.95
                except ValueError:
                    pass

        # 2. Detect Route
        extracted_route: Optional[str] = None
        route_m = self.route_pattern.search(slice_text)
        if route_m:
            r = route_m.group(1).upper()
            if r in ["ORAL", "PO"]:
                extracted_route = "PO"
            elif r in ["INTRAVENOUS", "IV"]:
                extracted_route = "IV"
            elif r in ["INTRAMUSCULAR", "IM"]:
                extracted_route = "IM"
            else:
                extracted_route = r
            confidences["route"] = 0.95

        # 3. Detect Frequency
        extracted_freq: Optional[str] = None
        freq_m = self.freq_pattern.search(slice_text)
        if freq_m:
            f = freq_m.group(1).upper()
            freq_map = {
                "OD": "QD", "DAILY": "QD", "ONCE DAILY": "QD",
                "BD": "BID", "TWICE DAILY": "BID",
                "TDS": "TID", "THREE TIMES DAILY": "TID",
                "FOUR TIMES DAILY": "QID"
            }
            extracted_freq = freq_map.get(f, f)
            confidences["frequency"] = 0.95

        # 4. Detect Duration
        extracted_duration: Optional[int] = None
        dur_m = self.dur_pattern.search(slice_text)
        if dur_m:
            num = dur_m.group(1) or dur_m.group(3)
            unit = (dur_m.group(2) or "days").lower()
            if num:
                try:
                    val = int(num)
                    if "week" in unit or "wk" in unit:
                        val = val * 7
                    extracted_duration = val
                    confidences["duration"] = 0.90
                except ValueError:
                    pass

        # Drug classification & AWaRe category
        drug_info = self.kb.get_drug_info(self.kb.normalize_drug_name(found_med))
        s_class = drug_info.get("super_class") if drug_info else None
        aware_cat = self.kb.get_aware_category(found_med)

        item = PrescriptionItem(
            medication_name=found_med,
            dose=extracted_dose,
            unit=extracted_unit,  # None if no dose found
            route=extracted_route,
            frequency=extracted_freq,
            duration_days=extracted_duration,
            antimicrobial_class=s_class,
            aware_category=AWaReCategory(aware_cat) if aware_cat in AWaReCategory.__members__ else AWaReCategory.NOT_APPLICABLE,
            extraction_confidence=confidences
        )

        return item, confidences


# Singleton parser
clinical_parser = ClinicalPrescriptionParser()
