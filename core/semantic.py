"""Семантический поиск: эмбеддинги rubert-tiny2 + Qdrant в local-режиме.

SQLite (dialect.db) остаётся источником истины: векторное хранилище —
производный пересобираемый индекс (см. utils/build_semantic_index.py), в нём
только эмбеддинги и payload с id, по которым результат джойнится обратно
к SQLite. Подробности и обоснования — utils/«заметки по векторной базе
данных.md». Клиентский код совместим с серверным Qdrant: переход на
`QdrantClient(url=...)` при росте нагрузки — замена одной строки.

Вектор документа собирается на индексации как взвешенная сумма компонентов
(толкование перевешивает примеры — обратная связь «сыроежка»). Здесь, на
поиске, дополнительно: дословное вхождение запроса в слово/формы карточки
(LEXICAL_BOOST) поднимает такие хиты выше любой семантической близости,
а фильтры (рубрики/районы/части речи) работают как предфильтрация Qdrant.
"""
import re
import threading
from pathlib import Path

from django.conf import settings
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchAny

COLLECTION = "dictionary_senses"
# e5-small, копия лежит в проекте (models/e5-small) — сеть не нужна.
# Запросы эмбеддятся с «query: …», документы индекса — с «passage: …»
# (utils/build_semantic_index.py). rubert-tiny2 заменена — её вектора
# в пищевом домене насыщены, дискриминации не даёт.
EMBED_MODEL_NAME = str(Path(settings.BASE_DIR) / "models" / "e5-small")
STORE_PATH = Path(settings.BASE_DIR) / "qdrant_storage"
TOP_K = 20
# Пул для переранжирования: берём втрое больше хитов, чем отдаём —
# буст словоформы может поднять точный лексический матч из глубины топа.
RERANK_POOL = TOP_K * 3
# Дословное вхождение запроса в слово/формы карточки: +буст к косинусу.
# Между бустнутыми порядок сохраняется (буст одинаковый).
# Дословный буст ПОДКАТЕГОРИЙ намеренно не делаем: за дословную рубрику
# отвечает фильтр; семантический же сигнал рубрики («сыроежки» → грибы)
# уже живёт в векторе — subcats входят в смысловой блок документа.
LEXICAL_BOOST = 0.3

_client = None
_embedder = None
_warm_lock = threading.Lock()


def _plain(text):
    """Текст без ударений (комбинируемый акут) — как _plain в core/views.py."""
    return re.sub(r"\u0301", "", text or "").lower()


def get_client():
    global _client
    if _client is None:
        _client = QdrantClient(path=str(STORE_PATH))
    return _client


def get_embedder():
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer(EMBED_MODEL_NAME)
    return _embedder


def is_warm():
    """Модель загружена в память (первый запуск — ~25 с, дальше мгновенно)."""
    return _embedder is not None


def ensure_warm():
    """Фоновая загрузка модели. Статус-эндпоинт дёргает это заранее —
    пока пользователь включает переключатель и набирает запрос, модель
    уже греется."""
    if _embedder is None:
        with _warm_lock:
            if _embedder is None:
                threading.Thread(target=get_embedder, daemon=True).start()


def status():
    return {
        "available": index_available(),
        "warm": is_warm(),
        "model": EMBED_MODEL_NAME,
    }


def index_available():
    client = get_client()
    return (
        client.collection_exists(COLLECTION)
        and client.get_collection(COLLECTION).points_count > 0
    )


def embed_query(query):
    model = get_embedder()
    return model.encode([f"query: {query}"], normalize_embeddings=True).tolist()[0]


def _payload_filter(filters):
    """Фильтры точного поиска -> предфильтрация Qdrant: ранжирование
    считается только по карточкам, прошедшим фильтры (а не «топ-20, потом
    выкинуть лишнее»)."""
    conditions = []
    for name, field in (
        ("subcategories", "subcats"),
        ("regions", "regions"),
        ("pos", "pos"),
    ):
        values = [value for value in (filters or {}).get(name) or [] if value]
        if values:
            conditions.append(FieldCondition(key=field, match=MatchAny(any=values)))
    return Filter(must=conditions) if conditions else None


def _lexical_boost(payload, query_plain):
    """Буст за дословное вхождение запроса в слово/формы карточки.
    Подкатегории бустом не обрабатываем — за дословную рубрику отвечает
    фильтр (см. LEXICAL_BOOST выше)."""
    word = payload.get("word") or ""
    forms = payload.get("forms") or ""
    if not query_plain:
        return 0.0
    return LEXICAL_BOOST if (
        query_plain in word or query_plain in forms or word in query_plain
    ) else 0.0


def semantic_search(query, limit=TOP_K, filters=None):
    """Топ близких толкований: [{sense_id, entry_id, word, score}, ...].

    Точные совпадения словоформы (слово/формы карточки содержат запрос)
    бустятся и всегда оказываются выше чисто семантических хитов.
    Возвращает None, если запрос пуст или индекс ещё не собран — вызывающий
    код трактует None как «семантика недоступна». Ошибки движка не ловим
    здесь: view оборачивает вызов, чтобы семантика не роняла точный поиск.
    """
    query = (query or "").strip()
    if not query or not index_available():
        return None
    query_plain = _plain(query)
    hits = get_client().query_points(
        collection_name=COLLECTION,
        query=embed_query(query),
        limit=RERANK_POOL,
        query_filter=_payload_filter(filters),
    ).points
    ranked = sorted(
        hits,
        key=lambda hit: hit.score + _lexical_boost(hit.payload, query_plain),
        reverse=True,
    )[:limit]
    return [
        {
            "sense_id": hit.payload["sense_id"],
            "entry_id": hit.payload["entry_id"],
            "word": hit.payload["word"],
            "score": hit.score,
        }
        for hit in ranked
    ]
