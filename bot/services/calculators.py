"""Функции расчёта на Decimal — зарплата, НДФЛ, взносы, НДС, транспортный налог."""

from decimal import Decimal, ROUND_HALF_UP

from bot.config.rates import (
    EPB,
    INSURANCE_ABOVE,
    INSURANCE_BASE,
    MROT,
    NDS_BASE_RATE,
    NDS_REDUCED_RATE,
    NDS_USN_REDUCED_5,
    NDS_USN_REDUCED_7,
    NDFL_SCALE,
    NDFL_SCALE_NORTH,
    TERRITORY_GROUPS,
    TRANSPORT_TAX,
)

TWO_PLACES = Decimal("0.01")


def _fmt(v: Decimal) -> str:
    """Форматирует число: пробелы-разделители тысяч, запятая-дробная."""
    s = f"{v:,.2f}"
    return s.replace(",", "\u00a0").replace(".", ",")


def _apply_scale(income: int, scale: list) -> Decimal:
    """Рассчитывает НДФЛ по прогрессивной шкале."""
    total_tax = Decimal(0)
    prev_bound = 0
    for bound, rate in scale:
        if bound is None:
            taxable = Decimal(income - prev_bound)
            total_tax += taxable * rate
            break
        if income <= bound:
            taxable = Decimal(income - prev_bound)
            total_tax += taxable * rate
            break
        taxable = Decimal(bound - prev_bound)
        total_tax += taxable * rate
        prev_bound = bound
    return total_tax.quantize(TWO_PLACES, ROUND_HALF_UP)


# ─────────────────────────────────────────────
# ЗАРПЛАТА С РК И НАДБАВКОЙ
# ─────────────────────────────────────────────

def calc_salary(territory: str, oklad: int, nadbavka_pct: int) -> str:
    """Расчёт зарплаты с районным коэффициентом и северной надбавкой."""
    group = TERRITORY_GROUPS.get(territory)
    if not group:
        return "❌ Неизвестная группа территорий."

    oklad_d = Decimal(oklad)
    rk = group["rk"]
    rk_extra = rk - 1
    max_nadb = group["max_nadbavka"]
    nadbavka = min(Decimal(nadbavka_pct) / 100, max_nadb)

    rk_sum = (oklad_d * rk_extra).quantize(TWO_PLACES, ROUND_HALF_UP)
    nadb_sum = (oklad_d * nadbavka).quantize(TWO_PLACES, ROUND_HALF_UP)
    gross = oklad_d + rk_sum + nadb_sum

    # НДФЛ: основная часть — шкала 13–22%, северная — 13%/15%
    annual_base = int(oklad_d * 12)
    annual_north = int((rk_sum + nadb_sum) * 12)

    ndfl_base = _apply_scale(annual_base, NDFL_SCALE)
    ndfl_north = _apply_scale(annual_north, NDFL_SCALE_NORTH)
    ndfl_year = ndfl_base + ndfl_north
    ndfl_monthly = (ndfl_year / 12).quantize(TWO_PLACES, ROUND_HALF_UP)

    net = (gross - ndfl_monthly).quantize(TWO_PLACES, ROUND_HALF_UP)

    mrot_warning = ""
    if oklad < MROT:
        mrot_warning = f"\n\n⚠️ Оклад ниже МРОТ ({_fmt(Decimal(MROT))} ₽)!"

    nadb_display = int(nadbavka * 100)

    return (
        f"<b>Расчёт зарплаты</b>\n"
        f"Территория: {group['name']}\n"
        f"РК: {rk} | Надбавка: {nadb_display}%\n\n"
        f"Оклад: {_fmt(oklad_d)} ₽\n"
        f"РК ({rk_extra}): +{_fmt(rk_sum)} ₽\n"
        f"Надбавка ({nadb_display}%): +{_fmt(nadb_sum)} ₽\n"
        f"<b>Начислено: {_fmt(gross)} ₽</b>\n\n"
        f"НДФЛ (основная часть): {_fmt((ndfl_base / 12).quantize(TWO_PLACES, ROUND_HALF_UP))} ₽/мес\n"
        f"НДФЛ (северная часть): {_fmt((ndfl_north / 12).quantize(TWO_PLACES, ROUND_HALF_UP))} ₽/мес\n"
        f"НДФЛ итого: −{_fmt(ndfl_monthly)} ₽\n"
        f"<b>На руки: {_fmt(net)} ₽</b>"
        f"{mrot_warning}\n\n"
        f"Доп. отпуск: {group['extra_vacation']} кал. дней\n"
        f"Раб. неделя (жен.): {group['women_work_week']} ч"
    )


# ─────────────────────────────────────────────
# НДФЛ — ПРОГРЕССИВНАЯ ШКАЛА 2026
# ─────────────────────────────────────────────

def calc_ndfl_progressive(annual_income: int) -> str:
    """Расчёт НДФЛ по прогрессивной шкале 2026 (5 ступеней)."""
    income_d = Decimal(annual_income)
    tax = _apply_scale(annual_income, NDFL_SCALE)
    effective = (
        (tax / income_d * 100).quantize(TWO_PLACES, ROUND_HALF_UP)
        if income_d
        else Decimal(0)
    )
    net = income_d - tax

    # Детализация по ступеням
    breakdown: list[str] = []
    prev = 0
    for bound, rate in NDFL_SCALE:
        if annual_income <= prev:
            break
        top = bound if bound and annual_income > bound else annual_income
        taxable = Decimal(top - prev)
        part_tax = (taxable * rate).quantize(TWO_PLACES, ROUND_HALF_UP)
        pct = int(rate * 100)
        breakdown.append(
            f"  {_fmt(Decimal(prev))}–{_fmt(Decimal(top))}: "
            f"{pct}% = {_fmt(part_tax)} ₽"
        )
        if bound is None or annual_income <= bound:
            break
        prev = bound

    detail = "\n".join(breakdown)

    return (
        f"<b>НДФЛ — прогрессивная шкала 2026</b>\n\n"
        f"Годовой доход: {_fmt(income_d)} ₽\n\n"
        f"{detail}\n\n"
        f"<b>НДФЛ за год: {_fmt(tax)} ₽</b>\n"
        f"Эффективная ставка: {effective}%\n"
        f"После НДФЛ: {_fmt(net)} ₽\n"
        f"В месяц (после НДФЛ): "
        f"{_fmt((net / 12).quantize(TWO_PLACES, ROUND_HALF_UP))} ₽"
    )


# ─────────────────────────────────────────────
# СТРАХОВЫЕ ВЗНОСЫ
# ─────────────────────────────────────────────

def calc_insurance_contributions(monthly_salary: int) -> str:
    """Расчёт страховых взносов с определением месяца исчерпания ЕПБ."""
    monthly = Decimal(monthly_salary)
    annual = monthly * 12

    month_names = [
        "январь", "февраль", "март", "апрель", "май", "июнь",
        "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
    ]

    if annual <= EPB:
        total = (annual * INSURANCE_BASE).quantize(TWO_PLACES, ROUND_HALF_UP)
        exhaust_month = "не исчерпана за год"
    else:
        within = (Decimal(EPB) * INSURANCE_BASE).quantize(TWO_PLACES, ROUND_HALF_UP)
        above = ((annual - EPB) * INSURANCE_ABOVE).quantize(TWO_PLACES, ROUND_HALF_UP)
        total = within + above
        months_to_exhaust = Decimal(EPB) / monthly
        exhaust_int = int(months_to_exhaust)
        if months_to_exhaust % 1 > 0:
            exhaust_int += 1
        exhaust_month = (
            month_names[exhaust_int - 1] if exhaust_int <= 12 else "не исчерпана"
        )

    monthly_contrib = (monthly * INSURANCE_BASE).quantize(TWO_PLACES, ROUND_HALF_UP)
    rate_within = f"{INSURANCE_BASE * 100}%"
    rate_above = f"{INSURANCE_ABOVE * 100}%"

    return (
        f"<b>Страховые взносы 2026</b>\n\n"
        f"Ежемесячная зарплата: {_fmt(monthly)} ₽\n"
        f"Годовой ФОТ: {_fmt(annual)} ₽\n"
        f"ЕПБ: {_fmt(Decimal(EPB))} ₽\n\n"
        f"Ставка до ЕПБ: {rate_within}\n"
        f"Ставка свыше ЕПБ: {rate_above}\n\n"
        f"Взносы в месяц (до ЕПБ): {_fmt(monthly_contrib)} ₽\n"
        f"<b>Взносы за год: {_fmt(total)} ₽</b>\n\n"
        f"ЕПБ исчерпана в: <b>{exhaust_month}</b>"
    )


# ─────────────────────────────────────────────
# НДС
# ─────────────────────────────────────────────

def calc_nds(amount: int, rate_pct: int) -> str:
    """Расчёт НДС — прямой и обратный."""
    rate_map = {
        22: NDS_BASE_RATE,
        10: NDS_REDUCED_RATE,
        5: NDS_USN_REDUCED_5,
        7: NDS_USN_REDUCED_7,
    }
    rate = rate_map.get(rate_pct, NDS_BASE_RATE)
    amount_d = Decimal(amount)

    nds = (amount_d * rate).quantize(TWO_PLACES, ROUND_HALF_UP)
    total = amount_d + nds

    # Обратный расчёт (из суммы с НДС)
    calc_rate = rate / (1 + rate)
    nds_from_total = (total * calc_rate).quantize(TWO_PLACES, ROUND_HALF_UP)

    return (
        f"<b>Расчёт НДС ({rate_pct}%)</b>\n\n"
        f"Сумма без НДС: {_fmt(amount_d)} ₽\n"
        f"НДС ({rate_pct}%): {_fmt(nds)} ₽\n"
        f"<b>Итого с НДС: {_fmt(total)} ₽</b>\n\n"
        f"<b>Обратный расчёт:</b>\n"
        f"Сумма с НДС: {_fmt(total)} ₽\n"
        f"В т.ч. НДС: {_fmt(nds_from_total)} ₽\n"
        f"Без НДС: {_fmt(total - nds_from_total)} ₽"
    )


# ─────────────────────────────────────────────
# ТРАНСПОРТНЫЙ НАЛОГ — ИРКУТСКАЯ ОБЛАСТЬ
# ─────────────────────────────────────────────

VEHICLE_TYPE_NAMES = {
    "car": "Легковой автомобиль",
    "truck": "Грузовой автомобиль",
    "bus": "Автобус",
    "motorcycle": "Мотоцикл",
}


def calc_transport_tax(vehicle_type: str, horsepower: int) -> str:
    """Расчёт транспортного налога по ставкам Иркутской области."""
    rates = TRANSPORT_TAX.get(vehicle_type)
    if not rates:
        return "❌ Неизвестный тип ТС."

    rate = None
    for low, high, r in rates:
        if low <= horsepower <= high:
            rate = r
            break

    if rate is None:
        return "❌ Не удалось определить ставку для данной мощности."

    hp_d = Decimal(horsepower)
    tax = (hp_d * rate).quantize(TWO_PLACES, ROUND_HALF_UP)

    return (
        f"<b>Транспортный налог — Иркутская область</b>\n\n"
        f"Тип ТС: {VEHICLE_TYPE_NAMES.get(vehicle_type, vehicle_type)}\n"
        f"Мощность: {horsepower} л.с.\n"
        f"Ставка: {_fmt(rate)} ₽/л.с.\n\n"
        f"<b>Налог за год: {_fmt(tax)} ₽</b>\n\n"
        f"Закон ИО от 04.07.2007 № 53-ОЗ"
    )
