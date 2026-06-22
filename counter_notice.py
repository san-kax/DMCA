from io import BytesIO
from datetime import date

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    HRFlowable,
    ListFlowable,
    ListItem,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT


def generate_counter_notice(notice_data: dict, company_info: dict) -> bytes:
    """Generate a DMCA Counter-Notice PDF and return it as bytes."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=inch,
        leftMargin=inch,
        topMargin=inch,
        bottomMargin=inch,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "DMCATitle",
        parent=styles["Heading1"],
        fontSize=20,
        textColor=colors.HexColor("#1a365d"),
        alignment=TA_CENTER,
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontSize=11,
        textColor=colors.HexColor("#4a5568"),
        alignment=TA_CENTER,
        spaceAfter=20,
    )
    section_header_style = ParagraphStyle(
        "SectionHeader",
        parent=styles["Heading2"],
        fontSize=12,
        textColor=colors.HexColor("#2d3748"),
        spaceBefore=16,
        spaceAfter=6,
        borderPad=4,
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=10,
        leading=16,
        textColor=colors.HexColor("#2d3748"),
    )
    label_style = ParagraphStyle(
        "Label",
        parent=styles["Normal"],
        fontSize=10,
        leading=16,
        textColor=colors.HexColor("#718096"),
    )
    legal_style = ParagraphStyle(
        "Legal",
        parent=styles["Normal"],
        fontSize=9,
        leading=14,
        textColor=colors.HexColor("#4a5568"),
        borderColor=colors.HexColor("#e2e8f0"),
        borderWidth=1,
        borderPad=8,
        backColor=colors.HexColor("#f7fafc"),
    )

    today = date.today().strftime("%B %d, %Y")

    # Company info with fallbacks
    name = company_info.get("name") or "[Your Name / Company Name]"
    address = company_info.get("address") or "[Your Address]"
    phone = company_info.get("phone") or "[Your Phone Number]"
    email = company_info.get("email") or "[Your Email Address]"

    # Notice details with fallbacks
    notice_id = notice_data.get("id") or "[Notice ID]"
    lumen_url = notice_data.get("lumen_url") or ""
    recipient = notice_data.get("recipient_name") or "Google LLC"
    notice_content = notice_data.get("content") or ""
    affected_url = notice_data.get("affected_url") or ""
    affected_urls = [affected_url] if affected_url else []

    story = []

    # --- Header ---
    story.append(Paragraph("DMCA Counter-Notice", title_style))
    story.append(Paragraph(f"Pursuant to 17 U.S.C. § 512(g)(3)", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#2b6cb0")))
    story.append(Spacer(1, 14))

    # Date
    story.append(Paragraph(f"<b>Date:</b> {today}", body_style))
    story.append(Spacer(1, 10))

    # --- Sender Information ---
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0")))
    story.append(Paragraph("Sender Information", section_header_style))

    info_lines = [
        ("Name / Company", name),
        ("Address", address),
        ("Phone", phone),
        ("Email", email),
    ]
    for label, value in info_lines:
        story.append(Paragraph(f'<font color="#718096">{label}:</font>  {value}', body_style))
    story.append(Spacer(1, 10))

    # --- Re: DMCA Notice ---
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0")))
    story.append(Paragraph("Re: DMCA Takedown Notice", section_header_style))

    story.append(Paragraph(f'<font color="#718096">Lumen Notice ID:</font>  {notice_id}', body_style))
    story.append(Paragraph(f'<font color="#718096">Filed With:</font>  {recipient}', body_style))
    if lumen_url:
        story.append(Paragraph(f'<font color="#718096">Lumen Record:</font>  {lumen_url}', body_style))
    if notice_content:
        story.append(Spacer(1, 6))
        story.append(Paragraph(f'<i><font color="#718096">{notice_content}</font></i>', body_style))
    story.append(Spacer(1, 10))

    # --- Affected URLs ---
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0")))
    story.append(Paragraph("Affected URLs", section_header_style))

    if affected_urls:
        url_items = [
            ListItem(Paragraph(u, body_style), leftIndent=20, bulletColor=colors.HexColor("#2b6cb0"))
            for u in affected_urls
        ]
        story.append(ListFlowable(url_items, bulletType="bullet", leftIndent=20))
    else:
        story.append(Paragraph("[No specific URLs listed in the notice]", body_style))
    story.append(Spacer(1, 10))

    # --- Legal Statements ---
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0")))
    story.append(Paragraph("Counter-Notice Statement", section_header_style))

    statements = [
        (
            "Good Faith Belief",
            "I have a good faith belief that the material was removed or disabled as a result of "
            "mistake or misidentification of the material to be removed or disabled.",
        ),
        (
            "Consent to Jurisdiction",
            "I consent to the jurisdiction of the Federal District Court for the judicial district "
            "in which my address is located, or if my address is outside of the United States, "
            "the judicial district in which the service provider may be found, and will accept "
            "service of process from the claimant.",
        ),
        (
            "Accuracy and Good Faith",
            "I swear, under penalty of perjury, that I have a good faith belief that the material "
            "identified above was removed or disabled as a result of a mistake or misidentification "
            "of the material to be removed or disabled.",
        ),
        (
            "Authorization",
            "I am the owner, or an agent authorized to act on behalf of the owner, of an exclusive "
            "right that is allegedly infringed.",
        ),
    ]

    for heading, text in statements:
        story.append(
            Paragraph(
                f"<b>{heading}:</b> {text}",
                legal_style,
            )
        )
        story.append(Spacer(1, 6))

    story.append(Spacer(1, 20))

    # --- Signature ---
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0")))
    story.append(Paragraph("Signature", section_header_style))

    story.append(Spacer(1, 30))
    story.append(
        Paragraph(
            "_" * 55 + f"&nbsp;&nbsp;&nbsp;&nbsp;Date: {today}",
            body_style,
        )
    )
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"Signature of {name}", label_style))
    story.append(Spacer(1, 30))
    story.append(
        Paragraph(
            "_" * 55,
            body_style,
        )
    )
    story.append(Spacer(1, 6))
    story.append(Paragraph("Printed Name", label_style))

    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cbd5e0")))
    story.append(Spacer(1, 6))
    story.append(
        Paragraph(
            "<i>This counter-notice is provided pursuant to the Digital Millennium Copyright Act "
            "(17 U.S.C. § 512). Please consult a qualified attorney before submitting this notice.</i>",
            ParagraphStyle(
                "Disclaimer",
                parent=styles["Normal"],
                fontSize=8,
                textColor=colors.HexColor("#a0aec0"),
                alignment=TA_CENTER,
            ),
        )
    )

    doc.build(story)
    buffer.seek(0)
    return buffer.read()
