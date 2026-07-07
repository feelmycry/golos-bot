from aiogram.fsm.state import State, StatesGroup


class SupportState(StatesGroup):
    writing_message = State()


class AdminReply(StatesGroup):
    writing_reply = State()
