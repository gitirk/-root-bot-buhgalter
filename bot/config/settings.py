"""Настройки приложения — загрузка из .env через pydantic-settings."""

import json
import logging
from pathlib import Path

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

USERS_FILE = Path("/app/data/allowed_users.json")


class Settings(BaseSettings):
    # Telegram
    bot_token: str = ""
    allowed_chat_ids: str = ""

    # AI API
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # ChromaDB
    chroma_host: str = "chromadb"
    chroma_port: int = 8000

    # PostgreSQL
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "buhgalter"
    postgres_user: str = "buhgalter"
    postgres_password: str = ""

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @property
    def admin_id(self) -> int:
        """Первый ID в ALLOWED_CHAT_IDS считается администратором."""
        if not self.allowed_chat_ids:
            return 0
        first = self.allowed_chat_ids.split(",")[0].strip()
        return int(first) if first else 0

    def _parse_allowed(self) -> set[int]:
        if not self.allowed_chat_ids:
            return set()
        return {
            int(x.strip())
            for x in self.allowed_chat_ids.split(",")
            if x.strip()
        }


settings = Settings()


def _load_persistent_users() -> set[int]:
    """Загружает сохранённых пользователей из JSON-файла."""
    if USERS_FILE.exists():
        try:
            data = json.loads(USERS_FILE.read_text())
            return {int(uid) for uid in data}
        except Exception as e:
            logger.error("Ошибка чтения %s: %s", USERS_FILE, e)
    return set()


def save_users() -> None:
    """Сохраняет текущий whitelist в JSON-файл."""
    try:
        USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        USERS_FILE.write_text(json.dumps(sorted(allowed_users)))
        logger.info("Whitelist сохранён: %d пользователей", len(allowed_users))
    except Exception as e:
        logger.error("Ошибка записи %s: %s", USERS_FILE, e)


# Динамический whitelist — объединяем .env и сохранённый файл
allowed_users: set[int] = settings._parse_allowed() | _load_persistent_users()
