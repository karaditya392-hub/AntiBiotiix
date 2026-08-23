# Explainable Antimicrobial Stewardship and Prescription Safety Assistant (S11 Microbe)

An explainable, evidence-grounded Clinical Decision-Support System (CDSS) for antimicrobial stewardship, prescription safety, allergy cross-reactivity checking, renal & hepatic dosage adjustments, therapeutic duplication detection, and guideline compliance.

---

## 🌟 Key Capabilities & Safety Architecture

1. **Clinical Decision Support Boundary:** Strictly advisory. The system assists clinicians by surfacing evidence-backed safety concerns, never autonomously prescribing or issuing definitive safe/unsafe declarations.
2. **Deterministic Clinical Rule Engine:** 23 structured, versioned, and attributed rules for:
   - Knowledge base coverage fail-safe (`COVERAGE-001`) preventing unassessed drugs from receiving silent all-clears.
   - Empirical guideline discordance alerts (`DIAG-001`) grounded in ICMR syndrome recommendations.
   - Direct and class-level beta-lactam allergy cross-reactivity with tokenized matching.
   - Renal function dosing via **CKD-EPI 2021 non-race adjusted formula** (eGFR thresholds, Nitrofurantoin contraindication).
   - Hepatic function dosing via **Child-Pugh criteria** (Metronidazole, Voriconazole, Rifampin).
   - Redundant anaerobic coverage duplication (Metronidazole + Piperacillin-Tazobactam) and same-class duplication.
   - Non-duplicate Drug-Drug Interactions: Additive cardiac QTc prolongation (Fluoroquinolones/Macrolides + Ondansetron/Amiodarone), Warfarin potentiation, Serotonin Syndrome (Linezolid + SSRIs), and Statin interactions across both home medications and co-prescribed items.
   - Vulnerable populations: Pregnancy teratogenicity risks (Fluoroquinolones, Tetracyclines), lactation safety, and pediatric weight-based dosing requirements.
   - Missing information guards for allergy, renal, hepatic, and pregnancy states.
3. **Structured Prescription Entity Extraction (Section 3A):** Hybrid Regex/NER parser with per-field confidence scoring, multi-drug segmentation, combination strength support (e.g. 875/125 mg), and mandatory clinician confirmation on low confidence or missing critical fields.
4. **Authoritative Guideline Knowledge Base & Precedence (Section 8, 8A, 8B):**
   - **Rank 1:** Local Hospital Antibiogram & Formulary
   - **Rank 2:** Indian Council of Medical Research (ICMR) National Treatment Guidelines (Edition 3, 2022-2023)
   - **Rank 3:** WHO AWaRe Classification (Access, Watch, Reserve 2023) & IDSA Guidelines
   - Authentic Indian resistance data from the ICMR AMR Surveillance Network (98,400 isolates).
5. **Deterministic Template Explainer with Injection-Hardened Input Handling (Section 10, 10A, 22A):**
   - Input sanitization and XML sandboxing neutralizing adversarial instructions embedded in free-text fields.
   - Model name, prompt template ID, and evidence SHA-256 hash computed and logged per explanation for full audit reproducibility.
6. **Server-Side Role Authorization & Clinician Override (Section 18, 18A):**
   - Mandatory substantive clinical rationale capture with server-side token validation (`ATTENDING_PHYSICIAN`, `INFECTIOUS_DISEASE_SPECIALIST`, `CLINICAL_PHARMACIST`, `RESIDENT_PHYSICIAN`). Client request body role claims are ignored.
7. **Immutable Audit Logging & Alert Fatigue Monitoring (Section 16A, 19):**
   - SHA-256 hash-chained append-only audit trail with transactional head reads and cryptographic verification endpoint (`/api/audit/verify`).
   - Per-rule override rate analytics flagging rules exceeding the 60% alert-fatigue threshold for clinical recalibration.
8. **Deterministic Stewardship Priority Rollup (Section 14, 15, 20):**
   - Pure, deterministic severity rollup categorizing review priority (HIGH, MODERATE, LOW) directly from active warnings, uncovered medications, and WHO Reserve agents with explicit contributing rule attribution.

---

## 🚀 Quick Start & Running Locally

### 1. Requirements
- Python 3.10+
- Dependencies: `fastapi`, `uvicorn`, `sqlalchemy`, `pydantic`, `pytest`, `httpx` (no opaque ML dependencies)
- Modern Web Browser (Chrome, Edge, Firefox, Safari)

### 2. Seed Database
```bash
python -m backend.seed_data
```

### 3. Run Automated Clinical Safety & Extraction Test Suite (237 Tests)
```bash
python -m pytest tests/ -v
```

### 4. Start the Application Server
```bash
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload
```
Open your browser at `http://127.0.0.1:8000/` to access the clinical decision-support interface.

---

## Comprehensive Test Suite (237 Tests Across 16 Modules)

- `tests/test_clinical_safety.py`: 27 clinical safety scenarios and edge cases.
- `tests/test_coverage_failsafe.py`: Unknown drug, real uncovered drug (Amikacin), and covered drug tests.
- `tests/test_auth_roles.py`: Token verification, spoofed body rejection (403), valid authorized override (200), and rule authoring permissions.
- `tests/test_stewardship_priority.py`: Deterministic severity rollup and triage ordering regression tests.
- `tests/test_extraction_accuracy.py`: 21-case labeled benchmark suite measuring per-field precision and recall.
- `tests/test_prompt_injection.py`: Adversarial prompt injection and instruction hijacking resistance tests.
- `tests/test_api_workflow.py`: End-to-end API lifecycle from text extraction to cryptographic audit chain verification.

---

## 📊 Audit Report

The complete 30-section audit report is available at:  
[`backend/audit/clinical_ml_audit_report.md`](file:///c:/Users/iraba/OneDrive/Desktop/Microbe/backend/audit/clinical_ml_audit_report.md)
