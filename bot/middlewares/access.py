"""Middleware белого списка — пропускает только chat_id из ALLOWED_CHAT_IDS."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.config.settings import allowed_users


class AccessMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not allowed_users:
            return await handler(event, data)

        chat_id: Optional[int] = None
        if isinstance(event, Message):
            chat_id = event.chat.id
        elif isinstance(event, CallbackQuery) and event.message:
            chat_id = event.message.chat.id

        if chat_id is not None and chat_id not in allowed_users:
            if isinstance(event, Message):
                await event.answer(
                    "🚫 Доступ ограничен. Обратитесь к администратору "
                    "для получения доступа.\n\n"
                    f"Ваш ID: <code>{chat_id}</code>",
                    parse_mode="HTML",
                )
            return None

        return await handler(event, data)
