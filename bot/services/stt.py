"""Speech-to-Text через OpenAI Whisper API."""

import io
import logging

from bot.config.settings import settings

logger = logging.getLogger(__name__)


async def transcribe_voice(audio_bytes: bytes, filename: str = "voice.ogg") -> str:
    """Транскрибирует аудио через Whisper API и возвращает текст."""
    if not settings.openai_api_key:
        return "⚠️ Не настроен OpenAI API-ключ для распознавания голоса."

    from openai import AsyncOpenAI

    try:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = filename
        response = await client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="ru",
        )
        return response.text
    except Exception as e:
        logger.error("Whisper API error: %s", e)
        return f"⚠️ Ошибка распознавания голоса: {e}"
