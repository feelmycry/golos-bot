from aiogram.fsm.state import State, StatesGroup


class GameState(StatesGroup):
    in_quest = State()


class GuildState(StatesGroup):
    entering_name  = State()
    entering_emoji = State()
    entering_code  = State()
