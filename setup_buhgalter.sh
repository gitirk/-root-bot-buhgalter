#!/bin/bash
# Создание структуры проекта бота-бухгалтера
# Запуск: bash setup_buhgalter.sh

BASE=~/bot/buhgalter
echo "=== Создаю структуру в $BASE ==="

# Каталоги
mkdir -p "$BASE/bot/handlers"
mkdir -p "$BASE/bot/config"
mkdir -p "$BASE/bot/services"
mkdir -p "$BASE/bot/utils"
mkdir -p "$BASE/knowledge_base/regional"
mkdir -p "$BASE/knowledge_base/federal"
mkdir -p "$BASE/knowledge_base/fsbu"
mkdir -p "$BASE/chroma_data"
mkdir -p "$BASE/templates"
mkdir -p "$BASE/scripts"

# Перенести существующий файл базы знаний
if [ -f "$BASE/knowledge-base-irkutsk-region (1).md" ]; then
    mv "$BASE/knowledge-base-irkutsk-region (1).md" "$BASE/knowledge_base/regional/irkutsk_region.md"
    echo "✓ Перенесён irkutsk_region.md"
elif [ -f "$BASE/knowledge-base-irkutsk-region.md" ]; then
    mv "$BASE/knowledge-base-irkutsk-region.md" "$BASE/knowledge_base/regional/irkutsk_region.md"
    echo "✓ Перенесён irkutsk_region.md"
fi

# __init__.py
touch "$BASE/bot/__init__.py"
touch "$BASE/bot/handlers/__init__.py"
touch "$BASE/bot/config/__init__.py"
touch "$BASE/bot/services/__init__.py"
touch "$BASE/bot/utils/__init__.py"

# .env шаблон
cat > "$BASE/.env.example" << 'EOF'
# Telegram
BOT_TOKEN=your_telegram_bot_token
ALLOWED_CHAT_IDS=123456789,987654321

# AI API
OPENAI_API_KEY=your_openai_key
# или
ANTHROPIC_API_KEY=your_anthropic_key

# ChromaDB
CHROMA_HOST=chromadb
CHROMA_PORT=8000

# PostgreSQL
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=buhgalter
POSTGRES_USER=buhgalter
POSTGRES_PASSWORD=change_me_strong_password
EOF

# .gitignore
cat > "$BASE/.gitignore" << 'EOF'
.env
__pycache__/
*.pyc
chroma_data/
*.log
.vscode/
EOF

# requirements.txt
cat > "$BASE/requirements.txt" << 'EOF'
aiogram==3.15.0
chromadb==0.5.23
openai==1.60.0
anthropic==0.42.0
python-dotenv==1.0.1
asyncpg==0.30.0
sqlalchemy[asyncio]==2.0.36
python-docx==1.1.2
openpyxl==3.1.5
reportlab==4.2.5
aiohttp==3.11.11
pydantic==2.10.4
pydantic-settings==2.7.1
EOF

# docker-compose.yml
cat > "$BASE/docker-compose.yml" << 'EOF'
version: "3.8"

services:
  bot:
    build: .
    container_name: buhgalter-bot
    restart: unless-stopped
    env_file: .env
    volumes:
      - ./knowledge_base:/app/knowledge_base:ro
      - ./templates:/app/templates:ro
      - ./chroma_data:/app/chroma_data
    depends_on:
      - chromadb
      - postgres
    networks:
      - buhgalter

  chromadb:
    image: chromadb/chroma:0.5.23
    container_name: buhgalter-chroma
    restart: unless-stopped
    volumes:
      - ./chroma_data:/chroma/chroma
    ports:
      - "127.0.0.1:8100:8000"
    networks:
      - buhgalter

  postgres:
    image: postgres:16-alpine
    container_name: buhgalter-pg
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "127.0.0.1:5433:5432"
    networks:
      - buhgalter

volumes:
  pgdata:

networks:
  buhgalter:
    driver: bridge
EOF

# Dockerfile
cat > "$BASE/Dockerfile" << 'EOF'
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot/ ./bot/
COPY knowledge_base/ ./knowledge_base/
COPY templates/ ./templates/

CMD ["python", "-m", "bot.main"]
EOF

echo ""
echo "=== Структура создана ==="
echo ""
find "$BASE" -not -path '*/chroma_data/*' | head -50
echo ""
echo "Следующий шаг: cd $BASE && cp .env.example .env && nano .env"
