"""
PDF Prescription Generator for AntiBioTix Clinical Support System.
Generates official prescription PDFs from database visit/prescription records.
"""

import io
# timedelta is used to build the IST offset on the fallback path below. It was
# missing from this import, so generating a prescription for a visit with no
# recorded date raised NameError instead of stamping the current time -- the branch
# only runs when visit_date is absent, which is why it survived.
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle


def _patient_label(patient: Dict[str, Any]) -> str:
    """
    "Rajesh Sharma (PATIENT-001)", or the bare id when no name is recorded.

    Records seeded before display_name held a bare name carry it as
    "PATIENT-001 (Rajesh Sharma)", so the parenthesised form is unwrapped rather
    than printed back with the id twice. A display_name that is just the id again,
    or the registration placeholder, is treated as no name at all.
    """
    import re as _re

    patient_id = str(patient.get("patient_id") or "N/A")
    name = (patient.get("display_name") or "").strip()
    wrapped = _re.match(r"^\s*\S+\s*\((.+)\)\s*$", name)
    if wrapped:
        name = wrapped.group(1).strip()
    if not name or name == patient_id or name == "Patient Record":
        return patient_id
    return f"{name} ({patient_id})"


def generate_prescription_pdf(
    patient: Dict[str, Any],
    visit: Dict[str, Any],
    prescription_items: List[Dict[str, Any]],
    warnings: List[Dict[str, Any]] = None,
    overrides: List[Dict[str, Any]] = None,
    clinician_id: str = "DOC-DEMO-01",
    clinician_role: str = "ATTENDING_PHYSICIAN"
) -> bytes:
    """Generate bytes for a formal clinical prescription PDF."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#173c3d')
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=13,
        textColor=colors.HexColor('#607371')
    )
    banner_style = ParagraphStyle(
        'SyntheticBanner',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11,
        alignment=1,
        textColor=colors.HexColor('#a65e38')
    )
    section_heading = ParagraphStyle(
        'SectionHead',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=15,
        textColor=colors.HexColor('#173c3d'),
        spaceBefore=10,
        spaceAfter=6
    )
    body_style = ParagraphStyle(
        'BodyText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#203236')
    )
    bold_style = ParagraphStyle(
        'BoldText',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#203236')
    )

    story = []

    # Synthetic Banner
    banner_table = Table(
        [[Paragraph("SYNTHETIC DEMONSTRATION DATA — NOT A REAL PRESCRIPTION", banner_style)]],
        colWidths=[540]
    )
    banner_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fbe9e5')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#a65e38'))
    ]))
    story.append(banner_table)
    story.append(Spacer(1, 10))

    # Header
    story.append(Paragraph("ANTIBIOTIX CLINICAL DECISION SUPPORT", title_style))
    story.append(Paragraph("Antimicrobial Stewardship & Prescription Safety Record", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#4e8a7a'), spaceAfter=10, spaceBefore=6))

    # Metadata Grid (Clinician, Date, Patient)
    v_date = visit.get("visit_date")
    if isinstance(v_date, datetime):
        v_date_str = v_date.strftime("%d %B %Y %H:%M IST")
    else:
        v_date_str = str(v_date or datetime.now(timezone(timedelta(hours=5, minutes=30), name="IST")).strftime("%d %B %Y %H:%M IST"))

    meta_data = [
        [
            Paragraph("<b>Prescribing Clinician:</b> " + clinician_id + " (" + clinician_role + ")", body_style),
            Paragraph("<b>Visit ID:</b> " + str(visit.get("visit_id", "N/A")), body_style)
        ],
        [
            # The name AND the id. A prescription identifying its patient only by
            # "PATIENT-014" is not a record a clinician can check at the bedside, and
            # the id alone is what this document carried. The id stays because it is
            # what the audit trail and every other record key on.
            Paragraph("<b>Patient:</b> " + _patient_label(patient), body_style),
            Paragraph("<b>Visit Date:</b> " + v_date_str, body_style)
        ],
        [
            Paragraph("<b>Age / Sex:</b> " + str(patient.get("age", "N/A")) + " yrs / " + str(patient.get("sex", "N/A")), body_style),
            Paragraph("<b>Weight:</b> " + str(patient.get("weight_kg", "N/A")) + " kg", body_style)
        ],
        [
            Paragraph("<b>Renal Status (eGFR):</b> " + str(patient.get("egfr_ml_min", "Not assessed")) + " mL/min", body_style),
            Paragraph("<b>Hepatic Class:</b> " + str(patient.get("child_pugh_class", "Normal")), body_style)
        ],
        [
            Paragraph("<b>Documented Allergies:</b> " + (", ".join(patient.get("allergies", [])) or "None documented"), bold_style),
            Paragraph("<b>Current Medications:</b> " + (", ".join(patient.get("active_medications", [])) or "None"), body_style)
        ]
    ]

    meta_table = Table(meta_data, colWidths=[270, 270])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fbfcf9')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#cbd9d4')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#eef3f0')),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 10))

    # Diagnosis & Symptoms
    story.append(Paragraph("Clinical Diagnosis & Findings", section_heading))
    diag_data = [
        [Paragraph("<b>Primary Diagnosis:</b>", bold_style), Paragraph(str(visit.get("diagnosis", "Not recorded")), body_style)],
        [Paragraph("<b>Clinical Notes:</b>", bold_style), Paragraph(str(visit.get("clinical_notes", "None recorded")), body_style)]
    ]
    diag_table = Table(diag_data, colWidths=[120, 420])
    diag_table.setStyle(TableStyle([
        ('PADDING', (0, 0), (-1, -1), 4),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(diag_table)
    story.append(Spacer(1, 10))

    # Prescribed Medications Table
    story.append(Paragraph("Prescribed Medication Orders (Rx)", section_heading))
    rx_header = [
        Paragraph("<b>Medication</b>", bold_style),
        Paragraph("<b>Dose</b>", bold_style),
        Paragraph("<b>Route</b>", bold_style),
        Paragraph("<b>Frequency</b>", bold_style),
        Paragraph("<b>Duration</b>", bold_style),
        Paragraph("<b>Indication</b>", bold_style)
    ]
    rx_rows = [rx_header]
    for item in prescription_items:
        rx_rows.append([
            Paragraph(str(item.get("medication_name", "")), bold_style),
            Paragraph(f"{item.get('dose', '')} {item.get('unit', '')}".strip(), body_style),
            Paragraph(str(item.get("route", "")), body_style),
            Paragraph(str(item.get("frequency", "")), body_style),
            Paragraph(f"{item.get('duration_days', '')} days".strip() if item.get('duration_days') else "", body_style),
            Paragraph(str(item.get("indication", visit.get("diagnosis", ""))), body_style)
        ])

    rx_table = Table(rx_rows, colWidths=[130, 70, 60, 80, 70, 130])
    rx_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e4f0e9')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#cbd9d4')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d8e2dd')),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(rx_table)
    story.append(Spacer(1, 12))

    # AntiBioTix Safety Analysis & Overrides
    if warnings or overrides:
        story.append(Paragraph("AntiBioTix Clinical Safety Decision Support Audit", section_heading))
        warn_text = []
        if warnings:
            for w in warnings:
                warn_text.append(f"• [{w.get('severity', 'WARNING')}] {w.get('title', '')} (Rule: {w.get('rule_id', '')}): {w.get('recommendation', '')}")
        if overrides:
            for o in overrides:
                warn_text.append(f"• [CLINICIAN OVERRIDE] Rule {o.get('rule_id', '')} overridden by {o.get('clinician_role', 'Clinician')}. Rationale: {o.get('reason', '')}")
        
        warn_para = Paragraph("<br/>".join(warn_text), body_style)
        warn_table = Table([[warn_para]], colWidths=[540])
        warn_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f0f6f1')),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#4e8a7a')),
            ('PADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(warn_table)
        story.append(Spacer(1, 12))

    # Legal / Clinical Disclaimer Footer
    disclaimer = (
        "AntiBioTix Clinical Decision Support System — Final prescribing authority and clinical judgment "
        "remain with the attending clinician. Synthetic demonstration record."
    )
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#cbd9d4'), spaceBefore=10, spaceAfter=6))
    story.append(Paragraph(disclaimer, subtitle_style))

    doc.build(story)
    return buffer.getvalue()
