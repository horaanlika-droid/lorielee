#!/usr/bin/env python3
"""Build the Russian-language Laurie Lee personality report PDF."""

from __future__ import annotations

import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Frame,
    HRFlowable,
    Image,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "analysis"
SOURCE = ANALYSIS / "laurie_lee_personality.md"
OUTPUT = ANALYSIS / "laurie_lee_personality.pdf"
IMAGE_SOURCES = ANALYSIS / "images"
FONT_REGULAR = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
FONT_BOLD = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")

INK = colors.HexColor("#24323C")
MUTED = colors.HexColor("#66737A")
GREEN = colors.HexColor("#587461")
RUST = colors.HexColor("#B96E4C")
PAPER = colors.HexColor("#F5F2E9")
PALE_GREEN = colors.HexColor("#E8EEE8")
RULE = colors.HexColor("#D5DCD5")
WHITE = colors.white


def register_fonts() -> None:
    pdfmetrics.registerFont(TTFont("DejaVu", str(FONT_REGULAR)))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(FONT_BOLD)))
    pdfmetrics.registerFontFamily(
        "DejaVu", normal="DejaVu", bold="DejaVu-Bold",
        italic="DejaVu", boldItalic="DejaVu-Bold",
    )


def make_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="CoverKicker", fontName="DejaVu-Bold", fontSize=9, leading=12,
        textColor=GREEN, tracking=1.4, spaceAfter=10,
    ))
    styles.add(ParagraphStyle(
        name="CoverTitle", fontName="DejaVu-Bold", fontSize=31, leading=37,
        textColor=INK, spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="CoverSub", fontName="DejaVu", fontSize=15, leading=21,
        textColor=GREEN, spaceAfter=14,
    ))
    styles.add(ParagraphStyle(
        name="CoverNote", fontName="DejaVu", fontSize=9.3, leading=14,
        textColor=INK, alignment=TA_LEFT,
    ))
    styles.add(ParagraphStyle(
        name="CoverDate", fontName="DejaVu", fontSize=8.3, leading=12,
        textColor=MUTED, spaceBefore=8,
    ))
    styles.add(ParagraphStyle(
        name="H2Custom", fontName="DejaVu-Bold", fontSize=16, leading=21,
        textColor=INK, spaceBefore=11, spaceAfter=9, keepWithNext=True,
    ))
    styles.add(ParagraphStyle(
        name="AxisHead", fontName="DejaVu-Bold", fontSize=12.4, leading=16,
        textColor=GREEN, spaceBefore=13, spaceAfter=5, keepWithNext=True,
    ))
    styles.add(ParagraphStyle(
        name="SubHead", fontName="DejaVu-Bold", fontSize=8.8, leading=12,
        textColor=RUST, spaceBefore=7, spaceAfter=3, keepWithNext=True,
    ))
    styles.add(ParagraphStyle(
        name="BodyCustom", fontName="DejaVu", fontSize=9.1, leading=13.25,
        textColor=INK, alignment=TA_JUSTIFY, spaceAfter=6.2,
        allowWidows=0, allowOrphans=0,
    ))
    styles.add(ParagraphStyle(
        name="ListCustom", fontName="DejaVu", fontSize=8.9, leading=13,
        textColor=INK, leftIndent=13, firstLineIndent=-13, spaceAfter=5,
    ))
    styles.add(ParagraphStyle(
        name="Caption", fontName="DejaVu", fontSize=7.7, leading=10.5,
        textColor=MUTED, alignment=TA_LEFT, spaceBefore=4, spaceAfter=9,
    ))
    styles.add(ParagraphStyle(
        name="Small", fontName="DejaVu", fontSize=8.1, leading=11.5,
        textColor=MUTED, alignment=TA_LEFT,
    ))
    styles.add(ParagraphStyle(
        name="Callout", fontName="DejaVu", fontSize=8.7, leading=12.8,
        textColor=INK, alignment=TA_LEFT,
    ))
    return styles


def inline_markup(text: str) -> str:
    """Convert the small Markdown inline subset used in this report to XML."""
    links: list[str] = []

    def protect_link(match: re.Match) -> str:
        label = match.group(1)
        url = match.group(2)
        token = f"@@LINK{len(links)}@@"
        links.append(
            f'<link href="{html.escape(url, quote=True)}" color="#587461">'
            f"{label}</link>"
        )
        return token

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", protect_link, text)
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"`([^`]+)`", r'<font name="DejaVu-Bold">\1</font>', text)
    for i, link in enumerate(links):
        text = text.replace(f"@@LINK{i}@@", link)
    return text


def image_flowable(path: Path, max_width: float = 440, max_height: float = 300) -> Image:
    image = Image(str(path))
    scale = min(max_width / image.imageWidth, max_height / image.imageHeight, 1.0)
    image.drawWidth = image.imageWidth * scale
    image.drawHeight = image.imageHeight * scale
    image.hAlign = "CENTER"
    return image


def parse_body(markdown: str, styles) -> list:
    lines = markdown.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("## Краткий вывод"))
    lines = lines[start:]
    story = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        image_match = re.fullmatch(r"!\[(.*?)\]\((.*?)\)", line)
        if image_match:
            image_path = (ANALYSIS / image_match.group(2)).resolve()
            if not image_path.is_file():
                raise FileNotFoundError(image_path)
            story.extend([Spacer(1, 3), image_flowable(image_path), Spacer(1, 3)])
            i += 1
            continue

        heading = re.match(r"^(#{2,4})\s+(.+)$", line)
        if heading:
            level = len(heading.group(1))
            title = inline_markup(heading.group(2))
            if level == 2:
                story.extend([Spacer(1, 4), Paragraph(title, styles["H2Custom"]),
                              HRFlowable(width="100%", thickness=0.7, color=RULE,
                                         spaceBefore=0, spaceAfter=8)])
            elif level == 3:
                story.extend([CondPageBreak(88), Paragraph(title, styles["AxisHead"]),
                              HRFlowable(width="32%", thickness=1.2, color=GREEN,
                                         hAlign="LEFT", spaceBefore=0, spaceAfter=7)])
            else:
                story.append(Paragraph(title, styles["SubHead"]))
            i += 1
            continue

        if line.startswith("- "):
            item = inline_markup(line[2:])
            story.append(Paragraph(f'<font color="#B96E4C">•</font> {item}', styles["ListCustom"]))
            i += 1
            continue

        ordered = re.match(r"^(\d+)\.\s+(.+)$", line)
        if ordered:
            item = inline_markup(ordered.group(2))
            story.append(Paragraph(
                f'<font name="DejaVu-Bold" color="#587461">{ordered.group(1)}.</font> {item}',
                styles["ListCustom"],
            ))
            i += 1
            continue

        paragraph = [line]
        i += 1
        while i < len(lines):
            candidate = lines[i].strip()
            if (not candidate or candidate.startswith("!") or
                    re.match(r"^#{2,4}\s+", candidate) or candidate.startswith("- ") or
                    re.match(r"^\d+\.\s+", candidate)):
                break
            paragraph.append(candidate)
            i += 1
        text = inline_markup(" ".join(paragraph))
        # The short italic paragraphs immediately after images are used as photo captions.
        if len(paragraph) == 1 and paragraph[0].startswith("*") and paragraph[0].endswith("*"):
            story.append(Paragraph(text, styles["Caption"]))
        else:
            story.append(Paragraph(text, styles["BodyCustom"]))
    return story


def draw_page(canvas, doc) -> None:
    canvas.saveState()
    width, height = A4
    if doc.page == 1:
        canvas.setFillColor(PAPER)
        canvas.rect(0, 0, width, height, fill=1, stroke=0)
        canvas.setFillColor(GREEN)
        canvas.rect(0, 0, 7, height, fill=1, stroke=0)
    else:
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.55)
        canvas.line(47, height - 38, width - 47, height - 38)
        canvas.setFont("DejaVu-Bold", 7.2)
        canvas.setFillColor(GREEN)
        canvas.drawString(47, height - 29, "ЛОРИ ЛИ  /  ДОКУМЕНТАЛЬНЫЙ ПОРТРЕТ")
        canvas.setStrokeColor(RULE)
        canvas.line(47, 35, width - 47, 35)
        canvas.setFont("DejaVu", 7.4)
        canvas.setFillColor(MUTED)
        canvas.drawString(47, 22, "Предварительный разбор · первичные тексты запрошены")
        canvas.drawRightString(width - 47, 22, f"{doc.page:02d}")
    canvas.restoreState()


def make_cover(styles) -> list:
    page_width, _ = A4
    available = page_width - 96
    slad = image_flowable(IMAGE_SOURCES / "slad-village-ian-hunter.jpg",
                          max_width=available, max_height=325)
    metrics = Table(
        [[
            Paragraph('<font name="DejaVu-Bold" color="#587461">9</font><br/><font size="7">ОСЕЙ РАЗБОРА</font>', styles["Callout"]),
            Paragraph('<font name="DejaVu-Bold" color="#587461">1</font><br/><font size="7">ЛОКАЛЬНАЯ БИОГРАФИЯ</font>', styles["Callout"]),
            Paragraph('<font name="DejaVu-Bold" color="#587461">4</font><br/><font size="7">ТЕКСТА ЛИ ПРОЧИТАНО В ОТКРЫТОМ ДОСТУПЕ</font>', styles["Callout"]),
        ]],
        colWidths=[available / 3] * 3,
    )
    metrics.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE_GREEN),
        ("BOX", (0, 0), (-1, -1), 0.5, RULE),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, WHITE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    return [
        Spacer(1, 15),
        Paragraph("АРХИВНО-БИОГРАФИЧЕСКИЙ РАЗБОР", styles["CoverKicker"]),
        Paragraph("Лори Ли", styles["CoverTitle"]),
        Paragraph("Личность между памятью, домом и дорогой", styles["CoverSub"]),
        HRFlowable(width="100%", thickness=1.2, color=RUST, spaceBefore=0, spaceAfter=15),
        slad,
        Paragraph("Слэд с дороги на Страуд · Ian Hunter · CC BY-SA 2.0", styles["Caption"]),
        Spacer(1, 3),
        Paragraph(
            "Девять осей: от дома Энни и ухода из Слэда до памяти, братского молчания "
            "и умения слушать. Основа — биография Валери Гроув; это предварительный "
            "разбор, не диагноз и не близкое чтение книг Ли.",
            styles["CoverNote"],
        ),
        Spacer(1, 14),
        metrics,
        Paragraph("Редакция от 16 октября 2026 · тексты произведений запрошены", styles["CoverDate"]),
        PageBreak(),
    ]


def build() -> Path:
    if not FONT_REGULAR.is_file() or not FONT_BOLD.is_file():
        raise FileNotFoundError("DejaVu Sans regular and bold fonts are required for Cyrillic output")
    register_fonts()
    styles = make_styles()
    markdown = SOURCE.read_text(encoding="utf-8")

    page_width, page_height = A4
    left = right = 47
    bottom = 43
    top = 52
    frame = Frame(left, bottom, page_width - left - right,
                  page_height - top - bottom, leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0, id="report-frame")
    doc = BaseDocTemplate(
        str(OUTPUT), pagesize=A4, leftMargin=left, rightMargin=right,
        topMargin=top, bottomMargin=bottom, title="Лори Ли: личность между памятью, домом и дорогой",
        author="Редакционный разбор", subject="Биографический анализ на основе Валери Гроув",
        pageCompression=1,
    )
    doc.addPageTemplates([PageTemplate(id="report", frames=[frame], onPage=draw_page)])
    story = make_cover(styles)
    story.extend(parse_body(markdown, styles))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc.build(story)
    return OUTPUT


if __name__ == "__main__":
    print("written:", build().relative_to(ROOT))
