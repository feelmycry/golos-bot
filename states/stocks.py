from aiogram.fsm.state import State, StatesGroup


class StocksState(StatesGroup):
    waiting_input = State()
