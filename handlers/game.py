"""
Игра "Инвестор: Восхождение" — Stage 1 MVP
Доступна только администраторам (для проверки).
Обычные пользователи видят заглушку "в разработке".
"""
from __future__ import annotations

import math
from datetime import datetime, date

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_IDS
from services.db import (
    game_get_or_create_player,
    game_get_location_progress,
    game_get_completed_quests,
    game_save_quest_result,
    game_update_player,
    game_collect_income,
    game_update_streak,
)
from states.game import GameState

router = Router()

# ── XP / Level helpers ────────────────────────────────────────────────────────

_LEVEL_BASE = 100
_LEVEL_MULT = 1.5


def xp_for_level(level: int) -> int:
    """XP required to go from level to level+1."""
    return int(_LEVEL_BASE * (_LEVEL_MULT ** (level - 1)))


def parse_level(total_xp: int) -> tuple[int, int, int]:
    """Return (level, xp_in_current_level, xp_needed_for_next_level)."""
    level = 1
    xp = total_xp
    while True:
        needed = xp_for_level(level)
        if xp < needed:
            return level, xp, needed
        xp -= needed
        level += 1


def xp_bar(xp_in: int, xp_needed: int, width: int = 10) -> str:
    filled = math.floor((xp_in / xp_needed) * width) if xp_needed else 0
    return "█" * filled + "░" * (width - filled)


# ── Game data: locations & quests ─────────────────────────────────────────────

LOCATIONS: dict[str, dict] = {
    "sber": {
        "name": "СБЕР-СИТИ",
        "emoji": "🏦",
        "sector": "Финансы",
        "description": (
            "Крупнейший банк России и Восточной Европы.\n"
            "Основан в 1841 году указом Николая I.\n"
            "Прибыль в 2023 году: <b>1,5 трлн рублей</b>."
        ),
        "income_per_hour": 8,
        "rep_rank": ["Новичок", "Знакомый", "Доверенный", "Партнёр", "Легенда"],
        "rep_thresholds": [0, 500, 1500, 3000, 6000],
        "quests": [
            {
                "id": "sber_q1",
                "title": "История банка",
                "story": (
                    "Ты только что вошёл в СБЕР-СИТИ. Охранник на входе "
                    "спрашивает у каждого посетителя один вопрос, прежде чем пустить внутрь..."
                ),
                "question": "В каком году был основан Сбербанк?",
                "options": ["1917", "1991", "1841", "1860"],
                "correct": 2,
                "xp": 120,
                "coins": 80,
                "rep": 150,
                "explanation": (
                    "Правильно — 1841 год. Именно тогда Николай I подписал Указ "
                    "о создании сберегательных касс. Первым вкладчиком стал надворный советник Кристофари."
                ),
            },
            {
                "id": "sber_q2",
                "title": "Тайна пеликана",
                "story": (
                    "В архивном отделе СБЕР-СИТИ ты находишь старинный документ. "
                    "На нём изображена первая эмблема банка..."
                ),
                "question": "Какое животное было на первой эмблеме Сберкассы России?",
                "options": ["Медведь", "Пеликан", "Орёл", "Лев"],
                "correct": 1,
                "xp": 100,
                "coins": 60,
                "rep": 120,
                "explanation": (
                    "Верно — Пеликан! В 1841 году именно пеликан стал символом банка. "
                    "Позже, в 1862 году, когда кассы перешли под Министерство финансов, "
                    "появилась новая эмблема — рог изобилия и пчелиный улей."
                ),
            },
            {
                "id": "sber_q3",
                "title": "Кризис 2008",
                "story": (
                    "Машина времени перенесла тебя в октябрь 2008 года. "
                    "Рынок обрушился. Акции Сбера торгуются по 14 рублей — "
                    "на 80% ниже максимума. Твой клиент в панике звонит тебе..."
                ),
                "question": "Что рекомендует грамотный финансовый советник в разгар кризиса?",
                "options": [
                    "Продать всё — рынок будет падать вечно",
                    "Держать позицию, докупить на просадке",
                    "Перевести всё в наличные рубли",
                    "Купить только иностранную валюту",
                ],
                "correct": 1,
                "xp": 200,
                "coins": 150,
                "rep": 200,
                "explanation": (
                    "Правильно! В 2008 году акции Сбера стоили 14 рублей. "
                    "К 2021 году они достигли 360 рублей — рост в 25 раз. "
                    "Те, кто держал и докупал в кризис, заработали состояние."
                ),
            },
            {
                "id": "sber_q4",
                "title": "Дивидендный сезон",
                "story": (
                    "Весна 2024 года. Сбер объявляет рекордные дивиденды. "
                    "Клиент спрашивает: 'Стоит ли покупать акции прямо сейчас, "
                    "до отсечки?' Ты думаешь..."
                ),
                "question": "Что происходит с акцией ПОСЛЕ дивидендной отсечки?",
                "options": [
                    "Цена растёт — все хотят дивиденды",
                    "Цена падает примерно на размер дивиденда",
                    "Цена остаётся неизменной",
                    "Торги приостанавливаются на 3 дня",
                ],
                "correct": 1,
                "xp": 180,
                "coins": 120,
                "rep": 180,
                "explanation": (
                    "Верно! После отсечки происходит дивидендный гэп — "
                    "цена акции снижается примерно на размер дивиденда. "
                    "Покупать 'за день до' ради дивидендов не выгодно: "
                    "ты получишь дивиденд, но потеряешь его в цене акции."
                ),
            },
            {
                "id": "sber_q5",
                "title": "Цифровой гигант",
                "story": (
                    "На презентации в конференц-зале СБЕР-СИТИ тебе показывают "
                    "экосистему продуктов. Сбер давно перестал быть просто банком..."
                ),
                "question": "Какое направление НЕ входит в экосистему Сбера?",
                "options": [
                    "СберЗдоровье (медицина)",
                    "СберМаркет (доставка)",
                    "СберАвиа (авиаперевозки)",
                    "GigaChat (AI-ассистент)",
                ],
                "correct": 2,
                "xp": 150,
                "coins": 100,
                "rep": 160,
                "explanation": (
                    "Правильно — авиаперевозок у Сбера нет. "
                    "Зато есть: GigaChat (ИИ-ассистент), СберЗдоровье, "
                    "СберМаркет, СберАвто, Окко (видеосервис), 2ГИС и многое другое. "
                    "Сбер трансформировался из банка в технологическую экосистему."
                ),
            },
        ],
    },
    "lukoil": {
        "name": "ЛУКОЙЛ-НАФТАГРАД",
        "emoji": "🛢️",
        "sector": "Нефть и газ",
        "description": (
            "Вторая по размеру частная нефтяная компания в мире после ExxonMobil.\n"
            "Обеспечивает <b>2,2% мировой добычи нефти</b>.\n"
            "Один из лидеров по дивидендной доходности на MOEX."
        ),
        "income_per_hour": 15,
        "rep_rank": ["Новичок", "Знакомый", "Доверенный", "Партнёр", "Легенда"],
        "rep_thresholds": [0, 500, 1500, 3000, 6000],
        "quests": [
            {
                "id": "lukoil_q1",
                "title": "Место в мире",
                "story": (
                    "На входе в ЛУКОЙЛ-НАФТАГРАД висит огромная карта мира "
                    "с флажками во всех странах присутствия. Охранник задаёт вопрос..."
                ),
                "question": "Какое место занимает ЛУКОЙЛ среди мировых частных нефтяных компаний по запасам?",
                "options": ["Первое", "Второе", "Пятое", "Десятое"],
                "correct": 1,
                "xp": 120,
                "coins": 90,
                "rep": 150,
                "explanation": (
                    "Верно — второе место! ЛУКОЙЛ занимает второе место в мире "
                    "среди частных нефтяных компаний по доказанным запасам "
                    "углеводородов, уступая только ExxonMobil."
                ),
            },
            {
                "id": "lukoil_q2",
                "title": "Вертикальная интеграция",
                "story": (
                    "Аналитик объясняет тебе бизнес-модель ЛУКОЙЛа на большом экране. "
                    "Он использует термин, который часто звучит в описании крупных нефтяников..."
                ),
                "question": "Что означает 'вертикально интегрированная нефтяная компания'?",
                "options": [
                    "Компания работает только в вертикальных скважинах",
                    "Компания охватывает всю цепочку: добыча → переработка → продажа",
                    "Компания управляется по вертикали власти",
                    "Компания экспортирует нефть только вертикально (трубопроводом)",
                ],
                "correct": 1,
                "xp": 160,
                "coins": 100,
                "rep": 160,
                "explanation": (
                    "Правильно! Вертикальная интеграция означает контроль над всей цепочкой: "
                    "разведка и добыча нефти → её переработка на НПЗ → "
                    "транспортировка → сбыт через АЗС. "
                    "Это снижает зависимость от внешних поставщиков и повышает маржу."
                ),
            },
            {
                "id": "lukoil_q3",
                "story": (
                    "Срочное сообщение на твоём терминале: нефть марки Brent "
                    "упала на 15% за последние 3 дня. Акции ЛУКОЙЛа снизились на 10%. "
                    "Клиент звонит в панике..."
                ),
                "title": "Нефть падает",
                "question": "Что из перечисленного НАИБОЛЕЕ вероятно вызвало резкое падение нефти?",
                "options": [
                    "Обнаружение огромных новых запасов нефти",
                    "Замедление мировой экономики + рост добычи ОПЕК",
                    "Закрытие всех НПЗ в Европе",
                    "Курс рубля укрепился",
                ],
                "correct": 1,
                "xp": 200,
                "coins": 140,
                "rep": 200,
                "explanation": (
                    "Верно! Нефть обычно падает при двух одновременных факторах: "
                    "снижении спроса (замедление экономики, особенно Китая) "
                    "и росте предложения (увеличение квот ОПЕК+). "
                    "Именно такая комбинация создаёт максимальное давление на цену."
                ),
            },
            {
                "id": "lukoil_q4",
                "title": "Независимость",
                "story": (
                    "На совещании аналитиков обсуждают уникальность ЛУКОЙЛа "
                    "среди российских нефтяных компаний. Один из них задаёт вопрос..."
                ),
                "question": "Чем ЛУКОЙЛ принципиально отличается от Роснефти и Газпрома?",
                "options": [
                    "Добывает больше нефти",
                    "Является частной компанией без государственного участия",
                    "Работает только в России",
                    "Не платит налоги",
                ],
                "correct": 1,
                "xp": 140,
                "coins": 90,
                "rep": 150,
                "explanation": (
                    "Правильно! ЛУКОЙЛ — единственная крупная российская нефтяная компания, "
                    "полностью свободная от государственного участия. "
                    "Это делает её ближе к западным нефтяным мейджорам по принципам корпоративного управления "
                    "и дивидендной политике. Роснефть и Газпром контролируются государством."
                ),
            },
            {
                "id": "lukoil_q5",
                "title": "Дивидендная история",
                "story": (
                    "Ты изучаешь историческую таблицу дивидендов ЛУКОЙЛа. "
                    "Компания известна своей дивидендной дисциплиной даже в кризисные годы..."
                ),
                "question": "Какова дивидендная политика ЛУКОЙЛа?",
                "options": [
                    "Платить дивиденды только в прибыльные годы",
                    "Направлять не менее 100% скорректированного FCF на дивиденды",
                    "Фиксированный дивиденд 10 рублей в год",
                    "Дивиденды платятся раз в 5 лет",
                ],
                "correct": 1,
                "xp": 180,
                "coins": 130,
                "rep": 180,
                "explanation": (
                    "Верно! ЛУКОЙЛ обязался направлять на дивиденды не менее 100% "
                    "скорректированного свободного денежного потока (FCF). "
                    "Это делает его одной из самых щедрых дивидендных компаний MOEX. "
                    "Дивиденды выплачиваются дважды в год."
                ),
            },
        ],
    },
}


# ── Keyboard helpers ───────────────────────────────────────────────────────────

def _game_main_kb(has_active_income: bool = False) -> object:
    b = InlineKeyboardBuilder()
    b.button(text="🗺️ Карта локаций", callback_data="game:map")
    b.button(text="💼 Мой портфель", callback_data="game:portfolio")
    b.button(text="👤 Профиль", callback_data="game:profile")
    b.button(text="◀️ Назад в меню", callback_data="back_to_menu")
    b.adjust(2, 1, 1)
    return b.as_markup()


def _location_kb(loc_id: str, quests: list, completed: set) -> object:
    b = InlineKeyboardBuilder()
    for q in quests:
        done = q["id"] in completed
        label = f"{'✅' if done else '📋'} {q['title']}"
        b.button(text=label, callback_data=f"game:quest:{loc_id}:{q['id']}")
    b.button(text="◀️ Назад к карте", callback_data="game:map")
    b.adjust(1)
    return b.as_markup()


def _quest_options_kb(loc_id: str, quest_id: str, options: list, correct: int, answered: int | None) -> object:
    b = InlineKeyboardBuilder()
    for i, opt in enumerate(options):
        if answered is None:
            label = f"{chr(0x31 + i)}️⃣ {opt}"
            cb = f"game:answer:{loc_id}:{quest_id}:{i}"
        else:
            if i == correct:
                label = f"✅ {opt}"
            elif i == answered:
                label = f"❌ {opt}"
            else:
                label = f"   {opt}"
            cb = f"game:noop"
        b.button(text=label, callback_data=cb)
    if answered is not None:
        b.button(text="▶️ Продолжить", callback_data=f"game:location:{loc_id}")
    b.adjust(1)
    return b.as_markup()


# ── Entry point: game button in main menu ─────────────────────────────────────

@router.callback_query(F.data == "game:open")
async def game_open(callback: CallbackQuery, state: FSMContext):
    """Gate: admin → game menu; regular user → stub alert."""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer(
            "🚧 Игра находится в разработке. Скоро откроем доступ!",
            show_alert=True,
        )
        return

    await state.clear()
    player = await game_get_or_create_player(callback.from_user.id)
    streak = await game_update_streak(callback.from_user.id)

    level, xp_in, xp_need = parse_level(player["xp"])
    bar = xp_bar(xp_in, xp_need)

    streak_msg = ""
    if streak and streak > 1:
        streak_msg = f"\n🔥 Стрик: {streak} дн. подряд — продолжай!"
    elif streak == 1:
        streak_msg = "\n🌅 Добро пожаловать! Стрик начат."

    text = (
        f"🎮 <b>ИНВЕСТОР: ВОСХОЖДЕНИЕ</b>\n"
        f"<i>Стань легендой фондового рынка России</i>\n\n"
        f"📊 Уровень <b>{level}</b> | XP: {xp_in}/{xp_need}\n"
        f"[{bar}]\n"
        f"💰 Монеты: <b>{player['coins']:,}</b>"
        f"{streak_msg}\n\n"
        f"Выбери действие:"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=_game_main_kb())
    await callback.answer()


# ── Map (location list) ────────────────────────────────────────────────────────

@router.callback_query(F.data == "game:map")
async def game_map(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return

    completed = await game_get_completed_quests(callback.from_user.id)
    loc_progress = await game_get_location_progress(callback.from_user.id)

    lines = ["🗺️ <b>КАРТА ЛОКАЦИЙ</b>\n"]
    b = InlineKeyboardBuilder()

    for loc_id, loc in LOCATIONS.items():
        total_q = len(loc["quests"])
        done_q = sum(1 for q in loc["quests"] if q["id"] in completed)
        rep = loc_progress.get(loc_id, {}).get("reputation", 0)
        rank = _get_rank(loc, rep)

        lines.append(
            f"{loc['emoji']} <b>{loc['name']}</b> [{loc['sector']}]\n"
            f"   Квесты: {done_q}/{total_q} | Репутация: {rep} ({rank})\n"
            f"   Доход: {loc['income_per_hour']} ИР/час\n"
        )
        b.button(
            text=f"{loc['emoji']} {loc['name']} ({done_q}/{total_q})",
            callback_data=f"game:location:{loc_id}",
        )

    b.button(text="◀️ Назад", callback_data="game:open")
    b.adjust(1)

    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=b.as_markup())
    await callback.answer()


def _get_rank(loc: dict, rep: int) -> str:
    ranks = loc["rep_rank"]
    thresholds = loc["rep_thresholds"]
    rank = ranks[0]
    for i, thresh in enumerate(thresholds):
        if rep >= thresh:
            rank = ranks[i]
    return rank


# ── Location detail ────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("game:location:"))
async def game_location(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return

    await state.clear()
    loc_id = callback.data[len("game:location:"):]
    loc = LOCATIONS.get(loc_id)
    if not loc:
        await callback.answer("Локация не найдена", show_alert=True)
        return

    completed = await game_get_completed_quests(callback.from_user.id)
    loc_progress = await game_get_location_progress(callback.from_user.id)
    rep = loc_progress.get(loc_id, {}).get("reputation", 0)
    shares = loc_progress.get(loc_id, {}).get("shares", 0)
    rank = _get_rank(loc, rep)

    done_q = sum(1 for q in loc["quests"] if q["id"] in completed)

    text = (
        f"{loc['emoji']} <b>{loc['name']}</b>\n"
        f"<i>{loc['sector']}</i>\n\n"
        f"{loc['description']}\n\n"
        f"🏅 Репутация: <b>{rep}</b> — {rank}\n"
        f"📈 Акций: <b>{shares}</b> (+{loc['income_per_hour']} ИР/час каждая)\n"
        f"✅ Квестов пройдено: {done_q}/{len(loc['quests'])}\n\n"
        f"Выбери квест:"
    )
    kb = _location_kb(loc_id, loc["quests"], completed)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


# ── Quest display ──────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("game:quest:"))
async def game_quest(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return

    parts = callback.data.split(":")  # game:quest:loc_id:quest_id
    loc_id, quest_id = parts[2], parts[3]
    loc = LOCATIONS.get(loc_id)
    if not loc:
        await callback.answer("Локация не найдена", show_alert=True)
        return

    quest = next((q for q in loc["quests"] if q["id"] == quest_id), None)
    if not quest:
        await callback.answer("Квест не найден", show_alert=True)
        return

    completed = await game_get_completed_quests(callback.from_user.id)
    already_done = quest_id in completed

    text = (
        f"{loc['emoji']} <b>{loc['name']}</b> › {quest['title']}\n\n"
        f"<i>{quest['story']}</i>\n\n"
        f"❓ <b>{quest['question']}</b>"
    )

    if already_done:
        text += "\n\n✅ <i>Этот квест уже пройден. Можно пройти заново для повторения (XP не начисляется).</i>"

    kb = _quest_options_kb(loc_id, quest_id, quest["options"], quest["correct"], None)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await state.set_state(GameState.in_quest)
    await state.update_data(loc_id=loc_id, quest_id=quest_id)
    await callback.answer()


# ── Answer processing ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("game:answer:"))
async def game_answer(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return

    parts = callback.data.split(":")  # game:answer:loc_id:quest_id:answer_idx
    loc_id, quest_id, answer_idx = parts[2], parts[3], int(parts[4])
    loc = LOCATIONS.get(loc_id)
    quest = next((q for q in loc["quests"] if q["id"] == quest_id), None) if loc else None

    if not quest:
        await callback.answer("Квест не найден", show_alert=True)
        return

    is_correct = answer_idx == quest["correct"]
    completed = await game_get_completed_quests(callback.from_user.id)
    already_done = quest_id in completed

    # Award XP/coins/rep only on first completion
    xp_gained = quest["xp"] if (is_correct and not already_done) else 0
    coins_gained = quest["coins"] if (is_correct and not already_done) else 0
    rep_gained = quest["rep"] if (is_correct and not already_done) else (quest["rep"] // 3 if is_correct else 0)

    if is_correct and not already_done:
        await game_save_quest_result(callback.from_user.id, quest_id, loc_id, xp_gained, coins_gained, rep_gained)
    elif is_correct:
        # Repeat pass — give partial rep only
        await game_save_quest_result(callback.from_user.id, quest_id, loc_id, 0, 0, rep_gained)

    player = await game_get_or_create_player(callback.from_user.id)
    level, xp_in, xp_need = parse_level(player["xp"])

    if is_correct:
        result_header = "✅ <b>Верно!</b>"
        reward_line = (
            f"\n\n🎁 Награда: +{xp_gained} XP, +{coins_gained} монет, +{rep_gained} репутации"
            if not already_done else
            f"\n\n🔄 <i>Повтор: репутация +{rep_gained}</i>"
        )
    else:
        result_header = "❌ <b>Неверно.</b>"
        reward_line = ""

    text = (
        f"{loc['emoji']} <b>{loc['name']}</b> › {quest['title']}\n\n"
        f"{result_header}\n\n"
        f"💡 <b>Объяснение:</b>\n{quest['explanation']}"
        f"{reward_line}\n\n"
        f"📊 Уровень {level} | XP {xp_in}/{xp_need}"
    )

    kb = _quest_options_kb(loc_id, quest_id, quest["options"], quest["correct"], answer_idx)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await state.clear()
    await callback.answer("✅ Верно!" if is_correct else "❌ Неверно")


@router.callback_query(F.data == "game:noop")
async def game_noop(callback: CallbackQuery):
    await callback.answer()


# ── Portfolio ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "game:portfolio")
async def game_portfolio(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return

    loc_progress = await game_get_location_progress(callback.from_user.id)
    lines = ["💼 <b>МОЙ ПОРТФЕЛЬ</b>\n"]
    b = InlineKeyboardBuilder()
    total_income = 0

    for loc_id, loc in LOCATIONS.items():
        progress = loc_progress.get(loc_id, {})
        shares = progress.get("shares", 0)
        income = shares * loc["income_per_hour"]
        total_income += income

        last_collected = progress.get("last_collected")
        pending = _calc_pending(last_collected, income) if shares > 0 else 0

        lines.append(
            f"{loc['emoji']} <b>{loc['name']}</b>\n"
            f"   Акций: {shares} × {loc['income_per_hour']} ИР/ч = {income} ИР/ч\n"
            f"   Накоплено: <b>{pending} ИР</b>\n"
        )
        if shares > 0 and pending > 0:
            b.button(
                text=f"💰 Собрать {pending} ИР из {loc['name']}",
                callback_data=f"game:collect:{loc_id}",
            )

    lines.append(f"\n📈 Итого доходность: <b>{total_income} ИР/час</b>")
    lines.append("\n<i>Акции зарабатываются за выполнение квестов.</i>")

    b.button(text="◀️ Назад", callback_data="game:open")
    b.adjust(1)

    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=b.as_markup())
    await callback.answer()


def _calc_pending(last_collected: str | None, income_per_hour: int) -> int:
    if not last_collected or income_per_hour == 0:
        return 0
    try:
        last = datetime.fromisoformat(last_collected)
        now = datetime.utcnow()
        hours = min((now - last).total_seconds() / 3600, 12)  # cap at 12h
        return int(hours * income_per_hour)
    except Exception:
        return 0


@router.callback_query(F.data.startswith("game:collect:"))
async def game_collect(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return

    loc_id = callback.data[len("game:collect:"):]
    loc = LOCATIONS.get(loc_id)
    if not loc:
        await callback.answer("Локация не найдена", show_alert=True)
        return

    loc_progress = await game_get_location_progress(callback.from_user.id)
    progress = loc_progress.get(loc_id, {})
    shares = progress.get("shares", 0)
    income = shares * loc["income_per_hour"]
    pending = _calc_pending(progress.get("last_collected"), income)

    if pending <= 0:
        await callback.answer("Нечего собирать — приходи позже!", show_alert=True)
        return

    await game_collect_income(callback.from_user.id, loc_id, pending)
    await callback.answer(f"💰 Собрано {pending} ИР из {loc['name']}!", show_alert=True)
    # Refresh portfolio view
    callback.data = "game:portfolio"
    await game_portfolio(callback)


# ── Profile ────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "game:profile")
async def game_profile(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return

    player = await game_get_or_create_player(callback.from_user.id)
    completed = await game_get_completed_quests(callback.from_user.id)
    loc_progress = await game_get_location_progress(callback.from_user.id)

    level, xp_in, xp_need = parse_level(player["xp"])
    bar = xp_bar(xp_in, xp_need, 12)

    total_quests = sum(len(loc["quests"]) for loc in LOCATIONS.values())
    done_quests = len(completed)

    total_rep = sum(p.get("reputation", 0) for p in loc_progress.values())

    lines = [
        f"👤 <b>ПРОФИЛЬ ИГРОКА</b>\n",
        f"🎖️ Уровень: <b>{level}</b>",
        f"⭐ XP: {player['xp']:,} ({xp_in}/{xp_need} до ур. {level + 1})",
        f"[{bar}]",
        f"💰 Монеты: <b>{player['coins']:,}</b>",
        f"🔥 Стрик: <b>{player['streak_days']} дн.</b>",
        f"\n📋 Квестов пройдено: {done_quests}/{total_quests}",
        f"🏅 Суммарная репутация: {total_rep}",
        f"\n<b>По локациям:</b>",
    ]

    for loc_id, loc in LOCATIONS.items():
        p = loc_progress.get(loc_id, {})
        rep = p.get("reputation", 0)
        shares = p.get("shares", 0)
        done = sum(1 for q in loc["quests"] if q["id"] in completed)
        rank = _get_rank(loc, rep)
        lines.append(
            f"{loc['emoji']} {loc['name']}: {done}/{len(loc['quests'])} квестов, "
            f"реп {rep} ({rank}), акций {shares}"
        )

    b = InlineKeyboardBuilder()
    b.button(text="◀️ Назад", callback_data="game:open")

    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=b.as_markup())
    await callback.answer()
