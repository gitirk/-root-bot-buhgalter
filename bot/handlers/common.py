"""Общие хендлеры: /start, /help, /add_user, /remove_user, /reindex, главное меню."""

import asyncio
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from bot.config.settings import allowed_users, save_users, settings
from bot.services.chat_history import clear_history

router = Router()

MAIN_MENU = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📋 Консультация"), KeyboardButton(text="🧮 Калькулятор")],
        [KeyboardButton(text="📄 Документы"), KeyboardButton(text="ℹ️ Справка")],
    ],
    resize_keyboard=True,
)

HELP_TEXT = (
    "<b>Бот-бухгалтер — Иркутская область</b>\n\n"
    "📋 <b>Консультация</b> — задайте любой вопрос по бухгалтерии, "
    "налогам, зарплате. Бот ищет ответ в базе знаний и формирует "
    "ответ с помощью ИИ.\n\n"
    "🧮 <b>Калькулятор</b> — расчёт зарплаты с РК и надбавкой, "
    "НДФЛ, страховых взносов, НДС, транспортного налога.\n\n"
    "📄 <b>Документы</b> — формирование первичных документов "
    "(счёт, акт, ТОРГ-12, расчётный листок).\n\n"
    "ℹ️ <b>Справка</b> — справочная информация по ставкам и срокам.\n\n"
    "Или просто напишите вопрос текстом — бот ответит как консультант."
)


@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "Здравствуйте! Я бот-бухгалтер для Иркутской области.\n"
        "Выберите раздел или задайте вопрос текстом.",
        reply_markup=MAIN_MENU,
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(HELP_TEXT, reply_markup=MAIN_MENU)


@router.message(Command("commands"))
async def cmd_commands(message: Message):
    text = (
        "<b>Список команд:</b>\n\n"
        "/start — запуск бота, главное меню\n"
        "/help — справка о возможностях бота\n"
        "/commands — список всех команд\n"
        "/clear — очистить историю диалога\n"
    )
    if _is_admin(message.from_user.id):
        text += (
            "\n<b>Команды администратора:</b>\n\n"
            "/add_user <code>ID</code> — добавить пользователя\n"
            "/remove_user <code>ID</code> — удалить пользователя\n"
            "/users — список пользователей\n"
            "/reindex — переиндексация базы знаний\n"
        )
    await message.answer(text, parse_mode="HTML")


@router.message(F.text == "ℹ️ Справка")
async def show_help(message: Message):
    await message.answer(HELP_TEXT, reply_markup=MAIN_MENU)


@router.message(Command("clear"))
async def cmd_clear(message: Message):
    clear_history(message.from_user.id)
    await message.answer("🗑 История диалога очищена.")


# ─── Управление доступом (только админ) ─────

def _is_admin(user_id: int) -> bool:
    return user_id == settings.admin_id


@router.message(Command("add_user"))
async def cmd_add_user(message: Message):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Эта команда доступна только администратору.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer(
            "Использование: /add_user <code>ID</code>\n"
            "Пример: /add_user 123456789",
            parse_mode="HTML",
        )
        return

    new_id = int(args[1].strip())
    if new_id in allowed_users:
        await message.answer(f"Пользователь <code>{new_id}</code> уже в списке.", parse_mode="HTML")
        return

    allowed_users.add(new_id)
    save_users()
    await message.answer(f"✅ Пользователь <code>{new_id}</code> добавлен.", parse_mode="HTML")


@router.message(Command("remove_user"))
async def cmd_remove_user(message: Message):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Эта команда доступна только администратору.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer(
            "Использование: /remove_user <code>ID</code>",
            parse_mode="HTML",
        )
        return

    rm_id = int(args[1].strip())
    if rm_id == settings.admin_id:
        await message.answer("⛔ Нельзя удалить администратора.")
        return

    if rm_id not in allowed_users:
        await message.answer(f"Пользователь <code>{rm_id}</code> не найден в списке.", parse_mode="HTML")
        return

    allowed_users.discard(rm_id)
    save_users()
    await message.answer(f"🗑 Пользователь <code>{rm_id}</code> удалён.", parse_mode="HTML")


@router.message(Command("users"))
async def cmd_list_users(message: Message):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Эта команда доступна только администратору.")
        return

    if not allowed_users:
        await message.answer("Белый список пуст — доступ открыт для всех.")
        return

    lines = [f"  <code>{uid}</code>" for uid in sorted(allowed_users)]
    await message.answer(
        f"<b>Белый список ({len(allowed_users)}):</b>\n" + "\n".join(lines),
        parse_mode="HTML",
    )


# ─── Переиндексация базы знаний (только админ) ─

@router.message(Command("reindex"))
async def cmd_reindex(message: Message):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Эта команда доступна только администратору.")
        return

    await message.answer("🔄 Переиндексация базы знаний...")

    from bot.services.rag import index_directory

    kb_path = Path("/app/knowledge_base")
    try:
        total = await asyncio.to_thread(index_directory, kb_path)
        await message.answer(
            f"✅ Готово. Проиндексировано <b>{total}</b> чанков.",
            parse_mode="HTML",
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка индексации: {e}")
