"""Certificate PDF generation with ReportLab."""
from __future__ import annotations

import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth

GREEN = colors.HexColor("#14532D")


def _wrap(c: canvas.Canvas, text: str, font: str, size: int, width: float) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if stringWidth(trial, font, size) <= width:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def certificate_pdf(doc: dict, village: str = "Gram Panchayat") -> bytes:
    data = doc["data"]
    is_birth = doc["doc_type"] == "birth_certificate"
    title = "BIRTH CERTIFICATE" if is_birth else "BONAFIDE CERTIFICATE"
    ref = f"GS-{'BC' if is_birth else 'BF'}-{doc['id']:06d}"

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    c.setStrokeColor(GREEN)
    c.setLineWidth(3)
    c.rect(28, 28, w - 56, h - 56)
    c.setLineWidth(0.8)
    c.rect(36, 36, w - 72, h - 72)

    c.setFillColor(GREEN)
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(w / 2, h - 100, village.upper())
    c.setFont("Helvetica", 11)
    c.setFillColor(colors.grey)
    c.drawCentredString(w / 2, h - 118, "Government of Maharashtra  |  GramSathi e-Governance")
    c.setFillColor(GREEN)
    c.setFont("Helvetica-Bold", 26)
    c.drawCentredString(w / 2, h - 175, title)
    c.setStrokeColor(GREEN)
    c.line(w / 2 - 90, h - 188, w / 2 + 90, h - 188)

    c.setFillColor(colors.black)
    c.setFont("Helvetica", 11)
    c.drawString(70, h - 225, f"Ref. No: {ref}")
    c.drawRightString(w - 70, h - 225, f"Date of issue: {(doc.get('reviewed_at') or date.today().isoformat())[:10]}")

    if is_birth:
        body = (
            f"This is to certify that {data['full_name']}, child of {data['father_name']}"
            + (f" and {data['mother_name']}" if data.get("mother_name") else "")
            + f", was born on {data['date_of_birth']}"
            + (f" at {data['place_of_birth']}" if data.get("place_of_birth") else "")
            + f". Residential address of the family: {data['address']}."
        )
    else:
        body = (
            f"This is to certify that {data['full_name']}, son/daughter of {data['father_name']}, born on {data['date_of_birth']}, "
            f"residing at {data['address']}, is a bonafide student"
            + (f" of {data['school_name']}" if data.get("school_name") else "")
            + "."
            + (f" This certificate is issued for the purpose of: {data['purpose']}." if data.get("purpose") else "")
        )

    c.setFont("Helvetica", 13)
    y = h - 290
    for line in _wrap(c, body, "Helvetica", 13, w - 140):
        c.drawString(70, y, line)
        y -= 24

    c.setFont("Helvetica-Oblique", 10)
    c.setFillColor(colors.grey)
    c.drawString(70, 150, "This is a computer-generated certificate issued after approval by the Gram Panchayat office.")
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 11)
    c.line(w - 230, 120, w - 70, 120)
    c.drawCentredString(w - 150, 104, "Gram Sevak / Sarpanch")
    c.showPage()
    c.save()
    return buf.getvalue()
