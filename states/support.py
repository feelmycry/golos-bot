from aiogram.fsm.state import State, StatesGroup


class SupportState(StatesGroup):
    writing_message = State()
