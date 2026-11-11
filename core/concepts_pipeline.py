"""Пайплайн извлечения концептов из толкований словаря (полный пересчёт).

Этапы соответствуют черновику `utils/построение_концептной_области.py`:
толкования → фильтр ссылок → Stanza → кандидаты → эмбеддинги →
кластеризация → таблицы `Concept` и `Concept_Sense`.

Отличия от черновика:
- кластеризация — average linkage (scipy) над сжатой матрицей расстояний,
  считаемой numpy-блоками (вместо двойного цикла по всем парам);
- при перезаписи таблиц статусы модерации переносятся по совпадению
  канонического имени концепта (и пары «имя — толкование» для связей).

Запускается через management command `manage.py build_concepts`.
"""
import json
import re
import unicodedata
from collections import Counter

import numpy as np
from django.db import transaction

from .models import Concept, ConceptSense, Sense

# Порог объединения кандидатов в кластер — как в черновике
# (0.7 семантика + 0.3 лексика); калибровать по итогам обкатки.
CLUSTER_THRESHOLD = 0.65
EMBEDDING_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"

CONTENT_POS = ("NOUN", "ADJ", "VERB", "ADV")
POS_PRIORITY = {"NOUN": 0, "ADJ": 1, "VERB": 2, "ADV": 3}

# «Ссылочный мусор» в толкованиях: сами толкованием не являются.
REF_PATTERN = re.compile(
    r"(то\s+же,\s+что|уменьш\.?|в\s+сочетании|сравн\.|см\.|увелич\.)",
    re.IGNORECASE,
)

# Размер блока сходства: пиковая память ~BLOCK * N * 4 байт на матрицу
# вместо полной N x N.
SIM_BLOCK = 2000

# Приоритет статусов при переносе: одобренное не должно слететь,
# если рядом завёлся отклонённый одноимённый.
STATUS_PRIORITY = {"approved": 3, "rejected": 2, "unchecked": 1}

# Кандидаты-словесный мусор, прошедший POS-фильтр. «Обычный» сознательно
# НЕ входит: это осмысленная помета «расхожее, частое явление».
CONCEPT_STOPWORDS = {
    "быть", "иметь", "мочь", "стать", "являться",
    "очень", "много", "мало", "совсем", "едва",
}

# Леммы короче — почти всегда шум («е», «со»).
MIN_LEMMA_LENGTH = 3


def normalize_text(text):
    """Убираем ударения и точки (как в черновике)."""
    if not isinstance(text, str):
        return ""
    # Ударение: комбинируемый знак U+0301 (десятичный 769)
    text = text.replace(chr(769), "").replace(".", "")
    return unicodedata.normalize("NFC", text).strip()


def fetch_meanings(limit=None):
    """Толкования для обсчёта: список словарей {sense_id, meaning}."""
    qs = (
        Sense.objects
        .exclude(meaning__isnull=True)
        .exclude(meaning="")
        .order_by("id")
    )
    if limit:
        qs = qs[:limit]
    return list(qs.values("id", "meaning").iterator())


def filter_meanings(meanings):
    """Отбрасываем толкования-ссылки («то же, что», «см.» и т.п.)."""
    return [m for m in meanings if not REF_PATTERN.search(m["meaning"] or "")]


def _is_negated(word, children_by_head):
    """Отрицание, зависящее от слова: дочерний 'advmod' с леммой не/ни."""
    return any(
        w.deprel == "advmod"
        and (w.lemma or "").lower() in {"не", "ни"}
        for w in children_by_head.get(word.id, [])
    )


def _syntactic_context(word, by_id, children_by_head):
    """Слово + содержательный родитель и дети — как в черновике."""
    parent = by_id.get(word.head)
    context = [word]
    if parent is not None and parent.upos in CONTENT_POS:
        context.append(parent)
    context.extend(
        w for w in children_by_head.get(word.id, [])
        if w.upos in CONTENT_POS
    )
    context = sorted({w.id: w for w in context}.values(), key=lambda w: w.id)
    return " ".join(w.text for w in context)


def extract_candidates(meanings, nlp):
    """Stanza-разбор толкований → кандидаты-концепты.

    Тексты нормализуются и гоняются пакетно через nlp.bulk_process: в ~5 раз
    быстрее пословного прогона при точном паритете разбора (замер: скилл
    dialect-graph). bulk_process возвращает документы в порядке входа —
    sense_id восстанавливается zip-ом с исходным списком.
    """
    items = [(item["id"], normalize_text(item["meaning"])) for item in meanings]
    items = [(sense_id, text) for sense_id, text in items if text]
    if not items:
        return []
    docs = nlp.bulk_process([text for _, text in items])

    candidates = []
    for (sense_id, _), doc in zip(items, docs):
        for sentence in doc.sentences:
            words = sentence.words
            by_id = {w.id: w for w in words}
            # Зависимости один раз на предложение: дети по главе нужны
            # и негации, и контексту — вместо скана всех слов на кандидата.
            children_by_head = {}
            for w in words:
                children_by_head.setdefault(w.head, []).append(w)
            for word in words:
                if word.upos not in CONTENT_POS:
                    continue
                lemma = (word.lemma or word.text).lower()
                surface = word.text
                if _is_negated(word, children_by_head):
                    lemma = "не " + lemma
                    surface = "не " + surface
                base = lemma.removeprefix("не ")
                if len(base) < MIN_LEMMA_LENGTH or base in CONCEPT_STOPWORDS:
                    continue
                candidates.append({
                    "sense_id": sense_id,
                    "lemma": lemma,
                    "surface": surface,
                    "upos": word.upos,
                    "syntactic_context": _syntactic_context(word, by_id, children_by_head),
                })
    return candidates


def embed_candidates(candidates, model):
    """Эмбеддинги кандидатов: «Понятие: lemma. Контекст: …» (нормированы).

    batch_size=64 — стартовая настройка; точный подбор под железо —
    отдельным замером encode с разными размерами.
    """
    if not candidates:
        dim = model.get_sentence_embedding_dimension()
        return np.empty((0, dim), dtype=np.float32)
    texts = [
        f"Понятие: {c['lemma']}. Контекст: {c['syntactic_context']}"
        for c in candidates
    ]
    embeddings = model.encode(
        texts,
        batch_size=64,
        normalize_embeddings=True,
        show_progress_bar=True,
        convert_to_numpy=True,
    )
    return np.asarray(embeddings, dtype=np.float32)


def cluster_candidates(candidates, embeddings):
    """Кластеризация average linkage по комбинированному сходству.

    Сходство = 0.7 косинус эмбеддингов + 0.3 косинус char-TFIDF лемм;
    расстояние = 1 - сходство. Дендрограмма режется на расстоянии
    1 - CLUSTER_THRESHOLD: кластер образуется, пока среднее внутрикластерное
    расстояние не превышает порог. Среднее расстояние не даёт «снежного кома»
    single-linkage (бывший мега-кластер «тест» на полсловаря), поэтому кап
    размера компоненты не нужен. Отдельные пары при этом могут оказаться ниже
    порога — осознанный компромисс; замер методов:
    utils/кластеризация/сравнение_методов_кластеризации.md.
    Совпадающие леммы оказываются в одном кластере автоматически: их расстояние 0.
    """
    from scipy.cluster.hierarchy import fcluster, linkage
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.preprocessing import normalize as sk_normalize

    n = len(candidates)
    if n <= 1:
        return list(range(1, n + 1))

    char_matrix = sk_normalize(
        TfidfVectorizer(analyzer="char", ngram_range=(2, 5), min_df=1)
        .fit_transform([c["lemma"] for c in candidates])
    )

    # Сжатая матрица расстояний для scipy linkage — блоками, без полной N x N.
    dist = np.empty(n * (n - 1) // 2, dtype=np.float64)
    pos = 0
    for start in range(0, n, SIM_BLOCK):
        end = min(start + SIM_BLOCK, n)
        semantic = embeddings[start:end] @ embeddings.T
        lexical = char_matrix[start:end] @ char_matrix.T
        combined = 0.7 * semantic + 0.3 * lexical.toarray()
        for r in range(end - start):
            i = start + r
            dist[pos:pos + n - i - 1] = 1.0 - combined[r, i + 1:]
            pos += n - i - 1
    np.clip(dist, 0.0, None, out=dist)  # float-шум вокруг сходства 1.0

    tree = linkage(dist, method="average")
    labels = fcluster(tree, t=1 - CLUSTER_THRESHOLD, criterion="distance")
    return [int(label) for label in labels]


def form_concepts(candidates, embeddings, labels):
    """Кластеры → концепты (имя, формы, частота, centroid) и связи."""
    groups = {}
    for idx, label in enumerate(labels):
        groups.setdefault(label, []).append(idx)

    concepts = []
    links = []
    for indices in groups.values():
        lemmas = [candidates[i]["lemma"] for i in indices]
        pos_by_lemma = Counter(
            (candidates[i]["lemma"], candidates[i]["upos"]) for i in indices
        )
        # Каноническое имя: POS-приоритет, далее частота (как в черновике).
        (name, _), _ = min(
            pos_by_lemma.items(),
            key=lambda kv: (POS_PRIORITY.get(kv[0][1], 10), -kv[1]),
        )
        centroid = embeddings[indices].mean(axis=0)
        centroid /= np.linalg.norm(centroid) or 1.0

        concepts.append({
            "name": name,
            "frequency": len(indices),
            "forms": sorted(set(lemmas)),
            "centroid": centroid.astype(np.float32),
        })

        seen_senses = set()
        for i in indices:
            sense_id = candidates[i]["sense_id"]
            if sense_id not in seen_senses:
                seen_senses.add(sense_id)
                links.append({
                    "name": name,
                    "sense_id": sense_id,
                    "matched_form": candidates[i]["lemma"],
                })
    return concepts, links


def _merge_status(current, new):
    """Более приоритетный из двух статусов (None-safe)."""
    if current is None:
        return new
    if new is None:
        return current
    return current if STATUS_PRIORITY.get(current, 0) >= STATUS_PRIORITY.get(new, 0) else new


@transaction.atomic
def persist(concepts, links):
    """Перезапись таблиц с переносом статусов модерации по имени концепта."""
    old_status = {}
    for name, status in Concept.objects.values_list("name", "status"):
        old_status[name] = _merge_status(old_status.get(name), status)

    old_link_status = {}
    for name, sense_id, status in ConceptSense.objects.values_list(
        "concept__name", "sense_id", "status"
    ):
        key = (name, sense_id)
        old_link_status[key] = _merge_status(old_link_status.get(key), status)

    ConceptSense.objects.all().delete()
    Concept.objects.all().delete()

    # Одноимённые кластеры маловероятны; при коллизии связи уходят к первому.
    id_by_name = {}
    for concept in concepts:
        obj = Concept.objects.create(
            name=concept["name"],
            frequency=concept["frequency"],
            forms=json.dumps(concept["forms"], ensure_ascii=False),
            status=old_status.get(concept["name"], "unchecked"),
            centroid_embedding=concept["centroid"].tobytes(),
        )
        id_by_name.setdefault(concept["name"], obj.id)

    ConceptSense.objects.bulk_create([
        ConceptSense(
            concept_id=id_by_name[link["name"]],
            sense_id=link["sense_id"],
            matched_form=link["matched_form"],
            status=old_link_status.get((link["name"], link["sense_id"]), "unchecked"),
        )
        for link in links
    ])

    return {"concepts": len(concepts), "links": len(links)}


def _stanza_pipeline():
    import stanza

    kwargs = {"processors": "tokenize,pos,lemma,depparse", "use_gpu": False, "verbose": False}
    try:
        return stanza.Pipeline("ru", **kwargs)
    except Exception:
        # Первый запуск — модели ещё не скачаны.
        stanza.download("ru", verbose=False)
        return stanza.Pipeline("ru", **kwargs)


def build_concepts(limit=None, stdout=None):
    """Полный пересчёт концептов. limit — пробный прогон на N толкованиях."""
    def log(message):
        if stdout is not None:
            stdout.write(message + "\n")
        else:
            print(message)

    log("Загрузка толкований…")
    meanings = filter_meanings(fetch_meanings(limit))
    log(f"Толкований после фильтра ссылок: {len(meanings)}")

    log("Загрузка моделей (первый запуск — скачивание)…")
    nlp = _stanza_pipeline()
    from sentence_transformers import SentenceTransformer

    embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)

    log("Извлечение кандидатов (Stanza)…")
    candidates = extract_candidates(meanings, nlp)
    log(f"Кандидатов: {len(candidates)}")

    log("Эмбеддинги…")
    embeddings = embed_candidates(candidates, embedding_model)

    log("Кластеризация…")
    labels = cluster_candidates(candidates, embeddings)

    log("Формирование концептов…")
    concepts, links = form_concepts(candidates, embeddings, labels)

    log("Запись в БД…")
    stats = persist(concepts, links)
    log(f"Готово: {stats['concepts']} концептов, {stats['links']} связей.")
    return stats
