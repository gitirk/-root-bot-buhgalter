"""OCR через Vision API — распознавание бухгалтерских документов."""

import base64
import io
import logging

from PIL import Image

from bot.config.settings import settings

logger = logging.getLogger(__name__)

MAX_IMAGE_SIDE = 1280  # макс. сторона в пикселях


def _compress_image(image_bytes: bytes) -> bytes:
    """Сжимает изображение до MAX_IMAGE_SIDE и качества 85% JPEG."""
    img = Image.open(io.BytesIO(image_bytes))
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > MAX_IMAGE_SIDE:
        ratio = MAX_IMAGE_SIDE / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()

OCR_SYSTEM_PROMPT = (
    "Ты — OCR-система для бухгалтерских документов. "
    "Извлеки из изображения следующую информацию:\n"
    "• Тип документа (счёт, акт, ТОРГ-12, счёт-фактура, УПД, платёжка и т.д.)\n"
    "• Номер документа\n"
    "• Дата документа\n"
    "• Контрагент (поставщик / покупатель)\n"
    "• Сумма\n"
    "• НДС (сумма и ставка)\n"
    "• Позиции (наименование, количество, цена, сумма)\n\n"
    "Верни структурированный текст на русском языке. "
    "Используй HTML-разметку (<b>, <i>, <code>) для форматирования. "
    "Если какие-то поля не удаётся распознать, укажи «не распознано»."
)


async def process_document_photo(image_bytes: bytes) -> str:
    """Отправляет изображение в Vision API и возвращает распознанный текст."""
    if settings.anthropic_api_key:
        return await _ocr_anthropic(image_bytes)
    if settings.openai_api_key:
        return await _ocr_openai(image_bytes)
    return "⚠️ Не настроен API-ключ для распознавания изображений."


async def _ocr_openai(image_bytes: bytes) -> str:
    from openai import AsyncOpenAI

    try:
        compressed = _compress_image(image_bytes)
        b64 = base64.b64encode(compressed).decode("utf-8")
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.chat.completions.create(
            model="gpt-5.2",
            messages=[
                {"role": "system", "content": OCR_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Распознай этот бухгалтерский документ.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64}",
                                "detail": "auto",
                            },
                        },
                    ],
                },
            ],
            max_completion_tokens=4096,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error("OpenAI Vision API error: %s", e)
        return f"⚠️ Ошибка распознавания: {e}"


async def _ocr_anthropic(image_bytes: bytes) -> str:
    import anthropic

    try:
        compressed = _compress_image(image_bytes)
        b64 = base64.b64encode(compressed).decode("utf-8")
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=OCR_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Распознай этот бухгалтерский документ.",
                        },
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": b64,
                            },
                        },
                    ],
                },
            ],
        )
        return response.content[0].text
    except Exception as e:
        logger.error("Anthropic Vision API error: %s", e)
        return f"⚠️ Ошибка распознавания: {e}"
