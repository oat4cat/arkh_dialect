# core/views.py
import json
import re
from collections import Counter
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.core.paginator import Paginator
from .filters import LexicalEntryFilter
from .models import (
    Category, ConceptSense, LexicalEntry, Region, Sense, SenseRelation,
    SenseSubcategory,
)
from .semantic import ensure_warm, semantic_search, status as semantic_status


def _meanings(entry):
    """Значения лексемы из связанных Sense (для попапов атласа)."""
    return "; ".join(
        sense.meaning
        for sense in entry.senses.all()
        if sense.meaning
    )


def _plain(text):
    """Текст без ударений, в нижнем регистре — для сопоставления слов."""
    return re.sub(r"\u0301", "", text or "").lower()


def _derivation_references(entry):
    """Отношения производности, где лексема карточки — производная
    (target): «уменьш. от воло́га» -> ссылка на волога (source)."""
    return [
        {
            "type": rel.relation_type,
            "word": rel.source_lexeme.word,
            "accent": rel.source_lexeme.accent or "",
            "sense_number": None,
        }
        for rel in entry.relations_to.all()
    ]


def _senses_payload(entry, selected_regions):
    """Значения лексемы для карточки: примеры фильтруются по выбранным
    районам, отсылки из SenseRelation/LexicalRelation цепляются к значению,
    чьё толкование содержит целевое слово (иначе — к первому значению)."""
    senses = sorted(entry.senses.all(), key=lambda s: s.sense_number or 0)

    references = [
        {
            "type": rel.relation_type,
            "word": rel.target_sense.lexical_entry.word,
            "accent": rel.target_sense.lexical_entry.accent or "",
            "sense_number": rel.target_sense.sense_number,
        }
        for sense in senses
        for rel in sense.relations_from.all()
    ]
    for ref in _derivation_references(entry):
        if ref not in references:
            references.append(ref)

    payload = []
    seen_text_ids = set()
    for sense in senses:
        examples = []
        for text_obj in sense.texts.all():
            if text_obj.pk in seen_text_ids:
                continue
            region_name = text_obj.region.name if text_obj.region else None
            if selected_regions and region_name not in selected_regions:
                continue
            seen_text_ids.add(text_obj.pk)
            examples.append({"text": text_obj.text, "region": region_name})

        payload.append({
            "sense_id": sense.id,
            "sense_number": sense.sense_number,
            "meaning": sense.meaning or "",
            "references": [],
            "examples": examples,
        })

    # Привязка отсылок к значениям: ищем целевое слово в тексте толкования
    for ref in references:
        target = _plain(ref["word"])
        placed = False
        for sense, item in zip(senses, payload):
            if target and target in _plain(sense.meaning):
                item["references"].append(ref)
                placed = True
                break
        if not placed and payload:
            payload[0]["references"].append(ref)

    return payload


def _entry_payload(entry, selected_regions):
    """Карточка лексемы для JSON-ответа (контракт фронта: createWordArticle).

    Возвращает None, если выбранные районы отсекли все примеры значений."""
    region_names = set()
    subcategory_names = dict.fromkeys(
        subcategory.name
        for sense in entry.senses.all()
        for subcategory in sense.subcategories.all()
    )

    senses = _senses_payload(entry, selected_regions)

    if selected_regions and not any(s["examples"] for s in senses):
        return None

    for sense in senses:
        for example in sense["examples"]:
            if example["region"]:
                region_names.add(example["region"])

    return {
        "word": entry.word,
        "accent": entry.accent,
        "grammatical_features": entry.grammatical_features,
        "forms": [
            {
                "form": form.form,
                "accent": form.accent,
                "grammatical_features": form.grammatical_features,
            }
            for form in entry.lexical_forms.all()
        ],
        "subcategories": list(subcategory_names),
        "regions": list(region_names),
        "senses": senses,
    }


@require_POST
def search_api(request):
    data = json.loads(request.body)

    qs = LexicalEntry.objects.prefetch_related(
        "senses__texts__region",
        "senses__subcategories",
        "senses__relations_from__target_sense__lexical_entry",
        "relations_to__source_lexeme",
        "lexical_forms",
    )

    entry_filter = LexicalEntryFilter(
        data={
            "word": data.get("word", ""),
            "subcategories": data.get("subcategories", []),
            "regions": data.get("regions", []),
            "part_of_speech": data.get("pos", []),
        },
        queryset=qs,
    )

    filtered_qs = entry_filter.qs

    order = int(data.get("order", 0))
    order_map = {
        0: "word",
        1: "-word",
        2: "senses__subcategories__name",
        3: "-senses__subcategories__name",
    }
    filtered_qs = filtered_qs.order_by(order_map.get(order, "word")).distinct()
    selected_regions = set(data.get("regions", []))
    word_query = (data.get("word") or "").strip()

    # Режим «поиск по смыслу» (переключатель на странице): точные совпадения
    # первыми, за ними семантика. Без слова режим не включается — семантике
    # нечего эмбеддить, остаётся обычный обзор с фильтрами.
    if data.get("use_semantic") and word_query:
        return _semantic_mode_response(filtered_qs, data, word_query, selected_regions)

    paginator = Paginator(filtered_qs, 20)
    page_obj = paginator.get_page(int(data.get("page", 1)))

    results = []
    for entry in page_obj:
        payload = _entry_payload(entry, selected_regions)
        if payload is not None:
            results.append(payload)

    # Авто-fallback, когда переключатель выключен: точный поиск пуст и задано
    # только слово (с фильтрами не подмешиваем — иначе неотфильтрованный
    # векторный результат нельзя было бы отличить от отфильтрованного точного).
    # Хиты Qdrant джойнятся обратно к SQLite — источнику истины.
    semantic = False
    if (
        not results
        and word_query
        and not data.get("subcategories")
        and not selected_regions
        and not data.get("pos")
    ):
        try:
            hits = semantic_search(word_query)
        except Exception:
            hits = None  # семантика не должна ронять точный поиск
        if hits:
            results = _semantic_results(hits)
            semantic = bool(results)

    return JsonResponse({
        "results": results,
        "semantic": semantic,
        "has_next": page_obj.has_next(),
        "has_prev": page_obj.has_previous(),
        "current_page": page_obj.number,
        "total_pages": paginator.num_pages,
    })


# Сколько лексем показываем на семантический запрос: как страница точного
# поиска (Paginator там по 20). Пагинации у fallback-режима нет — точный
# поиск пуст, листать нечего.
SEMANTIC_RESULT_LIMIT = 20


def _semantic_results(hits, limit=SEMANTIC_RESULT_LIMIT, exclude_entry_ids=frozenset()):
    """Карточки для семантических совпадений.

    Векторный поиск возвращает толкования; лексемы выводятся по одному разу
    в порядке лучшего хита (одна лексема может дать несколько хитов — её
    разные значения). exclude_entry_ids — уже выведенные точной частью
    (режим «поиск по смыслу»), повторять их не нужно. Данные карточек —
    из SQLite, как у точного поиска."""
    senses = (
        Sense.objects
        .filter(id__in=[hit["sense_id"] for hit in hits])
        .select_related("lexical_entry")
    )
    senses_by_id = {sense.id: sense for sense in senses}

    entry_order = []
    seen = set()
    for hit in hits:
        sense = senses_by_id.get(hit["sense_id"])
        if (
            not sense
            or sense.lexical_entry_id in seen
            or sense.lexical_entry_id in exclude_entry_ids
        ):
            continue
        seen.add(sense.lexical_entry_id)
        entry_order.append(sense.lexical_entry_id)

    entries = LexicalEntry.objects.filter(id__in=entry_order).prefetch_related(
        "senses__texts__region",
        "senses__subcategories",
        "senses__relations_from__target_sense__lexical_entry",
        "relations_to__source_lexeme",
        "lexical_forms",
    )
    entries_by_id = {entry.id: entry for entry in entries}

    results = []
    for entry_id in entry_order[:limit]:
        entry = entries_by_id.get(entry_id)
        if entry:
            results.append(_entry_payload(entry, set()))
    return results


def _semantic_mode_response(filtered_qs, data, word_query, selected_regions):
    """Ответ режима «поиск по смыслу»: точные совпадения словоформы первыми
    (обычный поиск с фильтрами, без пагинации), за ними семантические хиты.
    Фильтры уходят в Qdrant как предфильтрация: ранжирование считается только
    по карточкам, прошедшим фильтры, а не «топ-20, потом выкинуть лишнее».
    Одна страница, пагинации нет."""
    exact_results = []
    exact_ids = set()
    for entry in filtered_qs[:SEMANTIC_RESULT_LIMIT]:
        payload = _entry_payload(entry, selected_regions)
        if payload is not None:
            exact_results.append(payload)
            exact_ids.add(entry.pk)

    sem_results = []
    try:
        hits = semantic_search(
            word_query,
            filters={
                "subcategories": data.get("subcategories", []),
                "regions": list(selected_regions),
                "pos": data.get("pos", []),
            },
        )
        if hits:
            sem_results = _semantic_results(hits, exclude_entry_ids=exact_ids)
    except Exception:
        pass  # семантика не должна ронять точный поиск

    return JsonResponse({
        "results": exact_results + sem_results,
        "semantic": True,
        "semantic_exact": len(exact_results),
        "has_next": False,
        "has_prev": False,
        "current_page": 1,
        "total_pages": 1,
    })


@require_GET
def semantic_status_api(request):
    """Статус семантического поиска для фронта: индекс собран, модель
    прогрета. Холодную модель греет фоново — к первому запросу пользователя
    загрузка уже идёт или завершена."""
    ensure_warm()
    return JsonResponse(semantic_status())


@require_GET
def map_api(request):
    search = request.GET.get("search", "").strip()

    qs = LexicalEntry.objects.prefetch_related("senses__texts__region")
    if search:
        qs = qs.filter(word__icontains=search)

    results = []
    for entry in qs[:50]:
        regions = {
            text_obj.region.name
            for sense in entry.senses.all()
            for text_obj in sense.texts.all()
            if text_obj.region
        }

        for region in regions:
            results.append({
                "word": entry.word,
                "accent": entry.accent,
                "meaning": _meanings(entry),
                "grammatical_features": entry.grammatical_features,
                "region": region,
            })

    return JsonResponse(results, safe=False)


@require_GET
def get_regions_api(request):
    regions = Region.objects.values("name").order_by("name")
    return JsonResponse(list(regions), safe=False)


@require_GET
def get_categories_api(request):
    categories = Category.objects.prefetch_related(
        "subcategories"
    ).order_by("name")

    data = []
    for category in categories:
        data.append({
            "category": category.name,
            "subcategories": list(
                category.subcategories.values("name").order_by("name")
            ),
        })

    return JsonResponse(data, safe=False)


@require_GET
def get_pos_api(request):
    pos_list = (
        LexicalEntry.objects
        .values_list("part_of_speech", flat=True)
        .distinct()
        .order_by("part_of_speech")
    )
    pos_list = [pos for pos in pos_list if pos and pos.strip()]
    return JsonResponse(pos_list, safe=False)


def _subcategory_names(sense):
    """Тематические подкатегории толкования."""
    return [subcategory.name for subcategory in sense.subcategories.all()]


# Сколько соседей показывать на один концепт в карточке по умолчанию.
# Хабы собирают 1000+ членов; без лимита JSON раздувается до сотен килобайт.
# Остальные связи никуда не деваются — в БД хранятся все, лимит поднимается
# параметром limit (ползунок в карточке).
MAX_NEIGHBORS_PER_CONCEPT = 5
# Жёсткий потолок «соседей на понятие» для ползунка. Конфиг, не метрика:
# значение — 95-й процентиль размеров кластеров на корпусе 3-го тома.
# Медиана (2) и среднее (7.4) слишком малы для потолка (utils/кластеризация/
# метрики_кластеризации.html); p95 ≈ 28 покрывает полностью 95% кластеров
# и обрезает только хвост хабов. После пересборки концептов (build_concepts)
# пересчитать: sorted(Concept.frequency)[int(N * 0.95)].
MAX_NEIGHBORS_HARD_CAP = 28


def _neighbor_payload(sense, link, subcategories, shared_concepts, is_equivalent):
    """Соседнее толкование (чужой лексемы) для узла графа."""
    return {
        "word": sense.lexical_entry.word,
        "accent": sense.lexical_entry.accent or "",
        "sense_id": sense.id,
        "meaning": sense.meaning or "",
        "status": link.status,
        "subcategories": subcategories,
        # Близость к слову-корню: общие концепты весят больше, эквивалентность
        # («то же, что») выступает tie-break выше алфавита.
        "score": shared_concepts * 2 + (1 if is_equivalent else 0),
    }


def _concept_payload(concept, member_links, senses_by_id, subcats_by_sense,
                     own_sense_ids, shared_by_sense, equivalent_ids, limit):
    """Концепт и топ его чужих толкований для карточки (с полным числом).

    Топ выбирается по близости к слову-корню (см. score), размер — limit."""
    neighbors = [
        _neighbor_payload(
            senses_by_id[link.sense_id], link,
            subcats_by_sense.get(link.sense_id, []),
            shared_by_sense.get(link.sense_id, 0),
            link.sense_id in equivalent_ids,
        )
        for link in member_links
        if link.sense_id not in own_sense_ids
    ]
    neighbors.sort(key=lambda n: (-n["score"], n["word"], n["sense_id"]))
    return {
        "concept_id": concept.id,
        "name": concept.name,
        "status": concept.status,
        "neighbors": neighbors[:limit],
        "neighbors_total": len(neighbors),
    }


@require_GET
def graph_api(request):
    """Граф понятий для карточки: толкования слова → концепты → соседние лексемы."""
    word = request.GET.get("word", "").strip()
    if not word:
        return JsonResponse({"error": "параметр word обязателен"}, status=400)

    senses = list(
        Sense.objects
        .filter(lexical_entry__word=word)
        .prefetch_related("subcategories")
        .order_by("sense_number")
    )

    # Карточка держит раздел графа под каждым значением: sense_id сужает
    # граф до одного толкования (необязательный параметр)
    sense_id = request.GET.get("sense_id")
    if sense_id:
        try:
            senses = [s for s in senses if s.id == int(sense_id)]
        except ValueError:
            pass
    own_sense_ids = {sense.id for sense in senses}

    # Сколько соседей показывать на концепт (ползунок в карточке);
    # без параметра — дефолт, сверху — конфиг-потолок.
    limit = MAX_NEIGHBORS_PER_CONCEPT
    raw_limit = request.GET.get("limit")
    if raw_limit:
        try:
            limit = max(1, min(int(raw_limit), MAX_NEIGHBORS_HARD_CAP))
        except ValueError:
            pass

    # Неотклонённые связи толкований слова с неотклонёнными концептами
    own_links = list(
        ConceptSense.objects
        .filter(sense__in=senses)
        .exclude(status="rejected")
        .exclude(concept__status="rejected")
        .select_related("concept")
    )

    concepts_by_sense = {}
    for link in own_links:
        concepts_by_sense.setdefault(link.sense_id, []).append(link.concept)

    payload = []
    if own_links:
        concept_ids = sorted({link.concept_id for link in own_links})

        # Соседние толкования и подкатегории тянем подзапросами: SQLite
        # получает IN (SELECT ...), а не 1000+ параметров — Django разбивает
        # длинный параметризованный IN на OR-цепочки и упирается в лимит
        # глубины выражения (проверено на хабах вроде «тест», 1200+ членов).
        member_senses_qs = Sense.objects.filter(
            id__in=ConceptSense.objects
            .filter(concept_id__in=concept_ids)
            .values("sense_id")
        )
        member_links_qs = ConceptSense.objects.filter(concept_id__in=concept_ids)
        member_links = list(member_links_qs.exclude(status="rejected"))
        senses_by_id = {
            sense.id: sense
            for sense in member_senses_qs.select_related("lexical_entry")
        }
        subcats_by_sense = {}
        for row in (
            SenseSubcategory.objects
            .filter(sense__in=member_senses_qs)
            .select_related("subcategory")
        ):
            subcats_by_sense.setdefault(row.sense_id, []).append(row.subcategory.name)

        members_by_concept = {}
        for link in member_links:
            members_by_concept.setdefault(link.concept_id, []).append(link)

        # Близость соседа к слову-корню: сколько концептов графа разделяет
        # его толкование с толкованиями слова.
        shared_by_sense = Counter(link.sense_id for link in member_links)

        # Словарная эквивалентность («то же, что») в любую сторону —
        # самая сильная связь соседа со словом.
        own_ids = list(own_sense_ids)
        member_ids_subquery = member_links_qs.values("sense_id")
        equivalent_ids = set(
            SenseRelation.objects.filter(
                source_sense_id__in=own_ids,
                target_sense_id__in=member_ids_subquery,
                relation_type="dictionary_equivalent",
            ).values_list("target_sense_id", flat=True)
        ) | set(
            SenseRelation.objects.filter(
                source_sense_id__in=member_ids_subquery,
                target_sense_id__in=own_ids,
                relation_type="dictionary_equivalent",
            ).values_list("source_sense_id", flat=True)
        )

        for sense in senses:
            concepts = concepts_by_sense.get(sense.id, [])
            if not concepts:
                continue
            payload.append({
                "sense_id": sense.id,
                "meaning": sense.meaning or "",
                "subcategories": _subcategory_names(sense),
                "concepts": [
                    _concept_payload(
                        concept, members_by_concept.get(concept.id, []),
                        senses_by_id, subcats_by_sense, own_sense_ids,
                        shared_by_sense, equivalent_ids, limit,
                    )
                    for concept in concepts
                ],
            })

    return JsonResponse({
        "word": word,
        "senses": payload,
        "sense_id": int(sense_id) if sense_id and sense_id.isdigit() else None,
        "limit": limit,
        "max_limit": MAX_NEIGHBORS_HARD_CAP,
    })