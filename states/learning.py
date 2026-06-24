from aiogram.fsm.state import State, StatesGroup


class LearningState(StatesGroup):
    taking_quiz = State()
