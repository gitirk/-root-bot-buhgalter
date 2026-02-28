"""In-memory история чатов — последние N сообщений на пользователя."""

from collections import deque

MAX_MESSAGES = 30

_history: dict[int, deque[dict[str, str]]] = {}


def get_history(user_id: int) -> list[dict[str, str]]:
    """Возвращает историю сообщений пользователя."""
    return list(_history.get(user_id, []))


def add_message(user_id: int, role: str, content: str) -> None:
    """Добавляет сообщение в историю (role: 'user' | 'assistant')."""
    if user_id not in _history:
        _history[user_id] = deque(maxlen=MAX_MESSAGES)
    _history[user_id].append({"role": role, "content": content})


def clear_history(user_id: int) -> None:
    """Очищает историю пользователя."""
    _history.pop(user_id, None)
