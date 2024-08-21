import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
class Config:
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    TINKOFF_SANDBOX_TOKEN = os.getenv('TINKOFF_SANDBOX_TOKEN')
    TINKOFF_REAL_TOKEN = os.getenv('TINKOFF_REAL_TOKEN')
    TEST_CHAT_ID = 6166420250
    DB_FILE_PATH = "data.json"
