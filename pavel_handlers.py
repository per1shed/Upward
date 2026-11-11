"""Кнопки Пашка: финансы, состояние, трафик и разделы Tempo."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatAction
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from charts import chart_photo
from keyboards import (
    cancel_keyboard,
    finance_keyboard,
    goal_keyboard,
    plan_keyboard,
    state_keyboard,
    state_kind_keyboard,
    state_score_keyboard,
    stopwatch_keyboard,
)
from pavel import (
    current_block,
    is_pashok,
    latest_value,
    money,
    month_allowed,
    month_series,
    mode_label,
    next_mode,
    parse_amount,
    plan_blocks,
    profile,
    save_value,
    set_profile,
    stopwatch,
    stopwatch_text,
    sw_lap,
    sw_pause,
    sw_reset,
    sw_start,
)
from pavel_charts import (
    BALANCE,
    CASH,
    DEBT,
    MORAL,
    PHYSICAL,
    render_bars,
    render_finance,
    render_plan,
)
from timezone_utils import now_local, today_local
from ui_keyboard import answer_photo_tracked, answer_tracked, edit_text_tracked

router = Router(name="pavel")

MONTHS = (
    "",
    "январь",
    "февраль",
    "март",
    "апрель",
    "май",
    "июнь",
    "июль",
    "август",
    "сентябрь",
    "октябрь",
    "ноябрь",
    "декабрь",
)


class PavelInput(StatesGroup):
    cash = State()
    debt = State()
    goal_name = State()
    goal_amount = State()


def _only(user_id: int | None) -> bool:
    return is_pashok(user_id)


def _parse_month(data: str) -> tuple[int, int] | None:
    tail = data.rsplit(":", 1)[-1]
    if len(tail) == 7 and tail[4] == "-":
        year, month = tail.split("-")
        if year.isdigit() and month.isdigit():
            return int(year), int(month)
    return None


def _this_month(data: str) -> tuple[int, int]:
    parsed = _parse_month(data)
    if parsed and month_allowed(*parsed):
        return parsed
    today = today_local()
    return today.year, today.month


async def _finance_caption(user_id: int, year: int, month: int) -> str:
    return f"<b>Финансы</b> · {MONTHS[month]} {year}"


async def send_finance(message: Message, user_id: int, year: int, month: int) -> None:
    cash = await month_series(user_id, "cash", year, month, carry=True)
    debt = await month_series(user_id, "debt", year, month, carry=True)
    balance = await month_series(user_id, "balance", year, month, carry=True)
    money: list[float | None] = []
    debts: list[float | None] = []
    for cash_value, debt_value in zip(cash, debt):
        if debt_value in (None, 0):
            money.append(None)
            debts.append(None)
        else:
            money.append(cash_value)
            debts.append(debt_value)
    png = render_finance(
        [
            ("Баланс", balance, BALANCE),
            ("Деньги", money, CASH),
            ("Долги", debts, DEBT),
        ],
        year=year,
        month=month,
    )
    await message.bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_PHOTO)
    await answer_photo_tracked(
        message,
        chart_photo(png, "finance.png"),
        caption=await _finance_caption(user_id, year, month),
        reply_markup=finance_keyboard(year, month),
    )


async def send_state(message: Message, user_id: int, year: int, month: int) -> None:
    physical = await month_series(user_id, "physical", year, month, carry=True)
    moral = await month_series(user_id, "moral", year, month, carry=True)
    png = render_bars(
        [("Физическое", physical, PHYSICAL), ("Моральное", moral, MORAL)],
        year=year,
        month=month,
        scale=5,
    )
    phys = await latest_value(user_id, "physical", year, month)
    mor = await latest_value(user_id, "moral", year, month)

    def score(value: float | None) -> str:
        if value is None:
            return "—"
        rounded = round(value, 1)
        if abs(rounded - round(rounded)) < 0.05:
            return str(int(round(rounded)))
        return f"{rounded:.1f}".replace(".", ",")

    caption = (
        f"<b>Состояние</b> · {MONTHS[month]} {year}\n"
        f"Физическое {score(phys)}\n"
        f"Моральное {score(mor)}"
    )
    await message.bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_PHOTO)
    await answer_photo_tracked(
        message,
        chart_photo(png, "state.png"),
        caption=caption,
        reply_markup=state_keyboard(year, month),
    )


async def send_plan(message: Message, user_id: int) -> None:
    info = await profile(user_id)
    moment = now_local()
    stored = info["calendar_mode"]
    blocks = plan_blocks(moment.date(), stored)
    png = render_plan(blocks, moment, mode_label(stored, moment.date()), current_block(blocks, moment))
    await message.bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_PHOTO)
    await answer_photo_tracked(
        message,
        chart_photo(png, "plan.png"),
        reply_markup=plan_keyboard(stored),
    )


async def send_stopwatch(message: Message, user_id: int) -> None:
    state = await stopwatch(user_id)
    await answer_tracked(message, stopwatch_text(state), reply_markup=stopwatch_keyboard(state["status"]))


@router.callback_query(F.data == "p:fin")
@router.callback_query(F.data.regexp(r"^p:fin:\d{4}-\d{2}$"))
async def open_finance(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer("Строю график…")
    if not callback.from_user or not _only(callback.from_user.id) or callback.message is None:
        return
    await state.clear()
    year, month = _this_month(callback.data or "")
    await send_finance(callback.message, callback.from_user.id, year, month)


async def _remember_finance(user_id: int, cash: float, debt: float) -> None:
    today = today_local()
    await save_value(user_id, "cash", today, cash)
    await save_value(user_id, "debt", today, debt)
    await save_value(user_id, "balance", today, cash - debt)


@router.callback_query(F.data.in_({"p:fin:balance", "p:fin:edit"}))
async def edit_balance(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.from_user or not _only(callback.from_user.id) or callback.message is None:
        return
    await state.set_state(PavelInput.cash)
    await answer_tracked(
        callback.message,
        "Впишите баланс. Можно с минусом.",
        reply_markup=cancel_keyboard(callback.from_user.id),
    )


@router.callback_query(F.data == "p:fin:debt")
async def edit_debt(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.from_user or not _only(callback.from_user.id) or callback.message is None:
        return
    await state.set_state(PavelInput.debt)
    await answer_tracked(
        callback.message,
        "Впишите сумму долгов.",
        reply_markup=cancel_keyboard(callback.from_user.id),
    )


@router.message(PavelInput.cash, F.text)
async def finance_balance(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id if message.from_user else 0
    if not _only(user_id):
        return
    balance = parse_amount(message.text or "")
    if balance is None:
        await answer_tracked(message, "Впишите сумму баланса.", reply_markup=cancel_keyboard(user_id))
        return
    today = today_local()
    debt = await latest_value(user_id, "debt", today.year, today.month) or 0
    await _remember_finance(user_id, balance + debt, debt)
    await state.clear()
    await send_finance(message, user_id, today.year, today.month)


@router.message(PavelInput.debt, F.text)
async def finance_debt(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id if message.from_user else 0
    if not _only(user_id):
        return
    debt = parse_amount(message.text or "")
    if debt is None or debt < 0:
        await answer_tracked(message, "Впишите сумму долгов, ноль или больше.", reply_markup=cancel_keyboard(user_id))
        return
    today = today_local()
    cash = await latest_value(user_id, "cash", today.year, today.month) or 0
    await _remember_finance(user_id, cash, debt)
    await state.clear()
    await send_finance(message, user_id, today.year, today.month)


@router.callback_query(F.data == "p:goal")
async def ask_goal(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.from_user or not _only(callback.from_user.id) or callback.message is None:
        return
    info = await profile(callback.from_user.id)
    has_goal = info.get("finance_goal") is not None
    await state.set_state(PavelInput.goal_name)
    await state.update_data(had_goal=has_goal)
    text = "Впишите название финансовой цели."
    if info.get("finance_goal_name"):
        text = f"Сейчас: {info['finance_goal_name']}.\n\nВпишите новое название."
    await answer_tracked(callback.message, text, reply_markup=goal_keyboard(has_goal))


@router.callback_query(F.data == "p:goal:clear")
async def clear_goal(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer("Цель снята")
    if not callback.from_user or not _only(callback.from_user.id) or callback.message is None:
        return
    await state.clear()
    await set_profile(
        callback.from_user.id,
        finance_goal=None,
        finance_goal_name=None,
        finance_goal_start=None,
        finance_goal_set_on=None,
    )
    today = today_local()
    await send_finance(callback.message, callback.from_user.id, today.year, today.month)


@router.message(PavelInput.goal_name, F.text)
async def goal_name(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id if message.from_user else 0
    if not _only(user_id):
        return
    name = (message.text or "").strip()
    if not name or len(name) > 64:
        await answer_tracked(message, "Впишите название, до 64 символов.", reply_markup=goal_keyboard(bool((await state.get_data()).get("had_goal"))))
        return
    await state.update_data(goal_name=name)
    await state.set_state(PavelInput.goal_amount)
    had_goal = bool((await state.get_data()).get("had_goal"))
    await answer_tracked(message, "Впишите сумму цели.", reply_markup=goal_keyboard(had_goal))


@router.message(PavelInput.goal_amount, F.text)
async def goal_amount(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id if message.from_user else 0
    if not _only(user_id):
        return
    amount = parse_amount(message.text or "")
    if amount is None:
        await answer_tracked(message, "Впишите сумму цели.", reply_markup=goal_keyboard(bool((await state.get_data()).get("had_goal"))))
        return
    data = await state.get_data()
    balance = await latest_value(user_id, "balance", *today_local().timetuple()[:2])
    await set_profile(
        user_id,
        finance_goal_name=data.get("goal_name") or "Цель",
        finance_goal=amount,
        finance_goal_start=balance,
        finance_goal_set_on=today_local().isoformat(),
    )
    await state.clear()
    today = today_local()
    await send_finance(message, user_id, today.year, today.month)


@router.callback_query(F.data == "p:state")
@router.callback_query(F.data.regexp(r"^p:state:\d{4}-\d{2}$"))
async def open_state(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer("Строю график…")
    if not callback.from_user or not _only(callback.from_user.id) or callback.message is None:
        return
    await state.clear()
    year, month = _this_month(callback.data or "")
    await send_state(callback.message, callback.from_user.id, year, month)


@router.callback_query(F.data == "p:state:ask")
async def ask_state(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.from_user or not _only(callback.from_user.id) or callback.message is None:
        return
    await answer_tracked(callback.message, "Что отметить?", reply_markup=state_kind_keyboard())


@router.callback_query(F.data.startswith("p:state:kind:"))
async def ask_score(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.from_user or not _only(callback.from_user.id) or callback.message is None:
        return
    kind = (callback.data or "").rsplit(":", 1)[-1]
    title = "Физическое" if kind == "p" else "Моральное"
    await answer_tracked(callback.message, f"{title}: оценка от 1 до 5", reply_markup=state_score_keyboard(kind))


@router.callback_query(F.data.startswith("p:state:set:"))
async def set_score(callback: CallbackQuery) -> None:
    await callback.answer("Сохранено")
    if not callback.from_user or not _only(callback.from_user.id) or callback.message is None:
        return
    _prefix, _state, _set, kind, score = (callback.data or "").split(":")
    slug = "physical" if kind == "p" else "moral"
    today = today_local()
    await save_value(callback.from_user.id, slug, today, float(score))
    await send_state(callback.message, callback.from_user.id, today.year, today.month)


@router.callback_query(F.data == "p:sw")
async def open_sw(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.from_user or not _only(callback.from_user.id) or callback.message is None:
        return
    await state.clear()
    await send_stopwatch(callback.message, callback.from_user.id)


@router.callback_query(F.data.startswith("p:sw:"))
async def sw_action(callback: CallbackQuery) -> None:
    if not callback.from_user or not _only(callback.from_user.id) or callback.message is None:
        return
    action = (callback.data or "").rsplit(":", 1)[-1]
    user_id = callback.from_user.id
    if action == "start":
        await sw_start(user_id)
        await callback.answer("Старт")
    elif action == "pause":
        await sw_pause(user_id)
        await callback.answer("Пауза")
    elif action == "reset":
        await sw_reset(user_id)
        await callback.answer("Сброшено")
    elif action == "lap":
        state = await stopwatch(user_id)
        if state["status"] != "running":
            await callback.answer("Секундомер не запущен", show_alert=True)
            return
        await sw_lap(user_id)
        await callback.answer("Круг")
    else:
        await callback.answer()
    current = await stopwatch(user_id)
    edited = await edit_text_tracked(
        callback.message,
        stopwatch_text(current),
        reply_markup=stopwatch_keyboard(current["status"]),
    )
    if not edited:
        await send_stopwatch(callback.message, user_id)


@router.callback_query(F.data == "p:plan")
async def open_plan(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.from_user or not _only(callback.from_user.id) or callback.message is None:
        return
    await state.clear()
    await send_plan(callback.message, callback.from_user.id)


@router.callback_query(F.data == "p:plan:mode")
async def cycle_mode(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.from_user or not _only(callback.from_user.id) or callback.message is None:
        return
    info = await profile(callback.from_user.id)
    stored = next_mode(info["calendar_mode"])
    await set_profile(callback.from_user.id, calendar_mode=stored)
    await send_plan(callback.message, callback.from_user.id)
