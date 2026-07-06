import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
DB_PATH = os.getenv("DB_PATH", "training.db")
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()}
REDIS_URL = os.getenv("REDIS_URL", "")
MINIAPP_URL = os.getenv("MINIAPP_URL", "")
PAYMENTS_TOKEN = os.getenv("PAYMENTS_TOKEN", "")
