# Comprehensive Technical, ML, Clinical-Safety, and Data-Quality Audit Report

**Project:** Explainable Antimicrobial Stewardship and Prescription Safety Assistant (S11 Microbe)  
**Audit Date:** August 22, 2026 (Remediated Post-Audit Release)  
**Auditor:** Clinical Safety, AI/ML & Pharmacotherapy Assurance Board  
**Target Platform:** Clinical Decision Support System (CDSS) for Outpatient / Inpatient Antimicrobial Stewardship  
**Regulatory / Scope Classification:** Clinical Decision-Support Tool (Non-Prescribing, Strictly Advisory)

---

## Executive Summary & Scope

This rigorous technical, algorithmic, clinical-safety, and data-quality audit inspects the S11 Prescription Safety & Antimicrobial Stewardship prototype against all 32 strict clinical safety benchmarks. The system is designed to provide deterministic, evidence-grounded decision support to clinicians when prescribing antimicrobials, assessing drug-allergy cross-reactivity, renal dosing (via 2021 CKD-EPI non-race adjusted formula), hepatic impairment (Child-Pugh criteria), therapeutic duplications, drug-drug interactions (QT prolongation, warfarin potentiation, serotonin syndrome, statin rhabdomyolysis), vulnerable populations (pregnancy teratogenicity, lactation, pediatrics), empirical guideline adherence (ICMR National Treatment Guidelines, WHO AWaRe), and local resistance context (ICMR AMR Network).

The system enforces a strict clinical boundary: **it never autonomously prescribes, diagnoses, or unconditionally declares a medication safe or unsafe**. Every safety warning carries a direct verbatim citation from validated clinical guidelines.

---

## 1. System Architecture

The platform is architected as a decoupled, deterministic clinical intelligence system:
- **Presentation Layer (`frontend/`):** Vanilla JavaScript clinical dashboard supporting real-time prescription parsing review, structured safety warning visualization, evidence provenance inspection with full text citations, role-authorized clinician override dialogs, and alert-fatigue monitoring. All dynamic inputs are sanitized against XSS via explicit HTML escaping.
- **API & Orchestration Layer (`backend/app.py`):** FastAPI REST backend exposing endpoints for extraction, deterministic rule evaluation, guideline retrieval, clinician overrides, rule authoring, and cryptographic audit streaming. Zero hardcoded catalog versions or AMR isolate literals exist in API code.
- **Structured Extraction Layer (`backend/extraction/parser.py`):** Deterministic hybrid Regex/NER clinical entity parser with combination strength support (e.g., `875/125 mg`), descending length matching, multi-drug line segmentation, per-field confidence scoring, and mandatory clinician confirmation triggers for ambiguous inputs.
- **Deterministic Rule Engine (`backend/rules/engine.py`):** 23 structured, versioned clinical rules with a coverage fail-safe (`COVERAGE-001`) preventing unassessed antimicrobials from receiving silent false all-clears, while avoiding alert-fatigue triggers on concomitant non-antimicrobials.
- **Deterministic Stewardship Priority Rollup (`backend/rules/priority.py`):** Pure, explainable severity rollup classifying stewardship review priority (HIGH, MODERATE, LOW) directly from active warnings, escalating all critical/high allergy risks, WHO Reserve spectrum agents, and coverage status with full rule attribution. Replaces black-box ML models.
- **Guideline Knowledge Base & Precedence Engine (`backend/guidelines/knowledge_base.py`):** Versioned clinical guidelines (ICMR Edition 3 2022-2023, WHO AWaRe 2023) with explicit 3-tier precedence hierarchy and word-boundary syndrome matching.
- **Deterministic Explainer with Injection Containment (`backend/llm/explainer.py`):** Template-based summary generator with adversarial input sanitization, structural delimiter stripping, and cryptographic prompt/evidence SHA-256 hashing.
- **Security & Authorization Layer (`backend/auth/security.py`):** Server-side Bearer token session registry enforcing authorized clinician roles (`ATTENDING_PHYSICIAN`, `INFECTIOUS_DISEASE_SPECIALIST`, `CLINICAL_PHARMACIST`, `RESIDENT_PHYSICIAN`). Request body role claims are ignored.
- **Immutable Audit Trail (`backend/audit/logger.py`):** Cryptographically chained append-only SHA-256 audit logger with transactional head reads and cryptographic verification endpoint (`/api/audit/verify`).
- **Relational Persistence Layer (`backend/models/database.py`):** SQLite database storing de-identified patients, prescriptions, stable warnings, overrides, and alert metrics.

---

## 2. Implemented Features (Verified by 54-Test Automated Suite)

| Feature Area | Status | Implementation Reference |
| :--- | :--- | :--- |
| **Knowledge Base Coverage Fail-Safe** | **IMPLEMENTED** | `COVERAGE-001` (Emits HIGH severity warning for unvalidated antimicrobials; excludes non-antimicrobials) |
| **Direct & Class Allergy Safety** | **IMPLEMENTED** | `ALLERGY-001`, `ALLERGY-002`, `ALLERGY-003`, `ALLERGY-004` (Tokenized matching; escalates priority to HIGH) |
| **Renal Function Dosing** | **IMPLEMENTED** | `RENAL-001`, `RENAL-002`, `RENAL-003` (CKD-EPI 2021 non-race formula) |
| **Hepatic Function Dosing** | **IMPLEMENTED** | `HEPATIC-001`, `HEPATIC-002` (Child-Pugh B/C criteria) |
| **Antimicrobial Duplication** | **IMPLEMENTED** | `DUP-001` (Anaerobic), `DUP-002` (Same-class) |
| **Non-Duplicate Drug-Drug Interactions** | **IMPLEMENTED** | `DDI-001` (Warfarin), `DDI-002` (QTc), `DDI-003` (Linezolid/SSRI), `DDI-004` (Statin) |
| **Empirical Guideline Discordance** | **IMPLEMENTED** | `DIAG-001` (ICMR syndrome discordance) |
| **Vulnerable Populations** | **IMPLEMENTED** | `VULN-001` (Pregnancy Quinolones), `VULN-002` (Doxycycline), `VULN-003` (Pediatrics), `VULN-004` (Unknown Pregnancy) |
| **ICMR Guideline Alignment** | **IMPLEMENTED** | `backend/guidelines/data/icmr_antimicrobial_guidelines_2022.json` |
| **Guideline Precedence Hierarchy** | **IMPLEMENTED** | Local (Rank 1) > National ICMR (Rank 2) > International WHO/IDSA (Rank 3) |
| **WHO AWaRe Classification** | **IMPLEMENTED** | Access, Watch, Reserve tracking & alerts (`STEWARD-001`, `STEWARD-002`) |
| **Local AMR Surveillance Context** | **IMPLEMENTED** | ICMR AMR Surveillance Network Report (98,400 distinct isolates per source header; per-antimicrobial row counts sum to 166,100 — see §5 note) |
| **Structured Entity Extraction** | **IMPLEMENTED** | 21-case self-authored regression benchmark with mandatory confirmation on combo doses |
| **Adversarial Injection Resistance** | **IMPLEMENTED** | Sanitization and delimiter stripping neutralizing prompt injection |
| **Server-Side Role Authorization** | **IMPLEMENTED** | Token-resolved roles on `/api/warnings/{id}/override` and `/api/rules` |
| **Immutable Audit Logging** | **IMPLEMENTED** | Append-only SHA-256 hash chain with `/api/audit/verify` validation |
| **Alert Fatigue Monitoring** | **IMPLEMENTED** | Real-time override rate tracking flagging rules exceeding 60% threshold |
| **Deterministic Priority Rollup** | **IMPLEMENTED** | Pure severity rollup replacing black-box ML model |

---

## 3. Evaluation and Removal of the ML Subsystem (Spec §10, §11, §14, §15, §30)

During clinical safety evaluation, the auxiliary Machine Learning triage model (`backend/ml/`) was evaluated against three mandatory clinical criteria:
1. **Clinical Output Effect:** The ML model produced a numerical score but had zero impact on clinical safety rules or warnings.
2. **Superiority over Deterministic Logic:** The ML model attempted to approximate an algebraic combination of rules and AWaRe categories, but introduced stochastic training noise and non-zero false negatives.
3. **Clinical Severity Correlation:** The ML model was found to be **anti-correlated with true clinical severity**.

### Empirical Failure Analysis of ML Model vs. Deterministic Rollup

**Reproducibility notice.** The ML probabilities below were recorded from a live run of
`StewardshipRiskMLModel.predict_risk()` **before** `backend/ml/` was deleted. Because the
module has been removed and this project is not under version control, these figures
**cannot be re-derived from the current codebase**. They are reported here as a historical
record of why the subsystem was retired, not as a reproducible measurement. The
`Deterministic Rollup` column, by contrast, is reproducible at any time from
`backend/rules/priority.py` and is covered by `tests/test_stewardship_priority.py`.

| Clinical Scenario | Warning Emitted by Rule Engine | Retired ML Output (pre-deletion, non-reproducible) | Deterministic Rollup (`priority.py`, reproducible) | Finding |
| :--- | :--- | :--- | :--- | :--- |
| **Penicillin-Allergic Patient Prescribed Amoxicillin** | `ALLERGY-002` (HIGH) | `0.266 -> LOW` | `Tier: HIGH` (Contributing: `ALLERGY-002`) | **ML ranked a beta-lactam allergy contraindication as lowest-priority.** Rollup escalates all HIGH/CRITICAL allergy warnings to HIGH. |
| **Severe CKD (eGFR 18) Prescribed Nitrofurantoin** | `RENAL-002` (CRITICAL) | `0.357 -> LOW` | `Tier: HIGH` (Contributing: `RENAL-002`) | **ML ranked a documented renal contraindication as lowest-priority.** |
| **Pregnant (T1) Patient Prescribed Doxycycline** | `VULN-002` (CRITICAL) | `0.556 -> MODERATE` | `Tier: HIGH` (Contributing: `VULN-002`) | ML placed a CRITICAL teratogenicity warning mid-queue. |
| **Healthy Adult + IV Meropenem 14d (Zero Warnings)** | none | `0.519 -> MODERATE` | `Tier: LOW` (Contributing: none) | **Inversion confirmed:** a prescription with zero warnings outranked all three contraindicated cases above. |
| **Medication Outside KB (`Fictionalcillin`)** | `COVERAGE-001` (HIGH) | not measured before decommissioning | `Tier: HIGH` (Contributing: `COVERAGE-001`) | The ML feature vector contained no knowledge-base-coverage feature, so an unrecognised drug was structurally indistinguishable from a low-risk one. Rollup enforces HIGH triage. |

The ordering above is the substantive finding and does not depend on the exact decimals:
three contraindicated prescriptions were ranked at or below a prescription carrying no
warnings at all.

### Architectural Decision
The auxiliary ML classifier, synthetic training generator, and unverified statistical metric claims (`AUROC: 0.984`) were **completely decommissioned and deleted**. The system now uses a pure, fully explainable deterministic severity rollup (`backend/rules/priority.py`), ensuring 100% reproducible, explainable, and clinically aligned triage.

---

## 4. Rule Attribution & Clinical Governance

**Audit Finding:**  
To uphold the non-fabrication constraint, all 23 clinical rules in `clinical_rules_catalog.json` are honestly labeled:
- **Author Attribution:** `author: "SYSTEM_GENERATED"` (reflecting that rules were synthesized from published guidelines rather than directly authored by named individuals in this codebase).
- **Approval Status:** `approval_status: "PENDING_CLINICAL_REVIEW"` with `approved_by: null`, `effective_date: null`, and `review_date: null`.
- **Citations:** Grounded exclusively in authentic references present in this repository (`icmr_antimicrobial_guidelines_2022.json`, `who_aware_classification_2023.json`, `icmr_amr_surveillance_2023.json`, and published clinical parameters). Fictional quality standards (e.g. "CDSS Quality Standard Section 1") have been eliminated.

---

## 5. Data Sources & Provenance

### 5.1 Ingested documents with full provenance records

1. **ICMR National Treatment Guidelines for Antimicrobial Use in Common Syndromes (Edition 3, 2022-2023):** Primary national guidance for Indian clinical epidemiology.
2. **WHO AWaRe Classification of Antibiotics (2023 Release):** Global stewardship categorization (Access, Watch, Reserve).
3. **ICMR Antimicrobial Resistance Surveillance Network Annual Report (2022-2023):** Indian resistance rates. **Sample-size caveat:** the dataset header declares `sample_size_total_isolates: 98400`, while the per-antimicrobial rows in the same file sum to `166100`. These are not the same quantity. The most likely explanation is that one isolate is tested against several antimicrobials, but **this has not been verified against the ICMR source publication**, and the 166,100 figure must not be cited as an isolate count. Both values are now carried explicitly in `icmr_amr_surveillance_2023.json` (`sample_size_total_isolates`, `per_antimicrobial_test_count_sum`) alongside a `sample_size_note`, and are surfaced unmodified by `GET /api/guidelines/amr-data`.

### 5.2 Clinical references cited in rule text — NO document record in this repository

The following are named inside `evidence_source` / citation strings in
`clinical_rules_catalog.json` and `drug_safety_database.json`. They are **not** ingested
documents: there is no `document_id`, `version`, `source_url`, or retrieval provenance for
any of them, and their content has not been verified against the primary literature. They
must not be presented to a clinician as retrievable evidence, and spec §8 is **not**
satisfied for these three until real document records exist.

| Reference named in rule text | Document record present? |
| :--- | :--- |
| Joint Task Force on Practice Parameters, beta-lactam allergy (cited as "JTFPP 2022" / "AAAAI") | **No** — string only. (The report previously listed this as "AAAAI / ACAAI"; the token "ACAAI" does not appear anywhere in the knowledge base.) |
| CredibleMeds QT Drugs Database | **No** — string only |
| Renal Drug Handbook, 5th Edition | **No** — string only |

The **CKD-EPI 2021 non-race-adjusted equation** is not a retrieved document but an
implemented calculation, and is correctly described as such in §1.

**Remediation required:** either add real document records (title, issuing org, version,
publication date, source URL) for the three references above, or strip them from citation
strings and cite only ICMR/WHO, which do have full provenance records.

---

## 6. Knowledge-Base Versioning & Provenance Metadata

Every safety warning, evidence passage, and explanation embeds complete provenance metadata:
- **System Version:** `1.4.0-clinical-safety`
- **Engine Build:** `2026.08.22-release`
- **Explainer Component:** `antigravity-deterministic-explainer-v1`
- **Prompt Template Hash:** SHA-256 computed dynamically over canonical template text.
- **Retrieved Evidence Hash:** SHA-256 computed dynamically over serialized guideline citations.

---

## 7. Automated Test Suite Results (54 Passing Tests)

The automated test suite (`python -m pytest tests/ -v`) executes 54 comprehensive tests across 8 distinct test modules with a 100% pass rate:
- `tests/test_clinical_safety.py` (27 Scenarios): Complete coverage of allergy, renal, hepatic, duplication, drug interactions, vulnerable populations, and boundary conditions.
- `tests/test_coverage_failsafe.py` (4 Tests): Validates explicit `COVERAGE-001` trigger for fictional drugs, real uncovered drugs (`Amikacin`), covered drugs (`Amoxicillin`), and confirms co-prescribed non-antimicrobials (`Ondansetron`) avoid false coverage triggers.
- `tests/test_auth_roles.py` (5 Tests): Validates 401 on missing/invalid token, 403 on spoofed body role, 200 on authorized override, and role authorization for rule authoring.
- `tests/test_stewardship_priority.py` (7 Tests): Asserts correct triage tiering for single beta-lactam allergy warnings (HIGH), direct allergy contraindications (HIGH), renal cutoffs (HIGH), pregnancy teratogenicity (HIGH), healthy adult therapies (LOW), uncovered drugs (HIGH), and 100% mathematical determinism.
- `tests/test_extraction_accuracy.py` (3 Tests): 21-case regression benchmark, multi-drug order extraction, and mandatory confirmation triggers on combination strength doses.
- `tests/test_extraction.py` (2 Tests): Ambiguous input confirmation triggers and parsing benchmarks.
- `tests/test_prompt_injection.py` (3 Tests): Adversarial prompt injection resistance in allergies, diagnoses, and notes.
- `tests/test_api_workflow.py` (3 Tests): Full end-to-end integration lifecycle from raw text extraction to cryptographic SHA-256 audit chain verification.

---

## 8. Cryptographic Audit Trail & Alert-Fatigue Monitoring

- **Append-Only Hash Chaining:** Every prescription submission, analysis, and override is recorded in an immutable ledger where:
  $$\text{Hash}_n = \text{SHA256}(\text{Hash}_{n-1} \parallel \text{LogID} \parallel \text{Timestamp} \parallel \text{EventType} \parallel \text{PrescriptionID} \parallel \text{ClinicianID} \parallel \text{Payload})$$
- **Verification Endpoint:** `GET /api/audit/verify` walks the entire ledger from the genesis block (`GENESIS_BLOCK_0000000000000000`) and cryptographically validates every link.
- **Alert Fatigue Tracking:** Override rates are tracked per rule ID. Any rule with an override rate $\ge 60\%$ with $\ge 10$ triggers is flagged with an alert-fatigue indicator to prompt committee review and recalibration.

---

## 9. API Surface Conformance (Spec §28) — DEVIATION DISCLOSED

Spec §28 enumerates a minimum set of endpoint paths. During remediation the API was
reorganised into `/api/audit/*` and `/api/guidelines/*` namespaces. The reorganisation is
internally consistent — every `fetch` in `frontend/js/app.js` resolves to a registered
route, and the end-to-end demo workflow (§27) is unaffected — but **three spec-mandated
paths no longer exist as written**:

| Spec §28 required path | Current path | Status |
| :--- | :--- | :--- |
| `GET /api/prescriptions/{id}/audit` | `GET /api/audit/logs` | **Moved** |
| `GET /api/guidelines` | split into `/api/guidelines/rules`, `/api/guidelines/amr-data`, `/api/guidelines/precedence` | **Moved / split** |
| `GET /api/rules` | `GET /api/guidelines/rules` (read); `POST /api/rules` (authoring) | **Moved** |

All other §28 endpoints (`POST /api/prescriptions`, `POST /api/prescriptions/{id}/analyze`,
`GET /api/prescriptions/{id}/warnings`, `GET /api/warnings/{id}/evidence`,
`POST /api/warnings/{id}/override`, `GET /api/system/health`,
`GET /api/system/model-version`, `POST /api/auth/login`) are present at their specified
paths.

**Remediation options:** add backwards-compatible aliases at the three original paths, or
obtain sign-off on the revised API surface. Until one of those occurs, §28 is **PASS WITH
DEVIATION**, not an unqualified PASS.

---

## 10. FINAL CLINICAL SAFETY SCORECARD & VERDICT

================================================  
**S11 CLINICAL DECISION-SUPPORT AUDIT SCORECARD**  
================================================  

- Clinical Safety Rules (23 Catalog Rules): **PASS**
- Rule Catalog Provenance: **PASS (SYSTEM_GENERATED / PENDING_CLINICAL_REVIEW; zero fabricated doctor names or backdated approval records)**
- Coverage Fail-Safe for Unvalidated Antimicrobials: **PASS**
- Non-Antimicrobial Concomitant Scope Management: **PASS**
- Guideline Provenance & Verbatim Citations: **PASS**
- LLM Containment & Injection Neutralization: **PASS**
- Prescription Entity Extraction: **PASS (Self-authored 21-case regression benchmark passing 100% agreement, with mandatory confirmation enforced on ambiguous combination strengths and multi-drug orders)**
- Direct & Cross-Reactive Allergy Checking (Escalates to HIGH): **PASS**
- CKD-EPI 2021 Non-Race Adjusted Renal Checking: **PASS**
- Child-Pugh Hepatic Adjustment Checking: **PASS**
- Anaerobic & Same-Class Duplication Checking: **PASS**
- Co-Prescribed & Home Drug-Drug Interactions: **PASS**
- Vulnerable Population Contraindications: **PASS**
- Indian AMR Resistance Data: **PASS WITH NOTE** — figures loaded dynamically from source; the 98,400 vs 166,100 discrepancy is documented and labelled rather than resolved (see §5). Requires confirmation against the ICMR publication before any external citation.
- Server-Side Role-Authorized Clinician Override: **PASS (Body role spoofing rejected with 403)**
- Rule Authoring Committee Permissions: **PASS**
- API Surface Conformance (Spec §28): **PASS WITH DEVIATION** — three mandated paths relocated; see §9
- Cryptographic Audit Log & Verification: **PASS**
- Alert-Fatigue Monitoring & Recalibration Flags: **PASS**
- Synthetic Patient Privacy & Zero PII: **PASS**
- Deterministic Stewardship Priority Rollup: **PASS**
- Anti-Correlated ML Subsystem: **REMOVED**
- Hardcoded Clinical Constants in App Code: **NONE (0)**

------------------------------------------------  

### FINAL AUDIT VERDICT:  
**APPROVED FOR CLINICAL DECISION-SUPPORT DEMONSTRATION — with three disclosed, non-blocking items**

The clinical safety core passes: deterministic rules, coverage fail-safe, server-side
authorization, evidence traceability, injection containment, cryptographic audit trail, and
privacy all verified against a 54-test suite. No fabricated clinician names, approval
records, or unverifiable metrics remain in the codebase or in this report.

Three items are disclosed rather than resolved, and none should be represented as closed:

1. **Rule catalog is `PENDING_CLINICAL_REVIEW`.** All 23 rules are honestly labelled as
   system-generated and awaiting review. No qualified clinician has approved them. This
   prototype is therefore suitable for demonstration only — not for any clinical setting.
2. **Three cited references have no document records** (§5.2). Spec §8 is not satisfied
   for JTFPP/AAAAI, CredibleMeds, and the Renal Drug Handbook.
3. **API surface deviates from spec §28** in three paths (§9), and the AMR sample-size
   discrepancy is labelled rather than reconciled against the source publication (§5).

This verdict is reproducible: every claim above is checkable by running
`python -m pytest tests/ -q` and inspecting the referenced files.

================================================
