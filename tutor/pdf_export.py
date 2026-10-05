"""Create readable interview revision notes without executing generated code."""

from html import escape
from io import BytesIO
from pathlib import Path
import textwrap

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle

from tutor.schemas import SCORING_RUBRIC, StudyNotes


def _fonts() -> tuple[str, str]:
    """Use familiar local fonts when available, with built-in fallbacks."""
    fonts = [
        ("TutorBody", "Helvetica", ["C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]),
        ("TutorCode", "Courier", ["C:/Windows/Fonts/consola.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]),
    ]
    selected = []
    for name, fallback, paths in fonts:
        for path in paths:
            if Path(path).is_file():
                if name not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont(name, path))
                selected.append(name)
                break
        else:
            selected.append(fallback)
    return tuple(selected)


def build_pdf(
    problem: str,
    level: str,
    company: str,
    messages: list[dict[str, str]],
    notes: StudyNotes | None,
    *,
    status: str,
    model_name: str,
    assessment_notice: str = "",
    source_url: str = "",
    source_title: str = "",
    question_count: int = 0,
    answered_count: int = 0,
    research_sources: list[dict[str, str]] | None = None,
) -> bytes:
    """Export supplied notes and chat; a missing summary produces a partial report."""
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=46, leftMargin=46,
        topMargin=46, bottomMargin=46, title="Interview revision notes",
        author="AI Interview Tutor",
    )
    body_font, code_font = _fonts()
    styles = getSampleStyleSheet()
    for name in ("Normal", "Title", "Heading1", "Heading2"):
        styles[name].fontName = body_font
    styles["Normal"].fontSize = 10
    styles["Normal"].leading = 15
    styles["Normal"].spaceAfter = 8
    styles.add(ParagraphStyle("KeepNext", parent=styles["Normal"], keepWithNext=True))
    styles["Heading1"].fontSize = 16
    styles["Heading1"].leading = 21
    styles["Heading1"].keepWithNext = True
    styles["Heading2"].fontSize = 12
    styles["Heading2"].leading = 17
    styles["Heading2"].keepWithNext = True
    code_style = ParagraphStyle(
        "Code", fontName=code_font, fontSize=8, leading=11,
        backColor=colors.HexColor("#f3f4f6"), borderPadding=6,
        spaceBefore=6, spaceAfter=12,
    )
    story = []

    def paragraph(value: str, style: str = "Normal") -> Paragraph:
        return Paragraph(escape(str(value)).replace("\n", "<br/>"), styles[style])

    def add(value: str, style: str = "Normal") -> None:
        story.append(paragraph(value, style))

    def heading(value: str) -> None:
        add(value, "Heading1")

    def add_code(value: str) -> None:
        # Wrap display lines only. Preformatted treats code as plain text.
        lines = []
        for line in value.expandtabs(4).splitlines():
            lines.extend(textwrap.wrap(
                line, width=88, replace_whitespace=False, drop_whitespace=False,
                break_long_words=True, break_on_hyphens=False,
            ) or [""])
        story.append(Preformatted("\n".join(lines), code_style))

    add("Interview revision notes", "Title")
    add(f"Level: {level} | Company context: {company or 'None'}")
    add(f"Generation: Live model | Model: {model_name} | Session status: {status}")
    add(f"Answers recorded: {answered_count}.")
    add("AI-generated notes are learning guidance. Scores reflect answers in this session "
        "and do not predict hiring readiness.")
    add("UNTESTED: Any submitted, generated, or further-practice code has not been executed. "
        "Correctness explanations are not verified test results.")
    if answered_count < question_count:
        add("PARTIAL INTERVIEW: The interview ended early; "
            "marks can cover only the recorded answers.")
    if notes is None:
        add("INCOMPLETE / PARTIAL REPORT: Final study notes are unavailable. "
            "The source material and conversation are preserved below.")

    heading("Source material")
    if source_title:
        add(source_title, "Heading2")
    if source_url:
        add(f"Source URL: {source_url}")
    add(problem)

    if research_sources:
        heading("Additional context sources")
        add("These sources were suggested by web search. Search snippets have not been "
            "independently verified. Linked pages were not automatically opened.")
        for source in research_sources:
            add(source.get("title") or "Search result", "Heading2")
            if source.get("url"):
                add(f"Source URL: {source['url']}")

    heading("Interview feedback")
    assessment = notes.assessment if notes is not None else None
    if assessment is None:
        add(assessment_notice or "Not assessed: No interview marks are available.")
    else:
        add("AI review of your interview answers: Marks reflect the evidence below, "
            "not hiring readiness. Any submitted code has not been executed.", "KeepNext")
        add(f"Total: {assessment.total}/10" if assessment.total is not None
            else "Partial review - no overall score", "Heading2")
        rows = [[paragraph("Criterion"), paragraph("Marks"),
                 paragraph("Feedback and evidence")]]
        for field, label, maximum in SCORING_RUBRIC:
            item = getattr(assessment, field)
            marks = "Not assessed" if item.marks is None else f"{item.marks}/{maximum}"
            feedback = f"Reason: {item.reason}\nEvidence: {item.evidence or 'No evidence provided.'}"
            rows.append([paragraph(label), paragraph(marks), paragraph(feedback)])
        table = Table(rows, colWidths=[document.width * .22, document.width * .16,
                                      document.width * .62], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e7eef8")),
            ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        story.extend([table, Spacer(1, 10)])
        story.append(KeepTogether([
            paragraph("Two things to improve", "Heading2"),
            *[paragraph(f"{number}. {improvement}")
              for number, improvement in enumerate(assessment.improvements, 1)],
        ]))

    if notes is not None:
        heading("Topic summary and assumptions")
        add(notes.summary)
        for item in notes.assumptions:
            add(f"- {item}")
        if not notes.assumptions:
            add("No additional assumptions were recorded.")

        heading("Key concepts")
        for concept in notes.key_concepts:
            add(f"- {concept}")
        if not notes.key_concepts:
            add("No key concepts were recorded.")

        for approach in notes.approaches:
            heading(approach.name)
            add(approach.intuition)
            add("Python code (untested)", "Heading2")
            add("Long lines are wrapped for display only.")
            add_code(approach.code)
            add("Worked example / dry run", "Heading2")
            add(approach.worked_example)
            add("Correctness reasoning", "Heading2")
            add(approach.correctness)
            add(f"Time complexity: {approach.time_complexity}")
            add(f"Space complexity: {approach.space_complexity}")

        if notes.approaches:
            heading("Approach comparison")
            rows = [[paragraph("Approach"), paragraph("Time"), paragraph("Space")]]
            rows += [[paragraph(a.name), paragraph(a.time_complexity),
                      paragraph(a.space_complexity)] for a in notes.approaches]
            table = Table(rows, colWidths=[document.width * .38, document.width * .31,
                                          document.width * .31], repeatRows=1)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e7eef8")),
                ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]))
            story.extend([table, Spacer(1, 10)])
        heading("Feedback and common mistakes")
        add(notes.feedback)
        for mistake in notes.common_mistakes:
            add(f"- {mistake}")
        heading("Further practice")
        add("Optional revision prompts for later practice; these are not additional interview questions.")
        for number, follow_up in enumerate(notes.follow_ups, 1):
            add(f"{number}. {follow_up.question}", "Heading2")
            add(follow_up.sketch)
        heading("Revision checklist")
        add("Review the key concepts; explain them in your own words; work through an example; "
            "revisit the feedback; practise the topics that were unclear.")
        if notes.approaches:
            add("For code: trace an example, identify edge cases, justify time and space costs, "
                "and test it before relying on it.")

    heading("Interview transcript")
    for message in messages:
        add(f"{message.get('role', 'message').capitalize()}: {message.get('content', '')}")
    if not messages:
        add("No chat messages were recorded.")

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(body_font, 8)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(46, 25, "Interview tutor | Learning feedback, not hiring readiness")
        canvas.drawRightString(A4[0] - 46, 25, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
