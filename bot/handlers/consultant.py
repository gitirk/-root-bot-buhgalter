"""RAG-консультант: текст → поиск в ChromaDB → промпт с контекстом → ответ LLM."""

import io
import re

from aiogram import F, Router
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.services.chat_history import add_message, get_history
from bot.services.llm import ask_llm
from bot.services.ocr import process_document_photo
from bot.services.pdf_export import generate_pdf, generate_summary_prompt
from bot.services.rag import search_knowledge
from bot.services.stt import transcribe_voice

router = Router()

LONG_ANSWER_THRESHOLD = 3500
CAPTION_MAX_LEN = 1024

# Теги, которые поддерживает Telegram HTML
_ALLOWED_TAGS = re.compile(
    r"</?(?:b|strong|i|em|u|ins|s|strike|del|code|pre|a|blockquote|tg-spoiler)"
    r"(?:\s[^>]*)?>",
    re.IGNORECASE,
)


def _sanitize_html(text: str) -> str:
    """Оставляет только Telegram-совместимые HTML-теги."""
    # <li> → буллеты
    text = re.sub(r"<li[^>]*>", "\n• ", text, flags=re.IGNORECASE)
    # <br>, <p>, </p>, </li>, </ul>, </ol> → переносы строк
    text = re.sub(r"<(?:br|/p|/li|/ul|/ol|/div)[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<p[^>]*>", "\n", text, flags=re.IGNORECASE)
    # <h1>-<h6> → жирный текст
    text = re.sub(r"<h[1-6][^>]*>", "\n<b>", text, flags=re.IGNORECASE)
    text = re.sub(r"</h[1-6]>", "</b>\n", text, flags=re.IGNORECASE)
    # Удаляем все неподдерживаемые теги
    def _keep_allowed(m: re.Match) -> str:
        return m.group(0)
    # Сначала собираем допустимые теги, потом убираем остальные
    text = re.sub(r"<[^>]+>", lambda m: m.group(0) if _ALLOWED_TAGS.fullmatch(m.group(0)) else "", text)
    # Убираем множественные пустые строки
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

SYSTEM_PROMPT = (
    "Ты — опытный бухгалтер-консультант, специализирующийся на бухгалтерском "
    "и налоговом учёте в Иркутской области. Отвечай точно, со ссылками на НПА. "
    "Если информации недостаточно, скажи об этом. Ставки и коэффициенты — 2026 год. "
    "Отвечай на русском языке. Используй HTML-разметку для форматирования "
    "(<b>, <i>, <code>)."
)


@router.message(F.text == "📋 Консультация")
async def start_consultation(message: Message):
    await message.answer(
        "Задайте ваш вопрос по бухгалтерии, налогам или кадрам.\n"
        "Я найду информацию в базе знаний и дам развёрнутый ответ."
    )


# ─── Обработка фото документов (OCR) ────────

@router.message(F.photo)
async def handle_photo(message: Message):
    """Распознавание фото документа через Vision API."""
    await message.answer("🔍 Распознаю документ...")

    # Скачиваем фото максимального разрешения
    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    photo_bytes = await message.bot.download_file(file.file_path)
    image_data = photo_bytes.read()

    result = _sanitize_html(await process_document_photo(image_data))

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🧮 Расчёт НДС по документу",
            callback_data="ocr_calc_nds",
        )],
    ])

    # Сохраняем распознанный текст в caption для callback
    if len(result) > LONG_ANSWER_THRESHOLD:
        pdf_buf = generate_pdf(result, title="Распознанный документ")
        summary = _sanitize_html(await ask_llm(
            system="Кратко опиши содержимое распознанного документа в 2-3 предложениях (до 800 символов). "
                   "Укажи тип, номер, дату, сумму, НДС. Отвечай на русском. Используй HTML.",
            user=result,
        ))
        caption = f"📄 <b>Распознанный документ</b>\n\n{summary}"
        if len(caption) > CAPTION_MAX_LEN:
            caption = caption[: CAPTION_MAX_LEN - 3] + "..."

        try:
            await message.answer_document(
                document=BufferedInputFile(pdf_buf.read(), filename="document_ocr.pdf"),
                caption=caption,
                parse_mode="HTML",
                reply_markup=kb,
            )
        except Exception:
            pdf_buf.seek(0)
            await message.answer_document(
                document=BufferedInputFile(pdf_buf.read(), filename="document_ocr.pdf"),
                reply_markup=kb,
            )
            await message.answer(caption, parse_mode="HTML")
    else:
        await message.answer(result, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "ocr_calc_nds")
async def ocr_nds_hint(cb: CallbackQuery):
    """Подсказка по расчёту НДС после OCR."""
    await cb.message.answer(
        "Для расчёта НДС перейдите в 🧮 Калькулятор → 📦 НДС\n"
        "и введите сумму из распознанного документа."
    )
    await cb.answer()


# ─── Обработка PDF-документов ──────────────

@router.message(F.document)
async def handle_document(message: Message):
    """Извлечение текста из PDF и анализ через LLM."""
    doc = message.document
    mime = doc.mime_type or ""
    name = doc.file_name or ""

    if mime != "application/pdf" and not name.lower().endswith(".pdf"):
        await message.answer("📎 Пока поддерживается только формат PDF. Отправьте PDF-файл.")
        return

    await message.answer("📄 Читаю PDF-документ...")

    file = await message.bot.get_file(doc.file_id)
    file_data = await message.bot.download_file(file.file_path)
    pdf_bytes = file_data.read()

    # Извлекаем текст через pdfplumber
    import pdfplumber

    text_parts: list[str] = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
    except Exception as e:
        await message.answer(f"⚠️ Не удалось прочитать PDF: {e}")
        return

    if not text_parts:
        await message.answer(
            "⚠️ PDF не содержит текстового слоя (возможно, это скан).\n"
            "Попробуйте отправить документ как <b>фото</b> — я распознаю его через OCR.",
            parse_mode="HTML",
        )
        return

    extracted = "\n\n".join(text_parts)
    # Ограничиваем длину для LLM
    if len(extracted) > 15000:
        extracted = extracted[:15000] + "\n\n[...текст обрезан...]"

    pdf_system = (
        "Ты — опытный бухгалтер-консультант. Проанализируй содержимое документа. "
        "Определи тип документа, извлеки ключевые данные: номер, дату, контрагентов, "
        "суммы, НДС, позиции. Дай краткий анализ. "
        "Отвечай на русском. Используй HTML-разметку (<b>, <i>, <code>)."
    )

    result = _sanitize_html(await ask_llm(system=pdf_system, user=extracted))

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🧮 Расчёт НДС по документу",
            callback_data="ocr_calc_nds",
        )],
    ])

    if len(result) > LONG_ANSWER_THRESHOLD:
        pdf_buf = generate_pdf(result, title="Анализ документа")
        summary = _sanitize_html(await ask_llm(
            system="Кратко опиши содержимое документа в 2-3 предложениях (до 800 символов). "
                   "Укажи тип, номер, дату, сумму, НДС. Отвечай на русском. Используй HTML.",
            user=result,
        ))
        caption = f"📄 <b>Анализ документа</b>\n\n{summary}"
        if len(caption) > CAPTION_MAX_LEN:
            caption = caption[: CAPTION_MAX_LEN - 3] + "..."
        try:
            await message.answer_document(
                document=BufferedInputFile(pdf_buf.read(), filename="analysis.pdf"),
                caption=caption,
                parse_mode="HTML",
                reply_markup=kb,
            )
        except Exception:
            pdf_buf.seek(0)
            await message.answer_document(
                document=BufferedInputFile(pdf_buf.read(), filename="analysis.pdf"),
                reply_markup=kb,
            )
            await message.answer(caption, parse_mode="HTML")
    else:
        await message.answer(result, parse_mode="HTML", reply_markup=kb)


# ─── Обработка голосовых сообщений ─────────

@router.message(F.voice)
async def handle_voice(message: Message):
    """Распознавание голосового сообщения через Whisper API + консультация."""
    await message.answer("🎤 Распознаю голосовое сообщение...")

    file = await message.bot.get_file(message.voice.file_id)
    voice_data = await message.bot.download_file(file.file_path)
    audio_bytes = voice_data.read()

    text = await transcribe_voice(audio_bytes)
    if text.startswith("⚠️"):
        await message.answer(text)
        return

    await message.answer(f"📝 <b>Распознано:</b> {text}", parse_mode="HTML")
    await message.answer("⏳ Ищу информацию...")

    user_id = message.from_user.id
    add_message(user_id, "user", text)

    context_chunks = await search_knowledge(text)
    context = "\n\n---\n\n".join(context_chunks) if context_chunks else ""

    user_prompt = text
    if context:
        user_prompt = (
            f"Контекст из базы знаний:\n\n{context}\n\n---\n\n"
            f"Вопрос пользователя: {text}"
        )

    history = get_history(user_id)[:-1]  # без текущего сообщения — оно в user_prompt
    answer = _sanitize_html(await ask_llm(system=SYSTEM_PROMPT, user=user_prompt, history=history))
    add_message(user_id, "assistant", answer)

    if len(answer) > LONG_ANSWER_THRESHOLD:
        pdf_buf = generate_pdf(answer, title="Консультация бот-бухгалтера")
        summary = _sanitize_html(await ask_llm(
            system="Ты помощник. Сделай краткое саммари в 2-3 предложениях (до 800 символов). "
                   "Сохрани ключевые цифры и выводы. Отвечай на русском. Используй HTML.",
            user=answer,
        ))
        caption = f"📄 <b>Полный ответ — в PDF</b>\n\n{summary}"
        if len(caption) > CAPTION_MAX_LEN:
            caption = caption[: CAPTION_MAX_LEN - 3] + "..."
        try:
            await message.answer_document(
                document=BufferedInputFile(pdf_buf.read(), filename="consultation.pdf"),
                caption=caption,
                parse_mode="HTML",
            )
        except Exception:
            pdf_buf.seek(0)
            await message.answer_document(
                document=BufferedInputFile(pdf_buf.read(), filename="consultation.pdf"),
            )
            await message.answer(caption, parse_mode="HTML")
    else:
        await message.answer(answer, parse_mode="HTML")


# ─── Обработка текстовых вопросов (fallback) ─

@router.message(F.text)
async def handle_question(message: Message):
    """Обработка любого текстового сообщения как вопроса (fallback)."""
    await message.answer("⏳ Ищу информацию...")

    user_id = message.from_user.id
    add_message(user_id, "user", message.text)

    context_chunks = await search_knowledge(message.text)
    context = "\n\n---\n\n".join(context_chunks) if context_chunks else ""

    user_prompt = message.text
    if context:
        user_prompt = (
            f"Контекст из базы знаний:\n\n{context}\n\n---\n\n"
            f"Вопрос пользователя: {message.text}"
        )

    history = get_history(user_id)[:-1]  # без текущего сообщения — оно в user_prompt
    answer = _sanitize_html(await ask_llm(system=SYSTEM_PROMPT, user=user_prompt, history=history))
    add_message(user_id, "assistant", answer)

    if len(answer) > LONG_ANSWER_THRESHOLD:
        # Генерируем PDF
        pdf_buf = generate_pdf(answer, title="Консультация бот-бухгалтера")

        # Генерируем саммари
        summary = _sanitize_html(await ask_llm(
            system="Ты помощник. Сделай краткое саммари в 2-3 предложениях (до 800 символов). "
                   "Сохрани ключевые цифры и выводы. Отвечай на русском. Используй HTML.",
            user=answer,
        ))

        caption = f"📄 <b>Полный ответ — в PDF</b>\n\n{summary}"
        if len(caption) > CAPTION_MAX_LEN:
            caption = caption[: CAPTION_MAX_LEN - 3] + "..."

        try:
            await message.answer_document(
                document=BufferedInputFile(pdf_buf.read(), filename="consultation.pdf"),
                caption=caption,
                parse_mode="HTML",
            )
        except Exception:
            # Fallback: отправляем PDF без caption, затем текст отдельно
            pdf_buf.seek(0)
            await message.answer_document(
                document=BufferedInputFile(pdf_buf.read(), filename="consultation.pdf"),
            )
            await message.answer(caption, parse_mode="HTML")
    else:
        await message.answer(answer, parse_mode="HTML")
