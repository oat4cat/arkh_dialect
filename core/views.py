# core/views.py
import json
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.core.paginator import Paginator
from .filters import LexicalEntryFilter  
from .models import Category, ConceptSense, LexicalEntry, Region, Sense, SenseSubcategory


def _meanings(entry):
    """Значения лексемы из связанных Sense."""
    return "; ".join(
        sense.meaning
        for sense in entry.senses.all()
        if sense.meaning
    )


@require_POST
def search_api(request):
    data = json.loads(request.body)

    qs = LexicalEntry.objects.prefetch_related(
        "senses__texts__region",
        "senses__subcategories",
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

    paginator = Paginator(filtered_qs, 20)
    page_obj = paginator.get_page(int(data.get("page", 1)))
    selected_regions = set(data.get("regions", []))

    results = []
    for entry in page_obj:
        examples = []
        region_names = set()
        seen_text_ids = set()
        subcategory_names = dict.fromkeys(
            subcategory.name
            for sense in entry.senses.all()
            for subcategory in sense.subcategories.all()
        )

        for sense in entry.senses.all():
            for text_obj in sense.texts.all():
                if text_obj.pk in seen_text_ids:
                    continue

                region_name = text_obj.region.name if text_obj.region else None

                if selected_regions and region_name not in selected_regions:
                    continue

                seen_text_ids.add(text_obj.pk)
                examples.append({
                    "text": text_obj.text,
                    "region": region_name,
                })
                if region_name:
                    region_names.add(region_name)

        if selected_regions and not examples:
            continue

        results.append({
            "word": entry.word,
            "accent": entry.accent,
            "meaning": _meanings(entry),
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
            "examples": examples,
        })

    return JsonResponse({
        "results": results,
        "has_next": page_obj.has_next(),
        "has_prev": page_obj.has_previous(),
        "current_page": page_obj.number,
        "total_pages": paginator.num_pages,
    })


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


# Сколько соседей показывать на один концепт в карточке. Хабы вроде «тест»
# собирают 1000+ членов; без лимита JSON раздувается до сотен килобайт.
# Остальные связи никуда не деваются — в БД хранятся все, это ограничение
# только отображения (полный список открывается отдельно, позже).
MAX_NEIGHBORS_PER_CONCEPT = 5


def _neighbor_payload(sense, link, subcategories):
    """Соседнее толкование (чужой лексемы) для узла графа."""
    return {
        "word": sense.lexical_entry.word,
        "accent": sense.lexical_entry.accent or "",
        "sense_id": sense.id,
        "meaning": sense.meaning or "",
        "status": link.status,
        "subcategories": subcategories,
    }


def _concept_payload(concept, member_links, senses_by_id, subcats_by_sense, own_sense_ids):
    """Концепт и топ его чужих толкований для карточки (с полным числом)."""
    neighbors = [
        _neighbor_payload(
            senses_by_id[link.sense_id], link,
            subcats_by_sense.get(link.sense_id, []),
        )
        for link in member_links
        if link.sense_id not in own_sense_ids
    ]
    neighbors.sort(key=lambda n: (n["word"], n["sense_id"]))
    return {
        "concept_id": concept.id,
        "name": concept.name,
        "status": concept.status,
        "neighbors": neighbors[:MAX_NEIGHBORS_PER_CONCEPT],
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
    own_sense_ids = {sense.id for sense in senses}

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
        member_links = list(
            ConceptSense.objects
            .filter(concept_id__in=concept_ids)
            .exclude(status="rejected")
        )
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
                    )
                    for concept in concepts
                ],
            })

    return JsonResponse({"word": word, "senses": payload})