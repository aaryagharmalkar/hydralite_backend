# import json
# import os
# from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
# from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
# from reportlab.lib.pagesizes import A4
# from reportlab.pdfbase import pdfmetrics
# from reportlab.pdfbase.ttfonts import TTFont

# # ===============================
# # BASE PATHS
# # ===============================
# BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# PDF_DIR = os.path.join(BASE_DIR, "pdfs")
# FONTS_DIR = os.path.join(BASE_DIR, "fonts")

# os.makedirs(PDF_DIR, exist_ok=True)

# # ===============================
# # FONT MAP (LANGUAGE → FONT FILE)
# # ===============================
# FONT_MAP = {
#     "hi": "NotoSansDevanagari-Regular.ttf",
#     "mr": "NotoSansDevanagari-Regular.ttf",
#     "gu": "NotoSansGujarati-Regular.ttf",
#     "ta": "NotoSansTamil-Regular.ttf",
#     "te": "NotoSansTelugu-Regular.ttf",
#     "kn": "NotoSansKannada-Regular.ttf",
#     "ml": "NotoSansMalayalam-Regular.ttf",
#     "bn": "NotoSansBengali-Regular.ttf",
# }

# # ===============================
# # FONT REGISTRATION (SAFE)
# # ===============================
# def register_font(language: str) -> str:
#     """
#     Returns a ReportLab-safe font name.
#     English uses Helvetica (built-in).
#     Indian languages use proper Noto Sans Unicode fonts.
#     """

#     # ✅ English → built-in font
#     if language == "en":
#         return "Helvetica"

#     font_file = FONT_MAP.get(language)

#     if not font_file:
#         print("⚠ No font mapping found, falling back to Helvetica")
#         return "Helvetica"

#     font_path = os.path.join(FONTS_DIR, font_file)
#     font_name = font_file.replace(".ttf", "")

#     try:
#         if font_name not in pdfmetrics.getRegisteredFontNames():
#             pdfmetrics.registerFont(TTFont(font_name, font_path))
#         return font_name
#     except Exception as e:
#         print("⚠ Font registration failed, fallback to Helvetica:", e)
#         return "Helvetica"

# # ===============================
# # PDF GENERATOR
# # ===============================
# def generate_pdf(summary_json_path: str, language: str = "en") -> str:
#     # -------- LOAD SUMMARY JSON --------
#     with open(summary_json_path, "r", encoding="utf-8") as f:
#         summary = json.load(f)

#     base_name = os.path.splitext(os.path.basename(summary_json_path))[0]
#     pdf_path = os.path.join(PDF_DIR, f"{base_name}.pdf")

#     # -------- REGISTER FONT --------
#     font_name = register_font(language)

#     # -------- PDF DOCUMENT --------
#     doc = SimpleDocTemplate(
#         pdf_path,
#         pagesize=A4,
#         rightMargin=40,
#         leftMargin=40,
#         topMargin=40,
#         bottomMargin=40,
#     )

#     base_styles = getSampleStyleSheet()

#     styles = {
#         "heading": ParagraphStyle(
#             "heading",
#             parent=base_styles["Heading3"],
#             fontName=font_name,
#             spaceAfter=8,
#         ),
#         "normal": ParagraphStyle(
#             "normal",
#             parent=base_styles["Normal"],
#             fontName=font_name,
#             spaceAfter=4,
#         ),
#     }

#     story = []

#     # -------- SAFE PARAGRAPH HELPER --------
#     def safe_para(text):
#         """
#         Ensures text is safe for ReportLab Paragraph
#         """
#         if not text:
#             return "—"
#         return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

#     # -------- SECTION HELPER --------
#     def add_section(title, content):
#         story.append(Paragraph(f"<b>{safe_para(title)}</b>", styles["heading"]))
#         story.append(Spacer(1, 6))

#         if isinstance(content, list):
#             if not content:
#                 story.append(Paragraph("—", styles["normal"]))
#             else:
#                 for item in content:
#                     story.append(
#                         Paragraph(f"• {safe_para(item)}", styles["normal"])
#                     )
#         else:
#             story.append(Paragraph(safe_para(content), styles["normal"]))

#         story.append(Spacer(1, 14))

#     # -------- PDF CONTENT --------
#     add_section("Doctor Summary", summary.get("doctor_summary", ""))
#     add_section("Symptoms", summary.get("symptoms", []))
#     add_section("Patient History", summary.get("patient_history", []))
#     add_section("Risk Factors", summary.get("risk_factors", []))
#     add_section("Prescription", summary.get("prescription", []))
#     add_section("Advice", summary.get("advice", []))
#     add_section("Recommended Action", summary.get("recommended_action", ""))

#     # -------- BUILD PDF --------
#     doc.build(story)

#     return pdf_path


import json
import os
from datetime import datetime

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ===============================
# BASE PATHS
# ===============================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PDF_DIR = os.path.join(BASE_DIR, "pdfs")
FONTS_DIR = os.path.join(BASE_DIR, "fonts")

os.makedirs(PDF_DIR, exist_ok=True)

# ===============================
# FAKE DOCTOR DETAILS (LETTERHEAD)
# ===============================
DOCTOR_INFO = {
    "name": "Dr. Aarav Mehta",
    "degree": "MD (Internal Medicine)",
    "clinic": "Sanjeevani Multispeciality Clinic",
    "reg_no": "MMC/2024/45821",
    "phone": "+91 98765 43210",
    "address": "Mumbai, Maharashtra",
}

# ===============================
# FONT MAP
# ===============================
FONT_MAP = {
    "hi": "NotoSansDevanagari-Regular.ttf",
    "mr": "NotoSansDevanagari-Regular.ttf",
    "gu": "NotoSansGujarati-Regular.ttf",
    "ta": "NotoSansTamil-Regular.ttf",
    "te": "NotoSansTelugu-Regular.ttf",
    "kn": "NotoSansKannada-Regular.ttf",
    "ml": "NotoSansMalayalam-Regular.ttf",
    "bn": "NotoSansBengali-Regular.ttf",
}

# ===============================
# FONT REGISTRATION
# ===============================
def register_font(language: str) -> str:
    if language == "en":
        return "Helvetica"

    font_file = FONT_MAP.get(language)
    if not font_file:
        return "Helvetica"

    font_path = os.path.join(FONTS_DIR, font_file)
    font_name = font_file.replace(".ttf", "")

    try:
        if font_name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(font_name, font_path))
        return font_name
    except Exception:
        return "Helvetica"

# ===============================
# SAFE TEXT
# ===============================
def safe_text(text):
    if not text:
        return "—"
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

# ===============================
# LETTERHEAD
# ===============================
def add_letterhead(story, font_name):
    styles = getSampleStyleSheet()

    title = ParagraphStyle(
        "title",
        fontName=font_name,
        fontSize=15,
        alignment=1,
        spaceAfter=4,
    )

    sub = ParagraphStyle(
        "sub",
        fontName=font_name,
        fontSize=10,
        alignment=1,
    )

    story.append(Paragraph(f"<b>{DOCTOR_INFO['name']}</b>", title))
    story.append(Paragraph(DOCTOR_INFO["degree"], sub))
    story.append(Paragraph(DOCTOR_INFO["clinic"], sub))
    story.append(
        Paragraph(
            f"Reg No: {DOCTOR_INFO['reg_no']} | {DOCTOR_INFO['phone']} | {DOCTOR_INFO['address']}",
            sub,
        )
    )

    story.append(Spacer(1, 10))

    story.append(
        Table(
            [[""]],
            colWidths=[480],
            style=[
                ("LINEBELOW", (0, 0), (-1, -1), 2, colors.HexColor("#2F80ED"))
            ],
        )
    )


# ===============================
# PDF GENERATOR
# ===============================
def generate_pdf(summary_json_path: str, language: str = "en") -> str:
    with open(summary_json_path, "r", encoding="utf-8") as f:
        summary = json.load(f)

    base_name = os.path.splitext(os.path.basename(summary_json_path))[0]
    pdf_path = os.path.join(PDF_DIR, f"{base_name}.pdf")

    font_name = register_font(language)

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    base_styles = getSampleStyleSheet()

    styles = {
        "heading": ParagraphStyle(
            "heading",
            parent=base_styles["Heading3"],
            fontName=font_name,
            fontSize=11,
            textColor=colors.HexColor("#2F80ED"),
            spaceBefore=12,
            spaceAfter=6,
        ),
        "normal": ParagraphStyle(
            "normal",
            parent=base_styles["Normal"],
            fontName=font_name,
            spaceAfter=4,
        ),
        "rx": ParagraphStyle(
            "rx",
            parent=base_styles["Normal"],
            fontName=font_name,
            leftIndent=18,
            spaceAfter=6,
        ),
    }

    story = []

    # Letterhead
    add_letterhead(story, font_name)

    def add_section(title, content, rx=False):
        story.append(Paragraph(f"<b>{safe_text(title)}</b>", styles["heading"]))
        story.append(Spacer(1, 4))

        if isinstance(content, list):
            if not content:
                story.append(Paragraph("—", styles["normal"]))
            else:
                for item in content:
                    style = styles["rx"] if rx else styles["normal"]
                    prefix = "• " if rx else ""
                    story.append(
                        Paragraph(prefix + safe_text(item), style)
                    )
        else:
            story.append(Paragraph(safe_text(content), styles["normal"]))
        story.append(Spacer(1, 14))

    # CONTENT
    add_section("Doctor Summary", summary.get("doctor_summary", ""))
    add_section("Symptoms", summary.get("symptoms", []))
    add_section("Patient History", summary.get("patient_history", []))
    add_section("Risk Factors", summary.get("risk_factors", []))
    add_section("Prescription", summary.get("prescription", []), rx=True)
    add_section("Advice", summary.get("advice", []))
    add_section("Recommended Action", summary.get("recommended_action", ""))

    # FOOTER
    signature_block = KeepTogether([
    Spacer(1, 30),

    Paragraph(
        f"Date: {datetime.now().strftime('%d %b %Y')}",
        ParagraphStyle(
            "date",
            fontName=font_name,
            fontSize=10,
            alignment=2,
        ),
    ),

    Spacer(1, 18),

    Paragraph(
        "Signature:",
        ParagraphStyle(
            "sign_label",
            fontName=font_name,
            fontSize=10,
            alignment=2,
        ),
    ),

    Spacer(1, 22),  # space for actual handwritten sign

    Paragraph(
        "______________________________",
        ParagraphStyle(
            "sign_line",
            fontName=font_name,
            fontSize=10,
            alignment=2,
        ),
    ),

    Spacer(1, 6),

    Paragraph(
        f"<b>{DOCTOR_INFO['name']}</b>",
        ParagraphStyle(
            "sign_name",
            fontName=font_name,
            fontSize=10,
            alignment=2,
        ),
    ),
])

    story.append(signature_block)



    doc.build(story)
    return pdf_path