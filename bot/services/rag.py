"""Сервис RAG — индексация и поиск по базе знаний через ChromaDB."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import chromadb

from bot.config.settings import settings

logger = logging.getLogger(__name__)

COLLECTION_NAME = "knowledge_base"
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100

_client: Optional[chromadb.HttpClient] = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is None:
        _client = chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
        )
        _collection = _client.get_or_create_collection(COLLECTION_NAME)
    return _collection


def chunk_text(
    text: str,
    size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """Разбивает текст на перекрывающиеся чанки."""
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start += size - overlap
    return chunks


def _read_pdf(file_path: Path) -> str:
    """Извлекает текст из PDF через pdfplumber."""
    try:
        import pdfplumber

        text_parts: list[str] = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        return "\n\n".join(text_parts)
    except Exception as e:
        logger.error("PDF read error (%s): %s", file_path.name, e)
        return ""


def index_file(file_path: Path) -> int:
    """Индексирует .md или .pdf файл в ChromaDB. Возвращает кол-во чанков."""
    suffix = file_path.suffix.lower()
    if suffix == ".md":
        text = file_path.read_text(encoding="utf-8")
    elif suffix == ".pdf":
        text = _read_pdf(file_path)
    else:
        return 0

    chunks = chunk_text(text)
    if not chunks:
        return 0

    collection = _get_collection()
    ids = [f"{file_path.stem}_{i}" for i in range(len(chunks))]
    metadatas = [
        {"source": file_path.name, "chunk": i} for i in range(len(chunks))
    ]
    collection.upsert(ids=ids, documents=chunks, metadatas=metadatas)
    logger.info("Indexed %d chunks from %s", len(chunks), file_path.name)
    return len(chunks)


def index_directory(kb_path: Path) -> int:
    """Индексирует все .md и .pdf файлы рекурсивно."""
    total = 0
    for f in kb_path.rglob("*"):
        if f.suffix.lower() in (".md", ".pdf"):
            total += index_file(f)
    return total


async def search_knowledge(query: str, n_results: int = 5) -> list[str]:
    """Поиск по базе знаний, возвращает релевантные чанки."""
    try:
        collection = _get_collection()
        results = collection.query(query_texts=[query], n_results=n_results)
        if results and results["documents"]:
            return results["documents"][0]
    except Exception as e:
        logger.error("ChromaDB search error: %s", e)
    return []
