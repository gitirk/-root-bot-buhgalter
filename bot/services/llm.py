"""Единый интерфейс LLM — авто-выбор Anthropic или OpenAI по наличию ключа."""

import logging

from bot.config.settings import settings

logger = logging.getLogger(__name__)


async def ask_llm(
    system: str,
    user: str,
    history: list[dict[str, str]] | None = None,
) -> str:
    """Отправляет запрос в доступный LLM и возвращает ответ."""
    if settings.anthropic_api_key:
        return await _ask_anthropic(system, user, history)
    if settings.openai_api_key:
        return await _ask_openai(system, user, history)
    return (
        "⚠️ Не настроен API-ключ. "
        "Укажите OPENAI_API_KEY или ANTHROPIC_API_KEY в .env"
    )


async def _ask_anthropic(
    system: str, user: str, history: list[dict[str, str]] | None = None,
) -> str:
    import anthropic

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        messages = list(history or [])
        messages.append({"role": "user", "content": user})
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=system,
            messages=messages,
        )
        return response.content[0].text
    except Exception as e:
        logger.error("Anthropic API error: %s", e)
        return f"⚠️ Ошибка API: {e}"


async def _ask_openai(
    system: str, user: str, history: list[dict[str, str]] | None = None,
) -> str:
    from openai import AsyncOpenAI

    try:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        messages = [{"role": "system", "content": system}]
        messages.extend(history or [])
        messages.append({"role": "user", "content": user})
        response = await client.chat.completions.create(
            model="gpt-5.2",
            messages=messages,
            max_completion_tokens=4096,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error("OpenAI API error: %s", e)
        return f"⚠️ Ошибка API: {e}"
