"""Калькуляторы — FSM + InlineKeyboard для 6 типов расчётов."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.config.rates import TERRITORY_GROUPS, USN_REGIONAL
from bot.services.calculators import (
    calc_insurance_contributions,
    calc_nds,
    calc_ndfl_progressive,
    calc_salary,
    calc_transport_tax,
)
from bot.services.excel_export import (
    export_contributions_report,
    export_ndfl_report,
    export_salary_report,
)

router = Router()


# ─── FSM States ──────────────────────────────

class SalaryCalc(StatesGroup):
    territory = State()
    salary = State()
    nadbavka_pct = State()


class NDFLCalc(StatesGroup):
    income = State()


class InsuranceCalc(StatesGroup):
    monthly_salary = State()


class NDSCalc(StatesGroup):
    rate = State()
    amount = State()


class TransportCalc(StatesGroup):
    vehicle_type = State()
    horsepower = State()


# ─── Keyboards ───────────────────────────────

def calc_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Зарплата с РК", callback_data="calc_salary")],
        [InlineKeyboardButton(text="📊 НДФЛ 2026", callback_data="calc_ndfl")],
        [InlineKeyboardButton(text="🏥 Страховые взносы", callback_data="calc_insurance")],
        [InlineKeyboardButton(text="📦 НДС", callback_data="calc_nds")],
        [InlineKeyboardButton(text="🚗 Транспортный налог ИО", callback_data="calc_transport")],
        [InlineKeyboardButton(text="📋 УСН (Ирк. обл.)", callback_data="calc_usn")],
    ])


def territory_kb() -> InlineKeyboardMarkup:
    buttons = []
    for key, group in TERRITORY_GROUPS.items():
        label = f"{key}: {group['name']} (РК {group['rk']})"
        buttons.append(
            [InlineKeyboardButton(text=label, callback_data=f"terr_{key}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def vehicle_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚗 Легковой", callback_data="veh_car")],
        [InlineKeyboardButton(text="🚚 Грузовой", callback_data="veh_truck")],
        [InlineKeyboardButton(text="🚌 Автобус", callback_data="veh_bus")],
        [InlineKeyboardButton(text="🏍 Мотоцикл", callback_data="veh_motorcycle")],
    ])


def nds_rate_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="22% (основная)", callback_data="nds_22")],
        [InlineKeyboardButton(text="10% (льготная)", callback_data="nds_10")],
        [InlineKeyboardButton(text="5% (УСН до 250 млн)", callback_data="nds_5")],
        [InlineKeyboardButton(text="7% (УСН 250–450 млн)", callback_data="nds_7")],
    ])


def _excel_kb(callback_data: str) -> InlineKeyboardMarkup:
    """Inline-кнопка 'Скачать Excel'."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Скачать Excel", callback_data=callback_data)],
    ])


# ─── Вход в калькулятор ──────────────────────

@router.message(F.text == "🧮 Калькулятор")
async def show_calc_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Выберите калькулятор:", reply_markup=calc_menu_kb())


# ─── ЗАРПЛАТА ────────────────────────────────

@router.callback_query(F.data == "calc_salary")
async def salary_start(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text(
        "Выберите группу территорий Иркутской области:",
        reply_markup=territory_kb(),
    )
    await state.set_state(SalaryCalc.territory)
    await cb.answer()


@router.callback_query(SalaryCalc.territory, F.data.startswith("terr_"))
async def salary_territory(cb: CallbackQuery, state: FSMContext):
    group_key = cb.data.replace("terr_", "")
    await state.update_data(territory=group_key)
    await cb.message.edit_text("Введите оклад (руб.):")
    await state.set_state(SalaryCalc.salary)
    await cb.answer()


@router.message(SalaryCalc.salary)
async def salary_amount(message: Message, state: FSMContext):
    try:
        salary = int(message.text.replace(" ", "").replace(",", ".").split(".")[0])
    except (ValueError, IndexError):
        await message.answer("Введите число, например: 50000")
        return
    await state.update_data(salary=salary)
    group_data = await state.get_data()
    group = TERRITORY_GROUPS.get(group_data["territory"], {})
    max_nadb = int(group.get("max_nadbavka", 0) * 100)
    await message.answer(
        f"Введите фактический % северной надбавки (0–{max_nadb}).\n"
        f"Максимум для этой территории: {max_nadb}%"
    )
    await state.set_state(SalaryCalc.nadbavka_pct)


@router.message(SalaryCalc.nadbavka_pct)
async def salary_result(message: Message, state: FSMContext):
    try:
        nadbavka_pct = int(message.text.replace("%", "").strip())
    except ValueError:
        await message.answer("Введите число от 0 до 80, например: 30")
        return
    data = await state.get_data()
    result = calc_salary(data["territory"], data["salary"], nadbavka_pct)

    # Сохраняем параметры для Excel
    await state.update_data(nadbavka_pct=nadbavka_pct, calc_type="salary")

    await message.answer(result, parse_mode="HTML", reply_markup=_excel_kb("excel_salary"))


@router.callback_query(F.data == "excel_salary")
async def excel_salary(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    territory = data.get("territory", "Д")
    salary = data.get("salary", 0)
    nadbavka = data.get("nadbavka_pct", 0)

    buf = export_salary_report(territory, salary, nadbavka)
    await cb.message.answer_document(
        document=BufferedInputFile(buf.read(), filename="salary_report.xlsx"),
        caption="📊 Расчёт зарплаты — Excel",
    )
    await cb.answer()
    await state.clear()


# ─── НДФЛ ────────────────────────────────────

@router.callback_query(F.data == "calc_ndfl")
async def ndfl_start(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("Введите годовой доход (руб.):")
    await state.set_state(NDFLCalc.income)
    await cb.answer()


@router.message(NDFLCalc.income)
async def ndfl_result(message: Message, state: FSMContext):
    try:
        income = int(message.text.replace(" ", "").replace(",", ".").split(".")[0])
    except (ValueError, IndexError):
        await message.answer("Введите число, например: 3000000")
        return

    await state.update_data(income=income, calc_type="ndfl")

    result = calc_ndfl_progressive(income)
    await message.answer(result, parse_mode="HTML", reply_markup=_excel_kb("excel_ndfl"))


@router.callback_query(F.data == "excel_ndfl")
async def excel_ndfl(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    income = data.get("income", 0)

    buf = export_ndfl_report(income)
    await cb.message.answer_document(
        document=BufferedInputFile(buf.read(), filename="ndfl_report.xlsx"),
        caption="📊 НДФЛ 2026 — Excel",
    )
    await cb.answer()
    await state.clear()


# ─── СТРАХОВЫЕ ВЗНОСЫ ────────────────────────

@router.callback_query(F.data == "calc_insurance")
async def insurance_start(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text(
        "Введите ежемесячную начисленную зарплату (руб.):\n"
        "(включая РК и надбавку)"
    )
    await state.set_state(InsuranceCalc.monthly_salary)
    await cb.answer()


@router.message(InsuranceCalc.monthly_salary)
async def insurance_result(message: Message, state: FSMContext):
    try:
        salary = int(message.text.replace(" ", "").replace(",", ".").split(".")[0])
    except (ValueError, IndexError):
        await message.answer("Введите число, например: 100000")
        return

    await state.update_data(monthly_salary=salary, calc_type="insurance")

    result = calc_insurance_contributions(salary)
    await message.answer(result, parse_mode="HTML", reply_markup=_excel_kb("excel_insurance"))


@router.callback_query(F.data == "excel_insurance")
async def excel_insurance(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    salary = data.get("monthly_salary", 0)

    buf = export_contributions_report(salary)
    await cb.message.answer_document(
        document=BufferedInputFile(buf.read(), filename="insurance_report.xlsx"),
        caption="📊 Страховые взносы 2026 — Excel",
    )
    await cb.answer()
    await state.clear()


# ─── НДС ─────────────────────────────────────

@router.callback_query(F.data == "calc_nds")
async def nds_start(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("Выберите ставку НДС:", reply_markup=nds_rate_kb())
    await state.set_state(NDSCalc.rate)
    await cb.answer()


@router.callback_query(NDSCalc.rate, F.data.startswith("nds_"))
async def nds_rate_chosen(cb: CallbackQuery, state: FSMContext):
    rate_map = {"nds_22": 22, "nds_10": 10, "nds_5": 5, "nds_7": 7}
    rate = rate_map.get(cb.data, 22)
    await state.update_data(rate=rate)
    await cb.message.edit_text("Введите сумму без НДС (руб.):")
    await state.set_state(NDSCalc.amount)
    await cb.answer()


@router.message(NDSCalc.amount)
async def nds_result(message: Message, state: FSMContext):
    try:
        amount = int(message.text.replace(" ", "").replace(",", ".").split(".")[0])
    except (ValueError, IndexError):
        await message.answer("Введите число, например: 500000")
        return
    data = await state.get_data()
    result = calc_nds(amount, data["rate"])
    await message.answer(result, parse_mode="HTML")
    await state.clear()


# ─── ТРАНСПОРТНЫЙ НАЛОГ ──────────────────────

@router.callback_query(F.data == "calc_transport")
async def transport_start(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("Выберите тип ТС:", reply_markup=vehicle_type_kb())
    await state.set_state(TransportCalc.vehicle_type)
    await cb.answer()


@router.callback_query(TransportCalc.vehicle_type, F.data.startswith("veh_"))
async def transport_vehicle(cb: CallbackQuery, state: FSMContext):
    vtype = cb.data.replace("veh_", "")
    await state.update_data(vehicle_type=vtype)
    await cb.message.edit_text("Введите мощность двигателя (л.с.):")
    await state.set_state(TransportCalc.horsepower)
    await cb.answer()


@router.message(TransportCalc.horsepower)
async def transport_result(message: Message, state: FSMContext):
    try:
        hp = int(message.text.replace(" ", ""))
    except ValueError:
        await message.answer("Введите число, например: 150")
        return
    data = await state.get_data()
    result = calc_transport_tax(data["vehicle_type"], hp)
    await message.answer(result, parse_mode="HTML")
    await state.clear()


# ─── УСН (заглушка) ─────────────────────────

@router.callback_query(F.data == "calc_usn")
async def usn_info(cb: CallbackQuery):
    text = (
        "<b>УСН — Иркутская область</b>\n"
        "Закон ИО от 30.11.2015 № 112-ОЗ\n\n"
        f"<b>Доходы:</b>\n"
        f"  Стандартная: {USN_REGIONAL['income_standard'] * 100}%\n"
        f"  Льготная: {USN_REGIONAL['income_reduced'] * 100}%\n\n"
        f"<b>Доходы минус расходы:</b>\n"
        f"  Стандартная: {USN_REGIONAL['income_expense_standard'] * 100}%\n"
        f"  Льготная: {USN_REGIONAL['income_expense_reduced'] * 100}%\n\n"
        f"Доля льготной деятельности: ≥{USN_REGIONAL['min_revenue_share'] * 100}%\n\n"
        "<b>Льготные виды деятельности:</b>\n"
        "• Обрабатывающие производства (раздел C ОКВЭД 2)\n"
        "• Здравоохранение и соц. услуги (раздел Q)\n"
        "• Научные исследования и разработки\n"
        "• Сельское хозяйство\n\n"
        "⚠️ С 2026 г. виды деятельности должны совпадать с перечнем "
        "Правительства РФ (Распоряжение от 30.12.2025 № 4125-р).\n\n"
        "Налоговые каникулы: впервые зарегистрированные ИП — "
        "ставка 0% в течение 2 лет (производство, социальная, научная сферы)."
    )
    await cb.message.edit_text(text)
    await cb.answer()
