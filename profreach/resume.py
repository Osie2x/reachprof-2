from pathlib import Path
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.enums import TA_LEFT
from .models import ExperienceBlock, StudentInfo


def render_resume(
    student: StudentInfo,
    ordered_blocks: list[ExperienceBlock],
    output_path: str | Path,
) -> Path:
    """Render a one-page PDF resume using reportlab (pure Python, no system deps)."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=LETTER,
        leftMargin=0.6*inch,
        rightMargin=0.6*inch,
        topMargin=0.6*inch,
        bottomMargin=0.6*inch,
    )

    styles = getSampleStyleSheet()
    name_style = ParagraphStyle("name", fontSize=18, spaceAfter=2)
    contact_style = ParagraphStyle("contact", fontSize=9.5, textColor="#555555", spaceAfter=10)
    section_style = ParagraphStyle("section", fontSize=11, spaceBefore=12, spaceAfter=6, fontName="Helvetica-Bold")
    job_title_style = ParagraphStyle("jobtitle", fontSize=10.5, fontName="Helvetica-Bold")
    bullet_style = ParagraphStyle("bullet", fontSize=10.5, leftIndent=16, spaceAfter=1.5)

    story = []

    story.append(Paragraph(student.name, name_style))
    contact_parts = [student.email, student.phone, student.location]
    if student.github:
        contact_parts.append(student.github)
    if student.linkedin:
        contact_parts.append(student.linkedin)
    story.append(Paragraph(" · ".join(filter(None, contact_parts)), contact_style))

    story.append(Paragraph("EXPERIENCE", section_style))

    for block in ordered_blocks:
        header = block.title
        if block.organization:
            header += f", {block.organization}"
        dates = block.dates or ""
        story.append(Paragraph(f"{header}  <font size=9 color='#555555'>{dates}</font>", job_title_style))
        for bullet in block.bullets:
            story.append(Paragraph(f"• {bullet}", bullet_style))
        story.append(Spacer(1, 4))

    doc.build(story)
    return output_path
