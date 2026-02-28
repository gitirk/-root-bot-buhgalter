"""Генерация PDF для длинных ответов LLM. Шрифт DejaVu Sans (кириллица)."""

import io
import re
import textwrap

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

# ─── Регистрация кириллического шрифта ──────
_FONT_REGISTERED = False


def _register_fonts():
    global _FONT_REGISTERED
    if _FONT_REGISTERED:
        return
    # DejaVu Sans поставляется с большинством Linux-дистрибутивов
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    ):
        try:
            pdfmetrics.registerFont(TTFont("DejaVuSans", path))
            _FONT_REGISTERED = True
            return
        except Exception:
            continue
    # Fallback — попробуем найти через fc-match
    import subprocess

    try:
        result = subprocess.run(
            ["fc-match", "-f", "%{file}", "DejaVu Sans"],
            capture_output=True, text=True, timeout=5,
        )
        if result.stdout.strip():
            pdfmetrics.registerFont(TTFont("DejaVuSans", result.stdout.strip()))
            _FONT_REGISTERED = True
    except Exception:
        pass


def _strip_html(text: str) -> str:
    """Убирает HTML-теги для чистого текста в PDF."""
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return text


def generate_pdf(text: str, title: str = "Ответ бот-бухгалтера") -> io.BytesIO:
    """Генерирует PDF-документ с текстом. Возвращает BytesIO."""
    _register_fonts()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    font_name = "DejaVuSans" if _FONT_REGISTERED else "Helvetica"

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleRu",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=14,
        spaceAfter=12,
    )
    body_style = ParagraphStyle(
        "BodyRu",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=10,
        leading=14,
        spaceAfter=6,
    )

    story = []
    story.append(Paragraph(title, title_style))
    story.append(Spacer(1, 6 * mm))

    clean_text = _strip_html(text)
    for paragraph in clean_text.split("\n\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        # Заменяем одиночные переносы на <br/>
        paragraph = paragraph.replace("\n", "<br/>")
        # Экранируем спецсимволы XML
        paragraph = paragraph.replace("&", "&amp;").replace("<br/>", "<br/>")
        # Восстанавливаем <br/> после экранирования
        story.append(Paragraph(paragraph, body_style))

    doc.build(story)
    buf.seek(0)
    return buf


def generate_summary_prompt(text: str) -> str:
    """Промпт для генерации краткого саммари ответа."""
    return (
        "Сделай краткое саммари следующего текста в 3-5 предложениях. "
        "Саммари должно содержать ключевые цифры и выводы. "
        "Отвечай на русском. Используй HTML-разметку (<b>, <i>).\n\n"
        f"{text}"
    )
