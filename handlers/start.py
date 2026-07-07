from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, WebAppInfo
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import MINIAPP_URL, ADMIN_IDS
from services.db import upsert_user, get_user_stats, get_user_session_detail, game_link_mentor
from services.miniapp_auth import create_token

router = Router()

_COHORT_LABELS = {
    "young": "Молодой (до 35)",
    "middle": "Средний возраст (35–50)",
    "adult": "Взрослый (50–60)",
    "pensioner": "Пенсионер (60+)",
}

_STAGE_LABELS = {
    "greeting": "Приветствие",
    "needs": "Выявление потребности",
    "presentation": "Презентация",
    "objections": "Возражения",
    "closing": "Закрытие сделки",
    "full": "Полная встреча",
}


def _main_kb(user_id: int = 0, miniapp_token: str = ""):
    b = InlineKeyboardBuilder()
    b.button(text="🎯 Тренировка", callback_data="start_training")
    b.button(text="📰 Анализ новостей", callback_data="news:menu")
    b.button(text="🌅 Рыночный брифинг", callback_data="briefing:open")
    b.button(text="📈 Анализ акций", callback_data="stock:start")
    b.button(text="📚 Обучение", callback_data="learning:menu")
    b.button(text="🎮 Игра", callback_data="game:open")
    b.button(text="🆘 Поддержка", callback_data="support:menu")
    if MINIAPP_URL and user_id in ADMIN_IDS:
        url = f"{MINIAPP_URL}?t={miniapp_token}" if miniapp_token else MINIAPP_URL
        b.button(text="🎮 Играть", web_app=WebAppInfo(url=url))
    b.adjust(1)
    return b.as_markup()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, command: CommandObject = None):
    await state.clear()
    await upsert_user(message.from_user.id, message.from_user.username, message.from_user.first_name)

    args = command.args if command else None

    if args and args.startswith("duel_"):
        try:
            duel_id = int(args[5:])
        except ValueError:
            duel_id = None
        if duel_id:
            import json as _json
            from services.db import game_join_duel, game_get_duel
            joined = await game_join_duel(duel_id, message.from_user.id)
            if joined:
                duel = await game_get_duel(duel_id)
                questions = _json.loads(duel["questions_json"])
                await state.update_data(
                    duel_id=duel_id, duel_questions=questions, duel_idx=0, duel_score=0,
                    is_opponent=True,
                )
                from handlers.game import _send_duel_question
                await _send_duel_question(message, state, questions, 0, edit=False)
                return
            else:
                await message.answer("❌ Дуэль не найдена или уже начата.")
                # fall through to normal start

    elif args and args.startswith("mentor_"):
        try:
            mentor_id = int(args[7:])
        except ValueError:
            mentor_id = None
        if mentor_id is None:
            await message.answer("❌ Неверная ссылка наставника.")
            # fall through to normal start
        if mentor_id:
            linked = await game_link_mentor(mentor_id, message.from_user.id)
            if linked:
                await message.answer(
                    f"👨‍🏫 Наставник привязан! Теперь когда ты отвечаешь верно — наставник получает бонус XP.",
                    parse_mode="HTML",
                )
                try:
                    await message.bot.send_message(
                        mentor_id,
                        f"🎉 {message.from_user.first_name or 'Новый игрок'} принял твоё наставничество!"
                    )
                except Exception:
                    pass
            else:
                await message.answer("❌ Ссылка недействительна или ты уже привязан к наставнику.")
        # fall through to normal start menu

    elif args and args.startswith("coop_"):
        try:
            session_id = int(args[5:])
        except ValueError:
            session_id = None
        if session_id:
            from services.db import game_join_coop, game_get_coop
            import json as _json
            joined = await game_join_coop(session_id, message.from_user.id)
            if joined:
                sess = await game_get_coop(session_id)
                quest = _json.loads(sess["quest_json"])
                b_coop = InlineKeyboardBuilder()
                b_coop.button(text="▶️ Ответить", callback_data=f"game:coop_answer:{session_id}")
                b_coop.adjust(1)
                await message.answer(
                    f"🤝 <b>Совместный квест!</b>\n\n<b>{quest['question']}</b>\n\nНажми чтобы ответить:",
                    parse_mode="HTML", reply_markup=b_coop.as_markup(),
                )
                # Notify initiator
                try:
                    await message.bot.send_message(
                        sess["initiator_id"],
                        f"🤝 {message.from_user.first_name or 'Партнёр'} принял совместный квест! Отвечай!"
                    )
                except Exception:
                    pass
                return
            else:
                await message.answer("❌ Сессия не найдена или уже начата.")
        # fall through to normal start menu

    name = message.from_user.first_name or "Коллега"
    token = create_token(message.from_user.id)
    await message.answer(
        f"Привет, {name}! 👋\n\n"
        f"Это тренажёр по продажам инвестиционных продуктов и помощник по анализу новостей.\n\n"
        f"Помогу отработать навыки продаж по:\n"
        f"• НСЖ\n"
        f"• ПДС\n"
        f"• ОПИФ\n"
        f"• ОМС\n"
        f"• Стратегии автоследования\n\n"
        f"Отвечай <b>голосовыми сообщениями</b> — я распознаю, проанализирую и отвечу как настоящий клиент.",
        parse_mode="HTML",
        reply_markup=_main_kb(message.from_user.id, token or ""),
    )


@router.message(Command("admin"), ~F.from_user.id.in_(ADMIN_IDS))
async def cmd_admin_denied(message: Message):
    await message.answer("❌ У вас нет доступа к этой команде.")


@router.message(Command("myid"))
async def cmd_myid(message: Message):
    await message.answer(f"Твой Telegram ID: <code>{message.from_user.id}</code>", parse_mode="HTML")


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    token = create_token(message.from_user.id)
    await message.answer("Сессия сброшена. Выберите действие:", reply_markup=_main_kb(message.from_user.id, token or ""))


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    name = callback.from_user.first_name or "Коллега"
    token = create_token(callback.from_user.id)
    await callback.message.edit_text(
        f"Привет, {name}! Выберите действие:",
        reply_markup=_main_kb(callback.from_user.id, token or ""),
    )
    await callback.answer()


@router.callback_query(F.data == "check_sub")
async def check_subscription(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    name = callback.from_user.first_name or "Коллега"
    token = create_token(callback.from_user.id)
    await callback.message.edit_text(
        f"✅ Подписка подтверждена! Добро пожаловать, {name}!\n\n"
        f"Это тренажёр по продажам инвестиционных продуктов и помощник по анализу новостей.\n\n"
        f"Помогу отработать навыки продаж по:\n"
        f"• НСЖ\n• ПДС\n• ОПИФ\n• ОМС\n• Стратегии автоследования\n\n"
        f"Отвечай <b>голосовыми сообщениями</b> — я распознаю, проанализирую и отвечу как настоящий клиент.",
        parse_mode="HTML",
        reply_markup=_main_kb(callback.from_user.id, token or ""),
    )
    await callback.answer("✅ Добро пожаловать!")


@router.callback_query(F.data == "learning:stub")
async def learning_stub(callback: CallbackQuery):
    await callback.answer("🚧 Раздел в разработке — скоро появится!", show_alert=True)


_PRODUCT_LABELS = {
    "pds": "ПДС",
    "nsj": "НСЖ",
    "opif": "ОПИФ",
    "oms": "ОМС",
    "strategy": "Стратегия",
    "portfolio": "Портфель",
    "identify": "Подбор продукта",
}

_MODE_LABELS = {
    "full": "Полная встреча",
    "stage": "Конкретный этап",
    "identify": "Подбор продукта",
    "objection": "Отработка возражения",
}


def _score_bar(score: float | None) -> str:
    if score is None:
        return "—"
    filled = round(score)
    return "█" * filled + "░" * (10 - filled) + f" {score}/10"


@router.callback_query(F.data == "show_stats")
async def show_stats(callback: CallbackQuery):
    stats = await get_user_stats(callback.from_user.id)

    avg = stats.get("avg_score")
    avg_str = f"{avg}/10" if avg else "—"
    lines = [
        f"📊 <b>Ваша статистика тренировок</b>\n",
        f"Сессий завершено: <b>{stats['completed']}</b> из {stats['total']}",
        f"Средний балл: <b>{avg_str}</b>",
    ]

    if stats["by_product"]:
        lines.append("\n<b>По продуктам:</b>")
        for row in stats["by_product"]:
            label = _PRODUCT_LABELS.get(row.get("product", ""), row.get("product", "—"))
            done = int(row.get("completed") or 0)
            sc = row.get("avg_score")
            sc_str = f"  ср. балл <b>{sc}/10</b>" if sc else ""
            lines.append(f"• {label}: {done} сессий{sc_str}")

    if stats["by_stage"]:
        lines.append("\n<b>По этапам:</b>")
        for row in stats["by_stage"]:
            label = _STAGE_LABELS.get(row.get("stage", ""), row.get("stage", "—"))
            done = int(row.get("completed") or 0)
            lines.append(f"• {label}: {done} завершено")

    if stats["total"] == 0:
        lines.append("\nПока нет ни одной сессии. Начните первую тренировку!")

    b = InlineKeyboardBuilder()
    b.button(text="🎯 Тренировка", callback_data="start_training")
    if stats["completed"] > 0:
        b.button(text="📋 История сессий", callback_data="stats:history")
    b.button(text="◀️ Назад", callback_data="back_to_menu")
    b.adjust(1)

    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data == "stats:history")
async def show_session_history(callback: CallbackQuery):
    stats = await get_user_stats(callback.from_user.id)
    sessions = stats.get("recent_sessions", [])

    if not sessions:
        await callback.answer("История пуста", show_alert=True)
        return

    b = InlineKeyboardBuilder()
    for s in sessions:
        product = _PRODUCT_LABELS.get(s.get("product") or "", "—")
        stage = _STAGE_LABELS.get(s.get("stage") or "", "—")
        sc = s.get("score")
        sc_str = f" | {sc}/10" if sc else ""
        date_str = (s.get("completed_at") or "")[:10]
        b.button(
            text=f"{date_str} {stage} · {product}{sc_str}",
            callback_data=f"stats:session:{s['id']}",
        )
    b.button(text="◀️ Назад к статистике", callback_data="show_stats")
    b.adjust(1)

    await callback.message.edit_text(
        "📋 <b>История завершённых сессий</b>\n\nНажмите на сессию для просмотра оценки тренера:",
        parse_mode="HTML",
        reply_markup=b.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("stats:session:"))
async def show_session_detail(callback: CallbackQuery):
    session_id = int(callback.data.split(":")[-1])
    session = await get_user_session_detail(session_id, callback.from_user.id)

    if not session:
        await callback.answer("Сессия не найдена", show_alert=True)
        return

    stage = _STAGE_LABELS.get(session.get("stage") or "", "—")
    product = _PRODUCT_LABELS.get(session.get("product") or "", "—")
    mode = _MODE_LABELS.get(session.get("mode") or "", "—")
    sc = session.get("score")
    date_str = (session.get("completed_at") or "")[:16].replace("T", " ")
    feedback = session.get("final_feedback") or "Оценка не сохранена."

    header = (
        f"📋 <b>Сессия #{session_id}</b>\n"
        f"📅 {date_str}\n"
        f"🎯 {mode} · {stage} · {product}\n"
        f"⭐ Балл: <b>{sc}/10</b>\n\n" if sc else
        f"📋 <b>Сессия #{session_id}</b>\n"
        f"📅 {date_str}\n"
        f"🎯 {mode} · {stage} · {product}\n\n"
    )

    b = InlineKeyboardBuilder()
    b.button(text="◀️ К истории", callback_data="stats:history")
    b.adjust(1)

    text = header + feedback
    if len(text) > 4096:
        text = text[:4050] + "…"

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=b.as_markup())
    await callback.answer()
