"""
Build PDFs from markdown files using reportlab.
Usage: uv run --with reportlab build_pdfs.py
"""

import re
from pathlib import Path
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.platypus import KeepTogether

BASE = Path(__file__).parent
PDF_DIR = BASE / "pdf"
PDF_DIR.mkdir(exist_ok=True)

GRAY = HexColor("#444444")
RULE = HexColor("#bbbbbb")


def build_styles(size="normal"):
    small = size == "small"

    base_size = 9.8 if small else 10.5
    lead = 13.8 if small else 15.5

    body = ParagraphStyle(
        "body",
        fontName="Times-Roman",
        fontSize=base_size,
        leading=lead,
        spaceAfter=4 if small else 8,
        textColor=HexColor("#111111"),
    )
    h1 = ParagraphStyle(
        "h1",
        fontName="Times-Bold",
        fontSize=26 if small else 22,
        leading=30 if small else 26,
        spaceAfter=2,
        textColor=HexColor("#111111"),
    )
    h2 = ParagraphStyle(
        "h2",
        fontName="Times-Bold",
        fontSize=9.5 if small else 10,
        leading=13,
        spaceBefore=6 if small else 14,
        spaceAfter=2,
        textColor=GRAY,
        letterSpacing=0.8,
    )
    h3 = ParagraphStyle(
        "h3",
        fontName="Times-Italic",
        fontSize=12 if small else 11,
        leading=16,
        spaceAfter=8 if small else 10,
        textColor=GRAY,
    )
    italic_close = ParagraphStyle(
        "italic_close",
        fontName="Times-Italic",
        fontSize=base_size,
        leading=lead,
        spaceAfter=4,
        textColor=HexColor("#333333"),
    )
    return {"body": body, "h1": h1, "h2": h2, "h3": h3, "italic_close": italic_close}


def md_inline(text):
    """Convert inline markdown (bold, italic) to reportlab XML."""
    # bold italic
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<b><i>\1</i></b>', text)
    # bold
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    # italic
    text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
    # em dash
    text = text.replace(' — ', ' \u2014 ')
    return text


def parse_md(md_text, styles, is_onepage=False):
    """Parse markdown into reportlab flowables."""
    flowables = []
    lines = md_text.strip().split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if not line:
            i += 1
            continue

        if line.startswith("# "):
            text = md_inline(line[2:])
            flowables.append(Paragraph(text, styles["h1"]))

        elif line.startswith("### "):
            text = md_inline(line[4:])
            flowables.append(Paragraph(text, styles["h3"]))

        elif line.startswith("## "):
            text = md_inline(line[3:].upper() if is_onepage else line[3:])
            flowables.append(Paragraph(text, styles["h2"]))

        elif line == "---":
            flowables.append(Spacer(1, 4))
            flowables.append(HRFlowable(width="100%", thickness=0.5, color=RULE))
            flowables.append(Spacer(1, 4))

        elif line.startswith("- "):
            # bullet list — collect consecutive bullets
            bullets = []
            while i < len(lines) and lines[i].strip().startswith("- "):
                bullets.append(lines[i].strip()[2:])
                i += 1
            for b in bullets:
                text = "\u2013\u2002" + md_inline(b)
                flowables.append(Paragraph(text, styles["body"]))
            continue

        else:
            # paragraph — check if it starts with italic (closing paragraph)
            if line.startswith("*") and line.endswith("*") and not line.startswith("**"):
                text = md_inline(line)
                flowables.append(Paragraph(text, styles["italic_close"]))
            else:
                text = md_inline(line)
                flowables.append(Paragraph(text, styles["body"]))

        i += 1

    return flowables


def make_pdf(md_path: Path, pdf_path: Path, onepage=False):
    margins = (0.75 * inch, 0.75 * inch) if onepage else (0.85 * inch, 0.9 * inch)
    page_w, page_h = LETTER
    usable_w = page_w - 2 * margins[0]
    usable_h = page_h - 2 * margins[1]

    size = "small" if onepage else "normal"
    styles = build_styles(size)
    md_text = md_path.read_text()
    flowables = parse_md(md_text, styles, is_onepage=onepage)

    if onepage:
        # Measure raw content height
        content_h = 0
        for f in flowables:
            w, h = f.wrap(usable_w, usable_h)
            content_h += h
            if hasattr(f, 'style'):
                content_h += getattr(f.style, 'spaceAfter', 0)
                content_h += getattr(f.style, 'spaceBefore', 0)

        surplus = usable_h - content_h

        # Count natural gap slots: after h1, after h3, between each section (before h2), after each hr
        # We have: h1, h3, hr, [h2, body...] x5, hr, body, italic = ~14 gap slots
        # Distribute surplus across those slots as equal padding
        gap_slots = 14
        extra = max(0, surplus / gap_slots)

        # Inject spacers at natural break points
        spaced = []
        for idx, f in enumerate(flowables):
            spaced.append(f)
            style_name = getattr(getattr(f, 'style', None), 'name', '')
            if style_name in ('h1', 'h3', 'h2') or isinstance(f, HRFlowable):
                spaced.append(Spacer(1, extra))

        flowables = spaced

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=LETTER,
        leftMargin=margins[0],
        rightMargin=margins[0],
        topMargin=margins[1],
        bottomMargin=margins[1],
        title="",
        author="",
        subject="",
        creator="",
    )
    doc.build(flowables)
    print(f"  wrote {pdf_path.name}")


if __name__ == "__main__":
    print("Building PDFs...")
    make_pdf(BASE / "time_and_clocks.md", PDF_DIR / "time_and_clocks.pdf", onepage=False)
    make_pdf(BASE / "time_and_clocks_onepage.md", PDF_DIR / "time_and_clocks_onepage.pdf", onepage=True)
    print("Done.")
