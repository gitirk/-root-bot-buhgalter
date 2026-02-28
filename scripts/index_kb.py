#!/usr/bin/env python3
"""Скрипт индексации knowledge_base/ в ChromaDB."""

import sys
from pathlib import Path

# Добавляем корень проекта в sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.services.rag import index_directory  # noqa: E402

KB_PATH = Path(__file__).resolve().parent.parent / "knowledge_base"


def main():
    print(f"Индексация базы знаний из {KB_PATH}")
    if not KB_PATH.exists():
        print(f"❌ Каталог {KB_PATH} не найден")
        sys.exit(1)

    total = index_directory(KB_PATH)
    print(f"✅ Готово. Проиндексировано {total} чанков.")


if __name__ == "__main__":
    main()
