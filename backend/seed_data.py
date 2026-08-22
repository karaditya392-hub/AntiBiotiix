"""
Seed Database with Synthetic De-Identified Patients and Rules (Sections 24, 25)
Zero real patient PII - 100% synthetic clinical simulation scenarios.
"""
import json
from datetime import datetime, timezone
from backend.models.database import (
    SessionLocal, init_db, PatientDB, ClinicalRuleDB, 
    GuidelineDocumentDB, AMRSurveillanceDB, AlertMetricsDB
)
from backend.guidelines.knowledge_base import knowledge_base


def seed_database():
    init_db()
    db = SessionLocal()
    
    # 1. Seed Synthetic Patients
    patients_data = [
        {
            "patient_id": "PATIENT-001",
            "age": 45,
            "age_category": "ADULT",
            "weight_kg": 72.0,
            "sex": "MALE",
            "allergies_json": json.dumps(["Penicillin", "Amoxicillin"]),
            "allergy_status_known": True,
            "egfr_ml_min": 92.0,
            "serum_creatinine_mg_dl": 0.9,
            "renal_status_known": True,
            "child_pugh_class": None,
            "hepatic_status_known": True,
            "pregnancy_status": "CONFIRMED_NOT_PREGNANT",
            "lactation_status": "CONFIRMED_NOT_LACTATING",
            "active_medications_json": json.dumps(["Pantoprazole 40mg PO QD"]),
            "clinical_notes": "45yo male presenting with fever, cough, and right lower lobe consolidation consistent with CAP. Documented penicillin anaphylaxis 5 years ago."
        },
        {
            "patient_id": "PATIENT-002",
            "age": 68,
            "age_category": "GERIATRIC",
            "weight_kg": 64.0,
            "sex": "FEMALE",
            "allergies_json": json.dumps([]),
            "allergy_status_known": True,
            "egfr_ml_min": 22.0,
            "serum_creatinine_mg_dl": 2.8,
            "renal_status_known": True,
            "child_pugh_class": None,
            "hepatic_status_known": True,
            "pregnancy_status": "CONFIRMED_NOT_PREGNANT",
            "lactation_status": "CONFIRMED_NOT_LACTATING",
            "active_medications_json": json.dumps(["Amlodipine 5mg PO QD", "Torsemide 10mg PO QD"]),
            "clinical_notes": "68yo female with CKD Stage 4 (eGFR 22 mL/min via CKD-EPI 2021 non-race formula) presenting with dysuria, frequency, and suspected cystitis."
        },
        {
            "patient_id": "PATIENT-003",
            "age": 54,
            "age_category": "ADULT",
            "weight_kg": 78.0,
            "sex": "MALE",
            "allergies_json": json.dumps([]),
            "allergy_status_known": True,
            "egfr_ml_min": 75.0,
            "serum_creatinine_mg_dl": 1.1,
            "renal_status_known": True,
            "child_pugh_class": "Child-Pugh C",
            "hepatic_status_known": True,
            "pregnancy_status": "CONFIRMED_NOT_PREGNANT",
            "lactation_status": "CONFIRMED_NOT_LACTATING",
            "active_medications_json": json.dumps(["Furosemide 40mg PO QD", "Spironolactone 100mg PO QD", "Lactulose 30mL PO TID"]),
            "clinical_notes": "54yo male with decompensated alcoholic cirrhosis (Child-Pugh C, ascites, jaundice) presenting with abdominal pain and suspected spontaneous bacterial peritonitis."
        },
        {
            "patient_id": "PATIENT-004",
            "age": 28,
            "age_category": "ADULT",
            "weight_kg": 62.0,
            "sex": "FEMALE",
            "allergies_json": json.dumps([]),
            "allergy_status_known": True,
            "egfr_ml_min": 110.0,
            "serum_creatinine_mg_dl": 0.6,
            "renal_status_known": True,
            "child_pugh_class": None,
            "hepatic_status_known": True,
            "pregnancy_status": "PREGNANT_TRIMESTER_2",
            "lactation_status": "CONFIRMED_NOT_LACTATING",
            "active_medications_json": json.dumps(["Prenatal Multivitamin", "Iron Folic Acid"]),
            "clinical_notes": "28yo female G2P1 at 24 weeks gestation presenting with acute dysuria and flank discomfort."
        },
        {
            "patient_id": "PATIENT-005",
            "age": 62,
            "age_category": "ADULT",
            "weight_kg": 85.0,
            "sex": "MALE",
            "allergies_json": json.dumps([]),
            "allergy_status_known": True,
            "egfr_ml_min": 82.0,
            "serum_creatinine_mg_dl": 1.0,
            "renal_status_known": True,
            "child_pugh_class": None,
            "hepatic_status_known": True,
            "pregnancy_status": "CONFIRMED_NOT_PREGNANT",
            "lactation_status": "CONFIRMED_NOT_LACTATING",
            "active_medications_json": json.dumps(["Warfarin 5mg PO QD", "Atorvastatin 40mg PO QHS", "Metoprolol 50mg PO BID"]),
            "clinical_notes": "62yo male with mechanical mitral valve on Warfarin (baseline INR 2.5) and hyperlipidemia on Atorvastatin presenting with acute cough and purulent sputum."
        },
        {
            "patient_id": "PATIENT-006",
            "age": 4,
            "age_category": "PEDIATRIC",
            "weight_kg": 16.0,
            "sex": "MALE",
            "allergies_json": json.dumps([]),
            "allergy_status_known": True,
            "egfr_ml_min": 115.0,
            "serum_creatinine_mg_dl": 0.4,
            "renal_status_known": True,
            "child_pugh_class": None,
            "hepatic_status_known": True,
            "pregnancy_status": "CONFIRMED_NOT_PREGNANT",
            "lactation_status": "CONFIRMED_NOT_LACTATING",
            "active_medications_json": json.dumps([]),
            "clinical_notes": "4yo pediatric male (weight 16kg) presenting with acute otitis media and high fever. Requires weight-based dosing review."
        },
        {
            "patient_id": "PATIENT-007",
            "age": 72,
            "age_category": "GERIATRIC",
            "weight_kg": 58.0,
            "sex": "FEMALE",
            "allergies_json": json.dumps([]),
            "allergy_status_known": True,
            "egfr_ml_min": 55.0,
            "serum_creatinine_mg_dl": 1.1,
            "renal_status_known": True,
            "child_pugh_class": None,
            "hepatic_status_known": True,
            "pregnancy_status": "CONFIRMED_NOT_PREGNANT",
            "lactation_status": "CONFIRMED_NOT_LACTATING",
            "active_medications_json": json.dumps(["Ondansetron 8mg PO TID", "Amiodarone 200mg PO QD"]),
            "clinical_notes": "72yo female receiving chemotherapy on Ondansetron and Amiodarone for atrial fibrillation. High cardiac QTc prolongation risk profile."
        },
        {
            "patient_id": "PATIENT-008",
            "age": 35,
            "age_category": "ADULT",
            "weight_kg": 70.0,
            "sex": "MALE",
            "allergies_json": json.dumps([]),
            "allergy_status_known": True,
            "egfr_ml_min": 98.0,
            "serum_creatinine_mg_dl": 0.8,
            "renal_status_known": True,
            "child_pugh_class": None,
            "hepatic_status_known": True,
            "pregnancy_status": "CONFIRMED_NOT_PREGNANT",
            "lactation_status": "CONFIRMED_NOT_LACTATING",
            "active_medications_json": json.dumps(["Escitalopram 20mg PO QD", "Clonazepam 0.5mg PO PRN"]),
            "clinical_notes": "35yo male with severe depression on Escitalopram 20mg presenting with extensive MRSA skin and soft tissue abscess."
        },
        {
            "patient_id": "PATIENT-009",
            "age": 50,
            "age_category": "ADULT",
            "weight_kg": 75.0,
            "sex": "MALE",
            "allergies_json": json.dumps([]),
            "allergy_status_known": False,  # Missing allergy info
            "egfr_ml_min": None,           # Missing renal info
            "serum_creatinine_mg_dl": None,
            "renal_status_known": False,
            "child_pugh_class": None,
            "hepatic_status_known": False,
            "pregnancy_status": "CONFIRMED_NOT_PREGNANT",
            "lactation_status": "CONFIRMED_NOT_LACTATING",
            "active_medications_json": json.dumps([]),
            "clinical_notes": "50yo male newly admitted emergency patient. Allergy and renal lab records unavailable."
        },
        {
            "patient_id": "PATIENT-010",
            "age": 29,
            "age_category": "ADULT",
            "weight_kg": 55.0,
            "sex": "FEMALE",
            "allergies_json": json.dumps([]),
            "allergy_status_known": True,
            "egfr_ml_min": 95.0,
            "serum_creatinine_mg_dl": 0.7,
            "renal_status_known": True,
            "child_pugh_class": None,
            "hepatic_status_known": True,
            "pregnancy_status": "UNKNOWN",  # Unknown pregnancy status in female of childbearing age
            "lactation_status": "UNKNOWN",
            "active_medications_json": json.dumps([]),
            "clinical_notes": "29yo female presenting with acute sinusitis. Pregnancy test not yet performed."
        }
    ]

    for p_data in patients_data:
        existing = db.query(PatientDB).filter(PatientDB.patient_id == p_data["patient_id"]).first()
        if not existing:
            patient = PatientDB(**p_data)
            db.add(patient)

    # 2. Seed Clinical Rules
    for r in knowledge_base.rules_catalog:
        existing_r = db.query(ClinicalRuleDB).filter(ClinicalRuleDB.rule_id == r["rule_id"]).first()
        if not existing_r:
            rule_obj = ClinicalRuleDB(
                rule_id=r["rule_id"],
                rule_name=r["rule_name"],
                category=r["category"],
                severity=r["severity"],
                description=r["description"],
                input_conditions_json=json.dumps(r.get("input_conditions", "")),
                output_concern=r["output_concern"],
                recommendation=r["recommendation"],
                evidence_source=r["evidence_source"],
                guideline_version=r["guideline_version"],
                effective_date=r["effective_date"],
                review_date=r["review_date"],
                author=r["author"],
                approval_status=r["approval_status"],
                approved_by=r.get("approved_by"),
                source_url=r.get("source_url"),
                section_page=r.get("section_page")
            )
            db.add(rule_obj)

    # 3. Seed AMR Surveillance Records
    amr_list = knowledge_base.amr_data.get("antibiogram", [])
    for idx, row in enumerate(amr_list, 1):
        rec_id = f"AMR-ICMR-{idx:03d}"
        existing_amr = db.query(AMRSurveillanceDB).filter(AMRSurveillanceDB.record_id == rec_id).first()
        if not existing_amr:
            amr_obj = AMRSurveillanceDB(
                record_id=rec_id,
                organism=row["organism"],
                antimicrobial=row["antimicrobial"],
                resistance_rate_pct=row["resistance_rate_pct"],
                sample_size=row.get("sample_size", 10000),
                geographic_scope="India - ICMR AMR Network",
                data_source="ICMR AMR Surveillance Report 2022-2023",
                reporting_year=2023
            )
            db.add(amr_obj)

    # 4. Seed Alert Metrics Baseline
    for r in knowledge_base.rules_catalog:
        m = db.query(AlertMetricsDB).filter(AlertMetricsDB.rule_id == r["rule_id"]).first()
        if not m:
            db.add(AlertMetricsDB(
                rule_id=r["rule_id"],
                total_triggered=0,
                total_overridden=0,
                total_accepted=0
            ))

    db.commit()
    db.close()
    print("Database successfully seeded with 10 synthetic patients, clinical rules, and AMR data.")


if __name__ == "__main__":
    seed_database()
