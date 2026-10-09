# core/views.py
import json
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.core.paginator import Paginator
from .filters import LexicalEntryFilter  
from .models import Category, LexicalEntry, Region


def _meanings(entry):
    """Значения лексемы из связанных Sense."""
    return "; ".join(
        meaning
        for meaning in entry.senses.values_list("meaning", flat=True)
        if meaning
    )


@require_POST
def search_api(request):
    data = json.loads(request.body)

    qs = LexicalEntry.objects.prefetch_related(
        "subcategories",
        "texts__region",
        "senses",
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
        2: "subcategories__name",
        3: "-subcategories__name",
    }
    filtered_qs = filtered_qs.order_by(order_map.get(order, "word")).distinct()

    paginator = Paginator(filtered_qs, 20)
    page_obj = paginator.get_page(int(data.get("page", 1)))
    selected_regions = set(data.get("regions", []))

    results = []
    for entry in page_obj:
        examples = []
        region_names = set()

        for text_obj in entry.texts.all():
            region_name = text_obj.region.name if text_obj.region else None

            if selected_regions and region_name not in selected_regions:
                continue

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
            "subcategories": list(
                entry.subcategories.values_list("name", flat=True)
            ),
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

    qs = LexicalEntry.objects.prefetch_related("texts__region", "senses")
    if search:
        qs = qs.filter(word__icontains=search)

    results = []
    for entry in qs[:50]:
        regions = {
            text_obj.region.name
            for text_obj in entry.texts.all()
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