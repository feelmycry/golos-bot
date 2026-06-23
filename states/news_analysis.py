from aiogram.fsm.state import State, StatesGroup


class NewsAnalysis(StatesGroup):
    choosing_category = State()
    choosing_product = State()
    choosing_input_mode = State()
    waiting_news = State()
