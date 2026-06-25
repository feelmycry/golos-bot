from aiogram.fsm.state import State, StatesGroup


class GameState(StatesGroup):
    in_quest = State()
