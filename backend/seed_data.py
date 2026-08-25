"""
Seed Database with Synthetic De-Identified Patients and Rules (Sections 24, 25)
Zero real patient PII - 100% synthetic clinical simulation scenarios.

Teaching roster lives in SEED_ROSTER. Each entry is one unique patient with a
unique allergy set, diagnosis, initial prescription, and quick-scenario
preset. To add a new demo patient, append one dict to SEED_ROSTER — patient
row, seed visit, and console preset are derived from that single list.
"""
import argparse
import json
from backend.models.database import (
    SessionLocal, init_db, PatientDB, PrescriptionDB, PrescriptionItemDB,
    SafetyWarningDB, ClinicianOverrideDB, AuditLogDB, ClinicalRuleDB,
    GuidelineDocumentDB, AMRSurveillanceDB, AlertMetricsDB,
    VisitDB, SymptomDB, DiagnosisDB, PatientRAGDocumentDB
)
from backend.guidelines.knowledge_base import knowledge_base


# Append new demo patients here. Each patient_id, allergy list, diagnosis, prescription medication, and
# scenario key/label must be unique across the roster. Include a scenario
# block so the console gets a matching quick-preset chip.
SEED_ROSTER = [
    {
        "patient_id": "PATIENT-001",
        "display_name": "PATIENT-001 (Rajesh Sharma)",
        "age": 45, "age_category": "ADULT", "weight_kg": 72.0, "sex": "MALE",
        "allergies": ["Penicillin", "Amoxicillin"], "allergy_status_known": True,
        "egfr_ml_min": 92.0, "serum_creatinine_mg_dl": 0.9, "renal_status_known": True,
        "child_pugh_class": None, "hepatic_status_known": True,
        "pregnancy_status": "CONFIRMED_NOT_PREGNANT", "lactation_status": "CONFIRMED_NOT_LACTATING",
        "active_medications": ["Pantoprazole 40mg PO QD"],
        "clinical_notes": "45yo male presenting with fever, cough, and right lower lobe consolidation consistent with CAP. Documented penicillin anaphylaxis 5 years ago.",
        "diagnosis": "Community-acquired pneumonia",
        "prescription": ("Azithromycin", 500, "mg", "PO", "QD", 3),
        "scenario": {
            "key": "cap-amox-pen-allergy",
            "label": "Rajesh Sharma (PATIENT-001) - CAP: Amox in Penicillin Allergy",
            "diagnosis": "Community-Acquired Pneumonia (CAP)",
            "text": "Amoxicillin 500mg PO TID x 7 days for community acquired pneumonia",
        },
    },
    {
        "patient_id": "PATIENT-002",
        "display_name": "PATIENT-002 (Sunita Devi)",
        "age": 68, "age_category": "GERIATRIC", "weight_kg": 64.0, "sex": "FEMALE",
        "allergies": ["Sulfonamides"], "allergy_status_known": True,
        "egfr_ml_min": 22.0, "serum_creatinine_mg_dl": 2.8, "renal_status_known": True,
        "child_pugh_class": None, "hepatic_status_known": True,
        "pregnancy_status": "CONFIRMED_NOT_PREGNANT", "lactation_status": "CONFIRMED_NOT_LACTATING",
        "active_medications": ["Amlodipine 5mg PO QD", "Torsemide 10mg PO QD"],
        "clinical_notes": "68yo female with CKD Stage 4 (eGFR 22 mL/min via CKD-EPI 2021 non-race formula) presenting with dysuria, frequency, and suspected cystitis.",
        "diagnosis": "Acute uncomplicated cystitis",
        "prescription": ("Nitrofurantoin", 100, "mg", "PO", "BID", 5),
        "scenario": {
            "key": "uti-nitro-ckd",
            "label": "Sunita Devi (PATIENT-002) - UTI: Nitrofurantoin in CKD-4",
            "diagnosis": "Uncomplicated Urinary Tract Infection (Cystitis)",
            "text": "Nitrofurantoin 100mg PO BID x 5 days for acute cystitis",
        },
    },
    {
        "patient_id": "PATIENT-003",
        "display_name": "PATIENT-003 (Amitabh Verma)",
        "age": 54, "age_category": "ADULT", "weight_kg": 78.0, "sex": "MALE",
        "allergies": ["Meropenem"], "allergy_status_known": True,
        "egfr_ml_min": 75.0, "serum_creatinine_mg_dl": 1.1, "renal_status_known": True,
        "child_pugh_class": "Child-Pugh C", "hepatic_status_known": True,
        "pregnancy_status": "CONFIRMED_NOT_PREGNANT", "lactation_status": "CONFIRMED_NOT_LACTATING",
        "active_medications": ["Furosemide 40mg PO QD", "Spironolactone 100mg PO QD", "Lactulose 30mL PO TID"],
        "clinical_notes": "54yo male with decompensated alcoholic cirrhosis (Child-Pugh C, ascites, jaundice) presenting with abdominal pain and suspected spontaneous bacterial peritonitis.",
        "diagnosis": "Spontaneous bacterial peritonitis",
        "prescription": ("Cefotaxime", 2, "g", "IV", "Q8H", 5),
        "scenario": {
            "key": "cirrhosis-metronidazole",
            "label": "Amitabh Verma (PATIENT-003) - Cirrhosis: Metronidazole Overdose",
            "diagnosis": "Intra-abdominal Infection",
            "text": "Metronidazole 500mg IV TID x 10 days",
        },
    },
    {
        "patient_id": "PATIENT-004",
        "display_name": "PATIENT-004 (Priya Patel)",
        "age": 28, "age_category": "ADULT", "weight_kg": 62.0, "sex": "FEMALE",
        "allergies": ["Tetracycline"], "allergy_status_known": True,
        "egfr_ml_min": 110.0, "serum_creatinine_mg_dl": 0.6, "renal_status_known": True,
        "child_pugh_class": None, "hepatic_status_known": True,
        "pregnancy_status": "PREGNANT_TRIMESTER_2", "lactation_status": "CONFIRMED_NOT_LACTATING",
        "active_medications": ["Prenatal Multivitamin", "Iron Folic Acid"],
        "clinical_notes": "28yo female G2P1 at 24 weeks gestation presenting with acute dysuria and flank discomfort.",
        "diagnosis": "Pregnancy-associated urinary tract infection",
        "prescription": ("Cephalexin", 500, "mg", "PO", "QID", 7),
        "scenario": {
            "key": "pregnancy-ciprofloxacin",
            "label": "Priya Patel (PATIENT-004) - Pregnancy: Ciprofloxacin",
            "diagnosis": "Acute Pyelonephritis",
            "text": "Ciprofloxacin 500mg PO BID x 7 days",
        },
    },
    {
        "patient_id": "PATIENT-005",
        "display_name": "PATIENT-005 (Suresh Kumar)",
        "age": 62, "age_category": "ADULT", "weight_kg": 85.0, "sex": "MALE",
        "allergies": ["Clarithromycin"], "allergy_status_known": True,
        "egfr_ml_min": 82.0, "serum_creatinine_mg_dl": 1.0, "renal_status_known": True,
        "child_pugh_class": None, "hepatic_status_known": True,
        "pregnancy_status": "CONFIRMED_NOT_PREGNANT", "lactation_status": "CONFIRMED_NOT_LACTATING",
        "active_medications": ["Warfarin 5mg PO QD", "Atorvastatin 40mg PO QHS", "Metoprolol 50mg PO BID"],
        "clinical_notes": "62yo male with mechanical mitral valve on Warfarin (baseline INR 2.5) and hyperlipidemia on Atorvastatin presenting with acute cough and purulent sputum.",
        "diagnosis": "Acute bacterial bronchitis",
        "prescription": ("Doxycycline", 100, "mg", "PO", "BID", 5),
        "scenario": {
            "key": "ddi-clarithro-warfarin",
            "label": "Suresh Kumar (PATIENT-005) - DDI: Clarithromycin + Warfarin/Statin",
            "diagnosis": "Acute Bacterial Bronchitis",
            "text": "Clarithromycin 500mg PO BID x 7 days",
        },
    },
    {
        "patient_id": "PATIENT-006",
        "display_name": "PATIENT-006 (Aarav Gupta)",
        "age": 4, "age_category": "PEDIATRIC", "weight_kg": 16.0, "sex": "MALE",
        "allergies": ["Cefaclor"], "allergy_status_known": True,
        "egfr_ml_min": 115.0, "serum_creatinine_mg_dl": 0.4, "renal_status_known": True,
        "child_pugh_class": None, "hepatic_status_known": True,
        "pregnancy_status": "CONFIRMED_NOT_PREGNANT", "lactation_status": "CONFIRMED_NOT_LACTATING",
        "active_medications": ["Paracetamol 240mg PO QID PRN"],
        "clinical_notes": "4yo pediatric male (weight 16kg) presenting with acute otitis media and high fever. Requires weight-based dosing review.",
        "diagnosis": "Acute otitis media",
        "prescription": ("Amoxicillin", 400, "mg", "PO", "BID", 7),
        "scenario": {
            "key": "peds-cefaclor-otitis",
            "label": "Aarav Gupta (PATIENT-006) - Peds Otitis: Cefaclor in Cephalosporin Allergy",
            "diagnosis": "Acute Otitis Media (Pediatric)",
            "text": "Cefaclor 250mg PO TID x 7 days for acute otitis media",
        },
    },
    {
        "patient_id": "PATIENT-007",
        "display_name": "PATIENT-007 (Kamla Rao)",
        "age": 72, "age_category": "GERIATRIC", "weight_kg": 58.0, "sex": "FEMALE",
        "allergies": ["Ciprofloxacin"], "allergy_status_known": True,
        "egfr_ml_min": 55.0, "serum_creatinine_mg_dl": 1.1, "renal_status_known": True,
        "child_pugh_class": None, "hepatic_status_known": True,
        "pregnancy_status": "CONFIRMED_NOT_PREGNANT", "lactation_status": "CONFIRMED_NOT_LACTATING",
        "active_medications": ["Ondansetron 8mg PO TID", "Amiodarone 200mg PO QD"],
        "clinical_notes": "72yo female receiving chemotherapy on Ondansetron and Amiodarone for atrial fibrillation. High cardiac QTc prolongation risk profile.",
        "diagnosis": "Febrile neutropenia",
        "prescription": ("Piperacillin-Tazobactam", 4.5, "g", "IV", "Q6H", 7),
        "scenario": {
            "key": "ddi-qt-azithro",
            "label": "Kamla Rao (PATIENT-007) - DDI: Azithro + Ondansetron (QT)",
            "diagnosis": "Atypical Pneumonia",
            "text": "Azithromycin 500mg PO QD x 5 days",
        },
    },
    {
        "patient_id": "PATIENT-008",
        "display_name": "PATIENT-008 (Vikram Singh)",
        "age": 35, "age_category": "ADULT", "weight_kg": 70.0, "sex": "MALE",
        "allergies": ["Trimethoprim"], "allergy_status_known": True,
        "egfr_ml_min": 98.0, "serum_creatinine_mg_dl": 0.8, "renal_status_known": True,
        "child_pugh_class": None, "hepatic_status_known": True,
        "pregnancy_status": "CONFIRMED_NOT_PREGNANT", "lactation_status": "CONFIRMED_NOT_LACTATING",
        "active_medications": ["Escitalopram 20mg PO QD", "Clonazepam 0.5mg PO PRN"],
        "clinical_notes": "35yo male with severe depression on Escitalopram 20mg presenting with extensive MRSA skin and soft tissue abscess.",
        "diagnosis": "MRSA skin abscess",
        "prescription": ("Linezolid", 600, "mg", "PO", "BID", 7),
        "scenario": {
            "key": "ddi-linezolid-ssri",
            "label": "Vikram Singh (PATIENT-008) - DDI: Linezolid + Escitalopram",
            "diagnosis": "MRSA Soft Tissue Infection",
            "text": "Linezolid 600mg PO BID x 10 days",
        },
    },
    {
        "patient_id": "PATIENT-009",
        "display_name": "PATIENT-009 (Ramesh Iyer)",
        "age": 50, "age_category": "ADULT", "weight_kg": 75.0, "sex": "MALE",
        "allergies": ["Erythromycin"], "allergy_status_known": True,
        "egfr_ml_min": 90.0, "serum_creatinine_mg_dl": 1.0, "renal_status_known": True,
        "child_pugh_class": None, "hepatic_status_known": True,
        "pregnancy_status": "CONFIRMED_NOT_PREGNANT", "lactation_status": "CONFIRMED_NOT_LACTATING",
        "active_medications": ["Aspirin 75mg PO QD"],
        "clinical_notes": "50yo male with fever, hypotension, and suspected sepsis requiring urgent empiric broad-spectrum cover.",
        "diagnosis": "Suspected sepsis",
        "prescription": ("Meropenem", 1, "g", "IV", "Q8H", 7),
        "scenario": {
            "key": "sepsis-erythromycin",
            "label": "Ramesh Iyer (PATIENT-009) - Sepsis: Erythromycin in Macrolide Allergy",
            "diagnosis": "Suspected Sepsis",
            "text": "Erythromycin 500mg IV Q6H x 7 days",
        },
    },
    {
        "patient_id": "PATIENT-010",
        "display_name": "PATIENT-010 (Ananya Reddy)",
        "age": 29, "age_category": "ADULT", "weight_kg": 55.0, "sex": "FEMALE",
        "allergies": ["Flucloxacillin"], "allergy_status_known": True,
        "egfr_ml_min": 95.0, "serum_creatinine_mg_dl": 0.7, "renal_status_known": True,
        "child_pugh_class": None, "hepatic_status_known": True,
        "pregnancy_status": "UNKNOWN", "lactation_status": "UNKNOWN",
        "active_medications": ["Cetirizine 10mg PO QD"],
        "clinical_notes": "29yo female presenting with acute sinusitis. Pregnancy test not yet performed.",
        "diagnosis": "Acute bacterial sinusitis",
        "prescription": ("Amoxicillin-clavulanate", 875, "mg", "PO", "BID", 5),
        "scenario": {
            "key": "sinusitis-doxy-pregnancy",
            "label": "Ananya Reddy (PATIENT-010) - Sinusitis: Doxycycline in Unconfirmed Pregnancy",
            "diagnosis": "Acute Bacterial Sinusitis",
            "text": "Doxycycline 100mg PO BID x 7 days",
        },
    },
    {
        "patient_id": "PATIENT-011",
        "display_name": "PATIENT-011 (Meena Joshi)",
        "age": 39, "age_category": "ADULT", "weight_kg": 68.0, "sex": "FEMALE",
        "allergies": ["Vancomycin"], "allergy_status_known": True,
        "egfr_ml_min": 96.0, "serum_creatinine_mg_dl": 0.8, "renal_status_known": True,
        "child_pugh_class": None, "hepatic_status_known": True,
        "pregnancy_status": "CONFIRMED_NOT_PREGNANT", "lactation_status": "CONFIRMED_NOT_LACTATING",
        "active_medications": ["Metformin 500mg PO BID"],
        "clinical_notes": "39yo female with diabetes and non-purulent lower-limb cellulitis.",
        "diagnosis": "Non-purulent cellulitis",
        "prescription": ("Clindamycin", 300, "mg", "PO", "QID", 5),
        "scenario": {
            "key": "cellulitis-vancomycin",
            "label": "Meena Joshi (PATIENT-011) - Cellulitis: Vancomycin in Glycopeptide Allergy",
            "diagnosis": "Non-purulent Cellulitis",
            "text": "Vancomycin 1g IV Q12H x 7 days",
        },
    },
    {
        "patient_id": "PATIENT-012",
        "display_name": "PATIENT-012 (Dinesh Deshmukh)",
        "age": 57, "age_category": "ADULT", "weight_kg": 76.0, "sex": "MALE",
        "allergies": ["Ceftriaxone"], "allergy_status_known": True,
        "egfr_ml_min": 71.0, "serum_creatinine_mg_dl": 1.1, "renal_status_known": True,
        "child_pugh_class": None, "hepatic_status_known": True,
        "pregnancy_status": "CONFIRMED_NOT_PREGNANT", "lactation_status": "CONFIRMED_NOT_LACTATING",
        "active_medications": ["Tamsulosin 0.4mg PO QD"],
        "clinical_notes": "57yo male with fever and flank pain consistent with acute pyelonephritis.",
        "diagnosis": "Acute pyelonephritis",
        "prescription": ("Ciprofloxacin", 500, "mg", "PO", "BID", 7),
        "scenario": {
            "key": "pyelo-ceftriaxone",
            "label": "Dinesh Deshmukh (PATIENT-012) - Pyelonephritis: Ceftriaxone in Beta-Lactam Allergy",
            "diagnosis": "Acute Pyelonephritis",
            "text": "Ceftriaxone 2g IV QD x 7 days",
        },
    },
    {
        "patient_id": "PATIENT-013",
        "display_name": "PATIENT-013 (Lakshmi Nair)",
        "age": 66, "age_category": "GERIATRIC", "weight_kg": 59.0, "sex": "FEMALE",
        "allergies": ["Doxycycline"], "allergy_status_known": True,
        "egfr_ml_min": 48.0, "serum_creatinine_mg_dl": 1.3, "renal_status_known": True,
        "child_pugh_class": None, "hepatic_status_known": True,
        "pregnancy_status": "CONFIRMED_NOT_PREGNANT", "lactation_status": "CONFIRMED_NOT_LACTATING",
        "active_medications": ["Insulin glargine 18 units SC QHS"],
        "clinical_notes": "66yo female with diabetes and hospital-acquired pneumonia.",
        "diagnosis": "Hospital-acquired pneumonia",
        "prescription": ("Vancomycin", 1, "g", "IV", "Q12H", 7),
        "scenario": {
            "key": "hap-doxycycline",
            "label": "Lakshmi Nair (PATIENT-013) - HAP: Doxycycline in Tetracycline Allergy",
            "diagnosis": "Hospital-Acquired Pneumonia",
            "text": "Doxycycline 100mg PO BID x 7 days",
        },
    },
    {
        "patient_id": "PATIENT-014",
        "display_name": "PATIENT-014 (Rohan Banerjee)",
        "age": 31, "age_category": "ADULT", "weight_kg": 64.0, "sex": "MALE",
        "allergies": ["Nitrofurantoin"], "allergy_status_known": True,
        "egfr_ml_min": 108.0, "serum_creatinine_mg_dl": 0.7, "renal_status_known": True,
        "child_pugh_class": None, "hepatic_status_known": True,
        "pregnancy_status": "CONFIRMED_NOT_PREGNANT", "lactation_status": "CONFIRMED_NOT_LACTATING",
        "active_medications": ["ORS sachets PRN"],
        "clinical_notes": "31yo male with acute infectious diarrhoea and dehydration.",
        "diagnosis": "Acute infectious diarrhoea",
        "prescription": ("Metronidazole", 400, "mg", "PO", "TID", 5),
        "scenario": {
            "key": "diarrhoea-nitrofurantoin",
            "label": "Rohan Banerjee (PATIENT-014) - Enteritis: Nitrofurantoin in Nitro Allergy",
            "diagnosis": "Acute Infectious Diarrhoea",
            "text": "Nitrofurantoin 100mg PO BID x 5 days",
        },
    },
    {
        "patient_id": "PATIENT-015",
        "display_name": "PATIENT-015 (Kavya Kulkarni)",
        "age": 19, "age_category": "ADULT", "weight_kg": 61.0, "sex": "FEMALE",
        "allergies": ["Azithromycin"], "allergy_status_known": True,
        "egfr_ml_min": 112.0, "serum_creatinine_mg_dl": 0.6, "renal_status_known": True,
        "child_pugh_class": None, "hepatic_status_known": True,
        "pregnancy_status": "CONFIRMED_NOT_PREGNANT", "lactation_status": "CONFIRMED_NOT_LACTATING",
        "active_medications": ["Ibuprofen 200mg PO PRN"],
        "clinical_notes": "19yo female with fever, headache, and suspected bacterial meningitis.",
        "diagnosis": "Suspected bacterial meningitis",
        "prescription": ("Ceftriaxone", 2, "g", "IV", "Q12H", 10),
        "scenario": {
            "key": "meningitis-azithromycin",
            "label": "Kavya Kulkarni (PATIENT-015) - Meningitis: Azithromycin in Macrolide Allergy",
            "diagnosis": "Suspected Bacterial Meningitis",
            "text": "Azithromycin 500mg IV QD x 10 days",
        },
    },
    {
        "patient_id": "PATIENT-016",
        "display_name": "PATIENT-016 (Harishchandra Prasad)",
        "age": 73, "age_category": "GERIATRIC", "weight_kg": 70.0, "sex": "MALE",
        "allergies": ["Gentamicin"], "allergy_status_known": True,
        "egfr_ml_min": 58.0, "serum_creatinine_mg_dl": 1.2, "renal_status_known": True,
        "child_pugh_class": None, "hepatic_status_known": True,
        "pregnancy_status": "CONFIRMED_NOT_PREGNANT", "lactation_status": "CONFIRMED_NOT_LACTATING",
        "active_medications": ["Apixaban 5mg PO BID"],
        "clinical_notes": "73yo male with prosthetic-valve endocarditis under specialist review.",
        "diagnosis": "Prosthetic-valve endocarditis",
        "prescription": ("Rifampicin", 600, "mg", "PO", "QD", 14),
        "scenario": {
            "key": "endocarditis-gentamicin",
            "label": "Harishchandra Prasad (PATIENT-016) - Endocarditis: Gentamicin in Aminoglycoside Allergy",
            "diagnosis": "Prosthetic-Valve Endocarditis",
            "text": "Gentamicin 70mg IV Q8H x 14 days",
        },
    },
    {
        "patient_id": "PATIENT-017",
        "display_name": "PATIENT-017 (Diya Bhatt)",
        "age": 11, "age_category": "PEDIATRIC", "weight_kg": 37.0, "sex": "FEMALE",
        "allergies": ["Clindamycin"], "allergy_status_known": True,
        "egfr_ml_min": 120.0, "serum_creatinine_mg_dl": 0.5, "renal_status_known": True,
        "child_pugh_class": None, "hepatic_status_known": True,
        "pregnancy_status": "UNKNOWN", "lactation_status": "UNKNOWN",
        "active_medications": ["Multivitamin syrup 5mL PO QD"],
        "clinical_notes": "11yo female with confirmed group-A streptococcal pharyngitis.",
        "diagnosis": "Group-A streptococcal pharyngitis",
        "prescription": ("Penicillin V", 250, "mg", "PO", "BID", 10),
        "scenario": {
            "key": "peds-pharyngitis-clinda",
            "label": "Diya Bhatt (PATIENT-017) - Peds Pharyngitis: Clindamycin in Lincosamide Allergy",
            "diagnosis": "Group-A Streptococcal Pharyngitis",
            "text": "Clindamycin 300mg PO TID x 10 days",
        },
    },
    {
        "patient_id": "PATIENT-018",
        "display_name": "PATIENT-018 (Manoj Chatterjee)",
        "age": 47, "age_category": "ADULT", "weight_kg": 82.0, "sex": "MALE",
        "allergies": ["Colistin"], "allergy_status_known": True,
        "egfr_ml_min": 88.0, "serum_creatinine_mg_dl": 0.9, "renal_status_known": True,
        "child_pugh_class": None, "hepatic_status_known": True,
        "pregnancy_status": "CONFIRMED_NOT_PREGNANT", "lactation_status": "CONFIRMED_NOT_LACTATING",
        "active_medications": ["Ibuprofen 400mg PO PRN"],
        "clinical_notes": "47yo male with facial swelling from an acute odontogenic infection.",
        "diagnosis": "Acute odontogenic infection",
        "prescription": ("Ampicillin", 500, "mg", "PO", "TID", 5),
        "scenario": {
            "key": "dental-colistin",
            "label": "Manoj Chatterjee (PATIENT-018) - Dental: Colistin in Polymyxin Allergy",
            "diagnosis": "Acute Odontogenic Infection",
            "text": "Colistin 150mg IV BID x 5 days",
        },
    },
    {
        "patient_id": "PATIENT-019",
        "display_name": "PATIENT-019 (Shalini Agarwal)",
        "age": 58, "age_category": "ADULT", "weight_kg": 74.0, "sex": "FEMALE",
        "allergies": ["Levofloxacin"], "allergy_status_known": True,
        "egfr_ml_min": 67.0, "serum_creatinine_mg_dl": 1.0, "renal_status_known": True,
        "child_pugh_class": None, "hepatic_status_known": True,
        "pregnancy_status": "CONFIRMED_NOT_PREGNANT", "lactation_status": "CONFIRMED_NOT_LACTATING",
        "active_medications": ["Tiotropium inhaler QD"],
        "clinical_notes": "58yo female with COPD, increased sputum purulence, and suspected bacterial exacerbation.",
        "diagnosis": "Bacterial COPD exacerbation",
        "prescription": ("Cefuroxime", 500, "mg", "PO", "BID", 5),
        "scenario": {
            "key": "copd-levofloxacin",
            "label": "Shalini Agarwal (PATIENT-019) - COPD Exacerbation: Levofloxacin in Quinolone Allergy",
            "diagnosis": "Bacterial COPD Exacerbation",
            "text": "Levofloxacin 500mg PO QD x 5 days",
        },
    },
    {
        "patient_id": "PATIENT-020",
        "display_name": "PATIENT-020 (Aditya Menon)",
        "age": 24, "age_category": "ADULT", "weight_kg": 66.0, "sex": "MALE",
        "allergies": ["Cefixime"], "allergy_status_known": True,
        "egfr_ml_min": 102.0, "serum_creatinine_mg_dl": 0.8, "renal_status_known": True,
        "child_pugh_class": None, "hepatic_status_known": True,
        "pregnancy_status": "CONFIRMED_NOT_PREGNANT", "lactation_status": "CONFIRMED_NOT_LACTATING",
        "active_medications": ["Zinc sulfate 20mg PO QD"],
        "clinical_notes": "24yo male with culture-supported enteric fever and no complications.",
        "diagnosis": "Uncomplicated enteric fever",
        "prescription": ("Aztreonam", 1, "g", "IV", "Q8H", 10),
        "scenario": {
            "key": "enteric-cefixime",
            "label": "Aditya Menon (PATIENT-020) - Enteric Fever: Cefixime in Cephalosporin Allergy",
            "diagnosis": "Uncomplicated Enteric Fever",
            "text": "Cefixime 200mg PO BID x 10 days",
        },
    },
]


def _patient_row(entry: dict) -> dict:
    return {
        "patient_id": entry["patient_id"],
        "display_name": entry.get("display_name", f"{entry['patient_id']} (Synthetic Patient)"),
        "age": entry["age"],
        "age_category": entry["age_category"],
        "weight_kg": entry["weight_kg"],
        "sex": entry["sex"],
        "allergies_json": json.dumps(entry["allergies"]),
        "allergy_status_known": entry["allergy_status_known"],
        "egfr_ml_min": entry["egfr_ml_min"],
        "serum_creatinine_mg_dl": entry["serum_creatinine_mg_dl"],
        "renal_status_known": entry["renal_status_known"],
        "child_pugh_class": entry["child_pugh_class"],
        "hepatic_status_known": entry["hepatic_status_known"],
        "pregnancy_status": entry["pregnancy_status"],
        "lactation_status": entry["lactation_status"],
        "active_medications_json": json.dumps(entry["active_medications"]),
        "clinical_notes": entry["clinical_notes"],
    }


def seed_roster_ids() -> set:
    return {entry["patient_id"] for entry in SEED_ROSTER}


def seed_scenario_presets() -> list:
    """Fixed teaching chips — one unique preset per seeded patient."""
    return [
        {
            "key": entry["scenario"]["key"],
            "label": entry["scenario"]["label"],
            "patient_id": entry["patient_id"],
            "diagnosis": entry["scenario"]["diagnosis"],
            "text": entry["scenario"]["text"],
            "source": "seed",
        }
        for entry in SEED_ROSTER
    ]


def _format_item_text(item: PrescriptionItemDB) -> str:
    parts = [item.medication_name or "Antimicrobial"]
    if item.dose is not None:
        parts.append(f"{item.dose}{item.unit or ''}".strip())
    if item.route:
        parts.append(item.route)
    if item.frequency:
        parts.append(item.frequency)
    if item.duration_days:
        parts.append(f"x {item.duration_days} days")
    return " ".join(parts)


def registered_scenario_presets(db) -> list:
    """
    Quick-scenario chips for clinician-registered patients (not in SEED_ROSTER).

    Built from the latest visit so a newly registered patient appears in the
    console preset strip as soon as they have a diagnosis / prescription.
    """
    seed_ids = seed_roster_ids()
    presets = []
    patients = (
        db.query(PatientDB)
        .order_by(PatientDB.patient_id.asc())
        .all()
    )
    for patient in patients:
        if patient.patient_id in seed_ids:
            continue
        latest = (
            db.query(PrescriptionDB)
            .filter(PrescriptionDB.patient_id == patient.patient_id)
            .order_by(PrescriptionDB.created_at.desc())
            .first()
        )
        diagnosis = (latest.diagnosis if latest and latest.diagnosis else None) or (
            (patient.clinical_notes or "").strip()[:80] or "Clinical review"
        )
        text = ""
        if latest:
            if latest.raw_text and latest.raw_text.strip():
                text = latest.raw_text.strip()
            else:
                items = (
                    db.query(PrescriptionItemDB)
                    .filter(PrescriptionItemDB.prescription_id == latest.prescription_id)
                    .all()
                )
                if items:
                    text = " and ".join(_format_item_text(i) for i in items)
        if not text:
            text = (
                f"Antimicrobial therapy for {diagnosis} — "
                "enter agent, dose, route, and duration for safety review"
            )
        short = diagnosis if len(diagnosis) <= 42 else diagnosis[:39].rstrip() + "…"
        presets.append({
            "key": f"registered-{patient.patient_id.lower()}",
            "label": f"{patient.patient_id}: {short}",
            "patient_id": patient.patient_id,
            "diagnosis": diagnosis,
            "text": text,
            "source": "registered",
        })
    return presets


def list_scenario_presets(db) -> list:
    """Seed teaching presets first, then any clinician-registered patient chips."""
    return seed_scenario_presets() + registered_scenario_presets(db)


def seed_database(reset_patients: bool = False):
    init_db()
    db = SessionLocal()

    # 1. Seed Synthetic Patients. These are the fixed, deliberately varied
    # teaching roster shown to clinicians on first use. No real identifiers are
    # stored anywhere in this dataset.
    patients_data = [_patient_row(entry) for entry in SEED_ROSTER]

    if reset_patients:
        # The reset is intentionally opt-in. It is for restoring the small
        # synthetic teaching roster, not a normal startup action: clinician
        # registrations must remain available after they are created.
        db.query(ClinicianOverrideDB).delete(synchronize_session=False)
        db.query(SafetyWarningDB).delete(synchronize_session=False)
        db.query(PrescriptionItemDB).delete(synchronize_session=False)
        db.query(PrescriptionDB).delete(synchronize_session=False)
        db.query(SymptomDB).delete(synchronize_session=False)
        db.query(DiagnosisDB).delete(synchronize_session=False)
        db.query(VisitDB).delete(synchronize_session=False)
        db.query(PatientRAGDocumentDB).delete(synchronize_session=False)
        db.query(AuditLogDB).delete(synchronize_session=False)
        db.query(PatientDB).delete(synchronize_session=False)
        db.commit()

    # Seeded patients are FIXTURES, so seeding converges them to the intended
    # state rather than skipping any that already exist.
    #
    # Skipping looks idempotent but is not: anything that touches the API before
    # the seeder runs -- the test suite, or a click in the UI -- can create a row
    # for PATIENT-001 with no allergies. The old code then saw the id present and
    # left it that way, so the penicillin allergy every allergy test depends on
    # silently never arrived, and re-running the seeder could not repair it. The
    # failure surfaced as "assert 'Penicillin' in []", which points nowhere near
    # the cause.
    #
    # Only the seeded ids are touched. Patients created by a clinician through the
    # UI are never overwritten, because their ids are not in this list.
    repaired = []
    for p_data in patients_data:
        existing = db.query(PatientDB).filter(PatientDB.patient_id == p_data["patient_id"]).first()
        if not existing:
            db.add(PatientDB(**p_data))
            continue

        drifted = [
            field for field, value in p_data.items()
            if field != "patient_id" and getattr(existing, field, None) != value
        ]
        if drifted:
            for field, value in p_data.items():
                setattr(existing, field, value)
            repaired.append(f"{p_data['patient_id']} ({', '.join(drifted)})")

    # Each roster patient has one initial, intentionally distinct clinical
    # scenario. This makes the dashboard timeline useful immediately while
    # keeping the clinician free to add further visits and prescriptions.
    from datetime import datetime, timezone
    from backend.rag.patient_rag import index_visit_for_rag

    for index, entry in enumerate(SEED_ROSTER, 1):
        prescription_id = f"SEED-RX-{index:03d}"
        visit_id = f"VIS-{index:03d}"

        if not db.query(PrescriptionDB).filter(PrescriptionDB.prescription_id == prescription_id).first():
            medication, dose, unit, route, frequency, duration = entry["prescription"]
            diagnosis = entry["diagnosis"]
            db.add(PrescriptionDB(
                prescription_id=prescription_id, patient_id=entry["patient_id"], visit_id=visit_id, diagnosis=diagnosis,
                raw_text=f"{medication} {dose}{unit} {route} {frequency} for {duration} days",
                clinician_id="SYSTEM-SEED", clinician_role="ATTENDING_PHYSICIAN", status="RECORDED",
            ))
            db.add(PrescriptionItemDB(
                prescription_id=prescription_id, medication_name=medication, dose=dose, unit=unit,
                route=route, frequency=frequency, duration_days=duration, indication=diagnosis,
                antimicrobial_class="SEED_SCENARIO", aware_category="NOT_APPLICABLE",
                extraction_confidence_json=json.dumps({"seed": 1.0}),
            ))

        if not db.query(VisitDB).filter(VisitDB.visit_id == visit_id).first():
            v_date = datetime(2026, 8, 10, 10, 0, 0, tzinfo=timezone.utc)
            if entry["patient_id"] == "PATIENT-001":
                v_diag = "Upper respiratory infection"
                v_symptoms = ["Fever", "Cough", "Sore throat"]
                v_notes = "Patient presented with fever, cough, and sore throat."
            else:
                v_diag = entry["diagnosis"]
                v_symptoms = [entry["diagnosis"]]
                v_notes = entry["clinical_notes"]

            visit_obj = VisitDB(
                visit_id=visit_id,
                patient_id=entry["patient_id"],
                doctor_id="DOC-DEMO-01",
                visit_date=v_date,
                diagnosis=v_diag,
                clinical_notes=v_notes,
                prescription_id=prescription_id,
                status="COMPLETED"
            )
            db.add(visit_obj)
            db.flush()

            for sym in v_symptoms:
                db.add(SymptomDB(
                    visit_id=visit_id,
                    patient_id=entry["patient_id"],
                    name=sym,
                    severity="Moderate",
                    duration="3 days"
                ))
            db.add(DiagnosisDB(
                visit_id=visit_id,
                patient_id=entry["patient_id"],
                diagnosis_name=v_diag
            ))
            db.commit()
            index_visit_for_rag(db, visit_id)

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
    print(f"Database successfully seeded with {len(SEED_ROSTER)} synthetic patients, clinical rules, and AMR data.")
    if repaired:
        # Say so out loud: a silent repair hides that something had already
        # written over a fixture, which is worth knowing about.
        print(f"Repaired {len(repaired)} seeded patient record(s) that had drifted:")
        for entry in repaired:
            print(f"  - {entry}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the synthetic AntiBioTix teaching dataset.")
    parser.add_argument(
        "--reset-patients", action="store_true",
        help=f"Remove existing synthetic patient visits/audits and restore only the {len(SEED_ROSTER)} fixed demo records.",
    )
    args = parser.parse_args()
    seed_database(reset_patients=args.reset_patients)
