FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev fonts-dejavu-core fontconfig && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot/ ./bot/
COPY knowledge_base/ ./knowledge_base/
COPY templates/ ./templates/
COPY scripts/ ./scripts/

CMD ["python", "-m", "bot.main"]
