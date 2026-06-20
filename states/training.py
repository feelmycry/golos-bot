from aiogram.fsm.state import State, StatesGroup


class Training(StatesGroup):
    choosing_scenario = State()
    choosing_mode = State()
    choosing_stage = State()
    choosing_product = State()
    choosing_cohort = State()
    in_dialog = State()
