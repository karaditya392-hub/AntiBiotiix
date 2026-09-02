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
   - **A second national antimicrobial authority:** the **NCDC National Treatment Guidelines
     for Antimicrobial Use in Infectious Diseases, Version 1.0 (2016)** (`NCDC-NTG-AMR-2016`),
     whose syndromic empirical-therapy chapter spans GI/intra-abdominal, CNS, cardiovascular,
     SSTI, respiratory, urinary, obstetric, bone-and-joint and eye infections. It sits at
     national rank alongside ICMR, from a different issuing body. **Neither supersedes the
     other and this system does not adjudicate between them** — where they differ, the
     difference is surfaced and its clinical resolution is the reader's. No clinical rule
     cites it; ingesting it added evidence, not rule behaviour.
   - **Retrieval corpus: 94 documents, 15,894 verbatim chunks.** Alongside ICMR and WHO it
     holds 12 MoHFW/NHSRC Standard Treatment Guidelines, 16 national programme documents
     (NCDC, NVBDCP, NLEP, NACO/MoHFW, NPCDCS, NPPMBI, plus one unattributed Ayurvedic file),
     and 55 ICMR national documents (`scripts/ingest_icmr_national_corpus.py`).
     Every document records in its provenance notes **which kind of antimicrobial content it
     carries** — empirical antibacterial therapy, antimalarial policy, antiviral therapy,
     rabies prophylaxis, programme-set leprosy MDT, or none — because those are different
     answers and none of them except the first is a basis for antibacterial selection. Those
     that carry antibacterial recommendations name what governs when they differ from a
     national antimicrobial guideline or the local antibiogram.
   - **Document count is not a measure of antimicrobial coverage, and the corpus says so.**
     Of the 94 documents held, **11 are antimicrobial sources**; the rest are 54
     condition-specific clinical documents, 14 research-ethics guidelines, 6 programme and
     institutional policies, 4 laboratory and biosafety documents, 3 public-information files
     and 2 research-activity reports. Every document therefore declares a **`clinical_domain`**
     alongside its precedence rank, because rank says how much weight a document carries in a
     clinical conflict and cannot say *what it is authoritative about*. Each domain carries a
     reading contract that travels with every retrieved passage, and a retrieval result in
     which nothing carries antimicrobial authority says so in as many words. Agent
     comparison in `cross_source` is restricted to
     `config.ANTIMICROBIAL_CONTENT_DOCUMENT_IDS` — an explicit, auditable set — so that an
     oncology consensus document that does not mention piperacillin is never counted as a
     national guideline omitting it.
   - **Provenance is recorded as found, not as preferred.** Ten documents declare themselves
     undated rather than borrowing a year from a file name; the diabetic foot document
     declares itself a draft; two declare their attribution inferred rather than printed; the
     leprosy rehabilitation guideline discloses the commercial sponsor acknowledged in its own
     text. Three documents that are **not clinical guidelines** — a community mass-drug-
     administration leaflet, a 2006 public fact sheet, and an unattributed Ayurvedic
     compilation — are held at **precedence rank 4 (`NOT_A_CLINICAL_GUIDELINE`)** so they
     cannot sort alongside ICMR and NCDC, and so are the 26 ICMR ethics, laboratory, policy
     and research-report documents. Ingested by `scripts/ingest_mohfw_stg.py`,
     `scripts/ingest_national_guidelines.py` and `scripts/ingest_icmr_national_corpus.py`,
     which are the reproducibility record for what was claimed about each file.
   - **Four supplied files were not ingested, and the omission is recorded rather than
     silent.** Three are scanned images with no extractable text and one has 55 empty pages
     of 56; ingesting the last would have let the corpus report that it holds a guideline
     while holding one page of its foreword. Two further supplied files were this system's
     own generated patient prescription records — not guidelines, and never admissible to a
     corpus that answers clinical questions. All six exclusions are listed with their reasons
     at the top of `scripts/ingest_icmr_national_corpus.py`.
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

## 🤖 The Two Agent Pipelines

Both are visualised node by node at **Clinical Tools → Agent Console**
(`/#/clinical-tools/agents`). The diagram is not drawn in the frontend — it is
served from `/api/agents/graph`, declared beside the code that executes it in
`backend/agents/trace.py`, so it cannot drift from the pipeline it describes.
Every run returns a trace keyed by the same node ids, and a node that did not run
shows as **skipped with its reason**.

### Ingestion — `backend/agents/ingestion.py`

```
receive → convert to Markdown → extract → validate (guardrails) → LLM review
        → classify & rank → chunk → embed & index → Markdown returned
```

- **Markdown first, and it is not cosmetic.** Flat text extraction destroys the
  structure that gives a clinical statement its meaning: a dose detached from its
  table column is a dose attached to the wrong patient. `markdown_convert.py`
  recovers headings by font size and tables as pipe tables; `chunk_markdown` then
  cuts on that structure, never splits a table, and carries the enclosing heading
  and PDF page on every chunk.
- **Validation is a gate, not an annotation** (`backend/agents/validation.py`).
  Seven deterministic rules — content volume, injection, patient identifiers,
  encoding, structure, issuer, blank-form — run with no network and no key. A
  blocking failure ends the run before any model is consulted. The LLM review that
  follows **may only reject**: it can never clear a document a rule blocked and
  never raises a document's standing. The input is an arbitrary uploaded file, so a
  model whose approval carried weight would be a model the file could argue with.
- **The Markdown comes back** at `/api/agents/documents/{id}/markdown`, with
  provenance front matter. Everything downstream is derived from it, so it is the
  only way anyone can check that what was indexed is what the document said.
- **Rank is still granted, never claimed.** Rank 1 (local antibiogram) outranks
  the national guidelines, so it needs an attesting clinician role *and* the
  agent's own reading to agree. Disagreement falls to rank 4 and is recorded.

### Search — `backend/agents/pipeline.py`

```
question → refusal guards → PARALLEL FAN-OUT ─┬─ vector DB search ──────────┐
                                              └─ web search → LLM filter ───┤
                                                                            ▼
                            JSON render contract ← structured output ← couple & ground
```

- **The fan-out is genuinely parallel.** Both branches are I/O-bound and
  independent, so they run on separate threads; the wall clock is the slower
  branch, not the sum. A branch that fails or exceeds `SEARCH_PARALLEL_TIMEOUT_S`
  is reported as degraded and the pipeline proceeds without it — losing web
  evidence degrades an answer, losing corpus evidence would be a fault.
- **Parallelism changed when work happens, not what may be said.** Web results
  still pass the authenticity filter, still enter at precedence rank 5, and still
  cannot ground an antimicrobial recommendation alone.
- **The filter's refusals are rendered, not logged.** Every verdict — accepted and
  rejected, with its reason and score — reaches the client. A filter whose
  refusals are invisible cannot be reviewed.
- **The response is a render contract** (`backend/agents/render.py`,
  `schema: antibiotix.search.render/1`): sections, citations grouped by authority
  tier, per-source counts, filtration verdicts and the trace. Assembled
  deterministically, with each passage's origin label and reading caveat already
  attached — a client renders what it is given rather than deriving what to show,
  because the origin label is the first thing dropped when a layout is tight.

The same vector database serves both: a document ingested by the first pipeline is
retrievable by the second, by `/api/evidence/ask` citation search, and by the RAG
chat, from the moment it is indexed.

**The boundary neither pipeline crosses:** `backend/rules/engine.py` imports
nothing from `backend/agents`. Every deterministic safety warning fires with this
entire layer absent, the network down and no API key configured.

---

## 🚀 Quick Start & Running Locally

### 1. Requirements
- Python 3.10+
- Dependencies: `fastapi`, `uvicorn`, `sqlalchemy`, `pydantic`, `pytest`, `httpx`, `pymupdf`
- Modern Web Browser (Chrome, Edge, Firefox, Safari)

### 1a. Configure — one file, `.env` at the repository root

Copy `.env.example` to `.env`. **Every endpoint, key, model id and threshold the
system uses is read from that one file**, through `backend/config.py`, which is
the only module that reads the environment. Nothing calls `os.getenv()` at its own
call site — a key read where it is used is a key nobody can find later, and an
endpoint that differs between two modules is an outage that only appears in
production. A real environment variable always wins over the file, so container
and CI secrets are never overridden by a checked-out `.env`.

| Setting | What it governs |
| --- | --- |
| `NVIDIA_API_KEY`, `NVIDIA_BASE_URL`, `AGENT_LLM_MODEL` | Every LLM call: validation, classification, web filtration, structured output |
| `AGENT_LLM_FALLBACK_MODELS`, `AGENT_LLM_TIMEOUT_S`, `AGENT_LLM_TEMPERATURE` | Capacity fallback, timeout, determinism |
| `AGENT_LLM_MAX_TOKENS`, `AGENT_LLM_MAX_TOKENS_CEILING` | Completion budget — **covers the model's reasoning as well as its answer** |
| `EMBEDDING_BACKEND`, `EMBEDDING_MODEL`, `NVIDIA_EMBEDDING_MODEL` | Retrieval embeddings (changing these requires a migration) |
| `DATABASE_URL` | Persistence; empty = the SQLite file beside the repository |
| `WEB_SEARCH_*`, `WEB_FILTER_ACCEPT_THRESHOLD` | The web evidence path and its acceptance floor |
| `SEARCH_PARALLEL_TIMEOUT_S`, `SEARCH_MAX_PASSAGES` | The parallel fan-out |
| `MARKDOWN_OUTPUT_DIR`, `MARKDOWN_MAX_PAGES` | Where converted Markdown is written, and the page cap |
| `INGEST_VALIDATION_*` | Validation sample size, confidence floor, and strict mode |

**The system runs with this file absent.** No key means: web evidence off, the
filtration agent refuses every result rather than admitting unassessed sources,
ingestion runs its seven structural rules alone and says so, and search returns
retrieved passages verbatim instead of a composed answer. All clinical safety
rules fire exactly as they do today — they never read anything in this file.

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
- `tests/test_markdown_pipeline.py`: Markdown conversion (headings, tables that are never split, page anchors that never reach a reader) and the ingestion guardrails — including that a model may reject a document but never approve one.
- `tests/test_search_pipeline.py`: The parallel fan-out (asserted by wall clock), branch failure and timeout degradation, the refusals that parallelism must not have removed, and the render contract's authority tiers.

---

## 📊 Audit Report

The complete 30-section audit report is available at:  
[`backend/audit/clinical_ml_audit_report.md`](file:///c:/Users/iraba/OneDrive/Desktop/Microbe/backend/audit/clinical_ml_audit_report.md)
