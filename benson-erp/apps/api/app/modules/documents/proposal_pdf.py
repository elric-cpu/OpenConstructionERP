from io import BytesIO

from reportlab.lib.colors import Color, HexColor
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def render_proposal_pdf(context: dict) -> bytes:
    output = BytesIO()
    styles = getSampleStyleSheet()
    maroon = HexColor(context["primary_color"])
    story = [
        Paragraph(
            context["company_name"],
            ParagraphStyle("brand", parent=styles["Title"], textColor=maroon),
        ),
        Paragraph("CONSTRUCTION PROPOSAL", styles["Heading2"]),
        Spacer(1, 0.18 * inch),
        _summary_table(context, maroon),
        Spacer(1, 0.25 * inch),
        Paragraph("Scope of work", styles["Heading2"]),
    ]
    for line in context["lines"]:
        story.append(
            Paragraph(
                f'{line["description"]} — {line["quantity"]} {line["unit"]}',
                styles["BodyText"],
            )
        )
        story.append(Spacer(1, 0.06 * inch))
    story.extend(
        [
            Spacer(1, 0.18 * inch),
            Paragraph("Pricing", styles["Heading2"]),
            _price_table(context, maroon),
            Spacer(1, 0.25 * inch),
            Paragraph(
                "Next step: review this proposal and record acceptance in Benson Construction ERP. "
                "Any changes require a new proposal version.",
                styles["BodyText"],
            ),
        ]
    )
    document = SimpleDocTemplate(
        output,
        pagesize=LETTER,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
        title=f'Proposal {context["proposal_number"]}',
        author=context["company_name"],
    )
    document.build(story)
    return output.getvalue()


def _summary_table(context: dict, maroon: Color) -> Table:
    table = Table(
        [
            ["Proposal", context["proposal_number"], "Customer", context["customer_name"]],
            ["Property", context["property_address"], "Phone", context["company_phone"] or "—"],
        ],
        colWidths=[0.8 * inch, 2.25 * inch, 0.8 * inch, 2.25 * inch],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), maroon),
                ("BACKGROUND", (2, 0), (2, -1), maroon),
                ("TEXTCOLOR", (0, 0), (0, -1), HexColor("#FFFFFF")),
                ("TEXTCOLOR", (2, 0), (2, -1), HexColor("#FFFFFF")),
                ("GRID", (0, 0), (-1, -1), 0.4, HexColor("#B8B2A8")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def _price_table(context: dict, maroon: Color) -> Table:
    table = Table(
        [
            ["Contract price", f'${context["selling_price"]}'],
            ["Tax", f'${context["tax"]}'],
            ["Proposal total", f'${context["total"]}'],
        ],
        colWidths=[4.5 * inch, 1.6 * inch],
    )
    table.setStyle(
        TableStyle(
            [
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("LINEABOVE", (0, -1), (-1, -1), 1.2, maroon),
                ("TEXTCOLOR", (0, -1), (-1, -1), maroon),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ]
        )
    )
    return table
