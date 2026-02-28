"""Заглушка модуля документов — меню с типами документов."""

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

router = Router()


def docs_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📃 Счёт на оплату", callback_data="doc_invoice")],
        [InlineKeyboardButton(text="✅ Акт выполненных работ", callback_data="doc_act")],
        [InlineKeyboardButton(text="📦 ТОРГ-12", callback_data="doc_torg12")],
        [InlineKeyboardButton(text="💰 Расчётный листок", callback_data="doc_payslip")],
    ])


@router.message(F.text == "📄 Документы")
async def show_docs_menu(message: Message):
    await message.answer(
        "Выберите документ для формирования:", reply_markup=docs_menu_kb()
    )


@router.callback_query(F.data.startswith("doc_"))
async def doc_stub(cb: CallbackQuery):
    names = {
        "doc_invoice": "Счёт на оплату",
        "doc_act": "Акт выполненных работ",
        "doc_torg12": "ТОРГ-12",
        "doc_payslip": "Расчётный листок",
    }
    name = names.get(cb.data, "Документ")
    await cb.message.edit_text(
        f"🚧 <b>{name}</b>\n\n"
        "Модуль формирования документов в разработке.\n"
        "В следующей версии здесь будет генерация "
        "документа в формате Excel/PDF с учётом РК и надбавок "
        "Иркутской области."
    )
    await cb.answer()
