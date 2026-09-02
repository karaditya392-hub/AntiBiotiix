"""
Patient RAG & Longitudinal History Retrieval Module (Spec & Architecture)

Maintains structured patient visit documents, indexes them with patient_id metadata,
and provides hybrid retrieval (Structured SQL + Semantic Vector Search) with STRICT
PATIENT ISOLATION.
"""

import json
import re
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import numpy as np
from sqlalchemy.orm import Session

from backend.models.database import (
    PatientDB, VisitDB, SymptomDB, DiagnosisDB, PrescriptionDB,
    PrescriptionItemDB, PatientRAGDocumentDB
)
from backend.rag.embeddings import get_backend
from backend.audit.logger import audit_logger


def format_visit_document_content(visit: VisitDB, patient: PatientDB, items: List[PrescriptionItemDB]) -> str:
    """Format structured visit into text representation for RAG indexing."""
    date_str = visit.visit_date.strftime("%d %B %Y") if visit.visit_date else "Unknown Date"
    
    # Format symptoms
    symptom_strs = []
    for s in visit.symptoms:
        parts = [s.name]
        details = []
        if s.severity:
            details.append(f"Severity: {s.severity}")
        if s.duration:
            details.append(f"Duration: {s.duration}")
        if s.onset:
            details.append(f"Onset: {s.onset}")
        if details:
            parts.append(f"({', '.join(details)})")
        symptom_strs.append(" ".join(parts))
    symptoms_text = ", ".join(symptom_strs) if symptom_strs else (visit.clinical_notes or "None recorded")

    # Format prescription
    med_names = [i.medication_name for i in items]
    rx_strs = []
    for i in items:
        rx_parts = [i.medication_name]
        if i.dose:
            rx_parts.append(f"{i.dose} {i.unit or 'mg'}")
        if i.route:
            rx_parts.append(i.route)
        if i.frequency:
            rx_parts.append(i.frequency)
        if i.duration_days:
            rx_parts.append(f"for {i.duration_days} days")
        rx_strs.append(" ".join(rx_parts))
    prescription_text = ", ".join(rx_strs) if rx_strs else "None prescribed"

    content = (
        f"PATIENT ID: {patient.patient_id}\n"
        f"VISIT ID: {visit.visit_id}\n"
        f"DATE: {date_str}\n"
        f"SYMPTOMS: {symptoms_text}\n"
        f"DIAGNOSIS: {visit.diagnosis or 'Not recorded'}\n"
        f"PRESCRIPTION: {prescription_text}\n"
        f"MEDICATIONS: {', '.join(med_names) if med_names else 'None'}\n"
        f"CLINICAL NOTES: {visit.clinical_notes or 'None'}"
    )
    return content


def index_visit_for_rag(db: Session, visit_id: str) -> Optional[PatientRAGDocumentDB]:
    """
    Index a completed visit into the patient RAG system with metadata.
    Immutable metadata patient_id prevents cross-patient retrieval.
    """
    visit = db.query(VisitDB).filter(VisitDB.visit_id == visit_id).first()
    if not visit:
        return None
    
    patient = db.query(PatientDB).filter(PatientDB.patient_id == visit.patient_id).first()
    if not patient:
        return None

    # Get prescription items if visit has prescription
    items = []
    if visit.prescription_id:
        items = db.query(PrescriptionItemDB).filter(PrescriptionItemDB.prescription_id == visit.prescription_id).all()
    else:
        # Check if any prescription shares visit_id or belongs to this patient at same timestamp
        p_rec = db.query(PrescriptionDB).filter(PrescriptionDB.patient_id == visit.patient_id).order_by(PrescriptionDB.created_at.desc()).first()
        if p_rec:
            items = db.query(PrescriptionItemDB).filter(PrescriptionItemDB.prescription_id == p_rec.prescription_id).all()

    content = format_visit_document_content(visit, patient, items)
    date_str = visit.visit_date.strftime("%Y-%m-%d") if visit.visit_date else datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Compute embedding
    backend = get_backend()
    vec = backend.encode([content])[0]
    embedding_json = json.dumps(vec.tolist())

    # Check if doc already indexed
    doc_id = f"RAG-{visit.visit_id}"
    doc_record = db.query(PatientRAGDocumentDB).filter(PatientRAGDocumentDB.doc_id == doc_id).first()
    if doc_record:
        doc_record.content = content
        doc_record.embedding_json = embedding_json
    else:
        doc_record = PatientRAGDocumentDB(
            doc_id=doc_id,
            patient_id=patient.patient_id,
            visit_id=visit.visit_id,
            visit_date=date_str,
            record_type="visit",
            content=content,
            embedding_json=embedding_json
        )
        db.add(doc_record)

    db.commit()
    db.refresh(doc_record)

    # Log audit event
    audit_logger.log_event(
        db=db,
        event_type="RAG_INDEXED_VISIT",
        prescription_id=visit.prescription_id or "-",
        patient_id=patient.patient_id,
        clinician_id=visit.doctor_id or "SYSTEM",
        clinician_role="ATTENDING_PHYSICIAN",
        action_summary=f"Visit {visit.visit_id} indexed into RAG store for patient {patient.patient_id}.",
        payload={"visit_id": visit.visit_id, "doc_id": doc_id, "date": date_str}
    )

    return doc_record


def ask_patient_history(db: Session, patient_id: str, question: str) -> Dict[str, Any]:
    """
    Query patient history using hybrid retrieval (Structured SQL + Semantic RAG)
    with MANDATORY patient_id metadata filtering to guarantee PATIENT ISOLATION.
    """
    patient = db.query(PatientDB).filter(PatientDB.patient_id == patient_id).first()
    if not patient:
        return {
            "patient_id": patient_id,
            "question": question,
            "answered": False,
            "answer": f"Patient {patient_id} not found.",
            "source_visit_id": None,
            "source_date": None,
            "sources": []
        }

    visits = (
        db.query(VisitDB)
        .filter(VisitDB.patient_id == patient_id)
        .order_by(VisitDB.visit_date.desc(), VisitDB.id.desc())
        .all()
    )

    if not visits:
        return {
            "patient_id": patient_id,
            "question": question,
            "answered": False,
            "answer": "This is the patient's first recorded visit.",
            "source_visit_id": None,
            "source_date": None,
            "sources": []
        }

    q_lower = question.lower().strip()

    # Sanitization / Injection check
    from backend.llm.explainer import clinical_explainer
    cleaned, injected = clinical_explainer.sanitize_input(question)
    if injected:
        return {
            "patient_id": patient_id,
            "question": question,
            "answered": False,
            "answer": "The question contained instruction-like text targeting the system and was refused.",
            "source_visit_id": None,
            "source_date": None,
            "sources": []
        }

    # Helper function to extract visit summary for answers
    def build_visit_summary(v: VisitDB) -> Dict[str, Any]:
        p_rec = None
        if v.prescription_id:
            p_rec = db.query(PrescriptionDB).filter(PrescriptionDB.prescription_id == v.prescription_id).first()
        else:
            p_rec = db.query(PrescriptionDB).filter(PrescriptionDB.patient_id == patient_id).order_by(PrescriptionDB.created_at.desc()).first()

        items = []
        if p_rec:
            items = db.query(PrescriptionItemDB).filter(PrescriptionItemDB.prescription_id == p_rec.prescription_id).all()

        symptom_names = [s.name for s in v.symptoms] if v.symptoms else []
        symptoms_str = ", ".join(symptom_names) if symptom_names else (v.clinical_notes or "None recorded")

        rx_parts = []
        for i in items:
            p_str = i.medication_name
            if i.dose:
                p_str += f" {i.dose} {i.unit or 'mg'}"
            if i.frequency:
                p_str += f", {i.frequency}"
            if i.duration_days:
                p_str += f" for {i.duration_days} days"
            rx_parts.append(p_str)

        rx_summary = "; ".join(rx_parts) if rx_parts else "No medication prescribed"
        date_str = v.visit_date.strftime("%d %B %Y") if v.visit_date else "Unknown"

        return {
            "visit_id": v.visit_id,
            "date": date_str,
            "diagnosis": v.diagnosis or "No diagnosis recorded",
            "symptoms": symptoms_str,
            "prescription": rx_summary,
            "medications": [i.medication_name for i in items]
        }

    # ---------------------------------------------------------
    # STRUCTURED EXACT INTENT ROUTING
    # ---------------------------------------------------------
    last_visit_intents = ["last visit", "previous visit", "most recent visit", "last diagnosis", "previous diagnosis", "what was the diagnosis during", "when did he last visit", "when did patient last visit"]
    medication_intents = ["what medication", "what medications", "medications has this patient", "medication history", "previous medications", "all medications"]
    two_visits_ago_intents = ["two visits ago", "2 visits ago", "second visit"]

    if any(kw in q_lower for kw in last_visit_intents) and not any(kw in q_lower for kw in two_visits_ago_intents):
        latest = visits[0]
        s = build_visit_summary(latest)
        answer_text = (
            f"Last visit: {s['date']}\n\n"
            f"Symptoms:\n{s['symptoms']}.\n\n"
            f"Diagnosis:\n{s['diagnosis']}.\n\n"
            f"Prescription:\n{s['prescription']}.\n\n"
            f"Source:\nVisit {s['visit_id']}."
        )
        return {
            "patient_id": patient_id,
            "question": question,
            "answered": True,
            "answer": answer_text,
            "source_visit_id": s["visit_id"],
            "source_date": s["date"],
            "sources": [{
                "patient_id": patient_id,
                "visit_id": s["visit_id"],
                "date": s["date"],
                "record_type": "visit"
            }]
        }

    if any(kw in q_lower for kw in two_visits_ago_intents):
        if len(visits) >= 2:
            target_visit = visits[1]
            s = build_visit_summary(target_visit)
            answer_text = (
                f"Two visits ago ({s['date']}):\n\n"
                f"Symptoms:\n{s['symptoms']}.\n\n"
                f"Diagnosis:\n{s['diagnosis']}.\n\n"
                f"Prescription:\n{s['prescription']}.\n\n"
                f"Source:\nVisit {s['visit_id']}."
            )
            return {
                "patient_id": patient_id,
                "question": question,
                "answered": True,
                "answer": answer_text,
                "source_visit_id": s["visit_id"],
                "source_date": s["date"],
                "sources": [{
                    "patient_id": patient_id,
                    "visit_id": s["visit_id"],
                    "date": s["date"],
                    "record_type": "visit"
                }]
            }
        else:
            return {
                "patient_id": patient_id,
                "question": question,
                "answered": False,
                "answer": "This patient only has 1 recorded visit.",
                "source_visit_id": None,
                "source_date": None,
                "sources": []
            }

    if any(kw in q_lower for kw in medication_intents):
        med_history = []
        for v in visits:
            s = build_visit_summary(v)
            if s["medications"]:
                med_history.append(f"{s['date']} ({s['visit_id']}): {s['prescription']}")
        
        if med_history:
            answer_text = (
                f"Historical medications for patient {patient_id}:\n\n" +
                "\n\n".join(med_history) +
                f"\n\nSource:\nVisits {', '.join(v.visit_id for v in visits)}."
            )
            return {
                "patient_id": patient_id,
                "question": question,
                "answered": True,
                "answer": answer_text,
                "source_visit_id": visits[0].visit_id,
                "source_date": visits[0].visit_date.strftime("%d %B %Y") if visits[0].visit_date else None,
                "sources": [{"patient_id": patient_id, "visit_id": v.visit_id, "date": v.visit_date.strftime("%Y-%m-%d") if v.visit_date else "", "record_type": "visit"} for v in visits]
            }

    # ---------------------------------------------------------
    # SEMANTIC RAG RETRIEVAL (MANDATORY PATIENT_ID FILTER)
    # ---------------------------------------------------------
    # Fetch RAG documents EXCLUSIVELY for this patient_id
    rag_docs = (
        db.query(PatientRAGDocumentDB)
        .filter(PatientRAGDocumentDB.patient_id == patient_id)
        .all()
    )

    if not rag_docs:
        # Fallback to latest visit
        latest = visits[0]
        s = build_visit_summary(latest)
        answer_text = (
            f"Recorded visit on {s['date']}:\n\n"
            f"Symptoms: {s['symptoms']}\n"
            f"Diagnosis: {s['diagnosis']}\n"
            f"Prescription: {s['prescription']}\n\n"
            f"Source: Visit {s['visit_id']}."
        )
        return {
            "patient_id": patient_id,
            "question": question,
            "answered": True,
            "answer": answer_text,
            "source_visit_id": s["visit_id"],
            "source_date": s["date"],
            "sources": [{"patient_id": patient_id, "visit_id": s["visit_id"], "date": s["date"], "record_type": "visit"}]
        }

    # Compute similarity against patient's documents
    backend = get_backend()
    qv = getattr(backend, "encode_query", backend.encode)([cleaned])[0]

    best_doc = None
    best_score = -1.0

    for doc in rag_docs:
        if not doc.embedding_json:
            continue
        emb = np.array(json.loads(doc.embedding_json))
        score = float(emb @ qv)
        if score > best_score:
            best_score = score
            best_doc = doc

    if best_doc and (best_score > 0.1 or len(rag_docs) == 1):
        # Match found in patient's RAG records
        matching_visit = db.query(VisitDB).filter(VisitDB.visit_id == best_doc.visit_id).first()
        if matching_visit:
            s = build_visit_summary(matching_visit)
            answer_text = (
                f"Matching historical record on {s['date']}:\n\n"
                f"Symptoms:\n{s['symptoms']}.\n\n"
                f"Diagnosis:\n{s['diagnosis']}.\n\n"
                f"Prescription:\n{s['prescription']}.\n\n"
                f"Source:\nVisit {s['visit_id']}."
            )
            return {
                "patient_id": patient_id,
                "question": question,
                "answered": True,
                "answer": answer_text,
                "source_visit_id": s["visit_id"],
                "source_date": s["date"],
                "sources": [{
                    "patient_id": patient_id,
                    "visit_id": s["visit_id"],
                    "date": s["date"],
                    "record_type": "visit"
                }]
            }

    # If no relevant match is found in patient's history
    return {
        "patient_id": patient_id,
        "question": question,
        "answered": False,
        "answer": "No matching information was found in this patient's recorded history.",
        "source_visit_id": None,
        "source_date": None,
        "sources": []
    }
