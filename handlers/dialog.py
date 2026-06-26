import random
from io import BytesIO

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from states.training import Training
from services.whisper import transcribe_voice
from services.claude import continue_dialog, get_feedback, get_session_summary
from services.db import update_messages, complete_session

router = Router()

# Emojis shown between client phrases to add variety
_REACTION_EMOJIS = ["🤔", "💭", "🙄", "😊", "😐", "🧐", "💬", "👀", "😮", "🫤"]


def _dialog_kb():
    b = InlineKeyboardBuilder()
    b.button(text="💡 Подсказка", callback_data="dialog:hint")
    b.button(text="🏁 Завершить", callback_data="dialog:end")
    b.adjust(2)
    return b.as_markup()


def _after_end_kb():
    b = InlineKeyboardBuilder()
    b.button(text="🔄 Новая тренировка", callback_data="start_training")
    b.button(text="📊 Статистика", callback_data="show_stats")
    b.adjust(1)
    return b.as_markup()


async def _send_client_reply(message: Message, client_reply: str, msg_count: int, photo_urls: list) -> None:
    """Send client reply, adding a photo on every 2nd exchange."""
    emoji = random.choice(_REACTION_EMOJIS)
    text = f"{emoji} <b>Клиент отвечает:</b>\n\n<i>«{client_reply}»</i>\n\n🎙 Ваш следующий ответ:"

    # Show photo every 2nd client response
    if msg_count % 2 == 0 and photo_urls:
        photo_url = photo_urls[msg_count % len(photo_urls)]
        try:
            await message.answer_photo(
                photo=photo_url,
                caption=text,
                parse_mode="HTML",
                reply_markup=_dialog_kb(),
            )
            return
        except Exception:
            pass  # Fall through to text-only

    await message.answer(text, parse_mode="HTML", reply_markup=_dialog_kb())


@router.message(Training.in_dialog, F.voice)
async def handle_voice(message: Message, state: FSMContext):
    data = await state.get_data()
    profile = data["client_profile"]
    messages: list = data["messages"]
    stage: str = data["target_stage"]
    product: str | None = data.get("product")
    session_id: int = data["session_id"]
    msg_count: int = data.get("msg_count", 0) + 1
    photo_urls: list = data.get("photo_urls", [])

    status = await message.answer("🎧 Распознаю голос...")

    # Download voice
    bio = BytesIO()
    await message.bot.download(message.voice, destination=bio)
    bio.seek(0)

    # Transcribe
    try:
        transcription = await transcribe_voice(bio.read())
    except Exception as e:
        await status.edit_text(f"❌ Ошибка распознавания речи: {e}")
        return

    if not transcription:
        await status.edit_text(
            "❌ Не удалось распознать речь. Попробуйте говорить чётче.",
            reply_markup=_dialog_kb(),
        )
        return

    messages.append({"role": "employee", "content": transcription})

    await status.edit_text("🤔 Клиент думает...")

    try:
        client_reply = await continue_dialog(profile, stage, messages, product)
    except Exception as e:
        await status.edit_text(f"❌ Ошибка AI: {e}")
        return

    messages.append({"role": "client", "content": client_reply})

    await state.update_data(messages=messages, msg_count=msg_count)
    await update_messages(session_id, messages)

    await status.delete()

    # Show what employee said
    await message.answer(
        f"📝 <b>Вы сказали:</b>\n<i>{transcription}</i>",
        parse_mode="HTML",
    )

    # Show client reply (with photo every 2nd time)
    await _send_client_reply(message, client_reply, msg_count, photo_urls)


@router.message(Training.in_dialog, ~F.voice)
async def handle_non_voice(message: Message):
    await message.answer(
        "🎙 Пожалуйста, отправьте <b>голосовое сообщение</b> с вашим ответом.",
        parse_mode="HTML",
        reply_markup=_dialog_kb(),
    )


@router.callback_query(Training.in_dialog, F.data == "dialog:hint")
async def handle_hint(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    messages: list = data["messages"]
    stage: str = data["target_stage"]
    product: str | None = data.get("product")

    last_employee = next(
        (m["content"] for m in reversed(messages) if m["role"] == "employee"),
        None,
    )
    if not last_employee:
        await callback.answer("Сначала отправьте хотя бы один голосовой ответ!", show_alert=True)
        return

    await callback.answer("Анализирую...")
    hint_msg = await callback.message.answer("💡 Анализирую ваш ответ...")

    try:
        feedback = await get_feedback(messages, last_employee, stage, product)
        await hint_msg.edit_text(
            f"💡 <b>Подсказка тренера:</b>\n\n{feedback}",
            parse_mode="HTML",
        )
    except Exception as e:
        await hint_msg.edit_text(f"❌ Ошибка: {e}")


@router.callback_query(Training.in_dialog, F.data == "dialog:end")
async def handle_end(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    messages: list = data["messages"]
    stage: str = data["target_stage"]
    product: str | None = data.get("product")
    profile: dict = data["client_profile"]
    session_id: int = data["session_id"]

    employee_turns = [m for m in messages if m["role"] == "employee"]
    if not employee_turns:
        await callback.answer("Вы ещё не сделали ни одного ответа!", show_alert=True)
        return

    await callback.answer("Завершаю...")
    summary_msg = await callback.message.answer("📊 Готовлю итоговый анализ...")

    try:
        summary = await get_session_summary(messages, stage, product, profile)
        await complete_session(session_id, summary)
        await summary_msg.edit_text(
            f"🏁 <b>Сессия завершена!</b>\n\n{summary}",
            parse_mode="HTML",
            reply_markup=_after_end_kb(),
        )
        await state.clear()
    except Exception as e:
        await summary_msg.edit_text(f"❌ Ошибка при формировании итогов: {e}")


@router.callback_query(F.data == "dialog:end")
async def handle_end_stale(callback: CallbackQuery, state: FSMContext):
    """Fallback: кнопка «Завершить» нажата, но state устарел (перезапуск бота)."""
    await state.clear()
    await callback.answer("Сессия устарела после перезапуска бота.", show_alert=True)
    await callback.message.answer(
        "⚠️ Сессия была прервана перезапуском бота.\n\n"
        "Нажми /start чтобы начать заново.",
    )


@router.callback_query(F.data == "dialog:hint")
async def handle_hint_stale(callback: CallbackQuery, state: FSMContext):
    """Fallback: кнопка «Подсказка» нажата после перезапуска."""
    await state.clear()
    await callback.answer("Сессия устарела после перезапуска бота.", show_alert=True)
