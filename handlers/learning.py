import html as _html
import json
import random
import re
from html.parser import HTMLParser
from pathlib import Path

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_IDS
from services.db import get_learning_progress, mark_lesson_read, save_quiz_result
from services.subscription import is_product_subscribed
from states.learning import LearningState

FREE_LESSONS_M1 = 6  # first N lessons are free

router = Router()

# ── Load course data ──────────────────────────────────────────────────────────

_COURSE_PATH = Path(__file__).parent.parent / "data" / "course.json"
_course: dict = {}


def _get_course() -> dict:
    global _course
    if not _course:
        _course = json.loads(_COURSE_PATH.read_text(encoding="utf-8"))
    return _course


def _get_module(mod_id: str) -> dict | None:
    for m in _get_course()["modules"]:
        if m["id"] == mod_id:
            return m
    return None


def _get_lesson(lesson_id: str) -> tuple[dict | None, dict | None]:
    """Returns (module, lesson)."""
    for m in _get_course()["modules"]:
        for l in m["lessons"]:
            if l["id"] == lesson_id:
                return m, l
    return None, None


def _all_lessons_for_module(mod_id: str) -> list[dict]:
    m = _get_module(mod_id)
    return m["lessons"] if m else []


# ── Text helpers ──────────────────────────────────────────────────────────────

_PAGE_SIZE = 3500  # Telegram HTML limit is 4096; leave room for navigation


_ALLOWED_TAGS = {"b", "i", "u", "s", "code", "pre"}


class _TgHTMLCleaner(HTMLParser):
    """Parses arbitrary HTML and emits only Telegram-safe markup."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self._out: list[str] = []
        self._stack: list[str] = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in _ALLOWED_TAGS:
            self._out.append(f"<{tag}>")
            self._stack.append(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in _ALLOWED_TAGS and tag in self._stack:
            # Close everything on the stack up to this tag
            while self._stack and self._stack[-1] != tag:
                self._out.append(f"</{self._stack.pop()}>")
            if self._stack:
                self._stack.pop()
                self._out.append(f"</{tag}>")

    def handle_data(self, data):
        self._out.append(_html.escape(data, quote=False))

    def handle_entityref(self, name):
        self._out.append(f"&{name};")

    def handle_charref(self, name):
        self._out.append(f"&#{name};")

    def result(self) -> str:
        # Close any unclosed tags
        while self._stack:
            self._out.append(f"</{self._stack.pop()}>")
        return "".join(self._out)


def _clean_html(text: str) -> str:
    cleaner = _TgHTMLCleaner()
    cleaner.feed(text)
    out = cleaner.result()
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def _paginate(text: str) -> list[str]:
    """Split text into pages of ~_PAGE_SIZE chars, breaking at newlines."""
    if len(text) <= _PAGE_SIZE:
        return [text]
    pages = []
    while text:
        if len(text) <= _PAGE_SIZE:
            pages.append(text)
            break
        cut = text.rfind("\n", 0, _PAGE_SIZE)
        if cut <= 0:
            cut = _PAGE_SIZE
        pages.append(text[:cut].strip())
        text = text[cut:].strip()
    return pages


def _progress_icon(progress: dict, lesson_id: str) -> str:
    info = progress.get(lesson_id, {})
    if not info:
        return "⬜"
    if info.get("quiz_passed"):
        return "✅"
    if info.get("completed"):
        return "📖"
    return "⬜"


# ── Module/lesson level numbers ───────────────────────────────────────────────

_MOD_LABELS = {
    "m1": ("🚀", "Базовый уровень"),
    "m2": ("📊", "Средний уровень"),
    "m3": ("🏆", "Профессиональный уровень"),
}

# Product key per paid module
_MOD_PRODUCT = {"m2": "learning_medium", "m3": "learning_pro"}

# ── Menu: 3 modules ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "learning:menu")
async def learning_menu(callback: CallbackQuery):
    await callback.answer()
    course = _get_course()
    kb = InlineKeyboardBuilder()

    is_admin = callback.from_user.id in ADMIN_IDS
    for mod in course["modules"]:
        icon, label = _MOD_LABELS.get(mod["id"], ("📚", mod["level"]))
        product = _MOD_PRODUCT.get(mod["id"])
        if product and not is_admin:
            has_access = await is_product_subscribed(callback.from_user.id, product)
            if has_access:
                kb.row(InlineKeyboardButton(
                    text=f"{icon} {label}",
                    callback_data=f"learn:mod:{mod['id']}",
                ))
            else:
                kb.row(InlineKeyboardButton(
                    text=f"🔒 {label} — 200 ₽",
                    callback_data=f"learn:mod:{mod['id']}",
                ))
        else:
            kb.row(InlineKeyboardButton(
                text=f"{icon} {label}" + (" 👁" if is_admin and product else ""),
                callback_data=f"learn:mod:{mod['id']}",
            ))
    kb.row(InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_to_menu"))

    await callback.message.edit_text(
        "📚 <b>Обучение</b>\n\n"
        "Курс по инвестициям, фондовому рынку и макроэкономике.\n"
        "Выберите уровень:",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


# ── Lesson list for a module ──────────────────────────────────────────────────

@router.callback_query(F.data.startswith("learn:mod:"))
async def module_lessons(callback: CallbackQuery):
    mod_id = callback.data[len("learn:mod:"):]
    is_admin = callback.from_user.id in ADMIN_IDS

    # Paywall for m2 / m3
    product = _MOD_PRODUCT.get(mod_id)
    if product and not is_admin:
        has_access = await is_product_subscribed(callback.from_user.id, product)
        if not has_access:
            from handlers.payment import show_learning_medium_paywall, show_learning_pro_paywall
            if mod_id == "m2":
                await show_learning_medium_paywall(callback)
            else:
                await show_learning_pro_paywall(callback)
            return

    await callback.answer()
    mod = _get_module(mod_id)
    if not mod:
        await callback.answer("Модуль не найден", show_alert=True)
        return

    progress = await get_learning_progress(callback.from_user.id)
    lessons = mod["lessons"]

    completed = sum(1 for l in lessons if progress.get(l["id"], {}).get("completed"))
    icon, label = _MOD_LABELS.get(mod_id, ("📚", mod["level"]))

    lines = [
        f"{icon} <b>{label}</b>",
        f"<i>{mod['description']}</i>",
        f"\nПройдено: {completed}/{len(lessons)} уроков\n",
    ]

    is_admin = callback.from_user.id in ADMIN_IDS
    kb = InlineKeyboardBuilder()
    for i, lesson in enumerate(lessons):
        p_icon = _progress_icon(progress, lesson["id"])
        dur = f"{lesson['duration']} мин"
        is_locked = mod_id == "m1" and i >= FREE_LESSONS_M1 and not is_admin
        lock = "🔒 " if is_locked else ""
        kb.row(InlineKeyboardButton(
            text=f"{p_icon} {lock}{lesson['title']} · {dur}",
            callback_data=f"learn:lesson:{lesson['id']}:0",
        ))

    kb.row(InlineKeyboardButton(text="◀️ К уровням", callback_data="learning:menu"))

    await callback.message.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


# ── Lesson content (paginated) ────────────────────────────────────────────────

import logging as _logging
_log = _logging.getLogger(__name__)

@router.callback_query(F.data.startswith("learn:lesson:"))
async def show_lesson(callback: CallbackQuery):
    try:
        await callback.answer()
        parts = callback.data.split(":")
        # learn:lesson:{lesson_id}:{page}
        lesson_id = parts[2]
        page = int(parts[3]) if len(parts) > 3 else 0

        _log.info("show_lesson: user=%s lesson=%s page=%s", callback.from_user.id, lesson_id, page)

        mod, lesson = _get_lesson(lesson_id)
        if not lesson:
            _log.warning("show_lesson: lesson %s not found", lesson_id)
            await callback.message.answer(f"⚠️ Урок <code>{lesson_id}</code> не найден в курсе.", parse_mode="HTML")
            return

        is_admin = callback.from_user.id in ADMIN_IDS

        # Paywall: m1 lessons 7+ require learning_basic subscription
        if mod and mod["id"] == "m1" and not is_admin:
            lesson_num = int(lesson_id[3:]) if lesson_id[2:3] == "l" and lesson_id[3:].isdigit() else 0
            if lesson_num > FREE_LESSONS_M1:
                if not await is_product_subscribed(callback.from_user.id, "learning_basic"):
                    from handlers.payment import show_learning_paywall
                    await show_learning_paywall(callback)
                    return

        # Paywall: m2 / m3 require separate product subscription
        if mod and not is_admin:
            product = _MOD_PRODUCT.get(mod["id"])
            if product and not await is_product_subscribed(callback.from_user.id, product):
                from handlers.payment import show_learning_medium_paywall, show_learning_pro_paywall
                if mod["id"] == "m2":
                    await show_learning_medium_paywall(callback)
                else:
                    await show_learning_pro_paywall(callback)
                return

        content = _clean_html(lesson["content"])
        pages = _paginate(content)
        total_pages = len(pages)
        page = max(0, min(page, total_pages - 1))
        page_text = pages[page]

        _log.info("show_lesson: %s pages, page %s, content_len=%s", total_pages, page, len(content))

        header = (
            f"📖 <b>{_html.escape(lesson['title'])}</b>\n"
            f"<i>⏱ {lesson['duration']} мин · ⭐ {lesson['xp']} XP</i>"
        )
        if total_pages > 1:
            header += f" · Стр {page + 1}/{total_pages}"

        text = f"{header}\n\n{page_text}"

        kb = InlineKeyboardBuilder()

        # Pagination
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(
                text="◀️ Назад",
                callback_data=f"learn:lesson:{lesson_id}:{page - 1}",
            ))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(
                text="Далее ▶️",
                callback_data=f"learn:lesson:{lesson_id}:{page + 1}",
            ))
        if nav:
            kb.row(*nav)

        # On last page: quiz button or "complete" button
        if page == total_pages - 1:
            if lesson.get("quiz"):
                kb.row(InlineKeyboardButton(
                    text="🧠 Пройти тест",
                    callback_data=f"learn:quiz:{lesson_id}:0",
                ))
            else:
                kb.row(InlineKeyboardButton(
                    text="✅ Отметить как прочитанное",
                    callback_data=f"learn:done:{lesson_id}",
                ))

        # Back to module
        mod_id = mod["id"] if mod else "m1"
        kb.row(InlineKeyboardButton(text="◀️ К урокам", callback_data=f"learn:mod:{mod_id}"))

        # Mark as read when user opens lesson (even on page 0)
        if page == 0:
            await mark_lesson_read(callback.from_user.id, lesson_id)

        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
        except Exception as html_err:
            _log.warning("HTML parse failed for %s: %s — sending plain text", lesson_id, html_err)
            plain = re.sub(r"<[^>]+>", "", text).replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
            await callback.message.edit_text(plain, reply_markup=kb.as_markup())

    except Exception as e:
        _log.exception("show_lesson FAILED for %s", callback.data)
        try:
            await callback.message.answer(f"⚠️ Ошибка: {type(e).__name__}: {e}")
        except Exception:
            pass


@router.callback_query(F.data.startswith("learn:done:"))
async def lesson_done(callback: CallbackQuery):
    lesson_id = callback.data[len("learn:done:"):]
    await mark_lesson_read(callback.from_user.id, lesson_id)
    mod, lesson = _get_lesson(lesson_id)
    mod_id = mod["id"] if mod else "m1"
    await callback.answer("✅ Урок отмечен как прочитанный!", show_alert=False)
    # Return to module list
    callback.data = f"learn:mod:{mod_id}"
    await module_lessons(callback)


# ── Quiz ──────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("learn:quiz:"))
async def show_quiz_question(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    parts = callback.data.split(":")
    lesson_id = parts[2]
    q_idx = int(parts[3]) if len(parts) > 3 else 0

    mod, lesson = _get_lesson(lesson_id)
    if not lesson or not lesson.get("quiz"):
        await callback.answer("Тест не найден", show_alert=True)
        return

    quiz = lesson["quiz"]
    if q_idx >= len(quiz):
        # Quiz finished — show results
        await _show_quiz_results(callback, state, lesson_id)
        return

    q = quiz[q_idx]
    total = len(quiz)
    labels = ["А", "Б", "В", "Г", "Д", "Е", "Ж", "З"]

    # Shuffle answer options; store mapping so handle_answer can check correctness
    n = len(q["options"])
    shuffle_map = list(range(n))
    random.shuffle(shuffle_map)
    # shuffle_map[display_pos] = original_index

    text = (
        f"🧠 <b>Тест: {lesson['title']}</b>\n"
        f"<i>Вопрос {q_idx + 1} из {total}</i>\n\n"
        f"<b>{q['q']}</b>\n\n"
    )
    for display_pos in range(n):
        text += f"{labels[display_pos]}) {q['options'][shuffle_map[display_pos]]}\n"

    kb = InlineKeyboardBuilder()
    for display_pos in range(n):
        kb.button(
            text=labels[display_pos],
            callback_data=f"learn:ans:{lesson_id}:{q_idx}:{display_pos}",
        )
    kb.adjust(2)
    kb.row(InlineKeyboardButton(
        text="❌ Выйти из теста",
        callback_data=f"learn:lesson:{lesson_id}:0",
    ))

    await state.set_state(LearningState.taking_quiz)
    if q_idx == 0:
        await state.update_data(lesson_id=lesson_id, q_idx=q_idx, score=0, shuffle_map=shuffle_map)
    else:
        await state.update_data(lesson_id=lesson_id, q_idx=q_idx, shuffle_map=shuffle_map)

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("learn:ans:"))
async def handle_answer(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    lesson_id = parts[2]
    q_idx = int(parts[3])
    chosen = int(parts[4])

    mod, lesson = _get_lesson(lesson_id)
    if not lesson:
        await callback.answer()
        return

    quiz = lesson["quiz"]
    q = quiz[q_idx]
    correct = q["correct"]  # original index of correct answer
    labels = ["А", "Б", "В", "Г", "Д", "Е", "Ж", "З"]

    # Restore shuffle map from FSM to check answer correctly
    fsm = await state.get_data()
    score = fsm.get("score", 0)
    shuffle_map = fsm.get("shuffle_map", list(range(len(q["options"]))))

    # chosen is display position; map to original index
    original_chosen = shuffle_map[chosen] if chosen < len(shuffle_map) else chosen
    is_correct = original_chosen == correct
    if is_correct:
        score += 1
    await state.update_data(score=score)

    # Which display label is the correct answer
    correct_display = shuffle_map.index(correct) if correct in shuffle_map else correct
    result_icon = "✅" if is_correct else "❌"
    answer_label = labels[correct_display] if correct_display < len(labels) else str(correct_display)
    expl = q.get("explanation", "")

    text = (
        f"🧠 <b>Тест: {lesson['title']}</b>\n"
        f"<i>Вопрос {q_idx + 1} из {len(quiz)}</i>\n\n"
        f"<b>{q['q']}</b>\n\n"
        f"{result_icon} {'Верно!' if is_correct else f'Неверно. Правильный ответ: {answer_label}'}\n"
    )
    if expl:
        text += f"\n💡 {expl}"

    next_idx = q_idx + 1
    kb = InlineKeyboardBuilder()
    if next_idx < len(quiz):
        kb.row(InlineKeyboardButton(
            text="Следующий вопрос ▶️",
            callback_data=f"learn:quiz:{lesson_id}:{next_idx}",
        ))
    else:
        kb.row(InlineKeyboardButton(
            text="📊 Результаты теста",
            callback_data=f"learn:result:{lesson_id}:{score}",
        ))

    await callback.answer("✅ Верно!" if is_correct else "❌ Неверно")
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("learn:result:"))
async def show_quiz_result(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    parts = callback.data.split(":")
    lesson_id = parts[2]
    score = int(parts[3])

    mod, lesson = _get_lesson(lesson_id)
    if not lesson:
        return

    total = len(lesson["quiz"])
    passed = score >= (total + 1) // 2
    pct = round(score / total * 100) if total else 0

    await save_quiz_result(callback.from_user.id, lesson_id, score, total)
    await state.clear()

    if passed:
        icon = "🎉"
        verdict = f"Тест пройден! ({score}/{total} — {pct}%)"
    else:
        icon = "😔"
        verdict = f"Тест не пройден ({score}/{total} — {pct}%). Попробуйте ещё раз."

    text = (
        f"{icon} <b>{verdict}</b>\n\n"
        f"<b>Урок:</b> {lesson['title']}\n"
        f"<b>XP получено:</b> {lesson['xp'] if passed else lesson['xp'] // 2} ⭐"
    )

    mod_id = mod["id"] if mod else "m1"
    kb = InlineKeyboardBuilder()
    if not passed:
        kb.row(InlineKeyboardButton(
            text="🔄 Пройти тест снова",
            callback_data=f"learn:quiz:{lesson_id}:0",
        ))
    kb.row(InlineKeyboardButton(
        text="📖 Перечитать урок",
        callback_data=f"learn:lesson:{lesson_id}:0",
    ))
    kb.row(InlineKeyboardButton(
        text="◀️ К урокам",
        callback_data=f"learn:mod:{mod_id}",
    ))

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())


async def _show_quiz_results(callback: CallbackQuery, state: FSMContext, lesson_id: str):
    fsm = await state.get_data()
    score = fsm.get("score", 0)
    callback.data = f"learn:result:{lesson_id}:{score}"
    await show_quiz_result(callback, state)
